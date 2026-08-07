"""T21.1 legacy step 21.B: complete formal check execution (SPEC §4.5).

``execute_formal_plan`` invokes every frozen request of one
``FormalValidationPlanV1`` exactly once in plan order through a fresh
Task 18 execution boundary — one fresh identity-bound materialization
root per request (T18.2), one ``ExecutionRequestV1`` re-bound to the
frozen built-in profile (a drifted plan fails closed
``VALIDATION_ENVIRONMENT_CHANGED`` before any container call), the
closed ``DockerExecutionPortV1`` call, the sealed cleanup verdict, and
the authoritative parse of the bounded raw evidence (the T19.1 parsers
over the T20.1 frozen argv).  The returned ``FormalValidationEvidenceV1``
carries the complete ordered raw/check/teardown/cleanup/timeout/residual
evidence so missing, duplicate, or partial execution remains explicit
and non-success.  Check selection, plan mutation, success evaluation,
loop return, and approval creation remain out of scope (GREEN-4).
"""

from __future__ import annotations

import hashlib
import json
import shutil
import tempfile
from pathlib import Path
from typing import Annotated, Literal, Protocol, TypeAlias

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    Strict,
    StrictStr,
    ValidationError,
    field_validator,
    model_validator,
)

from vespercode.canonical.digest import domain_digest
from vespercode.canonical.json_v1 import CanonicalValueV1
from vespercode.contracts.evidence import _DIGEST_RE
from vespercode.contracts.optional import AbsentV1, PresentV1
from vespercode.execution.cleanup import (
    ExecutionCleanupResultV1,
    finalize_execution,
)
from vespercode.execution.docker_executor import RawExecutionResultV1
from vespercode.execution.docker_profile import (
    DockerExecutionProfileV1,
    ExecutionRequestV1,
    _FROZEN_CPUS,
    _FROZEN_ENVIRONMENT_VARIABLES,
    _FROZEN_MAX_OUTPUT_BYTES,
    _FROZEN_MEMORY_BYTES,
    _FROZEN_PIDS_LIMIT,
    _FROZEN_TMPFS_SIZE_BYTES,
)
from vespercode.execution.materialization import (
    MaterializationError,
    MaterializedCandidateV1,
    allocate_execution_root,
    materialize_candidate,
)
from vespercode.profiles.reference import (
    ReferenceProfileManifestV1,
    load_reference_profile,
)
from vespercode.validation.check_result import (
    CheckResultV1,
    _raw_evidence_digest,
    parse_mypy_result,
    parse_ruff_result,
)
from vespercode.validation.formal_plan import (
    FormalPytestExpectationV1,
    FormalValidationPlanV1,
    FormalValidationRequestV1,
)
from vespercode.validation.pytest_evidence import (
    PytestEvidenceV1,
    PytestReportExpectationV1,
    _extract_channel_document,
    parse_pytest_evidence,
)
from vespercode.validation.python_adapter import expected_argv

# The frozen in-container workspace mount (SPEC §1.4.5).
_FROZEN_WORKSPACE = "/workspace"

# The deterministic per-run root base prefix (the zero-residue discipline:
# every fresh root lives under one per-run base that the finally backstop
# removes, so no root can survive a run).
_BASE_PREFIX = "vesper-formal-"

FormalRequestRejectionCodeV1 = Literal[
    "TREE_INTEGRITY_FAILED",
    "VALIDATION_ENVIRONMENT_CHANGED",
]
"""The closed pre-execution rejection codes of one frozen request."""


class FormalRequestRejectionV1(BaseModel):
    """One closed pre-execution rejection of one frozen request.

    ``TREE_INTEGRITY_FAILED`` is the materialization boundary failure
    and ``VALIDATION_ENVIRONMENT_CHANGED`` the frozen built-in profile
    re-binding failure; both occur before any container call and make
    the request's execution explicitly missing (never silently skipped).
    """

    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal[1]
    code: FormalRequestRejectionCodeV1
    message: StrictStr

    @field_validator("schema_version", mode="before")
    @classmethod
    def _schema_version_is_exact_int(cls, value: object) -> object:
        if not isinstance(value, int) or isinstance(value, bool):
            raise ValueError("schema_version must be the decimal integer 1")
        return value


OptionalFormalRequestRejectionV1: TypeAlias = Annotated[
    AbsentV1 | PresentV1[FormalRequestRejectionV1],
    Field(discriminator="kind"),
]
"""Closed optional rejection: ABSENT exactly when the request executed."""

OptionalRawExecutionResultV1: TypeAlias = Annotated[
    AbsentV1 | PresentV1[RawExecutionResultV1],
    Field(discriminator="kind"),
]
OptionalExecutionCleanupResultV1: TypeAlias = Annotated[
    AbsentV1 | PresentV1[ExecutionCleanupResultV1],
    Field(discriminator="kind"),
]
OptionalPytestEvidenceV1: TypeAlias = Annotated[
    AbsentV1 | PresentV1[PytestEvidenceV1],
    Field(discriminator="kind"),
]
OptionalCheckResultV1: TypeAlias = Annotated[
    AbsentV1 | PresentV1[CheckResultV1],
    Field(discriminator="kind"),
]
OptionalParseErrorV1: TypeAlias = Annotated[
    AbsentV1 | PresentV1[StrictStr],
    Field(discriminator="kind"),
]


class FormalRequestEvidenceV1(BaseModel):
    """One complete ordered evidence row of one frozen request.

    Sealed value fields: the exact request identity and check kind, the
    closed pre-execution rejection (exactly when the request never ran),
    the complete raw evidence and the sealed cleanup/teardown verdict of
    the Task 18 boundary, the parsed authoritative check evidence
    (``pytest_evidence`` for the pytest checks, ``tool_result`` for the
    tool checks), and the closed parse error exactly when the
    authoritative evidence could not be produced — so timeout, error,
    and residual facts are never hidden as success.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal[1]
    request_id: StrictStr
    check_kind: Literal["COLLECT_ONLY", "FULL_PYTEST", "RUFF", "MYPY"]
    rejection: OptionalFormalRequestRejectionV1
    raw: RawExecutionResultV1 | None
    cleanup: ExecutionCleanupResultV1 | None
    pytest_evidence: OptionalPytestEvidenceV1
    tool_result: OptionalCheckResultV1
    parse_error: OptionalParseErrorV1

    @field_validator("schema_version", mode="before")
    @classmethod
    def _schema_version_is_exact_int(cls, value: object) -> object:
        if not isinstance(value, int) or isinstance(value, bool):
            raise ValueError("schema_version must be the decimal integer 1")
        return value

    @field_validator("request_id")
    @classmethod
    def _request_id_is_non_empty(cls, value: str) -> str:
        if value == "":
            raise ValueError("request ids must be non-empty")
        return value

    @model_validator(mode="after")
    def _require_closed_row_shape(self) -> FormalRequestEvidenceV1:
        is_rejected = isinstance(self.rejection, PresentV1)
        if is_rejected:
            if self.raw is not None or self.cleanup is not None:
                raise ValueError("rejected requests carry no raw or cleanup evidence")
            if (
                not isinstance(self.pytest_evidence, AbsentV1)
                or not isinstance(self.tool_result, AbsentV1)
                or not isinstance(self.parse_error, AbsentV1)
            ):
                raise ValueError(
                    "rejected requests carry no parsed evidence or parse error"
                )
            return self
        if self.raw is None or self.cleanup is None:
            raise ValueError("executed requests require raw and cleanup evidence")
        if self.raw.request_id != self.request_id:
            raise ValueError(
                "raw evidence must bind the exact request identity of the row"
            )
        is_pytest = self.check_kind in ("COLLECT_ONLY", "FULL_PYTEST")
        if is_pytest:
            if not isinstance(self.tool_result, AbsentV1):
                raise ValueError("pytest rows never carry a tool result")
            if isinstance(self.pytest_evidence, PresentV1):
                if not isinstance(self.parse_error, AbsentV1):
                    raise ValueError(
                        "a parsed pytest row cannot also carry a parse error"
                    )
                if self.pytest_evidence.value.run_kind != self.check_kind:
                    raise ValueError(
                        "pytest evidence run_kind must equal the row check kind"
                    )
            elif not isinstance(self.parse_error, PresentV1):
                raise ValueError(
                    "pytest rows require parsed evidence or an explicit parse error"
                )
        else:
            if not isinstance(self.pytest_evidence, AbsentV1):
                raise ValueError("tool rows never carry pytest evidence")
            if not isinstance(self.parse_error, AbsentV1):
                raise ValueError("tool rows never carry a parse error")
            if not isinstance(self.tool_result, PresentV1):
                raise ValueError("tool rows require the closed parsed result")
            result = self.tool_result.value
            if result.check_kind != self.check_kind:
                raise ValueError("tool result check kind must equal the row check kind")
            if result.raw_digest != _raw_evidence_digest(self.raw):
                raise ValueError(
                    "tool result raw_digest must bind the exact raw evidence"
                )
        return self

    @property
    def clean(self) -> bool:
        """True exactly when the row is executed and fully clean: no raw
        failure, no parse error, and the sealed cleanup verdict holds."""
        if isinstance(self.rejection, PresentV1):
            return False
        if self.raw is None or self.raw.error_code is not None:
            return False
        if not isinstance(self.parse_error, AbsentV1):
            return False
        if self.cleanup is None:
            return False
        return (
            self.cleanup.container_removed
            and self.cleanup.materialization_removed
            and self.cleanup.workspace_unchanged
        )


class FormalValidationEvidenceV1(BaseModel):
    """The complete ordered evidence bundle of one formal execution.

    Sealed value fields: the exact executed plan digest, the ordered
    executed request identities, the ordered per-request evidence rows
    (1:1 with the executed identities), the explicit missing request
    identities (rejected rows — execution never started), the explicit
    duplicate request identities (an executed identity seen more than
    once — non-success by construction), the exact ``complete`` boolean
    (true exactly when nothing is missing or duplicated and every row is
    clean), and the §0.1 ``evidence_digest`` binding every other field.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal[1]
    plan_digest: StrictStr
    executed_request_ids: tuple[StrictStr, ...]
    evidence: tuple[FormalRequestEvidenceV1, ...]
    missing_request_ids: tuple[StrictStr, ...]
    duplicate_request_ids: tuple[StrictStr, ...]
    complete: Annotated[bool, Strict()]
    evidence_digest: StrictStr

    @field_validator("schema_version", mode="before")
    @classmethod
    def _schema_version_is_exact_int(cls, value: object) -> object:
        if not isinstance(value, int) or isinstance(value, bool):
            raise ValueError("schema_version must be the decimal integer 1")
        return value

    @field_validator("plan_digest", "evidence_digest")
    @classmethod
    def _digests_have_exact_form(cls, value: str) -> str:
        if _DIGEST_RE.fullmatch(value) is None:
            raise ValueError("must be exactly 64 lowercase hexadecimal characters")
        return value

    @field_validator("executed_request_ids", "missing_request_ids")
    @classmethod
    def _request_ids_are_non_empty(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if any(request_id == "" for request_id in value):
            raise ValueError("request ids must be non-empty")
        return value

    @model_validator(mode="after")
    def _require_closed_completeness(self) -> FormalValidationEvidenceV1:
        executed = tuple(
            row.request_id
            for row in self.evidence
            if isinstance(row.rejection, AbsentV1)
        )
        missing = tuple(
            row.request_id
            for row in self.evidence
            if isinstance(row.rejection, PresentV1)
        )
        if len(self.evidence) != len(executed) + len(missing):
            raise ValueError("every evidence row is either executed or rejected")
        if self.executed_request_ids != executed:
            raise ValueError(
                "executed_request_ids must be the ordered executed row identities"
            )
        if self.missing_request_ids != missing:
            raise ValueError(
                "missing_request_ids must be the ordered rejected row identities"
            )
        if set(self.executed_request_ids) & set(self.missing_request_ids):
            raise ValueError("a request identity cannot be both executed and missing")
        duplicates = tuple(
            sorted(
                {
                    request_id
                    for request_id in self.executed_request_ids
                    if self.executed_request_ids.count(request_id) > 1
                }
            )
        )
        if self.duplicate_request_ids != duplicates:
            raise ValueError(
                "duplicate_request_ids must name every executed identity seen "
                "more than once"
            )
        complete = (
            self.missing_request_ids == ()
            and self.duplicate_request_ids == ()
            and all(row.clean for row in self.evidence)
        )
        if self.complete is not complete:
            raise ValueError("complete must be the exact closed completeness verdict")
        return self

    @model_validator(mode="after")
    def _digest_binds_every_other_field(self) -> FormalValidationEvidenceV1:
        if self.evidence_digest != formal_validation_evidence_digest(self):
            raise ValueError("evidence_digest does not bind the evidence fields")
        return self


class DockerExecutionPortV1(Protocol):
    """The closed execution surface of the formal coordinator (T18.2).

    The real ``DockerExecutor`` satisfies this structurally: one fresh
    container per request over the materialized candidate with bounded
    raw evidence.  The completeness matrix scripts a spy that records
    every exact (request, candidate) call.
    """

    def execute(
        self,
        request: ExecutionRequestV1,
        candidate: MaterializedCandidateV1,
    ) -> RawExecutionResultV1: ...


def _raw_document(raw: RawExecutionResultV1) -> dict[str, CanonicalValueV1]:
    """One raw result in the exact §0.1 evidence-document form."""
    return {
        "request_id": raw.request_id,
        "container_id": raw.container_id,
        "exit_code": (
            {"kind": "ABSENT"}
            if raw.exit_code is None
            else {"kind": "PRESENT", "value": raw.exit_code}
        ),
        "stdout_sha256": hashlib.sha256(raw.stdout).hexdigest(),
        "stderr_sha256": hashlib.sha256(raw.stderr).hexdigest(),
        "output_bytes": raw.output_bytes,
        "timed_out": raw.timed_out,
        "output_limit_exceeded": raw.output_limit_exceeded,
        "container_stopped": raw.container_stopped,
        "error_code": (
            {"kind": "ABSENT"}
            if raw.error_code is None
            else {"kind": "PRESENT", "value": raw.error_code}
        ),
    }


def _cleanup_document(
    cleanup: ExecutionCleanupResultV1,
) -> dict[str, CanonicalValueV1]:
    """One cleanup verdict in the exact §0.1 evidence-document form."""
    residual: CanonicalValueV1
    if cleanup.residual_artifact is None:
        residual = {"kind": "ABSENT"}
    else:
        residual = {
            "kind": "PRESENT",
            "value": {
                "artifact_id": cleanup.residual_artifact.artifact_id,
                "digest": cleanup.residual_artifact.digest.value,
            },
        }
    return {
        "container_removed": cleanup.container_removed,
        "materialization_removed": cleanup.materialization_removed,
        "workspace_unchanged": cleanup.workspace_unchanged,
        "residual_artifact": residual,
    }


def _row_document(row: FormalRequestEvidenceV1) -> dict[str, CanonicalValueV1]:
    """One evidence row in the exact §0.1 document form."""
    if isinstance(row.rejection, PresentV1):
        rejection_document: CanonicalValueV1 = {
            "kind": "PRESENT",
            "value": {
                "code": row.rejection.value.code,
                "message": row.rejection.value.message,
            },
        }
    else:
        rejection_document = {"kind": "ABSENT"}
    if row.raw is None:
        raw_document: CanonicalValueV1 = {"kind": "ABSENT"}
    else:
        raw_document = {"kind": "PRESENT", "value": _raw_document(row.raw)}
    if row.cleanup is None:
        cleanup_document: CanonicalValueV1 = {"kind": "ABSENT"}
    else:
        cleanup_document = {"kind": "PRESENT", "value": _cleanup_document(row.cleanup)}
    if isinstance(row.pytest_evidence, PresentV1):
        pytest_document: CanonicalValueV1 = {
            "kind": "PRESENT",
            "value": row.pytest_evidence.value.integrity_digest,
        }
    else:
        pytest_document = {"kind": "ABSENT"}
    if isinstance(row.tool_result, PresentV1):
        tool_document: CanonicalValueV1 = {
            "kind": "PRESENT",
            "value": row.tool_result.value.raw_digest,
        }
    else:
        tool_document = {"kind": "ABSENT"}
    if isinstance(row.parse_error, PresentV1):
        parse_document: CanonicalValueV1 = {
            "kind": "PRESENT",
            "value": row.parse_error.value,
        }
    else:
        parse_document = {"kind": "ABSENT"}
    return {
        "request_id": row.request_id,
        "check_kind": row.check_kind,
        "rejection": rejection_document,
        "raw": raw_document,
        "cleanup": cleanup_document,
        "pytest_evidence": pytest_document,
        "tool_result": tool_document,
        "parse_error": parse_document,
    }


def _evidence_digest_body(
    *,
    plan_digest: str,
    executed_request_ids: tuple[str, ...],
    evidence: tuple[FormalRequestEvidenceV1, ...],
    missing_request_ids: tuple[str, ...],
    duplicate_request_ids: tuple[str, ...],
    complete: bool,
) -> dict[str, CanonicalValueV1]:
    """The canonical §0.1 digest body of one evidence bundle."""
    return {
        "plan_digest": plan_digest,
        "executed_request_ids": tuple(executed_request_ids),
        "evidence": tuple(_row_document(row) for row in evidence),
        "missing_request_ids": tuple(missing_request_ids),
        "duplicate_request_ids": tuple(duplicate_request_ids),
        "complete": complete,
    }


def _compute_evidence_digest(
    *,
    plan_digest: str,
    executed_request_ids: tuple[str, ...],
    evidence: tuple[FormalRequestEvidenceV1, ...],
    missing_request_ids: tuple[str, ...],
    duplicate_request_ids: tuple[str, ...],
    complete: bool,
) -> str:
    """The §0.1 identity of every exact evidence field except itself."""
    return domain_digest(
        "FormalValidationEvidenceV1",
        1,
        _evidence_digest_body(
            plan_digest=plan_digest,
            executed_request_ids=executed_request_ids,
            evidence=evidence,
            missing_request_ids=missing_request_ids,
            duplicate_request_ids=duplicate_request_ids,
            complete=complete,
        ),
    )


def formal_validation_evidence_digest(
    evidence: FormalValidationEvidenceV1,
) -> str:
    """The §0.1 identity of every exact evidence field except itself."""
    return _compute_evidence_digest(
        plan_digest=evidence.plan_digest,
        executed_request_ids=evidence.executed_request_ids,
        evidence=evidence.evidence,
        missing_request_ids=evidence.missing_request_ids,
        duplicate_request_ids=evidence.duplicate_request_ids,
        complete=evidence.complete,
    )


def _packaged_manifest_bytes() -> bytes:
    """The packaged built-in manifest bytes (profiles/registry pattern)."""
    return (
        Path(__file__).resolve().parents[1]
        / "profiles"
        / "builtin"
        / "reference-profile-v1.json"
    ).read_bytes()


def _load_frozen_manifest() -> ReferenceProfileManifestV1:
    return load_reference_profile(_packaged_manifest_bytes())


def _frozen_execution_profile() -> DockerExecutionProfileV1:
    """The one frozen SPEC §1.4.5 execution profile v1.

    The profile is closed-frozen by ``DockerExecutionProfileV1``'s own
    validators and every ``ExecutionRequestV1`` re-binds the frozen
    manifest/image digests, so a drifted construction can never
    validate — the request fails closed as
    ``VALIDATION_ENVIRONMENT_CHANGED`` instead.
    """
    return DockerExecutionProfileV1.model_validate(
        {
            "schema_version": 1,
            "profile_version": 1,
            "network_mode": "none",
            "user": "10001:10001",
            "read_only_rootfs": True,
            "capabilities_dropped": "ALL",
            "docker_socket_mounted": False,
            "workdir": _FROZEN_WORKSPACE,
            "workspace_mount": {"target": _FROZEN_WORKSPACE, "read_only": True},
            "tmpfs_mount": {"path": "/tmp"},
            "resources": {
                "cpus": _FROZEN_CPUS,
                "memory_bytes": _FROZEN_MEMORY_BYTES,
                "pids_limit": _FROZEN_PIDS_LIMIT,
                "tmpfs_size_bytes": _FROZEN_TMPFS_SIZE_BYTES,
                "max_output_bytes": _FROZEN_MAX_OUTPUT_BYTES,
            },
            "environment": {
                "variables": [
                    {"name": name, "value": value}
                    for name, value in _FROZEN_ENVIRONMENT_VARIABLES
                ]
            },
            "fresh_container_per_check": True,
            "pytest_plugin_autoload_disabled": True,
        }
    )


def _rejected_row(
    request: FormalValidationRequestV1,
    code: FormalRequestRejectionCodeV1,
    message: str,
) -> FormalRequestEvidenceV1:
    """One explicit pre-execution rejection row (the request never ran)."""
    return FormalRequestEvidenceV1(
        schema_version=1,
        request_id=request.request_id,
        check_kind=request.check_kind,
        rejection=PresentV1(
            kind="PRESENT",
            value=FormalRequestRejectionV1(
                schema_version=1, code=code, message=message
            ),
        ),
        raw=None,
        cleanup=None,
        pytest_evidence=AbsentV1(kind="ABSENT"),
        tool_result=AbsentV1(kind="ABSENT"),
        parse_error=AbsentV1(kind="ABSENT"),
    )


def _row_with_parse_error(
    request: FormalValidationRequestV1,
    raw: RawExecutionResultV1,
    cleanup: ExecutionCleanupResultV1,
    error_code: str,
) -> FormalRequestEvidenceV1:
    """One executed row whose authoritative evidence could not be
    produced (the stable parse error is explicit)."""
    return FormalRequestEvidenceV1(
        schema_version=1,
        request_id=request.request_id,
        check_kind=request.check_kind,
        rejection=AbsentV1(kind="ABSENT"),
        raw=raw,
        cleanup=cleanup,
        pytest_evidence=AbsentV1(kind="ABSENT"),
        tool_result=AbsentV1(kind="ABSENT"),
        parse_error=PresentV1(kind="PRESENT", value=error_code),
    )


def _parse_collect_only(
    raw: bytes, expectation: FormalPytestExpectationV1
) -> PytestEvidenceV1 | None:
    """Complete ordered evidence of one collect-only report.

    The collect-only defines the baseline collection, so no prior plan
    exists to bind — the structural report contract (closed schema,
    integrity digest, the COLLECT_ONLY run kind, the frozen plugin
    version, and the bounded event count) is the whole validation
    (T20.2 interpretation).
    """
    if raw == b"":
        return None
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        return None
    document_text, duplicate = _extract_channel_document(text)
    if duplicate:
        return None
    if document_text is None:
        document_text = text
    try:
        document = json.loads(document_text)
    except json.JSONDecodeError:
        return None
    if not isinstance(document, dict):
        return None
    try:
        evidence = PytestEvidenceV1.model_validate(document)
    except ValidationError:
        return None
    if evidence.run_kind != "COLLECT_ONLY":
        return None
    if evidence.report_plugin_version != expectation.report_plugin_version:
        return None
    if len(evidence.events) > expectation.max_events:
        return None
    return evidence


def _parse_request_evidence(
    request: FormalValidationRequestV1,
    raw: RawExecutionResultV1,
    cleanup: ExecutionCleanupResultV1,
    frozen: ReferenceProfileManifestV1,
) -> FormalRequestEvidenceV1:
    """One closed row: raw failure, parse failure, or parsed evidence."""
    if request.check_kind in ("COLLECT_ONLY", "FULL_PYTEST"):
        if raw.error_code == "CHECK_TIMEOUT":
            return _row_with_parse_error(request, raw, cleanup, "CHECK_TIMEOUT")
        if raw.error_code is not None:
            return _row_with_parse_error(request, raw, cleanup, "CHECK_ERROR")
        expectation = request.expectation.pytest
        assert isinstance(expectation, PresentV1)
        if request.check_kind == "COLLECT_ONLY":
            parsed = _parse_collect_only(raw.stdout, expectation.value)
        else:
            outcome = parse_pytest_evidence(
                raw.stdout,
                PytestReportExpectationV1(
                    schema_version=1,
                    run_kind="FULL_PYTEST",
                    planned_node_ids=expectation.value.planned_node_ids,
                    report_plugin_version=expectation.value.report_plugin_version,
                ),
            )
            parsed = outcome.evidence if outcome.error_code is None else None
        if parsed is None:
            return _row_with_parse_error(request, raw, cleanup, "REPORTER_INVALID")
        return FormalRequestEvidenceV1(
            schema_version=1,
            request_id=request.request_id,
            check_kind=request.check_kind,
            rejection=AbsentV1(kind="ABSENT"),
            raw=raw,
            cleanup=cleanup,
            pytest_evidence=PresentV1(kind="PRESENT", value=parsed),
            tool_result=AbsentV1(kind="ABSENT"),
            parse_error=AbsentV1(kind="ABSENT"),
        )
    result: CheckResultV1
    if request.check_kind == "RUFF":
        result = parse_ruff_result(raw, frozen)
    else:
        result = parse_mypy_result(raw, frozen)
    return FormalRequestEvidenceV1(
        schema_version=1,
        request_id=request.request_id,
        check_kind=request.check_kind,
        rejection=AbsentV1(kind="ABSENT"),
        raw=raw,
        cleanup=cleanup,
        pytest_evidence=AbsentV1(kind="ABSENT"),
        tool_result=PresentV1(kind="PRESENT", value=result),
        parse_error=AbsentV1(kind="ABSENT"),
    )


def _execute_request(
    plan: FormalValidationPlanV1,
    request: FormalValidationRequestV1,
    executor: DockerExecutionPortV1,
    frozen: ReferenceProfileManifestV1,
    base: Path,
) -> FormalRequestEvidenceV1:
    """Execute one frozen request exactly once through a fresh Task 18
    boundary and collect its complete ordered evidence."""
    try:
        root = allocate_execution_root(base)
        materialized = materialize_candidate(plan.candidate_tree, root)
    except MaterializationError:
        return _rejected_row(
            request,
            "TREE_INTEGRITY_FAILED",
            "the fresh candidate materialization boundary failed",
        )
    try:
        if request.argv != expected_argv(request.check_kind):
            raise ValueError(
                "argv must equal the frozen adapter command for the check"
            )
        execution_request = ExecutionRequestV1.model_validate(
            {
                "schema_version": 1,
                "request_id": request.request_id,
                "reference_profile_digest": plan.reference_profile_digest,
                "docker_image_digest": plan.docker_image_digest,
                "docker_execution_profile_version": 1,
                "profile": _frozen_execution_profile(),
                "argv": request.argv,
            }
        )
    except ValidationError:
        return _rejected_row(
            request,
            "VALIDATION_ENVIRONMENT_CHANGED",
            "the frozen execution request no longer matches the built-in profile",
        )
    try:
        raw = executor.execute(execution_request, materialized)
    except Exception:
        # The executor's closed contract converts every daemon failure
        # into a closed ``RawExecutionResultV1`` error code (T18.1), so
        # an unexpected raise is a programming error: record the exact
        # request as a closed execution failure instead of losing the
        # partial evidence of the earlier requests.
        raw = RawExecutionResultV1(
            schema_version=1,
            request_id=request.request_id,
            container_id="",
            exit_code=None,
            stdout=b"",
            stderr=b"",
            output_bytes=0,
            timed_out=False,
            output_limit_exceeded=False,
            container_stopped=False,
            error_code="CHECK_EXECUTION_ERROR",
        )
    cleanup = finalize_execution(raw, plan.candidate_tree, materialized)
    return _parse_request_evidence(request, raw, cleanup, frozen)


def _rejected_evidence(
    plan: FormalValidationPlanV1,
    code: FormalRequestRejectionCodeV1,
    message: str,
) -> FormalValidationEvidenceV1:
    """One closed evidence with every request explicitly rejected (the
    frozen profile could not be loaded — zero container calls, never a
    raise out of the coordinator)."""
    rejected_rows = tuple(
        _rejected_row(request, code, message) for request in plan.execution_requests
    )
    executed: tuple[str, ...] = ()
    missing = plan.request_ids
    duplicates: tuple[str, ...] = ()
    complete = False
    digest = _compute_evidence_digest(
        plan_digest=plan.digest,
        executed_request_ids=executed,
        evidence=rejected_rows,
        missing_request_ids=missing,
        duplicate_request_ids=duplicates,
        complete=complete,
    )
    return FormalValidationEvidenceV1(
        schema_version=1,
        plan_digest=plan.digest,
        executed_request_ids=executed,
        evidence=rejected_rows,
        missing_request_ids=missing,
        duplicate_request_ids=duplicates,
        complete=complete,
        evidence_digest=digest,
    )


def execute_formal_plan(
    plan: FormalValidationPlanV1,
    executor: DockerExecutionPortV1,
) -> FormalValidationEvidenceV1:
    """Execute every frozen request exactly once in plan order through a
    fresh Task 18 boundary and return the complete ordered evidence.

    The coordinator never skips, inserts, replaces, or retries a request
    implicitly; the evidence model makes any missing, duplicate, or
    partial execution explicit and non-success (GREEN-1..GREEN-2).  A
    frozen reference profile that cannot be loaded fails closed with
    every request explicitly rejected ``VALIDATION_ENVIRONMENT_CHANGED``
    (zero container calls), never a raise out of the coordinator.
    """
    try:
        frozen = _load_frozen_manifest()
    except Exception:
        return _rejected_evidence(
            plan,
            "VALIDATION_ENVIRONMENT_CHANGED",
            "the frozen reference profile cannot be loaded",
        )
    base = Path(tempfile.mkdtemp(prefix=_BASE_PREFIX))
    rows: list[FormalRequestEvidenceV1] = []
    try:
        for request in plan.execution_requests:
            rows.append(_execute_request(plan, request, executor, frozen, base))
    finally:
        # Zero-residue discipline: every fresh root of this run lives
        # under the per-run base; the backstop removes the whole base
        # (T18.2 mode; a residue-blocked caller backstop owns any
        # surviving artifact identity the cleanup verdict names).
        shutil.rmtree(base, ignore_errors=True)
    executed = tuple(
        row.request_id for row in rows if isinstance(row.rejection, AbsentV1)
    )
    missing = tuple(
        row.request_id for row in rows if isinstance(row.rejection, PresentV1)
    )
    duplicates = tuple(
        sorted(
            {request_id for request_id in executed if executed.count(request_id) > 1}
        )
    )
    complete = missing == () and duplicates == () and all(row.clean for row in rows)
    digest = _compute_evidence_digest(
        plan_digest=plan.digest,
        executed_request_ids=executed,
        evidence=tuple(rows),
        missing_request_ids=missing,
        duplicate_request_ids=duplicates,
        complete=complete,
    )
    return FormalValidationEvidenceV1(
        schema_version=1,
        plan_digest=plan.digest,
        executed_request_ids=executed,
        evidence=tuple(rows),
        missing_request_ids=missing,
        duplicate_request_ids=duplicates,
        complete=complete,
        evidence_digest=digest,
    )

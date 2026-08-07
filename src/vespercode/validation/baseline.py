"""T20.2 legacy step 20.B: stable Baseline orchestration (SPEC §4.5/§1.4.1).

``run_baseline`` executes the frozen six-check Baseline sequence once each
in declared order — collect-only x2, full pytest, target rerun, Ruff, Mypy
— with fresh identity-bound execution boundaries per check (T18.2
materialization + cleanup), consumes the closed Task 19.C evidence
parsers, requires complete stable evidence and the exact Snapshot/plan/
target/reference-profile/environment/collection bindings before any
``ValidationManifestV1`` can be constructed, and returns either one
``PassingBaselineV1`` or one closed ``BaselineBlockedV1`` with stable
evidence refs (GREEN-1..GREEN-4).  Static plan construction, formal
validation, and candidate mutation remain out of scope.

The baseline evaluates in four closed stages:

1.  the plan/Snapshot binding gate (``TREE_INTEGRITY_FAILED``) and the
    frozen request construction (``VALIDATION_ENVIRONMENT_CHANGED``);
2.  per-check execution with fresh boundaries — any raw execution failure
    (``CHECK_TIMEOUT``/``CHECK_ERROR``), a surviving exact container or
    materialization root (``EXECUTION_WORKSPACE_MUTATED``, the zero-residue
    discipline), or report-parse failure (``REPORTER_INVALID``) blocks
    immediately, because the evidence chain is already incomplete and the
    SPEC §4.5 error codes are per-check closed outcomes;
3.  the complete-evidence ``evaluate_runtime_compatibility`` bundle check
    — collection stability, project-tree writes (the workspace-drift
    verdict of the cleanup contract), and check-environment errors surface
    as ``RUNTIME_PROFILE_VIOLATION`` with the exact §1.4.1
    ``violation_kind``;
4.  the §4.5 baseline predicates — every target present, stable
    ``CALL``/``FAIL`` with byte-identical repeated fingerprints, every
    non-target actually executed and ``PASS``, no forbidden pytest
    states, Ruff/Mypy ``PASS`` — blocking as ``TARGET_NOT_FOUND`` /
    ``TARGET_NOT_REPRODUCED`` / ``BASELINE_UNSTABLE`` / ``CHECK_ERROR``.

Only when every predicate holds does one immutable ``PassingBaselineV1``
exist; ``create_validation_manifest`` (manifest.py) then publishes the
single ``ValidationManifestV1``.  A blocked baseline is closed
NO_MANIFEST with zero publication by construction: no manifest object can
be constructed from any blocked evidence.
"""

from __future__ import annotations

import json
import shutil
import tempfile
import uuid
from pathlib import Path
from typing import Annotated, Literal, TypeAlias

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
from vespercode.contracts.evidence import DigestV1, _DIGEST_RE
from vespercode.contracts.optional import AbsentV1, PresentV1
from vespercode.execution.cleanup import (
    finalize_execution,
)
from vespercode.execution.docker_executor import (
    DockerExecutor,
    RawExecutionResultV1,
)
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
    allocate_execution_root,
    materialize_candidate,
)
from vespercode.profiles.reference import (
    ReferenceProfileManifestV1,
    load_reference_profile,
)
from vespercode.trees.candidate import CandidateTreeV1, root_candidate_revision
from vespercode.trees.content_store import ContentObjectStore
from vespercode.trees.snapshot import SnapshotTreeV1
from vespercode.validation.check_result import (
    CheckResultV1,
    _raw_evidence_digest,
    parse_mypy_result,
    parse_ruff_result,
)
from vespercode.validation.failure_fingerprint import (
    FingerprintNormalizationContextV1,
    build_failure_fingerprint,
)
from vespercode.validation.pytest_evidence import (
    MAX_REPORT_EVENTS,
    PytestEvidenceV1,
    PytestReportExpectationV1,
    _extract_channel_document,
    parse_pytest_evidence,
)
from vespercode.validation.python_adapter import BaselineCheckPlanV1
from vespercode.workspace.path_guard import protected_artifact_path

# The frozen in-container workspace mount (SPEC §1.4.5).  Container-side
# output can only ever reference this constant path, never the host
# materialization root, so the fingerprint normalization allowlist is the
# in-container spelling plus the per-check request/container identity.
_FROZEN_WORKSPACE = "/workspace"


def _require_digest_form(value: str) -> str:
    """Reject any spelling that is not exactly 64 lowercase hex chars."""
    if _DIGEST_RE.fullmatch(value) is None:
        raise ValueError("must be exactly 64 lowercase hexadecimal characters")
    return value


def _reject_coerced_schema_version(value: object) -> object:
    """Reject bool/float/string spelling of the integer literal 1."""
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError("schema_version must be the decimal integer 1")
    return value


RuntimeProfileViolationKindV1 = Literal[
    "EXTERNAL_SERVICE_REQUIRED",
    "VCS_RUNTIME_DEPENDENCY",
    "PROJECT_TREE_WRITE",
    "COLLECTION_UNSTABLE",
    "REPORT_INCOMPLETE",
    "CHECK_ENVIRONMENT_ERROR",
]
"""SPEC §1.4.1 ``RuntimeProfileViolationKind`` — the closed violation
vocabulary of the runtime compatibility check."""

OptionalRuntimeViolationKindV1: TypeAlias = Annotated[
    AbsentV1 | PresentV1[RuntimeProfileViolationKindV1],
    Field(discriminator="kind"),
]
"""Closed optional violation kind: ABSENT exactly when the verdict is
COMPATIBLE or the blocked reason is not ``RUNTIME_PROFILE_VIOLATION``."""


class RuntimeCompatibleV1(BaseModel):
    """SPEC §1.4.1 ``COMPATIBLE``: the reference profile binding and the
    §0.1 evidence digest of the complete Baseline evidence bundle."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal[1]
    status: Literal["COMPATIBLE"]
    reference_profile_digest: StrictStr
    evidence_digest: StrictStr

    @field_validator("schema_version", mode="before")
    @classmethod
    def _schema_version_is_exact_int(cls, value: object) -> object:
        return _reject_coerced_schema_version(value)

    @field_validator("reference_profile_digest", "evidence_digest")
    @classmethod
    def _digests_have_exact_form(cls, value: str) -> str:
        return _require_digest_form(value)


class RuntimeBaselineBlockedV1(BaseModel):
    """SPEC §1.4.1 ``BASELINE_BLOCKED``: the structured runtime-profile
    violation with the offending evidence refs."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal[1]
    status: Literal["BASELINE_BLOCKED"]
    reason: Literal["RUNTIME_PROFILE_VIOLATION"]
    violation_kind: RuntimeProfileViolationKindV1
    evidence_refs: tuple[StrictStr, ...]

    @field_validator("schema_version", mode="before")
    @classmethod
    def _schema_version_is_exact_int(cls, value: object) -> object:
        return _reject_coerced_schema_version(value)

    @field_validator("evidence_refs")
    @classmethod
    def _evidence_refs_are_digests(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        for ref in value:
            _require_digest_form(ref)
        return value


RuntimeCompatibilityResultV1: TypeAlias = Annotated[
    RuntimeCompatibleV1 | RuntimeBaselineBlockedV1,
    Field(discriminator="status"),
]
"""SPEC §1.4.1: ``COMPATIBLE | BASELINE_BLOCKED``."""


class BaselineEvidenceBundleV1(BaseModel):
    """The complete closed evidence bundle of one Baseline execution.

    All six checks must have completed and parsed (the caller blocks on
    raw execution and report-parse failures before a bundle exists); the
    six ``workspace_unchanged`` flags are the per-check post-execution
    tree re-verification verdicts of the cleanup contract (SPEC §4.5
    ``EXECUTION_WORKSPACE_MUTATED`` semantics, T18.2).  ``plan_digest``
    binds the bundle to the exact executed plan.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal[1]
    plan_digest: StrictStr
    reference_profile_digest: StrictStr
    collect_only_evidence: tuple[PytestEvidenceV1, PytestEvidenceV1]
    full_pytest_evidence: PytestEvidenceV1
    target_rerun_evidence: PytestEvidenceV1
    ruff_result: CheckResultV1
    mypy_result: CheckResultV1
    workspace_unchanged: tuple[Annotated[bool, Strict()], ...]

    @field_validator("schema_version", mode="before")
    @classmethod
    def _schema_version_is_exact_int(cls, value: object) -> object:
        return _reject_coerced_schema_version(value)

    @field_validator("plan_digest", "reference_profile_digest")
    @classmethod
    def _identity_digests_have_exact_form(cls, value: str) -> str:
        return _require_digest_form(value)

    @field_validator("workspace_unchanged")
    @classmethod
    def _require_six_drift_flags(cls, value: tuple[bool, ...]) -> tuple[bool, ...]:
        if len(value) != 6:
            raise ValueError(
                "workspace_unchanged must carry exactly one flag per Baseline check"
            )
        return value


def _evidence_digest(evidence: PytestEvidenceV1) -> str:
    """The authoritative §0.1 identity of one complete pytest report."""
    return evidence.integrity_digest


def _check_result_digest(result: CheckResultV1) -> str:
    """The authoritative §0.1 raw identity of one Ruff/Mypy check result."""
    return result.raw_digest


def _bundle_evidence_digest(
    *,
    plan_digest: str,
    collect_only_evidence_digests: tuple[str, str],
    full_pytest_evidence_digest: str,
    target_rerun_evidence_digest: str,
    ruff_result_digest: str,
    mypy_result_digest: str,
) -> str:
    """The §0.1 identity of the complete Baseline evidence bundle."""
    return domain_digest(
        "BaselineEvidenceBundleV1",
        1,
        {
            "plan_digest": plan_digest,
            "collect_only_evidence_digests": tuple(collect_only_evidence_digests),
            "full_pytest_evidence_digest": full_pytest_evidence_digest,
            "target_rerun_evidence_digest": target_rerun_evidence_digest,
            "ruff_result_digest": ruff_result_digest,
            "mypy_result_digest": mypy_result_digest,
        },
    )


def evaluate_runtime_compatibility(
    bundle: BaselineEvidenceBundleV1,
) -> RuntimeCompatibilityResultV1:
    """Evaluate the §1.4.1 runtime compatibility items over the complete
    closed evidence bundle.

    The evaluator emits exactly the violation kinds it can prove from the
    closed evidence facts: two collect-only collections that are not
    byte-identical and non-empty (``COLLECTION_UNSTABLE``), any
    post-execution project-tree write (``PROJECT_TREE_WRITE``), and any
    pytest session error in the complete reports
    (``CHECK_ENVIRONMENT_ERROR`` — the checks could not complete in the
    frozen environment).  ``REPORT_INCOMPLETE`` stays in the closed
    vocabulary but is not emitted here because an incomplete report fails
    closed at the parse layer before a bundle exists; ``EXTERNAL_SERVICE_
    REQUIRED`` and ``VCS_RUNTIME_DEPENDENCY`` are accepted model values
    but are not differentially observable from the closed report schema
    (their observable class is the session/collection error recorded as
    ``CHECK_ENVIRONMENT_ERROR``).
    """
    collect_first, collect_second = bundle.collect_only_evidence
    if (
        not collect_first.collected_node_ids
        or collect_first.collected_node_ids != collect_second.collected_node_ids
    ):
        return RuntimeBaselineBlockedV1(
            schema_version=1,
            status="BASELINE_BLOCKED",
            reason="RUNTIME_PROFILE_VIOLATION",
            violation_kind="COLLECTION_UNSTABLE",
            evidence_refs=(
                _evidence_digest(collect_first),
                _evidence_digest(collect_second),
            ),
        )
    if not all(bundle.workspace_unchanged):
        return RuntimeBaselineBlockedV1(
            schema_version=1,
            status="BASELINE_BLOCKED",
            reason="RUNTIME_PROFILE_VIOLATION",
            violation_kind="PROJECT_TREE_WRITE",
            evidence_refs=(
                _evidence_digest(collect_first),
                _evidence_digest(collect_second),
                _evidence_digest(bundle.full_pytest_evidence),
                _evidence_digest(bundle.target_rerun_evidence),
            ),
        )
    for evidence in (
        collect_first,
        collect_second,
        bundle.full_pytest_evidence,
        bundle.target_rerun_evidence,
    ):
        if any(event.event_type == "SESSION_ERROR" for event in evidence.events):
            return RuntimeBaselineBlockedV1(
                schema_version=1,
                status="BASELINE_BLOCKED",
                reason="RUNTIME_PROFILE_VIOLATION",
                violation_kind="CHECK_ENVIRONMENT_ERROR",
                evidence_refs=(_evidence_digest(evidence),),
            )
    return RuntimeCompatibleV1(
        schema_version=1,
        status="COMPATIBLE",
        reference_profile_digest=bundle.reference_profile_digest,
        evidence_digest=_bundle_evidence_digest(
            plan_digest=bundle.plan_digest,
            collect_only_evidence_digests=(
                _evidence_digest(collect_first),
                _evidence_digest(collect_second),
            ),
            full_pytest_evidence_digest=_evidence_digest(bundle.full_pytest_evidence),
            target_rerun_evidence_digest=_evidence_digest(bundle.target_rerun_evidence),
            ruff_result_digest=_check_result_digest(bundle.ruff_result),
            mypy_result_digest=_check_result_digest(bundle.mypy_result),
        ),
    )


# ---------------------------------------------------------------------------
# Baseline result vocabulary
# ---------------------------------------------------------------------------

BaselineBlockedReasonV1 = Literal[
    "BASELINE_UNSTABLE",
    "RUNTIME_PROFILE_VIOLATION",
    "TARGET_NOT_FOUND",
    "TARGET_NOT_REPRODUCED",
    "REPORTER_INVALID",
    "CHECK_ERROR",
    "CHECK_TIMEOUT",
    "TREE_INTEGRITY_FAILED",
    "EXECUTION_WORKSPACE_MUTATED",
    "VALIDATION_ENVIRONMENT_CHANGED",
]
"""The closed Baseline rejection vocabulary (SPEC §4.5 errors).

- ``BASELINE_UNSTABLE``: full/target fingerprint drift, forbidden pytest
  states, or a non-target failure.
- ``RUNTIME_PROFILE_VIOLATION``: the §1.4.1 runtime compatibility check
  failed (``violation_kind`` PRESENT).
- ``TARGET_NOT_FOUND`` / ``TARGET_NOT_REPRODUCED``: the fingerprint
  layer's own closed codes (a target absent from the collection, or not a
  complete ``CALL``/``FAIL``).
- ``REPORTER_INVALID``: an authoritative report did not parse.
- ``CHECK_ERROR`` / ``CHECK_TIMEOUT``: a Ruff/Mypy check did not PASS or
  an execution failed at the closed execution layer.
- ``TREE_INTEGRITY_FAILED``: the plan does not bind the sealed Snapshot
  (or the materialization boundary failed).
- ``EXECUTION_WORKSPACE_MUTATED``: a cleanup verdict left residue (the
  zero-residue discipline, T18.2 mode).
- ``VALIDATION_ENVIRONMENT_CHANGED``: the frozen request binding failed
  (the plan no longer matches the frozen built-in execution profile).
"""


class BaselineBlockedV1(BaseModel):
    """One closed Baseline rejection: stable reason, evidence refs, and
    the structured violation kind exactly when the reason is
    ``RUNTIME_PROFILE_VIOLATION``."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal[1]
    kind: Literal["BLOCKED"]
    reason: BaselineBlockedReasonV1
    evidence_refs: tuple[StrictStr, ...]
    violation_kind: OptionalRuntimeViolationKindV1

    @field_validator("schema_version", mode="before")
    @classmethod
    def _schema_version_is_exact_int(cls, value: object) -> object:
        return _reject_coerced_schema_version(value)

    @field_validator("evidence_refs")
    @classmethod
    def _evidence_refs_are_digests(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        for ref in value:
            _require_digest_form(ref)
        return value

    @model_validator(mode="after")
    def _require_exact_violation_presence(self) -> BaselineBlockedV1:
        if self.reason == "RUNTIME_PROFILE_VIOLATION":
            if not isinstance(self.violation_kind, PresentV1):
                raise ValueError(
                    "RUNTIME_PROFILE_VIOLATION results require a PRESENT violation kind"
                )
        elif isinstance(self.violation_kind, PresentV1):
            raise ValueError(
                "only RUNTIME_PROFILE_VIOLATION results may carry a violation kind"
            )
        return self


class BaselineTestRecordV1(BaseModel):
    """SPEC §4.5 ``BaselineTestRecordV1``: one per-test baseline record.

    The closed state table: ``ERROR`` records carry a non-CALL
    ``error_phase`` and no fingerprint; every other status carries
    ``error_phase=ABSENT``; only ``FAIL`` records may carry a PRESENT
    fingerprint digest (the manifest layer enforces that exactly the
    target records do).
    """

    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal[1]
    node_id: StrictStr
    status: Literal[
        "PASS", "FAIL", "SKIP", "XFAIL", "XPASS", "DESELECTED", "ERROR", "NOT_RUN"
    ]
    error_phase: (
        AbsentV1
        | PresentV1[Literal["COLLECTION", "SETUP", "CALL", "TEARDOWN", "ENVIRONMENT"]]
    )
    failure_fingerprint_digest: AbsentV1 | PresentV1[DigestV1]

    @field_validator("schema_version", mode="before")
    @classmethod
    def _schema_version_is_exact_int(cls, value: object) -> object:
        return _reject_coerced_schema_version(value)

    @field_validator("node_id")
    @classmethod
    def _node_id_is_non_empty(cls, value: str) -> str:
        if value == "":
            raise ValueError("record node ids must not be empty")
        return value

    @model_validator(mode="after")
    def _require_closed_record_table(self) -> BaselineTestRecordV1:
        if self.status == "ERROR":
            if not isinstance(self.error_phase, PresentV1):
                raise ValueError("ERROR records require a PRESENT error phase")
            if self.error_phase.value == "CALL":
                raise ValueError("ERROR records cannot be in the CALL phase")
            if isinstance(self.failure_fingerprint_digest, PresentV1):
                raise ValueError("ERROR records carry no failure fingerprint")
        else:
            if not isinstance(self.error_phase, AbsentV1):
                raise ValueError("non-ERROR records must carry error_phase ABSENT")
            if self.status != "FAIL" and isinstance(
                self.failure_fingerprint_digest, PresentV1
            ):
                raise ValueError(
                    "only FAIL records may carry a failure fingerprint digest"
                )
        return self


class PassingBaselineV1(BaseModel):
    """The single immutable success result of one Baseline execution.

    Every manifest identity field is bound verbatim from the exact
    executed plan and the complete authoritative evidence (the evidence
    digests are the parsed reports'/results' own §0.1 identities); the
    runtime compatibility verdict is COMPATIBLE by type.  Only
    ``run_baseline`` can construct this value, from the closed evidence
    bundle and the frozen runtime compatibility result.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal[1]
    kind: Literal["PASSING"]
    plan_digest: StrictStr
    check_plan_version: StrictStr
    adapter_version: StrictStr
    python_version: StrictStr
    pytest_version: StrictStr
    report_plugin_version: StrictStr
    ruff_version: StrictStr
    mypy_version: StrictStr
    docker_image_digest: StrictStr
    docker_execution_profile_version: Literal[1]
    reference_profile_digest: StrictStr
    snapshot_root_digest: StrictStr
    repository_policy_digest: StrictStr
    target_test_ids: tuple[StrictStr, ...]
    collected_node_ids: tuple[StrictStr, ...]
    collect_only_evidence_digests: tuple[StrictStr, StrictStr]
    full_pytest_evidence_digest: StrictStr
    target_rerun_evidence_digest: StrictStr
    ruff_result_digest: StrictStr
    mypy_result_digest: StrictStr
    baseline_test_records: tuple[BaselineTestRecordV1, ...]
    protected_artifact_set_digest: StrictStr
    runtime_compatibility: RuntimeCompatibleV1

    @field_validator(
        "schema_version", "docker_execution_profile_version", mode="before"
    )
    @classmethod
    def _versions_are_exact_int_one(cls, value: object) -> object:
        return _reject_coerced_schema_version(value)

    @field_validator(
        "plan_digest",
        "docker_image_digest",
        "reference_profile_digest",
        "snapshot_root_digest",
        "repository_policy_digest",
        "full_pytest_evidence_digest",
        "target_rerun_evidence_digest",
        "ruff_result_digest",
        "mypy_result_digest",
        "protected_artifact_set_digest",
    )
    @classmethod
    def _digests_have_exact_form(cls, value: str) -> str:
        return _require_digest_form(value)

    @field_validator(
        "check_plan_version",
        "adapter_version",
        "python_version",
        "pytest_version",
        "report_plugin_version",
        "ruff_version",
        "mypy_version",
    )
    @classmethod
    def _version_fields_are_non_empty(cls, value: str) -> str:
        if value == "":
            raise ValueError("version fields must be non-empty")
        return value

    @field_validator("collect_only_evidence_digests")
    @classmethod
    def _collect_only_digests_are_exactly_two(
        cls, value: tuple[str, str]
    ) -> tuple[str, str]:
        if len(value) != 2:
            raise ValueError(
                "collect-only evidence digests must be exactly two in ordinal order"
            )
        for digest in value:
            _require_digest_form(digest)
        return value

    @field_validator("target_test_ids", "collected_node_ids")
    @classmethod
    def _node_id_lists_are_non_empty(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if not value or any(node_id == "" for node_id in value):
            raise ValueError("target and collected node ids must be non-empty")
        return value


BaselineResultV1: TypeAlias = Annotated[
    PassingBaselineV1 | BaselineBlockedV1,
    Field(discriminator="kind"),
]
"""SPEC §4.5: ``BaselineResult = PassingBaselineV1 | BaselineBlockedV1``."""


def _blocked(
    reason: BaselineBlockedReasonV1,
    evidence_refs: tuple[str, ...],
    violation_kind: RuntimeProfileViolationKindV1 | None = None,
) -> BaselineBlockedV1:
    """One closed blocked result with the stable reason and refs."""
    binding: AbsentV1 | PresentV1[RuntimeProfileViolationKindV1]
    if violation_kind is None:
        binding = AbsentV1(kind="ABSENT")
    else:
        binding = PresentV1(kind="PRESENT", value=violation_kind)
    return BaselineBlockedV1(
        schema_version=1,
        kind="BLOCKED",
        reason=reason,
        evidence_refs=tuple(evidence_refs),
        violation_kind=binding,
    )


# ---------------------------------------------------------------------------
# Frozen execution boundary
# ---------------------------------------------------------------------------


def _frozen_execution_profile() -> DockerExecutionProfileV1:
    """The one frozen SPEC §1.4.5 execution profile v1.

    The profile is closed-frozen by ``DockerExecutionProfileV1``'s own
    validators (exact environment whitelist, exact resource limits) and
    every ``ExecutionRequestV1`` re-binds the frozen manifest/image
    digests, so a drifted construction can never validate — the baseline
    fails closed as ``VALIDATION_ENVIRONMENT_CHANGED`` instead.
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


def compute_resource_parameters_digest() -> str:
    """The §0.1 identity of the frozen resource parameters (SPEC §4.5
    ``ValidationManifestV1.resource_parameters_digest``)."""
    resources = _frozen_execution_profile().resources
    return domain_digest(
        "ResourceParametersV1",
        1,
        {
            "cpus": resources.cpus,
            "memory_bytes": resources.memory_bytes,
            "pids_limit": resources.pids_limit,
            "tmpfs_size_bytes": resources.tmpfs_size_bytes,
            "max_output_bytes": resources.max_output_bytes,
        },
    )


def compute_environment_whitelist_digest() -> str:
    """The §0.1 identity of the frozen environment whitelist (SPEC §4.5
    ``ValidationManifestV1.environment_whitelist_digest``)."""
    variables = _frozen_execution_profile().environment.variables
    return domain_digest(
        "EnvironmentWhitelistV1",
        1,
        {"variables": tuple((variable.name, variable.value) for variable in variables)},
    )


def compute_protected_artifact_set_digest(snapshot: SnapshotTreeV1) -> str:
    """The §0.1 identity of the protected artifact set of the sealed
    Snapshot: the ordered list of protected paths (SPEC §1.4.2 table)
    present in the tree.  The formal validation can re-derive the same
    set from the same Snapshot identity and compare (AC-04)."""
    protected = tuple(
        sorted(
            path.value
            for path in snapshot.list_file_paths()
            if protected_artifact_path(path.value)
        )
    )
    return domain_digest(
        "ProtectedArtifactSetV1",
        1,
        {"protected_paths": protected},
    )


# ---------------------------------------------------------------------------
# Baseline orchestration
# ---------------------------------------------------------------------------


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


def _snapshot_candidate(
    snapshot: SnapshotTreeV1,
) -> tuple[CandidateTreeV1, ContentObjectStore]:
    """One root candidate whose tree is the sealed Snapshot (T12.1)."""
    store = ContentObjectStore()
    for _path, raw in snapshot.file_bytes:
        store.put(raw)
    return root_candidate_revision(snapshot, store).tree, store


def _parse_collect_only_evidence(
    raw: bytes, report_plugin_version: str
) -> PytestEvidenceV1 | None:
    """Complete ordered evidence of one collect-only report.

    The first collect-only defines the baseline collection, so no prior
    plan exists to bind — the structural report contract (closed schema,
    integrity digest, exit consistency, the COLLECT_ONLY run kind, the
    frozen plugin version, and the bounded event count) is the whole
    validation.  Collection stability is the runtime compatibility
    check's ``COLLECTION_UNSTABLE``, never guessed from a single report.
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
    if evidence.report_plugin_version != report_plugin_version:
        return None
    if len(evidence.events) > MAX_REPORT_EVENTS:
        return None
    return evidence


def _request_for(
    plan: BaselineCheckPlanV1,
    check_id: str,
    ordinal: int,
    argv: object,
) -> ExecutionRequestV1:
    """One frozen execution request bound to the plan's identities.

    ``ExecutionRequestV1`` re-validates the frozen manifest/image digests
    and the closed execution profile, so a plan that no longer matches
    the frozen built-ins fails closed before any container call.
    """
    return ExecutionRequestV1.model_validate(
        {
            "schema_version": 1,
            "request_id": f"baseline-{check_id}-{ordinal}-{uuid.uuid4().hex}",
            "reference_profile_digest": plan.reference_profile_digest,
            "docker_image_digest": plan.docker_image_digest,
            "docker_execution_profile_version": 1,
            "profile": _frozen_execution_profile(),
            "argv": argv,
        }
    )


def _fingerprint_context(
    request: ExecutionRequestV1, raw: RawExecutionResultV1
) -> FingerprintNormalizationContextV1:
    """The per-check volatility allowlist for fingerprint normalization.

    Container-side output can only reference the frozen in-container
    workspace and tmp paths; the per-check request and container ids are
    the declared run/container volatility (SPEC §4.5 rule 2).
    """
    return FingerprintNormalizationContextV1(
        schema_version=1,
        execution_root=_FROZEN_WORKSPACE,
        tmp_root="/tmp",
        run_id=request.request_id,
        container_id=raw.container_id,
    )


def run_baseline(
    plan: BaselineCheckPlanV1,
    snapshot: SnapshotTreeV1,
    executor: DockerExecutor,
) -> BaselineResultV1:
    """Execute the frozen six-check Baseline sequence once each in
    declared order with fresh identity-bound boundaries and return one
    closed result.

    Stages: the plan/Snapshot static binding gate; per-check execution,
    cleanup, and authoritative parsing (any execution failure, cleanup
    residue, or report failure blocks immediately with its closed code);
    the two-collect stability gate; the complete-evidence runtime
    compatibility check; and the §4.5 baseline predicates.  Only when
    every predicate holds does one ``PassingBaselineV1`` exist.
    """

    if plan.snapshot_root_digest != snapshot.root_digest:
        return _blocked("TREE_INTEGRITY_FAILED", (plan.digest,))
    if plan.repository_policy_digest != snapshot.repository_policy_digest:
        return _blocked("TREE_INTEGRITY_FAILED", (plan.digest,))
    try:
        manifest = _load_frozen_manifest()
    except Exception:
        return _blocked("VALIDATION_ENVIRONMENT_CHANGED", (plan.digest,))
    if plan.reference_profile_digest != manifest.digest:
        return _blocked("VALIDATION_ENVIRONMENT_CHANGED", (plan.digest,))
    try:
        candidate, _store = _snapshot_candidate(snapshot)
    except Exception:
        return _blocked("TREE_INTEGRITY_FAILED", (plan.digest,))

    base = Path(tempfile.mkdtemp(prefix="vesper-baseline-"))
    refs: list[str] = []
    preserve_base = False
    try:
        collect_evidences: list[PytestEvidenceV1] = []
        full_evidence: PytestEvidenceV1 | None = None
        target_evidence: PytestEvidenceV1 | None = None
        ruff_result: CheckResultV1 | None = None
        mypy_result: CheckResultV1 | None = None
        workspace_unchanged: list[bool] = []
        raw_by_check: dict[str, RawExecutionResultV1] = {}
        request_by_check: dict[str, ExecutionRequestV1] = {}
        for ordinal, entry in enumerate(plan.entries, start=1):
            try:
                root = allocate_execution_root(base)
                materialized = materialize_candidate(candidate, root)
            except MaterializationError:
                return _blocked("TREE_INTEGRITY_FAILED", (*refs, plan.digest))
            try:
                request = _request_for(plan, entry.check_id, ordinal, entry.argv)
            except ValidationError:
                return _blocked("VALIDATION_ENVIRONMENT_CHANGED", (*refs, plan.digest))
            raw = executor.execute(request, materialized)
            cleanup = finalize_execution(raw, candidate, materialized)
            workspace_unchanged.append(cleanup.workspace_unchanged)
            raw_by_check[entry.check_id] = raw
            request_by_check[entry.check_id] = request
            if raw.error_code is not None:
                refs.append(_raw_evidence_digest(raw))
                if raw.error_code == "CHECK_TIMEOUT":
                    return _blocked("CHECK_TIMEOUT", (*refs,))
                return _blocked("CHECK_ERROR", (*refs,))
            # The zero-residue discipline fails fast per check: a surviving
            # exact container or materialization root (workspace drift is
            # the runtime check's PROJECT_TREE_WRITE) blocks immediately.
            # The offending raw evidence and the residual artifact identity
            # are bound into the blocked result, and the surviving root is
            # left in place as mutation evidence for the caller's cleanup
            # layer (the finally backstop below preserves it).
            if not cleanup.container_removed or not cleanup.materialization_removed:
                residual = cleanup.residual_artifact
                refs.append(_raw_evidence_digest(raw))
                if residual is not None:
                    refs.append(residual.digest.value)
                preserve_base = True
                return _blocked("EXECUTION_WORKSPACE_MUTATED", (*refs,))
            if entry.check_id == "COLLECT_ONLY":
                parsed = _parse_collect_only_evidence(
                    raw.stdout, plan.report_plugin_version
                )
                if parsed is None:
                    return _blocked(
                        "REPORTER_INVALID", (*refs, _raw_evidence_digest(raw))
                    )
                collect_evidences.append(parsed)
                refs.append(parsed.integrity_digest)
                if len(collect_evidences) == 2:
                    # Intentional fail-fast duplication of the bundle
                    # check's COLLECTION_UNSTABLE: an empty or drifted
                    # collection would make every downstream planned-node
                    # binding meaningless, so the baseline blocks before
                    # the full/target checks; the bundle-level evaluation
                    # in evaluate_runtime_compatibility remains the closed
                    # authority over the complete evidence.
                    first, second = collect_evidences
                    if (
                        not first.collected_node_ids
                        or first.collected_node_ids != second.collected_node_ids
                    ):
                        return _blocked(
                            "RUNTIME_PROFILE_VIOLATION",
                            (*refs,),
                            violation_kind="COLLECTION_UNSTABLE",
                        )
            elif entry.check_id == "FULL_PYTEST":
                expectation = PytestReportExpectationV1(
                    schema_version=1,
                    run_kind="FULL_PYTEST",
                    planned_node_ids=collect_evidences[0].collected_node_ids,
                    report_plugin_version=plan.report_plugin_version,
                )
                outcome = parse_pytest_evidence(raw.stdout, expectation)
                if outcome.error_code is not None:
                    return _blocked(
                        "REPORTER_INVALID", (*refs, _raw_evidence_digest(raw))
                    )
                assert outcome.evidence is not None
                full_evidence = outcome.evidence
                refs.append(full_evidence.integrity_digest)
            elif entry.check_id == "TARGET_TESTS":
                expectation = PytestReportExpectationV1(
                    schema_version=1,
                    run_kind="TARGET_TESTS",
                    planned_node_ids=plan.target_test_ids.target_test_ids,
                    report_plugin_version=plan.report_plugin_version,
                )
                outcome = parse_pytest_evidence(raw.stdout, expectation)
                if outcome.error_code is not None:
                    return _blocked(
                        "REPORTER_INVALID", (*refs, _raw_evidence_digest(raw))
                    )
                assert outcome.evidence is not None
                target_evidence = outcome.evidence
                refs.append(target_evidence.integrity_digest)
            elif entry.check_id == "RUFF":
                result = parse_ruff_result(raw, manifest)
                ruff_result = result
                refs.append(result.raw_digest)
            elif entry.check_id == "MYPY":
                result = parse_mypy_result(raw, manifest)
                mypy_result = result
                refs.append(result.raw_digest)
            else:  # pragma: no cover - the plan schema closes the identity set
                raise AssertionError(
                    f"unknown Baseline check identity: {entry.check_id}"
                )

        assert full_evidence is not None
        assert target_evidence is not None
        assert ruff_result is not None
        assert mypy_result is not None
        bundle = BaselineEvidenceBundleV1(
            schema_version=1,
            plan_digest=plan.digest,
            reference_profile_digest=plan.reference_profile_digest,
            collect_only_evidence=(collect_evidences[0], collect_evidences[1]),
            full_pytest_evidence=full_evidence,
            target_rerun_evidence=target_evidence,
            ruff_result=ruff_result,
            mypy_result=mypy_result,
            workspace_unchanged=tuple(workspace_unchanged),
        )
        verdict = evaluate_runtime_compatibility(bundle)
        if verdict.status != "COMPATIBLE":
            return _blocked(
                "RUNTIME_PROFILE_VIOLATION",
                (*refs,),
                violation_kind=verdict.violation_kind,
            )

        target_ids = plan.target_test_ids.target_test_ids
        target_set = set(target_ids)
        collected = collect_evidences[0].collected_node_ids
        collected_set = set(collected)
        for target in target_ids:
            if target not in collected_set:
                return _blocked("TARGET_NOT_FOUND", (*refs, plan.digest))

        full_request = request_by_check["FULL_PYTEST"]
        full_raw = raw_by_check["FULL_PYTEST"]
        fingerprints: dict[str, str] = {}
        for target in target_ids:
            fingerprint_outcome = build_failure_fingerprint(
                full_evidence,
                target,
                _fingerprint_context(full_request, full_raw),
            )
            if (
                fingerprint_outcome.kind != "STABLE"
                or fingerprint_outcome.fingerprint is None
            ):
                assert fingerprint_outcome.error_code is not None
                return _blocked(fingerprint_outcome.error_code, (*refs, plan.digest))
            fingerprints[target] = fingerprint_outcome.fingerprint.digest

        target_request = request_by_check["TARGET_TESTS"]
        target_raw = raw_by_check["TARGET_TESTS"]
        for target in target_ids:
            fingerprint_outcome = build_failure_fingerprint(
                target_evidence,
                target,
                _fingerprint_context(target_request, target_raw),
            )
            if (
                fingerprint_outcome.kind != "STABLE"
                or fingerprint_outcome.fingerprint is None
            ):
                assert fingerprint_outcome.error_code is not None
                return _blocked(fingerprint_outcome.error_code, (*refs, plan.digest))
            if fingerprint_outcome.fingerprint.digest != fingerprints[target]:
                return _blocked("BASELINE_UNSTABLE", (*refs, plan.digest))

        for evidence in (full_evidence, target_evidence):
            for event in evidence.events:
                if event.event_type == "DESELECTED":
                    return _blocked("BASELINE_UNSTABLE", (*refs, plan.digest))
                if event.event_type == "TEST_PHASE" and isinstance(
                    event.outcome, PresentV1
                ):
                    if event.outcome.value in (
                        "SKIP",
                        "XFAIL",
                        "XPASS",
                        "DESELECTED",
                        "NOT_RUN",
                        "ERROR",
                    ):
                        return _blocked("BASELINE_UNSTABLE", (*refs, plan.digest))
        # Every non-target must have actually executed in the CALL phase
        # and passed.  The production reporter emits one TEST_PHASE event
        # per phase (SETUP/CALL/TEARDOWN), so the predicate is: exactly
        # one CALL-phase event with outcome PASS; a non-target FAIL or
        # ERROR (or a skipped/unrun node with no CALL event) blocks.  The
        # forbidden-outcome scan above already covers the SKIP/XFAIL/XPASS/
        # DESELECTED/NOT_RUN/ERROR vocabulary for every node.
        for node_id in collected:
            if node_id in target_set:
                continue
            node_events = [
                event
                for event in full_evidence.events
                if event.event_type == "TEST_PHASE"
                and isinstance(event.node_id, PresentV1)
                and event.node_id.value == node_id
            ]
            call_events = [
                event
                for event in node_events
                if isinstance(event.phase, PresentV1) and event.phase.value == "CALL"
            ]
            if (
                len(call_events) != 1
                or not isinstance(call_events[0].outcome, PresentV1)
                or call_events[0].outcome.value != "PASS"
            ):
                return _blocked("BASELINE_UNSTABLE", (*refs, plan.digest))

        if ruff_result.status != "PASS":
            return _blocked("CHECK_ERROR", (*refs, plan.digest))
        if mypy_result.status != "PASS":
            return _blocked("CHECK_ERROR", (*refs, plan.digest))

        records: list[BaselineTestRecordV1] = []
        for node_id in sorted(collected):
            if node_id in target_set:
                records.append(
                    BaselineTestRecordV1(
                        schema_version=1,
                        node_id=node_id,
                        status="FAIL",
                        error_phase=AbsentV1(kind="ABSENT"),
                        failure_fingerprint_digest=PresentV1(
                            kind="PRESENT",
                            value=DigestV1(value=fingerprints[node_id]),
                        ),
                    )
                )
            else:
                records.append(
                    BaselineTestRecordV1(
                        schema_version=1,
                        node_id=node_id,
                        status="PASS",
                        error_phase=AbsentV1(kind="ABSENT"),
                        failure_fingerprint_digest=AbsentV1(kind="ABSENT"),
                    )
                )
        return PassingBaselineV1(
            schema_version=1,
            kind="PASSING",
            plan_digest=plan.digest,
            check_plan_version=plan.check_plan_version,
            adapter_version=plan.adapter_version,
            python_version=plan.python_version,
            pytest_version=plan.pytest_version,
            report_plugin_version=plan.report_plugin_version,
            ruff_version=plan.ruff_version,
            mypy_version=plan.mypy_version,
            docker_image_digest=plan.docker_image_digest,
            docker_execution_profile_version=plan.docker_execution_profile_version,
            reference_profile_digest=plan.reference_profile_digest,
            snapshot_root_digest=plan.snapshot_root_digest,
            repository_policy_digest=plan.repository_policy_digest,
            target_test_ids=target_ids,
            collected_node_ids=collected,
            collect_only_evidence_digests=(
                collect_evidences[0].integrity_digest,
                collect_evidences[1].integrity_digest,
            ),
            full_pytest_evidence_digest=full_evidence.integrity_digest,
            target_rerun_evidence_digest=target_evidence.integrity_digest,
            ruff_result_digest=ruff_result.raw_digest,
            mypy_result_digest=mypy_result.raw_digest,
            baseline_test_records=tuple(records),
            protected_artifact_set_digest=compute_protected_artifact_set_digest(
                snapshot
            ),
            runtime_compatibility=verdict,
        )
    finally:
        # A residue-blocked run leaves the surviving root in place as
        # mutation evidence (its artifact digest is bound in the blocked
        # result's evidence refs); every other path removes the whole
        # per-run base (zero residue).
        if not preserve_base:
            shutil.rmtree(base, ignore_errors=True)

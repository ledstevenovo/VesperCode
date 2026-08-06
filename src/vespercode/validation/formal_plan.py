"""T21.1 legacy step 21.A: formal-validation plan and preflight (SPEC §4.5).

``build_formal_validation_plan`` recomputes the exact current candidate
bytes, final-diff/protected-path state, policy identity, environment/
reference profile, Manifest, target, and collection bindings BEFORE any
execution request exists, and freezes the complete ordered collect/full
pytest/Ruff/Mypy request plan with immutable request identities,
candidate identity, bounds, argv, and expected evidence.  Every stale,
drifted, protected, or out-of-policy input yields zero execution
requests (``FormalPlanRejectedV1`` with ``execution_requests == ()``,
SPEC §4.5 "检查容器调用次数均为零"); only exact current inputs produce
one immutable ``FormalValidationPlanV1``.  The plan carries the sealed
``CandidateTreeV1`` so the execution boundary (Task 21.B) can
materialize the exact frozen candidate; the plan digest never binds the
runtime tree object, only its identity.

The T20.1 adapter's frozen argv is consumed read-only through
``PythonProjectAdapterV1.build_formal_plan``; Docker calls, evidence
interpretation, lifecycle mutation, and ``VerifiedCandidateV1`` creation
remain out of scope (GREEN-4).
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Literal, TypeAlias

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    Strict,
    StrictStr,
    field_validator,
    model_validator,
)

from src.vespercode.candidate.final_diff import (
    FinalDiffRejectedError,
    FinalDiffV1,
    recompute_final_diff,
)
from src.vespercode.candidate.identity import build_candidate_identity
from src.vespercode.canonical.digest import domain_digest
from src.vespercode.canonical.json_v1 import CanonicalValueV1
from src.vespercode.contracts.evidence import _DIGEST_RE
from src.vespercode.contracts.optional import AbsentV1, PresentV1
from src.vespercode.execution.docker_profile import ExecutionArgumentSequenceV1
from src.vespercode.profiles.reference import (
    ReferenceProfileManifestV1,
    load_reference_profile,
)
from src.vespercode.trees.candidate import CandidateRevisionV1, CandidateTreeV1
from src.vespercode.validation.baseline import (
    compute_environment_whitelist_digest,
    compute_protected_artifact_set_digest,
    compute_resource_parameters_digest,
)
from src.vespercode.validation.manifest import (
    ValidationManifestV1,
    validation_manifest_digest,
)
from src.vespercode.validation.pytest_evidence import MAX_REPORT_EVENTS
from src.vespercode.validation.python_adapter import (
    ADAPTER_VERSION,
    CheckPlanError,
    FormalCheckIdentityV1,
    FormalCheckPlanEntryV1,
    PythonProjectAdapterV1,
)
from src.vespercode.workspace.path_guard import protected_artifact_path

# The frozen SPEC §5.1 sub-timeouts of the formal-validation phase: every
# single check shares ``full_check_timeout_seconds`` and the whole phase
# shares ``formal_validation_timeout_seconds`` (§4.2.6 closed table).
# These values are frozen plan evidence at this boundary; the per-check
# execution deadline is enforced by the T18.1 ``DockerExecutor`` (its
# frozen 120 s bound is stricter than 300 s — fail-closed direction, no
# false success), and threading the phase bound through the run
# coordinator belongs to the loop layer (GREEN-4 boundary).
_FROZEN_FULL_CHECK_TIMEOUT_SECONDS = 300
_FROZEN_FORMAL_VALIDATION_TIMEOUT_SECONDS = 600

# The frozen formal request identity prefix (the exact ordered plan binds
# one immutable identity per check).
_REQUEST_PREFIX = "formal"


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


FormalPlanErrorCodeV1 = Literal[
    "CANDIDATE_STALE",
    "TREE_INTEGRITY_FAILED",
    "VALIDATION_ENVIRONMENT_CHANGED",
    "PROTECTED_ARTIFACT_CHANGED",
    "PATCH_PATH_NOT_EDITABLE",
]
"""The closed formal-preflight rejection vocabulary (SPEC §4.5 errors).

``CANDIDATE_STALE`` is the card-mandated spelling of the SPEC §4.3
stale-candidate rejection (the exact RED test asserts the literal code);
the other codes are the SPEC §4.5 errors of the preflight binding
checks.  Every rejection is zero-request atomic by construction.
"""


class FormalValidationBoundsV1(BaseModel):
    """The frozen SPEC §5.1 formal-validation bounds.

    ``full_check_timeout_seconds`` is the exact 300 s per-check sub-timeout
    and ``formal_validation_timeout_seconds`` the exact 600 s whole-phase
    bound of the §4.2.6 closed table; both are pinned literals and any
    other value rejects before a plan exists.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal[1]
    full_check_timeout_seconds: Annotated[int, Strict()]
    formal_validation_timeout_seconds: Annotated[int, Strict()]

    @field_validator("schema_version", mode="before")
    @classmethod
    def _schema_version_is_exact_int(cls, value: object) -> object:
        return _reject_coerced_schema_version(value)

    @field_validator(
        "full_check_timeout_seconds", "formal_validation_timeout_seconds", mode="before"
    )
    @classmethod
    def _timeouts_are_exact_ints(cls, value: object) -> object:
        if not isinstance(value, int) or isinstance(value, bool):
            raise ValueError("timeout bounds must be exact decimal integers")
        return value

    @model_validator(mode="after")
    def _require_exact_frozen_bounds(self) -> FormalValidationBoundsV1:
        if self.full_check_timeout_seconds != _FROZEN_FULL_CHECK_TIMEOUT_SECONDS:
            raise ValueError(
                "full_check_timeout_seconds must be the frozen SPEC §5.1 value 300"
            )
        if (
            self.formal_validation_timeout_seconds
            != _FROZEN_FORMAL_VALIDATION_TIMEOUT_SECONDS
        ):
            raise ValueError(
                "formal_validation_timeout_seconds must be the frozen "
                "SPEC §5.1 value 600"
            )
        return self


class FormalPytestExpectationV1(BaseModel):
    """The frozen expected-evidence contract of one pytest request.

    ``COLLECT_ONLY`` defines the collection itself (the T20.2 baseline
    interpretation: no prior plan exists to bind), so its planned node
    set is exactly empty; ``FULL_PYTEST`` binds the exact Manifest
    collection.  The report plugin version and the bounded event cap
    complete the expectation the execution layer parses against.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal[1]
    run_kind: Literal["COLLECT_ONLY", "FULL_PYTEST"]
    planned_node_ids: tuple[StrictStr, ...]
    report_plugin_version: StrictStr
    max_events: Annotated[int, Strict()] = MAX_REPORT_EVENTS

    @field_validator("schema_version", mode="before")
    @classmethod
    def _schema_version_is_exact_int(cls, value: object) -> object:
        return _reject_coerced_schema_version(value)

    @field_validator("max_events")
    @classmethod
    def _max_events_is_bounded(cls, value: int) -> int:
        if value < 1 or value > MAX_REPORT_EVENTS:
            raise ValueError("max_events must be within 1..65536")
        return value

    @field_validator("report_plugin_version")
    @classmethod
    def _plugin_version_is_non_empty(cls, value: str) -> str:
        if value == "":
            raise ValueError("report_plugin_version must be non-empty")
        return value

    @model_validator(mode="after")
    def _require_exact_collection_binding(self) -> FormalPytestExpectationV1:
        if self.run_kind == "COLLECT_ONLY":
            if self.planned_node_ids != ():
                raise ValueError(
                    "COLLECT_ONLY expectations bind an empty planned node set"
                )
        elif not self.planned_node_ids or any(
            node_id == "" for node_id in self.planned_node_ids
        ):
            raise ValueError(
                "FULL_PYTEST expectations bind the exact non-empty collection"
            )
        return self


class FormalRequestExpectationV1(BaseModel):
    """The frozen expected-evidence pairing of one formal request.

    Pytest checks carry a PRESENT pytest expectation and no tool version;
    Ruff/Mypy checks carry the frozen tool version and no pytest
    expectation.  Any other pairing rejects before a plan exists.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal[1]
    check_kind: FormalCheckIdentityV1
    pytest: AbsentV1 | PresentV1[FormalPytestExpectationV1]
    tool_version: AbsentV1 | PresentV1[StrictStr]

    @field_validator("schema_version", mode="before")
    @classmethod
    def _schema_version_is_exact_int(cls, value: object) -> object:
        return _reject_coerced_schema_version(value)

    @model_validator(mode="after")
    def _require_exact_kind_pairing(self) -> FormalRequestExpectationV1:
        is_pytest = self.check_kind in ("COLLECT_ONLY", "FULL_PYTEST")
        if is_pytest:
            if not isinstance(self.pytest, PresentV1):
                raise ValueError("pytest checks require a PRESENT pytest expectation")
            if not isinstance(self.tool_version, AbsentV1):
                raise ValueError("pytest checks never bind a tool version")
        else:
            if not isinstance(self.pytest, AbsentV1):
                raise ValueError("tool checks never bind a pytest expectation")
            if not isinstance(self.tool_version, PresentV1):
                raise ValueError("tool checks require a PRESENT tool version")
        return self


class FormalValidationRequestV1(BaseModel):
    """One immutable frozen execution request of the formal plan.

    The request identity is bound to its check kind and ordinal (no
    free-form identity can enter the frozen plan), the argv is the
    adapter-built immutable sequence (SPEC §4.5 fixed argv, no shell),
    the timeout is the frozen 300 s per-check sub-timeout, and the
    expected evidence is closed per kind.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal[1]
    request_id: StrictStr
    check_kind: FormalCheckIdentityV1
    argv: ExecutionArgumentSequenceV1
    timeout_seconds: Annotated[int, Strict()]
    expectation: FormalRequestExpectationV1

    @field_validator("schema_version", mode="before")
    @classmethod
    def _schema_version_is_exact_int(cls, value: object) -> object:
        return _reject_coerced_schema_version(value)

    @field_validator("timeout_seconds", mode="before")
    @classmethod
    def _timeout_is_exact_int(cls, value: object) -> object:
        if not isinstance(value, int) or isinstance(value, bool):
            raise ValueError("timeout_seconds must be an exact decimal integer")
        return value

    @field_validator("request_id")
    @classmethod
    def _request_id_is_non_empty(cls, value: str) -> str:
        if value == "":
            raise ValueError("request ids must be non-empty")
        return value

    @model_validator(mode="after")
    def _require_exact_frozen_bindings(self) -> FormalValidationRequestV1:
        expected = f"{_REQUEST_PREFIX}-{self.check_kind}-"
        if not self.request_id.startswith(expected):
            raise ValueError(
                "request ids must be bound to their check kind: "
                f"expected prefix {expected!r}"
            )
        suffix = self.request_id[len(expected) :]
        if not suffix.isdigit() or suffix == "0":
            raise ValueError("request ids must carry a positive ordinal suffix")
        if self.expectation.check_kind != self.check_kind:
            raise ValueError(
                "the expectation must bind the same check kind as the request"
            )
        if self.timeout_seconds != _FROZEN_FULL_CHECK_TIMEOUT_SECONDS:
            raise ValueError(
                "timeout_seconds must be the frozen SPEC §5.1 per-check value 300"
            )
        return self


class FormalValidationPlanV1(BaseModel):
    """The complete frozen formal-validation plan (SPEC §4.5).

    Sealed value fields: the exact current Manifest, candidate identity
    triple (candidate/tree/final-diff digests), Snapshot/policy identity,
    protected-artifact set, environment/reference profile, target and
    collection bindings, the frozen bounds, and the four ordered
    immutable requests (collect, full pytest, Ruff, Mypy) with their
    argv, timeout, and expected evidence.  ``candidate_tree`` is the
    sealed runtime tree the execution boundary materializes (never part
    of the digest); ``digest`` is the §0.1 identity of every other field
    and is re-bound at construction, so a plan with a non-binding digest
    can never exist.  ``error_code`` is exactly ``None`` on the frozen
    plan and ``execution_requests`` the complete ordered request plan.
    """

    model_config = ConfigDict(extra="forbid", frozen=True, arbitrary_types_allowed=True)
    schema_version: Literal[1]
    kind: Literal["FROZEN"]
    error_code: Literal[None] = None
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
    snapshot_tree_digest: StrictStr
    repository_policy_digest: StrictStr
    protected_artifact_set_digest: StrictStr
    resource_parameters_digest: StrictStr
    environment_whitelist_digest: StrictStr
    manifest_digest: StrictStr
    candidate_digest: StrictStr
    candidate_tree_digest: StrictStr
    final_diff_digest: StrictStr
    target_test_ids: tuple[StrictStr, ...]
    collected_node_ids: tuple[StrictStr, ...]
    bounds: FormalValidationBoundsV1
    execution_requests: tuple[FormalValidationRequestV1, ...]
    candidate_tree: CandidateTreeV1
    digest: StrictStr

    @field_validator(
        "schema_version", "docker_execution_profile_version", mode="before"
    )
    @classmethod
    def _version_is_exact_int_one(cls, value: object) -> object:
        return _reject_coerced_schema_version(value)

    @field_validator(
        "docker_image_digest",
        "reference_profile_digest",
        "snapshot_tree_digest",
        "repository_policy_digest",
        "protected_artifact_set_digest",
        "resource_parameters_digest",
        "environment_whitelist_digest",
        "manifest_digest",
        "candidate_digest",
        "candidate_tree_digest",
        "final_diff_digest",
        "digest",
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
    def _version_fields_must_be_non_empty(cls, value: str) -> str:
        if value == "":
            raise ValueError("version fields must be non-empty")
        return value

    @field_validator("target_test_ids", "collected_node_ids")
    @classmethod
    def _node_id_lists_are_non_empty(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if not value or any(node_id == "" for node_id in value):
            raise ValueError("target and collected node ids must be non-empty")
        return value

    @model_validator(mode="after")
    def _require_closed_plan_invariants(self) -> FormalValidationPlanV1:
        target_set = set(self.target_test_ids)
        if len(target_set) != len(self.target_test_ids):
            raise ValueError("target test ids must be unique")
        if not target_set.issubset(set(self.collected_node_ids)):
            raise ValueError("target test ids must be members of the collection")
        if tuple(request.check_kind for request in self.execution_requests) != (
            "COLLECT_ONLY",
            "FULL_PYTEST",
            "RUFF",
            "MYPY",
        ):
            raise ValueError(
                "execution requests must be exactly COLLECT_ONLY, FULL_PYTEST, "
                "RUFF, MYPY in order"
            )
        request_ids = tuple(request.request_id for request in self.execution_requests)
        if len(set(request_ids)) != len(request_ids):
            raise ValueError("execution request ids must be unique")
        snapshot = self.candidate_tree.snapshot
        if snapshot.root_digest != self.snapshot_tree_digest:
            raise ValueError(
                "the sealed candidate tree must bind the plan's Snapshot identity"
            )
        if self.candidate_tree.digest != self.candidate_tree_digest:
            raise ValueError(
                "the sealed candidate tree must bind the plan's candidate identity"
            )
        return self

    @model_validator(mode="after")
    def _digest_binds_every_other_field(self) -> FormalValidationPlanV1:
        if self.digest != formal_validation_plan_digest(self):
            raise ValueError("plan digest does not bind the plan fields")
        return self

    @property
    def request_ids(self) -> tuple[str, ...]:
        """The ordered immutable request identities of the frozen plan."""
        return tuple(request.request_id for request in self.execution_requests)


class FormalPlanRejectedV1(BaseModel):
    """One closed zero-request preflight rejection.

    The rejection carries the stable error code and a deterministic
    message; ``execution_requests`` is exactly empty (the zero-request
    failure atomicity of SPEC §4.5: no stale/drifted/protected input
    ever yields an execution request).
    """

    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal[1]
    kind: Literal["REJECTED"]
    error_code: FormalPlanErrorCodeV1
    error_message: StrictStr
    execution_requests: tuple[FormalValidationRequestV1, ...]

    @field_validator("schema_version", mode="before")
    @classmethod
    def _schema_version_is_exact_int(cls, value: object) -> object:
        return _reject_coerced_schema_version(value)

    @model_validator(mode="after")
    def _require_zero_request_atomicity(self) -> FormalPlanRejectedV1:
        if self.execution_requests != ():
            raise ValueError("rejected preflights must carry zero execution requests")
        return self


FormalPlanResultV1: TypeAlias = Annotated[
    FormalValidationPlanV1 | FormalPlanRejectedV1,
    Field(discriminator="kind"),
]
"""The closed preflight result: one frozen plan or one zero-request
rejection (SPEC §4.5)."""


def _pytest_expectation_document(
    expectation: FormalPytestExpectationV1,
) -> CanonicalValueV1:
    return {
        "run_kind": expectation.run_kind,
        "planned_node_ids": tuple(expectation.planned_node_ids),
        "report_plugin_version": expectation.report_plugin_version,
        "max_events": expectation.max_events,
    }


def _request_document(
    request: FormalValidationRequestV1,
) -> dict[str, CanonicalValueV1]:
    """One request in the exact §0.1 document form."""
    if isinstance(request.expectation.pytest, PresentV1):
        pytest_document: CanonicalValueV1 = {
            "kind": "PRESENT",
            "value": _pytest_expectation_document(request.expectation.pytest.value),
        }
    else:
        pytest_document = {"kind": "ABSENT"}
    if isinstance(request.expectation.tool_version, PresentV1):
        tool_document: CanonicalValueV1 = {
            "kind": "PRESENT",
            "value": request.expectation.tool_version.value,
        }
    else:
        tool_document = {"kind": "ABSENT"}
    return {
        "request_id": request.request_id,
        "check_kind": request.check_kind,
        "argv": tuple(request.argv.arguments),
        "timeout_seconds": request.timeout_seconds,
        "expectation": {
            "check_kind": request.expectation.check_kind,
            "pytest": pytest_document,
            "tool_version": tool_document,
        },
    }


def _plan_digest_body(
    *,
    check_plan_version: str,
    adapter_version: str,
    python_version: str,
    pytest_version: str,
    report_plugin_version: str,
    ruff_version: str,
    mypy_version: str,
    docker_image_digest: str,
    docker_execution_profile_version: int,
    reference_profile_digest: str,
    snapshot_tree_digest: str,
    repository_policy_digest: str,
    protected_artifact_set_digest: str,
    resource_parameters_digest: str,
    environment_whitelist_digest: str,
    manifest_digest: str,
    candidate_digest: str,
    candidate_tree_digest: str,
    final_diff_digest: str,
    target_test_ids: tuple[str, ...],
    collected_node_ids: tuple[str, ...],
    bounds: FormalValidationBoundsV1,
    execution_requests: tuple[FormalValidationRequestV1, ...],
) -> dict[str, CanonicalValueV1]:
    """The canonical §0.1 digest body of one frozen plan (no digest)."""
    return {
        "schema_version": 1,
        "kind": "FROZEN",
        "check_plan_version": check_plan_version,
        "adapter_version": adapter_version,
        "python_version": python_version,
        "pytest_version": pytest_version,
        "report_plugin_version": report_plugin_version,
        "ruff_version": ruff_version,
        "mypy_version": mypy_version,
        "docker_image_digest": docker_image_digest,
        "docker_execution_profile_version": docker_execution_profile_version,
        "reference_profile_digest": reference_profile_digest,
        "snapshot_tree_digest": snapshot_tree_digest,
        "repository_policy_digest": repository_policy_digest,
        "protected_artifact_set_digest": protected_artifact_set_digest,
        "resource_parameters_digest": resource_parameters_digest,
        "environment_whitelist_digest": environment_whitelist_digest,
        "manifest_digest": manifest_digest,
        "candidate_digest": candidate_digest,
        "candidate_tree_digest": candidate_tree_digest,
        "final_diff_digest": final_diff_digest,
        "target_test_ids": tuple(target_test_ids),
        "collected_node_ids": tuple(collected_node_ids),
        "bounds": {
            "full_check_timeout_seconds": bounds.full_check_timeout_seconds,
            "formal_validation_timeout_seconds": bounds.formal_validation_timeout_seconds,
        },
        "execution_requests": tuple(
            _request_document(request) for request in execution_requests
        ),
    }


def formal_validation_plan_digest(plan: FormalValidationPlanV1) -> str:
    """The §0.1 identity of every exact plan field except the digest and
    the runtime candidate tree (the tree's identity is bound by
    ``candidate_tree_digest``)."""
    return domain_digest(
        "FormalValidationPlanV1",
        1,
        _plan_digest_body(
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
            snapshot_tree_digest=plan.snapshot_tree_digest,
            repository_policy_digest=plan.repository_policy_digest,
            protected_artifact_set_digest=plan.protected_artifact_set_digest,
            resource_parameters_digest=plan.resource_parameters_digest,
            environment_whitelist_digest=plan.environment_whitelist_digest,
            manifest_digest=plan.manifest_digest,
            candidate_digest=plan.candidate_digest,
            candidate_tree_digest=plan.candidate_tree_digest,
            final_diff_digest=plan.final_diff_digest,
            target_test_ids=plan.target_test_ids,
            collected_node_ids=plan.collected_node_ids,
            bounds=plan.bounds,
            execution_requests=plan.execution_requests,
        ),
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


def _rejected(
    error_code: FormalPlanErrorCodeV1, error_message: str
) -> FormalPlanRejectedV1:
    """One closed zero-request rejection."""
    return FormalPlanRejectedV1(
        schema_version=1,
        kind="REJECTED",
        error_code=error_code,
        error_message=error_message,
        execution_requests=(),
    )


def _request_for(
    entry: FormalCheckPlanEntryV1,
    ordinal: int,
    manifest: ValidationManifestV1,
) -> FormalValidationRequestV1:
    """One immutable frozen request for one frozen check-plan entry."""
    if entry.check_id in ("COLLECT_ONLY", "FULL_PYTEST"):
        expectation = FormalRequestExpectationV1(
            schema_version=1,
            check_kind=entry.check_id,
            pytest=PresentV1(
                kind="PRESENT",
                value=FormalPytestExpectationV1(
                    schema_version=1,
                    run_kind=entry.check_id,
                    planned_node_ids=(
                        ()
                        if entry.check_id == "COLLECT_ONLY"
                        else tuple(manifest.collected_node_ids)
                    ),
                    report_plugin_version=manifest.report_plugin_version,
                ),
            ),
            tool_version=AbsentV1(kind="ABSENT"),
        )
    else:
        expectation = FormalRequestExpectationV1(
            schema_version=1,
            check_kind=entry.check_id,
            pytest=AbsentV1(kind="ABSENT"),
            tool_version=PresentV1(
                kind="PRESENT",
                value=(
                    manifest.ruff_version
                    if entry.check_id == "RUFF"
                    else manifest.mypy_version
                ),
            ),
        )
    return FormalValidationRequestV1(
        schema_version=1,
        request_id=f"{_REQUEST_PREFIX}-{entry.check_id}-{ordinal}",
        check_kind=entry.check_id,
        argv=entry.argv,
        timeout_seconds=_FROZEN_FULL_CHECK_TIMEOUT_SECONDS,
        expectation=expectation,
    )


def _map_recompute_rejection(error: FinalDiffRejectedError) -> FormalPlanErrorCodeV1:
    """One closed code for a recomputation rejection."""
    if error.error_code == "PATCH_PATH_NOT_EDITABLE":
        return "PATCH_PATH_NOT_EDITABLE"
    return "TREE_INTEGRITY_FAILED"


def _map_check_plan_error(error: CheckPlanError) -> FormalPlanErrorCodeV1:
    """One closed code for a T20.1 adapter construction rejection (a
    backstop: the preflight above already proves every adapter binding)."""
    if error.error_code.startswith("PROFILE_"):
        return "VALIDATION_ENVIRONMENT_CHANGED"
    return "TREE_INTEGRITY_FAILED"


def build_formal_validation_plan(
    manifest: ValidationManifestV1,
    candidate: CandidateRevisionV1,
    final_diff: FinalDiffV1,
) -> FormalPlanResultV1:
    """Recompute the exact current bindings and freeze the complete
    ordered collect/full pytest/Ruff/Mypy request plan, or return one
    closed zero-request rejection.

    The deterministic rejection priority (SPEC §4.3 path-priority order
    where applicable): Snapshot/policy identity chain, environment and
    reference profile, protected artifacts, editable policy, exact
    current final-diff/candidate recomputation, protected-artifact set,
    then candidate identity.  Only when every binding holds does one
    immutable ``FormalValidationPlanV1`` exist.
    """
    try:
        frozen = _load_frozen_manifest()
    except Exception:
        return _rejected(
            "VALIDATION_ENVIRONMENT_CHANGED",
            "the frozen reference profile cannot be loaded",
        )
    if manifest.digest != validation_manifest_digest(manifest):
        return _rejected(
            "TREE_INTEGRITY_FAILED",
            "the Manifest digest does not bind its exact current fields",
        )
    if final_diff.snapshot_tree_digest != manifest.snapshot_tree_digest:
        return _rejected(
            "TREE_INTEGRITY_FAILED",
            "the final diff does not bind the Manifest's Snapshot identity",
        )
    snapshot = candidate.tree.snapshot
    if snapshot.root_digest != manifest.snapshot_tree_digest:
        return _rejected(
            "TREE_INTEGRITY_FAILED",
            "the candidate tree does not bind the Manifest's Snapshot identity",
        )
    if snapshot.repository_policy_digest != manifest.repository_policy_digest:
        return _rejected(
            "TREE_INTEGRITY_FAILED",
            "the candidate Snapshot and the Manifest bind different policies",
        )
    if manifest.repository_policy_digest != frozen.editable_path_policy.digest:
        return _rejected(
            "TREE_INTEGRITY_FAILED",
            "the Manifest does not bind the frozen editable path policy",
        )
    if manifest.reference_profile_digest != frozen.digest:
        return _rejected(
            "VALIDATION_ENVIRONMENT_CHANGED",
            "the Manifest does not bind the frozen reference profile",
        )
    if (
        manifest.check_plan_version,
        manifest.adapter_version,
        manifest.python_version,
        manifest.pytest_version,
        manifest.report_plugin_version,
        manifest.ruff_version,
        manifest.mypy_version,
        manifest.docker_image_digest,
        manifest.docker_execution_profile_version,
    ) != (
        frozen.check_plan_version,
        ADAPTER_VERSION,
        frozen.python_version,
        frozen.pytest_version,
        frozen.report_plugin_version,
        frozen.ruff_version,
        frozen.mypy_version,
        frozen.docker_image_digest,
        frozen.docker_execution_profile_version,
    ):
        return _rejected(
            "VALIDATION_ENVIRONMENT_CHANGED",
            "Manifest tool/image/execution fields must exactly match the "
            "frozen reference profile",
        )
    if manifest.resource_parameters_digest != compute_resource_parameters_digest():
        return _rejected(
            "VALIDATION_ENVIRONMENT_CHANGED",
            "the resource parameters digest does not bind the frozen profile",
        )
    if manifest.environment_whitelist_digest != compute_environment_whitelist_digest():
        return _rejected(
            "VALIDATION_ENVIRONMENT_CHANGED",
            "the environment whitelist digest does not bind the frozen profile",
        )
    # The passed final diff is revalidated entry-by-entry (SPEC §4.5:
    # "必须重算当前 FinalDiffV1 并验证全部 entries 命中冻结
    # EditablePathPolicyV1"); protected artifacts take priority over the
    # editable policy (§4.3 path-rejection priority).
    for entry in final_diff.entries:
        if protected_artifact_path(entry.path.value):
            return _rejected(
                "PROTECTED_ARTIFACT_CHANGED",
                f"the final diff modifies the protected artifact {entry.path.value!r}",
            )
        if not frozen.editable_path_policy.matches(entry.path, entry.operation):
            return _rejected(
                "PATCH_PATH_NOT_EDITABLE",
                f"the final diff entry {entry.path.value!r} is not editable",
            )
    # GREEN-1: recompute the exact current net diff from the current tree
    # bytes; the passed final diff must be that exact current diff.
    try:
        current_diff = recompute_final_diff(
            snapshot, candidate.tree, frozen.editable_path_policy
        )
    except FinalDiffRejectedError as error:
        return _rejected(
            _map_recompute_rejection(error),
            f"the current candidate tree cannot produce a final diff: {error.reason}",
        )
    if current_diff.digest != final_diff.digest:
        return _rejected(
            "CANDIDATE_STALE",
            "the passed final diff is not the recomputed current diff",
        )
    if compute_protected_artifact_set_digest(snapshot) != (
        manifest.protected_artifact_set_digest
    ):
        return _rejected(
            "TREE_INTEGRITY_FAILED",
            "the recomputed protected artifact set does not bind the Manifest",
        )
    identity = build_candidate_identity(
        snapshot.root_digest, candidate.tree.digest, final_diff.digest
    )
    if candidate.candidate_digest != identity.digest:
        return _rejected(
            "CANDIDATE_STALE",
            "the candidate identity no longer matches the exact current "
            "Snapshot/candidate-tree/final-diff triple",
        )
    try:
        # The T20.1 adapter consumes structural protocols whose version
        # members are plain ``int``; the published models carry the
        # stricter ``Literal[1]``, which satisfies the protocol at
        # runtime (the exact-int-1 validators are the closed contract).
        check_plan = PythonProjectAdapterV1(frozen).build_formal_plan(
            manifest,  # type: ignore[arg-type]
            identity,  # type: ignore[arg-type]
        )
    except CheckPlanError as error:
        return _rejected(
            _map_check_plan_error(error),
            f"the frozen formal check plan cannot be built: {error.reason}",
        )
    requests = tuple(
        _request_for(entry, ordinal, manifest)
        for ordinal, entry in enumerate(check_plan.entries, start=1)
    )
    bounds = FormalValidationBoundsV1(
        schema_version=1,
        full_check_timeout_seconds=_FROZEN_FULL_CHECK_TIMEOUT_SECONDS,
        formal_validation_timeout_seconds=_FROZEN_FORMAL_VALIDATION_TIMEOUT_SECONDS,
    )
    digest = domain_digest(
        "FormalValidationPlanV1",
        1,
        _plan_digest_body(
            check_plan_version=manifest.check_plan_version,
            adapter_version=manifest.adapter_version,
            python_version=manifest.python_version,
            pytest_version=manifest.pytest_version,
            report_plugin_version=manifest.report_plugin_version,
            ruff_version=manifest.ruff_version,
            mypy_version=manifest.mypy_version,
            docker_image_digest=manifest.docker_image_digest,
            docker_execution_profile_version=manifest.docker_execution_profile_version,
            reference_profile_digest=manifest.reference_profile_digest,
            snapshot_tree_digest=manifest.snapshot_tree_digest,
            repository_policy_digest=manifest.repository_policy_digest,
            protected_artifact_set_digest=manifest.protected_artifact_set_digest,
            resource_parameters_digest=manifest.resource_parameters_digest,
            environment_whitelist_digest=manifest.environment_whitelist_digest,
            manifest_digest=manifest.digest,
            candidate_digest=identity.digest,
            candidate_tree_digest=candidate.tree.digest,
            final_diff_digest=final_diff.digest,
            target_test_ids=tuple(manifest.target_test_ids),
            collected_node_ids=tuple(manifest.collected_node_ids),
            bounds=bounds,
            execution_requests=requests,
        ),
    )
    return FormalValidationPlanV1(
        schema_version=1,
        kind="FROZEN",
        error_code=None,
        check_plan_version=manifest.check_plan_version,
        adapter_version=manifest.adapter_version,
        python_version=manifest.python_version,
        pytest_version=manifest.pytest_version,
        report_plugin_version=manifest.report_plugin_version,
        ruff_version=manifest.ruff_version,
        mypy_version=manifest.mypy_version,
        docker_image_digest=manifest.docker_image_digest,
        docker_execution_profile_version=manifest.docker_execution_profile_version,
        reference_profile_digest=manifest.reference_profile_digest,
        snapshot_tree_digest=manifest.snapshot_tree_digest,
        repository_policy_digest=manifest.repository_policy_digest,
        protected_artifact_set_digest=manifest.protected_artifact_set_digest,
        resource_parameters_digest=manifest.resource_parameters_digest,
        environment_whitelist_digest=manifest.environment_whitelist_digest,
        manifest_digest=manifest.digest,
        candidate_digest=identity.digest,
        candidate_tree_digest=candidate.tree.digest,
        final_diff_digest=final_diff.digest,
        target_test_ids=tuple(manifest.target_test_ids),
        collected_node_ids=tuple(manifest.collected_node_ids),
        bounds=bounds,
        execution_requests=requests,
        candidate_tree=candidate.tree,
        digest=digest,
    )

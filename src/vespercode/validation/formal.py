"""T21.1 legacy step 21.C: pure formal success and VerifiedCandidate.

``evaluate_formal_success`` revalidates the exact Manifest, candidate
revision and bytes, policy/environment, target fingerprint, plan digest,
request identities, and evidence bindings without reading ambient state,
requires the complete formal plan to have one authoritative passing
result and successful teardown/cleanup for every request, and creates
``VerifiedCandidateV1`` only for exact current complete passing evidence
(SPEC §4.5 formal success predicate, conditions 1-8, in closed order);
every skip/error/timeout/missing/duplicate/drift/fingerprint mismatch
returns one typed ``FormalValidationFailureV1``.  Planning, execution,
lifecycle mutation, candidate writes, and approval decisions remain out
of scope (GREEN-4).

The predicate evaluates the SPEC conditions in a fixed closed order:

1.  binding revalidation — Snapshot/policy identity chain, Manifest and
    plan digest self-binding, the recomputed candidate identity, the
    plan's identity bindings, the frozen environment, and the recomputed
    protected-artifact set (conditions 1 and 7);
2.  evidence binding — the evidence must bind the exact plan digest and
    self-bind its own digest, and the execution must be structurally
    complete (exact ordered identities, nothing missing or duplicated);
3.  per-request authoritative evidence — every request must have parsed
    authoritative evidence (no raw timeout/error, no parse error) and a
    successful teardown/cleanup verdict (conditions 3, 4, and 8);
4.  collection identity — the final collection equals the Manifest's
    (condition 2);
5.  test states — no forbidden state and every node actually executed
    and PASS (conditions 3-5);
6.  tools — Ruff and Mypy both PASS (condition 6).

Only when every condition holds does one ``VerifiedCandidateV1`` exist.
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Literal, TypeAlias

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictStr,
    field_validator,
)

from vespercode.candidate.identity import build_candidate_identity
from vespercode.canonical.digest import domain_digest
from vespercode.contracts.evidence import _DIGEST_RE
from vespercode.contracts.optional import PresentV1
from vespercode.profiles.reference import (
    ReferenceProfileManifestV1,
    load_reference_profile,
)
from vespercode.trees.candidate import CandidateRevisionV1
from vespercode.validation.baseline import (
    compute_environment_whitelist_digest,
    compute_protected_artifact_set_digest,
    compute_resource_parameters_digest,
)
from vespercode.validation.formal_execution import (
    FormalRequestEvidenceV1,
    FormalValidationEvidenceV1,
    formal_validation_evidence_digest,
)
from vespercode.validation.formal_plan import (
    FormalValidationPlanV1,
    formal_validation_plan_digest,
)
from vespercode.validation.manifest import (
    ValidationManifestV1,
    validation_manifest_digest,
)

FormalValidationErrorCodeV1 = Literal[
    "CANDIDATE_STALE",
    "TREE_INTEGRITY_FAILED",
    "VALIDATION_ENVIRONMENT_CHANGED",
    "EXECUTION_WORKSPACE_MUTATED",
    "REPORTER_INVALID",
    "CHECK_ERROR",
    "CHECK_TIMEOUT",
    "FORMAL_VALIDATION_FAILED",
]
"""The closed formal-validation failure vocabulary.

Exactly the SPEC §4.5 error list subset applicable to the pure formal
success predicate plus the card-mandated ``CANDIDATE_STALE`` (the exact
21.A RED test asserts the literal code for the SPEC §4.3 stale-candidate
rejection).  Every predicate condition that has no dedicated SPEC error
code (evidence binding/completeness, collection equality, forbidden
test states, node execution/pass, tool PASS under the T20.2 baseline
precedent) fails closed as the SPEC's own ``FORMAL_VALIDATION_FAILED``
or the closest listed code, with the exact violated condition bound
deterministically in ``error_message`` — the SPEC §7.1 rule against
adding new error codes without a SPEC amendment is respected."""


class VerifiedCandidateV1(BaseModel):
    """SPEC §7 row: only complete formal validation creates it.

    ``candidate_id`` is exactly the current candidate identity digest,
    ``manifest_id`` the exact current Manifest digest, and
    ``formal_result_digest`` the §0.1 identity of the complete formal
    result (plan digest, evidence digest, candidate digest, manifest
    digest).  Only ``evaluate_formal_success`` can construct this value,
    from complete passing current evidence.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal[1]
    kind: Literal["VERIFIED"]
    candidate_id: StrictStr
    manifest_id: StrictStr
    formal_result_digest: StrictStr

    @field_validator("schema_version", mode="before")
    @classmethod
    def _schema_version_is_exact_int(cls, value: object) -> object:
        if not isinstance(value, int) or isinstance(value, bool):
            raise ValueError("schema_version must be the decimal integer 1")
        return value

    @field_validator("candidate_id", "manifest_id", "formal_result_digest")
    @classmethod
    def _digests_have_exact_form(cls, value: str) -> str:
        if _DIGEST_RE.fullmatch(value) is None:
            raise ValueError("must be exactly 64 lowercase hexadecimal characters")
        return value


class FormalValidationFailureV1(BaseModel):
    """One typed closed formal-validation failure.

    The stable error code and a deterministic message; every skip/error/
    timeout/missing/duplicate/drift/fingerprint mismatch returns exactly
    one failure, never a partial success.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal[1]
    kind: Literal["FAILED"]
    error_code: FormalValidationErrorCodeV1
    error_message: StrictStr

    @field_validator("schema_version", mode="before")
    @classmethod
    def _schema_version_is_exact_int(cls, value: object) -> object:
        if not isinstance(value, int) or isinstance(value, bool):
            raise ValueError("schema_version must be the decimal integer 1")
        return value

    @field_validator("error_message")
    @classmethod
    def _error_message_is_non_empty(cls, value: str) -> str:
        if value == "":
            raise ValueError("failure messages must be non-empty")
        return value


FormalValidationOutcomeV1: TypeAlias = Annotated[
    VerifiedCandidateV1 | FormalValidationFailureV1,
    Field(discriminator="kind"),
]
"""SPEC §4.5 output: ``VerifiedCandidate | FormalValidationFailure``."""


def _failure(
    error_code: FormalValidationErrorCodeV1, error_message: str
) -> FormalValidationFailureV1:
    """One typed closed failure."""
    return FormalValidationFailureV1(
        schema_version=1,
        kind="FAILED",
        error_code=error_code,
        error_message=error_message,
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


def _authoritative_evidence(
    row: FormalRequestEvidenceV1,
) -> object | None:
    """The parsed authoritative evidence of one executed row (None when
    the row is rejected or carries an explicit parse error)."""
    if isinstance(row.rejection, PresentV1):
        return None
    if isinstance(row.pytest_evidence, PresentV1):
        return row.pytest_evidence.value
    if isinstance(row.tool_result, PresentV1):
        return row.tool_result.value
    return None


def evaluate_formal_success(
    manifest: ValidationManifestV1,
    candidate: CandidateRevisionV1,
    plan: FormalValidationPlanV1,
    evidence: FormalValidationEvidenceV1,
) -> FormalValidationOutcomeV1:
    """Evaluate the complete formal predicate and create
    ``VerifiedCandidateV1`` only for exact current complete passing
    evidence (GREEN-1..GREEN-4)."""
    # Stage 1: binding revalidation (conditions 1 and 7).
    try:
        frozen = _load_frozen_manifest()
    except Exception:
        return _failure(
            "VALIDATION_ENVIRONMENT_CHANGED",
            "the frozen reference profile cannot be loaded",
        )
    snapshot = candidate.tree.snapshot
    if snapshot.root_digest != manifest.snapshot_tree_digest:
        return _failure(
            "TREE_INTEGRITY_FAILED",
            "the candidate Snapshot does not bind the Manifest's identity",
        )
    if snapshot.repository_policy_digest != manifest.repository_policy_digest:
        return _failure(
            "TREE_INTEGRITY_FAILED",
            "the candidate Snapshot and the Manifest bind different policies",
        )
    if manifest.repository_policy_digest != frozen.editable_path_policy.digest:
        return _failure(
            "TREE_INTEGRITY_FAILED",
            "the Manifest does not bind the frozen editable path policy",
        )
    if manifest.digest != validation_manifest_digest(manifest):
        return _failure(
            "TREE_INTEGRITY_FAILED",
            "the Manifest digest does not bind its exact current fields",
        )
    if plan.digest != formal_validation_plan_digest(plan):
        return _failure(
            "TREE_INTEGRITY_FAILED",
            "the plan digest does not bind its exact current fields",
        )
    identity = build_candidate_identity(
        snapshot.root_digest, candidate.tree.digest, plan.final_diff_digest
    )
    if candidate.candidate_digest != identity.digest:
        return _failure(
            "CANDIDATE_STALE",
            "the candidate identity no longer matches the exact current "
            "Snapshot/candidate-tree/final-diff triple",
        )
    if (
        plan.manifest_digest != manifest.digest
        or plan.candidate_digest != candidate.candidate_digest
        or plan.snapshot_tree_digest != snapshot.root_digest
        or plan.repository_policy_digest != manifest.repository_policy_digest
        or plan.candidate_tree_digest != candidate.tree.digest
    ):
        return _failure(
            "TREE_INTEGRITY_FAILED",
            "the plan no longer binds the exact current Manifest/candidate "
            "identity chain",
        )
    if manifest.reference_profile_digest != frozen.digest:
        return _failure(
            "VALIDATION_ENVIRONMENT_CHANGED",
            "the Manifest does not bind the frozen reference profile",
        )
    if plan.reference_profile_digest != frozen.digest:
        return _failure(
            "VALIDATION_ENVIRONMENT_CHANGED",
            "the plan does not bind the frozen reference profile",
        )
    if plan.resource_parameters_digest != compute_resource_parameters_digest():
        return _failure(
            "VALIDATION_ENVIRONMENT_CHANGED",
            "the resource parameters digest does not bind the frozen profile",
        )
    if plan.environment_whitelist_digest != compute_environment_whitelist_digest():
        return _failure(
            "VALIDATION_ENVIRONMENT_CHANGED",
            "the environment whitelist digest does not bind the frozen profile",
        )
    protected_set = compute_protected_artifact_set_digest(snapshot)
    if protected_set != plan.protected_artifact_set_digest:
        return _failure(
            "TREE_INTEGRITY_FAILED",
            "the recomputed protected artifact set does not bind the plan",
        )
    if protected_set != manifest.protected_artifact_set_digest:
        return _failure(
            "TREE_INTEGRITY_FAILED",
            "the recomputed protected artifact set does not bind the Manifest",
        )

    # Stage 2: evidence binding and structural completeness.
    if evidence.plan_digest != plan.digest:
        return _failure(
            "FORMAL_VALIDATION_FAILED",
            "the evidence does not bind the exact executed plan",
        )
    if evidence.evidence_digest != formal_validation_evidence_digest(evidence):
        return _failure(
            "FORMAL_VALIDATION_FAILED",
            "the evidence digest does not bind its exact fields",
        )
    if (
        evidence.executed_request_ids != plan.request_ids
        or evidence.missing_request_ids != ()
        or evidence.duplicate_request_ids != ()
    ):
        return _failure(
            "FORMAL_VALIDATION_FAILED",
            "the formal plan did not execute completely: missing, duplicate, "
            "or partial execution remains explicit",
        )

    # Stage 3: every request must have one authoritative passing result
    # and a successful teardown/cleanup (conditions 3, 4, and 8).
    for index, row in enumerate(evidence.evidence):
        frozen_request = plan.execution_requests[index]
        if (
            row.request_id != frozen_request.request_id
            or row.check_kind != frozen_request.check_kind
        ):
            return _failure(
                "FORMAL_VALIDATION_FAILED",
                f"the evidence row {row.request_id!r} does not bind the "
                f"frozen request identity",
            )
        if isinstance(row.rejection, PresentV1):
            return _failure(
                "FORMAL_VALIDATION_FAILED",
                f"request {row.request_id!r} was never executed",
            )
        raw = row.raw
        if raw is not None and raw.request_id != row.request_id:
            return _failure(
                "FORMAL_VALIDATION_FAILED",
                f"the raw evidence {raw.request_id!r} does not bind the "
                f"evidence row {row.request_id!r}",
            )
        if raw is not None:
            if raw.error_code == "CHECK_TIMEOUT":
                return _failure(
                    "CHECK_TIMEOUT",
                    f"request {row.request_id!r} timed out",
                )
            if raw.error_code is not None:
                return _failure(
                    "CHECK_ERROR",
                    f"request {row.request_id!r} failed at the execution layer",
                )
        if isinstance(row.parse_error, PresentV1):
            code = row.parse_error.value
            if code in ("CHECK_TIMEOUT", "CHECK_ERROR", "REPORTER_INVALID"):
                return _failure(
                    code,  # type: ignore[arg-type]
                    f"request {row.request_id!r} produced no authoritative "
                    f"evidence: {code}",
                )
            return _failure(
                "CHECK_ERROR",
                f"request {row.request_id!r} produced no authoritative evidence",
            )
        cleanup = row.cleanup
        if cleanup is not None:
            if not cleanup.container_removed or not cleanup.materialization_removed:
                return _failure(
                    "EXECUTION_WORKSPACE_MUTATED",
                    f"request {row.request_id!r} left execution residue",
                )
            if not cleanup.workspace_unchanged:
                return _failure(
                    "EXECUTION_WORKSPACE_MUTATED",
                    f"request {row.request_id!r} mutated the execution workspace",
                )

    # Stage 4: the final pytest collection must equal the Manifest's
    # collection exactly (condition 2).
    full_evidence = _authoritative_evidence(evidence.evidence[1])
    if (
        full_evidence is None
        or getattr(full_evidence, "run_kind", None) != "FULL_PYTEST"
    ):
        return _failure(
            "FORMAL_VALIDATION_FAILED",
            "the full pytest check produced no authoritative evidence",
        )
    if tuple(getattr(full_evidence, "collected_node_ids", ())) != tuple(
        manifest.collected_node_ids
    ):
        return _failure(
            "FORMAL_VALIDATION_FAILED",
            "the final pytest collection does not equal the Manifest's collection",
        )

    # Stage 5: no forbidden test state and every node actually executed
    # and PASS (conditions 3-5).  Both pytest runs are scanned — the
    # collect-only row and the full row — because a collection or
    # session error is a forbidden-state fact of either run and a
    # crafted-but-valid collect row must not evade the scan.
    collect_evidence = _authoritative_evidence(evidence.evidence[0])
    if (
        collect_evidence is None
        or getattr(collect_evidence, "run_kind", None) != "COLLECT_ONLY"
    ):
        return _failure(
            "FORMAL_VALIDATION_FAILED",
            "the collect-only request produced no authoritative collect evidence",
        )
    collect_events = (
        tuple(getattr(collect_evidence, "events", ()))
        if collect_evidence is not None
        else ()
    )
    events = tuple(getattr(full_evidence, "events", ())) + collect_events
    for event in events:
        if event.event_type == "SESSION_ERROR":
            return _failure(
                "FORMAL_VALIDATION_FAILED",
                "the final run recorded a session/collection error",
            )
        if event.event_type == "DESELECTED":
            return _failure(
                "FORMAL_VALIDATION_FAILED",
                "the final run deselected a collected node",
            )
        if event.event_type == "TEST_PHASE" and isinstance(event.outcome, PresentV1):
            if event.outcome.value in (
                "SKIP",
                "XFAIL",
                "XPASS",
                "DESELECTED",
                "NOT_RUN",
                "ERROR",
            ):
                return _failure(
                    "FORMAL_VALIDATION_FAILED",
                    f"the final run recorded the forbidden state {event.outcome.value}",
                )
    for node_id in manifest.collected_node_ids:
        call_events = [
            event
            for event in events
            if event.event_type == "TEST_PHASE"
            and isinstance(event.node_id, PresentV1)
            and event.node_id.value == node_id
            and isinstance(event.phase, PresentV1)
            and event.phase.value == "CALL"
        ]
        if (
            len(call_events) != 1
            or not isinstance(call_events[0].outcome, PresentV1)
            or call_events[0].outcome.value != "PASS"
        ):
            return _failure(
                "FORMAL_VALIDATION_FAILED",
                f"node {node_id!r} did not actually execute and pass",
            )

    # Stage 6: Ruff and Mypy must both PASS (condition 6).
    for row in evidence.evidence[2:]:
        result = _authoritative_evidence(row)
        if result is None or getattr(result, "status", None) != "PASS":
            return _failure(
                "CHECK_ERROR",
                f"request {row.request_id!r} did not pass its check",
            )
        if getattr(result, "check_kind", None) != row.check_kind:
            return _failure(
                "FORMAL_VALIDATION_FAILED",
                f"the check result {getattr(result, 'check_kind', None)!r} "
                f"does not bind the request {row.request_id!r}",
            )

    # Success: only exact current complete passing evidence verifies.
    formal_result_digest = domain_digest(
        "FormalValidationResultV1",
        1,
        {
            "candidate_digest": candidate.candidate_digest,
            "manifest_digest": manifest.digest,
            "plan_digest": plan.digest,
            "evidence_digest": evidence.evidence_digest,
        },
    )
    return VerifiedCandidateV1(
        schema_version=1,
        kind="VERIFIED",
        candidate_id=candidate.candidate_digest,
        manifest_id=manifest.digest,
        formal_result_digest=formal_result_digest,
    )

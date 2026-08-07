"""T13.1 legacy step 13: centralized versioned ALLOW/ASK/DENY evaluation.

``PolicyEngine`` is the one pure, versioned policy evaluation over
immutable facts (SPEC §4.4.1): the six registered model actions are
allowed only in ``RUNNING(AGENT_LOOP)``, ``ASK`` exists only for the
control-plane final writeback operation, and every other capability is
a hard ``DENY`` from the single versioned rule table.  The governance
policy digest binds that rule table plus the sole editable policy
digest (§1.4.1/AC-31), and the immutable ``PolicyContextV1`` carries
only frozen digests and deterministic pre-policy facts — no prompt
text, repository content, mutable config, Grant, or approval state can
enter it, so none of those can widen the table (GREEN-1).  The
deterministic pre-policy path/protected/sensitive reason is preserved
exactly (GREEN-5), and an approval can never be passed to or override
an evaluation (GREEN-3).  Evaluation has no external side effects: it
cannot call a tool, create a wait, consume an approval, or mutate a
candidate; decisions are memoized by the (policy digest, action type,
action semantic digest, immutable context digest) key — a function of
the decision inputs — never by action instance id or mutable approval
status (GREEN-6/GREEN-7).  Approval persistence, tool dispatch, waits,
and candidate mutation remain out of scope (GREEN-4).
"""

from __future__ import annotations

from typing import Final, Literal, TypeAlias

from pydantic import (
    BaseModel,
    ConfigDict,
    StrictStr,
    field_validator,
    model_validator,
)

from vespercode.candidate.patch_engine import CandidatePatchErrorCodeV1
from vespercode.canonical.digest import domain_digest
from vespercode.canonical.json_v1 import CanonicalValueV1
from vespercode.contracts.action import ActionInstanceV1, PolicyDecisionV1
from vespercode.contracts.evidence import _DIGEST_RE
from vespercode.contracts.run import RunPhase

PolicyReasonCodeV1: TypeAlias = (
    CandidatePatchErrorCodeV1
    | Literal[
        "ACTION_NOT_ALLOWED_IN_PHASE",
        "UNKNOWN_CAPABILITY",
        "ARBITRARY_COMMAND",
        "SHELL_FIELD",
        "ACCEPTANCE_MODIFICATION",
        "CONFIG_MODIFICATION",
        "CONTROL_PLANE_MODIFICATION",
        "WRITEBACK_FACTS_UNVERIFIED",
    ]
)
"""The closed stable DENY reasons (SPEC §4.3 pre-policy codes plus the
versioned-rule-table capability codes)."""

PatchPathFactV1: TypeAlias = Literal["OK"] | CandidatePatchErrorCodeV1
"""One deterministic pre-policy patch fact: ``OK`` or the exact closed
rejection code the path/limit/candidate stage already produced."""


def _reject_coerced_schema_version(value: object) -> object:
    """Reject bool/float/string spelling of the integer schema version."""
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError("schema_version must be the decimal integer 1")
    return value


def _require_sha256_hex(value: str) -> str:
    """The closed 64-lowercase-hex digest form shared by every digest field."""
    if _DIGEST_RE.fullmatch(value) is None:
        raise ValueError("digests must be exactly 64 lowercase hexadecimal characters")
    return value


# The single versioned rule table (SPEC §4.2.3/§4.4.1): the registered
# model action set, the frozen check-plan ids, the sole approval subject,
# and the hard-DENY capability mapping.  The governance policy digest
# binds every exact entry, so the table can only change in code, never
# through config, prompt, repository text, Grant, or approval.
_REGISTERED_MODEL_ACTION_TYPES_V1: Final[tuple[str, ...]] = (
    "apply_candidate_patch",
    "list_files",
    "propose_completion",
    "read_file",
    "run_check",
    "search_text",
)
_ALLOWED_CHECK_PLAN_IDS_V1: Final[tuple[str, ...]] = (
    "FULL_PYTEST",
    "MYPY",
    "RUFF",
    "TARGET_TESTS",
)
FinalWritebackActionTypeV1 = Literal["final_writeback"]
"""The closed control-plane writeback action type (SPEC §4.4.1 ASK)."""

_CONTROL_PLANE_WRITEBACK_TYPE_V1: Final[FinalWritebackActionTypeV1] = "final_writeback"
_DENIED_CAPABILITY_TYPES_V1: Final[tuple[tuple[str, PolicyReasonCodeV1], ...]] = (
    # arbitrary-command capabilities (SPEC §4.4.1 "任意命令")
    ("execute_command", "ARBITRARY_COMMAND"),
    ("run_command", "ARBITRARY_COMMAND"),
    ("run_executable", "ARBITRARY_COMMAND"),
    ("run_script", "ARBITRARY_COMMAND"),
    ("run_shell", "ARBITRARY_COMMAND"),
    # shell-field carriers (SPEC §4.4.1 / AC-17 "shell 字段")
    ("run_with_shell", "SHELL_FIELD"),
    ("shell", "SHELL_FIELD"),
    # acceptance tampering (SPEC §4.4.1 "验收篡改")
    ("edit_pytest_config", "ACCEPTANCE_MODIFICATION"),
    ("edit_tests", "ACCEPTANCE_MODIFICATION"),
    ("modify_check_config", "ACCEPTANCE_MODIFICATION"),
    ("modify_tests", "ACCEPTANCE_MODIFICATION"),
    # configuration modification (SPEC §4.4.1 "控制面修改" config branch)
    ("edit_config", "CONFIG_MODIFICATION"),
    ("modify_config", "CONFIG_MODIFICATION"),
    ("modify_pyproject_toml", "CONFIG_MODIFICATION"),
    # control-plane modification (SPEC §4.4.1 "控制面修改")
    ("approve", "CONTROL_PLANE_MODIFICATION"),
    ("modify_approval", "CONTROL_PLANE_MODIFICATION"),
    ("modify_manifest", "CONTROL_PLANE_MODIFICATION"),
    ("modify_policy", "CONTROL_PLANE_MODIFICATION"),
    ("skip_approval", "CONTROL_PLANE_MODIFICATION"),
)
_DENIED_CAPABILITY_REASONS_V1: Final[dict[str, PolicyReasonCodeV1]] = dict(
    _DENIED_CAPABILITY_TYPES_V1
)


def governance_policy_digest(editable_policy_digest: str) -> str:
    """The §0.1 identity of the versioned rule table plus the sole
    editable policy digest (SPEC §4.4.1/AC-31).

    The digest binds every exact table entry (registered action types,
    frozen check-plan ids, the writeback action type, the denied
    capability mapping) and the one editable policy digest; it never
    reads prompt text, repository files, mutable config, Grant, or
    approval state (GREEN-1).
    """
    return domain_digest(
        "GovernancePolicyV1",
        1,
        {
            "schema_version": 1,
            "rule_version": 1,
            "registered_model_action_types": _REGISTERED_MODEL_ACTION_TYPES_V1,
            "allowed_check_plan_ids": _ALLOWED_CHECK_PLAN_IDS_V1,
            "control_plane_writeback_action_type": _CONTROL_PLANE_WRITEBACK_TYPE_V1,
            "denied_capability_types": _DENIED_CAPABILITY_TYPES_V1,
            "editable_policy_digest": editable_policy_digest,
        },
    )


class FinalWritebackOperationV1(BaseModel):
    """The control-plane final authority writeback facts (SPEC §4.4.1 ASK).

    This closed value is the only approval subject the engine can ever
    return ``ASK`` for.  The model path never constructs it — the six
    closed action schemas carry no such value and the model envelope
    carries only ``schema_version``/``action_type`` — so model actions
    cannot manufacture this operation or any other approval subject
    (GREEN-3).
    """

    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal[1]
    action_type: FinalWritebackActionTypeV1
    candidate_digest: StrictStr
    final_diff_digest: StrictStr
    policy_digest: StrictStr

    @field_validator("schema_version", mode="before")
    @classmethod
    def _schema_version_is_exact_int(cls, value: object) -> object:
        return _reject_coerced_schema_version(value)

    @field_validator("candidate_digest", "final_diff_digest", "policy_digest")
    @classmethod
    def _digests_must_be_sha256_hex(cls, value: str) -> str:
        return _require_sha256_hex(value)


def _optional_value(value: CanonicalValueV1 | None) -> CanonicalValueV1:
    """The canonical ABSENT/PRESENT encoding of one optional fact."""
    if value is None:
        return {"kind": "ABSENT"}
    return {"kind": "PRESENT", "value": value}


def _canonical_writeback(
    writeback: FinalWritebackOperationV1 | None,
) -> CanonicalValueV1:
    """One canonical §0.1 value for the optional writeback facts."""
    if writeback is None:
        return {"kind": "ABSENT"}
    return {
        "kind": "PRESENT",
        "value": {
            "schema_version": writeback.schema_version,
            "action_type": writeback.action_type,
            "candidate_digest": writeback.candidate_digest,
            "final_diff_digest": writeback.final_diff_digest,
            "policy_digest": writeback.policy_digest,
        },
    }


def policy_context_digest(
    *,
    run_phase: RunPhase,
    editable_policy_digest: str,
    reference_profile_digest: str,
    candidate_digest: str | None,
    final_diff_digest: str | None,
    patch_path_fact: PatchPathFactV1 | None,
    writeback: FinalWritebackOperationV1 | None,
) -> str:
    """The §0.1 identity of every exact immutable evaluation fact.

    ``policy_digest`` is not a separate input: it is the governance
    digest over the versioned rule table plus ``editable_policy_digest``,
    computed here so the context digest always binds the derived policy
    identity of the same table.
    """
    return domain_digest(
        "PolicyContextV1",
        1,
        {
            "schema_version": 1,
            "run_phase": run_phase,
            "policy_digest": governance_policy_digest(editable_policy_digest),
            "editable_policy_digest": editable_policy_digest,
            "reference_profile_digest": reference_profile_digest,
            "candidate_digest": _optional_value(candidate_digest),
            "final_diff_digest": _optional_value(final_diff_digest),
            "patch_path_fact": _optional_value(patch_path_fact),
            "writeback": _canonical_writeback(writeback),
        },
    )


class PolicyContextV1(BaseModel):
    """One immutable evaluation context over frozen facts only.

    The context binds the governance policy digest (derived from the
    versioned rule table plus the sole editable policy digest), the
    frozen reference profile digest, the current candidate/final-diff
    identities, the deterministic pre-policy patch fact, and the
    optional control-plane writeback facts; its self-digest binds every
    exact field.  No prompt text, repository content, mutable config,
    Grant, or approval state can enter the context (GREEN-1).
    """

    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal[1]
    run_phase: RunPhase
    policy_digest: StrictStr
    editable_policy_digest: StrictStr
    reference_profile_digest: StrictStr
    candidate_digest: StrictStr | None = None
    final_diff_digest: StrictStr | None = None
    patch_path_fact: PatchPathFactV1 | None = None
    writeback: FinalWritebackOperationV1 | None = None
    digest: StrictStr

    @field_validator("schema_version", mode="before")
    @classmethod
    def _schema_version_is_exact_int(cls, value: object) -> object:
        return _reject_coerced_schema_version(value)

    @field_validator(
        "policy_digest",
        "editable_policy_digest",
        "reference_profile_digest",
        "candidate_digest",
        "final_diff_digest",
        "digest",
    )
    @classmethod
    def _digests_must_be_sha256_hex(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return _require_sha256_hex(value)

    @model_validator(mode="after")
    def _bind_immutable_facts(self) -> PolicyContextV1:
        if self.policy_digest != governance_policy_digest(self.editable_policy_digest):
            raise ValueError(
                "policy_digest must bind the versioned rule table and the "
                "sole editable policy digest"
            )
        if self.digest != policy_context_digest(
            run_phase=self.run_phase,
            editable_policy_digest=self.editable_policy_digest,
            reference_profile_digest=self.reference_profile_digest,
            candidate_digest=self.candidate_digest,
            final_diff_digest=self.final_diff_digest,
            patch_path_fact=self.patch_path_fact,
            writeback=self.writeback,
        ):
            raise ValueError("digest must bind every other exact field")
        return self


class PolicyEvaluationV1(BaseModel):
    """One closed evaluation: ALLOW | ASK | DENY with the stable DENY
    reason (SPEC §4.4.1 / NFR-USE stable rejection codes)."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal[1]
    decision: PolicyDecisionV1
    reason_code: PolicyReasonCodeV1 | None = None

    @field_validator("schema_version", mode="before")
    @classmethod
    def _schema_version_is_exact_int(cls, value: object) -> object:
        return _reject_coerced_schema_version(value)

    @model_validator(mode="after")
    def _require_exact_outcome(self) -> PolicyEvaluationV1:
        if self.decision == "DENY":
            if self.reason_code is None:
                raise ValueError("DENY evaluations require the stable reason code")
        elif self.reason_code is not None:
            raise ValueError("ALLOW and ASK evaluations must not carry a reason code")
        return self


class PolicyEngine:
    """One pure, versioned ALLOW | ASK | DENY evaluation over immutable
    facts (SPEC §4.4.1).

    ``evaluate`` is closed to ``(instance, context)``: it accepts no
    approval, Grant, config, or mutable state, so an approval can never
    convert a ``DENY`` evaluation into ``ALLOW`` (GREEN-3/GREEN-5).
    Decisions are memoized by a key that is a function of the decision
    inputs — (policy digest, action type, action semantic digest,
    immutable context digest) — never by action instance id or mutable
    approval status (GREEN-7).  The action type is part of the key
    because the semantic digest is an unconstrained identity in this
    baseline (no ``ActionSemanticDigestV1`` producer exists yet): two
    contract-valid instances can share a semantic digest while requiring
    different decisions, so a memo keyed only by the digest would be
    unsound.  The memo is per-engine (one per Run) and bounded by the
    number of distinct decision keys observed; it has no external
    effect.
    """

    def __init__(self) -> None:
        self._cache: dict[tuple[str, str, str, str], PolicyEvaluationV1] = {}
        self._cache_hits = 0

    @property
    def cache_hits(self) -> int:
        """The number of memoized returns (deterministic test hook)."""
        return self._cache_hits

    def evaluate(
        self, instance: ActionInstanceV1, context: PolicyContextV1
    ) -> PolicyEvaluationV1:
        key = (
            context.policy_digest,
            instance.action.action_type,
            instance.semantic_digest,
            context.digest,
        )
        cached = self._cache.get(key)
        if cached is not None:
            self._cache_hits += 1
            return cached
        decision = _decide(instance, context)
        self._cache[key] = decision
        return decision


def _decide(instance: ActionInstanceV1, context: PolicyContextV1) -> PolicyEvaluationV1:
    """One deterministic decision over the shared envelope and frozen facts.

    Unregistered capabilities (including command/shell/acceptance/config/
    control-plane types) are hard ``DENY`` in every phase; the six
    registered model actions are decided per phase and pre-policy facts;
    the control-plane writeback is the only ``ASK`` subject (GREEN-3).
    """
    action_type = instance.action.action_type
    if action_type in _REGISTERED_MODEL_ACTION_TYPES_V1:
        return _decide_model_action(action_type, context)
    if action_type == _CONTROL_PLANE_WRITEBACK_TYPE_V1:
        return _decide_control_plane_writeback(context)
    return _deny(_DENIED_CAPABILITY_REASONS_V1.get(action_type, "UNKNOWN_CAPABILITY"))


def _decide_model_action(
    action_type: str, context: PolicyContextV1
) -> PolicyEvaluationV1:
    """One registered model action: allowed only in ``RUNNING(AGENT_LOOP)``
    and only when its deterministic pre-policy facts hold (GREEN-2)."""
    if context.run_phase != "AGENT_LOOP":
        return _deny("ACTION_NOT_ALLOWED_IN_PHASE")
    if action_type == "apply_candidate_patch":
        return _decide_candidate_patch(context)
    return _allow()


def _decide_candidate_patch(context: PolicyContextV1) -> PolicyEvaluationV1:
    """One current-candidate patch: the pre-policy fact decides, and the
    more specific stable path/protected/sensitive reason is preserved
    exactly (GREEN-5)."""
    if context.candidate_digest is None:
        return _deny("STALE_CANDIDATE")
    fact = context.patch_path_fact
    if fact is None:
        return _deny("TREE_INTEGRITY_FAILED")
    if fact == "OK":
        return _allow()
    return _deny(fact)


def _decide_control_plane_writeback(
    context: PolicyContextV1,
) -> PolicyEvaluationV1:
    """The sole ASK subject (GREEN-3): the control-plane final writeback.

    The writeback facts must exist and bind the same policy, candidate,
    and final-diff identity as the frozen context; any gap fails closed
    with ``WRITEBACK_FACTS_UNVERIFIED`` or ``TREE_INTEGRITY_FAILED`` and
    never reaches ``ASK``.
    """
    writeback = context.writeback
    if writeback is None:
        return _deny("WRITEBACK_FACTS_UNVERIFIED")
    if (
        writeback.policy_digest != context.policy_digest
        or writeback.candidate_digest != context.candidate_digest
        or writeback.final_diff_digest != context.final_diff_digest
    ):
        return _deny("TREE_INTEGRITY_FAILED")
    return _ask()


def _allow() -> PolicyEvaluationV1:
    return PolicyEvaluationV1(schema_version=1, decision="ALLOW")


def _ask() -> PolicyEvaluationV1:
    return PolicyEvaluationV1(schema_version=1, decision="ASK")


def _deny(reason: PolicyReasonCodeV1) -> PolicyEvaluationV1:
    return PolicyEvaluationV1(schema_version=1, decision="DENY", reason_code=reason)

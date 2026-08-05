"""T13.1 legacy step 13: policy decision/precedence/cache matrix tests.

The Domain companion of ``test_policy.py``: every ALLOW row, every
phase-forbidden row, the preserved pre-policy path/protected/sensitive
reasons, the hard-DENY capability table, the unknown-action fail-closed
behavior, the sole ASK subject (control-plane final writeback) with its
identity-mismatch rejections, the approval-immunity of every DENY, the
decision cache keyed only by (policy digest, action semantic digest,
immutable context digest), the governance-digest propagation, and the
pure-evaluation import surface (GREEN-1..GREEN-7).
"""

from __future__ import annotations

import ast
import hashlib
import inspect
from pathlib import Path
from typing import Any, cast, get_args

import pytest

# The policy engine consumes pydantic runtime contracts; the hash-locked
# gate toolchain installs no runtime dependencies, so this module skips
# cleanly there (formal env runs it fully).
pytest.importorskip("pydantic")

from pydantic import ValidationError

from src.vespercode.candidate.patch_engine import CandidatePatchErrorCodeV1
from src.vespercode.canonical.digest import domain_digest
from src.vespercode.contracts.action import (
    ActionInstanceV1,
    CheckPlanIdV1,
    SharedActionV1,
)
from src.vespercode.contracts.run import RunPhase
from src.vespercode.governance.policy import (
    FinalWritebackOperationV1,
    PatchPathFactV1,
    PolicyContextV1,
    PolicyEngine,
    PolicyEvaluationV1,
    _ALLOWED_CHECK_PLAN_IDS_V1,
    _DENIED_CAPABILITY_TYPES_V1,
    _REGISTERED_MODEL_ACTION_TYPES_V1,
    governance_policy_digest,
    policy_context_digest,
)
from src.vespercode.profiles.reference import (
    ReferenceProfileManifestV1,
    load_reference_profile,
)

_REFERENCE_MANIFEST = (
    Path(__file__).resolve().parents[3] / "reference/manifest/reference-profile-v1.json"
)
_CURRENT_CANDIDATE = hashlib.sha256(b"current-candidate").hexdigest()
_CURRENT_FINAL_DIFF = hashlib.sha256(b"current-final-diff").hexdigest()
_NON_AGENT_LOOP_PHASES: tuple[RunPhase, ...] = tuple(
    phase for phase in get_args(RunPhase) if phase != "AGENT_LOOP"
)


def builtin_reference() -> ReferenceProfileManifestV1:
    """The frozen packaged reference profile (digest-verified)."""
    loaded = load_reference_profile(_REFERENCE_MANIFEST.read_bytes())
    assert isinstance(loaded, ReferenceProfileManifestV1)
    return loaded


def semantic_digest_for(action_type: str) -> str:
    """A deterministic action semantic identity for one action type."""
    return hashlib.sha256(action_type.encode("utf-8")).hexdigest()


def action_instance(action_type: str, action_id: str = "action-1") -> ActionInstanceV1:
    """One Harness-bound action instance with a stable semantic identity."""
    return action_instance_with_digest(
        action_type, semantic_digest_for(action_type), action_id=action_id
    )


def action_instance_with_digest(
    action_type: str, semantic_digest: str, action_id: str = "action-1"
) -> ActionInstanceV1:
    """One contract-valid instance carrying an arbitrary semantic digest.

    T05.1 validates only that the instance digest binds ``(action_id,
    semantic_digest)``; the semantic digest itself is an unconstrained
    64-hex identity in this baseline (no ``ActionSemanticDigestV1``
    producer exists yet), so a caller can mint any digest for any action
    type.  The decision memo must therefore key on the decision inputs,
    never on the unbound digest alone.
    """
    return ActionInstanceV1(
        action_id=action_id,
        semantic_digest=semantic_digest,
        instance_digest=domain_digest(
            "ActionInstanceDigestV1",
            1,
            {
                "schema_version": 1,
                "action_id": action_id,
                "semantic_digest": semantic_digest,
            },
        ),
        action=SharedActionV1(schema_version=1, action_type=action_type),
    )


def policy_context(
    *,
    run_phase: RunPhase = "AGENT_LOOP",
    editable_policy_digest: str | None = None,
    candidate_digest: str | None = _CURRENT_CANDIDATE,
    final_diff_digest: str | None = None,
    patch_path_fact: PatchPathFactV1 | None = "OK",
    writeback: FinalWritebackOperationV1 | None = None,
) -> PolicyContextV1:
    """One immutable context bound to the frozen built-in policy/profile.

    ``editable_policy_digest`` defaults to the packaged built-in policy
    digest; any other 64-hex value proves the engine binds only the
    derived digest chain, never packaged bytes.
    """
    manifest = builtin_reference()
    if editable_policy_digest is None:
        editable_policy_digest = manifest.editable_path_policy.digest
    return PolicyContextV1(
        schema_version=1,
        run_phase=run_phase,
        editable_policy_digest=editable_policy_digest,
        reference_profile_digest=manifest.digest,
        policy_digest=governance_policy_digest(editable_policy_digest),
        candidate_digest=candidate_digest,
        final_diff_digest=final_diff_digest,
        patch_path_fact=patch_path_fact,
        writeback=writeback,
        digest=policy_context_digest(
            run_phase=run_phase,
            editable_policy_digest=editable_policy_digest,
            reference_profile_digest=manifest.digest,
            candidate_digest=candidate_digest,
            final_diff_digest=final_diff_digest,
            patch_path_fact=patch_path_fact,
            writeback=writeback,
        ),
    )


def writeback_operation(
    *,
    candidate_digest: str = _CURRENT_CANDIDATE,
    final_diff_digest: str = _CURRENT_FINAL_DIFF,
    policy_digest: str | None = None,
) -> FinalWritebackOperationV1:
    """One control-plane final writeback facts value bound to the same
    governance policy digest as ``policy_context``."""
    manifest = builtin_reference()
    if policy_digest is None:
        policy_digest = governance_policy_digest(manifest.editable_path_policy.digest)
    return FinalWritebackOperationV1(
        schema_version=1,
        action_type="final_writeback",
        candidate_digest=candidate_digest,
        final_diff_digest=final_diff_digest,
        policy_digest=policy_digest,
    )


# Every row that must DENY, with the context overrides that produce it.
_DENY_SCENARIOS: tuple[tuple[str, dict[str, object]], ...] = (
    ("apply_candidate_patch", {"patch_path_fact": "PATCH_PATH_NOT_EDITABLE"}),
    ("apply_candidate_patch", {"patch_path_fact": "PROTECTED_ARTIFACT_CHANGED"}),
    ("apply_candidate_patch", {"patch_path_fact": "SENSITIVE_PATH"}),
    ("apply_candidate_patch", {"patch_path_fact": "PATCH_LIMIT_EXCEEDED"}),
    ("apply_candidate_patch", {"patch_path_fact": "TREE_INTEGRITY_FAILED"}),
    ("apply_candidate_patch", {"patch_path_fact": None}),
    ("apply_candidate_patch", {"candidate_digest": None}),
    ("run_shell", {}),
    ("run_check", {"run_phase": "PREFLIGHT"}),
    ("read_file", {"run_phase": "PERSISTENCE"}),
    ("final_writeback", {}),
    ("mystery_capability", {}),
)


class TestDecisionMatrix:
    """The complete ALLOW/ASK/DENY rows (GREEN-2/GREEN-3/GREEN-4)."""

    @pytest.mark.parametrize("action_type", _REGISTERED_MODEL_ACTION_TYPES_V1)
    def test_registered_model_actions_are_allowed_in_agent_loop(
        self, action_type: str
    ) -> None:
        evaluation = PolicyEngine().evaluate(
            action_instance(action_type), policy_context()
        )
        assert evaluation.decision == "ALLOW"
        assert evaluation.reason_code is None

    @pytest.mark.parametrize("action_type", _REGISTERED_MODEL_ACTION_TYPES_V1)
    @pytest.mark.parametrize("run_phase", _NON_AGENT_LOOP_PHASES)
    def test_model_actions_outside_agent_loop_are_phase_denied(
        self, action_type: str, run_phase: RunPhase
    ) -> None:
        evaluation = PolicyEngine().evaluate(
            action_instance(action_type), policy_context(run_phase=run_phase)
        )
        assert evaluation.decision == "DENY"
        assert evaluation.reason_code == "ACTION_NOT_ALLOWED_IN_PHASE"

    def test_phase_matrix_derives_from_the_closed_phase_set(self) -> None:
        # A new RunPhase would otherwise silently escape the phase-deny
        # matrix; the derived constant keeps the matrix exhaustive.
        assert set(_NON_AGENT_LOOP_PHASES) == set(get_args(RunPhase)) - {"AGENT_LOOP"}

    def test_phase_deny_beats_patch_fact_deny(self) -> None:
        context = policy_context(
            run_phase="PREFLIGHT", patch_path_fact="PATCH_PATH_NOT_EDITABLE"
        )
        evaluation = PolicyEngine().evaluate(
            action_instance("apply_candidate_patch"), context
        )
        assert evaluation.decision == "DENY"
        assert evaluation.reason_code == "ACTION_NOT_ALLOWED_IN_PHASE"

    @pytest.mark.parametrize("reason", get_args(CandidatePatchErrorCodeV1))
    def test_prepolicy_fact_reason_is_preserved_exactly(
        self, reason: PatchPathFactV1
    ) -> None:
        evaluation = PolicyEngine().evaluate(
            action_instance("apply_candidate_patch"),
            policy_context(patch_path_fact=reason),
        )
        assert evaluation.decision == "DENY"
        assert evaluation.reason_code == reason

    def test_patch_without_prepolicy_facts_denies_closed(self) -> None:
        evaluation = PolicyEngine().evaluate(
            action_instance("apply_candidate_patch"),
            policy_context(patch_path_fact=None),
        )
        assert evaluation.decision == "DENY"
        assert evaluation.reason_code == "TREE_INTEGRITY_FAILED"

    def test_patch_without_current_candidate_is_stale(self) -> None:
        evaluation = PolicyEngine().evaluate(
            action_instance("apply_candidate_patch"),
            policy_context(candidate_digest=None),
        )
        assert evaluation.decision == "DENY"
        assert evaluation.reason_code == "STALE_CANDIDATE"

    def test_stale_candidate_beats_the_patch_path_fact_reason(self) -> None:
        # The candidate-staleness priority (§4.3 STALE_CANDIDATE) is
        # checked before the pre-policy path fact is consulted.
        evaluation = PolicyEngine().evaluate(
            action_instance("apply_candidate_patch"),
            policy_context(
                candidate_digest=None,
                patch_path_fact="PATCH_PATH_NOT_EDITABLE",
            ),
        )
        assert evaluation.decision == "DENY"
        assert evaluation.reason_code == "STALE_CANDIDATE"

    @pytest.mark.parametrize(
        ("action_type", "expected_reason"), _DENIED_CAPABILITY_TYPES_V1
    )
    def test_denied_capability_table_maps_every_entry(
        self, action_type: str, expected_reason: str
    ) -> None:
        evaluation = PolicyEngine().evaluate(
            action_instance(action_type), policy_context()
        )
        assert evaluation.decision == "DENY"
        assert evaluation.reason_code == expected_reason

    @pytest.mark.parametrize(
        "action_type",
        (
            "mystery_capability",
            "read_all_files",
            "patch_repo",
            "delete_file",
            "set_environment",
            "final_writeback_request",
        ),
    )
    def test_unknown_capabilities_fail_closed(self, action_type: str) -> None:
        evaluation = PolicyEngine().evaluate(
            action_instance(action_type), policy_context()
        )
        assert evaluation.decision == "DENY"
        assert evaluation.reason_code == "UNKNOWN_CAPABILITY"

    @pytest.mark.parametrize(
        ("action_type", "run_phase", "expected_reason"),
        (
            # The hard-DENY capability reason (SPEC §4.4.1) carries no phase
            # qualifier: an unregistered capability is DENY in every phase,
            # more specific than the generic phase-forbidden code (§4.2.3
            # applies ACTION_NOT_ALLOWED_IN_PHASE to the six registered
            # actions outside RUNNING(AGENT_LOOP)).
            ("run_shell", "PREFLIGHT", "ARBITRARY_COMMAND"),
            ("run_shell", "FORMAL_VALIDATION", "ARBITRARY_COMMAND"),
            ("run_with_shell", "PERSISTENCE", "SHELL_FIELD"),
            ("modify_tests", "BASELINE", "ACCEPTANCE_MODIFICATION"),
            ("modify_pyproject_toml", "PREFLIGHT", "CONFIG_MODIFICATION"),
            ("approve", "PERSISTENCE", "CONTROL_PLANE_MODIFICATION"),
            ("mystery_capability", "PERSISTENCE", "UNKNOWN_CAPABILITY"),
        ),
    )
    def test_denied_capabilities_deny_in_every_phase(
        self,
        action_type: str,
        run_phase: RunPhase,
        expected_reason: str,
    ) -> None:
        evaluation = PolicyEngine().evaluate(
            action_instance(action_type), policy_context(run_phase=run_phase)
        )
        assert evaluation.decision == "DENY"
        assert evaluation.reason_code == expected_reason

    def test_control_plane_writeback_is_the_only_ask(self) -> None:
        context = policy_context(
            final_diff_digest=_CURRENT_FINAL_DIFF,
            writeback=writeback_operation(),
        )
        evaluation = PolicyEngine().evaluate(
            action_instance("final_writeback"), context
        )
        assert evaluation.decision == "ASK"
        assert evaluation.reason_code is None

    @pytest.mark.parametrize("run_phase", get_args(RunPhase))
    def test_writeback_ask_is_phase_independent(self, run_phase: RunPhase) -> None:
        context = policy_context(
            run_phase=run_phase,
            final_diff_digest=_CURRENT_FINAL_DIFF,
            writeback=writeback_operation(),
        )
        evaluation = PolicyEngine().evaluate(
            action_instance("final_writeback"), context
        )
        assert evaluation.decision == "ASK"
        assert evaluation.reason_code is None

    @pytest.mark.parametrize("run_phase", get_args(RunPhase))
    def test_writeback_without_facts_denies_in_every_phase(
        self, run_phase: RunPhase
    ) -> None:
        evaluation = PolicyEngine().evaluate(
            action_instance("final_writeback"), policy_context(run_phase=run_phase)
        )
        assert evaluation.decision == "DENY"
        assert evaluation.reason_code == "WRITEBACK_FACTS_UNVERIFIED"

    @pytest.mark.parametrize(
        "action_type",
        (*_REGISTERED_MODEL_ACTION_TYPES_V1, "run_shell", "mystery_capability"),
    )
    def test_no_other_action_can_ever_ask(self, action_type: str) -> None:
        evaluation = PolicyEngine().evaluate(
            action_instance(action_type), policy_context()
        )
        assert evaluation.decision != "ASK"

    def test_writeback_without_control_plane_facts_denies_closed(self) -> None:
        evaluation = PolicyEngine().evaluate(
            action_instance("final_writeback"), policy_context()
        )
        assert evaluation.decision == "DENY"
        assert evaluation.reason_code == "WRITEBACK_FACTS_UNVERIFIED"

    @pytest.mark.parametrize(
        ("override", "expected_reason"),
        (
            ({"candidate_digest": "1" * 64}, "TREE_INTEGRITY_FAILED"),
            ({"final_diff_digest": "2" * 64}, "TREE_INTEGRITY_FAILED"),
            ({"policy_digest": "3" * 64}, "TREE_INTEGRITY_FAILED"),
        ),
    )
    def test_writeback_identity_mismatch_denies_closed(
        self, override: dict[str, str], expected_reason: str
    ) -> None:
        context = policy_context(
            final_diff_digest=_CURRENT_FINAL_DIFF,
            writeback=writeback_operation(**cast(Any, override)),
        )
        evaluation = PolicyEngine().evaluate(
            action_instance("final_writeback"), context
        )
        assert evaluation.decision == "DENY"
        assert evaluation.reason_code == expected_reason

    def test_writeback_mismatch_with_no_current_candidate_denies_closed(
        self,
    ) -> None:
        context = policy_context(
            candidate_digest=None,
            final_diff_digest=_CURRENT_FINAL_DIFF,
            writeback=writeback_operation(),
        )
        evaluation = PolicyEngine().evaluate(
            action_instance("final_writeback"), context
        )
        assert evaluation.decision == "DENY"
        assert evaluation.reason_code == "TREE_INTEGRITY_FAILED"


class TestApprovalImmunity:
    """An approval can never be passed, and never converts DENY to ALLOW
    (GREEN-3/GREEN-5/AC-02)."""

    def test_evaluate_signature_accepts_no_approval_parameter(self) -> None:
        parameters = inspect.signature(PolicyEngine.evaluate).parameters
        assert list(parameters) == ["self", "instance", "context"]
        assert "approval" not in parameters

    @pytest.mark.parametrize(("action_type", "context_overrides"), _DENY_SCENARIOS)
    def test_approval_cannot_override_any_deny(
        self, action_type: str, context_overrides: dict[str, object]
    ) -> None:
        engine = PolicyEngine()
        context = policy_context(**cast(Any, context_overrides))
        evaluation = engine.evaluate(action_instance(action_type), context)
        assert evaluation.decision == "DENY"
        with pytest.raises(TypeError):
            cast(Any, engine).evaluate(
                action_instance(action_type), context, approval=object()
            )

    def test_context_has_no_approval_or_grant_fields(self) -> None:
        fields = PolicyContextV1.model_fields
        assert "approval" not in fields
        assert "approval_status" not in fields
        assert "grant" not in fields
        assert "grant_id" not in fields
        assert "prompt" not in fields
        assert "config" not in fields


class TestCacheKeys:
    """Decisions are memoized only by (policy digest, action semantic
    digest, immutable context digest) — never by instance id or mutable
    approval status (GREEN-7)."""

    def test_cache_keys_semantic_digest_and_context_not_instance_id(
        self,
    ) -> None:
        engine = PolicyEngine()
        context = policy_context()
        first = action_instance("read_file", action_id="action-1")
        second = action_instance("read_file", action_id="action-2")
        assert first.action_id != second.action_id
        assert first.semantic_digest == second.semantic_digest
        assert engine.evaluate(first, context) == engine.evaluate(second, context)
        assert engine.cache_hits == 1

    def test_cache_misses_on_immutable_context_change(self) -> None:
        engine = PolicyEngine()
        instance = action_instance("apply_candidate_patch")
        allowed = engine.evaluate(instance, policy_context())
        denied = engine.evaluate(
            instance, policy_context(patch_path_fact="SENSITIVE_PATH")
        )
        assert allowed.decision == "ALLOW"
        assert denied.decision == "DENY"
        assert engine.cache_hits == 0

    def test_cache_key_includes_the_governance_policy_digest(self) -> None:
        engine = PolicyEngine()
        instance = action_instance("read_file")
        builtin_context = policy_context()
        foreign_context = policy_context(editable_policy_digest="9" * 64)
        assert builtin_context.policy_digest != foreign_context.policy_digest
        assert engine.evaluate(instance, builtin_context) == engine.evaluate(
            instance, foreign_context
        )
        assert engine.cache_hits == 0

    def test_cache_key_binds_the_decision_inputs_not_a_spoofable_digest(
        self,
    ) -> None:
        # The semantic digest is unconstrained in this baseline, so a
        # contract-valid instance may carry a digest minted for a
        # DIFFERENT action type.  The memo key includes the action type
        # (the actual decision input), so a spoofed digest can never
        # turn a hard DENY into a cached ALLOW.
        engine = PolicyEngine()
        context = policy_context()
        spoofed = action_instance_with_digest(
            "read_file", semantic_digest_for("run_shell")
        )
        denied = action_instance("run_shell")
        assert spoofed.semantic_digest == denied.semantic_digest
        allowed = engine.evaluate(spoofed, context)
        assert allowed.decision == "ALLOW"
        denial = engine.evaluate(denied, context)
        assert denial.decision == "DENY"
        assert denial.reason_code == "ARBITRARY_COMMAND"
        assert engine.cache_hits == 0


class TestDigestPropagation:
    """The governance digest binds the versioned rule table plus the sole
    editable policy digest (GREEN-1/AC-31)."""

    def test_frozen_check_plan_ids_pin_the_contract_literal(self) -> None:
        # GREEN-2's frozen check plans are bound into the governance
        # digest via this table; the table must track the closed
        # CheckPlanIdV1 literal exactly so a drift silently rotates the
        # policy digest instead of silently widening the set.
        assert set(_ALLOWED_CHECK_PLAN_IDS_V1) == set(get_args(CheckPlanIdV1))

    def test_governance_digest_binds_the_editable_policy_digest(self) -> None:
        first = governance_policy_digest("a" * 64)
        second = governance_policy_digest("b" * 64)
        assert first != second
        assert first == governance_policy_digest("a" * 64)

    def test_context_rejects_a_policy_digest_not_binding_the_table(
        self,
    ) -> None:
        manifest = builtin_reference()
        editable_digest = manifest.editable_path_policy.digest
        base = {
            "schema_version": 1,
            "run_phase": "AGENT_LOOP",
            "editable_policy_digest": editable_digest,
            "reference_profile_digest": manifest.digest,
            "policy_digest": governance_policy_digest(editable_digest),
            "candidate_digest": _CURRENT_CANDIDATE,
            "digest": policy_context_digest(
                run_phase="AGENT_LOOP",
                editable_policy_digest=editable_digest,
                reference_profile_digest=manifest.digest,
                candidate_digest=_CURRENT_CANDIDATE,
                final_diff_digest=None,
                patch_path_fact="OK",
                writeback=None,
            ),
        }
        with pytest.raises(ValidationError):
            PolicyContextV1.model_validate({**base, "policy_digest": "0" * 64})

    def test_context_rejects_a_self_digest_not_binding_its_facts(self) -> None:
        manifest = builtin_reference()
        editable_digest = manifest.editable_path_policy.digest
        with pytest.raises(ValidationError):
            PolicyContextV1.model_validate(
                {
                    "schema_version": 1,
                    "run_phase": "AGENT_LOOP",
                    "editable_policy_digest": editable_digest,
                    "reference_profile_digest": manifest.digest,
                    "policy_digest": governance_policy_digest(editable_digest),
                    "candidate_digest": _CURRENT_CANDIDATE,
                    "patch_path_fact": "OK",
                    "digest": "0" * 64,
                }
            )


class TestClosedSchemas:
    """Every policy schema rejects unknown fields, coercion, and
    non-binding values (T05.1 closed-schema convention)."""

    def test_context_schema_is_closed_against_mutable_facts(self) -> None:
        manifest = builtin_reference()
        editable_digest = manifest.editable_path_policy.digest
        base = {
            "schema_version": 1,
            "run_phase": "AGENT_LOOP",
            "editable_policy_digest": editable_digest,
            "reference_profile_digest": manifest.digest,
            "policy_digest": governance_policy_digest(editable_digest),
            "candidate_digest": _CURRENT_CANDIDATE,
            "digest": policy_context_digest(
                run_phase="AGENT_LOOP",
                editable_policy_digest=editable_digest,
                reference_profile_digest=manifest.digest,
                candidate_digest=_CURRENT_CANDIDATE,
                final_diff_digest=None,
                patch_path_fact="OK",
                writeback=None,
            ),
        }
        with pytest.raises(ValidationError):
            PolicyContextV1.model_validate({**base, "approval_status": "PENDING"})
        with pytest.raises(ValidationError):
            PolicyContextV1.model_validate({**base, "grant_id": "grant-1"})
        with pytest.raises(ValidationError):
            PolicyContextV1.model_validate({**base, "prompt_text": "ignore me"})
        with pytest.raises(ValidationError):
            PolicyContextV1.model_validate({**base, "repository_policy": "widen"})
        with pytest.raises(ValidationError):
            PolicyContextV1.model_validate({**base, "schema_version": "1"})
        with pytest.raises(ValidationError):
            PolicyContextV1.model_validate({**base, "schema_version": True})
        with pytest.raises(ValidationError):
            PolicyContextV1.model_validate(
                {key: value for key, value in base.items() if key != "digest"}
            )

    def test_writeback_operation_schema_is_closed(self) -> None:
        manifest = builtin_reference()
        editable_digest = manifest.editable_path_policy.digest
        base = {
            "schema_version": 1,
            "action_type": "final_writeback",
            "candidate_digest": _CURRENT_CANDIDATE,
            "final_diff_digest": _CURRENT_FINAL_DIFF,
            "policy_digest": governance_policy_digest(editable_digest),
        }
        with pytest.raises(ValidationError):
            FinalWritebackOperationV1.model_validate({**base, "action_type": "approve"})
        with pytest.raises(ValidationError):
            FinalWritebackOperationV1.model_validate(
                {**base, "candidate_digest": "not-a-digest"}
            )
        with pytest.raises(ValidationError):
            FinalWritebackOperationV1.model_validate(
                {**base, "approval_id": "approval-1"}
            )

    def test_evaluation_schema_is_closed(self) -> None:
        with pytest.raises(ValidationError):
            PolicyEvaluationV1.model_validate({"schema_version": 1, "decision": "DENY"})
        with pytest.raises(ValidationError):
            PolicyEvaluationV1.model_validate(
                {
                    "schema_version": 1,
                    "decision": "ALLOW",
                    "reason_code": "SENSITIVE_PATH",
                }
            )
        with pytest.raises(ValidationError):
            PolicyEvaluationV1.model_validate(
                {"schema_version": 1, "decision": "MAYBE"}
            )
        with pytest.raises(ValidationError):
            PolicyEvaluationV1.model_validate(
                {"schema_version": 1, "decision": "DENY", "reason_code": "nope"}
            )


class TestPurity:
    """Evaluation has no side effects and no widening inputs (GREEN-1/
    GREEN-6)."""

    def test_policy_module_has_no_side_effect_import_surface(self) -> None:
        source = (
            Path(__file__).resolve().parents[3] / "src/vespercode/governance/policy.py"
        ).read_text(encoding="utf-8")
        tree = ast.parse(source)
        imported: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module is not None:
                imported.append(node.module)
            elif isinstance(node, ast.Import):
                imported.extend(alias.name for alias in node.names)
        # Every src.vespercode import must stay within the pure fact
        # vocabulary (canonicalization, closed contracts, and the
        # pre-policy rejection codes); tools, storage, credentials, LLM,
        # dispatch, workspace, trees, profiles, and control-plane
        # surfaces can never enter the evaluation module.
        allowed_prefixes = (
            "src.vespercode.canonical",
            "src.vespercode.contracts",
            "src.vespercode.candidate",
        )
        for module in imported:
            if not module.startswith("src.vespercode"):
                continue
            assert any(
                module == prefix or module.startswith(prefix + ".")
                for prefix in allowed_prefixes
            ), module

    def test_evaluation_is_deterministic(self) -> None:
        engine = PolicyEngine()
        instance = action_instance("read_file")
        context = policy_context()
        assert engine.evaluate(instance, context) == engine.evaluate(instance, context)
        assert engine.evaluate(instance, context).model_dump() == {
            "schema_version": 1,
            "decision": "ALLOW",
            "reason_code": None,
        }

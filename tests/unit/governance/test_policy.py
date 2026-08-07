"""T13.1 legacy step 13: centralized versioned policy evaluation tests.

Pins the one pure ALLOW/ASK/DENY evaluation over immutable facts: the
governance policy digest binds the versioned rule table plus the sole
editable policy digest, only the six registered model actions are
allowed in ``RUNNING(AGENT_LOOP)``, ``ASK`` exists only for the
control-plane final writeback operation, every other capability is a
hard ``DENY``, the deterministic pre-policy path/protected/sensitive
reason is preserved, and an approval can never be passed to or override
an evaluation (GREEN-1..GREEN-7).  Approval persistence, dispatch,
waits, and candidate mutation remain out of scope (GREEN-4).
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, cast

import pytest

# The policy engine consumes pydantic runtime contracts; the hash-locked
# gate toolchain installs no runtime dependencies, so this module skips
# cleanly there (formal env runs it fully).
pytest.importorskip("pydantic")

from vespercode.canonical.digest import domain_digest
from vespercode.contracts.action import ActionInstanceV1, SharedActionV1
from vespercode.contracts.run import RunPhase
from vespercode.governance.policy import (
    FinalWritebackOperationV1,
    PatchPathFactV1,
    PolicyContextV1,
    PolicyEngine,
    governance_policy_digest,
    policy_context_digest,
)
from vespercode.profiles.reference import (
    ReferenceProfileManifestV1,
    load_reference_profile,
)

_REFERENCE_MANIFEST = (
    Path(__file__).resolve().parents[3] / "reference/manifest/reference-profile-v1.json"
)
_CURRENT_CANDIDATE = hashlib.sha256(b"current-candidate").hexdigest()


def builtin_reference() -> ReferenceProfileManifestV1:
    """The frozen packaged reference profile (digest-verified)."""
    loaded = load_reference_profile(_REFERENCE_MANIFEST.read_bytes())
    assert isinstance(loaded, ReferenceProfileManifestV1)
    return loaded


def semantic_digest_for(action_type: str) -> str:
    """A deterministic action semantic identity for one action type.

    T05.1 treats the semantic digest as the opaque 64-hex §0.1 binding of
    the full action value; this helper derives it deterministically from
    the action type so every instance of the same action shares the
    semantic identity the decision cache must key on.
    """
    return hashlib.sha256(action_type.encode("utf-8")).hexdigest()


def action_instance(action_type: str, action_id: str = "action-1") -> ActionInstanceV1:
    """One Harness-bound action instance with a stable semantic identity.

    The instance digest is the exact T05.1 ``ActionInstanceDigestV1``
    binding of ``{schema_version, action_id, semantic_digest}``.
    """
    semantic_digest = semantic_digest_for(action_type)
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
    candidate_digest: str | None = _CURRENT_CANDIDATE,
    final_diff_digest: str | None = None,
    patch_path_fact: PatchPathFactV1 | None = "OK",
    writeback: FinalWritebackOperationV1 | None = None,
) -> PolicyContextV1:
    """One immutable context bound to the frozen built-in policy/profile.

    ``policy_digest`` is the governance digest over the versioned rule
    table plus the packaged editable policy digest, so the context can
    never exist with a policy identity the rule table does not bind.
    """
    manifest = builtin_reference()
    editable_digest = manifest.editable_path_policy.digest
    return PolicyContextV1(
        schema_version=1,
        run_phase=run_phase,
        editable_policy_digest=editable_digest,
        reference_profile_digest=manifest.digest,
        policy_digest=governance_policy_digest(editable_digest),
        candidate_digest=candidate_digest,
        final_diff_digest=final_diff_digest,
        patch_path_fact=patch_path_fact,
        writeback=writeback,
        digest=policy_context_digest(
            run_phase=run_phase,
            editable_policy_digest=editable_digest,
            reference_profile_digest=manifest.digest,
            candidate_digest=candidate_digest,
            final_diff_digest=final_diff_digest,
            patch_path_fact=patch_path_fact,
            writeback=writeback,
        ),
    )


@pytest.fixture
def policy_engine() -> PolicyEngine:
    """One engine instance with its own decision memo."""
    return PolicyEngine()


@pytest.fixture
def noneditable_patch_instance() -> ActionInstanceV1:
    """A schema-valid current-candidate patch instance whose deterministic
    pre-policy path facts rejected the patch as outside the editable
    roots."""
    return action_instance("apply_candidate_patch")


@pytest.fixture
def noneditable_context() -> PolicyContextV1:
    """A ``RUNNING(AGENT_LOOP)`` context binding the sole built-in
    editable policy digest, the frozen reference profile, and the
    preserved pre-policy ``PATCH_PATH_NOT_EDITABLE`` fact."""
    return policy_context(patch_path_fact="PATCH_PATH_NOT_EDITABLE")


def test_user_approval_cannot_override_noneditable_path_deny(
    policy_engine: PolicyEngine,
    noneditable_patch_instance: ActionInstanceV1,
    noneditable_context: PolicyContextV1,
) -> None:
    evaluation = policy_engine.evaluate(noneditable_patch_instance, noneditable_context)
    assert evaluation.decision == "DENY"
    assert evaluation.reason_code == "PATCH_PATH_NOT_EDITABLE"
    with pytest.raises(TypeError):
        cast(Any, policy_engine).evaluate(
            noneditable_patch_instance,
            noneditable_context,
            approval=object(),
        )

"""T14.1 legacy step 14.A: the immutable final-writeback subject builder.

``build_final_writeback_subject`` binds every immutable authorization
fact — the exact current Run identity, the Candidate identity and the
recomputed current ``FinalDiffV1``, the frozen editable policy, the
formal validation evidence, the frozen workspace preimage, the frozen
run config, and the expiry — into one pure ``FinalWritebackSubjectV1``
whose §0.1 digest covers every field except itself.  Before any subject
exists, every FinalDiff entry is revalidated against the frozen
``EditablePathPolicyV1`` (an out-of-scope entry rejects with
``PATCH_PATH_NOT_EDITABLE``) and the policy/reference/validation/run-
config digests are verified to transmit the same editable policy
identity (``TREE_INTEGRITY_FAILED``).  Wait creation, decision
persistence, approval consumption, policy override, and workspace
writes remain out of scope (GREEN-4).
"""

from __future__ import annotations

from typing import Literal, TypeAlias

from pydantic import (
    BaseModel,
    ConfigDict,
    StrictStr,
    field_validator,
    model_validator,
)

from vespercode.candidate.final_diff import FinalDiffV1
from vespercode.canonical.digest import domain_digest
from vespercode.canonical.timestamp_v1 import CanonicalTimestampV1
from vespercode.contracts.evidence import _DIGEST_RE
from vespercode.profiles.editable import EditablePathPolicyV1

_DIGEST_FIELDS: tuple[str, ...] = (
    "candidate_digest",
    "validation_manifest_digest",
    "validation_repository_policy_digest",
    "formal_evidence_digest",
    "workspace_preimage_digest",
    "run_config_digest",
    "run_config_reference_profile_digest",
    "reference_profile_digest",
    "reference_policy_digest",
)


class FinalWritebackBindingV1(BaseModel):
    """One immutable aggregation of the exact current writeback facts.

    The binding carries only harness-derived current facts: the Run
    identity, the Candidate identity digest, the recomputed current
    ``FinalDiffV1``, the formal validation evidence digest, the frozen
    workspace preimage digest, the frozen run-config digest plus its
    reference-profile/policy identity, the frozen editable policy, and
    the reference-profile manifest identity.  User decisions and mutable
    approval data can never enter (GREEN-2).
    """

    model_config = ConfigDict(extra="forbid", frozen=True)
    run_id: StrictStr
    candidate_digest: StrictStr
    final_diff: FinalDiffV1
    validation_manifest_digest: StrictStr
    validation_repository_policy_digest: StrictStr
    formal_evidence_digest: StrictStr
    workspace_preimage_digest: StrictStr
    run_config_digest: StrictStr
    run_config_reference_profile_digest: StrictStr
    run_config_policy_id: StrictStr
    reference_profile_digest: StrictStr
    reference_policy_digest: StrictStr
    policy: EditablePathPolicyV1

    @field_validator("run_id", "run_config_policy_id")
    @classmethod
    def _identifiers_must_be_non_empty(cls, value: str) -> str:
        if value == "":
            raise ValueError("identifiers must be non-empty")
        return value

    @field_validator(*_DIGEST_FIELDS)
    @classmethod
    def _digests_have_exact_form(cls, value: str) -> str:
        if _DIGEST_RE.fullmatch(value) is None:
            raise ValueError("must be exactly 64 lowercase hexadecimal characters")
        return value


FinalWritebackSubjectCodeV1: TypeAlias = Literal[
    "PATCH_PATH_NOT_EDITABLE",
    "TREE_INTEGRITY_FAILED",
]
"""The closed subject-construction rejections (SPEC §4.4.2)."""


class FinalWritebackSubjectError(ValueError):
    """Closed rejection of an out-of-scope or identity-drifted subject."""

    def __init__(self, error_code: FinalWritebackSubjectCodeV1, message: str) -> None:
        super().__init__(f"{error_code}: {message}")
        self.error_code = error_code


def _subject_digest(
    *,
    run_id: str,
    action_semantic_digest: str,
    candidate_digest: str,
    final_diff_digest: str,
    validation_manifest_digest: str,
    formal_evidence_digest: str,
    workspace_preimage_digest: str,
    run_config_digest: str,
    policy_digest: str,
    reference_profile_digest: str,
    expires_at: CanonicalTimestampV1,
) -> str:
    """The §0.1 identity of every exact subject field except the digest."""
    return domain_digest(
        "FinalWritebackSubjectV1",
        1,
        {
            "schema_version": 1,
            "run_id": run_id,
            "action_type": "final_writeback",
            "action_semantic_digest": action_semantic_digest,
            "candidate_digest": candidate_digest,
            "final_diff_digest": final_diff_digest,
            "validation_manifest_digest": validation_manifest_digest,
            "formal_evidence_digest": formal_evidence_digest,
            "workspace_preimage_digest": workspace_preimage_digest,
            "run_config_digest": run_config_digest,
            "policy_digest": policy_digest,
            "reference_profile_digest": reference_profile_digest,
            "expires_at": expires_at.value,
        },
    )


def _action_semantic_digest(candidate_digest: str, final_diff_digest: str) -> str:
    """SPEC §4.4.2: the closed ActionSemanticDigestV1 identity of the
    final-writeback operation over its two candidate facts."""
    return domain_digest(
        "ActionSemanticDigestV1",
        1,
        {
            "schema_version": 1,
            "action_type": "final_writeback",
            "candidate_digest": candidate_digest,
            "final_diff_digest": final_diff_digest,
        },
    )


class FinalWritebackSubjectV1(BaseModel):
    """SPEC §4.4.2: the immutable final-writeback approval subject.

    The §0.1 ``digest`` binds every other exact field and serves as the
    ``subject_digest``; the mutable approval state (``status``,
    ``created_at``) never enters the subject, and the model rejects any
    digest that does not equal the identity of its own fields (AC-03).
    """

    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal[1]
    run_id: StrictStr
    action_type: Literal["final_writeback"]
    action_semantic_digest: StrictStr
    candidate_digest: StrictStr
    final_diff_digest: StrictStr
    validation_manifest_digest: StrictStr
    formal_evidence_digest: StrictStr
    workspace_preimage_digest: StrictStr
    run_config_digest: StrictStr
    policy_digest: StrictStr
    reference_profile_digest: StrictStr
    expires_at: CanonicalTimestampV1
    digest: StrictStr

    @property
    def subject_digest(self) -> str:
        """SPEC §4.4.2 ``subject_digest``: exactly the self-digest."""
        return self.digest

    @field_validator("run_id")
    @classmethod
    def _run_id_must_be_non_empty(cls, value: str) -> str:
        if value == "":
            raise ValueError("run_id must be non-empty")
        return value

    @field_validator(
        "action_semantic_digest",
        "candidate_digest",
        "final_diff_digest",
        "validation_manifest_digest",
        "formal_evidence_digest",
        "workspace_preimage_digest",
        "run_config_digest",
        "policy_digest",
        "reference_profile_digest",
        "digest",
    )
    @classmethod
    def _digests_have_exact_form(cls, value: str) -> str:
        if _DIGEST_RE.fullmatch(value) is None:
            raise ValueError("must be exactly 64 lowercase hexadecimal characters")
        return value

    @model_validator(mode="after")
    def _digest_binds_every_field(self) -> FinalWritebackSubjectV1:
        if self.digest != _subject_digest(
            run_id=self.run_id,
            action_semantic_digest=self.action_semantic_digest,
            candidate_digest=self.candidate_digest,
            final_diff_digest=self.final_diff_digest,
            validation_manifest_digest=self.validation_manifest_digest,
            formal_evidence_digest=self.formal_evidence_digest,
            workspace_preimage_digest=self.workspace_preimage_digest,
            run_config_digest=self.run_config_digest,
            policy_digest=self.policy_digest,
            reference_profile_digest=self.reference_profile_digest,
            expires_at=self.expires_at,
        ):
            raise ValueError(
                "digest must equal the §0.1 identity of every other exact field"
            )
        return self


def build_final_writeback_subject(
    binding: FinalWritebackBindingV1,
    expires_at: CanonicalTimestampV1,
) -> FinalWritebackSubjectV1:
    """Build one pure immutable final-writeback subject (SPEC §4.4.2).

    Every FinalDiff entry is revalidated against the frozen editable
    policy (``PATCH_PATH_NOT_EDITABLE``) and the policy/reference/
    validation/run-config facts are verified to transmit the same
    editable policy identity (``TREE_INTEGRITY_FAILED``) before any
    subject exists; the subject then canonicalizes every exact bound
    fact into its §0.1 digest.
    """
    for entry in binding.final_diff.entries:
        if not binding.policy.matches(entry.path, entry.operation):
            raise FinalWritebackSubjectError(
                "PATCH_PATH_NOT_EDITABLE",
                f"entry path {entry.path.value!r} is not editable for "
                f"{entry.operation}",
            )
    if binding.reference_policy_digest != binding.policy.digest:
        raise FinalWritebackSubjectError(
            "TREE_INTEGRITY_FAILED",
            "reference profile does not transmit the frozen editable policy identity",
        )
    if binding.validation_repository_policy_digest != binding.policy.digest:
        raise FinalWritebackSubjectError(
            "TREE_INTEGRITY_FAILED",
            "validation manifest does not transmit the frozen editable policy identity",
        )
    if binding.run_config_reference_profile_digest != binding.reference_profile_digest:
        raise FinalWritebackSubjectError(
            "TREE_INTEGRITY_FAILED",
            "run config does not transmit the reference profile identity",
        )
    if binding.run_config_policy_id != binding.policy.policy_id:
        raise FinalWritebackSubjectError(
            "TREE_INTEGRITY_FAILED",
            "run config does not transmit the editable policy id",
        )
    action_semantic_digest = _action_semantic_digest(
        binding.candidate_digest, binding.final_diff.digest
    )
    return FinalWritebackSubjectV1(
        schema_version=1,
        run_id=binding.run_id,
        action_type="final_writeback",
        action_semantic_digest=action_semantic_digest,
        candidate_digest=binding.candidate_digest,
        final_diff_digest=binding.final_diff.digest,
        validation_manifest_digest=binding.validation_manifest_digest,
        formal_evidence_digest=binding.formal_evidence_digest,
        workspace_preimage_digest=binding.workspace_preimage_digest,
        run_config_digest=binding.run_config_digest,
        policy_digest=binding.policy.digest,
        reference_profile_digest=binding.reference_profile_digest,
        expires_at=expires_at,
        digest=_subject_digest(
            run_id=binding.run_id,
            action_semantic_digest=action_semantic_digest,
            candidate_digest=binding.candidate_digest,
            final_diff_digest=binding.final_diff.digest,
            validation_manifest_digest=binding.validation_manifest_digest,
            formal_evidence_digest=binding.formal_evidence_digest,
            workspace_preimage_digest=binding.workspace_preimage_digest,
            run_config_digest=binding.run_config_digest,
            policy_digest=binding.policy.digest,
            reference_profile_digest=binding.reference_profile_digest,
            expires_at=expires_at,
        ),
    )

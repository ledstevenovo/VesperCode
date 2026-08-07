"""T12.1 legacy step 12.D: CandidateIdentityV1 three-root binding.

``build_candidate_identity`` binds the candidate's semantic identity to
exactly three roots — the Snapshot tree digest, the Candidate tree
digest, and the canonical ``FinalDiffV1`` digest — under the §0.1
``CandidateIdentityV1`` domain (SPEC §4.3).  Revision ids, parent ids,
and all mutable revision metadata never enter the identity; restoring the
exact three bound facts restores the original digest, and any claimed
digest that does not bind its own fields rejects at construction.  Patch
application, revision publication, writeback approval, mutable workspace
access, and any other identity input remain out of scope (GREEN-4).
"""

from __future__ import annotations

from typing import Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    StrictStr,
    field_validator,
    model_validator,
)

from vespercode.canonical.digest import domain_digest
from vespercode.contracts.evidence import _DIGEST_RE
from vespercode.trees.candidate import CandidateRevisionV1


class CandidateIdentityV1(BaseModel):
    """SPEC §4.3 closed three-root candidate identity.

    ``digest`` is the §0.1 identity of every exact field except itself and
    must bind them at construction; ``candidate_digest`` in the run-level
    binding is exactly this digest.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal[1]
    snapshot_tree_digest: StrictStr
    candidate_tree_digest: StrictStr
    final_diff_digest: StrictStr
    digest: StrictStr

    @field_validator("schema_version", mode="before")
    @classmethod
    def _schema_version_is_exact_int(cls, value: object) -> object:
        if not isinstance(value, int) or isinstance(value, bool):
            raise ValueError("schema_version must be the decimal integer 1")
        return value

    @field_validator(
        "snapshot_tree_digest", "candidate_tree_digest", "final_diff_digest", "digest"
    )
    @classmethod
    def _require_sha256_hex(cls, value: str) -> str:
        if _DIGEST_RE.fullmatch(value) is None:
            raise ValueError(
                "digests must be exactly 64 lowercase hexadecimal characters"
            )
        return value

    @model_validator(mode="after")
    def _require_bound_digest(self) -> CandidateIdentityV1:
        if self.digest != _candidate_identity_digest(
            self.snapshot_tree_digest,
            self.candidate_tree_digest,
            self.final_diff_digest,
        ):
            raise ValueError("digest must bind the three exact roots")
        return self


def build_candidate_identity(
    snapshot_tree_digest: str,
    candidate_tree_digest: str,
    final_diff_digest: str,
) -> CandidateIdentityV1:
    """Bind the three exact roots into one closed candidate identity.

    The identity is a pure function of the three digest roots: revision
    metadata is never an input, so restoring the exact bound facts always
    restores the original digest.
    """
    return CandidateIdentityV1(
        schema_version=1,
        snapshot_tree_digest=snapshot_tree_digest,
        candidate_tree_digest=candidate_tree_digest,
        final_diff_digest=final_diff_digest,
        digest=_candidate_identity_digest(
            snapshot_tree_digest, candidate_tree_digest, final_diff_digest
        ),
    )


def bind_revision_identity(
    revision: CandidateRevisionV1, final_diff_digest: str
) -> CandidateRevisionV1:
    """Bind one revision's ``candidate_digest`` to the three-root identity.

    SPEC §4.3 pins the run-level candidate digest to exactly
    ``CandidateIdentityV1.digest``; this is realized by binding the
    revision to the exact recomputed ``FinalDiffV1.digest`` after Task
    12.D recomputation.  Everything else about the revision — the audit
    chain (``revision_id``/``parent_revision_id``) and the immutable tree —
    is unchanged, so the binding never affects the semantic identity it
    sets.
    """
    identity = build_candidate_identity(
        revision.tree.snapshot.root_digest,
        revision.tree.digest,
        final_diff_digest,
    )
    return revision.model_copy(update={"candidate_digest": identity.digest})


def _candidate_identity_digest(
    snapshot_tree_digest: str,
    candidate_tree_digest: str,
    final_diff_digest: str,
) -> str:
    """The §0.1 identity of every exact CandidateIdentityV1 field except
    the digest (SPEC §0.1 object_type ``CandidateIdentityV1``)."""
    return domain_digest(
        "CandidateIdentityV1",
        1,
        {
            "schema_version": 1,
            "snapshot_tree_digest": snapshot_tree_digest,
            "candidate_tree_digest": candidate_tree_digest,
            "final_diff_digest": final_diff_digest,
        },
    )

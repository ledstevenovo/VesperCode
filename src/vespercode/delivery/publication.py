"""T36.2 legacy step 36.B: pure fail-closed release/GHCR publication
verification contract.

``verify_release_publication_result`` is the pure zero-I/O verifier
T37.1 consumes before writing any release evidence: given the frozen
release inputs (the final merged prerequisite main ``source_commit``,
the tag, the exact wheel SHA-256, and the Task 2 reference manifest
digest) and the observed terminal result of one protected external
publication, it returns either ``ACCEPTED`` (exact complete alignment,
``evidence_write_allowed=True``) or ``REJECTED`` with the declared
closed error code and ``evidence_write_allowed=False``.  The verifier
performs zero network, credential, environment, subprocess,
publication, or filesystem access, and never normalizes or rewrites an
input (GREEN-1/GREEN-2/GREEN-4).
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, StrictBool, StrictStr

ReleasePublicationErrorCodeV1 = Literal[
    "SOURCE_COMMIT_MISMATCH",
    "TAG_MISMATCH",
    "WHEEL_DIGEST_MISMATCH",
    "GHCR_DIGEST_MISMATCH",
    "PULLED_IMAGE_DIGEST_MISMATCH",
    "WHEEL_INSTALL_FAILED",
    "IMAGE_SMOKE_FAILED",
]


class FrozenReleaseInputsV1(BaseModel):
    """Immutable frozen release inputs (36.B GREEN-1).

    Supplied by T37.1 alone from the final merged prerequisite main
    ``source_commit``.  ``reference_manifest_digest`` is compared raw
    against the observed GHCR RepoDigest, so it must be supplied in the
    raw registry form (``sha256:``-prefixed) — not copied verbatim from
    the bare 64-hex form stored in T36.1's ``ReleaseEvidenceV1``
    (``wheel_sha256`` stays bare hex in both contracts; only the image
    digests carry the prefix here).
    """

    model_config = ConfigDict(extra="forbid", frozen=True)
    source_commit: StrictStr
    tag_name: StrictStr
    wheel_sha256: StrictStr
    reference_manifest_digest: StrictStr


class ObservedReleaseResultV1(BaseModel):
    """Immutable observed terminal result of one protected publication."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    source_commit: StrictStr
    tag_name: StrictStr
    released_wheel_sha256: StrictStr
    ghcr_repo_digest: StrictStr
    pulled_image_digest: StrictStr
    wheel_install_passed: StrictBool
    image_smoke_passed: StrictBool


class ReleasePublicationAcceptedV1(BaseModel):
    """Closed acceptance: exact complete alignment, evidence writing
    allowed."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    kind: Literal["ACCEPTED"] = "ACCEPTED"
    evidence_write_allowed: Literal[True] = True


class ReleasePublicationRejectedV1(BaseModel):
    """Closed rejection: any mismatch, evidence writing forbidden."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    kind: Literal["REJECTED"] = "REJECTED"
    error_code: ReleasePublicationErrorCodeV1
    evidence_write_allowed: Literal[False] = False


ReleasePublicationVerificationV1 = (
    ReleasePublicationAcceptedV1 | ReleasePublicationRejectedV1
)


def verify_release_publication_result(
    frozen: FrozenReleaseInputsV1,
    observed: ObservedReleaseResultV1,
) -> ReleasePublicationVerificationV1:
    """Compare every displayed fact in the declared deterministic error
    order (36.B GREEN-2).

    Order: source commit, tag, wheel SHA-256, frozen manifest vs GHCR
    RepoDigest, pulled-image digest vs GHCR RepoDigest, wheel install
    result, image smoke result.  Any mismatch returns ``REJECTED`` with
    ``evidence_write_allowed=False``; only exact complete alignment
    returns ``ACCEPTED``.  Inputs are compared verbatim — never
    normalized or rewritten.
    """
    if observed.source_commit != frozen.source_commit:
        return ReleasePublicationRejectedV1(error_code="SOURCE_COMMIT_MISMATCH")
    if observed.tag_name != frozen.tag_name:
        return ReleasePublicationRejectedV1(error_code="TAG_MISMATCH")
    if observed.released_wheel_sha256 != frozen.wheel_sha256:
        return ReleasePublicationRejectedV1(error_code="WHEEL_DIGEST_MISMATCH")
    if observed.ghcr_repo_digest != frozen.reference_manifest_digest:
        return ReleasePublicationRejectedV1(error_code="GHCR_DIGEST_MISMATCH")
    if observed.pulled_image_digest != observed.ghcr_repo_digest:
        return ReleasePublicationRejectedV1(error_code="PULLED_IMAGE_DIGEST_MISMATCH")
    if not observed.wheel_install_passed:
        return ReleasePublicationRejectedV1(error_code="WHEEL_INSTALL_FAILED")
    if not observed.image_smoke_passed:
        return ReleasePublicationRejectedV1(error_code="IMAGE_SMOKE_FAILED")
    return ReleasePublicationAcceptedV1()

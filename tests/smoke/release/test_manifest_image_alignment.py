"""T36.2 legacy step 36.B: Release/GHCR publication verification tests.

The exact displayed RED test ``test_release_rejects_ghcr_digest_different_from_frozen_manifest``
is copied from the T36.2 card with its body byte-identical; the matrix
test pins the 36.B row (Expected 36.B): fake frozen/observed digest
mismatch returns exact ``REJECTED/GHCR_DIGEST_MISMATCH/
evidence_write_allowed=False``; exact fake alignment returns
``ACCEPTED/evidence_write_allowed=True``; every closed mismatch variant
follows the declared deterministic priority; all tests use only fake
values, perform zero external I/O, and write no evidence.
"""

from __future__ import annotations

import pytest

from vespercode.delivery.publication import (
    FrozenReleaseInputsV1,
    ObservedReleaseResultV1,
    ReleasePublicationAcceptedV1,
    ReleasePublicationRejectedV1,
    verify_release_publication_result,
)

pytestmark = pytest.mark.deployment_smoke


@pytest.mark.deployment_smoke
def test_release_rejects_ghcr_digest_different_from_frozen_manifest() -> None:
    frozen = FrozenReleaseInputsV1(
        source_commit="a" * 40,
        tag_name="v1.0.0",
        wheel_sha256="b" * 64,
        reference_manifest_digest="sha256:" + "c" * 64,
    )
    observed = ObservedReleaseResultV1(
        source_commit=frozen.source_commit,
        tag_name=frozen.tag_name,
        released_wheel_sha256=frozen.wheel_sha256,
        ghcr_repo_digest="sha256:" + "d" * 64,
        pulled_image_digest="sha256:" + "d" * 64,
        wheel_install_passed=True,
        image_smoke_passed=True,
    )

    result = verify_release_publication_result(frozen, observed)

    assert isinstance(result, ReleasePublicationRejectedV1)
    assert result.kind == "REJECTED"
    assert result.error_code == "GHCR_DIGEST_MISMATCH"
    assert result.evidence_write_allowed is False


def _aligned_pair() -> tuple[FrozenReleaseInputsV1, ObservedReleaseResultV1]:
    """One fake fully aligned frozen/observed pair (36.B matrix base)."""
    frozen = FrozenReleaseInputsV1(
        source_commit="a" * 40,
        tag_name="v1.0.0",
        wheel_sha256="b" * 64,
        reference_manifest_digest="sha256:" + "c" * 64,
    )
    observed = ObservedReleaseResultV1(
        source_commit=frozen.source_commit,
        tag_name=frozen.tag_name,
        released_wheel_sha256=frozen.wheel_sha256,
        ghcr_repo_digest=frozen.reference_manifest_digest,
        pulled_image_digest=frozen.reference_manifest_digest,
        wheel_install_passed=True,
        image_smoke_passed=True,
    )
    return frozen, observed


def test_release_publication_matrix() -> None:
    """PLAN 36.B row (Expected 36.B): every closed mismatch variant
    follows the declared deterministic priority; exact alignment
    accepts.  All fake values, zero external I/O, no evidence written."""
    from pydantic import ValidationError

    # Baseline: exact complete alignment accepts.
    frozen, observed = _aligned_pair()
    accepted = verify_release_publication_result(frozen, observed)
    assert isinstance(accepted, ReleasePublicationAcceptedV1)
    assert accepted.kind == "ACCEPTED"
    assert accepted.evidence_write_allowed is True

    # Row 1: source commit mismatch -> SOURCE_COMMIT_MISMATCH (first
    # priority even when other fields also mismatch).
    drifted = observed.model_copy(update={"source_commit": "1" * 40})
    result = verify_release_publication_result(frozen, drifted)
    assert isinstance(result, ReleasePublicationRejectedV1)
    assert result.error_code == "SOURCE_COMMIT_MISMATCH"
    assert result.evidence_write_allowed is False

    # Row 2: tag mismatch -> TAG_MISMATCH.
    drifted = observed.model_copy(update={"tag_name": "v9.9.9"})
    result = verify_release_publication_result(frozen, drifted)
    assert isinstance(result, ReleasePublicationRejectedV1)
    assert result.error_code == "TAG_MISMATCH"

    # Row 3: wheel digest mismatch -> WHEEL_DIGEST_MISMATCH.
    drifted = observed.model_copy(update={"released_wheel_sha256": "f" * 64})
    result = verify_release_publication_result(frozen, drifted)
    assert isinstance(result, ReleasePublicationRejectedV1)
    assert result.error_code == "WHEEL_DIGEST_MISMATCH"

    # Row 4: GHCR RepoDigest differs from the frozen manifest
    # -> GHCR_DIGEST_MISMATCH (the exact RED path, re-pinned).
    drifted = observed.model_copy(
        update={
            "ghcr_repo_digest": "sha256:" + "d" * 64,
            "pulled_image_digest": "sha256:" + "d" * 64,
        }
    )
    result = verify_release_publication_result(frozen, drifted)
    assert isinstance(result, ReleasePublicationRejectedV1)
    assert result.error_code == "GHCR_DIGEST_MISMATCH"

    # Row 5: pulled image differs from the published GHCR digest
    # -> PULLED_IMAGE_DIGEST_MISMATCH.
    drifted = observed.model_copy(update={"pulled_image_digest": "sha256:" + "e" * 64})
    result = verify_release_publication_result(frozen, drifted)
    assert isinstance(result, ReleasePublicationRejectedV1)
    assert result.error_code == "PULLED_IMAGE_DIGEST_MISMATCH"

    # Row 6: wheel install failed -> WHEEL_INSTALL_FAILED.
    drifted = observed.model_copy(update={"wheel_install_passed": False})
    result = verify_release_publication_result(frozen, drifted)
    assert isinstance(result, ReleasePublicationRejectedV1)
    assert result.error_code == "WHEEL_INSTALL_FAILED"

    # Row 7: image smoke failed -> IMAGE_SMOKE_FAILED.
    drifted = observed.model_copy(update={"image_smoke_passed": False})
    result = verify_release_publication_result(frozen, drifted)
    assert isinstance(result, ReleasePublicationRejectedV1)
    assert result.error_code == "IMAGE_SMOKE_FAILED"

    # Row 8: deterministic priority — a later mismatch is shadowed by an
    # earlier one (source commit wins over every later field).
    drifted = observed.model_copy(
        update={
            "source_commit": "2" * 40,
            "released_wheel_sha256": "f" * 64,
            "image_smoke_passed": False,
        }
    )
    result = verify_release_publication_result(frozen, drifted)
    assert isinstance(result, ReleasePublicationRejectedV1)
    assert result.error_code == "SOURCE_COMMIT_MISMATCH"

    # Row 9: priority — GHCR mismatch wins over pulled/install/smoke.
    drifted = observed.model_copy(
        update={
            "ghcr_repo_digest": "sha256:" + "d" * 64,
            "pulled_image_digest": "sha256:" + "d" * 64,
            "wheel_install_passed": False,
        }
    )
    result = verify_release_publication_result(frozen, drifted)
    assert isinstance(result, ReleasePublicationRejectedV1)
    assert result.error_code == "GHCR_DIGEST_MISMATCH"

    # Row 10: the contracts are closed and immutable — unknown fields
    # and mutation reject/are forbidden.
    with pytest.raises(ValidationError):
        FrozenReleaseInputsV1.model_validate(
            {
                "source_commit": "a" * 40,
                "tag_name": "v1.0.0",
                "wheel_sha256": "b" * 64,
                "reference_manifest_digest": "sha256:" + "c" * 64,
                "invented": True,
            }
        )
    with pytest.raises(ValidationError):
        ObservedReleaseResultV1.model_validate(
            {
                **observed.model_dump(),
                "invented": True,
            }
        )

    # Row 11: the frozen contracts are immutable — assignment rejects
    # at runtime (statically the assignment is legal).
    with pytest.raises(ValidationError):
        frozen.source_commit = "0" * 40
    with pytest.raises(ValidationError):
        accepted.kind = "REJECTED"  # type: ignore[assignment]

    # Row 12: the error-code literal is closed — an undeclared code
    # rejects.
    with pytest.raises(ValidationError):
        ReleasePublicationRejectedV1.model_validate({"error_code": "INVENTED"})

    # Row 13: priority — GHCR mismatch wins over a simultaneously
    # mismatched pulled digest (mutually different values disambiguate
    # the GHCR_DIGEST_MISMATCH vs PULLED_IMAGE_DIGEST_MISMATCH order).
    drifted = observed.model_copy(
        update={
            "ghcr_repo_digest": "sha256:" + "d" * 64,
            "pulled_image_digest": "sha256:" + "e" * 64,
        }
    )
    result = verify_release_publication_result(frozen, drifted)
    assert isinstance(result, ReleasePublicationRejectedV1)
    assert result.error_code == "GHCR_DIGEST_MISMATCH"

    # Row 14: priority — tag mismatch wins over a simultaneously
    # mismatched wheel digest (disambiguates TAG_MISMATCH vs
    # WHEEL_DIGEST_MISMATCH order).
    drifted = observed.model_copy(
        update={
            "tag_name": "v9.9.9",
            "released_wheel_sha256": "f" * 64,
        }
    )
    result = verify_release_publication_result(frozen, drifted)
    assert isinstance(result, ReleasePublicationRejectedV1)
    assert result.error_code == "TAG_MISMATCH"

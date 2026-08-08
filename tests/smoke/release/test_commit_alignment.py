"""T36.1 legacy step 36.A: closed release evidence commit-alignment tests.

The exact displayed RED test ``test_release_evidence_rejects_commit_misalignment``
is copied from the T36.1 card with its body byte-identical; the matrix
test pins the 36.A row (Expected 36.A): closed schemas and exact identity
alignment reject every missing/mismatched/non-terminal case.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from vespercode.delivery.evidence import ReleaseEvidenceV1

pytestmark = pytest.mark.deployment_smoke


@pytest.fixture()
def valid_release_evidence() -> dict[str, object]:
    """One self-consistent non-secret release evidence payload (36.A)."""
    return {
        "schema_version": 1,
        "release_id": "release-36-a-smoke",
        "tag_name": "v1.0.0",
        "source_commit": "a" * 40,
        "github_tag_commit": "a" * 40,
        "wheel_sha256": "b" * 64,
        "reference_manifest_digest": "d" * 64,
        "ghcr_repo_digest": "d" * 64,
        "pulled_image_digest": "d" * 64,
        "release_url": "https://github.com/ledstevenovo/VesperCode/releases/tag/v1.0.0",
        "ci_run_id": "31236183711",
        "ci_run_url": "https://github.com/ledstevenovo/VesperCode/actions/runs/31236183711",
        "environment_category": "github_actions",
        "status": "SUCCEEDED",
        "recorded_at": "2026-08-08T03:00:00Z",
        "access_metadata": {
            "release_public": True,
            "wheel_checksum_public": True,
            "ghcr_image_public": True,
        },
    }


def test_release_evidence_rejects_commit_misalignment(
    valid_release_evidence: dict[str, object],
) -> None:
    valid_release_evidence["github_tag_commit"] = "0" * 40
    with pytest.raises(ValidationError):
        ReleaseEvidenceV1.model_validate(valid_release_evidence)


def test_release_evidence_matrix(
    valid_release_evidence: dict[str, object],
) -> None:
    """PLAN 36.A row (Expected 36.A): closed schemas and exact identity
    alignment reject every missing/mismatched/non-terminal case."""
    import copy

    # Baseline: the self-consistent record validates.
    assert ReleaseEvidenceV1.model_validate(valid_release_evidence) is not None

    # Row 1: tag/source commit misalignment rejects.
    drifted = copy.deepcopy(valid_release_evidence)
    drifted["github_tag_commit"] = "1" * 40
    with pytest.raises(ValidationError):
        ReleaseEvidenceV1.model_validate(drifted)

    # Row 2: pulled image differs from the published GHCR digest rejects.
    drifted = copy.deepcopy(valid_release_evidence)
    drifted["pulled_image_digest"] = "e" * 64
    with pytest.raises(ValidationError):
        ReleaseEvidenceV1.model_validate(drifted)

    # Row 3: malformed commit (wrong length / non-hex / uppercase) rejects.
    for bad in ("a" * 39, "g" * 40, "A" * 40, ""):
        drifted = copy.deepcopy(valid_release_evidence)
        drifted["source_commit"] = bad
        with pytest.raises(ValidationError):
            ReleaseEvidenceV1.model_validate(drifted)

    # Row 4: malformed content-addressed digest rejects.
    for field in (
        "wheel_sha256",
        "reference_manifest_digest",
        "ghcr_repo_digest",
        "pulled_image_digest",
    ):
        drifted = copy.deepcopy(valid_release_evidence)
        drifted[field] = "z" * 64
        with pytest.raises(ValidationError):
            ReleaseEvidenceV1.model_validate(drifted)

    # Row 5: non-terminal status rejects (only SUCCEEDED/FAILED).
    drifted = copy.deepcopy(valid_release_evidence)
    drifted["status"] = "PLANNED"
    with pytest.raises(ValidationError):
        ReleaseEvidenceV1.model_validate(drifted)

    # Row 6: unknown environment category rejects.
    drifted = copy.deepcopy(valid_release_evidence)
    drifted["environment_category"] = "circle_ci"
    with pytest.raises(ValidationError):
        ReleaseEvidenceV1.model_validate(drifted)

    # Row 7: unknown fields reject (closed schema).
    drifted = copy.deepcopy(valid_release_evidence)
    drifted["invented_field"] = True
    with pytest.raises(ValidationError):
        ReleaseEvidenceV1.model_validate(drifted)

    # Row 8: malformed recorded_at timestamp rejects.
    drifted = copy.deepcopy(valid_release_evidence)
    drifted["recorded_at"] = "not-a-timestamp"
    with pytest.raises(ValidationError):
        ReleaseEvidenceV1.model_validate(drifted)

    # Row 9: malformed URL rejects.
    drifted = copy.deepcopy(valid_release_evidence)
    drifted["release_url"] = "not-a-url"
    with pytest.raises(ValidationError):
        ReleaseEvidenceV1.model_validate(drifted)

    # Row 10: access metadata values must be booleans (non-secret flags).
    drifted = copy.deepcopy(valid_release_evidence)
    drifted["access_metadata"] = {"release_public": "yes"}
    with pytest.raises(ValidationError):
        ReleaseEvidenceV1.model_validate(drifted)

    # Row 11: missing required fields reject.
    for field in ("source_commit", "wheel_sha256", "tag_name", "recorded_at"):
        drifted = copy.deepcopy(valid_release_evidence)
        drifted.pop(field)
        with pytest.raises(ValidationError):
            ReleaseEvidenceV1.model_validate(drifted)

    # Row 12: the frozen reference manifest must equal the GHCR image
    # digest (SPEC AC-30 four-way digest equality).
    drifted = copy.deepcopy(valid_release_evidence)
    drifted["reference_manifest_digest"] = "e" * 64
    with pytest.raises(ValidationError):
        ReleaseEvidenceV1.model_validate(drifted)

    # Row 13: a future/planned schema version rejects (closed version).
    drifted = copy.deepcopy(valid_release_evidence)
    drifted["schema_version"] = 2
    with pytest.raises(ValidationError):
        ReleaseEvidenceV1.model_validate(drifted)

    # Row 14: a naive or date-only timestamp rejects (not an instant).
    for bad in ("2026-08-08", "2026-08-08T03:00:00", "2026-08-08 03:00:00Z"):
        drifted = copy.deepcopy(valid_release_evidence)
        drifted["recorded_at"] = bad
        with pytest.raises(ValidationError):
            ReleaseEvidenceV1.model_validate(drifted)

"""T36.1 legacy step 36.A: closed delivery evidence schema tests.

The CI and deployment records are closed non-secret unions with the
same strictness as the release record, and the read-only verifier
``load_and_verify_release_evidence`` enforces cross-record commit
alignment, terminal state, freshness (when live), and content-addressed
digests while never mutating the evidence store.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from pydantic import ValidationError

from vespercode.delivery.evidence import (
    CIReleaseEvidenceV1,
    DeploymentEvidenceV1,
    load_and_verify_release_evidence,
)

pytestmark = pytest.mark.deployment_smoke

_COMMIT = "a" * 40
_DIGEST = "b" * 64
_NOW = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

_CI_VALID = {
    "schema_version": 1,
    "ci_run_id": "31236183711",
    "ci_run_url": "https://github.com/ledstevenovo/VesperCode/actions/runs/31236183711",
    "source_commit": _COMMIT,
    "environment_category": "github_actions",
    "status": "SUCCEEDED",
    "recorded_at": _NOW,
}

_DEPLOYMENT_VALID = {
    "schema_version": 1,
    "deployment_id": "deploy-36-a-smoke",
    "source_commit": _COMMIT,
    "demo_image_digest": _DIGEST,
    "render_url": "https://vespercode.onrender.com",
    "environment_category": "github_actions",
    "status": "SUCCEEDED",
    "recorded_at": _NOW,
    "access_metadata": {"render_public": True},
}

_RELEASE_VALID = {
    "schema_version": 1,
    "release_id": "release-36-a-smoke",
    "tag_name": "v1.0.0",
    "source_commit": _COMMIT,
    "github_tag_commit": _COMMIT,
    "wheel_sha256": "b" * 64,
    "reference_manifest_digest": "d" * 64,
    "ghcr_repo_digest": "d" * 64,
    "pulled_image_digest": "d" * 64,
    "release_url": "https://github.com/ledstevenovo/VesperCode/releases/tag/v1.0.0",
    "ci_run_id": "31236183711",
    "ci_run_url": "https://github.com/ledstevenovo/VesperCode/actions/runs/31236183711",
    "environment_category": "github_actions",
    "status": "SUCCEEDED",
    "recorded_at": _NOW,
    "access_metadata": {
        "release_public": True,
        "wheel_checksum_public": True,
        "ghcr_image_public": True,
    },
}


def _write_evidence(root: Path, records: dict[str, dict[str, object]]) -> None:
    root.mkdir(parents=True, exist_ok=True)
    for name, payload in records.items():
        (root / name).write_text(
            json.dumps(payload, ensure_ascii=False, sort_keys=True),
            encoding="utf-8",
        )


def _evidence_bundle(commit: str = _COMMIT) -> dict[str, dict[str, object]]:
    ci = dict(_CI_VALID, source_commit=commit)
    release = dict(_RELEASE_VALID, source_commit=commit, github_tag_commit=commit)
    deployment = dict(_DEPLOYMENT_VALID, source_commit=commit)
    return {
        "ci-v1.json": ci,
        "release-v1.json": release,
        "deployment-v1.json": deployment,
    }


def test_ci_evidence_rejects_malformed_records() -> None:
    with pytest.raises(ValidationError):
        CIReleaseEvidenceV1.model_validate(dict(_CI_VALID, source_commit="zz"))
    with pytest.raises(ValidationError):
        CIReleaseEvidenceV1.model_validate(dict(_CI_VALID, status="QUEUED"))
    with pytest.raises(ValidationError):
        CIReleaseEvidenceV1.model_validate(dict(_CI_VALID, invented=True))
    with pytest.raises(ValidationError):
        CIReleaseEvidenceV1.model_validate(dict(_CI_VALID, recorded_at="later"))
    assert CIReleaseEvidenceV1.model_validate(_CI_VALID) is not None


def test_deployment_evidence_rejects_malformed_records() -> None:
    with pytest.raises(ValidationError):
        DeploymentEvidenceV1.model_validate(
            dict(_DEPLOYMENT_VALID, demo_image_digest="bad")
        )
    with pytest.raises(ValidationError):
        DeploymentEvidenceV1.model_validate(dict(_DEPLOYMENT_VALID, render_url="nope"))
    with pytest.raises(ValidationError):
        DeploymentEvidenceV1.model_validate(
            dict(_DEPLOYMENT_VALID, access_metadata={"x": 1})
        )
    assert DeploymentEvidenceV1.model_validate(_DEPLOYMENT_VALID) is not None


def test_loader_accepts_aligned_terminal_evidence(tmp_path: Path) -> None:
    _write_evidence(tmp_path, _evidence_bundle())
    bundle = load_and_verify_release_evidence(tmp_path, require_live=True)
    assert bundle.ci.source_commit == _COMMIT
    assert bundle.release.source_commit == _COMMIT
    assert bundle.deployment.source_commit == _COMMIT
    assert bundle.release.github_tag_commit == _COMMIT


def test_loader_rejects_missing_evidence_files(tmp_path: Path) -> None:
    _write_evidence(tmp_path, {"ci-v1.json": _CI_VALID})
    with pytest.raises(ValueError, match="missing delivery evidence"):
        load_and_verify_release_evidence(tmp_path, require_live=False)


def test_loader_rejects_cross_record_commit_misalignment(
    tmp_path: Path,
) -> None:
    records = _evidence_bundle()
    records["deployment-v1.json"]["source_commit"] = "c" * 40
    _write_evidence(tmp_path, records)
    with pytest.raises(ValueError, match="misalignment"):
        load_and_verify_release_evidence(tmp_path, require_live=False)


def test_loader_rejects_cross_record_ci_run_misalignment(
    tmp_path: Path,
) -> None:
    records = _evidence_bundle()
    records["release-v1.json"]["ci_run_id"] = "different-run"
    _write_evidence(tmp_path, records)
    with pytest.raises(ValueError, match="ci_run_id misalignment"):
        load_and_verify_release_evidence(tmp_path, require_live=False)


def test_loader_rejects_non_terminal_status_when_live(tmp_path: Path) -> None:
    records = _evidence_bundle()
    records["release-v1.json"]["status"] = "FAILED"
    _write_evidence(tmp_path, records)
    with pytest.raises(ValueError, match="not terminal-success"):
        load_and_verify_release_evidence(tmp_path, require_live=True)
    # Without require_live the terminal-state gate is skipped.
    assert load_and_verify_release_evidence(tmp_path, require_live=False) is not None


def test_loader_rejects_stale_evidence_when_live(tmp_path: Path) -> None:
    stale = (datetime.now(timezone.utc) - timedelta(days=2)).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )
    records = _evidence_bundle()
    records["release-v1.json"]["recorded_at"] = stale
    _write_evidence(tmp_path, records)
    with pytest.raises(ValueError, match="stale"):
        load_and_verify_release_evidence(tmp_path, require_live=True)
    # Freshness is a live-only gate.
    assert load_and_verify_release_evidence(tmp_path, require_live=False) is not None


def test_loader_rejects_future_dated_evidence_when_live(
    tmp_path: Path,
) -> None:
    future = (datetime.now(timezone.utc) + timedelta(days=1)).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )
    records = _evidence_bundle()
    records["deployment-v1.json"]["recorded_at"] = future
    _write_evidence(tmp_path, records)
    with pytest.raises(ValueError, match="in the future"):
        load_and_verify_release_evidence(tmp_path, require_live=True)
    # Future dating is a live-only gate.
    assert load_and_verify_release_evidence(tmp_path, require_live=False) is not None


def test_loader_is_read_only(tmp_path: Path) -> None:
    _write_evidence(tmp_path, _evidence_bundle())
    before = {
        name: (tmp_path / name).read_bytes()
        for name in ("ci-v1.json", "release-v1.json", "deployment-v1.json")
    }
    load_and_verify_release_evidence(tmp_path, require_live=False)
    after = {
        name: (tmp_path / name).read_bytes()
        for name in ("ci-v1.json", "release-v1.json", "deployment-v1.json")
    }
    assert before == after

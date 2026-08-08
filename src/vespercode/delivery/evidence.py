"""T36.1 legacy step 36.A: closed delivery evidence schemas and the
read-only release-evidence verifier.

The three evidence records (CI, release, deployment) are closed bounded
non-secret unions containing only confirmed ids, URLs, commits,
digests, timestamps, environment categories, terminal outcomes, and
access metadata (GREEN-1).  ``load_and_verify_release_evidence`` is the
read-only verifier T37.1 consumes before any external publication:
exact source/tag commit alignment, wheel/checksum, reference
manifest/GHCR image, freshness, terminal state, content-addressed
digests, and cross-record alignment, rejecting unknown, planned,
invented, missing, or inaccessible evidence (GREEN-2/GREEN-4).  This
module performs zero external mutation, credentials, publication, or
filesystem writes.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Final, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    HttpUrl,
    StrictBool,
    StrictStr,
    ValidationInfo,
    field_validator,
    model_validator,
)

_HEX_CHARS: Final = frozenset("0123456789abcdef")

# The evidence schema is closed at version 1 (each record's
# ``schema_version`` is ``Literal[1]``); a future/planned version
# rejects.  The environment categories and terminal statuses are closed
# inline as ``Literal`` types on each record (single source of truth).

_CI_EVIDENCE_FILE: Final = "ci-v1.json"
_RELEASE_EVIDENCE_FILE: Final = "release-v1.json"
_DEPLOYMENT_EVIDENCE_FILE: Final = "deployment-v1.json"
_EVIDENCE_FILES: Final = (
    _CI_EVIDENCE_FILE,
    _RELEASE_EVIDENCE_FILE,
    _DEPLOYMENT_EVIDENCE_FILE,
)

# Freshness window for live evidence: the release evidence is recorded
# immediately after the terminal external operation, so any record older
# than one day cannot be the just-performed release (GREEN-2 freshness).
FRESHNESS_WINDOW_SECONDS: Final = 24 * 60 * 60


def _require_hex(value: str, length: int, field: str | None) -> str:
    label = field or "value"
    if len(value) != length or any(c not in _HEX_CHARS for c in value):
        raise ValueError(f"{label} must be {length} lowercase hex characters")
    return value


_ISO_UTC_RE: Final = r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:Z|[+-]\d{2}:\d{2})$"


def _require_iso_timestamp(value: str, field: str | None) -> str:
    """Require a full timezone-qualified ISO-8601 instant.

    A naive or date-only string is not an absolute instant, so its
    freshness cannot be verified; the live gate must never see one.
    """
    label = field or "value"
    if re.match(_ISO_UTC_RE, value) is None:
        raise ValueError(
            f"{label} must be an ISO-8601 timestamp with timezone "
            "(YYYY-MM-DDTHH:MM:SSZ or +HH:MM)"
        )
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{label} must be an ISO-8601 timestamp") from exc
    return value


class CIReleaseEvidenceV1(BaseModel):
    """Closed non-secret CI evidence: confirmed ids, URLs, commits,
    digests, timestamps, environment category, terminal outcome."""

    model_config = ConfigDict(extra="forbid")
    schema_version: Literal[1]
    ci_run_id: StrictStr
    ci_run_url: HttpUrl
    source_commit: StrictStr
    environment_category: Literal["github_actions", "gitlab_ci", "local_formal"]
    status: Literal["SUCCEEDED", "FAILED"]
    recorded_at: StrictStr

    @field_validator("source_commit")
    @classmethod
    def _commit_form(cls, value: str, info: ValidationInfo) -> str:
        return _require_hex(value, 40, info.field_name)

    @field_validator("recorded_at")
    @classmethod
    def _timestamp_form(cls, value: str, info: ValidationInfo) -> str:
        return _require_iso_timestamp(value, info.field_name)


class ReleaseEvidenceV1(BaseModel):
    """Closed non-secret release evidence (36.A GREEN-1/GREEN-2).

    Exact alignment inside one record: the tag commit must equal the
    source commit (``github_tag_commit == source_commit``), the
    reference manifest digest must equal the GHCR repository digest
    (SPEC AC-30: the published image is the frozen Task 2 reference
    image), and the pulled image digest must equal that same GHCR
    digest — so a record can never describe a release that was not
    built from the frozen source or whose published artifact differs
    from what was pulled.
    """

    model_config = ConfigDict(extra="forbid")
    schema_version: Literal[1]
    release_id: StrictStr
    tag_name: StrictStr
    source_commit: StrictStr
    github_tag_commit: StrictStr
    wheel_sha256: StrictStr
    reference_manifest_digest: StrictStr
    ghcr_repo_digest: StrictStr
    pulled_image_digest: StrictStr
    release_url: HttpUrl
    ci_run_id: StrictStr
    ci_run_url: HttpUrl
    environment_category: Literal["github_actions", "gitlab_ci", "local_formal"]
    status: Literal["SUCCEEDED", "FAILED"]
    recorded_at: StrictStr
    access_metadata: dict[str, StrictBool]

    @field_validator("source_commit", "github_tag_commit")
    @classmethod
    def _commit_form(cls, value: str, info: ValidationInfo) -> str:
        return _require_hex(value, 40, info.field_name)

    @field_validator(
        "wheel_sha256",
        "reference_manifest_digest",
        "ghcr_repo_digest",
        "pulled_image_digest",
    )
    @classmethod
    def _digest_form(cls, value: str, info: ValidationInfo) -> str:
        return _require_hex(value, 64, info.field_name)

    @field_validator("recorded_at")
    @classmethod
    def _timestamp_form(cls, value: str, info: ValidationInfo) -> str:
        return _require_iso_timestamp(value, info.field_name)

    @model_validator(mode="after")
    def _commit_alignment(self) -> "ReleaseEvidenceV1":
        if self.github_tag_commit != self.source_commit:
            raise ValueError(
                "github_tag_commit must equal source_commit "
                "(release tag must point at the frozen source commit)"
            )
        if self.pulled_image_digest != self.ghcr_repo_digest:
            raise ValueError(
                "pulled_image_digest must equal ghcr_repo_digest "
                "(the pulled image must be the published image)"
            )
        if self.reference_manifest_digest != self.ghcr_repo_digest:
            raise ValueError(
                "reference_manifest_digest must equal ghcr_repo_digest "
                "(SPEC AC-30: the published GHCR image must be the frozen "
                "Task 2 reference manifest image)"
            )
        return self


class DeploymentEvidenceV1(BaseModel):
    """Closed non-secret deployment evidence (36.A GREEN-1 vocabulary)."""

    model_config = ConfigDict(extra="forbid")
    schema_version: Literal[1]
    deployment_id: StrictStr
    source_commit: StrictStr
    demo_image_digest: StrictStr
    render_url: HttpUrl
    environment_category: Literal["github_actions", "gitlab_ci", "local_formal"]
    status: Literal["SUCCEEDED", "FAILED"]
    recorded_at: StrictStr
    access_metadata: dict[str, StrictBool]

    @field_validator("source_commit")
    @classmethod
    def _commit_form(cls, value: str, info: ValidationInfo) -> str:
        return _require_hex(value, 40, info.field_name)

    @field_validator("demo_image_digest")
    @classmethod
    def _digest_form(cls, value: str, info: ValidationInfo) -> str:
        return _require_hex(value, 64, info.field_name)

    @field_validator("recorded_at")
    @classmethod
    def _timestamp_form(cls, value: str, info: ValidationInfo) -> str:
        return _require_iso_timestamp(value, info.field_name)


class DeliveryEvidenceV1(BaseModel):
    """One closed bundle of the three aligned evidence records."""

    model_config = ConfigDict(extra="forbid")
    ci: CIReleaseEvidenceV1
    release: ReleaseEvidenceV1
    deployment: DeploymentEvidenceV1


def load_and_verify_release_evidence(
    root: str | Path, require_live: bool
) -> DeliveryEvidenceV1:
    """Read and verify the frozen delivery evidence under *root*.

    Reads ``ci-v1.json``, ``release-v1.json``, and ``deployment-v1.json``
    from *root*, validates each closed record, and enforces the
    cross-record alignment: all three records must share the exact
    source commit, every digest must be content-addressed hex, and with
    ``require_live`` the records must be terminal, fresh (within
    ``FRESHNESS_WINDOW_SECONDS``), and present — a missing file,
    planned/non-terminal status, stale timestamp, or any mismatch fails
    closed with ``ValueError`` and no partial evidence is returned.
    This verifier is read-only: it never mutates the evidence store.
    """
    evidence_root = Path(root)
    missing = [name for name in _EVIDENCE_FILES if not (evidence_root / name).is_file()]
    if missing:
        raise ValueError(f"missing delivery evidence file(s): {', '.join(missing)}")
    ci = CIReleaseEvidenceV1.model_validate(
        json.loads((evidence_root / _CI_EVIDENCE_FILE).read_text(encoding="utf-8"))
    )
    release = ReleaseEvidenceV1.model_validate(
        json.loads((evidence_root / _RELEASE_EVIDENCE_FILE).read_text(encoding="utf-8"))
    )
    deployment = DeploymentEvidenceV1.model_validate(
        json.loads(
            (evidence_root / _DEPLOYMENT_EVIDENCE_FILE).read_text(encoding="utf-8")
        )
    )
    records: dict[
        str, CIReleaseEvidenceV1 | ReleaseEvidenceV1 | DeploymentEvidenceV1
    ] = {
        _CI_EVIDENCE_FILE: ci,
        _RELEASE_EVIDENCE_FILE: release,
        _DEPLOYMENT_EVIDENCE_FILE: deployment,
    }

    source_commits = {record.source_commit for record in records.values()}
    if len(source_commits) != 1:
        raise ValueError(
            f"cross-record source_commit misalignment: {sorted(source_commits)}"
        )
    if release.ci_run_id != ci.ci_run_id:
        raise ValueError(
            "cross-record ci_run_id misalignment: "
            f"release={release.ci_run_id} ci={ci.ci_run_id}"
        )
    if release.ci_run_url != ci.ci_run_url:
        raise ValueError(
            "cross-record ci_run_url misalignment: "
            f"release={release.ci_run_url} ci={ci.ci_run_url}"
        )

    if require_live:
        now = datetime.now(timezone.utc)
        for name, record in records.items():
            recorded_at = datetime.fromisoformat(
                record.recorded_at.replace("Z", "+00:00")
            )
            if record.status != "SUCCEEDED":
                raise ValueError(
                    f"{name} is not terminal-success (status={record.status})"
                )
            age = (now - recorded_at).total_seconds()
            if age < 0:
                raise ValueError(
                    f"{name} recorded_at is in the future (age={age:.0f}s)"
                )
            if age > FRESHNESS_WINDOW_SECONDS:
                raise ValueError(
                    f"{name} recorded_at is stale "
                    f"(age={age:.0f}s > {FRESHNESS_WINDOW_SECONDS}s)"
                )

    return DeliveryEvidenceV1(ci=ci, release=release, deployment=deployment)

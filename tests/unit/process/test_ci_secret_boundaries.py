"""T35.1 legacy step 35.C: fail-closed CI secret boundary tests.

The protected release credentials (SPEC §5.5/§8.4) are project-level
masked protected variables injected only into the protected-tag release
job; the committed CI files must never reference them in any ordinary
push/MR/fork job, and inside the release job every reference must sit
after the three-way source-commit precheck.  These tests validate the
complete static event/secret matrix offline; no platform is queried and
no release is executed during GREEN.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pytest

from tests.unit.process.test_github_actions_contract import (
    GitHubActionsContractV1,
    GITHUB_WORKFLOW_PATH_V1,
    load_ci_yaml_subset,
    load_github_actions_contract,
)
from tests.unit.process.test_gitlab_ci_contract import (
    GITLAB_CI_PATH_V1,
    GitLabContractV1,
    RELEASE_SECRET_NAMES_V1,
    load_gitlab_ci_contract,
)

# The fail-closed ordering contract: every release secret reference in
# the release job must appear in a script item that comes after the item
# carrying the three-way source-commit precheck marker.
PRECHECK_MARKER_V1 = "three-way"

# Light-weight value-pattern scan: the CI files must not commit any
# recognizable secret value (the hash-locked credential scanner runs
# separately in the FORMAL_OFFLINE_V1 closure).
FORBIDDEN_VALUE_PATTERNS_V1: tuple[str, ...] = (
    "ghp_",
    "gho_",
    "glpat-",
    "AKIA",
    "sk-",
)


@dataclass(frozen=True)
class CISecretBoundaryV1:
    """Static secret-boundary verdict over the two committed CI files."""

    github: GitHubActionsContractV1
    gitlab: GitLabContractV1
    github_text: str
    gitlab_text: str
    gitlab_doc: dict[str, object]

    def violations(self) -> tuple[str, ...]:
        """Every fail-closed boundary violation, deterministically
        sorted; the boundary holds exactly when this is empty."""
        found: list[str] = []
        for secret in RELEASE_SECRET_NAMES_V1:
            if secret.lower() in self.github_text.lower():
                found.append(f"github references {secret}")
        if self.github.secrets_referenced:
            found.append(
                "github workflow references action secrets: "
                + ",".join(self.github.secrets_referenced)
            )
        for job in sorted(self.gitlab.job_names):
            mentions = _job_secret_mentions(self.gitlab_doc, job)
            if mentions and job != self.gitlab.release_job_name:
                found.append(
                    f"ordinary job {job} references release secrets: "
                    + ",".join(sorted(mentions))
                )
        if self.gitlab.release_job_name is None:
            found.append("no protected-tag release job is defined")
            return tuple(sorted(found))
        if not self.gitlab.release_requires_protected:
            found.append("release job is not gated by a protected-tag rule")
        if not self.gitlab.release_precheck_present:
            found.append("release job has no three-way precheck step")
        script = _job_script(self.gitlab_doc, self.gitlab.release_job_name)
        precheck_indexes = [
            index for index, item in enumerate(script) if PRECHECK_MARKER_V1 in item
        ]
        if not precheck_indexes:
            found.append("release script has no precheck item")
            return tuple(sorted(found))
        precheck_index = precheck_indexes[0]
        for index, item in enumerate(script):
            for secret in RELEASE_SECRET_NAMES_V1:
                if secret in item and index < precheck_index:
                    found.append(
                        f"{secret} referenced before the precheck (item {index})"
                    )
                if secret in item and index == precheck_index:
                    found.append(f"{secret} referenced inside the precheck item")
        for pattern in FORBIDDEN_VALUE_PATTERNS_V1:
            if pattern in self.github_text or pattern in self.gitlab_text:
                found.append(f"forbidden value pattern {pattern!r} committed")
        return tuple(sorted(set(found)))


def _raw_lines(data: object) -> tuple[str, ...]:
    """All string leaves of the parsed document (deterministic order)."""
    found: list[str] = []
    pending: list[object] = [data]
    while pending:
        current = pending.pop(0)
        if isinstance(current, dict):
            pending[:0] = list(current.values())
        elif isinstance(current, list):
            pending[:0] = list(current)
        elif isinstance(current, str):
            found.append(current)
    return tuple(found)


def _job_secret_mentions(doc: dict[str, object], job: str) -> tuple[str, ...]:
    body = doc.get(job)
    if not isinstance(body, dict):
        return ()
    mentions: set[str] = set()
    for leaf in _raw_lines(body):
        for secret in RELEASE_SECRET_NAMES_V1:
            if secret in leaf:
                mentions.add(secret)
    return tuple(sorted(mentions))


def _job_script(doc: dict[str, object], job: str) -> tuple[str, ...]:
    body = doc.get(job)
    if not isinstance(body, dict):
        return ()
    script = body.get("script")
    if not isinstance(script, list):
        return ()
    return tuple(item for item in script if isinstance(item, str))


@pytest.fixture(scope="module")
def secret_boundary() -> CISecretBoundaryV1:
    github = load_github_actions_contract(GITHUB_WORKFLOW_PATH_V1)
    gitlab = load_gitlab_ci_contract(GITLAB_CI_PATH_V1)
    gitlab_text = GITLAB_CI_PATH_V1.read_text(encoding="utf-8")
    return CISecretBoundaryV1(
        github=github,
        gitlab=gitlab,
        github_text=GITHUB_WORKFLOW_PATH_V1.read_text(encoding="utf-8"),
        gitlab_text=gitlab_text,
        gitlab_doc=load_ci_yaml_subset(gitlab_text),
    )


def test_release_secrets_never_enter_ordinary_jobs(
    secret_boundary: CISecretBoundaryV1,
) -> None:
    """Boundary: ordinary push/MR/fork jobs carry no release/GHCR/Render
    credential — the protected masked variables are injected only into
    the protected-tag release job."""
    assert secret_boundary.violations() == ()


def test_release_job_gated_and_precheck_ordered(
    secret_boundary: CISecretBoundaryV1,
) -> None:
    """Fail-closed rules: the release job requires protected context,
    exact three-way commit equality (precheck), passing prerequisite job
    sets and secrets only after all prechecks pass."""
    gitlab = secret_boundary.gitlab
    assert gitlab.release_job_name == "release"
    assert gitlab.release_requires_protected is True
    assert gitlab.release_precheck_present is True
    assert gitlab.release_tag_pattern is not None
    assert set(gitlab.release_prerequisites) == {
        "unit-test",
        "wheel-build-smoke",
        "reference-image-build",
        "demo-image-build",
    }


def test_github_workflow_never_references_secrets(
    secret_boundary: CISecretBoundaryV1,
) -> None:
    """GREEN-2: the GitHub workflow is fully secretless — no action
    secret and no release credential name appears anywhere in it."""
    assert secret_boundary.github.secrets_referenced == ()
    for secret in RELEASE_SECRET_NAMES_V1:
        assert secret not in secret_boundary.github_text


def test_no_secret_values_committed_in_ci_files(
    secret_boundary: CISecretBoundaryV1,
) -> None:
    for pattern in FORBIDDEN_VALUE_PATTERNS_V1:
        assert pattern not in secret_boundary.github_text
        assert pattern not in secret_boundary.gitlab_text


def test_fail_closed_on_missing_or_ungated_pipeline(tmp_path: Path) -> None:
    """Missing/ungated pipeline state must be reported, never silently
    accepted: the empty contract has no gated release job and no precheck
    (the 35.C RED state)."""
    empty = load_gitlab_ci_contract(tmp_path / "missing-gitlab-ci.yml")
    assert empty.release_job_name is None
    assert empty.release_precheck_present is False
    assert empty.release_requires_protected is False
    assert empty.runs_release(tag="v1.0.0", protected=False) is True

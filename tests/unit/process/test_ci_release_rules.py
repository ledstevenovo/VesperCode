"""T35.1 legacy step 35.C: protected release rules and dual-platform
evidence contract tests.

The committed ``.github/workflows/ci.yml`` and ``.gitlab-ci.yml`` are the
single static sources of truth: the dual contract below is parsed offline
with the standard library only and fails closed whenever the required
protected-tag release admission is missing.  During GREEN no platform is
queried and no release is executed; the post-commit Real step freezes the
real GitHub evidence only (GitLab has no project yet and is recorded
honestly as skipped).

DualCIContractResultV1 is defined in this test module; the committed
``scripts/verify_ci_contract.py`` mirrors it for the Contract command and
for Task 36.A, and the agreement test at the bottom locks the two
together.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pytest

from tests.unit.process.test_github_actions_contract import (
    EXPECTED_JOBS_V1,
    GitHubActionsContractV1,
    GITHUB_WORKFLOW_PATH_V1,
    load_github_actions_contract,
)
from tests.unit.process.test_gitlab_ci_contract import (
    ALL_FOUR_JOBS_V1,
    GITLAB_CI_PATH_V1,
    GitLabContractV1,
    PUSH_WITHOUT_DEMO_V1,
    RELEASE_SECRET_NAMES_V1,
    load_gitlab_ci_contract,
)

# The frozen protected-tag pattern: only semver vX.Y.Z tags in a
# protected (maintainer-controlled) ref may enter the release stage.
RELEASE_TAG_PATTERN_V1 = r"^v[0-9]+\.[0-9]+\.[0-9]+$"


@dataclass(frozen=True)
class CIContextRowV1:
    """One complete event-matrix row (platform, context, scheduled jobs)."""

    platform: str
    context: str
    job_names: frozenset[str]


@dataclass(frozen=True)
class PlatformEvidenceCategoryV1:
    """One categorized platform-evidence row for Task 36.A.

    Categories group the non-secret artifacts/reports each verification
    job must leave behind so later remote records can bind to them.
    """

    platform: str
    category: str
    job_names: frozenset[str]
    required_artifacts: tuple[str, ...]


@dataclass(frozen=True)
class DualCIContractResultV1:
    """The complete static dual-platform CI contract."""

    github: GitHubActionsContractV1
    gitlab: GitLabContractV1
    event_matrix: tuple[CIContextRowV1, ...]
    platform_evidence: tuple[PlatformEvidenceCategoryV1, ...]


def _github_evidence_categories(
    github: GitHubActionsContractV1,
) -> tuple[PlatformEvidenceCategoryV1, ...]:
    return (
        PlatformEvidenceCategoryV1(
            platform="github",
            category="unit-test",
            job_names=frozenset({"unit-test"}),
            required_artifacts=("unit-test-report",),
        ),
        PlatformEvidenceCategoryV1(
            platform="github",
            category="reference-image-build",
            job_names=frozenset({"reference-image-build"}),
            required_artifacts=("reference-image-smoke-report",),
        ),
        PlatformEvidenceCategoryV1(
            platform="github",
            category="demo-image-build",
            job_names=frozenset({"demo-image-build"}),
            required_artifacts=("demo-image-smoke-report",),
        ),
    )


def _gitlab_evidence_categories(
    gitlab: GitLabContractV1,
) -> tuple[PlatformEvidenceCategoryV1, ...]:
    categories: list[PlatformEvidenceCategoryV1] = []
    for job in (
        "unit-test",
        "wheel-build-smoke",
        "reference-image-build",
        "demo-image-build",
    ):
        categories.append(
            PlatformEvidenceCategoryV1(
                platform="gitlab",
                category=job,
                job_names=frozenset({job}),
                required_artifacts=gitlab.artifacts_by_job.get(job, ()),
            )
        )
    categories.append(
        PlatformEvidenceCategoryV1(
            platform="gitlab",
            category="release",
            job_names=frozenset({"release"}),
            # The release job binds the wheel artifact identity produced
            # by wheel-build-smoke from the exact source commit.
            required_artifacts=("dist-ci/vespercode.sha256",),
        )
    )
    return tuple(categories)


def _event_matrix(
    github: GitHubActionsContractV1,
    gitlab: GitLabContractV1,
) -> tuple[CIContextRowV1, ...]:
    return (
        CIContextRowV1(platform="github", context="push", job_names=EXPECTED_JOBS_V1),
        CIContextRowV1(
            platform="github", context="pull_request", job_names=EXPECTED_JOBS_V1
        ),
        CIContextRowV1(
            platform="gitlab",
            context="merge_request (feature)",
            job_names=gitlab.jobs_for(event="merge_request", branch="feature"),
        ),
        CIContextRowV1(
            platform="gitlab",
            context="push (feature)",
            job_names=gitlab.jobs_for(event="push", branch="feature"),
        ),
        CIContextRowV1(
            platform="gitlab",
            context="push (main)",
            job_names=gitlab.jobs_for(event="push", branch="main"),
        ),
        CIContextRowV1(
            platform="gitlab",
            context="protected tag v1.0.0",
            job_names=gitlab.jobs_for(
                event="tag", branch=None, tag="v1.0.0", protected=True
            ),
        ),
        CIContextRowV1(
            platform="gitlab",
            context="unprotected tag v1.0.0",
            job_names=gitlab.jobs_for(event="tag", branch=None, tag="v1.0.0"),
        ),
    )


def load_dual_ci_contract(
    github_path: Path, gitlab_path: Path
) -> DualCIContractResultV1:
    github = load_github_actions_contract(github_path)
    gitlab = load_gitlab_ci_contract(gitlab_path)
    return DualCIContractResultV1(
        github=github,
        gitlab=gitlab,
        event_matrix=_event_matrix(github, gitlab),
        platform_evidence=_github_evidence_categories(github)
        + _gitlab_evidence_categories(gitlab),
    )


@pytest.fixture(scope="module")
def dual_ci_contract() -> DualCIContractResultV1:
    return load_dual_ci_contract(GITHUB_WORKFLOW_PATH_V1, GITLAB_CI_PATH_V1)


def test_unprotected_tag_cannot_enter_release_stage(
    dual_ci_contract: DualCIContractResultV1,
) -> None:
    assert dual_ci_contract.gitlab.runs_release(tag="v1.0.0", protected=False) is False


def test_release_rule_boundary_matrix(
    dual_ci_contract: DualCIContractResultV1,
) -> None:
    """§5.1 matrix rows (card 35.C Expected lines; the T02.1 precedent
    makes the Expected rows the operative matrix authority): fail-closed
    protected-tag admission, three-way precondition, prerequisite job
    completeness and the complete event matrix."""
    gitlab = dual_ci_contract.gitlab
    assert gitlab.runs_release(tag="v1.0.0", protected=False) is False
    assert gitlab.runs_release(tag="v1.0.0", protected=True) is True
    assert gitlab.runs_release(tag="v2.3.4", protected=True) is True
    assert gitlab.runs_release(tag="v1.0.0-rc1", protected=True) is False
    assert gitlab.runs_release(tag="1.0.0", protected=True) is False
    assert gitlab.runs_release(tag="v1.0.0", protected=False) is False
    assert gitlab.release_tag_pattern == RELEASE_TAG_PATTERN_V1
    assert gitlab.release_requires_protected is True
    assert gitlab.release_precheck_present is True
    assert gitlab.release_prerequisites == tuple(sorted(ALL_FOUR_JOBS_V1))
    assert dual_ci_contract.github.runs_all(events={"push", "pull_request"})
    assert dual_ci_contract.github.external_publish_actions == ()
    assert dual_ci_contract.github.secrets_referenced == ()
    assert gitlab.secrets_referenced == ()
    assert dual_ci_contract.event_matrix == (
        (
            CIContextRowV1(
                platform="github",
                context="push",
                job_names=frozenset(
                    {"unit-test", "reference-image-build", "demo-image-build"}
                ),
            ),
            CIContextRowV1(
                platform="github",
                context="pull_request",
                job_names=frozenset(
                    {"unit-test", "reference-image-build", "demo-image-build"}
                ),
            ),
            CIContextRowV1(
                platform="gitlab",
                context="merge_request (feature)",
                job_names=ALL_FOUR_JOBS_V1,
            ),
            CIContextRowV1(
                platform="gitlab",
                context="push (feature)",
                job_names=PUSH_WITHOUT_DEMO_V1,
            ),
            CIContextRowV1(
                platform="gitlab",
                context="push (main)",
                job_names=ALL_FOUR_JOBS_V1,
            ),
            CIContextRowV1(
                platform="gitlab",
                context="protected tag v1.0.0",
                job_names=frozenset({"reference-image-build", "release"}),
            ),
            CIContextRowV1(
                platform="gitlab",
                context="unprotected tag v1.0.0",
                job_names=frozenset(),
            ),
        )
    )
    assert all(
        row.platform in {"github", "gitlab"} for row in dual_ci_contract.event_matrix
    )
    categories = dual_ci_contract.platform_evidence
    assert len(categories) == 8
    assert all(category.required_artifacts for category in categories)


def test_release_admission_requires_all_prerequisite_jobs(
    dual_ci_contract: DualCIContractResultV1,
) -> None:
    """GREEN-1: release admission requires passing prerequisite job sets
    (the four verification jobs) and a precheck step before any secret
    reference; the protected tag rule is the only admission path."""
    gitlab = dual_ci_contract.gitlab
    assert set(gitlab.release_prerequisites) == set(ALL_FOUR_JOBS_V1)
    assert gitlab.release_requires_protected is True
    assert gitlab.release_precheck_present is True
    assert gitlab.release_job_name == "release"


def test_committed_verifier_agrees_with_static_contract(
    dual_ci_contract: DualCIContractResultV1,
) -> None:
    """The committed scripts/verify_ci_contract.py (35.C artifact, also
    exercised by the Contract command) must agree with this static
    contract on the committed files; skipped until the script exists."""
    script = pytest.importorskip("scripts.verify_ci_contract")
    result = script.verify_ci_contract(GITHUB_WORKFLOW_PATH_V1, GITLAB_CI_PATH_V1)
    assert result.github.runs_all(events={"push", "pull_request"})
    assert result.github.external_publish_actions == ()
    assert result.github.secrets_referenced == ()
    assert result.gitlab.jobs_for(event="merge_request", branch="feature") == (
        ALL_FOUR_JOBS_V1
    )
    assert result.gitlab.runs_release(tag="v1.0.0", protected=False) is False
    assert result.gitlab.runs_release(tag="v1.0.0", protected=True) is True
    assert result.gitlab.release_tag_pattern == RELEASE_TAG_PATTERN_V1
    assert result.gitlab.release_requires_protected is True
    assert result.gitlab.release_precheck_present is True
    assert tuple(sorted(result.gitlab.release_prerequisites)) == tuple(
        sorted(ALL_FOUR_JOBS_V1)
    )
    assert result.gitlab.secrets_referenced == ()
    assert len(result.event_matrix) == 7
    assert len(result.platform_evidence) == 8
    assert RELEASE_SECRET_NAMES_V1 == (
        "GHCR_PUSH_TOKEN",
        "GITHUB_RELEASE_TOKEN",
        "RENDER_API_KEY",
    )

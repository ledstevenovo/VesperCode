"""T35.1 legacy step 35.B: GitLab verification pipeline contract tests.

The committed ``.gitlab-ci.yml`` is the single static source of truth:
every assertion below parses that file offline with the standard library
only (the restricted YAML subset parser lives in the 35.A test module)
and fails closed when the required verification-pipeline contract is
missing.  During GREEN no remote query is performed; the GitLab Real
step is skipped because no GitLab project exists (recorded honestly, no
fabricated pipeline state).

GitLabContractV1 is defined in this test module; the release-admission
semantics (``runs_release``) are defined here as well and exercised by
the 35.C tests.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import pytest

from tests.unit.process.test_github_actions_contract import load_ci_yaml_subset

_REPO_ROOT = Path(__file__).resolve().parents[3]
GITLAB_CI_PATH_V1 = _REPO_ROOT / ".gitlab-ci.yml"

ALL_FOUR_JOBS_V1: frozenset[str] = frozenset(
    {"unit-test", "wheel-build-smoke", "reference-image-build", "demo-image-build"}
)
PUSH_WITHOUT_DEMO_V1: frozenset[str] = frozenset(
    {"unit-test", "wheel-build-smoke", "reference-image-build"}
)

# Canonical protected release secret names (SPEC §5.5/§8.4): only the
# protected tag release job may reference them, and only after its
# prechecks pass.  Ordinary push/MR/fork jobs must never see them.
RELEASE_SECRET_NAMES_V1: tuple[str, ...] = (
    "GHCR_PUSH_TOKEN",
    "GITHUB_RELEASE_TOKEN",
    "RENDER_API_KEY",
)

# The project Windows runner binding: wheel-build-smoke must be bound to
# exactly this project Windows 11 x64 runner tag (SPEC §8.4).
WINDOWS_RUNNER_TAG_V1 = "windows-11-x64-vespercode"

_TAG_PATTERN_TOKEN_V1 = "$CI_COMMIT_TAG =~ "

_RESERVED_GITLAB_KEYS_V1: frozenset[str] = frozenset(
    {
        "stages",
        "variables",
        "workflow",
        "include",
        "default",
        "image",
        "services",
        "tags",
        "cache",
    }
)


def _string(value: object, what: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{what} must be a string, got {value!r}")
    return value


def _mapping(value: object, what: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ValueError(f"{what} must be a mapping, got {value!r}")
    return value


def _sequence(value: object, what: str) -> list[object]:
    if isinstance(value, list):
        return value
    if value == ():
        return []
    raise ValueError(f"{what} must be a sequence, got {value!r}")


def _string_sequence(value: object, what: str) -> tuple[str, ...]:
    return tuple(_string(item, what) for item in _sequence(value, what))


def _rule_matches(
    rule: str,
    *,
    event: str,
    branch: str | None,
    tag: str | None,
    protected: bool,
) -> bool:
    """Evaluate one ``&&``-joined GitLab rules condition set.

    Unknown or unsupported conditions fail closed (never match), and a
    job with no declared rules never runs: the committed pipeline
    declares exclusive rules for every job (SPEC §8.4).
    """
    for condition in (part.strip() for part in rule.split("&&")):
        if condition == '$CI_PIPELINE_SOURCE == "merge_request_event"':
            if event != "merge_request":
                return False
        elif condition == '$CI_PIPELINE_SOURCE == "push"':
            if event != "push":
                return False
        elif condition == "$CI_COMMIT_BRANCH":
            if not branch:
                return False
        elif condition.startswith('$CI_COMMIT_BRANCH == "') and condition.endswith('"'):
            if branch != condition[len('$CI_COMMIT_BRANCH == "') : -1]:
                return False
        elif condition.startswith(_TAG_PATTERN_TOKEN_V1):
            if tag is None:
                return False
            match = re.fullmatch(r"/(.*)/", condition[len(_TAG_PATTERN_TOKEN_V1) :])
            if match is None:
                return False
            if re.fullmatch(match.group(1), tag) is None:
                return False
        elif condition == '$CI_COMMIT_REF_PROTECTED == "true"':
            if not protected:
                return False
        elif condition == '$CI_COMMIT_REF_PROTECTED == "false"':
            if protected:
                return False
        elif condition == "$CI_COMMIT_TAG":
            if not tag:
                return False
        else:
            return False
    return True


@dataclass(frozen=True)
class GitLabContractV1:
    """Static contract parsed from ``.gitlab-ci.yml``."""

    job_names: frozenset[str]
    stages: tuple[str, ...]
    rules_by_job: dict[str, tuple[str, ...]]
    windows_runner_tag: str | None
    allow_failure_jobs: tuple[str, ...]
    artifacts_by_job: dict[str, tuple[str, ...]]
    # Release secret names referenced by ordinary (non-release) jobs;
    # the release job itself references them only after its precheck.
    secrets_referenced: tuple[str, ...]
    release_job_name: str | None
    release_tag_pattern: str | None
    release_requires_protected: bool
    release_prerequisites: tuple[str, ...]
    release_precheck_present: bool

    def jobs_for(
        self,
        *,
        event: str,
        branch: str | None = None,
        tag: str | None = None,
        protected: bool = False,
    ) -> frozenset[str]:
        """The exact job set GitLab schedules for the given context.

        Exclusive ``rules`` decide every context; a job runs only when at
        least one of its declared rules matches (SPEC §8.4 push, merge
        request, main and tag contracts).
        """
        matching: set[str] = set()
        for job in self.job_names:
            rules = self.rules_by_job.get(job, ())
            if not rules:
                continue
            if any(
                _rule_matches(
                    rule, event=event, branch=branch, tag=tag, protected=protected
                )
                for rule in rules
            ):
                matching.add(job)
        return frozenset(matching)

    def runs_release(self, *, tag: str, protected: bool) -> bool:
        """Fail-closed protected-tag release admission (35.C).

        Admission requires a defined release job gated by the frozen
        protected-tag rule: protected context plus a tag matching the
        frozen pattern.  Without any protected-tag gate the pipeline is
        considered to admit every tag (the fail-open state the 35.C rule
        closes), so the assertion ``is False`` for an unprotected tag is
        the 35.C RED until the gate exists.
        """
        if self.release_tag_pattern is None:
            return True
        if not protected or not self.release_requires_protected:
            return False
        return re.fullmatch(self.release_tag_pattern, tag) is not None


def _empty_gitlab_contract() -> GitLabContractV1:
    return GitLabContractV1(
        job_names=frozenset(),
        stages=(),
        rules_by_job={},
        windows_runner_tag=None,
        allow_failure_jobs=(),
        artifacts_by_job={},
        secrets_referenced=(),
        release_job_name=None,
        release_tag_pattern=None,
        release_requires_protected=False,
        release_prerequisites=(),
        release_precheck_present=False,
    )


def _extract_tag_pattern(rule: str) -> str | None:
    if _TAG_PATTERN_TOKEN_V1 not in rule:
        return None
    # The pattern is the first /…/ segment of the condition; trailing
    # &&-joined conditions must not defeat the extraction.
    match = re.match(r"^/(.*)/", rule.split(_TAG_PATTERN_TOKEN_V1, 1)[1])
    if match is None:
        return None
    return match.group(1)


def load_gitlab_ci_contract(path: Path) -> GitLabContractV1:
    """Build the static contract from the committed pipeline; the absent
    file yields the empty fail-closed contract (the 35.B RED state)."""
    if not path.is_file():
        return _empty_gitlab_contract()
    data = load_ci_yaml_subset(path.read_text(encoding="utf-8"))
    stages = _string_sequence(data.get("stages", ()), "stage")
    job_names = frozenset(key for key in data if key not in _RESERVED_GITLAB_KEYS_V1)
    rules_by_job: dict[str, tuple[str, ...]] = {}
    windows_runner_tag: str | None = None
    allow_failure_jobs: list[str] = []
    artifacts_by_job: dict[str, tuple[str, ...]] = {}
    secrets_referenced: set[str] = set()
    release_job_name: str | None = None
    release_tag_pattern: str | None = None
    release_requires_protected = False
    release_prerequisites: tuple[str, ...] = ()
    release_precheck_present = False
    for job in sorted(job_names):
        if (
            _string(
                _mapping(data[job], f"job {job}").get("stage", ""), f"job {job} stage"
            )
            == "release"
        ):
            release_job_name = job
    for job in sorted(job_names):
        body = _mapping(data[job], f"job {job}")
        if _string(body.get("stage", ""), f"job {job} stage") == "release":
            release_job_name = job
            for rule in _sequence(body.get("rules", ()), f"job {job} rules"):
                rule_body = _mapping(rule, f"job {job} rule")
                condition = _string(rule_body.get("if", ""), f"job {job} rule if")
                pattern = _extract_tag_pattern(condition)
                if pattern is not None:
                    release_tag_pattern = pattern
                if '$CI_COMMIT_REF_PROTECTED == "true"' in condition:
                    release_requires_protected = True
            release_prerequisites = _string_sequence(
                body.get("needs", ()), f"job {job} needs"
            )
            script = _sequence(body.get("script", ()), f"job {job} script")
            release_precheck_present = any(
                "three-way" in _string(item, f"job {job} script item")
                for item in script
            )
        tags = body.get("tags")
        if tags is not None:
            tag_values = _string_sequence(tags, f"job {job} tags")
            if job == "wheel-build-smoke":
                windows_runner_tag = tag_values[0] if tag_values else None
        if body.get("allow_failure") is True:
            allow_failure_jobs.append(job)
        artifacts = body.get("artifacts")
        if isinstance(artifacts, dict):
            artifacts_by_job[job] = _string_sequence(
                artifacts.get("paths", ()), f"job {job} artifact paths"
            )
        rules_by_job[job] = tuple(
            _string(
                _mapping(rule, f"job {job} rule").get("if", ""), f"job {job} rule if"
            )
            for rule in _sequence(body.get("rules", ()), f"job {job} rules")
        )
        if job == release_job_name:
            continue
        for leaf in _string_leaf_values(body):
            lowered = leaf.lower()
            for name in RELEASE_SECRET_NAMES_V1:
                if name.lower() in lowered:
                    secrets_referenced.add(name)
    return GitLabContractV1(
        job_names=job_names,
        stages=stages,
        rules_by_job=rules_by_job,
        windows_runner_tag=windows_runner_tag,
        allow_failure_jobs=tuple(sorted(allow_failure_jobs)),
        artifacts_by_job=artifacts_by_job,
        secrets_referenced=tuple(sorted(secrets_referenced)),
        release_job_name=release_job_name,
        release_tag_pattern=release_tag_pattern,
        release_requires_protected=release_requires_protected,
        release_prerequisites=release_prerequisites,
        release_precheck_present=release_precheck_present,
    )


def _string_leaf_values(data: object) -> tuple[str, ...]:
    """Every string leaf of the parsed document (deterministic order)."""
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


@pytest.fixture(scope="module")
def gitlab_contract() -> GitLabContractV1:
    return load_gitlab_ci_contract(GITLAB_CI_PATH_V1)


def test_gitlab_runs_all_four_verification_jobs_for_merge_request(
    gitlab_contract: GitLabContractV1,
) -> None:
    assert gitlab_contract.jobs_for(event="merge_request", branch="feature") == {
        "unit-test",
        "wheel-build-smoke",
        "reference-image-build",
        "demo-image-build",
    }


def test_gitlab_pipeline_boundary_matrix(gitlab_contract: GitLabContractV1) -> None:
    """§5.1 matrix rows (card 35.B Expected lines; the T02.1 precedent
    makes the Expected rows the operative matrix authority): the exact
    four-job set for merge requests, the push/main/tag contexts with
    exclusive rules, the project Windows runner binding, ordinary
    secretlessness and artifact retention."""
    assert gitlab_contract.jobs_for(event="merge_request", branch="feature") == (
        ALL_FOUR_JOBS_V1
    )
    assert gitlab_contract.jobs_for(event="push", branch="feature") == (
        PUSH_WITHOUT_DEMO_V1
    )
    assert gitlab_contract.jobs_for(event="push", branch="main") == ALL_FOUR_JOBS_V1
    assert gitlab_contract.jobs_for(event="push", branch="fix/ci-lock") == (
        PUSH_WITHOUT_DEMO_V1
    )
    assert (
        gitlab_contract.jobs_for(event="tag", branch=None, tag="v1.0.0") == frozenset()
    )
    assert ALL_FOUR_JOBS_V1 <= gitlab_contract.job_names
    assert "verify" in gitlab_contract.stages
    assert gitlab_contract.windows_runner_tag == WINDOWS_RUNNER_TAG_V1
    assert gitlab_contract.allow_failure_jobs == ()
    assert gitlab_contract.secrets_referenced == ()
    assert "tests/.tmp/unit-test-report.xml" in gitlab_contract.artifacts_by_job.get(
        "unit-test", ()
    )
    for job in gitlab_contract.job_names:
        assert gitlab_contract.rules_by_job[job], f"job {job} has no exclusive rules"


def test_wheel_build_smoke_binds_windows_runner_and_blocks_without_it(
    gitlab_contract: GitLabContractV1,
) -> None:
    """SPEC §8.4: wheel-build-smoke runs on the project Windows 11 x64
    runner; a missing runner leaves the job pending forever (never
    allowed to fail/retry away), so it blocks merge and release."""
    assert gitlab_contract.windows_runner_tag == WINDOWS_RUNNER_TAG_V1
    assert "wheel-build-smoke" not in gitlab_contract.allow_failure_jobs
    assert "wheel-build-smoke" in gitlab_contract.jobs_for(
        event="merge_request", branch="feature"
    )

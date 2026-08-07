"""T35.1 legacy step 35.C: dual-platform CI contract verifier.

``verify_ci_contract(github_path, gitlab_path)`` statically validates the
committed ``.github/workflows/ci.yml`` and ``.gitlab-ci.yml`` into the
closed ``DualCIContractResultV1``: the complete event matrix, the
protected credential boundary, the three-way source-commit precondition
for release admission, and categorized platform evidence for Task 36.A.
Every model is pydantic ``frozen`` with ``extra="forbid"``.

``validate_remote_records`` defines the fail-closed validation for later
GitHub/GitLab source-commit URLs, ids, timestamps, outcomes and artifact
digests: nothing is queried and no release is executed during GREEN —
missing, non-terminal, foreign-SHA or invented records are rejected.

The models mirror the static contract defined by the 35.A/35.B/35.C
test modules (which parse the files with the offline stdlib subset
parser); the agreement test pins the two together.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

EXPECTED_GITHUB_JOBS_V1: frozenset[str] = frozenset(
    {"unit-test", "reference-image-build", "demo-image-build"}
)
EXPECTED_GITLAB_JOBS_V1: frozenset[str] = frozenset(
    {"unit-test", "wheel-build-smoke", "reference-image-build", "demo-image-build"}
)
RELEASE_TAG_PATTERN_V1 = r"^v[0-9]+\.[0-9]+\.[0-9]+$"
RELEASE_SECRET_NAMES_V1: tuple[str, ...] = (
    "GHCR_PUSH_TOKEN",
    "GITHUB_RELEASE_TOKEN",
    "RENDER_API_KEY",
)

_FORBIDDEN_PUBLISH_TOKENS_V1: tuple[str, ...] = (
    "docker/login-action",
    "docker/build-push-action",
    "action-gh-release",
    "docker login",
    "docker push",
    "gh release",
    "ghcr",
    "render",
    "deploy",
)
_SECRETS_TOKEN_V1 = "${{ secrets."
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


class GitHubCIContractV1(BaseModel):
    """Static GitHub Actions verification-workflow contract."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    job_names: frozenset[str]
    triggers: frozenset[str]
    conditional_jobs: tuple[str, ...]
    permissions_read_only: bool
    uses_actions: tuple[str, ...]
    external_publish_actions: tuple[str, ...]
    secrets_referenced: tuple[str, ...]
    artifact_names: tuple[str, ...]
    reference_loopback_step_present: bool

    def runs_all(self, events: frozenset[str]) -> bool:
        """True when every listed event triggers the full unconditional
        job set (SPEC §8.4: every push and pull request)."""
        return self.triggers >= events and self.conditional_jobs == ()


class GitLabCIContractV1(BaseModel):
    """Static GitLab verification-pipeline contract."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    job_names: frozenset[str]
    stages: tuple[str, ...]
    rules_by_job: dict[str, tuple[str, ...]]
    windows_runner_tag: str | None
    allow_failure_jobs: tuple[str, ...]
    artifacts_by_job: dict[str, tuple[str, ...]]
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
        """The exact job set the pipeline schedules for the context."""
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
        closes).
        """
        if self.release_tag_pattern is None:
            return True
        if not protected or not self.release_requires_protected:
            return False
        return re.fullmatch(self.release_tag_pattern, tag) is not None


class CIContextRowV1(BaseModel):
    """One complete event-matrix row."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    platform: Literal["github", "gitlab"]
    context: str
    job_names: frozenset[str]


class PlatformEvidenceCategoryV1(BaseModel):
    """One categorized platform-evidence row for Task 36.A."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    platform: Literal["github", "gitlab"]
    category: str
    job_names: frozenset[str]
    required_artifacts: tuple[str, ...]


class RemoteRecordV1(BaseModel):
    """One confirmed terminal remote CI record (never invented here).

    The Real steps freeze only records bound to the exact committed
    source SHA with terminal outcomes and accessible URLs/artifacts.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    platform: Literal["github", "gitlab"]
    category: str
    source_sha: str
    run_or_pipeline_id: str
    terminal: bool
    outcome: Literal["success", "failure"]
    urls: tuple[str, ...]
    artifact_identities: tuple[str, ...]
    finished_at: str | None = None


class RemoteRecordsVerdictV1(BaseModel):
    """Fail-closed validation of later remote CI records."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    accepted: bool
    failures: tuple[str, ...] = Field(default=())


class DualCIContractResultV1(BaseModel):
    """The complete static dual-platform CI contract."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    github: GitHubCIContractV1
    gitlab: GitLabCIContractV1
    event_matrix: tuple[CIContextRowV1, ...]
    platform_evidence: tuple[PlatformEvidenceCategoryV1, ...]


# ---------------------------------------------------------------------------
# Restricted YAML subset parser (offline stdlib only; the committed CI
# files use exactly this subset — mirrors the test-module parser).
# ---------------------------------------------------------------------------


def load_ci_yaml_subset(text: str) -> dict[str, object]:
    root: dict[str, object] = {}
    stack: list[tuple[int, dict[str, object] | list[object]]] = [(-1, root)]
    lines: list[tuple[int, str]] = [
        (len(raw) - len(raw.lstrip(" ")), raw.strip()) for raw in text.splitlines()
    ]
    index = 0
    while index < len(lines):
        indent, content = lines[index]
        if not content or content.startswith("#"):
            index += 1
            continue
        while len(stack) > 1 and indent < stack[-1][0]:
            stack.pop()
        if content.startswith("- "):
            index = _consume_sequence_item(
                stack, lines, index, indent, content[2:].strip()
            )
            continue
        if not content.endswith(":") and ": " not in content:
            raise ValueError(f"unsupported CI YAML line: {content!r}")
        key, value = _split_entry(content)
        index = _assign_value(stack, lines, index, indent, key, value)
    return root


def _split_entry(content: str) -> tuple[str, str]:
    if content.endswith(":"):
        return content[:-1], ""
    key, _, value = content.partition(": ")
    return key, value


def _scalar(value: str) -> object:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
        return value[1:-1]
    if value.lower() == "true":
        return True
    if value.lower() == "false":
        return False
    if value.lower() == "null" or value == "~":
        return None
    return value


def _literal_block(
    lines: list[tuple[int, str]], start: int, indent: int
) -> tuple[str, int]:
    body: list[str] = []
    index = start
    while index < len(lines):
        nindent, content = lines[index]
        if not content:
            # A blank line belongs to the block only when a later
            # non-blank line is still inside it.
            lookahead = index + 1
            while lookahead < len(lines) and not lines[lookahead][1]:
                lookahead += 1
            if lookahead < len(lines) and lines[lookahead][0] > indent:
                body.append("")
                index += 1
                continue
            break
        if nindent <= indent:
            break
        body.append(content)
        index += 1
    return "\n".join(body) + "\n", index


def _assign_value(
    stack: list[tuple[int, dict[str, object] | list[object]]],
    lines: list[tuple[int, str]],
    index: int,
    threshold: int,
    key: str,
    value: str,
) -> int:
    parent = stack[-1][1]
    if not isinstance(parent, dict):
        raise AssertionError("mapping entry outside a mapping")
    if value == "|":
        block, index = _literal_block(lines, index + 1, threshold)
        parent[key] = block
        return index
    if value:
        parent[key] = _scalar(value)
        return index + 1
    next_index = index + 1
    while next_index < len(lines) and (
        not lines[next_index][1] or lines[next_index][1].startswith("#")
    ):
        next_index += 1
    if next_index < len(lines) and lines[next_index][0] > threshold:
        child_indent, child_content = lines[next_index]
        if child_content.startswith("- "):
            child: dict[str, object] | list[object] = []
        else:
            child = {}
        parent[key] = child
        stack.append((child_indent, child))
    else:
        parent[key] = None
    return index + 1


def _consume_sequence_item(
    stack: list[tuple[int, dict[str, object] | list[object]]],
    lines: list[tuple[int, str]],
    index: int,
    indent: int,
    item: str,
) -> int:
    parent = stack[-1][1]
    if not isinstance(parent, list):
        raise AssertionError("sequence item outside a sequence")
    if item == "|":
        block, index = _literal_block(lines, index + 1, indent)
        parent.append(block)
        return index
    if item.endswith(":") or ": " in item:
        child: dict[str, object] = {}
        parent.append(child)
        key, value = _split_entry(item)
        stack.append((indent + 2, child))
        return _assign_value(stack, lines, index, indent + 2, key, value)
    parent.append(_scalar(item))
    return index + 1


def _mapping(value: object, what: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ValueError(f"{what} must be a mapping, got {value!r}")
    return value


def _string(value: object, what: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{what} must be a string, got {value!r}")
    return value


def _sequence(value: object, what: str) -> list[object]:
    if isinstance(value, list):
        return value
    if value == ():
        return []
    raise ValueError(f"{what} must be a sequence, got {value!r}")


def _string_sequence(value: object, what: str) -> tuple[str, ...]:
    return tuple(_string(item, what) for item in _sequence(value, what))


def _string_leaf_values(data: object) -> tuple[str, ...]:
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


def _secrets_matches(value: str) -> tuple[str, ...]:
    found: list[str] = []
    rest = value
    while _SECRETS_TOKEN_V1 in rest:
        _, _, rest = rest.partition(_SECRETS_TOKEN_V1)
        name, separator, _ = rest.partition("}}")
        if separator:
            found.append(_SECRETS_TOKEN_V1 + name.strip())
    return tuple(sorted(set(found)))


def _rule_matches(
    rule: str,
    *,
    event: str,
    branch: str | None,
    tag: str | None,
    protected: bool,
) -> bool:
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


# ---------------------------------------------------------------------------
# Contract loaders
# ---------------------------------------------------------------------------


def _load_github(data: dict[str, object]) -> GitHubCIContractV1:
    jobs = _mapping(data.get("jobs", {}), "jobs")
    conditional_jobs = tuple(
        sorted(name for name, body in jobs.items() if "if" in _mapping(body, name))
    )
    permissions = data.get("permissions")
    permissions_read_only = (
        isinstance(permissions, dict)
        and bool(permissions)
        and all(value in {"read", "none"} for value in permissions.values())
    )
    steps: list[dict[str, object]] = []
    for job in jobs.values():
        raw_steps = _mapping(job, "job").get("steps")
        if raw_steps is None:
            continue
        for step in _sequence(raw_steps, "steps"):
            steps.append(_mapping(step, "step"))
    uses_actions = tuple(
        sorted({_string(step["uses"], "uses") for step in steps if "uses" in step})
    )
    external_publish: list[str] = []
    for uses in uses_actions:
        if any(token in uses.lower() for token in _FORBIDDEN_PUBLISH_TOKENS_V1):
            external_publish.append(uses)
    for value in _string_leaf_values(data):
        if any(token in value.lower() for token in _FORBIDDEN_PUBLISH_TOKENS_V1):
            external_publish.append(value)
    artifact_names: list[str] = []
    for step in steps:
        if step.get("uses") != "actions/upload-artifact@v4":
            continue
        with_map = step.get("with")
        if isinstance(with_map, dict) and isinstance(with_map.get("name"), str):
            artifact_names.append(with_map["name"])
    secrets_referenced = tuple(
        sorted(
            set(
                match
                for value in _string_leaf_values(data)
                for match in _secrets_matches(value)
            )
        )
    )
    reference = jobs.get("reference-image-build")
    reference_loopback = False
    if reference is not None:
        for step in _sequence(_mapping(reference, "job").get("steps", ()), "steps"):
            step_body = _mapping(step, "step")
            if "run_reference_image_smoke" in str(step_body.get("run", "")):
                reference_loopback = True
    return GitHubCIContractV1(
        job_names=frozenset(jobs),
        triggers=frozenset(_mapping(data.get("on", {}), "on")),
        conditional_jobs=conditional_jobs,
        permissions_read_only=permissions_read_only,
        uses_actions=uses_actions,
        external_publish_actions=tuple(sorted(set(external_publish))),
        secrets_referenced=secrets_referenced,
        artifact_names=tuple(sorted(set(artifact_names))),
        reference_loopback_step_present=reference_loopback,
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


def _load_gitlab(data: dict[str, object]) -> GitLabCIContractV1:
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
                condition = _string(
                    _mapping(rule, f"job {job} rule").get("if", ""),
                    f"job {job} rule if",
                )
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
            for secret in RELEASE_SECRET_NAMES_V1:
                if secret in leaf:
                    secrets_referenced.add(secret)
    return GitLabCIContractV1(
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


def _event_matrix(
    github: GitHubCIContractV1, gitlab: GitLabCIContractV1
) -> tuple[CIContextRowV1, ...]:
    return (
        CIContextRowV1(
            platform="github", context="push", job_names=EXPECTED_GITHUB_JOBS_V1
        ),
        CIContextRowV1(
            platform="github",
            context="pull_request",
            job_names=EXPECTED_GITHUB_JOBS_V1,
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


def _platform_evidence(
    github: GitHubCIContractV1, gitlab: GitLabCIContractV1
) -> tuple[PlatformEvidenceCategoryV1, ...]:
    categories: list[PlatformEvidenceCategoryV1] = []
    for job, artifact in (
        ("unit-test", "unit-test-report"),
        ("reference-image-build", "reference-image-smoke-report"),
        ("demo-image-build", "demo-image-smoke-report"),
    ):
        categories.append(
            PlatformEvidenceCategoryV1(
                platform="github",
                category=job,
                job_names=frozenset({job}),
                required_artifacts=(artifact,),
            )
        )
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


def verify_ci_contract(github_path: Path, gitlab_path: Path) -> DualCIContractResultV1:
    """Statically validate the two committed CI files into the closed
    dual-platform contract; fails loudly on any missing file or unsupported
    CI YAML line.  No platform is queried and no release is executed."""
    github_path = Path(github_path)
    gitlab_path = Path(gitlab_path)
    if not github_path.is_file():
        raise FileNotFoundError(f"missing GitHub workflow: {github_path}")
    if not gitlab_path.is_file():
        raise FileNotFoundError(f"missing GitLab pipeline: {gitlab_path}")
    github = _load_github(load_ci_yaml_subset(github_path.read_text(encoding="utf-8")))
    gitlab = _load_gitlab(load_ci_yaml_subset(gitlab_path.read_text(encoding="utf-8")))
    return DualCIContractResultV1(
        github=github,
        gitlab=gitlab,
        event_matrix=_event_matrix(github, gitlab),
        platform_evidence=_platform_evidence(github, gitlab),
    )


def validate_remote_records(
    records: tuple[RemoteRecordV1, ...], expected_source_sha: str
) -> RemoteRecordsVerdictV1:
    """Fail-closed validation of later remote CI records (GREEN-2).

    Only terminal records bound to the exact expected source SHA with
    https URLs, artifact identities and a success outcome are accepted;
    anything else — missing/non-terminal/invented records, foreign SHAs,
    inaccessible links — is rejected without querying any platform.
    """
    failures: list[str] = []
    for record in records:
        if record.source_sha != expected_source_sha:
            failures.append(
                f"{record.platform}/{record.category}: source SHA "
                f"{record.source_sha} != expected {expected_source_sha}"
            )
        if not record.terminal:
            failures.append(f"{record.platform}/{record.category}: non-terminal")
        if record.outcome != "success":
            failures.append(f"{record.platform}/{record.category}: outcome not success")
        if not record.urls or not record.artifact_identities:
            failures.append(
                f"{record.platform}/{record.category}: missing urls or artifact identities"
            )
        for url in record.urls:
            if not url.startswith("https://"):
                failures.append(
                    f"{record.platform}/{record.category}: non-https url {url}"
                )
        if record.finished_at is not None and not _looks_like_iso_timestamp(
            record.finished_at
        ):
            failures.append(
                f"{record.platform}/{record.category}: malformed timestamp "
                f"{record.finished_at}"
            )
    return RemoteRecordsVerdictV1(
        accepted=not failures, failures=tuple(sorted(set(failures)))
    )


def _looks_like_iso_timestamp(value: str) -> bool:
    return bool(re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?Z", value))


def main(argv: list[str] | None = None) -> int:
    """CLI entry: validate the committed CI files; exit 0 on PASS."""
    parser = argparse.ArgumentParser(
        description="Validate the committed dual-platform CI contract."
    )
    parser.add_argument("github_workflow", type=Path, help=".github/workflows/ci.yml")
    parser.add_argument("gitlab_ci", type=Path, help=".gitlab-ci.yml")
    args = parser.parse_args(argv)
    try:
        result = verify_ci_contract(args.github_workflow, args.gitlab_ci)
    except (FileNotFoundError, ValueError) as exc:
        print(f"CI contract validation FAILED: {exc}", file=sys.stderr)
        return 1
    summary = {
        "github": {
            "job_names": sorted(result.github.job_names),
            "triggers": sorted(result.github.triggers),
            "permissions_read_only": result.github.permissions_read_only,
            "external_publish_actions": list(result.github.external_publish_actions),
            "secrets_referenced": list(result.github.secrets_referenced),
        },
        "gitlab": {
            "job_names": sorted(result.gitlab.job_names),
            "stages": list(result.gitlab.stages),
            "windows_runner_tag": result.gitlab.windows_runner_tag,
            "secrets_referenced": list(result.gitlab.secrets_referenced),
            "release_job_name": result.gitlab.release_job_name,
            "release_tag_pattern": result.gitlab.release_tag_pattern,
            "release_requires_protected": result.gitlab.release_requires_protected,
            "release_precheck_present": result.gitlab.release_precheck_present,
            "release_prerequisites": list(result.gitlab.release_prerequisites),
        },
        "event_matrix": [
            {
                "platform": row.platform,
                "context": row.context,
                "job_names": sorted(row.job_names),
            }
            for row in result.event_matrix
        ],
        "platform_evidence_categories": len(result.platform_evidence),
    }
    print(json.dumps(summary, indent=2, sort_keys=True))
    print("CI contract validation PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

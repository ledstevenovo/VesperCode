"""T35.1 legacy step 35.A: GitHub Actions verification workflow contract.

The committed ``.github/workflows/ci.yml`` is the single static source of
truth: every assertion below parses that file offline with the standard
library only and fails closed when the required verification-workflow
contract is missing.  During GREEN no remote query is performed; the
card's Real step freezes the real GitHub run evidence against the closed
binding defined here.

GitHubActionsContractV1 is defined in this test module (per the card: it
is statically parsed from ``.github/workflows/ci.yml``).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import AbstractSet

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[3]
GITHUB_WORKFLOW_PATH_V1 = _REPO_ROOT / ".github" / "workflows" / "ci.yml"

EXPECTED_JOBS_V1: frozenset[str] = frozenset(
    {"unit-test", "reference-image-build", "demo-image-build"}
)

# Locked setup: the verification workflow may use exactly these pinned
# actions (SPEC §8.4 locked setup; the card locked-setup pin set).
LOCKED_ACTION_PINS_V1: frozenset[str] = frozenset(
    {
        "actions/checkout@v4",
        "actions/setup-python@v5",
        "actions/upload-artifact@v4",
        "docker/setup-buildx-action@v3",
    }
)

# External publish actions and commands are forbidden in the ordinary
# verification workflow (SPEC §8.4; card boundary): external registry
# login/push, Release, GHCR, Render or any other publish action.
FORBIDDEN_PUBLISH_TOKENS_V1: tuple[str, ...] = (
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


def load_ci_yaml_subset(text: str) -> dict[str, object]:
    """Parse the restricted YAML subset the committed CI files use.

    Only this subset is used by the two committed CI files so their static
    contracts stay parseable offline with the standard library: comments,
    blank lines, block mappings, block sequences, plain/single/double-
    quoted scalars, null values and literal block scalars.  Flow
    collections, anchors, aliases, tags, folded scalars and multi-document
    streams are not supported (none are used).
    """
    root: dict[str, object] = {}
    # (indent, container) stack; the top entry owns the current level and
    # a deeper entry is pushed when a null value opens a nested block.
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
    """Assign *key* in the current container; a nested container opens at
    the first line deeper than *threshold*.  Returns the next line index."""
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


def _secrets_matches(value: str) -> tuple[str, ...]:
    found: list[str] = []
    rest = value
    while _SECRETS_TOKEN_V1 in rest:
        _, _, rest = rest.partition(_SECRETS_TOKEN_V1)
        name, separator, _ = rest.partition("}}")
        if separator:
            found.append(_SECRETS_TOKEN_V1 + name.strip())
    return tuple(sorted(set(found)))


def _iter_steps(data: dict[str, object]) -> list[dict[str, object]]:
    steps: list[dict[str, object]] = []
    for job in _mapping(data.get("jobs", {}), "jobs").values():
        job_body = _mapping(job, "job")
        raw_steps = job_body.get("steps")
        if raw_steps is None:
            continue
        if not isinstance(raw_steps, list):
            raise ValueError("steps must be a sequence")
        for step in raw_steps:
            steps.append(_mapping(step, "step"))
    return steps


def _string(value: object, what: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{what} must be a string, got {value!r}")
    return value


def _action_uses(data: dict[str, object]) -> tuple[str, ...]:
    return tuple(
        sorted(
            {
                _string(step["uses"], "uses")
                for step in _iter_steps(data)
                if "uses" in step
            }
        )
    )


def _artifact_names(data: dict[str, object]) -> tuple[str, ...]:
    names: list[str] = []
    for step in _iter_steps(data):
        if step.get("uses") != "actions/upload-artifact@v4":
            continue
        with_map = step.get("with")
        if isinstance(with_map, dict):
            name = with_map.get("name")
            if isinstance(name, str):
                names.append(name)
    return tuple(sorted(set(names)))


def _external_publish_actions(data: dict[str, object]) -> tuple[str, ...]:
    found: list[str] = []
    for uses in _action_uses(data):
        if any(token in uses.lower() for token in FORBIDDEN_PUBLISH_TOKENS_V1):
            found.append(uses)
    for value in _string_leaf_values(data):
        if any(token in value.lower() for token in FORBIDDEN_PUBLISH_TOKENS_V1):
            found.append(value)
    return tuple(sorted(set(found)))


def _reference_loopback_step_present(data: dict[str, object]) -> bool:
    jobs = _mapping(data.get("jobs", {}), "jobs")
    reference = jobs.get("reference-image-build")
    if reference is None:
        return False
    for step in _iter_steps({"jobs": {"reference-image-build": reference}}):
        if "run_reference_image_smoke" in str(step.get("run", "")):
            return True
    return False


@dataclass(frozen=True)
class GitHubActionsContractV1:
    """Static contract parsed from ``.github/workflows/ci.yml``."""

    job_names: frozenset[str]
    triggers: frozenset[str]
    conditional_jobs: tuple[str, ...]
    permissions_read_only: bool
    uses_actions: tuple[str, ...]
    external_publish_actions: tuple[str, ...]
    secrets_referenced: tuple[str, ...]
    artifact_names: tuple[str, ...]
    reference_loopback_step_present: bool

    def runs_all(self, events: AbstractSet[str]) -> bool:
        """True when every listed event triggers the full unconditional
        job set (SPEC §8.4: every push and pull request)."""
        return self.triggers >= frozenset(events) and self.conditional_jobs == ()


@dataclass(frozen=True)
class GitHubTerminalRunEvidenceV1:
    """Closed GitHub run binding (GREEN-2 definition).

    The post-commit Real step accepts only terminal job URLs and artifact
    identities bound to the exact committed source SHA; anything else —
    a foreign SHA, missing job URLs/artifact identities, or non-github.com
    run links — is rejected.  During GREEN no remote query is performed.
    """

    source_sha: str
    run_id: str
    terminal_job_urls: tuple[str, ...]
    artifact_identities: tuple[str, ...]

    def verify(self, expected_sha: str) -> None:
        if self.source_sha != expected_sha:
            raise ValueError(
                f"evidence source SHA {self.source_sha} does not match {expected_sha}"
            )
        if not self.terminal_job_urls or not self.artifact_identities:
            raise ValueError(
                "terminal evidence requires job URLs and artifact identities"
            )
        for url in self.terminal_job_urls:
            if not url.startswith("https://github.com/"):
                raise ValueError(f"job URL is not a terminal github.com URL: {url}")


_EMPTY_GITHUB_CONTRACT = GitHubActionsContractV1(
    job_names=frozenset(),
    triggers=frozenset(),
    conditional_jobs=(),
    permissions_read_only=False,
    uses_actions=(),
    external_publish_actions=(),
    secrets_referenced=(),
    artifact_names=(),
    reference_loopback_step_present=False,
)


def load_github_actions_contract(path: Path) -> GitHubActionsContractV1:
    """Build the static contract from the committed workflow; the absent
    file yields the empty fail-closed contract (the 35.A RED state)."""
    if not path.is_file():
        return _EMPTY_GITHUB_CONTRACT
    data = load_ci_yaml_subset(path.read_text(encoding="utf-8"))
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
    secrets_referenced = tuple(
        sorted(
            set(
                match
                for value in _string_leaf_values(data)
                for match in _secrets_matches(value)
            )
        )
    )
    return GitHubActionsContractV1(
        job_names=frozenset(jobs),
        triggers=frozenset(_mapping(data.get("on", {}), "on")),
        conditional_jobs=conditional_jobs,
        permissions_read_only=permissions_read_only,
        uses_actions=_action_uses(data),
        external_publish_actions=_external_publish_actions(data),
        secrets_referenced=secrets_referenced,
        artifact_names=_artifact_names(data),
        reference_loopback_step_present=_reference_loopback_step_present(data),
    )


@pytest.fixture(scope="module")
def github_contract() -> GitHubActionsContractV1:
    return load_github_actions_contract(GITHUB_WORKFLOW_PATH_V1)


# The exact RED body of the card (PLAN.md 35.A): the first assert is
# ruff-wrapped (the card displays it on one 98-char line) — a documented
# tooling deviation of the T17.1/T24.1 precedent class; the assertions
# themselves are unchanged.
def test_github_runs_three_no_publish_jobs_on_push_and_pr(
    github_contract: GitHubActionsContractV1,
) -> None:
    assert github_contract.job_names == {
        "unit-test",
        "reference-image-build",
        "demo-image-build",
    }
    assert github_contract.runs_all(events={"push", "pull_request"})
    assert github_contract.external_publish_actions == ()


# §5.1 matrix rows (card 35.A Expected lines; §5.1 itself defines no CI
# matrix, so the Expected rows are the operative matrix authority per the
# T02.1 precedent): exact jobs/triggers/permissions/locked setup, fork
# secretlessness, loopback-inside-reference only, artifacts, and the
# no-external-publish boundary.
_BOUNDARY_MATRIX_V1: tuple[tuple[str, object], ...] = (
    ("job_names", EXPECTED_JOBS_V1),
    ("triggers", frozenset({"push", "pull_request"})),
    ("conditional_jobs", ()),
    ("permissions_read_only", True),
    (
        "uses_actions",
        (
            "actions/checkout@v4",
            "actions/setup-python@v5",
            "actions/upload-artifact@v4",
            "docker/setup-buildx-action@v3",
        ),
    ),
    ("external_publish_actions", ()),
    ("secrets_referenced", ()),
    (
        "artifact_names",
        (
            "demo-image-smoke-report",
            "reference-image-smoke-report",
            "unit-test-report",
        ),
    ),
    ("reference_loopback_step_present", True),
)


@pytest.mark.parametrize(("field", "expected"), _BOUNDARY_MATRIX_V1)
def test_github_actions_boundary_matrix(
    github_contract: GitHubActionsContractV1,
    field: str,
    expected: object,
) -> None:
    assert getattr(github_contract, field) == expected


def test_fork_pull_request_runs_secretless(
    github_contract: GitHubActionsContractV1,
) -> None:
    """GREEN-2: fork/ordinary verification stays secretless — no workflow
    or job references any GitHub secret, so fork PRs complete the full
    three-job closure with no credential and no skip path."""
    assert github_contract.secrets_referenced == ()
    assert github_contract.external_publish_actions == ()
    assert github_contract.runs_all(events=frozenset({"pull_request"}))


def test_closed_binding_rejects_foreign_sha_or_missing_terminal_evidence() -> None:
    """GREEN-2: the closed binding accepts only terminal job URLs and
    artifact identities for the exact committed source SHA."""
    sha = "a" * 40
    foreign = GitHubTerminalRunEvidenceV1(
        source_sha="b" * 40,
        run_id="1234",
        terminal_job_urls=(
            "https://github.com/ledstevenovo/VesperCode/actions/runs/1234",
        ),
        artifact_identities=("unit-test-report@1",),
    )
    with pytest.raises(ValueError, match="does not match"):
        foreign.verify(sha)
    incomplete = GitHubTerminalRunEvidenceV1(
        source_sha=sha, run_id="1234", terminal_job_urls=(), artifact_identities=()
    )
    with pytest.raises(ValueError, match="terminal evidence requires"):
        incomplete.verify(sha)
    valid = GitHubTerminalRunEvidenceV1(
        source_sha=sha,
        run_id="1234",
        terminal_job_urls=(
            "https://github.com/ledstevenovo/VesperCode/actions/runs/1234",
        ),
        artifact_identities=("unit-test-report@1",),
    )
    valid.verify(sha)

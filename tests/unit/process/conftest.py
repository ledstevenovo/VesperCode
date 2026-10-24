"""T37.1 test fixtures: disposable repository copies for read-only verifiers.

Provides ``repository_copy`` (a full tracked-content copy of the repository
with no git metadata, so the process verifiers can run against a mutable
copy) plus the mutation helpers the card's RED tests call directly:
``write_readme_without_section``, ``remove_cold_start_record``, and
``remove_document_check_record``.  The helpers mutate only the supplied
copy; committed process files are never touched.

The report models are pydantic runtime contracts; the hash-locked gate
toolchain does not install runtime dependencies, so this module skips
cleanly there instead of failing at collection (formal env runs it fully).
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest

pytest.importorskip("pydantic")

from scripts.verify_process_evidence import (  # noqa: E402
    ProcessEvidenceResultV1,
    _COLD_START_HEADING_RE,
    _DOCUMENT_CHECK_HEADING_RE,
)
from scripts.verify_readme_contract import README_SECTIONS  # noqa: E402

_REPO_ROOT = Path(__file__).resolve().parents[3]
_IGNORED_DIRS = {
    ".git",
    ".venv",
    ".venv-formal",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
}


def _tracked_root_entries() -> frozenset[str]:
    """The top-level tracked names (files and directories) of the repo."""
    completed = subprocess.run(
        ("git", "ls-files"),
        cwd=str(_REPO_ROOT),
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    return frozenset(
        line.split("/", 1)[0] for line in completed.stdout.splitlines() if line
    )


_TRACKED_ROOT_ENTRIES = _tracked_root_entries()


@pytest.fixture
def repository_copy(tmp_path: Path) -> Path:
    """A full tracked-content repository copy under *tmp_path*.

    Copies exactly the git-tracked tree: root-level entries come from
    ``git ls-files``, so untracked local residue — stale worktrees, tool
    caches, credential-bearing local tool configs — can never enter a
    test copy, and the static ignore list still prunes cache and
    virtualenv directories below tracked directories.  Every
    process/README verifier runs against a mutable copy and the mutation
    helpers below remove records without touching the real repository.
    """
    dest = tmp_path / "repo"

    def _ignore(directory: str, names: list[str]) -> list[str]:
        if Path(directory) == _REPO_ROOT:
            return [name for name in names if name not in _TRACKED_ROOT_ENTRIES]
        return [name for name in names if name in _IGNORED_DIRS]

    shutil.copytree(_REPO_ROOT, dest, ignore=_ignore)
    return dest


def write_readme_without_section(root: Path, section_title: str) -> None:
    """Write ``README.md`` under *root* with every contract section except
    *section_title*, so the README verifier reports exactly the section's
    dedicated error code and nothing else."""
    lines: list[str] = []
    for title in README_SECTIONS:
        if title == section_title:
            continue
        lines.append(f"## {title}")
        lines.append(f"Section content for {title}.")
        lines.append("")
    (root / "README.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def remove_cold_start_record(path: Path) -> None:
    """Strip the cold-start completion section headings from *path*.

    Removes the ``## <n>. …冷启动…通过`` section headings (the disposable
    cold-start completion record); body text may remain, exactly as a
    missing record would appear in the process file.
    """
    text = path.read_text(encoding="utf-8")
    cleaned = _COLD_START_HEADING_RE.sub("", text)
    path.write_text(cleaned, encoding="utf-8")


def remove_document_check_record(path: Path) -> None:
    """Strip the document-check section heading from *path*."""
    text = path.read_text(encoding="utf-8")
    cleaned = _DOCUMENT_CHECK_HEADING_RE.sub("", text)
    path.write_text(cleaned, encoding="utf-8")


def remove_document_check_body(path: Path) -> None:
    """Strip the document-check section body, keeping its heading line."""
    text = path.read_text(encoding="utf-8")
    # ``[^\n]*`` keeps the heading anchor on its own line: a greedy ``.*``
    # (DOTALL) would swallow the whole file to the last ``文档检查``.
    section = re.compile(
        r"(^## \d+\. [^\n]*文档检查[^\n]*\n).*?(?=^## |\Z)",
        re.MULTILINE | re.DOTALL,
    )
    path.write_text(section.sub(r"\1", text), encoding="utf-8")


def _strip_anchor_lines(path: Path, task_id: str, pattern: re.Pattern[str]) -> None:
    """Remove matching lines from *task_id*'s COMPLETION anchor body."""
    text = path.read_text(encoding="utf-8")
    anchor = re.compile(
        r"^## " + re.escape(task_id) + r"-COMPLETION-(\d{8})\n(.*?)(?=^## |\Z)",
        re.MULTILINE | re.DOTALL,
    )

    def _strip(match: re.Match[str]) -> str:
        body = pattern.sub("", match.group(2))
        return f"## {task_id}-COMPLETION-{match.group(1)}\n{body}"

    path.write_text(anchor.sub(_strip, text), encoding="utf-8")


def remove_completion_review_marker(path: Path, task_id: str) -> None:
    """Remove review-related lines from *task_id*'s COMPLETION anchor."""
    _strip_anchor_lines(
        path,
        task_id,
        re.compile(r"(?im)^.*(SPEC_REVIEW_PASS|QUALITY_REVIEW_PASS|评审|review).*$\n?"),
    )


def remove_completion_commit_lines(path: Path, task_id: str) -> None:
    """Remove commit-mention lines from *task_id*'s COMPLETION anchor."""
    _strip_anchor_lines(path, task_id, re.compile(r"(?im)^.*\bcommit\b.*$\n?"))


@pytest.fixture
def failed_process_evidence() -> ProcessEvidenceResultV1:
    """A process-evidence result that fails closed, injected into the
    delivery gate to prove a failed T37.1 process result is rejected."""
    return ProcessEvidenceResultV1(
        error_codes=("COLD_START_RECORD_MISSING",),
        details=("SPEC_PROCESS.md carries no passing cold-start record",),
    )


def remove_v2_task_card(root: Path, card_id: str) -> None:
    """Remove the v2 task card *card_id* from the PLAN.

    The v2 delivery gate's per-card terminality/provenance checks read the
    v1 ``### Task T`` card blocks (see ``verify_delivery._CARD_RE``), so the
    committed v2 relaxed-format PLAN (``## Task V2-01 …``) yields no v1
    cards and those checks are vacuous.  The v2-active fail-closed signal is
    the PLAN task-card count pin: deleting one card drops the count from the
    pinned 40 to 39, so the process-evidence loader reports
    PLAN_TASK_COUNT_MISMATCH and the delivery gate reports
    PROCESS_EVIDENCE_INVALID.  This is the v2 equivalent of the v1
    "mark the owning card incomplete" mutation.
    """
    plan = root / "PLAN.md"
    text = plan.read_text(encoding="utf-8")
    card_re = re.compile(
        r"(?ms)^## (?:Task )?" + re.escape(card_id) + r"(?:[ \t]|$)(?:[^\n]*\n)+?"
        r"(?=^## |\Z)"
    )
    updated, count = card_re.subn("", text, count=1)
    if count != 1:
        raise AssertionError(f"no v2 task card with id {card_id}")
    plan.write_text(updated, encoding="utf-8")


def add_legacy_steps_line(root: Path, card_id: str, step_token: str) -> None:
    """Insert a v1-format ``**Legacy steps:**`` line into v2 card *card_id*.

    The v2 PLAN declares zero legacy steps (EXPECTED_LEGACY_STEP_COUNT = 0).
    A ``**Legacy steps:**`` line is v1 residue: the loader's
    ``_LEGACY_STEPS_RE`` matches the line (the v1 format carries no leading
    ``- ``), so the unique legacy-step set becomes non-empty and the count
    pin fails closed with PLAN_LEGACY_STEP_COUNT_MISMATCH.  This is the v2
    equivalent of the v1 "mark a legacy step incomplete" mutation.
    """
    plan = root / "PLAN.md"
    text = plan.read_text(encoding="utf-8")
    heading = re.compile(
        r"(?m)^(## (?:Task )?" + re.escape(card_id) + r"(?:[ \t]|$)[^\n]*\n)"
    )
    updated, count = heading.subn(
        r"\1**Legacy steps:** " + step_token + r", FAKE-STEP\n",
        text,
        count=1,
    )
    if count != 1:
        raise AssertionError(f"no v2 task card with id {card_id}")
    plan.write_text(updated, encoding="utf-8")


@pytest.fixture
def ready_repository(repository_copy: Path) -> Path:
    """A repository copy in the only state the delivery gate accepts.

    v2 alignment: the delivery gate's per-card terminality and provenance
    checks read the v1 ``### Task T`` card blocks, so the committed v2
    relaxed-format PLAN yields no v1 cards and those checks are vacuous.
    The v2-active acceptance signals are the process-evidence loader (PLAN
    card count 40, zero legacy steps, AGENT_LOG anchors), the README contract
    and the reflection contract — all of which the clean tracked copy
    already satisfies.  The fixture therefore only guarantees a structurally
    compliant student reflection is present (the one contract the clean copy
    does not always carry), matching the v1 fixture's intent.
    """
    reflection = repository_copy / "REFLECTION.md"
    if not reflection.is_file():
        reflection.write_text(
            "## 反思\n\nAI 仅协助润色，内容由学生本人撰写。\n\n" + "字" * 1600 + "\n",
            encoding="utf-8",
        )
    return repository_copy

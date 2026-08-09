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


@pytest.fixture
def repository_copy(tmp_path: Path) -> Path:
    """A full tracked-content repository copy under *tmp_path*.

    Copies the committed tree (no ``.git``, no virtualenvs, no caches) so
    every process/README verifier can run against a mutable copy and the
    mutation helpers below can remove records without touching the real
    repository.
    """
    dest = tmp_path / "repo"
    shutil.copytree(
        _REPO_ROOT,
        dest,
        ignore=shutil.ignore_patterns(*_IGNORED_DIRS),
    )
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


def remove_completion_anchor(path: Path, task_id: str) -> None:
    """Remove *task_id*'s whole COMPLETION anchor block from *path*."""
    text = path.read_text(encoding="utf-8")
    anchor = re.compile(
        r"(?ms)^## " + re.escape(task_id) + r"-COMPLETION-\d{8}\n.*?(?=^## |\Z)",
    )
    path.write_text(anchor.sub("", text), encoding="utf-8")


@pytest.fixture
def failed_process_evidence() -> ProcessEvidenceResultV1:
    """A process-evidence result that fails closed, injected into the
    delivery gate to prove a failed T37.1 process result is rejected."""
    return ProcessEvidenceResultV1(
        error_codes=("COLD_START_RECORD_MISSING",),
        details=("SPEC_PROCESS.md carries no passing cold-start record",),
    )


def mark_child_incomplete(root: Path, step_token: str) -> None:
    """Mark the task card that lists *step_token* as not terminal.

    Turns the owning card's ``**Status:** Done`` into ``Not started`` so the
    legacy step is no longer covered by any terminal task.  The card's
    ``**Legacy steps:**`` tokens are left untouched, so the pinned 141-token
    count contract of the process-evidence loader stays intact.
    """
    plan = root / "PLAN.md"
    text = plan.read_text(encoding="utf-8")
    card_re = re.compile(r"(?ms)^(### Task T\d+\.\d+:.+?)(?=^### Task |\Z)")
    step_re = re.compile(
        r"^\*\*Legacy steps:\*\*[^\n]*\b" + re.escape(step_token) + r"\b",
        re.MULTILINE,
    )
    updated = 0

    def _mark(match: re.Match[str]) -> str:
        nonlocal updated
        block = match.group(1)
        if step_re.search(block) is None:
            return block
        block, count = re.subn(
            r"(?m)^(\*\*Status:\*\* )Done\b",
            r"\1Not started",
            block,
            count=1,
        )
        updated += count
        if count != 1:
            raise AssertionError(f"{step_token} owning card has no Done status")
        return block

    plan.write_text(card_re.sub(_mark, text), encoding="utf-8")
    if updated != 1:
        raise AssertionError(f"no task card lists legacy step {step_token}")


@pytest.fixture
def ready_repository(repository_copy: Path) -> Path:
    """A repository copy in the only state the delivery gate accepts:
    every task card terminal with recorded completion evidence, and a
    structurally compliant student reflection present."""
    plan = repository_copy / "PLAN.md"
    text = plan.read_text(encoding="utf-8")
    # T37.1 is the only ``In progress`` card; with it terminal, the only
    # remaining ``Not started`` card is T37.2.
    text = text.replace("**Status:** In progress", "**Status:** Complete", 1)
    text = text.replace("**Status:** Not started", "**Status:** Complete", 1)
    plan.write_text(text, encoding="utf-8")

    log = repository_copy / "AGENT_LOG.md"
    with log.open("a", encoding="utf-8") as handle:
        handle.write(
            "\n## T37.1-COMPLETION-20260809\n"
            "- **Timestamp (Asia/Taipei):** `2026-08-09T10:00:00+0800`\n"
            "- **Review:** SPEC_REVIEW_PASS\n"
            "- **Commit:** implementation commit `9575f45`\n"
            "\n## T37.2-COMPLETION-20260809\n"
            "- **Timestamp (Asia/Taipei):** `2026-08-09T10:00:00+0800`\n"
            "- **Review:** SPEC_REVIEW_PASS\n"
            "- **Commit:** implementation commit `493384e`\n"
        )

    (repository_copy / "REFLECTION.md").write_text(
        "## 反思\n\nAI 仅协助润色，内容由学生本人撰写。\n\n" + "字" * 1600 + "\n",
        encoding="utf-8",
    )
    return repository_copy

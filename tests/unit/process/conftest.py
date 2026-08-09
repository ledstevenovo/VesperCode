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

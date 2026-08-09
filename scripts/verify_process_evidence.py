"""T37.1 legacy step 37.B: delivery process evidence verifier (read-only).

Fail-closed checker for the append-preserving process records: the
SPEC_PROCESS cold-start and document-check records, the PLAN task-card and
unique legacy-step counts, the AGENT_LOG chronology (every completion entry
carries a valid timestamp within one day of its header date), and per-task
review, commit, PR-URL, and human-intervention records inside each completion
anchor (recorded PR values that are URLs must be https — narrative records
such as "pending …" are honest no-PR records, not URLs — and
human-intervention values must be non-empty when recorded; absent fields in
early anchors are not inferred).  The verifier never
mutates any process file and performs no external I/O beyond reading the
three committed records under the supplied root.
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

from pydantic import BaseModel, ConfigDict

# PLAN contract pins (verified against the committed PLAN.md; changing either
# of these without a matching PLAN change fails closed).
EXPECTED_TASK_COUNT = 68
EXPECTED_LEGACY_STEP_COUNT = 141

_COLD_START_HEADING_RE = re.compile(r"^## \d+\. .*冷启动.*通过", re.MULTILINE)
_DOCUMENT_CHECK_HEADING_RE = re.compile(r"^## \d+\. .*文档检查", re.MULTILINE)
_TASK_HEADING_RE = re.compile(r"^### Task (T\d+\.\d+):", re.MULTILINE)
_LEGACY_STEPS_RE = re.compile(r"^\*\*Legacy steps:\*\*\s*(.+)$", re.MULTILINE)
_LEGACY_TOKEN_SPLIT_RE = re.compile(r"[;,、]")
_ANCHOR_RE = re.compile(
    r"^## (T\d+\.\d+)-COMPLETION-(\d{8})\n(.*?)(?=^## |\Z)",
    re.MULTILINE | re.DOTALL,
)
_TIMESTAMP_RE = re.compile(
    r"\*\*Timestamp \(Asia/Taipei\):\*\*\s*`"
    r"(\d{4}-\d{2}-\d{2})(?:T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2}))?"
    r"`"
)
_REVIEW_MARKER_RE = re.compile(
    r"SPEC_REVIEW_PASS|QUALITY_REVIEW_PASS|SPEC review|Quality review|评审|review",
    re.IGNORECASE,
)
_COMMIT_MARKER_RE = re.compile(r"commit\b|提交")
# ``**PR URL:**`` style labels close their bold markers after the colon;
# ``[^\S\r\n]*`` swallows horizontal whitespace only, so the captured value
# stays on the record's own line: a recorded-but-empty field is detected
# instead of leaking into the next line's text.
_PR_URL_RE = re.compile(r"\*\*PR URL[:：]\*\*[^\S\r\n]*([^\r\n]*)")
_HUMAN_INTERVENTION_RE = re.compile(
    r"\*\*Human intervention[:：]\*\*[^\S\r\n]*([^\r\n]*)"
)


class ProcessEvidenceResultV1(BaseModel):
    """The deterministic process-evidence verdict.

    ``error_codes`` carries the stable fail-closed codes (consumers match
    exact elements); ``details`` carries the human-readable evidence for
    each code, in the same order.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    error_codes: tuple[str, ...] = ()
    details: tuple[str, ...] = ()


def _expanded_legacy_steps(text: str) -> set[str]:
    """The unique expanded legacy-step tokens across every task card.

    ``**Legacy steps:**`` values are comma-separated step tokens
    (``26.A, 26.D, 26.E`` style); whitespace is stripped and empty tokens
    are dropped.  The count of this set is pinned by
    ``EXPECTED_LEGACY_STEP_COUNT``.
    """
    tokens: set[str] = set()
    for match in _LEGACY_STEPS_RE.finditer(text):
        for part in _LEGACY_TOKEN_SPLIT_RE.split(match.group(1)):
            token = part.strip()
            if token:
                tokens.add(token)
    return tokens


def _entry_timestamp_date(body: str) -> str | None:
    """The date (YYYYMMDD) of a completion anchor's Timestamp, if valid."""
    match = _TIMESTAMP_RE.search(body)
    if match is None:
        return None
    return match.group(1).replace("-", "")


def _days_between(entry_date: str, header_date: str) -> int:
    """Calendar-day difference between YYYYMMDD values (month-safe)."""
    from datetime import date

    entry = date.fromisoformat(f"{entry_date[:4]}-{entry_date[4:6]}-{entry_date[6:]}")
    header = date.fromisoformat(
        f"{header_date[:4]}-{header_date[4:6]}-{header_date[6:]}"
    )
    return abs((entry - header).days)


def verify_process_evidence(root: Path | str) -> ProcessEvidenceResultV1:
    """Fail-closed process-evidence check under *root*.

    Reads ``SPEC_PROCESS.md``, ``AGENT_LOG.md``, and ``PLAN.md`` from
    *root* and enforces: cold-start record present, document-check record
    present, exact PLAN task-card count, exact unique legacy-step count,
    valid AGENT_LOG completion chronology, and per-anchor review and commit
    records.  Any violation is reported as its dedicated error code; a
    missing process file fails loudly with ``FileNotFoundError``.
    """
    evidence_root = Path(root)
    missing = [
        name
        for name in ("SPEC_PROCESS.md", "AGENT_LOG.md", "PLAN.md")
        if not (evidence_root / name).is_file()
    ]
    if missing:
        raise FileNotFoundError(
            f"missing process evidence file(s): {', '.join(missing)}"
        )
    spec = (evidence_root / "SPEC_PROCESS.md").read_text(encoding="utf-8")
    log = (evidence_root / "AGENT_LOG.md").read_text(encoding="utf-8")
    plan = (evidence_root / "PLAN.md").read_text(encoding="utf-8")

    error_codes: list[str] = []
    details: list[str] = []

    if _COLD_START_HEADING_RE.search(spec) is None:
        error_codes.append("COLD_START_RECORD_MISSING")
        details.append("SPEC_PROCESS.md carries no cold-start completion record")
    if _DOCUMENT_CHECK_HEADING_RE.search(spec) is None:
        error_codes.append("DOCUMENT_CHECK_RECORD_MISSING")
        details.append("SPEC_PROCESS.md carries no document-check record")

    task_count = len(_TASK_HEADING_RE.findall(plan))
    if task_count != EXPECTED_TASK_COUNT:
        error_codes.append("PLAN_TASK_COUNT_MISMATCH")
        details.append(f"expected {EXPECTED_TASK_COUNT} task cards, found {task_count}")
    legacy_step_count = len(_expanded_legacy_steps(plan))
    if legacy_step_count != EXPECTED_LEGACY_STEP_COUNT:
        error_codes.append("PLAN_LEGACY_STEP_COUNT_MISMATCH")
        details.append(
            f"expected {EXPECTED_LEGACY_STEP_COUNT} unique legacy steps, "
            f"found {legacy_step_count}"
        )

    chronology_invalid = False
    for match in _ANCHOR_RE.finditer(log):
        header_date = match.group(2)
        entry_date = _entry_timestamp_date(match.group(3))
        if entry_date is None or _days_between(entry_date, header_date) > 1:
            chronology_invalid = True
    # Every Timestamp line must carry a parseable value, not only anchor
    # ones (date-level ``2026-08-02`` values are legal, arbitrary text is not).
    timestamp_lines = len(re.findall(r"\*\*Timestamp \(Asia/Taipei\):\*\*", log))
    if len(_TIMESTAMP_RE.findall(log)) != timestamp_lines:
        chronology_invalid = True
    if chronology_invalid:
        error_codes.append("AGENT_LOG_CHRONOLOGY_INVALID")
        details.append("AGENT_LOG.md completion entries or timestamps are not valid")

    for match in _ANCHOR_RE.finditer(log):
        task_id = match.group(1)
        body = match.group(3)
        if _REVIEW_MARKER_RE.search(body) is None:
            error_codes.append(f"REVIEW_RECORD_MISSING:{task_id}")
            details.append(f"{task_id} completion anchor carries no review evidence")
        if _COMMIT_MARKER_RE.search(body) is None:
            error_codes.append(f"COMMIT_RECORD_MISSING:{task_id}")
            details.append(f"{task_id} completion anchor carries no commit evidence")
        pr_match = _PR_URL_RE.search(body)
        if pr_match is not None:
            pr_value = pr_match.group(1).strip()
            # A recorded PR value that is a URL must be https; narrative
            # records such as "pending — human decision …" document that
            # no PR exists yet and are not treated as URLs.
            if re.match(r"^https?://", pr_value, re.IGNORECASE) and not (
                pr_value.lower().startswith("https://")
            ):
                error_codes.append(f"PR_RECORD_INVALID:{task_id}")
                details.append(f"{task_id} PR URL is not an https URL")
        human_match = _HUMAN_INTERVENTION_RE.search(body)
        if human_match is not None and not human_match.group(1).strip():
            error_codes.append(f"HUMAN_INTERVENTION_INVALID:{task_id}")
            details.append(f"{task_id} human-intervention record is empty")

    return ProcessEvidenceResultV1(
        error_codes=tuple(error_codes), details=tuple(details)
    )


def main(argv: list[str] | None = None) -> int:
    """CLI entry: verify process evidence; exit 0 only when every check passes."""
    parser = argparse.ArgumentParser(
        description="Verify the delivery process evidence (read-only)."
    )
    parser.add_argument(
        "root", type=Path, help="repository root holding the process records"
    )
    args = parser.parse_args(argv)
    try:
        result = verify_process_evidence(args.root)
    except Exception as exc:
        print(f"process evidence REJECTED: {exc}")
        return 1
    if result.error_codes:
        print(f"process evidence REJECTED: {', '.join(result.error_codes)}")
        return 1
    print("process evidence ACCEPTED: all process records verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""T37.2 legacy step 37.C: final delivery readiness gate (read-only).

Aggregates the truthful readiness signals fail-closed: the T37.1 process
evidence (through the injectable ``process_evidence_loader``), the PLAN
task-card terminality, the 141-unique legacy-step terminal coverage, the
per-card completion-evidence provenance (every terminal card must own a
COMPLETION anchor in AGENT_LOG or a record in SPEC_PROCESS — the T37.1
quality review's whole-anchor-deletion handoff), the README contract,
the student-reflection structural contract, and — only with
``require_live`` — the frozen delivery evidence records with their
cross-record source-commit alignment.  The gate consumes the truthful
``ProcessEvidenceResultV1`` from T37.1 and does not duplicate a separate
review or admission parser; it never fabricates missing evidence or
human decisions and never mutates any process file.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Callable

from pydantic import BaseModel, ConfigDict

_REPO_ROOT = Path(__file__).resolve().parents[1]
_SRC_ROOT = _REPO_ROOT / "src"
if str(_SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(_SRC_ROOT))
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from vespercode.delivery.evidence import (  # noqa: E402
    _CI_EVIDENCE_FILE,
    _DEPLOYMENT_EVIDENCE_FILE,
    _RELEASE_EVIDENCE_FILE,
    load_and_verify_release_evidence,
)

from scripts.verify_process_evidence import (  # noqa: E402
    _TASK_HEADING_RE,
    _expanded_legacy_steps,
    ProcessEvidenceResultV1,
    verify_process_evidence,
)
from scripts.verify_readme_contract import verify_readme_contract  # noqa: E402
from scripts.verify_reflection import verify_reflection  # noqa: E402

# Terminal statuses (the committed PLAN uses exactly ``Complete``,
# ``Complete — …``, and ``Done``; anything else is not terminal).
_TERMINAL_STATUS_RE = re.compile(r"^(?:Complete|Done)\b", re.MULTILINE)
_STATUS_RE = re.compile(r"^\*\*Status:\*\*\s*(.+)$", re.MULTILINE)
_CARD_RE = re.compile(r"(?ms)^(### Task T\d+\.\d+:.+?)(?=^### Task |\Z)")

_EVIDENCE_FILE_NAMES = (
    _CI_EVIDENCE_FILE,
    _RELEASE_EVIDENCE_FILE,
    _DEPLOYMENT_EVIDENCE_FILE,
)

# The T37.1 process-evidence loader is injectable so tests can prove the
# gate rejects a failed process result without mutating the real records.
ProcessEvidenceLoader = Callable[[Path | str], ProcessEvidenceResultV1]


class DeliveryReadinessResultV1(BaseModel):
    """The deterministic delivery-readiness verdict."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    error_codes: tuple[str, ...] = ()
    details: tuple[str, ...] = ()


def _task_cards(plan: str) -> list[tuple[str, str]]:
    """``(task_id, card_block)`` pairs in file order."""
    cards: list[tuple[str, str]] = []
    for heading in _TASK_HEADING_RE.finditer(plan):
        match = _CARD_RE.search(plan, heading.start())
        if match is not None:
            cards.append((heading.group(1), match.group(1)))
    return cards


def verify_delivery(
    root: Path | str,
    require_live: bool,
    *,
    process_evidence_loader: ProcessEvidenceLoader = verify_process_evidence,
) -> DeliveryReadinessResultV1:
    """Fail-closed aggregate readiness gate under *root*.

    Deterministic check order: process evidence (injected loader) ->
    task terminality and completion-evidence provenance -> legacy-step
    coverage -> README contract -> reflection contract -> live delivery
    evidence (``require_live`` only).  Missing process files fail loudly
    with ``FileNotFoundError``; the reflection/README failures are
    reported as their aggregate codes with the underlying detail.
    """
    delivery_root = Path(root)
    error_codes: list[str] = []
    details: list[str] = []

    process_result = process_evidence_loader(delivery_root)
    if process_result.error_codes:
        error_codes.append("PROCESS_EVIDENCE_INVALID")
        details.append(f"process evidence: {', '.join(process_result.error_codes)}")

    spec = (delivery_root / "SPEC_PROCESS.md").read_text(encoding="utf-8")
    log = (delivery_root / "AGENT_LOG.md").read_text(encoding="utf-8")
    plan = (delivery_root / "PLAN.md").read_text(encoding="utf-8")

    # Every task card must be terminal.
    terminal_ids: set[str] = set()
    for task_id, card in _task_cards(plan):
        status_match = _STATUS_RE.search(card)
        status = status_match.group(1) if status_match is not None else ""
        if _TERMINAL_STATUS_RE.match(status) is None:
            error_codes.append(f"TASK_NOT_TERMINAL:{task_id}")
            details.append(f"{task_id} is not terminal (Status: {status.strip()})")
        else:
            terminal_ids.add(task_id)

    # Per-card provenance: every terminal card must own its recorded
    # completion evidence — its own AGENT_LOG COMPLETION anchor, or a
    # record in the SPEC_PROCESS final region (``## 80.`` onward; the
    # T31.1/T33.1/T34.2 delivery records live in §80-85).  A bare mention
    # anywhere else (milestone tables, cross-references) does not count,
    # so a silently deleted anchor cannot leave a Complete card without
    # provenance (the T37.1 quality-review handoff).
    final_region_start = spec.find("## 80.")
    final_region = spec[final_region_start:] if final_region_start >= 0 else spec
    for task_id, card in _task_cards(plan):
        if task_id not in terminal_ids:
            continue
        has_anchor = re.search(
            r"^## " + re.escape(task_id) + r"-COMPLETION-\d{8}(?!\d)",
            log,
            re.MULTILINE,
        )
        escaped_task_id = re.escape(task_id)
        completion_marker = r"(?:完成|收官|达成)"
        has_record = re.search(
            r"^(?:"
            r"#{2,6}\s+[^\r\n]*\b"
            + escaped_task_id
            + r"\b[^\r\n]*"
            + completion_marker
            + r"|(?:[-*]\s+)?\*\*[^*\r\n]*\b"
            + escaped_task_id
            + r"\b[^*\r\n]*"
            + completion_marker
            + r"[^*\r\n]*\*\*)",
            final_region,
            re.MULTILINE,
        )
        if has_anchor is None and has_record is None:
            error_codes.append(f"COMPLETION_EVIDENCE_MISSING:{task_id}")
            details.append(
                f"{task_id} is terminal but has no AGENT_LOG anchor or "
                "SPEC_PROCESS final-region record"
            )

    # Every declared legacy step must be covered by at least one terminal
    # task card.
    covered_steps: set[str] = set()
    for task_id, card in _task_cards(plan):
        if task_id not in terminal_ids:
            continue
        steps_match = re.search(r"^\*\*Legacy steps:\*\*\s*(.+)$", card, re.MULTILINE)
        if steps_match is not None:
            for part in re.split(r"[;,、]", steps_match.group(1)):
                token = part.strip()
                if token:
                    covered_steps.add(token)
    for step in sorted(_expanded_legacy_steps(plan) - covered_steps):
        error_codes.append(f"LEGACY_STEP_INCOMPLETE:{step}")
        details.append(f"legacy step {step} is not covered by a terminal task")

    # README and reflection aggregate contract failures.
    try:
        readme_result = verify_readme_contract(delivery_root / "README.md")
    except Exception as exc:
        error_codes.append("README_CONTRACT_FAILED")
        details.append(f"README contract: {exc}")
    else:
        if readme_result.error_codes:
            error_codes.append("README_CONTRACT_FAILED")
            details.append(f"README contract: {', '.join(readme_result.error_codes)}")
    try:
        reflection_result = verify_reflection(delivery_root / "REFLECTION.md")
    except Exception as exc:
        error_codes.append("REFLECTION_CONTRACT_FAILED")
        details.append(f"reflection contract: {exc}")
    else:
        if reflection_result.error_codes:
            error_codes.append("REFLECTION_CONTRACT_FAILED")
            details.append(
                f"reflection contract: {', '.join(reflection_result.error_codes)}"
            )

    # Live delivery evidence: terminal, fresh, cross-record source-commit
    # aligned (require_live only — the records exist only after terminal
    # CI/release/deployment facts are observed).
    if require_live:
        evidence_root = delivery_root / "delivery" / "evidence"
        source_drift = False
        if all((evidence_root / name).is_file() for name in _EVIDENCE_FILE_NAMES):
            commits: set[str] = set()
            for name in _EVIDENCE_FILE_NAMES:
                try:
                    record = json.loads(
                        (evidence_root / name).read_text(encoding="utf-8")
                    )
                    commits.add(record.get("source_commit"))
                except (
                    OSError,
                    UnicodeDecodeError,
                    json.JSONDecodeError,
                    AttributeError,
                ):
                    pass  # the loader reports the real schema failure below
            if len(commits) > 1:
                source_drift = True
                error_codes.append("SOURCE_COMMIT_DRIFT")
                details.append("delivery evidence source_commit values are not aligned")
        try:
            load_and_verify_release_evidence(evidence_root, require_live=True)
        except Exception as exc:
            if not source_drift:
                error_codes.append("DELIVERY_EVIDENCE_INVALID")
                details.append(f"delivery evidence: {exc}")

    return DeliveryReadinessResultV1(
        error_codes=tuple(error_codes), details=tuple(details)
    )


def main(argv: list[str] | None = None) -> int:
    """CLI entry: verify delivery readiness; exit 0 only when every check passes."""
    parser = argparse.ArgumentParser(
        description="Verify final delivery readiness (read-only)."
    )
    parser.add_argument(
        "root", type=Path, help="repository root holding the delivery records"
    )
    parser.add_argument(
        "--live",
        action="store_true",
        help="also require terminal, fresh, source-aligned delivery evidence",
    )
    args = parser.parse_args(argv)
    try:
        result = verify_delivery(args.root, require_live=args.live)
    except Exception as exc:
        print(f"delivery readiness REJECTED: {exc}")
        return 1
    if result.error_codes:
        print(f"delivery readiness REJECTED: {', '.join(result.error_codes)}")
        return 1
    print("delivery readiness ACCEPTED: all final delivery records verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

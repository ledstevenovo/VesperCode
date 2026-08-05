"""T04.2 legacy step 4.E: redacted changed-file credential scanner.

Scans only an explicit path sequence with the Task 1 frozen credential
rule table, treats binary input as non-text, and reports only sorted
bounded ``(path, rule_id)`` findings plus the scanned-file count.  Matched
values, contents, offsets, derivatives, and network traffic are never
emitted.  The CLI accepts exactly ``--changed --redact --fail-on-match``,
enumerates the git changed-file union through the Task 1 gate scan, and
fails on a match with exit 1 (or exit 2 on usage/enumeration/read errors).
File discovery, undeclared-path reads, and external requests remain out of
scope (GREEN-4).
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Literal, Sequence, TypeAlias

from pydantic import BaseModel, ConfigDict

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts.gate_scan import _RULES, _enumerate_changed_paths  # noqa: E402

_ScanFailureCodeV1 = Literal[
    "CREDENTIAL_SCAN_NOT_REGULAR_FILE",
    "CREDENTIAL_SCAN_READ_FAILED",
]


class CredentialScanFindingV1(BaseModel):
    """One bounded (path, rule_id) finding; never the matched value."""

    model_config = ConfigDict(frozen=True)

    path: str
    rule_id: str


CredentialScanFindingSequenceV1: TypeAlias = tuple[CredentialScanFindingV1, ...]


class CredentialScanReportV1(BaseModel):
    """Immutable ordered report: sorted findings plus the scanned count."""

    model_config = ConfigDict(frozen=True)

    findings: CredentialScanFindingSequenceV1
    scanned_file_count: int


class CredentialScanErrorV1(ValueError):
    """Closed scanner failure with a stable code; never a matched value."""

    def __init__(
        self,
        error_code: _ScanFailureCodeV1,
        path: str,
    ) -> None:
        super().__init__(f"{error_code}: {path}")
        self.error_code = error_code
        self.path = path


def _is_binary(data: bytes) -> bool:
    return b"\x00" in data


def scan_changed_files(paths: Sequence[Path]) -> CredentialScanReportV1:
    """Scan only *paths* and return the sorted redacted report.

    Binary inputs are treated as non-text and never pattern-scanned.
    Missing, non-regular, or unreadable paths fail closed with a stable
    error before any finding is returned.  Findings are sorted by
    ``(path, rule_id)`` and carry only the path and rule id — never a
    matched value, offset, content, or derivative.
    """
    findings: list[CredentialScanFindingV1] = []
    scanned = 0
    for raw_path in paths:
        path = Path(raw_path)
        if not path.is_file():
            raise CredentialScanErrorV1("CREDENTIAL_SCAN_NOT_REGULAR_FILE", str(path))
        try:
            data = path.read_bytes()
        except OSError as exc:
            raise CredentialScanErrorV1(
                "CREDENTIAL_SCAN_READ_FAILED", str(path)
            ) from exc
        scanned += 1
        if _is_binary(data):
            continue
        for rule_id, pattern in _RULES:
            if pattern.search(data) is not None:
                findings.append(
                    CredentialScanFindingV1(path=str(path), rule_id=rule_id)
                )
    findings.sort(key=lambda finding: (finding.path, finding.rule_id))
    return CredentialScanReportV1(findings=tuple(findings), scanned_file_count=scanned)


def _render_matches(report: CredentialScanReportV1, root: Path) -> str:
    """Render the redacted MATCH lines relative to *root*; never a value."""
    return "\n".join(
        f"MATCH\t{os.path.relpath(finding.path, root).replace('\\', '/')}"
        f"\t{finding.rule_id}"
        for finding in report.findings
    )


def main(argv: list[str]) -> int:
    if sorted(argv) != ["--changed", "--fail-on-match", "--redact"]:
        sys.stderr.write("ERROR\tCREDENTIAL_SCAN_INVALID_ARGUMENT\n")
        return 2
    try:
        changed = _enumerate_changed_paths(_REPO_ROOT)
    except Exception:
        sys.stderr.write("ERROR\tCREDENTIAL_SCAN_GIT_ENUMERATION_FAILED\n")
        return 2
    try:
        report = scan_changed_files(tuple(_REPO_ROOT / path for path in changed))
    except CredentialScanErrorV1 as exc:
        sys.stderr.write(f"ERROR\t{exc.error_code}\t{exc.path}\n")
        return 2
    rendered = _render_matches(report, _REPO_ROOT)
    if rendered:
        sys.stdout.write(rendered + "\n")
    return 1 if report.findings else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

"""T19.1 legacy step 19.A: closed check results and static-tool parsing.

Converts one bounded ``RawExecutionResultV1`` (T18.2) for a profile-frozen
Ruff or Mypy execution into the sole closed ``CheckResultV1`` combinations
(SPEC §4.5 ``CheckResult.status = PASS | FAIL | ERROR | TIMEOUT |
NOT_RUN``) and fails closed on malformed, truncated, non-UTF-8,
exit-inconsistent, output-limited, isolated-violated, execution-failed, or
version-inconsistent output — a PASS can never be decided from the process
exit code alone ("不能仅按进程退出码判定 PASS").

The v1 parsers bind their format knowledge to the frozen T02.4 gate
toolchain identities (SPEC §1.4.1, ``ReferenceProfileManifestV1``): a
profile whose ``ruff_version``/``mypy_version`` is not the frozen value is
version-inconsistent output support and fails closed before any status is
produced.

Owns the closed check-result schema and the frozen Ruff 0.16.1 / Mypy
2.3.0 text-format parsing only.  Pytest reporting, failure fingerprinting,
execution, and Baseline decisions remain out of scope (GREEN-4).
"""

from __future__ import annotations

import hashlib
import re
from typing import Annotated, Literal, TypeAlias

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    Strict,
    StrictStr,
    field_validator,
    model_validator,
)

from vespercode.canonical.digest import domain_digest
from vespercode.contracts.action import CheckPlanIdV1
from vespercode.contracts.optional import AbsentV1, PresentV1
from vespercode.execution.docker_executor import RawExecutionResultV1
from vespercode.profiles.reference import ReferenceProfileManifestV1

# The frozen T02.4 gate toolchain identities (SPEC §1.4.1; the packaged
# built-in manifest carries the same values).  The v1 parsers know only
# these exact text formats; any other tool version is version-inconsistent
# output support and fails closed with CHECK_ERROR.
_FROZEN_RUFF_VERSION = "0.16.1"
_FROZEN_MYPY_VERSION = "2.3.0"

CheckFindingErrorCodeV1 = Literal[
    "CHECK_PASS",
    "CHECK_FAILED",
    "CHECK_ERROR",
    "CHECK_TIMEOUT",
    "CHECK_NOT_RUN",
]
"""The closed finding vocabulary of the sole permitted combinations."""

OptionalIntV1: TypeAlias = Annotated[
    AbsentV1 | PresentV1[Annotated[int, Strict(), Field(ge=1)]],
    Field(discriminator="kind"),
]
"""SPEC §0.1 closed optional integer (ABSENT for Mypy's missing column).

The PRESENT value is Strict and positive, so bool/float/string spellings
and zero/negative columns reject instead of coercing (the T05.1
strict-on-scalars convention).
"""


class CheckFindingLocationV1(BaseModel):
    """One diagnostic location: exact reported path, line, optional column."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    path: StrictStr
    line: Annotated[int, Field(strict=True, ge=1)]
    column: OptionalIntV1

    @field_validator("path")
    @classmethod
    def _path_is_non_empty(cls, value: str) -> str:
        if value == "":
            raise ValueError("diagnostic paths must not be empty")
        return value


class CheckFindingV1(BaseModel):
    """One structured finding of a closed check result.

    ``error_code`` is the stable closed vocabulary; ``location`` is the
    exact reported diagnostic location (None only for status findings
    that carry no location).
    """

    model_config = ConfigDict(extra="forbid", frozen=True)
    error_code: CheckFindingErrorCodeV1
    message: StrictStr
    location: CheckFindingLocationV1 | None = None

    @field_validator("message")
    @classmethod
    def _message_is_non_empty(cls, value: str) -> str:
        if value == "":
            raise ValueError("finding messages must not be empty")
        return value


CheckFindingSequenceV1: TypeAlias = tuple[CheckFindingV1, ...]
"""An immutable ordered tuple of zero or more ``CheckFindingV1`` items."""


class CheckResultV1(BaseModel):
    """The sole closed check-result combination (SPEC §4.5).

    Exactly the card Interface fields: ``status``, ``check_kind``,
    ``structured_findings``, and the deterministic canonical
    ``raw_digest`` binding the complete bounded raw evidence.  The
    permitted status-to-findings combinations are closed and
    machine-enforced: PASS and NOT_RUN carry no findings; FAIL carries one
    or more ``CHECK_FAILED`` findings; ERROR and TIMEOUT carry exactly one
    stable finding.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)
    status: Literal["PASS", "FAIL", "ERROR", "TIMEOUT", "NOT_RUN"]
    check_kind: CheckPlanIdV1
    structured_findings: CheckFindingSequenceV1
    raw_digest: StrictStr

    @field_validator("raw_digest")
    @classmethod
    def _raw_digest_is_64_lowercase_hex(cls, value: str) -> str:
        if re.fullmatch(r"[0-9a-f]{64}", value) is None:
            raise ValueError(
                "raw_digest must be exactly 64 lowercase hexadecimal characters"
            )
        return value

    @model_validator(mode="after")
    def _require_permitted_combination(self) -> CheckResultV1:
        findings = self.structured_findings
        codes = tuple(finding.error_code for finding in findings)
        if self.status in ("PASS", "NOT_RUN"):
            if findings != ():
                raise ValueError(f"{self.status} results carry no findings")
        elif self.status == "FAIL":
            if not findings or any(code != "CHECK_FAILED" for code in codes):
                raise ValueError(
                    "FAIL results carry one or more CHECK_FAILED findings only"
                )
        elif self.status == "ERROR":
            if len(findings) != 1 or codes != ("CHECK_ERROR",):
                raise ValueError("ERROR results carry exactly one CHECK_ERROR finding")
        elif self.status == "TIMEOUT":
            if len(findings) != 1 or codes != ("CHECK_TIMEOUT",):
                raise ValueError(
                    "TIMEOUT results carry exactly one CHECK_TIMEOUT finding"
                )
        return self


def _raw_evidence_digest(raw: RawExecutionResultV1) -> str:
    """The deterministic canonical raw identity (SPEC §0.1).

    Binds the complete bounded raw evidence: exact stdout/stderr byte
    digests, the container exit code, the exact byte total, and the closed
    failure flags/code.  Equal raw evidence always yields the same digest.
    """
    exit_code_field: dict[str, str | int] = (
        {"kind": "ABSENT"}
        if raw.exit_code is None
        else {"kind": "PRESENT", "value": raw.exit_code}
    )
    error_code_field: dict[str, str | int] = (
        {"kind": "ABSENT"}
        if raw.error_code is None
        else {"kind": "PRESENT", "value": raw.error_code}
    )
    return domain_digest(
        "RawExecutionResultV1",
        1,
        {
            "stdout_sha256": hashlib.sha256(raw.stdout).hexdigest(),
            "stderr_sha256": hashlib.sha256(raw.stderr).hexdigest(),
            "exit_code": exit_code_field,
            "output_bytes": raw.output_bytes,
            "timed_out": raw.timed_out,
            "output_limit_exceeded": raw.output_limit_exceeded,
            "container_stopped": raw.container_stopped,
            "error_code": error_code_field,
        },
    )


def _error_result(
    raw: RawExecutionResultV1,
    check_kind: CheckPlanIdV1,
    message: str,
) -> CheckResultV1:
    return CheckResultV1(
        status="ERROR",
        check_kind=check_kind,
        structured_findings=(
            CheckFindingV1(error_code="CHECK_ERROR", message=message, location=None),
        ),
        raw_digest=_raw_evidence_digest(raw),
    )


def _closed_execution_outcome(
    raw: RawExecutionResultV1,
    check_kind: CheckPlanIdV1,
) -> CheckResultV1 | None:
    """Map the closed execution failures to TIMEOUT/ERROR (None on success)."""
    if raw.error_code is None:
        return None
    if raw.error_code == "CHECK_TIMEOUT":
        return CheckResultV1(
            status="TIMEOUT",
            check_kind=check_kind,
            structured_findings=(
                CheckFindingV1(
                    error_code="CHECK_TIMEOUT",
                    message="check timed out",
                    location=None,
                ),
            ),
            raw_digest=_raw_evidence_digest(raw),
        )
    if raw.error_code == "CHECK_OUTPUT_LIMIT_EXCEEDED":
        return _error_result(
            raw, check_kind, "output limit exceeded: evidence truncated"
        )
    if raw.error_code == "CHECK_ISOLATION_VIOLATION":
        return _error_result(raw, check_kind, "container isolation violation")
    if raw.error_code == "CHECK_EXECUTION_ERROR":
        return _error_result(raw, check_kind, "container execution error")
    raise AssertionError(f"unreachable execution error code: {raw.error_code}")


def _decode_stdout(raw: RawExecutionResultV1) -> str | None:
    """Strict UTF-8 decode of the bounded stdout; None fails closed."""
    try:
        return raw.stdout.decode("utf-8")
    except UnicodeDecodeError:
        return None


def _normalize_line_endings(text: str) -> str:
    return text.replace("\r\n", "\n").replace("\r", "\n")


# Ruff 0.16.1 terminal summary and hint shapes (observed from the frozen
# tool; the profile-frozen version binding makes these the closed v1 set).
_RUFF_FOUND_RE = re.compile(r"^Found (\d+) errors?\.$")
_RUFF_FIX_HINT_RE = re.compile(r"^\[\*\] \d+ fixable with the `--fix` option\.$")
_RUFF_NO_FIXES_RE = re.compile(
    r"^No fixes available \(\d+ hidden fix(?:es)? can be enabled with the "
    r"`--unsafe-fixes` option\)\.$"
)
_RUFF_CLEAN = "All checks passed!"
_RUFF_LOCATION_RE = re.compile(r"^ --> (.+):(\d+):(\d+)$")
_RUFF_HEADER_RE = re.compile(r"^([A-Z][A-Z0-9]*)(?: \[\*\] )?(.*)$")
# Every excerpt/help line shape of the frozen full text format; any other
# line is an unknown diagnostic category and fails closed.
_RUFF_EXCERPT_RES = (
    re.compile(r"^ +\|"),
    re.compile(r"^\d+ \|"),
    re.compile(r"^\d+ \+"),
    re.compile(r"^  - "),
    re.compile(r"^help: "),
    re.compile(r"^  = "),
)


def _is_ruff_excerpt(line: str) -> bool:
    return any(pattern.match(line) is not None for pattern in _RUFF_EXCERPT_RES)


def _parse_ruff_text(text: str, raw: RawExecutionResultV1) -> CheckResultV1:
    """Parse one frozen Ruff 0.16.1 text output into a closed result.

    Returns an ERROR result on any shape that cannot prove completeness;
    on complete output returns PASS (clean) or FAIL (violations), with the
    terminal violation count bound to the parsed blocks and the exit code
    cross-checked for consistency.
    """
    text = _normalize_line_endings(text)
    if text == "":
        return _error_result(
            raw, "RUFF", "output is empty: completeness cannot be proven"
        )
    if text.strip() == _RUFF_CLEAN:
        if raw.exit_code != 0:
            return _error_result(raw, "RUFF", "exit code contradicts clean output")
        return CheckResultV1(
            status="PASS",
            check_kind="RUFF",
            structured_findings=(),
            raw_digest=_raw_evidence_digest(raw),
        )
    lines = text.split("\n")
    non_empty_indices = [index for index, line in enumerate(lines) if line != ""]
    if not non_empty_indices:
        return _error_result(
            raw, "RUFF", "output is empty: completeness cannot be proven"
        )
    terminal_index = non_empty_indices[-1]
    if _RUFF_FIX_HINT_RE.match(lines[terminal_index]) or _RUFF_NO_FIXES_RE.match(
        lines[terminal_index]
    ):
        terminal_index = non_empty_indices[-2] if len(non_empty_indices) >= 2 else -1
        if terminal_index < 0:
            return _error_result(raw, "RUFF", "malformed output: hint without summary")
    found = _RUFF_FOUND_RE.match(lines[terminal_index])
    if found is None:
        return _error_result(
            raw, "RUFF", "truncated output: missing the Found N errors. summary line"
        )
    expected_count = int(found.group(1))
    if expected_count < 1:
        return _error_result(raw, "RUFF", "malformed output: empty violation summary")
    blocks: list[tuple[str, str, str, int, int]] = []
    index = 0
    while index < terminal_index:
        line = lines[index]
        if line == "" or _is_ruff_excerpt(line):
            index += 1
            continue
        header = _RUFF_HEADER_RE.match(line)
        if header is None:
            return _error_result(raw, "RUFF", f"unknown diagnostic line: {line!r}")
        code = header.group(1)
        message = header.group(2)
        if message == "" or message.startswith(" "):
            message = message.lstrip(" ")
        if message == "":
            return _error_result(raw, "RUFF", "malformed diagnostic header")
        if index + 1 >= terminal_index:
            return _error_result(
                raw, "RUFF", "unknown diagnostic category: header without location"
            )
        location = _RUFF_LOCATION_RE.match(lines[index + 1])
        if location is None:
            return _error_result(
                raw, "RUFF", "unknown diagnostic category: header without location"
            )
        path, line, column = location.groups()
        blocks.append((code, message, path, int(line), int(column)))
        index += 2
    if len(blocks) != expected_count:
        return _error_result(
            raw,
            "RUFF",
            "violation count mismatch: output is truncated or incomplete",
        )
    if raw.exit_code == 0:
        return _error_result(raw, "RUFF", "exit code contradicts findings")
    findings = tuple(
        CheckFindingV1(
            error_code="CHECK_FAILED",
            message=message,
            location=CheckFindingLocationV1(
                path=path,
                line=line,
                column=PresentV1(kind="PRESENT", value=column),
            ),
        )
        for _code, message, path, line, column in blocks
    )
    return CheckResultV1(
        status="FAIL",
        check_kind="RUFF",
        structured_findings=findings,
        raw_digest=_raw_evidence_digest(raw),
    )


def parse_ruff_result(
    raw: RawExecutionResultV1,
    profile: ReferenceProfileManifestV1,
) -> CheckResultV1:
    """Parse one bounded Ruff execution into the sole closed result."""
    if profile.ruff_version != _FROZEN_RUFF_VERSION:
        return _error_result(
            raw,
            "RUFF",
            f"unsupported ruff version {profile.ruff_version}: the v1 parser "
            f"binds the frozen format {_FROZEN_RUFF_VERSION}",
        )
    closed = _closed_execution_outcome(raw, "RUFF")
    if closed is not None:
        return closed
    text = _decode_stdout(raw)
    if text is None:
        return _error_result(raw, "RUFF", "output is not valid UTF-8")
    return _parse_ruff_text(text, raw)


# Mypy 2.3.0 terminal summary and error-line shapes (observed from the
# frozen tool; CRLF and LF both accepted).
_MYPY_SUCCESS_RE = re.compile(r"^Success: no issues found in \d+ source files?$")
_MYPY_FOUND_RE = re.compile(
    r"^Found (\d+) errors? in (\d+) files? \(checked \d+ source files?\)$"
)
_MYPY_DIAGNOSTIC_RE = re.compile(r"^([^:]+):(\d+): (error|note): (.+)$")


def _parse_mypy_text(text: str, raw: RawExecutionResultV1) -> CheckResultV1:
    text = _normalize_line_endings(text)
    if text == "":
        return _error_result(
            raw, "MYPY", "output is empty: completeness cannot be proven"
        )
    lines = text.split("\n")
    non_empty_indices = [index for index, line in enumerate(lines) if line != ""]
    if not non_empty_indices:
        return _error_result(
            raw, "MYPY", "output is empty: completeness cannot be proven"
        )
    terminal = lines[non_empty_indices[-1]]
    success = _MYPY_SUCCESS_RE.match(terminal)
    if success is not None:
        if raw.exit_code != 0:
            return _error_result(raw, "MYPY", "exit code contradicts clean output")
        return CheckResultV1(
            status="PASS",
            check_kind="MYPY",
            structured_findings=(),
            raw_digest=_raw_evidence_digest(raw),
        )
    found = _MYPY_FOUND_RE.match(terminal)
    if found is None:
        return _error_result(
            raw,
            "MYPY",
            "truncated output: missing the Found N errors in M files summary line",
        )
    expected_errors = int(found.group(1))
    expected_files = int(found.group(2))
    if expected_errors < 1:
        return _error_result(raw, "MYPY", "malformed output: empty error summary")
    errors: list[tuple[str, int, str]] = []
    error_files: set[str] = set()
    for line in lines[: non_empty_indices[-1]]:
        if line == "":
            continue
        diagnostic = _MYPY_DIAGNOSTIC_RE.match(line)
        if diagnostic is None:
            return _error_result(raw, "MYPY", f"unknown diagnostic line: {line!r}")
        path, line_text, category, message = diagnostic.groups()
        if category == "error":
            errors.append((path, int(line_text), message))
            error_files.add(path)
    if len(errors) != expected_errors:
        return _error_result(
            raw,
            "MYPY",
            "error count mismatch: output is truncated or incomplete",
        )
    if len(error_files) != expected_files:
        return _error_result(
            raw,
            "MYPY",
            "file count mismatch: output is truncated or incomplete",
        )
    if raw.exit_code == 0:
        return _error_result(raw, "MYPY", "exit code contradicts findings")
    findings = tuple(
        CheckFindingV1(
            error_code="CHECK_FAILED",
            message=message,
            location=CheckFindingLocationV1(
                path=path,
                line=line,
                column=AbsentV1(kind="ABSENT"),
            ),
        )
        for path, line, message in errors
    )
    return CheckResultV1(
        status="FAIL",
        check_kind="MYPY",
        structured_findings=findings,
        raw_digest=_raw_evidence_digest(raw),
    )


def parse_mypy_result(
    raw: RawExecutionResultV1,
    profile: ReferenceProfileManifestV1,
) -> CheckResultV1:
    """Parse one bounded Mypy execution into the sole closed result."""
    if profile.mypy_version != _FROZEN_MYPY_VERSION:
        return _error_result(
            raw,
            "MYPY",
            f"unsupported mypy version {profile.mypy_version}: the v1 parser "
            f"binds the frozen format {_FROZEN_MYPY_VERSION}",
        )
    closed = _closed_execution_outcome(raw, "MYPY")
    if closed is not None:
        return closed
    text = _decode_stdout(raw)
    if text is None:
        return _error_result(raw, "MYPY", "output is not valid UTF-8")
    return _parse_mypy_text(text, raw)

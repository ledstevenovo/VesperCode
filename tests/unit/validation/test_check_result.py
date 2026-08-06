"""T19.1 legacy step 19.A: closed check-result schema tests.

The unit surface proves ``CheckFindingV1``/``CheckFindingSequenceV1``/
``CheckResultV1`` are immutable, closed (unknown fields and type-confused
spellings reject), and enforce the sole permitted status-to-findings
combination table (PASS and NOT_RUN -> empty; FAIL -> one or more
``CHECK_FAILED`` findings; ERROR and TIMEOUT -> exactly one stable
finding).  The parser-driven closed matrix of the bounded Ruff/Mypy
formats lives in ``test_ruff_mypy_parsing.py``; this module owns the
closed schema matrix of the result/finding value types themselves.
"""

from __future__ import annotations

from typing import cast

import pytest

# The check-result contracts are pydantic runtime models; the hash-locked
# gate toolchain does not install runtime dependencies, so this module
# skips cleanly there instead of failing at collection (formal env runs it
# fully).
pytest.importorskip("pydantic")

from pydantic import ValidationError

from src.vespercode.contracts.optional import AbsentV1, PresentV1
from src.vespercode.validation.check_result import (
    CheckFindingErrorCodeV1,
    CheckFindingLocationV1,
    CheckFindingSequenceV1,
    CheckFindingV1,
    CheckResultV1,
)

_DIGEST = "a" * 64


def _location(
    path: str = "src/vf/calc.py",
    line: int = 4,
    column: int | None = 8,
) -> CheckFindingLocationV1:
    if column is None:
        column_value: AbsentV1 | PresentV1[int] = AbsentV1(kind="ABSENT")
    else:
        column_value = PresentV1(kind="PRESENT", value=column)
    return CheckFindingLocationV1(path=path, line=line, column=column_value)


def _finding(
    error_code: CheckFindingErrorCodeV1 = "CHECK_FAILED",
    message: str = "violation message",
    path: str = "src/vf/calc.py",
    line: int = 4,
    column: int | None = 8,
) -> CheckFindingV1:
    return CheckFindingV1(
        error_code=error_code,
        message=message,
        location=_location(path=path, line=line, column=column),
    )


def _result(
    status: str,
    findings: tuple[CheckFindingV1, ...],
    *,
    check_kind: str = "RUFF",
) -> dict[str, object]:
    return {
        "status": status,
        "check_kind": check_kind,
        "structured_findings": findings,
        "raw_digest": _DIGEST,
    }


def test_permitted_status_finding_combinations_construct() -> None:
    """Every row of the closed combination table constructs exactly."""
    assert CheckResultV1.model_validate(_result("PASS", ())).status == "PASS"
    fail = CheckResultV1.model_validate(
        _result("FAIL", (_finding(), _finding(message="second")))
    )
    assert [item.error_code for item in fail.structured_findings] == [
        "CHECK_FAILED",
        "CHECK_FAILED",
    ]
    error = CheckResultV1.model_validate(
        _result("ERROR", (_finding(error_code="CHECK_ERROR"),))
    )
    assert error.structured_findings[0].error_code == "CHECK_ERROR"
    timeout = CheckResultV1.model_validate(
        _result("TIMEOUT", (_finding(error_code="CHECK_TIMEOUT"),))
    )
    assert timeout.structured_findings[0].error_code == "CHECK_TIMEOUT"
    not_run = CheckResultV1.model_validate(
        _result("NOT_RUN", (), check_kind="TARGET_TESTS")
    )
    assert not_run.structured_findings == ()


def test_forbidden_status_finding_combinations_reject() -> None:
    """Every forbidden combination of the closed table rejects."""
    rejected: list[dict[str, object]] = [
        # PASS and NOT_RUN carry no findings at all.
        _result("PASS", (_finding(),)),
        _result("NOT_RUN", (_finding(error_code="CHECK_NOT_RUN"),)),
        # FAIL requires at least one CHECK_FAILED finding.
        _result("FAIL", ()),
        _result("FAIL", (_finding(error_code="CHECK_ERROR"),)),
        _result("FAIL", (_finding(error_code="CHECK_TIMEOUT"),)),
        _result("FAIL", (_finding(), _finding(error_code="CHECK_ERROR"))),
        # ERROR and TIMEOUT carry exactly one stable finding.
        _result("ERROR", ()),
        _result(
            "ERROR",
            (_finding(error_code="CHECK_ERROR"), _finding(error_code="CHECK_ERROR")),
        ),
        _result("ERROR", (_finding(),)),
        _result("TIMEOUT", ()),
        _result(
            "TIMEOUT",
            (
                _finding(error_code="CHECK_TIMEOUT"),
                _finding(error_code="CHECK_TIMEOUT"),
            ),
        ),
        _result("TIMEOUT", (_finding(error_code="CHECK_ERROR"),)),
    ]
    for payload in rejected:
        with pytest.raises(ValidationError):
            CheckResultV1.model_validate(payload)


def test_check_result_rejects_unknown_or_type_confused_fields() -> None:
    """Unknown fields, bool/float/string coercion, and drift reject."""
    rejected: list[dict[str, object]] = [
        {**_result("PASS", ()), "extra": 1},
        {**_result("PASS", ()), "status": "UNKNOWN"},
        {**_result("PASS", ()), "status": 1},
        {**_result("PASS", ()), "status": "pass"},
        {**_result("PASS", ()), "check_kind": "RUFF_LINT"},
        {**_result("PASS", ()), "check_kind": "ruff"},
        {**_result("PASS", ()), "check_kind": 1},
        {**_result("PASS", ()), "raw_digest": "A" * 64},
        {**_result("PASS", ()), "raw_digest": "a" * 63},
        {**_result("PASS", ()), "raw_digest": "a" * 65},
        {**_result("PASS", ()), "raw_digest": 1},
    ]
    for payload in rejected:
        with pytest.raises(ValidationError):
            CheckResultV1.model_validate(payload)


def test_check_finding_sequence_is_an_immutable_ordered_tuple() -> None:
    """The sequence is a plain tuple: indexable, ordered, immutable."""
    sequence: CheckFindingSequenceV1 = (_finding(), _finding(message="second"))
    assert sequence[0].error_code == "CHECK_FAILED"
    assert sequence[1].message == "second"
    assert CheckFindingSequenceV1() == ()
    with pytest.raises(TypeError):
        sequence[0] = _finding()  # type: ignore[index]
    with pytest.raises(ValidationError):
        sequence[0].message = "changed"


def test_check_finding_location_is_closed() -> None:
    present = _location(path="src/a.py", line=1, column=2)
    assert isinstance(present.column, PresentV1)
    absent = _location(path="src/a.py", line=1, column=None)
    assert isinstance(absent.column, AbsentV1)
    rejected: list[dict[str, object]] = [
        {"path": "", "line": 1, "column": {"kind": "ABSENT"}},
        {"path": "src/a.py", "line": 0, "column": {"kind": "ABSENT"}},
        {"path": "src/a.py", "line": -1, "column": {"kind": "ABSENT"}},
        {"path": "src/a.py", "line": 1, "column": {"kind": "ABSENT"}, "extra": 1},
        {"path": "src/a.py", "line": 1, "column": {"kind": "PRESENT", "value": 0}},
        {"path": "src/a.py", "line": 1, "column": {"kind": "PRESENT", "value": -3}},
        {"path": "src/a.py", "line": "1", "column": {"kind": "ABSENT"}},
        {"path": "src/a.py", "line": True, "column": {"kind": "ABSENT"}},
        {"path": "src/a.py", "line": 1, "column": None},
        {"path": "src/a.py", "line": 1},
    ]
    for payload in rejected:
        with pytest.raises(ValidationError):
            CheckFindingLocationV1.model_validate(payload)


def test_check_finding_rejects_unknown_error_codes() -> None:
    with pytest.raises(ValidationError):
        _finding(error_code=cast(CheckFindingErrorCodeV1, "CHECK_UNKNOWN"))
    with pytest.raises(ValidationError):
        _finding(error_code=cast(CheckFindingErrorCodeV1, "check_error"))

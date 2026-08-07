"""T19.1 legacy step 19.A: bounded Ruff/Mypy parsing into closed results.

``parse_ruff_result``/``parse_mypy_result`` convert one bounded raw
execution evidence into the sole closed ``CheckResultV1`` combinations:
PASS and FAIL come only from complete, profile-frozen output shapes whose
terminal summary line proves completeness; ERROR/TIMEOUT come from
truncated, malformed, version-inconsistent, non-UTF-8, exit-inconsistent,
output-limited, isolation-violated, or execution-failed evidence; NOT_RUN
never leaves the schema (SPEC §4.5: "不能仅按进程退出码判定 PASS").  The
exact displayed RED test proves a truncated Ruff output becomes a closed
``CHECK_ERROR`` result, and the matrix pins every closed combination
against the real Ruff 0.16.1 / Mypy 2.3.0 output shapes.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

# The check-result contracts are pydantic runtime models; the hash-locked
# gate toolchain does not install runtime dependencies, so this module
# skips cleanly there instead of failing at collection (formal env runs it
# fully).
pytest.importorskip("pydantic")

from vespercode.contracts.optional import PresentV1
from vespercode.execution.docker_executor import (
    ExecutionErrorCodeV1,
    RawExecutionResultV1,
)
from vespercode.profiles.reference import (
    ReferenceProfileManifestV1,
    load_reference_profile,
)
from vespercode.validation.check_result import (
    parse_mypy_result,
    parse_ruff_result,
)

# The frozen T02.4 gate-toolchain identities (SPEC §1.4.1) that the v1
# parsers bind their format knowledge to: the parsers accept only the
# profile-frozen tool version whose text format they can prove complete.
_FROZEN_RUFF_VERSION = "0.16.1"
_FROZEN_MYPY_VERSION = "2.3.0"


@pytest.fixture
def reference_profile() -> ReferenceProfileManifestV1:
    """The packaged frozen built-in manifest (T06.2-proven loader)."""
    path = (
        Path(__file__).resolve().parents[3]
        / "src"
        / "vespercode"
        / "profiles"
        / "builtin"
        / "reference-profile-v1.json"
    )
    return load_reference_profile(path.read_bytes())


def _drifted_profile(
    reference_profile: ReferenceProfileManifestV1,
    **overrides: str,
) -> ReferenceProfileManifestV1:
    """One form-valid manifest with a drifted tool version (identity only).

    The drift is the input under test: the v1 parser binds the frozen
    format, so any non-frozen tool version is version-inconsistent output
    support and fails closed before any status can be produced.
    """
    payload = json.loads(
        (
            Path(__file__).resolve().parents[3]
            / "src"
            / "vespercode"
            / "profiles"
            / "builtin"
            / "reference-profile-v1.json"
        ).read_bytes()
    )
    payload.update(overrides)
    return ReferenceProfileManifestV1.model_validate(payload)


def _raw_result(
    *,
    stdout: bytes,
    stderr: bytes = b"",
    exit_code: int | None = 0,
    timed_out: bool = False,
    output_limit_exceeded: bool = False,
    container_stopped: bool = False,
    error_code: ExecutionErrorCodeV1 | None = None,
) -> RawExecutionResultV1:
    return RawExecutionResultV1(
        schema_version=1,
        request_id="req-19-a",
        container_id="c" * 64,
        exit_code=exit_code,
        stdout=stdout,
        stderr=stderr,
        output_bytes=len(stdout) + len(stderr),
        timed_out=timed_out,
        output_limit_exceeded=output_limit_exceeded,
        container_stopped=container_stopped,
        error_code=error_code,
    )


def _ruff_clean() -> bytes:
    return b"All checks passed!\n"


def _ruff_f401_block() -> bytes:
    """The real Ruff 0.16.1 full-format block for one fixable F401."""
    return (
        b"F401 [*] `os` imported but unused\n"
        b" --> src/vf/calc.py:4:8\n"
        b"  |\n"
        b"2 |     return a - b\n"
        b"3 |\n"
        b"4 | import os\n"
        b"  |        ^^\n"
        b"help: Remove unused import: `os`\n"
        b"  |\n"
        b"3 |\n"
        b"  - import os\n"
        b"  |\n"
        b"\n"
    )


def _ruff_f841_block() -> bytes:
    """The real Ruff 0.16.1 block for one non-fixable F841 (no fixes)."""
    return (
        b"F841 Local variable `unused` is assigned to but never used\n"
        b" --> src/vf/calc.py:2:5\n"
        b"  |\n"
        b"1 | def f() -> None:\n"
        b"2 |     unused = 42\n"
        b"  |     ^^^^^^\n"
        b"help: Remove assignment to unused variable `unused`\n"
        b"\n"
    )


def _ruff_two_blocks() -> bytes:
    return (
        _ruff_f401_block()
        + b"I001 [*] Import block is un-sorted or un-formatted\n"
        + b" --> src/vf/other.py:1:1\n"
        + b"  |\n"
        + b"1 | import sys\n"
        + b"  | ^^^^^^^^^^\n"
        + b"  |\n"
        + b"\n"
    )


def _mypy_errors() -> bytes:
    """Real Mypy 2.3.0 error output (CRLF, notes between errors)."""
    return (
        b'src\\vf\\calc.py:2: error: Incompatible return value type (got "str", expected "int")  [return-value]\r\n'
        b'src\\vf\\calc.py:6: error: Incompatible types in assignment (expression has type "str", variable has type "int")  [assignment]\r\n'
        b"src\\vf\\other.py:3: error: Function is missing a return type annotation  [no-untyped-def]\r\n"
        b'src\\vf\\other.py:3: note: Use "-> None" if function does not return a value\r\n'
        b"Found 3 errors in 2 files (checked 2 source files)\r\n"
    )


def _mypy_clean() -> bytes:
    return b"Success: no issues found in 1 source file\r\n"


def truncated_ruff_execution() -> RawExecutionResultV1:
    """One Ruff check whose output was cut mid-block (no terminal summary).

    The block header and location are present but the output never reaches
    the ``Found N errors.`` terminal line, so completeness cannot be
    proven and the parse must fail closed with ``CHECK_ERROR``.
    """
    return _raw_result(
        stdout=(
            b"F401 [*] `os` imported but unused\n"
            b" --> src/vf/calc.py:4:8\n"
            b"  |\n"
            b"4 | import os\n"
        ),
        exit_code=1,
    )


def test_truncated_ruff_output_is_check_error(
    reference_profile: ReferenceProfileManifestV1,
) -> None:
    result = parse_ruff_result(truncated_ruff_execution(), reference_profile)
    assert result.status == "ERROR"
    assert result.structured_findings[0].error_code == "CHECK_ERROR"


def test_clean_ruff_output_is_pass_without_findings(
    reference_profile: ReferenceProfileManifestV1,
) -> None:
    result = parse_ruff_result(
        _raw_result(stdout=_ruff_clean(), exit_code=0), reference_profile
    )
    assert result.status == "PASS"
    assert result.structured_findings == ()


def test_complete_ruff_violations_are_ordered_fail_findings(
    reference_profile: ReferenceProfileManifestV1,
) -> None:
    raw = _raw_result(
        stdout=_ruff_two_blocks()
        + b"Found 2 errors.\n[*] 2 fixable with the `--fix` option.\n",
        exit_code=1,
    )
    result = parse_ruff_result(raw, reference_profile)
    assert result.status == "FAIL"
    findings = result.structured_findings
    assert [finding.error_code for finding in findings] == [
        "CHECK_FAILED",
        "CHECK_FAILED",
    ]
    first = findings[0]
    assert first.message == "`os` imported but unused"
    assert first.location is not None
    assert first.location.path == "src/vf/calc.py"
    assert first.location.line == 4
    column = first.location.column
    assert isinstance(column, PresentV1)
    assert column.value == 8
    assert findings[1].location is not None
    assert findings[1].location.path == "src/vf/other.py"


def test_ruff_failure_without_fix_hint_is_still_fail(
    reference_profile: ReferenceProfileManifestV1,
) -> None:
    raw = _raw_result(
        stdout=_ruff_f841_block() + b"Found 1 error.\n"
        b"No fixes available (1 hidden fix can be enabled with the `--unsafe-fixes` option).\n",
        exit_code=1,
    )
    result = parse_ruff_result(raw, reference_profile)
    assert result.status == "FAIL"
    assert result.structured_findings[0].message == (
        "Local variable `unused` is assigned to but never used"
    )


def test_complete_mypy_errors_are_ordered_fail_findings(
    reference_profile: ReferenceProfileManifestV1,
) -> None:
    result = parse_mypy_result(
        _raw_result(stdout=_mypy_errors(), exit_code=1), reference_profile
    )
    assert result.status == "FAIL"
    findings = result.structured_findings
    assert [finding.error_code for finding in findings] == [
        "CHECK_FAILED",
        "CHECK_FAILED",
        "CHECK_FAILED",
    ]
    assert findings[0].message == (
        'Incompatible return value type (got "str", expected "int")  [return-value]'
    )
    assert findings[0].location is not None
    assert findings[0].location.path == "src\\vf\\calc.py"
    assert findings[0].location.line == 2
    assert findings[0].location.column.kind == "ABSENT"


def test_clean_mypy_output_is_pass(
    reference_profile: ReferenceProfileManifestV1,
) -> None:
    result = parse_mypy_result(
        _raw_result(stdout=_mypy_clean(), exit_code=0), reference_profile
    )
    assert result.status == "PASS"
    assert result.structured_findings == ()


def test_closed_execution_failures_map_to_timeout_and_error(
    reference_profile: ReferenceProfileManifestV1,
) -> None:
    timeout = parse_ruff_result(
        _raw_result(
            stdout=b"",
            exit_code=137,
            timed_out=True,
            container_stopped=True,
            error_code="CHECK_TIMEOUT",
        ),
        reference_profile,
    )
    assert timeout.status == "TIMEOUT"
    assert timeout.structured_findings[0].error_code == "CHECK_TIMEOUT"
    for error_code in (
        "CHECK_OUTPUT_LIMIT_EXCEEDED",
        "CHECK_ISOLATION_VIOLATION",
        "CHECK_EXECUTION_ERROR",
    ):
        raw = _raw_result(
            stdout=b"",
            exit_code=None if error_code != "CHECK_OUTPUT_LIMIT_EXCEEDED" else 137,
            output_limit_exceeded=error_code == "CHECK_OUTPUT_LIMIT_EXCEEDED",
            container_stopped=error_code == "CHECK_OUTPUT_LIMIT_EXCEEDED",
            error_code=error_code,
        )
        for parse in (parse_ruff_result, parse_mypy_result):
            result = parse(raw, reference_profile)
            assert result.status == "ERROR"
            assert result.structured_findings[0].error_code == "CHECK_ERROR"


def test_raw_digest_is_deterministic_canonical_identity(
    reference_profile: ReferenceProfileManifestV1,
) -> None:
    first = parse_ruff_result(
        _raw_result(stdout=_ruff_clean(), exit_code=0), reference_profile
    )
    second = parse_ruff_result(
        _raw_result(stdout=_ruff_clean(), exit_code=0), reference_profile
    )
    assert first.raw_digest == second.raw_digest
    assert len(first.raw_digest) == 64


def test_check_kind_binds_the_parse_owner(
    reference_profile: ReferenceProfileManifestV1,
) -> None:
    assert (
        parse_ruff_result(
            _raw_result(stdout=_ruff_clean(), exit_code=0), reference_profile
        ).check_kind
        == "RUFF"
    )
    assert (
        parse_mypy_result(
            _raw_result(stdout=_mypy_clean(), exit_code=0), reference_profile
        ).check_kind
        == "MYPY"
    )


_MATRIX_CASES: list[
    tuple[str, RawExecutionResultV1, dict[str, str], str, tuple[str, ...]]
] = [
    # Ruff: the frozen 0.16.1 text format.
    ("ruff-clean-pass", _raw_result(stdout=_ruff_clean(), exit_code=0), {}, "PASS", ()),
    (
        "ruff-violations-fail",
        _raw_result(
            stdout=_ruff_f401_block()
            + b"Found 1 error.\n[*] 1 fixable with the `--fix` option.\n",
            exit_code=1,
        ),
        {},
        "FAIL",
        ("CHECK_FAILED",),
    ),
    (
        "ruff-multi-block-fail",
        _raw_result(
            stdout=_ruff_two_blocks()
            + b"Found 2 errors.\n[*] 2 fixable with the `--fix` option.\n",
            exit_code=1,
        ),
        {},
        "FAIL",
        ("CHECK_FAILED", "CHECK_FAILED"),
    ),
    (
        "ruff-empty-output",
        _raw_result(stdout=b"", exit_code=0),
        {},
        "ERROR",
        ("CHECK_ERROR",),
    ),
    ("ruff-truncated", truncated_ruff_execution(), {}, "ERROR", ("CHECK_ERROR",)),
    (
        "ruff-missing-summary",
        _raw_result(stdout=_ruff_f401_block(), exit_code=1),
        {},
        "ERROR",
        ("CHECK_ERROR",),
    ),
    (
        "ruff-count-mismatch",
        _raw_result(stdout=_ruff_f401_block() + b"Found 2 errors.\n", exit_code=1),
        {},
        "ERROR",
        ("CHECK_ERROR",),
    ),
    (
        "ruff-unknown-category",
        _raw_result(
            stdout=b"F401 [*] `os` imported but unused\n  |\nFound 1 error.\n",
            exit_code=1,
        ),
        {},
        "ERROR",
        ("CHECK_ERROR",),
    ),
    (
        "ruff-clean-exit-inconsistent",
        _raw_result(stdout=_ruff_clean(), exit_code=1),
        {},
        "ERROR",
        ("CHECK_ERROR",),
    ),
    (
        "ruff-dirty-exit-inconsistent",
        _raw_result(
            stdout=_ruff_f401_block()
            + b"Found 1 error.\n[*] 1 fixable with the `--fix` option.\n",
            exit_code=0,
        ),
        {},
        "ERROR",
        ("CHECK_ERROR",),
    ),
    (
        "ruff-not-utf8",
        _raw_result(stdout=b"\xff\xfe\x00", exit_code=0),
        {},
        "ERROR",
        ("CHECK_ERROR",),
    ),
    (
        "ruff-timeout",
        _raw_result(
            stdout=b"",
            exit_code=137,
            timed_out=True,
            container_stopped=True,
            error_code="CHECK_TIMEOUT",
        ),
        {},
        "TIMEOUT",
        ("CHECK_TIMEOUT",),
    ),
    (
        "ruff-output-limit",
        _raw_result(
            stdout=b"",
            exit_code=137,
            output_limit_exceeded=True,
            container_stopped=True,
            error_code="CHECK_OUTPUT_LIMIT_EXCEEDED",
        ),
        {},
        "ERROR",
        ("CHECK_ERROR",),
    ),
    (
        "ruff-isolation",
        _raw_result(stdout=b"", exit_code=None, error_code="CHECK_ISOLATION_VIOLATION"),
        {},
        "ERROR",
        ("CHECK_ERROR",),
    ),
    (
        "ruff-execution-error",
        _raw_result(stdout=b"", exit_code=None, error_code="CHECK_EXECUTION_ERROR"),
        {},
        "ERROR",
        ("CHECK_ERROR",),
    ),
    (
        "ruff-version-mismatch",
        _raw_result(stdout=_ruff_clean(), exit_code=0),
        {"ruff_version": "0.99.0"},
        "ERROR",
        ("CHECK_ERROR",),
    ),
    # Mypy: the frozen 2.3.0 text format (CRLF accepted).
    ("mypy-clean-pass", _raw_result(stdout=_mypy_clean(), exit_code=0), {}, "PASS", ()),
    (
        "mypy-errors-fail",
        _raw_result(stdout=_mypy_errors(), exit_code=1),
        {},
        "FAIL",
        ("CHECK_FAILED", "CHECK_FAILED", "CHECK_FAILED"),
    ),
    (
        "mypy-truncated",
        _raw_result(stdout=_mypy_errors().split(b"\r\n")[0] + b"\r\n", exit_code=1),
        {},
        "ERROR",
        ("CHECK_ERROR",),
    ),
    (
        "mypy-unknown-line",
        _raw_result(
            stdout=b"src\\vf\\calc.py:2: warning: unknown  [warn]\r\n"
            b"Found 1 error in 1 file (checked 1 source file)\r\n",
            exit_code=1,
        ),
        {},
        "ERROR",
        ("CHECK_ERROR",),
    ),
    (
        "mypy-count-mismatch",
        _raw_result(
            stdout=b"src\\vf\\calc.py:2: error: broken\r\n"
            b"Found 2 errors in 1 file (checked 1 source file)\r\n",
            exit_code=1,
        ),
        {},
        "ERROR",
        ("CHECK_ERROR",),
    ),
    (
        "mypy-file-count-mismatch",
        _raw_result(
            stdout=b"src\\vf\\calc.py:2: error: broken\r\n"
            b"Found 1 error in 2 files (checked 1 source file)\r\n",
            exit_code=1,
        ),
        {},
        "ERROR",
        ("CHECK_ERROR",),
    ),
    (
        "mypy-exit-inconsistent",
        _raw_result(stdout=_mypy_errors(), exit_code=0),
        {},
        "ERROR",
        ("CHECK_ERROR",),
    ),
    (
        "mypy-clean-exit-inconsistent",
        _raw_result(stdout=_mypy_clean(), exit_code=1),
        {},
        "ERROR",
        ("CHECK_ERROR",),
    ),
    (
        "mypy-not-utf8",
        _raw_result(stdout=b"\xff\xfe\x00", exit_code=0),
        {},
        "ERROR",
        ("CHECK_ERROR",),
    ),
    (
        "mypy-timeout",
        _raw_result(
            stdout=b"",
            exit_code=137,
            timed_out=True,
            container_stopped=True,
            error_code="CHECK_TIMEOUT",
        ),
        {},
        "TIMEOUT",
        ("CHECK_TIMEOUT",),
    ),
    (
        "mypy-output-limit",
        _raw_result(
            stdout=b"",
            exit_code=137,
            output_limit_exceeded=True,
            container_stopped=True,
            error_code="CHECK_OUTPUT_LIMIT_EXCEEDED",
        ),
        {},
        "ERROR",
        ("CHECK_ERROR",),
    ),
    (
        "mypy-isolation",
        _raw_result(stdout=b"", exit_code=None, error_code="CHECK_ISOLATION_VIOLATION"),
        {},
        "ERROR",
        ("CHECK_ERROR",),
    ),
    (
        "mypy-execution-error",
        _raw_result(stdout=b"", exit_code=None, error_code="CHECK_EXECUTION_ERROR"),
        {},
        "ERROR",
        ("CHECK_ERROR",),
    ),
    (
        "mypy-version-mismatch",
        _raw_result(stdout=_mypy_clean(), exit_code=0),
        {"mypy_version": "2.99.0"},
        "ERROR",
        ("CHECK_ERROR",),
    ),
]


@pytest.mark.parametrize(
    "case_id, raw, profile_override, expected_status, expected_codes",
    _MATRIX_CASES,
)
def test_static_tool_result_parsing_matrix(
    case_id: str,
    raw: RawExecutionResultV1,
    profile_override: dict[str, str],
    expected_status: str,
    expected_codes: tuple[str, ...],
    reference_profile: ReferenceProfileManifestV1,
) -> None:
    """Every closed status/finding combination of both frozen formats."""
    profile = (
        _drifted_profile(reference_profile, **profile_override)
        if profile_override
        else reference_profile
    )
    if case_id.startswith("mypy"):
        result = parse_mypy_result(raw, profile)
    else:
        result = parse_ruff_result(raw, profile)
    assert result.status == expected_status
    assert (
        tuple(finding.error_code for finding in result.structured_findings)
        == expected_codes
    )
    assert len(result.raw_digest) == 64

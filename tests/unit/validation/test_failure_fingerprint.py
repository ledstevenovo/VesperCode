"""T19.1 legacy step 19.C: stable target failure fingerprint tests.

``build_failure_fingerprint`` produces a stable ``FailureFingerprintV1``
only for one complete exact target ``CALL``/``FAIL`` from authoritative
``PytestEvidenceV1``; the allowlisted volatility (execution root, temp
root, run/container id) is replaced with fixed placeholders while user
numbers, times, hexadecimal text, and assertion content are preserved
(SPEC §4.5).  The exact displayed RED test proves user hexadecimal text
survives normalization, and the stability matrix pins the deterministic
STABLE and NOT_FINGERPRINTABLE rows.
"""

from __future__ import annotations

import hashlib
import json

import pytest

# The fingerprint contracts are pydantic runtime models; the hash-locked
# gate toolchain does not install runtime dependencies, so this module
# skips cleanly there instead of failing at collection (formal env runs it
# fully).
pytest.importorskip("pydantic")

from vespercode.contracts.optional import PresentV1
from vespercode.validation.failure_fingerprint import (
    FingerprintNormalizationContextV1,
    build_failure_fingerprint,
)
from vespercode.validation.pytest_evidence import PytestEventV1, PytestEvidenceV1

_TARGET = "tests/test_a.py::test_value"
_EXECUTION_ROOT = "C:/Users/runner/vesper-exec-19"
_TMP_ROOT = "C:/Users/runner/AppData/Local/Temp"
_RUN_ID = "run-19abc"
_CONTAINER_ID = "c" * 64


def _absent() -> dict[str, str]:
    return {"kind": "ABSENT"}


def _present_text(value: str) -> dict[str, object]:
    return {"kind": "PRESENT", "value": value}


def _event(
    sequence: int,
    event_type: str,
    **fields: object,
) -> dict[str, object]:
    event: dict[str, object] = {"sequence": sequence, "event_type": event_type}
    for name in (
        "node_id",
        "phase",
        "outcome",
        "wasxfail",
        "exception",
        "display_summary",
    ):
        event[name] = fields.pop(name, _absent())
    if fields:
        raise AssertionError(f"unknown event field: {sorted(fields)}")
    return event


def _exception(
    exception_type: str = "AssertionError",
    normalized_message: str = "assert 0xdeadbeef == 1",
    assertion_diff: str
    | None = "assert 0xdeadbeef == 1\n +  where 0xdeadbeef = value()",
    frames: tuple[tuple[str, str, int], ...] = (("tests/test_a.py", "test_value", 7),),
) -> dict[str, object]:
    return {
        "exception_type": exception_type,
        "normalized_message": normalized_message,
        "normalized_assertion_diff": (
            _present_text(assertion_diff) if assertion_diff is not None else _absent()
        ),
        "project_frames": [
            {
                "relative_path": relative_path,
                "function_name": function_name,
                "line_number": line_number,
            }
            for relative_path, function_name, line_number in frames
        ],
    }


def _report_digest(report: dict[str, object]) -> str:
    body = {key: value for key, value in report.items() if key != "integrity_digest"}
    prefix = b"VesperCode\x00PytestEvidenceV1\x001\x00"
    return hashlib.sha256(
        prefix
        + json.dumps(
            body, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
    ).hexdigest()


def _evidence_dict(
    *,
    normalized_message: str = "assert 0xdeadbeef == 1",
    exception_type: str = "AssertionError",
    assertion_diff: str
    | None = "assert 0xdeadbeef == 1\n +  where 0xdeadbeef = value()",
    frames: tuple[tuple[str, str, int], ...] = (("tests/test_a.py", "test_value", 7),),
    target_outcome: str = "FAIL",
    target_phase: str = "CALL",
    events: list[dict[str, object]] | None = None,
    pytest_exit_code: int = 1,
) -> dict[str, object]:
    if events is None:
        exception_field: dict[str, object]
        if target_outcome in ("FAIL", "ERROR"):
            exception_field = {
                "kind": "PRESENT",
                "value": _exception(
                    exception_type=exception_type,
                    normalized_message=normalized_message,
                    assertion_diff=assertion_diff,
                    frames=frames,
                ),
            }
        else:
            exception_field = {"kind": "ABSENT"}
        events = [
            _event(1, "SESSION_START"),
            _event(2, "COLLECTION_ITEM", node_id=_present_text(_TARGET)),
            _event(
                3,
                "TEST_PHASE",
                node_id=_present_text(_TARGET),
                phase=_present_text(target_phase),
                outcome=_present_text(target_outcome),
                exception=exception_field,
            ),
            _event(4, "SESSION_END"),
        ]
    report: dict[str, object] = {
        "schema_version": 1,
        "report_plugin_version": "1",
        "run_kind": "FULL_PYTEST",
        "planned_node_ids": [_TARGET],
        "collected_node_ids": [_TARGET],
        "events": events,
        "pytest_exit_code": pytest_exit_code,
        "event_count": len(events),
        "normal_end_marker": True,
        "integrity_digest": "0" * 64,
    }
    report["integrity_digest"] = _report_digest(report)
    return report


def _evidence(
    *,
    normalized_message: str = "assert 0xdeadbeef == 1",
    exception_type: str = "AssertionError",
    assertion_diff: str | None = (
        "assert 0xdeadbeef == 1\n +  where 0xdeadbeef = value()"
    ),
    frames: tuple[tuple[str, str, int], ...] = (("tests/test_a.py", "test_value", 7),),
    target_outcome: str = "FAIL",
    target_phase: str = "CALL",
    events: list[dict[str, object]] | None = None,
    pytest_exit_code: int = 1,
) -> PytestEvidenceV1:
    return PytestEvidenceV1.model_validate(
        _evidence_dict(
            normalized_message=normalized_message,
            exception_type=exception_type,
            assertion_diff=assertion_diff,
            frames=frames,
            target_outcome=target_outcome,
            target_phase=target_phase,
            events=events,
            pytest_exit_code=pytest_exit_code,
        )
    )


@pytest.fixture
def failing_evidence() -> PytestEvidenceV1:
    """One complete CALL/FAIL evidence whose message carries user hex."""
    return _evidence()


def normalization_context() -> FingerprintNormalizationContextV1:
    return FingerprintNormalizationContextV1(
        schema_version=1,
        execution_root=_EXECUTION_ROOT,
        tmp_root=_TMP_ROOT,
        run_id=_RUN_ID,
        container_id=_CONTAINER_ID,
    )


def test_duplicate_call_events_are_not_fingerprintable() -> None:
    # A rerun/divergent report with two CALL events for the target node
    # is not fingerprintable: the first event alone would hide the
    # divergence.  The evidence is constructed past the model validators
    # (which already ban duplicate CALLs) so the fingerprint boundary's
    # own exactly-one gate is exercised directly.
    events = [
        _event(1, "SESSION_START"),
        _event(2, "COLLECTION_ITEM", node_id=_present_text(_TARGET)),
        _event(
            3,
            "TEST_PHASE",
            node_id=_present_text(_TARGET),
            phase=_present_text("CALL"),
            outcome=_present_text("FAIL"),
            exception={
                "kind": "PRESENT",
                "value": _exception(),
            },
        ),
        _event(
            4,
            "TEST_PHASE",
            node_id=_present_text(_TARGET),
            phase=_present_text("CALL"),
            outcome=_present_text("FAIL"),
            exception={
                "kind": "PRESENT",
                "value": _exception(),
            },
        ),
        _event(5, "SESSION_END"),
    ]
    document = _evidence_dict(events=events)
    # The evidence is assembled past the bundle validator (which bans the
    # duplicate CALL) but the events themselves are real validated values,
    # so the fingerprint boundary operates on typed events.
    document["events"] = tuple(PytestEventV1.model_validate(event) for event in events)
    evidence = PytestEvidenceV1.model_construct(**document)
    outcome = build_failure_fingerprint(evidence, _TARGET, normalization_context())
    assert outcome.kind == "NOT_FINGERPRINTABLE"
    assert outcome.error_code == "TARGET_NOT_REPRODUCED"


def test_user_hexadecimal_value_is_not_normalized_away(
    failing_evidence: PytestEvidenceV1,
) -> None:
    outcome = build_failure_fingerprint(
        failing_evidence, "tests/test_a.py::test_value", normalization_context()
    )
    assert outcome.kind == "STABLE"
    assert "deadbeef" in outcome.normalized_exception_text


def test_complete_call_fail_produces_deterministic_fingerprint(
    failing_evidence: PytestEvidenceV1,
) -> None:
    first = build_failure_fingerprint(
        failing_evidence, _TARGET, normalization_context()
    )
    second = build_failure_fingerprint(
        failing_evidence, _TARGET, normalization_context()
    )
    assert first.kind == "STABLE"
    assert second.kind == "STABLE"
    assert first.fingerprint is not None
    assert second.fingerprint is not None
    assert first.fingerprint.digest == second.fingerprint.digest
    assert first.fingerprint.node_id == _TARGET
    assert first.fingerprint.failure_phase == "CALL"
    assert first.fingerprint.exception_type == "AssertionError"
    assert first.fingerprint.project_frame_signatures[0].relative_path.value == (
        "tests/test_a.py"
    )
    assert first.fingerprint.project_frame_signatures[0].line_number == 7


def test_allowlisted_volatility_is_normalized_away(
    failing_evidence: PytestEvidenceV1,
) -> None:
    """Two runs whose volatile values differ fingerprint identically."""
    other_context = FingerprintNormalizationContextV1(
        schema_version=1,
        execution_root="D:/other/exec-root-2",
        tmp_root="D:/other/tmp-2",
        run_id="run-xyz789",
        container_id="d" * 64,
    )
    first_message = f"assert {_EXECUTION_ROOT}/run/{_RUN_ID} == 1"
    second_message = "assert D:/other/exec-root-2/run/run-xyz789 == 1"
    first = build_failure_fingerprint(
        _evidence(
            normalized_message=first_message,
            assertion_diff=first_message,
        ),
        _TARGET,
        normalization_context(),
    )
    second = build_failure_fingerprint(
        _evidence(
            normalized_message=second_message,
            assertion_diff=second_message,
        ),
        _TARGET,
        other_context,
    )
    assert first.kind == "STABLE"
    assert second.kind == "STABLE"
    assert first.fingerprint is not None
    assert second.fingerprint is not None
    assert first.fingerprint.digest == second.fingerprint.digest
    assert "vesper-exec-19" not in first.normalized_exception_text
    assert "run-19abc" not in first.normalized_exception_text
    assert "<EXECUTION_ROOT>" in first.normalized_exception_text
    assert "<RUN_ID>" in first.normalized_exception_text


def test_assertion_diff_is_preserved_in_fingerprint_content(
    failing_evidence: PytestEvidenceV1,
) -> None:
    outcome = build_failure_fingerprint(
        failing_evidence, _TARGET, normalization_context()
    )
    assert outcome.kind == "STABLE"
    assert outcome.fingerprint is not None
    diff = outcome.fingerprint.normalized_assertion_diff
    assert isinstance(diff, PresentV1) and diff.kind == "PRESENT"
    assert "where 0xdeadbeef = value()" in diff.value


_MATRIX_CASES: list[tuple[str, dict[str, object], str, str | None, str]] = []


def _matrix_case(
    case_id: str,
    evidence: dict[str, object],
    node_id: str,
    expected_kind: str | None,
    expected_error_code: str,
) -> None:
    _MATRIX_CASES.append(
        (case_id, evidence, node_id, expected_kind, expected_error_code)
    )


# Stable complete CALL/FAIL rows.
_matrix_case(
    "stable-complete-call-fail",
    _evidence_dict(),
    _TARGET,
    "STABLE",
    "",
)
_plain_lf = _evidence_dict(
    normalized_message="assert 0xdeadbeef == 1\r\nsecond line",
    assertion_diff="assert 0xdeadbeef == 1\r\nsecond line",
)
_matrix_case(
    "stable-lf-unified",
    _plain_lf,
    _TARGET,
    "STABLE",
    "",
)
_matrix_case(
    "stable-non-assertion-exception",
    _evidence_dict(
        exception_type="ValueError",
        normalized_message="invalid value: 3.14159 at 12:34:56",
        assertion_diff=None,
    ),
    _TARGET,
    "STABLE",
    "",
)
_matrix_case(
    "stable-windows-root-variants",
    _evidence_dict(
        normalized_message=(
            f"assert {_EXECUTION_ROOT.replace('/', chr(92))} == 1\n"
            f" +  where tmp = {_TMP_ROOT.replace('/', chr(92))}"
        ),
        assertion_diff=(
            f"assert {_EXECUTION_ROOT.replace('/', chr(92))} == 1\n"
            f" +  where tmp = {_TMP_ROOT.replace('/', chr(92))}"
        ),
    ),
    _TARGET,
    "STABLE",
    "",
)
# Target gating rows.
_matrix_case(
    "target-node-not-found",
    _evidence_dict(
        events=[
            _event(1, "SESSION_START"),
            _event(2, "COLLECTION_ITEM", node_id=_present_text(_TARGET)),
            _event(3, "SESSION_END"),
        ],
        pytest_exit_code=0,
    ),
    _TARGET,
    "NOT_FINGERPRINTABLE",
    "TARGET_NOT_FOUND",
)
_matrix_case(
    "target-call-pass",
    _evidence_dict(target_outcome="PASS", pytest_exit_code=0),
    _TARGET,
    "NOT_FINGERPRINTABLE",
    "TARGET_NOT_REPRODUCED",
)
_matrix_case(
    "target-setup-error",
    _evidence_dict(
        target_phase="SETUP",
        target_outcome="ERROR",
        exception_type="RuntimeError",
        normalized_message="setup boom",
        assertion_diff=None,
    ),
    _TARGET,
    "NOT_FINGERPRINTABLE",
    "TARGET_NOT_REPRODUCED",
)
_matrix_case(
    "target-teardown-error",
    _evidence_dict(
        target_phase="TEARDOWN",
        target_outcome="ERROR",
        exception_type="RuntimeError",
        normalized_message="teardown boom",
        assertion_diff=None,
    ),
    _TARGET,
    "NOT_FINGERPRINTABLE",
    "TARGET_NOT_REPRODUCED",
)
_matrix_case(
    "target-environment-error",
    _evidence_dict(
        target_phase="ENVIRONMENT",
        target_outcome="ERROR",
        exception_type="RuntimeError",
        normalized_message="env boom",
        assertion_diff=None,
    ),
    _TARGET,
    "NOT_FINGERPRINTABLE",
    "TARGET_NOT_REPRODUCED",
)
# Exception evidence rows.
_matrix_case(
    "assertion-without-diff",
    _evidence_dict(
        exception_type="AssertionError",
        normalized_message="assert x",
        assertion_diff=None,
    ),
    _TARGET,
    "NOT_FINGERPRINTABLE",
    "TARGET_NOT_REPRODUCED",
)
_matrix_case(
    "non-assertion-with-diff",
    _evidence_dict(
        exception_type="ValueError",
        normalized_message="boom",
        assertion_diff="boom",
    ),
    _TARGET,
    "NOT_FINGERPRINTABLE",
    "TARGET_NOT_REPRODUCED",
)


@pytest.mark.parametrize(
    "case_id, evidence_dict, node_id, expected_kind, expected_error_code",
    _MATRIX_CASES,
)
def test_failure_fingerprint_stability_matrix(
    case_id: str,
    evidence_dict: dict[str, object],
    node_id: str,
    expected_kind: str | None,
    expected_error_code: str,
) -> None:
    """Every closed STABLE and NOT_FINGERPRINTABLE row."""
    evidence = PytestEvidenceV1.model_validate(evidence_dict)
    outcome = build_failure_fingerprint(evidence, node_id, normalization_context())
    assert outcome.kind == expected_kind, case_id
    if expected_kind == "STABLE":
        assert outcome.fingerprint is not None, case_id
        assert outcome.error_code is None, case_id
        assert len(outcome.fingerprint.digest) == 64, case_id
    else:
        assert outcome.fingerprint is None, case_id
        assert outcome.error_code == expected_error_code, case_id


def test_user_content_change_destabilizes_the_fingerprint() -> None:
    """User body changes must change the fingerprint (SPEC §4.5 rule 4)."""
    first = build_failure_fingerprint(_evidence(), _TARGET, normalization_context())
    second = build_failure_fingerprint(
        _evidence(normalized_message="assert 0xdeadbeef == 2"),
        _TARGET,
        normalization_context(),
    )
    assert first.kind == "STABLE"
    assert second.kind == "STABLE"
    assert first.fingerprint is not None
    assert second.fingerprint is not None
    assert first.fingerprint.digest != second.fingerprint.digest


def test_user_numbers_and_times_are_preserved() -> None:
    evidence = _evidence(
        exception_type="ValueError",
        normalized_message="got 42 items at 12:34:56 (3.14159s)",
        assertion_diff=None,
    )
    outcome = build_failure_fingerprint(evidence, _TARGET, normalization_context())
    assert outcome.kind == "STABLE"
    assert "12:34:56" in outcome.normalized_exception_text
    assert "3.14159" in outcome.normalized_exception_text
    assert "42" in outcome.normalized_exception_text


def test_unmarked_address_style_hex_is_user_content() -> None:
    """Any remaining hex in reporter-normalized text is user content."""
    evidence = _evidence(
        exception_type="AssertionError",
        normalized_message="assert 0xdeadbeef == 0x1234abcd",
        assertion_diff="assert 0xdeadbeef == 0x1234abcd",
    )
    outcome = build_failure_fingerprint(evidence, _TARGET, normalization_context())
    assert outcome.kind == "STABLE"
    assert "0xdeadbeef" in outcome.normalized_exception_text
    assert "0x1234abcd" in outcome.normalized_exception_text

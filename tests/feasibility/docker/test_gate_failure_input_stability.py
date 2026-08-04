"""T02.4 step 2.F: gate failure input stability probe.

Two independent target-failure runs must produce byte-identical normalized
gate fingerprint inputs; ``compare_failure_inputs`` binds node id, phase,
outcome, normalized message, and canonical location so any semantic input
difference compares unequal.
"""

from __future__ import annotations

import dataclasses
import tempfile
from pathlib import Path

import pytest

from spikes.docker_reference_boundary.failure_fingerprint_probe import (
    GateFailureFingerprintInputV1,
    compare_failure_inputs,
    normalize_call_fail_input,
)
from spikes.docker_reference_boundary.pytest_reporter import (
    GatePytestEventV1,
    GatePytestReportV1,
    build_gate_pytest_report,
    run_gate_pytest,
    validate_gate_pytest_report,
)

_NODE_ADDRESS = "tests/test_calculator.py::test_address_is_normalized"


def _seed_project(tmp: Path) -> Path:
    """One deterministic mini-project whose failure message embeds a runtime
    object address that differs between independent runs."""
    project = tmp / "project"
    (project / "src" / "vesper_fixture").mkdir(parents=True)
    (project / "tests").mkdir(parents=True)
    (project / "conftest.py").write_text(
        "import os, sys\n"
        "sys.path.insert(0, os.path.join("
        "os.path.dirname(os.path.abspath(__file__)), 'src'))\n",
        encoding="utf-8",
    )
    (project / "src" / "vesper_fixture" / "calculator.py").write_text(
        "def add(left, right):\n"
        "    return left - right\n"
        "def multiply(left, right):\n"
        "    return left * right\n",
        encoding="utf-8",
    )
    (project / "tests" / "test_calculator.py").write_text(
        "def test_address_is_normalized() -> None:\n"
        "    obj = object()\n"
        "    assert obj is None\n",
        encoding="utf-8",
    )
    return project


def _capture_input() -> GateFailureFingerprintInputV1:
    """One independent target-failure run at a fresh execution-copy root."""
    with tempfile.TemporaryDirectory(prefix="vesper-fingerprint-") as tmp:
        root = _seed_project(Path(tmp))
        report = run_gate_pytest(
            root, (_NODE_ADDRESS,), target_node_ids=(_NODE_ADDRESS,)
        )
        assert validate_gate_pytest_report(report).passed is True
        return normalize_call_fail_input(report, _NODE_ADDRESS)


def first_failure_input() -> GateFailureFingerprintInputV1:
    return _capture_input()


def second_failure_input() -> GateFailureFingerprintInputV1:
    return _capture_input()


def test_independent_target_failures_have_identical_inputs() -> None:
    comparison = compare_failure_inputs(first_failure_input(), second_failure_input())
    assert comparison.equal is True
    assert comparison.left_digest == comparison.right_digest


def _fail_event(
    sequence: int,
    *,
    message: str,
    node_id: str = _NODE_ADDRESS,
    relative_path: str = "tests/test_calculator.py",
    function_name: str = "test_address_is_normalized",
    line_number: int = 3,
) -> GatePytestEventV1:
    return GatePytestEventV1(
        sequence=sequence,
        event_type="TEST_PHASE",
        node_id=node_id,
        phase="CALL",
        outcome="FAIL",
        exception_type="AssertionError",
        normalized_message=message,
        relative_path=relative_path,
        function_name=function_name,
        line_number=line_number,
    )


def _synthetic_report(
    message: str,
    *,
    node_id: str = _NODE_ADDRESS,
    relative_path: str = "tests/test_calculator.py",
    function_name: str = "test_address_is_normalized",
    line_number: int = 3,
) -> GatePytestReportV1:
    events = (
        GatePytestEventV1(sequence=1, event_type="SESSION_START"),
        GatePytestEventV1(sequence=2, event_type="COLLECTION_ITEM", node_id=node_id),
        _fail_event(
            3,
            message=message,
            node_id=node_id,
            relative_path=relative_path,
            function_name=function_name,
            line_number=line_number,
        ),
        GatePytestEventV1(sequence=4, event_type="SESSION_END"),
    )
    return build_gate_pytest_report(
        planned_node_ids=(node_id,),
        collected_node_ids=(node_id,),
        events=events,
        normal_end=True,
        exit_code=1,
    )


def _synthetic_input(
    message: str,
    *,
    node_id: str = _NODE_ADDRESS,
    relative_path: str = "tests/test_calculator.py",
    function_name: str = "test_address_is_normalized",
    line_number: int = 3,
) -> GateFailureFingerprintInputV1:
    return normalize_call_fail_input(
        _synthetic_report(
            message,
            node_id=node_id,
            relative_path=relative_path,
            function_name=function_name,
            line_number=line_number,
        ),
        node_id,
    )


def test_address_differences_compare_equal_after_normalization() -> None:
    first = _synthetic_input("assert <object object at 0x000002C814A9E080> is None")
    second = _synthetic_input("assert <object object at 0x0000024755E5E080> is None")
    assert first.normalized_message == "assert <object object at <ADDRESS>> is None"
    comparison = compare_failure_inputs(first, second)
    assert comparison.equal is True
    assert comparison.left_digest == comparison.right_digest


def test_normalization_unifies_line_endings_and_temp_root() -> None:
    tmp_root = tempfile.gettempdir()
    message = (
        "assert 0 == 4\r\n"
        f" +  where 0 = add(2, 2, root={tmp_root})\r\n"
        "error at 0x0000024755E5E080"
    )
    normalized = normalize_call_fail_input(_synthetic_report(message), _NODE_ADDRESS)
    assert normalized.normalized_message == (
        "assert 0 == 4\n +  where 0 = add(2, 2, root=<TMP_ROOT>)\nerror at <ADDRESS>"
    )


def test_normalization_is_deterministic() -> None:
    first = _synthetic_input("assert 0 == 4")
    second = _synthetic_input("assert 0 == 4")
    comparison = compare_failure_inputs(first, second)
    assert comparison.equal is True
    assert comparison.left_digest == comparison.right_digest
    assert compare_failure_inputs(first, first).equal is True


def test_normalized_input_is_immutable() -> None:
    normalized = _synthetic_input("assert 0 == 4")
    with pytest.raises(dataclasses.FrozenInstanceError):
        normalized.node_id = "changed"  # type: ignore[misc]
    with pytest.raises(dataclasses.FrozenInstanceError):
        normalized.location.line_number = 9  # type: ignore[misc]
    with pytest.raises(dataclasses.FrozenInstanceError):
        normalized.normalized_message = "changed"  # type: ignore[misc]


def test_every_semantic_difference_compares_unequal() -> None:
    base = _synthetic_input("assert 0 == 4")
    differences = [
        _synthetic_input("assert 0 == 5"),
        _synthetic_input("assert 0 == 4", node_id="tests/other.py::test_x"),
        _synthetic_input(
            "assert 0 == 4", relative_path="src/vesper_fixture/calculator.py"
        ),
        _synthetic_input("assert 0 == 4", function_name="other_function"),
        _synthetic_input("assert 0 == 4", line_number=12),
    ]
    for other in differences:
        comparison = compare_failure_inputs(base, other)
        assert comparison.equal is False
        assert comparison.left_digest != comparison.right_digest
    # The closed phase/outcome binding: a non-FAIL phase never normalizes.
    with pytest.raises(ValueError, match="no CALL/FAIL event"):
        normalize_call_fail_input(
            _synthetic_report("assert 0 == 4"), "tests/other.py::test_x"
        )


def test_normalize_rejects_call_fail_without_structured_exception() -> None:
    report = _synthetic_report("assert 0 == 4")
    stripped = dataclasses.replace(
        next(event for event in report.events if event.event_type == "TEST_PHASE"),
        normalized_message=None,
        relative_path=None,
        function_name=None,
        line_number=None,
    )
    events = tuple(
        stripped if event.event_type == "TEST_PHASE" else event
        for event in report.events
    )
    malformed = build_gate_pytest_report(
        report.planned_node_ids,
        report.collected_node_ids,
        events,
        normal_end=True,
        exit_code=1,
    )
    with pytest.raises(ValueError, match="structured exception"):
        normalize_call_fail_input(malformed, _NODE_ADDRESS)


def test_normalize_requires_explicit_call_fail_event() -> None:
    setup_error_events = (
        GatePytestEventV1(sequence=1, event_type="SESSION_START"),
        GatePytestEventV1(
            sequence=2, event_type="COLLECTION_ITEM", node_id=_NODE_ADDRESS
        ),
        GatePytestEventV1(
            sequence=3,
            event_type="TEST_PHASE",
            node_id=_NODE_ADDRESS,
            phase="SETUP",
            outcome="ERROR",
            exception_type="RuntimeError",
            normalized_message="fixture exploded",
            relative_path="tests/test_calculator.py",
            function_name="test_address_is_normalized",
            line_number=2,
        ),
        GatePytestEventV1(sequence=4, event_type="SESSION_END"),
    )
    setup_error_report = build_gate_pytest_report(
        planned_node_ids=(_NODE_ADDRESS,),
        collected_node_ids=(_NODE_ADDRESS,),
        events=setup_error_events,
        normal_end=True,
        exit_code=1,
    )
    with pytest.raises(ValueError, match="no CALL/FAIL event"):
        normalize_call_fail_input(setup_error_report, _NODE_ADDRESS)

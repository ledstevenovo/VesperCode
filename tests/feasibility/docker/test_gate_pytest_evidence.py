"""T02.4 step 2.E: authoritative gate pytest evidence.

The explicit gate reporter captures one pytest lifecycle as an immutable
ordered event sequence; ``validate_gate_pytest_report`` fails closed on
missing, truncated, duplicate, implicit, or mismatched lifecycle evidence
with one stable rejection reason, and only a complete explicit report passes.
"""

from __future__ import annotations

import dataclasses
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from spikes.docker_reference_boundary import pytest_reporter
from spikes.docker_reference_boundary.pytest_reporter import (
    GatePytestEventV1,
    GatePytestReportV1,
    GatePytestEventSequenceV1,
    build_gate_pytest_report,
    load_gate_pytest_report,
    run_gate_pytest,
    validate_gate_pytest_report,
)

_NODE_ADD = "tests/test_calculator.py::test_add_returns_sum"
_NODE_MULTIPLY = "tests/test_calculator.py::test_multiply_returns_product"
_PLANNED = (_NODE_ADD, _NODE_MULTIPLY)


def _event(
    sequence: int,
    event_type: str,
    **fields: object,
) -> GatePytestEventV1:
    return GatePytestEventV1(
        sequence=sequence,
        event_type=event_type,  # type: ignore[arg-type]
        **fields,  # type: ignore[arg-type]
    )


def _complete_events() -> GatePytestEventSequenceV1:
    return (
        _event(1, "SESSION_START"),
        _event(2, "COLLECTION_ITEM", node_id=_NODE_ADD),
        _event(3, "COLLECTION_ITEM", node_id=_NODE_MULTIPLY),
        _event(
            4,
            "TEST_PHASE",
            node_id=_NODE_ADD,
            phase="CALL",
            outcome="FAIL",
            exception_type="AssertionError",
            normalized_message="assert 0 == 4",
            relative_path="tests/test_calculator.py",
            function_name="test_add_returns_sum",
            line_number=6,
        ),
        _event(
            5,
            "TEST_PHASE",
            node_id=_NODE_MULTIPLY,
            phase="CALL",
            outcome="PASS",
        ),
        _event(6, "SESSION_END"),
    )


def complete_gate_report() -> GatePytestReportV1:
    return build_gate_pytest_report(
        planned_node_ids=_PLANNED,
        collected_node_ids=_PLANNED,
        events=_complete_events(),
        normal_end=True,
        exit_code=1,
    )


def report_without_teardown() -> GatePytestReportV1:
    """One complete-looking lifecycle that never emits SESSION_END."""
    return build_gate_pytest_report(
        planned_node_ids=_PLANNED,
        collected_node_ids=_PLANNED,
        events=_complete_events()[:-1],
        normal_end=False,
        exit_code=1,
    )


def test_missing_teardown_event_invalidates_gate_report() -> None:
    assert validate_gate_pytest_report(report_without_teardown()).passed is False


def test_complete_explicit_report_passes() -> None:
    result = validate_gate_pytest_report(complete_gate_report())
    assert result.passed is True
    assert result.reason == pytest_reporter.REASON_COMPLETE


def test_gate_report_and_events_are_immutable() -> None:
    report = complete_gate_report()
    with pytest.raises(dataclasses.FrozenInstanceError):
        report.exit_code = 0  # type: ignore[misc]
    with pytest.raises(dataclasses.FrozenInstanceError):
        report.events[0].sequence = 99  # type: ignore[misc]
    with pytest.raises(dataclasses.FrozenInstanceError):
        report.planned_node_ids += (_NODE_ADD,)  # type: ignore[misc]
    with pytest.raises(dataclasses.FrozenInstanceError):
        report.events += report.events  # type: ignore[misc]
    with pytest.raises(TypeError):
        report.planned_node_ids[0] = "changed"  # type: ignore[index]


def _mutated_report(
    events: GatePytestEventSequenceV1,
    *,
    collected: tuple[str, ...] = _PLANNED,
    planned: tuple[str, ...] = _PLANNED,
    normal_end: bool = True,
    exit_code: int = 1,
) -> GatePytestReportV1:
    return build_gate_pytest_report(
        planned_node_ids=planned,
        collected_node_ids=collected,
        events=events,
        normal_end=normal_end,
        exit_code=exit_code,
    )


def _replaced(
    events: GatePytestEventSequenceV1,
    index: int,
    **fields: object,
) -> GatePytestEventSequenceV1:
    updated = tuple(
        dataclasses.replace(events[index], **fields)  # type: ignore[arg-type]
        if i == index
        else event
        for i, event in enumerate(events)
    )
    return updated


def _renumbered(events: GatePytestEventSequenceV1) -> GatePytestEventSequenceV1:
    """Renumber a raw event tuple to continuous sequences 1..n."""
    return tuple(
        _event(
            index + 1,
            event.event_type,
            **{
                name: getattr(event, name)
                for name in (
                    "node_id",
                    "phase",
                    "outcome",
                    "wasxfail",
                    "exception_type",
                    "normalized_message",
                    "relative_path",
                    "function_name",
                    "line_number",
                )
            },
        )
        for index, event in enumerate(events)
    )


def _fail_event(sequence: int) -> GatePytestEventV1:
    return _event(
        sequence,
        "TEST_PHASE",
        node_id=_NODE_ADD,
        phase="CALL",
        outcome="FAIL",
        exception_type="AssertionError",
        normalized_message="assert 0 == 4",
        relative_path="tests/test_calculator.py",
        function_name="test_add_returns_sum",
        line_number=6,
    )


def test_reporter_rejection_matrix() -> None:
    """Every missing, truncated, duplicate, implicit, or mismatched form of
    lifecycle evidence fails closed with its stable reason."""
    cases: list[tuple[str, GatePytestReportV1]] = [
        # Truncated lifecycle: no end marker at all.
        (
            pytest_reporter.REASON_END,
            _mutated_report(_complete_events()[:-1], normal_end=False),
        ),
        # End marker present but the report claims it did not end normally.
        (
            pytest_reporter.REASON_NORMAL_END,
            _mutated_report(_complete_events(), normal_end=False),
        ),
        # Missing session start.
        (
            pytest_reporter.REASON_START,
            _mutated_report(
                _renumbered(
                    (
                        _event(0, "COLLECTION_ITEM", node_id=_NODE_ADD),
                        _event(0, "COLLECTION_ITEM", node_id=_NODE_MULTIPLY),
                        _fail_event(0),
                        _event(
                            0,
                            "TEST_PHASE",
                            node_id=_NODE_MULTIPLY,
                            phase="CALL",
                            outcome="PASS",
                        ),
                        _event(0, "SESSION_END"),
                    )
                )
            ),
        ),
        # Broken sequence numbering.
        (
            pytest_reporter.REASON_SEQUENCE,
            _mutated_report(_replaced(_complete_events(), 3, sequence=9)),
        ),
        # Duplicate event sequence.
        (
            pytest_reporter.REASON_DUPLICATE,
            _mutated_report(_replaced(_complete_events(), 3, sequence=2)),
        ),
        # A SESSION_END in the middle of the lifecycle.
        (
            pytest_reporter.REASON_ORDER,
            _mutated_report(
                _renumbered(
                    (
                        _event(0, "SESSION_START"),
                        _event(0, "COLLECTION_ITEM", node_id=_NODE_ADD),
                        _event(0, "SESSION_END"),
                        _event(0, "COLLECTION_ITEM", node_id=_NODE_MULTIPLY),
                        _fail_event(0),
                        _event(
                            0,
                            "TEST_PHASE",
                            node_id=_NODE_MULTIPLY,
                            phase="CALL",
                            outcome="PASS",
                        ),
                        _event(0, "SESSION_END"),
                    )
                )
            ),
        ),
        # A second SESSION_START in the middle.
        (
            pytest_reporter.REASON_ORDER,
            _mutated_report(
                _renumbered(
                    (
                        _event(0, "SESSION_START"),
                        _event(0, "COLLECTION_ITEM", node_id=_NODE_ADD),
                        _event(0, "SESSION_START"),
                        _event(0, "COLLECTION_ITEM", node_id=_NODE_MULTIPLY),
                        _fail_event(0),
                        _event(
                            0,
                            "TEST_PHASE",
                            node_id=_NODE_MULTIPLY,
                            phase="CALL",
                            outcome="PASS",
                        ),
                        _event(0, "SESSION_END"),
                    )
                )
            ),
        ),
        # SESSION_START declaring an implicit field.
        (
            pytest_reporter.REASON_IMPLICIT,
            _mutated_report(_replaced(_complete_events(), 0, node_id=_NODE_ADD)),
        ),
        # TEST_PHASE without an explicit phase.
        (
            pytest_reporter.REASON_IMPLICIT,
            _mutated_report(_replaced(_complete_events(), 3, phase=None)),
        ),
        # TEST_PHASE FAIL with a phase other than CALL.
        (
            pytest_reporter.REASON_IMPLICIT,
            _mutated_report(_replaced(_complete_events(), 3, phase="SETUP")),
        ),
        # FAIL without a structured exception.
        (
            pytest_reporter.REASON_FAIL_NO_EXC,
            _mutated_report(
                _replaced(
                    _complete_events(),
                    3,
                    exception_type=None,
                    normalized_message=None,
                    relative_path=None,
                    function_name=None,
                    line_number=None,
                )
            ),
        ),
        # ERROR without a structured exception.
        (
            pytest_reporter.REASON_ERROR_NO_EXC,
            _mutated_report(
                _replaced(_complete_events(), 4, phase="SETUP", outcome="ERROR")
            ),
        ),
        # PASS declaring an exception field.
        (
            pytest_reporter.REASON_IMPLICIT,
            _mutated_report(
                _replaced(_complete_events(), 4, exception_type="AssertionError")
            ),
        ),
        # XPASS without the explicit wasxfail marker.
        (
            pytest_reporter.REASON_IMPLICIT,
            _mutated_report(_replaced(_complete_events(), 4, outcome="XPASS")),
        ),
        # DESELECTED events never form complete gate evidence.
        (
            pytest_reporter.REASON_DESELECTED,
            _mutated_report(
                _renumbered(
                    (
                        _event(0, "SESSION_START"),
                        _event(0, "COLLECTION_ITEM", node_id=_NODE_ADD),
                        _event(0, "COLLECTION_ITEM", node_id=_NODE_MULTIPLY),
                        _event(0, "DESELECTED", node_id=_NODE_MULTIPLY),
                        _fail_event(0),
                        _event(
                            0,
                            "TEST_PHASE",
                            node_id=_NODE_MULTIPLY,
                            phase="CALL",
                            outcome="PASS",
                        ),
                        _event(0, "SESSION_END"),
                    )
                )
            ),
        ),
        # Collection errors never form complete gate evidence.
        (
            pytest_reporter.REASON_COLLECTION_ERROR,
            _mutated_report(
                _renumbered(
                    (
                        _event(0, "SESSION_START"),
                        _event(
                            0,
                            "SESSION_ERROR",
                            exception_type="CollectionError",
                            normalized_message="broken collector",
                        ),
                        _event(0, "COLLECTION_ITEM", node_id=_NODE_ADD),
                        _event(0, "COLLECTION_ITEM", node_id=_NODE_MULTIPLY),
                        _fail_event(0),
                        _event(
                            0,
                            "TEST_PHASE",
                            node_id=_NODE_MULTIPLY,
                            phase="CALL",
                            outcome="PASS",
                        ),
                        _event(0, "SESSION_END"),
                    )
                )
            ),
        ),
        # An empty collection is not gate evidence.
        (
            pytest_reporter.REASON_EMPTY_COLLECTION,
            _mutated_report(_complete_events(), collected=()),
        ),
        # A planned node that was never collected.
        (
            pytest_reporter.REASON_MISSING_COLLECTED,
            _mutated_report(_complete_events(), collected=(_NODE_ADD,)),
        ),
        # A collected node outside the plan.
        (
            pytest_reporter.REASON_UNPLANNED,
            _mutated_report(
                _complete_events(),
                planned=(_NODE_ADD,),
                collected=(_NODE_ADD, _NODE_MULTIPLY),
            ),
        ),
        # The same node set in a different order is still mismatched.
        (
            pytest_reporter.REASON_MISMATCH,
            _mutated_report(
                _complete_events(),
                collected=(_NODE_MULTIPLY, _NODE_ADD),
            ),
        ),
        # A planned node that was never executed.
        (
            pytest_reporter.REASON_NOT_EXECUTED,
            _mutated_report(
                _renumbered(
                    (
                        _event(0, "SESSION_START"),
                        _event(0, "COLLECTION_ITEM", node_id=_NODE_ADD),
                        _event(0, "COLLECTION_ITEM", node_id=_NODE_MULTIPLY),
                        _fail_event(0),
                        _event(0, "SESSION_END"),
                    )
                )
            ),
        ),
        # A TEST_PHASE node outside the collected set.
        (
            pytest_reporter.REASON_UNCOLLECTED,
            _mutated_report(
                _replaced(_complete_events(), 4, node_id="tests/other.py::test_x")
            ),
        ),
        # The same node and phase executed twice.
        (
            pytest_reporter.REASON_DUPLICATE_PHASE,
            _mutated_report(
                _renumbered(
                    (
                        _event(0, "SESSION_START"),
                        _event(0, "COLLECTION_ITEM", node_id=_NODE_ADD),
                        _event(0, "COLLECTION_ITEM", node_id=_NODE_MULTIPLY),
                        _fail_event(0),
                        _fail_event(0),
                        _event(
                            0,
                            "TEST_PHASE",
                            node_id=_NODE_MULTIPLY,
                            phase="CALL",
                            outcome="PASS",
                        ),
                        _event(0, "SESSION_END"),
                    )
                )
            ),
        ),
        # Failures reported while the exit code claims success.
        (
            pytest_reporter.REASON_EXIT,
            _mutated_report(_complete_events(), exit_code=0),
        ),
        # A clean run whose exit code claims a failure.
        (
            pytest_reporter.REASON_EXIT,
            _mutated_report(
                _renumbered(
                    (
                        _event(0, "SESSION_START"),
                        _event(0, "COLLECTION_ITEM", node_id=_NODE_ADD),
                        _event(0, "COLLECTION_ITEM", node_id=_NODE_MULTIPLY),
                        _event(
                            0,
                            "TEST_PHASE",
                            node_id=_NODE_ADD,
                            phase="CALL",
                            outcome="PASS",
                        ),
                        _event(
                            0,
                            "TEST_PHASE",
                            node_id=_NODE_MULTIPLY,
                            phase="CALL",
                            outcome="PASS",
                        ),
                        _event(0, "SESSION_END"),
                    )
                ),
                exit_code=1,
            ),
        ),
        # A tampered integrity identity.
        (
            pytest_reporter.REASON_INTEGRITY,
            dataclasses.replace(complete_gate_report(), integrity_digest="00" * 32),
        ),
        # No lifecycle events at all.
        (
            pytest_reporter.REASON_EMPTY_EVENTS,
            _mutated_report(()),
        ),
    ]
    for reason, report in cases:
        result = validate_gate_pytest_report(report)
        assert result.passed is False, reason
        assert result.reason == reason


def _seed_project(tmp: Path) -> Path:
    """One deterministic mini-project with one stable failing test."""
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
        "from vesper_fixture.calculator import add, multiply\n"
        "def test_add_returns_sum():\n"
        "    assert add(2, 2) == 4\n"
        "def test_multiply_returns_product():\n"
        "    assert multiply(3, 4) == 12\n",
        encoding="utf-8",
    )
    return project


def test_real_capture_collection_full_run_and_target_rerun(tmp_path: Path) -> None:
    root = _seed_project(tmp_path)
    collect = run_gate_pytest(root, (), collect_only=True)
    assert validate_gate_pytest_report(collect).passed is True
    assert collect.collected_node_ids == _PLANNED
    collect_second = run_gate_pytest(root, (), collect_only=True)
    assert collect_second.collected_node_ids == collect.collected_node_ids

    full = run_gate_pytest(root, _PLANNED)
    assert validate_gate_pytest_report(full).passed is True
    assert full.normal_end is True
    assert full.exit_code == 1
    fail_events = [
        event
        for event in full.events
        if event.event_type == "TEST_PHASE" and event.outcome == "FAIL"
    ]
    assert len(fail_events) == 1
    failure = fail_events[0]
    assert failure.node_id == _NODE_ADD
    assert failure.phase == "CALL"
    assert failure.exception_type == "AssertionError"
    assert isinstance(failure.normalized_message, str)
    assert "assert 0 == 4" in failure.normalized_message
    assert failure.relative_path == "tests/test_calculator.py"
    assert failure.function_name == "test_add_returns_sum"
    assert isinstance(failure.line_number, int) and failure.line_number > 0

    target = run_gate_pytest(root, (_NODE_ADD,), target_node_ids=(_NODE_ADD,))
    assert validate_gate_pytest_report(target).passed is True
    assert target.collected_node_ids == (_NODE_ADD,)
    assert target.exit_code == 1


def test_gate_reporter_is_only_loaded_explicitly(tmp_path: Path) -> None:
    root = _seed_project(tmp_path)
    channel = tmp_path / "events.jsonl"
    env = os.environ.copy()
    env["PYTHONPATH"] = str(pytest_reporter.REPO_ROOT)
    env[pytest_reporter.REPORT_CHANNEL_ENV] = str(channel)
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "-o",
            "cacheprovider=disabled",
            "--rootdir",
            str(root),
            str(root),
            "-q",
        ],
        cwd=str(root),
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert proc.returncode == 1  # the failing test ran without the reporter
    assert not channel.exists()


def test_gate_reporter_fails_closed_without_report_channel(tmp_path: Path) -> None:
    root = _seed_project(tmp_path)
    env = os.environ.copy()
    env["PYTHONPATH"] = str(pytest_reporter.REPO_ROOT)
    env.pop(pytest_reporter.REPORT_CHANNEL_ENV, None)
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "-p",
            "spikes.docker_reference_boundary.pytest_reporter",
            "-o",
            "cacheprovider=disabled",
            "--rootdir",
            str(root),
            str(root),
            "-q",
        ],
        cwd=str(root),
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert proc.returncode != 0
    assert "REPORT_CHANNEL" in proc.stdout + proc.stderr


def _channel_line(**overrides: object) -> str:
    event: dict[str, object] = {
        "sequence": 1,
        "event_type": "SESSION_START",
        "node_id": None,
        "phase": None,
        "outcome": None,
        "wasxfail": None,
        "exception_type": None,
        "normalized_message": None,
        "relative_path": None,
        "function_name": None,
        "line_number": None,
    }
    event.update(overrides)
    return json.dumps(event, ensure_ascii=False, separators=(",", ":"))


def test_loader_rejects_malformed_channel(tmp_path: Path) -> None:
    channel = tmp_path / "events.jsonl"
    channel.write_text("", encoding="utf-8")
    with pytest.raises(ValueError, match="empty"):
        load_gate_pytest_report(channel, _PLANNED, 0)
    channel.write_text("not json\n", encoding="utf-8")
    with pytest.raises(ValueError, match="invalid JSON"):
        load_gate_pytest_report(channel, _PLANNED, 0)
    channel.write_text('{"sequence": 1}\n', encoding="utf-8")
    with pytest.raises(ValueError, match="invalid field set"):
        load_gate_pytest_report(channel, _PLANNED, 0)
    channel.write_text(_channel_line(sequence="1") + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="sequence must be an integer"):
        load_gate_pytest_report(channel, _PLANNED, 0)
    channel.write_text(_channel_line(event_type="UNKNOWN") + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="event_type"):
        load_gate_pytest_report(channel, _PLANNED, 0)
    channel.write_text(_channel_line(phase="MIDNIGHT") + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="phase"):
        load_gate_pytest_report(channel, _PLANNED, 0)
    channel.write_text(_channel_line(outcome="RAN") + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="outcome"):
        load_gate_pytest_report(channel, _PLANNED, 0)
    channel.write_text(_channel_line(wasxfail=1) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="wasxfail"):
        load_gate_pytest_report(channel, _PLANNED, 0)
    channel.write_text(_channel_line(line_number="5") + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="line_number"):
        load_gate_pytest_report(channel, _PLANNED, 0)
    channel.write_text(_channel_line(node_id=7) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="node_id"):
        load_gate_pytest_report(channel, _PLANNED, 0)


def test_loader_derives_collected_and_normal_end(tmp_path: Path) -> None:
    channel = tmp_path / "events.jsonl"
    channel.write_text(
        _channel_line()
        + "\n"
        + _channel_line(sequence=2, event_type="COLLECTION_ITEM", node_id=_NODE_ADD)
        + "\n"
        + _channel_line(sequence=3, event_type="SESSION_END")
        + "\n",
        encoding="utf-8",
    )
    report = load_gate_pytest_report(channel, (), 0)
    assert report.collected_node_ids == (_NODE_ADD,)
    assert report.normal_end is True
    assert validate_gate_pytest_report(report).passed is True
    truncated = tmp_path / "truncated.jsonl"
    truncated.write_text(
        _channel_line()
        + "\n"
        + _channel_line(sequence=2, event_type="COLLECTION_ITEM", node_id=_NODE_ADD)
        + "\n",
        encoding="utf-8",
    )
    report = load_gate_pytest_report(truncated, (), 0)
    assert report.normal_end is False
    assert validate_gate_pytest_report(report).passed is False
    assert validate_gate_pytest_report(report).reason == pytest_reporter.REASON_END

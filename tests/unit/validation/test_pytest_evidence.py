"""T19.1 legacy step 19.B: authoritative pytest event report parsing.

``parse_pytest_evidence`` turns one bounded raw report channel into the
single complete ordered ``PytestEvidenceV1`` and fails closed with the
stable ``REPORTER_INVALID`` code for missing, duplicate, reordered,
truncated, over-limit, corrupt, schema-violating, exit-inconsistent, or
expectation-mismatched evidence — the report's integrity and normal end
are authoritative over any exit code or console text (SPEC §4.5).  The
exact displayed RED test proves a report whose terminal ``SESSION_END``
event is missing is rejected, and the corruption matrix pins every closed
rejection row.

Mypy-required note (T05.1 precedent "displayed RED tests copied with
minimal mypy-required dict annotations"): the displayed RED test slices
``complete_pytest_report_dict["events"]`` where the displayed annotation
is ``dict[str, object]``; mypy strict rejects indexing ``object``, so the
exact line carries ``# type: ignore[index]`` — a comment only, no
behavioral change to the displayed test.
"""

from __future__ import annotations

import hashlib
import json
from typing import TypeVar

import pytest

# The evidence contracts are pydantic runtime models; the hash-locked
# gate toolchain does not install runtime dependencies, so this module
# skips cleanly there instead of failing at collection (formal env runs it
# fully).
pytest.importorskip("pydantic")

from vespercode.contracts.optional import AbsentV1, PresentV1
from vespercode.validation.pytest_evidence import (
    PytestReportExpectationV1,
    parse_pytest_evidence,
)

_PLUGIN_VERSION = "1"
_NODE_ADD = "tests/test_calculator.py::test_add_returns_sum"
_NODE_MULTIPLY = "tests/test_calculator.py::test_multiply_returns_product"
_PLANNED = (_NODE_ADD, _NODE_MULTIPLY)

_T = TypeVar("_T")


def _require_present(optional: AbsentV1 | PresentV1[_T]) -> _T:
    """Assert the closed optional is PRESENT and return its exact value."""
    assert isinstance(optional, PresentV1)
    return optional.value


def canonical_json_bytes(value: dict[str, object]) -> bytes:
    """The canonical report bytes: compact, sorted keys, raw UTF-8."""
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def recompute_report_digest(report: dict[str, object]) -> str:
    """Independent SPEC §0.1 recomputation of the integrity digest.

    The digest binds every field except ``integrity_digest`` through the
    canonical UTF-8 JSON bytes under the exact domain prefix
    ``UTF8("VesperCode") || 0x00 || "PytestEvidenceV1" || 0x00 || "1" ||
    0x00``.
    """
    body = {key: value for key, value in report.items() if key != "integrity_digest"}
    prefix = b"VesperCode\x00PytestEvidenceV1\x001\x00"
    return hashlib.sha256(prefix + canonical_json_bytes(body)).hexdigest()


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
    *,
    exception_type: str = "AssertionError",
    normalized_message: str = "assert 0 == 4\n +  where 0 = add(2, 2)",
    assertion_diff: str = "assert 0 == 4\n +  where 0 = add(2, 2)",
    frames: tuple[tuple[str, str, int], ...] = (
        ("tests/test_calculator.py", "test_add_returns_sum", 6),
    ),
) -> dict[str, object]:
    return {
        "exception_type": exception_type,
        "normalized_message": normalized_message,
        "normalized_assertion_diff": _present_text(assertion_diff),
        "project_frames": [
            {
                "relative_path": relative_path,
                "function_name": function_name,
                "line_number": line_number,
            }
            for relative_path, function_name, line_number in frames
        ],
    }


def _complete_events() -> list[dict[str, object]]:
    return [
        _event(1, "SESSION_START"),
        _event(2, "COLLECTION_ITEM", node_id=_present_text(_NODE_ADD)),
        _event(3, "COLLECTION_ITEM", node_id=_present_text(_NODE_MULTIPLY)),
        _event(
            4,
            "TEST_PHASE",
            node_id=_present_text(_NODE_ADD),
            phase=_present_text("CALL"),
            outcome=_present_text("FAIL"),
            exception={"kind": "PRESENT", "value": _exception()},
        ),
        _event(
            5,
            "TEST_PHASE",
            node_id=_present_text(_NODE_MULTIPLY),
            phase=_present_text("CALL"),
            outcome=_present_text("PASS"),
        ),
        _event(6, "SESSION_END"),
    ]


def _complete_report_dict() -> dict[str, object]:
    report: dict[str, object] = {
        "schema_version": 1,
        "report_plugin_version": _PLUGIN_VERSION,
        "run_kind": "FULL_PYTEST",
        "planned_node_ids": list(_PLANNED),
        "collected_node_ids": list(_PLANNED),
        "events": _complete_events(),
        "pytest_exit_code": 1,
        "event_count": 6,
        "normal_end_marker": True,
        "integrity_digest": "0" * 64,
    }
    report["integrity_digest"] = recompute_report_digest(report)
    return report


@pytest.fixture
def complete_pytest_report_dict() -> dict[str, object]:
    """One complete ordered FULL_PYTEST report with a self-binding digest."""
    return _complete_report_dict()


def expected_full_pytest_report() -> PytestReportExpectationV1:
    return PytestReportExpectationV1(
        schema_version=1,
        run_kind="FULL_PYTEST",
        planned_node_ids=_PLANNED,
        report_plugin_version=_PLUGIN_VERSION,
    )


def test_missing_session_end_is_reporter_invalid(
    complete_pytest_report_dict: dict[str, object],
) -> None:
    complete_pytest_report_dict["events"] = complete_pytest_report_dict["events"][:-1]  # type: ignore[index]
    complete_pytest_report_dict["integrity_digest"] = recompute_report_digest(
        complete_pytest_report_dict
    )
    outcome = parse_pytest_evidence(
        canonical_json_bytes(complete_pytest_report_dict), expected_full_pytest_report()
    )
    assert outcome.error_code == "REPORTER_INVALID"
    assert outcome.evidence is None


def test_complete_report_parses_into_authoritative_evidence(
    complete_pytest_report_dict: dict[str, object],
) -> None:
    outcome = parse_pytest_evidence(
        canonical_json_bytes(complete_pytest_report_dict), expected_full_pytest_report()
    )
    assert outcome.error_code is None
    assert outcome.evidence is not None
    evidence = outcome.evidence
    assert evidence.schema_version == 1
    assert evidence.run_kind == "FULL_PYTEST"
    assert evidence.planned_node_ids == _PLANNED
    assert evidence.collected_node_ids == _PLANNED
    assert evidence.pytest_exit_code == 1
    assert evidence.event_count == 6
    assert evidence.normal_end_marker is True
    assert evidence.integrity_digest == recompute_report_digest(
        complete_pytest_report_dict
    )
    assert [event.event_type for event in evidence.events] == [
        "SESSION_START",
        "COLLECTION_ITEM",
        "COLLECTION_ITEM",
        "TEST_PHASE",
        "TEST_PHASE",
        "SESSION_END",
    ]
    failure = evidence.events[3]
    assert _require_present(failure.phase) == "CALL"
    assert _require_present(failure.outcome) == "FAIL"
    exception = _require_present(failure.exception)
    assert exception.exception_type == "AssertionError"
    assert exception.project_frames[0].relative_path.value == (
        "tests/test_calculator.py"
    )


def test_collect_only_and_target_kind_reports_parse(
    complete_pytest_report_dict: dict[str, object],
) -> None:
    collect = {
        **complete_pytest_report_dict,
        "run_kind": "COLLECT_ONLY",
        "pytest_exit_code": 0,
    }
    collect = _with_events(
        collect,
        [
            {**event, "sequence": index + 1}
            for index, event in enumerate(
                event
                for event in _events_of(collect)
                if event["event_type"] != "TEST_PHASE"
            )
        ],
    )
    collect["event_count"] = len(_events_of(collect))
    collect["integrity_digest"] = recompute_report_digest(collect)
    expectation = PytestReportExpectationV1(
        schema_version=1,
        run_kind="COLLECT_ONLY",
        planned_node_ids=_PLANNED,
        report_plugin_version=_PLUGIN_VERSION,
    )
    outcome = parse_pytest_evidence(canonical_json_bytes(collect), expectation)
    assert outcome.error_code is None
    assert outcome.evidence is not None
    assert outcome.evidence.run_kind == "COLLECT_ONLY"


def test_skip_xfail_and_deselect_events_are_closed(
    complete_pytest_report_dict: dict[str, object],
) -> None:
    events = [
        _event(1, "SESSION_START"),
        _event(2, "COLLECTION_ITEM", node_id=_present_text(_NODE_ADD)),
        _event(3, "COLLECTION_ITEM", node_id=_present_text(_NODE_MULTIPLY)),
        _event(
            4,
            "TEST_PHASE",
            node_id=_present_text(_NODE_ADD),
            phase=_present_text("SETUP"),
            outcome=_present_text("SKIP"),
        ),
        _event(
            5,
            "TEST_PHASE",
            node_id=_present_text(_NODE_MULTIPLY),
            phase=_present_text("CALL"),
            outcome=_present_text("XFAIL"),
            wasxfail={"kind": "PRESENT", "value": True},
        ),
        _event(6, "DESELECTED", node_id=_present_text(_NODE_MULTIPLY)),
        _event(7, "SESSION_END"),
    ]
    report: dict[str, object] = {
        **complete_pytest_report_dict,
        "events": events,
        "event_count": 7,
        "pytest_exit_code": 0,
    }
    report["integrity_digest"] = recompute_report_digest(report)
    outcome = parse_pytest_evidence(
        canonical_json_bytes(report), expected_full_pytest_report()
    )
    assert outcome.error_code is None
    assert outcome.evidence is not None
    assert _require_present(outcome.evidence.events[3].outcome) == "SKIP"
    assert _require_present(outcome.evidence.events[4].outcome) == "XFAIL"
    assert _require_present(outcome.evidence.events[4].wasxfail) is True
    assert outcome.evidence.events[5].event_type == "DESELECTED"


def test_all_five_error_phases_are_closed(
    complete_pytest_report_dict: dict[str, object],
) -> None:
    """All five ErrorPhase values are closed report vocabulary.

    SETUP/TEARDOWN/ENVIRONMENT appear on TEST_PHASE events; COLLECTION
    appears on SESSION_ERROR events (report-level collection failures);
    CALL failures are the only FAIL phase and are pinned in the complete
    report fixture.
    """
    events = [
        _event(1, "SESSION_START"),
        _event(2, "COLLECTION_ITEM", node_id=_present_text(_NODE_ADD)),
        _event(
            3,
            "TEST_PHASE",
            node_id=_present_text(_NODE_ADD),
            phase=_present_text("SETUP"),
            outcome=_present_text("ERROR"),
            exception={
                "kind": "PRESENT",
                "value": _exception(
                    exception_type="RuntimeError",
                    normalized_message="setup boom",
                    assertion_diff="setup boom",
                ),
            },
        ),
        _event(
            4,
            "TEST_PHASE",
            node_id=_present_text(_NODE_ADD),
            phase=_present_text("TEARDOWN"),
            outcome=_present_text("ERROR"),
            exception={
                "kind": "PRESENT",
                "value": _exception(
                    exception_type="RuntimeError",
                    normalized_message="teardown boom",
                    assertion_diff="teardown boom",
                ),
            },
        ),
        _event(
            5,
            "TEST_PHASE",
            node_id=_present_text(_NODE_ADD),
            phase=_present_text("ENVIRONMENT"),
            outcome=_present_text("ERROR"),
            exception={
                "kind": "PRESENT",
                "value": _exception(
                    exception_type="RuntimeError",
                    normalized_message="env boom",
                    assertion_diff="env boom",
                ),
            },
        ),
        _event(
            6,
            "SESSION_ERROR",
            exception={
                "kind": "PRESENT",
                "value": _exception(
                    exception_type="CollectionError",
                    normalized_message="collect boom",
                    assertion_diff="collect boom",
                    frames=(),
                ),
            },
        ),
        _event(7, "SESSION_END"),
    ]
    report: dict[str, object] = {
        **complete_pytest_report_dict,
        "events": events,
        "event_count": 7,
        "pytest_exit_code": 2,
    }
    report["integrity_digest"] = recompute_report_digest(report)
    outcome = parse_pytest_evidence(
        canonical_json_bytes(report), expected_full_pytest_report()
    )
    assert outcome.error_code is None
    phases = {
        _require_present(event.phase)
        for event in outcome.evidence.events  # type: ignore[union-attr]
        if event.event_type == "TEST_PHASE"
    }
    assert phases == {"SETUP", "TEARDOWN", "ENVIRONMENT"}


def _events_of(report: dict[str, object]) -> list[dict[str, object]]:
    """The typed events list of one report dict."""
    events = report["events"]
    assert isinstance(events, list)
    return events


def _with_events(
    report: dict[str, object], events: list[dict[str, object]]
) -> dict[str, object]:
    """One report dict whose events are replaced (digest recomputed after)."""
    return {**report, "events": events}


_MATRIX_CASES: list[
    tuple[str, dict[str, object], PytestReportExpectationV1 | None]
] = []


def _matrix_case(
    case_id: str,
    report: dict[str, object],
    expectation: PytestReportExpectationV1 | None = None,
) -> None:
    _MATRIX_CASES.append((case_id, report, expectation))


_matrix_case("complete-valid-report", _complete_report_dict())

_missing_end = _complete_report_dict()
_missing_end = _with_events(_missing_end, _events_of(_missing_end)[:-1])
_missing_end["event_count"] = 5
_missing_end["integrity_digest"] = recompute_report_digest(_missing_end)
_matrix_case("missing-session-end", _missing_end)

_missing_start = _complete_report_dict()
_missing_start = _with_events(_missing_start, _events_of(_missing_start)[1:])
_missing_start["event_count"] = 5
_missing_start["integrity_digest"] = recompute_report_digest(_missing_start)
_matrix_case("missing-session-start", _missing_start)

_duplicate_events = _events_of(_complete_report_dict())
_duplicate_events.insert(2, _duplicate_events[1])
_duplicate_event = _with_events(_complete_report_dict(), _duplicate_events)
_duplicate_event["event_count"] = 7
_duplicate_event["integrity_digest"] = recompute_report_digest(_duplicate_event)
_matrix_case("duplicate-event-sequence", _duplicate_event)

_reordered_events = _events_of(_complete_report_dict())
_reordered_events[1], _reordered_events[2] = _reordered_events[2], _reordered_events[1]
_reordered = _with_events(_complete_report_dict(), _reordered_events)
_reordered["integrity_digest"] = recompute_report_digest(_reordered)
_matrix_case("reordered-collection-events", _reordered)

_sequence_gap_events = [
    {**_event, "sequence": index + 1 if index < 3 else index + 2}
    for index, _event in enumerate(_events_of(_complete_report_dict()))
]
_sequence_gap = _with_events(_complete_report_dict(), _sequence_gap_events)
_sequence_gap["integrity_digest"] = recompute_report_digest(_sequence_gap)
_matrix_case("sequence-gap", _sequence_gap)

_event_after_end = _complete_report_dict()
_event_after_end = _with_events(
    _event_after_end,
    [
        *_events_of(_event_after_end),
        _event(
            7,
            "TEST_PHASE",
            node_id=_present_text(_NODE_ADD),
            phase=_present_text("CALL"),
            outcome=_present_text("PASS"),
        ),
    ],
)
_event_after_end["event_count"] = 7
_event_after_end["integrity_digest"] = recompute_report_digest(_event_after_end)
_matrix_case("session-end-not-last", _event_after_end)

_second_start = _complete_report_dict()
_second_start = _with_events(
    _second_start,
    [
        *_events_of(_second_start)[:3],
        _event(4, "SESSION_START"),
        *_events_of(_second_start)[3:],
    ],
)
_second_start["event_count"] = 7
_second_start["integrity_digest"] = recompute_report_digest(_second_start)
_matrix_case("second-session-start", _second_start)

_normal_end_false = _complete_report_dict()
_normal_end_false["normal_end_marker"] = False
_normal_end_false["integrity_digest"] = recompute_report_digest(_normal_end_false)
_matrix_case("normal-end-marker-false", _normal_end_false)

_digest_corrupt = _complete_report_dict()
_digest_corrupt["integrity_digest"] = "f" * 64
_matrix_case("integrity-digest-corrupt", _digest_corrupt)

_unknown_schema_field = _complete_report_dict()
_unknown_schema_field["extra_field"] = 1
_unknown_schema_field["integrity_digest"] = recompute_report_digest(
    _unknown_schema_field
)
_matrix_case("unknown-schema-field", _unknown_schema_field)

_missing_schema_field = _complete_report_dict()
_missing_schema_field.pop("report_plugin_version")
_missing_schema_field["integrity_digest"] = recompute_report_digest(
    _missing_schema_field
)
_matrix_case("missing-schema-field", _missing_schema_field)

_schema_version_drift = _complete_report_dict()
_schema_version_drift["schema_version"] = 2
_schema_version_drift["integrity_digest"] = recompute_report_digest(
    _schema_version_drift
)
_matrix_case("schema-version-drift", _schema_version_drift)

_event_count_mismatch = _complete_report_dict()
_event_count_mismatch["event_count"] = 5
_event_count_mismatch["integrity_digest"] = recompute_report_digest(
    _event_count_mismatch
)
_matrix_case("event-count-mismatch", _event_count_mismatch)

_fail_without_exception_events = _events_of(_complete_report_dict())
_fail_without_exception_events[3] = _event(
    4,
    "TEST_PHASE",
    node_id=_present_text(_NODE_ADD),
    phase=_present_text("CALL"),
    outcome=_present_text("FAIL"),
)
_fail_without_exception = _with_events(
    _complete_report_dict(), _fail_without_exception_events
)
_fail_without_exception["integrity_digest"] = recompute_report_digest(
    _fail_without_exception
)
_matrix_case("fail-without-exception", _fail_without_exception)

_fail_in_setup_events = _events_of(_complete_report_dict())
_fail_in_setup_events[3] = _event(
    4,
    "TEST_PHASE",
    node_id=_present_text(_NODE_ADD),
    phase=_present_text("SETUP"),
    outcome=_present_text("FAIL"),
    exception={"kind": "PRESENT", "value": _exception()},
)
_fail_in_setup = _with_events(_complete_report_dict(), _fail_in_setup_events)
_fail_in_setup["integrity_digest"] = recompute_report_digest(_fail_in_setup)
_matrix_case("fail-in-setup-phase", _fail_in_setup)

_error_in_call_events = _events_of(_complete_report_dict())
_error_in_call_events[3] = _event(
    4,
    "TEST_PHASE",
    node_id=_present_text(_NODE_ADD),
    phase=_present_text("CALL"),
    outcome=_present_text("ERROR"),
    exception={
        "kind": "PRESENT",
        "value": _exception(
            exception_type="RuntimeError",
            normalized_message="boom",
            assertion_diff="boom",
        ),
    },
)
_error_in_call = _with_events(_complete_report_dict(), _error_in_call_events)
_error_in_call["integrity_digest"] = recompute_report_digest(_error_in_call)
_matrix_case("error-in-call-phase", _error_in_call)

_no_frames_events = _events_of(_complete_report_dict())
_no_frames_events[3] = _event(
    4,
    "TEST_PHASE",
    node_id=_present_text(_NODE_ADD),
    phase=_present_text("CALL"),
    outcome=_present_text("FAIL"),
    exception={
        "kind": "PRESENT",
        "value": _exception(frames=()),
    },
)
_no_frames = _with_events(_complete_report_dict(), _no_frames_events)
_no_frames["integrity_digest"] = recompute_report_digest(_no_frames)
_matrix_case("fail-exception-without-frames", _no_frames)

_xfail_no_wasxfail_events = _events_of(_complete_report_dict())
_xfail_no_wasxfail_events[3] = _event(
    4,
    "TEST_PHASE",
    node_id=_present_text(_NODE_ADD),
    phase=_present_text("CALL"),
    outcome=_present_text("XFAIL"),
)
_xfail_no_wasxfail = _with_events(_complete_report_dict(), _xfail_no_wasxfail_events)
_xfail_no_wasxfail["integrity_digest"] = recompute_report_digest(_xfail_no_wasxfail)
_matrix_case("xfail-without-wasxfail", _xfail_no_wasxfail)

_pass_with_exception_events = _events_of(_complete_report_dict())
_pass_with_exception_events[3] = _event(
    4,
    "TEST_PHASE",
    node_id=_present_text(_NODE_ADD),
    phase=_present_text("CALL"),
    outcome=_present_text("PASS"),
    exception={"kind": "PRESENT", "value": _exception()},
)
_pass_with_exception = _with_events(
    _complete_report_dict(), _pass_with_exception_events
)
_pass_with_exception["integrity_digest"] = recompute_report_digest(_pass_with_exception)
_matrix_case("pass-with-exception", _pass_with_exception)

_implicit_events = _events_of(_complete_report_dict())
_implicit_events[3] = _event(4, "TEST_PHASE", outcome=_present_text("PASS"))
_implicit = _with_events(_complete_report_dict(), _implicit_events)
_implicit["integrity_digest"] = recompute_report_digest(_implicit)
_matrix_case("implicit-test-phase-fields", _implicit)

_uncollected_events = _events_of(_complete_report_dict())
_uncollected_events[3] = _event(
    4,
    "TEST_PHASE",
    node_id=_present_text("tests/other.py::test_x"),
    phase=_present_text("CALL"),
    outcome=_present_text("PASS"),
)
_uncollected = _with_events(_complete_report_dict(), _uncollected_events)
_uncollected["integrity_digest"] = recompute_report_digest(_uncollected)
_matrix_case("test-phase-node-uncollected", _uncollected)

_unplanned_events = [
    _event(2, "COLLECTION_ITEM", node_id=_present_text(_NODE_ADD)),
    _event(3, "COLLECTION_ITEM", node_id=_present_text(_NODE_MULTIPLY)),
    _event(4, "COLLECTION_ITEM", node_id=_present_text("tests/other.py::test_x")),
    _event(
        5,
        "TEST_PHASE",
        node_id=_present_text(_NODE_ADD),
        phase=_present_text("CALL"),
        outcome=_present_text("FAIL"),
        exception={"kind": "PRESENT", "value": _exception()},
    ),
    _event(
        6,
        "TEST_PHASE",
        node_id=_present_text(_NODE_MULTIPLY),
        phase=_present_text("CALL"),
        outcome=_present_text("PASS"),
    ),
    _event(7, "SESSION_END"),
]
_unplanned = _with_events(_complete_report_dict(), _unplanned_events)
_unplanned["collected_node_ids"] = [
    _NODE_ADD,
    _NODE_MULTIPLY,
    "tests/other.py::test_x",
]
_unplanned["event_count"] = 7
_unplanned["integrity_digest"] = recompute_report_digest(_unplanned)
_matrix_case("unplanned-node-collected", _unplanned)

_missing_planned_events = [
    _event(1, "SESSION_START"),
    _event(2, "COLLECTION_ITEM", node_id=_present_text(_NODE_ADD)),
    _event(
        3,
        "TEST_PHASE",
        node_id=_present_text(_NODE_ADD),
        phase=_present_text("CALL"),
        outcome=_present_text("FAIL"),
        exception={"kind": "PRESENT", "value": _exception()},
    ),
    _event(4, "SESSION_END"),
]
_missing_planned = _with_events(_complete_report_dict(), _missing_planned_events)
_missing_planned["collected_node_ids"] = [_NODE_ADD]
_missing_planned["event_count"] = 4
_missing_planned["integrity_digest"] = recompute_report_digest(_missing_planned)
_matrix_case("planned-node-not-collected", _missing_planned)

_exit_zero_events = _events_of(_complete_report_dict())
_exit_zero = _with_events(_complete_report_dict(), _exit_zero_events)
_exit_zero["pytest_exit_code"] = 0
_exit_zero["integrity_digest"] = recompute_report_digest(_exit_zero)
_matrix_case("exit-code-zero-with-failures", _exit_zero)

_clean_events = [
    event
    for event in _events_of(_complete_report_dict())
    if event["event_type"] != "TEST_PHASE"
]
_exit_nonzero = _with_events(_complete_report_dict(), _clean_events)
_exit_nonzero["pytest_exit_code"] = 1
_exit_nonzero["event_count"] = 4
_exit_nonzero["integrity_digest"] = recompute_report_digest(_exit_nonzero)
_matrix_case("exit-code-nonzero-without-failures", _exit_nonzero)

_collection_error_events = [
    _event(1, "SESSION_START"),
    _event(
        2,
        "SESSION_ERROR",
        exception={
            "kind": "PRESENT",
            "value": _exception(
                exception_type="CollectionError",
                normalized_message="boom",
                assertion_diff="boom",
                frames=(),
            ),
        },
    ),
    _event(3, "SESSION_END"),
]
_collection_error = _with_events(_complete_report_dict(), _collection_error_events)
_collection_error["collected_node_ids"] = []
_collection_error["event_count"] = 3
_collection_error["pytest_exit_code"] = 2
_collection_error["integrity_digest"] = recompute_report_digest(_collection_error)
_matrix_case("collection-error-with-session-error", _collection_error)

_session_error_no_exception_events = [
    _event(1, "SESSION_START"),
    _event(2, "SESSION_ERROR"),
    _event(3, "SESSION_END"),
]
_session_error_no_exception = _with_events(
    _complete_report_dict(), _session_error_no_exception_events
)
_session_error_no_exception["collected_node_ids"] = []
_session_error_no_exception["event_count"] = 3
_session_error_no_exception["pytest_exit_code"] = 2
_session_error_no_exception["integrity_digest"] = recompute_report_digest(
    _session_error_no_exception
)
_matrix_case("session-error-without-exception", _session_error_no_exception)

_over_limit = _complete_report_dict()
_over_limit["event_count"] = 6
_over_limit["integrity_digest"] = recompute_report_digest(_over_limit)
_matrix_case(
    "over-limit-events",
    _over_limit,
    PytestReportExpectationV1(
        schema_version=1,
        run_kind="FULL_PYTEST",
        planned_node_ids=_PLANNED,
        report_plugin_version=_PLUGIN_VERSION,
        max_events=5,
    ),
)

_run_kind_mismatch = _complete_report_dict()
_run_kind_mismatch["integrity_digest"] = recompute_report_digest(_run_kind_mismatch)
_matrix_case(
    "run-kind-mismatch",
    _run_kind_mismatch,
    PytestReportExpectationV1(
        schema_version=1,
        run_kind="TARGET_TESTS",
        planned_node_ids=_PLANNED,
        report_plugin_version=_PLUGIN_VERSION,
    ),
)

_plugin_version_mismatch = _complete_report_dict()
_plugin_version_mismatch["integrity_digest"] = recompute_report_digest(
    _plugin_version_mismatch
)
_matrix_case(
    "plugin-version-mismatch",
    _plugin_version_mismatch,
    PytestReportExpectationV1(
        schema_version=1,
        run_kind="FULL_PYTEST",
        planned_node_ids=_PLANNED,
        report_plugin_version="2",
    ),
)

_planned_mismatch = _complete_report_dict()
_planned_mismatch["integrity_digest"] = recompute_report_digest(_planned_mismatch)
_matrix_case(
    "planned-node-ids-mismatch",
    _planned_mismatch,
    PytestReportExpectationV1(
        schema_version=1,
        run_kind="FULL_PYTEST",
        planned_node_ids=(_NODE_ADD,),
        report_plugin_version=_PLUGIN_VERSION,
    ),
)


@pytest.mark.parametrize(
    "case_id, report, expectation",
    _MATRIX_CASES,
)
def test_pytest_report_corruption_matrix(
    case_id: str,
    report: dict[str, object],
    expectation: PytestReportExpectationV1 | None,
) -> None:
    """Every closed rejection row of the report contract."""
    outcome = parse_pytest_evidence(
        canonical_json_bytes(report),
        expectation if expectation is not None else expected_full_pytest_report(),
    )
    if case_id == "complete-valid-report":
        assert outcome.error_code is None
        assert outcome.evidence is not None
    else:
        assert outcome.error_code == "REPORTER_INVALID", case_id
        assert outcome.evidence is None, case_id


def test_parse_rejects_empty_raw_bytes() -> None:
    outcome = parse_pytest_evidence(b"", expected_full_pytest_report())
    assert outcome.error_code == "REPORTER_INVALID"
    assert outcome.evidence is None


def test_parse_rejects_non_utf8_raw_bytes() -> None:
    outcome = parse_pytest_evidence(b"\xff\xfe\x00", expected_full_pytest_report())
    assert outcome.error_code == "REPORTER_INVALID"


def test_parse_rejects_corrupt_json() -> None:
    outcome = parse_pytest_evidence(b'{"events": [', expected_full_pytest_report())
    assert outcome.error_code == "REPORTER_INVALID"


def test_parse_rejects_console_text_without_channel(
    complete_pytest_report_dict: dict[str, object],
) -> None:
    raw = (
        b"============================ test session starts ============================\n"
        b"1 failed in 0.06s\n"
    )
    outcome = parse_pytest_evidence(raw, expected_full_pytest_report())
    assert outcome.error_code == "REPORTER_INVALID"


def test_parse_extracts_channel_from_interleaved_console_text(
    complete_pytest_report_dict: dict[str, object],
) -> None:
    document = canonical_json_bytes(complete_pytest_report_dict)
    raw = b"FGATEEV1:" + document + b"[100%]" + b"\n" + b"1 failed in 0.06s\n"
    outcome = parse_pytest_evidence(raw, expected_full_pytest_report())
    assert outcome.error_code is None
    assert outcome.evidence is not None


def test_parse_rejects_duplicate_channel_documents(
    complete_pytest_report_dict: dict[str, object],
) -> None:
    document = canonical_json_bytes(complete_pytest_report_dict)
    raw = b"GATEEV1:" + document + b"\nGATEEV1:" + document + b"\n"
    outcome = parse_pytest_evidence(raw, expected_full_pytest_report())
    assert outcome.error_code == "REPORTER_INVALID"


def test_parse_ignores_non_report_gateev1_console_lines(
    complete_pytest_report_dict: dict[str, object],
) -> None:
    document = canonical_json_bytes(complete_pytest_report_dict)
    raw = b"GATEEV1:user printed something\n" + b"GATEEV1:" + document + b"\n"
    outcome = parse_pytest_evidence(raw, expected_full_pytest_report())
    assert outcome.error_code is None
    assert outcome.evidence is not None

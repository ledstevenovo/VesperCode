"""T30.2 legacy step 30.D: bounded Demo session limit tests.

The runner enforces the in-memory five-minute, 20-action, and
10-concurrent session limits plus explicit reset/expiry and no recovery
(card GREEN-2): every rejection is a closed ``DemoAdvanceErrorV1`` with a
stable code, fires before any action, only affects the one session, and
never creates a recovery protocol (SPEC §5.1/§4.9).  The 20-action bound
cannot be reached by the six-step fixed scenario, so the limit test
advances a synthetic closed scenario (T30.1 types) to the bound.
"""

from __future__ import annotations

from typing import Final, Literal

import pytest

pytest.importorskip("pydantic")

from src.vespercode.canonical.clock import FakeClockV1
from src.vespercode.canonical.timestamp_v1 import CanonicalTimestampV1
from src.vespercode.contracts.evidence import DigestV1
from src.vespercode.contracts.optional import AbsentV1
from src.vespercode.demo.runner import (
    DEMO_MAX_ACTIONS_V1,
    DEMO_MAX_SESSIONS_V1,
    DEMO_SESSION_TTL_MILLISECONDS_V1,
    DemoAdvanceErrorV1,
    DemoScenarioRunner,
)
from src.vespercode.demo.scenario import FIXED_DEMO_SCENARIO_V1
from src.vespercode.demo.types import (
    DemoDecisionV1,
    DemoScenarioV1,
    DemoStepResultV1,
    DemoTraceV1,
)

_CLOCK_EPOCH = CanonicalTimestampV1("2026-08-06T09:00:00.000Z").epoch_milliseconds
_FIXED_DIGEST: Final = "ab" * 32
_FIXED_DECISION_TS = CanonicalTimestampV1("2026-08-05T09:30:15.000Z")


def _decision(choice: Literal["APPROVE", "REJECT"]) -> DemoDecisionV1:
    return DemoDecisionV1(
        demo_session_id="demo-session-v1",
        subject_digest=DigestV1(value=_FIXED_DIGEST),
        decision=choice,
        created_at=_FIXED_DECISION_TS,
    )


def _fresh_runner(
    scenario: DemoScenarioV1 = FIXED_DEMO_SCENARIO_V1,
) -> DemoScenarioRunner:
    return DemoScenarioRunner(clock=FakeClockV1(_CLOCK_EPOCH), scenario=scenario)


def _synthetic_long_scenario() -> DemoScenarioV1:
    """One synthetic closed scenario of 21 model-action steps.

    The 20-action bound cannot be reached by the six-step fixed scenario;
    the synthetic scenario (arbitrary-but-frozen closed T30.1 data)
    drives the runner to the exact limit so the enforcement fires.
    """
    steps = tuple(
        DemoStepResultV1(
            step_index=index,
            action_label="RUN_CHECK FULL_PYTEST",
            outcome="COMPLETED",
            status="DEMO_RUNNING",
            decision=AbsentV1(kind="ABSENT"),
        )
        for index in range(DEMO_MAX_ACTIONS_V1 + 1)
    )
    return DemoScenarioV1(
        scenario_id="synthetic-limit-v1",
        scenario_version=1,
        input_kinds=("FIXED_SOURCE", "FIXED_FAILURE", "FIXED_PATCH"),
        source="synthetic fixed source",
        injected_failure="tests/test_example.py::test_example_success",
        expected_patch=(
            "--- a/src/example.py\n"
            "+++ b/src/example.py\n"
            "@@ -1,2 +1,2 @@\n"
            " def example():\n"
            "-    return 0\n"
            "+    return 1\n"
        ),
        decisions=(),
        statuses=("DEMO_CREATED", "DEMO_RUNNING", "DEMO_COMPLETED"),
        trace=DemoTraceV1(scenario_id="synthetic-limit-v1", steps=steps),
    )


def test_five_minute_expiry_rejects_before_any_action() -> None:
    """A session expires five minutes after creation: the next advance
    rejects closed before any action, and only that session is affected
    (no recovery protocol)."""
    clock = FakeClockV1(_CLOCK_EPOCH)
    runner = DemoScenarioRunner(clock=clock)
    session = runner.create_session("expiry-session")
    assert DEMO_SESSION_TTL_MILLISECONDS_V1 == 300_000
    clock.advance(DEMO_SESSION_TTL_MILLISECONDS_V1)
    with pytest.raises(DemoAdvanceErrorV1) as expired:
        runner.advance(session, None)
    assert expired.value.error_code == "DEMO_SESSION_EXPIRED"
    # The session is dead only for itself: other sessions still advance.
    clock.advance(-DEMO_SESSION_TTL_MILLISECONDS_V1)
    other = runner.create_session("expiry-other")
    clock.advance(DEMO_SESSION_TTL_MILLISECONDS_V1 // 2)
    runner.advance(other, None)


def test_twenty_action_limit_stops_before_the_action() -> None:
    """At most 20 actions per session: the 21st advance is rejected closed
    before any action (SPEC §5.1)."""
    runner = _fresh_runner(_synthetic_long_scenario())
    session = runner.create_session("limit-session")
    for _ in range(DEMO_MAX_ACTIONS_V1):
        runner.advance(session, None)
        session = runner.session("limit-session")
    with pytest.raises(DemoAdvanceErrorV1) as limited:
        runner.advance(session, None)
    assert limited.value.error_code == "DEMO_ACTION_LIMIT"


def test_ten_concurrent_sessions_cap() -> None:
    """The process-level concurrency cap is 10: the 11th concurrent
    session is rejected closed."""
    runner = _fresh_runner()
    for index in range(DEMO_MAX_SESSIONS_V1):
        runner.create_session(f"concurrent-{index}")
    with pytest.raises(DemoAdvanceErrorV1) as capped:
        runner.create_session("concurrent-10")
    assert capped.value.error_code == "DEMO_SESSION_LIMIT"
    # A dropped session frees a slot.
    runner.reset_session("concurrent-0")
    runner.create_session("concurrent-10")


def test_explicit_reset_discards_the_session() -> None:
    """An explicit reset drops only that session: later advances reject
    as unknown, and the failure never creates a recovery protocol."""
    runner = _fresh_runner()
    session = runner.create_session("reset-session")
    runner.reset_session("reset-session")
    with pytest.raises(DemoAdvanceErrorV1) as unknown:
        runner.advance(session, None)
    assert unknown.value.error_code == "DEMO_SESSION_NOT_FOUND"
    with pytest.raises(DemoAdvanceErrorV1) as missing:
        runner.reset_session("reset-session")
    assert missing.value.error_code == "DEMO_SESSION_NOT_FOUND"


def test_duplicate_and_stale_sessions_reject_closed() -> None:
    """A duplicate session id and a stale session value both reject
    closed with stable codes (the state digest binds the exact state)."""
    runner = _fresh_runner()
    runner.create_session("identity-session")
    with pytest.raises(DemoAdvanceErrorV1) as duplicate:
        runner.create_session("identity-session")
    assert duplicate.value.error_code == "DEMO_SESSION_ID_EXISTS"

    session = runner.create_session("stale-session")
    runner.advance(session, None)
    current = runner.session("stale-session")
    assert current != session
    with pytest.raises(DemoAdvanceErrorV1) as stale:
        runner.advance(session, None)
    assert stale.value.error_code == "DEMO_STATE_MISMATCH"


def test_scenario_trace_end_rejects_closed() -> None:
    """A scenario whose trace ends before the session state rejects
    closed instead of raising a raw IndexError (the M3 fail-closed
    pin)."""
    one_step = DemoScenarioV1(
        scenario_id="synthetic-short-v1",
        scenario_version=1,
        input_kinds=("FIXED_SOURCE", "FIXED_FAILURE", "FIXED_PATCH"),
        source="synthetic fixed source",
        injected_failure="tests/test_example.py::test_example_success",
        expected_patch=(
            "--- a/src/example.py\n"
            "+++ b/src/example.py\n"
            "@@ -1,2 +1,2 @@\n"
            " def example():\n"
            "-    return 0\n"
            "+    return 1\n"
        ),
        decisions=(),
        statuses=("DEMO_CREATED", "DEMO_RUNNING", "DEMO_COMPLETED"),
        trace=DemoTraceV1(
            scenario_id="synthetic-short-v1",
            steps=(
                DemoStepResultV1(
                    step_index=0,
                    action_label="RUN_CHECK FULL_PYTEST",
                    outcome="COMPLETED",
                    status="DEMO_RUNNING",
                    decision=AbsentV1(kind="ABSENT"),
                ),
            ),
        ),
    )
    runner = _fresh_runner(one_step)
    session = runner.create_session("short-session")
    runner.advance(session, None)
    session = runner.session("short-session")
    with pytest.raises(DemoAdvanceErrorV1) as ended:
        runner.advance(session, None)
    assert ended.value.error_code == "DEMO_STATE_MISMATCH"


def test_unknown_feedback_kind_rejects_closed() -> None:
    """A feedback row of an unknown kind fails closed during the
    rehydration instead of rehydrating as a wrong record (the M2
    fail-closed pin; the schema's CHECK constraint makes the branch
    defensive, so the pin drives the private mapping directly)."""
    from typing import Any, cast

    from src.vespercode.demo.runner import _rehydrate_feedback_row

    bogus_row = cast(
        Any,
        {
            "feedback_id": "bogus-row",
            "kind": "BOGUS",
            "severity": "CRITICAL",
            "created_at": "2026-08-07T09:00:00.000Z",
            "summary": "bogus",
            "source_ref": "{}",
            "bounded_payload": "{}",
            "evidence_refs": "[]",
            "consumed_by_turn_id": None,
        },
    )
    with pytest.raises(DemoAdvanceErrorV1) as unknown:
        _rehydrate_feedback_row(bogus_row)
    assert unknown.value.error_code == "DEMO_STATE_MISMATCH"


def test_writeback_decision_gates_reject_closed() -> None:
    """The FINAL_WRITEBACK steps advance only through the exact fixed
    decision; missing and wrong decisions reject closed and never form a
    formal approval."""
    runner = _fresh_runner()
    session = runner.create_session("gate-session")
    for _ in range(4):
        runner.advance(session, None)
        session = runner.session("gate-session")
    with pytest.raises(DemoAdvanceErrorV1) as missing:
        runner.advance(session, None)
    assert missing.value.error_code == "DEMO_DECISION_REQUIRED"
    with pytest.raises(DemoAdvanceErrorV1) as wrong:
        runner.advance(session, _decision("APPROVE"))
    assert wrong.value.error_code == "DEMO_DECISION_MISMATCH"

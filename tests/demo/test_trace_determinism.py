"""T30.2 legacy step 30.D: fixed repeated Demo trace determinism tests.

The fixed Mock scenario must produce the identical canonical trace across
separate runners and repeated full runs (SPEC §5.2 NFR-REL, AC-09): the
same scenario version, inputs, and visitor decisions produce the same key
states and action sequence, the emitted steps equal the fixed scenario
trace, and the session lifecycle is deterministic.  A completed session
is discarded (SPEC §4.9), so the step results are the only lasting trace.
"""

from __future__ import annotations

from typing import Final, Literal

import pytest

pytest.importorskip("pydantic")

from src.vespercode.canonical.clock import FakeClockV1
from src.vespercode.canonical.timestamp_v1 import CanonicalTimestampV1
from src.vespercode.contracts.evidence import DigestV1
from src.vespercode.demo.runner import (
    DemoAdvanceErrorV1,
    DemoScenarioRunner,
)
from src.vespercode.demo.scenario import FIXED_DEMO_SCENARIO_V1
from src.vespercode.demo.types import DemoDecisionV1

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


def _full_trace(runner: DemoScenarioRunner, session_id: str) -> tuple[bytes, ...]:
    """Advance the whole fixed scenario and return the canonical trace."""
    session = runner.create_session(session_id)
    trace: list[bytes] = []
    for index in range(len(FIXED_DEMO_SCENARIO_V1.trace.steps)):
        decision = None
        if index == 4:
            decision = _decision("REJECT")
        elif index == 5:
            decision = _decision("APPROVE")
        result = runner.advance(session, decision)
        trace.append(result.step.to_canonical_bytes())
        if index < len(FIXED_DEMO_SCENARIO_V1.trace.steps) - 1:
            session = runner.session(session_id)
    return tuple(trace)


def _fresh_runner() -> DemoScenarioRunner:
    return DemoScenarioRunner(clock=FakeClockV1(_CLOCK_EPOCH))


def test_fixed_trace_is_byte_identical_across_separate_runners() -> None:
    """Two independently constructed runners at the same fixed clock
    produce the identical canonical trace, equal to the fixed scenario
    trace (AC-09 determinism)."""
    first = _full_trace(_fresh_runner(), "determinism-run-1")
    second = _full_trace(_fresh_runner(), "determinism-run-2")
    assert first == second
    fixed = tuple(
        step.to_canonical_bytes() for step in FIXED_DEMO_SCENARIO_V1.trace.steps
    )
    assert first == fixed


def test_fixed_trace_is_byte_identical_across_repeated_runs() -> None:
    """Repeated full runs on one runner (fresh sessions) stay
    byte-identical (the feedback records replay deterministically)."""
    runner = _fresh_runner()
    first = _full_trace(runner, "repeat-run-1")
    second = _full_trace(runner, "repeat-run-2")
    assert first == second


def test_session_values_are_deterministic_and_completion_discards() -> None:
    """The created session value is deterministic across runners (the
    state digest binds the exact state), and a completed session is
    discarded: further advances and lookups reject closed."""
    first = _fresh_runner().create_session("session-v1")
    second = _fresh_runner().create_session("session-v1")
    assert first.to_canonical_bytes() == second.to_canonical_bytes()
    assert first.status == "DEMO_CREATED"

    runner = _fresh_runner()
    session = runner.create_session("session-v1")
    for index in range(4):
        runner.advance(session, None)
        session = runner.session("session-v1")
    rejected = runner.advance(session, _decision("REJECT"))
    assert rejected.step.status == "DEMO_WAITING_USER"
    session = runner.session("session-v1")
    assert session.status == "DEMO_WAITING_USER"
    completed = runner.advance(session, _decision("APPROVE"))
    assert completed.step.status == "DEMO_COMPLETED"
    with pytest.raises(DemoAdvanceErrorV1) as after_completion:
        runner.advance(session, None)
    assert after_completion.value.error_code == "DEMO_SESSION_NOT_FOUND"
    with pytest.raises(DemoAdvanceErrorV1) as lookup:
        runner.session("session-v1")
    assert lookup.value.error_code == "DEMO_SESSION_NOT_FOUND"
    # The in-memory-only lifecycle: no formal Run row exists and no
    # recovery state was ever created.
    assert runner.database.read_rows("SELECT COUNT(*) FROM runs")[0][0] == 0


def test_stop_decision_is_continu_e_for_the_fixed_scenario() -> None:
    """The real shared stop evaluation keeps the fixed scenario running:
    every advance returns the CONTINUE verdict (the demo's own bounds
    reject before any action, and the frozen limits are never reached by
    the six fixed steps)."""
    runner = _fresh_runner()
    session = runner.create_session("continue-run")
    for index in range(4):
        result = runner.advance(session, None)
        assert result.stop_decision == "CONTINUE"
        session = runner.session("continue-run")
    result = runner.advance(session, _decision("REJECT"))
    assert result.stop_decision == "CONTINUE"
    session = runner.session("continue-run")
    result = runner.advance(session, _decision("APPROVE"))
    assert result.stop_decision == "CONTINUE"

"""T32.1 legacy step 32.B: semantic-determinism mechanism trace tests.

Repeated mechanism runs are semantically deterministic: two fresh
offline runs (the once-only run contract) produce byte-identical stage
traces, identical bounded reports, and identical content-addressed and
semantic digests, and the fixed Demo trace is byte-identical across
repeated scenario executions (SPEC §5.2/AC-09).  The trace binds no
volatile field (no action id, turn id, record id, or timestamp), so the
canonical form is the semantic form.
"""

from __future__ import annotations

import pytest

pytest.importorskip("pydantic")

from vespercode.canonical.clock import FakeClockV1
from vespercode.canonical.timestamp_v1 import CanonicalTimestampV1
from vespercode.demo.runner import DemoScenarioRunner
from vespercode.demo.scenario import FIXED_DEMO_SCENARIO_V1

from scripts.run_mechanism_demo import MechanismHarness


@pytest.fixture
def mechanism_harness() -> MechanismHarness:
    return MechanismHarness()


def _full_demo_trace(runner: DemoScenarioRunner, session_id: str) -> tuple[bytes, ...]:
    """Advance the whole fixed Demo scenario and return the canonical
    step results (the fixed writeback decisions drive steps 4 and 5)."""
    session = runner.create_session(session_id)
    trace: list[bytes] = []
    for index in range(len(FIXED_DEMO_SCENARIO_V1.trace.steps)):
        decision = None
        if index == 4:
            decision = FIXED_DEMO_SCENARIO_V1.decisions[0]
        elif index == 5:
            decision = FIXED_DEMO_SCENARIO_V1.decisions[1]
        result = runner.advance(session, decision)
        trace.append(result.step.to_canonical_bytes())
        if index < len(FIXED_DEMO_SCENARIO_V1.trace.steps) - 1:
            session = runner.session(session_id)
    return tuple(trace)


def test_repeated_mechanism_runs_are_semantically_identical(
    mechanism_harness: MechanismHarness,
) -> None:
    first = mechanism_harness.run()
    second = MechanismHarness().run()
    assert second.trace.stages == first.trace.stages
    assert second.report_text == first.report_text
    assert second.report_byte_count == first.report_byte_count
    assert second.report_digest == first.report_digest
    assert second.trace.trace_id == first.trace.trace_id
    assert second.trace.digest == first.trace.digest
    assert second.semantic_digest == first.semantic_digest
    # The trace binds no declared volatile field: every stage's canonical
    # serialization is byte-stable across the two runs (the quality-review
    # M1 pin: a cross-run comparison, never a self-comparison).
    for first_stage, second_stage in zip(first.trace.stages, second.trace.stages):
        assert second_stage.model_dump(exclude_none=True) == first_stage.model_dump(
            exclude_none=True
        )


def test_repeated_feedback_recovery_traces_are_identical(
    mechanism_harness: MechanismHarness,
) -> None:
    first = mechanism_harness.run_feedback_recovery()
    second = MechanismHarness().run_feedback_recovery()
    assert second == first
    assert second.first_action_digest == first.first_action_digest
    assert second.corrective_action_digest == first.corrective_action_digest
    assert second.feedback_consumption_count == 1


def test_repeated_demo_trace_is_byte_identical() -> None:
    clock = FakeClockV1(
        CanonicalTimestampV1("2026-08-07T09:00:00.000Z").epoch_milliseconds
    )
    first = _full_demo_trace(DemoScenarioRunner(clock=clock), "determinism-run-1")
    second = _full_demo_trace(DemoScenarioRunner(clock=clock), "determinism-run-2")
    assert second == first
    assert first == tuple(
        step.to_canonical_bytes() for step in FIXED_DEMO_SCENARIO_V1.trace.steps
    )

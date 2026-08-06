"""T25.3 legacy step 25.A: pure stop decision tests.

The exact RED test pins the repetition-boundary decision (three
identical semantic results on the same candidate stop with
``REPEATED_ACTION_LIMIT``); the matrix pins the exact closed precedence
table of the 25.A Expected line — each configured turn/call/repetition/
no-progress/deadline/cancel/completion boundary stops on the exact
limit, one-below-limit continues, the smaller applicable deadline wins,
and the precedence order is deterministic (SPEC §4.2.6/§4.2.8, Registry
row 25.A).
"""

from __future__ import annotations

import pytest

# The evaluators consume pydantic runtime contracts; the hash-locked gate
# toolchain installs no runtime dependencies, so this module skips
# cleanly there (formal env runs it fully).
pytest.importorskip("pydantic")

from src.vespercode.canonical.timestamp_v1 import CanonicalTimestampV1
from src.vespercode.loop.progress import ProgressDecisionV1
from src.vespercode.loop.stopping import (
    ContinueV1,
    LoopEvidenceV1,
    RunLoopStateV1,
    StopEvaluator,
    StopV1,
    ValidateV1,
)

_RUN_DEADLINE = CanonicalTimestampV1("2026-08-06T09:15:00.000Z")
_NOW = CanonicalTimestampV1("2026-08-06T09:02:00.000Z")
_WAIT_DEADLINE = CanonicalTimestampV1("2026-08-06T09:05:00.000Z")


def state_with_same_action_digest(repetitions: int = 3) -> RunLoopStateV1:
    """One run-loop state with room for the repetition boundary."""
    return RunLoopStateV1(
        turn_count=repetitions,
        call_count=repetitions,
        max_turns=20,
        max_llm_calls=20,
        run_deadline=_RUN_DEADLINE,
        wait_deadline=None,
    )


def loop_evidence(state: RunLoopStateV1) -> LoopEvidenceV1:
    """One neutral step evidence for the given state."""
    return LoopEvidenceV1(completion_requested=False, cancellation_honored=False)


def no_progress_decision(state: RunLoopStateV1) -> ProgressDecisionV1:
    """One progress decision carrying the exact repetition streak."""
    return ProgressDecisionV1(
        has_progress=False,
        consecutive_no_progress_turns=state.turn_count - 1,
        consecutive_repeated_semantic=state.turn_count,
        consecutive_invalid_outputs=0,
    )


def current_time(state: RunLoopStateV1) -> CanonicalTimestampV1:
    """The explicit current time (25.A: clock values are explicit inputs)."""
    return _NOW


def test_repeated_semantic_action_stops_at_exact_limit() -> None:
    state = state_with_same_action_digest(repetitions=3)
    decision = StopEvaluator().evaluate(
        state,
        loop_evidence(state),
        no_progress_decision(state),
        current_time(state),
    )
    assert isinstance(decision, StopV1)
    assert decision.reason == "REPEATED_ACTION_LIMIT"


def test_stop_progress_boundary_matrix() -> None:
    """PLAN Registry row 25.A: the exact stop/progress boundary matrix.

    Per the SPEC_PROCESS 49 precedent the card Expected line is the
    operative matrix authority: each configured boundary stops on the
    exact limit, one-below-limit continues, and the smaller applicable
    deadline wins.
    """
    evaluator = StopEvaluator()

    def decide(
        *,
        turn_count: int = 0,
        call_count: int = 0,
        max_turns: int = 20,
        max_llm_calls: int = 20,
        run_deadline: CanonicalTimestampV1 = _RUN_DEADLINE,
        wait_deadline: CanonicalTimestampV1 | None = None,
        now: CanonicalTimestampV1 = _NOW,
        progress: ProgressDecisionV1 | None = None,
        completion_requested: bool = False,
        cancellation_honored: bool = False,
    ) -> StopV1 | ContinueV1 | ValidateV1:
        state = RunLoopStateV1(
            turn_count=turn_count,
            call_count=call_count,
            max_turns=max_turns,
            max_llm_calls=max_llm_calls,
            run_deadline=run_deadline,
            wait_deadline=wait_deadline,
        )
        if progress is None:
            progress = ProgressDecisionV1(
                has_progress=False,
                consecutive_no_progress_turns=0,
                consecutive_repeated_semantic=0,
                consecutive_invalid_outputs=0,
            )
        return evaluator.evaluate(
            state,
            LoopEvidenceV1(
                completion_requested=completion_requested,
                cancellation_honored=cancellation_honored,
            ),
            progress,
            now,
        )

    # --- Repetition: one-below-limit continues; the exact limit stops. ---
    below = decide(
        turn_count=2,
        progress=ProgressDecisionV1(
            has_progress=False,
            consecutive_no_progress_turns=1,
            consecutive_repeated_semantic=2,
            consecutive_invalid_outputs=0,
        ),
    )
    assert isinstance(below, ContinueV1)
    exact = decide(
        turn_count=3,
        progress=ProgressDecisionV1(
            has_progress=False,
            consecutive_no_progress_turns=2,
            consecutive_repeated_semantic=3,
            consecutive_invalid_outputs=0,
        ),
    )
    assert isinstance(exact, StopV1)
    assert exact.reason == "REPEATED_ACTION_LIMIT"

    # --- No progress: the exact 6-turn limit stops, 5 continues. ---
    five = decide(
        turn_count=5,
        progress=ProgressDecisionV1(
            has_progress=False,
            consecutive_no_progress_turns=5,
            consecutive_repeated_semantic=0,
            consecutive_invalid_outputs=0,
        ),
    )
    assert isinstance(five, ContinueV1)
    six = decide(
        turn_count=6,
        progress=ProgressDecisionV1(
            has_progress=False,
            consecutive_no_progress_turns=6,
            consecutive_repeated_semantic=0,
            consecutive_invalid_outputs=0,
        ),
    )
    assert isinstance(six, StopV1)
    assert six.reason == "NO_PROGRESS_LIMIT"

    # --- Invalid output: one continues, the exact two-stop limit stops. ---
    one = decide(
        turn_count=1,
        progress=ProgressDecisionV1(
            has_progress=False,
            consecutive_no_progress_turns=1,
            consecutive_repeated_semantic=0,
            consecutive_invalid_outputs=1,
        ),
    )
    assert isinstance(one, ContinueV1)
    two = decide(
        turn_count=2,
        progress=ProgressDecisionV1(
            has_progress=False,
            consecutive_no_progress_turns=2,
            consecutive_repeated_semantic=0,
            consecutive_invalid_outputs=2,
        ),
    )
    assert isinstance(two, StopV1)
    assert two.reason == "MODEL_OUTPUT_INVALID_LIMIT"

    # --- Turn/call budget: one-below-limit continues, the exact cap stops. ---
    below_turn = decide(turn_count=2, call_count=2, max_turns=3, max_llm_calls=20)
    assert isinstance(below_turn, ContinueV1)
    at_turn = decide(turn_count=3, call_count=3, max_turns=3, max_llm_calls=20)
    assert isinstance(at_turn, StopV1)
    assert at_turn.reason == "TURN_BUDGET_EXHAUSTED"
    at_call = decide(turn_count=2, call_count=3, max_turns=20, max_llm_calls=3)
    assert isinstance(at_call, StopV1)
    assert at_call.reason == "CALL_BUDGET_EXHAUSTED"
    # Both caps exhausted at once: the closed precedence names the turn cap.
    both = decide(turn_count=3, call_count=3, max_turns=3, max_llm_calls=3)
    assert isinstance(both, StopV1)
    assert both.reason == "TURN_BUDGET_EXHAUSTED"

    # --- Deadline: before continues, at the run deadline stops. ---
    before = decide(now=CanonicalTimestampV1("2026-08-06T09:14:59.000Z"))
    assert isinstance(before, ContinueV1)
    at_deadline = decide(now=_RUN_DEADLINE)
    assert isinstance(at_deadline, StopV1)
    assert at_deadline.reason == "WALL_CLOCK_DEADLINE_EXCEEDED"

    # --- The smaller applicable deadline wins over the run deadline. ---
    wait_first = decide(
        now=CanonicalTimestampV1("2026-08-06T09:05:00.000Z"),
        wait_deadline=_WAIT_DEADLINE,
    )
    assert isinstance(wait_first, StopV1)
    assert wait_first.reason == "WALL_CLOCK_DEADLINE_EXCEEDED"
    wait_later = decide(
        now=CanonicalTimestampV1("2026-08-06T09:04:59.000Z"),
        wait_deadline=_WAIT_DEADLINE,
    )
    assert isinstance(wait_later, ContinueV1)

    # --- Cancellation: only when honored at a deterministic safe point. ---
    cancel = decide(cancellation_honored=True)
    assert isinstance(cancel, StopV1)
    assert cancel.reason == "CANCELLED"
    no_cancel = decide(cancellation_honored=False)
    assert isinstance(no_cancel, ContinueV1)

    # --- Completion: the declared VALIDATE boundary, never SUCCEEDED. ---
    validate = decide(completion_requested=True)
    assert isinstance(validate, ValidateV1)
    # The completion at the exact turn cap still validates: validation
    # entry consumes no agent turn/call, so VALIDATE precedes the budget
    # rows in the closed table.
    at_cap_completion = decide(
        turn_count=3,
        call_count=3,
        max_turns=3,
        max_llm_calls=3,
        completion_requested=True,
    )
    assert isinstance(at_cap_completion, ValidateV1)

    # --- Precedence pins: the user cancel and the exact limits win. ---
    cancel_over_limit = decide(
        turn_count=3,
        max_turns=3,
        progress=ProgressDecisionV1(
            has_progress=False,
            consecutive_no_progress_turns=2,
            consecutive_repeated_semantic=3,
            consecutive_invalid_outputs=0,
        ),
        cancellation_honored=True,
    )
    assert isinstance(cancel_over_limit, StopV1)
    assert cancel_over_limit.reason == "CANCELLED"
    repetition_over_budget = decide(
        turn_count=3,
        call_count=3,
        max_turns=3,
        max_llm_calls=3,
        progress=ProgressDecisionV1(
            has_progress=False,
            consecutive_no_progress_turns=2,
            consecutive_repeated_semantic=3,
            consecutive_invalid_outputs=0,
        ),
    )
    assert isinstance(repetition_over_budget, StopV1)
    assert repetition_over_budget.reason == "REPEATED_ACTION_LIMIT"
    invalid_over_repetition = decide(
        turn_count=2,
        progress=ProgressDecisionV1(
            has_progress=False,
            consecutive_no_progress_turns=2,
            consecutive_repeated_semantic=3,
            consecutive_invalid_outputs=2,
        ),
    )
    assert isinstance(invalid_over_repetition, StopV1)
    assert invalid_over_repetition.reason == "MODEL_OUTPUT_INVALID_LIMIT"
    no_progress_over_repetition = decide(
        turn_count=6,
        progress=ProgressDecisionV1(
            has_progress=False,
            consecutive_no_progress_turns=6,
            consecutive_repeated_semantic=3,
            consecutive_invalid_outputs=0,
        ),
    )
    assert isinstance(no_progress_over_repetition, StopV1)
    # The repetition streak fires at 3 before the no-progress streak at 6.
    assert no_progress_over_repetition.reason == "REPEATED_ACTION_LIMIT"

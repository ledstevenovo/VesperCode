"""T32.1 legacy step 32.B: feedback-recovery mechanism trace tests.

The exact displayed RED test ``test_failed_check_feedback_changes_next_action_once``
is copied from the T32.1 card.  The already-RED matrix test
``test_mechanism_feedback_recovery_matrix`` pins the PLAN 32.B row: the
injected check failure is consumed once and changes the next action;
stale/tampered feedback is rejected; continuation/repetition limits
hold; the final report binds both attempts.
"""

from __future__ import annotations

import pytest

pytest.importorskip("pydantic")

from src.vespercode.loop.feedback_consumption import (
    FeedbackRepositoryV1,
    consume_feedback,
)

from scripts.run_mechanism_demo import MechanismHarness


@pytest.fixture
def mechanism_harness() -> MechanismHarness:
    return MechanismHarness()


def test_failed_check_feedback_changes_next_action_once(
    mechanism_harness: MechanismHarness,
) -> None:
    trace = mechanism_harness.run_feedback_recovery()
    assert trace.first_action_digest != trace.corrective_action_digest
    assert trace.feedback_consumption_count == 1


def test_mechanism_feedback_recovery_matrix(
    mechanism_harness: MechanismHarness,
) -> None:
    """PLAN 32.B row: injected check failure is consumed once and
    changes the next action; stale/tampered feedback is rejected;
    continuation/repetition limits hold; final report binds both
    attempts.
    """
    trace = mechanism_harness.run_feedback_recovery()
    assert trace.first_action_digest != trace.corrective_action_digest
    assert trace.feedback_consumption_count == 1
    # The final report binds both attempts: the fresh run's
    # feedback-correction stage records the same two digests and the
    # same one-time consumption.
    result = MechanismHarness().run()
    by_id = {stage.step_id: stage for stage in result.trace.stages}
    feedback_stage = by_id["feedback-correction"]
    assert feedback_stage.first_action_digest == trace.first_action_digest
    assert feedback_stage.corrective_action_digest == trace.corrective_action_digest
    assert feedback_stage.feedback_consumption_count == 1
    # Stale/tampered feedback is rejected: a forged reference against a
    # real turn consumes zero records (production Task 24.C).
    repository = FeedbackRepositoryV1(mechanism_harness.database)
    forged = consume_feedback("mechanism-turn-1", ("forged-feedback-ref",), repository)
    assert forged.kind == "MISSING_REF"
    assert forged.consumed_refs == ()
    # Continuation/repetition limits hold: the fixed paged continuation
    # stage records exact equivalence and zero-payload tamper/stale
    # codes, and repeated runs are semantically identical.
    continuation = by_id["paged-continuation"]
    assert continuation.paged_list_equivalence is True
    assert continuation.paged_search_equivalence is True
    assert continuation.tamper_error_code == "CONTINUATION_INVALID"
    assert continuation.stale_error_code == "CONTINUATION_STALE"
    repeated = MechanismHarness().run()
    assert repeated.trace.stages == result.trace.stages
    assert repeated.semantic_digest == result.semantic_digest

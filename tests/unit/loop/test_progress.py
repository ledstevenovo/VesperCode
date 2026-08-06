"""T25.3 legacy step 25.A: pure progress observation tests.

The ProgressEvaluator derives deterministic progress decisions from
immutable semantic action, candidate revision, check, and completion
evidence under exact bounded windows (GREEN-1): a ProgressMarker is a
candidate-tree digest change, a previously unseen semantic check result
for the current candidate, or the formal-validation entry; each declared
streak resets only on its declared condition (SPEC §4.2.6, Registry row
25.A).
"""

from __future__ import annotations

import pytest

# The evaluator consumes pydantic runtime contracts; the hash-locked gate
# toolchain installs no runtime dependencies, so this module skips
# cleanly there (formal env runs it fully).
pytest.importorskip("pydantic")

from pydantic import ValidationError

from src.vespercode.loop.progress import (
    MAX_PROGRESS_WINDOW_PRIORS_V1,
    ProgressEvaluator,
    ProgressObservationV1,
    ProgressWindowV1,
)

_CANDIDATE_A = "a" * 64
_CANDIDATE_B = "b" * 64
_ACTION_1 = "c" * 64
_ACTION_2 = "d" * 64
_RESULT_1 = "e" * 64
_RESULT_2 = "f" * 64
_CHECK_1 = "1" * 64
_CHECK_2 = "2" * 64


def obs(
    turn_index: int,
    candidate: str | None = _CANDIDATE_A,
    action: str | None = _ACTION_1,
    result: str | None = _RESULT_1,
    checks: tuple[str, ...] = (),
    invalid: bool = False,
    formal: bool = False,
) -> ProgressObservationV1:
    """One deterministic turn observation with bounded digests.

    An invalid output can never carry a semantic action or result (the
    closed observation contract), so the helper nulls them.
    """
    return ProgressObservationV1(
        turn_index=turn_index,
        candidate_digest=candidate,
        semantic_action_digest=None if invalid else action,
        semantic_result_digest=None if invalid else result,
        semantic_check_digests=checks,
        invalid_output=invalid,
        entered_formal_validation=formal,
    )


def decide(
    *prior: ProgressObservationV1,
    current: ProgressObservationV1,
) -> tuple[bool, int, int, int]:
    """Evaluate the window of priors plus the current observation."""
    decision = ProgressEvaluator().evaluate(
        ProgressWindowV1(turns=prior),
        current,
    )
    return (
        decision.has_progress,
        decision.consecutive_no_progress_turns,
        decision.consecutive_repeated_semantic,
        decision.consecutive_invalid_outputs,
    )


def test_candidate_change_is_a_progress_marker() -> None:
    progress, no_progress, _, _ = decide(
        obs(1, candidate=_CANDIDATE_A),
        current=obs(2, candidate=_CANDIDATE_B),
    )
    assert progress is True
    assert no_progress == 0
    # The same candidate is no marker.
    progress, no_progress, _, _ = decide(
        obs(1, candidate=_CANDIDATE_A),
        current=obs(2, candidate=_CANDIDATE_A),
    )
    assert progress is False
    assert no_progress == 2


def test_unseen_semantic_check_result_is_a_progress_marker() -> None:
    progress, no_progress, _, _ = decide(
        current=obs(1, checks=(_CHECK_1,)),
    )
    assert progress is True
    assert no_progress == 0
    # The identical check result on the next turn is not unseen; the
    # first turn's unseen check was itself a marker, so only the second
    # turn trails without a marker.
    progress, no_progress, _, _ = decide(
        obs(1, checks=(_CHECK_1,)),
        current=obs(2, checks=(_CHECK_1,)),
    )
    assert progress is False
    assert no_progress == 1
    # A new check result is a marker even when another check repeats.
    progress, no_progress, _, _ = decide(
        obs(1, checks=(_CHECK_1,)),
        current=obs(2, checks=(_CHECK_1, _CHECK_2)),
    )
    assert progress is True
    assert no_progress == 0


def test_formal_validation_entry_is_a_progress_marker() -> None:
    progress, no_progress, _, _ = decide(
        obs(1),
        obs(2),
        current=obs(3, formal=True),
    )
    assert progress is True
    assert no_progress == 0


def test_no_progress_streak_resets_only_on_a_marker() -> None:
    _, no_progress, _, _ = decide(
        obs(1),
        obs(2),
        current=obs(3),
    )
    assert no_progress == 3
    _, no_progress, _, _ = decide(
        obs(1),
        obs(2),
        obs(3),
        current=obs(4, candidate=_CANDIDATE_B),
    )
    assert no_progress == 0
    _, no_progress, _, _ = decide(
        obs(1),
        obs(2, candidate=_CANDIDATE_B),
        current=obs(3, candidate=_CANDIDATE_B),
    )
    # The candidate-change marker at turn 2 reset the streak; only turn
    # 3 trails without a marker.
    assert no_progress == 1


def test_repetition_streak_requires_same_candidate_action_and_result() -> None:
    _, _, repeated, _ = decide(
        obs(1, action=_ACTION_1, result=_RESULT_1),
        obs(2, action=_ACTION_1, result=_RESULT_1),
        current=obs(3, action=_ACTION_1, result=_RESULT_1),
    )
    assert repeated == 3
    # A changed semantic result breaks the chain.
    _, _, repeated, _ = decide(
        obs(1, action=_ACTION_1, result=_RESULT_1),
        current=obs(2, action=_ACTION_1, result=_RESULT_2),
    )
    assert repeated == 1
    # A changed action breaks the chain.
    _, _, repeated, _ = decide(
        obs(1, action=_ACTION_1, result=_RESULT_1),
        current=obs(2, action=_ACTION_2, result=_RESULT_1),
    )
    assert repeated == 1
    # A candidate change breaks the chain (same-candidate requirement).
    _, _, repeated, _ = decide(
        obs(1, candidate=_CANDIDATE_A, action=_ACTION_1, result=_RESULT_1),
        current=obs(2, candidate=_CANDIDATE_B, action=_ACTION_1, result=_RESULT_1),
    )
    assert repeated == 1
    # An invalid output carries no action and breaks the chain.
    _, _, repeated, _ = decide(
        obs(1, action=_ACTION_1, result=_RESULT_1),
        current=obs(2, invalid=True),
    )
    assert repeated == 0


def test_invalid_output_streak_resets_only_on_valid_output() -> None:
    _, _, _, invalid = decide(
        obs(1, invalid=True),
        current=obs(2, invalid=True),
    )
    assert invalid == 2
    _, _, _, invalid = decide(
        obs(1, invalid=True),
        obs(2, invalid=True),
        current=obs(3),
    )
    assert invalid == 0


def test_window_is_exactly_bounded() -> None:
    priors = tuple(obs(index) for index in range(1, MAX_PROGRESS_WINDOW_PRIORS_V1 + 1))
    # The exact bound is accepted.
    ProgressWindowV1(turns=priors)
    with pytest.raises(ValidationError):
        ProgressWindowV1(turns=priors + (obs(MAX_PROGRESS_WINDOW_PRIORS_V1 + 1),))

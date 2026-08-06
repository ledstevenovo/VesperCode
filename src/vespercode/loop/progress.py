"""T25.3 legacy step 25.A: pure progress observation under exact windows.

``ProgressEvaluator`` derives deterministic progress decisions from
immutable semantic action, candidate revision, feedback, check, and
completion evidence under exact bounded windows (GREEN-1): each turn's
``ProgressObservationV1`` binds the candidate digest the turn saw, the
dispatched action's semantic digest, the semantic result identity, the
semantic check-result identities, the invalid-output fact, and the
formal-validation entry fact; the evaluator recomputes every trailing
streak over the bounded window plus the current observation, so the same
window and observation always produce the same decision and the
declared counters reset only on their declared conditions (SPEC
§4.2.6, Registry row 25.A).  Stopping, wait, cancellation, repository,
LLM, dispatch, audit, and outer-loop effects remain out of scope
(GREEN-4).
"""

from __future__ import annotations

from typing import Annotated

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    Strict,
    StrictStr,
    field_validator,
    model_validator,
)

MAX_PROGRESS_WINDOW_PRIORS_V1 = 5
"""The exact bound of prior turn observations one evaluation needs.

The closed stop table (25.A GREEN-2) decides the 6-turn no-progress
limit from 5 prior observations plus the current one; every other
counter needs no more prior evidence (repetition 2 priors, invalid
output 1 prior).  The window is therefore bounded at 5 priors.
"""


def _require_digest(value: str | None) -> str | None:
    """One optional SHA-256 identity: 64 lowercase hex when present."""
    if value is None:
        return None
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise ValueError("digests must be exactly 64 lowercase hexadecimal characters")
    return value


class ProgressObservationV1(BaseModel):
    """One turn's immutable progress-relevant evidence (SPEC §4.2.6).

    The candidate digest is the digest the turn saw (the frozen step
    context binding); the semantic action digest and the semantic result
    identity are the dispatched action's ``semantic_digest`` and its
    result payload digest (both absent when nothing was dispatched);
    ``semantic_check_digests`` are the previously-unseen-check identities
    the turn produced; ``entered_formal_validation`` marks the completion
    step that requests the formal-validation entry.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)
    turn_index: Annotated[int, Strict(), Field(ge=1)]
    candidate_digest: StrictStr | None = None
    semantic_action_digest: StrictStr | None = None
    semantic_result_digest: StrictStr | None = None
    semantic_check_digests: tuple[StrictStr, ...] = ()
    invalid_output: bool
    entered_formal_validation: bool

    @field_validator(
        "candidate_digest", "semantic_action_digest", "semantic_result_digest"
    )
    @classmethod
    def _digests_have_exact_form(cls, value: str | None) -> str | None:
        return _require_digest(value)

    @field_validator("semantic_check_digests")
    @classmethod
    def _check_digests_have_exact_form(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        for digest in value:
            if (
                not isinstance(digest, str)
                or len(digest) != 64
                or any(character not in "0123456789abcdef" for character in digest)
            ):
                raise ValueError(
                    "check digests must be exactly 64 lowercase hexadecimal characters"
                )
        return value

    @model_validator(mode="after")
    def _invalid_output_carries_no_semantic_action(self) -> ProgressObservationV1:
        if self.invalid_output and (
            self.semantic_action_digest is not None
            or self.semantic_result_digest is not None
        ):
            raise ValueError("an invalid output carries no semantic action or result")
        return self


class ProgressWindowV1(BaseModel):
    """One bounded ordered window of prior turn observations (GREEN-1).

    ``turns`` holds the exact trailing prior observations (oldest first)
    that the evaluator combines with the current observation; a window
    beyond the exact bound is a construction error.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)
    turns: tuple[ProgressObservationV1, ...] = ()

    @model_validator(mode="after")
    def _window_is_exactly_bounded(self) -> ProgressWindowV1:
        if len(self.turns) > MAX_PROGRESS_WINDOW_PRIORS_V1:
            raise ValueError(
                "a progress window holds at most "
                f"{MAX_PROGRESS_WINDOW_PRIORS_V1} prior observations"
            )
        return self


class ProgressDecisionV1(BaseModel):
    """One closed progress verdict over the window (25.A GREEN-1/2).

    ``has_progress`` reports whether the current observation produced a
    ProgressMarker; the three streak counters are the exact trailing
    counts over the bounded window plus the observation, and each resets
    only on its declared condition: the no-progress streak resets on a
    marker, the repetition streak on a changed repetition key (candidate
    or semantic action+result), and the invalid-output streak on a valid
    output (SPEC §4.2.6, Registry row 25.A).
    """

    model_config = ConfigDict(extra="forbid", frozen=True)
    has_progress: bool
    consecutive_no_progress_turns: Annotated[int, Strict(), Field(ge=0)]
    consecutive_repeated_semantic: Annotated[int, Strict(), Field(ge=0)]
    consecutive_invalid_outputs: Annotated[int, Strict(), Field(ge=0)]


def _turn_is_marker(
    turns: tuple[ProgressObservationV1, ...],
    index: int,
) -> bool:
    """Whether turn ``index`` produced a ProgressMarker (SPEC §4.2.6).

    A marker is: a candidate-tree digest change against the previous
    turn (both digests known and different); a semantic check result
    never seen in any earlier turn; or the formal-validation entry.
    Candidate boundaries of ``None`` never count as a change.
    """
    turn = turns[index]
    if turn.entered_formal_validation:
        return True
    if index > 0:
        previous = turns[index - 1]
        if (
            turn.candidate_digest is not None
            and previous.candidate_digest is not None
            and turn.candidate_digest != previous.candidate_digest
        ):
            return True
    seen_before: set[str] = set()
    for earlier in turns[:index]:
        seen_before.update(earlier.semantic_check_digests)
    return any(digest not in seen_before for digest in turn.semantic_check_digests)


def _repetition_key(turn: ProgressObservationV1) -> tuple[str, str, str] | None:
    """The exact repetition key: (candidate, semantic action, result).

    ``None`` when no semantic action was dispatched (an invalid output
    or an undispatchable step can never repeat).
    """
    if (
        turn.semantic_action_digest is None
        or turn.semantic_result_digest is None
        or turn.candidate_digest is None
    ):
        return None
    return (
        turn.candidate_digest,
        turn.semantic_action_digest,
        turn.semantic_result_digest,
    )


class ProgressEvaluator:
    """One deterministic pure progress evaluator (25.A GREEN-1).

    Every streak is recomputed from scratch over the bounded window plus
    the current observation, so the same evidence always yields the same
    decision and each declared counter resets only on its declared
    condition: no-progress on a marker, repetition on a changed
    repetition key, invalid outputs on a valid output.
    """

    def evaluate(
        self,
        window: ProgressWindowV1,
        observation: ProgressObservationV1,
    ) -> ProgressDecisionV1:
        turns = window.turns + (observation,)
        has_progress = _turn_is_marker(turns, len(turns) - 1)

        no_progress_streak = 0
        for index in range(len(turns) - 1, -1, -1):
            if _turn_is_marker(turns, index):
                break
            no_progress_streak += 1

        current_key = _repetition_key(observation)
        repeated_streak = 0
        if current_key is not None:
            for turn in reversed(turns):
                if _repetition_key(turn) != current_key:
                    break
                repeated_streak += 1

        invalid_streak = 0
        for turn in reversed(turns):
            if not turn.invalid_output:
                break
            invalid_streak += 1

        return ProgressDecisionV1(
            has_progress=has_progress,
            consecutive_no_progress_turns=no_progress_streak,
            consecutive_repeated_semantic=repeated_streak,
            consecutive_invalid_outputs=invalid_streak,
        )

"""T25.3 legacy step 25.A: pure stop decision over a closed precedence table.

``StopEvaluator.evaluate`` decides repeated-action, no-progress, budget,
invalid-output, cancellation, and the smaller applicable deadline stops
from immutable inputs only — the run-loop state, the step evidence, the
progress decision, and the explicit current time — through one closed
precedence table with explicit time (GREEN-2).  It never performs a loop
side effect: repository, LLM, parser, dispatcher, wait transition,
audit, and outer-loop effects remain out of scope (GREEN-4/Boundary).
The stop reasons form the closed loop vocabulary shared by the wait,
cancellation, and engine layers.
"""

from __future__ import annotations

from typing import Annotated, Literal, TypeAlias

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    Strict,
    StrictStr,
    model_validator,
)

from vespercode.canonical.timestamp_v1 import CanonicalTimestampV1
from vespercode.loop.progress import ProgressDecisionV1

LoopStopReasonV1: TypeAlias = Literal[
    "REPEATED_ACTION_LIMIT",
    "NO_PROGRESS_LIMIT",
    "MODEL_OUTPUT_INVALID_LIMIT",
    "TURN_BUDGET_EXHAUSTED",
    "CALL_BUDGET_EXHAUSTED",
    "WALL_CLOCK_DEADLINE_EXCEEDED",
    "CANCELLED",
    "WAIT_REJECTED",
    "WAIT_EXPIRED",
    "WAIT_STALE",
    "LLM_CALL_FAILED",
    "CREDENTIAL_MISSING",
    "CREDENTIAL_BACKEND_UNSAFE",
    "DISCLOSURE_SCOPE_EXCEEDED",
    "DISCLOSURE_BUDGET_EXCEEDED",
    "DISCLOSURE_GRANT_EXPIRED",
    "DISCLOSURE_GRANT_REVOKED",
    "LLM_ENDPOINT_MISMATCH",
    "CONTEXT_BUDGET_EXCEEDED",
    "INTERNAL_ERROR",
    "PROCESS_RESTART_DURING_TURN",
    "PROCESS_RESTARTED_DURING_RUN",
    "RUN_ALREADY_TERMINAL",
]
"""The closed loop stop vocabulary (SPEC §4.2.6/§4.2.8, §4.4.4, §4.2.7).

The 25.A precedence table produces the first six plus CANCELLED; the
wait layer produces WAIT_REJECTED/WAIT_EXPIRED/WAIT_STALE; the call
boundary's stable codes pass through (LLM_CALL_FAILED and friends); the
restart guard's two reasons and the terminal-run note complete the
closed vocabulary the loop and its boundary result can carry.
"""


class RunLoopStateV1(BaseModel):
    """One immutable snapshot of the run-loop counters and deadlines.

    The consumed turn/call counts and the frozen ``RunLimitsV1`` caps
    are explicit inputs; ``wait_deadline`` is the active wait's expiry
    when the run is waiting (the §4.2.7 smaller-deadline binding), and
    ``None`` otherwise.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)
    turn_count: Annotated[int, Strict(), Field(ge=0)]
    call_count: Annotated[int, Strict(), Field(ge=0)]
    max_turns: Annotated[int, Strict(), Field(ge=1)]
    max_llm_calls: Annotated[int, Strict(), Field(ge=1)]
    run_deadline: CanonicalTimestampV1
    wait_deadline: CanonicalTimestampV1 | None = None

    @model_validator(mode="after")
    def _deadlines_are_ordered(self) -> RunLoopStateV1:
        if self.wait_deadline is not None:
            if (
                self.wait_deadline.epoch_milliseconds
                > self.run_deadline.epoch_milliseconds
            ):
                raise ValueError("the wait deadline can never exceed the run deadline")
        return self


class LoopEvidenceV1(BaseModel):
    """One step's immutable stop-relevant evidence.

    ``completion_requested`` marks a ``VALIDATION_REQUESTED`` completion
    proposal (SPEC §4.2.5 step 6 — the StopEvaluator may only request
    the formal-validation transition, never publish SUCCEEDED);
    ``cancellation_honored`` is set only when a cancellation request is
    pending at a deterministic safe point (Task 25.E).
    """

    model_config = ConfigDict(extra="forbid", frozen=True)
    completion_requested: bool
    cancellation_honored: bool


class ContinueV1(BaseModel):
    """One closed continue decision: the loop may begin the next turn."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    kind: Literal["CONTINUE"]
    message: StrictStr


class ValidateV1(BaseModel):
    """One closed validate decision: enter formal validation (never success)."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    kind: Literal["VALIDATE"]
    message: StrictStr


class StopV1(BaseModel):
    """One closed stop decision with the exact stable reason (the RED)."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    kind: Literal["STOP"]
    reason: LoopStopReasonV1
    message: StrictStr


StopDecisionV1: TypeAlias = Annotated[
    ContinueV1 | ValidateV1 | StopV1, Field(discriminator="kind")
]
"""SPEC §4.2.1: ``Continue | Validate | Stop`` (closed, discriminant)."""


class StopEvaluator:
    """One deterministic pure stop evaluator (25.A GREEN-2/GREEN-3).

    The exact closed precedence table, highest precedence first:
    CANCELLED (the user's explicit terminal override at a safe point),
    MODEL_OUTPUT_INVALID_LIMIT (streak 2), REPEATED_ACTION_LIMIT
    (streak 3), NO_PROGRESS_LIMIT (streak 6) — ordered by the natural
    limit magnitudes, so the earliest exact limit fires first — then
    VALIDATE (validation entry consumes no agent turn or call, so it
    precedes the budget rows), TURN_BUDGET_EXHAUSTED,
    CALL_BUDGET_EXHAUSTED, WALL_CLOCK_DEADLINE_EXCEEDED (against the
    smaller applicable Run or wait deadline), then CONTINUE.
    """

    def evaluate(
        self,
        state: RunLoopStateV1,
        evidence: LoopEvidenceV1,
        progress: ProgressDecisionV1,
        now: CanonicalTimestampV1,
    ) -> StopDecisionV1:
        """Return the one closed decision of the precedence table.

        Pure: only the immutable inputs and the explicit clock value are
        consulted, so repeated evaluations are identical and no loop
        side effect ever happens here (GREEN-4/Boundary).
        """
        if evidence.cancellation_honored:
            return StopV1(
                kind="STOP",
                reason="CANCELLED",
                message="the run was cancelled at a deterministic safe point",
            )
        if progress.consecutive_invalid_outputs >= 2:
            return StopV1(
                kind="STOP",
                reason="MODEL_OUTPUT_INVALID_LIMIT",
                message="two consecutive invalid model outputs",
            )
        if progress.consecutive_repeated_semantic >= 3:
            return StopV1(
                kind="STOP",
                reason="REPEATED_ACTION_LIMIT",
                message="the same semantic action and result repeated "
                "three times on the same candidate",
            )
        if progress.consecutive_no_progress_turns >= 6:
            return StopV1(
                kind="STOP",
                reason="NO_PROGRESS_LIMIT",
                message="six turns without a ProgressMarker",
            )
        if evidence.completion_requested:
            return ValidateV1(
                kind="VALIDATE",
                message="the completion proposal requests formal validation",
            )
        if state.turn_count >= state.max_turns:
            return StopV1(
                kind="STOP",
                reason="TURN_BUDGET_EXHAUSTED",
                message="the frozen turn budget is exhausted",
            )
        if state.call_count >= state.max_llm_calls:
            return StopV1(
                kind="STOP",
                reason="CALL_BUDGET_EXHAUSTED",
                message="the frozen LLM call budget is exhausted",
            )
        applicable = state.run_deadline
        if (
            state.wait_deadline is not None
            and state.wait_deadline.epoch_milliseconds < applicable.epoch_milliseconds
        ):
            applicable = state.wait_deadline
        if now.epoch_milliseconds >= applicable.epoch_milliseconds:
            return StopV1(
                kind="STOP",
                reason="WALL_CLOCK_DEADLINE_EXCEEDED",
                message="the smaller applicable deadline has been reached",
            )
        return ContinueV1(
            kind="CONTINUE",
            message="the loop may begin the next turn",
        )

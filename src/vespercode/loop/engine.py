"""T25.3 legacy step 25.G: the thin sequential agent-loop composition.

``AgentLoopEngine`` composes the injected production children of Tasks
25.A–25.F — ``StopEvaluator``/``ProgressEvaluator`` (25.A),
``TurnBoundary`` (25.B), ``CallOrchestrator`` (25.C), ``ActionPipeline``
(25.D), ``WaitController``/``CancellationController`` (25.E),
``RestartGuard`` (25.F) — into the exact sequential stage order
context → authorize/one-call → parse/policy/ALLOW-dispatch/feedback →
progress/stop → close (GREEN-1), preserving exactly one active turn and
one eligible call per step, stopping at the first typed
wait/terminal/failure boundary, and exposing ordered evidence without
duplicating child decisions (GREEN-2).  The engine owns orchestration
only: no policy table, parser, feedback rule, count predicate, retry,
wait predicate, or restart predicate lives here (GREEN-4/Boundary);
the auxiliary wiring ports (persisted run facts, context assembly,
request preparation, response resolution, step-context assembly, and
wait provision) are supplied by the run-service composition.
"""

from __future__ import annotations

from typing import Annotated, Literal, Protocol, TypeAlias, cast

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    Strict,
    StrictStr,
    field_validator,
)

from src.vespercode.canonical.clock import ClockV1
from src.vespercode.canonical.timestamp_v1 import CanonicalTimestampV1
from src.vespercode.contracts.optional import AbsentV1, PresentV1
from src.vespercode.contracts.run import (
    RunLimitsV1,
    RunStateV1,
    WaitContextV1,
    WaitDecisionV1,
    WaitKind,
)
from src.vespercode.llm.base import ModelResponse
from src.vespercode.llm.prepared_request import PreparedModelRequestV1
from src.vespercode.loop.action_pipeline import (
    ActionPipelineContextV1,
    ActionStepResultV1,
)
from src.vespercode.loop.call_orchestrator import (
    CallOnceV1,
    LLMCallResultV1,
)
from src.vespercode.loop.cancellation import CancellationDecisionV1
from src.vespercode.loop.context_projection import (
    ContextBudgetFailureV1,
    ContextProjectionV1,
)
from src.vespercode.loop.progress import (
    MAX_PROGRESS_WINDOW_PRIORS_V1,
    ProgressDecisionV1,
    ProgressObservationV1,
    ProgressWindowV1,
)
from src.vespercode.loop.restart import (
    RestartDispositionV1,
    RunEvidenceV1,
)
from src.vespercode.loop.stopping import (
    LoopEvidenceV1,
    LoopStopReasonV1,
    RunLoopStateV1,
    StopDecisionV1,
    StopV1,
    ValidateV1,
)
from src.vespercode.loop.turn_boundary import (
    CloseTurnResultV1,
    TurnOutcomeV1,
)
from src.vespercode.loop.wait_control import (
    WaitTransitionResultV1,
)
from src.vespercode.storage.run_repository import (
    RunRecordV1,
    TransitionCommandV1,
    TransitionResultV1,
)

LoopStepKindV1: TypeAlias = Literal["CONTINUE", "STOPPED", "WAITING", "VALIDATE"]
"""One step's closed outcome (GREEN-2: the first typed boundary)."""

_RUNNING_AGENT_LOOP = RunStateV1(
    status="RUNNING", phase=PresentV1(kind="PRESENT", value="AGENT_LOOP")
)
_RUNNING_FORMAL_VALIDATION = RunStateV1(
    status="RUNNING", phase=PresentV1(kind="PRESENT", value="FORMAL_VALIDATION")
)
_RUNNING_PERSISTENCE = RunStateV1(
    status="RUNNING", phase=PresentV1(kind="PRESENT", value="PERSISTENCE")
)
_WAITING_USER = RunStateV1(status="WAITING_USER", phase=AbsentV1(kind="ABSENT"))
_STOPPED = RunStateV1(status="STOPPED", phase=AbsentV1(kind="ABSENT"))

_NEUTRAL_PROGRESS = ProgressDecisionV1(
    has_progress=False,
    consecutive_no_progress_turns=0,
    consecutive_repeated_semantic=0,
    consecutive_invalid_outputs=0,
)


def _stop_command(run_id: str) -> TransitionCommandV1:
    """One transition to the STOPPED terminal state."""
    return TransitionCommandV1(
        run_id=run_id, expected=_RUNNING_AGENT_LOOP, target=_STOPPED
    )


LoopStageNameV1: TypeAlias = Literal[
    "context",
    "call_once",
    "action_pipeline",
    "progress",
    "stop",
    "close_turn",
]
"""The declared stage sequence of one step (the card's exact RED)."""


class LoopStepEvidenceV1(BaseModel):
    """One ordered evidence entry: the stage and its closed outcome.

    The engine labels each stage's child outcome without re-deciding it
    (GREEN-2); the ordered tuple is the step's audit trail.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)
    stage: LoopStageNameV1
    outcome: StrictStr


class LoopStepResultV1(BaseModel):
    """One closed single-step outcome with ordered evidence."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal[1]
    kind: LoopStepKindV1
    message: StrictStr
    stop_reason: LoopStopReasonV1 | None = None
    turn_id: StrictStr | None = None
    turn_count: Annotated[int, Strict(), Field(ge=0)]
    call_count: Annotated[int, Strict(), Field(ge=0)]
    wait_id: StrictStr | None = None
    wait_kind: WaitKind | None = None
    evidence: tuple[LoopStepEvidenceV1, ...] = ()

    @field_validator("schema_version", mode="before")
    @classmethod
    def _schema_version_is_exact_int(cls, value: object) -> object:
        if not isinstance(value, int) or isinstance(value, bool):
            raise ValueError("schema_version must be the decimal integer 1")
        return value


class LoopBoundaryResultV1(BaseModel):
    """One closed loop-boundary outcome (run_until_boundary).

    ``turns_executed``/``calls_executed`` are the run's cumulative
    persisted counts at the boundary (the total consumed so far, read
    fresh from the Task 25.B counter rows), not the counts produced by
    this call alone; a boundary that stops before any step (cancel,
    restart, wait pause, deadline) reports the run's current counts,
    which are zero for a run that never crossed a counting boundary.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal[1]
    kind: Literal["STOPPED", "WAITING", "VALIDATE_REQUESTED", "DEFERRED"]
    message: StrictStr
    stop_reason: LoopStopReasonV1 | None = None
    turns_executed: Annotated[int, Strict(), Field(ge=0)]
    calls_executed: Annotated[int, Strict(), Field(ge=0)]
    wait_id: StrictStr | None = None
    wait_kind: WaitKind | None = None

    @field_validator("schema_version", mode="before")
    @classmethod
    def _schema_version_is_exact_int(cls, value: object) -> object:
        if not isinstance(value, int) or isinstance(value, bool):
            raise ValueError("schema_version must be the decimal integer 1")
        return value


class StopEvaluatorPortV1(Protocol):
    """One injected 25.A stop child (the card's DI shape)."""

    def evaluate(
        self,
        state: RunLoopStateV1,
        evidence: LoopEvidenceV1,
        progress: ProgressDecisionV1,
        now: CanonicalTimestampV1,
    ) -> StopDecisionV1: ...


class ProgressEvaluatorPortV1(Protocol):
    """One injected 25.A progress child (the card's DI shape)."""

    def evaluate(
        self,
        window: ProgressWindowV1,
        observation: ProgressObservationV1,
    ) -> ProgressDecisionV1: ...


class TurnBoundaryPortV1(Protocol):
    """One injected 25.B child; the engine consumes only the close port."""

    def close_turn(
        self,
        run_id: str,
        turn_id: str,
        outcome: TurnOutcomeV1,
        expected_revision: int,
    ) -> CloseTurnResultV1: ...


class CallOrchestratorPortV1(Protocol):
    """One injected 25.C child (the one eligible call per step)."""

    def call_once(self, command: CallOnceV1) -> LLMCallResultV1: ...


class ActionPipelinePortV1(Protocol):
    """One injected 25.D child (parse/policy/ALLOW-dispatch/feedback)."""

    def execute(
        self, response: ModelResponse, context: ActionPipelineContextV1
    ) -> ActionStepResultV1: ...


class WaitControllerPortV1(Protocol):
    """One injected 25.E wait child (enter/resume/expire transitions)."""

    def enter(
        self, wait: WaitContextV1, now: CanonicalTimestampV1
    ) -> WaitTransitionResultV1: ...
    def resume(
        self,
        wait: WaitContextV1,
        decision: WaitDecisionV1,
        now: CanonicalTimestampV1,
    ) -> WaitTransitionResultV1: ...
    def expire(
        self, wait: WaitContextV1, now: CanonicalTimestampV1
    ) -> WaitTransitionResultV1: ...


class CancellationControllerPortV1(Protocol):
    """One injected 25.E cancellation child (safe-point evaluation)."""

    def evaluate_safe_point(
        self, run: RunRecordV1, cancellation_requested: bool
    ) -> CancellationDecisionV1: ...


class RestartGuardPortV1(Protocol):
    """One injected 25.F restart child (the boundary dispositions)."""

    def inspect(self, run: RunEvidenceV1) -> RestartDispositionV1: ...


class RunFactsPortV1(Protocol):
    """One read/write port over the persisted loop facts (orchestration).

    The production implementation wraps the Task 7.B ``RunRepository``,
    the Task 25.B counting rows, and the one-active-turn invariant; the
    engine owns no SQL.
    """

    def run_record(self, run_id: str) -> RunRecordV1: ...
    def run_limits(self, run_id: str) -> RunLimitsV1: ...
    def turn_call_counts(self, run_id: str) -> tuple[int, int]: ...
    def active_turn_exists(self, run_id: str) -> bool: ...
    def active_turn(self, run_id: str) -> tuple[str, int] | None: ...
    def active_wait(self, run_id: str) -> WaitContextV1 | None: ...
    def pending_wait_decision(self, run_id: str) -> WaitDecisionV1 | None: ...
    def cancellation_requested(self, run_id: str) -> bool: ...
    def transition(self, command: TransitionCommandV1) -> TransitionResultV1: ...


class LoopContextBuilderPortV1(Protocol):
    """One context-assembly port (the ``context`` stage, Task 25.1)."""

    def build_context(
        self, run_id: str
    ) -> ContextProjectionV1 | ContextBudgetFailureV1: ...


class LoopRequestPreparerPortV1(Protocol):
    """One request-preparation port (the one eligible call's command).

    The production wiring freezes the prepared request from the run's
    frozen LLM profile and builds the closed ``CallOnceV1`` (Tasks
    16.A/25.C); the engine performs no request construction itself.
    """

    def prepare_call(
        self, run_id: str, projection: ContextProjectionV1
    ) -> CallOnceV1: ...


class ResponseResolverPortV1(Protocol):
    """One response-resolution port over the body-free call result.

    The Task 25.C boundary returns the closed body-free
    ``LLMCallResultV1`` (SPEC §4.4.4 keeps response bodies out of
    SQLite); the loop's response-visible stage needs the exact
    ``ModelResponse``, so the wiring supplies the resolver.  The
    resolver performs no adapter call, no counting, and no transport —
    the one eligible call per step is the orchestrator's counted
    invocation.
    """

    def resolve(
        self,
        request: PreparedModelRequestV1,
        result: LLMCallResultV1,
    ) -> ModelResponse | None: ...


class LoopStepContextBuilderPortV1(Protocol):
    """One action-step context assembly port (the 25.D context)."""

    def build_step_context(
        self, run_id: str, projection: ContextProjectionV1
    ) -> ActionPipelineContextV1: ...


class LoopWaitProviderPortV1(Protocol):
    """One wait-provision port for call-boundary aborts (Task 15.D wiring).

    The provider owns the governance decision "does this abort require a
    declared wait (with a positive interval)?"; the engine only asks.
    ``None`` means the abort stops the run with its stable code.
    """

    def wait_for_abort(self, run_id: str, abort_code: str) -> WaitContextV1 | None: ...


class AgentLoopEngine:
    """One thin sequential loop composer (25.G GREEN-1..GREEN-4)."""

    def __init__(
        self,
        *,
        stop_evaluator: StopEvaluatorPortV1,
        progress_evaluator: ProgressEvaluatorPortV1,
        turn_boundary: TurnBoundaryPortV1,
        call_orchestrator: CallOrchestratorPortV1,
        action_pipeline: ActionPipelinePortV1,
        wait_controller: WaitControllerPortV1,
        cancellation_controller: CancellationControllerPortV1,
        restart_guard: RestartGuardPortV1,
        run_facts: RunFactsPortV1,
        context_builder: LoopContextBuilderPortV1,
        request_preparer: LoopRequestPreparerPortV1,
        response_resolver: ResponseResolverPortV1,
        step_context_builder: LoopStepContextBuilderPortV1,
        wait_provider: LoopWaitProviderPortV1,
        clock: ClockV1,
    ) -> None:
        self._stop_evaluator = stop_evaluator
        self._progress_evaluator = progress_evaluator
        self._turn_boundary = turn_boundary
        self._call_orchestrator = call_orchestrator
        self._action_pipeline = action_pipeline
        self._wait_controller = wait_controller
        self._cancellation_controller = cancellation_controller
        self._restart_guard = restart_guard
        self._run_facts = run_facts
        self._context_builder = context_builder
        self._request_preparer = request_preparer
        self._response_resolver = response_resolver
        self._step_context_builder = step_context_builder
        self._wait_provider = wait_provider
        self._clock = clock
        self._windows: dict[str, tuple[ProgressObservationV1, ...]] = {}
        self._latest_progress: dict[str, ProgressDecisionV1] = {}

    def step(self, run_id: str) -> LoopStepResultV1:
        """Execute one sequential step: context, one call, the pipeline,
        progress, stop, close (25.G GREEN-1/GREEN-2).

        The turn/call counting and the one active turn are the Task 25.C
        child's own boundaries (the orchestrator's adjacent
        begin/record_call_started); the engine reads the ACTIVE turn via
        the one-active-turn invariant (Task 25.B) for the close.  The
        step stops at the first typed wait/terminal/failure boundary and
        exposes the ordered evidence labels without re-deciding any
        child outcome.
        """
        run = self._run_facts.run_record(run_id)
        limits = self._run_facts.run_limits(run_id)
        turn_count, call_count = self._run_facts.turn_call_counts(run_id)
        # The cancellation safe point at the action boundary precedes
        # every side effect of the step.
        cancellation = self._cancellation_controller.evaluate_safe_point(
            run, self._run_facts.cancellation_requested(run_id)
        )
        if cancellation.kind == "SAFE_TO_CANCEL":
            self._run_facts.transition(_stop_command(run_id))
            return self._step_result(
                "STOPPED",
                "cancelled at the action boundary",
                "CANCELLED",
                None,
                turn_count,
                call_count,
                [],
            )
        now = self._clock.now()
        projection = self._context_builder.build_context(run_id)
        evidence: list[LoopStepEvidenceV1] = []
        if isinstance(projection, ContextBudgetFailureV1):
            evidence.append(
                LoopStepEvidenceV1(stage="context", outcome="CONTEXT_BUDGET_EXCEEDED")
            )
            self._run_facts.transition(_stop_command(run_id))
            return self._step_result(
                "STOPPED",
                projection.message,
                "CONTEXT_BUDGET_EXCEEDED",
                None,
                turn_count,
                call_count,
                evidence,
            )
        evidence.append(
            LoopStepEvidenceV1(stage="context", outcome=projection.projection_digest)
        )
        command = self._request_preparer.prepare_call(run_id, projection)
        call_result = self._call_orchestrator.call_once(command)
        evidence.append(
            LoopStepEvidenceV1(stage="call_once", outcome=call_result.status)
        )
        turn_count, call_count = self._run_facts.turn_call_counts(run_id)
        if call_result.status == "NOT_ATTEMPTED":
            # The call never crossed the counting boundary: zero side
            # effects, no turn to close.  The wait provider owns the
            # governance decision "does this abort require a declared
            # wait?"; the engine only asks.
            wait = self._wait_provider.wait_for_abort(
                run_id, call_result.error_code or "INTERNAL_ERROR"
            )
            if wait is not None:
                outcome = self._wait_controller.enter(wait, now)
                if outcome.kind == "ENTERED":
                    self._run_facts.transition(
                        TransitionCommandV1(
                            run_id=run_id,
                            expected=_RUNNING_AGENT_LOOP,
                            target=_WAITING_USER,
                        )
                    )
                    return self._step_result(
                        "WAITING",
                        "a declared wait pauses the loop",
                        None,
                        None,
                        turn_count,
                        call_count,
                        evidence,
                        wait_id=wait.wait_id,
                        wait_kind=wait.wait_kind,
                    )
                return self._abort_stopped(
                    run_id,
                    "the declared wait could not be entered",
                    "WAIT_STALE",
                    turn_count,
                    call_count,
                    evidence,
                )
            return self._abort_stopped(
                run_id,
                "the call was not attempted",
                cast(
                    LoopStopReasonV1,
                    call_result.error_code or "INTERNAL_ERROR",
                ),
                turn_count,
                call_count,
                evidence,
            )
        if call_result.status != "SUCCEEDED":
            # FAILED / DELIVERY_UNKNOWN: the turn exists (post-count);
            # v1 never retries and never reconstructs an uncertain
            # response (SPEC §4.2.8/§4.4.4).
            _, close = self._close_turn(run_id, "FAILED", evidence)
            if call_result.status == "DELIVERY_UNKNOWN":
                return self._stopped(
                    run_id,
                    "the delivery is unknown; v1 never retries",
                    "INTERNAL_ERROR",
                    turn_count,
                    call_count,
                    evidence,
                    close,
                )
            return self._stopped(
                run_id,
                "the LLM call failed",
                cast(
                    LoopStopReasonV1,
                    call_result.error_code or "LLM_CALL_FAILED",
                ),
                turn_count,
                call_count,
                evidence,
                close,
            )
        response = self._response_resolver.resolve(command.request, call_result)
        if response is None:
            _, close = self._close_turn(run_id, "FAILED", evidence)
            return self._stopped(
                run_id,
                "the call response could not be resolved",
                "INTERNAL_ERROR",
                turn_count,
                call_count,
                evidence,
                close,
            )
        step_context = self._step_context_builder.build_step_context(run_id, projection)
        action_step = self._action_pipeline.execute(response, step_context)
        evidence.append(
            LoopStepEvidenceV1(
                stage="action_pipeline", outcome=action_step.parse_outcome
            )
        )
        observation = self._observe(action_step, step_context, turn_count)
        window = self._windows.get(run_id, ())
        progress = self._progress_evaluator.evaluate(
            ProgressWindowV1(turns=window), observation
        )
        evidence.append(
            LoopStepEvidenceV1(
                stage="progress",
                outcome="PROGRESS" if progress.has_progress else "NO_PROGRESS",
            )
        )
        self._windows[run_id] = (window + (observation,))[
            -MAX_PROGRESS_WINDOW_PRIORS_V1:
        ]
        self._latest_progress[run_id] = progress
        active_wait = self._run_facts.active_wait(run_id)
        state = RunLoopStateV1(
            turn_count=turn_count,
            call_count=call_count,
            max_turns=limits.max_turns,
            max_llm_calls=limits.max_llm_calls,
            run_deadline=run.run_deadline,
            wait_deadline=(active_wait.expires_at if active_wait is not None else None),
        )
        decision = self._stop_evaluator.evaluate(
            state,
            LoopEvidenceV1(
                completion_requested=observation.entered_formal_validation,
                cancellation_honored=False,
            ),
            progress,
            now,
        )
        evidence.append(
            LoopStepEvidenceV1(stage="stop", outcome=self._stop_label(decision))
        )
        if isinstance(decision, ValidateV1):
            _, close = self._close_turn(run_id, "SUCCEEDED", evidence)
            return self._validate_after_close(
                run_id,
                decision.message,
                turn_count,
                call_count,
                evidence,
                close,
            )
        if isinstance(decision, StopV1):
            close_outcome: TurnOutcomeV1 = (
                "FAILED" if action_step.parse_outcome == "INVALID" else "SUCCEEDED"
            )
            _, close = self._close_turn(run_id, close_outcome, evidence)
            return self._stopped(
                run_id,
                decision.message,
                decision.reason,
                turn_count,
                call_count,
                evidence,
                close,
            )
        continue_outcome: TurnOutcomeV1 = (
            "FAILED" if action_step.parse_outcome == "INVALID" else "SUCCEEDED"
        )
        turn_id, close = self._close_turn(run_id, continue_outcome, evidence)
        if close is None or close.kind != "APPLIED":
            return self._step_result(
                "STOPPED",
                "the active turn could not be closed",
                "INTERNAL_ERROR",
                None,
                turn_count,
                call_count,
                evidence,
            )
        return self._step_result(
            "CONTINUE",
            decision.message,
            None,
            turn_id,
            turn_count,
            call_count,
            evidence,
        )

    def run_until_boundary(self, run_id: str) -> LoopBoundaryResultV1:
        """Run steps until the first typed boundary (25.G GREEN-1/2).

        The restart guard (Task 25.F) is consulted at the boundary entry
        for every state the loop cannot itself drive — an interrupted
        ACTIVE turn, a terminal run, a recovery-required run, or a
        coordinator-owned phase.  The loop's drive states are
        RUNNING(AGENT_LOOP) without an ACTIVE turn and WAITING_USER; a
        RUNNING run between turns is indistinguishable from a restart
        point, so the PROCESS_RESTARTED_DURING_RUN stop for that state
        belongs to the run service's restart gate (SPEC §4.2.7), never
        to the loop's own entry.  Declared waits pause the loop and
        resume exactly once through the Task 25.E child; the
        cancellation safe point and the smaller-applicable-deadline
        boundary are re-checked before every step, so no side effect
        ever starts after a passed deadline or an honored cancellation.
        """
        run = self._run_facts.run_record(run_id)
        entry_turn_count, entry_call_count = self._run_facts.turn_call_counts(run_id)
        active_turn = self._run_facts.active_turn_exists(run_id)
        drive_state = not active_turn and (
            (
                run.status == "RUNNING"
                and run.phase.kind == "PRESENT"
                and run.phase.value == "AGENT_LOOP"
            )
            or run.status == "WAITING_USER"
        )
        if not drive_state:
            restart = self._restart_guard.inspect(
                RunEvidenceV1(
                    schema_version=1,
                    run_id=run_id,
                    status=run.status,
                    phase=run.phase.value if run.phase.kind == "PRESENT" else None,
                    active_turn=active_turn,
                )
            )
            if restart.kind == "STOP":
                assert restart.stop_reason is not None
                return LoopBoundaryResultV1(
                    schema_version=1,
                    kind="STOPPED",
                    message="an interrupted non-persistent turn stops the run",
                    stop_reason=restart.stop_reason,
                    turns_executed=entry_turn_count,
                    calls_executed=entry_call_count,
                )
            if restart.kind == "DEFER_RECOVERY":
                return LoopBoundaryResultV1(
                    schema_version=1,
                    kind="DEFERRED",
                    message="the persistence recovery machinery owns the run",
                    stop_reason=None,
                    turns_executed=entry_turn_count,
                    calls_executed=entry_call_count,
                )
            # The guard's CONTINUE covers terminal and never-started runs;
            # a terminal run stays terminal, everything else fails closed.
            if run.status in ("SUCCEEDED", "STOPPED"):
                return self._boundary_result(
                    "STOPPED",
                    "the run is already terminal",
                    "RUN_ALREADY_TERMINAL",
                    run_id,
                )
            return self._boundary_result(
                "STOPPED",
                "the loop cannot drive this run state",
                "INTERNAL_ERROR",
                run_id,
            )
        while True:
            run = self._run_facts.run_record(run_id)
            if run.status == "WAITING_USER":
                wait = self._run_facts.active_wait(run_id)
                if wait is None:
                    return self._boundary_result(
                        "STOPPED",
                        "WAITING_USER without a persisted wait fails closed",
                        "WAIT_STALE",
                        run_id,
                    )
                pending = self._run_facts.pending_wait_decision(run_id)
                if pending is not None:
                    outcome = self._wait_controller.resume(
                        wait, pending, self._clock.now()
                    )
                    if outcome.kind == "RESUMED":
                        target = (
                            _RUNNING_AGENT_LOOP
                            if outcome.resume_action == "RESUME_AGENT_LOOP"
                            else _RUNNING_PERSISTENCE
                        )
                        self._run_facts.transition(
                            TransitionCommandV1(
                                run_id=run_id, expected=_WAITING_USER, target=target
                            )
                        )
                        if target == _RUNNING_PERSISTENCE:
                            # A FINAL_WRITEBACK approval hands the run to
                            # the persistence coordinator (SPEC §4.2.7);
                            # the loop never drives RUNNING(PERSISTENCE).
                            return self._boundary_result(
                                "DEFERRED",
                                "the persistence coordinator owns the run",
                                None,
                                run_id,
                            )
                        continue
                    self._run_facts.transition(
                        TransitionCommandV1(
                            run_id=run_id, expected=_WAITING_USER, target=_STOPPED
                        )
                    )
                    if outcome.kind == "REJECTED":
                        return self._boundary_result(
                            "STOPPED", outcome.message, "WAIT_REJECTED", run_id
                        )
                    if outcome.kind == "WAIT_EXPIRED":
                        return self._boundary_result(
                            "STOPPED", outcome.message, "WAIT_EXPIRED", run_id
                        )
                    return self._boundary_result(
                        "STOPPED", outcome.message, "WAIT_STALE", run_id
                    )
                outcome = self._wait_controller.expire(wait, self._clock.now())
                if outcome.kind == "WAIT_EXPIRED":
                    self._run_facts.transition(
                        TransitionCommandV1(
                            run_id=run_id, expected=_WAITING_USER, target=_STOPPED
                        )
                    )
                    return self._boundary_result(
                        "STOPPED", outcome.message, "WAIT_EXPIRED", run_id
                    )
                wait_turn_count, wait_call_count = self._run_facts.turn_call_counts(
                    run_id
                )
                return LoopBoundaryResultV1(
                    schema_version=1,
                    kind="WAITING",
                    message="the loop pauses at the declared wait",
                    stop_reason=None,
                    turns_executed=wait_turn_count,
                    calls_executed=wait_call_count,
                    wait_id=wait.wait_id,
                    wait_kind=wait.wait_kind,
                )
            if run.status in ("SUCCEEDED", "STOPPED"):
                return self._boundary_result(
                    "STOPPED",
                    "the run is already terminal",
                    "RUN_ALREADY_TERMINAL",
                    run_id,
                )
            if run.status != "RUNNING" or (
                run.phase.kind != "PRESENT" or run.phase.value != "AGENT_LOOP"
            ):
                return self._boundary_result(
                    "STOPPED",
                    "the loop runs only in RUNNING(AGENT_LOOP)",
                    "INTERNAL_ERROR",
                    run_id,
                )
            cancellation = self._cancellation_controller.evaluate_safe_point(
                run, self._run_facts.cancellation_requested(run_id)
            )
            if cancellation.kind == "SAFE_TO_CANCEL":
                self._run_facts.transition(_stop_command(run_id))
                return self._boundary_result(
                    "STOPPED",
                    "cancelled at a deterministic safe point",
                    "CANCELLED",
                    run_id,
                )
            limits = self._run_facts.run_limits(run_id)
            turn_count, call_count = self._run_facts.turn_call_counts(run_id)
            active_wait = self._run_facts.active_wait(run_id)
            state = RunLoopStateV1(
                turn_count=turn_count,
                call_count=call_count,
                max_turns=limits.max_turns,
                max_llm_calls=limits.max_llm_calls,
                run_deadline=run.run_deadline,
                wait_deadline=(
                    active_wait.expires_at if active_wait is not None else None
                ),
            )
            decision = self._stop_evaluator.evaluate(
                state,
                LoopEvidenceV1(
                    completion_requested=False,
                    cancellation_honored=False,
                ),
                self._latest_progress.get(run_id, _NEUTRAL_PROGRESS),
                self._clock.now(),
            )
            if isinstance(decision, StopV1):
                self._run_facts.transition(_stop_command(run_id))
                return self._boundary_result(
                    "STOPPED", decision.message, decision.reason, run_id
                )
            step_result = self.step(run_id)
            if step_result.kind == "STOPPED":
                assert step_result.stop_reason is not None
                return LoopBoundaryResultV1(
                    schema_version=1,
                    kind="STOPPED",
                    message=step_result.message,
                    stop_reason=step_result.stop_reason,
                    turns_executed=step_result.turn_count,
                    calls_executed=step_result.call_count,
                )
            if step_result.kind == "WAITING":
                return LoopBoundaryResultV1(
                    schema_version=1,
                    kind="WAITING",
                    message=step_result.message,
                    stop_reason=None,
                    turns_executed=step_result.turn_count,
                    calls_executed=step_result.call_count,
                    wait_id=step_result.wait_id,
                    wait_kind=step_result.wait_kind,
                )
            if step_result.kind == "VALIDATE":
                return LoopBoundaryResultV1(
                    schema_version=1,
                    kind="VALIDATE_REQUESTED",
                    message=step_result.message,
                    stop_reason=None,
                    turns_executed=step_result.turn_count,
                    calls_executed=step_result.call_count,
                )

    def _observe(
        self,
        action_step: ActionStepResultV1,
        step_context: ActionPipelineContextV1,
        turn_count: int,
    ) -> ProgressObservationV1:
        """Extract the step's immutable progress facts (no predicates)."""
        dispatch = action_step.dispatch_result
        action_digest: str | None = None
        result_digest: str | None = None
        check_digests: tuple[str, ...] = ()
        completion = False
        if dispatch is not None:
            action_digest = dispatch.semantic_digest
            if dispatch.payload_ref.kind == "PRESENT":
                result_digest = dispatch.payload_ref.value.digest.value
                if dispatch.result_type == "RunCheckResult":
                    check_digests = (dispatch.payload_ref.value.digest.value,)
            completion = (
                dispatch.result_type == "ProposeCompletionResult"
                and dispatch.status == "SUCCEEDED"
            )
        return ProgressObservationV1(
            turn_index=turn_count,
            candidate_digest=step_context.current_candidate_digest,
            semantic_action_digest=action_digest,
            semantic_result_digest=result_digest,
            semantic_check_digests=check_digests,
            invalid_output=action_step.parse_outcome == "INVALID",
            entered_formal_validation=completion,
        )

    def _validate_after_close(
        self,
        run_id: str,
        message: str,
        turn_count: int,
        call_count: int,
        evidence: list[LoopStepEvidenceV1],
        close: CloseTurnResultV1 | None,
    ) -> LoopStepResultV1:
        """One VALIDATE boundary after the turn close (25.G GREEN-2).

        The close must APPLY (fail closed otherwise); the run then
        enters RUNNING(FORMAL_VALIDATION) — the loop never publishes
        SUCCEEDED (SPEC §4.2.5 step 7).
        """
        if close is None or close.kind != "APPLIED":
            return self._step_result(
                "STOPPED",
                "the active turn could not be closed",
                "INTERNAL_ERROR",
                None,
                turn_count,
                call_count,
                evidence,
            )
        self._run_facts.transition(
            TransitionCommandV1(
                run_id=run_id,
                expected=_RUNNING_AGENT_LOOP,
                target=_RUNNING_FORMAL_VALIDATION,
            )
        )
        return self._step_result(
            "VALIDATE",
            message,
            None,
            None,
            turn_count,
            call_count,
            evidence,
        )

    def _abort_stopped(
        self,
        run_id: str,
        message: str,
        reason: LoopStopReasonV1,
        turn_count: int,
        call_count: int,
        evidence: list[LoopStepEvidenceV1],
    ) -> LoopStepResultV1:
        """One zero-count abort stop: no turn was ever created (25.C)."""
        self._run_facts.transition(_stop_command(run_id))
        return self._step_result(
            "STOPPED",
            message,
            reason,
            None,
            turn_count,
            call_count,
            evidence,
        )

    def _stopped(
        self,
        run_id: str,
        message: str,
        reason: LoopStopReasonV1,
        turn_count: int,
        call_count: int,
        evidence: list[LoopStepEvidenceV1],
        close: CloseTurnResultV1 | None,
    ) -> LoopStepResultV1:
        """One closed stop after the turn close (25.G GREEN-2).

        The run's terminal transition is best-effort orchestration; a
        close that did not APPLY is contradictory evidence and fails
        closed with INTERNAL_ERROR.
        """
        self._run_facts.transition(_stop_command(run_id))
        if close is None or close.kind != "APPLIED":
            return self._step_result(
                "STOPPED",
                "the active turn could not be closed",
                "INTERNAL_ERROR",
                None,
                turn_count,
                call_count,
                evidence,
            )
        return self._step_result(
            "STOPPED",
            message,
            reason,
            None,
            turn_count,
            call_count,
            evidence,
        )

    def _close_turn(
        self,
        run_id: str,
        outcome: TurnOutcomeV1,
        evidence: list[LoopStepEvidenceV1],
    ) -> tuple[str | None, CloseTurnResultV1 | None]:
        """Close the ACTIVE turn exactly once (one-active-turn invariant).

        The engine reads the turn identity through the Task 25.B
        invariant; a missing turn or a close rejection is contradictory
        evidence and fails closed on the evidence (the caller maps it).
        Returns the closed turn id and the close outcome so the step
        result can bind the turn identity it consumed.
        """
        active = self._run_facts.active_turn(run_id)
        if active is None:
            evidence.append(
                LoopStepEvidenceV1(stage="close_turn", outcome="NO_ACTIVE_TURN")
            )
            return (None, None)
        turn_id, revision = active
        result = self._turn_boundary.close_turn(run_id, turn_id, outcome, revision)
        evidence.append(LoopStepEvidenceV1(stage="close_turn", outcome=result.kind))
        return (turn_id, result)

    @staticmethod
    def _stop_label(decision: StopDecisionV1) -> str:
        if isinstance(decision, ValidateV1):
            return "VALIDATE"
        if isinstance(decision, StopV1):
            return f"STOP:{decision.reason}"
        return "CONTINUE"

    @staticmethod
    def _step_result(
        kind: LoopStepKindV1,
        message: str,
        stop_reason: LoopStopReasonV1 | None,
        turn_id: str | None,
        turn_count: int,
        call_count: int,
        evidence: list[LoopStepEvidenceV1],
        *,
        wait_id: str | None = None,
        wait_kind: WaitKind | None = None,
    ) -> LoopStepResultV1:
        return LoopStepResultV1(
            schema_version=1,
            kind=kind,
            message=message,
            stop_reason=stop_reason,
            turn_id=turn_id,
            turn_count=turn_count,
            call_count=call_count,
            wait_id=wait_id,
            wait_kind=wait_kind,
            evidence=tuple(evidence),
        )

    def _boundary_result(
        self,
        kind: Literal["STOPPED", "WAITING", "VALIDATE_REQUESTED", "DEFERRED"],
        message: str,
        stop_reason: LoopStopReasonV1 | None,
        run_id: str,
    ) -> LoopBoundaryResultV1:
        turn_count, call_count = self._run_facts.turn_call_counts(run_id)
        return LoopBoundaryResultV1(
            schema_version=1,
            kind=kind,
            message=message,
            stop_reason=stop_reason,
            turns_executed=turn_count,
            calls_executed=call_count,
        )

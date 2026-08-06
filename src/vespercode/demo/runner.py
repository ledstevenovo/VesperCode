"""T30.2 legacy step 30.D: the shared-core Demo runner and bounded sessions.

``DemoScenarioRunner`` thinly composes the real shared pure-core pipeline
(GREEN-1): the production Task 25.D ``ActionPipeline`` is constructed
once from the Task 13 policy engine, the Task 17.C dispatcher, the Task
24.A/24.C feedback builder/consumption, the Task 25.A stop evaluator,
and the ephemeral in-memory ``:memory:`` control database the real
pipeline requires — with only Task 30.C ports injected — and every
advance records exact provenance beginning with production
``ActionPipeline.execute`` without copying any child rule.  The fixed Mock
scenario advances only through deterministic trace steps (GREEN-2):
in-memory five-minute, 20-action, and 10-concurrent limits with explicit
reset/expiry and no recovery; a visitor decision only forms a
``DemoDecisionV1`` that advances the fixed scenario and can never become a
formal approval or disclosure grant.  Formal loop engine, Web, local
files, Docker, credentials, persistence, recovery, external adapters,
and real providers remain out of scope (GREEN-4/Boundary).

The ephemeral ``:memory:`` SQLite database is the wiring the production
``ActionPipeline`` requires (its feedback repository and action-record
repository are concrete sqlite-backed components); it never touches disk,
holds only demo turn/feedback/action rows (zero ``runs`` rows — no formal
Run identity is ever constructed), and dies with the process — it is not
persistence (SPEC §5.6/§6.4) and not a formal capability adapter.  The
Demo app serves synchronous routes through FastAPI's threadpool
(uvicorn/TestClient), so the connection allows cross-thread use; the
per-session flow is serialized by the visitor and every write is its own
``BEGIN IMMEDIATE`` transaction.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import dataclass
from typing import Annotated, Final, Literal, cast

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    Strict,
)

from src.vespercode.candidate.patch_engine import ApplyCandidatePatchAction
from src.vespercode.canonical.clock import ClockV1
from src.vespercode.canonical.digest import domain_digest
from src.vespercode.canonical.path_v1 import CanonicalRelativePathV1
from src.vespercode.canonical.timestamp_v1 import CanonicalTimestampV1
from src.vespercode.contracts.evidence import ArtifactRefV1, DigestV1
from src.vespercode.contracts.optional import AbsentV1, PresentV1
from src.vespercode.demo.executor import DemoExecutor
from src.vespercode.demo.scenario import FIXED_DEMO_SCENARIO_V1
from src.vespercode.demo.types import (
    DemoDecisionV1,
    DemoRunStatus,
    DemoScenarioV1,
    DemoSessionV1,
    DemoStepResultV1,
)
from src.vespercode.governance.policy import (
    PatchPathFactV1,
    PolicyEngine,
)
from src.vespercode.llm.base import ModelResponse
from src.vespercode.loop.action_binding import (
    reset_issued_action_ids,
)
from src.vespercode.loop.action_pipeline import (
    ActionPipeline,
    ActionPipelineContextV1,
    ActionRecordRepositoryV1,
)
from src.vespercode.loop.agent_actions import (
    AgentAction,
    RunCheckActionV1,
)
from src.vespercode.loop.feedback import (
    ActionFeedbackSourceV1,
    CheckFeedbackSourceV1,
    ControlFeedbackSourceV1,
    FeedbackKindV1,
    FeedbackRecordV1,
    FeedbackSeverityV1,
    FeedbackSourceV1,
    build_feedback,
    select_feedback,
)
from src.vespercode.loop.feedback_consumption import (
    FeedbackRepositoryV1,
    consume_feedback,
)
from src.vespercode.loop.progress import ProgressDecisionV1
from src.vespercode.loop.stopping import (
    LoopEvidenceV1,
    RunLoopStateV1,
    StopDecisionV1,
    StopEvaluator,
)
from src.vespercode.storage.connection import ControlDatabase
from src.vespercode.storage.migration_engine import apply_migrations
from src.vespercode.storage.migrations.v0001_run_wait import RUN_WAIT_V1_MIGRATION
from src.vespercode.storage.migrations.v0002_idempotency import IDEMPOTENCY_V1_MIGRATION
from src.vespercode.storage.migrations.v0003_disclosure_grants import (
    DISCLOSURE_GRANTS_V1_MIGRATION,
)
from src.vespercode.storage.migrations.v0004_disclosure_authorizations import (
    DISCLOSURE_AUTHORIZATIONS_V1_MIGRATION,
)
from src.vespercode.storage.migrations.v0005_memory import MEMORY_V1_MIGRATION
from src.vespercode.storage.migrations.v0006_audit import AUDIT_V1_MIGRATION
from src.vespercode.storage.migrations.v0007_agent_turns import AGENT_TURNS_V1_MIGRATION
from src.vespercode.storage.migrations.v0008_feedback import FEEDBACK_V1_MIGRATION
from src.vespercode.storage.migrations.v0009_actions import ACTIONS_V1_MIGRATION
from src.vespercode.tools.dispatcher import ToolDispatcher
from src.vespercode.tools.file_results import FileToolResultV1
from src.vespercode.validation.check_result import (
    CheckFindingV1,
    CheckResultV1,
)

DEMO_SHARED_CORE_MODULES_V1: Final[frozenset[str]] = frozenset(
    {
        "vespercode.governance.policy",
        "vespercode.loop.agent_actions",
        "vespercode.loop.action_parser",
        "vespercode.loop.action_binding",
        "vespercode.loop.context_projection",
        "vespercode.loop.feedback",
        "vespercode.loop.stopping",
        "vespercode.loop.action_pipeline",
        "vespercode.tools.dispatcher",
    }
)
"""The exact declared shared pure-core module set of the Demo runner
(card 30.D interface, byte-exact): composition constructs the production
Task 25.D ``ActionPipeline`` from the Task 13/17.A-17.C/24.A/24.C
components named here."""

DEMO_MAX_ACTIONS_V1: Final = 20
"""SPEC §5.1: the public Demo performs at most 20 actions per session."""

DEMO_MAX_SESSIONS_V1: Final = 10
"""SPEC §5.1: the process-level Demo concurrency cap is 10 sessions."""

DEMO_SESSION_TTL_MILLISECONDS_V1: Final = 300_000
"""SPEC §5.1/§4.9: one Demo session lasts at most 5 minutes."""

_FIXED_DIGEST: Final = "ab" * 32
"""The fixed digest identity of every sealed Demo value."""

_FIXED_CHECK_PLAN_V1: Final = "FULL_PYTEST"
"""The fixed frozen check plan of the Demo scenario."""

_WRITEBACK_LABEL_V1: Final = "FINAL_WRITEBACK"
"""The fixed action label of the scenario's two writeback steps."""

_DEMO_SCRIPT_PATCHES_V1: Final[tuple[tuple[int, str], ...]] = (
    (
        0,
        "--- a/docs/outside-scope.md\n"
        "+++ b/docs/outside-scope.md\n"
        "@@ -1 +1 @@\n"
        "-README.md\n"
        "+docs/outside-scope.md\n",
    ),
    (
        1,
        "--- a/README.md\n"
        "+++ b/README.md\n"
        "@@ -1 +1 @@\n"
        "-VesperCode Mock Demo\n"
        "+VesperCode Demo\n",
    ),
    (
        3,
        "--- a/tests/test_example.py\n"
        "+++ b/tests/test_example.py\n"
        "@@ -1 +1 @@\n"
        "-    return 0\n"
        "+    return 1\n",
    ),
)
"""The fixed model-action patch texts of the demo script (steps 0, 1, 3).

Step 2's patch text is the fixed scenario's ``expected_patch`` itself;
the writeback steps (4, 5) are control-plane steps with no model action.
The patch texts are never parsed by the candidate patch engine — the
fixed pre-policy facts deny steps 0/1/3 before dispatch — so they are
arbitrary-but-frozen demo data (deterministic script, no ambient input).
"""

_DEMO_SCRIPT_PATCH_FACTS_V1: Final[tuple[tuple[int, str], ...]] = (
    (0, "PATCH_PATH_NOT_EDITABLE"),
    (1, "PATCH_PATH_NOT_EDITABLE"),
    (2, "OK"),
    (3, "PROTECTED_ARTIFACT_CHANGED"),
)
"""The fixed pre-policy patch facts of the demo script (card GREEN-2)."""


class DemoAdvanceErrorCodeV1:
    """The closed rejection codes of one Demo session/advance request."""

    SESSION_NOT_FOUND: Final = "DEMO_SESSION_NOT_FOUND"
    SESSION_ID_EXISTS: Final = "DEMO_SESSION_ID_EXISTS"
    SESSION_EXPIRED: Final = "DEMO_SESSION_EXPIRED"
    SESSION_LIMIT: Final = "DEMO_SESSION_LIMIT"
    ACTION_LIMIT: Final = "DEMO_ACTION_LIMIT"
    STATE_MISMATCH: Final = "DEMO_STATE_MISMATCH"
    DECISION_REQUIRED: Final = "DEMO_DECISION_REQUIRED"
    DECISION_MISMATCH: Final = "DEMO_DECISION_MISMATCH"


class DemoAdvanceErrorV1(ValueError):
    """One closed rejection of a Demo session or advance request.

    The stable ``error_code`` is the closed vocabulary the app maps to
    HTTP statuses; a rejection never creates a recovery protocol and only
    affects the one session (SPEC §4.9)."""

    def __init__(self, error_code: str, message: str) -> None:
        super().__init__(message)
        self.error_code = error_code


class DemoAdvanceResultV1(BaseModel):
    """One closed advance outcome (the card's exact RED envelope).

    The T30.1 ``DemoStepResultV1`` is frozen and cannot carry
    ``executor_kind``, so the runner returns this closed envelope
    embedding the canonical step; ``executor_kind`` proves the step came
    from the Demo executor, ``stop_decision`` exposes the real shared
    stop verdict, and ``formal_capability_calls`` is the zero proof that
    no formal capability adapter was constructed or called.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal[1]
    step: DemoStepResultV1
    executor_kind: Literal["DEMO_EXECUTOR"]
    stop_decision: Literal["CONTINUE", "STOP", "VALIDATE"]
    formal_capability_calls: Annotated[int, Strict(), Field(ge=0)] = 0


@dataclass(frozen=True)
class _DemoRunState:
    """One closed in-memory session state (never persisted, never
    recovered; SPEC §4.9 ``DemoSession`` row semantics)."""

    step_index: int
    status: DemoRunStatus
    action_count: int
    created_at: CanonicalTimestampV1
    expires_at: CanonicalTimestampV1


class _DemoActionIdGenerator:
    """One deterministic Harness action-id generator (the same action id
    sequence never repeats, so binding stays deterministic)."""

    def __init__(self) -> None:
        self._counter = 0

    def next_id(self) -> str:
        self._counter += 1
        return f"demo-action-{self._counter}"


class _DemoVisibleTree:
    """The fixed visible tree of the demo (empty sealed tree)."""

    digest = _FIXED_DIGEST

    def list_directories(self) -> tuple[CanonicalRelativePathV1, ...]:
        return ()

    def list_file_paths(self) -> tuple[CanonicalRelativePathV1, ...]:
        return ()

    def read_bytes(self, path: CanonicalRelativePathV1) -> bytes:
        raise KeyError(path)


class _DemoArtifactStore:
    """One fixed in-memory artifact store (file-tool payload publication
    returns the fixed sealed reference; no disk is ever touched)."""

    def put(self, payload: FileToolResultV1) -> ArtifactRefV1:
        del payload
        return ArtifactRefV1(
            artifact_id="demo-artifact-v1",
            digest=DigestV1(value=_FIXED_DIGEST),
        )


class DemoScenarioRunner:
    """The headless shared-core Demo runner (30.D GREEN-1..GREEN-4).

    The real declared shared pure-core components are constructed once
    (the Task 25.D ``ActionPipeline``, the Task 13 ``PolicyEngine``, the
    Task 17.C ``ToolDispatcher``, the Task 24.C feedback repository, the
    action-record repository, and the Task 25.A ``StopEvaluator``) and
    only Task 30.C ports are injected; every advance records exact
    provenance beginning with production ``ActionPipeline.execute``.
    Sessions are in-memory, five-minute/20-action/10-concurrent bounded,
    and non-recoverable.
    """

    def __init__(
        self,
        clock: ClockV1,
        scenario: DemoScenarioV1 = FIXED_DEMO_SCENARIO_V1,
        executor: DemoExecutor | None = None,
    ) -> None:
        self._clock = clock
        self._scenario = scenario
        self._executor = executor or DemoExecutor(scenario)
        connection = sqlite3.connect(
            ":memory:",
            isolation_level=None,
            check_same_thread=False,
        )
        connection.row_factory = sqlite3.Row
        self._database = ControlDatabase(connection)
        apply_migrations(self._database, _DEMO_MIGRATIONS_V1)
        self._pipeline = ActionPipeline()
        self._policy_engine = PolicyEngine()
        self._dispatcher = ToolDispatcher()
        self._feedback_repository = FeedbackRepositoryV1(self._database)
        self._action_record_repository = ActionRecordRepositoryV1(self._database)
        self._stopping = StopEvaluator()
        self._visible_tree = _DemoVisibleTree()
        self._artifact_store = _DemoArtifactStore()
        self._action_id_generator = _DemoActionIdGenerator()
        reset_issued_action_ids()
        self._registry: dict[str, _DemoRunState] = {}

    @property
    def database(self) -> ControlDatabase:
        """The ephemeral in-memory wiring the real pipeline requires.

        Read-only inspection surface for the in-memory-only lifecycle
        proof: the database holds only demo turn/feedback/action rows and
        never a formal Run row; it never touches disk.
        """
        return self._database

    def create_session(self, demo_session_id: str) -> DemoSessionV1:
        """Create one bounded in-memory session at step 0.

        Expired sessions are pruned first (deterministic lifecycle), the
        10-session process cap is enforced, and the session value's
        ``state_digest`` binds the exact state (step, status, creation,
        and expiry) so every later advance can reject stale values.
        """
        now = self._clock.now()
        self._registry = {
            session_id: state
            for session_id, state in self._registry.items()
            if now.epoch_milliseconds < state.expires_at.epoch_milliseconds
        }
        if len(self._registry) >= DEMO_MAX_SESSIONS_V1:
            raise DemoAdvanceErrorV1(
                DemoAdvanceErrorCodeV1.SESSION_LIMIT,
                f"the Demo process cap of {DEMO_MAX_SESSIONS_V1} concurrent "
                "sessions is reached",
            )
        if demo_session_id in self._registry:
            raise DemoAdvanceErrorV1(
                DemoAdvanceErrorCodeV1.SESSION_ID_EXISTS,
                "a Demo session with this id already exists",
            )
        expires_at = CanonicalTimestampV1.from_epoch_milliseconds(
            now.epoch_milliseconds + DEMO_SESSION_TTL_MILLISECONDS_V1
        )
        state = _DemoRunState(
            step_index=0,
            status="DEMO_CREATED",
            action_count=0,
            created_at=now,
            expires_at=expires_at,
        )
        self._registry[demo_session_id] = state
        return self._session_value(demo_session_id, state)

    def session(self, demo_session_id: str) -> DemoSessionV1:
        """The current closed session value of one known session."""
        state = self._registry.get(demo_session_id)
        if state is None:
            raise DemoAdvanceErrorV1(
                DemoAdvanceErrorCodeV1.SESSION_NOT_FOUND,
                "no Demo session with this id exists",
            )
        return self._session_value(demo_session_id, state)

    def reset_session(self, demo_session_id: str) -> None:
        """Drop one session explicitly (SPEC §4.9 reset: a failure only
        affects that session and never creates a recovery protocol)."""
        if demo_session_id not in self._registry:
            raise DemoAdvanceErrorV1(
                DemoAdvanceErrorCodeV1.SESSION_NOT_FOUND,
                "no Demo session with this id exists",
            )
        del self._registry[demo_session_id]

    def advance(
        self,
        session: DemoSessionV1,
        decision: DemoDecisionV1 | None,
    ) -> DemoAdvanceResultV1:
        """Advance one session by exactly one fixed scenario step.

        The session value is validated against the in-memory registry
        (id, state digest, expiry) and the 20-action limit fires before
        any action; model-action steps drive the real shared pipeline
        (parse -> bind -> policy -> ALLOW-only dispatch -> feedback),
        writeback steps advance only through the exact fixed visitor
        decision, and every step ends with the real shared stop
        evaluation.  A completed session is discarded (SPEC §4.9), so
        the step results are the only lasting trace.
        """
        state = self._registry.get(session.demo_session_id)
        if state is None:
            raise DemoAdvanceErrorV1(
                DemoAdvanceErrorCodeV1.SESSION_NOT_FOUND,
                "no Demo session with this id exists",
            )
        expected = self._state_digest(state)
        if session.state_digest.value != expected:
            raise DemoAdvanceErrorV1(
                DemoAdvanceErrorCodeV1.STATE_MISMATCH,
                "the session value is stale or does not match the current state",
            )
        now = self._clock.now()
        if now.epoch_milliseconds >= state.expires_at.epoch_milliseconds:
            raise DemoAdvanceErrorV1(
                DemoAdvanceErrorCodeV1.SESSION_EXPIRED,
                "the Demo session has expired after five minutes",
            )
        if state.action_count >= DEMO_MAX_ACTIONS_V1:
            raise DemoAdvanceErrorV1(
                DemoAdvanceErrorCodeV1.ACTION_LIMIT,
                f"the Demo session reached its {DEMO_MAX_ACTIONS_V1}-action limit",
            )
        if state.step_index >= len(self._scenario.trace.steps):
            raise DemoAdvanceErrorV1(
                DemoAdvanceErrorCodeV1.STATE_MISMATCH,
                "the scenario trace ended before the session state",
            )
        step = self._scenario.trace.steps[state.step_index]
        if step.action_label == _WRITEBACK_LABEL_V1:
            self._advance_writeback(step, decision)
        else:
            self._advance_model_action(step, state, session.demo_session_id, now)
        stop_decision = self._stop_decision(state, now)
        next_state = _DemoRunState(
            step_index=state.step_index + 1,
            status=step.status,
            action_count=state.action_count + 1,
            created_at=state.created_at,
            expires_at=state.expires_at,
        )
        if step.status == "DEMO_COMPLETED":
            del self._registry[session.demo_session_id]
        else:
            self._registry[session.demo_session_id] = next_state
        return DemoAdvanceResultV1(
            schema_version=1,
            step=step,
            executor_kind="DEMO_EXECUTOR",
            stop_decision=stop_decision,
            formal_capability_calls=0,
        )

    def _advance_model_action(
        self,
        step: DemoStepResultV1,
        state: _DemoRunState,
        demo_session_id: str,
        now: CanonicalTimestampV1,
    ) -> None:
        """Drive one fixed model action through the real shared pipeline.

        The fixed script action is parsed, bound, policy-evaluated, and
        (only on ALLOW) dispatched through the Task 30.C ports; the fixed
        injected check failure materializes as structured CHECK feedback
        (SPEC §10.4 item 3), which is selected and consumed by the real
        Task 24.B/24.C functions.
        """
        action = self._script_action(state.step_index)
        response = _model_response(action)
        turn_id = f"demo-turn-{demo_session_id}-{state.step_index}"
        self._insert_demo_turn(
            turn_id, f"demo-run-{demo_session_id}-{state.step_index}"
        )
        context = ActionPipelineContextV1(
            turn_id=turn_id,
            consumed_feedback_refs=(),
            run_phase="AGENT_LOOP",
            editable_policy_digest=_FIXED_DIGEST,
            reference_profile_digest=_FIXED_DIGEST,
            current_candidate_digest=_FIXED_DIGEST,
            final_diff_digest=None,
            patch_path_fact=_script_patch_fact(state.step_index),
            visible_tree=self._visible_tree,
            ports=self._executor.tool_ports(),
            artifact_store=self._artifact_store,
            policy_engine=self._policy_engine,
            dispatcher=self._dispatcher,
            feedback_repository=self._feedback_repository,
            action_record_repository=self._action_record_repository,
            clock=self._clock,
            action_id_generator=self._action_id_generator,
        )
        self._pipeline.execute(response, context)
        if step.outcome == "CHECK_FAILED":
            records = build_feedback(self._fixed_check_result(), self._clock)
            self._feedback_repository.append(records)
        selection = select_feedback(self._rehydrate_feedback_records())
        if selection.refs:
            consume_feedback(turn_id, selection.refs, self._feedback_repository)

    def _advance_writeback(
        self, step: DemoStepResultV1, decision: DemoDecisionV1 | None
    ) -> None:
        """Advance one fixed writeback step through the exact visitor
        decision only.

        The visitor's ``DemoDecisionV1`` never becomes a formal approval
        or disclosure grant — it only advances the fixed scenario, and
        the emitted step carries the fixed canonical decision.
        """
        if step.decision.kind != "PRESENT":
            raise DemoAdvanceErrorV1(
                DemoAdvanceErrorCodeV1.STATE_MISMATCH,
                "the fixed scenario defines no decision for this writeback step",
            )
        if decision is None:
            raise DemoAdvanceErrorV1(
                DemoAdvanceErrorCodeV1.DECISION_REQUIRED,
                "the writeback step requires the visitor decision",
            )
        if decision.decision != step.decision.value.decision:
            raise DemoAdvanceErrorV1(
                DemoAdvanceErrorCodeV1.DECISION_MISMATCH,
                "the visitor decision does not match the fixed scenario step",
            )

    def _stop_decision(
        self, state: _DemoRunState, now: CanonicalTimestampV1
    ) -> Literal["CONTINUE", "STOP", "VALIDATE"]:
        """The real shared stop verdict over the demo state.

        The demo's own bounds reject before any action, so the fixed
        scenario always CONTINUEs; the shared precedence table still
        decides from the frozen demo limits and the session deadline.
        """
        decision: StopDecisionV1 = self._stopping.evaluate(
            RunLoopStateV1(
                turn_count=state.action_count,
                call_count=state.action_count,
                max_turns=DEMO_MAX_ACTIONS_V1,
                max_llm_calls=DEMO_MAX_ACTIONS_V1,
                run_deadline=state.expires_at,
                wait_deadline=None,
            ),
            LoopEvidenceV1(
                completion_requested=False,
                cancellation_honored=False,
            ),
            ProgressDecisionV1(
                has_progress=False,
                consecutive_no_progress_turns=0,
                consecutive_repeated_semantic=0,
                consecutive_invalid_outputs=0,
            ),
            now,
        )
        return decision.kind

    def _script_action(self, step_index: int) -> AgentAction:
        """The fixed model action of one script step.

        Steps 0/1/3 are the fixed patch actions; step 2 is the fixed
        scenario's expected patch; every other model-action step (only
        synthetic limit scenarios reach it) is the fixed closed run-check
        action over the frozen check plan.
        """
        if step_index == 2:
            return ApplyCandidatePatchAction(
                schema_version=1,
                action_type="apply_candidate_patch",
                base_candidate_digest=_FIXED_DIGEST,
                patch_format="UNIFIED_DIFF_V1",
                patch_text=self._scenario.expected_patch,
            )
        patch_text = dict(_DEMO_SCRIPT_PATCHES_V1).get(step_index)
        if patch_text is not None:
            return ApplyCandidatePatchAction(
                schema_version=1,
                action_type="apply_candidate_patch",
                base_candidate_digest=_FIXED_DIGEST,
                patch_format="UNIFIED_DIFF_V1",
                patch_text=patch_text,
            )
        return RunCheckActionV1(
            schema_version=1,
            action_type="run_check",
            check_plan_id=_FIXED_CHECK_PLAN_V1,
        )

    def _fixed_check_result(self) -> CheckResultV1:
        """The fixed failing check result of the injected failure."""
        return CheckResultV1(
            status="FAIL",
            check_kind=_FIXED_CHECK_PLAN_V1,
            structured_findings=(
                CheckFindingV1(
                    error_code="CHECK_FAILED",
                    message=(
                        f"the fixed injected failure: {self._scenario.injected_failure}"
                    ),
                    location=None,
                ),
            ),
            raw_digest=_FIXED_DIGEST,
        )

    def _rehydrate_feedback_records(self) -> tuple[FeedbackRecordV1, ...]:
        """Every stored feedback record, in append order.

        The Task 24.C repository exposes no read-back API, so the runner
        rehydrates the stored rows itself — a pure row-to-value mapping
        the real Task 24.B selection consumes.  Columns are read by
        name, so a column reorder cannot break the mapping; any row that
        fails to rehydrate into a closed record rejects closed (SPEC
        §5.2 fail-closed).
        """
        rows = self._database.read_rows(
            "SELECT feedback_id, kind, severity, created_at, summary,"
            " source_ref, bounded_payload, evidence_refs, consumed_by_turn_id"
            " FROM feedback_records ORDER BY rowid"
        )
        return tuple(_rehydrate_feedback_row(row) for row in rows)

    def _insert_demo_turn(self, turn_id: str, run_id: str) -> None:
        """Insert one in-memory demo turn row for the real pipeline's
        feedback consumption and action-record storage (raw wiring row;
        no formal Run row is ever created — foreign keys stay off, the
        SQLite default)."""
        with self._database.immediate_transaction() as tx:
            tx.execute(
                "INSERT INTO agent_turns (turn_id, run_id, status)"
                " VALUES (?, ?, 'ACTIVE')",
                (turn_id, run_id),
            )

    def _session_value(
        self, demo_session_id: str, state: _DemoRunState
    ) -> DemoSessionV1:
        return DemoSessionV1(
            demo_session_id=demo_session_id,
            scenario_version=1,
            status=state.status,
            state_digest=DigestV1(value=self._state_digest(state)),
            expires_at=state.expires_at,
        )

    @staticmethod
    def _state_digest(state: _DemoRunState) -> str:
        """The deterministic §0.1 state digest of one session state."""
        return domain_digest(
            "DemoSessionStateV1",
            1,
            {
                "step_index": state.step_index,
                "status": state.status,
                "created_at": state.created_at.value,
                "expires_at": state.expires_at.value,
            },
        )


_DEMO_MIGRATIONS_V1: Final = (
    RUN_WAIT_V1_MIGRATION,
    IDEMPOTENCY_V1_MIGRATION,
    DISCLOSURE_GRANTS_V1_MIGRATION,
    DISCLOSURE_AUTHORIZATIONS_V1_MIGRATION,
    MEMORY_V1_MIGRATION,
    AUDIT_V1_MIGRATION,
    AGENT_TURNS_V1_MIGRATION,
    FEEDBACK_V1_MIGRATION,
    ACTIONS_V1_MIGRATION,
)
"""The exact contiguous migration set of the in-memory wiring (the
migration engine requires contiguous versions from 1)."""


def _script_patch_fact(step_index: int) -> PatchPathFactV1:
    """The fixed pre-policy patch fact of one script step."""
    value = dict(_DEMO_SCRIPT_PATCH_FACTS_V1).get(step_index, "OK")
    return cast(PatchPathFactV1, value)


def _model_response(action: AgentAction) -> ModelResponse:
    """One fixed closed model response for a script action.

    The canonical JSON text, its plain SHA-256, and the exact byte count
    bind the exact action bytes (SPEC §4.4.4); deterministic across
    runs.
    """
    text = json.dumps(action.model_dump(), sort_keys=True, separators=(",", ":"))
    raw = text.encode("utf-8")
    return ModelResponse(
        schema_version=1,
        text=text,
        text_digest=hashlib.sha256(raw).hexdigest(),
        byte_count=len(raw),
    )


def _rehydrate_feedback_row(row: sqlite3.Row) -> FeedbackRecordV1:
    """One stored feedback row back into its closed record value.

    Reads every column by name (a column reorder cannot break the
    mapping) and fails closed on any unknown record kind — a corrupt or
    foreign row can never rehydrate as a wrong record (SPEC §5.2).
    """
    source_facts = json.loads(str(row["source_ref"]))
    kind = str(row["kind"])
    source_ref: FeedbackSourceV1
    if kind == "CHECK":
        path: AbsentV1 | PresentV1[CanonicalRelativePathV1] = AbsentV1(kind="ABSENT")
        if source_facts["path"]["kind"] == "PRESENT":
            path = PresentV1(
                kind="PRESENT",
                value=CanonicalRelativePathV1(source_facts["path"]["value"]),
            )
        source_ref = CheckFeedbackSourceV1(
            kind="CHECK",
            check_kind=source_facts["check_kind"],
            path=path,
        )
    elif kind == "ACTION":
        source_ref = ActionFeedbackSourceV1(
            kind="ACTION",
            action_id=source_facts["action_id"],
            semantic_digest=source_facts["semantic_digest"],
        )
    elif kind == "CONTROL":
        source_ref = ControlFeedbackSourceV1(
            kind="CONTROL",
            error_code=source_facts["error_code"],
        )
    else:
        raise DemoAdvanceErrorV1(
            DemoAdvanceErrorCodeV1.STATE_MISMATCH,
            "the demo wiring holds a feedback record of an unknown kind",
        )
    consumed = (
        str(row["consumed_by_turn_id"])
        if row["consumed_by_turn_id"] is not None
        else None
    )
    return FeedbackRecordV1(
        id=str(row["feedback_id"]),
        kind=cast(FeedbackKindV1, kind),
        severity=cast(FeedbackSeverityV1, str(row["severity"])),
        created_at=CanonicalTimestampV1(str(row["created_at"])),
        summary=str(row["summary"]),
        source_ref=source_ref,
        bounded_payload=str(row["bounded_payload"]),
        evidence_refs=tuple(json.loads(str(row["evidence_refs"]))),
        consumed_by_turn=consumed,
    )

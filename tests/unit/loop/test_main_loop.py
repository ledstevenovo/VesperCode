"""T25.3 legacy step 25.G: thin sequential agent-loop composition tests.

The exact RED test pins the declared stage sequence (context, one call,
the action pipeline, progress, stop, close) with recording children; the
matrix pins the exact composition of the 25.G Expected line — each
engine step calls context, one LLM call, parse, policy, dispatch,
feedback, and stop once in order, and the Mock/OpenAI, correction,
wait, cancel, stop, and completion traces use the child implementations
while preserving exactly one active turn and one eligible call
(SPEC §4.2.5/§4.2.6/§4.2.7, Registry row 25.G).
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any, Callable, Literal, Mapping, cast

import pytest

# The engine consumes pydantic runtime contracts; the hash-locked gate
# toolchain installs no runtime dependencies, so this module skips
# cleanly there (formal env runs it fully).
pytest.importorskip("pydantic")

from src.vespercode.candidate.patch_engine import CandidatePatchOutcomeV1
from src.vespercode.credentials.port import (
    CredentialBackendProbeV1,
    CredentialMissingV1,
    CredentialStatusV1,
    CredentialStoreMutationV1,
    SecretCredentialV1,
)
from src.vespercode.canonical.clock import FakeClockV1
from src.vespercode.canonical.path_v1 import CanonicalRelativePathV1
from src.vespercode.canonical.timestamp_v1 import CanonicalTimestampV1
from src.vespercode.contracts.evidence import ArtifactRefV1, DigestV1
from src.vespercode.contracts.optional import AbsentV1, PresentV1
from src.vespercode.contracts.run import (
    RunLimitsV1,
    RunPhase,
    RunStatus,
    WaitContextV1,
    WaitDecisionV1,
    WaitKind,
)
from src.vespercode.governance.disclosure_decision import (
    DecideDisclosureGrantV1,
    DisclosureDecisionServiceV1,
)
from src.vespercode.governance.disclosure_ledger import DisclosureLedger
from src.vespercode.governance.disclosure_scope import (
    DirectoryDisclosureScopeV1,
    DisclosureScopeSequenceV1,
)
from src.vespercode.governance.disclosure_subject import (
    DisclosureGrantSubjectV1,
    DisclosureSubjectRequestV1,
    build_disclosure_subject,
)
from src.vespercode.governance.request_sources import (
    RequestContentSegmentV1,
    RequestMessageV1,
    RequestSourceCategoryV1,
    validate_segment_sources,
)
from src.vespercode.governance.policy import PolicyEngine
from src.vespercode.llm.base import ModelResponse
from src.vespercode.llm.call_result import (
    PresentResponseDigestV1,
)
from src.vespercode.llm.mock_adapter import MockLLMAdapter
from src.vespercode.llm.openai_adapter import (
    LLMTransportResultV1,
    OpenAILLMAdapter,
)
from src.vespercode.llm.prepared_request import (
    MockPreparedModelRequestV1,
    OpenAIPreparedModelRequestV1,
    prepare_mock_request,
    prepare_openai_request,
)
from src.vespercode.loop.action_binding import reset_issued_action_ids
from src.vespercode.loop.action_pipeline import (
    ActionPipeline,
    ActionPipelineContextV1,
    ActionRecordRepositoryV1,
    ActionStepFeedbackV1,
    ActionStepResultV1,
)
from src.vespercode.loop.agent_actions import ActionInstanceV1
from src.vespercode.loop.call_orchestrator import (
    CallOnceV1,
    CallOrchestrator,
    LLMCallResultV1,
)
from src.vespercode.loop.cancellation import CancellationController
from src.vespercode.loop.context_projection import (
    ContextBudgetFailureV1,
    ContextProjectionV1,
)
from src.vespercode.loop.engine import (
    AgentLoopEngine,
    LoopContextBuilderPortV1,
    LoopRequestPreparerPortV1,
    LoopWaitProviderPortV1,
    RunFactsPortV1,
)
from src.vespercode.loop.feedback_consumption import (
    FeedbackRepositoryV1,
)
from src.vespercode.loop.progress import ProgressDecisionV1
from src.vespercode.loop.stopping import ContinueV1
from src.vespercode.loop.progress import ProgressEvaluator
from src.vespercode.loop.restart import RestartGuard
from src.vespercode.loop.stopping import StopEvaluator
from src.vespercode.loop.turn_boundary import (
    CloseTurnResultV1,
    TurnBoundary,
    TurnOutcomeV1,
)
from src.vespercode.loop.wait_control import WaitController
from src.vespercode.profiles.endpoints import OpenAIEndpointV1
from src.vespercode.profiles.llm import (
    MockLLMProfileV1,
    OpenAILLMProfileV1,
    load_llm_profile,
)
from src.vespercode.profiles.registry import build_profile_registry
from src.vespercode.storage.connection import (
    ControlDatabase,
    open_control_database,
)
from src.vespercode.storage.migration_engine import apply_migrations
from src.vespercode.storage.migrations.v0001_run_wait import RUN_WAIT_V1_MIGRATION
from src.vespercode.storage.migrations.v0002_idempotency import (
    IDEMPOTENCY_V1_MIGRATION,
)
from src.vespercode.storage.migrations.v0003_disclosure_grants import (
    DISCLOSURE_GRANTS_V1_MIGRATION,
)
from src.vespercode.storage.migrations.v0004_disclosure_authorizations import (
    DISCLOSURE_AUTHORIZATIONS_V1_MIGRATION,
)
from src.vespercode.storage.migrations.v0005_memory import MEMORY_V1_MIGRATION
from src.vespercode.storage.migrations.v0006_audit import AUDIT_V1_MIGRATION
from src.vespercode.storage.migrations.v0007_agent_turns import (
    AGENT_TURNS_V1_MIGRATION,
)
from src.vespercode.storage.migrations.v0008_feedback import FEEDBACK_V1_MIGRATION
from src.vespercode.storage.migrations.v0009_actions import ACTIONS_V1_MIGRATION
from src.vespercode.storage.run_repository import (
    RunRecordV1,
    RunRepository,
    TransitionCommandV1,
    TransitionResultV1,
)
from src.vespercode.tools.dispatcher import (
    ActionResultV1,
    CompletionOutcomeV1,
    DispatchContextV1,
    RunCheckOutcomeV1,
    ToolDispatcher,
)
from src.vespercode.tools.file_results import (
    FileToolErrorV1,
    ListFilesSuccessV1,
)

_CREATED_AT = CanonicalTimestampV1("2026-08-06T09:00:00.000Z")
_RUN_DEADLINE = CanonicalTimestampV1("2026-08-06T09:15:00.000Z")
_CLOCK_EPOCH = _CREATED_AT.epoch_milliseconds
_EXPIRES_AT = CanonicalTimestampV1("2026-08-06T09:05:00.000Z")
_DECIDED_AT = CanonicalTimestampV1("2026-08-06T09:01:00.000Z")
_CANDIDATE_DIGEST = "a" * 64
_REFERENCE_PROFILE_DIGEST = "b" * 64
_EDITABLE_POLICY_DIGEST = (
    build_profile_registry().resolve_editable("PYTHON_SRC_ONLY_V1").digest
)
_SUBJECT_DIGEST = "1" * 64

_OPENAI_BUILTIN = (
    Path(__file__).resolve().parents[3]
    / "src/vespercode/profiles/builtin/openai-single-turn-v1.json"
)
_MOCK_BUILTIN = (
    Path(__file__).resolve().parents[3]
    / "src/vespercode/profiles/builtin/mock-deterministic-v1.json"
)

_MIGRATIONS = (
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

_LIMITS = RunLimitsV1(
    max_turns=20,
    max_llm_calls=20,
    max_run_wall_clock_seconds=900,
    user_wait_timeout_seconds=300,
    tool_timeout_seconds=60,
    target_check_timeout_seconds=120,
    full_check_timeout_seconds=300,
    baseline_timeout_seconds=600,
    formal_validation_timeout_seconds=600,
)

_SCRIPT_RESPONSE_TEXT = (
    '{"schema_version":1,"action_type":"list_files","root":{"kind":"ROOT"},'
    '"recursive":false,"max_entries":1,"cursor":{"kind":"ABSENT"}}'
)
_COMPLETION_TEXT = json.dumps(
    {
        "schema_version": 1,
        "action_type": "propose_completion",
        "candidate_digest": _CANDIDATE_DIGEST,
        "rationale_summary": "the fix is complete",
    },
    sort_keys=True,
    separators=(",", ":"),
)


def _response(text: str) -> ModelResponse:
    raw = text.encode("utf-8")
    return ModelResponse(
        schema_version=1,
        text=text,
        text_digest=hashlib.sha256(raw).hexdigest(),
        byte_count=len(raw),
    )


def mock_profile() -> MockLLMProfileV1:
    loaded = load_llm_profile(_MOCK_BUILTIN.read_bytes())
    assert isinstance(loaded, MockLLMProfileV1)
    return loaded


def openai_profile() -> OpenAILLMProfileV1:
    loaded = load_llm_profile(_OPENAI_BUILTIN.read_bytes())
    assert isinstance(loaded, OpenAILLMProfileV1)
    return loaded


def _segment(
    category: RequestSourceCategoryV1,
    content: str,
    path: str | None = None,
) -> RequestContentSegmentV1:
    raw = content.encode("utf-8")
    return RequestContentSegmentV1(
        source_category=category,
        source_path=(
            AbsentV1(kind="ABSENT")
            if path is None
            else PresentV1(kind="PRESENT", value=CanonicalRelativePathV1(path))
        ),
        content=content,
        content_digest=hashlib.sha256(raw).hexdigest(),
        byte_count=len(raw),
    )


def _projection(
    *,
    path: str = "src/a.py",
    feedback_content: str | None = None,
) -> ContextProjectionV1:
    """One frozen projection: protocol + task + one source file segment."""
    user_segments = [
        _segment("TASK", "fix the failing test"),
        _segment("FILE_CONTENT", "source bytes", path),
    ]
    if feedback_content is not None:
        user_segments.append(_segment("FEEDBACK", feedback_content))
    messages = (
        RequestMessageV1(
            role="SYSTEM",
            segments=(_segment("HARNESS_PROTOCOL", "VesperCode protocol"),),
        ),
        RequestMessageV1(role="USER", segments=tuple(user_segments)),
    )
    byte_count = sum(
        len(segment.content.encode("utf-8"))
        for message in messages
        for segment in message.segments
    )
    return ContextProjectionV1(
        messages=messages,
        source_projection=(),
        canonical_byte_count=byte_count,
        projection_digest=hashlib.sha256(b"projection").hexdigest(),
    )


def _insert_run(
    database: ControlDatabase,
    run_id: str,
    *,
    status: str = "RUNNING",
    phase: str | None = "AGENT_LOOP",
    profile_id: str = "mock-deterministic-v1",
) -> None:
    with database.immediate_transaction() as tx:
        tx.execute(
            "INSERT INTO run_config_snapshots (config_snapshot_id, digest,"
            " llm_profile_id, reference_profile_id, policy_id, target_test_ids,"
            " limits_digest, frozen_at)"
            " VALUES (?, ?, ?, 'python-src-py312-v1', 'PYTHON_SRC_ONLY_V1',"
            " '[]', ?, ?)",
            (
                f"snap-{run_id}",
                hashlib.sha256(f"snap-{run_id}".encode("utf-8")).hexdigest(),
                profile_id,
                "c" * 64,
                _CREATED_AT.value,
            ),
        )
        tx.execute(
            "INSERT INTO runs (run_id, workspace_identity, config_snapshot_id,"
            " status, phase, revision, started_at, run_deadline)"
            " VALUES (?, 'ws-1', ?, ?, ?, 1, ?, ?)",
            (
                run_id,
                f"snap-{run_id}",
                status,
                phase,
                _CREATED_AT.value,
                _RUN_DEADLINE.value,
            ),
        )


def _active_turn(database: ControlDatabase, run_id: str) -> tuple[str, int] | None:
    rows = database.read_rows(
        "SELECT turn_id, revision FROM agent_turns"
        " WHERE run_id = ? AND status = 'ACTIVE'",
        (run_id,),
    )
    if not rows:
        return None
    return (str(rows[0][0]), int(rows[0][1]))


def _counter_row(database: ControlDatabase, run_id: str) -> tuple[int, int]:
    rows = database.read_rows(
        "SELECT turn_count, call_count FROM run_turn_call_counters WHERE run_id = ?",
        (run_id,),
    )
    if not rows:
        return (0, 0)
    return (int(rows[0][0]), int(rows[0][1]))


# ---------------------------------------------------------------------------
# The recording stages (the card's exact RED fixtures)
# ---------------------------------------------------------------------------


class _StageRecorder:
    """One named recorder: appends its stage name and returns a canned value."""

    def __init__(
        self,
        name: str,
        calls: list[str],
        value: Any,
    ) -> None:
        self._name = name
        self._calls = calls
        self._value = value

    def evaluate(self, *args: Any, **kwargs: Any) -> Any:
        self._calls.append(self._name)
        return self._value


class RecordingLoopStages:
    """One duck-typed recording implementation of every injected child.

    Only the six declared stage methods record; every other child returns
    canned values so the RED test pins exactly the declared sequence.
    """

    def __init__(self) -> None:
        self._calls: list[str] = []
        self.clock = FakeClockV1(_CLOCK_EPOCH)
        self.progress = _StageRecorder("progress", self._calls, None)
        self.stop = _StageRecorder("stop", self._calls, None)
        self._canned_projection = _projection()
        self._canned_request: CallOnceV1 | None = None
        self._canned_call: LLMCallResultV1 | None = None
        self._canned_step: ActionStepResultV1 | None = None
        self._canned_context: ActionPipelineContextV1 | None = None

    @property
    def calls(self) -> tuple[str, ...]:
        """The exact ordered stage record (the card's RED comparison)."""
        return tuple(self._calls)

    def build_context(self, run_id: str) -> ContextProjectionV1:
        self._calls.append("context")
        return self._canned_projection

    def prepare_call(self, run_id: str, projection: ContextProjectionV1) -> CallOnceV1:
        assert self._canned_request is not None
        return self._canned_request

    def call_once(self, command: CallOnceV1) -> LLMCallResultV1:
        self._calls.append("call_once")
        assert self._canned_call is not None
        return self._canned_call

    def resolve(
        self,
        request: MockPreparedModelRequestV1 | OpenAIPreparedModelRequestV1,
        result: LLMCallResultV1,
    ) -> ModelResponse | None:
        return _response(_SCRIPT_RESPONSE_TEXT)

    def build_step_context(
        self, run_id: str, projection: ContextProjectionV1
    ) -> ActionPipelineContextV1:
        assert self._canned_context is not None
        return self._canned_context

    def execute(
        self, response: ModelResponse, context: ActionPipelineContextV1
    ) -> ActionStepResultV1:
        self._calls.append("action_pipeline")
        assert self._canned_step is not None
        return self._canned_step

    def close_turn(
        self,
        run_id: str,
        turn_id: str,
        outcome: TurnOutcomeV1,
        expected_revision: int,
    ) -> CloseTurnResultV1:
        self._calls.append("close_turn")
        return CloseTurnResultV1(
            kind="APPLIED",
            message="turn closed",
            outcome=outcome,
            turn_count=1,
            call_count=1,
        )

    def enter(self, wait: WaitContextV1, now: CanonicalTimestampV1) -> Any:
        return None

    def resume(
        self,
        wait: WaitContextV1,
        decision: WaitDecisionV1,
        now: CanonicalTimestampV1,
    ) -> Any:
        return None

    def expire(self, wait: WaitContextV1, now: CanonicalTimestampV1) -> Any:
        return None

    def evaluate_safe_point(
        self, run: RunRecordV1, cancellation_requested: bool
    ) -> Any:
        from src.vespercode.loop.cancellation import CancellationDecisionV1

        return CancellationDecisionV1(kind="HOLD", reason="NO_CANCELLATION")

    def inspect(self, run: Any) -> Any:
        from src.vespercode.loop.restart import RestartDispositionV1

        return RestartDispositionV1(
            schema_version=1,
            kind="CONTINUE",
            stop_reason=None,
            resend_allowed=False,
            run_id=run.run_id,
        )

    def run_record(self, run_id: str) -> RunRecordV1:
        return RunRecordV1(
            run_id=run_id,
            workspace_identity="ws-1",
            status="RUNNING",
            phase=PresentV1(kind="PRESENT", value="AGENT_LOOP"),
            config_snapshot_id="snap-1",
            started_at=_CREATED_AT,
            run_deadline=_RUN_DEADLINE,
        )

    def run_limits(self, run_id: str) -> RunLimitsV1:
        return _LIMITS

    def turn_call_counts(self, run_id: str) -> tuple[int, int]:
        return (1, 1)

    def active_turn_exists(self, run_id: str) -> bool:
        return True

    def active_turn(self, run_id: str) -> tuple[str, int] | None:
        return ("turn-1", 1)

    def active_wait(self, run_id: str) -> WaitContextV1 | None:
        return None

    def pending_wait_decision(self, run_id: str) -> WaitDecisionV1 | None:
        return None

    def cancellation_requested(self, run_id: str) -> bool:
        return False

    def transition(self, command: TransitionCommandV1) -> TransitionResultV1:
        return TransitionResultV1(kind="APPLIED", message="transition applied")

    def wait_for_abort(self, run_id: str, abort_code: str) -> WaitContextV1 | None:
        return None


def _canned_step() -> ActionStepResultV1:
    return ActionStepResultV1(
        schema_version=1,
        parse_outcome="PARSED",
        policy_decision="ALLOW",
        action_id="act-1",
        dispatch_result=None,
        feedback=ActionStepFeedbackV1(schema_version=1, kind="NONE"),
        append_outcome=None,
        consume_outcome=None,
        action_record=None,
    )


def _canned_context(
    database: ControlDatabase,
) -> ActionPipelineContextV1:
    return ActionPipelineContextV1(
        turn_id="turn-1",
        consumed_feedback_refs=(),
        run_phase="AGENT_LOOP",
        editable_policy_digest=_EDITABLE_POLICY_DIGEST,
        reference_profile_digest=_REFERENCE_PROFILE_DIGEST,
        current_candidate_digest=_CANDIDATE_DIGEST,
        final_diff_digest=None,
        patch_path_fact="PATCH_PATH_NOT_EDITABLE",
        visible_tree=_StubTree(),
        ports=_StubPorts(),
        artifact_store=_StubArtifactStore(),
        policy_engine=PolicyEngine(),
        dispatcher=ToolDispatcher(),
        feedback_repository=FeedbackRepositoryV1(database),
        action_record_repository=ActionRecordRepositoryV1(database),
        clock=FakeClockV1(_CLOCK_EPOCH),
        action_id_generator=_SequenceIdGenerator(),
    )


class _StubTree:
    digest = "f" * 64

    def list_directories(self) -> tuple[CanonicalRelativePathV1, ...]:
        return ()

    def list_file_paths(self) -> tuple[CanonicalRelativePathV1, ...]:
        return ()

    def read_bytes(self, path: CanonicalRelativePathV1) -> bytes:
        raise KeyError(path)


class _StubArtifactStore:
    def put(self, payload: object) -> ArtifactRefV1:
        return ArtifactRefV1(
            artifact_id="artifact-1",
            digest=DigestV1(value=hashlib.sha256(b"payload").hexdigest()),
        )


class _StubPorts:
    """One registered six-port set (the Task 17.C typed-attribute shape)."""

    list_files: Callable[..., Any] | None
    read_file: Callable[..., Any] | None
    search_text: Callable[..., Any] | None
    apply_candidate_patch: Callable[..., Any] | None
    run_check: Callable[..., Any] | None
    propose_completion: Callable[..., Any] | None

    def __init__(self) -> None:
        self.list_files = lambda tree, action: ListFilesSuccessV1(
            kind="SUCCESS",
            entries=(),
            truncated=False,
            next_cursor=AbsentV1(kind="ABSENT"),
        )
        self.read_file = lambda tree, action: FileToolErrorV1(
            kind="ERROR",
            error_code="FILE_NOT_TEXT",
            bounded_message="the file is not a supported text file",
        )
        self.search_text = lambda tree, action: FileToolErrorV1(
            kind="ERROR",
            error_code="FILE_NOT_TEXT",
            bounded_message="the file is not a supported text file",
        )
        self.apply_candidate_patch = lambda action: _patch_outcome_rejected()
        self.run_check = lambda action: RunCheckOutcomeV1(
            kind="REJECTED",
            error_code="INTERNAL_ERROR",
            bounded_message="the target check plan could not run",
        )
        self.propose_completion = lambda action: CompletionOutcomeV1(
            kind="VALIDATION_REQUESTED"
        )


def _patch_outcome_rejected() -> CandidatePatchOutcomeV1:
    raise AssertionError("a patch action must never reach a port in this matrix")


class SpyDispatcher(ToolDispatcher):
    """One dispatcher spy counting every dispatch invocation."""

    def __init__(self) -> None:
        super().__init__()
        self.call_count = 0

    def dispatch(
        self, instance: ActionInstanceV1, context: DispatchContextV1
    ) -> ActionResultV1:
        self.call_count += 1
        return super().dispatch(instance, context)


class _SequenceIdGenerator:
    """One deterministic Harness action-id generator."""

    def __init__(self) -> None:
        self._next = 0

    def next_id(self) -> str:
        self._next += 1
        return f"act-{self._next}"


@pytest.fixture
def stages(tmp_path: Path) -> RecordingLoopStages:
    recording = RecordingLoopStages()
    database = open_control_database(tmp_path / "recording.db")
    apply_migrations(database, _MIGRATIONS)
    recording._canned_context = _canned_context(database)
    recording._canned_request = _canned_mock_command("run-1")
    recording._canned_call = _canned_call_result()
    recording._canned_step = _canned_step()
    recording.progress._value = ProgressDecisionV1(
        has_progress=False,
        consecutive_no_progress_turns=0,
        consecutive_repeated_semantic=0,
        consecutive_invalid_outputs=0,
    )
    recording.stop._value = ContinueV1(
        kind="CONTINUE", message="the loop may begin the next turn"
    )
    return recording


def _canned_mock_command(run_id: str) -> CallOnceV1:
    profile = mock_profile()
    request = prepare_mock_request(profile, _projection().messages)
    return CallOnceV1(
        schema_version=1,
        run_id=run_id,
        request=request,
        llm_profile_digest=profile.digest,
        adapter_version=profile.adapter_version,
        script_id=profile.script_id,
        script_digest=profile.script_digest,
    )


def _canned_call_result() -> LLMCallResultV1:
    raw = _SCRIPT_RESPONSE_TEXT.encode("utf-8")
    return LLMCallResultV1(
        schema_version=1,
        mode="MOCK",
        llm_profile_digest=mock_profile().digest,
        request_digest=hashlib.sha256(b"request").hexdigest(),
        authorization_record_ref=AbsentV1(kind="ABSENT"),
        status="SUCCEEDED",
        response_digest=PresentResponseDigestV1(
            kind="PRESENT", value=hashlib.sha256(raw).hexdigest()
        ),
        error=AbsentV1(kind="ABSENT"),
    )


@pytest.fixture
def engine(stages: RecordingLoopStages) -> AgentLoopEngine:
    return AgentLoopEngine(
        stop_evaluator=stages.stop,
        progress_evaluator=stages.progress,
        turn_boundary=stages,
        call_orchestrator=stages,
        action_pipeline=stages,
        wait_controller=stages,
        cancellation_controller=stages,
        restart_guard=stages,
        run_facts=stages,
        context_builder=stages,
        request_preparer=stages,
        response_resolver=stages,
        step_context_builder=stages,
        wait_provider=stages,
        clock=stages.clock,
    )


def test_one_engine_step_calls_each_stage_once_in_order(
    engine: AgentLoopEngine,
    stages: RecordingLoopStages,
) -> None:
    engine.step("run-1")
    # The card displays this assertion on one 97-char line; the repo's
    # own formatter wraps it (T17.1/T24.1 precedent) — the tuple is
    # byte-identical to the card.
    assert stages.calls == (
        "context",
        "call_once",
        "action_pipeline",
        "progress",
        "stop",
        "close_turn",
    )


# ---------------------------------------------------------------------------
# Real-children composition fixtures (the 25.G matrix)
# ---------------------------------------------------------------------------


class _DbRunFacts:
    """One production-shaped RunFactsPortV1 over the control database.

    Reads the persisted run, limits, counters, active turn, and wait rows
    and applies transitions through the Task 7.B repository; the engine
    owns no SQL.
    """

    def __init__(
        self,
        database: ControlDatabase,
        *,
        limits: RunLimitsV1 = _LIMITS,
        cancellation: bool = False,
    ) -> None:
        self._database = database
        self._limits = limits
        self._cancellation = cancellation
        self._decisions: dict[str, WaitDecisionV1] = {}

    def run_record(self, run_id: str) -> RunRecordV1:
        rows = self._database.read_rows(
            "SELECT workspace_identity, config_snapshot_id, status, phase,"
            " started_at, run_deadline FROM runs WHERE run_id = ?",
            (run_id,),
        )
        assert rows, "the seeded run must exist"
        row = rows[0]
        return RunRecordV1(
            run_id=run_id,
            workspace_identity=str(row[0]),
            config_snapshot_id=str(row[1]),
            status=cast(RunStatus, str(row[2])),
            phase=(
                PresentV1(kind="PRESENT", value=cast(RunPhase, str(row[3])))
                if row[3] is not None
                else AbsentV1(kind="ABSENT")
            ),
            started_at=CanonicalTimestampV1(str(row[4])),
            run_deadline=CanonicalTimestampV1(str(row[5])),
        )

    def run_limits(self, run_id: str) -> RunLimitsV1:
        return self._limits

    def turn_call_counts(self, run_id: str) -> tuple[int, int]:
        rows = self._database.read_rows(
            "SELECT turn_count, call_count FROM run_turn_call_counters"
            " WHERE run_id = ?",
            (run_id,),
        )
        if not rows:
            return (0, 0)
        return (int(rows[0][0]), int(rows[0][1]))

    def active_turn_exists(self, run_id: str) -> bool:
        rows = self._database.read_rows(
            "SELECT 1 FROM agent_turns WHERE run_id = ? AND status = 'ACTIVE'",
            (run_id,),
        )
        return bool(rows)

    def active_turn(self, run_id: str) -> tuple[str, int] | None:
        rows = self._database.read_rows(
            "SELECT turn_id, revision FROM agent_turns"
            " WHERE run_id = ? AND status = 'ACTIVE'",
            (run_id,),
        )
        if not rows:
            return None
        return (str(rows[0][0]), int(rows[0][1]))

    def active_wait(self, run_id: str) -> WaitContextV1 | None:
        rows = self._database.read_rows(
            "SELECT wait_id, wait_kind, source_phase, subject_digest,"
            " created_at, expires_at FROM wait_contexts"
            " WHERE run_id = ? AND status IN ('PENDING', 'DECIDING')",
            (run_id,),
        )
        if not rows:
            return None
        row = rows[0]
        return WaitContextV1(
            wait_id=str(row[0]),
            run_id=run_id,
            wait_kind=cast(WaitKind, str(row[1])),
            source_phase=cast(Literal["AGENT_LOOP", "FORMAL_VALIDATION"], str(row[2])),
            subject_digest=DigestV1(value=str(row[3])),
            created_at=CanonicalTimestampV1(str(row[4])),
            expires_at=CanonicalTimestampV1(str(row[5])),
        )

    def pending_wait_decision(self, run_id: str) -> WaitDecisionV1 | None:
        return self._decisions.get(run_id)

    def cancellation_requested(self, run_id: str) -> bool:
        return self._cancellation

    def transition(self, command: TransitionCommandV1) -> TransitionResultV1:
        return RunRepository(self._database).compare_and_transition(command)


class _QueueContextBuilder:
    """One context-assembly port returning canned projections in order."""

    def __init__(self, projections: list[ContextProjectionV1]) -> None:
        self._projections = list(projections)

    def build_context(
        self, run_id: str
    ) -> ContextProjectionV1 | ContextBudgetFailureV1:
        return self._projections.pop(0)


class _MockRequestPreparer:
    """One production-shaped preparer (frozen profile + projection)."""

    def __init__(self, profile: MockLLMProfileV1) -> None:
        self._profile = profile

    def prepare_call(self, run_id: str, projection: ContextProjectionV1) -> CallOnceV1:
        request = prepare_mock_request(self._profile, projection.messages)
        return CallOnceV1(
            schema_version=1,
            run_id=run_id,
            request=request,
            llm_profile_digest=self._profile.digest,
            adapter_version=self._profile.adapter_version,
            script_id=self._profile.script_id,
            script_digest=self._profile.script_digest,
        )


class _OpenAIRequestPreparer:
    """One production-shaped preparer for the OpenAI trace."""

    def __init__(
        self,
        profile: OpenAILLMProfileV1,
        *,
        grant_id: str,
        authorization_record_id: str,
        event_id: str,
    ) -> None:
        self._profile = profile
        self._grant_id = grant_id
        self._authorization_record_id = authorization_record_id
        self._event_id = event_id

    def prepare_call(self, run_id: str, projection: ContextProjectionV1) -> CallOnceV1:
        request = prepare_openai_request(self._profile, projection.messages)
        return CallOnceV1(
            schema_version=1,
            run_id=run_id,
            request=request,
            llm_profile_digest=self._profile.digest,
            adapter_version=self._profile.adapter_version,
            endpoint_id=self._profile.endpoint_id,
            model=self._profile.model,
            request_serializer_version=self._profile.request_serializer_version,
            redaction_profile_id=self._profile.redaction_profile_id,
            grant_id=self._grant_id,
            authorization_record_id=self._authorization_record_id,
            event_id=self._event_id,
        )


class _QueueResponseResolver:
    """One call-free response resolver: canned responses per call order.

    The resolver performs no adapter invocation, no counting, and no
    transport — the one eligible call per step is the orchestrator's
    counted invocation (pinned by the counting/transport evidence).
    """

    def __init__(self, responses: list[ModelResponse | None]) -> None:
        self._responses = list(responses)

    def resolve(
        self,
        request: MockPreparedModelRequestV1 | OpenAIPreparedModelRequestV1,
        result: LLMCallResultV1,
    ) -> ModelResponse | None:
        if result.status != "SUCCEEDED":
            return None
        if not self._responses:
            return None
        return self._responses.pop(0)


class _FixedStepContextBuilder:
    """One production-shaped step-context assembly (real repositories)."""

    def __init__(
        self,
        database: ControlDatabase,
        *,
        candidate_digest: str | None = _CANDIDATE_DIGEST,
    ) -> None:
        self._database = database
        self._candidate_digest = candidate_digest

    def build_step_context(
        self, run_id: str, projection: ContextProjectionV1
    ) -> ActionPipelineContextV1:
        active = _active_turn(self._database, run_id)
        assert active is not None, "the counted call must own an ACTIVE turn"
        turn_id, _ = active
        reset_issued_action_ids()
        return ActionPipelineContextV1(
            turn_id=turn_id,
            consumed_feedback_refs=projection.feedback_refs,
            run_phase="AGENT_LOOP",
            editable_policy_digest=_EDITABLE_POLICY_DIGEST,
            reference_profile_digest=_REFERENCE_PROFILE_DIGEST,
            current_candidate_digest=self._candidate_digest,
            final_diff_digest=None,
            patch_path_fact="PATCH_PATH_NOT_EDITABLE",
            visible_tree=_StubTree(),
            ports=_StubPorts(),
            artifact_store=_StubArtifactStore(),
            policy_engine=PolicyEngine(),
            dispatcher=SpyDispatcher(),
            feedback_repository=FeedbackRepositoryV1(self._database),
            action_record_repository=ActionRecordRepositoryV1(self._database),
            clock=FakeClockV1(_CLOCK_EPOCH),
            action_id_generator=_SequenceIdGenerator(),
        )


class _FixedWaitProvider:
    """One wait-provision port: a configured abort-to-wait map.

    The provider owns the governance decision "does this abort require a
    declared wait?"; the engine only asks.  When a wait is returned it is
    also persisted (the production wiring's Task 7.B create_wait).
    """

    def __init__(
        self,
        database: ControlDatabase,
        waits: dict[str, WaitContextV1],
    ) -> None:
        self._database = database
        self._waits = dict(waits)
        self._next_wait = 1

    def wait_for_abort(self, run_id: str, abort_code: str) -> WaitContextV1 | None:
        wait = self._waits.pop(abort_code, None)
        if wait is None:
            return None
        RunRepository(self._database).create_wait(wait)
        return wait


def _script_response() -> ModelResponse:
    return _response(_SCRIPT_RESPONSE_TEXT)


def _completion_response() -> ModelResponse:
    return _response(_COMPLETION_TEXT)


def _invalid_response() -> ModelResponse:
    return _response("this is not a json object")


def _deny_patch_response() -> ModelResponse:
    facts = {
        "schema_version": 1,
        "action_type": "apply_candidate_patch",
        "base_candidate_digest": _CANDIDATE_DIGEST,
        "patch_format": "UNIFIED_DIFF_V1",
        "patch_text": "--- a/docs/outside.md\n+++ b/docs/outside.md\n",
    }
    return _response(
        json.dumps(facts, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    )


def _wait_for_run(run_id: str, wait_id: str) -> WaitContextV1:
    """One declared DISCLOSURE_GRANT wait bound to the run."""
    return WaitContextV1(
        wait_id=wait_id,
        run_id=run_id,
        wait_kind="DISCLOSURE_GRANT",
        source_phase="AGENT_LOOP",
        subject_digest=DigestV1(value=_SUBJECT_DIGEST),
        created_at=_CREATED_AT,
        expires_at=_EXPIRES_AT,
    )


def _real_engine(
    database: ControlDatabase,
    *,
    orchestrator: CallOrchestrator,
    projections: list[ContextProjectionV1],
    responses: list[ModelResponse | None],
    limits: RunLimitsV1 = _LIMITS,
    cancellation: bool = False,
    wait_provider: LoopWaitProviderPortV1 | None = None,
    candidate_digest: str | None = _CANDIDATE_DIGEST,
    clock: FakeClockV1 | None = None,
    run_facts: RunFactsPortV1 | None = None,
    context_builder: LoopContextBuilderPortV1 | None = None,
    request_preparer: LoopRequestPreparerPortV1 | None = None,
) -> AgentLoopEngine:
    """One engine over the real 25.A-25.F children plus fixture ports."""
    facts = (
        run_facts
        if run_facts is not None
        else _DbRunFacts(database, limits=limits, cancellation=cancellation)
    )
    if wait_provider is None:
        wait_provider = _FixedWaitProvider(database, {})
    return AgentLoopEngine(
        stop_evaluator=StopEvaluator(),
        progress_evaluator=ProgressEvaluator(),
        turn_boundary=TurnBoundary(database, clock=FakeClockV1(_CLOCK_EPOCH)),
        call_orchestrator=orchestrator,
        action_pipeline=ActionPipeline(),
        wait_controller=WaitController(),
        cancellation_controller=CancellationController(),
        restart_guard=RestartGuard(),
        run_facts=facts,
        context_builder=(
            context_builder
            if context_builder is not None
            else _QueueContextBuilder(projections)
        ),
        request_preparer=(
            request_preparer
            if request_preparer is not None
            else _MockRequestPreparer(mock_profile())
        ),
        response_resolver=_QueueResponseResolver(responses),
        step_context_builder=_FixedStepContextBuilder(
            database, candidate_digest=candidate_digest
        ),
        wait_provider=wait_provider,
        clock=clock if clock is not None else FakeClockV1(_CLOCK_EPOCH),
    )


def _limits(*, max_turns: int = 20, max_llm_calls: int = 20) -> RunLimitsV1:
    """One frozen limit set with the exact turn/call caps."""
    return RunLimitsV1(
        max_turns=max_turns,
        max_llm_calls=max_llm_calls,
        max_run_wall_clock_seconds=900,
        user_wait_timeout_seconds=300,
        tool_timeout_seconds=60,
        target_check_timeout_seconds=120,
        full_check_timeout_seconds=300,
        baseline_timeout_seconds=600,
        formal_validation_timeout_seconds=600,
    )


class _CredentialStore:
    """One credential port with a configurable missing/present value."""

    def __init__(self, missing: bool = True) -> None:
        self._missing = missing
        self.probe_calls = 0
        self.read_calls = 0

    def probe_backend(self) -> CredentialBackendProbeV1:
        self.probe_calls += 1
        return CredentialBackendProbeV1(
            schema_version=1,
            backend_id="WINDOWS_CREDENTIAL_MANAGER",
            capability="READ_WRITE_DELETE",
        )

    def get_for_call(self, provider: str) -> SecretCredentialV1 | CredentialMissingV1:
        self.read_calls += 1
        if self._missing:
            return CredentialMissingV1(schema_version=1, kind="MISSING")
        return SecretCredentialV1.from_hidden_input("test-secret")

    def set(
        self, provider: str, secret: SecretCredentialV1
    ) -> CredentialStoreMutationV1:
        raise NotImplementedError("the loop never mutates credentials")

    def status(self, provider: str) -> CredentialStatusV1:
        raise NotImplementedError("the loop never reads credential status")

    def clear(self, provider: str) -> CredentialStoreMutationV1:
        raise NotImplementedError("the loop never clears credentials")


class _TransportSpy:
    """One bounded HTTP transport spy with a configurable failure status."""

    def __init__(self) -> None:
        self.attempts = 0
        self.fail_status: int | None = None

    def post(
        self,
        url: str,
        headers: Mapping[str, str],
        body: bytes,
    ) -> LLMTransportResultV1:
        self.attempts += 1
        if self.fail_status is not None:
            return LLMTransportResultV1(
                status_code=self.fail_status, headers=(), body=b""
            )
        return LLMTransportResultV1(
            status_code=200,
            headers=(),
            body=json.dumps(
                {"choices": [{"message": {"content": _SCRIPT_RESPONSE_TEXT}}]},
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8"),
        )


def _disclosure_subject(run_id: str) -> DisclosureGrantSubjectV1:
    """One grant subject over the in-scope projection sources (Task 15.2)."""
    sources = validate_segment_sources(_projection().messages)
    scopes: DisclosureScopeSequenceV1 = (
        DirectoryDisclosureScopeV1(
            kind="DIRECTORY", path=CanonicalRelativePathV1("src")
        ),
    )
    return build_disclosure_subject(
        DisclosureSubjectRequestV1(
            run_id=run_id,
            expires_at=_EXPIRES_AT,
            cumulative_byte_budget=1000,
            url=AbsentV1(kind="ABSENT"),
        ),
        sources,
        scopes,
        openai_profile(),
        OpenAIEndpointV1(
            endpoint_id="OPENAI_PUBLIC_API_V1",
            scheme="https",
            host="api.openai.com",
            effective_port=443,
            base_path="/v1",
        ),
    )


def _seed_granted_run(database: ControlDatabase, run_id: str) -> None:
    """Insert one run, wait, and APPROVED Grant (the Task 15.2 lifecycle)."""
    _insert_run(
        database,
        run_id,
        status="WAITING_USER",
        phase=None,
        profile_id="openai-single-turn-v1",
    )
    subject = _disclosure_subject(run_id)
    RunRepository(database).create_wait(
        WaitContextV1(
            wait_id=f"wait-{run_id}",
            run_id=run_id,
            wait_kind="DISCLOSURE_GRANT",
            source_phase="AGENT_LOOP",
            subject_digest=DigestV1(value=subject.digest),
            created_at=_CREATED_AT,
            expires_at=_EXPIRES_AT,
        )
    )
    outcome = DisclosureDecisionServiceV1(database).decide(
        DecideDisclosureGrantV1(
            decision=WaitDecisionV1(
                wait_id=f"wait-{run_id}",
                run_id=run_id,
                wait_kind="DISCLOSURE_GRANT",
                subject_digest=DigestV1(value=subject.digest),
                decision="APPROVE",
                event_id=f"evt-{run_id}",
                decided_at=_DECIDED_AT,
            ),
            subject=subject,
            grant_id=f"grant-{run_id}",
        )
    )
    assert outcome.kind == "APPROVED"


def _mock_orchestrator(
    database: ControlDatabase,
    tmp_path: Path,
) -> CallOrchestrator:
    """One real orchestrator over the real Mock adapter (no real ports)."""
    return CallOrchestrator(
        boundary=TurnBoundary(database, clock=FakeClockV1(_CLOCK_EPOCH)),
        ledger=DisclosureLedger(database, tmp_path / "ledger.db"),
        credential_store=_CredentialStore(),
        mock_adapter=MockLLMAdapter(),
        clock=FakeClockV1(_CLOCK_EPOCH),
    )


def _openai_orchestrator(
    database: ControlDatabase,
    tmp_path: Path,
    *,
    credential: _CredentialStore,
    transport: _TransportSpy,
) -> CallOrchestrator:
    """One real orchestrator over the real OpenAI adapter and ledger."""
    return CallOrchestrator(
        boundary=TurnBoundary(database, clock=FakeClockV1(_CLOCK_EPOCH)),
        ledger=DisclosureLedger(database, tmp_path / "ledger.db"),
        credential_store=credential,
        mock_adapter=MockLLMAdapter(),
        openai_adapter=OpenAILLMAdapter(transport=transport),
        clock=FakeClockV1(_CLOCK_EPOCH),
    )


@pytest.fixture
def control_database(tmp_path: Path) -> Iterator[ControlDatabase]:
    database = open_control_database(tmp_path / "main_loop.db")
    apply_migrations(database, _MIGRATIONS)
    yield database
    database.close()


def test_engine_mock_trace_uses_child_implementations(
    control_database: ControlDatabase,
    tmp_path: Path,
) -> None:
    """The Mock composition: one eligible call, one active turn closed."""
    _insert_run(control_database, "run-1")
    engine = _real_engine(
        control_database,
        orchestrator=_mock_orchestrator(control_database, tmp_path),
        projections=[_projection()],
        responses=[_script_response()],
    )
    result = engine.step("run-1")
    assert result.kind == "CONTINUE"
    assert result.turn_count == 1
    assert result.call_count == 1
    assert [entry.stage for entry in result.evidence] == [
        "context",
        "call_once",
        "action_pipeline",
        "progress",
        "stop",
        "close_turn",
    ]
    # Exactly one turn was created and closed with SUCCEEDED.
    turns = control_database.read_rows(
        "SELECT status, outcome FROM agent_turns WHERE run_id = 'run-1'"
    )
    assert len(turns) == 1
    assert turns[0][0] == "CLOSED"
    assert turns[0][1] == "SUCCEEDED"
    # The run stays in the loop phase on a CONTINUE step.
    runs = control_database.read_rows(
        "SELECT status, phase FROM runs WHERE run_id = 'run-1'"
    )
    assert runs[0][0] == "RUNNING"
    assert runs[0][1] == "AGENT_LOOP"


def test_engine_openai_trace_uses_child_implementations(
    control_database: ControlDatabase,
    tmp_path: Path,
) -> None:
    """The OpenAI composition: one authorized call, one transport attempt."""
    _seed_granted_run(control_database, "run-1")
    credential = _CredentialStore(missing=False)
    transport = _TransportSpy()
    engine = _real_engine(
        control_database,
        orchestrator=_openai_orchestrator(
            control_database, tmp_path, credential=credential, transport=transport
        ),
        projections=[_projection()],
        responses=[_script_response()],
        request_preparer=_OpenAIRequestPreparer(
            openai_profile(),
            grant_id="grant-run-1",
            authorization_record_id="rec-1",
            event_id="evt-1",
        ),
    )
    result = engine.step("run-1")
    assert result.kind == "CONTINUE"
    assert result.turn_count == 1
    assert result.call_count == 1
    # Exactly one credential probe/read and exactly one transport attempt.
    assert credential.probe_calls == 1
    assert credential.read_calls == 1
    assert transport.attempts == 1
    turns = control_database.read_rows(
        "SELECT status, outcome FROM agent_turns WHERE run_id = 'run-1'"
    )
    assert len(turns) == 1
    assert turns[0][1] == "SUCCEEDED"


def test_engine_correction_trace_consumes_feedback_once(
    control_database: ControlDatabase,
    tmp_path: Path,
) -> None:
    """The correction composition: the appended failure feedback is bound
    to the next turn's projection and consumed exactly once (AC-05)."""
    _insert_run(control_database, "run-1")

    class _FeedbackProjectionBuilder:
        """First projection plain; the second carries the appended record."""

        def __init__(self) -> None:
            self._first = True

        def build_context(
            self, run_id: str
        ) -> ContextProjectionV1 | ContextBudgetFailureV1:
            if self._first:
                self._first = False
                return _projection()
            rows = control_database.read_rows(
                "SELECT feedback_id FROM feedback_records"
                " WHERE consumed_by_turn_id IS NULL ORDER BY feedback_id"
            )
            assert rows, "the DENY step must have appended one record"
            feedback_id = str(rows[0][0])
            return _projection(feedback_content='{"id":"%s"}' % feedback_id)

    engine = _real_engine(
        control_database,
        orchestrator=_mock_orchestrator(control_database, tmp_path),
        projections=[_projection()],
        responses=[_deny_patch_response(), _script_response()],
        context_builder=_FeedbackProjectionBuilder(),
    )
    first = engine.step("run-1")
    assert first.kind == "CONTINUE"
    records = control_database.read_rows(
        "SELECT feedback_id, consumed_by_turn_id FROM feedback_records"
    )
    assert len(records) == 1
    assert records[0][1] is None
    second = engine.step("run-1")
    assert second.kind == "CONTINUE"
    records = control_database.read_rows(
        "SELECT feedback_id, consumed_by_turn_id FROM feedback_records"
    )
    assert len(records) == 1
    assert records[0][1] is not None


def test_engine_writeback_resume_hands_off_to_persistence(
    control_database: ControlDatabase,
    tmp_path: Path,
) -> None:
    """A FINAL_WRITEBACK approval enters RUNNING(PERSISTENCE) and hands
    the run to the persistence coordinator (a DEFERRED boundary), never
    a false INTERNAL_ERROR from the loop's phase gate (SPEC §4.2.7)."""
    _insert_run(
        control_database,
        "run-1",
        status="WAITING_USER",
        phase=None,
        profile_id="openai-single-turn-v1",
    )
    facts = _DbRunFacts(control_database)
    writeback_wait = WaitContextV1(
        wait_id="wait-wb",
        run_id="run-1",
        wait_kind="FINAL_WRITEBACK",
        source_phase="FORMAL_VALIDATION",
        subject_digest=DigestV1(value=_SUBJECT_DIGEST),
        created_at=_CREATED_AT,
        expires_at=_EXPIRES_AT,
    )
    RunRepository(control_database).create_wait(writeback_wait)
    facts._decisions["run-1"] = WaitDecisionV1(
        wait_id="wait-wb",
        run_id="run-1",
        wait_kind="FINAL_WRITEBACK",
        subject_digest=DigestV1(value=_SUBJECT_DIGEST),
        decision="APPROVE",
        event_id="evt-wb",
        decided_at=_DECIDED_AT,
    )
    engine = _real_engine(
        control_database,
        orchestrator=_mock_orchestrator(control_database, tmp_path),
        projections=[],
        responses=[],
        run_facts=facts,
    )
    boundary = engine.run_until_boundary("run-1")
    assert boundary.kind == "DEFERRED"
    assert boundary.stop_reason is None
    runs = control_database.read_rows(
        "SELECT status, phase FROM runs WHERE run_id = 'run-1'"
    )
    assert runs[0][0] == "RUNNING"
    assert runs[0][1] == "PERSISTENCE"
    assert _counter_row(control_database, "run-1") == (0, 0)


def test_engine_wait_trace_pauses_and_resumes_once(
    control_database: ControlDatabase,
    tmp_path: Path,
) -> None:
    """The wait composition: a declared DISCLOSURE_GRANT wait pauses the
    loop, resumes exactly once, and returns to the same loop core."""
    _seed_granted_run(control_database, "run-1")
    credential = _CredentialStore(missing=False)
    transport = _TransportSpy()
    facts = _DbRunFacts(control_database)
    wait_provider = _FixedWaitProvider(
        control_database,
        {"DISCLOSURE_SCOPE_EXCEEDED": _wait_for_run("run-1", "wait-1")},
    )
    engine = _real_engine(
        control_database,
        orchestrator=_openai_orchestrator(
            control_database, tmp_path, credential=credential, transport=transport
        ),
        projections=[_projection(path="docs/x.md"), _projection(path="docs/x.md")],
        responses=[_script_response()],
        request_preparer=_OpenAIRequestPreparer(
            openai_profile(),
            grant_id="grant-run-1",
            authorization_record_id="rec-1",
            event_id="evt-1",
        ),
        wait_provider=wait_provider,
        run_facts=facts,
    )
    # The out-of-scope abort enters the declared wait with zero counts.
    step = engine.step("run-1")
    assert step.kind == "WAITING"
    assert step.wait_kind == "DISCLOSURE_GRANT"
    assert step.turn_count == 0
    assert step.call_count == 0
    runs = control_database.read_rows("SELECT status FROM runs WHERE run_id = 'run-1'")
    assert runs[0][0] == "WAITING_USER"
    # Without a decision the boundary pauses at the declared wait.
    boundary = engine.run_until_boundary("run-1")
    assert boundary.kind == "WAITING"
    assert boundary.wait_id == "wait-1"
    # The exact approval resumes once and returns to the loop.
    facts._decisions["run-1"] = WaitDecisionV1(
        wait_id="wait-1",
        run_id="run-1",
        wait_kind="DISCLOSURE_GRANT",
        subject_digest=DigestV1(value=_SUBJECT_DIGEST),
        decision="APPROVE",
        event_id="evt-approve",
        decided_at=_DECIDED_AT,
    )
    boundary = engine.run_until_boundary("run-1")
    assert boundary.kind == "STOPPED"
    assert boundary.stop_reason == "DISCLOSURE_SCOPE_EXCEEDED"
    runs = control_database.read_rows("SELECT status FROM runs WHERE run_id = 'run-1'")
    assert runs[0][0] == "STOPPED"
    # The one-winner resume never duplicated a turn or a call.
    assert _counter_row(control_database, "run-1") == (0, 0)


def test_engine_cancel_stops_at_the_safe_point(
    control_database: ControlDatabase,
    tmp_path: Path,
) -> None:
    """The cancel composition: a pending cancellation stops at the action
    boundary with zero side effects."""
    _insert_run(control_database, "run-1")
    engine = _real_engine(
        control_database,
        orchestrator=_mock_orchestrator(control_database, tmp_path),
        projections=[],
        responses=[],
        cancellation=True,
    )
    boundary = engine.run_until_boundary("run-1")
    assert boundary.kind == "STOPPED"
    assert boundary.stop_reason == "CANCELLED"
    assert boundary.turns_executed == 0
    runs = control_database.read_rows("SELECT status FROM runs WHERE run_id = 'run-1'")
    assert runs[0][0] == "STOPPED"
    assert not control_database.read_rows(
        "SELECT 1 FROM agent_turns WHERE run_id = 'run-1'"
    )


def test_engine_budget_stop_at_the_exact_turn_limit(
    control_database: ControlDatabase,
    tmp_path: Path,
) -> None:
    """The stop composition: the frozen turn cap stops on the exact
    limit with the consumed counts kept."""
    _insert_run(control_database, "run-1")
    engine = _real_engine(
        control_database,
        orchestrator=_mock_orchestrator(control_database, tmp_path),
        projections=[_projection()],
        responses=[_script_response()],
        limits=_limits(max_turns=1),
    )
    boundary = engine.run_until_boundary("run-1")
    assert boundary.kind == "STOPPED"
    assert boundary.stop_reason == "TURN_BUDGET_EXHAUSTED"
    assert boundary.turns_executed == 1
    assert boundary.calls_executed == 1
    runs = control_database.read_rows("SELECT status FROM runs WHERE run_id = 'run-1'")
    assert runs[0][0] == "STOPPED"


def test_engine_repeated_action_stops_at_the_exact_limit(
    control_database: ControlDatabase,
    tmp_path: Path,
) -> None:
    """The repetition composition: three identical semantic results on the
    same candidate stop with REPEATED_ACTION_LIMIT (SPEC §4.2.6)."""
    _insert_run(control_database, "run-1")
    engine = _real_engine(
        control_database,
        orchestrator=_mock_orchestrator(control_database, tmp_path),
        projections=[_projection(), _projection(), _projection()],
        responses=[_script_response(), _script_response(), _script_response()],
    )
    first = engine.step("run-1")
    assert first.kind == "CONTINUE"
    second = engine.step("run-1")
    assert second.kind == "CONTINUE"
    third = engine.step("run-1")
    assert third.kind == "STOPPED"
    assert third.stop_reason == "REPEATED_ACTION_LIMIT"
    assert third.turn_count == 3
    assert third.call_count == 3
    # Every completed turn was closed; the run is terminal now.
    turns = control_database.read_rows(
        "SELECT status, outcome FROM agent_turns WHERE run_id = 'run-1'"
    )
    assert len(turns) == 3
    assert all(row[0] == "CLOSED" for row in turns)
    runs = control_database.read_rows("SELECT status FROM runs WHERE run_id = 'run-1'")
    assert runs[0][0] == "STOPPED"


def test_engine_completion_requests_formal_validation(
    control_database: ControlDatabase,
    tmp_path: Path,
) -> None:
    """The completion composition: a VALIDATION_REQUESTED proposal enters
    the formal-validation phase, never SUCCEEDED (SPEC §4.2.5 step 6)."""
    _insert_run(control_database, "run-1")
    engine = _real_engine(
        control_database,
        orchestrator=_mock_orchestrator(control_database, tmp_path),
        projections=[_projection()],
        responses=[_completion_response()],
    )
    boundary = engine.run_until_boundary("run-1")
    assert boundary.kind == "VALIDATE_REQUESTED"
    assert boundary.turns_executed == 1
    runs = control_database.read_rows(
        "SELECT status, phase FROM runs WHERE run_id = 'run-1'"
    )
    assert runs[0][0] == "RUNNING"
    assert runs[0][1] == "FORMAL_VALIDATION"


def test_engine_context_budget_failure_stops_with_zero_side_effects(
    control_database: ControlDatabase,
    tmp_path: Path,
) -> None:
    """One CONTEXT_BUDGET_EXCEEDED stops before the call with zero counts."""
    _insert_run(control_database, "run-1")

    class _BudgetFailureBuilder:
        def build_context(
            self, run_id: str
        ) -> ContextProjectionV1 | ContextBudgetFailureV1:
            return ContextBudgetFailureV1(
                error_code="CONTEXT_BUDGET_EXCEEDED",
                message="mandatory context content exceeds the frozen budget",
                mandatory_byte_count=65537,
                budget_bytes=65536,
            )

    engine = _real_engine(
        control_database,
        orchestrator=_mock_orchestrator(control_database, tmp_path),
        projections=[],
        responses=[],
        context_builder=_BudgetFailureBuilder(),
    )
    step = engine.step("run-1")
    assert step.kind == "STOPPED"
    assert step.stop_reason == "CONTEXT_BUDGET_EXCEEDED"
    assert step.turn_count == 0
    assert step.call_count == 0
    assert not control_database.read_rows(
        "SELECT 1 FROM agent_turns WHERE run_id = 'run-1'"
    )
    runs = control_database.read_rows("SELECT status FROM runs WHERE run_id = 'run-1'")
    assert runs[0][0] == "STOPPED"


def test_engine_invalid_output_stops_at_the_exact_limit(
    control_database: ControlDatabase,
    tmp_path: Path,
) -> None:
    """The invalid-output composition: two consecutive invalid outputs
    stop with MODEL_OUTPUT_INVALID_LIMIT and each invalid turn closes
    FAILED (SPEC §4.2.8)."""
    _insert_run(control_database, "run-1")
    engine = _real_engine(
        control_database,
        orchestrator=_mock_orchestrator(control_database, tmp_path),
        projections=[_projection(), _projection()],
        responses=[_invalid_response(), _invalid_response()],
    )
    first = engine.step("run-1")
    assert first.kind == "CONTINUE"
    second = engine.step("run-1")
    assert second.kind == "STOPPED"
    assert second.stop_reason == "MODEL_OUTPUT_INVALID_LIMIT"
    assert second.turn_count == 2
    assert second.call_count == 2
    turns = control_database.read_rows(
        "SELECT status, outcome FROM agent_turns WHERE run_id = 'run-1'"
    )
    assert len(turns) == 2
    assert all(row[0] == "CLOSED" for row in turns)
    assert all(row[1] == "FAILED" for row in turns)
    runs = control_database.read_rows("SELECT status FROM runs WHERE run_id = 'run-1'")
    assert runs[0][0] == "STOPPED"


def test_engine_restart_stop_at_the_boundary_entry(
    control_database: ControlDatabase,
    tmp_path: Path,
) -> None:
    """One interrupted ACTIVE turn stops at the boundary entry with zero
    side effects; the interrupted turn is never resumed or closed."""
    _insert_run(control_database, "run-1")
    with control_database.immediate_transaction() as tx:
        tx.execute(
            "INSERT INTO agent_turns (turn_id, run_id, revision, status,"
            " outcome, closed_at, request_ref, result_ref)"
            " VALUES ('turn-1', 'run-1', 1, 'ACTIVE', NULL, NULL, NULL, NULL)"
        )
    engine = _real_engine(
        control_database,
        orchestrator=_mock_orchestrator(control_database, tmp_path),
        projections=[],
        responses=[],
    )
    boundary = engine.run_until_boundary("run-1")
    assert boundary.kind == "STOPPED"
    assert boundary.stop_reason == "PROCESS_RESTART_DURING_TURN"
    assert boundary.turns_executed == 0
    turns = control_database.read_rows(
        "SELECT status FROM agent_turns WHERE run_id = 'run-1'"
    )
    assert turns[0][0] == "ACTIVE"


def test_main_loop_composition_matrix(
    control_database: ControlDatabase,
    tmp_path: Path,
) -> None:
    """PLAN Registry row 25.G: the exact composition matrix.

    Per the SPEC_PROCESS 49 precedent the card Expected line is the
    operative matrix authority: each engine step calls context, one LLM
    call, parse, policy, dispatch, feedback, and stop once in order, and
    the Mock/OpenAI, correction, wait, cancel, stop, and completion
    traces use the same core while preserving exactly one active turn
    and one eligible call.
    """
    # --- Mock trace: exactly one eligible call, ordered stage evidence. ---
    _insert_run(control_database, "run-mock")
    mock_engine = _real_engine(
        control_database,
        orchestrator=_mock_orchestrator(control_database, tmp_path),
        projections=[_projection()],
        responses=[_script_response()],
    )
    mock_step = mock_engine.step("run-mock")
    assert mock_step.kind == "CONTINUE"
    assert [entry.stage for entry in mock_step.evidence] == [
        "context",
        "call_once",
        "action_pipeline",
        "progress",
        "stop",
        "close_turn",
    ]
    assert _counter_row(control_database, "run-mock") == (1, 1)

    # --- OpenAI trace: one authorized call and one transport attempt. ---
    _seed_granted_run(control_database, "run-openai")
    credential = _CredentialStore(missing=False)
    transport = _TransportSpy()
    openai_engine = _real_engine(
        control_database,
        orchestrator=_openai_orchestrator(
            control_database, tmp_path, credential=credential, transport=transport
        ),
        projections=[_projection()],
        responses=[_script_response()],
        request_preparer=_OpenAIRequestPreparer(
            openai_profile(),
            grant_id="grant-run-openai",
            authorization_record_id="rec-openai",
            event_id="evt-openai",
        ),
    )
    openai_step = openai_engine.step("run-openai")
    assert openai_step.kind == "CONTINUE"
    assert _counter_row(control_database, "run-openai") == (1, 1)
    assert transport.attempts == 1

    # --- Stop trace: the exact turn cap with consumed counts kept. ---
    _insert_run(control_database, "run-stop")
    stop_engine = _real_engine(
        control_database,
        orchestrator=_mock_orchestrator(control_database, tmp_path),
        projections=[_projection()],
        responses=[_script_response()],
        limits=_limits(max_turns=1),
    )
    stop_step = stop_engine.step("run-stop")
    assert stop_step.kind == "STOPPED"
    assert stop_step.stop_reason == "TURN_BUDGET_EXHAUSTED"
    assert _counter_row(control_database, "run-stop") == (1, 1)

    # --- Cancel trace: zero side effects at the safe point. ---
    _insert_run(control_database, "run-cancel")
    cancel_engine = _real_engine(
        control_database,
        orchestrator=_mock_orchestrator(control_database, tmp_path),
        projections=[],
        responses=[],
        cancellation=True,
    )
    cancel_boundary = cancel_engine.run_until_boundary("run-cancel")
    assert cancel_boundary.kind == "STOPPED"
    assert cancel_boundary.stop_reason == "CANCELLED"
    assert _counter_row(control_database, "run-cancel") == (0, 0)

    # --- Completion trace: VALIDATE enters the formal-validation phase. ---
    _insert_run(control_database, "run-complete")
    complete_engine = _real_engine(
        control_database,
        orchestrator=_mock_orchestrator(control_database, tmp_path),
        projections=[_projection()],
        responses=[_completion_response()],
    )
    complete_boundary = complete_engine.run_until_boundary("run-complete")
    assert complete_boundary.kind == "VALIDATE_REQUESTED"
    runs = control_database.read_rows(
        "SELECT status, phase FROM runs WHERE run_id = 'run-complete'"
    )
    assert runs[0][1] == "FORMAL_VALIDATION"

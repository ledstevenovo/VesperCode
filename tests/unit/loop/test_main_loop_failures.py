"""T25.2 legacy step 25.D: action-step failure-exposure tests.

The main-loop failure surface of the 25.D step: a rejected feedback
append, a failed action-record store, and a feedback-consume conflict are
never hidden — each surfaces on the closed ``ActionStepResultV1`` — and
an invalid model output never reaches the dispatcher or the policy.  The
successor task (25.G) may add outer-loop stop/wait integration cases to
this file without rewriting the call/dispatch assertions (PLAN row 546).
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any, Callable, Literal, cast

import pytest

# The pipeline consumes pydantic runtime contracts; the hash-locked gate
# toolchain installs no runtime dependencies, so this module skips
# cleanly there (formal env runs it fully).
pytest.importorskip("pydantic")

from vespercode.candidate.patch_engine import CandidatePatchOutcomeV1
from vespercode.canonical.clock import FakeClockV1
from vespercode.canonical.path_v1 import CanonicalRelativePathV1
from vespercode.canonical.timestamp_v1 import CanonicalTimestampV1
from vespercode.contracts.evidence import ArtifactRefV1, DigestV1
from vespercode.contracts.optional import AbsentV1
from vespercode.governance.policy import PatchPathFactV1, PolicyEngine
from vespercode.llm.base import ModelResponse
from vespercode.loop.action_binding import reset_issued_action_ids
from vespercode.loop.action_pipeline import (
    ActionPipeline,
    ActionPipelineContextV1,
    ActionRecordRepositoryV1,
    ActionRecordStoredV1,
)
from vespercode.loop.agent_actions import ActionInstanceV1
from vespercode.loop.feedback import (
    CheckFeedbackSourceV1,
    FeedbackRecordV1,
)
from vespercode.loop.feedback_consumption import (
    FeedbackAppendResultV1,
    FeedbackRepositoryV1,
)
from vespercode.profiles.registry import build_profile_registry
from vespercode.storage.connection import (
    ControlDatabase,
    open_control_database,
)
from vespercode.storage.migration_engine import apply_migrations
from vespercode.storage.migrations.v0001_run_wait import RUN_WAIT_V1_MIGRATION
from vespercode.storage.migrations.v0002_idempotency import (
    IDEMPOTENCY_V1_MIGRATION,
)
from vespercode.storage.migrations.v0003_disclosure_grants import (
    DISCLOSURE_GRANTS_V1_MIGRATION,
)
from vespercode.storage.migrations.v0004_disclosure_authorizations import (
    DISCLOSURE_AUTHORIZATIONS_V1_MIGRATION,
)
from vespercode.storage.migrations.v0005_memory import MEMORY_V1_MIGRATION
from vespercode.storage.migrations.v0006_audit import AUDIT_V1_MIGRATION
from vespercode.storage.migrations.v0007_agent_turns import (
    AGENT_TURNS_V1_MIGRATION,
)
from vespercode.storage.migrations.v0008_feedback import FEEDBACK_V1_MIGRATION
from vespercode.storage.migrations.v0009_actions import ACTIONS_V1_MIGRATION
from vespercode.tools.dispatcher import (
    ActionResultV1,
    CompletionOutcomeV1,
    DispatchContextV1,
    RunCheckOutcomeV1,
    ToolDispatcher,
)
from vespercode.tools.file_results import (
    FileToolErrorV1,
    ListFilesSuccessV1,
)

from vespercode.contracts.optional import PresentV1
from vespercode.governance.request_sources import (
    RequestContentSegmentV1,
    RequestMessageV1,
    validate_segment_sources,
)
from vespercode.llm.call_result import (
    PresentAuthorizationRecordRefV1,
    PresentLLMCallErrorV1,
    PresentResponseDigestV1,
)
from vespercode.llm.prepared_request import (
    MockPreparedModelRequestV1,
    OpenAIPreparedModelRequestV1,
    prepare_mock_request,
)
from vespercode.loop.call_orchestrator import (
    CallOnceV1,
    LLMCallResultV1,
)
from vespercode.loop.cancellation import CancellationController
from vespercode.loop.context_projection import (
    ContextBudgetFailureV1,
    ContextProjectionV1,
    _projection_digest,
)
from vespercode.loop.engine import AgentLoopEngine
from vespercode.loop.progress import ProgressEvaluator
from vespercode.loop.restart import RestartGuard
from vespercode.loop.stopping import StopEvaluator
from vespercode.loop.turn_boundary import TurnBoundary
from vespercode.loop.wait_control import WaitController
from vespercode.profiles.llm import (
    MockLLMProfileV1,
    load_llm_profile,
)
from vespercode.contracts.run import (
    RunLimitsV1,
    RunPhase,
    RunStatus,
    WaitContextV1,
    WaitDecisionV1,
)
from vespercode.storage.run_repository import (
    RunRecordV1,
    RunRepository,
    TransitionCommandV1,
    TransitionResultV1,
)

_CREATED_AT = CanonicalTimestampV1("2026-08-06T09:00:00.000Z")
_CANDIDATE_DIGEST = "a" * 64
_EDITABLE_POLICY_DIGEST = (
    build_profile_registry().resolve_editable("PYTHON_SRC_ONLY_V1").digest
)
_REFERENCE_PROFILE_DIGEST = "b" * 64

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


def _response(text: str) -> ModelResponse:
    raw = text.encode("utf-8")
    return ModelResponse(
        schema_version=1,
        text=text,
        text_digest=hashlib.sha256(raw).hexdigest(),
        byte_count=len(raw),
    )


def outside_scope_patch_response() -> ModelResponse:
    facts: dict[str, Any] = {
        "schema_version": 1,
        "action_type": "apply_candidate_patch",
        "base_candidate_digest": _CANDIDATE_DIGEST,
        "patch_format": "UNIFIED_DIFF_V1",
        "patch_text": "--- a/docs/outside-scope.md\n+++ b/docs/outside-scope.md\n",
    }
    return _response(
        json.dumps(facts, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    )


def invalid_response() -> ModelResponse:
    return _response("this is not a json object")


class _SequenceIdGenerator:
    """One deterministic Harness action-id generator."""

    def __init__(self) -> None:
        self._next = 0

    def next_id(self) -> str:
        self._next += 1
        return f"act-{self._next}"


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
        # The Task 17.C dispatcher vocabulary is closed and carries no
        # check-specific rejection code; INTERNAL_ERROR is the honest
        # closed code for "the frozen check plan could not run".
        self.run_check = lambda action: RunCheckOutcomeV1(
            kind="REJECTED",
            error_code="INTERNAL_ERROR",
            bounded_message="the target check plan could not run",
        )
        self.propose_completion = lambda action: CompletionOutcomeV1(
            kind="VALIDATION_REQUESTED"
        )


def _patch_outcome_rejected() -> CandidatePatchOutcomeV1:
    """A patch action must never reach a port in this matrix."""
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


class _RejectingAppendRepository(FeedbackRepositoryV1):
    """One injected repository whose append always rejects."""

    def append(self, records: object) -> FeedbackAppendResultV1:
        return FeedbackAppendResultV1(
            kind="REJECTED",
            message="injected feedback append failure",
        )


class _FailingRecordRepository(ActionRecordRepositoryV1):
    """One injected repository whose store always fails closed."""

    def store(self, draft: object) -> ActionRecordStoredV1:
        return ActionRecordStoredV1(
            schema_version=1,
            kind="FAILED",
            message="injected action-record storage failure",
        )


def feedback_record(record_id: str) -> FeedbackRecordV1:
    """One deterministic unconsumed feedback record for consume seeding."""
    return FeedbackRecordV1(
        id=record_id,
        kind="CHECK",
        severity="HIGH",
        created_at=_CREATED_AT,
        summary="the target test failed",
        source_ref=CheckFeedbackSourceV1(
            kind="CHECK",
            check_kind="TARGET_TESTS",
            path=AbsentV1(kind="ABSENT"),
        ),
        bounded_payload='{"check_kind":"TARGET_TESTS","status":"FAIL"}',
    )


def _seed(database: ControlDatabase) -> None:
    with database.immediate_transaction() as tx:
        tx.execute(
            "INSERT INTO run_config_snapshots (config_snapshot_id, digest,"
            " llm_profile_id, reference_profile_id, policy_id, target_test_ids,"
            " limits_digest, frozen_at)"
            " VALUES (?, ?, 'mock-deterministic-v1',"
            " 'python-src-py312-v1', 'PYTHON_SRC_ONLY_V1', '[]', ?, ?)",
            ("snap-1", "d" * 64, "c" * 64, _CREATED_AT.value),
        )
        tx.execute(
            "INSERT INTO runs (run_id, workspace_identity, config_snapshot_id,"
            " status, phase, revision, started_at, run_deadline)"
            " VALUES ('run-1', 'workspace-1', 'snap-1', 'RUNNING', 'AGENT_LOOP',"
            " 1, ?, ?)",
            (_CREATED_AT.value, "2026-08-06T09:15:00.000Z"),
        )
        tx.execute(
            "INSERT INTO agent_turns (turn_id, run_id, revision, status,"
            " outcome, closed_at, request_ref, result_ref)"
            " VALUES ('turn-1', 'run-1', 1, 'ACTIVE', NULL, NULL, NULL, NULL)"
        )


def _context(
    *,
    feedback_repository: FeedbackRepositoryV1,
    action_record_repository: ActionRecordRepositoryV1,
    consumed_feedback_refs: tuple[str, ...] = (),
    dispatcher: ToolDispatcher | None = None,
) -> ActionPipelineContextV1:
    # The Harness action-id set is per-process and the run boundary resets
    # it (Task 17.B); each step context here resets it deterministically.
    reset_issued_action_ids()
    return ActionPipelineContextV1(
        turn_id="turn-1",
        consumed_feedback_refs=consumed_feedback_refs,
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
        dispatcher=dispatcher if dispatcher is not None else SpyDispatcher(),
        feedback_repository=feedback_repository,
        action_record_repository=action_record_repository,
        clock=FakeClockV1(_CREATED_AT.epoch_milliseconds),
        action_id_generator=_SequenceIdGenerator(),
    )


@pytest.fixture
def control_database(tmp_path: Path) -> Iterator[ControlDatabase]:
    database = open_control_database(tmp_path / "main_loop_failures.db")
    apply_migrations(database, _MIGRATIONS)
    _seed(database)
    yield database
    database.close()


def test_feedback_append_failure_is_not_hidden(
    control_database: ControlDatabase,
) -> None:
    pipeline = _deny_pipeline()
    context = _context(
        feedback_repository=_RejectingAppendRepository(control_database),
        action_record_repository=ActionRecordRepositoryV1(control_database),
    )
    result = pipeline.execute(outside_scope_patch_response(), context)
    assert result.policy_decision == "DENY"
    assert result.feedback.kind == "REJECTED"
    assert result.feedback.error_code == "PATCH_PATH_NOT_EDITABLE"
    assert result.feedback.record_id is None
    assert result.append_outcome is not None
    assert result.append_outcome.kind == "REJECTED"
    # The action record still stores the DENY decision explicitly.
    assert result.action_record is not None
    assert result.action_record.kind == "STORED"


def test_action_record_failure_is_not_hidden(
    control_database: ControlDatabase,
) -> None:
    pipeline = _deny_pipeline()
    context = _context(
        feedback_repository=FeedbackRepositoryV1(control_database),
        action_record_repository=_FailingRecordRepository(control_database),
    )
    result = pipeline.execute(outside_scope_patch_response(), context)
    assert result.policy_decision == "DENY"
    assert result.feedback.kind == "APPENDED"
    assert result.action_record is not None
    assert result.action_record.kind == "FAILED"
    assert result.action_record.message == "injected action-record storage failure"


def test_consume_conflict_is_not_hidden(
    control_database: ControlDatabase,
) -> None:
    pipeline = _deny_pipeline()
    repository = FeedbackRepositoryV1(control_database)
    # Seed an already-consumed record: another turn (of another run, per
    # the one-active-turn invariant) won the consume.
    assert repository.append((feedback_record("fb-1"),)).kind == "APPENDED"
    with control_database.immediate_transaction() as tx:
        tx.execute(
            "INSERT INTO run_config_snapshots (config_snapshot_id, digest,"
            " llm_profile_id, reference_profile_id, policy_id, target_test_ids,"
            " limits_digest, frozen_at)"
            " VALUES ('snap-2', ?, 'mock-deterministic-v1',"
            " 'python-src-py312-v1', 'PYTHON_SRC_ONLY_V1', '[]', ?, ?)",
            ("e" * 64, "c" * 64, _CREATED_AT.value),
        )
        tx.execute(
            "INSERT INTO runs (run_id, workspace_identity, config_snapshot_id,"
            " status, phase, revision, started_at, run_deadline)"
            " VALUES ('run-2', 'workspace-2', 'snap-2', 'RUNNING', 'AGENT_LOOP',"
            " 1, ?, ?)",
            (_CREATED_AT.value, "2026-08-06T09:15:00.000Z"),
        )
        tx.execute(
            "INSERT INTO agent_turns (turn_id, run_id, revision, status,"
            " outcome, closed_at, request_ref, result_ref)"
            " VALUES ('turn-2', 'run-2', 1, 'ACTIVE', NULL, NULL, NULL, NULL)"
        )
        tx.execute(
            "UPDATE feedback_records SET consumed_by_turn_id = 'turn-2'"
            " WHERE feedback_id = 'fb-1'"
        )
    context = _context(
        feedback_repository=repository,
        action_record_repository=ActionRecordRepositoryV1(control_database),
        consumed_feedback_refs=("fb-1",),
    )
    result = pipeline.execute(outside_scope_patch_response(), context)
    assert result.consume_outcome is not None
    assert result.consume_outcome.kind == "ALREADY_CONSUMED"
    # The DENY step still completes with its own feedback and record.
    assert result.feedback.kind == "APPENDED"
    assert result.feedback.error_code == "PATCH_PATH_NOT_EDITABLE"
    assert result.action_record is not None
    assert result.action_record.kind == "STORED"


def test_invalid_output_never_reaches_dispatch_or_policy(
    control_database: ControlDatabase,
) -> None:
    pipeline = _deny_pipeline()
    dispatcher = SpyDispatcher()
    context = _context(
        feedback_repository=FeedbackRepositoryV1(control_database),
        action_record_repository=ActionRecordRepositoryV1(control_database),
        dispatcher=dispatcher,
    )
    result = pipeline.execute(invalid_response(), context)
    assert result.parse_outcome == "INVALID"
    assert result.policy_decision is None
    assert result.action_id is None
    assert result.dispatch_result is None
    assert result.action_record is None
    assert dispatcher.call_count == 0
    assert result.feedback.kind == "APPENDED"
    assert result.feedback.error_code == "NOT_JSON_OBJECT"


def test_duplicate_action_record_rejects_closed(
    control_database: ControlDatabase,
) -> None:
    """A duplicate action identity is a typed REJECTED outcome, never a
    raw sqlite error (the store detects the violation by exception type)."""
    pipeline = _deny_pipeline()
    repository = FeedbackRepositoryV1(control_database)
    first_context = _context(
        feedback_repository=repository,
        action_record_repository=ActionRecordRepositoryV1(control_database),
    )
    first = pipeline.execute(outside_scope_patch_response(), first_context)
    assert first.action_record is not None
    assert first.action_record.kind == "STORED"
    assert first.action_record.action_id == "act-1"
    # The identical step context regenerates the same Harness action id
    # (the per-process set was reset), so the second store hits the PK.
    second_context = _context(
        feedback_repository=repository,
        action_record_repository=ActionRecordRepositoryV1(control_database),
    )
    second = pipeline.execute(outside_scope_patch_response(), second_context)
    assert second.action_record is not None
    assert second.action_record.kind == "REJECTED"
    assert "action id" in second.action_record.message
    assert len(control_database.read_rows("SELECT 1 FROM action_records")) == 1


_FAILURE_CLOCK = CanonicalTimestampV1("2026-08-06T09:00:00.000Z")
_FAILURE_LIMITS = RunLimitsV1(
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


class _StubCallOrchestrator:
    """One call child returning the canned closed result (25.C shape)."""

    def __init__(self, result: LLMCallResultV1) -> None:
        self._result = result

    def call_once(self, command: CallOnceV1) -> LLMCallResultV1:
        return self._result


class _FailureFacts:
    """One compact run-facts port over the seeded control database."""

    def __init__(
        self,
        database: ControlDatabase,
        *,
        cancellation: bool = False,
        wait_provider_waits: dict[str, WaitContextV1] | None = None,
    ) -> None:
        self._database = database
        self._cancellation = cancellation

    def run_record(self, run_id: str) -> RunRecordV1:
        rows = self._database.read_rows(
            "SELECT workspace_identity, config_snapshot_id, status, phase,"
            " started_at, run_deadline FROM runs WHERE run_id = ?",
            (run_id,),
        )
        assert rows
        row = rows[0]
        return RunRecordV1(
            run_id=run_id,
            workspace_identity=str(row[0]),
            config_snapshot_id=str(row[1]),
            status=cast(RunStatus, str(row[2])),
            phase=(
                AbsentV1(kind="ABSENT")
                if row[3] is None
                else PresentV1(kind="PRESENT", value=cast(RunPhase, str(row[3])))
            ),
            started_at=CanonicalTimestampV1(str(row[4])),
            run_deadline=CanonicalTimestampV1(str(row[5])),
        )

    def run_limits(self, run_id: str) -> RunLimitsV1:
        return _FAILURE_LIMITS

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
        return bool(
            self._database.read_rows(
                "SELECT 1 FROM agent_turns WHERE run_id = ? AND status = 'ACTIVE'",
                (run_id,),
            )
        )

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
        return None

    def pending_wait_decision(self, run_id: str) -> WaitDecisionV1 | None:
        return None

    def cancellation_requested(self, run_id: str) -> bool:
        return self._cancellation

    def transition(self, command: TransitionCommandV1) -> TransitionResultV1:
        return RunRepository(self._database).compare_and_transition(command)


class _StubContextBuilder:
    """One canned projection builder (the failure paths stop after it)."""

    def build_context(
        self, run_id: str
    ) -> ContextProjectionV1 | ContextBudgetFailureV1:
        content = "VesperCode v1 protocol."
        messages = (
            RequestMessageV1(
                role="SYSTEM",
                segments=(
                    RequestContentSegmentV1(
                        source_category="HARNESS_PROTOCOL",
                        source_path=AbsentV1(kind="ABSENT"),
                        content=content,
                        content_digest=hashlib.sha256(content.encode()).hexdigest(),
                        byte_count=len(content.encode()),
                    ),
                ),
            ),
        )
        sources = validate_segment_sources(messages)
        return ContextProjectionV1(
            messages=messages,
            source_projection=sources,
            canonical_byte_count=len(content.encode()),
            projection_digest=_projection_digest(messages, sources),
        )


_MOCK_BUILTIN = (
    Path(__file__).resolve().parents[3]
    / "src/vespercode/profiles/builtin/mock-deterministic-v1.json"
)


def _mock_profile() -> MockLLMProfileV1:
    loaded = load_llm_profile(_MOCK_BUILTIN.read_bytes())
    assert isinstance(loaded, MockLLMProfileV1)
    return loaded


def _canned_command(run_id: str) -> CallOnceV1:
    """One valid Mock command the stub call child ignores."""
    raw = b"VesperCode protocol"
    message = RequestMessageV1(
        role="SYSTEM",
        segments=(
            RequestContentSegmentV1(
                source_category="HARNESS_PROTOCOL",
                source_path=AbsentV1(kind="ABSENT"),
                content="VesperCode protocol",
                content_digest=hashlib.sha256(raw).hexdigest(),
                byte_count=len(raw),
            ),
        ),
    )
    profile = _mock_profile()
    request = prepare_mock_request(profile, (message,))
    return CallOnceV1(
        schema_version=1,
        run_id=run_id,
        request=request,
        llm_profile_digest=profile.digest,
        adapter_version=profile.adapter_version,
        script_id=profile.script_id,
        script_digest=profile.script_digest,
    )


class _StubRequestPreparer:
    def prepare_call(self, run_id: str, projection: ContextProjectionV1) -> CallOnceV1:
        return _canned_command(run_id)


class _StubStepContextBuilder:
    def build_step_context(
        self, run_id: str, projection: ContextProjectionV1
    ) -> ActionPipelineContextV1:
        raise AssertionError("the failure paths never reach the pipeline")


class _StubResolver:
    def __init__(self, response: ModelResponse | None = None) -> None:
        self._response = response

    def resolve(
        self,
        request: MockPreparedModelRequestV1 | OpenAIPreparedModelRequestV1,
        result: LLMCallResultV1,
    ) -> ModelResponse | None:
        return self._response


class _StubWaitProvider:
    def __init__(self, waits: dict[str, WaitContextV1] | None = None) -> None:
        self._waits = dict(waits or {})

    def wait_for_abort(self, run_id: str, abort_code: str) -> WaitContextV1 | None:
        return self._waits.pop(abort_code, None)


def _seed_run(database: ControlDatabase, run_id: str) -> None:
    """Insert one fresh RUNNING(AGENT_LOOP) run (unique snapshot digest)."""
    with database.immediate_transaction() as tx:
        tx.execute(
            "INSERT INTO run_config_snapshots (config_snapshot_id, digest,"
            " llm_profile_id, reference_profile_id, policy_id, target_test_ids,"
            " limits_digest, frozen_at)"
            " VALUES (?, ?, 'mock-deterministic-v1', 'python-src-py312-v1',"
            " 'PYTHON_SRC_ONLY_V1', '[]', ?, ?)",
            (
                f"snap-{run_id}",
                hashlib.sha256(f"snap-{run_id}".encode("utf-8")).hexdigest(),
                "c" * 64,
                _CREATED_AT.value,
            ),
        )
        tx.execute(
            "INSERT INTO runs (run_id, workspace_identity, config_snapshot_id,"
            " status, phase, revision, started_at, run_deadline)"
            " VALUES (?, 'workspace-1', ?, 'RUNNING', 'AGENT_LOOP', 1, ?, ?)",
            (run_id, f"snap-{run_id}", _CREATED_AT.value, "2026-08-06T09:15:00.000Z"),
        )


def _seed_counted_turn(database: ControlDatabase, run_id: str) -> None:
    """One post-count state: the counted turn and the ACTIVE turn row."""
    with database.immediate_transaction() as tx:
        tx.execute(
            "INSERT INTO run_turn_call_counters"
            " (run_id, turn_count, call_count, revision) VALUES (?, 1, 1, 1)",
            (run_id,),
        )
        tx.execute(
            "INSERT INTO agent_turns (turn_id, run_id, revision, status,"
            " outcome, closed_at, request_ref, result_ref)"
            " VALUES ('turn-fail', ?, 1, 'ACTIVE', NULL, NULL, NULL, NULL)",
            (run_id,),
        )


class _FixedPatchPathFactProvider:
    """One fixed-fact patch-path provider for engine failure tests.

    The pipeline never forwards the context's caller-supplied fact; the
    RED failure contexts carry the non-editable fact, so the pipeline is
    wired with a provider deriving exactly that fact.
    """

    def __init__(self, fact: PatchPathFactV1) -> None:
        self._fact = fact

    def derive(self, action: object) -> PatchPathFactV1:
        return self._fact


def _deny_pipeline() -> ActionPipeline:
    """One pipeline wired with the fixed non-editable patch-path fact."""
    return ActionPipeline(
        patch_path_fact_provider=_FixedPatchPathFactProvider(
            "PATCH_PATH_NOT_EDITABLE"
        )
    )


def _failure_engine(
    database: ControlDatabase,
    *,
    result: LLMCallResultV1,
    resolver: _StubResolver | None = None,
    wait_provider: _StubWaitProvider | None = None,
) -> AgentLoopEngine:
    """One engine with a canned call child and the real loop children."""
    return AgentLoopEngine(
        stop_evaluator=StopEvaluator(),
        progress_evaluator=ProgressEvaluator(),
        turn_boundary=TurnBoundary(
            database, clock=FakeClockV1(_CREATED_AT.epoch_milliseconds)
        ),
        call_orchestrator=_StubCallOrchestrator(result),
        action_pipeline=_deny_pipeline(),
        wait_controller=WaitController(),
        cancellation_controller=CancellationController(),
        restart_guard=RestartGuard(),
        run_facts=_FailureFacts(database),
        context_builder=_StubContextBuilder(),
        request_preparer=_StubRequestPreparer(),
        response_resolver=(resolver if resolver is not None else _StubResolver()),
        step_context_builder=_StubStepContextBuilder(),
        wait_provider=(
            wait_provider if wait_provider is not None else _StubWaitProvider()
        ),
        clock=FakeClockV1(_CREATED_AT.epoch_milliseconds),
    )


def _call_result(
    *,
    status: Literal["NOT_ATTEMPTED", "SUCCEEDED", "FAILED", "DELIVERY_UNKNOWN"],
    error_code: str | None = None,
    response_digest: str | None = None,
    mode: Literal["MOCK", "OPENAI"] = "MOCK",
    authorization_ref: str | None = None,
) -> LLMCallResultV1:
    """One canned orchestrator result for the outer-loop cases."""
    return LLMCallResultV1(
        schema_version=1,
        mode=mode,
        llm_profile_digest="b" * 64,
        request_digest="c" * 64,
        authorization_record_ref=(
            PresentAuthorizationRecordRefV1(
                kind="PRESENT", authorization_record_id=authorization_ref
            )
            if authorization_ref is not None
            else AbsentV1(kind="ABSENT")
        ),
        status=status,
        response_digest=(
            PresentResponseDigestV1(kind="PRESENT", value=response_digest)
            if response_digest is not None
            else AbsentV1(kind="ABSENT")
        ),
        error=(
            PresentLLMCallErrorV1(kind="PRESENT", stable_error_code=error_code)
            if error_code is not None
            else AbsentV1(kind="ABSENT")
        ),
    )


def test_engine_post_count_failure_closes_turn_failed(
    control_database: ControlDatabase,
) -> None:
    """One post-count LLM failure closes the ACTIVE turn with FAILED and
    stops with the stable code; the consumed counts are kept."""
    _seed_run(control_database, "run-fail")
    _seed_counted_turn(control_database, "run-fail")
    engine = _failure_engine(
        control_database,
        result=_call_result(status="FAILED", error_code="LLM_CALL_FAILED"),
    )
    step = engine.step("run-fail")
    assert step.kind == "STOPPED"
    assert step.stop_reason == "LLM_CALL_FAILED"
    assert step.turn_count == 1
    assert step.call_count == 1
    turns = control_database.read_rows(
        "SELECT status, outcome FROM agent_turns WHERE run_id = 'run-fail'"
    )
    assert turns[0][0] == "CLOSED"
    assert turns[0][1] == "FAILED"


def test_engine_pre_count_abort_stops_with_zero_counts(
    control_database: ControlDatabase,
) -> None:
    """One zero-count abort stops with the stable code and creates no
    turn row (CREDENTIAL_MISSING before every side effect)."""
    _seed_run(control_database, "run-fail")
    engine = _failure_engine(
        control_database,
        result=_call_result(status="NOT_ATTEMPTED", error_code="CREDENTIAL_MISSING"),
    )
    step = engine.step("run-fail")
    assert step.kind == "STOPPED"
    assert step.stop_reason == "CREDENTIAL_MISSING"
    assert step.turn_count == 0
    assert step.call_count == 0
    assert not control_database.read_rows(
        "SELECT 1 FROM agent_turns WHERE run_id = 'run-fail'"
    )


def test_engine_delivery_unknown_never_retries(
    control_database: ControlDatabase,
) -> None:
    """One DELIVERY_UNKNOWN stops with INTERNAL_ERROR: v1 never retries
    and never reconstructs an uncertain response."""
    _seed_run(control_database, "run-fail")
    _seed_counted_turn(control_database, "run-fail")
    engine = _failure_engine(
        control_database,
        result=_call_result(
            status="DELIVERY_UNKNOWN",
            error_code="LLM_CALL_FAILED",
            mode="OPENAI",
            authorization_ref="rec-1",
        ),
    )
    step = engine.step("run-fail")
    assert step.kind == "STOPPED"
    assert step.stop_reason == "INTERNAL_ERROR"
    turns = control_database.read_rows(
        "SELECT outcome FROM agent_turns WHERE run_id = 'run-fail'"
    )
    assert turns[0][0] == "FAILED"


def test_engine_wait_entry_stale_stops(
    control_database: ControlDatabase,
) -> None:
    """One wait whose declared entry is contradictory never pauses: the
    step stops with WAIT_STALE and zero side effects."""
    _seed_run(control_database, "run-fail")
    future_wait = WaitContextV1(
        wait_id="wait-1",
        run_id="run-fail",
        wait_kind="DISCLOSURE_GRANT",
        source_phase="AGENT_LOOP",
        subject_digest=DigestV1(value="1" * 64),
        created_at=CanonicalTimestampV1("2026-08-06T09:03:00.000Z"),
        expires_at=CanonicalTimestampV1("2026-08-06T09:05:00.000Z"),
    )
    engine = _failure_engine(
        control_database,
        result=_call_result(status="NOT_ATTEMPTED", error_code="CREDENTIAL_MISSING"),
        wait_provider=_StubWaitProvider({"CREDENTIAL_MISSING": future_wait}),
    )
    step = engine.step("run-fail")
    assert step.kind == "STOPPED"
    assert step.stop_reason == "WAIT_STALE"
    assert step.turn_count == 0
    assert step.call_count == 0
    runs = control_database.read_rows(
        "SELECT status FROM runs WHERE run_id = 'run-fail'"
    )
    assert runs[0][0] == "STOPPED"


def test_engine_response_resolution_failure_stops(
    control_database: ControlDatabase,
) -> None:
    """One SUCCEEDED call whose response cannot be resolved stops with
    INTERNAL_ERROR after closing the turn FAILED (fail closed)."""
    _seed_run(control_database, "run-fail")
    _seed_counted_turn(control_database, "run-fail")
    engine = _failure_engine(
        control_database,
        result=_call_result(
            status="SUCCEEDED",
            response_digest=hashlib.sha256(b"response").hexdigest(),
        ),
        resolver=_StubResolver(None),
    )
    step = engine.step("run-fail")
    assert step.kind == "STOPPED"
    assert step.stop_reason == "INTERNAL_ERROR"
    turns = control_database.read_rows(
        "SELECT outcome FROM agent_turns WHERE run_id = 'run-fail'"
    )
    assert turns[0][0] == "FAILED"

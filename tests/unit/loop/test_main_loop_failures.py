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
from typing import Any, Callable

import pytest

# The pipeline consumes pydantic runtime contracts; the hash-locked gate
# toolchain installs no runtime dependencies, so this module skips
# cleanly there (formal env runs it fully).
pytest.importorskip("pydantic")

from src.vespercode.candidate.patch_engine import CandidatePatchOutcomeV1
from src.vespercode.canonical.clock import FakeClockV1
from src.vespercode.canonical.path_v1 import CanonicalRelativePathV1
from src.vespercode.canonical.timestamp_v1 import CanonicalTimestampV1
from src.vespercode.contracts.evidence import ArtifactRefV1, DigestV1
from src.vespercode.contracts.optional import AbsentV1
from src.vespercode.governance.policy import PolicyEngine
from src.vespercode.llm.base import ModelResponse
from src.vespercode.loop.action_binding import reset_issued_action_ids
from src.vespercode.loop.action_pipeline import (
    ActionPipeline,
    ActionPipelineContextV1,
    ActionRecordRepositoryV1,
    ActionRecordStoredV1,
)
from src.vespercode.loop.agent_actions import ActionInstanceV1
from src.vespercode.loop.feedback import (
    CheckFeedbackSourceV1,
    FeedbackRecordV1,
)
from src.vespercode.loop.feedback_consumption import (
    FeedbackAppendResultV1,
    FeedbackRepositoryV1,
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
    pipeline = ActionPipeline()
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
    pipeline = ActionPipeline()
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
    pipeline = ActionPipeline()
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
    pipeline = ActionPipeline()
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
    pipeline = ActionPipeline()
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

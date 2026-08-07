"""T25.2 legacy step 25.D: parse/policy/dispatch/feedback action-step tests.

The exact RED test pins the DENY feedback path (a policy DENY skips the
dispatcher and returns the stable feedback code); the matrix pins the
exact trace matrix of the 25.D Expected line — invalid output, DENY, tool
failure, check rejection feedback, completion proposal, and consume-once
traces — all without hidden dispatch and with the body-free action-record
row per bound action.
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

from vespercode.candidate.patch_engine import CandidatePatchOutcomeV1
from vespercode.canonical.clock import FakeClockV1
from vespercode.canonical.path_v1 import CanonicalRelativePathV1
from vespercode.canonical.timestamp_v1 import CanonicalTimestampV1
from vespercode.contracts.evidence import ArtifactRefV1, DigestV1
from vespercode.contracts.optional import AbsentV1
from vespercode.contracts.run import RunPhase
from vespercode.governance.policy import PatchPathFactV1, PolicyEngine
from vespercode.llm.base import ModelResponse
from vespercode.loop.action_binding import reset_issued_action_ids
from vespercode.loop.action_pipeline import (
    ActionPipeline,
    ActionPipelineContextV1,
    ActionRecordRepositoryV1,
)
from vespercode.loop.agent_actions import ActionInstanceV1
from vespercode.loop.feedback import (
    CheckFeedbackSourceV1,
    FeedbackRecordV1,
)
from vespercode.loop.feedback_consumption import FeedbackRepositoryV1
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

_CREATED_AT = CanonicalTimestampV1("2026-08-06T09:00:00.000Z")
_CLOCK_EPOCH = _CREATED_AT.epoch_milliseconds
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


def _action_response(facts: dict[str, Any]) -> ModelResponse:
    text = json.dumps(facts, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return _response(text)


def outside_scope_patch_response(
    candidate_digest: str = _CANDIDATE_DIGEST,
) -> ModelResponse:
    """One structurally legal patch targeting a non-editable path."""
    return _action_response(
        {
            "schema_version": 1,
            "action_type": "apply_candidate_patch",
            "base_candidate_digest": candidate_digest,
            "patch_format": "UNIFIED_DIFF_V1",
            "patch_text": (
                "--- a/docs/outside-scope.md\n"
                "+++ b/docs/outside-scope.md\n"
                "@@ -0,0 +1 @@\n"
                "+denied\n"
            ),
        }
    )


def list_files_response() -> ModelResponse:
    return _action_response(
        {
            "schema_version": 1,
            "action_type": "list_files",
            "root": {"kind": "ROOT"},
            "recursive": False,
            "max_entries": 1,
            "cursor": {"kind": "ABSENT"},
        }
    )


def read_file_response() -> ModelResponse:
    return _action_response(
        {
            "schema_version": 1,
            "action_type": "read_file",
            "path": "src/binary.dat",
            "start_line": 1,
            "line_count": 1,
            "max_bytes": 1024,
        }
    )


def run_check_response() -> ModelResponse:
    return _action_response(
        {
            "schema_version": 1,
            "action_type": "run_check",
            "check_plan_id": "TARGET_TESTS",
        }
    )


def completion_response() -> ModelResponse:
    return _action_response(
        {
            "schema_version": 1,
            "action_type": "propose_completion",
            "candidate_digest": _CANDIDATE_DIGEST,
            "rationale_summary": "the failing test is fixed",
        }
    )


def invalid_response() -> ModelResponse:
    return _response("this is not a json object")


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


# The RED test's fixed signature reads ``dispatcher.call_count`` from the
# fixture while the card body calls ``valid_context()`` with no arguments,
# so the context must use the same shared spy the fixture returns.
_SHARED_DISPATCHER = SpyDispatcher()


class _SequenceIdGenerator:
    """One deterministic Harness action-id generator (fresh per context)."""

    def __init__(self, prefix: str) -> None:
        self._prefix = prefix
        self._next = 0

    def next_id(self) -> str:
        self._next += 1
        return f"{self._prefix}-{self._next}"


class _StubTree:
    """One minimal immutable visible tree for the file-tool ports."""

    digest = "f" * 64

    def list_directories(self) -> tuple[CanonicalRelativePathV1, ...]:
        return ()

    def list_file_paths(self) -> tuple[CanonicalRelativePathV1, ...]:
        return ()

    def read_bytes(self, path: CanonicalRelativePathV1) -> bytes:
        raise KeyError(path)


class _StubArtifactStore:
    """One deterministic bounded artifact store for published payloads."""

    def __init__(self) -> None:
        self._next = 0

    def put(self, payload: object) -> ArtifactRefV1:
        self._next += 1
        return ArtifactRefV1(
            artifact_id=f"artifact-{self._next}",
            digest=DigestV1(
                value=hashlib.sha256(
                    json.dumps(
                        {"payload": str(payload), "n": self._next},
                        sort_keys=True,
                    ).encode("utf-8")
                ).hexdigest()
            ),
        )


class _StubPorts:
    """One registered six-port set: list succeeds, read/check fail, done.

    The ports are typed attributes (the Task 17.C ToolPortsV1 shape, per
    the T17.1 test pattern).
    """

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
        # closed code for "the frozen check plan could not run" (the
        # FR-VAL CHECK_ERROR vocabulary belongs to the check pipeline).
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


def _seed_run_and_turn(
    database: ControlDatabase,
    run_id: str = "run-1",
    turn_id: str = "turn-1",
) -> None:
    with database.immediate_transaction() as tx:
        tx.execute(
            "INSERT INTO run_config_snapshots (config_snapshot_id, digest,"
            " llm_profile_id, reference_profile_id, policy_id, target_test_ids,"
            " limits_digest, frozen_at)"
            " VALUES (?, ?, 'mock-deterministic-v1', 'python-src-py312-v1',"
            " 'PYTHON_SRC_ONLY_V1', '[]', ?, ?)",
            (f"snap-{run_id}", "d" * 64, "c" * 64, _CREATED_AT.value),
        )
        tx.execute(
            "INSERT INTO runs (run_id, workspace_identity, config_snapshot_id,"
            " status, phase, revision, started_at, run_deadline)"
            " VALUES (?, 'workspace-1', ?, 'RUNNING', 'AGENT_LOOP', 1, ?, ?)",
            (run_id, f"snap-{run_id}", _CREATED_AT.value, "2026-08-06T09:15:00.000Z"),
        )
        tx.execute(
            "INSERT INTO agent_turns (turn_id, run_id, revision, status,"
            " outcome, closed_at, request_ref, result_ref)"
            " VALUES (?, ?, 1, 'ACTIVE', NULL, NULL, NULL, NULL)",
            (turn_id, run_id),
        )


def _fresh_database() -> ControlDatabase:
    """One fresh in-memory control database with the full v0001-v0009 prefix."""
    database = open_control_database(Path(":memory:"))
    apply_migrations(database, _MIGRATIONS)
    _seed_run_and_turn(database)
    return database


def valid_context(
    *,
    database: ControlDatabase | None = None,
    turn_id: str = "turn-1",
    consumed_feedback_refs: tuple[str, ...] = (),
    run_phase: RunPhase = "AGENT_LOOP",
    current_candidate_digest: str | None = _CANDIDATE_DIGEST,
    final_diff_digest: str | None = None,
    patch_path_fact: PatchPathFactV1 | None = "PATCH_PATH_NOT_EDITABLE",
    dispatcher: ToolDispatcher | None = None,
    action_prefix: str = "act",
) -> ActionPipelineContextV1:
    """One deterministic action-step context (the RED fixture).

    With no arguments it builds its own fresh in-memory database and
    carries the precomputed non-editable-path fact, so the card's exact
    RED body ``pipeline.execute(outside_scope_patch_response(),
    valid_context())`` yields the DENY/PATCH_PATH_NOT_EDITABLE trace
    verbatim; the matrix passes its own seeded database and explicit
    facts so rows are isolated and DB rows can be asserted.
    """
    db = database if database is not None else _fresh_database()
    # The Harness action-id set is per-process and the run boundary resets
    # it (Task 17.B); each step context here resets it so the same script
    # reproduces the same instance sequence deterministically.
    reset_issued_action_ids()
    return ActionPipelineContextV1(
        turn_id=turn_id,
        consumed_feedback_refs=consumed_feedback_refs,
        run_phase=run_phase,
        editable_policy_digest=_EDITABLE_POLICY_DIGEST,
        reference_profile_digest=_REFERENCE_PROFILE_DIGEST,
        current_candidate_digest=current_candidate_digest,
        final_diff_digest=final_diff_digest,
        patch_path_fact=patch_path_fact,
        visible_tree=_StubTree(),
        ports=_StubPorts(),
        artifact_store=_StubArtifactStore(),
        policy_engine=PolicyEngine(),
        dispatcher=dispatcher if dispatcher is not None else _SHARED_DISPATCHER,
        feedback_repository=FeedbackRepositoryV1(db),
        action_record_repository=ActionRecordRepositoryV1(db),
        clock=FakeClockV1(_CLOCK_EPOCH),
        action_id_generator=_SequenceIdGenerator(action_prefix),
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


@pytest.fixture
def control_database(tmp_path: Path) -> Iterator[ControlDatabase]:
    database = open_control_database(tmp_path / "action_pipeline.db")
    apply_migrations(database, _MIGRATIONS)
    _seed_run_and_turn(database)
    yield database
    database.close()


@pytest.fixture
def dispatcher() -> SpyDispatcher:
    return _SHARED_DISPATCHER


@pytest.fixture
def pipeline() -> ActionPipeline:
    return ActionPipeline()


def _action_rows(database: ControlDatabase) -> list[tuple[str | None, ...]]:
    rows = database.read_rows(
        "SELECT action_id, turn_id, action_type, semantic_digest,"
        " instance_digest, policy_decision, result_ref FROM action_records"
        " ORDER BY action_id"
    )
    return [
        tuple(str(value) if value is not None else None for value in row)
        for row in rows
    ]


def _feedback_rows(database: ControlDatabase) -> list[tuple[str | None, ...]]:
    rows = database.read_rows(
        "SELECT feedback_id, kind, consumed_by_turn_id FROM feedback_records"
        " ORDER BY feedback_id"
    )
    return [
        tuple(str(value) if value is not None else None for value in row)
        for row in rows
    ]


def test_policy_deny_skips_dispatch_and_returns_feedback(
    pipeline: ActionPipeline,
    dispatcher: SpyDispatcher,
) -> None:
    result = pipeline.execute(outside_scope_patch_response(), valid_context())
    assert result.policy_decision == "DENY"
    assert dispatcher.call_count == 0
    assert result.feedback.error_code == "PATCH_PATH_NOT_EDITABLE"


def test_action_pipeline_trace_matrix(
    control_database: ControlDatabase,
    pipeline: ActionPipeline,
    dispatcher: SpyDispatcher,
) -> None:
    """PLAN Registry row 25.D: the exact action-step trace matrix.

    Per the SPEC_PROCESS 49 precedent the card Expected line is the
    operative matrix authority: invalid, DENY, tool failure, check
    feedback, completion proposal, and consume-once traces pass without
    hidden dispatch.
    """

    # --- ALLOW trace: one dispatch, no feedback, stored action record. ---
    dispatcher.call_count = 0
    allowed = pipeline.execute(
        list_files_response(),
        valid_context(database=control_database, action_prefix="allow"),
    )
    assert allowed.parse_outcome == "PARSED"
    assert allowed.policy_decision == "ALLOW"
    assert allowed.action_id == "allow-1"
    assert allowed.dispatch_result is not None
    assert allowed.dispatch_result.status == "SUCCEEDED"
    assert allowed.feedback.kind == "NONE"
    assert allowed.feedback.error_code is None
    assert allowed.action_record is not None
    assert allowed.action_record.kind == "STORED"
    assert dispatcher.call_count == 1
    rows = _action_rows(control_database)
    assert len(rows) == 1
    assert rows[0][0] == "allow-1"
    assert rows[0][1] == "turn-1"
    assert rows[0][2] == "list_files"
    assert rows[0][5] == "ALLOW"
    assert rows[0][6] == "artifact-1"

    # --- DENY trace: no dispatch, control feedback, DENY record. ---
    dispatcher.call_count = 0
    denied = pipeline.execute(
        outside_scope_patch_response(),
        valid_context(
            database=control_database,
            action_prefix="deny",
            patch_path_fact="PATCH_PATH_NOT_EDITABLE",
        ),
    )
    assert denied.policy_decision == "DENY"
    assert denied.dispatch_result is None
    assert dispatcher.call_count == 0
    assert denied.feedback.kind == "APPENDED"
    assert denied.feedback.error_code == "PATCH_PATH_NOT_EDITABLE"
    assert denied.feedback.record_id == (
        "control:PATCH_PATH_NOT_EDITABLE:2026-08-06T09:00:00.000Z"
    )
    rows = _action_rows(control_database)
    assert len(rows) == 2
    assert rows[1][0] == "deny-1"
    assert rows[1][2] == "apply_candidate_patch"
    assert rows[1][5] == "DENY"
    assert rows[1][6] is None

    # --- Invalid output trace: parse failure, no policy, no dispatch,
    #     control feedback, no action record. ---
    dispatcher.call_count = 0
    invalid = pipeline.execute(
        invalid_response(),
        valid_context(database=control_database, action_prefix="invalid"),
    )
    assert invalid.parse_outcome == "INVALID"
    assert invalid.policy_decision is None
    assert invalid.action_id is None
    assert invalid.dispatch_result is None
    assert invalid.action_record is None
    assert dispatcher.call_count == 0
    assert invalid.feedback.kind == "APPENDED"
    assert invalid.feedback.error_code == "NOT_JSON_OBJECT"
    assert len(_action_rows(control_database)) == 2

    # --- Tool failure trace: ALLOW dispatch fails, ACTION feedback with
    #     the tool's stable code, ALLOW record with no result ref. ---
    dispatcher.call_count = 0
    failed = pipeline.execute(
        read_file_response(),
        valid_context(database=control_database, action_prefix="tool"),
    )
    assert failed.policy_decision == "ALLOW"
    assert failed.dispatch_result is not None
    assert failed.dispatch_result.status == "FAILED"
    assert dispatcher.call_count == 1
    assert failed.feedback.kind == "APPENDED"
    assert failed.feedback.error_code == "FILE_NOT_TEXT"
    rows = _action_rows(control_database)
    assert len(rows) == 3
    assert rows[2][0] == "tool-1"
    assert rows[2][2] == "read_file"
    assert rows[2][5] == "ALLOW"
    assert rows[2][6] is None

    # --- Check feedback trace: a rejected run-check plan returns the
    #     closed rejection code as feedback, never hidden. ---
    dispatcher.call_count = 0
    checked = pipeline.execute(
        run_check_response(),
        valid_context(database=control_database, action_prefix="check"),
    )
    assert checked.policy_decision == "ALLOW"
    assert checked.dispatch_result is not None
    assert checked.dispatch_result.status == "FAILED"
    assert dispatcher.call_count == 1
    assert checked.feedback.kind == "APPENDED"
    assert checked.feedback.error_code == "INTERNAL_ERROR"
    assert len(_action_rows(control_database)) == 4

    # --- Completion proposal trace: ALLOW dispatch, no feedback, record. ---
    dispatcher.call_count = 0
    proposed = pipeline.execute(
        completion_response(),
        valid_context(database=control_database, action_prefix="done"),
    )
    assert proposed.policy_decision == "ALLOW"
    assert proposed.dispatch_result is not None
    assert proposed.dispatch_result.status == "SUCCEEDED"
    assert dispatcher.call_count == 1
    assert proposed.feedback.kind == "NONE"
    rows = _action_rows(control_database)
    assert len(rows) == 5
    # Ordered by action_id: allow-1, check-1, deny-1, done-1, tool-1.
    assert rows[3][2] == "propose_completion"
    assert rows[3][5] == "ALLOW"

    # --- Phase gate trace: policy denies before the dispatcher. ---
    dispatcher.call_count = 0
    phased = pipeline.execute(
        list_files_response(),
        valid_context(
            database=control_database,
            action_prefix="phase",
            run_phase="PREFLIGHT",
        ),
    )
    assert phased.policy_decision == "DENY"
    assert phased.feedback.error_code == "ACTION_NOT_ALLOWED_IN_PHASE"
    assert dispatcher.call_count == 0
    assert len(_action_rows(control_database)) == 6

    # --- Consume-once trace: the turn's selected refs bind exactly once. ---
    repository = FeedbackRepositoryV1(control_database)
    assert repository.append((feedback_record("fb-1"),)).kind == "APPENDED"
    dispatcher.call_count = 0
    first = pipeline.execute(
        outside_scope_patch_response(),
        valid_context(
            database=control_database,
            action_prefix="consume",
            consumed_feedback_refs=("fb-1",),
            patch_path_fact="PATCH_PATH_NOT_EDITABLE",
        ),
    )
    assert first.consume_outcome is not None
    assert first.consume_outcome.kind == "CONSUMED"
    assert first.consume_outcome.consumed_refs == ("fb-1",)
    # The identical consume command replays stably through the Task 07
    # ledger (never a double consume) — the refs bind exactly once.
    second = pipeline.execute(
        outside_scope_patch_response(),
        valid_context(
            database=control_database,
            action_prefix="consume2",
            consumed_feedback_refs=("fb-1",),
            patch_path_fact="PATCH_PATH_NOT_EDITABLE",
        ),
    )
    assert second.consume_outcome is not None
    assert second.consume_outcome.kind == "REPLAY"
    assert dispatcher.call_count == 0
    assert ("fb-1", "CHECK", "turn-1") in _feedback_rows(control_database)

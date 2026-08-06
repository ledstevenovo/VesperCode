"""T24.1 legacy step 24.C: atomic feedback-to-turn consumption tests.

The exact RED test pins the one-winner consumption (two different turns
can never both consume one feedback record); the matrix pins the exact
repository contract (bounded append with exact replay and zero-row
conflicts, turn/reference identity validation, the atomic
compare-and-consume transaction, stable same-command replay, zero
mutation for missing/duplicate/forged/conflicted refs, concurrency with
exactly one winner, and closed surrogate rejection).
"""

from __future__ import annotations

import threading
from collections.abc import Iterator
from pathlib import Path

import pytest

# The repository consumes pydantic runtime contracts; the hash-locked
# gate toolchain installs no runtime dependencies, so this module skips
# cleanly there (formal env runs it fully).
pytest.importorskip("pydantic")

from src.vespercode.canonical.path_v1 import CanonicalRelativePathV1
from src.vespercode.canonical.timestamp_v1 import CanonicalTimestampV1
from src.vespercode.contracts.optional import AbsentV1, PresentV1
from src.vespercode.loop.feedback import (
    CheckFeedbackSourceV1,
    FeedbackRecordV1,
    FeedbackSeverityV1,
)
from src.vespercode.loop.feedback_consumption import (
    FeedbackAppendResultV1,
    FeedbackConsumptionResultV1,
    FeedbackRepositoryV1,
    consume_feedback,
)
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
from src.vespercode.storage.migrations.v0008_feedback import (
    FEEDBACK_V1_MIGRATION,
)

_CREATED_AT = CanonicalTimestampV1("2026-08-06T09:00:00.000Z")

_MIGRATIONS = (
    RUN_WAIT_V1_MIGRATION,
    IDEMPOTENCY_V1_MIGRATION,
    DISCLOSURE_GRANTS_V1_MIGRATION,
    DISCLOSURE_AUTHORIZATIONS_V1_MIGRATION,
    MEMORY_V1_MIGRATION,
    AUDIT_V1_MIGRATION,
    AGENT_TURNS_V1_MIGRATION,
    FEEDBACK_V1_MIGRATION,
)


def feedback_record(
    record_id: str,
    *,
    severity: FeedbackSeverityV1 = "HIGH",
    summary: str = "check failed",
) -> FeedbackRecordV1:
    """One deterministic valid record (helper duplication is deliberate)."""
    return FeedbackRecordV1(
        id=record_id,
        kind="CHECK",
        severity=severity,
        created_at=_CREATED_AT,
        summary=summary,
        source_ref=CheckFeedbackSourceV1(
            kind="CHECK",
            check_kind="TARGET_TESTS",
            path=AbsentV1(kind="ABSENT"),
        ),
        bounded_payload='{"check_kind":"TARGET_TESTS","status":"FAIL"}',
    )


def _seed_run(
    database: ControlDatabase,
    run_id: str,
    status: str,
    phase: str | None,
) -> None:
    """Insert one deterministic run row (config snapshot + run)."""
    with database.immediate_transaction() as tx:
        tx.execute(
            "INSERT INTO run_config_snapshots (config_snapshot_id, digest,"
            " llm_profile_id, reference_profile_id, policy_id, target_test_ids,"
            " limits_digest, frozen_at)"
            " VALUES (?, ?, 'llm-1', 'ref-1', 'policy-1', '[]', 'limits-1', ?)",
            (f"cfg-{run_id}", f"{run_id}{'a' * 64}"[:64], _CREATED_AT.value),
        )
        tx.execute(
            "INSERT INTO runs (run_id, workspace_identity, config_snapshot_id,"
            " status, phase, revision, started_at, run_deadline)"
            " VALUES (?, 'workspace-a', ?, ?, ?, 1, ?, ?)",
            (
                run_id,
                f"cfg-{run_id}",
                status,
                phase,
                _CREATED_AT.value,
                "2026-08-06T10:00:00.000Z",
            ),
        )


def _seed_turn(database: ControlDatabase, run_id: str, turn_id: str) -> None:
    """Insert one deterministic ACTIVE agent_turns row."""
    with database.immediate_transaction() as tx:
        tx.execute(
            "INSERT INTO agent_turns (turn_id, run_id, revision, status,"
            " outcome, closed_at, request_ref, result_ref)"
            " VALUES (?, ?, 1, 'ACTIVE', NULL, NULL, NULL, NULL)",
            (turn_id, run_id),
        )


@pytest.fixture
def control_database(tmp_path: Path) -> Iterator[ControlDatabase]:
    database = open_control_database(tmp_path / "feedback_consumption.db")
    apply_migrations(database, _MIGRATIONS)
    yield database
    database.close()


@pytest.fixture
def repository(control_database: ControlDatabase) -> FeedbackRepositoryV1:
    # Each turn is the sole ACTIVE turn of its own run (the v0007
    # one-active-turn partial unique index allows only one per Run).
    _seed_run(control_database, "run-1", "RUNNING", "AGENT_LOOP")
    _seed_turn(control_database, "run-1", "turn-1")
    _seed_run(control_database, "run-2", "RUNNING", "AGENT_LOOP")
    _seed_turn(control_database, "run-2", "turn-2")
    return FeedbackRepositoryV1(control_database)


def consume_for_two_turns(
    repository: FeedbackRepositoryV1, feedback_id: str
) -> tuple[FeedbackConsumptionResultV1, ...]:
    """Append one record and consume it for two different turns."""
    appended = repository.append((feedback_record(feedback_id),))
    assert appended.kind == "APPENDED"
    first = consume_feedback("turn-1", (feedback_id,), repository)
    second = consume_feedback("turn-2", (feedback_id,), repository)
    return (first, second)


def test_two_turns_cannot_consume_one_feedback_record(
    repository: FeedbackRepositoryV1,
) -> None:
    results = consume_for_two_turns(repository, "feedback-1")
    assert sorted(result.kind for result in results) == ["ALREADY_CONSUMED", "CONSUMED"]


def _consumed_by(database: ControlDatabase, feedback_id: str) -> str | None:
    rows = database.read_rows(
        "SELECT consumed_by_turn_id FROM feedback_records WHERE feedback_id = ?",
        (feedback_id,),
    )
    if not rows:
        return None
    value = rows[0][0]
    return None if value is None else str(value)


def _record_rows(database: ControlDatabase) -> int:
    rows = database.read_rows("SELECT COUNT(*) FROM feedback_records")
    return int(rows[0][0])


def test_feedback_consumption_transaction_matrix(
    tmp_path: Path,
    control_database: ControlDatabase,
    repository: FeedbackRepositoryV1,
) -> None:
    """PLAN Registry row 24.C: the exact consumption transaction matrix.

    Per the SPEC_PROCESS 49 precedent the card Expected line is the
    operative matrix authority: exact v0008 schema; exactly one turn
    consumes each record; replay is stable; and missing, duplicate,
    forged, or conflicted refs change nothing.
    """
    # --- Append: bounded records, exact replay, zero-row conflicts. ---
    # Task 24.A bounded records are always appendable: a record with a
    # long (but fitting) attributed source path appends exactly once.
    long_path_record = FeedbackRecordV1(
        id="fb-long-path",
        kind="CHECK",
        severity="HIGH",
        created_at=_CREATED_AT,
        summary="long attributed path",
        source_ref=CheckFeedbackSourceV1(
            kind="CHECK",
            check_kind="TARGET_TESTS",
            path=PresentV1(
                kind="PRESENT",
                value=CanonicalRelativePathV1("src/" + "a" * 100 + ".py"),
            ),
        ),
        bounded_payload='{"check_kind":"TARGET_TESTS"}',
    )
    long_append = repository.append((long_path_record,))
    assert long_append.kind == "APPENDED"
    assert long_append.appended_count == 1
    assert _record_rows(control_database) == 1
    assert _consumed_by(control_database, "fb-long-path") is None

    first_append = repository.append((feedback_record("fb-1"),))
    assert first_append.kind == "APPENDED"
    assert first_append.appended_count == 1
    assert _record_rows(control_database) == 2
    # Exact replay of the identical record is free and stable.
    replay = repository.append((feedback_record("fb-1"),))
    assert replay.kind == "REPLAY"
    assert replay.appended_count == 0
    assert _record_rows(control_database) == 2
    # The same id with different facts is a conflict: zero rows.
    conflict = repository.append(
        (feedback_record("fb-1", severity="CRITICAL", summary="different"),)
    )
    assert conflict.kind == "EVENT_ID_REUSE_CONFLICT"
    assert conflict.appended_count == 0
    assert _record_rows(control_database) == 2
    assert _consumed_by(control_database, "fb-1") is None
    # An empty sequence rejects with zero rows; lone-surrogate records
    # fail closed at the model boundary before any append exists.
    empty = repository.append(())
    assert empty.kind == "REJECTED"
    assert _record_rows(control_database) == 2
    with pytest.raises(Exception, match="scalar"):
        FeedbackRecordV1(
            id="fb-sur",
            kind="CHECK",
            severity="HIGH",
            created_at=_CREATED_AT,
            summary="bad \ud800",
            source_ref=CheckFeedbackSourceV1(
                kind="CHECK",
                check_kind="TARGET_TESTS",
                path=AbsentV1(kind="ABSENT"),
            ),
            bounded_payload='{"check_kind":"TARGET_TESTS"}',
        )
    assert _record_rows(control_database) == 2
    # A whole sequence appends atomically.
    batch = repository.append((feedback_record("fb-2"), feedback_record("fb-3")))
    assert batch.kind == "APPENDED"
    assert batch.appended_count == 2
    assert _record_rows(control_database) == 4
    # A conflict anywhere in the sequence rolls everything back.
    mixed = repository.append(
        (feedback_record("fb-4"), feedback_record("fb-2", summary="changed"))
    )
    assert mixed.kind == "EVENT_ID_REUSE_CONFLICT"
    assert _record_rows(control_database) == 4
    assert _consumed_by(control_database, "fb-4") is None

    # --- Consumption: exactly one turn wins; the rest changes nothing. ---
    consumed = consume_feedback("turn-1", ("fb-2",), repository)
    assert consumed.kind == "CONSUMED"
    assert consumed.turn_id == "turn-1"
    assert consumed.consumed_refs == ("fb-2",)
    assert _consumed_by(control_database, "fb-2") == "turn-1"
    # A second turn is ALREADY_CONSUMED with zero mutation.
    second = consume_feedback("turn-2", ("fb-2",), repository)
    assert second.kind == "ALREADY_CONSUMED"
    assert _consumed_by(control_database, "fb-2") == "turn-1"
    # Replaying the exact same consume command is stable (REPLAY).
    replay_consume = consume_feedback("turn-1", ("fb-2",), repository)
    assert replay_consume.kind == "REPLAY"
    assert replay_consume.consumed_refs == ("fb-2",)
    assert _consumed_by(control_database, "fb-2") == "turn-1"
    # A missing turn changes nothing.
    missing_turn = consume_feedback("turn-missing", ("fb-1",), repository)
    assert missing_turn.kind == "TURN_NOT_FOUND"
    assert _consumed_by(control_database, "fb-1") is None
    # A missing (forged) ref changes nothing.
    missing_ref = consume_feedback("turn-2", ("fb-ghost",), repository)
    assert missing_ref.kind == "MISSING_REF"
    # Duplicate refs in one command change nothing.
    duplicate = consume_feedback("turn-2", ("fb-1", "fb-1"), repository)
    assert duplicate.kind == "DUPLICATE_REF"
    assert _consumed_by(control_database, "fb-1") is None
    # A mixed command (one free ref, one already consumed) changes
    # nothing at all: the free ref stays unconsumed.
    mixed_consume = consume_feedback("turn-2", ("fb-1", "fb-2"), repository)
    assert mixed_consume.kind == "ALREADY_CONSUMED"
    assert _consumed_by(control_database, "fb-1") is None
    # Surrogate identities reject with zero side effects.
    surrogate_consume = consume_feedback("turn-\ud800", ("fb-1",), repository)
    assert surrogate_consume.kind == "REJECTED"
    surrogate_ref = consume_feedback("turn-2", ("fb-\udfff",), repository)
    assert surrogate_ref.kind == "REJECTED"
    assert _consumed_by(control_database, "fb-1") is None
    # Empty refs are rejected before any mutation.
    empty_refs = consume_feedback("turn-2", (), repository)
    assert empty_refs.kind == "REJECTED"
    assert _consumed_by(control_database, "fb-1") is None

    # --- Concurrency: exactly one winner consumes each record. ---
    repository.append((feedback_record("fb-concurrent"),))
    outcomes: list[str] = []
    database_path = tmp_path / "feedback_consumption.db"

    def _consume(turn_id: str) -> None:
        # Each contender uses its own connection so the BEGIN IMMEDIATE
        # transactions serialize at the database level.
        database = open_control_database(database_path)
        try:
            own = FeedbackRepositoryV1(database)
            outcomes.append(consume_feedback(turn_id, ("fb-concurrent",), own).kind)
        finally:
            database.close()

    threads = [
        threading.Thread(target=_consume, args=("turn-1",)),
        threading.Thread(target=_consume, args=("turn-2",)),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert sorted(outcomes) == ["ALREADY_CONSUMED", "CONSUMED"]
    assert _consumed_by(control_database, "fb-concurrent") in ("turn-1", "turn-2")

    # --- Result contracts are closed and bounded. ---
    assert (
        FeedbackAppendResultV1(
            kind="APPENDED", message="ok", appended_count=1
        ).appended_count
        == 1
    )
    assert FeedbackConsumptionResultV1(
        kind="CONSUMED",
        message="ok",
        turn_id="turn-1",
        consumed_refs=("fb-1",),
    ).consumed_refs == ("fb-1",)
    with pytest.raises(Exception):
        FeedbackAppendResultV1(kind="MAYBE", message="x")  # type: ignore[arg-type]

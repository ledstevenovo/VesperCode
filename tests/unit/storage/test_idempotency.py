"""T07.2/T07.3 legacy step 7.C: transaction-bound idempotency ledger tests.

The exact RED test pins the event-id reuse conflict contract; the matrix
pins first-NEW recording, REPLAY purity, conflict non-mutation, rollback,
and the concurrent one-NEW-one-REPLAY row against the PLAN Registry row
for 7.C.
"""

from __future__ import annotations

import threading
from collections.abc import Iterator
from pathlib import Path

import pytest

# The repository consumes pydantic runtime contracts; the hash-locked gate
# toolchain installs no runtime dependencies, so this module skips cleanly
# there (formal env runs it fully).
pytest.importorskip("pydantic")

from vespercode.storage.connection import (
    ControlDatabase,
    ControlTransactionV1,
    open_control_database,
)
from vespercode.storage.idempotency import IdempotencyRepository
from vespercode.storage.migration_engine import apply_migrations
from vespercode.storage.migrations.v0001_run_wait import RUN_WAIT_V1_MIGRATION
from vespercode.storage.migrations.v0002_idempotency import (
    IDEMPOTENCY_V1_MIGRATION,
)


@pytest.fixture
def control_database(tmp_path: Path) -> Iterator[ControlDatabase]:
    database = open_control_database(tmp_path / "idempotency.db")
    apply_migrations(
        database,
        (RUN_WAIT_V1_MIGRATION, IDEMPOTENCY_V1_MIGRATION),
    )
    yield database
    database.close()


@pytest.fixture
def repository(control_database: ControlDatabase) -> IdempotencyRepository:
    return IdempotencyRepository(control_database)


@pytest.fixture
def transaction(control_database: ControlDatabase) -> Iterator[ControlTransactionV1]:
    """One caller-owned Task 7.A immediate transaction for the test body."""
    with control_database.immediate_transaction() as tx:
        yield tx


def test_event_id_reuse_with_different_request_is_conflict(
    repository: IdempotencyRepository,
    transaction: ControlTransactionV1,
) -> None:
    assert (
        repository.record_or_replay(
            transaction, "wait", "evt-1", "a" * 64, "b" * 64
        ).kind
        == "NEW"
    )
    assert (
        repository.record_or_replay(
            transaction, "wait", "evt-1", "c" * 64, "d" * 64
        ).kind
        == "EVENT_ID_REUSE_CONFLICT"
    )


def _ledger_rows(
    database: ControlDatabase,
    scope: str,
) -> list[tuple[str, str, str, str]]:
    rows = database.read_rows(
        "SELECT scope, event_id, request_digest, result_digest"
        " FROM idempotency_events WHERE scope = ? ORDER BY event_id",
        (scope,),
    )
    return [(str(r[0]), str(r[1]), str(r[2]), str(r[3])) for r in rows]


def test_idempotency_replay_rollback_concurrency_matrix(
    tmp_path: Path,
    control_database: ControlDatabase,
    repository: IdempotencyRepository,
) -> None:
    """PLAN Registry row 7.C.

    First request => NEW and one ledger row; identical request/result =>
    REPLAY with unchanged domain/ledger counts; changed request =>
    EVENT_ID_REUSE_CONFLICT with zero mutation; rollback leaves no row;
    concurrent identical requests produce one NEW and one REPLAY.
    """
    request = "1" * 64
    result = "2" * 64

    # First request => NEW and exactly one ledger row.
    with control_database.immediate_transaction() as tx:
        first = repository.record_or_replay(tx, "wait", "evt-1", request, result)
    assert first.kind == "NEW"
    assert first.result_digest == result
    assert _ledger_rows(control_database, "wait") == [
        ("wait", "evt-1", request, result)
    ]

    # Identical request/result => REPLAY with unchanged ledger counts.
    with control_database.immediate_transaction() as tx:
        replayed = repository.record_or_replay(tx, "wait", "evt-1", request, result)
    assert replayed.kind == "REPLAY"
    assert replayed.result_digest == result
    assert _ledger_rows(control_database, "wait") == [
        ("wait", "evt-1", request, result)
    ]

    # Identical request with different result bytes still REPLAYs the
    # recorded first result (the first result wins, no mutation).
    with control_database.immediate_transaction() as tx:
        different_result = repository.record_or_replay(
            tx, "wait", "evt-1", request, "3" * 64
        )
    assert different_result.kind == "REPLAY"
    assert different_result.result_digest == result
    assert _ledger_rows(control_database, "wait") == [
        ("wait", "evt-1", request, result)
    ]

    # Changed request bytes => EVENT_ID_REUSE_CONFLICT with zero mutation.
    with control_database.immediate_transaction() as tx:
        conflict = repository.record_or_replay(tx, "wait", "evt-1", "4" * 64, "5" * 64)
    assert conflict.kind == "EVENT_ID_REUSE_CONFLICT"
    assert conflict.result_digest == result
    assert _ledger_rows(control_database, "wait") == [
        ("wait", "evt-1", request, result)
    ]

    # Rollback leaves no row: the recording is bound to the caller tx.
    with pytest.raises(RuntimeError, match="abort"):
        with control_database.immediate_transaction() as tx:
            recorded = repository.record_or_replay(
                tx, "wait", "evt-rolled-back", "6" * 64, "7" * 64
            )
            assert recorded.kind == "NEW"
            raise RuntimeError("abort")
    assert all(
        row[1] != "evt-rolled-back" for row in _ledger_rows(control_database, "wait")
    )

    # Concurrent identical requests produce exactly one NEW and one REPLAY.
    # Each thread opens its own connection (sqlite3 connections are
    # thread-bound); BEGIN IMMEDIATE serializes the writers.
    database_path = tmp_path / "idempotency.db"
    outcomes: list[str] = []
    barrier = threading.Barrier(2, timeout=60)

    def _record() -> None:
        database = open_control_database(database_path)
        try:
            ledger = IdempotencyRepository(database)
            barrier.wait()
            with database.immediate_transaction() as tx:
                outcomes.append(
                    ledger.record_or_replay(
                        tx, "wait", "evt-concurrent", request, result
                    ).kind
                )
        finally:
            database.close()

    threads = [threading.Thread(target=_record) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert sorted(outcomes) == ["NEW", "REPLAY"]
    assert _ledger_rows(control_database, "wait") == [
        ("wait", "evt-1", request, result),
        ("wait", "evt-concurrent", request, result),
    ]


def test_record_or_replay_rejects_empty_identities(
    repository: IdempotencyRepository,
    transaction: ControlTransactionV1,
) -> None:
    for scope, event_id in (("", "evt-1"), ("wait", "")):
        with pytest.raises(ValueError, match="non-empty"):
            repository.record_or_replay(
                transaction, scope, event_id, "a" * 64, "b" * 64
            )


def test_record_or_replay_rejects_non_digest_identities(
    repository: IdempotencyRepository,
    transaction: ControlTransactionV1,
) -> None:
    for request_digest, result_digest in (
        ("not-hex", "b" * 64),
        ("a" * 64, "SHORT"),
    ):
        with pytest.raises(ValueError, match="digest"):
            repository.record_or_replay(
                transaction, "wait", "evt-1", request_digest, result_digest
            )
    bad_type: object = 123
    with pytest.raises(ValueError, match="digest"):
        repository.record_or_replay(
            transaction,
            "wait",
            "evt-1",
            bad_type,  # type: ignore[arg-type]
            "b" * 64,
        )


def test_new_records_only_inside_the_caller_transaction(
    control_database: ControlDatabase,
    repository: IdempotencyRepository,
) -> None:
    # A committed caller transaction persists the recording...
    with control_database.immediate_transaction() as tx:
        first = repository.record_or_replay(tx, "wait", "evt-tx", "a" * 64, "b" * 64)
        assert first.kind == "NEW"
        assert _ledger_rows(control_database, "wait") == [
            ("wait", "evt-tx", "a" * 64, "b" * 64)
        ]
    assert _ledger_rows(control_database, "wait") == [
        ("wait", "evt-tx", "a" * 64, "b" * 64)
    ]
    # ...and a rolled-back caller transaction leaves no row behind.
    with pytest.raises(RuntimeError, match="abort"):
        with control_database.immediate_transaction() as tx:
            repository.record_or_replay(tx, "wait", "evt-tx2", "c" * 64, "d" * 64)
            raise RuntimeError("abort")
    assert _ledger_rows(control_database, "wait") == [
        ("wait", "evt-tx", "a" * 64, "b" * 64)
    ]

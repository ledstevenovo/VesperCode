"""T22.1 legacy step 22.C: transactional memory clear tests.

Pins the exact RED (a successful clear is immediately ineligible for
selection) and the full clear transaction matrix: replay is idempotent
under the T07.3 ledger, event-id reuse for a different request is a
conflict, forged/unknown/cross-workspace clears change nothing, a
mid-transaction failure rolls the whole tombstone batch back with zero
ledger events, already-cleared targets stay immutable, and other
workspaces are never touched.  Audit/source facts, creation/selection
policy, and retention remain out of scope (GREEN-4).
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest

# The service consumes pydantic runtime contracts; the hash-locked gate
# toolchain installs no runtime dependencies, so this module skips
# cleanly there (formal env runs it fully).
pytest.importorskip("pydantic")

from vespercode.canonical.timestamp_v1 import CanonicalTimestampV1
from vespercode.memory.clear import (
    ClearMemoryCommandV1,
    MemoryClearService,
)
from vespercode.memory.entry import (
    KnownFailureSourceV1,
    MemoryCreatorV1,
    MemoryKindV1,
    MemorySourceV1,
    UserDecisionSourceV1,
    UserVisibleTextSourceV1,
)
from vespercode.memory.repository import (
    CreateMemoryCommandV1,
    MemoryRepository,
)
from vespercode.memory.selection import (
    MemorySelectionQueryV1,
    MemorySelectorV1,
)
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

_CREATED_AT = CanonicalTimestampV1("2026-08-06T09:00:00.000Z")
_CLEARED_AT = CanonicalTimestampV1("2026-08-06T11:00:00.000Z")


@pytest.fixture
def control_database(tmp_path: Path) -> Iterator[ControlDatabase]:
    database = open_control_database(tmp_path / "memory.db")
    apply_migrations(
        database,
        (
            RUN_WAIT_V1_MIGRATION,
            IDEMPOTENCY_V1_MIGRATION,
            DISCLOSURE_GRANTS_V1_MIGRATION,
            DISCLOSURE_AUTHORIZATIONS_V1_MIGRATION,
            MEMORY_V1_MIGRATION,
        ),
    )
    yield database
    database.close()


def _source_for(kind: MemoryKindV1) -> MemorySourceV1:
    """One matching bounded source variant per kind (helper duplication is
    deliberate: the card's exact Files list forbids a shared helper module)."""
    if kind == "PROJECT_CONVENTION":
        return UserVisibleTextSourceV1(kind="USER_VISIBLE_TEXT", reference="conv-1")
    if kind == "USER_DECISION":
        return UserDecisionSourceV1(
            kind="USER_DECISION", decision="APPROVE", reference="wait-1"
        )
    return KnownFailureSourceV1(
        kind="KNOWN_FAILURE",
        check_result_digest="a" * 64,
        failure_fingerprint_digest="b" * 64,
    )


def _insert(
    repository: MemoryRepository,
    workspace: str,
    entry_id: str,
    summary: str = "convention text",
    kind: MemoryKindV1 = "PROJECT_CONVENTION",
    creator: MemoryCreatorV1 = "USER",
) -> None:
    created = repository.create(
        CreateMemoryCommandV1(
            workspace_identity=workspace,
            kind=kind,
            summary=summary,
            creator=creator,
            source=_source_for(kind),
            entry_id=entry_id,
            created_at=_CREATED_AT,
        )
    )
    assert created.kind == "CREATED"


def memory_clear_fixture() -> tuple[MemoryClearService, MemorySelectorV1]:
    """One in-memory database with two workspace-a conventions to clear
    (SPEC 4.7 prescribes in-memory SQLite for the deterministic tests)."""
    database = open_control_database(Path(":memory:"))
    apply_migrations(
        database,
        (
            RUN_WAIT_V1_MIGRATION,
            IDEMPOTENCY_V1_MIGRATION,
            DISCLOSURE_GRANTS_V1_MIGRATION,
            DISCLOSURE_AUTHORIZATIONS_V1_MIGRATION,
            MEMORY_V1_MIGRATION,
        ),
    )
    repository = MemoryRepository(database)
    _insert(repository, "workspace-a", "conv-1")
    _insert(repository, "workspace-a", "conv-2")
    service = MemoryClearService(database, repository)
    selector = MemorySelectorV1(repository)
    return service, selector


def clear_workspace_command() -> ClearMemoryCommandV1:
    return ClearMemoryCommandV1(
        workspace_identity="workspace-a",
        creator="USER",
        event_id="clear-red-1",
        target_entry_ids=("conv-1", "conv-2"),
        decided_at=_CLEARED_AT,
    )


def query() -> MemorySelectionQueryV1:
    return MemorySelectionQueryV1(workspace_identity_digest="workspace-a")


def test_successful_clear_is_immediately_ineligible_for_selection() -> None:
    service, selector = memory_clear_fixture()
    service.clear(clear_workspace_command())
    assert selector.select(query()).entries == ()


def test_memory_clear_transaction_matrix(
    control_database: ControlDatabase,
) -> None:
    """Expected (22.C): atomic clears, idempotent replay, zero-row rejects."""
    repository = MemoryRepository(control_database)
    _insert(repository, "workspace-a", "conv-1")
    _insert(repository, "workspace-a", "conv-2")
    _insert(
        repository,
        "workspace-b",
        "conv-b",
        kind="USER_DECISION",
        creator="CONTROL_PLANE",
    )
    service = MemoryClearService(control_database, repository)
    selector = MemorySelectorV1(repository)

    # Exact authorized clear: tombstones commit and selection excludes the
    # targeted workspace-a entries immediately.
    clear_a = service.clear(
        ClearMemoryCommandV1(
            workspace_identity="workspace-a",
            creator="USER",
            event_id="clear-1",
            target_entry_ids=("conv-1", "conv-2"),
            decided_at=_CLEARED_AT,
        )
    )
    assert clear_a.kind == "CLEARED"
    assert clear_a.cleared_count == 2
    assert (
        selector.select(
            MemorySelectionQueryV1(workspace_identity_digest="workspace-a")
        ).entries
        == ()
    )
    # The other workspace is untouched.
    assert [
        entry.entry_id
        for entry in selector.select(
            MemorySelectionQueryV1(workspace_identity_digest="workspace-b")
        ).entries
    ] == ["conv-b"]

    # Replay of the identical clear event is free and changes nothing.
    replay = service.clear(
        ClearMemoryCommandV1(
            workspace_identity="workspace-a",
            creator="USER",
            event_id="clear-1",
            target_entry_ids=("conv-1", "conv-2"),
            decided_at=_CLEARED_AT,
        )
    )
    assert replay.kind == "REPLAY"
    _assert_tombstone(control_database, "conv-1", "clear-1")

    # Event-id reuse for a different request is a conflict with zero rows.
    conflict = service.clear(
        ClearMemoryCommandV1(
            workspace_identity="workspace-a",
            creator="USER",
            event_id="clear-1",
            target_entry_ids=("conv-1",),
            decided_at=_CLEARED_AT,
        )
    )
    assert conflict.kind == "EVENT_ID_REUSE_CONFLICT"
    _assert_tombstone(control_database, "conv-1", "clear-1")

    # Forged clears (creator is not the user) change nothing.
    forged = service.clear(
        ClearMemoryCommandV1(
            workspace_identity="workspace-b",
            creator="MODEL",
            event_id="clear-forged",
            target_entry_ids=("conv-b",),
            decided_at=_CLEARED_AT,
        )
    )
    assert forged.error_code == "MEMORY_CREATOR_FORBIDDEN"
    _assert_no_tombstone(control_database, "conv-b")

    # Cross-workspace targeting is a scope violation with zero rows on the
    # valid target as well (partial failure changes nothing).
    cross = service.clear(
        ClearMemoryCommandV1(
            workspace_identity="workspace-b",
            creator="USER",
            event_id="clear-cross",
            target_entry_ids=("conv-b", "conv-1"),
            decided_at=_CLEARED_AT,
        )
    )
    assert cross.error_code == "MEMORY_SCOPE_VIOLATION"
    _assert_no_tombstone(control_database, "conv-b")
    _assert_tombstone(control_database, "conv-1", "clear-1")

    # Unknown targets are a scope violation with zero rows.
    unknown = service.clear(
        ClearMemoryCommandV1(
            workspace_identity="workspace-a",
            creator="USER",
            event_id="clear-unknown",
            target_entry_ids=("conv-1", "no-such-entry"),
            decided_at=_CLEARED_AT,
        )
    )
    assert unknown.error_code == "MEMORY_SCOPE_VIOLATION"
    _assert_tombstone(control_database, "conv-1", "clear-1")

    # A mid-transaction failure rolls the whole tombstone batch back and
    # removes the ledger event, so nothing changes.  The bomb target is a
    # fresh uncleared entry whose update is aborted by a local trigger.
    _insert(repository, "workspace-a", "conv-3")
    _insert(repository, "workspace-a", "conv-4")
    with control_database.immediate_transaction() as tx:
        tx.execute(
            "CREATE TRIGGER bomb_clear BEFORE UPDATE ON memory_entries"
            " WHEN NEW.entry_id = 'conv-4'"
            " BEGIN SELECT RAISE(ABORT, 'bomb'); END"
        )
    failed = service.clear(
        ClearMemoryCommandV1(
            workspace_identity="workspace-a",
            creator="USER",
            event_id="clear-bomb",
            target_entry_ids=("conv-3", "conv-4"),
            decided_at=_CLEARED_AT,
        )
    )
    assert failed.error_code == "MEMORY_STORE_FAILED"
    _assert_no_tombstone(control_database, "conv-3")
    _assert_no_tombstone(control_database, "conv-4")
    assert (
        len(
            control_database.read_rows(
                "SELECT 1 FROM idempotency_events WHERE event_id = 'clear-bomb'"
            )
        )
        == 0
    )

    # A later clear targeting an already-cleared entry is a safe no-op and
    # never rewrites the immutable tombstone.
    again = service.clear(
        ClearMemoryCommandV1(
            workspace_identity="workspace-a",
            creator="USER",
            event_id="clear-again",
            target_entry_ids=("conv-1",),
            decided_at=_CLEARED_AT,
        )
    )
    assert again.kind == "CLEARED"
    assert again.cleared_count == 0
    _assert_tombstone(control_database, "conv-1", "clear-1")


def _tombstone(
    control_database: ControlDatabase, entry_id: str
) -> tuple[str | None, str | None]:
    rows = control_database.read_rows(
        "SELECT cleared_at, clear_transaction_id FROM memory_entries"
        " WHERE entry_id = ?",
        (entry_id,),
    )
    assert len(rows) == 1
    cleared_at: str | None = rows[0][0]
    transaction_id: str | None = rows[0][1]
    return cleared_at, transaction_id


def _assert_tombstone(
    control_database: ControlDatabase, entry_id: str, transaction_id: str
) -> None:
    cleared_at, recorded = _tombstone(control_database, entry_id)
    assert cleared_at == _CLEARED_AT.value
    assert recorded == transaction_id


def _assert_no_tombstone(control_database: ControlDatabase, entry_id: str) -> None:
    cleared_at, recorded = _tombstone(control_database, entry_id)
    assert cleared_at is None
    assert recorded is None

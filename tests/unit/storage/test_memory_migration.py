"""T22.1 legacy step 22.A: exact v0005 memory schema tests.

Pins the immutable descriptor (version 5 / name / checksum binding), the
exact ``memory_entries`` table (columns, kind/creator CHECK closures,
untrusted flag, nullable clear tombstone fields, the workspace index, and
no secret/permission/full-body column), strict version gating (v0005
cannot apply before v0001-v0004), and idempotent replay.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest

# The migration consumes pydantic runtime contracts; the hash-locked gate
# toolchain installs no runtime dependencies, so this module skips cleanly
# there (formal env runs it fully).
pytest.importorskip("pydantic")

from src.vespercode.storage.connection import (
    ControlDatabase,
    open_control_database,
)
from src.vespercode.storage.migration_engine import (
    MigrationV1,
    apply_migrations,
    migration_checksum,
)
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
from src.vespercode.storage.migrations.v0005_memory import (
    MEMORY_V1_MIGRATION,
    MEMORY_V1_STATEMENTS,
)


@pytest.fixture
def control_database(tmp_path: Path) -> Iterator[ControlDatabase]:
    database = open_control_database(tmp_path / "memory_migration.db")
    yield database
    database.close()


def _table_names(database: ControlDatabase) -> set[str]:
    with database.immediate_transaction() as tx:
        return {
            str(row[0])
            for row in tx.execute(
                "SELECT name FROM sqlite_schema"
                " WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
            ).fetchall()
        }
    raise AssertionError("unreachable")


def _columns(database: ControlDatabase, table: str) -> dict[str, str]:
    with database.immediate_transaction() as tx:
        return {
            str(row[1]): str(row[2])
            for row in tx.execute(f"PRAGMA table_info({table})").fetchall()
        }
    raise AssertionError("unreachable")


def _prefix() -> tuple[MigrationV1, MigrationV1, MigrationV1, MigrationV1]:
    return (
        RUN_WAIT_V1_MIGRATION,
        IDEMPOTENCY_V1_MIGRATION,
        DISCLOSURE_GRANTS_V1_MIGRATION,
        DISCLOSURE_AUTHORIZATIONS_V1_MIGRATION,
    )


def test_memory_migration_has_exact_schema(
    control_database: ControlDatabase,
) -> None:
    """PLAN Registry row 449: exact v0005 memory schema."""
    # Descriptor: immutable, version 5, exact name, checksum bound to DDL.
    assert isinstance(MEMORY_V1_MIGRATION, MigrationV1)
    assert MEMORY_V1_MIGRATION.version == 5
    assert MEMORY_V1_MIGRATION.name == "memory_v1"
    assert MEMORY_V1_MIGRATION.checksum.value == migration_checksum(
        5,
        "memory_v1",
        "\n".join(MEMORY_V1_STATEMENTS),
    )
    with pytest.raises(Exception):
        MEMORY_V1_MIGRATION.version = 6  # type: ignore[misc]
    with pytest.raises(TypeError):
        MEMORY_V1_STATEMENTS[0] = (  # type: ignore[index]
            "CREATE TABLE tampered (id INTEGER PRIMARY KEY)"
        )

    # Version 5 cannot apply before the v0001-v0004 prefix.
    assert (
        apply_migrations(control_database, (MEMORY_V1_MIGRATION,)).kind == "VERSION_GAP"
    )
    assert _table_names(control_database) == set()

    # Applied after the prefix: exactly one more table.
    assert (
        apply_migrations(control_database, _prefix() + (MEMORY_V1_MIGRATION,)).kind
        == "APPLIED"
    )
    assert _table_names(control_database) == {
        "schema_migrations",
        "run_config_snapshots",
        "runs",
        "wait_contexts",
        "idempotency_events",
        "disclosure_grant_subjects",
        "disclosure_grants",
        "disclosure_authorizations",
        "memory_entries",
    }
    assert (
        apply_migrations(control_database, _prefix() + (MEMORY_V1_MIGRATION,)).kind
        == "NOOP"
    )

    # MemoryEntry (Registry row 449): PK entry_id, exact workspace identity,
    # kind/creator/summary/source, timestamps, untrusted marker, and the
    # clear tombstone fields only - no secret, permission, full-body,
    # audit, or governance column.
    assert _columns(control_database, "memory_entries") == {
        "entry_id": "TEXT",
        "workspace_identity": "TEXT",
        "kind": "TEXT",
        "summary": "TEXT",
        "creator": "TEXT",
        "source": "TEXT",
        "created_at": "TEXT",
        "updated_at": "TEXT",
        "untrusted": "INTEGER",
        "cleared_at": "TEXT",
        "clear_transaction_id": "TEXT",
    }
    with control_database.immediate_transaction() as tx:
        indexes = tx.execute("PRAGMA index_list(memory_entries)").fetchall()
    index_names = {str(row[1]) for row in indexes}
    assert "ix_memory_entries_workspace" in index_names


def test_memory_schema_check_constraints_reject_invalid_rows(
    control_database: ControlDatabase,
) -> None:
    """The exact schema closes kind/creator/untrusted values at the DDL."""
    assert (
        apply_migrations(control_database, _prefix() + (MEMORY_V1_MIGRATION,)).kind
        == "APPLIED"
    )
    with control_database.immediate_transaction() as tx:
        with pytest.raises(Exception, match="CHECK constraint failed"):
            tx.execute(
                "INSERT INTO memory_entries (entry_id, workspace_identity,"
                " kind, summary, creator, source, created_at, updated_at,"
                " untrusted, cleared_at, clear_transaction_id)"
                " VALUES ('mem-1', 'workspace-a', 'MODEL_OUTPUT',"
                " 'summary', 'USER', '{}', '2026-08-06T09:00:00.000Z',"
                " '2026-08-06T09:00:00.000Z', 0, NULL, NULL)"
            )
        with pytest.raises(Exception, match="CHECK constraint failed"):
            tx.execute(
                "INSERT INTO memory_entries (entry_id, workspace_identity,"
                " kind, summary, creator, source, created_at, updated_at,"
                " untrusted, cleared_at, clear_transaction_id)"
                " VALUES ('mem-2', 'workspace-a', 'PROJECT_CONVENTION',"
                " 'summary', 'AGENT', '{}', '2026-08-06T09:00:00.000Z',"
                " '2026-08-06T09:00:00.000Z', 0, NULL, NULL)"
            )
        with pytest.raises(Exception, match="CHECK constraint failed"):
            tx.execute(
                "INSERT INTO memory_entries (entry_id, workspace_identity,"
                " kind, summary, creator, source, created_at, updated_at,"
                " untrusted, cleared_at, clear_transaction_id)"
                " VALUES ('mem-3', 'workspace-a', 'PROJECT_CONVENTION',"
                " 'summary', 'USER', '{}', '2026-08-06T09:00:00.000Z',"
                " '2026-08-06T09:00:00.000Z', 2, NULL, NULL)"
            )
        tx.execute(
            "INSERT INTO memory_entries (entry_id, workspace_identity,"
            " kind, summary, creator, source, created_at, updated_at,"
            " untrusted, cleared_at, clear_transaction_id)"
            " VALUES ('mem-4', 'workspace-a', 'PROJECT_CONVENTION',"
            " 'summary', 'USER', '{}', '2026-08-06T09:00:00.000Z',"
            " '2026-08-06T09:00:00.000Z', 1, '2026-08-06T11:00:00.000Z',"
            " 'clear-1')"
        )
        # The tombstone pair is nullable, so a non-cleared entry is legal.
        tx.execute(
            "INSERT INTO memory_entries (entry_id, workspace_identity,"
            " kind, summary, creator, source, created_at, updated_at,"
            " untrusted, cleared_at, clear_transaction_id)"
            " VALUES ('mem-5', 'workspace-b', 'RUN_SUMMARY',"
            " 'summary', 'CONTROL_PLANE', '{}', '2026-08-06T09:00:00.000Z',"
            " '2026-08-06T09:00:00.000Z', 0, NULL, NULL)"
        )

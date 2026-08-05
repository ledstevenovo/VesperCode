"""T07.3 legacy step 7.C: exact v0002 idempotency ledger schema tests.

Pins the immutable descriptor (version/name/checksum binding), the exact
``idempotency_events`` table shape (scope/event/request/result identities
with the composite primary key), strict version gating (version 2 cannot
apply before version 1), idempotent replay, and the one-row-per-identity
constraint.
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
    IDEMPOTENCY_V1_STATEMENTS,
)


@pytest.fixture
def control_database(tmp_path: Path) -> Iterator[ControlDatabase]:
    database = open_control_database(tmp_path / "idempotency.db")
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


def _columns(database: ControlDatabase, table: str) -> dict[str, str]:
    with database.immediate_transaction() as tx:
        return {
            str(row[1]): str(row[2])
            for row in tx.execute(f"PRAGMA table_info({table})").fetchall()
        }


def test_idempotency_migration_has_exact_schema(
    control_database: ControlDatabase,
) -> None:
    """Exact v0002 ledger: scope/event/request/result with composite PK."""
    # Descriptor: immutable, version 2, exact name, checksum bound to DDL.
    assert isinstance(IDEMPOTENCY_V1_MIGRATION, MigrationV1)
    assert IDEMPOTENCY_V1_MIGRATION.version == 2
    assert IDEMPOTENCY_V1_MIGRATION.name == "idempotency_v1"
    assert IDEMPOTENCY_V1_MIGRATION.checksum.value == migration_checksum(
        2,
        "idempotency_v1",
        "\n".join(IDEMPOTENCY_V1_STATEMENTS),
    )
    with pytest.raises(Exception):
        IDEMPOTENCY_V1_MIGRATION.version = 3  # type: ignore[misc]
    with pytest.raises(TypeError):
        IDEMPOTENCY_V1_STATEMENTS[0] = "CREATE TABLE tampered (id INTEGER PRIMARY KEY)"  # type: ignore[index]

    # Version 2 cannot apply before version 1 (strict engine ordering).
    assert apply_migrations(control_database, (IDEMPOTENCY_V1_MIGRATION,)).kind == (
        "VERSION_GAP"
    )
    assert _table_names(control_database) == set()

    # Applied after the v0001 prefix: exactly one more ledger table.
    assert (
        apply_migrations(
            control_database,
            (RUN_WAIT_V1_MIGRATION, IDEMPOTENCY_V1_MIGRATION),
        ).kind
        == "APPLIED"
    )
    assert _table_names(control_database) == {
        "schema_migrations",
        "runs",
        "run_config_snapshots",
        "wait_contexts",
        "idempotency_events",
    }
    assert (
        apply_migrations(
            control_database,
            (RUN_WAIT_V1_MIGRATION, IDEMPOTENCY_V1_MIGRATION),
        ).kind
        == "NOOP"
    )

    # Exact columns: scope/event/request/result identities only, composite
    # primary key over (scope, event_id), no body or timestamp columns.
    assert _columns(control_database, "idempotency_events") == {
        "scope": "TEXT",
        "event_id": "TEXT",
        "request_digest": "TEXT",
        "result_digest": "TEXT",
    }
    with control_database.immediate_transaction() as tx:
        primary_key = tx.execute("PRAGMA table_info(idempotency_events)").fetchall()
    assert [int(row[5]) for row in primary_key if int(row[5])] == [1, 2]

    # One row per (scope, event_id): a duplicate identity is rejected.
    with control_database.immediate_transaction() as tx:
        tx.execute(
            "INSERT INTO idempotency_events (scope, event_id, request_digest,"
            " result_digest) VALUES ('wait', 'evt-1', ?, ?)",
            ("a" * 64, "b" * 64),
        )
        with pytest.raises(Exception, match="UNIQUE constraint failed"):
            tx.execute(
                "INSERT INTO idempotency_events (scope, event_id, request_digest,"
                " result_digest) VALUES ('wait', 'evt-1', ?, ?)",
                ("c" * 64, "d" * 64),
            )
        # The same event id under a different scope is a different identity.
        tx.execute(
            "INSERT INTO idempotency_events (scope, event_id, request_digest,"
            " result_digest) VALUES ('other', 'evt-1', ?, ?)",
            ("c" * 64, "d" * 64),
        )

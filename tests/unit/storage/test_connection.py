"""T07.1 legacy step 7.A: explicit control-database connection policy tests.

Pins the explicit transaction identity (BEGIN IMMEDIATE / COMMIT /
ROLLBACK), the ``schema_migrations`` bootstrap, foreign-key enforcement,
the trace-callback seam, and the checksum-history replacement seam.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest

# The connection consumes pydantic runtime contracts (DigestV1); the
# hash-locked gate toolchain installs no runtime dependencies, so this
# module skips cleanly there (formal env runs it fully).
pytest.importorskip("pydantic")

from src.vespercode.storage.connection import (
    ControlDatabase,
    ControlDatabaseErrorV1,
    ControlTransactionErrorV1,
    open_control_database,
)
from src.vespercode.storage.migration_engine import apply_migrations


@pytest.fixture
def control_database(tmp_path: Path) -> Iterator[ControlDatabase]:
    database = open_control_database(tmp_path / "control.db")
    yield database
    database.close()


def test_first_apply_bootstraps_migration_history(
    control_database: ControlDatabase,
) -> None:
    """The engine bootstraps the history table inside its batch transaction."""
    assert apply_migrations(control_database, ()).kind == "NOOP"
    assert control_database.recorded_migrations() == ()


def test_immediate_transaction_commits_on_success(
    control_database: ControlDatabase,
) -> None:
    with control_database.immediate_transaction() as tx:
        tx.execute("CREATE TABLE committed_entities (id INTEGER PRIMARY KEY)")
        tx.execute(
            "INSERT INTO committed_entities (id) VALUES (?)",
            (7,),
        )
    with control_database.immediate_transaction() as tx:
        assert tx.execute("SELECT id FROM committed_entities").fetchall() == [(7,)]


def test_nested_immediate_transaction_fails_closed(
    control_database: ControlDatabase,
) -> None:
    with control_database.immediate_transaction() as outer:
        with pytest.raises(ControlTransactionErrorV1):
            with control_database.immediate_transaction():
                pass
        outer.execute("CREATE TABLE outer_entities (id INTEGER PRIMARY KEY)")


def test_open_control_database_rejects_non_path() -> None:
    with pytest.raises(ControlDatabaseErrorV1, match="must be a Path"):
        open_control_database("control.db")  # type: ignore[arg-type]


def test_immediate_transaction_rolls_back_on_exception(
    control_database: ControlDatabase,
) -> None:
    with pytest.raises(RuntimeError, match="synthetic"):
        with control_database.immediate_transaction() as tx:
            tx.execute("CREATE TABLE rolled_back_entities (id INTEGER PRIMARY KEY)")
            raise RuntimeError("synthetic failure")
    with control_database.immediate_transaction() as tx:
        assert (
            tx.execute(
                "SELECT name FROM sqlite_schema WHERE type = 'table'"
                " AND name = 'rolled_back_entities'"
            ).fetchall()
            == []
        )


def test_uncommitted_write_is_invisible_to_second_connection(
    tmp_path: Path,
) -> None:
    writer = open_control_database(tmp_path / "shared.db")
    reader = open_control_database(tmp_path / "shared.db")
    try:
        with writer.immediate_transaction() as tx:
            tx.execute("CREATE TABLE shared_entities (id INTEGER PRIMARY KEY)")
            tx.execute("INSERT INTO shared_entities (id) VALUES (?)", (1,))
            # A plain autocommit read (no BEGIN IMMEDIATE, so it never
            # blocks on the writer's reserved lock) sees the pre-write
            # snapshot until the writer commits.
            assert (
                reader.read_rows(
                    "SELECT name FROM sqlite_schema WHERE type = 'table'"
                    " AND name = 'shared_entities'"
                )
                == []
            )
        assert reader.read_rows("SELECT id FROM shared_entities") == [(1,)]
    finally:
        writer.close()
        reader.close()


def test_foreign_keys_are_enforced(control_database: ControlDatabase) -> None:
    with control_database.immediate_transaction() as tx:
        tx.execute("CREATE TABLE parents (id INTEGER PRIMARY KEY)")
        tx.execute(
            "CREATE TABLE children (id INTEGER PRIMARY KEY,"
            " parent_id INTEGER NOT NULL REFERENCES parents(id))"
        )
        tx.execute("INSERT INTO parents (id) VALUES (?)", (1,))
        tx.execute(
            "INSERT INTO children (id, parent_id) VALUES (?, ?)",
            (1, 1),
        )
        with pytest.raises(Exception, match="FOREIGN KEY constraint failed"):
            tx.execute(
                "INSERT INTO children (id, parent_id) VALUES (?, ?)",
                (2, 99),
            )


def test_replace_recorded_migration_checksum_updates_history(
    control_database: ControlDatabase,
) -> None:
    apply_migrations(control_database, ())  # bootstrap the history table
    with control_database.immediate_transaction() as tx:
        tx.execute(
            "INSERT INTO schema_migrations (version, name, checksum, applied_at)"
            " VALUES (1, 'probe', ?, ?)",
            ("a" * 64, "2026-08-05T09:30:15.123Z"),
        )
    control_database.replace_recorded_migration_checksum(
        version=1,
        checksum="0" * 64,
    )
    assert control_database.recorded_migrations() == ((1, "probe", "0" * 64),)
    with pytest.raises(ValueError, match="not recorded"):
        control_database.replace_recorded_migration_checksum(
            version=2,
            checksum="0" * 64,
        )


def test_set_trace_callback_collects_statements(
    control_database: ControlDatabase,
) -> None:
    statements: list[str] = []
    control_database.set_trace_callback(statements.append)
    with control_database.immediate_transaction() as tx:
        tx.execute("CREATE TABLE traced_entities (id INTEGER PRIMARY KEY)")
    assert any("traced_entities" in statement for statement in statements)

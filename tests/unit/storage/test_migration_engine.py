"""T07.1 legacy step 7.A: domain-independent SQLite migration engine tests.

The exact RED test pins the applied-checksum drift fail-closed contract;
the matrix pins first-apply recording, replay no-op, drift rejection, and
whole-batch rollback against the PLAN Registry row for 7.A.  Synthetic
migrations carry no application-domain schema (GREEN-4).
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest

# The engine consumes pydantic runtime contracts (DigestV1, result models);
# the hash-locked gate toolchain installs no runtime dependencies, so this
# module skips cleanly there (formal env runs it fully).
pytest.importorskip("pydantic")

from vespercode.canonical.timestamp_v1 import CanonicalTimestampV1
from vespercode.contracts.evidence import DigestV1
from vespercode.storage.connection import (
    ControlDatabase,
    ControlTransactionV1,
    open_control_database,
)
from vespercode.storage.migration_engine import (
    MigrationV1,
    apply_migrations,
    migration_checksum,
)


@pytest.fixture
def control_database(tmp_path: Path) -> Iterator[ControlDatabase]:
    database = open_control_database(tmp_path / "control.db")
    yield database
    database.close()


@pytest.fixture
def synthetic_migrations() -> tuple[MigrationV1, ...]:
    """Two closed synthetic migrations with application-free DDL fixtures.

    The apply callables use plain ``CREATE TABLE`` without ``IF NOT EXISTS``,
    so an accidental replay re-execution fails loudly instead of silently
    passing (replay must be a true no-op).
    """

    def _apply_synthetic_v1(tx: ControlTransactionV1) -> None:
        tx.execute("CREATE TABLE synthetic_v1_entities (id INTEGER PRIMARY KEY)")

    def _apply_synthetic_v2(tx: ControlTransactionV1) -> None:
        tx.execute("CREATE TABLE synthetic_v2_entities (id INTEGER PRIMARY KEY)")

    return (
        MigrationV1(
            version=1,
            name="synthetic_v1",
            checksum=DigestV1(value="1" * 64),
            apply=_apply_synthetic_v1,
        ),
        MigrationV1(
            version=2,
            name="synthetic_v2",
            checksum=DigestV1(value="2" * 64),
            apply=_apply_synthetic_v2,
        ),
    )


def test_migration_checksum_is_deterministic_and_binding() -> None:
    """The checksum binds version/name/DDL deterministically (SPEC 0.1)."""
    ddl = "CREATE TABLE probe (id INTEGER PRIMARY KEY)"
    assert migration_checksum(1, "probe_v1", ddl) == migration_checksum(
        1, "probe_v1", ddl
    )
    assert migration_checksum(1, "probe_v1", ddl) != migration_checksum(
        2, "probe_v1", ddl
    )
    assert migration_checksum(1, "probe_v1", ddl) != migration_checksum(
        1, "probe_v2", ddl
    )
    assert migration_checksum(1, "probe_v1", ddl) != migration_checksum(
        1, "probe_v1", ddl + " -- changed"
    )
    for bad_version in (0, -1, True):
        with pytest.raises(ValueError, match="positive integer"):
            migration_checksum(bad_version, "probe_v1", ddl)
    with pytest.raises(ValueError, match="non-empty"):
        migration_checksum(1, "", ddl)


def test_changed_applied_migration_checksum_fails_closed(
    control_database: ControlDatabase,
    synthetic_migrations: tuple[MigrationV1, ...],
) -> None:
    apply_migrations(control_database, synthetic_migrations)
    control_database.replace_recorded_migration_checksum(version=1, checksum="0" * 64)
    result = apply_migrations(control_database, synthetic_migrations)
    assert result.kind == "MIGRATION_CHECKSUM_MISMATCH"


def _recorded_migrations(
    database: ControlDatabase,
) -> list[tuple[int, str, str]]:
    with database.immediate_transaction() as tx:
        return [
            (int(row[0]), str(row[1]), str(row[2]))
            for row in tx.execute(
                "SELECT version, name, checksum FROM schema_migrations ORDER BY version"
            ).fetchall()
        ]


def _table_names(database: ControlDatabase) -> set[str]:
    with database.immediate_transaction() as tx:
        return {
            str(row[0])
            for row in tx.execute(
                "SELECT name FROM sqlite_schema"
                " WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
            ).fetchall()
        }


def test_migration_replay_rollback_matrix(
    tmp_path: Path,
    synthetic_migrations: tuple[MigrationV1, ...],
) -> None:
    """PLAN Registry row 7.A.

    First application records version/checksum once; exact replay is a
    no-op; applied-checksum drift fails closed; a migration exception
    rolls back schema and history together; duplicate and gap descriptors
    fail closed before any mutation.
    """
    migrations = synthetic_migrations
    expected_rows = [
        (1, "synthetic_v1", "1" * 64),
        (2, "synthetic_v2", "2" * 64),
    ]

    # First application records version/checksum exactly once.
    database = open_control_database(tmp_path / "matrix.db")
    try:
        first = apply_migrations(database, migrations)
        assert first.kind == "APPLIED"
        assert _recorded_migrations(database) == expected_rows
        assert _table_names(database) == {
            "schema_migrations",
            "synthetic_v1_entities",
            "synthetic_v2_entities",
        }
        # The history ledger records an applied_at canonical timestamp.
        with database.immediate_transaction() as tx:
            applied_at = str(
                tx.execute(
                    "SELECT applied_at FROM schema_migrations WHERE version = 1"
                ).fetchone()[0]
            )
        CanonicalTimestampV1.parse(applied_at)

        # Exact replay is a no-op: same rows, no re-execution (a re-run of
        # the plain CREATE TABLE apply would fail instead of passing).
        replayed = apply_migrations(database, migrations)
        assert replayed.kind == "NOOP"
        assert _recorded_migrations(database) == expected_rows
        assert _table_names(database) == {
            "schema_migrations",
            "synthetic_v1_entities",
            "synthetic_v2_entities",
        }

        # Applied-checksum drift fails closed with no history change.
        database.replace_recorded_migration_checksum(version=2, checksum="0" * 64)
        drifted = apply_migrations(database, migrations)
        assert drifted.kind == "MIGRATION_CHECKSUM_MISMATCH"
        assert _recorded_migrations(database) == [
            (1, "synthetic_v1", "1" * 64),
            (2, "synthetic_v2", "0" * 64),
        ]
        database.replace_recorded_migration_checksum(version=2, checksum="2" * 64)

        # A migration exception rolls back schema and history together.
        def _exploding_apply(tx: ControlTransactionV1) -> None:
            tx.execute("CREATE TABLE synthetic_v3_entities (id INTEGER PRIMARY KEY)")
            raise RuntimeError("synthetic failure")

        failing = (
            *migrations,
            MigrationV1(
                version=3,
                name="synthetic_v3",
                checksum=DigestV1(value="3" * 64),
                apply=_exploding_apply,
            ),
        )
        failed = apply_migrations(database, failing)
        assert failed.kind == "MIGRATION_FAILED"
        assert _recorded_migrations(database) == expected_rows
        assert "synthetic_v3_entities" not in _table_names(database)
    finally:
        database.close()

    # Duplicate and gap descriptors fail closed before any mutation: the
    # rejection happens before the batch transaction, so not even the
    # history table bootstrap runs.
    duplicate_database = open_control_database(tmp_path / "duplicate.db")
    try:
        duplicates = (migrations[0], migrations[0])
        assert apply_migrations(duplicate_database, duplicates).kind == (
            "DUPLICATE_VERSION"
        )
        assert _table_names(duplicate_database) == set()
    finally:
        duplicate_database.close()

    gap_database = open_control_database(tmp_path / "gap.db")
    try:
        gapped = (migrations[1],)
        assert apply_migrations(gap_database, gapped).kind == "VERSION_GAP"
        assert _table_names(gap_database) == set()
    finally:
        gap_database.close()

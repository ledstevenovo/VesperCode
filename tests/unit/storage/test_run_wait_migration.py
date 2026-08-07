"""T07.2 legacy step 7.B: exact v0001 Run/config/wait schema tests.

Pins the immutable descriptor (version/name/checksum binding), the exact
tables/columns/FKs of the PLAN storage registry rows for Run,
RunConfigSnapshot, and WaitContext, the one-active-wait-per-Run index,
and idempotent replay.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest

# The migration consumes pydantic runtime contracts; the hash-locked gate
# toolchain installs no runtime dependencies, so this module skips cleanly
# there (formal env runs it fully).
pytest.importorskip("pydantic")

from vespercode.storage.connection import (
    ControlDatabase,
    open_control_database,
)
from vespercode.storage.migration_engine import (
    MigrationV1,
    apply_migrations,
    migration_checksum,
)
from vespercode.storage.migrations.v0001_run_wait import (
    RUN_WAIT_V1_MIGRATION,
    RUN_WAIT_V1_STATEMENTS,
)


@pytest.fixture
def control_database(tmp_path: Path) -> Iterator[ControlDatabase]:
    database = open_control_database(tmp_path / "run_wait.db")
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


def test_run_wait_migration_has_exact_schema(
    control_database: ControlDatabase,
) -> None:
    """PLAN Registry rows 424/429/431: exact v0001 Run/config/wait schema."""
    # Descriptor: immutable, version 1, exact name, checksum bound to DDL.
    assert isinstance(RUN_WAIT_V1_MIGRATION, MigrationV1)
    assert RUN_WAIT_V1_MIGRATION.version == 1
    assert RUN_WAIT_V1_MIGRATION.name == "run_wait_v1"
    assert RUN_WAIT_V1_MIGRATION.checksum.value == migration_checksum(
        1,
        "run_wait_v1",
        "\n".join(RUN_WAIT_V1_STATEMENTS),
    )
    with pytest.raises(Exception):
        RUN_WAIT_V1_MIGRATION.version = 2  # type: ignore[misc]
    with pytest.raises(TypeError):
        RUN_WAIT_V1_STATEMENTS[0] = "CREATE TABLE tampered (id INTEGER PRIMARY KEY)"  # type: ignore[index]

    assert apply_migrations(control_database, (RUN_WAIT_V1_MIGRATION,)).kind == (
        "APPLIED"
    )
    assert _table_names(control_database) == {
        "schema_migrations",
        "runs",
        "run_config_snapshots",
        "wait_contexts",
    }
    assert apply_migrations(control_database, (RUN_WAIT_V1_MIGRATION,)).kind == "NOOP"

    # Run (Registry row 424): PK run_id, immutable config FK, lifecycle
    # revision compare-and-update fields, deadline/status/phase, no bodies.
    assert _columns(control_database, "runs") == {
        "run_id": "TEXT",
        "workspace_identity": "TEXT",
        "config_snapshot_id": "TEXT",
        "status": "TEXT",
        "phase": "TEXT",
        "revision": "INTEGER",
        "started_at": "TEXT",
        "run_deadline": "TEXT",
    }
    with control_database.immediate_transaction() as tx:
        fks = tx.execute("PRAGMA foreign_key_list(runs)").fetchall()
    assert {str(row[3]): str(row[2]) for row in fks} == {
        "config_snapshot_id": "run_config_snapshots"
    }

    # RunConfigSnapshot (Registry row 429): PK, unique canonical digest,
    # frozen profile/policy/target/limit identities, no credential value.
    assert _columns(control_database, "run_config_snapshots") == {
        "config_snapshot_id": "TEXT",
        "digest": "TEXT",
        "llm_profile_id": "TEXT",
        "reference_profile_id": "TEXT",
        "policy_id": "TEXT",
        "target_test_ids": "TEXT",
        "limits_digest": "TEXT",
        "frozen_at": "TEXT",
    }
    with control_database.immediate_transaction() as tx:
        unique_indexes = {
            str(row[1])
            for row in tx.execute("PRAGMA index_list(run_config_snapshots)").fetchall()
            if int(row[2])
        }
    assert "sqlite_autoindex_run_config_snapshots_1" in unique_indexes
    assert "sqlite_autoindex_run_config_snapshots_2" in unique_indexes

    # WaitContext (Registry row 431): PK wait_id, FK run_id -> runs, exact
    # kind/subject/expiry/decision binding, one active wait per Run.
    assert _columns(control_database, "wait_contexts") == {
        "wait_id": "TEXT",
        "run_id": "TEXT",
        "wait_kind": "TEXT",
        "source_phase": "TEXT",
        "subject_digest": "TEXT",
        "created_at": "TEXT",
        "expires_at": "TEXT",
        "status": "TEXT",
        "decision": "TEXT",
        "decided_at": "TEXT",
    }
    with control_database.immediate_transaction() as tx:
        wait_fks = tx.execute("PRAGMA foreign_key_list(wait_contexts)").fetchall()
        indexes = tx.execute("PRAGMA index_list(wait_contexts)").fetchall()
    assert {str(row[3]): str(row[2]) for row in wait_fks} == {"run_id": "runs"}
    assert any(
        str(row[1]) == "ux_wait_contexts_one_active_wait_per_run" for row in indexes
    )


def test_run_wait_schema_check_constraints_reject_invalid_rows(
    control_database: ControlDatabase,
) -> None:
    """The exact schema closes status/phase/wait/decision values at the DDL.

    The CHECK constraints are part of the exact v0001 schema: unknown
    statuses/phases/wait kinds/decisions and the RUNNING-phase coupling
    are rejected before any repository code can see them.
    """
    assert apply_migrations(control_database, (RUN_WAIT_V1_MIGRATION,)).kind == (
        "APPLIED"
    )
    with control_database.immediate_transaction() as tx:
        tx.execute(
            "INSERT INTO run_config_snapshots"
            " (config_snapshot_id, digest, llm_profile_id, reference_profile_id,"
            " policy_id, target_test_ids, limits_digest, frozen_at)"
            " VALUES ('snap-checks', ?, 'mock-deterministic-v1',"
            " 'python-src-py312-v1', 'PYTHON_SRC_ONLY_V1', '[]', ?,"
            " '2026-08-05T09:00:00.000Z')",
            ("b" * 64, "c" * 64),
        )
        with pytest.raises(Exception, match="CHECK constraint failed"):
            tx.execute(
                "INSERT INTO runs (run_id, workspace_identity,"
                " config_snapshot_id, status, phase, revision, started_at,"
                " run_deadline) VALUES ('run-bad-status', 'ws', 'snap-checks',"
                " 'PAUSED', NULL, 1, '2026-08-05T09:00:00.000Z',"
                " '2026-08-05T09:15:00.000Z')"
            )
        with pytest.raises(Exception, match="CHECK constraint failed"):
            tx.execute(
                "INSERT INTO runs (run_id, workspace_identity,"
                " config_snapshot_id, status, phase, revision, started_at,"
                " run_deadline) VALUES ('run-bad-phase-coupling', 'ws',"
                " 'snap-checks', 'CREATED', 'PREFLIGHT', 1,"
                " '2026-08-05T09:00:00.000Z', '2026-08-05T09:15:00.000Z')"
            )
        tx.execute(
            "INSERT INTO runs (run_id, workspace_identity, config_snapshot_id,"
            " status, phase, revision, started_at, run_deadline)"
            " VALUES ('run-valid', 'ws', 'snap-checks', 'RUNNING',"
            " 'PREFLIGHT', 1, '2026-08-05T09:00:00.000Z',"
            " '2026-08-05T09:15:00.000Z')"
        )
        with pytest.raises(Exception, match="CHECK constraint failed"):
            tx.execute(
                "INSERT INTO wait_contexts (wait_id, run_id, wait_kind,"
                " source_phase, subject_digest, created_at, expires_at, status)"
                " VALUES ('wait-bad-kind', 'run-valid', 'UNKNOWN_KIND',"
                " 'AGENT_LOOP', ?, '2026-08-05T09:00:00.000Z',"
                " '2026-08-05T09:05:00.000Z', 'PENDING')",
                ("a" * 64,),
            )
        tx.execute(
            "INSERT INTO wait_contexts (wait_id, run_id, wait_kind,"
            " source_phase, subject_digest, created_at, expires_at, status)"
            " VALUES ('wait-valid', 'run-valid', 'DISCLOSURE_GRANT',"
            " 'AGENT_LOOP', ?, '2026-08-05T09:00:00.000Z',"
            " '2026-08-05T09:05:00.000Z', 'PENDING')",
            ("a" * 64,),
        )
        with pytest.raises(Exception, match="CHECK constraint failed"):
            tx.execute(
                "UPDATE wait_contexts SET decision = 'MAYBE'"
                " WHERE wait_id = 'wait-valid'"
            )

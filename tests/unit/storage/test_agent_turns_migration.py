"""T25.1 legacy step 25.B: exact v0007 active-turn schema tests.

Pins the immutable descriptor (version 7 / name ``agent_turns_v1`` /
checksum binding), the exact ``agent_turns`` table (columns, Run foreign
key, lifecycle revision, closed ACTIVE/CLOSED status with the closed
four-value outcome CHECK and the ACTIVE/CLOSED coupling, body-free
request/result references), the one-active-turn partial unique index per
Run, the exact ``run_turn_call_counters`` table (PK run_id, non-negative
monotonic counters with their own revision), strict version gating
(v0007 cannot apply before v0001-v0006), and idempotent replay.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest

# The migration consumes pydantic runtime contracts; the hash-locked
# gate toolchain installs no runtime dependencies, so this module skips
# cleanly there (formal env runs it fully).
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
    AGENT_TURNS_V1_STATEMENTS,
)

_CREATED_AT = "2026-08-06T09:00:00.000Z"


@pytest.fixture
def control_database(tmp_path: Path) -> Iterator[ControlDatabase]:
    database = open_control_database(tmp_path / "agent_turns_migration.db")
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


def _prefix() -> tuple[MigrationV1, ...]:
    return (
        RUN_WAIT_V1_MIGRATION,
        IDEMPOTENCY_V1_MIGRATION,
        DISCLOSURE_GRANTS_V1_MIGRATION,
        DISCLOSURE_AUTHORIZATIONS_V1_MIGRATION,
        MEMORY_V1_MIGRATION,
        AUDIT_V1_MIGRATION,
    )


def test_agent_turn_migration_has_exact_schema(
    control_database: ControlDatabase,
) -> None:
    """PLAN Registry row 25.B: exact v0007 active-turn schema."""
    # Descriptor: immutable, version 7, exact name, checksum bound to DDL.
    assert isinstance(AGENT_TURNS_V1_MIGRATION, MigrationV1)
    assert AGENT_TURNS_V1_MIGRATION.version == 7
    assert AGENT_TURNS_V1_MIGRATION.name == "agent_turns_v1"
    assert AGENT_TURNS_V1_MIGRATION.checksum.value == migration_checksum(
        7,
        "agent_turns_v1",
        "\n".join(AGENT_TURNS_V1_STATEMENTS),
    )
    with pytest.raises(Exception):
        AGENT_TURNS_V1_MIGRATION.version = 8  # type: ignore[misc]
    with pytest.raises(TypeError):
        AGENT_TURNS_V1_STATEMENTS[0] = (  # type: ignore[index]
            "CREATE TABLE tampered (id INTEGER PRIMARY KEY)"
        )

    # Version 7 cannot apply before the v0001-v0006 prefix.
    assert (
        apply_migrations(control_database, (AGENT_TURNS_V1_MIGRATION,)).kind
        == "VERSION_GAP"
    )
    assert _table_names(control_database) == set()

    # Applied after the prefix: exactly two more tables, idempotently.
    assert (
        apply_migrations(control_database, _prefix() + (AGENT_TURNS_V1_MIGRATION,)).kind
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
        "audit_events",
        "agent_turns",
        "run_turn_call_counters",
    }
    assert (
        apply_migrations(control_database, _prefix() + (AGENT_TURNS_V1_MIGRATION,)).kind
        == "NOOP"
    )

    # AgentTurn (Registry row 25.B): PK turn_id, Run foreign key, lifecycle
    # revision, closed ACTIVE/CLOSED status with the closed four-value
    # outcome CHECK, body-free request/result references — no body column.
    assert _columns(control_database, "agent_turns") == {
        "turn_id": "TEXT",
        "run_id": "TEXT",
        "revision": "INTEGER",
        "status": "TEXT",
        "outcome": "TEXT",
        "closed_at": "TEXT",
        "request_ref": "TEXT",
        "result_ref": "TEXT",
    }
    with control_database.immediate_transaction() as tx:
        foreign_keys = tx.execute("PRAGMA foreign_key_list(agent_turns)").fetchall()
    assert [(str(row[3]), str(row[2])) for row in foreign_keys] == [("run_id", "runs")]
    with control_database.immediate_transaction() as tx:
        indexes = tx.execute("PRAGMA index_list(agent_turns)").fetchall()
    index_names = {str(row[1]) for row in indexes}
    assert "ux_agent_turns_one_active_turn_per_run" in index_names

    # The one-active-turn constraint: a partial unique index on ACTIVE rows.
    active_index = next(
        str(row[1])
        for row in indexes
        if str(row[1]) == "ux_agent_turns_one_active_turn_per_run"
    )
    with control_database.immediate_transaction() as tx:
        active_info = tx.execute(f"PRAGMA index_info({active_index})").fetchall()
    assert [str(row[2]) for row in active_info] == ["run_id"]
    with control_database.immediate_transaction() as tx:
        partial = tx.execute(f"PRAGMA index_xinfo({active_index})").fetchall()
    # The trailing marker row (cid < 0, no name) proves the index is partial.
    assert int(partial[-1][1]) < 0
    assert partial[-1][2] is None

    # RunTurnCallCounter: PK run_id, non-negative monotonic counters with
    # their own revision, Run foreign key.
    assert _columns(control_database, "run_turn_call_counters") == {
        "run_id": "TEXT",
        "turn_count": "INTEGER",
        "call_count": "INTEGER",
        "revision": "INTEGER",
    }
    with control_database.immediate_transaction() as tx:
        counter_fks = tx.execute(
            "PRAGMA foreign_key_list(run_turn_call_counters)"
        ).fetchall()
    assert [(str(row[3]), str(row[2])) for row in counter_fks] == [("run_id", "runs")]


def test_agent_turn_schema_check_constraints_reject_invalid_rows(
    control_database: ControlDatabase,
) -> None:
    """The exact schema closes status, outcome, coupling, counts, and Run."""
    assert (
        apply_migrations(control_database, _prefix() + (AGENT_TURNS_V1_MIGRATION,)).kind
        == "APPLIED"
    )
    with control_database.immediate_transaction() as tx:
        # The Run foreign key is enforced: no run row, no turn.
        with pytest.raises(Exception, match="FOREIGN KEY constraint failed"):
            tx.execute(
                "INSERT INTO agent_turns (turn_id, run_id, revision, status,"
                " outcome, closed_at, request_ref, result_ref)"
                " VALUES ('turn-0', 'run-1', 1, 'ACTIVE', NULL, NULL, NULL, NULL)"
            )
        # Seed the run row inside this same transaction (no nested BEGIN).
        tx.execute(
            "INSERT INTO run_config_snapshots (config_snapshot_id, digest,"
            " llm_profile_id, reference_profile_id, policy_id, target_test_ids,"
            " limits_digest, frozen_at)"
            " VALUES ('cfg-1',"
            " 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',"
            " 'llm-1', 'ref-1', 'policy-1', '[]', 'limits-1', ?)",
            (_CREATED_AT,),
        )
        tx.execute(
            "INSERT INTO runs (run_id, workspace_identity, config_snapshot_id,"
            " status, phase, revision, started_at, run_deadline)"
            " VALUES ('run-1', 'workspace-a', 'cfg-1', 'RUNNING', 'AGENT_LOOP',"
            " 1, ?, ?)",
            (_CREATED_AT, "2026-08-06T10:00:00.000Z"),
        )
        # The status CHECK closes the allowlist at the DDL.
        with pytest.raises(Exception, match="CHECK constraint failed"):
            tx.execute(
                "INSERT INTO agent_turns (turn_id, run_id, revision, status,"
                " outcome, closed_at, request_ref, result_ref)"
                " VALUES ('turn-1', 'run-1', 1, 'PAUSED', NULL, NULL, NULL, NULL)"
            )
        # The outcome CHECK closes the four-value union at the DDL.
        with pytest.raises(Exception, match="CHECK constraint failed"):
            tx.execute(
                "INSERT INTO agent_turns (turn_id, run_id, revision, status,"
                " outcome, closed_at, request_ref, result_ref)"
                " VALUES ('turn-2', 'run-1', 1, 'CLOSED', 'MAYBE', ?, NULL, NULL)",
                (_CREATED_AT,),
            )
        # The ACTIVE/CLOSED coupling rejects an ACTIVE turn with an outcome.
        with pytest.raises(Exception, match="CHECK constraint failed"):
            tx.execute(
                "INSERT INTO agent_turns (turn_id, run_id, revision, status,"
                " outcome, closed_at, request_ref, result_ref)"
                " VALUES ('turn-3', 'run-1', 1, 'ACTIVE', 'SUCCEEDED', NULL,"
                " NULL, NULL)"
            )
        # The ACTIVE/CLOSED coupling rejects a CLOSED turn without an outcome.
        with pytest.raises(Exception, match="CHECK constraint failed"):
            tx.execute(
                "INSERT INTO agent_turns (turn_id, run_id, revision, status,"
                " outcome, closed_at, request_ref, result_ref)"
                " VALUES ('turn-4', 'run-1', 1, 'CLOSED', NULL, NULL, NULL, NULL)"
            )
        # A legal ACTIVE row and a legal CLOSED row for the same run coexist.
        tx.execute(
            "INSERT INTO agent_turns (turn_id, run_id, revision, status,"
            " outcome, closed_at, request_ref, result_ref)"
            " VALUES ('turn-5', 'run-1', 1, 'ACTIVE', NULL, NULL, 'req-1', NULL)"
        )
        tx.execute(
            "INSERT INTO agent_turns (turn_id, run_id, revision, status,"
            " outcome, closed_at, request_ref, result_ref)"
            " VALUES ('turn-6', 'run-1', 2, 'CLOSED', 'FAILED', ?, NULL, 'res-1')",
            (_CREATED_AT,),
        )
        # Only one ACTIVE turn per Run: the partial unique index backstops.
        with pytest.raises(Exception, match="UNIQUE constraint failed"):
            tx.execute(
                "INSERT INTO agent_turns (turn_id, run_id, revision, status,"
                " outcome, closed_at, request_ref, result_ref)"
                " VALUES ('turn-7', 'run-1', 1, 'ACTIVE', NULL, NULL, NULL, NULL)"
            )
        # The counter CHECKs reject negative counts.
        with pytest.raises(Exception, match="CHECK constraint failed"):
            tx.execute(
                "INSERT INTO run_turn_call_counters"
                " (run_id, turn_count, call_count, revision)"
                " VALUES ('run-1', -1, 0, 1)"
            )
        with pytest.raises(Exception, match="CHECK constraint failed"):
            tx.execute(
                "INSERT INTO run_turn_call_counters"
                " (run_id, turn_count, call_count, revision)"
                " VALUES ('run-1', 0, -1, 1)"
            )
        tx.execute(
            "INSERT INTO run_turn_call_counters"
            " (run_id, turn_count, call_count, revision)"
            " VALUES ('run-1', 0, 0, 1)"
        )

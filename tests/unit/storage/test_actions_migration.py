"""T25.2 legacy step 25.D: exact v0009 action-record schema tests.

Pins the immutable descriptor (version 9 / name ``actions_v1`` / checksum
binding), the exact ``action_records`` table (PK action_id, Run turn
foreign key, closed six-value action_type CHECK, exact 64-hex
instance/semantic digests, closed ALLOW/ASK/DENY policy-decision CHECK,
and the body-free result reference), strict version gating (v0009 cannot
apply before v0001-v0008), and idempotent replay.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest

# The migration consumes pydantic runtime contracts; the hash-locked
# gate toolchain installs no runtime dependencies, so this module skips
# cleanly there (formal env runs it fully).
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
from src.vespercode.storage.migrations.v0005_memory import MEMORY_V1_MIGRATION
from src.vespercode.storage.migrations.v0006_audit import AUDIT_V1_MIGRATION
from src.vespercode.storage.migrations.v0007_agent_turns import (
    AGENT_TURNS_V1_MIGRATION,
)
from src.vespercode.storage.migrations.v0008_feedback import FEEDBACK_V1_MIGRATION
from src.vespercode.storage.migrations.v0009_actions import (
    ACTIONS_V1_MIGRATION,
    ACTIONS_V1_STATEMENTS,
)

_CREATED_AT = "2026-08-06T09:00:00.000Z"

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


@pytest.fixture
def control_database(tmp_path: Path) -> Iterator[ControlDatabase]:
    database = open_control_database(tmp_path / "actions_migration.db")
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


def test_action_migration_has_exact_schema(
    control_database: ControlDatabase,
) -> None:
    """PLAN Registry row 25.D: exact v0009 body-free action-record schema."""
    # Descriptor: immutable, version 9, exact name, checksum bound to DDL.
    assert isinstance(ACTIONS_V1_MIGRATION, MigrationV1)
    assert ACTIONS_V1_MIGRATION.version == 9
    assert ACTIONS_V1_MIGRATION.name == "actions_v1"
    assert ACTIONS_V1_MIGRATION.checksum.value == migration_checksum(
        9,
        "actions_v1",
        "\n".join(ACTIONS_V1_STATEMENTS),
    )
    with pytest.raises(Exception):
        ACTIONS_V1_MIGRATION.version = 10  # type: ignore[misc]
    with pytest.raises(TypeError):
        ACTIONS_V1_STATEMENTS[0] = (  # type: ignore[index]
            "CREATE TABLE tampered (id INTEGER PRIMARY KEY)"
        )

    # Version 9 cannot apply before the v0001-v0008 prefix.
    assert (
        apply_migrations(control_database, (ACTIONS_V1_MIGRATION,)).kind
        == "VERSION_GAP"
    )
    assert _table_names(control_database) == set()

    # Applied after the prefix: exactly one more table, idempotently.
    assert (
        apply_migrations(control_database, _MIGRATIONS + (ACTIONS_V1_MIGRATION,)).kind
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
        "feedback_records",
        "action_records",
    }
    assert (
        apply_migrations(control_database, _MIGRATIONS + (ACTIONS_V1_MIGRATION,)).kind
        == "NOOP"
    )

    # ActionRecord (Registry row 25.D): PK action_id, turn foreign key,
    # closed six-value action_type, exact 64-hex digests, closed
    # ALLOW/ASK/DENY policy decision, and the body-free result reference —
    # no action body and no result body column.
    assert _columns(control_database, "action_records") == {
        "action_id": "TEXT",
        "turn_id": "TEXT",
        "action_type": "TEXT",
        "semantic_digest": "TEXT",
        "instance_digest": "TEXT",
        "policy_decision": "TEXT",
        "result_ref": "TEXT",
    }
    with control_database.immediate_transaction() as tx:
        foreign_keys = tx.execute("PRAGMA foreign_key_list(action_records)").fetchall()
    assert [(str(row[3]), str(row[2])) for row in foreign_keys] == [
        ("turn_id", "agent_turns")
    ]


def test_action_schema_check_constraints_reject_invalid_rows(
    control_database: ControlDatabase,
) -> None:
    """The exact schema closes type, decision, digests, and turn identity."""
    assert (
        apply_migrations(control_database, _MIGRATIONS + (ACTIONS_V1_MIGRATION,)).kind
        == "APPLIED"
    )
    with control_database.immediate_transaction() as tx:
        # Seed the run and an ACTIVE turn (the v0007 turn foreign key).
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
        tx.execute(
            "INSERT INTO agent_turns (turn_id, run_id, revision, status,"
            " outcome, closed_at, request_ref, result_ref)"
            " VALUES ('turn-1', 'run-1', 1, 'ACTIVE', NULL, NULL, NULL, NULL)"
        )
        # The turn foreign key is enforced: no turn row, no action record.
        with pytest.raises(Exception, match="FOREIGN KEY constraint failed"):
            tx.execute(
                "INSERT INTO action_records (action_id, turn_id, action_type,"
                " semantic_digest, instance_digest, policy_decision, result_ref)"
                " VALUES (?, 'turn-missing', 'list_files',"
                " ?, ?, 'ALLOW', NULL)",
                ("a-0", "b" * 64, "c" * 64),
            )
        # The action_type CHECK closes the six model actions at the DDL.
        with pytest.raises(Exception, match="CHECK constraint failed"):
            tx.execute(
                "INSERT INTO action_records (action_id, turn_id, action_type,"
                " semantic_digest, instance_digest, policy_decision, result_ref)"
                " VALUES (?, 'turn-1', 'execute_command',"
                " ?, ?, 'ALLOW', NULL)",
                ("a-1", "b" * 64, "c" * 64),
            )
        # The policy-decision CHECK closes the ALLOW/ASK/DENY union.
        with pytest.raises(Exception, match="CHECK constraint failed"):
            tx.execute(
                "INSERT INTO action_records (action_id, turn_id, action_type,"
                " semantic_digest, instance_digest, policy_decision, result_ref)"
                " VALUES (?, 'turn-1', 'read_file',"
                " ?, ?, 'MAYBE', NULL)",
                ("a-2", "b" * 64, "c" * 64),
            )
        # The digest CHECKs reject non-64-hex digests.
        with pytest.raises(Exception, match="CHECK constraint failed"):
            tx.execute(
                "INSERT INTO action_records (action_id, turn_id, action_type,"
                " semantic_digest, instance_digest, policy_decision, result_ref)"
                " VALUES (?, 'turn-1', 'read_file',"
                " ?, ?, 'ALLOW', NULL)",
                ("a-3", "not-a-digest", "c" * 64),
            )
        with pytest.raises(Exception, match="CHECK constraint failed"):
            tx.execute(
                "INSERT INTO action_records (action_id, turn_id, action_type,"
                " semantic_digest, instance_digest, policy_decision, result_ref)"
                " VALUES (?, 'turn-1', 'read_file',"
                " ?, ?, 'ALLOW', NULL)",
                ("a-4", "b" * 64, "not-a-digest"),
            )
        # A legal body-free row stores the result reference only.
        tx.execute(
            "INSERT INTO action_records (action_id, turn_id, action_type,"
            " semantic_digest, instance_digest, policy_decision, result_ref)"
            " VALUES (?, 'turn-1', 'apply_candidate_patch',"
            " ?, ?, 'DENY', NULL)",
            ("a-5", "b" * 64, "c" * 64),
        )
        tx.execute(
            "INSERT INTO action_records (action_id, turn_id, action_type,"
            " semantic_digest, instance_digest, policy_decision, result_ref)"
            " VALUES (?, 'turn-1', 'list_files',"
            " ?, ?, 'ALLOW', ?)",
            ("a-6", "b" * 64, "c" * 64, "artifact-1"),
        )
        # action_id is the unique action identity: duplicates reject.
        with pytest.raises(Exception, match="UNIQUE constraint failed"):
            tx.execute(
                "INSERT INTO action_records (action_id, turn_id, action_type,"
                " semantic_digest, instance_digest, policy_decision, result_ref)"
                " VALUES (?, 'turn-1', 'search_text',"
                " ?, ?, 'ALLOW', NULL)",
                ("a-6", "d" * 64, "e" * 64),
            )

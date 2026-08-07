"""T26.2 legacy step 26.C: exact v0012 recovery terminal-result schema tests.

Pins the immutable descriptor (version 12 / name ``recovery_v1`` /
checksum binding), the exact ``recovery_results`` table (columns, the FK
to the v0011 persistence transaction, the closed three-value disposition
CHECK, the non-negative write count, and the body-free column set),
strict version gating (v0012 cannot apply before the v0001–v0011
prefix), and idempotent replay.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest

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
)
from vespercode.storage.migrations.v0008_feedback import FEEDBACK_V1_MIGRATION
from vespercode.storage.migrations.v0009_actions import ACTIONS_V1_MIGRATION
from vespercode.storage.migrations.v0010_writeback_approvals import (
    WRITEBACK_APPROVALS_V1_MIGRATION,
)
from vespercode.storage.migrations.v0011_persistence import (
    PERSISTENCE_V1_MIGRATION,
)
from vespercode.storage.migrations.v0012_recovery import (
    RECOVERY_V1_MIGRATION,
    RECOVERY_V1_STATEMENTS,
)

_PREFIX_MIGRATIONS = (
    RUN_WAIT_V1_MIGRATION,
    IDEMPOTENCY_V1_MIGRATION,
    DISCLOSURE_GRANTS_V1_MIGRATION,
    DISCLOSURE_AUTHORIZATIONS_V1_MIGRATION,
    MEMORY_V1_MIGRATION,
    AUDIT_V1_MIGRATION,
    AGENT_TURNS_V1_MIGRATION,
    FEEDBACK_V1_MIGRATION,
    ACTIONS_V1_MIGRATION,
    WRITEBACK_APPROVALS_V1_MIGRATION,
    PERSISTENCE_V1_MIGRATION,
)


@pytest.fixture
def control_database(tmp_path: Path) -> Iterator[ControlDatabase]:
    database = open_control_database(tmp_path / "recovery_v0012.db")
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


def test_recovery_migration_has_exact_schema(
    control_database: ControlDatabase,
) -> None:
    """PLAN Registry row 26.C: exact v0012 terminal-result schema."""
    # Descriptor: immutable, version 12, exact name, checksum bound to DDL.
    assert isinstance(RECOVERY_V1_MIGRATION, MigrationV1)
    assert RECOVERY_V1_MIGRATION.version == 12
    assert RECOVERY_V1_MIGRATION.name == "recovery_v1"
    assert RECOVERY_V1_MIGRATION.checksum.value == migration_checksum(
        12,
        "recovery_v1",
        "\n".join(RECOVERY_V1_STATEMENTS),
    )
    with pytest.raises(Exception):
        RECOVERY_V1_MIGRATION.version = 13  # type: ignore[misc]
    with pytest.raises(TypeError):
        RECOVERY_V1_STATEMENTS[0] = (  # type: ignore[index]
            "CREATE TABLE tampered (id INTEGER PRIMARY KEY)"
        )

    # Version 12 cannot apply before the v0001–v0011 prefix.
    assert (
        apply_migrations(control_database, (RECOVERY_V1_MIGRATION,)).kind
        == "VERSION_GAP"
    )
    assert _table_names(control_database) == set()

    # Applied after the prefix: exactly the declared tables.
    assert (
        apply_migrations(
            control_database, (*_PREFIX_MIGRATIONS, RECOVERY_V1_MIGRATION)
        ).kind
        == "APPLIED"
    )
    assert _table_names(control_database) == {
        "schema_migrations",
        "runs",
        "run_config_snapshots",
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
        "writeback_approval_subjects",
        "writeback_approvals",
        "persistence_transactions",
        "persistence_path_records",
        "recovery_results",
    }
    assert (
        apply_migrations(
            control_database, (*_PREFIX_MIGRATIONS, RECOVERY_V1_MIGRATION)
        ).kind
        == "NOOP"
    )

    # recovery_results: PK transaction id with the FK to the v0011
    # transaction, the closed three-value disposition, the evidence
    # digest, the changed canonical paths, the durable write count, and
    # the applied-at timestamp — no body column.
    assert _columns(control_database, "recovery_results") == {
        "transaction_id": "TEXT",
        "disposition": "TEXT",
        "evidence_digest": "TEXT",
        "changed_paths": "TEXT",
        "workspace_write_count": "INTEGER",
        "applied_at": "TEXT",
    }
    with control_database.immediate_transaction() as tx:
        fks = tx.execute("PRAGMA foreign_key_list(recovery_results)").fetchall()
    assert {str(row[3]): str(row[2]) for row in fks} == {
        "transaction_id": "persistence_transactions"
    }


def test_recovery_schema_check_constraints_reject_invalid_rows(
    control_database: ControlDatabase,
) -> None:
    """The exact schema closes the disposition vocabulary and the write
    count at the DDL and never stores any body."""
    assert (
        apply_migrations(
            control_database, (*_PREFIX_MIGRATIONS, RECOVERY_V1_MIGRATION)
        ).kind
        == "APPLIED"
    )
    with control_database.immediate_transaction() as tx:
        tx.execute(
            "INSERT INTO run_config_snapshots (config_snapshot_id, digest,"
            " llm_profile_id, reference_profile_id, policy_id, target_test_ids,"
            " limits_digest, frozen_at) VALUES ('snap-1', ?, 'mock-deterministic-v1',"
            " 'python-src-py312-v1', 'PYTHON_SRC_ONLY_V1', '[]', ?,"
            " '2026-08-05T09:00:00.000Z')",
            ("a" * 64, "b" * 64),
        )
        tx.execute(
            "INSERT INTO runs (run_id, workspace_identity, config_snapshot_id,"
            " status, phase, revision, started_at, run_deadline)"
            " VALUES ('run-1', 'ws-1', 'snap-1', 'WAITING_USER', NULL, 1,"
            " '2026-08-05T09:00:00.000Z', '2026-08-05T09:15:00.000Z')"
        )
        tx.execute(
            "INSERT INTO wait_contexts (wait_id, run_id, wait_kind,"
            " source_phase, subject_digest, created_at, expires_at, status)"
            " VALUES ('wait-1', 'run-1', 'FINAL_WRITEBACK',"
            " 'FORMAL_VALIDATION', 'c' * 64, '2026-08-05T09:00:00.000Z',"
            " '2026-08-05T09:05:00.000Z', 'PENDING')"
        )
        tx.execute(
            "INSERT INTO writeback_approval_subjects (subject_digest, run_id,"
            " candidate_digest, final_diff_digest, validation_manifest_digest,"
            " formal_evidence_digest, workspace_preimage_digest, run_config_digest,"
            " policy_digest, reference_profile_digest, action_semantic_digest,"
            " expires_at) VALUES ('c' * 64, 'run-1', 'd' * 64, 'e' * 64,"
            " 'f' * 64, '0' * 64, '1' * 64, '2' * 64, '3' * 64, '4' * 64,"
            " '5' * 64, '2026-08-05T09:05:00.000Z')"
        )
        tx.execute(
            "INSERT INTO writeback_approvals (approval_id, subject_digest,"
            " run_id, wait_id, created_at, status) VALUES"
            " ('approval-1', 'c' * 64, 'run-1', 'wait-1',"
            " '2026-08-05T09:01:00.000Z', 'PENDING')"
        )
        tx.execute(
            "INSERT INTO persistence_transactions (transaction_id, run_id,"
            " approval_id, workspace_identity_digest, workspace_path,"
            " final_diff_digest, policy_digest, state, run_deadline,"
            " prepared_at, updated_at, workspace_write_count) VALUES"
            " ('tx-1', 'run-1', 'approval-1', '55' * 64, 'C:\\\\work\\\\vesper',"
            " '66' * 64, '33' * 64, 'PREPARED', '2026-08-05T09:15:00.000Z',"
            " '2026-08-05T09:00:00.000Z', '2026-08-05T09:00:00.000Z', 0)"
        )
        valid_result = (
            "INSERT INTO recovery_results (transaction_id, disposition,"
            " evidence_digest, changed_paths, workspace_write_count, applied_at)"
            " VALUES ('tx-1', 'COMMITTED', 'aa' * 64, '[]', 0,"
            " '2026-08-05T09:02:00.000Z')"
        )
        tx.execute(valid_result)
        with pytest.raises(Exception):
            tx.execute(valid_result.replace("'COMMITTED'", "'SUCCEEDED'"))
        with pytest.raises(Exception):
            tx.execute(
                valid_result.replace("'tx-1'", "'tx-2'").replace(", 0,", ", -1,")
            )
        # One terminal result per transaction: the PK rejects a duplicate.
        with pytest.raises(Exception):
            tx.execute(valid_result)

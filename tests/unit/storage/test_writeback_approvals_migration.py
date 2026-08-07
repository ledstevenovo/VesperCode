"""T14.1 legacy step 14.B: exact v0010 writeback approval schema tests.

Pins the immutable descriptor (version 10 / name / checksum binding), the
exact ``writeback_approval_subjects`` and ``writeback_approvals`` tables
(columns, FKs, the one-approval-per-wait unique index, the closed
PENDING/REJECTED/EXPIRED/CONSUMED status CHECK), strict version gating
(v0010 cannot apply before the v0001–v0009 prefix), and idempotent replay.
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
    WRITEBACK_APPROVALS_V1_STATEMENTS,
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
)


@pytest.fixture
def control_database(tmp_path: Path) -> Iterator[ControlDatabase]:
    database = open_control_database(tmp_path / "writeback_approvals.db")
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


def test_writeback_approval_migration_has_exact_schema(
    control_database: ControlDatabase,
) -> None:
    """PLAN Registry row 14.B: exact v0010 subject/approval schema."""
    # Descriptor: immutable, version 10, exact name, checksum bound to DDL.
    assert isinstance(WRITEBACK_APPROVALS_V1_MIGRATION, MigrationV1)
    assert WRITEBACK_APPROVALS_V1_MIGRATION.version == 10
    assert WRITEBACK_APPROVALS_V1_MIGRATION.name == "writeback_approvals_v1"
    assert WRITEBACK_APPROVALS_V1_MIGRATION.checksum.value == migration_checksum(
        10,
        "writeback_approvals_v1",
        "\n".join(WRITEBACK_APPROVALS_V1_STATEMENTS),
    )
    with pytest.raises(Exception):
        WRITEBACK_APPROVALS_V1_MIGRATION.version = 11  # type: ignore[misc]
    with pytest.raises(TypeError):
        WRITEBACK_APPROVALS_V1_STATEMENTS[0] = (  # type: ignore[index]
            "CREATE TABLE tampered (id INTEGER PRIMARY KEY)"
        )

    # Version 10 cannot apply before the v0001–v0009 prefix.
    assert (
        apply_migrations(control_database, (WRITEBACK_APPROVALS_V1_MIGRATION,)).kind
        == "VERSION_GAP"
    )
    assert _table_names(control_database) == set()

    # Applied after the prefix: exactly the declared tables.
    assert (
        apply_migrations(
            control_database, (*_PREFIX_MIGRATIONS, WRITEBACK_APPROVALS_V1_MIGRATION)
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
    }
    assert (
        apply_migrations(
            control_database, (*_PREFIX_MIGRATIONS, WRITEBACK_APPROVALS_V1_MIGRATION)
        ).kind
        == "NOOP"
    )

    # writeback_approval_subjects: PK/unique subject digest, immutable
    # bound facts, no mutable status and no candidate body.
    assert _columns(control_database, "writeback_approval_subjects") == {
        "subject_digest": "TEXT",
        "run_id": "TEXT",
        "candidate_digest": "TEXT",
        "final_diff_digest": "TEXT",
        "validation_manifest_digest": "TEXT",
        "formal_evidence_digest": "TEXT",
        "workspace_preimage_digest": "TEXT",
        "run_config_digest": "TEXT",
        "policy_digest": "TEXT",
        "reference_profile_digest": "TEXT",
        "action_semantic_digest": "TEXT",
        "expires_at": "TEXT",
    }
    with control_database.immediate_transaction() as tx:
        subject_fks = tx.execute(
            "PRAGMA foreign_key_list(writeback_approval_subjects)"
        ).fetchall()
    assert {str(row[3]): str(row[2]) for row in subject_fks} == {"run_id": "runs"}

    # writeback_approvals: PK approval_id, FK subject digest / run / wait,
    # created_at, and the closed PENDING/REJECTED/EXPIRED/CONSUMED status.
    assert _columns(control_database, "writeback_approvals") == {
        "approval_id": "TEXT",
        "subject_digest": "TEXT",
        "run_id": "TEXT",
        "wait_id": "TEXT",
        "created_at": "TEXT",
        "status": "TEXT",
    }
    with control_database.immediate_transaction() as tx:
        approval_fks = tx.execute(
            "PRAGMA foreign_key_list(writeback_approvals)"
        ).fetchall()
        indexes = tx.execute("PRAGMA index_list(writeback_approvals)").fetchall()
    assert {str(row[3]): str(row[2]) for row in approval_fks} == {
        "subject_digest": "writeback_approval_subjects",
        "run_id": "runs",
        "wait_id": "wait_contexts",
    }
    index_names = {str(row[1]) for row in indexes}
    assert "ux_writeback_approvals_one_per_wait" in index_names


def test_writeback_approval_schema_check_constraints_reject_invalid_rows(
    control_database: ControlDatabase,
) -> None:
    """The exact schema closes approval status values at the DDL."""
    assert (
        apply_migrations(
            control_database, (*_PREFIX_MIGRATIONS, WRITEBACK_APPROVALS_V1_MIGRATION)
        ).kind
        == "APPLIED"
    )
    with control_database.immediate_transaction() as tx:
        tx.execute(
            "INSERT INTO run_config_snapshots"
            " (config_snapshot_id, digest, llm_profile_id, reference_profile_id,"
            " policy_id, target_test_ids, limits_digest, frozen_at)"
            " VALUES ('snap-1', ?, 'mock-deterministic-v1', 'python-src-py312-v1',"
            " 'PYTHON_SRC_ONLY_V1', '[]', ?, '2026-08-05T09:00:00.000Z')",
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
        for extra_wait, extra_run in (
            ("wait-2", "run-2"),
            ("wait-3", "run-3"),
            ("wait-4", "run-4"),
        ):
            tx.execute(
                "INSERT INTO runs (run_id, workspace_identity, config_snapshot_id,"
                " status, phase, revision, started_at, run_deadline)"
                " VALUES (?, 'ws-1', 'snap-1', 'WAITING_USER', NULL, 1,"
                " '2026-08-05T09:00:00.000Z', '2026-08-05T09:15:00.000Z')",
                (extra_run,),
            )
            tx.execute(
                "INSERT INTO wait_contexts (wait_id, run_id, wait_kind,"
                " source_phase, subject_digest, created_at, expires_at, status)"
                " VALUES (?, ?, 'FINAL_WRITEBACK',"
                " 'FORMAL_VALIDATION', 'c' * 64, '2026-08-05T09:00:00.000Z',"
                " '2026-08-05T09:05:00.000Z', 'PENDING')",
                (extra_wait, extra_run),
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
    # The four legal statuses persist (one approval per wait).
    with control_database.immediate_transaction() as tx:
        for approval_id, wait_id, status in (
            ("approval-pending", "wait-1", "PENDING"),
            ("approval-rejected", "wait-2", "REJECTED"),
            ("approval-expired", "wait-3", "EXPIRED"),
            ("approval-consumed", "wait-4", "CONSUMED"),
        ):
            tx.execute(
                "INSERT INTO writeback_approvals (approval_id, subject_digest,"
                " run_id, wait_id, created_at, status) VALUES"
                " (?, 'c' * 64, 'run-1', ?, '2026-08-05T09:01:00.000Z', ?)",
                (approval_id, wait_id, status),
            )
        with pytest.raises(Exception):
            tx.execute(
                "INSERT INTO writeback_approvals (approval_id, subject_digest,"
                " run_id, wait_id, created_at, status) VALUES"
                " ('approval-bad', 'c' * 64, 'run-1', 'wait-1',"
                " '2026-08-05T09:01:00.000Z', 'GRANTED')"
            )
    # One approval per wait: a second approval for the same wait fails
    # closed at the DDL.
    with control_database.immediate_transaction() as tx:
        with pytest.raises(Exception):
            tx.execute(
                "INSERT INTO writeback_approvals (approval_id, subject_digest,"
                " run_id, wait_id, created_at, status) VALUES"
                " ('approval-second', 'c' * 64, 'run-1', 'wait-1',"
                " '2026-08-05T09:01:00.000Z', 'PENDING')"
            )

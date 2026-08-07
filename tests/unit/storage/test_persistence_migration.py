"""T26.1 legacy step 26.A: exact v0011 persistence schema tests.

Pins the immutable descriptor (version 11 / name ``persistence_v1`` /
checksum binding), the exact ``persistence_transactions`` and
``persistence_path_records`` tables (columns, FKs, the one-active-
workspace partial unique index, the ordered-sequence unique index, the
closed state/operation/durable-state CHECKs, and the body-free column
set), strict version gating (v0011 cannot apply before the
v0001–v0010 prefix), and idempotent replay.
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
)
from vespercode.storage.migrations.v0011_persistence import (
    PERSISTENCE_V1_MIGRATION,
    PERSISTENCE_V1_STATEMENTS,
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
)


@pytest.fixture
def control_database(tmp_path: Path) -> Iterator[ControlDatabase]:
    database = open_control_database(tmp_path / "persistence_v0011.db")
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


def _indexes(database: ControlDatabase, table: str) -> set[str]:
    with database.immediate_transaction() as tx:
        return {
            str(row[1])
            for row in tx.execute(f"PRAGMA index_list({table})")
            if not str(row[1]).startswith("sqlite_autoindex")
        }


def test_persistence_migration_has_exact_schema(
    control_database: ControlDatabase,
) -> None:
    """PLAN Registry row 26.A: exact v0011 transaction/path schema."""
    # Descriptor: immutable, version 11, exact name, checksum bound to DDL.
    assert isinstance(PERSISTENCE_V1_MIGRATION, MigrationV1)
    assert PERSISTENCE_V1_MIGRATION.version == 11
    assert PERSISTENCE_V1_MIGRATION.name == "persistence_v1"
    assert PERSISTENCE_V1_MIGRATION.checksum.value == migration_checksum(
        11,
        "persistence_v1",
        "\n".join(PERSISTENCE_V1_STATEMENTS),
    )
    with pytest.raises(Exception):
        PERSISTENCE_V1_MIGRATION.version = 12  # type: ignore[misc]
    with pytest.raises(TypeError):
        PERSISTENCE_V1_STATEMENTS[0] = (  # type: ignore[index]
            "CREATE TABLE tampered (id INTEGER PRIMARY KEY)"
        )

    # Version 11 cannot apply before the v0001–v0010 prefix.
    assert (
        apply_migrations(control_database, (PERSISTENCE_V1_MIGRATION,)).kind
        == "VERSION_GAP"
    )
    assert _table_names(control_database) == set()

    # Applied after the prefix: exactly the declared tables.
    assert (
        apply_migrations(
            control_database, (*_PREFIX_MIGRATIONS, PERSISTENCE_V1_MIGRATION)
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
    }
    assert (
        apply_migrations(
            control_database, (*_PREFIX_MIGRATIONS, PERSISTENCE_V1_MIGRATION)
        ).kind
        == "NOOP"
    )

    # persistence_transactions: PK transaction id, Run/approval FKs,
    # workspace identity + canonical path, final-diff/policy digests, the
    # closed five-state vocabulary, the run deadline, and the durable
    # write count — no body column.
    assert _columns(control_database, "persistence_transactions") == {
        "transaction_id": "TEXT",
        "run_id": "TEXT",
        "approval_id": "TEXT",
        "workspace_identity_digest": "TEXT",
        "workspace_path": "TEXT",
        "final_diff_digest": "TEXT",
        "policy_digest": "TEXT",
        "state": "TEXT",
        "run_deadline": "TEXT",
        "prepared_at": "TEXT",
        "updated_at": "TEXT",
        "workspace_write_count": "INTEGER",
    }
    with control_database.immediate_transaction() as tx:
        transaction_fks = tx.execute(
            "PRAGMA foreign_key_list(persistence_transactions)"
        ).fetchall()
    assert {str(row[3]): str(row[2]) for row in transaction_fks} == {
        "run_id": "runs",
        "approval_id": "writeback_approvals",
    }

    # persistence_path_records: PK (transaction, path), closed operation,
    # typed ABSENT/PRESENT preimage evidence, body-free postimage binding,
    # ordered 1-based sequence, closed durable state, backup artifact
    # reference and last evidence digest — no body column.
    assert _columns(control_database, "persistence_path_records") == {
        "transaction_id": "TEXT",
        "path": "TEXT",
        "operation": "TEXT",
        "sequence": "INTEGER",
        "preimage_kind": "TEXT",
        "preimage_raw_bytes_digest": "TEXT",
        "preimage_text_encoding": "TEXT",
        "preimage_text_newline": "TEXT",
        "preimage_object_identity_digest": "TEXT",
        "postimage_raw_bytes_digest": "TEXT",
        "postimage_text_encoding": "TEXT",
        "postimage_text_newline": "TEXT",
        "postimage_required_object_policy_digest": "TEXT",
        "durable_state": "TEXT",
        "backup_ref": "TEXT",
        "backup_digest": "TEXT",
        "last_evidence_digest": "TEXT",
    }
    with control_database.immediate_transaction() as tx:
        record_fks = tx.execute(
            "PRAGMA foreign_key_list(persistence_path_records)"
        ).fetchall()
    assert {str(row[3]): str(row[2]) for row in record_fks} == {
        "transaction_id": "persistence_transactions"
    }
    assert _indexes(control_database, "persistence_transactions") == {
        "ux_persistence_transactions_one_active_workspace"
    }
    assert _indexes(control_database, "persistence_path_records") == {
        "ux_persistence_path_records_ordered_sequence"
    }


def test_persistence_schema_check_constraints_reject_invalid_rows(
    control_database: ControlDatabase,
) -> None:
    """The exact schema closes state/operation/durable-state/sequence/count
    values at the DDL and never stores any body."""
    assert (
        apply_migrations(
            control_database, (*_PREFIX_MIGRATIONS, PERSISTENCE_V1_MIGRATION)
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

    valid_transaction = (
        "INSERT INTO persistence_transactions (transaction_id, run_id,"
        " approval_id, workspace_identity_digest, workspace_path,"
        " final_diff_digest, policy_digest, state, run_deadline, prepared_at,"
        " updated_at, workspace_write_count) VALUES"
        " ('tx-1', 'run-1', 'approval-1', ?, 'C:\\\\work\\\\vesper',"
        " '66' * 64, '33' * 64, 'PREPARED', '2026-08-05T09:15:00.000Z',"
        " '2026-08-05T09:00:00.000Z', '2026-08-05T09:00:00.000Z', 0)"
    )
    valid_record = (
        "INSERT INTO persistence_path_records (transaction_id, path,"
        " operation, sequence, preimage_kind, preimage_raw_bytes_digest,"
        " preimage_text_encoding, preimage_text_newline,"
        " preimage_object_identity_digest, postimage_raw_bytes_digest,"
        " postimage_text_encoding, postimage_text_newline,"
        " postimage_required_object_policy_digest, durable_state,"
        " backup_ref, backup_digest, last_evidence_digest) VALUES"
        " ('tx-1', 'src/a.py', 'CREATE', 1, 'ABSENT', 'ABSENT', 'ABSENT',"
        " 'ABSENT', 'ABSENT', '22' * 64, 'UTF8', 'LF', '33' * 64,"
        " 'NOT_STARTED', 'ABSENT', 'ABSENT', 'ABSENT')"
    )
    with control_database.immediate_transaction() as tx:
        tx.execute(valid_transaction, ("55" * 64,))
        tx.execute(valid_record)
        with pytest.raises(Exception):
            tx.execute(
                valid_transaction.replace("'PREPARED'", "'GRANTED'"),
                ("55" * 64,),
            )
        with pytest.raises(Exception):
            tx.execute(
                valid_record.replace("'CREATE'", "'DELETE'"),
            )
        with pytest.raises(Exception):
            tx.execute(
                valid_record.replace("'NOT_STARTED'", "'WRITTEN'"),
            )
        with pytest.raises(Exception):
            tx.execute(
                valid_record.replace("1, 'ABSENT'", "0, 'ABSENT'"),
            )
        with pytest.raises(Exception):
            tx.execute(
                valid_transaction.replace(", 0)", ", -1)"),
                ("55" * 64,),
            )
        # The compound preimage CHECK closes PRESENT evidence: a PRESENT
        # preimage cannot carry the ABSENT sentinel in its evidence columns.
        with pytest.raises(Exception):
            tx.execute(
                valid_record.replace("'CREATE', 1, 'ABSENT'", "'CREATE', 1, 'PRESENT'"),
            )
        # The text metadata CHECKs close the encoding/newline vocabularies.
        with pytest.raises(Exception):
            tx.execute(
                "INSERT INTO persistence_path_records (transaction_id, path,"
                " operation, sequence, preimage_kind, preimage_raw_bytes_digest,"
                " preimage_text_encoding, preimage_text_newline,"
                " preimage_object_identity_digest, postimage_raw_bytes_digest,"
                " postimage_text_encoding, postimage_text_newline,"
                " postimage_required_object_policy_digest, durable_state,"
                " backup_ref, backup_digest, last_evidence_digest) VALUES"
                " ('tx-1', 'src/b.py', 'CREATE', 2, 'ABSENT', 'ABSENT',"
                " 'ABSENT', 'ABSENT', 'ABSENT', '22' * 64, 'LATIN1', 'LF',"
                " '33' * 64, 'NOT_STARTED', 'ABSENT', 'ABSENT', 'ABSENT')"
            )
        with pytest.raises(Exception):
            tx.execute(
                "INSERT INTO persistence_path_records (transaction_id, path,"
                " operation, sequence, preimage_kind, preimage_raw_bytes_digest,"
                " preimage_text_encoding, preimage_text_newline,"
                " preimage_object_identity_digest, postimage_raw_bytes_digest,"
                " postimage_text_encoding, postimage_text_newline,"
                " postimage_required_object_policy_digest, durable_state,"
                " backup_ref, backup_digest, last_evidence_digest) VALUES"
                " ('tx-1', 'src/c.py', 'CREATE', 3, 'ABSENT', 'ABSENT',"
                " 'ABSENT', 'ABSENT', 'ABSENT', '22' * 64, 'UTF8', 'CR',"
                " '33' * 64, 'NOT_STARTED', 'ABSENT', 'ABSENT', 'ABSENT')"
            )
        # The operation-preimage combination CHECKs close the CREATE/REPLACE
        # bindings at the DDL: a REPLACE cannot carry an ABSENT preimage or
        # an ABSENT backup, and a CREATE cannot carry a PRESENT backup.
        with pytest.raises(Exception):
            tx.execute(
                valid_record.replace("'CREATE', 1, 'ABSENT'", "'REPLACE', 1, 'ABSENT'")
            )
        with pytest.raises(Exception):
            tx.execute(
                "INSERT INTO persistence_path_records (transaction_id, path,"
                " operation, sequence, preimage_kind, preimage_raw_bytes_digest,"
                " preimage_text_encoding, preimage_text_newline,"
                " preimage_object_identity_digest, postimage_raw_bytes_digest,"
                " postimage_text_encoding, postimage_text_newline,"
                " postimage_required_object_policy_digest, durable_state,"
                " backup_ref, backup_digest, last_evidence_digest) VALUES"
                " ('tx-1', 'src/d.py', 'CREATE', 4, 'ABSENT', 'ABSENT',"
                " 'ABSENT', 'ABSENT', 'ABSENT', '22' * 64, 'UTF8', 'LF',"
                " '33' * 64, 'NOT_STARTED', 'BACKUP-x', '11' * 64, 'ABSENT')"
            )
        # The unique ordered-sequence index rejects a duplicate sequence.
        with pytest.raises(Exception):
            tx.execute(valid_record)
        # The one-active-workspace partial index admits a second PREPARED
        # only after the first becomes terminal.
        tx.execute(
            "UPDATE persistence_transactions SET state = 'COMMITTED'"
            " WHERE transaction_id = 'tx-1'"
        )
        tx.execute(valid_transaction.replace("'tx-1'", "'tx-2'"), ("55" * 64,))
        tx.execute(
            "UPDATE persistence_transactions SET state = 'WRITING'"
            " WHERE transaction_id = 'tx-2'"
        )
        with pytest.raises(Exception):
            tx.execute(valid_transaction.replace("'tx-1'", "'tx-3'"), ("55" * 64,))

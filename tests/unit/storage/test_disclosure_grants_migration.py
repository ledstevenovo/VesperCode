"""T15.2 legacy step 15.D: exact v0003 disclosure Grant/subject schema tests.

Pins the immutable descriptor (version 3 / name / checksum binding), the
exact ``disclosure_grant_subjects`` and ``disclosure_grants`` tables
(columns, FKs, the one-grant-per-wait and one-active-per-subject unique
indexes, the status CHECK closure), strict version gating (v0003 cannot
apply before v0001+v0002), and idempotent replay.
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
    DISCLOSURE_GRANTS_V1_STATEMENTS,
)


@pytest.fixture
def control_database(tmp_path: Path) -> Iterator[ControlDatabase]:
    database = open_control_database(tmp_path / "disclosure_grants.db")
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


def test_disclosure_grant_migration_has_exact_schema(
    control_database: ControlDatabase,
) -> None:
    """PLAN Registry rows 447/448: exact v0003 subject/Grant schema."""
    # Descriptor: immutable, version 3, exact name, checksum bound to DDL.
    assert isinstance(DISCLOSURE_GRANTS_V1_MIGRATION, MigrationV1)
    assert DISCLOSURE_GRANTS_V1_MIGRATION.version == 3
    assert DISCLOSURE_GRANTS_V1_MIGRATION.name == "disclosure_grants_v1"
    assert DISCLOSURE_GRANTS_V1_MIGRATION.checksum.value == migration_checksum(
        3,
        "disclosure_grants_v1",
        "\n".join(DISCLOSURE_GRANTS_V1_STATEMENTS),
    )
    with pytest.raises(Exception):
        DISCLOSURE_GRANTS_V1_MIGRATION.version = 4  # type: ignore[misc]
    with pytest.raises(TypeError):
        DISCLOSURE_GRANTS_V1_STATEMENTS[0] = (  # type: ignore[index]
            "CREATE TABLE tampered (id INTEGER PRIMARY KEY)"
        )

    # Version 3 cannot apply before the v0001/v0002 prefix.
    assert (
        apply_migrations(control_database, (DISCLOSURE_GRANTS_V1_MIGRATION,)).kind
        == "VERSION_GAP"
    )
    assert _table_names(control_database) == set()

    # Applied after the v0001+v0002 prefix: exactly two more tables.
    assert (
        apply_migrations(
            control_database,
            (
                RUN_WAIT_V1_MIGRATION,
                IDEMPOTENCY_V1_MIGRATION,
                DISCLOSURE_GRANTS_V1_MIGRATION,
            ),
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
    }
    assert (
        apply_migrations(
            control_database,
            (
                RUN_WAIT_V1_MIGRATION,
                IDEMPOTENCY_V1_MIGRATION,
                DISCLOSURE_GRANTS_V1_MIGRATION,
            ),
        ).kind
        == "NOOP"
    )

    # DisclosureGrantSubjectV1 (Registry row 447): PK/unique subject digest,
    # frozen provider/endpoint/model/serializer/scope/category/budget/expiry
    # facts, and no segment content.
    assert _columns(control_database, "disclosure_grant_subjects") == {
        "subject_digest": "TEXT",
        "run_id": "TEXT",
        "llm_profile_digest": "TEXT",
        "provider": "TEXT",
        "endpoint_id": "TEXT",
        "model": "TEXT",
        "request_serializer_version": "TEXT",
        "allowed_source_paths": "TEXT",
        "allowed_source_categories": "TEXT",
        "redaction_profile_id": "TEXT",
        "cumulative_byte_budget": "INTEGER",
        "expires_at": "TEXT",
    }
    with control_database.immediate_transaction() as tx:
        subject_fks = tx.execute(
            "PRAGMA foreign_key_list(disclosure_grant_subjects)"
        ).fetchall()
    assert {str(row[3]): str(row[2]) for row in subject_fks} == {"run_id": "runs"}

    # DisclosureGrant (Registry row 448): PK grant_id, FK subject digest /
    # run / wait, consumed_bytes and ACTIVE/REVOKED/EXPIRED/EXHAUSTED state.
    assert _columns(control_database, "disclosure_grants") == {
        "grant_id": "TEXT",
        "subject_digest": "TEXT",
        "run_id": "TEXT",
        "wait_id": "TEXT",
        "created_at": "TEXT",
        "consumed_bytes": "INTEGER",
        "status": "TEXT",
    }
    with control_database.immediate_transaction() as tx:
        grant_fks = tx.execute("PRAGMA foreign_key_list(disclosure_grants)").fetchall()
        indexes = tx.execute("PRAGMA index_list(disclosure_grants)").fetchall()
    assert {str(row[3]): str(row[2]) for row in grant_fks} == {
        "subject_digest": "disclosure_grant_subjects",
        "run_id": "runs",
        "wait_id": "wait_contexts",
    }
    index_names = {str(row[1]) for row in indexes}
    assert "ux_disclosure_grants_one_grant_per_wait" in index_names
    assert "ux_disclosure_grants_one_active_per_subject" in index_names


def test_disclosure_grant_schema_check_constraints_reject_invalid_rows(
    control_database: ControlDatabase,
) -> None:
    """The exact schema closes grant status/byte/identity values at the DDL."""
    assert (
        apply_migrations(
            control_database,
            (
                RUN_WAIT_V1_MIGRATION,
                IDEMPOTENCY_V1_MIGRATION,
                DISCLOSURE_GRANTS_V1_MIGRATION,
            ),
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
            " VALUES ('wait-1', 'run-1', 'DISCLOSURE_GRANT', 'AGENT_LOOP',"
            " ?, '2026-08-05T09:00:00.000Z', '2026-08-05T09:05:00.000Z',"
            " 'PENDING')",
            ("c" * 64,),
        )
        tx.execute(
            "INSERT INTO disclosure_grant_subjects (subject_digest, run_id,"
            " llm_profile_digest, provider, endpoint_id, model,"
            " request_serializer_version, allowed_source_paths,"
            " allowed_source_categories, redaction_profile_id,"
            " cumulative_byte_budget, expires_at)"
            " VALUES (?, 'run-1', ?, 'openai', 'OPENAI_PUBLIC_API_V1',"
            " 'gpt-4.1-mini', '1', '[]', '[\"TOOL_RESULT\"]',"
            " 'NO_CONTENT_REDACTION_V1', 1000, '2026-08-05T09:05:00.000Z')",
            ("c" * 64, "d" * 64),
        )
        with pytest.raises(Exception, match="CHECK constraint failed"):
            tx.execute(
                "INSERT INTO disclosure_grants (grant_id, subject_digest,"
                " run_id, wait_id, created_at, consumed_bytes, status)"
                " VALUES ('grant-bad-status', ?, 'run-1', 'wait-1',"
                " '2026-08-05T09:01:00.000Z', 0, 'PAUSED')",
                ("c" * 64,),
            )
        with pytest.raises(Exception, match="CHECK constraint failed"):
            tx.execute(
                "INSERT INTO disclosure_grants (grant_id, subject_digest,"
                " run_id, wait_id, created_at, consumed_bytes, status)"
                " VALUES ('grant-bad-bytes', ?, 'run-1', 'wait-1',"
                " '2026-08-05T09:01:00.000Z', -1, 'ACTIVE')",
                ("c" * 64,),
            )
        tx.execute(
            "INSERT INTO disclosure_grants (grant_id, subject_digest,"
            " run_id, wait_id, created_at, consumed_bytes, status)"
            " VALUES ('grant-1', ?, 'run-1', 'wait-1',"
            " '2026-08-05T09:01:00.000Z', 0, 'ACTIVE')",
            ("c" * 64,),
        )
        # One grant per wait: a second grant for the same wait is rejected.
        # (wait-2 belongs to its own run — v0001 allows one active wait per run.)
        tx.execute(
            "INSERT INTO runs (run_id, workspace_identity, config_snapshot_id,"
            " status, phase, revision, started_at, run_deadline)"
            " VALUES ('run-2', 'ws-1', 'snap-1', 'WAITING_USER', NULL, 1,"
            " '2026-08-05T09:00:00.000Z', '2026-08-05T09:15:00.000Z')"
        )
        tx.execute(
            "INSERT INTO wait_contexts (wait_id, run_id, wait_kind,"
            " source_phase, subject_digest, created_at, expires_at, status)"
            " VALUES ('wait-2', 'run-2', 'DISCLOSURE_GRANT', 'AGENT_LOOP',"
            " ?, '2026-08-05T09:00:00.000Z', '2026-08-05T09:05:00.000Z',"
            " 'PENDING')",
            ("c" * 64,),
        )
        with pytest.raises(Exception, match="UNIQUE constraint failed"):
            tx.execute(
                "INSERT INTO disclosure_grants (grant_id, subject_digest,"
                " run_id, wait_id, created_at, consumed_bytes, status)"
                " VALUES ('grant-2', ?, 'run-2', 'wait-2',"
                " '2026-08-05T09:01:00.000Z', 0, 'ACTIVE')",
                ("c" * 64,),
            )
        # A second ACTIVE grant for the same subject is rejected; a REVOKED
        # one is allowed (only one active Grant per subject at any time).
        tx.execute(
            "UPDATE disclosure_grants SET status = 'REVOKED' WHERE grant_id = 'grant-1'"
        )
        tx.execute(
            "INSERT INTO disclosure_grants (grant_id, subject_digest,"
            " run_id, wait_id, created_at, consumed_bytes, status)"
            " VALUES ('grant-2', ?, 'run-2', 'wait-2',"
            " '2026-08-05T09:01:00.000Z', 0, 'ACTIVE')",
            ("c" * 64,),
        )

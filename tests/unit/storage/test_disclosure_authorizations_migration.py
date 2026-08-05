"""T15.2 legacy step 15.E: exact v0004 disclosure authorization schema tests.

Pins the immutable descriptor (version 4 / name / checksum binding), the
exact ``disclosure_authorizations`` table (columns, FK to
``disclosure_grants``, body-free actual-source projection, no
refund/body columns), strict version gating (v0004 cannot apply before
the v0001+v0002+v0003 prefix), and idempotent replay.
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
)
from src.vespercode.storage.migrations.v0004_disclosure_authorizations import (
    DISCLOSURE_AUTHORIZATIONS_V1_MIGRATION,
    DISCLOSURE_AUTHORIZATIONS_V1_STATEMENTS,
)


@pytest.fixture
def control_database(tmp_path: Path) -> Iterator[ControlDatabase]:
    database = open_control_database(tmp_path / "disclosure_authorizations.db")
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


def test_disclosure_authorization_migration_has_exact_schema(
    control_database: ControlDatabase,
) -> None:
    """PLAN Registry row 452: exact v0004 authorization schema."""
    # Descriptor: immutable, version 4, exact name, checksum bound to DDL.
    assert isinstance(DISCLOSURE_AUTHORIZATIONS_V1_MIGRATION, MigrationV1)
    assert DISCLOSURE_AUTHORIZATIONS_V1_MIGRATION.version == 4
    assert DISCLOSURE_AUTHORIZATIONS_V1_MIGRATION.name == "disclosure_authorizations_v1"
    assert DISCLOSURE_AUTHORIZATIONS_V1_MIGRATION.checksum.value == migration_checksum(
        4,
        "disclosure_authorizations_v1",
        "\n".join(DISCLOSURE_AUTHORIZATIONS_V1_STATEMENTS),
    )
    with pytest.raises(Exception):
        DISCLOSURE_AUTHORIZATIONS_V1_MIGRATION.version = 5  # type: ignore[misc]
    with pytest.raises(TypeError):
        DISCLOSURE_AUTHORIZATIONS_V1_STATEMENTS[0] = (  # type: ignore[index]
            "CREATE TABLE tampered (id INTEGER PRIMARY KEY)"
        )

    # Version 4 cannot apply before the v0001+v0002+v0003 prefix.
    assert (
        apply_migrations(
            control_database, (DISCLOSURE_AUTHORIZATIONS_V1_MIGRATION,)
        ).kind
        == "VERSION_GAP"
    )
    assert _table_names(control_database) == set()

    # Applied after the full prefix: exactly one more table.
    assert (
        apply_migrations(
            control_database,
            (
                RUN_WAIT_V1_MIGRATION,
                IDEMPOTENCY_V1_MIGRATION,
                DISCLOSURE_GRANTS_V1_MIGRATION,
                DISCLOSURE_AUTHORIZATIONS_V1_MIGRATION,
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
        "disclosure_authorizations",
    }
    assert (
        apply_migrations(
            control_database,
            (
                RUN_WAIT_V1_MIGRATION,
                IDEMPOTENCY_V1_MIGRATION,
                DISCLOSURE_GRANTS_V1_MIGRATION,
                DISCLOSURE_AUTHORIZATIONS_V1_MIGRATION,
            ),
        ).kind
        == "NOOP"
    )

    # DisclosureAuthorizationRecordV1 (Registry row 452): PK
    # authorization_id, FK grant_id -> disclosure_grants, unique request
    # identity/charge, exact body-free actual-source projection, and no
    # refund/body column.
    assert _columns(control_database, "disclosure_authorizations") == {
        "authorization_id": "TEXT",
        "grant_id": "TEXT",
        "grant_subject_digest": "TEXT",
        "llm_profile_digest": "TEXT",
        "provider": "TEXT",
        "endpoint_id": "TEXT",
        "model": "TEXT",
        "request_serializer_version": "TEXT",
        "request_digest": "TEXT",
        "actual_sources": "TEXT",
        "canonical_byte_count": "INTEGER",
        "redaction_profile_id": "TEXT",
        "created_at": "TEXT",
    }
    with control_database.immediate_transaction() as tx:
        fks = tx.execute(
            "PRAGMA foreign_key_list(disclosure_authorizations)"
        ).fetchall()
    assert {str(row[3]): str(row[2]) for row in fks} == {
        "grant_id": "disclosure_grants"
    }


def test_disclosure_authorization_record_rejects_duplicate_identity(
    control_database: ControlDatabase,
) -> None:
    """The PK closes the authorization id space at the DDL."""
    assert (
        apply_migrations(
            control_database,
            (
                RUN_WAIT_V1_MIGRATION,
                IDEMPOTENCY_V1_MIGRATION,
                DISCLOSURE_GRANTS_V1_MIGRATION,
                DISCLOSURE_AUTHORIZATIONS_V1_MIGRATION,
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
        tx.execute(
            "INSERT INTO disclosure_grants (grant_id, subject_digest,"
            " run_id, wait_id, created_at, consumed_bytes, status)"
            " VALUES ('grant-1', ?, 'run-1', 'wait-1',"
            " '2026-08-05T09:01:00.000Z', 0, 'ACTIVE')",
            ("c" * 64,),
        )
        row = (
            "INSERT INTO disclosure_authorizations (authorization_id, grant_id,"
            " grant_subject_digest, llm_profile_digest, provider, endpoint_id,"
            " model, request_serializer_version, request_digest, actual_sources,"
            " canonical_byte_count, redaction_profile_id, created_at)"
            " VALUES (?, 'grant-1', ?, ?, 'openai', 'OPENAI_PUBLIC_API_V1',"
            " 'gpt-4.1-mini', '1', ?, '[{\"message_index\":0}]', 100,"
            " 'NO_CONTENT_REDACTION_V1', '2026-08-05T09:02:00.000Z')"
        )
        tx.execute(row, ("rec-1", "c" * 64, "d" * 64, "e" * 64))
        with pytest.raises(Exception, match="UNIQUE constraint failed"):
            tx.execute(row, ("rec-1", "c" * 64, "d" * 64, "e" * 64))
        # The same request digest may authorize again (SPEC re-send
        # re-charges): only the authorization id is unique.
        tx.execute(row, ("rec-2", "c" * 64, "d" * 64, "e" * 64))

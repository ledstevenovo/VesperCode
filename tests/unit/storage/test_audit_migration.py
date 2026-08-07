"""T23.1 legacy step 23.A: exact v0006 audit schema tests.

Pins the immutable descriptor (version 6 / name ``audit_v1`` / checksum
binding), the exact ``audit_events`` table (columns, Run foreign key,
per-Run unique increasing sequence with a positive-sequence CHECK, the
closed event-type CHECK allowlist, the canonical created-at timestamp,
and no secret/body/request/response/raw-output column), strict version
gating (v0006 cannot apply before v0001-v0005), and idempotent replay.
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
from vespercode.storage.migrations.v0005_memory import (
    MEMORY_V1_MIGRATION,
)
from vespercode.storage.migrations.v0006_audit import (
    AUDIT_V1_MIGRATION,
    AUDIT_V1_STATEMENTS,
)

_CREATED_AT = "2026-08-06T09:00:00.000Z"


@pytest.fixture
def control_database(tmp_path: Path) -> Iterator[ControlDatabase]:
    database = open_control_database(tmp_path / "audit_migration.db")
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


def _prefix() -> tuple[MigrationV1, MigrationV1, MigrationV1, MigrationV1, MigrationV1]:
    return (
        RUN_WAIT_V1_MIGRATION,
        IDEMPOTENCY_V1_MIGRATION,
        DISCLOSURE_GRANTS_V1_MIGRATION,
        DISCLOSURE_AUTHORIZATIONS_V1_MIGRATION,
        MEMORY_V1_MIGRATION,
    )


def test_audit_migration_has_exact_schema(
    control_database: ControlDatabase,
) -> None:
    """PLAN Registry row 450: exact v0006 audit schema."""
    # Descriptor: immutable, version 6, exact name, checksum bound to DDL.
    assert isinstance(AUDIT_V1_MIGRATION, MigrationV1)
    assert AUDIT_V1_MIGRATION.version == 6
    assert AUDIT_V1_MIGRATION.name == "audit_v1"
    assert AUDIT_V1_MIGRATION.checksum.value == migration_checksum(
        6,
        "audit_v1",
        "\n".join(AUDIT_V1_STATEMENTS),
    )
    with pytest.raises(Exception):
        AUDIT_V1_MIGRATION.version = 7  # type: ignore[misc]
    with pytest.raises(TypeError):
        AUDIT_V1_STATEMENTS[0] = (  # type: ignore[index]
            "CREATE TABLE tampered (id INTEGER PRIMARY KEY)"
        )

    # Version 6 cannot apply before the v0001-v0005 prefix.
    assert (
        apply_migrations(control_database, (AUDIT_V1_MIGRATION,)).kind == "VERSION_GAP"
    )
    assert _table_names(control_database) == set()

    # Applied after the prefix: exactly one more table, idempotently.
    assert (
        apply_migrations(control_database, _prefix() + (AUDIT_V1_MIGRATION,)).kind
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
    }
    assert (
        apply_migrations(control_database, _prefix() + (AUDIT_V1_MIGRATION,)).kind
        == "NOOP"
    )

    # AuditEvent (Registry row 450): PK event_id, Run foreign key, per-Run
    # unique increasing sequence, closed event-type CHECK, redacted payload,
    # canonical created-at — no secret, body, request/response, or raw-output
    # column.
    assert _columns(control_database, "audit_events") == {
        "event_id": "TEXT",
        "run_id": "TEXT",
        "sequence": "INTEGER",
        "event_type": "TEXT",
        "redacted_payload": "TEXT",
        "created_at": "TEXT",
    }
    with control_database.immediate_transaction() as tx:
        foreign_keys = tx.execute("PRAGMA foreign_key_list(audit_events)").fetchall()
    assert [(str(row[3]), str(row[2])) for row in foreign_keys] == [("run_id", "runs")]
    with control_database.immediate_transaction() as tx:
        indexes = tx.execute("PRAGMA index_list(audit_events)").fetchall()
    index_names = {str(row[1]) for row in indexes}
    assert "ix_audit_events_created" in index_names
    unique_indexes = [str(row[1]) for row in indexes if str(row[3]) == "u"]
    assert len(unique_indexes) == 1  # the UNIQUE (run_id, sequence) autoindex
    with control_database.immediate_transaction() as tx:
        info = tx.execute(f"PRAGMA index_info({unique_indexes[0]})").fetchall()
    assert [(str(row[2])) for row in info] == ["run_id", "sequence"]


def test_audit_schema_check_constraints_reject_invalid_rows(
    control_database: ControlDatabase,
) -> None:
    """The exact schema closes event type, sequence, uniqueness, and Run."""
    assert (
        apply_migrations(control_database, _prefix() + (AUDIT_V1_MIGRATION,)).kind
        == "APPLIED"
    )
    with control_database.immediate_transaction() as tx:
        # The Run foreign key is enforced: no run row, no audit event.
        with pytest.raises(Exception, match="FOREIGN KEY constraint failed"):
            tx.execute(
                "INSERT INTO audit_events (event_id, run_id, sequence,"
                " event_type, redacted_payload, created_at)"
                " VALUES ('e-0', 'run-1', 1, 'LIFECYCLE', '{}', ?)",
                (_CREATED_AT,),
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
        # The event-type CHECK closes the allowlist at the DDL.
        with pytest.raises(Exception, match="CHECK constraint failed"):
            tx.execute(
                "INSERT INTO audit_events (event_id, run_id, sequence,"
                " event_type, redacted_payload, created_at)"
                " VALUES ('e-1', 'run-1', 1, 'MODEL_OUTPUT', '{}', ?)",
                (_CREATED_AT,),
            )
        # The sequence CHECK rejects non-positive per-Run sequences.
        with pytest.raises(Exception, match="CHECK constraint failed"):
            tx.execute(
                "INSERT INTO audit_events (event_id, run_id, sequence,"
                " event_type, redacted_payload, created_at)"
                " VALUES ('e-2', 'run-1', 0, 'LIFECYCLE', '{}', ?)",
                (_CREATED_AT,),
            )
        tx.execute(
            "INSERT INTO audit_events (event_id, run_id, sequence,"
            " event_type, redacted_payload, created_at)"
            " VALUES ('e-3', 'run-1', 1, 'LIFECYCLE', '{}', ?)",
            (_CREATED_AT,),
        )
        # The per-Run unique sequence is the DDL backstop.
        with pytest.raises(Exception, match="UNIQUE constraint failed"):
            tx.execute(
                "INSERT INTO audit_events (event_id, run_id, sequence,"
                " event_type, redacted_payload, created_at)"
                " VALUES ('e-4', 'run-1', 1, 'LIFECYCLE', '{}', ?)",
                (_CREATED_AT,),
            )

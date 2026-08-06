"""T24.1 legacy step 24.C: exact v0008 feedback schema tests.

Pins the immutable descriptor (version 8 / name ``feedback_v1`` /
checksum binding), the exact ``feedback_records`` table (PK
``feedback_id``, the closed kind/severity CHECK allowlists, canonical
created-at, the bounded summary/source/payload/evidence columns, and the
nullable ``consumed_by_turn_id`` foreign key to ``agent_turns`` — the
one-winner unconsumed predicate ``consumed_by_turn_id IS NULL``), strict
version gating (v0008 cannot apply before v0001-v0007), and idempotent
replay.
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
from src.vespercode.storage.migrations.v0008_feedback import (
    FEEDBACK_V1_MIGRATION,
    FEEDBACK_V1_STATEMENTS,
)

_CREATED_AT = "2026-08-06T09:00:00.000Z"


@pytest.fixture
def control_database(tmp_path: Path) -> Iterator[ControlDatabase]:
    database = open_control_database(tmp_path / "feedback_migration.db")
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
        AGENT_TURNS_V1_MIGRATION,
    )


def test_feedback_migration_has_exact_schema(
    control_database: ControlDatabase,
) -> None:
    """PLAN Registry row 444: exact v0008 feedback schema."""
    # Descriptor: immutable, version 8, exact name, checksum bound to DDL.
    assert isinstance(FEEDBACK_V1_MIGRATION, MigrationV1)
    assert FEEDBACK_V1_MIGRATION.version == 8
    assert FEEDBACK_V1_MIGRATION.name == "feedback_v1"
    assert FEEDBACK_V1_MIGRATION.checksum.value == migration_checksum(
        8,
        "feedback_v1",
        "\n".join(FEEDBACK_V1_STATEMENTS),
    )
    with pytest.raises(Exception):
        FEEDBACK_V1_MIGRATION.version = 9  # type: ignore[misc]
    with pytest.raises(TypeError):
        FEEDBACK_V1_STATEMENTS[0] = (  # type: ignore[index]
            "CREATE TABLE tampered (id INTEGER PRIMARY KEY)"
        )

    # Version 8 cannot apply before the v0001-v0007 prefix.
    assert (
        apply_migrations(control_database, (FEEDBACK_V1_MIGRATION,)).kind
        == "VERSION_GAP"
    )
    assert _table_names(control_database) == set()

    # Applied after the prefix: exactly one more table, idempotently.
    assert (
        apply_migrations(control_database, _prefix() + (FEEDBACK_V1_MIGRATION,)).kind
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
    }
    assert (
        apply_migrations(control_database, _prefix() + (FEEDBACK_V1_MIGRATION,)).kind
        == "NOOP"
    )

    # FeedbackRecord (Registry row 444): PK feedback_id, bounded structured
    # record columns, canonical created-at, JSON evidence refs, and the
    # nullable turn foreign key — no raw check body and no secret column.
    assert _columns(control_database, "feedback_records") == {
        "feedback_id": "TEXT",
        "kind": "TEXT",
        "severity": "TEXT",
        "created_at": "TEXT",
        "summary": "TEXT",
        "source_ref": "TEXT",
        "bounded_payload": "TEXT",
        "evidence_refs": "TEXT",
        "consumed_by_turn_id": "TEXT",
    }
    with control_database.immediate_transaction() as tx:
        foreign_keys = tx.execute(
            "PRAGMA foreign_key_list(feedback_records)"
        ).fetchall()
    assert [(str(row[3]), str(row[2])) for row in foreign_keys] == [
        ("consumed_by_turn_id", "agent_turns")
    ]


def test_feedback_schema_check_constraints_reject_invalid_rows(
    control_database: ControlDatabase,
) -> None:
    """The exact schema closes kind/severity, bounds, FK, and nullable FK."""
    assert (
        apply_migrations(control_database, _prefix() + (FEEDBACK_V1_MIGRATION,)).kind
        == "APPLIED"
    )
    with control_database.immediate_transaction() as tx:
        # The Run and Turn rows are required for the foreign keys.
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
        # The kind CHECK closes the allowlist at the DDL.
        with pytest.raises(Exception, match="CHECK constraint failed"):
            tx.execute(
                "INSERT INTO feedback_records (feedback_id, kind, severity,"
                " created_at, summary, source_ref, bounded_payload,"
                " evidence_refs, consumed_by_turn_id)"
                " VALUES ('fb-1', 'MEMO', 'HIGH', ?, 'summary', '{}', '{}',"
                " '[]', NULL)",
                (_CREATED_AT,),
            )
        # The severity CHECK closes the allowlist at the DDL.
        with pytest.raises(Exception, match="CHECK constraint failed"):
            tx.execute(
                "INSERT INTO feedback_records (feedback_id, kind, severity,"
                " created_at, summary, source_ref, bounded_payload,"
                " evidence_refs, consumed_by_turn_id)"
                " VALUES ('fb-2', 'CHECK', 'URGENT', ?, 'summary', '{}', '{}',"
                " '[]', NULL)",
                (_CREATED_AT,),
            )
        # The bounded-column CHECKs are the DDL backstop.
        with pytest.raises(Exception, match="CHECK constraint failed"):
            tx.execute(
                "INSERT INTO feedback_records (feedback_id, kind, severity,"
                " created_at, summary, source_ref, bounded_payload,"
                " evidence_refs, consumed_by_turn_id)"
                " VALUES ('fb-3', 'CHECK', 'HIGH', ?, '', '{}', '{}', '[]',"
                " NULL)",
                (_CREATED_AT,),
            )
        # The turn foreign key is enforced and nullable: a bound record
        # needs an existing turn, an unconsumed record is always legal.
        with pytest.raises(Exception, match="FOREIGN KEY constraint failed"):
            tx.execute(
                "INSERT INTO feedback_records (feedback_id, kind, severity,"
                " created_at, summary, source_ref, bounded_payload,"
                " evidence_refs, consumed_by_turn_id)"
                " VALUES ('fb-4', 'CHECK', 'HIGH', ?, 'summary', '{}', '{}',"
                " '[]', 'turn-missing')",
                (_CREATED_AT,),
            )
        tx.execute(
            "INSERT INTO feedback_records (feedback_id, kind, severity,"
            " created_at, summary, source_ref, bounded_payload,"
            " evidence_refs, consumed_by_turn_id)"
            " VALUES ('fb-5', 'CHECK', 'HIGH', ?, 'summary', '{}', '{}',"
            " '[]', NULL)",
            (_CREATED_AT,),
        )
        tx.execute(
            "INSERT INTO feedback_records (feedback_id, kind, severity,"
            " created_at, summary, source_ref, bounded_payload,"
            " evidence_refs, consumed_by_turn_id)"
            " VALUES ('fb-6', 'ACTION', 'CRITICAL', ?, 'summary', '{}', '{}',"
            " '[]', 'turn-1')",
            (_CREATED_AT,),
        )

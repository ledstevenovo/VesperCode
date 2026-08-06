"""T23.1 legacy step 23.C: recovery-preserving audit retention RED + matrix.

Pins the exact RED (an old unresolved recovery keeps its audit evidence)
and the PLAN legacy-step matrix row 23.C: eligible terminal records
before the strict 30-day cutoff delete in deterministic bounded batches;
active/waiting/recovery/unresolved/missing-terminal evidence is
preserved; repeated retention is idempotent and never crosses
workspaces.  Active-Run clear, transaction redesign, backup-body
erasure, visibility projection, and terminal inference remain out of
scope (GREEN-4).
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from pathlib import Path
from typing import cast

import pytest

# The retention evaluator consumes pydantic runtime contracts; the
# hash-locked gate toolchain installs no runtime dependencies, so this
# module skips cleanly there (formal env runs it fully).
pytest.importorskip("pydantic")

from src.vespercode.audit.event import AuditEventTypeV1
from src.vespercode.audit.repository import (
    AppendAuditEventV1,
    AuditPageRequestV1,
    AuditRepository,
)
from src.vespercode.audit.retention import AuditRetentionResultV1, apply_audit_retention
from src.vespercode.canonical.timestamp_v1 import CanonicalTimestampV1
from src.vespercode.storage.connection import (
    ControlDatabase,
    open_control_database,
)
from src.vespercode.storage.migration_engine import apply_migrations
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

# day_31 = 2026-08-06T09:00:00.000Z; the strict cutoff is exactly 30 days
# earlier; old facts are 36 days earlier; fresh facts are 5 days earlier.
_CREATED_AT = CanonicalTimestampV1("2026-08-06T09:00:00.000Z")
_OLD_AT = CanonicalTimestampV1("2026-07-01T09:00:00.000Z")
_EDGE_30_AT = CanonicalTimestampV1("2026-07-07T09:00:00.000Z")

_MIGRATIONS = (
    RUN_WAIT_V1_MIGRATION,
    IDEMPOTENCY_V1_MIGRATION,
    DISCLOSURE_GRANTS_V1_MIGRATION,
    DISCLOSURE_AUTHORIZATIONS_V1_MIGRATION,
    MEMORY_V1_MIGRATION,
    AUDIT_V1_MIGRATION,
)


@pytest.fixture
def database_path(tmp_path: Path) -> Path:
    return tmp_path / "audit_retention.db"


@pytest.fixture
def control_database(database_path: Path) -> Iterator[ControlDatabase]:
    database = open_control_database(database_path)
    apply_migrations(database, _MIGRATIONS)
    yield database
    database.close()


@pytest.fixture
def audit_repository(control_database: ControlDatabase) -> AuditRepository:
    return AuditRepository(control_database)


@pytest.fixture
def day_31() -> CanonicalTimestampV1:
    return _CREATED_AT


def _seed_run(
    database: ControlDatabase,
    run_id: str,
    status: str,
    phase: str | None,
    *,
    workspace: str = "workspace-a",
) -> None:
    """Insert one deterministic run row (config snapshot + run)."""
    with database.immediate_transaction() as tx:
        tx.execute(
            "INSERT INTO run_config_snapshots (config_snapshot_id, digest,"
            " llm_profile_id, reference_profile_id, policy_id, target_test_ids,"
            " limits_digest, frozen_at)"
            " VALUES (?, ?, 'llm-1', 'ref-1', 'policy-1', '[]', 'limits-1', ?)",
            (f"cfg-{run_id}", f"{run_id}{'a' * 64}"[:64], _CREATED_AT.value),
        )
        tx.execute(
            "INSERT INTO runs (run_id, workspace_identity, config_snapshot_id,"
            " status, phase, revision, started_at, run_deadline)"
            " VALUES (?, ?, ?, ?, ?, 1, ?, ?)",
            (
                run_id,
                workspace,
                f"cfg-{run_id}",
                status,
                phase,
                _CREATED_AT.value,
                "2026-08-06T10:00:00.000Z",
            ),
        )


def append_event(
    event_type: str,
    payload: dict[str, str],
    *,
    run_id: str,
    event_id: str,
    created_at: CanonicalTimestampV1,
) -> AppendAuditEventV1:
    """One deterministic append command (card RED fixture helper)."""
    return AppendAuditEventV1(
        run_id=run_id,
        event_type=cast(AuditEventTypeV1, event_type),
        payload=payload,
        evidence_refs=(),
        event_id=event_id,
        created_at=created_at,
    )


def first_page() -> AuditPageRequestV1:
    """The unbounded first page request (card RED fixture helper)."""
    return AuditPageRequestV1(page_size=100)


def seed_old_unresolved_recovery(audit_repository: AuditRepository) -> None:
    """The card RED fixture: old audit evidence of one unresolved recovery."""
    _seed_run(audit_repository.database, "run-recovery", "RECOVERY_REQUIRED", None)
    for index, (event_type, payload) in enumerate(
        (
            ("RECOVERY", {"transaction_id": "tx-1", "disposition": "UNRESOLVED"}),
            ("STOP_EVIDENCE", {"reason_code": "PERSISTENCE_INCOMPLETE"}),
        )
    ):
        result = audit_repository.append(
            append_event(
                event_type,
                payload,
                run_id="run-recovery",
                event_id=f"recovery-{index}",
                created_at=_OLD_AT,
            )
        )
        assert result.kind == "APPENDED"


def _run_traced_retention(
    audit_repository: AuditRepository,
    day_31: CanonicalTimestampV1,
) -> tuple[AuditRetentionResultV1, int]:
    """Run retention once and count its BEGIN IMMEDIATE transactions."""
    statements: list[str] = []
    audit_repository.database.set_trace_callback(statements.append)
    try:
        result = apply_audit_retention(day_31, audit_repository)
    finally:
        audit_repository.database.set_trace_callback(None)
    transactions = sum(
        1
        for statement in statements
        if statement.strip().upper().startswith("BEGIN IMMEDIATE")
    )
    return result, transactions


def _delete_run_row_out_of_band(database_path: Path, run_id: str) -> None:
    """Delete one runs row through a foreign-key-free side connection.

    The ControlDatabase always enforces foreign keys, so a Run row
    missing under its audit events is only reachable out-of-band;
    retention must still fail closed and preserve its events.
    """
    connection = sqlite3.connect(str(database_path))
    try:
        connection.execute("PRAGMA foreign_keys = OFF")
        connection.execute("DELETE FROM runs WHERE run_id = ?", (run_id,))
        connection.commit()
    finally:
        connection.close()


def test_retention_preserves_unresolved_recovery_evidence(
    audit_repository: AuditRepository,
    day_31: CanonicalTimestampV1,
) -> None:
    seed_old_unresolved_recovery(audit_repository)
    result = apply_audit_retention(day_31, audit_repository)
    assert result.deleted_event_count == 0
    assert audit_repository.list_run("run-recovery", first_page()).items


def test_audit_retention_matrix(
    audit_repository: AuditRepository,
    day_31: CanonicalTimestampV1,
    database_path: Path,
) -> None:
    """PLAN legacy-step matrix row 23.C: recovery-preserving retention."""
    # Eligible terminal records before the cutoff delete in deterministic
    # bounded batches (100 rows per transaction).
    _seed_run(audit_repository.database, "run-ended", "SUCCEEDED", None)
    for index in range(250):
        appended = audit_repository.append(
            append_event(
                "STOP_EVIDENCE",
                {"reason_code": "TURN_LIMIT"},
                run_id="run-ended",
                event_id=f"ended-{index}",
                created_at=_OLD_AT,
            )
        )
        assert appended.kind == "APPENDED"
    result, transactions = _run_traced_retention(audit_repository, day_31)
    assert transactions == 3
    assert result.cutoff == CanonicalTimestampV1("2026-07-07T09:00:00.000Z")
    assert result.batch_size == 100
    assert result.deleted_event_count == 250
    assert result.preserved_event_count == 0
    assert audit_repository.event_count == 0
    rerun = apply_audit_retention(day_31, audit_repository)
    assert rerun.deleted_event_count == 0
    assert audit_repository.event_count == 0

    # The cutoff is strict: an event exactly 30 days old is not eligible.
    _seed_run(audit_repository.database, "run-edge", "STOPPED", None)
    for index, created_at in enumerate((_EDGE_30_AT, _EDGE_30_AT, _OLD_AT)):
        appended = audit_repository.append(
            append_event(
                "STOP_EVIDENCE",
                {"reason_code": "TURN_LIMIT"},
                run_id="run-edge",
                event_id=f"edge-{index}",
                created_at=created_at,
            )
        )
        assert appended.kind == "APPENDED"
    result = apply_audit_retention(day_31, audit_repository)
    assert result.deleted_event_count == 1
    # The exactly-30-day-old events are not candidates at all (only events
    # strictly older than the cutoff are examined), so they remain intact.
    assert result.preserved_event_count == 0
    assert [
        item.sequence
        for item in audit_repository.list_run("run-edge", first_page()).items
    ] == [1, 2]

    # Active, waiting, recovery, unresolved, and missing-terminal evidence
    # is preserved no matter how old.
    for run_id, event_id in (
        ("run-active", "act-0"),
        ("run-created", "cre-0"),
        ("run-waiting", "wai-0"),
    ):
        _seed_run(
            audit_repository.database,
            run_id,
            "RUNNING"
            if run_id == "run-active"
            else ("CREATED" if run_id == "run-created" else "WAITING_USER"),
            "PREFLIGHT" if run_id == "run-active" else None,
        )
        appended = audit_repository.append(
            append_event(
                "STOP_EVIDENCE",
                {"reason_code": "TURN_LIMIT"},
                run_id=run_id,
                event_id=event_id,
                created_at=_OLD_AT,
            )
        )
        assert appended.kind == "APPENDED"
    seed_old_unresolved_recovery(audit_repository)
    # An unresolved recovery reference preserves a terminal-status Run.
    _seed_run(audit_repository.database, "run-unresolved", "SUCCEEDED", None)
    for index, (event_type, payload) in enumerate(
        (
            ("RECOVERY", {"transaction_id": "tx-9", "disposition": "UNRESOLVED"}),
            ("STOP_EVIDENCE", {"reason_code": "PERSISTENCE_INCOMPLETE"}),
        )
    ):
        appended = audit_repository.append(
            append_event(
                event_type,
                payload,
                run_id="run-unresolved",
                event_id=f"unres-{index}",
                created_at=_OLD_AT,
            )
        )
        assert appended.kind == "APPENDED"
    # A missing terminal Run (run row deleted out-of-band) is preserved.
    _seed_run(audit_repository.database, "run-missing", "SUCCEEDED", None)
    for index in range(2):
        appended = audit_repository.append(
            append_event(
                "STOP_EVIDENCE",
                {"reason_code": "TURN_LIMIT"},
                run_id="run-missing",
                event_id=f"miss-{index}",
                created_at=_OLD_AT,
            )
        )
        assert appended.kind == "APPENDED"
    _delete_run_row_out_of_band(database_path, "run-missing")
    result = apply_audit_retention(day_31, audit_repository)
    # This call deletes nothing (all remaining old candidates belong to
    # preserved Runs); each call reports only its own bounded counts.
    assert result.deleted_event_count == 0
    # Preserved candidates: active/created/waiting 3 + recovery 2 +
    # unresolved-reference 2 + missing-terminal 2 = 9.
    assert result.preserved_event_count == 9
    for run_id in (
        "run-active",
        "run-created",
        "run-waiting",
        "run-recovery",
        "run-unresolved",
        "run-missing",
    ):
        assert audit_repository.list_run(run_id, first_page()).items

    # Retention never crosses workspaces.
    _seed_run(
        audit_repository.database,
        "run-ws-a",
        "SUCCEEDED",
        None,
        workspace="workspace-a",
    )
    _seed_run(
        audit_repository.database,
        "run-ws-b",
        "RUNNING",
        "AGENT_LOOP",
        workspace="workspace-b",
    )
    for run_id, event_id in (("run-ws-a", "wsa-0"), ("run-ws-b", "wsb-0")):
        appended = audit_repository.append(
            append_event(
                "STOP_EVIDENCE",
                {"reason_code": "TURN_LIMIT"},
                run_id=run_id,
                event_id=event_id,
                created_at=_OLD_AT,
            )
        )
        assert appended.kind == "APPENDED"
    result = apply_audit_retention(day_31, audit_repository)
    assert result.deleted_event_count == 1
    # This call re-examines every old candidate: the 9 preserved ones from
    # the previous call plus the new workspace-b event.
    assert result.preserved_event_count == 10
    assert not audit_repository.list_run("run-ws-a", first_page()).items
    assert audit_repository.list_run("run-ws-b", first_page()).items
    rerun = apply_audit_retention(day_31, audit_repository)
    assert rerun.deleted_event_count == 0
    assert rerun.preserved_event_count == 10

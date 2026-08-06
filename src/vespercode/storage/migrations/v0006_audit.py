"""T23.1 legacy step 23.A: immutable v0006 audit DDL migration.

The one audit schema per the SPEC 7 AuditEvent row: ``audit_events``
(PK ``event_id``, FK ``run_id`` -> runs, per-Run unique increasing
``sequence`` with a positive-sequence CHECK, the closed event-type CHECK
allowlist, the redacted canonical payload text, and the canonical
created-at timestamp; there is no secret, body, request/response, or
raw-output column).  The workspace index and the per-Run unique
constraint make every append/list/retention query exact and bounded.
The final registry composition (Task 7.D) is not editable here.
"""

from __future__ import annotations

from src.vespercode.contracts.evidence import DigestV1
from src.vespercode.storage.connection import ControlTransactionV1
from src.vespercode.storage.migration_engine import (
    MigrationV1,
    migration_checksum,
)

AUDIT_V1_STATEMENTS: tuple[str, ...] = (
    """CREATE TABLE audit_events (
        event_id TEXT PRIMARY KEY,
        run_id TEXT NOT NULL REFERENCES runs(run_id),
        sequence INTEGER NOT NULL CHECK (sequence >= 1),
        event_type TEXT NOT NULL CHECK (event_type IN (
            'LIFECYCLE',
            'ACTION',
            'POLICY_DECISION',
            'FINAL_WRITEBACK_APPROVAL',
            'DISCLOSURE_GRANT',
            'DISCLOSURE_AUTHORIZATION',
            'CHECK_RESULT',
            'RECOVERY',
            'STOP_EVIDENCE',
            'LLM_CALL'
        )),
        redacted_payload TEXT NOT NULL,
        created_at TEXT NOT NULL,
        UNIQUE (run_id, sequence)
    )""",
    """CREATE INDEX ix_audit_events_created
        ON audit_events(created_at)""",
)
"""The exact immutable v0006 statements; the checksum binds these bytes."""


def _apply_audit_v1(tx: ControlTransactionV1) -> None:
    for statement in AUDIT_V1_STATEMENTS:
        tx.execute(statement)


AUDIT_V1_MIGRATION = MigrationV1(
    version=6,
    name="audit_v1",
    checksum=DigestV1(
        value=migration_checksum(
            6,
            "audit_v1",
            "\n".join(AUDIT_V1_STATEMENTS),
        )
    ),
    apply=_apply_audit_v1,
)
"""Immutable v0006 audit migration consumed by Task 7.D."""

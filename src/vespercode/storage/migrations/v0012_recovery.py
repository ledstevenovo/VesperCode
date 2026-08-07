"""T26.2 legacy step 26.C: immutable v0012 recovery terminal-result DDL.

The single table stores the body-free, service-proven terminal recovery
results: PK transaction id (FK to the v0011 persistence transaction),
the closed COMMITTED/ROLLED_BACK/UNRESOLVED disposition, the evidence
digest, the changed canonical paths, the durable workspace write count,
and the applied-at timestamp — never any file body.  The final registry
composition (Task 7.D) is not editable here.
"""

from __future__ import annotations

from vespercode.contracts.evidence import DigestV1
from vespercode.storage.connection import ControlTransactionV1
from vespercode.storage.migration_engine import (
    MigrationV1,
    migration_checksum,
)

RECOVERY_V1_STATEMENTS: tuple[str, ...] = (
    """CREATE TABLE recovery_results (
        transaction_id TEXT PRIMARY KEY
            REFERENCES persistence_transactions(transaction_id),
        disposition TEXT NOT NULL CHECK (disposition IN (
            'COMMITTED',
            'ROLLED_BACK',
            'UNRESOLVED'
        )),
        evidence_digest TEXT NOT NULL,
        changed_paths TEXT NOT NULL,
        workspace_write_count INTEGER NOT NULL
            CHECK (workspace_write_count >= 0),
        applied_at TEXT NOT NULL
    )""",
)
"""The exact immutable v0012 statements; the checksum binds these bytes.

``changed_paths`` stores the canonical JSON array of the paths the apply
authoritatively changed; no table stores any body byte.
"""


def _apply_recovery_v1(tx: ControlTransactionV1) -> None:
    for statement in RECOVERY_V1_STATEMENTS:
        tx.execute(statement)


RECOVERY_V1_MIGRATION = MigrationV1(
    version=12,
    name="recovery_v1",
    checksum=DigestV1(
        value=migration_checksum(
            12,
            "recovery_v1",
            "\n".join(RECOVERY_V1_STATEMENTS),
        )
    ),
    apply=_apply_recovery_v1,
)
"""Immutable v0012 recovery migration consumed by Task 7.D."""

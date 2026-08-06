"""T22.1 legacy step 22.A: immutable v0005 memory DDL migration.

The one table ``memory_entries`` stores only the bounded structured
memory facts: PK ``entry_id``, exact ``workspace_identity``, the closed
kind/creator unions, the bounded summary, the canonical source storage
text, creation/update timestamps, the untrusted marker, and the nullable
clear tombstone pair (``cleared_at`` / ``clear_transaction_id``).  There
is no secret, permission, full-source-body, audit, or governance column,
and the workspace index binds every exact-workspace list/selection query.
The final registry composition (Task 7.D) is not editable here.
"""

from __future__ import annotations

from src.vespercode.contracts.evidence import DigestV1
from src.vespercode.storage.connection import ControlTransactionV1
from src.vespercode.storage.migration_engine import (
    MigrationV1,
    migration_checksum,
)

MEMORY_V1_STATEMENTS: tuple[str, ...] = (
    """CREATE TABLE memory_entries (
        entry_id TEXT PRIMARY KEY,
        workspace_identity TEXT NOT NULL,
        kind TEXT NOT NULL CHECK (kind IN (
            'PROJECT_CONVENTION',
            'USER_DECISION',
            'RUN_SUMMARY',
            'KNOWN_FAILURE'
        )),
        summary TEXT NOT NULL,
        creator TEXT NOT NULL CHECK (creator IN (
            'USER',
            'CONTROL_PLANE',
            'MODEL'
        )),
        source TEXT NOT NULL,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        untrusted INTEGER NOT NULL DEFAULT 1 CHECK (untrusted IN (0, 1)),
        cleared_at TEXT,
        clear_transaction_id TEXT
    )""",
    """CREATE INDEX ix_memory_entries_workspace
        ON memory_entries(workspace_identity)""",
)
"""The exact immutable v0005 statements; the checksum binds these bytes."""


def _apply_memory_v1(tx: ControlTransactionV1) -> None:
    for statement in MEMORY_V1_STATEMENTS:
        tx.execute(statement)


MEMORY_V1_MIGRATION = MigrationV1(
    version=5,
    name="memory_v1",
    checksum=DigestV1(
        value=migration_checksum(
            5,
            "memory_v1",
            "\n".join(MEMORY_V1_STATEMENTS),
        )
    ),
    apply=_apply_memory_v1,
)
"""Immutable v0005 memory migration consumed by Task 7.D."""

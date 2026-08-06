"""T26.1 legacy step 26.A: immutable v0011 persistence transaction/path DDL.

The two tables store the body-free persistence facts: ``persistence_
transactions`` (PK transaction id, FK Run and consumed approval, the
workspace identity digest and canonical path, the frozen final-diff and
policy digests, the closed PREPARED/WRITING/COMMITTED/ROLLED_BACK/
UNRESOLVED state, the run deadline, and the durable write count, with a
partial unique index admitting at most one active workspace
transaction) and ``persistence_path_records`` (PK (transaction, path),
the closed CREATE/REPLACE operation, the typed ABSENT/PRESENT preimage
evidence, the body-free postimage binding, the 1-based ordered sequence
with a unique index, the closed durable write state, and the backup
artifact reference / last evidence digest — never any body column).  The
final registry composition (Task 7.D) is not editable here.
"""

from __future__ import annotations

from src.vespercode.contracts.evidence import DigestV1
from src.vespercode.storage.connection import ControlTransactionV1
from src.vespercode.storage.migration_engine import (
    MigrationV1,
    migration_checksum,
)

PERSISTENCE_V1_STATEMENTS: tuple[str, ...] = (
    """CREATE TABLE persistence_transactions (
        transaction_id TEXT PRIMARY KEY,
        run_id TEXT NOT NULL REFERENCES runs(run_id),
        approval_id TEXT NOT NULL
            REFERENCES writeback_approvals(approval_id),
        workspace_identity_digest TEXT NOT NULL,
        workspace_path TEXT NOT NULL,
        final_diff_digest TEXT NOT NULL,
        policy_digest TEXT NOT NULL,
        state TEXT NOT NULL CHECK (state IN (
            'PREPARED',
            'WRITING',
            'COMMITTED',
            'ROLLED_BACK',
            'UNRESOLVED'
        )),
        run_deadline TEXT NOT NULL,
        prepared_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        workspace_write_count INTEGER NOT NULL
            CHECK (workspace_write_count >= 0)
    )""",
    """CREATE UNIQUE INDEX ux_persistence_transactions_one_active_workspace
        ON persistence_transactions(workspace_identity_digest)
        WHERE state IN ('PREPARED', 'WRITING', 'UNRESOLVED')""",
    """CREATE TABLE persistence_path_records (
        transaction_id TEXT NOT NULL
            REFERENCES persistence_transactions(transaction_id),
        path TEXT NOT NULL,
        operation TEXT NOT NULL CHECK (operation IN ('CREATE', 'REPLACE')),
        sequence INTEGER NOT NULL CHECK (sequence >= 1),
        preimage_kind TEXT NOT NULL
            CHECK (preimage_kind IN ('ABSENT', 'PRESENT')),
        preimage_raw_bytes_digest TEXT NOT NULL CHECK (
            preimage_kind = 'ABSENT'
            OR preimage_raw_bytes_digest NOT IN ('ABSENT')
        ),
        preimage_text_encoding TEXT NOT NULL CHECK (
            preimage_kind = 'ABSENT'
            OR preimage_text_encoding IN ('UTF8', 'UTF8_BOM')
        ),
        preimage_text_newline TEXT NOT NULL CHECK (
            preimage_kind = 'ABSENT'
            OR preimage_text_newline IN ('LF', 'CRLF')
        ),
        preimage_object_identity_digest TEXT NOT NULL CHECK (
            preimage_kind = 'ABSENT'
            OR preimage_object_identity_digest NOT IN ('ABSENT')
        ),
        postimage_raw_bytes_digest TEXT NOT NULL,
        postimage_text_encoding TEXT NOT NULL
            CHECK (postimage_text_encoding IN ('UTF8', 'UTF8_BOM')),
        postimage_text_newline TEXT NOT NULL
            CHECK (postimage_text_newline IN ('LF', 'CRLF')),
        postimage_required_object_policy_digest TEXT NOT NULL,
        durable_state TEXT NOT NULL CHECK (durable_state IN (
            'NOT_STARTED',
            'REPLACED',
            'VERIFIED',
            'ROLLED_BACK'
        )),
        backup_ref TEXT NOT NULL,
        backup_digest TEXT NOT NULL,
        last_evidence_digest TEXT NOT NULL,
        CHECK (
            operation = 'REPLACE'
            OR (preimage_kind = 'ABSENT' AND backup_ref = 'ABSENT')
        ),
        CHECK (operation = 'CREATE' OR preimage_kind = 'PRESENT'),
        CHECK (operation = 'CREATE' OR backup_ref != 'ABSENT'),
        CHECK (backup_ref = 'ABSENT' OR backup_digest != 'ABSENT'),
        PRIMARY KEY (transaction_id, path)
    )""",
    """CREATE UNIQUE INDEX ux_persistence_path_records_ordered_sequence
        ON persistence_path_records(transaction_id, sequence)""",
)
"""The exact immutable v0011 statements; the checksum binds these bytes.

``backup_ref``/``backup_digest``/``last_evidence_digest`` use the typed
``ABSENT`` sentinel for absent optional evidence and the artifact id /
64-hex digest pair for present evidence (SPEC 0.1: never an empty
string).  No table stores any body byte.
"""


def _apply_persistence_v1(tx: ControlTransactionV1) -> None:
    for statement in PERSISTENCE_V1_STATEMENTS:
        tx.execute(statement)


PERSISTENCE_V1_MIGRATION = MigrationV1(
    version=11,
    name="persistence_v1",
    checksum=DigestV1(
        value=migration_checksum(
            11,
            "persistence_v1",
            "\n".join(PERSISTENCE_V1_STATEMENTS),
        )
    ),
    apply=_apply_persistence_v1,
)
"""Immutable v0011 persistence migration consumed by Task 7.D."""

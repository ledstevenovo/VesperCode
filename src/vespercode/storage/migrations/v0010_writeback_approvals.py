"""T14.1 legacy step 14.B: immutable v0010 writeback approval/subject DDL.

The two tables store the frozen final-writeback authorization facts: the
immutable ``writeback_approval_subjects`` (PK/unique subject digest,
frozen candidate/diff/validation/evidence/preimage/config/policy/
reference facts and expiry, no mutable status and no candidate body) and
the mutable ``writeback_approvals`` (PK approval_id, FKs subject
digest/run/wait, ``created_at``, the closed
``PENDING/REJECTED/EXPIRED/CONSUMED`` status, and one approval per wait
via a unique index).  The final registry composition (Task 7.D) is not
editable here.
"""

from __future__ import annotations

from vespercode.contracts.evidence import DigestV1
from vespercode.storage.connection import ControlTransactionV1
from vespercode.storage.migration_engine import (
    MigrationV1,
    migration_checksum,
)

WRITEBACK_APPROVALS_V1_STATEMENTS: tuple[str, ...] = (
    """CREATE TABLE writeback_approval_subjects (
        subject_digest TEXT PRIMARY KEY,
        run_id TEXT NOT NULL REFERENCES runs(run_id),
        candidate_digest TEXT NOT NULL,
        final_diff_digest TEXT NOT NULL,
        validation_manifest_digest TEXT NOT NULL,
        formal_evidence_digest TEXT NOT NULL,
        workspace_preimage_digest TEXT NOT NULL,
        run_config_digest TEXT NOT NULL,
        policy_digest TEXT NOT NULL,
        reference_profile_digest TEXT NOT NULL,
        action_semantic_digest TEXT NOT NULL,
        expires_at TEXT NOT NULL
    )""",
    """CREATE TABLE writeback_approvals (
        approval_id TEXT PRIMARY KEY,
        subject_digest TEXT NOT NULL
            REFERENCES writeback_approval_subjects(subject_digest),
        run_id TEXT NOT NULL REFERENCES runs(run_id),
        wait_id TEXT NOT NULL REFERENCES wait_contexts(wait_id),
        created_at TEXT NOT NULL,
        status TEXT NOT NULL CHECK (status IN (
            'PENDING',
            'REJECTED',
            'EXPIRED',
            'CONSUMED'
        ))
    )""",
    """CREATE UNIQUE INDEX ux_writeback_approvals_one_per_wait
        ON writeback_approvals(wait_id)""",
)
"""The exact immutable v0010 statements; the checksum binds these bytes."""


def _apply_writeback_approvals_v1(tx: ControlTransactionV1) -> None:
    for statement in WRITEBACK_APPROVALS_V1_STATEMENTS:
        tx.execute(statement)


WRITEBACK_APPROVALS_V1_MIGRATION = MigrationV1(
    version=10,
    name="writeback_approvals_v1",
    checksum=DigestV1(
        value=migration_checksum(
            10,
            "writeback_approvals_v1",
            "\n".join(WRITEBACK_APPROVALS_V1_STATEMENTS),
        )
    ),
    apply=_apply_writeback_approvals_v1,
)
"""Immutable v0010 writeback approval migration consumed by Task 7.D."""

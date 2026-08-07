"""T24.1 legacy step 24.C: immutable v0008 feedback DDL migration.

The one feedback schema per SPEC 7 FeedbackRecord row and Registry row
444: ``feedback_records`` (PK ``feedback_id``, the closed
CHECK-allowlisted kind/severity columns, the canonical created-at
timestamp, the bounded summary/source/payload columns, the JSON evidence
references, and the nullable ``consumed_by_turn_id`` foreign key to
``agent_turns`` — the one-winner unconsumed predicate
``consumed_by_turn_id IS NULL``); there is no raw check body and no
secret column.  The final registry composition (Task 7.D) is not
editable here.
"""

from __future__ import annotations

from vespercode.contracts.evidence import DigestV1
from vespercode.storage.connection import ControlTransactionV1
from vespercode.storage.migration_engine import (
    MigrationV1,
    migration_checksum,
)

FEEDBACK_V1_STATEMENTS: tuple[str, ...] = (
    """CREATE TABLE feedback_records (
        feedback_id TEXT PRIMARY KEY,
        kind TEXT NOT NULL CHECK (kind IN ('CHECK', 'ACTION', 'CONTROL')),
        severity TEXT NOT NULL CHECK (severity IN (
            'CRITICAL',
            'HIGH',
            'MEDIUM',
            'LOW'
        )),
        created_at TEXT NOT NULL,
        summary TEXT NOT NULL CHECK (length(summary) BETWEEN 1 AND 512),
        source_ref TEXT NOT NULL CHECK (length(source_ref) BETWEEN 1 AND 256),
        bounded_payload TEXT NOT NULL CHECK (length(bounded_payload) BETWEEN 1 AND 4096),
        evidence_refs TEXT NOT NULL CHECK (length(evidence_refs) BETWEEN 1 AND 2048),
        consumed_by_turn_id TEXT REFERENCES agent_turns(turn_id)
    )""",
)
"""The exact immutable v0008 statements; the checksum binds these bytes."""


def _apply_feedback_v1(tx: ControlTransactionV1) -> None:
    for statement in FEEDBACK_V1_STATEMENTS:
        tx.execute(statement)


FEEDBACK_V1_MIGRATION = MigrationV1(
    version=8,
    name="feedback_v1",
    checksum=DigestV1(
        value=migration_checksum(
            8,
            "feedback_v1",
            "\n".join(FEEDBACK_V1_STATEMENTS),
        )
    ),
    apply=_apply_feedback_v1,
)
"""Immutable v0008 feedback migration consumed by Task 7.D."""

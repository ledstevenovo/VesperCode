"""T15.2 legacy step 15.D: immutable v0003 disclosure Grant/subject DDL.

The two tables store the frozen disclosure authorization facts: the
immutable ``disclosure_grant_subjects`` (PK/unique subject digest, frozen
provider/endpoint/model/serializer/scope/category/budget/expiry facts, no
segment content) and the mutable ``disclosure_grants`` (PK grant_id, FKs
subject digest/run/wait, ``consumed_bytes``, closed
``ACTIVE/REVOKED/EXPIRED/EXHAUSTED`` status, one grant per wait, and at
most one ACTIVE grant per subject via a partial unique index).  The final
registry composition (Task 7.D) is not editable here.
"""

from __future__ import annotations

from src.vespercode.contracts.evidence import DigestV1
from src.vespercode.storage.connection import ControlTransactionV1
from src.vespercode.storage.migration_engine import (
    MigrationV1,
    migration_checksum,
)

DISCLOSURE_GRANTS_V1_STATEMENTS: tuple[str, ...] = (
    """CREATE TABLE disclosure_grant_subjects (
        subject_digest TEXT PRIMARY KEY,
        run_id TEXT NOT NULL REFERENCES runs(run_id),
        llm_profile_digest TEXT NOT NULL,
        provider TEXT NOT NULL,
        endpoint_id TEXT NOT NULL,
        model TEXT NOT NULL,
        request_serializer_version TEXT NOT NULL,
        allowed_source_paths TEXT NOT NULL,
        allowed_source_categories TEXT NOT NULL,
        redaction_profile_id TEXT NOT NULL,
        cumulative_byte_budget INTEGER NOT NULL,
        expires_at TEXT NOT NULL
    )""",
    """CREATE TABLE disclosure_grants (
        grant_id TEXT PRIMARY KEY,
        subject_digest TEXT NOT NULL
            REFERENCES disclosure_grant_subjects(subject_digest),
        run_id TEXT NOT NULL REFERENCES runs(run_id),
        wait_id TEXT NOT NULL REFERENCES wait_contexts(wait_id),
        created_at TEXT NOT NULL,
        consumed_bytes INTEGER NOT NULL DEFAULT 0
            CHECK (consumed_bytes >= 0),
        status TEXT NOT NULL CHECK (status IN (
            'ACTIVE',
            'REVOKED',
            'EXPIRED',
            'EXHAUSTED'
        ))
    )""",
    """CREATE UNIQUE INDEX ux_disclosure_grants_one_grant_per_wait
        ON disclosure_grants(wait_id)""",
    """CREATE UNIQUE INDEX ux_disclosure_grants_one_active_per_subject
        ON disclosure_grants(subject_digest)
        WHERE status = 'ACTIVE'""",
)
"""The exact immutable v0003 statements; the checksum binds these bytes."""


def _apply_disclosure_grants_v1(tx: ControlTransactionV1) -> None:
    for statement in DISCLOSURE_GRANTS_V1_STATEMENTS:
        tx.execute(statement)


DISCLOSURE_GRANTS_V1_MIGRATION = MigrationV1(
    version=3,
    name="disclosure_grants_v1",
    checksum=DigestV1(
        value=migration_checksum(
            3,
            "disclosure_grants_v1",
            "\n".join(DISCLOSURE_GRANTS_V1_STATEMENTS),
        )
    ),
    apply=_apply_disclosure_grants_v1,
)
"""Immutable v0003 disclosure Grant migration consumed by Task 7.D."""

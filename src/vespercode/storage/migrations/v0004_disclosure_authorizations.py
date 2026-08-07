"""T15.2 legacy step 15.E: immutable v0004 disclosure authorization DDL.

The one table ``disclosure_authorizations`` stores the durable per-request
authorization records: primary key ``authorization_id``, FK ``grant_id ->
disclosure_grants``, the exact request identity/charge facts, the exact
body-free actual-source projection, and no refund or body column.  The
final registry composition (Task 7.D) is not editable here.
"""

from __future__ import annotations

from vespercode.contracts.evidence import DigestV1
from vespercode.storage.connection import ControlTransactionV1
from vespercode.storage.migration_engine import (
    MigrationV1,
    migration_checksum,
)

DISCLOSURE_AUTHORIZATIONS_V1_STATEMENTS: tuple[str, ...] = (
    """CREATE TABLE disclosure_authorizations (
        authorization_id TEXT PRIMARY KEY,
        grant_id TEXT NOT NULL REFERENCES disclosure_grants(grant_id),
        grant_subject_digest TEXT NOT NULL,
        llm_profile_digest TEXT NOT NULL,
        provider TEXT NOT NULL,
        endpoint_id TEXT NOT NULL,
        model TEXT NOT NULL,
        request_serializer_version TEXT NOT NULL,
        request_digest TEXT NOT NULL,
        actual_sources TEXT NOT NULL,
        canonical_byte_count INTEGER NOT NULL,
        redaction_profile_id TEXT NOT NULL,
        created_at TEXT NOT NULL
    )""",
)
"""The exact immutable v0004 statements; the checksum binds these bytes."""


def _apply_disclosure_authorizations_v1(tx: ControlTransactionV1) -> None:
    for statement in DISCLOSURE_AUTHORIZATIONS_V1_STATEMENTS:
        tx.execute(statement)


DISCLOSURE_AUTHORIZATIONS_V1_MIGRATION = MigrationV1(
    version=4,
    name="disclosure_authorizations_v1",
    checksum=DigestV1(
        value=migration_checksum(
            4,
            "disclosure_authorizations_v1",
            "\n".join(DISCLOSURE_AUTHORIZATIONS_V1_STATEMENTS),
        )
    ),
    apply=_apply_disclosure_authorizations_v1,
)
"""Immutable v0004 disclosure authorization migration consumed by Task 7.D."""

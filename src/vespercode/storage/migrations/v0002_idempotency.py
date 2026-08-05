"""T07.3 legacy step 7.C: immutable v0002 idempotency ledger DDL migration.

The one ledger table ``idempotency_events`` stores only scope/event/
request/result identities: composite primary key over ``(scope,
event_id)``, request/result digests, and no body, timestamp, or secret
columns.  The final registry composition (Task 7.D) is not editable here.
"""

from __future__ import annotations

from src.vespercode.contracts.evidence import DigestV1
from src.vespercode.storage.connection import ControlTransactionV1
from src.vespercode.storage.migration_engine import (
    MigrationV1,
    migration_checksum,
)

IDEMPOTENCY_V1_STATEMENTS: tuple[str, ...] = (
    """CREATE TABLE idempotency_events (
        scope TEXT NOT NULL,
        event_id TEXT NOT NULL,
        request_digest TEXT NOT NULL,
        result_digest TEXT NOT NULL,
        PRIMARY KEY (scope, event_id)
    )""",
)
"""The exact immutable v0002 statements; the checksum binds these bytes."""


def _apply_idempotency_v1(tx: ControlTransactionV1) -> None:
    for statement in IDEMPOTENCY_V1_STATEMENTS:
        tx.execute(statement)


IDEMPOTENCY_V1_MIGRATION = MigrationV1(
    version=2,
    name="idempotency_v1",
    checksum=DigestV1(
        value=migration_checksum(
            2,
            "idempotency_v1",
            "\n".join(IDEMPOTENCY_V1_STATEMENTS),
        )
    ),
    apply=_apply_idempotency_v1,
)
"""Immutable v0002 idempotency migration consumed by Task 7.D."""

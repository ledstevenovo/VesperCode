"""T23.1 legacy step 23.C: recovery-preserving audit retention.

``apply_audit_retention`` computes the strict 30-day cutoff from the
supplied canonical time and deletes, in deterministic bounded batches,
only audit events whose Run is explicitly ended (recorded SUCCEEDED or
STOPPED) and strictly older than the cutoff.  Every event referenced by
an unresolved recovery (any Run carrying an UNRESOLVED recovery fact)
and every active, non-ended, ambiguous, or missing-terminal Run is
preserved — missing Run rows fail closed and are never inferred as
terminal — and repeated runs are idempotent.  Active-Run clear,
transaction redesign, backup-body erasure, visibility projection, and
terminal inference remain out of scope (GREEN-4).
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from src.vespercode.audit.repository import AuditRepository
from src.vespercode.canonical.timestamp_v1 import CanonicalTimestampV1

RETENTION_DAYS = 30
"""SPEC 4.7/5.6: the default audit retention window in days."""

RETENTION_BATCH_SIZE = 100
"""The bounded deterministic deletion batch (one transaction per batch)."""

_RETENTION_DAY_MILLISECONDS = 86_400_000
_ENDED_RUN_STATUSES: frozenset[str] = frozenset({"SUCCEEDED", "STOPPED"})
"""Explicitly ended Runs: the only Runs whose old audit may be removed."""


class AuditRetentionResultV1(BaseModel):
    """One closed retention outcome with deterministic bounded counts.

    ``preserved_event_count`` counts the strictly-old candidate events
    that were examined and preserved; events not older than the cutoff
    are never candidates and are trivially untouched.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)
    cutoff: CanonicalTimestampV1
    deleted_event_count: int
    preserved_event_count: int
    batch_size: int


def apply_audit_retention(
    now: CanonicalTimestampV1,
    repository: AuditRepository,
) -> AuditRetentionResultV1:
    """Remove only strictly eligible old audit of explicitly ended Runs.

    Eligibility is fail-closed: an event is deleted only when its Run
    row exists with a recorded terminal status (SUCCEEDED or STOPPED),
    the event is strictly older than ``now - 30 days``, and the Run has
    no unresolved recovery reference in its audit trail.  Every other
    candidate (active, waiting, recovery-required, unresolved-recovery-
    referenced, ambiguous, or missing-terminal) is preserved, deletion
    proceeds in deterministic batches ordered by Run then sequence, and
    a rerun deletes nothing more.
    """
    cutoff_milliseconds = (
        now.epoch_milliseconds - RETENTION_DAYS * _RETENTION_DAY_MILLISECONDS
    )
    cutoff = CanonicalTimestampV1.from_epoch_milliseconds(cutoff_milliseconds)
    database = repository.database

    # Unresolved recovery references: any Run whose audit trail carries an
    # UNRESOLVED recovery fact keeps every one of its events, even when the
    # Run row lags to a recorded terminal status.
    unresolved_rows = database.read_rows(
        "SELECT DISTINCT run_id FROM audit_events WHERE event_type = 'RECOVERY'"
        " AND json_extract(redacted_payload, '$.disposition') = 'UNRESOLVED'"
    )
    unresolved_run_ids = {str(row[0]) for row in unresolved_rows}

    # The runs table is the endedness authority; a missing or non-terminal
    # row never proves endedness (fail closed, missing evidence is never
    # terminal evidence).
    status_rows = database.read_rows("SELECT run_id, status FROM runs")
    run_statuses = {str(row[0]): str(row[1]) for row in status_rows}

    # Canonical timestamps are zero-padded fixed-width, so the lexical
    # comparison is exact chronological order.
    candidate_rows = database.read_rows(
        "SELECT event_id, run_id, sequence FROM audit_events"
        " WHERE created_at < ? ORDER BY run_id, sequence",
        (cutoff.value,),
    )
    eligible: list[tuple[str, str]] = []
    preserved = 0
    for event_id, run_id, _sequence in candidate_rows:
        if run_id in unresolved_run_ids:
            preserved += 1
            continue
        if run_statuses.get(run_id) not in _ENDED_RUN_STATUSES:
            preserved += 1
            continue
        eligible.append((event_id, str(run_id)))

    deleted = 0
    for start in range(0, len(eligible), RETENTION_BATCH_SIZE):
        batch = eligible[start : start + RETENTION_BATCH_SIZE]
        placeholders = ",".join("?" for _ in batch)
        with database.immediate_transaction() as tx:
            tx.execute(
                f"DELETE FROM audit_events WHERE event_id IN ({placeholders})",
                tuple(event_id for event_id, _run_id in batch),
            )
        deleted += len(batch)
    return AuditRetentionResultV1(
        cutoff=cutoff,
        deleted_event_count=deleted,
        preserved_event_count=preserved,
        batch_size=RETENTION_BATCH_SIZE,
    )

"""T23.1 legacy step 23.A: transactional redacted monotonic audit repository.

``AuditRepository.append`` redacts and minimizes the allowlisted payload
before one immediate transaction, assigns the unique increasing per-Run
sequence atomically (``MAX(sequence) + 1`` with the UNIQUE backstop and
a closed overflow rejection), and records the event under the T07.3
idempotency ledger so exact replay is free and event reuse for a
different request is a conflict — every rejection leaves zero rows.
``AuditRepository.list_run`` returns bounded keyset pages in sequence
order; ``AuditRepository.clear_ended_run`` removes only the audit of
explicitly ended Runs under the ledger and never exposes removed
content.  Final registry edits, user projection, external actions, and
time-based retention remain out of scope (GREEN-4).
"""

from __future__ import annotations

import sqlite3
from typing import Annotated, Literal, TypeAlias, cast

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictStr,
    field_validator,
)

from src.vespercode.audit.event import (
    AuditErrorCodeV1,
    AuditEventTypeV1,
    AuditEventV1,
    AuditPayloadErrorV1,
    AuditPayloadInputV1,
    parse_payload,
    redact_payload,
    serialize_payload,
)
from src.vespercode.canonical.digest import domain_digest
from src.vespercode.canonical.json_v1 import CanonicalJsonErrorV1
from src.vespercode.canonical.timestamp_v1 import CanonicalTimestampV1
from src.vespercode.storage.connection import (
    ControlDatabase,
    ControlTransactionV1,
)
from src.vespercode.storage.idempotency import IdempotencyRepository

AUDIT_SEQUENCE_MAX_V1 = 2_147_483_647
"""The closed per-Run sequence bound (the 32-bit signed integer maximum).

The bound is deliberately conservative: SQLite stores integers up to
64 bits, but a per-Run sequence above the 32-bit signed maximum is
rejected as overflow.  ``MAX(sequence) + 1`` above this bound is an
overflow rejection with zero rows; the UNIQUE (run_id, sequence)
constraint is the DDL backstop.
"""

_APPEND_EVENT_SCOPE = "audit_append"
_CLEAR_EVENT_SCOPE = "audit_clear"


class _AppendRollback(Exception):
    """Internal sentinel: roll back the transaction and return the result.

    A rejection discovered inside the immediate transaction (unknown
    Run, sequence overflow) raises this sentinel so the NEW ledger record
    rolls back atomically before the closed rejection is returned (the
    same pattern as the Task 15 decision rollback and T22.1 memory).
    """

    def __init__(self, result: AuditAppendResultV1) -> None:
        super().__init__(result.message)
        self.result = result


class _ClearRollback(Exception):
    """Internal sentinel: roll back the transaction and return the result."""

    def __init__(self, result: AuditClearResultV1) -> None:
        super().__init__(result.message)
        self.result = result


def _require_non_empty_identifier(value: str) -> str:
    """Identity fields must never be empty; empty ids cannot bind."""
    if value == "":
        raise ValueError("identifiers must be non-empty")
    return value


class AppendAuditEventV1(BaseModel):
    """One closed redactable audit append command.

    Carries only the harness-observed facts (exact Run id, allowlisted
    event type, bounded raw payload, bounded evidence references, the
    replay event identity, and the observed creation time); content
    bounds, redaction, sequencing, and Run identity are enforced by the
    repository, so every rejection is a closed zero-row result.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)
    run_id: StrictStr
    event_type: AuditEventTypeV1
    payload: AuditPayloadInputV1
    evidence_refs: tuple[StrictStr, ...] = ()
    event_id: StrictStr
    created_at: CanonicalTimestampV1

    @field_validator("run_id", "event_id")
    @classmethod
    def _ids_must_be_non_empty(cls, value: str) -> str:
        return _require_non_empty_identifier(value)


AuditAppendKindV1: TypeAlias = Literal[
    "APPENDED",
    "REPLAY",
    "EVENT_ID_REUSE_CONFLICT",
    "REJECTED",
    "FAILED",
]
"""The closed outcomes of one append command."""


class AuditAppendResultV1(BaseModel):
    """One closed append outcome.

    ``error_code`` is present exactly on rejected/failed outcomes;
    ``event`` is present on appended outcomes and on replay of an event
    that still exists (a replay after an explicit clear never
    resurrects removed content and returns ``event=None``).
    """

    model_config = ConfigDict(extra="forbid", frozen=True)
    kind: AuditAppendKindV1
    message: StrictStr
    error_code: AuditErrorCodeV1 | None = None
    event: AuditEventV1 | None = None


class AuditCursorV1(BaseModel):
    """One keyset pagination cursor bound to its exact Run."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    run_id: StrictStr
    last_sequence: Annotated[int, Field(strict=True, ge=0)]


class AuditPageRequestV1(BaseModel):
    """One closed bounded page request over an exact Run's events."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    page_size: Annotated[int, Field(strict=True, ge=1, le=100)]
    cursor: AuditCursorV1 | None = None


class AuditPageV1(BaseModel):
    """One bounded ordered page of events plus the next keyset cursor."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    run_id: StrictStr
    items: tuple[AuditEventV1, ...]
    next_cursor: AuditCursorV1 | None = None


class AuditPaginationErrorV1(ValueError):
    """Closed rejection for a page cursor that does not bind the Run."""


class ClearEndedRunAuditV1(BaseModel):
    """One closed explicit clear command for an ended Run's local audit.

    Binds the exact Run, the replay event identity, and the observed
    decision time; the ended-Run authority is enforced by the
    repository, so every rejection is a closed zero-row result.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)
    run_id: StrictStr
    event_id: StrictStr
    decided_at: CanonicalTimestampV1

    @field_validator("run_id", "event_id")
    @classmethod
    def _ids_must_be_non_empty(cls, value: str) -> str:
        return _require_non_empty_identifier(value)


AuditClearKindV1: TypeAlias = Literal[
    "CLEARED",
    "REPLAY",
    "EVENT_ID_REUSE_CONFLICT",
    "REJECTED",
    "FAILED",
]
"""The closed outcomes of one clear command."""


class AuditClearResultV1(BaseModel):
    """One closed clear outcome (counts only, never removed content)."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    kind: AuditClearKindV1
    message: StrictStr
    cleared_event_count: int = 0
    error_code: AuditErrorCodeV1 | None = None


class AuditRepository:
    """Transactional redacted monotonic audit repository over v0006."""

    def __init__(self, database: ControlDatabase) -> None:
        self._database = database
        self._idempotency = IdempotencyRepository(database)

    @property
    def database(self) -> ControlDatabase:
        """The owned control database (transaction access for callers)."""
        return self._database

    @property
    def event_count(self) -> int:
        """The total number of persisted audit event rows (read-only).

        The card RED reads it as an attribute (``event_count == 0``),
        so it is a property, not a method.
        """
        return len(self._database.read_rows("SELECT 1 FROM audit_events"))

    def append(self, command: AppendAuditEventV1) -> AuditAppendResultV1:
        """Append one redacted event atomically, or reject with zero rows.

        The payload is redacted and minimized before the one immediate
        transaction; inside it the T07.3 ledger is consulted first so an
        exact replay is free, event reuse for a different request is a
        conflict, and a NEW append then revalidates the exact Run
        identity and assigns ``MAX(sequence) + 1`` in-transaction (an
        unknown Run or a sequence overflow rolls the NEW ledger record
        back with the closed rejection).  The request digest binds the
        semantic identity (Run, event type, redacted payload facts, and
        the ordered evidence references), not the volatile observed
        time, so re-sending the same event id with a different
        created_at replays the recorded outcome while a request with
        different facts or references is a conflict.
        """
        try:
            redacted = redact_payload(
                command.event_type, command.payload, command.evidence_refs
            )
        except AuditPayloadErrorV1 as exc:
            return AuditAppendResultV1(
                kind="REJECTED",
                error_code="AUDIT_STORE_FAILED",
                message=str(exc),
            )
        try:
            request_digest = domain_digest(
                "AppendAuditEventV1",
                1,
                {
                    "run_id": command.run_id,
                    "event_type": command.event_type,
                    "payload": command.payload,
                    "evidence_refs": tuple(command.evidence_refs),
                },
            )
            result_digest = domain_digest(
                "AuditAppendResultV1",
                1,
                {"run_id": command.run_id, "event_id": command.event_id},
            )
        except CanonicalJsonErrorV1:
            # A lone surrogate in an identity field cannot be canonically
            # encoded; the rejection stays closed with zero rows and no
            # ledger record (T22.1 lesson, SPEC 5.4).
            return AuditAppendResultV1(
                kind="REJECTED",
                error_code="AUDIT_STORE_FAILED",
                message="audit request cannot be encoded canonically",
            )
        try:
            with self._database.immediate_transaction() as tx:
                ledger = self._idempotency.record_or_replay(
                    tx,
                    _APPEND_EVENT_SCOPE,
                    command.event_id,
                    request_digest,
                    result_digest,
                )
                if ledger.kind == "REPLAY":
                    return AuditAppendResultV1(
                        kind="REPLAY",
                        message="audit append already recorded identically",
                        event=self._read_event_in_tx(tx, command.event_id),
                    )
                if ledger.kind == "EVENT_ID_REUSE_CONFLICT":
                    return AuditAppendResultV1(
                        kind="EVENT_ID_REUSE_CONFLICT",
                        message="audit append event id reused for a different request",
                    )
                run_row = tx.execute(
                    "SELECT 1 FROM runs WHERE run_id = ?",
                    (command.run_id,),
                ).fetchone()
                if run_row is None:
                    raise _AppendRollback(
                        AuditAppendResultV1(
                            kind="REJECTED",
                            error_code="AUDIT_STORE_FAILED",
                            message="audit run does not exist",
                        )
                    )
                sequence_row = tx.execute(
                    "SELECT COALESCE(MAX(sequence), 0) + 1 FROM audit_events"
                    " WHERE run_id = ?",
                    (command.run_id,),
                ).fetchone()
                sequence = int(sequence_row[0])
                if sequence > AUDIT_SEQUENCE_MAX_V1:
                    raise _AppendRollback(
                        AuditAppendResultV1(
                            kind="REJECTED",
                            error_code="AUDIT_STORE_FAILED",
                            message="audit sequence overflow",
                        )
                    )
                event = AuditEventV1(
                    run_id=command.run_id,
                    sequence=sequence,
                    event_type=command.event_type,
                    redacted_payload=redacted,
                    created_at=command.created_at,
                )
                tx.execute(
                    "INSERT INTO audit_events (event_id, run_id, sequence,"
                    " event_type, redacted_payload, created_at)"
                    " VALUES (?, ?, ?, ?, ?, ?)",
                    (
                        command.event_id,
                        event.run_id,
                        event.sequence,
                        event.event_type,
                        serialize_payload(event.redacted_payload),
                        event.created_at.value,
                    ),
                )
        except _AppendRollback as failure:
            # The transaction rolled back (ledger record removed too).
            return failure.result
        except Exception:
            # The transaction rolled back; the fixed message never leaks
            # raw exception text (SPEC 5.4).
            return AuditAppendResultV1(
                kind="FAILED",
                error_code="AUDIT_STORE_FAILED",
                message="audit store failed",
            )
        return AuditAppendResultV1(
            kind="APPENDED",
            message="audit event appended",
            event=event,
        )

    def list_run(
        self,
        run_id: str,
        page: AuditPageRequestV1,
    ) -> AuditPageV1:
        """One bounded ordered page of an exact Run's events.

        Keyset pagination by the per-Run sequence is stable: repeated
        walks produce the same complete ordered set with no duplicates
        or misses, and a cursor bound to another Run fails closed with
        zero partial results.
        """
        if page.cursor is not None and page.cursor.run_id != run_id:
            raise AuditPaginationErrorV1("audit page cursor belongs to another run")
        last_sequence = page.cursor.last_sequence if page.cursor is not None else 0
        rows = self._database.read_rows(
            "SELECT event_id, run_id, sequence, event_type, redacted_payload,"
            " created_at FROM audit_events WHERE run_id = ? AND sequence > ?"
            " ORDER BY sequence LIMIT ?",
            (run_id, last_sequence, page.page_size + 1),
        )
        items = tuple(self._row_to_event(row) for row in rows[: page.page_size])
        next_cursor: AuditCursorV1 | None = None
        if len(rows) > page.page_size:
            next_cursor = AuditCursorV1(
                run_id=run_id,
                last_sequence=items[-1].sequence,
            )
        return AuditPageV1(run_id=run_id, items=items, next_cursor=next_cursor)

    def clear_ended_run(self, command: ClearEndedRunAuditV1) -> AuditClearResultV1:
        """Explicitly clear one ended Run's local audit atomically.

        The T07.3 ledger makes exact replay free and event reuse for a
        different request a conflict; inside the one immediate
        transaction the ended-Run authority is revalidated (missing or
        active/non-ended Runs reject with zero rows and roll the NEW
        ledger record back), then the Run's audit rows are deleted
        together.  The closed result carries counts only and never
        exposes removed content.
        """
        try:
            request_digest = domain_digest(
                "ClearEndedRunAuditV1",
                1,
                {"run_id": command.run_id},
            )
            result_digest = domain_digest(
                "AuditClearResultV1",
                1,
                {"run_id": command.run_id},
            )
        except CanonicalJsonErrorV1:
            # A lone surrogate in the identity cannot be canonically
            # encoded; the rejection stays closed with zero rows and no
            # ledger record (T22.1 lesson, SPEC 5.4).
            return AuditClearResultV1(
                kind="REJECTED",
                error_code="AUDIT_STORE_FAILED",
                message="audit request cannot be encoded canonically",
            )
        try:
            with self._database.immediate_transaction() as tx:
                ledger = self._idempotency.record_or_replay(
                    tx,
                    _CLEAR_EVENT_SCOPE,
                    command.event_id,
                    request_digest,
                    result_digest,
                )
                if ledger.kind == "REPLAY":
                    return AuditClearResultV1(
                        kind="REPLAY",
                        message="audit clear already recorded identically",
                    )
                if ledger.kind == "EVENT_ID_REUSE_CONFLICT":
                    return AuditClearResultV1(
                        kind="EVENT_ID_REUSE_CONFLICT",
                        message="audit clear event id reused for a different request",
                    )
                run_row = tx.execute(
                    "SELECT status FROM runs WHERE run_id = ?",
                    (command.run_id,),
                ).fetchone()
                if run_row is None:
                    raise _ClearRollback(
                        AuditClearResultV1(
                            kind="REJECTED",
                            error_code="AUDIT_STORE_FAILED",
                            message="audit run does not exist",
                        )
                    )
                if str(run_row[0]) not in ("SUCCEEDED", "STOPPED"):
                    raise _ClearRollback(
                        AuditClearResultV1(
                            kind="REJECTED",
                            error_code="AUDIT_STORE_FAILED",
                            message="only ended runs can be cleared",
                        )
                    )
                cleared = tx.execute(
                    "DELETE FROM audit_events WHERE run_id = ?",
                    (command.run_id,),
                ).rowcount
        except _ClearRollback as failure:
            # The transaction rolled back (ledger record removed too).
            return failure.result
        except Exception:
            # The transaction rolled back; the fixed message never leaks
            # raw exception text (SPEC 5.4).
            return AuditClearResultV1(
                kind="FAILED",
                error_code="AUDIT_STORE_FAILED",
                message="audit store failed",
            )
        return AuditClearResultV1(
            kind="CLEARED",
            message="audit events cleared",
            cleared_event_count=cleared,
        )

    def _read_event_in_tx(
        self,
        tx: ControlTransactionV1,
        event_id: str,
    ) -> AuditEventV1 | None:
        """Read one event row inside the caller transaction."""
        rows = tx.execute(
            "SELECT event_id, run_id, sequence, event_type, redacted_payload,"
            " created_at FROM audit_events WHERE event_id = ?",
            (event_id,),
        ).fetchall()
        if not rows:
            return None
        return AuditRepository._row_to_event(rows[0])

    @staticmethod
    def _row_to_event(row: sqlite3.Row) -> AuditEventV1:
        """One audit_events row into the bounded immutable event value."""
        return AuditEventV1(
            run_id=str(row[1]),
            sequence=int(row[2]),
            event_type=cast(AuditEventTypeV1, str(row[3])),
            redacted_payload=parse_payload(str(row[4])),
            created_at=CanonicalTimestampV1.parse(str(row[5])),
        )

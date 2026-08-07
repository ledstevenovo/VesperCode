"""T24.1 legacy step 24.C: atomic feedback-to-turn consumption.

``FeedbackRepositoryV1.append`` stores Task 24.A's already validated
bounded records atomically: the feedback row itself is the replay
identity, so an exact re-append replays (REPLAY) and the same id with
different facts is an EVENT_ID_REUSE_CONFLICT that rolls the whole
sequence back (zero rows).  ``consume_feedback`` validates the turn and
the ordered reference identities and then binds every selected reference
to exactly one turn inside one compare-and-consume transaction: the
unconsumed predicate ``consumed_by_turn_id IS NULL`` makes exactly one
turn win, a different turn for an already-bound record is
ALREADY_CONSUMED with zero mutation, the identical command replays
stably through the T07.3 ledger, and missing, duplicate, forged, or
conflicted refs change nothing.  Feedback rebuilding/selection, context
assembly, adapter calls, candidate/workspace mutation, raw bodies, and
credentials remain out of scope (GREEN-4).
"""

from __future__ import annotations

import hashlib
import sqlite3
from typing import Annotated, Literal, TypeAlias

from pydantic import BaseModel, ConfigDict, Field, Strict, StrictStr

from vespercode.canonical.digest import domain_digest
from vespercode.canonical.json_v1 import CanonicalJsonErrorV1, canonical_json_bytes
from vespercode.loop.feedback import (
    FeedbackRecordSequenceV1,
    FeedbackRecordV1,
    serialize_feedback_record,
    serialize_feedback_source,
)
from vespercode.storage.connection import (
    ControlDatabase,
)
from vespercode.storage.idempotency import IdempotencyRepository

FEEDBACK_ID_MAX_BYTES_V1 = 128
"""One bounded feedback reference (mirrors the record id bound)."""

FEEDBACK_APPEND_SCOPE = "feedback_append"
FEEDBACK_CONSUME_SCOPE = "feedback_consume"

FeedbackReferenceSequenceV1: TypeAlias = tuple[str, ...]
"""The immutable ordered tuple of feedback ids (card Interface)."""

FeedbackAppendKindV1: TypeAlias = Literal[
    "APPENDED",
    "REPLAY",
    "EVENT_ID_REUSE_CONFLICT",
    "REJECTED",
    "FAILED",
]
"""The closed outcomes of one append command."""


class FeedbackAppendResultV1(BaseModel):
    """One closed append outcome (counts only, never stored content)."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    kind: FeedbackAppendKindV1
    message: StrictStr
    appended_count: Annotated[int, Strict(), Field(ge=0)] = 0


FeedbackConsumptionKindV1: TypeAlias = Literal[
    "CONSUMED",
    "REPLAY",
    "ALREADY_CONSUMED",
    "MISSING_REF",
    "TURN_NOT_FOUND",
    "DUPLICATE_REF",
    "REJECTED",
    "FAILED",
]
"""The closed outcomes of one consume command."""


class FeedbackConsumptionResultV1(BaseModel):
    """One closed consumption outcome bound to its exact turn and refs."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    kind: FeedbackConsumptionKindV1
    message: StrictStr
    turn_id: StrictStr
    consumed_refs: FeedbackReferenceSequenceV1 = ()


class _AppendRollback(Exception):
    """Internal sentinel: roll back the append transaction atomically.

    A conflict discovered inside the immediate transaction (a stored id
    reused for a different record) raises this sentinel so every insert
    of the sequence rolls back before the closed conflict is returned.
    """

    def __init__(self, result: FeedbackAppendResultV1) -> None:
        super().__init__(result.message)
        self.result = result


class _ConsumeRollback(Exception):
    """Internal sentinel: roll back the transaction and return the result.

    A rejection discovered inside the immediate transaction (missing
    turn, missing ref, already-consumed ref) raises this sentinel so the
    NEW ledger record rolls back atomically before the closed rejection
    is returned (the same pattern as the Task 15 decision, T22.1 memory,
    and T23.1 audit rollbacks).
    """

    def __init__(self, result: FeedbackConsumptionResultV1) -> None:
        super().__init__(result.message)
        self.result = result


def _require_reference(value: str) -> str:
    """One feedback reference must be non-empty and at most 128 bytes."""
    if not isinstance(value, str) or value == "":
        raise ValueError("feedback refs must be non-empty")
    try:
        encoded = value.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise ValueError(
            "feedback refs must be a sequence of Unicode scalar values"
        ) from exc
    if len(encoded) > FEEDBACK_ID_MAX_BYTES_V1:
        raise ValueError("feedback refs must be at most 128 UTF-8 bytes")
    return value


def _require_turn_id(value: str) -> str:
    """The turn identity must be non-empty and at most 128 bytes."""
    if not isinstance(value, str) or value == "":
        raise ValueError("turn ids must be non-empty")
    try:
        encoded = value.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise ValueError(
            "turn ids must be a sequence of Unicode scalar values"
        ) from exc
    if len(encoded) > FEEDBACK_ID_MAX_BYTES_V1:
        raise ValueError("turn ids must be at most 128 UTF-8 bytes")
    return value


def _consume_event_id(turn_id: str, refs: FeedbackReferenceSequenceV1) -> str:
    """The stable ledger identity of one exact consume command.

    Binds the exact turn and the canonical ordered reference tuple, so
    the identical command always replays and any turn or reference
    change is a different command.
    """
    refs_digest = hashlib.sha256(canonical_json_bytes(tuple(refs))).hexdigest()[:24]
    return f"{turn_id}:{refs_digest}"


class FeedbackRepositoryV1:
    """Transactional feedback repository over the exact v0008 schema."""

    def __init__(self, database: ControlDatabase) -> None:
        self._database = database
        self._idempotency = IdempotencyRepository(database)

    @property
    def database(self) -> ControlDatabase:
        """The owned control database (transaction access for callers)."""
        return self._database

    @staticmethod
    def _row_matches(record: FeedbackRecordV1, row: sqlite3.Row) -> bool:
        """One stored row vs the record's exact semantic facts."""
        return (
            str(row[0]) == record.kind
            and str(row[1]) == record.severity
            and str(row[2]) == record.created_at.value
            and str(row[3]) == record.summary
            and str(row[4]) == serialize_feedback_source(record.source_ref)
            and str(row[5]) == record.bounded_payload
            and str(row[6])
            == canonical_json_bytes(tuple(record.evidence_refs)).decode("utf-8")
        )

    def append(
        self,
        records: FeedbackRecordSequenceV1,
    ) -> FeedbackAppendResultV1:
        """Append one sequence of already-validated bounded records.

        The whole sequence is one atomic immediate transaction: every
        record is serialized canonically before it (surrogates reject
        with zero rows), an exact re-append of an identical record
        replays, the same id with different facts is a conflict that
        rolls the entire sequence back, and the closed result carries
        counts only — never stored content.
        """
        if not records:
            return FeedbackAppendResultV1(
                kind="REJECTED",
                message="no feedback records to append",
            )
        try:
            serialized = tuple(
                (record, serialize_feedback_record(record)) for record in records
            )
        except CanonicalJsonErrorV1:
            return FeedbackAppendResultV1(
                kind="REJECTED",
                message="feedback record cannot be encoded canonically",
            )
        appended_count = 0
        try:
            with self._database.immediate_transaction() as tx:
                for record, _text in serialized:
                    existing = tx.execute(
                        "SELECT kind, severity, created_at, summary, source_ref,"
                        " bounded_payload, evidence_refs FROM feedback_records"
                        " WHERE feedback_id = ?",
                        (record.id,),
                    ).fetchone()
                    if existing is not None:
                        if not FeedbackRepositoryV1._row_matches(record, existing):
                            raise _AppendRollback(
                                FeedbackAppendResultV1(
                                    kind="EVENT_ID_REUSE_CONFLICT",
                                    message="feedback id reused for a different record",
                                )
                            )
                        continue
                    tx.execute(
                        "INSERT INTO feedback_records (feedback_id, kind,"
                        " severity, created_at, summary, source_ref,"
                        " bounded_payload, evidence_refs, consumed_by_turn_id)"
                        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, NULL)",
                        (
                            record.id,
                            record.kind,
                            record.severity,
                            record.created_at.value,
                            record.summary,
                            serialize_feedback_source(record.source_ref),
                            record.bounded_payload,
                            canonical_json_bytes(tuple(record.evidence_refs)).decode(
                                "utf-8"
                            ),
                        ),
                    )
                    appended_count += 1
        except _AppendRollback as failure:
            # The transaction rolled back; every insert of the sequence
            # is removed together.
            return failure.result
        except Exception:
            # The transaction rolled back; the fixed message never leaks
            # raw exception text (SPEC 5.4).
            return FeedbackAppendResultV1(
                kind="FAILED",
                message="feedback append failed",
            )
        if appended_count == 0:
            return FeedbackAppendResultV1(
                kind="REPLAY",
                message="feedback records already appended identically",
            )
        return FeedbackAppendResultV1(
            kind="APPENDED",
            message="feedback records appended",
            appended_count=appended_count,
        )


def consume_feedback(
    turn_id: str,
    refs: FeedbackReferenceSequenceV1,
    repository: FeedbackRepositoryV1,
) -> FeedbackConsumptionResultV1:
    """Bind one ordered reference tuple to exactly one turn atomically.

    The turn and the ordered reference identities are validated before
    one compare-and-consume transaction: each unconsumed reference is
    bound through ``UPDATE ... WHERE consumed_by_turn_id IS NULL`` with
    a row-count check, so exactly one turn wins, a different turn for an
    already-bound record is ALREADY_CONSUMED, the identical command
    replays stably through the T07.3 ledger, and missing, duplicate,
    forged, or conflicted refs change nothing (the whole transaction
    rolls back, the NEW ledger record included).
    """
    try:
        validated_turn = _require_turn_id(turn_id)
        validated_refs = tuple(_require_reference(ref) for ref in refs)
    except ValueError as exc:
        return FeedbackConsumptionResultV1(
            kind="REJECTED",
            message=str(exc),
            turn_id=turn_id,
        )
    if not validated_refs:
        return FeedbackConsumptionResultV1(
            kind="REJECTED",
            message="at least one feedback reference is required",
            turn_id=validated_turn,
        )
    if len(set(validated_refs)) != len(validated_refs):
        return FeedbackConsumptionResultV1(
            kind="DUPLICATE_REF",
            message="feedback references must be unique",
            turn_id=validated_turn,
        )
    try:
        request_digest = domain_digest(
            "ConsumeFeedbackV1",
            1,
            {"turn_id": validated_turn, "refs": tuple(validated_refs)},
        )
        result_digest = domain_digest(
            "FeedbackConsumptionResultV1",
            1,
            {"turn_id": validated_turn, "refs": tuple(validated_refs)},
        )
        event_id = _consume_event_id(validated_turn, validated_refs)
    except CanonicalJsonErrorV1:
        return FeedbackConsumptionResultV1(
            kind="REJECTED",
            message="consume command cannot be encoded canonically",
            turn_id=validated_turn,
        )
    try:
        with repository.database.immediate_transaction() as tx:
            ledger = repository._idempotency.record_or_replay(
                tx,
                FEEDBACK_CONSUME_SCOPE,
                event_id,
                request_digest,
                result_digest,
            )
            if ledger.kind == "REPLAY":
                return FeedbackConsumptionResultV1(
                    kind="REPLAY",
                    message="feedback consumption already recorded identically",
                    turn_id=validated_turn,
                    consumed_refs=validated_refs,
                )
            if ledger.kind == "EVENT_ID_REUSE_CONFLICT":
                # Unreachable for the deterministic command identity (a
                # SHA-256 collision); the outcome stays closed and
                # mutation-free.
                raise _ConsumeRollback(
                    FeedbackConsumptionResultV1(
                        kind="FAILED",
                        message="consume command identity conflict",
                        turn_id=validated_turn,
                    )
                )
            turn_row = tx.execute(
                "SELECT 1 FROM agent_turns WHERE turn_id = ?",
                (validated_turn,),
            ).fetchone()
            if turn_row is None:
                raise _ConsumeRollback(
                    FeedbackConsumptionResultV1(
                        kind="TURN_NOT_FOUND",
                        message="turn does not exist",
                        turn_id=validated_turn,
                    )
                )
            placeholders = ",".join("?" for _ in validated_refs)
            found = tx.execute(
                f"SELECT COUNT(*) FROM feedback_records"
                f" WHERE feedback_id IN ({placeholders})",
                tuple(validated_refs),
            ).fetchone()
            if int(found[0]) != len(validated_refs):
                raise _ConsumeRollback(
                    FeedbackConsumptionResultV1(
                        kind="MISSING_REF",
                        message="one or more feedback refs do not exist",
                        turn_id=validated_turn,
                    )
                )
            for ref in validated_refs:
                updated = tx.execute(
                    "UPDATE feedback_records SET consumed_by_turn_id = ?"
                    " WHERE feedback_id = ? AND consumed_by_turn_id IS NULL",
                    (validated_turn, ref),
                )
                if updated.rowcount != 1:
                    raise _ConsumeRollback(
                        FeedbackConsumptionResultV1(
                            kind="ALREADY_CONSUMED",
                            message="feedback record is already consumed",
                            turn_id=validated_turn,
                        )
                    )
    except _ConsumeRollback as failure:
        # The transaction rolled back (the NEW ledger record too).
        return failure.result
    except Exception:
        # The transaction rolled back; the fixed message never leaks
        # raw exception text (SPEC 5.4).
        return FeedbackConsumptionResultV1(
            kind="FAILED",
            message="feedback consumption failed",
            turn_id=validated_turn,
        )
    return FeedbackConsumptionResultV1(
        kind="CONSUMED",
        message="feedback records consumed by the turn",
        turn_id=validated_turn,
        consumed_refs=validated_refs,
    )

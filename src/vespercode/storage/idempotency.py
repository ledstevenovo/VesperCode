"""T07.3 legacy step 7.C: transaction-bound idempotency ledger repository.

``IdempotencyRepository.record_or_replay`` records scope/event/request/
result identities only inside the caller-owned Task 7.A transaction: the
first identity returns ``NEW``, an identical request replays the recorded
first result without domain mutation, and a different request for the
same event id returns ``EVENT_ID_REUSE_CONFLICT`` without mutation.
Final registry edits, domain-result reconstruction, Run transitions, and
replay/conflict mutation remain out of scope (GREEN-4).
"""

from __future__ import annotations

import re
import sqlite3
from typing import Literal

from pydantic import BaseModel, ConfigDict, StrictStr

from src.vespercode.storage.connection import (
    ControlDatabase,
    ControlTransactionV1,
)

_DIGEST_RE = re.compile(r"[0-9a-f]{64}")


class IdempotencyResultV1(BaseModel):
    """One closed ledger outcome; ``result_digest`` is the recorded identity."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    kind: Literal["NEW", "REPLAY", "EVENT_ID_REUSE_CONFLICT"]
    result_digest: StrictStr


class IdempotencyRepository:
    """Transaction-bound ledger over the exact v0002 idempotency_events."""

    def __init__(self, database: ControlDatabase) -> None:
        # The ledger methods operate on the caller-owned transaction; the
        # database is the repository's construction binding (mirrors the
        # Run repository) and its future read/introspection home.
        self._database = database

    def record_or_replay(
        self,
        tx: ControlTransactionV1,
        scope: str,
        event_id: str,
        request_digest: str,
        result_digest: str,
    ) -> IdempotencyResultV1:
        """Record one identity or replay/conflict on the recorded one.

        Runs entirely inside *tx*: a rollback of the caller transaction
        removes the recording, and replay/conflict never mutate the
        ledger or any domain state.
        """
        if not isinstance(scope, str) or scope == "":
            raise ValueError("scope must be non-empty")
        if not isinstance(event_id, str) or event_id == "":
            raise ValueError("event_id must be non-empty")
        if (
            not isinstance(request_digest, str)
            or _DIGEST_RE.fullmatch(request_digest) is None
        ):
            raise ValueError("request_digest must be exactly 64 lowercase hex")
        if (
            not isinstance(result_digest, str)
            or _DIGEST_RE.fullmatch(result_digest) is None
        ):
            raise ValueError("result_digest must be exactly 64 lowercase hex")

        recorded = tx.execute(
            "SELECT request_digest, result_digest FROM idempotency_events"
            " WHERE scope = ? AND event_id = ?",
            (scope, event_id),
        ).fetchone()
        if recorded is not None:
            return self._replay_or_conflict(
                str(recorded[0]), str(recorded[1]), request_digest
            )
        try:
            tx.execute(
                "INSERT INTO idempotency_events"
                " (scope, event_id, request_digest, result_digest)"
                " VALUES (?, ?, ?, ?)",
                (scope, event_id, request_digest, result_digest),
            )
        except sqlite3.IntegrityError:
            # A competing writer inserted the identity between the select
            # and the insert (serialized by BEGIN IMMEDIATE, so this only
            # covers a same-transaction repeat); fall back to the recorded
            # row so the outcome stays closed and mutation-free.
            recorded = tx.execute(
                "SELECT request_digest, result_digest FROM idempotency_events"
                " WHERE scope = ? AND event_id = ?",
                (scope, event_id),
            ).fetchone()
            if recorded is not None:
                return self._replay_or_conflict(
                    str(recorded[0]), str(recorded[1]), request_digest
                )
            raise
        return IdempotencyResultV1(kind="NEW", result_digest=result_digest)

    def _replay_or_conflict(
        self,
        recorded_request: str,
        recorded_result: str,
        request_digest: str,
    ) -> IdempotencyResultV1:
        if recorded_request == request_digest:
            return IdempotencyResultV1(
                kind="REPLAY",
                result_digest=recorded_result,
            )
        return IdempotencyResultV1(
            kind="EVENT_ID_REUSE_CONFLICT",
            result_digest=recorded_result,
        )

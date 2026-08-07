"""T15.2 legacy step 15.F: exact active disclosure Grant revocation.

``DisclosureRevocationServiceV1.revoke`` binds the revocation to the exact
ACTIVE Grant, Run, subject digest, and idempotency event (reusing the
T07.3 ledger) inside one immediate transaction before transitioning the
matching Grant ACTIVE → REVOKED exactly once.  Stale, mismatched,
already-revoked, expired, exhausted, or event-reused commands are
deterministic and mutate no unrelated Grant; the exact replay of a
successful revocation returns the recorded event outcome.  Wait
decisions, Grant creation, request authorization, byte charging, body
storage, and committed-charge refunds remain out of scope (GREEN-4).
"""

from __future__ import annotations

from typing import Literal, TypeAlias

from pydantic import BaseModel, ConfigDict, StrictStr

from vespercode.canonical.digest import domain_digest
from vespercode.canonical.timestamp_v1 import CanonicalTimestampV1
from vespercode.contracts.evidence import DigestV1
from vespercode.storage.connection import ControlDatabase
from vespercode.storage.idempotency import IdempotencyRepository

_REVOKE_EVENT_SCOPE = "disclosure_revoke"

GrantMutationKindV1: TypeAlias = Literal[
    "REVOKED",
    "SUBJECT_MISMATCH",
    "RUN_MISMATCH",
    "ALREADY_REVOKED",
    "NOT_FOUND",
    "EXPIRED",
    "EXHAUSTED",
    "REPLAY",
    "REPLAY_CONFLICT",
]
"""The closed outcomes of one revocation command."""


class RevokeDisclosureGrantV1(BaseModel):
    """One closed revocation command exactly bound to its Grant/event."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    grant_id: StrictStr
    run_id: StrictStr
    subject_digest: DigestV1
    event_id: StrictStr
    revoked_at: CanonicalTimestampV1


class GrantMutationResultV1(BaseModel):
    """One closed revocation outcome with a stable reason."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    kind: GrantMutationKindV1
    message: StrictStr


class _RevocationRollback(Exception):
    """Internal sentinel: roll back the transaction and return the result.

    The immediate-transaction context manager commits on clean exit and
    rolls back only on an exception; a rejected revocation must not
    persist the idempotency event row it reserved, so the sentinel rolls
    the whole transaction back before the result is returned.
    """

    def __init__(self, result: GrantMutationResultV1) -> None:
        super().__init__(result.message)
        self.result = result


def _revoke_request_digest(command: RevokeDisclosureGrantV1) -> str:
    """The §0.1 identity of one exact revocation request.

    The grant, run, subject, and revocation instant all bind the event, so
    the same event id with any different request fact is a replay
    conflict.
    """
    return domain_digest(
        "DisclosureGrantRevokeRequestV1",
        1,
        {
            "grant_id": command.grant_id,
            "run_id": command.run_id,
            "subject_digest": command.subject_digest.value,
            "revoked_at": command.revoked_at.value,
        },
    )


def _revoke_result_digest(command: RevokeDisclosureGrantV1) -> str:
    """The §0.1 identity of the recorded REVOKED outcome."""
    return domain_digest(
        "DisclosureGrantRevokeResultV1",
        1,
        {"kind": "REVOKED", "grant_id": command.grant_id},
    )


class DisclosureRevocationServiceV1:
    """Transaction-bound active-to-revoked Grant mutation."""

    def __init__(self, database: ControlDatabase) -> None:
        self._database = database
        self._ledger = IdempotencyRepository(database)

    @property
    def database(self) -> ControlDatabase:
        """The owned control database (transaction access for callers)."""
        return self._database

    def active_grant_count(self) -> int:
        """The number of ACTIVE Grant rows (read-only)."""
        return len(
            self._database.read_rows(
                "SELECT 1 FROM disclosure_grants WHERE status = 'ACTIVE'"
            )
        )

    def revoke(self, command: RevokeDisclosureGrantV1) -> GrantMutationResultV1:
        """Revoke exactly the matching ACTIVE Grant, or fail closed.

        The idempotency event is bound first (its ledger row commits only
        with the successful revocation — any rejected command rolls the
        event row back), then the Grant's run/subject/status are compared
        inside the same transaction, and finally the ACTIVE → REVOKED
        compare-and-update runs exactly once.
        """
        try:
            with self._database.immediate_transaction() as tx:
                recorded = self._ledger.record_or_replay(
                    tx,
                    _REVOKE_EVENT_SCOPE,
                    command.event_id,
                    _revoke_request_digest(command),
                    _revoke_result_digest(command),
                )
                if recorded.kind == "REPLAY":
                    return GrantMutationResultV1(
                        kind="REPLAY",
                        message="revocation event already recorded",
                    )
                if recorded.kind == "EVENT_ID_REUSE_CONFLICT":
                    return GrantMutationResultV1(
                        kind="REPLAY_CONFLICT",
                        message="revocation event reused for a different request",
                    )
                row = tx.execute(
                    "SELECT grant_id, subject_digest, run_id, wait_id, created_at,"
                    " consumed_bytes, status FROM disclosure_grants"
                    " WHERE grant_id = ?",
                    (command.grant_id,),
                ).fetchone()
                if row is None:
                    raise _RevocationRollback(
                        GrantMutationResultV1(
                            kind="NOT_FOUND", message="grant does not exist"
                        )
                    )
                grant_run = str(row[2])
                grant_subject = str(row[1])
                grant_status = str(row[6])
                if grant_run != command.run_id:
                    raise _RevocationRollback(
                        GrantMutationResultV1(
                            kind="RUN_MISMATCH",
                            message="grant belongs to a different run",
                        )
                    )
                if grant_subject != command.subject_digest.value:
                    raise _RevocationRollback(
                        GrantMutationResultV1(
                            kind="SUBJECT_MISMATCH",
                            message="grant subject does not match the command subject",
                        )
                    )
                if grant_status == "REVOKED":
                    raise _RevocationRollback(
                        GrantMutationResultV1(
                            kind="ALREADY_REVOKED",
                            message="grant already revoked",
                        )
                    )
                if grant_status == "EXPIRED":
                    raise _RevocationRollback(
                        GrantMutationResultV1(
                            kind="EXPIRED", message="grant already expired"
                        )
                    )
                if grant_status == "EXHAUSTED":
                    raise _RevocationRollback(
                        GrantMutationResultV1(
                            kind="EXHAUSTED", message="grant already exhausted"
                        )
                    )
                updated = tx.execute(
                    "UPDATE disclosure_grants SET status = 'REVOKED'"
                    " WHERE grant_id = ? AND status = 'ACTIVE'",
                    (command.grant_id,),
                ).rowcount
                if updated != 1:
                    raise _RevocationRollback(
                        GrantMutationResultV1(
                            kind="ALREADY_REVOKED",
                            message="grant revocation lost the active-state race",
                        )
                    )
                return GrantMutationResultV1(kind="REVOKED", message="grant revoked")
        except _RevocationRollback as failure:
            return failure.result

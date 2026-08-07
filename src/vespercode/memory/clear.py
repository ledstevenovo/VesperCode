"""T22.1 legacy step 22.C: transactional authorized memory clear.

``MemoryClearService.clear`` validates the explicit user authority, the
exact workspace identity, the command/replay identity, and the target
scope before entering one atomic tombstone transaction: the T07.3
idempotency ledger makes exact replay free and event-id reuse for a
different request a conflict, and the targeted eligibility changes
(tombstone pair) commit together so every future selection excludes the
targeted entries immediately.  The request digest binds the semantic
identity (workspace, sorted targets, creator), not the volatile
observed time, so re-sending the same event id with a different
``decided_at`` replays the recorded outcome.  Forged, cross-workspace,
unknown-target, and mid-transaction partial failures change nothing;
already-cleared targets stay immutable and other workspaces are never
touched.  Immutable audit/source facts, creation/selection policy, and
retention remain out of scope (GREEN-4).
"""

from __future__ import annotations

import sqlite3
from typing import Literal, TypeAlias

from pydantic import BaseModel, ConfigDict, Field, StrictStr

from vespercode.canonical.digest import domain_digest
from vespercode.canonical.timestamp_v1 import CanonicalTimestampV1
from vespercode.memory.entry import (
    MemoryCreatorV1,
    MemoryErrorCodeV1,
)
from vespercode.memory.repository import MemoryRepository
from vespercode.storage.connection import ControlDatabase
from vespercode.storage.idempotency import IdempotencyRepository

_CLEAR_EVENT_SCOPE = "memory_clear"
_CLEAR_TARGET_MAX = 100


class ClearMemoryCommandV1(BaseModel):
    """One closed authorized memory clear command.

    Binds the exact workspace identity, the explicit user creator, the
    replay event identity, the bounded target entry set, and the
    observed decision time; nothing else may influence the outcome.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)
    workspace_identity: StrictStr
    creator: MemoryCreatorV1
    event_id: StrictStr
    target_entry_ids: tuple[StrictStr, ...] = Field(min_length=1, max_length=100)
    decided_at: CanonicalTimestampV1


MemoryClearKindV1: TypeAlias = Literal[
    "CLEARED",
    "REPLAY",
    "EVENT_ID_REUSE_CONFLICT",
    "REJECTED",
    "FAILED",
]
"""The closed outcomes of one clear command."""


class MemoryClearResultV1(BaseModel):
    """One closed memory clear outcome.

    ``cleared_count`` counts the entries whose tombstone was newly
    committed by this transaction; ``error_code`` is present exactly on
    rejected/failed outcomes.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)
    kind: MemoryClearKindV1
    message: StrictStr
    cleared_count: int = 0
    error_code: MemoryErrorCodeV1 | None = None


class MemoryClearService:
    """Transaction-bound memory clear service over the v0005 schema."""

    def __init__(
        self,
        database: ControlDatabase,
        repository: MemoryRepository,
    ) -> None:
        self._database = database
        self._repository = repository
        self._idempotency = IdempotencyRepository(database)

    def clear(self, command: ClearMemoryCommandV1) -> MemoryClearResultV1:
        """Clear the exact targeted workspace entries atomically.

        Authority, exact workspace identity, replay identity, and target
        scope are validated before the one immediate transaction; inside
        it the ledger recording and the tombstone updates commit
        together, so replay is free, conflicts are mutation-free, and
        any mid-transaction failure rolls the whole batch back.
        """
        if command.creator != "USER":
            return MemoryClearResultV1(
                kind="REJECTED",
                error_code="MEMORY_CREATOR_FORBIDDEN",
                message="only the user can clear memory",
            )
        if not command.event_id:
            return MemoryClearResultV1(
                kind="REJECTED",
                error_code="MEMORY_CONTENT_REJECTED",
                message="clear event id must be non-empty",
            )
        scope_error = self._target_scope_error(command)
        if scope_error is not None:
            return scope_error
        request_digest = domain_digest(
            "ClearMemoryCommandV1",
            1,
            {
                "workspace_identity": command.workspace_identity,
                "target_entry_ids": tuple(sorted(command.target_entry_ids)),
                "creator": command.creator,
            },
        )
        result_digest = domain_digest(
            "MemoryClearResultV1",
            1,
            {
                "workspace_identity": command.workspace_identity,
                "target_entry_ids": tuple(sorted(command.target_entry_ids)),
            },
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
                    return MemoryClearResultV1(
                        kind="REPLAY",
                        message="clear already recorded identically",
                    )
                if ledger.kind == "EVENT_ID_REUSE_CONFLICT":
                    return MemoryClearResultV1(
                        kind="EVENT_ID_REUSE_CONFLICT",
                        message="clear event id reused for a different request",
                    )
                cleared = 0
                for target in command.target_entry_ids:
                    cleared += tx.execute(
                        "UPDATE memory_entries SET cleared_at = ?,"
                        " clear_transaction_id = ? WHERE entry_id = ?"
                        " AND workspace_identity = ? AND cleared_at IS NULL",
                        (
                            command.decided_at.value,
                            command.event_id,
                            target,
                            command.workspace_identity,
                        ),
                    ).rowcount
        except sqlite3.Error:
            # The transaction rolled back (tombstones and ledger together);
            # the fixed message never leaks raw exception text (SPEC 5.4).
            return MemoryClearResultV1(
                kind="FAILED",
                error_code="MEMORY_STORE_FAILED",
                message="memory store failed",
            )
        return MemoryClearResultV1(
            kind="CLEARED",
            message="memory entries cleared",
            cleared_count=cleared,
        )

    def _target_scope_error(
        self,
        command: ClearMemoryCommandV1,
    ) -> MemoryClearResultV1 | None:
        """The pre-transaction target-scope validation of one clear.

        Every target must exist and belong to the exact workspace
        identity; any out-of-scope target rejects the whole command with
        zero rows (SPEC 4.7 MEMORY_SCOPE_VIOLATION).
        """
        placeholders = ",".join("?" for _ in command.target_entry_ids)
        rows = self._database.read_rows(
            "SELECT entry_id, workspace_identity FROM memory_entries"
            f" WHERE entry_id IN ({placeholders})",
            command.target_entry_ids,
        )
        workspaces = {str(row[0]): str(row[1]) for row in rows}
        for target in command.target_entry_ids:
            if target not in workspaces:
                return MemoryClearResultV1(
                    kind="REJECTED",
                    error_code="MEMORY_SCOPE_VIOLATION",
                    message="clear target entry does not exist",
                )
            if workspaces[target] != command.workspace_identity:
                return MemoryClearResultV1(
                    kind="REJECTED",
                    error_code="MEMORY_SCOPE_VIOLATION",
                    message="clear target entry belongs to another workspace",
                )
        return None

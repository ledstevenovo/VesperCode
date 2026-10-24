"""Route A / A3: durable transaction recovery.

A writeback fault leaves a durable, non-terminal transaction (``PREPARED``,
``WRITING``, or ``UNRESOLVED``) plus a journal of intended writes and
observed originals in the v2 database.  ``V2RecoveryService`` restarts
from that state alone:

- ``preview`` compares each journal row against the workspace with
  ordinary byte comparison and classifies the target as ``APPLIED``,
  ``PENDING``, ``DRIFTED`` (matches neither the journal nor its
  original), or ``UNREADABLE`` (the port refuses the path);
- ``apply`` completes pending writes through the boundary-checked port
  and rolls the state through the legal map to ``COMMITTED``;
- ``rollback`` restores recorded originals (restoring replaced content,
  removing created files) and records ``ROLLED_BACK``; restores publish
  through planned writes, so an externally modified target is refused
  rather than overwritten, and the removal of a created file is bound to
  the journaled bytes, so externally changed content is refused rather
  than deleted;
- drift or unreadable targets block both paths fail-closed instead of
  guessing over externally modified bytes.

All decisions come from the durable database and byte comparison; nothing
in memory is required, so a fresh process recovers a crashed run.
"""

from __future__ import annotations

import sqlite3

from vespercode.contracts.v2_writeback import (
    ACTIVE_TRANSACTION_STATES,
    JournalEntryV2,
    RecoveryItemV2,
    RecoveryOutcomeV2,
    RecoveryPreviewV2,
    WorkspaceContentMismatchError,
)
from vespercode.storage.v2_database import V2Database, V2DatabaseError


class V2RecoveryService:
    """Restart-safe recovery for non-terminal writeback transactions."""

    def __init__(self, database: V2Database, port: object) -> None:
        self._database = database
        self._port = port

    def pending_transaction_ids(self) -> tuple[str, ...]:
        """Every non-terminal transaction awaiting recovery, oldest first."""

        return tuple(
            str(row["transaction_id"])
            for row in self._database.list_transactions_in_states(
                tuple(sorted(ACTIVE_TRANSACTION_STATES))
            )
        )

    def preview(self, transaction_id: str) -> RecoveryPreviewV2:
        """Report the byte-comparison verdict for every journal row."""

        transaction, entries = self._load_active(transaction_id)
        items = tuple(self._item(entry) for entry in entries)
        return RecoveryPreviewV2(
            transaction_id,
            str(transaction["state"]),
            items,
            any(item.state in {"DRIFTED", "UNREADABLE"} for item in items),
        )

    def apply(self, transaction_id: str) -> RecoveryOutcomeV2:
        """Complete the pending writes and commit the transaction."""

        transaction, entries = self._load_active(transaction_id)
        items = tuple(self._item(entry) for entry in entries)
        if any(item.state in {"DRIFTED", "UNREADABLE"} for item in items):
            return RecoveryOutcomeV2(
                "BLOCKED",
                transaction_id,
                "recovery is blocked by drifted or unreadable targets",
            )
        state = str(transaction["state"])
        if state in ("PREPARED", "UNRESOLVED"):
            if not self._database.transition_transaction(
                transaction_id, from_state=state, to_state="WRITING"
            ):
                return RecoveryOutcomeV2(
                    "FAILED",
                    transaction_id,
                    "transaction changed state during recovery",
                )
        try:
            for entry, item in zip(entries, items):
                if item.state == "PENDING":
                    self._port.apply(entry.planned())  # type: ignore[attr-defined]
        except WorkspaceContentMismatchError:
            try:
                self._database.transition_transaction(
                    transaction_id, from_state="WRITING", to_state="UNRESOLVED"
                )
            except V2DatabaseError:
                pass
            return RecoveryOutcomeV2(
                "FAILED",
                transaction_id,
                "external change detected during recovery; "
                "transaction remains UNRESOLVED",
            )
        except Exception:
            try:
                self._database.transition_transaction(
                    transaction_id, from_state="WRITING", to_state="UNRESOLVED"
                )
            except V2DatabaseError:
                pass
            return RecoveryOutcomeV2(
                "FAILED",
                transaction_id,
                "recovery write fault; transaction remains UNRESOLVED",
            )
        if not self._database.transition_transaction(
            transaction_id, from_state="WRITING", to_state="COMMITTED"
        ):
            return RecoveryOutcomeV2(
                "FAILED",
                transaction_id,
                "transaction could not commit during recovery",
            )
        return RecoveryOutcomeV2(
            "APPLIED", transaction_id, f"{len(entries)} journal write(s) applied"
        )

    def rollback(self, transaction_id: str) -> RecoveryOutcomeV2:
        """Restore recorded originals and record ROLLED_BACK."""

        transaction, entries = self._load_active(transaction_id)
        items = tuple(self._item(entry) for entry in entries)
        if any(item.state in {"DRIFTED", "UNREADABLE"} for item in items):
            return RecoveryOutcomeV2(
                "BLOCKED",
                transaction_id,
                "recovery is blocked by drifted or unreadable targets",
            )
        try:
            for entry, item in zip(entries, items):
                if item.state != "APPLIED":
                    continue
                if entry.action_type == "CREATE":
                    # Compare-and-delete: the removal is bound to the
                    # journaled bytes, so externally changed content is
                    # refused instead of deleted.
                    self._port.remove_expected(entry.path, entry.content)  # type: ignore[attr-defined]
                else:
                    self._port.apply(entry.planned_restore())  # type: ignore[attr-defined]
        except WorkspaceContentMismatchError:
            return RecoveryOutcomeV2(
                "FAILED",
                transaction_id,
                "external change detected during rollback; "
                "transaction remains non-terminal",
            )
        except Exception:
            return RecoveryOutcomeV2(
                "FAILED",
                transaction_id,
                "rollback fault; transaction remains non-terminal",
            )
        if not self._database.transition_transaction(
            transaction_id, from_state=str(transaction["state"]), to_state="ROLLED_BACK"
        ):
            return RecoveryOutcomeV2(
                "FAILED",
                transaction_id,
                "transaction could not enter ROLLED_BACK",
            )
        return RecoveryOutcomeV2(
            "ROLLED_BACK",
            transaction_id,
            f"{len(entries)} journal write(s) rolled back",
        )

    def _load_active(
        self, transaction_id: str
    ) -> tuple[sqlite3.Row, tuple[JournalEntryV2, ...]]:
        transaction = self._database.get_transaction(transaction_id)
        if (
            transaction is None
            or str(transaction["state"]) not in ACTIVE_TRANSACTION_STATES
        ):
            raise ValueError("recovery requires a non-terminal transaction")
        rows = self._database.get_transaction_journal(transaction_id)
        # A corrupted journal must fail closed before any state advance:
        # an empty journal, a row bound to a different transaction, or
        # positions that are not contiguous from zero mean the write
        # plan cannot be verified, so preview/apply/rollback all refuse
        # it.  The messages are static; no journal content is leaked.
        if not rows:
            raise ValueError(
                "transaction journal is empty or corrupted; refusing recovery"
            )
        entries = []
        for expected_position, row in enumerate(rows):
            if int(row["position"]) != expected_position:
                raise ValueError(
                    "transaction journal positions are corrupted; refusing recovery"
                )
            if str(row["transaction_id"]) != transaction_id:
                raise ValueError(
                    "transaction journal row is bound to a different "
                    "transaction; refusing recovery"
                )
            # JournalEntryV2 validates action types and original-content
            # shapes, refusing the remaining malformed forms.
            entries.append(
                JournalEntryV2(
                    int(row["position"]),
                    str(row["path"]),
                    str(row["action_type"]),
                    str(row["content"]),
                    None
                    if row["original_content"] is None
                    else str(row["original_content"]),
                )
            )
        return transaction, tuple(entries)

    def _item(self, entry: JournalEntryV2) -> RecoveryItemV2:
        return RecoveryItemV2(
            entry.position,
            entry.path,
            entry.action_type,
            self._entry_state(entry),
        )

    def _entry_state(self, entry: JournalEntryV2) -> str:
        try:
            current = self._port.read_text(entry.path)  # type: ignore[attr-defined]
        except Exception:
            return "UNREADABLE"
        if current == entry.content:
            return "APPLIED"
        if current == entry.original_content:
            return "PENDING"
        return "DRIFTED"


__all__ = ["V2RecoveryService"]

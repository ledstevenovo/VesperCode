"""Route A / A2: explicit, approval-bound atomic writeback.

``V2WritebackService`` is the only component that turns staged candidate
content into real workspace writes.  It fails closed at every step:

1. candidate freshness — the control-plane revision must match the request;
2. approval — an explicit, pending, matching, unconsumed user approval;
3. policy — the relaxed governance policy re-evaluates every target;
4. secret-content gate — staged content and observed originals are
   scanned by a deterministic conservative marker scanner, so nothing
   that looks like a credential enters the journal;
5. strict targets — CREATE targets must be absent, REPLACE targets must
   be readable existing files;
6. atomic begin — the approval is consumed and the journal (intended
   writes plus observed originals) is committed in one SQLite
   transaction;
7. apply — each write goes through the injected workspace port as a
   ``PlannedWriteV2``: the target is rechecked immediately before the
   mutation and, for REPLACE, must still hold exactly the journaled
   original bytes, so an external change is refused (FAILED/UNRESOLVED)
   instead of overwritten;
8. durable states — PREPARED -> WRITING -> COMMITTED, or UNRESOLVED on a
   fault, leaving a recovery-previewable journal instead of guessing.

Validation happens entirely before any write, so stale, mismatched,
denied, or secret-bearing requests leave zero writes and an untouched
approval.
"""

from __future__ import annotations

from pathlib import Path

from vespercode.contracts.v2_writeback import (
    JournalEntryV2,
    WorkspaceContentMismatchError,
    WritebackOutcomeV2,
    WritebackRequestV2,
)
from vespercode.governance.v2_secret_scanner import find_secret_marker
from vespercode.governance.relaxed_policy import (
    ActionRequestV2,
    DecisionV2,
    RelaxedPolicyV2,
)
from vespercode.storage.v2_database import V2Database, V2DatabaseError


class V2WritebackService:
    """Atomic CREATE/REPLACE writeback gated by an explicit approval."""

    def __init__(
        self,
        database: V2Database,
        port: object,
        *,
        workspace: Path,
        policy: RelaxedPolicyV2 | None = None,
    ) -> None:
        if not isinstance(workspace, Path):
            raise TypeError("workspace must be a Path")
        if not workspace.is_dir():
            raise ValueError("workspace must be an existing directory")
        self._database = database
        self._port = port
        self._workspace = workspace
        self._policy = policy or RelaxedPolicyV2()

    def request_writeback(self, request: WritebackRequestV2) -> WritebackOutcomeV2:
        candidate = self._database.get_candidate(request.candidate_id)
        if candidate is None or str(candidate["run_id"]) != request.run_id:
            return WritebackOutcomeV2(
                "DENIED", None, "unknown candidate for this run"
            )
        if int(candidate["revision"]) != request.candidate_revision:
            return WritebackOutcomeV2(
                "STALE", None, "candidate revision is stale"
            )
        approval = self._database.get_writeback_approval(request.approval_id)
        if (
            approval is None
            or str(approval["status"]) != "PENDING"
            or str(approval["candidate_id"]) != request.candidate_id
            or int(approval["candidate_revision"]) != request.candidate_revision
        ):
            return WritebackOutcomeV2(
                "DENIED",
                None,
                "writeback approval is missing, consumed, or mismatched",
            )
        paths = [operation.path for operation in request.operations]
        if len(set(paths)) != len(paths):
            return WritebackOutcomeV2(
                "DENIED", None, "duplicate target paths in one writeback"
            )
        for operation in request.operations:
            decision = self._policy.evaluate(
                ActionRequestV2(operation.action_type, operation.path, self._workspace)
            )
            if decision is DecisionV2.DENY:
                return WritebackOutcomeV2(
                    "DENIED", None, f"policy denied write to {operation.path}"
                )
        # Secret-content gate: nothing that looks like a credential may be
        # journaled into the control database.  This runs before any port
        # write, before the approval is consumed, and before a transaction
        # exists; the refusal message never contains the matched material.
        for operation in request.operations:
            if find_secret_marker(operation.content) is not None:
                return WritebackOutcomeV2(
                    "DENIED", None, f"secret-like content refused: {operation.path}"
                )
        entries: list[JournalEntryV2] = []
        for position, operation in enumerate(request.operations):
            try:
                self._port.validate(operation)  # type: ignore[attr-defined]
                current = self._port.read_text(operation.path)  # type: ignore[attr-defined]
            except Exception:
                return WritebackOutcomeV2(
                    "MISMATCH",
                    None,
                    f"target is not a valid {operation.action_type} target: {operation.path}",
                )
            if current is not None and find_secret_marker(current) is not None:
                # Journaling the observed original would copy the existing
                # credential into the database; refuse before journaling.
                return WritebackOutcomeV2(
                    "DENIED", None, f"secret-like original content refused: {operation.path}"
                )
            if operation.action_type == "CREATE" and current is not None:
                return WritebackOutcomeV2(
                    "MISMATCH", None, f"CREATE target already exists: {operation.path}"
                )
            if operation.action_type == "REPLACE" and current is None:
                return WritebackOutcomeV2(
                    "MISMATCH", None, f"REPLACE target does not exist: {operation.path}"
                )
            entries.append(
                JournalEntryV2(
                    position,
                    operation.path,
                    operation.action_type,
                    operation.content,
                    current,
                )
            )
        try:
            transaction_id = self._database.begin_writeback_transaction(
                run_id=request.run_id,
                candidate_id=request.candidate_id,
                candidate_revision=request.candidate_revision,
                approval_id=request.approval_id,
                entries=tuple(entries),
            )
        except V2DatabaseError as exc:
            if "stale" in str(exc).lower():
                return WritebackOutcomeV2("STALE", None, "candidate revision is stale")
            return WritebackOutcomeV2(
                "DENIED", None, f"writeback was rejected: {exc}"
            )
        if not self._database.transition_transaction(
            transaction_id, from_state="PREPARED", to_state="WRITING"
        ):
            return WritebackOutcomeV2(
                "FAILED",
                transaction_id,
                "transaction could not enter WRITING; awaiting recovery",
            )
        try:
            for entry in entries:
                self._port.apply(entry.planned())  # type: ignore[attr-defined]
        except WorkspaceContentMismatchError:
            try:
                self._database.transition_transaction(
                    transaction_id, from_state="WRITING", to_state="UNRESOLVED"
                )
            except V2DatabaseError:
                pass
            return WritebackOutcomeV2(
                "FAILED",
                transaction_id,
                f"external change detected; refusing to overwrite; "
                f"transaction {transaction_id} is UNRESOLVED and awaits recovery",
            )
        except Exception:
            try:
                self._database.transition_transaction(
                    transaction_id, from_state="WRITING", to_state="UNRESOLVED"
                )
            except V2DatabaseError:
                pass
            return WritebackOutcomeV2(
                "FAILED",
                transaction_id,
                f"write fault; transaction {transaction_id} is UNRESOLVED "
                "and awaits recovery",
            )
        if not self._database.transition_transaction(
            transaction_id, from_state="WRITING", to_state="COMMITTED"
        ):
            return WritebackOutcomeV2(
                "FAILED",
                transaction_id,
                "transaction could not commit; state changed concurrently",
            )
        return WritebackOutcomeV2(
            "COMMITTED", transaction_id, f"{len(entries)} write(s) committed"
        )


__all__ = ["V2WritebackService"]

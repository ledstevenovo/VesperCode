"""T22.1 legacy step 22.A: transactional authorized memory repository.

``MemoryRepository.create`` enforces the SPEC 4.7 creator/kind matrix
(project conventions are created only by the user; the control-plane
kinds only by the control plane; model-originated writes are always
forbidden) and the bounded content contract (non-empty bounded summary,
matching closed source variant, no secret content, no full source
bodies) inside one immediate transaction, inserting exactly one
non-cleared entry row in the exact workspace or zero rows.
``MemoryRepository.confirm`` records a user's explicit confirmation of
one existing project convention (the untrusted marker is cleared and
updated_at advances) under the T07.3 idempotency ledger so exact replay
is free and event reuse for a different request is a conflict.
``MemoryRepository.list`` returns the non-cleared entries of the exact
workspace in stable creation order.  Selection, clearing, registry
edits, audit, and governance/config/validation authority remain out of
scope (GREEN-4).
"""

from __future__ import annotations

import re
import sqlite3
from typing import TypeAlias, cast

from pydantic import BaseModel, ConfigDict, StrictStr

from vespercode.canonical.digest import domain_digest
from vespercode.canonical.json_v1 import CanonicalJsonErrorV1
from vespercode.canonical.timestamp_v1 import CanonicalTimestampV1
from vespercode.memory.entry import (
    MemoryCreatorV1,
    MemoryEntryV1,
    MemoryKindV1,
    MemoryMutationResultV1,
    MemorySourceV1,
    parse_source,
    serialize_source,
)
from vespercode.storage.connection import (
    ControlDatabase,
    ControlTransactionV1,
)
from vespercode.storage.idempotency import IdempotencyRepository

MemoryEntrySequenceV1: TypeAlias = tuple[MemoryEntryV1, ...]


class _ConfirmRollback(Exception):
    """Internal sentinel: roll back the transaction and return the result.

    A confirm scope failure discovered inside the immediate transaction
    raises this sentinel so the NEW ledger record and any in-transaction
    writes roll back atomically before the closed rejection is returned
    (the same pattern as the Task 15 decision rollback).
    """

    def __init__(self, result: MemoryMutationResultV1) -> None:
        super().__init__(result.message)
        self.result = result


_MEMORY_SUMMARY_MAX_CHARS = 2048
_MEMORY_SOURCE_REF_MAX_CHARS = 256
_MEMORY_RUN_ID_MAX_CHARS = 128
_MEMORY_DIGEST_REF_MAX_CHARS = 128
_CONFIRM_EVENT_SCOPE = "memory_confirm"

_PRIVATE_KEY_BLOCK_RE = re.compile(
    rb"(?<![A-Za-z0-9])-----BEGIN [A-Z0-9][A-Z0-9 -]* PRIVATE KEY-----"
    rb"(?![A-Za-z0-9_])"
)
_GENERIC_API_KEY_RE = re.compile(
    rb"(?<![A-Za-z0-9])(?i:API_KEY|SECRET_KEY|ACCESS_TOKEN|AUTH_TOKEN)"
    rb"(?![A-Za-z0-9_])[ \t]*(?>=>|=|:)[ \t]*(?:([\"'])([^\n]+?)\1|"
    rb"[^ \t\r\n\v\f,;)}\x22']+)"
)
_CREDENTIAL_URL_RE = re.compile(
    rb"(?<![A-Za-z0-9])[A-Za-z][A-Za-z0-9+.-]*://[^/\s:@]+:[^/\s@]+@"
)
"""The memory secret vocabulary mirrors the Task 1 frozen credential rule
table (scripts/gate_scan.py).  It stays local because ``scripts/`` is not
part of the packaged runtime (T33.1 wheel); any later change to the gate
rules must be mirrored here."""


def _contains_secret(text: str) -> bool:
    data = text.encode("utf-8")
    return (
        _PRIVATE_KEY_BLOCK_RE.search(data) is not None
        or _GENERIC_API_KEY_RE.search(data) is not None
        or _CREDENTIAL_URL_RE.search(data) is not None
    )


class CreateMemoryCommandV1(BaseModel):
    """One closed authorized memory creation command.

    Carries only the harness-observed facts (exact workspace identity,
    kind, bounded summary, creator, matching closed source, generated
    entry id, and observed creation time); content bounds and the
    creator/kind authority are enforced by the repository, so every
    rejection is a closed zero-row result.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)
    workspace_identity: StrictStr
    kind: MemoryKindV1
    summary: StrictStr
    creator: MemoryCreatorV1
    source: MemorySourceV1
    entry_id: StrictStr
    created_at: CanonicalTimestampV1


class ConfirmProjectConventionV1(BaseModel):
    """One closed user confirmation of an existing project convention.

    Binds the exact workspace identity, the targeted entry, the user
    creator, the confirmation event identity (replay), and the observed
    decision time; nothing else may influence the outcome.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)
    workspace_identity: StrictStr
    entry_id: StrictStr
    creator: MemoryCreatorV1
    event_id: StrictStr
    decided_at: CanonicalTimestampV1


def _authorized_creator(kind: MemoryKindV1, creator: MemoryCreatorV1) -> bool:
    """SPEC 4.7: the sole authorized creator for one memory kind."""
    if creator == "MODEL":
        return False
    if kind == "PROJECT_CONVENTION":
        return creator == "USER"
    return creator == "CONTROL_PLANE"


def _source_kind_matches(kind: MemoryKindV1, source: MemorySourceV1) -> bool:
    """SPEC 4.7: the closed kind-to-content-source mapping."""
    return {
        "PROJECT_CONVENTION": "USER_VISIBLE_TEXT",
        "USER_DECISION": "USER_DECISION",
        "RUN_SUMMARY": "RUN_SUMMARY",
        "KNOWN_FAILURE": "KNOWN_FAILURE",
    }[kind] == source.kind


def _validate_content(
    kind: MemoryKindV1,
    summary: str,
    source: MemorySourceV1,
) -> str | None:
    """The bounded-content contract; returns the rejection reason or None."""
    if not isinstance(summary, str) or not summary:
        return "memory summary must be non-empty"
    if len(summary) > _MEMORY_SUMMARY_MAX_CHARS:
        return "memory summary exceeds the 2048-character bound"
    if not _source_kind_matches(kind, source):
        return "memory source variant does not match the entry kind"
    if source.kind == "USER_VISIBLE_TEXT":
        if not source.reference or len(source.reference) > _MEMORY_SOURCE_REF_MAX_CHARS:
            return "memory source reference is empty or exceeds the 256-character bound"
    elif source.kind == "USER_DECISION":
        if not source.reference or len(source.reference) > _MEMORY_SOURCE_REF_MAX_CHARS:
            return "memory source reference is empty or exceeds the 256-character bound"
    elif source.kind == "RUN_SUMMARY":
        if not source.run_id or len(source.run_id) > _MEMORY_RUN_ID_MAX_CHARS:
            return "memory source run id is empty or exceeds the 128-character bound"
    else:
        if (
            not source.check_result_digest
            or len(source.check_result_digest) > _MEMORY_DIGEST_REF_MAX_CHARS
        ):
            return "memory source check-result digest is empty or over-limit"
        if (
            not source.failure_fingerprint_digest
            or len(source.failure_fingerprint_digest) > _MEMORY_DIGEST_REF_MAX_CHARS
        ):
            return "memory source fingerprint digest is empty or over-limit"
    try:
        if _contains_secret(summary) or _contains_secret(serialize_source(source)):
            return "memory content contains a secret value"
    except (UnicodeEncodeError, CanonicalJsonErrorV1):
        # Lone surrogates (e.g. surrogateescape-decoded user text) cannot
        # be canonically encoded; the rejection stays closed with zero
        # rows instead of escaping as an untyped exception.
        return "memory content cannot be encoded canonically"
    return None


class MemoryRepository:
    """Transactional authorized memory repository over the v0005 schema."""

    def __init__(self, database: ControlDatabase) -> None:
        self._database = database
        self._idempotency = IdempotencyRepository(database)

    @property
    def database(self) -> ControlDatabase:
        """The owned control database (transaction access for callers)."""
        return self._database

    def entry_count(self) -> int:
        """The total number of persisted memory entry rows (read-only)."""
        return len(self._database.read_rows("SELECT 1 FROM memory_entries"))

    def create(
        self,
        command: CreateMemoryCommandV1,
    ) -> MemoryMutationResultV1:
        """Create one authorized bounded entry transactionally, or zero rows."""
        if not command.workspace_identity:
            return MemoryMutationResultV1(
                kind="REJECTED",
                error_code="MEMORY_SCOPE_VIOLATION",
                message="workspace identity must be non-empty",
            )
        if not command.entry_id:
            return MemoryMutationResultV1(
                kind="REJECTED",
                error_code="MEMORY_CONTENT_REJECTED",
                message="memory entry id must be non-empty",
            )
        if not _authorized_creator(command.kind, command.creator):
            return MemoryMutationResultV1(
                kind="REJECTED",
                error_code="MEMORY_CREATOR_FORBIDDEN",
                message="creator is not authorized for this memory kind",
            )
        content_error = _validate_content(command.kind, command.summary, command.source)
        if content_error is not None:
            return MemoryMutationResultV1(
                kind="REJECTED",
                error_code="MEMORY_CONTENT_REJECTED",
                message=content_error,
            )
        entry = MemoryEntryV1(
            entry_id=command.entry_id,
            workspace_identity=command.workspace_identity,
            kind=command.kind,
            summary=command.summary,
            creator=command.creator,
            source=command.source,
            created_at=command.created_at,
            updated_at=command.created_at,
            untrusted=command.kind == "PROJECT_CONVENTION",
        )
        try:
            with self._database.immediate_transaction() as tx:
                tx.execute(
                    "INSERT INTO memory_entries (entry_id, workspace_identity,"
                    " kind, summary, creator, source, created_at, updated_at,"
                    " untrusted, cleared_at, clear_transaction_id)"
                    " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, NULL)",
                    (
                        entry.entry_id,
                        entry.workspace_identity,
                        entry.kind,
                        entry.summary,
                        entry.creator,
                        serialize_source(entry.source),
                        entry.created_at.value,
                        entry.updated_at.value,
                        int(entry.untrusted),
                    ),
                )
        except sqlite3.IntegrityError:
            return MemoryMutationResultV1(
                kind="FAILED",
                error_code="MEMORY_STORE_FAILED",
                message="memory entry id already exists",
            )
        except Exception:
            # The insert rolled back; the fixed message never leaks raw
            # exception text (SPEC 5.4).
            return MemoryMutationResultV1(
                kind="FAILED",
                error_code="MEMORY_STORE_FAILED",
                message="memory store failed",
            )
        return MemoryMutationResultV1(
            kind="CREATED",
            message="memory entry created",
            entry=entry,
        )

    def confirm(
        self,
        command: ConfirmProjectConventionV1,
    ) -> MemoryMutationResultV1:
        """Record one explicit user confirmation of a convention atomically.

        The authority (user creator) is checked before the one immediate
        transaction; inside it the T07.3 ledger is consulted first so an
        exact replay is free (even after a later clear), event reuse for
        a different request is a conflict, and a NEW confirmation then
        revalidates the exact workspace scope, convention kind, and
        non-cleared state in-transaction (a scope failure rolls the NEW
        ledger record back with the closed rejection).  The request
        digest binds the semantic identity (workspace, entry, creator),
        not the volatile observed time, so re-sending the same event id
        with a different decided_at replays the recorded outcome.
        """
        if command.creator != "USER":
            return MemoryMutationResultV1(
                kind="REJECTED",
                error_code="MEMORY_CREATOR_FORBIDDEN",
                message="only the user can confirm a project convention",
            )
        if not command.event_id:
            return MemoryMutationResultV1(
                kind="REJECTED",
                error_code="MEMORY_CONTENT_REJECTED",
                message="confirmation event id must be non-empty",
            )
        request_digest = domain_digest(
            "ConfirmProjectConventionV1",
            1,
            {
                "workspace_identity": command.workspace_identity,
                "entry_id": command.entry_id,
                "creator": command.creator,
            },
        )
        result_digest = domain_digest(
            "MemoryConfirmResultV1",
            1,
            {
                "workspace_identity": command.workspace_identity,
                "entry_id": command.entry_id,
            },
        )
        try:
            with self._database.immediate_transaction() as tx:
                ledger = self._idempotency.record_or_replay(
                    tx,
                    _CONFIRM_EVENT_SCOPE,
                    command.event_id,
                    request_digest,
                    result_digest,
                )
                if ledger.kind == "REPLAY":
                    return MemoryMutationResultV1(
                        kind="REPLAY",
                        message="confirmation already recorded identically",
                        entry=self._read_entry_in_tx(tx, command.entry_id),
                    )
                if ledger.kind == "EVENT_ID_REUSE_CONFLICT":
                    return MemoryMutationResultV1(
                        kind="EVENT_ID_REUSE_CONFLICT",
                        message="confirmation event id reused for a different request",
                    )
                scope_error = self._confirm_scope_error(tx, command)
                if scope_error is not None:
                    raise _ConfirmRollback(scope_error)
                updated = tx.execute(
                    "UPDATE memory_entries SET untrusted = 0, updated_at = ?"
                    " WHERE entry_id = ? AND workspace_identity = ?"
                    " AND cleared_at IS NULL",
                    (
                        command.decided_at.value,
                        command.entry_id,
                        command.workspace_identity,
                    ),
                ).rowcount
                if updated != 1:
                    raise _ConfirmRollback(
                        MemoryMutationResultV1(
                            kind="FAILED",
                            error_code="MEMORY_STORE_FAILED",
                            message="memory store failed",
                        )
                    )
        except _ConfirmRollback as failure:
            # The transaction rolled back (NEW ledger record removed).
            return failure.result
        except Exception:
            # The transaction rolled back (ledger and update together);
            # the fixed message never leaks raw exception text (SPEC 5.4).
            return MemoryMutationResultV1(
                kind="FAILED",
                error_code="MEMORY_STORE_FAILED",
                message="memory store failed",
            )
        return MemoryMutationResultV1(
            kind="CONFIRMED",
            message="project convention confirmed",
            entry=self._read_entry(command.entry_id),
        )

    @staticmethod
    def _confirm_scope_error(
        tx: ControlTransactionV1,
        command: ConfirmProjectConventionV1,
    ) -> MemoryMutationResultV1 | None:
        """The in-transaction scope validation of one NEW confirmation.

        Runs inside the immediate transaction after the ledger consult,
        so ``BEGIN IMMEDIATE`` serializes competing writers and the
        exact workspace scope, convention kind, and non-cleared state
        cannot change before the update.
        """
        rows = tx.execute(
            "SELECT workspace_identity, kind, cleared_at FROM memory_entries"
            " WHERE entry_id = ?",
            (command.entry_id,),
        ).fetchall()
        if not rows:
            return MemoryMutationResultV1(
                kind="REJECTED",
                error_code="MEMORY_SCOPE_VIOLATION",
                message="memory entry does not exist",
            )
        workspace_identity, kind, cleared_at = (
            str(rows[0][0]),
            str(rows[0][1]),
            rows[0][2],
        )
        if workspace_identity != command.workspace_identity:
            return MemoryMutationResultV1(
                kind="REJECTED",
                error_code="MEMORY_SCOPE_VIOLATION",
                message="memory entry belongs to another workspace",
            )
        if kind != "PROJECT_CONVENTION":
            return MemoryMutationResultV1(
                kind="REJECTED",
                error_code="MEMORY_WRITE_NOT_AUTHORIZED",
                message="confirm authorizes only project conventions",
            )
        if cleared_at is not None:
            return MemoryMutationResultV1(
                kind="REJECTED",
                error_code="MEMORY_SCOPE_VIOLATION",
                message="cleared memory entries cannot be confirmed",
            )
        return None

    def list(
        self,
        workspace_identity_digest: str,
    ) -> MemoryEntrySequenceV1:
        """The non-cleared entries of the exact workspace, stable order.

        Orders by creation timestamp then entry id, so repeated listing
        is deterministic and never falls back to paths, names, or
        neighboring workspaces.
        """
        rows = self._database.read_rows(
            "SELECT entry_id, workspace_identity, kind, summary, creator,"
            " source, created_at, updated_at, untrusted, cleared_at,"
            " clear_transaction_id FROM memory_entries"
            " WHERE workspace_identity = ? AND cleared_at IS NULL"
            " ORDER BY created_at, entry_id",
            (workspace_identity_digest,),
        )
        return tuple(self._row_to_entry(row) for row in rows)

    def _read_entry(self, entry_id: str) -> MemoryEntryV1 | None:
        """Read one entry row after the caller transaction committed."""
        rows = self._database.read_rows(
            "SELECT entry_id, workspace_identity, kind, summary, creator,"
            " source, created_at, updated_at, untrusted, cleared_at,"
            " clear_transaction_id FROM memory_entries WHERE entry_id = ?",
            (entry_id,),
        )
        if not rows:
            return None
        return MemoryRepository._row_to_entry(rows[0])

    @staticmethod
    def _read_entry_in_tx(
        tx: ControlTransactionV1, entry_id: str
    ) -> MemoryEntryV1 | None:
        """Read one entry row inside the caller transaction."""
        rows = tx.execute(
            "SELECT entry_id, workspace_identity, kind, summary, creator,"
            " source, created_at, updated_at, untrusted, cleared_at,"
            " clear_transaction_id FROM memory_entries WHERE entry_id = ?",
            (entry_id,),
        ).fetchall()
        if not rows:
            return None
        return MemoryRepository._row_to_entry(rows[0])

    @staticmethod
    def _row_to_entry(row: sqlite3.Row) -> MemoryEntryV1:
        """One memory_entries row into the bounded entry value."""
        cleared_at_raw = row[9]
        clear_transaction_id_raw = row[10]
        return MemoryEntryV1(
            entry_id=str(row[0]),
            workspace_identity=str(row[1]),
            kind=cast(MemoryKindV1, str(row[2])),
            summary=str(row[3]),
            creator=cast(MemoryCreatorV1, str(row[4])),
            source=parse_source(str(row[5])),
            created_at=CanonicalTimestampV1.parse(str(row[6])),
            updated_at=CanonicalTimestampV1.parse(str(row[7])),
            untrusted=bool(row[8]),
            cleared_at=(
                CanonicalTimestampV1.parse(str(cleared_at_raw))
                if cleared_at_raw is not None
                else None
            ),
            clear_transaction_id=(
                str(clear_transaction_id_raw)
                if clear_transaction_id_raw is not None
                else None
            ),
        )

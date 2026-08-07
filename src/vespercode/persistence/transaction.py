"""T26.1 legacy step 26.A: immutable v0011 transaction value and repositories.

The value layer defines one immutable ``PersistenceTransactionV1``
binding the Run, the consumed approval, the workspace identity, the
frozen final-diff digest and policy digest, the closed transaction state,
the run deadline, and the durable write count.  The repositories enforce
repository creation (PREPARED only, unique transaction id), the unique
active workspace transaction, the unique ordered per-path identity
(duplicate-path rejection and strictly sorted 1-based sequences), and
the immutable closed transitions — all body-free: no artifact or
workspace byte is ever read or written here (GREEN-2/GREEN-4).
"""

from __future__ import annotations

import sqlite3
from typing import Literal, cast

from pydantic import (
    BaseModel,
    ConfigDict,
    StrictStr,
    field_validator,
    model_validator,
)

from vespercode.canonical.path_v1 import CanonicalRelativePathV1
from vespercode.canonical.timestamp_v1 import CanonicalTimestampV1
from vespercode.contracts.evidence import (
    ArtifactRefV1,
    DigestV1,
    OptionalDigestV1,
    _DIGEST_RE,
)
from vespercode.contracts.optional import AbsentV1, PresentV1
from vespercode.persistence.path_record import (
    DuplicatePersistencePath,
    PathWriteStateV1,
    PersistencePathRecordSequenceV1,
    PersistencePathRecordV1,
    PersistencePostimageV1,
    PersistencePreimageV1,
    PersistenceTransactionStateV1,
    WriteOperationV1,
)
from vespercode.trees.text_classifier import TextMetadataV1
from vespercode.storage.connection import (
    ControlDatabase,
    ControlTransactionV1,
)

_ACTIVE_STATES: frozenset[str] = frozenset({"PREPARED", "WRITING", "UNRESOLVED"})
_TERMINAL_STATES: frozenset[str] = frozenset({"COMMITTED", "ROLLED_BACK"})
_ABSENT = "ABSENT"


def _require_sha256_hex(value: str) -> str:
    if _DIGEST_RE.fullmatch(value) is None:
        raise ValueError("digest must be exactly 64 lowercase hexadecimal characters")
    return value


def _require_non_empty(value: str) -> str:
    if value == "":
        raise ValueError("identifier must be non-empty")
    return value


def _reject_coerced_schema_version(value: object) -> object:
    """Reject bool/float/string spellings of the integer schema version."""
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError("schema_version must be the decimal integer 1")
    return value


class PersistenceTransactionV1(BaseModel):
    """One immutable persistence transaction (SPEC 4.6 / 7 row).

    Binds the Run and consumed approval identity, the workspace identity
    digest and canonical path, the frozen final-diff and policy digests,
    the closed state, the run deadline, and the durable workspace write
    count; ``updated_at`` never precedes ``prepared_at``.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal[1]
    transaction_id: StrictStr
    run_id: StrictStr
    approval_id: StrictStr
    workspace_identity_digest: StrictStr
    workspace_path: StrictStr
    final_diff_digest: StrictStr
    policy_digest: StrictStr
    state: PersistenceTransactionStateV1
    run_deadline: CanonicalTimestampV1
    prepared_at: CanonicalTimestampV1
    updated_at: CanonicalTimestampV1
    workspace_write_count: int

    @field_validator("schema_version", mode="before")
    @classmethod
    def _schema_version_is_exact_int(cls, value: object) -> object:
        return _reject_coerced_schema_version(value)

    @field_validator("transaction_id", "run_id", "approval_id", "workspace_path")
    @classmethod
    def _identifiers_must_be_non_empty(cls, value: str) -> str:
        return _require_non_empty(value)

    @field_validator("workspace_identity_digest", "final_diff_digest", "policy_digest")
    @classmethod
    def _digest_has_exact_form(cls, value: str) -> str:
        return _require_sha256_hex(value)

    @field_validator("workspace_write_count", mode="before")
    @classmethod
    def _write_count_is_exact_int(cls, value: object) -> object:
        if not isinstance(value, int) or isinstance(value, bool):
            raise ValueError("workspace_write_count must be a decimal integer")
        if value < 0:
            raise ValueError("workspace_write_count must not be negative")
        return value

    @model_validator(mode="after")
    def _bind_created_and_updated(self) -> PersistenceTransactionV1:
        if self.updated_at.epoch_milliseconds < self.prepared_at.epoch_milliseconds:
            raise ValueError("updated_at must not precede prepared_at")
        return self


_LEGAL_TRANSACTION_TRANSITIONS: frozenset[tuple[str, str]] = frozenset(
    {
        # Normal writeback: the first replace turns PREPARED into WRITING.
        ("PREPARED", "WRITING"),
        # Zero-write deadline stop / cancellation (SPEC 4.6 item 11).
        ("PREPARED", "ROLLED_BACK"),
        # Recovery: terminal dispositions from any non-terminal state.
        ("PREPARED", "COMMITTED"),
        ("PREPARED", "UNRESOLVED"),
        ("WRITING", "COMMITTED"),
        ("WRITING", "ROLLED_BACK"),
        ("WRITING", "UNRESOLVED"),
        # Recovery may also resolve an UNRESOLVED transaction into a
        # service-proven terminal disposition (SPEC 4.6 item 10 / AC-22).
        ("UNRESOLVED", "COMMITTED"),
        ("UNRESOLVED", "ROLLED_BACK"),
    }
)
"""The closed transaction-level transition table (SPEC 4.6 items 7/10/11)."""

_LEGAL_PATH_TRANSITIONS: frozenset[tuple[str, str]] = frozenset(
    {
        ("NOT_STARTED", "REPLACED"),
        ("REPLACED", "VERIFIED"),
        # Recovery may enter ROLLED_BACK from any of the first three
        # states after re-verifying actual bytes (SPEC 4.6 item 7).
        ("NOT_STARTED", "ROLLED_BACK"),
        ("REPLACED", "ROLLED_BACK"),
        ("VERIFIED", "ROLLED_BACK"),
    }
)
"""The closed per-path durable-state transition table (SPEC 4.6 item 7).

Recovery advances lagging states only step by step over the legal pairs
(never skipping evidence), so a NOT_STARTED path whose bytes provably
match its postimage is advanced NOT_STARTED -> REPLACED -> VERIFIED.
"""

TransitionErrorKindV1 = Literal["INVALID_TRANSITION", "NOT_FOUND", "STALE"]


class TransactionTransitionErrorV1(ValueError):
    """Closed transition rejection: illegal pair, missing row, or stale state."""

    def __init__(self, error_code: TransitionErrorKindV1, message: str) -> None:
        super().__init__(f"{error_code}: {message}")
        self.error_code = error_code


class PersistenceTransactionRepositoryV1:
    """Transaction-bound persistence-transaction repository (v0011).

    Creation admits only ``PREPARED`` transactions with a unique id and
    no competing active workspace transaction; transitions are
    compare-and-update over the closed legal table inside one explicit
    immediate transaction, so exactly one legal transition wins and a
    stale or missing row never mutates (SPEC 4.6 items 7/10/11).
    """

    def __init__(self, database: ControlDatabase) -> None:
        self._database = database

    @property
    def database(self) -> ControlDatabase:
        """The owned control database (transaction access for callers)."""
        return self._database

    def create(self, transaction: PersistenceTransactionV1) -> PersistenceTransactionV1:
        """Insert one PREPARED transaction atomically; duplicates fail closed.

        A second non-terminal transaction for the same workspace identity
        is rejected before any write (the unique active workspace
        transaction, SPEC 4.6/AC-21); terminal transactions never block.
        """
        if transaction.state != "PREPARED":
            raise ValueError("create accepts only PREPARED transactions")
        with self._database.immediate_transaction() as tx:
            existing = tx.execute(
                "SELECT 1 FROM persistence_transactions WHERE transaction_id = ?",
                (transaction.transaction_id,),
            ).fetchone()
            if existing is not None:
                raise ValueError(
                    f"transaction {transaction.transaction_id} already exists"
                )
            active = tx.execute(
                "SELECT 1 FROM persistence_transactions"
                " WHERE workspace_identity_digest = ? AND state IN"
                " ('PREPARED', 'WRITING', 'UNRESOLVED')",
                (transaction.workspace_identity_digest,),
            ).fetchone()
            if active is not None:
                raise ValueError(
                    "workspace already owns an active persistence transaction"
                )
            try:
                tx.execute(
                    "INSERT INTO persistence_transactions (transaction_id, run_id,"
                    " approval_id, workspace_identity_digest, workspace_path,"
                    " final_diff_digest, policy_digest, state, run_deadline,"
                    " prepared_at, updated_at, workspace_write_count)"
                    " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        transaction.transaction_id,
                        transaction.run_id,
                        transaction.approval_id,
                        transaction.workspace_identity_digest,
                        transaction.workspace_path,
                        transaction.final_diff_digest,
                        transaction.policy_digest,
                        transaction.state,
                        transaction.run_deadline.value,
                        transaction.prepared_at.value,
                        transaction.updated_at.value,
                        transaction.workspace_write_count,
                    ),
                )
            except sqlite3.IntegrityError as exc:
                # A missing run/approval row fails closed as an invalid
                # binding, never a raw sqlite exception (quality review I-1).
                raise ValueError(
                    f"run or approval identity does not exist: {exc}"
                ) from exc
        return transaction

    def get(self, transaction_id: str) -> PersistenceTransactionV1 | None:
        """Read one transaction value, or ``None`` when it does not exist."""
        row = self._database.read_rows(
            "SELECT transaction_id, run_id, approval_id, workspace_identity_digest,"
            " workspace_path, final_diff_digest, policy_digest, state, run_deadline,"
            " prepared_at, updated_at, workspace_write_count"
            " FROM persistence_transactions WHERE transaction_id = ?",
            (transaction_id,),
        )
        if not row:
            return None
        return _row_to_transaction(row[0])

    def has_active_for_workspace(self, workspace_identity_digest: str) -> bool:
        """True exactly when the workspace owns a non-terminal transaction."""
        return self.find_active_by_workspace(workspace_identity_digest) is not None

    def find_active_by_workspace(
        self, workspace_identity_digest: str
    ) -> PersistenceTransactionV1 | None:
        """The unique active workspace transaction, or ``None``.

        The v0011 partial unique index admits at most one active
        transaction per workspace (SPEC 4.6/AC-21 recovery gate).
        """
        row = self._database.read_rows(
            "SELECT transaction_id, run_id, approval_id, workspace_identity_digest,"
            " workspace_path, final_diff_digest, policy_digest, state, run_deadline,"
            " prepared_at, updated_at, workspace_write_count"
            " FROM persistence_transactions"
            " WHERE workspace_identity_digest = ? AND state IN"
            " ('PREPARED', 'WRITING', 'UNRESOLVED')",
            (workspace_identity_digest,),
        )
        if not row:
            return None
        return _row_to_transaction(row[0])

    def has_unresolved(self, workspace_identity_digest: str) -> bool:
        """Read-only recovery gate: an UNRESOLVED transaction exists (AC-21)."""
        row = self._database.read_rows(
            "SELECT 1 FROM persistence_transactions"
            " WHERE workspace_identity_digest = ? AND state = 'UNRESOLVED'",
            (workspace_identity_digest,),
        )
        return bool(row)

    def transition(
        self,
        transaction_id: str,
        *,
        expected: PersistenceTransactionStateV1,
        target: PersistenceTransactionStateV1,
        updated_at: CanonicalTimestampV1,
        workspace_write_count: int,
    ) -> None:
        """Apply one legal closed transition exactly once (compare-and-update).

        The (expected, target) pair must be in the closed table; the
        update compares the recorded state and refreshes the updated-at
        and durable write-count facts, so an illegal pair, a missing
        transaction, or a stale recorded state never mutates anything.
        """
        with self._database.immediate_transaction() as tx:
            self.transition_in(
                tx,
                transaction_id,
                expected=expected,
                target=target,
                updated_at=updated_at,
                workspace_write_count=workspace_write_count,
            )

    def transition_in(
        self,
        tx: ControlTransactionV1,
        transaction_id: str,
        *,
        expected: PersistenceTransactionStateV1,
        target: PersistenceTransactionStateV1,
        updated_at: CanonicalTimestampV1,
        workspace_write_count: int,
    ) -> None:
        """The compare-and-update transition inside a caller transaction.

        Enables one atomic terminal recording (recovery apply) without
        nesting transactions; the same closed-table and CAS semantics
        apply (T07.2 ``lock_wait_for_decision(tx, ...)`` precedent).
        """
        if (expected, target) not in _LEGAL_TRANSACTION_TRANSITIONS:
            raise TransactionTransitionErrorV1(
                "INVALID_TRANSITION",
                f"illegal transaction transition {expected} -> {target}",
            )
        updated = tx.execute(
            "UPDATE persistence_transactions SET state = ?, updated_at = ?,"
            " workspace_write_count = ? WHERE transaction_id = ? AND state = ?",
            (
                target,
                updated_at.value,
                workspace_write_count,
                transaction_id,
                expected,
            ),
        ).rowcount
        if updated != 1:
            row = tx.execute(
                "SELECT state FROM persistence_transactions WHERE transaction_id = ?",
                (transaction_id,),
            ).fetchone()
            if row is None:
                raise TransactionTransitionErrorV1(
                    "NOT_FOUND", "transaction does not exist"
                )
            raise TransactionTransitionErrorV1(
                "STALE",
                "expected state does not match the recorded state",
            )


class PersistencePathRecordRepositoryV1:
    """Transaction-bound ordered per-path record repository (v0011).

    Appends the frozen records of one PREPARED transaction in strictly
    sorted canonical-path order with exactly the next 1-based sequence
    (duplicate paths reject through the closed ``DuplicatePersistencePath``
    rejection and the DDL backstop); listing returns the ordered
    sequence; per-path progress updates are compare-and-update over the
    closed durable-state table.  No body byte is ever read or written.
    """

    def __init__(self, database: ControlDatabase) -> None:
        self._database = database

    @property
    def database(self) -> ControlDatabase:
        """The owned control database (transaction access for callers)."""
        return self._database

    def append(self, transaction_id: str, record: PersistencePathRecordV1) -> None:
        """Append one frozen record to a PREPARED transaction.

        The transaction must exist and still be PREPARED; the path must
        be new (``DuplicatePersistencePath`` otherwise) and sort strictly
        after every already-appended path; the sequence must be exactly
        the next 1-based position.  Every rejection fires before any
        insert and performs zero writes.
        """
        with self._database.immediate_transaction() as tx:
            state_row = tx.execute(
                "SELECT state FROM persistence_transactions WHERE transaction_id = ?",
                (transaction_id,),
            ).fetchone()
            if state_row is None:
                raise ValueError(f"transaction {transaction_id} does not exist")
            if str(state_row[0]) != "PREPARED":
                raise ValueError(
                    "path records are frozen at PREPARED; found "
                    f"state {str(state_row[0])}"
                )
            duplicate = tx.execute(
                "SELECT 1 FROM persistence_path_records"
                " WHERE transaction_id = ? AND path = ?",
                (transaction_id, record.path.value),
            ).fetchone()
            if duplicate is not None:
                raise DuplicatePersistencePath(
                    f"path {record.path.value!r} already recorded in {transaction_id}"
                )
            last = tx.execute(
                "SELECT path, sequence FROM persistence_path_records"
                " WHERE transaction_id = ? ORDER BY sequence DESC LIMIT 1",
                (transaction_id,),
            ).fetchone()
            expected_sequence = 1 if last is None else int(last[1]) + 1
            if record.sequence != expected_sequence:
                raise ValueError(
                    f"expected sequence {expected_sequence}, found {record.sequence}"
                )
            if last is not None and record.path.value <= str(last[0]):
                raise ValueError(
                    "path records must be appended in strictly sorted "
                    "canonical-path order"
                )
            try:
                tx.execute(
                    "INSERT INTO persistence_path_records (transaction_id, path,"
                    " operation, sequence, preimage_kind, preimage_raw_bytes_digest,"
                    " preimage_text_encoding, preimage_text_newline,"
                    " preimage_object_identity_digest, postimage_raw_bytes_digest,"
                    " postimage_text_encoding, postimage_text_newline,"
                    " postimage_required_object_policy_digest, durable_state,"
                    " backup_ref, backup_digest, last_evidence_digest)"
                    " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    _record_to_row_columns(transaction_id, record),
                )
            except sqlite3.IntegrityError as exc:
                # A missing transaction row or a DDL backstop rejection
                # fails closed as a closed error, never a raw sqlite
                # exception (quality review I-1).
                raise ValueError(f"invalid path record binding: {exc}") from exc

    def list_ordered(self, transaction_id: str) -> PersistencePathRecordSequenceV1:
        """The immutable ordered per-path records of one transaction."""
        rows = self._database.read_rows(
            "SELECT transaction_id, path, operation, sequence, preimage_kind,"
            " preimage_raw_bytes_digest, preimage_text_encoding,"
            " preimage_text_newline, preimage_object_identity_digest,"
            " postimage_raw_bytes_digest, postimage_text_encoding,"
            " postimage_text_newline, postimage_required_object_policy_digest,"
            " durable_state, backup_ref, backup_digest, last_evidence_digest"
            " FROM persistence_path_records WHERE transaction_id = ?"
            " ORDER BY sequence",
            (transaction_id,),
        )
        return tuple(_row_to_record(row) for row in rows)

    def update_durable_state(
        self,
        transaction_id: str,
        path: str,
        *,
        expected: PathWriteStateV1,
        target: PathWriteStateV1,
        last_evidence_digest: OptionalDigestV1 | None = None,
    ) -> PersistencePathRecordV1:
        """Apply one legal per-path progress transition exactly once.

        Only ``NOT_STARTED -> REPLACED -> VERIFIED`` and recovery's
        ``ROLLED_BACK`` from any of the first three states apply; the
        compare-and-update means a stale or missing row never mutates
        (SPEC 4.6 item 7: no skipping evidence, no return from
        ``ROLLED_BACK``).  Returns the refreshed record; illegal, stale,
        and missing progress raise the same closed transition rejection
        as the transaction transitions.
        """
        with self._database.immediate_transaction() as tx:
            return self.update_durable_state_in(
                tx,
                transaction_id,
                path,
                expected=expected,
                target=target,
                last_evidence_digest=last_evidence_digest,
            )

    def update_durable_state_in(
        self,
        tx: ControlTransactionV1,
        transaction_id: str,
        path: str,
        *,
        expected: PathWriteStateV1,
        target: PathWriteStateV1,
        last_evidence_digest: OptionalDigestV1 | None = None,
    ) -> PersistencePathRecordV1:
        """The per-path progress transition inside a caller transaction.

        Enables one atomic terminal recording (recovery apply) without
        nesting transactions; the same closed-table and CAS semantics
        apply.
        """
        if (expected, target) not in _LEGAL_PATH_TRANSITIONS:
            raise TransactionTransitionErrorV1(
                "INVALID_TRANSITION",
                f"illegal path transition {expected} -> {target}",
            )
        evidence_value: object = "ABSENT"
        if last_evidence_digest is not None:
            evidence_value = (
                "ABSENT"
                if last_evidence_digest.kind == "ABSENT"
                else last_evidence_digest.value.value
            )
        exists = tx.execute(
            "SELECT 1 FROM persistence_path_records"
            " WHERE transaction_id = ? AND path = ?",
            (transaction_id, path),
        ).fetchone()
        if exists is None:
            raise TransactionTransitionErrorV1(
                "NOT_FOUND", "path record does not exist"
            )
        updated = tx.execute(
            "UPDATE persistence_path_records SET durable_state = ?,"
            " last_evidence_digest = ? WHERE transaction_id = ? AND path = ?"
            " AND durable_state = ?",
            (target, evidence_value, transaction_id, path, expected),
        ).rowcount
        if updated != 1:
            raise TransactionTransitionErrorV1(
                "STALE",
                "expected durable state does not match the recorded state",
            )
        for record in self.list_ordered(transaction_id):
            if record.path.value == path:
                return record
        raise TransactionTransitionErrorV1("NOT_FOUND", "path record does not exist")


def _row_to_transaction(row: sqlite3.Row) -> PersistenceTransactionV1:
    """Map one v0011 transaction row back to the immutable value."""
    return PersistenceTransactionV1(
        schema_version=1,
        transaction_id=str(row[0]),
        run_id=str(row[1]),
        approval_id=str(row[2]),
        workspace_identity_digest=str(row[3]),
        workspace_path=str(row[4]),
        final_diff_digest=str(row[5]),
        policy_digest=str(row[6]),
        state=cast(PersistenceTransactionStateV1, str(row[7])),
        run_deadline=CanonicalTimestampV1.parse(str(row[8])),
        prepared_at=CanonicalTimestampV1.parse(str(row[9])),
        updated_at=CanonicalTimestampV1.parse(str(row[10])),
        workspace_write_count=int(row[11]),
    )


def _record_to_row_columns(
    transaction_id: str,
    record: PersistencePathRecordV1,
) -> tuple[object, ...]:
    """Map one immutable path record to its v0011 column values.

    ``ABSENT`` optional evidence is stored as the literal ``ABSENT``
    sentinel (SPEC 0.1: a typed sentinel, never an empty string);
    ``PRESENT`` evidence stores the artifact id and digest pair.
    """
    if record.preimage.kind == "ABSENT":
        preimage_digest: object = _ABSENT
        preimage_encoding: object = _ABSENT
        preimage_newline: object = _ABSENT
        preimage_identity: object = _ABSENT
    else:
        preimage_metadata = record.preimage.text_metadata
        assert preimage_metadata is not None
        preimage_digest = record.preimage.raw_bytes_digest
        preimage_encoding = preimage_metadata.encoding
        preimage_newline = preimage_metadata.newline
        preimage_identity = record.preimage.object_identity_digest
    if record.backup_ref.kind == "ABSENT":
        backup_ref: object = _ABSENT
        backup_digest: object = _ABSENT
    else:
        backup_ref = record.backup_ref.value.artifact_id
        backup_digest = record.backup_ref.value.digest.value
    if record.last_evidence_digest.kind == "ABSENT":
        last_evidence_digest: object = _ABSENT
    else:
        last_evidence_digest = record.last_evidence_digest.value.value
    return (
        transaction_id,
        record.path.value,
        record.operation,
        record.sequence,
        record.preimage.kind,
        preimage_digest,
        preimage_encoding,
        preimage_newline,
        preimage_identity,
        record.postimage.raw_bytes_digest,
        record.postimage.text_metadata.encoding,
        record.postimage.text_metadata.newline,
        record.postimage.required_object_policy_digest,
        record.durable_state,
        backup_ref,
        backup_digest,
        last_evidence_digest,
    )


def _row_to_record(row: sqlite3.Row) -> PersistencePathRecordV1:
    """Map one v0011 path-record row back to the immutable value."""
    preimage_kind = str(row[4])
    if preimage_kind == "PRESENT":
        preimage = PersistencePreimageV1(
            kind="PRESENT",
            raw_bytes_digest=str(row[5]),
            text_metadata=TextMetadataV1(
                encoding=cast(Literal["UTF8", "UTF8_BOM"], str(row[6])),
                newline=cast(Literal["LF", "CRLF"], str(row[7])),
                final_newline=True,
            ),
            object_identity_digest=str(row[8]),
        )
    else:
        preimage = PersistencePreimageV1(kind="ABSENT")
    backup_kind = str(row[14])
    if backup_kind != _ABSENT:
        backup_ref: AbsentV1 | PresentV1[ArtifactRefV1] = PresentV1[ArtifactRefV1](
            kind="PRESENT",
            value=ArtifactRefV1(
                artifact_id=backup_kind,
                digest=DigestV1(value=str(row[15])),
            ),
        )
    else:
        backup_ref = AbsentV1(kind="ABSENT")
    if str(row[16]) != _ABSENT:
        last_evidence: AbsentV1 | PresentV1[DigestV1] = PresentV1[DigestV1](
            kind="PRESENT", value=DigestV1(value=str(row[16]))
        )
    else:
        last_evidence = AbsentV1(kind="ABSENT")
    return PersistencePathRecordV1(
        schema_version=1,
        path=CanonicalRelativePathV1(str(row[1])),
        operation=cast(WriteOperationV1, str(row[2])),
        sequence=int(row[3]),
        preimage=preimage,
        postimage=PersistencePostimageV1(
            raw_bytes_digest=str(row[9]),
            text_metadata=TextMetadataV1(
                encoding=cast(Literal["UTF8", "UTF8_BOM"], str(row[10])),
                newline=cast(Literal["LF", "CRLF"], str(row[11])),
                final_newline=True,
            ),
            required_object_policy_digest=str(row[12]),
        ),
        durable_state=cast(PathWriteStateV1, str(row[13])),
        backup_ref=backup_ref,
        last_evidence_digest=last_evidence,
    )

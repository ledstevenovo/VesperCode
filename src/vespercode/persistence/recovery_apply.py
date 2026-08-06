"""T26.2 legacy step 26.C: explicit recovery apply under the workspace lease.

``RecoveryApplyService.apply`` executes only a current bound recovery
preview under the workspace lease: it re-acquires the lease, recomputes
the preview (a stale digest performs zero writes), executes only the
bound recovery path (``COMMITTED`` redoes the write-after verification
and records the terminal; ``ROLLED_BACK`` rechecks the current
identities before every authoritative change, restores REPLACE paths
from their verified backup artifacts, deletes only a CREATE file that
still exactly matches its postimage, and records the terminal), and
records exactly one service-proven terminal result.  Stale, external-
change, ACL, deadline, or partial evidence never overwrites anything
and remains unresolved (SPEC 4.6 / AC-29 / AC-22 / §8.2).
"""

from __future__ import annotations

import hashlib
import json
from typing import Literal, Protocol

from pydantic import (
    BaseModel,
    ConfigDict,
    StrictStr,
    field_validator,
)

from src.vespercode.canonical.digest import domain_digest
from src.vespercode.canonical.path_v1 import CanonicalRelativePathV1
from src.vespercode.canonical.timestamp_v1 import CanonicalTimestampV1
from src.vespercode.contracts.evidence import DigestV1
from src.vespercode.contracts.optional import PresentV1
from src.vespercode.persistence.artifacts import (
    PersistenceArtifactIntegrityError,
    PersistenceArtifactStoreV1,
)
from src.vespercode.persistence.path_record import PersistencePathRecordV1
from src.vespercode.persistence.recovery_preview import (
    RecoveryDispositionV1,
    RecoveryPathObservationV1,
    RecoveryPreviewErrorV1,
    RecoveryPreviewService,
    RecoveryPreviewV1,
    classify_path,
)
from src.vespercode.persistence.transaction import (
    PersistencePathRecordRepositoryV1,
    PersistenceTransactionRepositoryV1,
    PersistenceTransactionV1,
    TransactionTransitionErrorV1,
)
from src.vespercode.persistence.writeback import ClockPort
from src.vespercode.storage.connection import (
    ControlDatabase,
    ControlTransactionV1,
)
from src.vespercode.workspace.identity_win32 import WorkspaceIdentityV1
from src.vespercode.workspace.mutex_win32 import (
    WorkspaceLeaseV1,
    WorkspaceMutex,
    WorkspaceMutexError,
    WorkspaceMutexTimeoutError,
)

RecoveryApplyErrorCodeV1 = Literal[
    "RECOVERY_PREVIEW_STALE",
    "RECOVERY_DISPOSITION_MISMATCH",
    "RECOVERY_ALREADY_TERMINAL",
    "RECOVERY_UNRESOLVED",
    "WORKSPACE_MISMATCH",
    "WORKSPACE_LOCK_LOST",
    "ARTIFACT_ACL_UNSAFE",
    "PERSISTENCE_FAILED",
]
"""The closed recovery-apply error codes (RECOVERY_PREVIEW_STALE is the
card-mandated stable code for a stale preview digest)."""


def _reject_coerced_schema_version(value: object) -> object:
    """Reject bool/float/string spellings of the integer schema version."""
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError("schema_version must be the decimal integer 1")
    return value


class ApplyRecoveryV1(BaseModel):
    """One explicit recovery command bound to a current preview.

    ``explicit_apply`` is the closed literal ``True`` (recovery can never
    be applied implicitly); ``requested_disposition`` is the proven
    terminal the caller asks the service to execute.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal[1]
    transaction_id: StrictStr
    workspace_identity_digest: StrictStr
    preview_digest: StrictStr
    requested_disposition: Literal["COMMITTED", "ROLLED_BACK"]
    explicit_apply: Literal[True]

    @field_validator("schema_version", mode="before")
    @classmethod
    def _schema_version_is_exact_int(cls, value: object) -> object:
        return _reject_coerced_schema_version(value)


class RecoveryResultV1(BaseModel):
    """One closed recovery-apply outcome.

    ``disposition`` is the proven or requested three-value disposition;
    ``changed_paths`` honestly lists every path the apply authoritatively
    changed (empty for COMMITTED and every zero-change outcome);
    ``evidence_digest`` binds the proven disposition and changed paths.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal[1]
    transaction_id: StrictStr
    disposition: RecoveryDispositionV1
    error_code: RecoveryApplyErrorCodeV1 | None = None
    changed_paths: tuple[StrictStr, ...]
    evidence_digest: StrictStr | None = None
    workspace_write_count: int
    message: StrictStr

    @field_validator("schema_version", mode="before")
    @classmethod
    def _schema_version_is_exact_int(cls, value: object) -> object:
        return _reject_coerced_schema_version(value)

    @field_validator("workspace_write_count", mode="before")
    @classmethod
    def _write_count_is_exact_int(cls, value: object) -> object:
        if not isinstance(value, int) or isinstance(value, bool):
            raise ValueError("workspace_write_count must be a decimal integer")
        if value < 0:
            raise ValueError("workspace_write_count must not be negative")
        return value


class RecoveryWorkspacePort(Protocol):
    """The injected workspace authority: observe, replace, delete."""

    def observe(self, path: CanonicalRelativePathV1) -> RecoveryPathObservationV1: ...

    def replace(self, path: CanonicalRelativePathV1, body: bytes) -> None: ...

    def delete(self, path: CanonicalRelativePathV1) -> None: ...

    @property
    def write_count(self) -> int: ...


class RecoveryLeasePort(Protocol):
    """The injected cross-process workspace lease for the apply."""

    def acquire(self) -> None: ...

    def release(self) -> None: ...

    def is_held(self) -> bool: ...


class RecoveryLeaseUnavailableV1(ValueError):
    """Closed rejection: the workspace lease cannot be acquired."""


class RealRecoveryLeasePort:
    """The concrete lease port over the Task 9.1 workspace mutex."""

    def __init__(self, identity: WorkspaceIdentityV1, timeout_ms: int) -> None:
        self._identity = identity
        self._timeout_ms = timeout_ms
        self._lease: WorkspaceLeaseV1 | None = None

    def acquire(self) -> None:
        try:
            self._lease = WorkspaceMutex.acquire(self._identity, self._timeout_ms)
        except (WorkspaceMutexTimeoutError, WorkspaceMutexError) as exc:
            raise RecoveryLeaseUnavailableV1(str(exc)) from exc

    def release(self) -> None:
        if self._lease is not None:
            WorkspaceMutex.release(self._lease)
            self._lease = None

    def is_held(self) -> bool:
        return self._lease is not None


class RecoveryResultRepositoryV1:
    """v0012 body-free terminal-result storage (one row per apply)."""

    def __init__(self, database: ControlDatabase) -> None:
        self._database = database

    @property
    def database(self) -> ControlDatabase:
        """The owned control database (transaction access for callers)."""
        return self._database

    def record(
        self,
        tx: ControlTransactionV1,
        *,
        transaction_id: str,
        disposition: RecoveryDispositionV1,
        evidence_digest: str,
        changed_paths: tuple[str, ...],
        workspace_write_count: int,
        applied_at: CanonicalTimestampV1,
    ) -> None:
        """Insert one service-proven terminal result inside the caller tx.

        One terminal result per transaction: a duplicate recording fails
        closed at the primary key.
        """
        tx.execute(
            "INSERT INTO recovery_results (transaction_id, disposition,"
            " evidence_digest, changed_paths, workspace_write_count, applied_at)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            (
                transaction_id,
                disposition,
                evidence_digest,
                json.dumps(
                    list(changed_paths), ensure_ascii=False, separators=(",", ":")
                ),
                workspace_write_count,
                applied_at.value,
            ),
        )


class RecoveryApplyService:
    """The explicit recovery apply bound to one current preview."""

    def __init__(
        self,
        *,
        transaction_repository: PersistenceTransactionRepositoryV1,
        path_repository: PersistencePathRecordRepositoryV1,
        artifact_store: PersistenceArtifactStoreV1,
        preview_service: RecoveryPreviewService,
        workspace: RecoveryWorkspacePort,
        lease: RecoveryLeasePort,
        results: RecoveryResultRepositoryV1,
        clock: ClockPort,
        workspace_identity_digest: str,
    ) -> None:
        self._transactions = transaction_repository
        self._paths = path_repository
        self._artifacts = artifact_store
        self._preview_service = preview_service
        self._workspace = workspace
        self._lease = lease
        self._results = results
        self._clock = clock
        self._workspace_identity_digest = workspace_identity_digest

    def apply(self, command: ApplyRecoveryV1) -> RecoveryResultV1:
        """Execute the bound recovery path under the workspace lease.

        Admission: the transaction must exist, be non-terminal, and bind
        the command workspace; the lease must be acquirable; the preview
        must recompute to the exact bound digest; and the requested
        disposition must equal the proven disposition.  Every later
        authoritative change rechecks the current identities; a stale,
        external, ACL, deadline, or partial state aborts with zero
        further changes and never overwrites.
        """
        transaction = self._transactions.get(command.transaction_id)
        if transaction is None:
            return self._result(
                command,
                "UNRESOLVED",
                "PERSISTENCE_FAILED",
                (),
                "no persistence transaction for recovery",
            )
        if transaction.state in ("COMMITTED", "ROLLED_BACK"):
            return self._result(
                command,
                transaction.state,
                "RECOVERY_ALREADY_TERMINAL",
                (),
                f"transaction already terminal: {transaction.state}",
            )
        if transaction.workspace_identity_digest != command.workspace_identity_digest:
            return self._result(
                command,
                "UNRESOLVED",
                "WORKSPACE_MISMATCH",
                (),
                "transaction does not bind the command workspace",
            )
        if transaction.workspace_identity_digest != self._workspace_identity_digest:
            return self._result(
                command,
                "UNRESOLVED",
                "WORKSPACE_MISMATCH",
                (),
                "transaction does not bind the apply workspace",
            )
        try:
            self._lease.acquire()
        except RecoveryLeaseUnavailableV1 as exc:
            return self._result(
                command,
                "UNRESOLVED",
                "WORKSPACE_LOCK_LOST",
                (),
                str(exc),
            )
        try:
            return self._apply_locked(command, transaction)
        finally:
            self._lease.release()

    def _apply_locked(
        self,
        command: ApplyRecoveryV1,
        transaction: PersistenceTransactionV1,
    ) -> RecoveryResultV1:
        # The current preview recomputed under the lease binds the apply.
        try:
            preview = self._preview_service.preview_transaction(command.transaction_id)
        except RecoveryPreviewErrorV1 as exc:
            return self._result(
                command,
                "UNRESOLVED",
                "RECOVERY_UNRESOLVED",
                (),
                str(exc),
            )
        if preview.preview_digest != command.preview_digest:
            return self._result(
                command,
                preview.disposition,
                "RECOVERY_PREVIEW_STALE",
                (),
                "preview digest is stale; recompute the preview",
            )
        if preview.disposition == "UNRESOLVED":
            return self._result(
                command,
                "UNRESOLVED",
                "RECOVERY_UNRESOLVED",
                (),
                "no service-proven terminal disposition is available",
            )
        if preview.disposition != command.requested_disposition:
            return self._result(
                command,
                preview.disposition,
                "RECOVERY_DISPOSITION_MISMATCH",
                (),
                f"proven disposition {preview.disposition} differs from "
                f"the requested {command.requested_disposition}",
            )
        if preview.disposition == "COMMITTED":
            return self._apply_committed(command, transaction, preview)
        return self._apply_rolled_back(command, transaction, preview)

    def _apply_committed(
        self,
        command: ApplyRecoveryV1,
        transaction: PersistenceTransactionV1,
        preview: RecoveryPreviewV1,
    ) -> RecoveryResultV1:
        """COMMITTED: redo the write-after verification, record terminal.

        Every path must still exactly match its postimage (a supported
        FILE at the postimage digest); the apply performs no workspace
        change and records the terminal COMMITTED result.
        """
        records = self._paths.list_ordered(transaction.transaction_id)
        for record in records:
            observation = self._workspace.observe(record.path)
            if classify_path(record, observation) != "POSTIMAGE":
                return self._result(
                    command,
                    "UNRESOLVED",
                    "RECOVERY_UNRESOLVED",
                    (),
                    f"path {record.path.value!r} no longer matches its postimage",
                )
        evidence = self._evidence_digest("COMMITTED", ())
        try:
            self._record_terminal(
                transaction,
                state="COMMITTED",
                path_state="VERIFIED",
                disposition="COMMITTED",
                evidence_digest=evidence,
                changed_paths=(),
            )
        except TransactionTransitionErrorV1 as exc:
            return self._result(
                command,
                "UNRESOLVED",
                "PERSISTENCE_FAILED",
                (),
                f"terminal recording failed: {exc}",
            )
        return self._result(
            command,
            "COMMITTED",
            None,
            (),
            "write-after verification redone; transaction committed",
            evidence_digest=evidence,
        )

    def _apply_rolled_back(
        self,
        command: ApplyRecoveryV1,
        transaction: PersistenceTransactionV1,
        preview: RecoveryPreviewV1,
    ) -> RecoveryResultV1:
        """ROLLED_BACK: restore every applied path under the lease.

        Per-path, immediately before each authoritative change: a fresh
        observation rechecks the current identities.  A CREATE path that
        still exactly matches its postimage is deleted (AC-29 safe ABSENT
        rollback) and verified gone; a REPLACE path at its postimage is
        restored from its verified backup artifact and verified at the
        preimage bytes.  Stale, external, ACL, deadline, or partial
        evidence aborts with the honestly changed paths and no terminal.
        """
        records = self._paths.list_ordered(transaction.transaction_id)
        changed: list[str] = []
        for record in records:
            stalled = self._roll_back_one(command, transaction, record, changed)
            if stalled is not None:
                return stalled
        evidence = self._evidence_digest("ROLLED_BACK", tuple(changed))
        try:
            self._record_terminal(
                transaction,
                state="ROLLED_BACK",
                path_state="ROLLED_BACK",
                disposition="ROLLED_BACK",
                evidence_digest=evidence,
                changed_paths=tuple(changed),
            )
        except TransactionTransitionErrorV1 as exc:
            return self._result(
                command,
                "UNRESOLVED",
                "PERSISTENCE_FAILED",
                tuple(changed),
                f"terminal recording failed: {exc}",
            )
        return self._result(
            command,
            "ROLLED_BACK",
            None,
            tuple(changed),
            "recovery rolled the transaction back",
            evidence_digest=evidence,
        )

    def _roll_back_one(
        self,
        command: ApplyRecoveryV1,
        transaction: PersistenceTransactionV1,
        record: PersistencePathRecordV1,
        changed: list[str],
    ) -> RecoveryResultV1 | None:
        """Roll one path back, rechecking the current identity first."""
        observation = self._workspace.observe(record.path)
        classification = classify_path(record, observation)
        if classification in ("PREIMAGE", "ABSENT"):
            return None
        if classification == "EXTERNAL_CHANGE":
            return self._result(
                command,
                "UNRESOLVED",
                "RECOVERY_UNRESOLVED",
                tuple(changed),
                f"path {record.path.value!r} was externally changed",
            )
        if classification == "UNPROVABLE":
            return self._result(
                command,
                "UNRESOLVED",
                "RECOVERY_UNRESOLVED",
                tuple(changed),
                f"path {record.path.value!r} identity is unprovable",
            )
        # POSTIMAGE: the path is at its postimage and must be rolled back.
        if self._deadline_expired(transaction):
            return self._result(
                command,
                "UNRESOLVED",
                "RECOVERY_UNRESOLVED",
                tuple(changed),
                "run_deadline expired; no further workspace changes allowed",
            )
        if not self._lease.is_held():
            return self._result(
                command,
                "UNRESOLVED",
                "WORKSPACE_LOCK_LOST",
                tuple(changed),
                "workspace lease lost during recovery",
            )
        if record.operation == "CREATE":
            return self._roll_back_create(command, transaction, record, changed)
        return self._roll_back_replace(command, transaction, record, changed)

    def _roll_back_create(
        self,
        command: ApplyRecoveryV1,
        transaction: PersistenceTransactionV1,
        record: PersistencePathRecordV1,
        changed: list[str],
    ) -> RecoveryResultV1 | None:
        """Delete one CREATE file that still exactly matches its postimage.

        The deletion is verified immediately after (AC-29: an external
        recreation in the unlink window fails closed with the path
        honestly listed and no terminal record).
        """
        try:
            self._workspace.delete(record.path)
        except OSError as exc:
            return self._result(
                command,
                "UNRESOLVED",
                "RECOVERY_UNRESOLVED",
                tuple(changed),
                f"cannot delete {record.path.value!r}: {exc}",
            )
        after = self._workspace.observe(record.path)
        if after.object_kind != "ABSENT" or not after.supported:
            return self._result(
                command,
                "UNRESOLVED",
                "RECOVERY_UNRESOLVED",
                tuple(changed + [record.path.value]),
                f"CREATE path {record.path.value!r} reappeared during rollback",
            )
        changed.append(record.path.value)
        return None

    def _roll_back_replace(
        self,
        command: ApplyRecoveryV1,
        transaction: PersistenceTransactionV1,
        record: PersistencePathRecordV1,
        changed: list[str],
    ) -> RecoveryResultV1 | None:
        """Restore one REPLACE path from its verified backup artifact.

        The backup is re-verified (kind/length/digest and the current-
        user-only ACL) immediately before the restore; the restored bytes
        are verified at the preimage digest before the path is listed.
        """
        if record.backup_ref.kind != "PRESENT":
            return self._result(
                command,
                "UNRESOLVED",
                "RECOVERY_UNRESOLVED",
                tuple(changed),
                f"REPLACE path {record.path.value!r} lacks a backup reference",
            )
        ref = self._artifacts.resolve("BACKUP", record.backup_ref.value.digest.value)
        try:
            backup_bytes = self._artifacts.read_verified(ref)
        except PersistenceArtifactIntegrityError as exc:
            return self._result(
                command,
                "UNRESOLVED",
                "RECOVERY_UNRESOLVED",
                tuple(changed),
                f"backup of {record.path.value!r} failed verification: {exc}",
            )
        acl = self._artifacts.verify_acl(ref)
        if acl.current_user_only is not True:
            return self._result(
                command,
                "UNRESOLVED",
                "ARTIFACT_ACL_UNSAFE",
                tuple(changed),
                f"backup of {record.path.value!r} is not current-user-only",
            )
        preimage_digest = record.preimage.raw_bytes_digest
        if (
            preimage_digest is None
            or hashlib.sha256(backup_bytes).hexdigest() != preimage_digest
        ):
            return self._result(
                command,
                "UNRESOLVED",
                "RECOVERY_UNRESOLVED",
                tuple(changed),
                f"backup bytes of {record.path.value!r} do not match its preimage",
            )
        try:
            self._workspace.replace(record.path, backup_bytes)
        except OSError as exc:
            return self._result(
                command,
                "UNRESOLVED",
                "RECOVERY_UNRESOLVED",
                tuple(changed),
                f"cannot restore {record.path.value!r}: {exc}",
            )
        after = self._workspace.observe(record.path)
        if (
            not after.supported
            or after.object_kind != "FILE"
            or after.content_digest.kind == "ABSENT"
            or after.content_digest.value.value != preimage_digest
        ):
            return self._result(
                command,
                "UNRESOLVED",
                "RECOVERY_UNRESOLVED",
                tuple(changed + [record.path.value]),
                f"restored path {record.path.value!r} does not match its preimage",
            )
        changed.append(record.path.value)
        return None

    def _deadline_expired(self, transaction: PersistenceTransactionV1) -> bool:
        """SPEC 4.6 item 11: after the deadline no authoritative workspace
        change is allowed; only the control-plane terminal may persist."""
        return (
            self._clock.now().epoch_milliseconds
            >= transaction.run_deadline.epoch_milliseconds
        )

    def _record_terminal(
        self,
        transaction: PersistenceTransactionV1,
        *,
        state: Literal["COMMITTED", "ROLLED_BACK"],
        path_state: Literal["VERIFIED", "ROLLED_BACK"],
        disposition: RecoveryDispositionV1,
        evidence_digest: str,
        changed_paths: tuple[str, ...],
    ) -> None:
        """Record the service-proven terminal atomically.

        The per-path durable states, the transaction terminal transition,
        and the terminal result row are written inside one immediate
        transaction so the terminal facts cannot be torn.
        """
        with self._transactions.database.immediate_transaction() as tx:
            for record in self._paths.list_ordered(transaction.transaction_id):
                if record.durable_state == path_state:
                    continue
                self._advance_path_state(tx, transaction, record, path_state)
            self._transactions.transition_in(
                tx,
                transaction.transaction_id,
                expected=transaction.state,
                target=state,
                updated_at=self._clock.now(),
                workspace_write_count=self._workspace.write_count,
            )
            self._results.record(
                tx,
                transaction_id=transaction.transaction_id,
                disposition=disposition,
                evidence_digest=evidence_digest,
                changed_paths=changed_paths,
                workspace_write_count=self._workspace.write_count,
                applied_at=self._clock.now(),
            )

    def _advance_path_state(
        self,
        tx: ControlTransactionV1,
        transaction: PersistenceTransactionV1,
        record: PersistencePathRecordV1,
        path_state: Literal["VERIFIED", "ROLLED_BACK"],
    ) -> None:
        """Advance one lagging durable state over the legal pairs only.

        SPEC 4.6 items 7–8: recovery never skips evidence, so a
        NOT_STARTED path advances NOT_STARTED -> REPLACED -> VERIFIED and
        any of the first three states enters ROLLED_BACK directly.
        """
        evidence_digest = (
            record.postimage.raw_bytes_digest
            if path_state == "VERIFIED"
            else (record.preimage.raw_bytes_digest or record.postimage.raw_bytes_digest)
        )
        evidence = PresentV1[DigestV1](
            kind="PRESENT", value=DigestV1(value=evidence_digest)
        )
        if path_state == "VERIFIED" and record.durable_state == "NOT_STARTED":
            self._paths.update_durable_state_in(
                tx,
                transaction.transaction_id,
                record.path.value,
                expected="NOT_STARTED",
                target="REPLACED",
                last_evidence_digest=evidence,
            )
            self._paths.update_durable_state_in(
                tx,
                transaction.transaction_id,
                record.path.value,
                expected="REPLACED",
                target="VERIFIED",
                last_evidence_digest=evidence,
            )
            return
        self._paths.update_durable_state_in(
            tx,
            transaction.transaction_id,
            record.path.value,
            expected=record.durable_state,
            target=path_state,
            last_evidence_digest=evidence,
        )

    def _evidence_digest(
        self, disposition: RecoveryDispositionV1, changed_paths: tuple[str, ...]
    ) -> str:
        """The deterministic evidence identity of one proven outcome."""
        return domain_digest(
            "RecoveryResultV1",
            1,
            {
                "disposition": disposition,
                "changed_paths": changed_paths,
            },
        )

    def _result(
        self,
        command: ApplyRecoveryV1,
        disposition: RecoveryDispositionV1,
        error_code: RecoveryApplyErrorCodeV1 | None,
        changed_paths: tuple[str, ...],
        message: str,
        *,
        evidence_digest: str | None = None,
    ) -> RecoveryResultV1:
        return RecoveryResultV1(
            schema_version=1,
            transaction_id=command.transaction_id,
            disposition=disposition,
            error_code=error_code,
            changed_paths=changed_paths,
            evidence_digest=evidence_digest,
            workspace_write_count=self._workspace.write_count,
            message=message,
        )

"""T26.1 legacy step 26.E: thin approval-bound atomic writeback composition.

``PersistenceCoordinator.persist`` composes the Task 26.A repositories
and Task 26.D artifact storage into the exact approval-bound 1–3-path
atomic writeback protocol of SPEC 4.6: it binds the command to the exact
current Run, verified candidate, final diff, workspace identity, event,
unconsumed approval, and ordered canonical paths before any
authoritative write; publishes preimage/backup artifacts; creates the
durable PREPARED transaction; re-verifies lease/preimage/identity facts;
stops at the safe points (cancellation, deadline before the first write);
consumes the approval once immediately before the first atomic replace;
records per-path progress; verifies every postimage; and publishes
``COMMITTED`` only after every predicate succeeds.  Any interruption
leaves a durable non-terminal transaction rather than false success.
``RealWorkspacePort`` is the concrete atomic-replace workspace port over
the Task 9.1 identity/lease machinery.  This module owns thin
sequencing only: DDL, repository rules, the artifact backend, recovery
preview/apply, and policy expansion remain out of scope (GREEN-4).
"""

from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Protocol

from pydantic import (
    BaseModel,
    ConfigDict,
    StrictStr,
    field_validator,
    model_validator,
)

from vespercode.candidate.final_diff import FinalDiffV1
from vespercode.canonical.path_v1 import CanonicalRelativePathV1
from vespercode.canonical.timestamp_v1 import CanonicalTimestampV1
from vespercode.contracts.evidence import ArtifactRefV1, DigestV1
from vespercode.contracts.optional import AbsentV1, PresentV1
from vespercode.governance.writeback_approval import (
    ApprovalNotConsumableErrorV1,
    ConsumeWritebackApprovalV1,
    WritebackApprovalRepository,
    verify_consumable,
)
from vespercode.governance.writeback_decision import FinalWritebackApprovalV1
from vespercode.governance.writeback_subject import FinalWritebackSubjectV1
from vespercode.persistence.artifacts import (
    PersistenceArtifactAclError,
    PersistenceArtifactStoreV1,
)
from vespercode.persistence.path_record import (
    PersistencePathRecordV1,
    PersistencePreimageV1,
    PersistencePostimageV1,
    WriteOperationV1,
    object_identity_digest,
)
from vespercode.persistence.transaction import (
    PersistencePathRecordRepositoryV1,
    PersistenceTransactionRepositoryV1,
    PersistenceTransactionV1,
    TransactionTransitionErrorV1,
)
from vespercode.profiles.editable import EditablePathPolicyV1
from vespercode.trees.snapshot import SnapshotFileEntryV1, SnapshotTreeV1
from vespercode.workspace.identity_win32 import WorkspaceIdentityV1
from vespercode.workspace.identity_win32 import WorkspaceObjectRejectedV1
from vespercode.workspace.mutex_win32 import WorkspaceLeaseV1, WorkspaceMutex
from vespercode.workspace.object_win32 import inspect_workspace_object

PersistenceOutcomeV1 = Literal["SUCCEEDED", "STOPPED", "RECOVERY_REQUIRED"]
"""SPEC 4.6 output: the closed coordinator outcomes."""

PersistenceErrorCodeV1 = Literal[
    "APPROVAL_REQUIRED",
    "APPROVAL_STALE",
    "PATCH_PATH_NOT_EDITABLE",
    "TREE_INTEGRITY_FAILED",
    "WORKSPACE_CHANGED",
    "WORKSPACE_LOCK_LOST",
    "ARTIFACT_ACL_UNSAFE",
    "PERSISTENCE_FAILED",
    "PERSISTENCE_UNCERTAIN",
    "WRITEBACK_MISMATCH",
]
"""SPEC 4.6 error codes plus the card-mandated ``APPROVAL_REQUIRED``."""


def _reject_coerced_schema_version(value: object) -> object:
    """Reject bool/float/string spellings of the integer schema version."""
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError("schema_version must be the decimal integer 1")
    return value


class PersistenceResultV1(BaseModel):
    """One closed coordinator outcome (SPEC 4.6 output)."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal[1]
    outcome: PersistenceOutcomeV1
    error_code: PersistenceErrorCodeV1 | None = None
    transaction_id: StrictStr | None = None
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


class WritebackBodyV1(BaseModel):
    """One ordered 1–3 writeback body bound to a final-diff entry."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal[1]
    path: CanonicalRelativePathV1
    operation: WriteOperationV1
    body: bytes

    @field_validator("schema_version", mode="before")
    @classmethod
    def _schema_version_is_exact_int(cls, value: object) -> object:
        return _reject_coerced_schema_version(value)


class PersistVerifiedCandidateV1(BaseModel):
    """One exact writeback command binding every current authority fact.

    The command binds the Run, the consumed approval identity, the
    verified candidate digest, the recomputed ``FinalDiffV1`` (with its
    self-bound digest), the workspace identity and frozen preimage
    digest, the run deadline, the current unconsumed approval and its
    immutable subject, and the ordered 1–3 canonical path bodies —
    before any authoritative write (GREEN-1).
    """

    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal[1]
    run_id: StrictStr
    approval_id: StrictStr
    event_id: StrictStr
    candidate_digest: StrictStr
    final_diff: FinalDiffV1
    final_diff_digest: StrictStr
    policy_digest: StrictStr
    workspace_identity_digest: StrictStr
    workspace_preimage_digest: StrictStr
    run_deadline: CanonicalTimestampV1
    approval: FinalWritebackApprovalV1
    approval_subject: FinalWritebackSubjectV1
    postimage_bodies: tuple[WritebackBodyV1, ...]

    @field_validator("schema_version", mode="before")
    @classmethod
    def _schema_version_is_exact_int(cls, value: object) -> object:
        return _reject_coerced_schema_version(value)

    @model_validator(mode="after")
    def _require_bound_command(self) -> PersistVerifiedCandidateV1:
        if not 1 <= len(self.postimage_bodies) <= 3:
            raise ValueError("writeback requires exactly 1–3 ordered paths")
        diff_paths = [entry.path.value for entry in self.final_diff.entries]
        body_paths = [body.path.value for body in self.postimage_bodies]
        if diff_paths != body_paths:
            raise ValueError("postimage bodies must bind the final-diff paths in order")
        diff_ops = [entry.operation for entry in self.final_diff.entries]
        body_ops = [body.operation for body in self.postimage_bodies]
        if diff_ops != body_ops:
            raise ValueError("postimage bodies must bind the final-diff operations")
        return self


class PersistenceCommandFactoryV1:
    """Binds the exact current facts into one approved-run command."""

    def __init__(
        self,
        *,
        final_diff: FinalDiffV1,
        candidate_digest: str,
        policy_digest: str,
        workspace_identity_digest: str,
        workspace_preimage_digest: str,
        approval: FinalWritebackApprovalV1,
        approval_subject: FinalWritebackSubjectV1,
        run_deadline: CanonicalTimestampV1,
        postimage_bodies: tuple[WritebackBodyV1, ...],
    ) -> None:
        self._final_diff = final_diff
        self._candidate_digest = candidate_digest
        self._policy_digest = policy_digest
        self._workspace_identity_digest = workspace_identity_digest
        self._workspace_preimage_digest = workspace_preimage_digest
        self._approval = approval
        self._approval_subject = approval_subject
        self._run_deadline = run_deadline
        self._postimage_bodies = postimage_bodies

    def for_approved_run(
        self,
        run_id: str,
        approval_id: str,
        event_id: str,
    ) -> PersistVerifiedCandidateV1:
        """One command bound to the exact Run, approval, and event."""
        return PersistVerifiedCandidateV1(
            schema_version=1,
            run_id=run_id,
            approval_id=approval_id,
            event_id=event_id,
            candidate_digest=self._candidate_digest,
            final_diff=self._final_diff,
            final_diff_digest=self._final_diff.digest,
            policy_digest=self._policy_digest,
            workspace_identity_digest=self._workspace_identity_digest,
            workspace_preimage_digest=self._workspace_preimage_digest,
            run_deadline=self._run_deadline,
            approval=self._approval,
            approval_subject=self._approval_subject,
            postimage_bodies=self._postimage_bodies,
        )


class WorkspaceWritePort(Protocol):
    """The injected workspace authority: bytes, identities, atomic writes."""

    def identity_digest(self) -> str: ...

    def lease_held(self) -> bool: ...

    def workspace_path(self) -> str: ...

    def read_bytes(self, path: CanonicalRelativePathV1) -> bytes: ...

    def is_absent(self, path: CanonicalRelativePathV1) -> bool: ...

    def object_identity_digest(self, path: CanonicalRelativePathV1) -> str: ...

    def replace(self, path: CanonicalRelativePathV1, body: bytes) -> None: ...

    def delete(self, path: CanonicalRelativePathV1) -> None: ...

    def verify_postimage(self, path: CanonicalRelativePathV1, digest: str) -> bool: ...

    @property
    def write_count(self) -> int: ...

    def verify_untouched(
        self, snapshot_tree_digest: str, involved_paths: tuple[str, ...]
    ) -> bool: ...


class ClockPort(Protocol):
    """The injected deterministic clock (sole current-time source)."""

    def now(self) -> CanonicalTimestampV1: ...


class CancellationPort(Protocol):
    """The injected cancellation fact checked at the pre-write safe point."""

    def is_cancelled(self) -> bool: ...


class NoCancellationPort:
    """The default cancellation port: never cancelled."""

    def is_cancelled(self) -> bool:
        return False


@dataclass(frozen=True)
class WritebackFaultPointV1:
    """One deterministic interruption point in the writeback protocol.

    ``kind`` is the guarded durable event (PREPARED/WRITING/REPLACE/
    PROGRESS/TERMINAL), ``position`` is BEFORE or AFTER that event, and
    ``sequence`` is the 1-based sorted path sequence for REPLACE/PROGRESS
    (0 for the protocol-level events).
    """

    kind: Literal["PREPARED", "WRITING", "REPLACE", "PROGRESS", "TERMINAL"]
    position: Literal["BEFORE", "AFTER"]
    sequence: int = 0

    def __post_init__(self) -> None:
        if self.sequence < 0:
            raise ValueError("fault point sequence must be non-negative")
        if self.kind in ("REPLACE", "PROGRESS") and self.sequence == 0:
            raise ValueError(f"fault point kind {self.kind!r} requires a path sequence")
        if self.kind not in ("REPLACE", "PROGRESS") and self.sequence != 0:
            raise ValueError(
                f"fault point kind {self.kind!r} cannot carry a path sequence"
            )


class WritebackFaultPort(Protocol):
    """Injected deterministic interruption port for the protocol."""

    def raise_at(self, point: WritebackFaultPointV1) -> None: ...


class NoWritebackFaultPort:
    """The default fault port: never interrupts."""

    def raise_at(self, point: WritebackFaultPointV1) -> None:
        return None


class ArmedFaultPort:
    """A deterministic fault port that interrupts exactly one armed point.

    The production fault-injection seam (SPEC 5.4: 测试模式允许注入故障点):
    an armed point raises the closed ``PersistenceFaultInjectedError``
    and every other point passes.
    """

    def __init__(self, point: WritebackFaultPointV1) -> None:
        self._point = point

    def raise_at(self, point: WritebackFaultPointV1) -> None:
        if point == self._point:
            raise PersistenceFaultInjectedError(f"armed fault point: {point}")


class PersistenceFaultInjectedError(Exception):
    """Deterministic crash-like interruption at an armed fault point."""


class RealWorkspacePort:
    """The concrete workspace port over Task 9.1 identity/lease machinery.

    Reads and inspects real Win32 final-object identities, replaces
    files atomically (same-directory temp + flush + fsync + replace),
    deletes only under the recovery apply contract, and counts every
    authoritative workspace change.  A mutation ``OSError`` (permission,
    disk, or a concurrent external removal in the replace/delete window)
    propagates as the crash-like fault the persistence contract binds:
    the durable transaction stays non-terminal, no false success is ever
    reported, and recovery decides the disposition from the actual bytes
    (SPEC 4.6 item 8; quality review M-7).
    """

    def __init__(
        self,
        identity: WorkspaceIdentityV1,
        lease: WorkspaceLeaseV1 | None = None,
        snapshot: SnapshotTreeV1 | None = None,
    ) -> None:
        self._identity = identity
        self._lease = lease
        self._snapshot = snapshot
        self._released = False
        self._write_count = 0

    def identity_digest(self) -> str:
        return self._identity.digest

    def lease_held(self) -> bool:
        return self._lease is not None and not self._released

    def workspace_path(self) -> str:
        return self._identity.canonical_absolute_path

    def release(self) -> None:
        """Explicitly release the owned workspace lease (idempotent)."""
        if self._lease is not None and not self._released:
            WorkspaceMutex.release(self._lease)
            self._released = True

    def _confined_target(self, path: CanonicalRelativePathV1) -> Path:
        root = Path(self._identity.canonical_absolute_path)
        target = (root / path.value).resolve()
        if not target.is_relative_to(root):
            raise ValueError(f"write path escapes the workspace: {path.value!r}")
        return target

    def read_bytes(self, path: CanonicalRelativePathV1) -> bytes:
        return self._confined_target(path).read_bytes()

    def is_absent(self, path: CanonicalRelativePathV1) -> bool:
        return not self._confined_target(path).exists()

    def object_identity_digest(self, path: CanonicalRelativePathV1) -> str:
        facts = inspect_workspace_object(self._identity, path)
        return object_identity_digest(facts.volume_serial_number, facts.file_id_128_hex)

    def replace(self, path: CanonicalRelativePathV1, body: bytes) -> None:
        target = self._confined_target(path)
        tmp = target.with_name(target.name + ".vesper-tmp")
        with tmp.open("wb") as handle:
            handle.write(body)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, target)
        self._write_count += 1

    def delete(self, path: CanonicalRelativePathV1) -> None:
        self._confined_target(path).unlink()
        self._write_count += 1

    def verify_postimage(self, path: CanonicalRelativePathV1, digest: str) -> bool:
        try:
            observed = hashlib.sha256(
                self._confined_target(path).read_bytes()
            ).hexdigest()
        except OSError:
            return False
        return observed == digest

    @property
    def write_count(self) -> int:
        return self._write_count

    def verify_untouched(
        self, snapshot_tree_digest: str, involved_paths: tuple[str, ...]
    ) -> bool:
        """Re-verify the tracked files outside the writeback (SPEC 4.6
        item 9: 重验未涉及 tracked 文件未变化).

        The bound snapshot is the authority: its digest must match the
        requested identity and every tracked file outside the involved
        paths must still carry its sealed content digest.  An unbound
        snapshot fails closed.
        """
        if self._snapshot is None:
            return False
        if self._snapshot.root_digest != snapshot_tree_digest:
            return False
        for entry in self._snapshot.entries:
            if not isinstance(entry, SnapshotFileEntryV1):
                continue
            if entry.path.value in involved_paths:
                continue
            try:
                raw = self._confined_target(entry.path).read_bytes()
            except OSError:
                return False
            if hashlib.sha256(raw).hexdigest() != entry.content_ref.sha256:
                return False
        return True


class PersistenceCoordinator:
    """The thin approved writeback protocol composition (SPEC 4.6)."""

    def __init__(
        self,
        *,
        transaction_repository: PersistenceTransactionRepositoryV1,
        path_repository: PersistencePathRecordRepositoryV1,
        artifact_store: PersistenceArtifactStoreV1,
        approval_repository: WritebackApprovalRepository,
        workspace: WorkspaceWritePort,
        policy: EditablePathPolicyV1,
        clock: ClockPort,
        cancel: CancellationPort | None = None,
        faults: WritebackFaultPort | None = None,
    ) -> None:
        self._transactions = transaction_repository
        self._paths = path_repository
        self._artifacts = artifact_store
        self._approvals = approval_repository
        self._workspace = workspace
        self._policy = policy
        self._clock = clock
        self._cancel = cancel if cancel is not None else NoCancellationPort()
        self._faults = faults if faults is not None else NoWritebackFaultPort()

    @property
    def artifact_store(self) -> PersistenceArtifactStoreV1:
        """The owned artifact storage (test/evidence seam)."""
        return self._artifacts

    @property
    def path_repository(self) -> PersistencePathRecordRepositoryV1:
        """The owned ordered path-record repository (test/evidence seam)."""
        return self._paths

    @property
    def transaction_repository(self) -> PersistenceTransactionRepositoryV1:
        """The owned persistence-transaction repository (test/evidence seam)."""
        return self._transactions

    def persist(self, command: PersistVerifiedCandidateV1) -> PersistenceResultV1:
        """Execute the exact approval-bound 1–3-path atomic writeback.

        Ends only in ``SUCCEEDED`` (verified COMMITTED), a durable
        non-terminal transaction, or a closed zero-write stop; the
        approval is consumed at most once, immediately before the first
        atomic replace, and is never restored afterwards (SPEC 4.6).
        """
        # 1. Frozen editable-policy binding (SPEC 4.6 precondition 1):
        # every entry must hit the frozen editable policy (越界 ->
        # PATCH_PATH_NOT_EDITABLE) and the policy digest must transmit the
        # same editable policy identity (不一致 -> TREE_INTEGRITY_FAILED).
        for body in command.postimage_bodies:
            if not self._policy.matches(body.path, body.operation):
                return self._result(
                    "STOPPED",
                    "PATCH_PATH_NOT_EDITABLE",
                    None,
                    f"path {body.path.value!r} is not editable for {body.operation}",
                )
        if command.policy_digest != self._policy.digest:
            return self._result(
                "STOPPED",
                "TREE_INTEGRITY_FAILED",
                None,
                "policy digest does not transmit the frozen editable policy",
            )
        # 2. Final-diff and body binding (SPEC 4.6 preconditions 2–3).
        if command.final_diff_digest != command.final_diff.digest:
            return self._result(
                "STOPPED",
                "TREE_INTEGRITY_FAILED",
                None,
                "final diff digest does not bind its exact rows",
            )
        for entry, body in zip(command.final_diff.entries, command.postimage_bodies):
            if hashlib.sha256(body.body).hexdigest() != entry.postimage_digest:
                return self._result(
                    "STOPPED",
                    "TREE_INTEGRITY_FAILED",
                    None,
                    f"postimage body for {body.path.value!r} does not match its diff",
                )
        # 3. Subject binding (SPEC 4.4.2 / AC-03).
        subject = command.approval_subject
        if (
            subject.final_diff_digest != command.final_diff_digest
            or subject.candidate_digest != command.candidate_digest
            or subject.workspace_preimage_digest != command.workspace_preimage_digest
        ):
            return self._result(
                "STOPPED",
                "TREE_INTEGRITY_FAILED",
                None,
                "approval subject drifts from the current candidate/diff/preimage",
            )
        # 4–5. Workspace identity and lease (SPEC 4.6 precondition 6).
        if self._workspace.identity_digest() != command.workspace_identity_digest:
            return self._result(
                "STOPPED",
                "WORKSPACE_CHANGED",
                None,
                "authoritative workspace identity changed",
            )
        if not self._workspace.lease_held():
            return self._result(
                "STOPPED",
                "WORKSPACE_LOCK_LOST",
                None,
                "cross-process workspace lease is not held",
            )
        # 6. Frozen-preimage observation (read-only; SPEC 4.6 precondition 6).
        observed = self._observe_preimages(command)
        if isinstance(observed, PersistenceResultV1):
            return observed
        # 7. Approval consumability pre-check (pure, zero side effects):
        # a missing or non-consumable approval stops before any durable
        # record or artifact exists (zero residue).
        precheck = self._precheck_approval(command)
        if precheck is not None:
            return precheck
        # 8. Backup-before-replace: publish preimage/backup artifacts.
        artifact_refs = self._publish_artifacts(command, observed)
        if isinstance(artifact_refs, PersistenceResultV1):
            return artifact_refs
        # 8. Durable PREPARED transaction with the full path records.
        transaction = self._prepare_transaction(command)
        self._faults.raise_at(WritebackFaultPointV1("PREPARED", "BEFORE"))
        try:
            self._transactions.create(transaction)
            for record in self._records_for(command, observed, artifact_refs):
                self._paths.append(transaction.transaction_id, record)
        except ValueError as exc:
            # A duplicate transaction id (replayed event identity) or a
            # competing active transaction fails closed with zero writes.
            return self._result(
                "STOPPED",
                "PERSISTENCE_FAILED",
                None,
                str(exc),
            )
        self._faults.raise_at(WritebackFaultPointV1("PREPARED", "AFTER"))
        # 9. Step-3 re-verification: lease, preimages, and identities still
        # match the frozen evidence (SPEC 4.6 item 3).
        reverified = self._reverify_preimages(transaction, command)
        if reverified is not None:
            return reverified
        # 10. Cancellation safe point (SPEC 4.2.6: before the first replace).
        # 11. Deadline before the first write (SPEC 4.6 item 11).  Both
        # zero-write stops use the closed-error wrapper: a concurrent
        # recovery resolving the PREPARED transaction first maps the CAS
        # failure to a closed result, never a raw exception (review I-2).
        try:
            if self._cancel.is_cancelled():
                self._transactions.transition(
                    transaction.transaction_id,
                    expected="PREPARED",
                    target="ROLLED_BACK",
                    updated_at=self._clock.now(),
                    workspace_write_count=0,
                )
                return self._result(
                    "STOPPED",
                    None,
                    transaction.transaction_id,
                    "cancelled before the first workspace write",
                )
            if self._deadline_expired(command):
                self._transactions.transition(
                    transaction.transaction_id,
                    expected="PREPARED",
                    target="ROLLED_BACK",
                    updated_at=self._clock.now(),
                    workspace_write_count=0,
                )
                return self._result(
                    "STOPPED",
                    None,
                    transaction.transaction_id,
                    "run_deadline expired before the first workspace write",
                )
        except TransactionTransitionErrorV1 as exc:
            return self._result(
                "RECOVERY_REQUIRED",
                "PERSISTENCE_FAILED",
                transaction.transaction_id,
                f"writeback stop transition failed: {exc}",
            )
        # 12. Consume the approval once, immediately before the first
        # atomic replace (GREEN-2 / SPEC 4.4.2).  The transactional
        # re-verification decides the race; a consumption failure performs
        # zero workspace writes and leaves the durable PREPARED
        # transaction (the approval is never restored).
        now = self._clock.now()
        consume_command = ConsumeWritebackApprovalV1(
            approval_id=command.approval_id,
            subject=subject,
            event_id=command.event_id,
            consumed_at=now,
        )
        consume_result = self._approvals.consume(consume_command)
        if consume_result.kind != "CONSUMED":
            code: PersistenceErrorCodeV1 = (
                "APPROVAL_REQUIRED"
                if consume_result.kind == "NOT_FOUND"
                else "APPROVAL_STALE"
            )
            return self._result(
                "STOPPED",
                code,
                transaction.transaction_id,
                f"approval consumption failed: {consume_result.message}",
            )
        # 13. First replace turns the transaction WRITING (SPEC 4.6 item 5).
        # From here on every repository transition failure is mapped to a
        # closed result (a concurrent recovery may race the CAS), never a
        # raw exception (review M-2).
        try:
            self._faults.raise_at(WritebackFaultPointV1("WRITING", "BEFORE"))
            self._transactions.transition(
                transaction.transaction_id,
                expected="PREPARED",
                target="WRITING",
                updated_at=self._clock.now(),
                workspace_write_count=0,
            )
            self._faults.raise_at(WritebackFaultPointV1("WRITING", "AFTER"))
            # 14. Per-path replaces with pre-write rechecks, progress, and
            # postimage verification (SPEC 4.6 items 4–8).
            for body in command.postimage_bodies:
                stalled = self._write_one_path(transaction, command, body)
                if stalled is not None:
                    return stalled
            # 15. Terminal COMMITTED only after every predicate succeeds
            # (SPEC 4.6 items 9–10): re-verify that the tracked files
            # outside the writeback are unchanged.
            involved = tuple(body.path.value for body in command.postimage_bodies)
            if not self._workspace.verify_untouched(
                command.final_diff.snapshot_tree_digest, involved
            ):
                return self._fail_uncertain(
                    transaction,
                    "WORKSPACE_CHANGED",
                    "a tracked file outside the writeback changed",
                )
        except TransactionTransitionErrorV1 as exc:
            return self._result(
                "RECOVERY_REQUIRED",
                "PERSISTENCE_FAILED",
                transaction.transaction_id,
                f"writeback transition failed: {exc}",
            )
        self._faults.raise_at(WritebackFaultPointV1("TERMINAL", "BEFORE"))
        self._transactions.transition(
            transaction.transaction_id,
            expected="WRITING",
            target="COMMITTED",
            updated_at=self._clock.now(),
            workspace_write_count=self._workspace.write_count,
        )
        self._faults.raise_at(WritebackFaultPointV1("TERMINAL", "AFTER"))
        return self._result(
            "SUCCEEDED",
            None,
            transaction.transaction_id,
            "writeback committed",
        )

    def _result(
        self,
        outcome: PersistenceOutcomeV1,
        error_code: PersistenceErrorCodeV1 | None,
        transaction_id: str | None,
        message: str,
    ) -> PersistenceResultV1:
        return PersistenceResultV1(
            schema_version=1,
            outcome=outcome,
            error_code=error_code,
            transaction_id=transaction_id,
            workspace_write_count=self._workspace.write_count,
            message=message,
        )

    def _deadline_expired(self, command: PersistVerifiedCandidateV1) -> bool:
        return (
            self._clock.now().epoch_milliseconds
            >= command.run_deadline.epoch_milliseconds
        )

    def _observe_preimages(
        self, command: PersistVerifiedCandidateV1
    ) -> dict[str, PersistencePreimageV1] | PersistenceResultV1:
        """Observe the frozen preimage evidence for every path (read-only).

        A present preimage must match the diff's content digest and a
        CREATE target must be absent; any drift is an external workspace
        change and fails closed before any durable write.
        """
        observed: dict[str, PersistencePreimageV1] = {}
        entries = {entry.path.value: entry for entry in command.final_diff.entries}
        for body in command.postimage_bodies:
            entry = entries[body.path.value]
            if body.operation == "CREATE":
                if not self._workspace.is_absent(body.path):
                    return self._result(
                        "STOPPED",
                        "WORKSPACE_CHANGED",
                        None,
                        f"CREATE target {body.path.value!r} already exists",
                    )
                observed[body.path.value] = PersistencePreimageV1(kind="ABSENT")
                continue
            try:
                raw = self._workspace.read_bytes(body.path)
                identity = self._workspace.object_identity_digest(body.path)
            except (OSError, KeyError, WorkspaceObjectRejectedV1):
                return self._result(
                    "STOPPED",
                    "WORKSPACE_CHANGED",
                    None,
                    f"cannot observe the preimage of {body.path.value!r}",
                )
            preimage_digest = entry.preimage.content_digest
            if (
                preimage_digest is None
                or hashlib.sha256(raw).hexdigest() != preimage_digest
            ):
                return self._result(
                    "STOPPED",
                    "WORKSPACE_CHANGED",
                    None,
                    f"preimage bytes of {body.path.value!r} drifted from the diff",
                )
            metadata = entry.preimage.text_metadata
            if metadata is None:
                return self._result(
                    "STOPPED",
                    "TREE_INTEGRITY_FAILED",
                    None,
                    f"REPLACE diff entry {body.path.value!r} lacks preimage metadata",
                )
            observed[body.path.value] = PersistencePreimageV1(
                kind="PRESENT",
                raw_bytes_digest=preimage_digest,
                text_metadata=metadata,
                object_identity_digest=identity,
            )
        return observed

    def _publish_artifacts(
        self,
        command: PersistVerifiedCandidateV1,
        observed: dict[str, PersistencePreimageV1],
    ) -> dict[str, str] | PersistenceResultV1:
        """Publish PREIMAGE and BACKUP artifacts for every REPLACE path.

        The backup exists before the first atomic replace (backup-before-
        replace); an unsafe or unproven artifact ACL fails closed with
        zero records and zero workspace writes.
        """
        refs: dict[str, str] = {}
        for body in command.postimage_bodies:
            if body.operation != "REPLACE":
                continue
            preimage = observed[body.path.value]
            if preimage.raw_bytes_digest is None:
                return self._result(
                    "STOPPED",
                    "PERSISTENCE_FAILED",
                    None,
                    f"missing preimage evidence for {body.path.value!r}",
                )
            try:
                preimage_bytes = self._workspace.read_bytes(body.path)
            except (OSError, KeyError, WorkspaceObjectRejectedV1):
                return self._result(
                    "STOPPED",
                    "WORKSPACE_CHANGED",
                    None,
                    f"cannot read the preimage of {body.path.value!r}",
                )
            if hashlib.sha256(preimage_bytes).hexdigest() != preimage.raw_bytes_digest:
                return self._result(
                    "STOPPED",
                    "WORKSPACE_CHANGED",
                    None,
                    f"preimage of {body.path.value!r} drifted before backup",
                )
            try:
                preimage_ref = self._artifacts.put("PREIMAGE", preimage_bytes)
                backup_ref = self._artifacts.put("BACKUP", preimage_bytes)
            except PersistenceArtifactAclError as exc:
                return self._result(
                    "STOPPED",
                    "ARTIFACT_ACL_UNSAFE",
                    None,
                    str(exc),
                )
            except OSError as exc:
                return self._result(
                    "STOPPED",
                    "PERSISTENCE_FAILED",
                    None,
                    str(exc),
                )
            if (
                preimage_ref.digest.value != preimage.raw_bytes_digest
                or backup_ref.digest.value != preimage.raw_bytes_digest
            ):
                return self._result(
                    "STOPPED",
                    "WORKSPACE_CHANGED",
                    None,
                    f"preimage artifact for {body.path.value!r} drifted",
                )
            refs[body.path.value] = backup_ref.artifact_id
        return refs

    def _records_for(
        self,
        command: PersistVerifiedCandidateV1,
        observed: dict[str, PersistencePreimageV1],
        backup_refs: dict[str, str],
    ) -> tuple[PersistencePathRecordV1, ...]:
        """The frozen body-free path records for the PREPARED log."""
        records: list[PersistencePathRecordV1] = []
        for sequence, body in enumerate(command.postimage_bodies, start=1):
            entry = next(
                e for e in command.final_diff.entries if e.path.value == body.path.value
            )
            if body.operation == "CREATE":
                backup_ref: AbsentV1 | PresentV1[ArtifactRefV1] = AbsentV1(
                    kind="ABSENT"
                )
            else:
                preimage_digest = observed[body.path.value].raw_bytes_digest
                if preimage_digest is None:
                    raise ValueError(f"missing preimage digest for {body.path.value!r}")
                backup_ref = PresentV1[ArtifactRefV1](
                    kind="PRESENT",
                    value=ArtifactRefV1(
                        artifact_id=backup_refs[body.path.value],
                        digest=DigestV1(value=preimage_digest),
                    ),
                )
            records.append(
                PersistencePathRecordV1(
                    schema_version=1,
                    path=body.path,
                    operation=body.operation,
                    preimage=observed[body.path.value],
                    postimage=PersistencePostimageV1(
                        raw_bytes_digest=entry.postimage_digest,
                        text_metadata=entry.postimage_text_metadata,
                        required_object_policy_digest=command.policy_digest,
                    ),
                    sequence=sequence,
                    durable_state="NOT_STARTED",
                    backup_ref=backup_ref,
                    last_evidence_digest=AbsentV1(kind="ABSENT"),
                )
            )
        return tuple(records)

    def _prepare_transaction(
        self,
        command: PersistVerifiedCandidateV1,
    ) -> PersistenceTransactionV1:
        """One durable PREPARED transaction value (SPEC 4.6 item 2)."""
        now = self._clock.now()
        return PersistenceTransactionV1(
            schema_version=1,
            transaction_id="txn-"
            + hashlib.sha256(
                (
                    command.workspace_identity_digest
                    + command.final_diff_digest
                    + command.event_id
                ).encode("utf-8")
            ).hexdigest()[:32],
            run_id=command.run_id,
            approval_id=command.approval_id,
            workspace_identity_digest=command.workspace_identity_digest,
            workspace_path=self._workspace_absolute_path(command),
            final_diff_digest=command.final_diff_digest,
            policy_digest=command.policy_digest,
            state="PREPARED",
            run_deadline=command.run_deadline,
            prepared_at=now,
            updated_at=now,
            workspace_write_count=0,
        )

    def _workspace_absolute_path(self, command: PersistVerifiedCandidateV1) -> str:
        """The canonical workspace path text from the port."""
        return self._workspace.workspace_path()

    def _reverify_preimages(
        self,
        transaction: PersistenceTransactionV1,
        command: PersistVerifiedCandidateV1,
    ) -> PersistenceResultV1 | None:
        """Step-3 re-verification: lease, bytes, and identities still match.

        A failure keeps every path NOT_STARTED with zero workspace
        writes; the approval is not yet consumed and is never restored
        afterwards (SPEC 4.6 item 3).
        """
        if not self._workspace.lease_held():
            return self._result(
                "RECOVERY_REQUIRED",
                "WORKSPACE_LOCK_LOST",
                transaction.transaction_id,
                "workspace lease lost before the first write",
            )
        records = {
            record.path.value: record
            for record in self._paths.list_ordered(transaction.transaction_id)
        }
        for body in command.postimage_bodies:
            record = records[body.path.value]
            if record.preimage.kind == "ABSENT":
                if not self._workspace.is_absent(body.path):
                    return self._result(
                        "RECOVERY_REQUIRED",
                        "WORKSPACE_CHANGED",
                        transaction.transaction_id,
                        f"CREATE target {body.path.value!r} appeared before the first write",
                    )
                continue
            try:
                raw = self._workspace.read_bytes(body.path)
                identity = self._workspace.object_identity_digest(body.path)
            except (OSError, KeyError, WorkspaceObjectRejectedV1):
                return self._result(
                    "RECOVERY_REQUIRED",
                    "WORKSPACE_CHANGED",
                    transaction.transaction_id,
                    f"cannot re-observe the preimage of {body.path.value!r}",
                )
            if (
                hashlib.sha256(raw).hexdigest() != record.preimage.raw_bytes_digest
                or identity != record.preimage.object_identity_digest
            ):
                return self._result(
                    "RECOVERY_REQUIRED",
                    "WORKSPACE_CHANGED",
                    transaction.transaction_id,
                    f"preimage of {body.path.value!r} drifted before the first write",
                )
        return None

    def _precheck_approval(
        self, command: PersistVerifiedCandidateV1
    ) -> PersistenceResultV1 | None:
        """The pure approval consumability pre-check (zero side effects).

        Missing, non-PENDING, subject-drifted, or expired approvals stop
        before any durable record or artifact exists; the transactional
        consume later re-verifies every fact immediately before the first
        atomic replace.
        """
        approval = command.approval
        if approval.approval_id != command.approval_id:
            return self._result(
                "STOPPED",
                "APPROVAL_REQUIRED",
                None,
                "command does not bind its approval identity",
            )
        if approval.run_id != command.run_id:
            return self._result(
                "STOPPED",
                "APPROVAL_REQUIRED",
                None,
                "approval does not bind the current run",
            )
        if approval.subject_digest.value != command.approval_subject.digest:
            return self._result(
                "STOPPED",
                "APPROVAL_STALE",
                None,
                "approval subject drifts from the current subject",
            )
        if approval.status != "PENDING":
            return self._result(
                "STOPPED",
                "APPROVAL_REQUIRED",
                None,
                f"no consumable approval: status is {approval.status}",
            )
        consume_command = ConsumeWritebackApprovalV1(
            approval_id=command.approval_id,
            subject=command.approval_subject,
            event_id=command.event_id,
            consumed_at=self._clock.now(),
        )
        try:
            verify_consumable(approval, consume_command)
        except ApprovalNotConsumableErrorV1 as exc:
            code: PersistenceErrorCodeV1 = (
                "APPROVAL_STALE"
                if exc.error_code in ("STALE", "EXPIRED")
                else "APPROVAL_REQUIRED"
            )
            return self._result(
                "STOPPED",
                code,
                None,
                f"approval is not consumable: {exc.error_code}",
            )
        return None

    def _write_one_path(
        self,
        transaction: PersistenceTransactionV1,
        command: PersistVerifiedCandidateV1,
        body: WritebackBodyV1,
    ) -> PersistenceResultV1 | None:
        """One atomic replace with pre-write rechecks and verification."""
        # SPEC 4.6 item 11: check the deadline before every authoritative
        # write.  A provably zero-write transaction (deadline crossing
        # between the step-11 check and the first replace) ends ROLLED_BACK
        # with outcome STOPPED; a transaction with completed writes ends
        # UNRESOLVED with no further writes.
        if self._deadline_expired(command):
            if self._workspace.write_count == 0:
                self._transactions.transition(
                    transaction.transaction_id,
                    expected="WRITING",
                    target="ROLLED_BACK",
                    updated_at=self._clock.now(),
                    workspace_write_count=0,
                )
                return self._result(
                    "STOPPED",
                    None,
                    transaction.transaction_id,
                    "run_deadline expired before the first workspace write",
                )
            self._transactions.transition(
                transaction.transaction_id,
                expected="WRITING",
                target="UNRESOLVED",
                updated_at=self._clock.now(),
                workspace_write_count=self._workspace.write_count,
            )
            return self._result(
                "RECOVERY_REQUIRED",
                "PERSISTENCE_UNCERTAIN",
                transaction.transaction_id,
                f"run_deadline expired before writing {body.path.value!r}",
            )
        # SPEC 4.6 item 4: re-verify lease, preimage, and identity.
        if not self._workspace.lease_held():
            return self._fail_uncertain(
                transaction,
                "WORKSPACE_LOCK_LOST",
                "workspace lease lost during writeback",
            )
        record = next(
            r
            for r in self._paths.list_ordered(transaction.transaction_id)
            if r.path.value == body.path.value
        )
        if record.preimage.kind == "ABSENT":
            if not self._workspace.is_absent(body.path):
                return self._fail_uncertain(
                    transaction,
                    "WORKSPACE_CHANGED",
                    f"CREATE target {body.path.value!r} appeared before its write",
                )
        else:
            try:
                raw = self._workspace.read_bytes(body.path)
                identity = self._workspace.object_identity_digest(body.path)
            except (OSError, KeyError, WorkspaceObjectRejectedV1):
                return self._fail_uncertain(
                    transaction,
                    "WORKSPACE_CHANGED",
                    f"cannot re-observe {body.path.value!r} before its write",
                )
            if (
                hashlib.sha256(raw).hexdigest() != record.preimage.raw_bytes_digest
                or identity != record.preimage.object_identity_digest
            ):
                return self._fail_uncertain(
                    transaction,
                    "WORKSPACE_CHANGED",
                    f"preimage of {body.path.value!r} drifted before its write",
                )
        self._faults.raise_at(
            WritebackFaultPointV1("REPLACE", "BEFORE", record.sequence)
        )
        self._workspace.replace(body.path, body.body)
        self._faults.raise_at(
            WritebackFaultPointV1("REPLACE", "AFTER", record.sequence)
        )
        # SPEC 4.6 item 6: REPLACED only when the object exactly matches
        # the postimage; write-after verification then records VERIFIED.
        if not self._workspace.verify_postimage(
            body.path, record.postimage.raw_bytes_digest
        ):
            return self._fail_uncertain(
                transaction,
                "WRITEBACK_MISMATCH",
                f"postimage of {body.path.value!r} does not match after the replace",
            )
        self._faults.raise_at(
            WritebackFaultPointV1("PROGRESS", "BEFORE", record.sequence)
        )
        evidence = PresentV1[DigestV1](
            kind="PRESENT", value=DigestV1(value=record.postimage.raw_bytes_digest)
        )
        self._paths.update_durable_state(
            transaction.transaction_id,
            body.path.value,
            expected="NOT_STARTED",
            target="REPLACED",
            last_evidence_digest=evidence,
        )
        if not self._workspace.verify_postimage(
            body.path, record.postimage.raw_bytes_digest
        ):
            return self._fail_uncertain(
                transaction,
                "WRITEBACK_MISMATCH",
                f"write-after verification failed for {body.path.value!r}",
            )
        self._paths.update_durable_state(
            transaction.transaction_id,
            body.path.value,
            expected="REPLACED",
            target="VERIFIED",
            last_evidence_digest=evidence,
        )
        self._faults.raise_at(
            WritebackFaultPointV1("PROGRESS", "AFTER", record.sequence)
        )
        return None

    def _fail_uncertain(
        self,
        transaction: PersistenceTransactionV1,
        error_code: PersistenceErrorCodeV1,
        message: str,
    ) -> PersistenceResultV1:
        """A mid-writeback failure: no further writes, durable UNRESOLVED."""
        self._transactions.transition(
            transaction.transaction_id,
            expected="WRITING",
            target="UNRESOLVED",
            updated_at=self._clock.now(),
            workspace_write_count=self._workspace.write_count,
        )
        return self._result(
            "RECOVERY_REQUIRED",
            error_code,
            transaction.transaction_id,
            message,
        )

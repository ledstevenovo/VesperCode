"""T14.1 legacy step 14.B: atomic final-writeback wait decision lifecycle.

``FinalWritebackDecisionServiceV1.decide`` locks the exact PENDING
final-writeback wait inside one immediate transaction (reusing the T07.2
wait-lock/commit CAS), reloads its current subject binding, evaluates
the clock state, creates at most one PENDING approval for an exact
current unexpired APPROVE (persisting the immutable subject facts
first), records the decision, and transitions the Run to
``RUNNING(PERSISTENCE)``.  REJECT, expiry, stale subject, wrong binding,
cancelled runs, and duplicate/replay-conflict decisions remain atomic
and create no approval and no resume; a hard DENY never reaches this
layer (the T13.1 policy blocks it before a wait exists).  Final registry
edits, approval consumption, candidate-byte persistence, and any DENY
override remain out of scope (GREEN-4).
"""

from __future__ import annotations

from typing import Literal, TypeAlias, cast

from pydantic import BaseModel, ConfigDict, StrictStr, field_validator

from vespercode.canonical.timestamp_v1 import CanonicalTimestampV1
from vespercode.contracts.evidence import DigestV1
from vespercode.contracts.optional import AbsentV1, PresentV1
from vespercode.contracts.run import RunStateV1, WaitDecisionV1
from vespercode.governance.writeback_subject import FinalWritebackSubjectV1
from vespercode.runs.lifecycle import LifecycleRules
from vespercode.storage.connection import (
    ControlDatabase,
    ControlTransactionV1,
)
from vespercode.storage.run_repository import RunRepository

FinalWritebackApprovalStatusV1: TypeAlias = Literal[
    "PENDING",
    "REJECTED",
    "EXPIRED",
    "CONSUMED",
]
"""SPEC §4.4.2: the closed FinalWritebackApproval status vocabulary."""

FinalWritebackDecisionKindV1: TypeAlias = Literal[
    "APPROVED",
    "REJECTED",
    "EXPIRED",
    "STALE",
    "BINDING_MISMATCH",
    "CANCELLED",
    "NOT_FOUND",
    "REPLAY",
    "CONFLICT",
]
"""The closed outcomes of one final-writeback decision."""


class FinalWritebackApprovalV1(BaseModel):
    """SPEC §4.4.2: the mutable approval record bound to its subject/wait.

    The value carries ``schema_version`` per the SPEC block; the v0010
    table stores the identity columns and the run/wait FKs without a
    schema_version column, so the model is the value contract and the
    DDL the storage contract.  The mutable status never enters the
    subject (AC-03).
    """

    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal[1]
    approval_id: StrictStr
    subject_digest: DigestV1
    run_id: StrictStr
    wait_id: StrictStr
    created_at: CanonicalTimestampV1
    status: FinalWritebackApprovalStatusV1

    @field_validator("approval_id", "run_id", "wait_id")
    @classmethod
    def _identifiers_must_be_non_empty(cls, value: str) -> str:
        if value == "":
            raise ValueError("identifiers must be non-empty")
        return value


class DecideFinalWritebackV1(BaseModel):
    """One closed final-writeback decision command.

    The decision binds wait_id/run_id/wait_kind/subject_digest/event/time
    (T07.2 ``WaitDecisionV1``) and carries the immutable subject to
    approve plus the harness-generated approval id; nothing else may
    influence the outcome.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)
    decision: WaitDecisionV1
    subject: FinalWritebackSubjectV1
    approval_id: StrictStr


class FinalWritebackDecisionResultV1(BaseModel):
    """One closed decision outcome; ``approval`` is present on APPROVED."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    kind: FinalWritebackDecisionKindV1
    message: StrictStr
    approval: FinalWritebackApprovalV1 | None = None


class _DecisionRollback(Exception):
    """Internal sentinel: roll back the transaction and return the result.

    The immediate-transaction context manager commits on clean exit and
    rolls back only on an exception; any decision outcome that must not
    persist its in-transaction writes raises this sentinel so the whole
    transaction (wait reservation, subject/approval rows, run transition)
    rolls back atomically before the result is returned (T15 lesson).
    """

    def __init__(self, result: FinalWritebackDecisionResultV1) -> None:
        super().__init__(result.message)
        self.result = result


def _read_wait_row(
    tx: ControlTransactionV1,
    wait_id: str,
) -> tuple[str, str, str, str, str, str, str, str | None] | None:
    """The wait identity/binding row inside the caller transaction."""
    row = tx.execute(
        "SELECT wait_id, run_id, wait_kind, source_phase, subject_digest,"
        " created_at, expires_at, decision FROM wait_contexts"
        " WHERE wait_id = ?",
        (wait_id,),
    ).fetchone()
    if row is None:
        return None
    decision: str | None = row[7]
    return (
        str(row[0]),
        str(row[1]),
        str(row[2]),
        str(row[3]),
        str(row[4]),
        str(row[5]),
        str(row[6]),
        decision,
    )


class FinalWritebackDecisionServiceV1:
    """Transaction-bound final-writeback decision lifecycle over v0010."""

    def __init__(self, database: ControlDatabase) -> None:
        self._database = database
        self._repository = RunRepository(database)

    @property
    def database(self) -> ControlDatabase:
        """The owned control database (transaction access for callers)."""
        return self._database

    def approval_count(self) -> int:
        """The total number of persisted approval rows (read-only)."""
        return len(self._database.read_rows("SELECT 1 FROM writeback_approvals"))

    def pending_approval_count(self) -> int:
        """The number of PENDING approval rows (read-only)."""
        return len(
            self._database.read_rows(
                "SELECT 1 FROM writeback_approvals WHERE status = 'PENDING'"
            )
        )

    def decide(
        self,
        command: DecideFinalWritebackV1,
    ) -> FinalWritebackDecisionResultV1:
        """Lock and decide the exact final-writeback wait atomically.

        One immediate transaction serializes competing writers; the wait
        lock/commit is the T07.2 compare-and-update, so exactly one
        correctly bound decision wins and at most one PENDING approval
        can ever exist for the subject.
        """
        decision = command.decision
        if decision.wait_kind != "FINAL_WRITEBACK":
            return FinalWritebackDecisionResultV1(
                kind="BINDING_MISMATCH",
                message="final-writeback decisions bind only FINAL_WRITEBACK waits",
            )
        try:
            with self._database.immediate_transaction() as tx:
                row = _read_wait_row(tx, decision.wait_id)
                if row is None:
                    return FinalWritebackDecisionResultV1(
                        kind="NOT_FOUND", message="final-writeback wait does not exist"
                    )
                (
                    _wait_id,
                    run_id,
                    wait_kind,
                    _source_phase,
                    subject_digest,
                    _created_at,
                    expires_at,
                    recorded_decision,
                ) = row
                if run_id != decision.run_id or wait_kind != decision.wait_kind:
                    return FinalWritebackDecisionResultV1(
                        kind="BINDING_MISMATCH",
                        message="decision does not bind the recorded wait identity",
                    )
                if subject_digest != decision.subject_digest.value:
                    return FinalWritebackDecisionResultV1(
                        kind="STALE",
                        message="decision subject does not match the wait subject",
                    )
                if command.subject.digest != decision.subject_digest.value:
                    # Contradictory evidence fails closed (SPEC §5.2): the
                    # user decision bound subject S but the command carries
                    # subject T, so no approval for T may be created.
                    return FinalWritebackDecisionResultV1(
                        kind="STALE",
                        message="carried subject does not match the decision subject",
                    )
                status = _wait_status(tx, decision.wait_id)
                if status == "DECIDED":
                    return self._replay_or_conflict(tx, command, recorded_decision)
                if status == "EXPIRED":
                    return FinalWritebackDecisionResultV1(
                        kind="EXPIRED", message="final-writeback wait already expired"
                    )
                if not _run_is_waiting_user(tx, decision.run_id):
                    return FinalWritebackDecisionResultV1(
                        kind="CANCELLED",
                        message="run is no longer waiting for this writeback",
                    )
                if (
                    decision.decided_at.epoch_milliseconds
                    > CanonicalTimestampV1.parse(expires_at).epoch_milliseconds
                ):
                    _settle_wait_expired(tx, decision.wait_id)
                    return FinalWritebackDecisionResultV1(
                        kind="EXPIRED",
                        message="decision arrived after the wait expired",
                    )
                if command.subject.expires_at.value != expires_at:
                    return FinalWritebackDecisionResultV1(
                        kind="STALE",
                        message="subject expiry must equal the wait expiry",
                    )
                lock_result = self._repository.lock_wait_for_decision(tx, decision)
                if lock_result.kind != "LOCKED" or lock_result.lock is None:
                    raise _DecisionRollback(
                        FinalWritebackDecisionResultV1(
                            kind="CONFLICT",
                            message="wait could not be reserved for this decision",
                        )
                    )
                if decision.decision == "REJECT":
                    commit = self._repository.commit_wait_decision(
                        tx, lock_result.lock, decision
                    )
                    if commit.kind != "APPLIED":
                        raise _DecisionRollback(
                            FinalWritebackDecisionResultV1(
                                kind="CONFLICT",
                                message="wait decision could not be recorded",
                            )
                        )
                    return FinalWritebackDecisionResultV1(
                        kind="REJECTED", message="final-writeback wait rejected"
                    )
                approval = self._create_approval(tx, command)
                commit = self._repository.commit_wait_decision(
                    tx, lock_result.lock, decision
                )
                if commit.kind != "APPLIED":
                    raise _DecisionRollback(
                        FinalWritebackDecisionResultV1(
                            kind="CONFLICT",
                            message="wait decision could not be recorded",
                        )
                    )
                if not self._resume_run(tx, decision.run_id):
                    raise _DecisionRollback(
                        FinalWritebackDecisionResultV1(
                            kind="CANCELLED",
                            message="run cannot enter the persistence phase",
                        )
                    )
                return FinalWritebackDecisionResultV1(
                    kind="APPROVED",
                    message="final-writeback approval created",
                    approval=approval,
                )
        except _DecisionRollback as failure:
            return failure.result

    def _replay_or_conflict(
        self,
        tx: ControlTransactionV1,
        command: DecideFinalWritebackV1,
        recorded_decision: str | None,
    ) -> FinalWritebackDecisionResultV1:
        """Stable replay or conflict on an already-decided wait (no mutation).

        An exactly matching decision replays the recorded outcome; a
        different decision for the same wait is a conflict.  Neither path
        creates an approval or resumes the Run again.
        """
        decision = command.decision
        if recorded_decision == decision.decision:
            approval = None
            if recorded_decision == "APPROVE":
                approval = self._approval_for_wait(tx, decision.wait_id)
            return FinalWritebackDecisionResultV1(
                kind="REPLAY",
                message="wait decision already recorded identically",
                approval=approval,
            )
        return FinalWritebackDecisionResultV1(
            kind="CONFLICT",
            message="wait decision already recorded differently",
        )

    def _create_approval(
        self,
        tx: ControlTransactionV1,
        command: DecideFinalWritebackV1,
    ) -> FinalWritebackApprovalV1:
        """Persist the immutable subject facts and one PENDING approval.

        The subject row is inserted once (a digest-identical replay of the
        insert is ignored); the approval row binds the exact wait and
        subject and the storage index enforces one approval per wait.  A
        harness-generated duplicate approval id raises
        sqlite3.IntegrityError: the whole transaction rolls back
        atomically (wait reservation, decision, subject row) and the
        control plane fails closed as INTERNAL_ERROR — the closed result
        vocabulary deliberately has no kind for a control-plane id bug.
        """
        subject = command.subject
        tx.execute(
            "INSERT OR IGNORE INTO writeback_approval_subjects"
            " (subject_digest, run_id, candidate_digest, final_diff_digest,"
            " validation_manifest_digest, formal_evidence_digest,"
            " workspace_preimage_digest, run_config_digest, policy_digest,"
            " reference_profile_digest, action_semantic_digest, expires_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                subject.digest,
                command.decision.run_id,
                subject.candidate_digest,
                subject.final_diff_digest,
                subject.validation_manifest_digest,
                subject.formal_evidence_digest,
                subject.workspace_preimage_digest,
                subject.run_config_digest,
                subject.policy_digest,
                subject.reference_profile_digest,
                subject.action_semantic_digest,
                subject.expires_at.value,
            ),
        )
        tx.execute(
            "INSERT INTO writeback_approvals (approval_id, subject_digest,"
            " run_id, wait_id, created_at, status)"
            " VALUES (?, ?, ?, ?, ?, 'PENDING')",
            (
                command.approval_id,
                subject.digest,
                command.decision.run_id,
                command.decision.wait_id,
                command.decision.decided_at.value,
            ),
        )
        return FinalWritebackApprovalV1(
            schema_version=1,
            approval_id=command.approval_id,
            subject_digest=DigestV1(value=subject.digest),
            run_id=command.decision.run_id,
            wait_id=command.decision.wait_id,
            created_at=command.decision.decided_at,
            status="PENDING",
        )

    def _resume_run(self, tx: ControlTransactionV1, run_id: str) -> bool:
        """Transition WAITING_USER → RUNNING(PERSISTENCE) inside the tx."""
        if not LifecycleRules.is_legal_transition(
            RunStateV1(status="WAITING_USER", phase=AbsentV1(kind="ABSENT")),
            RunStateV1(
                status="RUNNING", phase=PresentV1(kind="PRESENT", value="PERSISTENCE")
            ),
        ):
            return False
        updated = tx.execute(
            "UPDATE runs SET status = 'RUNNING', phase = 'PERSISTENCE',"
            " revision = revision + 1 WHERE run_id = ? AND status ="
            " 'WAITING_USER' AND phase IS NULL",
            (run_id,),
        ).rowcount
        return updated == 1

    def _approval_for_wait(
        self,
        tx: ControlTransactionV1,
        wait_id: str,
    ) -> FinalWritebackApprovalV1 | None:
        row = tx.execute(
            "SELECT approval_id, subject_digest, run_id, wait_id, created_at,"
            " status FROM writeback_approvals WHERE wait_id = ?",
            (wait_id,),
        ).fetchone()
        if row is None:
            return None
        return FinalWritebackApprovalV1(
            schema_version=1,
            approval_id=str(row[0]),
            subject_digest=DigestV1(value=str(row[1])),
            run_id=str(row[2]),
            wait_id=str(row[3]),
            created_at=CanonicalTimestampV1.parse(str(row[4])),
            status=cast(FinalWritebackApprovalStatusV1, str(row[5])),
        )


def _wait_status(tx: ControlTransactionV1, wait_id: str) -> str:
    row = tx.execute(
        "SELECT status FROM wait_contexts WHERE wait_id = ?", (wait_id,)
    ).fetchone()
    if row is None:
        return "MISSING"
    return str(row[0])


def _settle_wait_expired(tx: ControlTransactionV1, wait_id: str) -> None:
    """Settle a still-open wait as EXPIRED (never clobbers a DECIDED row)."""
    tx.execute(
        "UPDATE wait_contexts SET status = 'EXPIRED'"
        " WHERE wait_id = ? AND status IN ('PENDING', 'DECIDING')",
        (wait_id,),
    )


def _run_is_waiting_user(tx: ControlTransactionV1, run_id: str) -> bool:
    row = tx.execute(
        "SELECT status, phase FROM runs WHERE run_id = ?", (run_id,)
    ).fetchone()
    if row is None:
        return False
    return str(row[0]) == "WAITING_USER" and row[1] is None

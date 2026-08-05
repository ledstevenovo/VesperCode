"""T07.2 legacy step 7.B: transactional Run/wait lifecycle repository.

``RunRepository`` persists runs, config snapshots (schema only), and
wait contexts; transitions are compare-and-update (CAS) on status/phase
with a monotonic lifecycle revision inside one explicit immediate
transaction; exactly one correctly bound wait decision can win because
``BEGIN IMMEDIATE`` serializes writers and the lock/commit update is a
compare-and-update on the wait status.  Approval, Grant, authorization,
idempotency replay, audit projection, and persistence-recovery schema
remain out of scope (GREEN-4).
"""

from __future__ import annotations

from typing import Literal, cast

from pydantic import BaseModel, ConfigDict, StrictStr, model_validator

from src.vespercode.canonical.timestamp_v1 import CanonicalTimestampV1
from src.vespercode.contracts.evidence import DigestV1
from src.vespercode.contracts.run import (
    OptionalRunPhaseV1,
    RunStateV1,
    RunStatus,
    WaitContextV1,
    WaitDecisionV1,
    WaitKind,
)
from src.vespercode.runs.lifecycle import LifecycleRules
from src.vespercode.storage.connection import (
    ControlDatabase,
    ControlTransactionV1,
)


class RunRecordV1(BaseModel):
    """One immutable Run record (SPEC 7 Run entity, flat status/phase)."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    run_id: StrictStr
    workspace_identity: StrictStr
    status: RunStatus
    phase: OptionalRunPhaseV1
    config_snapshot_id: StrictStr
    started_at: CanonicalTimestampV1
    run_deadline: CanonicalTimestampV1

    @model_validator(mode="after")
    def _bind_state_and_deadline(self) -> RunRecordV1:
        # Reuse the T05.1 closed state/phase consistency contract.
        RunStateV1(status=self.status, phase=self.phase)
        if self.run_deadline.epoch_milliseconds < self.started_at.epoch_milliseconds:
            raise ValueError("run_deadline must not precede started_at")
        return self


class TransitionCommandV1(BaseModel):
    """One compare-and-update lifecycle command with the exact expected state."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    run_id: StrictStr
    expected: RunStateV1
    target: RunStateV1


class TransitionResultV1(BaseModel):
    """One closed lifecycle transition outcome."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    kind: Literal["APPLIED", "STALE", "INVALID", "NOT_FOUND"]
    message: StrictStr


class LockedWaitDecisionV1(BaseModel):
    """The exact bound wait identity reserved by one decision lock."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    wait_id: StrictStr
    run_id: StrictStr
    wait_kind: WaitKind
    source_phase: Literal["AGENT_LOOP", "FORMAL_VALIDATION"]
    subject_digest: DigestV1
    created_at: CanonicalTimestampV1
    expires_at: CanonicalTimestampV1


class WaitDecisionLockResultV1(BaseModel):
    """One closed wait-lock outcome; ``lock`` is present only when LOCKED."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    kind: Literal[
        "LOCKED",
        "NOT_FOUND",
        "BINDING_MISMATCH",
        "ALREADY_DECIDED",
        "EXPIRED",
    ]
    lock: LockedWaitDecisionV1 | None = None


class WaitDecisionResultV1(BaseModel):
    """One closed wait-decision outcome with a stable reason."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    kind: Literal[
        "APPLIED",
        "ALREADY_DECIDED",
        "BINDING_MISMATCH",
        "EXPIRED",
        "NOT_EXPIRED",
        "NOT_FOUND",
        "NOT_LOCKED",
    ]
    message: StrictStr


class RunAlreadyExistsErrorV1(ValueError):
    """Closed rejection for a duplicate run id."""


class WaitAlreadyExistsErrorV1(ValueError):
    """Closed rejection for a duplicate wait id."""


class RunRepository:
    """Transactional persistence for the coupled Run/config/wait lifecycle."""

    def __init__(self, database: ControlDatabase) -> None:
        self._database = database

    @property
    def database(self) -> ControlDatabase:
        """The owned control database (transaction access for callers)."""
        return self._database

    def insert_created(self, run: RunRecordV1) -> None:
        """Insert one CREATED run atomically; duplicates fail closed."""
        if run.status != "CREATED" or run.phase.kind != "ABSENT":
            raise ValueError("insert_created accepts only CREATED runs")
        with self._database.immediate_transaction() as tx:
            existing = tx.execute(
                "SELECT 1 FROM runs WHERE run_id = ?",
                (run.run_id,),
            ).fetchone()
            if existing is not None:
                raise RunAlreadyExistsErrorV1(f"run {run.run_id} already exists")
            tx.execute(
                "INSERT INTO runs (run_id, workspace_identity,"
                " config_snapshot_id, status, phase, revision, started_at,"
                " run_deadline) VALUES (?, ?, ?, ?, NULL, 1, ?, ?)",
                (
                    run.run_id,
                    run.workspace_identity,
                    run.config_snapshot_id,
                    run.status,
                    run.started_at.value,
                    run.run_deadline.value,
                ),
            )

    def compare_and_transition(
        self,
        command: TransitionCommandV1,
    ) -> TransitionResultV1:
        """Apply one closed legal transition exactly once (compare-and-update).

        The (expected, target) pair must be in the SPEC 4.2.7 table;
        the update compares status/phase and increments the lifecycle
        revision, so stale and missing runs never mutate.
        """
        if not LifecycleRules.is_legal_transition(command.expected, command.target):
            return TransitionResultV1(
                kind="INVALID",
                message="illegal lifecycle transition",
            )
        target_phase = (
            command.target.phase.value
            if command.target.phase.kind == "PRESENT"
            else None
        )
        expected_phase = (
            command.expected.phase.value
            if command.expected.phase.kind == "PRESENT"
            else None
        )
        with self._database.immediate_transaction() as tx:
            exists = tx.execute(
                "SELECT 1 FROM runs WHERE run_id = ?",
                (command.run_id,),
            ).fetchone()
            if exists is None:
                return TransitionResultV1(
                    kind="NOT_FOUND",
                    message="run does not exist",
                )
            updated = tx.execute(
                "UPDATE runs SET status = ?, phase = ?, revision = revision + 1"
                " WHERE run_id = ? AND status = ? AND phase IS ?",
                (
                    command.target.status,
                    target_phase,
                    command.run_id,
                    command.expected.status,
                    expected_phase,
                ),
            ).rowcount
        if updated == 1:
            return TransitionResultV1(
                kind="APPLIED",
                message="transition applied",
            )
        return TransitionResultV1(
            kind="STALE",
            message="expected state does not match the recorded state",
        )

    def create_wait(self, context: WaitContextV1) -> None:
        """Insert one PENDING wait context; duplicates fail closed."""
        with self._database.immediate_transaction() as tx:
            existing = tx.execute(
                "SELECT 1 FROM wait_contexts WHERE wait_id = ?",
                (context.wait_id,),
            ).fetchone()
            if existing is not None:
                raise WaitAlreadyExistsErrorV1(f"wait {context.wait_id} already exists")
            tx.execute(
                "INSERT INTO wait_contexts (wait_id, run_id, wait_kind,"
                " source_phase, subject_digest, created_at, expires_at,"
                " status) VALUES (?, ?, ?, ?, ?, ?, ?, 'PENDING')",
                (
                    context.wait_id,
                    context.run_id,
                    context.wait_kind,
                    context.source_phase,
                    context.subject_digest.value,
                    context.created_at.value,
                    context.expires_at.value,
                ),
            )

    def lock_wait_for_decision(
        self,
        tx: ControlTransactionV1,
        decision: WaitDecisionV1,
    ) -> WaitDecisionLockResultV1:
        """Reserve exactly one wait for one decision inside the caller tx.

        The decision must bind wait_id/run_id/wait_kind/subject_digest to
        a PENDING wait that has not expired; the reservation is a
        compare-and-update on the wait status, so only one competing
        decision can ever hold the lock.
        """
        row = tx.execute(
            "SELECT wait_id, run_id, wait_kind, source_phase, subject_digest,"
            " created_at, expires_at, status FROM wait_contexts"
            " WHERE wait_id = ?",
            (decision.wait_id,),
        ).fetchone()
        if row is None:
            return WaitDecisionLockResultV1(kind="NOT_FOUND")
        wait_id, run_id, wait_kind, source_phase = (
            str(row[0]),
            str(row[1]),
            str(row[2]),
            str(row[3]),
        )
        subject_digest, created_at, expires_at, status = (
            str(row[4]),
            str(row[5]),
            str(row[6]),
            str(row[7]),
        )
        if (
            run_id != decision.run_id
            or wait_kind != decision.wait_kind
            or subject_digest != decision.subject_digest.value
        ):
            return WaitDecisionLockResultV1(kind="BINDING_MISMATCH")
        if status != "PENDING":
            return WaitDecisionLockResultV1(kind="ALREADY_DECIDED")
        if (
            decision.decided_at.epoch_milliseconds
            > CanonicalTimestampV1.parse(expires_at).epoch_milliseconds
        ):
            return WaitDecisionLockResultV1(kind="EXPIRED")
        updated = tx.execute(
            "UPDATE wait_contexts SET status = 'DECIDING'"
            " WHERE wait_id = ? AND status = 'PENDING'",
            (decision.wait_id,),
        ).rowcount
        if updated != 1:
            return WaitDecisionLockResultV1(kind="ALREADY_DECIDED")
        lock = LockedWaitDecisionV1(
            wait_id=wait_id,
            run_id=run_id,
            wait_kind=wait_kind,
            source_phase=cast(Literal["AGENT_LOOP", "FORMAL_VALIDATION"], source_phase),
            subject_digest=DigestV1(value=subject_digest),
            created_at=CanonicalTimestampV1.parse(created_at),
            expires_at=CanonicalTimestampV1.parse(expires_at),
        )
        return WaitDecisionLockResultV1(kind="LOCKED", lock=lock)

    def commit_wait_decision(
        self,
        tx: ControlTransactionV1,
        lock: LockedWaitDecisionV1,
        decision: WaitDecisionV1,
    ) -> WaitDecisionResultV1:
        """Record one locked decision inside the caller tx, or fail closed.

        The decision must bind the locked wait exactly and arrive before
        the wait expires; the recording is a compare-and-update on the
        DECIDING status, so no other decision can also win.
        """
        if (
            decision.wait_id != lock.wait_id
            or decision.run_id != lock.run_id
            or decision.wait_kind != lock.wait_kind
            or decision.subject_digest.value != lock.subject_digest.value
        ):
            return WaitDecisionResultV1(
                kind="BINDING_MISMATCH",
                message="decision does not bind the locked wait",
            )
        if decision.decided_at.epoch_milliseconds > lock.expires_at.epoch_milliseconds:
            return WaitDecisionResultV1(
                kind="EXPIRED",
                message="decision arrived after the wait expired",
            )
        row = tx.execute(
            "SELECT status FROM wait_contexts WHERE wait_id = ?",
            (lock.wait_id,),
        ).fetchone()
        if row is None:
            return WaitDecisionResultV1(
                kind="NOT_FOUND",
                message="wait does not exist",
            )
        status = str(row[0])
        if status != "DECIDING":
            if status == "PENDING":
                return WaitDecisionResultV1(
                    kind="NOT_LOCKED",
                    message="wait is not locked",
                )
            return WaitDecisionResultV1(
                kind="ALREADY_DECIDED",
                message="wait decision already recorded",
            )
        updated = tx.execute(
            "UPDATE wait_contexts SET status = 'DECIDED', decision = ?,"
            " decided_at = ? WHERE wait_id = ? AND status = 'DECIDING'",
            (decision.decision, decision.decided_at.value, lock.wait_id),
        ).rowcount
        if updated != 1:
            return WaitDecisionResultV1(
                kind="ALREADY_DECIDED",
                message="wait decision already recorded",
            )
        return WaitDecisionResultV1(
            kind="APPLIED",
            message="wait decision applied",
        )

    def expire_wait(
        self,
        tx: ControlTransactionV1,
        lock: LockedWaitDecisionV1,
        now: CanonicalTimestampV1,
    ) -> WaitDecisionResultV1:
        """Settle one wait as EXPIRED when its deadline has passed.

        The settlement never clobbers a DECIDED row; a wait that was
        reserved (DECIDING) or still PENDING becomes EXPIRED once ``now``
        reaches ``expires_at``, and an already-settled wait is stable.
        """
        row = tx.execute(
            "SELECT status FROM wait_contexts WHERE wait_id = ?",
            (lock.wait_id,),
        ).fetchone()
        if row is None:
            return WaitDecisionResultV1(
                kind="NOT_FOUND",
                message="wait does not exist",
            )
        status = str(row[0])
        if status in ("DECIDED", "EXPIRED"):
            return WaitDecisionResultV1(
                kind="ALREADY_DECIDED",
                message="wait decision already settled",
            )
        if now.epoch_milliseconds < lock.expires_at.epoch_milliseconds:
            return WaitDecisionResultV1(
                kind="NOT_EXPIRED",
                message="wait has not expired yet",
            )
        tx.execute(
            "UPDATE wait_contexts SET status = 'EXPIRED'"
            " WHERE wait_id = ? AND status != 'DECIDED'",
            (lock.wait_id,),
        )
        return WaitDecisionResultV1(
            kind="EXPIRED",
            message="wait expired",
        )

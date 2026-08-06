"""T14.1 legacy step 14.C: one-time concurrent writeback approval consume.

``WritebackApprovalRepository.consume`` reverifies one PENDING approval
against the exact current writeback subject — stored subject identity
and every immutable field, the candidate/validation/policy binding and
Run identity, the subject expiry, and the consumption command — inside
one immediate transaction, then transitions exactly one concurrent
matching consumer to ``CONSUMED`` via a compare-and-update on the
status.  Expired, stale, subject-mismatched, rejected, replayed, or
already-consumed attempts produce no second success and perform zero
persistence calls; ``verify_consumable`` is the pure pre-check the
control plane runs before the authoritative transactional consume.  Wait
decisions, subject construction, DENY override, and workspace
persistence remain out of scope (GREEN-4).
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Literal, TypeAlias, cast

from pydantic import BaseModel, ConfigDict, StrictStr

from src.vespercode.canonical.timestamp_v1 import CanonicalTimestampV1
from src.vespercode.governance.writeback_decision import (
    FinalWritebackApprovalV1,
    FinalWritebackApprovalStatusV1,
)
from src.vespercode.governance.writeback_subject import FinalWritebackSubjectV1
from src.vespercode.storage.connection import ControlDatabase

ApprovalConsumptionKindV1: TypeAlias = Literal[
    "CONSUMED",
    "ALREADY_CONSUMED",
    "NOT_FOUND",
    "STALE",
    "EXPIRED",
    "REJECTED",
]
"""The closed outcomes of one consumption command."""


class ConsumeWritebackApprovalV1(BaseModel):
    """One closed consumption command.

    Carries only the approval id, the exact current subject (the binding
    of the current candidate/validation/policy/Run facts), and the
    event/time identity of this consumption attempt; the repository
    revalidates every fact against the stored approval and subject rows
    before any transition.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)
    approval_id: StrictStr
    subject: FinalWritebackSubjectV1
    event_id: StrictStr
    consumed_at: CanonicalTimestampV1


class ApprovalConsumptionResultV1(BaseModel):
    """One closed consumption outcome."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    kind: ApprovalConsumptionKindV1
    message: StrictStr


class ApprovalNotConsumableErrorV1(ValueError):
    """Closed pure pre-check rejection of a non-consumable approval."""

    def __init__(self, error_code: ApprovalConsumptionKindV1, message: str) -> None:
        super().__init__(f"{error_code}: {message}")
        self.error_code = error_code


class _ConsumptionRollback(Exception):
    """Internal sentinel: roll back the transaction and return the outcome.

    The immediate-transaction context manager commits on clean exit and
    rolls back only on an exception; every zero-consumption failure must
    not persist anything, so the sentinel rolls the whole transaction
    back before the outcome returns (T15 lesson).
    """

    def __init__(self, outcome: ApprovalConsumptionResultV1) -> None:
        super().__init__(outcome.message)
        self.outcome = outcome


def verify_consumable(
    approval: FinalWritebackApprovalV1,
    command: ConsumeWritebackApprovalV1,
) -> None:
    """Pure consumability pre-check; raises on every non-consumable state.

    The repository's transactional ``consume`` is the authoritative
    re-verification; this check gives the control plane the same closed
    outcome before any transaction begins.
    """
    if approval.status == "CONSUMED":
        raise ApprovalNotConsumableErrorV1(
            "ALREADY_CONSUMED", "approval already consumed"
        )
    if approval.status == "REJECTED":
        raise ApprovalNotConsumableErrorV1("REJECTED", "approval already rejected")
    if approval.status == "EXPIRED":
        raise ApprovalNotConsumableErrorV1("EXPIRED", "approval already expired")
    if approval.subject_digest.value != command.subject.digest:
        raise ApprovalNotConsumableErrorV1(
            "STALE", "command subject does not match the approval subject"
        )
    if approval.run_id != command.subject.run_id:
        raise ApprovalNotConsumableErrorV1(
            "STALE", "command subject does not bind the approval run"
        )
    if (
        command.consumed_at.epoch_milliseconds
        > command.subject.expires_at.epoch_milliseconds
    ):
        raise ApprovalNotConsumableErrorV1("EXPIRED", "approval already expired")


class WritebackApprovalRepository:
    """Transaction-bound compare-and-consume over the v0010 schema."""

    def __init__(
        self, database: ControlDatabase, database_path: Path | None = None
    ) -> None:
        self._database = database
        self._database_path = database_path

    @property
    def database(self) -> ControlDatabase:
        """The owned control database (transaction access for callers)."""
        return self._database

    @property
    def database_path(self) -> Path:
        """The on-disk control database path (per-thread connection seam).

        sqlite3 connections are thread-bound, so concurrency tests open
        one connection per worker on the same file (T07.2 precedent); the
        path is set by the control plane when known, and tests that use
        per-thread connections pass it explicitly.
        """
        if self._database_path is None:
            raise ValueError("database path is not bound to this repository")
        return self._database_path

    def consume(
        self,
        command: ConsumeWritebackApprovalV1,
    ) -> ApprovalConsumptionResultV1:
        """Reverify and atomically consume exactly one PENDING approval.

        One immediate transaction serializes competing writers; the
        status compare-and-update lets exactly one concurrent matching
        consumer win, so at most one CONSUMED success can ever exist for
        one approval (SPEC §4.4.2: only the current PENDING, unexpired,
        fully matching approval transitions to CONSUMED in one atomic
        update).
        """
        try:
            with self._database.immediate_transaction() as tx:
                row = tx.execute(
                    "SELECT approval_id, subject_digest, run_id, wait_id,"
                    " created_at, status FROM writeback_approvals"
                    " WHERE approval_id = ?",
                    (command.approval_id,),
                ).fetchone()
                if row is None:
                    return ApprovalConsumptionResultV1(
                        kind="NOT_FOUND", message="approval does not exist"
                    )
                status = cast(FinalWritebackApprovalStatusV1, str(row[5]))
                if status == "CONSUMED":
                    return ApprovalConsumptionResultV1(
                        kind="ALREADY_CONSUMED", message="approval already consumed"
                    )
                if status == "REJECTED":
                    return ApprovalConsumptionResultV1(
                        kind="REJECTED", message="approval already rejected"
                    )
                if status == "EXPIRED":
                    return ApprovalConsumptionResultV1(
                        kind="EXPIRED", message="approval already expired"
                    )
                subject_digest = str(row[1])
                if command.subject.digest != subject_digest:
                    return ApprovalConsumptionResultV1(
                        kind="STALE",
                        message="command subject does not match the approval subject",
                    )
                if str(row[2]) != command.subject.run_id:
                    raise _ConsumptionRollback(
                        ApprovalConsumptionResultV1(
                            kind="STALE",
                            message="approval does not bind the current run",
                        )
                    )
                subject_row = tx.execute(
                    "SELECT subject_digest, run_id, candidate_digest,"
                    " final_diff_digest, validation_manifest_digest,"
                    " formal_evidence_digest, workspace_preimage_digest,"
                    " run_config_digest, policy_digest, reference_profile_digest,"
                    " action_semantic_digest, expires_at"
                    " FROM writeback_approval_subjects WHERE subject_digest = ?",
                    (subject_digest,),
                ).fetchone()
                if subject_row is None:
                    raise _ConsumptionRollback(
                        ApprovalConsumptionResultV1(
                            kind="STALE",
                            message="approval subject row does not exist",
                        )
                    )
                if self._subject_fields_drift(command.subject, subject_row):
                    raise _ConsumptionRollback(
                        ApprovalConsumptionResultV1(
                            kind="STALE",
                            message="current subject facts drift from the approval",
                        )
                    )
                expires_at = CanonicalTimestampV1.parse(str(subject_row[11]))
                if (
                    command.consumed_at.epoch_milliseconds
                    > expires_at.epoch_milliseconds
                ):
                    raise _ConsumptionRollback(
                        ApprovalConsumptionResultV1(
                            kind="EXPIRED", message="approval already expired"
                        )
                    )
                updated = tx.execute(
                    "UPDATE writeback_approvals SET status = 'CONSUMED'"
                    " WHERE approval_id = ? AND status = 'PENDING'",
                    (command.approval_id,),
                ).rowcount
                if updated != 1:
                    raise _ConsumptionRollback(
                        ApprovalConsumptionResultV1(
                            kind="ALREADY_CONSUMED",
                            message="consumption race lost: another consumer won",
                        )
                    )
                return ApprovalConsumptionResultV1(
                    kind="CONSUMED", message="final writeback approval consumed"
                )
        except _ConsumptionRollback as failure:
            # Every failure rolls the whole transaction back and performs
            # zero persistence calls: the PLAN Registry row 14.C contract
            # ("stale, expired, rejected, subject-mismatched, or
            # already-consumed approval performs zero persistence calls")
            # binds the outcome, so no status-hygiene settlement is
            # written for an expired attempt either.
            return failure.outcome

    @staticmethod
    def _subject_fields_drift(
        subject: FinalWritebackSubjectV1,
        subject_row: sqlite3.Row,
    ) -> bool:
        """Whether the command subject drifts from the stored subject row.

        The stored row is the exact immutable subject facts persisted at
        decision time; any candidate/validation/policy/Run fact drift
        between then and the consumption makes the approval stale
        (SPEC §4.4.2: only a fully matching current subject consumes).
        """
        return (
            subject.run_id != str(subject_row[1])
            or subject.candidate_digest != str(subject_row[2])
            or subject.final_diff_digest != str(subject_row[3])
            or subject.validation_manifest_digest != str(subject_row[4])
            or subject.formal_evidence_digest != str(subject_row[5])
            or subject.workspace_preimage_digest != str(subject_row[6])
            or subject.run_config_digest != str(subject_row[7])
            or subject.policy_digest != str(subject_row[8])
            or subject.reference_profile_digest != str(subject_row[9])
            or subject.action_semantic_digest != str(subject_row[10])
        )

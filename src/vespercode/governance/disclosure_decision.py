"""T15.2 legacy step 15.D: atomic disclosure Grant decision lifecycle.

``DisclosureDecisionServiceV1.decide`` locks the exact PENDING disclosure
wait inside one immediate transaction (reusing the T07.2 wait-lock/commit
CAS), creates at most one matching ACTIVE Grant for an exact current
unexpired APPROVE (persisting the immutable subject facts first), records
the decision, and transitions the Run back to ``RUNNING(AGENT_LOOP)``.
REJECT, expiry, stale subject, wrong binding, cancelled runs, and
duplicate/replay-conflict decisions remain atomic and create no Grant and
no resume.  Final registry edits, Task 15.F revocation, request-body
validation, prepared-request authorization, and byte charging remain out
of scope (GREEN-4).
"""

from __future__ import annotations

import json
from typing import Literal, TypeAlias, cast

from pydantic import BaseModel, ConfigDict, StrictStr

from src.vespercode.canonical.json_v1 import CanonicalValueV1, canonical_json_bytes
from src.vespercode.canonical.path_v1 import CanonicalRelativePathV1
from src.vespercode.canonical.timestamp_v1 import CanonicalTimestampV1
from src.vespercode.contracts.evidence import DigestV1
from src.vespercode.contracts.optional import AbsentV1, PresentV1
from src.vespercode.contracts.run import RunStateV1, WaitDecisionV1
from src.vespercode.governance.disclosure_scope import (
    DirectoryDisclosureScopeV1,
    DisclosurePathScopeV1,
    FileDisclosureScopeV1,
    RootDisclosureScopeV1,
)
from src.vespercode.governance.disclosure_subject import DisclosureGrantSubjectV1
from src.vespercode.governance.request_sources import RequestSourceCategoryV1
from src.vespercode.runs.lifecycle import LifecycleRules
from src.vespercode.storage.connection import (
    ControlDatabase,
    ControlTransactionV1,
)
from src.vespercode.storage.run_repository import RunRepository

DisclosureGrantStatusV1: TypeAlias = Literal[
    "ACTIVE",
    "REVOKED",
    "EXPIRED",
    "EXHAUSTED",
]
"""SPEC §4.4.3: the closed DisclosureGrant status vocabulary."""

DisclosureDecisionKindV1: TypeAlias = Literal[
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
"""The closed outcomes of one Grant decision."""


class DisclosureGrantV1(BaseModel):
    """SPEC §4.4.3: the mutable Grant record bound to its subject/wait.

    The value carries ``schema_version`` per the SPEC block; the v0003
    table (PLAN storage registry row 448) stores the identity columns and
    the run/wait FKs without a schema_version column, so the model is the
    value contract and the DDL the storage contract.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal[1]
    grant_id: StrictStr
    subject_digest: DigestV1
    run_id: StrictStr
    wait_id: StrictStr
    created_at: CanonicalTimestampV1
    consumed_bytes: int
    status: DisclosureGrantStatusV1


class DecideDisclosureGrantV1(BaseModel):
    """One closed Grant decision command.

    The decision binds wait_id/run_id/wait_kind/subject_digest/event/time
    (T07.2 ``WaitDecisionV1``) and carries the immutable subject to grant
    plus the harness-generated grant id; nothing else may influence the
    outcome.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)
    decision: WaitDecisionV1
    subject: DisclosureGrantSubjectV1
    grant_id: StrictStr


class DisclosureDecisionResultV1(BaseModel):
    """One closed Grant decision outcome; ``grant`` is present on APPROVED."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    kind: DisclosureDecisionKindV1
    message: StrictStr
    grant: DisclosureGrantV1 | None = None


class _DecisionRollback(Exception):
    """Internal sentinel: roll back the transaction and return the result.

    The immediate-transaction context manager commits on clean exit and
    rolls back only on an exception; any decision outcome that must not
    persist its in-transaction writes raises this sentinel so the whole
    transaction (wait reservation, subject/Grant rows, run transition)
    rolls back atomically before the result is returned.
    """

    def __init__(self, result: DisclosureDecisionResultV1) -> None:
        super().__init__(result.message)
        self.result = result


def _scope_to_canonical(scope: DisclosurePathScopeV1) -> dict[str, CanonicalValueV1]:
    """One scope's canonical storage shape (SPEC §4.4.3)."""
    if scope.kind == "ROOT":
        return {"kind": "ROOT"}
    return {"kind": scope.kind, "path": scope.path.value}


def serialize_scope_sequence(
    scopes: tuple[DisclosurePathScopeV1, ...],
) -> str:
    """The canonical JSON storage form of the subject's path scopes."""
    return canonical_json_bytes(
        tuple(_scope_to_canonical(scope) for scope in scopes)
    ).decode("utf-8")


def parse_scope_sequence(text: str) -> tuple[DisclosurePathScopeV1, ...]:
    """Rebuild the subject's path scopes from their canonical storage form."""
    raw = json.loads(text)
    if not isinstance(raw, list):
        raise ValueError("stored scope sequence must be a JSON array")
    scopes: list[DisclosurePathScopeV1] = []
    for entry in raw:
        if not isinstance(entry, dict):
            raise ValueError("stored scope entries must be objects")
        kind = entry.get("kind")
        if kind == "ROOT":
            scopes.append(RootDisclosureScopeV1(kind="ROOT"))
        elif kind == "FILE":
            scopes.append(
                FileDisclosureScopeV1(
                    kind="FILE", path=CanonicalRelativePathV1(entry["path"])
                )
            )
        elif kind == "DIRECTORY":
            scopes.append(
                DirectoryDisclosureScopeV1(
                    kind="DIRECTORY", path=CanonicalRelativePathV1(entry["path"])
                )
            )
        else:
            raise ValueError(f"unknown stored scope kind {kind!r}")
    return tuple(scopes)


def serialize_categories(
    categories: tuple[RequestSourceCategoryV1, ...],
) -> str:
    """The canonical JSON storage form of the subject's categories."""
    return canonical_json_bytes(tuple(categories)).decode("utf-8")


def parse_categories(text: str) -> tuple[RequestSourceCategoryV1, ...]:
    """Rebuild the subject's categories from their canonical storage form."""
    raw = json.loads(text)
    if not isinstance(raw, list) or not all(isinstance(item, str) for item in raw):
        raise ValueError("stored categories must be a JSON array of strings")
    return tuple(cast(RequestSourceCategoryV1, item) for item in raw)


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


class DisclosureDecisionServiceV1:
    """Transaction-bound Grant decision lifecycle over the v0003 schema."""

    def __init__(self, database: ControlDatabase) -> None:
        self._database = database
        self._repository = RunRepository(database)

    @property
    def database(self) -> ControlDatabase:
        """The owned control database (transaction access for callers)."""
        return self._database

    def grant_count(self) -> int:
        """The total number of persisted Grant rows (read-only)."""
        return len(self._database.read_rows("SELECT 1 FROM disclosure_grants"))

    def active_grant_count(self) -> int:
        """The number of ACTIVE Grant rows (read-only)."""
        return len(
            self._database.read_rows(
                "SELECT 1 FROM disclosure_grants WHERE status = 'ACTIVE'"
            )
        )

    def decide(
        self,
        command: DecideDisclosureGrantV1,
    ) -> DisclosureDecisionResultV1:
        """Lock and decide the exact disclosure wait atomically.

        One immediate transaction serializes competing writers; the wait
        lock/commit is the T07.2 compare-and-update, so exactly one
        correctly bound decision wins and at most one matching ACTIVE
        Grant can ever exist for the subject.
        """
        decision = command.decision
        if decision.wait_kind != "DISCLOSURE_GRANT":
            return DisclosureDecisionResultV1(
                kind="BINDING_MISMATCH",
                message="disclosure decisions bind only DISCLOSURE_GRANT waits",
            )
        try:
            with self._database.immediate_transaction() as tx:
                row = _read_wait_row(tx, decision.wait_id)
                if row is None:
                    return DisclosureDecisionResultV1(
                        kind="NOT_FOUND", message="disclosure wait does not exist"
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
                    return DisclosureDecisionResultV1(
                        kind="BINDING_MISMATCH",
                        message="decision does not bind the recorded wait identity",
                    )
                if subject_digest != decision.subject_digest.value:
                    return DisclosureDecisionResultV1(
                        kind="STALE",
                        message="decision subject does not match the wait subject",
                    )
                status = _wait_status(tx, decision.wait_id)
                if status == "DECIDED":
                    return self._replay_or_conflict(tx, command, recorded_decision)
                if status == "EXPIRED":
                    return DisclosureDecisionResultV1(
                        kind="EXPIRED", message="disclosure wait already expired"
                    )
                if not _run_is_waiting_user(tx, decision.run_id):
                    return DisclosureDecisionResultV1(
                        kind="CANCELLED",
                        message="run is no longer waiting for this disclosure",
                    )
                if (
                    decision.decided_at.epoch_milliseconds
                    > CanonicalTimestampV1.parse(expires_at).epoch_milliseconds
                ):
                    _settle_wait_expired(tx, decision.wait_id)
                    return DisclosureDecisionResultV1(
                        kind="EXPIRED",
                        message="decision arrived after the wait expired",
                    )
                if command.subject.expires_at.value != expires_at:
                    return DisclosureDecisionResultV1(
                        kind="STALE",
                        message="subject expiry must equal the wait expiry",
                    )
                lock_result = self._repository.lock_wait_for_decision(tx, decision)
                if lock_result.kind != "LOCKED" or lock_result.lock is None:
                    raise _DecisionRollback(
                        DisclosureDecisionResultV1(
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
                            DisclosureDecisionResultV1(
                                kind="CONFLICT",
                                message="wait decision could not be recorded",
                            )
                        )
                    return DisclosureDecisionResultV1(
                        kind="REJECTED", message="disclosure wait rejected"
                    )
                grant = self._create_grant(tx, command)
                commit = self._repository.commit_wait_decision(
                    tx, lock_result.lock, decision
                )
                if commit.kind != "APPLIED":
                    raise _DecisionRollback(
                        DisclosureDecisionResultV1(
                            kind="CONFLICT",
                            message="wait decision could not be recorded",
                        )
                    )
                if not self._resume_run(tx, decision.run_id):
                    raise _DecisionRollback(
                        DisclosureDecisionResultV1(
                            kind="CANCELLED",
                            message="run cannot return to the agent loop",
                        )
                    )
                return DisclosureDecisionResultV1(
                    kind="APPROVED",
                    message="disclosure grant created",
                    grant=grant,
                )
        except _DecisionRollback as failure:
            return failure.result

    def _replay_or_conflict(
        self,
        tx: ControlTransactionV1,
        command: DecideDisclosureGrantV1,
        recorded_decision: str | None,
    ) -> DisclosureDecisionResultV1:
        """Stable replay or conflict on an already-decided wait (no mutation).

        An exactly matching decision replays the recorded outcome; a
        different decision for the same wait is a conflict.  Neither path
        creates a Grant or resumes the Run again.
        """
        decision = command.decision
        if recorded_decision == decision.decision:
            grant = None
            if recorded_decision == "APPROVE":
                grant = self._grant_for_wait(tx, decision.wait_id)
            return DisclosureDecisionResultV1(
                kind="REPLAY",
                message="wait decision already recorded identically",
                grant=grant,
            )
        return DisclosureDecisionResultV1(
            kind="CONFLICT",
            message="wait decision already recorded differently",
        )

    def _create_grant(
        self,
        tx: ControlTransactionV1,
        command: DecideDisclosureGrantV1,
    ) -> DisclosureGrantV1:
        """Persist the immutable subject facts and one ACTIVE Grant.

        The subject row is inserted once (a digest-identical replay of the
        insert is ignored); the Grant row binds the exact wait and subject
        and the storage indexes enforce one grant per wait and at most one
        ACTIVE grant per subject.  A harness-generated duplicate grant id
        raises sqlite3.IntegrityError: the whole transaction rolls back
        atomically (wait reservation, decision, subject row) and the
        control plane fails closed as INTERNAL_ERROR — the closed result
        vocabulary deliberately has no kind for a control-plane id bug.
        """
        subject = command.subject
        tx.execute(
            "INSERT OR IGNORE INTO disclosure_grant_subjects"
            " (subject_digest, run_id, llm_profile_digest, provider,"
            " endpoint_id, model, request_serializer_version,"
            " allowed_source_paths, allowed_source_categories,"
            " redaction_profile_id, cumulative_byte_budget, expires_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                subject.digest,
                command.decision.run_id,
                subject.llm_profile_digest,
                subject.provider,
                subject.endpoint_id,
                subject.model,
                subject.request_serializer_version,
                serialize_scope_sequence(subject.allowed_source_paths),
                serialize_categories(subject.allowed_source_categories),
                subject.redaction_profile_id,
                subject.cumulative_byte_budget,
                subject.expires_at.value,
            ),
        )
        tx.execute(
            "INSERT INTO disclosure_grants (grant_id, subject_digest, run_id,"
            " wait_id, created_at, consumed_bytes, status)"
            " VALUES (?, ?, ?, ?, ?, 0, 'ACTIVE')",
            (
                command.grant_id,
                subject.digest,
                command.decision.run_id,
                command.decision.wait_id,
                command.decision.decided_at.value,
            ),
        )
        return DisclosureGrantV1(
            schema_version=1,
            grant_id=command.grant_id,
            subject_digest=DigestV1(value=subject.digest),
            run_id=command.decision.run_id,
            wait_id=command.decision.wait_id,
            created_at=command.decision.decided_at,
            consumed_bytes=0,
            status="ACTIVE",
        )

    def _resume_run(self, tx: ControlTransactionV1, run_id: str) -> bool:
        """Transition WAITING_USER → RUNNING(AGENT_LOOP) inside the tx."""
        if not LifecycleRules.is_legal_transition(
            RunStateV1(status="WAITING_USER", phase=AbsentV1(kind="ABSENT")),
            RunStateV1(
                status="RUNNING", phase=PresentV1(kind="PRESENT", value="AGENT_LOOP")
            ),
        ):
            return False
        updated = tx.execute(
            "UPDATE runs SET status = 'RUNNING', phase = 'AGENT_LOOP',"
            " revision = revision + 1 WHERE run_id = ? AND status ="
            " 'WAITING_USER' AND phase IS NULL",
            (run_id,),
        ).rowcount
        return updated == 1

    def _grant_for_wait(
        self,
        tx: ControlTransactionV1,
        wait_id: str,
    ) -> DisclosureGrantV1 | None:
        row = tx.execute(
            "SELECT grant_id, subject_digest, run_id, wait_id, created_at,"
            " consumed_bytes, status FROM disclosure_grants WHERE wait_id = ?",
            (wait_id,),
        ).fetchone()
        if row is None:
            return None
        return DisclosureGrantV1(
            schema_version=1,
            grant_id=str(row[0]),
            subject_digest=DigestV1(value=str(row[1])),
            run_id=str(row[2]),
            wait_id=str(row[3]),
            created_at=CanonicalTimestampV1.parse(str(row[4])),
            consumed_bytes=int(row[5]),
            status=cast(DisclosureGrantStatusV1, str(row[6])),
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

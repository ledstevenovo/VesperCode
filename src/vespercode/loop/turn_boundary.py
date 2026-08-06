"""T25.1 legacy step 25.B: active-turn and call-counting boundary.

``TurnBoundary`` owns exactly the active-turn storage behavior of the
SPEC 4.2.5 atomic counting point, decomposed into compare-and-update
operations (Task 7.B style): ``begin`` atomically establishes one ACTIVE
turn per Run and advances the turn counter at that single successful
boundary; ``record_call_started`` advances the call counter at the exact
call-start boundary with a revision compare-and-update on the ACTIVE
turn; ``close_turn`` closes the ACTIVE turn with a closed four-value
outcome and a revision compare-and-update; ``abort_before_call`` is the
zero-count abort path that never creates a turn and never advances either
counter, returning the run's exact unchanged counts for every
credential/Grant/readiness/transport boundary.  After the counting
boundaries a failure of any kind (catchable pre-call failure closed as
``NOT_ATTEMPTED``, call failure, invalid output, internal processing
failure) keeps the consumed counts; only the abort path is zero-side-
effect.  Registry edits, request preparation, credential/Grant/
authorization checks, transport, and outer-loop orchestration remain out
of scope (GREEN-4).
"""

from __future__ import annotations

import sqlite3
import uuid
from typing import Annotated, Literal, Protocol, TypeAlias, cast

from pydantic import BaseModel, ConfigDict, Field, StrictStr

from src.vespercode.canonical.clock import ClockV1, SystemClockV1
from src.vespercode.contracts.optional import PresentV1
from src.vespercode.contracts.run import RunStateV1
from src.vespercode.storage.connection import (
    ControlDatabase,
    ControlTransactionV1,
)

TurnOutcomeV1: TypeAlias = Literal[
    "SUCCEEDED",
    "FAILED",
    "NOT_ATTEMPTED",
    "ABORTED",
]
"""The closed four-value turn outcome (SPEC_PROCESS 12.2.4 union).

``SUCCEEDED`` and ``FAILED`` cover the completed and failed turn;
``NOT_ATTEMPTED`` records a catchable pre-call failure after the counting
boundary (SPEC 4.2.5); ``ABORTED`` covers the internal processing failure
(the ``TURN_ABORTED`` value of the SPEC_PROCESS 12.2.4 four-value union).
"""

_TURN_OUTCOMES: frozenset[str] = frozenset(
    {"SUCCEEDED", "FAILED", "NOT_ATTEMPTED", "ABORTED"}
)

_RUNNING_AGENT_LOOP = RunStateV1(
    status="RUNNING", phase=PresentV1(kind="PRESENT", value="AGENT_LOOP")
)
"""The only state in which a turn can be established (SPEC 4.2.3/4.2.5)."""


class AbortBeforeCallResultV1(BaseModel):
    """One zero-count pre-call abort outcome with the exact stable reason."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    reason: Annotated[StrictStr, Field(min_length=1, max_length=64)]
    turn_count: Annotated[int, Field(strict=True, ge=0)]
    call_count: Annotated[int, Field(strict=True, ge=0)]


class BeginTurnResultV1(BaseModel):
    """One closed begin-turn outcome; ``turn_id`` present only when APPLIED."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    kind: Literal["APPLIED", "ALREADY_ACTIVE", "STALE", "INVALID", "NOT_FOUND"]
    message: StrictStr
    turn_id: StrictStr | None = None
    turn_count: Annotated[int, Field(strict=True, ge=0)]
    call_count: Annotated[int, Field(strict=True, ge=0)]


class RecordCallStartedResultV1(BaseModel):
    """One closed call-start outcome with the exact count result."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    kind: Literal["APPLIED", "NOT_FOUND", "RUN_MISMATCH", "CLOSED", "STALE"]
    message: StrictStr
    turn_count: Annotated[int, Field(strict=True, ge=0)]
    call_count: Annotated[int, Field(strict=True, ge=0)]


class CloseTurnResultV1(BaseModel):
    """One closed close-turn outcome with the recorded outcome and counts."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    kind: Literal["APPLIED", "NOT_FOUND", "RUN_MISMATCH", "CLOSED", "STALE"]
    message: StrictStr
    outcome: TurnOutcomeV1
    turn_count: Annotated[int, Field(strict=True, ge=0)]
    call_count: Annotated[int, Field(strict=True, ge=0)]


class TurnBoundaryErrorV1(ValueError):
    """Closed rejection for an invalid turn-boundary operation."""


class TurnCounterMissingErrorV1(ValueError):
    """Closed internal rejection when the run counter row is missing.

    Reachable only through out-of-band database corruption, because
    ``begin`` always creates the counter row inside the same immediate
    transaction as the ACTIVE turn it establishes.
    """


def _require_turn_id(value: str) -> str:
    """The Harness-generated turn id must be non-empty and at most 128 bytes."""
    if not isinstance(value, str) or value == "":
        raise TurnBoundaryErrorV1("turn id must be a non-empty string")
    if len(value.encode("utf-8")) > 128:
        raise TurnBoundaryErrorV1("turn id must be at most 128 bytes")
    return value


def _require_revision(value: int) -> int:
    """The compare-and-update revision must be a positive integer."""
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        raise TurnBoundaryErrorV1("expected revision must be a positive integer")
    return value


def _require_turn_outcome(value: str) -> TurnOutcomeV1:
    """The turn outcome must be one of the closed four values."""
    if value not in _TURN_OUTCOMES:
        raise TurnBoundaryErrorV1(f"unknown turn outcome {value!r}")
    return cast(TurnOutcomeV1, value)


def _require_reason(value: str) -> str:
    """The stable abort reason must be a bounded non-empty string."""
    if not isinstance(value, str) or value == "":
        raise TurnBoundaryErrorV1("abort reason must be a non-empty string")
    if len(value) > 64:
        raise TurnBoundaryErrorV1("abort reason must be at most 64 characters")
    return value


class TurnIdGeneratorV1(Protocol):
    """The injectable Harness-owned turn id generator."""

    def next_id(self) -> str: ...


class _UuidTurnIdGeneratorV1:
    """Default generator: one fresh non-empty UUID string per call."""

    def next_id(self) -> str:
        return str(uuid.uuid4())


class TurnBoundary:
    """Transactional active-turn and call-counting storage boundary.

    Every mutation runs inside one explicit ``BEGIN IMMEDIATE`` transaction
    (Task 7.B style), so exactly one contender can begin a turn, the
    partial unique index admits at most one ACTIVE turn per Run, and the
    revision compare-and-update operations let exactly one call-start and
    exactly one close win per turn.
    """

    def __init__(
        self,
        database: ControlDatabase,
        clock: ClockV1 | None = None,
        turn_id_generator: TurnIdGeneratorV1 | None = None,
    ) -> None:
        self._database = database
        self._clock = clock if clock is not None else SystemClockV1()
        self._turn_id_generator = (
            turn_id_generator
            if turn_id_generator is not None
            else _UuidTurnIdGeneratorV1()
        )

    @property
    def database(self) -> ControlDatabase:
        """The owned control database (transaction access for callers)."""
        return self._database

    def _read_counts(
        self,
        tx: ControlTransactionV1,
        run_id: str,
    ) -> tuple[int, int]:
        """The run's exact current counts inside one caller transaction."""
        row = tx.execute(
            "SELECT turn_count, call_count FROM run_turn_call_counters"
            " WHERE run_id = ?",
            (run_id,),
        ).fetchone()
        if row is None:
            return (0, 0)
        return (int(row[0]), int(row[1]))

    def _load_turn(
        self,
        tx: ControlTransactionV1,
        turn_id: str,
    ) -> tuple[str, int, str] | None:
        """One turn's (run_id, revision, status) inside the caller tx."""
        row = tx.execute(
            "SELECT run_id, revision, status FROM agent_turns WHERE turn_id = ?",
            (turn_id,),
        ).fetchone()
        if row is None:
            return None
        return (str(row[0]), int(row[1]), str(row[2]))

    def abort_before_call(
        self,
        run_id: str,
        reason: str,
    ) -> AbortBeforeCallResultV1:
        """One zero-side-effect exact count outcome for a pre-call failure.

        Never creates a turn, never advances a counter, and never mutates
        anything: it reads the run's current counters (0/0 when the run has
        never reached a counting boundary) and reports them with the stable
        failure reason, so every credential/Grant/readiness/transport
        boundary has an explicit exact count outcome (SPEC 5.1/4.2.5).
        """
        _require_reason(reason)
        rows = self._database.read_rows(
            "SELECT turn_count, call_count FROM run_turn_call_counters"
            " WHERE run_id = ?",
            (run_id,),
        )
        if not rows:
            return AbortBeforeCallResultV1(
                reason=reason,
                turn_count=0,
                call_count=0,
            )
        return AbortBeforeCallResultV1(
            reason=reason,
            turn_count=int(rows[0][0]),
            call_count=int(rows[0][1]),
        )

    def begin(
        self,
        run_id: str,
        expected_state: RunStateV1,
    ) -> BeginTurnResultV1:
        """Atomically establish one active turn and advance the turn counter.

        The run must be recorded in exactly ``RUNNING(AGENT_LOOP)``: an
        illegal expectation (any state that can never host a turn, e.g.
        ``WAITING_USER``) is ``INVALID``, a legal expectation that does not
        match the recorded state is ``STALE``, and a missing run is
        ``NOT_FOUND`` — all without mutation.  Only this successful
        boundary advances the turn counter; the call counter advances only
        at ``record_call_started``.
        """
        if expected_state != _RUNNING_AGENT_LOOP:
            rows = self._database.read_rows(
                "SELECT turn_count, call_count FROM run_turn_call_counters"
                " WHERE run_id = ?",
                (run_id,),
            )
            if not rows:
                return BeginTurnResultV1(
                    kind="INVALID",
                    message="begin requires RUNNING(AGENT_LOOP)",
                    turn_count=0,
                    call_count=0,
                )
            return BeginTurnResultV1(
                kind="INVALID",
                message="begin requires RUNNING(AGENT_LOOP)",
                turn_count=int(rows[0][0]),
                call_count=int(rows[0][1]),
            )
        with self._database.immediate_transaction() as tx:
            run = tx.execute(
                "SELECT status, phase FROM runs WHERE run_id = ?",
                (run_id,),
            ).fetchone()
            if run is None:
                return BeginTurnResultV1(
                    kind="NOT_FOUND",
                    message="run does not exist",
                    turn_count=0,
                    call_count=0,
                )
            if str(run[0]) != "RUNNING" or run[1] != "AGENT_LOOP":
                turn_count, call_count = self._read_counts(tx, run_id)
                return BeginTurnResultV1(
                    kind="STALE",
                    message="run is not in the expected RUNNING(AGENT_LOOP) state",
                    turn_count=turn_count,
                    call_count=call_count,
                )
            active = tx.execute(
                "SELECT 1 FROM agent_turns WHERE run_id = ? AND status = 'ACTIVE'",
                (run_id,),
            ).fetchone()
            if active is not None:
                turn_count, call_count = self._read_counts(tx, run_id)
                return BeginTurnResultV1(
                    kind="ALREADY_ACTIVE",
                    message="an active turn already exists for this run",
                    turn_count=turn_count,
                    call_count=call_count,
                )
            counter = tx.execute(
                "SELECT turn_count, call_count FROM run_turn_call_counters"
                " WHERE run_id = ?",
                (run_id,),
            ).fetchone()
            turn_id = _require_turn_id(self._turn_id_generator.next_id())
            try:
                tx.execute(
                    "INSERT INTO agent_turns (turn_id, run_id, revision, status,"
                    " outcome, closed_at, request_ref, result_ref)"
                    " VALUES (?, ?, 1, 'ACTIVE', NULL, NULL, NULL, NULL)",
                    (turn_id, run_id),
                )
            except sqlite3.IntegrityError as exc:
                raise TurnBoundaryErrorV1(
                    f"turn id {turn_id!r} already exists"
                ) from exc
            if counter is None:
                tx.execute(
                    "INSERT INTO run_turn_call_counters"
                    " (run_id, turn_count, call_count, revision)"
                    " VALUES (?, 1, 0, 1)",
                    (run_id,),
                )
                turn_count, call_count = 1, 0
            else:
                turn_count, call_count = int(counter[0]), int(counter[1])
                tx.execute(
                    "UPDATE run_turn_call_counters SET turn_count = turn_count + 1,"
                    " revision = revision + 1 WHERE run_id = ?",
                    (run_id,),
                )
                turn_count, call_count = turn_count + 1, call_count
            return BeginTurnResultV1(
                kind="APPLIED",
                message="turn established",
                turn_id=turn_id,
                turn_count=turn_count,
                call_count=call_count,
            )

    def record_call_started(
        self,
        run_id: str,
        turn_id: str,
        expected_revision: int,
    ) -> RecordCallStartedResultV1:
        """Advance the call counter at the exact call-start CAS boundary.

        The turn must be ACTIVE, belong to the given run, and carry the
        exact expected revision; a missing, run-mismatched, closed, or
        stale turn leaves every counter unchanged.  Only this successful
        boundary advances the call counter; the counts never move backward.
        """
        _require_revision(expected_revision)
        with self._database.immediate_transaction() as tx:
            turn_count, call_count = self._read_counts(tx, run_id)
            loaded = self._load_turn(tx, turn_id)
            if loaded is None:
                return RecordCallStartedResultV1(
                    kind="NOT_FOUND",
                    message="turn does not exist",
                    turn_count=turn_count,
                    call_count=call_count,
                )
            turn_run_id, revision, status = loaded
            if turn_run_id != run_id:
                return RecordCallStartedResultV1(
                    kind="RUN_MISMATCH",
                    message="turn does not belong to this run",
                    turn_count=turn_count,
                    call_count=call_count,
                )
            if status != "ACTIVE":
                return RecordCallStartedResultV1(
                    kind="CLOSED",
                    message="turn is not active",
                    turn_count=turn_count,
                    call_count=call_count,
                )
            if revision != expected_revision:
                return RecordCallStartedResultV1(
                    kind="STALE",
                    message="turn revision does not match the expected revision",
                    turn_count=turn_count,
                    call_count=call_count,
                )
            updated = tx.execute(
                "UPDATE run_turn_call_counters SET call_count = call_count + 1,"
                " revision = revision + 1 WHERE run_id = ?",
                (run_id,),
            )
            if updated.rowcount != 1:
                raise TurnCounterMissingErrorV1(f"counter row missing for run {run_id}")
            tx.execute(
                "UPDATE agent_turns SET revision = revision + 1"
                " WHERE turn_id = ? AND status = 'ACTIVE' AND revision = ?",
                (turn_id, expected_revision),
            )
            turn_count, call_count = self._read_counts(tx, run_id)
            return RecordCallStartedResultV1(
                kind="APPLIED",
                message="call start recorded",
                turn_count=turn_count,
                call_count=call_count,
            )

    def close_turn(
        self,
        run_id: str,
        turn_id: str,
        outcome: TurnOutcomeV1,
        expected_revision: int,
    ) -> CloseTurnResultV1:
        """Close one ACTIVE turn exactly once with a closed outcome (CAS).

        The turn must be ACTIVE, belong to the given run, and carry the
        exact expected revision; a missing, run-mismatched, closed (replay
        conflict), or stale turn leaves every counter unchanged.  Closing
        never changes the consumed counts: after the counting boundaries
        the turn/call stay consumed for every outcome, including
        ``NOT_ATTEMPTED`` (SPEC 4.2.5).
        """
        validated_outcome = _require_turn_outcome(outcome)
        _require_revision(expected_revision)
        with self._database.immediate_transaction() as tx:
            turn_count, call_count = self._read_counts(tx, run_id)
            loaded = self._load_turn(tx, turn_id)
            if loaded is None:
                return CloseTurnResultV1(
                    kind="NOT_FOUND",
                    message="turn does not exist",
                    outcome=validated_outcome,
                    turn_count=turn_count,
                    call_count=call_count,
                )
            turn_run_id, revision, status = loaded
            if turn_run_id != run_id:
                return CloseTurnResultV1(
                    kind="RUN_MISMATCH",
                    message="turn does not belong to this run",
                    outcome=validated_outcome,
                    turn_count=turn_count,
                    call_count=call_count,
                )
            if status != "ACTIVE":
                return CloseTurnResultV1(
                    kind="CLOSED",
                    message="turn is not active",
                    outcome=validated_outcome,
                    turn_count=turn_count,
                    call_count=call_count,
                )
            if revision != expected_revision:
                return CloseTurnResultV1(
                    kind="STALE",
                    message="turn revision does not match the expected revision",
                    outcome=validated_outcome,
                    turn_count=turn_count,
                    call_count=call_count,
                )
            updated = tx.execute(
                "UPDATE agent_turns SET status = 'CLOSED', outcome = ?,"
                " closed_at = ?, revision = revision + 1"
                " WHERE turn_id = ? AND status = 'ACTIVE' AND revision = ?",
                (
                    validated_outcome,
                    self._clock.now().value,
                    turn_id,
                    expected_revision,
                ),
            )
            if updated.rowcount != 1:
                return CloseTurnResultV1(
                    kind="STALE",
                    message="turn revision does not match the expected revision",
                    outcome=validated_outcome,
                    turn_count=turn_count,
                    call_count=call_count,
                )
            return CloseTurnResultV1(
                kind="APPLIED",
                message="turn closed",
                outcome=validated_outcome,
                turn_count=turn_count,
                call_count=call_count,
            )

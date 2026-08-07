"""T25.2 legacy step 25.F: non-persistent restart fail-close inspection.

``RestartGuard.inspect`` inspects the persisted Run, active-turn, phase,
and terminal evidence to distinguish a clean boundary from any
interrupted non-persistent Agent turn after process restart (SPEC
§4.2.7): an ACTIVE turn always takes precedence and stops with
``PROCESS_RESTART_DURING_TURN``; a non-persistent phase or a
``WAITING_USER`` run stops with ``PROCESS_RESTARTED_DURING_RUN``; a
terminal run or a never-started ``CREATED`` run is a clean boundary; the
persistent phase and ``RECOVERY_REQUIRED`` defer to the persistence
recovery machinery (Task 3, out of scope); and contradictory or
incomplete evidence fails closed (SPEC 5.2).  Every disposition forbids
resend, and the guard never reconstructs request/response bodies,
consumes waits, or invokes a tool (GREEN-2/GREEN-4).
"""

from __future__ import annotations

from typing import Literal, TypeAlias

from pydantic import (
    BaseModel,
    ConfigDict,
    StrictStr,
    field_validator,
    model_validator,
)

from vespercode.contracts.run import RunPhase

_MAX_IDENTIFIER_CHARS = 128

_RUN_STATUSES: frozenset[str] = frozenset(
    {"CREATED", "RUNNING", "WAITING_USER", "RECOVERY_REQUIRED", "SUCCEEDED", "STOPPED"}
)

RestartStopReasonV1: TypeAlias = Literal[
    "PROCESS_RESTART_DURING_TURN",
    "PROCESS_RESTARTED_DURING_RUN",
]
"""The closed restart stop reasons (SPEC §4.2.7; the card's exact RED)."""


class RunEvidenceV1(BaseModel):
    """One persisted run snapshot: the exact facts the guard needs.

    Carries the run identity, the persisted status, the persisted phase
    (present only when the run was RUNNING), and whether an ACTIVE
    ``agent_turns`` row exists for the run (the one-active-turn invariant
    of Task 25.B).  Incomplete evidence (a RUNNING run without a phase) is
    carried as-is; the guard interprets it fail-closed.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal[1]
    run_id: StrictStr
    status: StrictStr
    phase: RunPhase | None = None
    active_turn: bool = False

    @field_validator("schema_version", mode="before")
    @classmethod
    def _schema_version_is_exact_int(cls, value: object) -> object:
        if not isinstance(value, int) or isinstance(value, bool):
            raise ValueError("schema_version must be the decimal integer 1")
        return value

    @field_validator("status")
    @classmethod
    def _status_is_closed(cls, value: str) -> str:
        if value not in _RUN_STATUSES:
            raise ValueError(f"unknown run status {value!r}")
        return value

    @field_validator("run_id")
    @classmethod
    def _run_id_is_bounded(cls, value: str) -> str:
        if value == "":
            raise ValueError("run ids must be non-empty")
        if len(value.encode("utf-8")) > _MAX_IDENTIFIER_CHARS:
            raise ValueError("run ids must be at most 128 UTF-8 bytes")
        return value

    @field_validator("active_turn")
    @classmethod
    def _active_turn_is_exact_bool(cls, value: bool) -> bool:
        if not isinstance(value, bool):
            raise ValueError("active_turn must be a boolean")
        return value


class RestartDispositionV1(BaseModel):
    """One typed fail-closed stop/audit disposition (GREEN-2).

    ``STOP`` carries the exact restart stop reason and always forbids
    resend; ``CONTINUE`` marks a clean boundary (no interrupted turn);
    ``DEFER_RECOVERY`` hands the persistent phase and recovery-required
    runs to the persistence recovery machinery.  The caller executes the
    command (stop the run and record the audit event); the guard itself
    never mutates, reconstructs, resends, or recovers.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal[1]
    kind: Literal["STOP", "CONTINUE", "DEFER_RECOVERY"]
    stop_reason: RestartStopReasonV1 | None = None
    resend_allowed: Literal[False] = False
    run_id: StrictStr

    @field_validator("schema_version", mode="before")
    @classmethod
    def _schema_version_is_exact_int(cls, value: object) -> object:
        if not isinstance(value, int) or isinstance(value, bool):
            raise ValueError("schema_version must be the decimal integer 1")
        return value

    @field_validator("run_id")
    @classmethod
    def _run_id_is_bounded(cls, value: str) -> str:
        if value == "":
            raise ValueError("run ids must be non-empty")
        if len(value.encode("utf-8")) > _MAX_IDENTIFIER_CHARS:
            raise ValueError("run ids must be at most 128 UTF-8 bytes")
        return value

    @model_validator(mode="after")
    def _require_exact_outcome(self) -> RestartDispositionV1:
        if self.kind == "STOP":
            if self.stop_reason is None:
                raise ValueError("STOP dispositions require the stop reason")
        elif self.stop_reason is not None:
            raise ValueError("non-STOP dispositions carry no stop reason")
        return self


class RestartGuard:
    """One deterministic fail-closed restart inspector (25.F GREEN-1).

    ``inspect`` interprets persisted evidence with active-turn precedence
    and terminal/phase discrimination; it performs no side effects and
    forbids resend on every disposition.
    """

    def inspect(self, run: RunEvidenceV1) -> RestartDispositionV1:
        """Return one typed stop/audit disposition for the persisted run.

        The disposition table (25.F Expected line): an ACTIVE turn always
        stops with ``PROCESS_RESTART_DURING_TURN`` (active-turn precedence
        over every status, including contradictory terminal evidence);
        terminal runs and never-started runs are clean boundaries; the
        persistent phase and ``RECOVERY_REQUIRED`` defer to the
        persistence recovery machinery; every other RUNNING phase and
        both ``WAITING_USER`` kinds stop with
        ``PROCESS_RESTARTED_DURING_RUN``; and incomplete evidence (a
        RUNNING run without a phase) fails closed as an interrupted
        non-persistent run (SPEC 5.2).
        """
        if run.active_turn:
            return self._disposition(run, "STOP", "PROCESS_RESTART_DURING_TURN")
        if run.status in ("SUCCEEDED", "STOPPED"):
            return self._disposition(run, "CONTINUE", None)
        if run.status == "RECOVERY_REQUIRED" or run.phase == "PERSISTENCE":
            return self._disposition(run, "DEFER_RECOVERY", None)
        if run.status == "CREATED":
            return self._disposition(run, "CONTINUE", None)
        # RUNNING with any non-persistent phase (or an incomplete RUNNING
        # evidence row) and the two WAITING_USER kinds are interrupted
        # non-persistent runs.
        return self._disposition(run, "STOP", "PROCESS_RESTARTED_DURING_RUN")

    @staticmethod
    def _disposition(
        run: RunEvidenceV1,
        kind: Literal["STOP", "CONTINUE", "DEFER_RECOVERY"],
        stop_reason: RestartStopReasonV1 | None,
    ) -> RestartDispositionV1:
        return RestartDispositionV1(
            schema_version=1,
            kind=kind,
            stop_reason=stop_reason,
            resend_allowed=False,
            run_id=run.run_id,
        )

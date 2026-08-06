"""T25.3 legacy step 25.E: pure wait, deadline, and resume transitions.

``WaitController`` validates exact persisted Run/wait/decision identities
and permits pause or resume only at declared wait states with one-winner
decision handling (GREEN-1); it compares injected time against the
smaller applicable deadline — the wait's ``expires_at`` is by §4.2.7
construction ``min(created_at + user_wait_timeout, run_deadline)`` — and
never resumes an expired, stale, duplicated, or mismatched action
(GREEN-2/GREEN-3).  The controller consumes persisted bindings and
injected time only: it never calls the LLM, tool dispatcher, or
persistence writer (GREEN-4/Boundary).  The applied-decision registry is
a bounded per-process set (Task 17.B precedent) so the same decision
event can win exactly once.
"""

from __future__ import annotations

from typing import Literal, TypeAlias

from pydantic import BaseModel, ConfigDict, StrictStr

from src.vespercode.canonical.timestamp_v1 import CanonicalTimestampV1
from src.vespercode.contracts.run import WaitContextV1, WaitDecisionV1

WaitTransitionKindV1: TypeAlias = Literal[
    "ENTERED",
    "RESUMED",
    "REJECTED",
    "WAIT_EXPIRED",
    "NOT_EXPIRED",
    "REPLAY",
    "STALE",
]
"""The closed wait-transition outcomes (SPEC §4.2.7/§4.2.8, 25.E)."""

WaitResumeActionV1: TypeAlias = Literal["RESUME_AGENT_LOOP", "ENTER_PERSISTENCE"]
"""The declared post-resume action (DISCLOSURE_GRANT vs FINAL_WRITEBACK)."""


class WaitTransitionResultV1(BaseModel):
    """One closed wait-transition outcome (the card's RED contract).

    ``WAIT_EXPIRED`` and every terminal outcome carry ``resume_action``
    of ``None`` — an expired, rejected, stale, or replayed wait never
    resumes an agent action; ``wait_deadline`` is the effective smaller
    applicable deadline whenever the wait remains active.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)
    kind: WaitTransitionKindV1
    message: StrictStr
    resume_action: WaitResumeActionV1 | None = None
    wait_deadline: CanonicalTimestampV1 | None = None


class WaitController:
    """One deterministic pure wait-transition controller (25.E GREEN-1..4)."""

    def __init__(self) -> None:
        self._applied_events: set[str] = set()
        self._applied_waits: set[str] = set()

    def reset_applied_decisions(self) -> None:
        """Clear the one-winner registry (deterministic test isolation)."""
        self._applied_events.clear()
        self._applied_waits.clear()

    def enter(
        self,
        wait: WaitContextV1,
        now: CanonicalTimestampV1,
    ) -> WaitTransitionResultV1:
        """Validate one declared wait at entry (GREEN-1).

        A wait whose expiry already passed never enters (``WAIT_EXPIRED``)
        and a wait whose creation lies in the future is contradictory
        (``STALE``); otherwise the pause is declared with the effective
        smaller applicable deadline (``wait.expires_at``).
        """
        if now.epoch_milliseconds >= wait.expires_at.epoch_milliseconds:
            return WaitTransitionResultV1(
                kind="WAIT_EXPIRED",
                message="the wait has already expired",
            )
        if now.epoch_milliseconds < wait.created_at.epoch_milliseconds:
            return WaitTransitionResultV1(
                kind="STALE",
                message="the wait creation lies in the future",
            )
        return WaitTransitionResultV1(
            kind="ENTERED",
            message="the wait is declared",
            wait_deadline=wait.expires_at,
        )

    def resume(
        self,
        wait: WaitContextV1,
        decision: WaitDecisionV1,
        now: CanonicalTimestampV1,
    ) -> WaitTransitionResultV1:
        """Resume exactly one declared wait, expiry first (GREEN-2/3).

        The closed order: an expired wait never resumes (now or the
        decision's own timestamp past ``expires_at`` is ``WAIT_EXPIRED``),
        a decision predating the wait or bound to another wait/run/kind/
        subject is ``STALE``, an already-applied decision event or an
        already-resumed wait is ``REPLAY`` (one winner), an APPROVE
        resumes with the declared action, and a REJECT stops.
        """
        if now.epoch_milliseconds >= wait.expires_at.epoch_milliseconds:
            return WaitTransitionResultV1(
                kind="WAIT_EXPIRED",
                message="the wait has expired",
            )
        if decision.decided_at.epoch_milliseconds > wait.expires_at.epoch_milliseconds:
            return WaitTransitionResultV1(
                kind="WAIT_EXPIRED",
                message="the decision was made after the wait expired",
            )
        if decision.decided_at.epoch_milliseconds < wait.created_at.epoch_milliseconds:
            return WaitTransitionResultV1(
                kind="STALE",
                message="the decision predates the wait",
            )
        if (
            decision.wait_id != wait.wait_id
            or decision.run_id != wait.run_id
            or decision.wait_kind != wait.wait_kind
            or decision.subject_digest.value != wait.subject_digest.value
        ):
            return WaitTransitionResultV1(
                kind="STALE",
                message="the decision does not bind this exact wait",
            )
        if (
            decision.event_id in self._applied_events
            or wait.wait_id in self._applied_waits
        ):
            return WaitTransitionResultV1(
                kind="REPLAY",
                message="this wait already won its one decision",
            )
        if decision.decision == "REJECT":
            self._applied_events.add(decision.event_id)
            self._applied_waits.add(wait.wait_id)
            return WaitTransitionResultV1(
                kind="REJECTED",
                message="the user rejected the wait",
            )
        self._applied_events.add(decision.event_id)
        self._applied_waits.add(wait.wait_id)
        return WaitTransitionResultV1(
            kind="RESUMED",
            message="the wait was approved exactly once",
            resume_action=(
                "RESUME_AGENT_LOOP"
                if wait.wait_kind == "DISCLOSURE_GRANT"
                else "ENTER_PERSISTENCE"
            ),
            wait_deadline=wait.expires_at,
        )

    def expire(
        self,
        wait: WaitContextV1,
        now: CanonicalTimestampV1,
    ) -> WaitTransitionResultV1:
        """Check the wait at a pause point (GREEN-2).

        ``WAIT_EXPIRED`` when the smaller applicable deadline passed,
        ``NOT_EXPIRED`` (the pause continues) otherwise.
        """
        if now.epoch_milliseconds >= wait.expires_at.epoch_milliseconds:
            return WaitTransitionResultV1(
                kind="WAIT_EXPIRED",
                message="the wait has expired",
            )
        return WaitTransitionResultV1(
            kind="NOT_EXPIRED",
            message="the wait remains pending",
            wait_deadline=wait.expires_at,
        )

"""T07.2 legacy step 7.B: pure Run/wait lifecycle target-state derivation.

``LifecycleRules.evaluate`` derives the exact SPEC 4.2.7 target state from
one closed ``LifecycleEventV1`` applied to one ``RunStateV1``: every legal
transition (start, phase advance/continue, wait entry/approval/termination,
stop, succeed, persistence failure, recovery outcome) maps exactly, and
every illegal combination (wrong source phase, wrong wait kind/phase
binding, terminal reopen, recovery source violation) fails closed with the
closed ``LifecycleTransitionErrorV1`` before any persistence.  Persistence,
decisions, and clocks remain out of scope (GREEN-4).
"""

from __future__ import annotations

from typing import Literal, TypeAlias

from pydantic import BaseModel, ConfigDict, model_validator

from vespercode.contracts.optional import AbsentV1, PresentV1
from vespercode.contracts.run import (
    RunPhase,
    RunStateV1,
    RunStatus,
    WaitKind,
)

LifecycleEventKindV1: TypeAlias = Literal[
    "START",
    "PHASE",
    "WAIT",
    "WAIT_APPROVED",
    "WAIT_TERMINATED",
    "STOP",
    "SUCCEED",
    "PERSISTENCE_FAILED",
    "RECOVER",
]

RecoverOutcomeV1: TypeAlias = Literal["SUCCEEDED", "STOPPED", "KEEP"]


class LifecycleEventV1(BaseModel):
    """One closed lifecycle event with its exact kind-bound payload."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    kind: LifecycleEventKindV1
    phase: RunPhase | None = None
    wait_kind: WaitKind | None = None
    recover_outcome: RecoverOutcomeV1 | None = None

    @model_validator(mode="after")
    def _require_exact_kind_payload(self) -> LifecycleEventV1:
        if self.kind == "PHASE" and self.phase is None:
            raise ValueError("PHASE events require their exact phase")
        if self.kind != "PHASE" and self.phase is not None:
            raise ValueError("only PHASE events carry a phase")
        if (
            self.kind in ("WAIT", "WAIT_APPROVED", "WAIT_TERMINATED")
            and self.wait_kind is None
        ):
            raise ValueError(f"{self.kind} events require their exact wait kind")
        if (
            self.kind not in ("WAIT", "WAIT_APPROVED", "WAIT_TERMINATED")
            and self.wait_kind is not None
        ):
            raise ValueError("only wait events carry a wait kind")
        if self.kind == "RECOVER" and self.recover_outcome is None:
            raise ValueError("RECOVER events require their exact outcome")
        if self.kind != "RECOVER" and self.recover_outcome is not None:
            raise ValueError("only RECOVER events carry a recovery outcome")
        return self


class LifecycleTransitionErrorV1(ValueError):
    """Closed rejection for an illegal lifecycle transition."""


def _running(phase: RunPhase) -> RunStateV1:
    return RunStateV1(status="RUNNING", phase=PresentV1(kind="PRESENT", value=phase))


def _plain(status: RunStatus) -> RunStateV1:
    return RunStateV1(status=status, phase=AbsentV1(kind="ABSENT"))


def _candidate_target(
    current: RunStateV1,
    event: LifecycleEventV1,
) -> RunStateV1 | None:
    """The event's exact target for *current*, or None when not applicable."""
    kind = event.kind
    if kind == "START":
        return _running("PREFLIGHT") if current.status == "CREATED" else None
    if kind == "PHASE":
        if current.status != "RUNNING":
            return None
        assert event.phase is not None
        return _running(event.phase)
    if kind == "WAIT":
        assert event.wait_kind is not None
        if event.wait_kind == "DISCLOSURE_GRANT":
            if current == _running("AGENT_LOOP"):
                return _plain("WAITING_USER")
        elif event.wait_kind == "FINAL_WRITEBACK":
            if current == _running("FORMAL_VALIDATION"):
                return _plain("WAITING_USER")
        return None
    if kind == "WAIT_APPROVED":
        if current.status != "WAITING_USER":
            return None
        assert event.wait_kind is not None
        if event.wait_kind == "DISCLOSURE_GRANT":
            return _running("AGENT_LOOP")
        if event.wait_kind == "FINAL_WRITEBACK":
            return _running("PERSISTENCE")
        return None
    if kind == "WAIT_TERMINATED":
        return _plain("STOPPED") if current.status == "WAITING_USER" else None
    if kind == "STOP":
        if current.status in ("SUCCEEDED", "STOPPED", "RECOVERY_REQUIRED"):
            return None
        return _plain("STOPPED")
    if kind == "SUCCEED":
        return _plain("SUCCEEDED") if current == _running("PERSISTENCE") else None
    if kind == "PERSISTENCE_FAILED":
        return (
            _plain("RECOVERY_REQUIRED") if current == _running("PERSISTENCE") else None
        )
    if kind == "RECOVER":
        if current.status != "RECOVERY_REQUIRED":
            return None
        assert event.recover_outcome is not None
        if event.recover_outcome == "SUCCEEDED":
            return _plain("SUCCEEDED")
        if event.recover_outcome == "STOPPED":
            return _plain("STOPPED")
        return _plain("RECOVERY_REQUIRED")
    return None


# The closed SPEC 4.2.7 transition table: every legal (expected, target)
# state pair.  This is the single authority consumed both by
# ``LifecycleRules.evaluate`` and by the repository's compare-and-transition
# legality gate.
_LEGAL_STATE_PAIRS: frozenset[tuple[RunStateV1, RunStateV1]] = frozenset(
    {
        (_plain("CREATED"), _running("PREFLIGHT")),
        (_plain("CREATED"), _plain("STOPPED")),
        (_running("PREFLIGHT"), _running("BASELINE")),
        (_running("PREFLIGHT"), _plain("STOPPED")),
        (_running("BASELINE"), _running("AGENT_LOOP")),
        (_running("BASELINE"), _plain("STOPPED")),
        (_running("AGENT_LOOP"), _running("AGENT_LOOP")),
        (_running("AGENT_LOOP"), _plain("WAITING_USER")),
        (_running("AGENT_LOOP"), _running("FORMAL_VALIDATION")),
        (_running("AGENT_LOOP"), _plain("STOPPED")),
        (_running("FORMAL_VALIDATION"), _running("AGENT_LOOP")),
        (_running("FORMAL_VALIDATION"), _plain("WAITING_USER")),
        (_running("FORMAL_VALIDATION"), _plain("STOPPED")),
        (_plain("WAITING_USER"), _running("AGENT_LOOP")),
        (_plain("WAITING_USER"), _running("PERSISTENCE")),
        (_plain("WAITING_USER"), _plain("STOPPED")),
        (_running("PERSISTENCE"), _plain("SUCCEEDED")),
        (_running("PERSISTENCE"), _plain("STOPPED")),
        (_running("PERSISTENCE"), _plain("RECOVERY_REQUIRED")),
        (_plain("RECOVERY_REQUIRED"), _plain("SUCCEEDED")),
        (_plain("RECOVERY_REQUIRED"), _plain("STOPPED")),
        (_plain("RECOVERY_REQUIRED"), _plain("RECOVERY_REQUIRED")),
    }
)


class LifecycleRules:
    """Pure target-state derivation over the closed SPEC 4.2.7 table."""

    @staticmethod
    def evaluate(
        current: RunStateV1,
        event: LifecycleEventV1,
    ) -> RunStateV1:
        """Derive the exact target state, failing closed on illegal input."""
        target = _candidate_target(current, event)
        if target is None or not LifecycleRules.is_legal_transition(current, target):
            raise LifecycleTransitionErrorV1(
                f"{current.status} cannot apply event {event.kind}"
            )
        return target

    @staticmethod
    def is_legal_transition(expected: RunStateV1, target: RunStateV1) -> bool:
        """Whether the (expected, target) pair is in the closed SPEC table."""
        return (expected, target) in _LEGAL_STATE_PAIRS

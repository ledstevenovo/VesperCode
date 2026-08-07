"""T25.3 legacy step 25.E: cancellation safe-point evaluation.

``CancellationController.evaluate_safe_point`` honors a pending
cancellation request only at deterministic safe points (SPEC §4.2.6):
the action boundary and the waiting-user state are safe; an in-progress
persistence transaction (after the first file replacement), an unresolved
recovery, a coordinator-owned phase, a never-started run, and an already
terminal run all hold the request until their own boundary.  The
controller is pure over the persisted ``RunRecordV1`` and the request
flag; the caller executes the stop (GREEN-4).
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, StrictStr

from vespercode.storage.run_repository import RunRecordV1


class CancellationDecisionV1(BaseModel):
    """One closed safe-point verdict (SPEC §4.2.6, 25.E).

    ``SAFE_TO_CANCEL`` means the cancellation may be honored at this
    deterministic point with zero side effects; ``HOLD`` keeps the
    request pending until the next safe point (or terminal state).
    """

    model_config = ConfigDict(extra="forbid", frozen=True)
    kind: Literal["SAFE_TO_CANCEL", "HOLD"]
    reason: StrictStr


class CancellationController:
    """One deterministic pure safe-point evaluator (25.E GREEN-2)."""

    def evaluate_safe_point(
        self,
        run: RunRecordV1,
        cancellation_requested: bool,
    ) -> CancellationDecisionV1:
        """Return the one closed safe-point verdict (SPEC §4.2.6).

        The exact table: no request holds; the waiting-user state and the
        AGENT_LOOP action boundary are safe; an in-progress persistence
        transaction (after the first file replacement), an unresolved
        recovery, a coordinator-owned phase, a never-started run, and an
        already-terminal run all hold the request until their own
        boundary.  Pure: the caller executes the stop.
        """
        if not cancellation_requested:
            return CancellationDecisionV1(kind="HOLD", reason="NO_CANCELLATION")
        if run.status == "WAITING_USER":
            return CancellationDecisionV1(kind="SAFE_TO_CANCEL", reason="WAITING_USER")
        if run.status == "RUNNING" and run.phase.kind == "PRESENT":
            if run.phase.value == "AGENT_LOOP":
                return CancellationDecisionV1(
                    kind="SAFE_TO_CANCEL", reason="ACTION_BOUNDARY"
                )
            if run.phase.value == "PERSISTENCE":
                return CancellationDecisionV1(
                    kind="HOLD", reason="PERSISTENCE_IN_PROGRESS"
                )
            return CancellationDecisionV1(kind="HOLD", reason="COORDINATOR_PHASE")
        if run.status == "RECOVERY_REQUIRED":
            return CancellationDecisionV1(kind="HOLD", reason="RECOVERY_IN_PROGRESS")
        if run.status in ("SUCCEEDED", "STOPPED"):
            return CancellationDecisionV1(kind="HOLD", reason="ALREADY_TERMINAL")
        if run.status == "CREATED":
            return CancellationDecisionV1(kind="HOLD", reason="NOT_STARTED")
        return CancellationDecisionV1(kind="HOLD", reason="COORDINATOR_PHASE")

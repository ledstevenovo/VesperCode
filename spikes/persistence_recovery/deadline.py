"""T03.1 legacy step 3.C: persistence deadline stop semantics.

Evaluates the persistence deadline as a pure function of immutable
transaction facts, the observed workspace write count, and the current
time (SPEC 4.6 item 11 and 4.2.6): before any write the disposition is
STOPPED_ZERO_WRITE; after any write it is RECOVERY_REQUIRED; further
workspace writes are authorized exactly while ``now_ms < deadline_ms``
and zero/no further writes once expired.  This module performs no I/O,
owns no current object identity, and applies no rollback/recovery.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from spikes.persistence_recovery.protocol import GateTransactionV1

DeadlineDispositionV1 = Literal["STOPPED_ZERO_WRITE", "RECOVERY_REQUIRED"]


@dataclass(frozen=True)
class DeadlineEvaluationV1:
    """Immutable outcome of one deadline evaluation.

    ``disposition`` describes the stop this evaluation produces: with
    zero observed workspace writes the transaction can still stop with
    zero writes (STOPPED_ZERO_WRITE); with any write it can only stop
    into recovery (RECOVERY_REQUIRED).  ``further_workspace_writes_allowed``
    is the write authorization: true exactly while the deadline has not
    expired, false once ``now_ms >= deadline_ms``.
    """

    disposition: DeadlineDispositionV1
    further_workspace_writes_allowed: bool


def evaluate_persistence_deadline(
    transaction: GateTransactionV1,
    observed_write_count: int,
    now_ms: int,
) -> DeadlineEvaluationV1:
    """Evaluate the persistence deadline for *transaction* at *now_ms*.

    Pure and side-effect free: the same immutable inputs always produce
    the identical closed :class:`DeadlineEvaluationV1`.
    """
    if observed_write_count < 0:
        raise ValueError("observed_write_count must be non-negative")
    disposition: DeadlineDispositionV1 = (
        "STOPPED_ZERO_WRITE" if observed_write_count == 0 else "RECOVERY_REQUIRED"
    )
    return DeadlineEvaluationV1(
        disposition=disposition,
        further_workspace_writes_allowed=now_ms < transaction.deadline_ms,
    )

"""T23.1 legacy step 23.B: pure user-facing Run visibility projection.

``build_run_visibility`` validates the exact Run identity and the
monotonic typed event/wait inputs, then maps each formal
Run/phase/wait/recovery/terminal fact through one closed precedence
table into exactly one bounded user-visible state: recovery facts
(recorded ``RECOVERY_REQUIRED`` or an unresolved recovery reference)
always dominate terminal projection, so a recovery-required Run is
never shown as PASS/STOPPED and absent evidence is never inferred as
success.  The output carries only the bounded stable state label,
reason code, next action, and safe evidence references of the most
recent fact — never internal rows or payload bodies.  SQLite access,
event mutation, lifecycle changes, and external-outcome claims remain
out of scope (GREEN-4).
"""

from __future__ import annotations

from typing import Literal, TypeAlias, cast

from pydantic import BaseModel, ConfigDict, StrictStr

from vespercode.audit.event import AuditEventV1, RecoveryPayloadV1
from vespercode.contracts.run import WaitContextV1
from vespercode.storage.run_repository import RunRecordV1

WaitContextSequenceV1: TypeAlias = tuple[WaitContextV1, ...]
"""Immutable ordered tuple of the Run's typed wait contexts."""

AuditEventSequenceV1: TypeAlias = tuple[AuditEventV1, ...]
"""Immutable ordered tuple of the Run's typed audit facts."""

StateLabelV1: TypeAlias = Literal[
    "CREATED",
    "PREFLIGHT",
    "BASELINE",
    "AGENT_LOOP",
    "FORMAL_VALIDATION",
    "PERSISTENCE",
    "WAITING_USER",
    "RECOVERY_REQUIRED",
    "SUCCEEDED",
    "STOPPED",
]
"""The distinct unambiguous user-visible state labels (SPEC 4.9)."""

ReasonCodeV1: TypeAlias = Literal[
    "RUN_CREATED",
    "RUNNING_PHASE",
    "USER_DECISION_PENDING",
    "WAIT_CONTEXT_MISSING",
    "RECOVERY_PENDING",
    "RUN_SUCCEEDED",
    "RUN_STOPPED",
]
"""The closed stable reason codes behind one visible state."""

NextActionV1: TypeAlias = Literal[
    "START",
    "CONTINUE",
    "AWAIT_USER_DECISION",
    "REVIEW_RECOVERY",
    "RETRIEVE_EVIDENCE",
    "REVIEW_STOP_REASON",
]
"""The closed bounded next-action suggestions."""


class RunVisibilityV1(BaseModel):
    """One bounded user-visible Run state and reason.

    The state label, reason code, and next action are closed stable
    codes; ``evidence_refs`` carries only the safe evidence references
    of the most recent fact (never internal rows, payload bodies, or
    raw outputs).
    """

    model_config = ConfigDict(extra="forbid", frozen=True)
    run_id: StrictStr
    state_label: StateLabelV1
    reason_code: ReasonCodeV1
    next_action: NextActionV1
    evidence_refs: tuple[StrictStr, ...]


class ProjectionValidationErrorV1(ValueError):
    """Closed rejection for an invalid projection input."""


def _validate_inputs(
    run: RunRecordV1,
    waits: WaitContextSequenceV1,
    events: AuditEventSequenceV1,
) -> None:
    """Validate the exact identity and monotonic typed inputs.

    Every event must belong to the exact Run with a strictly increasing
    per-Run sequence; every wait must belong to the exact Run with
    unique ids and non-decreasing creation times.  The phase/status
    consistency is already guaranteed by the closed ``RunRecordV1`` type
    and is re-checked defensively so the projection stays fail-closed on
    its own.
    """
    previous_sequence = 0
    for event in events:
        if event.run_id != run.run_id:
            raise ProjectionValidationErrorV1("audit event belongs to another run")
        if event.sequence <= previous_sequence:
            raise ProjectionValidationErrorV1("audit event sequence is not monotonic")
        previous_sequence = event.sequence
    seen_wait_ids: set[str] = set()
    previous_created_at: int | None = None
    for wait in waits:
        if wait.run_id != run.run_id:
            raise ProjectionValidationErrorV1("wait context belongs to another run")
        if wait.wait_id in seen_wait_ids:
            raise ProjectionValidationErrorV1("wait context is duplicated")
        seen_wait_ids.add(wait.wait_id)
        created_at = wait.created_at.epoch_milliseconds
        if previous_created_at is not None and created_at < previous_created_at:
            raise ProjectionValidationErrorV1(
                "wait context timestamps are not monotonic"
            )
        previous_created_at = created_at
    if run.status == "RUNNING" and run.phase.kind != "PRESENT":
        raise ProjectionValidationErrorV1("RUNNING run has no phase")
    if run.status != "RUNNING" and run.phase.kind == "PRESENT":
        raise ProjectionValidationErrorV1("non-RUNNING run carries a phase")


def _is_unresolved_recovery(event: AuditEventV1) -> bool:
    """Whether one typed audit fact is an unresolved recovery reference."""
    if event.event_type != "RECOVERY":
        return False
    payload = event.redacted_payload
    if not isinstance(payload, RecoveryPayloadV1):
        return False
    return payload.disposition == "UNRESOLVED"


def build_run_visibility(
    run: RunRecordV1,
    waits: WaitContextSequenceV1,
    events: AuditEventSequenceV1,
) -> RunVisibilityV1:
    """Project one Run's formal facts into exactly one bounded visible state.

    The closed precedence table maps recovery facts first (recorded
    ``RECOVERY_REQUIRED`` status or any unresolved recovery reference),
    then the recorded terminal/phase facts; a WAITING_USER Run without a
    wait context keeps the wait state but reports the missing wait
    evidence instead of fabricating a decision prompt.  The reason code
    and next action are stable closed codes, and the evidence
    references are the most recent fact's safe references (already
    bounded to eight by the payload contract), so absent evidence never
    projects as PASS/STOPPED.
    """
    _validate_inputs(run, waits, events)
    unresolved_recovery = any(_is_unresolved_recovery(event) for event in events)
    if run.status == "RECOVERY_REQUIRED" or unresolved_recovery:
        label: StateLabelV1 = "RECOVERY_REQUIRED"
        reason: ReasonCodeV1 = "RECOVERY_PENDING"
        next_action: NextActionV1 = "REVIEW_RECOVERY"
    elif run.status == "SUCCEEDED":
        label = "SUCCEEDED"
        reason = "RUN_SUCCEEDED"
        next_action = "RETRIEVE_EVIDENCE"
    elif run.status == "STOPPED":
        label = "STOPPED"
        reason = "RUN_STOPPED"
        next_action = "REVIEW_STOP_REASON"
    elif run.status == "WAITING_USER":
        label = "WAITING_USER"
        reason = "USER_DECISION_PENDING" if waits else "WAIT_CONTEXT_MISSING"
        next_action = "AWAIT_USER_DECISION"
    elif run.status == "RUNNING":
        assert run.phase.kind == "PRESENT"
        label = cast(StateLabelV1, run.phase.value)
        reason = "RUNNING_PHASE"
        next_action = "CONTINUE"
    else:
        label = "CREATED"
        reason = "RUN_CREATED"
        next_action = "START"
    evidence_refs: tuple[StrictStr, ...]
    if events:
        # The most recent fact's safe references; the payload contract
        # bounds every fact to at most eight references.
        evidence_refs = events[-1].redacted_payload.evidence_refs
    else:
        evidence_refs = ()
    return RunVisibilityV1(
        run_id=run.run_id,
        state_label=label,
        reason_code=reason,
        next_action=next_action,
        evidence_refs=evidence_refs,
    )

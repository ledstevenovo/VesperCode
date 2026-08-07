"""T25.3 legacy step 25.E: wait, deadline, and cancellation lifecycle tests.

The exact RED test pins the expiry-first transition (an expired wait
never resumes an agent action); the matrix pins the exact decision table
of the 25.E Expected line — exact approval resumes once, reject/expiry/
cancel stop as declared, and duplicate, wrong-binding, stale-deadline,
or replay-conflict input never resumes (SPEC §4.2.7/§4.2.8, Registry row
25.E).
"""

from __future__ import annotations

import pytest

# The controllers consume pydantic runtime contracts; the hash-locked
# gate toolchain installs no runtime dependencies, so this module skips
# cleanly there (formal env runs it fully).
pytest.importorskip("pydantic")

from vespercode.canonical.timestamp_v1 import CanonicalTimestampV1
from vespercode.contracts.evidence import DigestV1
from vespercode.contracts.run import (
    RunPhase,
    RunStatus,
    WaitContextV1,
    WaitDecisionV1,
    WaitDecisionChoiceV1,
    WaitKind,
)
from vespercode.loop.cancellation import CancellationController
from vespercode.loop.wait_control import WaitController
from vespercode.contracts.optional import AbsentV1, PresentV1
from vespercode.storage.run_repository import RunRecordV1

_CREATED_AT = CanonicalTimestampV1("2026-08-06T09:00:00.000Z")
_EXPIRES_AT = CanonicalTimestampV1("2026-08-06T09:05:00.000Z")
_DECIDED_AT = CanonicalTimestampV1("2026-08-06T09:01:00.000Z")
_NOW = CanonicalTimestampV1("2026-08-06T09:02:00.000Z")
_SUBJECT_DIGEST = "1" * 64
_RUN_DEADLINE = CanonicalTimestampV1("2026-08-06T09:15:00.000Z")


def active_wait(
    *,
    wait_id: str = "wait-1",
    run_id: str = "run-1",
    wait_kind: WaitKind = "DISCLOSURE_GRANT",
    created_at: CanonicalTimestampV1 = _CREATED_AT,
    expires_at: CanonicalTimestampV1 = _EXPIRES_AT,
) -> WaitContextV1:
    """One exact §4.2.7 wait binding (expires_at is the smaller deadline)."""
    return WaitContextV1(
        wait_id=wait_id,
        run_id=run_id,
        wait_kind=wait_kind,
        source_phase="AGENT_LOOP"
        if wait_kind == "DISCLOSURE_GRANT"
        else "FORMAL_VALIDATION",
        subject_digest=DigestV1(value=_SUBJECT_DIGEST),
        created_at=created_at,
        expires_at=expires_at,
    )


def valid_decision(
    *,
    wait: WaitContextV1 | None = None,
    decision: WaitDecisionChoiceV1 = "APPROVE",
    event_id: str = "evt-1",
    decided_at: CanonicalTimestampV1 = _DECIDED_AT,
) -> WaitDecisionV1:
    """One decision exactly bound to the wait (SPEC §4.2.7/AC-27)."""
    bound = wait if wait is not None else active_wait()
    return WaitDecisionV1(
        wait_id=bound.wait_id,
        run_id=bound.run_id,
        wait_kind=bound.wait_kind,
        subject_digest=DigestV1(value=_SUBJECT_DIGEST),
        decision=decision,
        event_id=event_id,
        decided_at=decided_at,
    )


def expired_wait() -> WaitContextV1:
    """One wait whose expiry lies before every resume time."""
    return active_wait(expires_at=CanonicalTimestampV1("2026-08-06T09:01:30.000Z"))


def after(timestamp: CanonicalTimestampV1) -> CanonicalTimestampV1:
    """One deterministic timestamp strictly after the given one."""
    return CanonicalTimestampV1.from_epoch_milliseconds(
        timestamp.epoch_milliseconds + 60_000
    )


def run_record(
    *,
    status: RunStatus = "WAITING_USER",
    phase: RunPhase | None = None,
) -> RunRecordV1:
    """One persisted run record for the cancellation safe-point rows."""
    return RunRecordV1(
        run_id="run-1",
        workspace_identity="workspace-1",
        status=status,
        phase=(
            AbsentV1(kind="ABSENT")
            if phase is None
            else PresentV1(kind="PRESENT", value=phase)
        ),
        config_snapshot_id="snap-1",
        started_at=_CREATED_AT,
        run_deadline=_RUN_DEADLINE,
    )


@pytest.fixture
def wait_control() -> WaitController:
    return WaitController()


def test_expired_wait_never_resumes_agent_action(
    wait_control: WaitController,
) -> None:
    wait = expired_wait()
    result = wait_control.resume(wait, valid_decision(), after(wait.expires_at))
    assert result.kind == "WAIT_EXPIRED"
    assert result.resume_action is None


def test_wait_resume_decision_matrix(wait_control: WaitController) -> None:
    """PLAN Registry row 25.E: the exact wait/resume decision matrix.

    Per the SPEC_PROCESS 49 precedent the card Expected line is the
    operative matrix authority: exact approval resumes once; reject,
    expiry, and cancel stop as declared; duplicate, wrong binding, stale
    deadline, or replay conflict never resumes an agent action.
    """
    wait_control.reset_applied_decisions()

    # --- Exact approval resumes once with the declared action. ---
    approved = wait_control.resume(active_wait(), valid_decision(), _NOW)
    assert approved.kind == "RESUMED"
    assert approved.resume_action == "RESUME_AGENT_LOOP"
    assert approved.wait_deadline == _EXPIRES_AT
    # FINAL_WRITEBACK approval enters persistence.
    writeback = active_wait(wait_kind="FINAL_WRITEBACK", wait_id="wait-fw")
    approved_writeback = wait_control.resume(
        writeback, valid_decision(wait=writeback, event_id="evt-fw"), _NOW
    )
    assert approved_writeback.kind == "RESUMED"
    assert approved_writeback.resume_action == "ENTER_PERSISTENCE"

    # --- Duplicate and replay conflict never resume again. ---
    duplicate = wait_control.resume(active_wait(), valid_decision(), _NOW)
    assert duplicate.kind == "REPLAY"
    assert duplicate.resume_action is None
    other_wait = active_wait(wait_id="wait-2", run_id="run-2")
    other = wait_control.resume(
        other_wait, valid_decision(wait=other_wait, event_id="evt-2"), _NOW
    )
    assert other.kind == "RESUMED"
    second_event = wait_control.resume(
        other_wait, valid_decision(wait=other_wait, event_id="evt-3"), _NOW
    )
    assert second_event.kind == "REPLAY"
    assert second_event.resume_action is None

    # --- Reject stops as declared with no resume. ---
    wait_control.reset_applied_decisions()
    rejected = wait_control.resume(
        active_wait(),
        valid_decision(decision="REJECT"),
        _NOW,
    )
    assert rejected.kind == "REJECTED"
    assert rejected.resume_action is None

    # --- Expiry stops as declared (the exact RED, plus stale deadline). ---
    stale_deadline = wait_control.resume(
        active_wait(),
        valid_decision(decided_at=after(_EXPIRES_AT)),
        _NOW,
    )
    assert stale_deadline.kind == "WAIT_EXPIRED"
    assert stale_deadline.resume_action is None
    expired_now = wait_control.resume(
        active_wait(),
        valid_decision(),
        after(_EXPIRES_AT),
    )
    assert expired_now.kind == "WAIT_EXPIRED"
    assert expired_now.resume_action is None

    # --- Wrong bindings never resume (STALE). ---
    for wrong in (
        valid_decision(wait=active_wait(wait_id="wait-x")),
        valid_decision(wait=active_wait(run_id="run-x")),
        valid_decision(wait=active_wait(wait_kind="FINAL_WRITEBACK")),
    ):
        wrong_binding = wait_control.resume(active_wait(), wrong, _NOW)
        assert wrong_binding.kind == "STALE"
        assert wrong_binding.resume_action is None
    # A decision decided before its wait was created is stale evidence.
    premature = wait_control.resume(
        active_wait(),
        valid_decision(decided_at=CanonicalTimestampV1("2026-08-06T08:59:00.000Z")),
        _NOW,
    )
    assert premature.kind == "STALE"
    assert premature.resume_action is None

    # --- Enter: valid waits enter with the effective smaller deadline;
    #     expired or future waits never enter. ---
    entered = wait_control.enter(active_wait(), _NOW)
    assert entered.kind == "ENTERED"
    assert entered.wait_deadline == _EXPIRES_AT
    enter_expired = wait_control.enter(expired_wait(), _NOW)
    assert enter_expired.kind == "WAIT_EXPIRED"
    enter_future = wait_control.enter(
        active_wait(created_at=CanonicalTimestampV1("2026-08-06T09:03:00.000Z")),
        _NOW,
    )
    assert enter_future.kind == "STALE"

    # --- Expire: not-expired pauses, expired stops. ---
    not_expired = wait_control.expire(active_wait(), _NOW)
    assert not_expired.kind == "NOT_EXPIRED"
    assert not_expired.wait_deadline == _EXPIRES_AT
    force_expired = wait_control.expire(expired_wait(), _NOW)
    assert force_expired.kind == "WAIT_EXPIRED"

    # --- Cancel stops as declared only at deterministic safe points. ---
    controller = CancellationController()
    safe_waiting = controller.evaluate_safe_point(
        run_record(status="WAITING_USER"), True
    )
    assert safe_waiting.kind == "SAFE_TO_CANCEL"
    safe_action = controller.evaluate_safe_point(
        run_record(status="RUNNING", phase="AGENT_LOOP"), True
    )
    assert safe_action.kind == "SAFE_TO_CANCEL"
    assert safe_action.reason == "ACTION_BOUNDARY"
    held_persistence = controller.evaluate_safe_point(
        run_record(status="RUNNING", phase="PERSISTENCE"), True
    )
    assert held_persistence.kind == "HOLD"
    assert held_persistence.reason == "PERSISTENCE_IN_PROGRESS"
    held_recovery = controller.evaluate_safe_point(
        run_record(status="RECOVERY_REQUIRED"), True
    )
    assert held_recovery.kind == "HOLD"
    assert held_recovery.reason == "RECOVERY_IN_PROGRESS"
    held_terminal = controller.evaluate_safe_point(run_record(status="SUCCEEDED"), True)
    assert held_terminal.kind == "HOLD"
    held_phase = controller.evaluate_safe_point(
        run_record(status="RUNNING", phase="FORMAL_VALIDATION"), True
    )
    assert held_phase.kind == "HOLD"
    assert held_phase.reason == "COORDINATOR_PHASE"
    no_request = controller.evaluate_safe_point(
        run_record(status="WAITING_USER"), False
    )
    assert no_request.kind == "HOLD"
    assert no_request.reason == "NO_CANCELLATION"

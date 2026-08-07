"""T23.1 legacy step 23.B: user-facing Run visibility projection RED + matrix.

Pins the exact RED (a recovery-required Run is never projected as
STOPPED) and the PLAN legacy-step matrix row 23.B: every
CREATED/RUNNING/WAIT/terminal state projects exactly once with bounded
stable labels, reason codes, next actions, and safe evidence references;
RECOVERY_REQUIRED takes precedence over STOPPED (and over SUCCEEDED
when an unresolved recovery reference exists); impossible/missing phase
is rejected at the closed RunRecordV1 type and regressing revision,
cross-Run identity, and duplicate/regressing wait inputs are rejected
with the closed ``ProjectionValidationErrorV1``; absent evidence is
never treated as PASS/STOPPED.  The projection is pure over typed
Tasks 7.B/23.A facts only (GREEN-4).
"""

from __future__ import annotations

from typing import cast

import pytest

# The projection consumes pydantic runtime contracts; the hash-locked
# gate toolchain installs no runtime dependencies, so this module skips
# cleanly there (formal env runs it fully).
pytest.importorskip("pydantic")

from pydantic import ValidationError

from vespercode.audit.event import (
    AuditEventV1,
    AuditPayloadV1,
    CheckResultPayloadV1,
    LifecyclePayloadV1,
    RecoveryPayloadV1,
    StopEvidencePayloadV1,
)
from vespercode.audit.projection import (
    ProjectionValidationErrorV1,
    RunVisibilityV1,
    build_run_visibility,
)
from vespercode.canonical.timestamp_v1 import CanonicalTimestampV1
from vespercode.contracts.evidence import DigestV1
from vespercode.contracts.optional import AbsentV1, PresentV1
from vespercode.contracts.run import RunPhase, RunStatus, WaitContextV1
from vespercode.storage.run_repository import RunRecordV1

_CREATED_AT = CanonicalTimestampV1("2026-08-06T09:00:00.000Z")
_EARLIER_AT = CanonicalTimestampV1("2026-08-06T08:00:00.000Z")
_DEADLINE = CanonicalTimestampV1("2026-08-06T10:00:00.000Z")


def _run(run_id: str, status: str, phase: str | None) -> RunRecordV1:
    """One deterministic closed Run record value (no storage access)."""
    return RunRecordV1(
        run_id=run_id,
        workspace_identity="workspace-a",
        status=cast(RunStatus, status),
        phase=(
            PresentV1(kind="PRESENT", value=cast(RunPhase, phase))
            if phase is not None
            else AbsentV1(kind="ABSENT")
        ),
        config_snapshot_id="cfg-1",
        started_at=_CREATED_AT,
        run_deadline=_DEADLINE,
    )


def _event(
    run_id: str,
    sequence: int,
    payload: AuditPayloadV1,
) -> AuditEventV1:
    """One deterministic typed audit fact for the exact Run."""
    return AuditEventV1(
        run_id=run_id,
        sequence=sequence,
        event_type=payload.kind,
        redacted_payload=payload,
        created_at=_CREATED_AT,
    )


def _wait(
    run_id: str,
    wait_id: str,
    created_at: CanonicalTimestampV1,
) -> WaitContextV1:
    """One deterministic wait context for the exact Run."""
    return WaitContextV1(
        wait_id=wait_id,
        run_id=run_id,
        wait_kind="DISCLOSURE_GRANT",
        source_phase="AGENT_LOOP",
        subject_digest=DigestV1(value="a" * 64),
        created_at=created_at,
        expires_at=_DEADLINE,
    )


@pytest.fixture
def recovery_run() -> RunRecordV1:
    """The card RED fixture: one recorded RECOVERY_REQUIRED Run."""
    return _run("run-recovery", "RECOVERY_REQUIRED", None)


@pytest.fixture
def recovery_events() -> tuple[AuditEventV1, ...]:
    """The card RED fixture: unresolved recovery evidence plus stop evidence."""
    return (
        _event(
            "run-recovery",
            1,
            RecoveryPayloadV1(
                kind="RECOVERY",
                transaction_id="tx-1",
                disposition="UNRESOLVED",
            ),
        ),
        _event(
            "run-recovery",
            2,
            StopEvidencePayloadV1(
                kind="STOP_EVIDENCE",
                reason_code="PERSISTENCE_INCOMPLETE",
            ),
        ),
    )


def test_recovery_required_is_never_projected_as_stopped(
    recovery_run: RunRecordV1,
    recovery_events: tuple[AuditEventV1, ...],
) -> None:
    visibility = build_run_visibility(recovery_run, (), recovery_events)
    assert visibility.state_label == "RECOVERY_REQUIRED"
    assert visibility.next_action == "REVIEW_RECOVERY"


def test_audit_projection_lifecycle_matrix() -> None:
    """PLAN legacy-step matrix row 23.B: closed lifecycle projection."""
    # Every CREATED/RUNNING/terminal state projects exactly once.
    cases: tuple[tuple[str, str, str | None, str, str], ...] = (
        ("run-created", "CREATED", None, "CREATED", "START"),
        ("run-preflight", "RUNNING", "PREFLIGHT", "PREFLIGHT", "CONTINUE"),
        ("run-baseline", "RUNNING", "BASELINE", "BASELINE", "CONTINUE"),
        ("run-agent", "RUNNING", "AGENT_LOOP", "AGENT_LOOP", "CONTINUE"),
        ("run-formal", "RUNNING", "FORMAL_VALIDATION", "FORMAL_VALIDATION", "CONTINUE"),
        ("run-persist", "RUNNING", "PERSISTENCE", "PERSISTENCE", "CONTINUE"),
        ("run-succeeded", "SUCCEEDED", None, "SUCCEEDED", "RETRIEVE_EVIDENCE"),
        ("run-stopped", "STOPPED", None, "STOPPED", "REVIEW_STOP_REASON"),
    )
    for run_id, status, phase, label, next_action in cases:
        visibility = build_run_visibility(_run(run_id, status, phase), (), ())
        assert visibility.state_label == label
        assert visibility.next_action == next_action
        assert visibility.reason_code is not None
        assert visibility.run_id == run_id

    # Wait facts project WAITING_USER; a missing wait context is never
    # fabricated into a decision prompt.
    waiting = build_run_visibility(
        _run("run-wait", "WAITING_USER", None),
        (_wait("run-wait", "wait-1", _CREATED_AT),),
        (),
    )
    assert waiting.state_label == "WAITING_USER"
    assert waiting.next_action == "AWAIT_USER_DECISION"
    assert waiting.reason_code == "USER_DECISION_PENDING"
    missing = build_run_visibility(
        _run("run-wait-missing", "WAITING_USER", None), (), ()
    )
    assert missing.state_label == "WAITING_USER"
    assert missing.reason_code == "WAIT_CONTEXT_MISSING"

    # RECOVERY_REQUIRED takes precedence over STOPPED, and an unresolved
    # recovery reference overrides any recorded terminal state.
    status_only = build_run_visibility(
        _run("run-rec-status", "RECOVERY_REQUIRED", None), (), ()
    )
    assert status_only.state_label == "RECOVERY_REQUIRED"
    assert status_only.next_action == "REVIEW_RECOVERY"
    stopped_with_recovery = build_run_visibility(
        _run("run-stop-rec", "STOPPED", None),
        (),
        (
            _event(
                "run-stop-rec",
                1,
                RecoveryPayloadV1(
                    kind="RECOVERY",
                    transaction_id="tx-2",
                    disposition="UNRESOLVED",
                ),
            ),
        ),
    )
    assert stopped_with_recovery.state_label == "RECOVERY_REQUIRED"
    succeeded_with_recovery = build_run_visibility(
        _run("run-succ-rec", "SUCCEEDED", None),
        (),
        (
            _event(
                "run-succ-rec",
                1,
                RecoveryPayloadV1(
                    kind="RECOVERY",
                    transaction_id="tx-3",
                    disposition="UNRESOLVED",
                ),
            ),
        ),
    )
    assert succeeded_with_recovery.state_label == "RECOVERY_REQUIRED"
    resolved = build_run_visibility(
        _run("run-succ-resolved", "SUCCEEDED", None),
        (),
        (
            _event(
                "run-succ-resolved",
                1,
                RecoveryPayloadV1(
                    kind="RECOVERY",
                    transaction_id="tx-4",
                    disposition="COMMITTED",
                ),
            ),
        ),
    )
    assert resolved.state_label == "SUCCEEDED"

    # Impossible/missing phase is rejected at the closed RunRecordV1 type.
    with pytest.raises(ValidationError):
        _run("run-bad", "RUNNING", None)
    with pytest.raises(ValidationError):
        _run("run-bad", "CREATED", "PREFLIGHT")

    # Regressing revision, duplicate sequences, and cross-Run identity are
    # rejected before any mapping.
    stop = StopEvidencePayloadV1(kind="STOP_EVIDENCE", reason_code="TURN_LIMIT")
    with pytest.raises(ProjectionValidationErrorV1):
        build_run_visibility(
            _run("run-rev", "SUCCEEDED", None),
            (),
            (_event("run-rev", 2, stop), _event("run-rev", 1, stop)),
        )
    with pytest.raises(ProjectionValidationErrorV1):
        build_run_visibility(
            _run("run-dup", "SUCCEEDED", None),
            (),
            (_event("run-dup", 1, stop), _event("run-dup", 1, stop)),
        )
    with pytest.raises(ProjectionValidationErrorV1):
        build_run_visibility(
            _run("run-x", "SUCCEEDED", None),
            (),
            (_event("run-other", 1, stop),),
        )
    with pytest.raises(ProjectionValidationErrorV1):
        build_run_visibility(
            _run("run-x", "WAITING_USER", None),
            (_wait("run-other", "w-1", _CREATED_AT),),
            (),
        )
    with pytest.raises(ProjectionValidationErrorV1):
        build_run_visibility(
            _run("run-x", "WAITING_USER", None),
            (
                _wait("run-x", "w-1", _CREATED_AT),
                _wait("run-x", "w-2", _EARLIER_AT),
            ),
            (),
        )
    with pytest.raises(ProjectionValidationErrorV1):
        build_run_visibility(
            _run("run-x", "WAITING_USER", None),
            (
                _wait("run-x", "w-1", _CREATED_AT),
                _wait("run-x", "w-1", _CREATED_AT),
            ),
            (),
        )

    # Safe bounded evidence references from the most recent fact only;
    # internal rows and payload bodies are never exposed.
    evidenced = _event(
        "run-evid",
        1,
        CheckResultPayloadV1(
            kind="CHECK_RESULT",
            check_kind="TARGET_TESTS",
            status="FAIL",
            evidence_refs=("ref-1", "ref-2"),
        ),
    )
    visibility = build_run_visibility(
        _run("run-evid", "RUNNING", "AGENT_LOOP"), (), (evidenced,)
    )
    assert visibility.evidence_refs == ("ref-1", "ref-2")
    assert set(RunVisibilityV1.model_fields) == {
        "run_id",
        "state_label",
        "reason_code",
        "next_action",
        "evidence_refs",
    }
    with pytest.raises(ValidationError):
        visibility.state_label = "NOT_A_STATE"  # type: ignore[assignment]

    first = _event(
        "run-two",
        1,
        LifecyclePayloadV1(
            kind="LIFECYCLE",
            status="RUNNING",
            phase="PREFLIGHT",
            evidence_refs=("old-ref",),
        ),
    )
    second = _event(
        "run-two",
        2,
        LifecyclePayloadV1(
            kind="LIFECYCLE",
            status="RUNNING",
            phase="BASELINE",
            evidence_refs=("new-ref",),
        ),
    )
    two = build_run_visibility(
        _run("run-two", "RUNNING", "BASELINE"), (), (first, second)
    )
    assert two.evidence_refs == ("new-ref",)
    assert isinstance(two, RunVisibilityV1)

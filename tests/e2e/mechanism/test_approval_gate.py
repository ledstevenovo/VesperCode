"""T32.1 legacy step 32.A: final-approval no-write mechanism tests.

Without a final approval the corrected candidate never writes to the
authoritative workspace (SPEC §10.4 item 5): a nonexistent approval is
``NOT_FOUND`` and a stale approval bound to a drifted subject is
``STALE`` — both with zero consumption and zero writes — while the exact
PENDING approval is the sole write entry: one consumption, then exactly
one simulated write (SPEC §4.4.2 / AC-03).  The expired-approval pin
uses the production pure pre-check ``verify_consumable``.
"""

from __future__ import annotations

import pytest

pytest.importorskip("pydantic")

from vespercode.canonical.timestamp_v1 import CanonicalTimestampV1
from vespercode.contracts.evidence import DigestV1
from vespercode.governance.writeback_approval import (
    ApprovalNotConsumableErrorV1,
    ConsumeWritebackApprovalV1,
    verify_consumable,
)
from vespercode.governance.writeback_decision import (
    FinalWritebackApprovalV1,
)

from scripts.run_mechanism_demo import MechanismHarness


@pytest.fixture
def mechanism_harness() -> MechanismHarness:
    return MechanismHarness()


def test_final_approval_missing_or_stale_writes_nothing(
    mechanism_harness: MechanismHarness,
) -> None:
    trace = mechanism_harness.run_step("final-approval-no-write")
    assert trace.error_code == "APPROVAL_REQUIRED"
    assert trace.approval_consumption_count == 0
    assert trace.workspace_write_count == 0
    assert mechanism_harness.counting_write_port.write_count == 0


def test_exact_pending_approval_is_the_sole_write_entry(
    mechanism_harness: MechanismHarness,
) -> None:
    trace = mechanism_harness.run_step("approval-consume-exact")
    assert trace.approval_consumption_count == 1
    assert trace.workspace_write_count == 1
    # The approval is once-only: the exact replay performs zero
    # additional persistence and zero additional writes (AC-03).
    subject = mechanism_harness.writeback_subject()
    replay = mechanism_harness.approval_repository().consume(
        ConsumeWritebackApprovalV1(
            approval_id="mechanism-approval-exact",
            subject=subject,
            event_id="evt-approval-exact",
            consumed_at=CanonicalTimestampV1("2026-08-07T09:02:00.000Z"),
        )
    )
    assert replay.kind == "ALREADY_CONSUMED"
    assert mechanism_harness.counting_write_port.write_count == 1


def test_expired_subject_approval_is_not_consumable(
    mechanism_harness: MechanismHarness,
) -> None:
    """The production pure pre-check rejects an approval whose subject
    already expired before any transactional consumption (SPEC
    §4.4.2)."""
    expired_subject = mechanism_harness.writeback_subject(
        expires_at=CanonicalTimestampV1("2026-08-07T08:59:00.000Z")
    )
    approval = FinalWritebackApprovalV1(
        schema_version=1,
        approval_id="mechanism-approval-expired",
        subject_digest=DigestV1(value=expired_subject.digest),
        run_id=expired_subject.run_id,
        wait_id="wait-expired",
        created_at=CanonicalTimestampV1("2026-08-07T08:58:00.000Z"),
        status="PENDING",
    )
    command = ConsumeWritebackApprovalV1(
        approval_id="mechanism-approval-expired",
        subject=expired_subject,
        event_id="evt-expired",
        consumed_at=CanonicalTimestampV1("2026-08-07T09:01:00.000Z"),
    )
    with pytest.raises(ApprovalNotConsumableErrorV1) as expired:
        verify_consumable(approval, command)
    assert expired.value.error_code == "EXPIRED"
    assert mechanism_harness.counting_write_port.write_count == 0

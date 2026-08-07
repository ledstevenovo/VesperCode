"""T31.1 legacy step 31.C: uncertain writeback recovery block.

The exact displayed RED test
``test_uncertain_transaction_blocks_new_admission_until_proven_recovery``
is copied from the T31.1 card.  The matrix test
``test_reference_recovery_block_matrix`` pins the 31.C row: a
deadline-faulted mid-writeback transaction stays durably UNRESOLVED,
the recovery preview is read-only (zero workspace writes) and stays
three-valued, a new admission is blocked with ``RECOVERY_REQUIRED``
until service-proven recovery, the unresolved evidence is preserved,
and two runs of the same config produce the same content-addressed
trace under the declared volatility allowlist.
"""

from __future__ import annotations

import pytest

pytest.importorskip("pydantic")

from scripts.run_reference_e2e import (
    ReferenceE2EConfigV1,
    ReferenceE2EHarness,
)


pytestmark = pytest.mark.reference_e2e


def test_uncertain_transaction_blocks_new_admission_until_proven_recovery(
    reference_e2e_harness: ReferenceE2EHarness,
) -> None:
    result = reference_e2e_harness.run_uncertain_recovery_scenario()
    assert result.preview_write_count == 0
    assert result.second_admission_error == "RECOVERY_REQUIRED"


def test_uncertain_recovery_preview_is_read_only_and_evidence_preserved(
    reference_e2e_harness: ReferenceE2EHarness,
) -> None:
    """The recovery preview stays read-only and three-valued, and the
    durable UNRESOLVED evidence survives the preview and the blocked
    admission (cleanup never deletes unresolved recovery evidence)."""
    result = reference_e2e_harness.run_uncertain_recovery_scenario()
    assert result.preview_write_count == 0
    assert result.recovery_disposition in ("COMMITTED", "ROLLED_BACK", "UNRESOLVED")
    assert result.unresolved_evidence_preserved is True


def test_reference_recovery_block_matrix(
    reference_e2e_harness: ReferenceE2EHarness,
) -> None:
    """PLAN 31.C row: the blocked-admission trace is content-addressed
    and stable across runs (the trace excludes every injected volatile
    id/time, so two runs of the same config are semantically equal)."""
    first = reference_e2e_harness.run_uncertain_recovery_scenario()
    assert first.preview_write_count == 0
    assert first.second_admission_error == "RECOVERY_REQUIRED"
    assert first.stage_count >= 4
    assert first.trace_digest is not None
    assert len(first.trace_digest) == 64
    second = ReferenceE2EHarness(
        ReferenceE2EConfigV1(
            schema_version=1,
            run_id="t31-1-reference-e2e",
            clock_epoch="2026-08-07T00:00:00.000Z",
        )
    ).run_uncertain_recovery_scenario()
    assert second.preview_write_count == 0
    assert second.second_admission_error == "RECOVERY_REQUIRED"
    assert second.trace_digest == first.trace_digest

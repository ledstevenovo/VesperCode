"""T31.1 legacy step 31.A: reference E2E harness and happy path.

The exact displayed RED test
``test_reference_happy_path_reaches_verified_candidate`` is copied from
the T31.1 card.  The matrix test ``test_reference_success_matrix``
pins the 31.A row: the real Windows + Docker + Mock happy path reaches
a bound VerifiedCandidate and the final wait with zero workspace
writes.
"""

from __future__ import annotations

import pytest

pytest.importorskip("pydantic")

pytestmark = pytest.mark.reference_e2e

from scripts.run_reference_e2e import (
    ReferenceE2EConfigV1,
    ReferenceE2EHarness,
)


def test_reference_happy_path_reaches_verified_candidate(
    reference_e2e_harness: ReferenceE2EHarness,
) -> None:
    result = reference_e2e_harness.run_until_final_wait()
    assert result.verified_candidate_created is True
    assert result.workspace_write_count == 0


def test_reference_success_matrix(
    reference_e2e_harness: ReferenceE2EHarness,
) -> None:
    """PLAN 31.A row: happy path produces an ordered content-addressed
    trace whose stages are Baseline -> corrective loop -> formal
    validation -> VerifiedCandidate -> final wait, with zero workspace
    writes and zero residue."""
    result = reference_e2e_harness.run_until_final_wait()
    assert result.verified_candidate_created is True
    assert result.workspace_write_count == 0
    assert result.error_code is None
    assert result.stage_count >= 5
    assert result.trace_digest is not None
    assert len(result.trace_digest) == 64
    # Deterministic replay: the same config reproduces the same trace.
    second = ReferenceE2EHarness(
        ReferenceE2EConfigV1(
            schema_version=1,
            run_id="t31-1-reference-e2e",
            clock_epoch="2026-08-07T00:00:00.000Z",
        )
    ).run_until_final_wait()
    assert second.verified_candidate_created is True
    assert second.trace_digest == result.trace_digest

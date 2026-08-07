"""T31.1 legacy step 31.B: final-wait no-write branches.

The production happy path reaches the final wait after the bound
VerifiedCandidate; the final wait writes nothing to the workspace and
leaves zero residue.
"""

from __future__ import annotations

import pytest

pytest.importorskip("pydantic")

pytestmark = pytest.mark.reference_e2e

from scripts.run_reference_e2e import (
    ReferenceE2EConfigV1,
    ReferenceE2EHarness,
)


def test_final_wait_writes_nothing(
    reference_e2e_harness: ReferenceE2EHarness,
) -> None:
    result = reference_e2e_harness.run_final_wait_no_write_scenario()
    assert result.verified_candidate_created is True
    assert result.workspace_write_count == 0
    assert result.preview_write_count == 0


def test_final_wait_trace_is_stable(
    reference_e2e_harness: ReferenceE2EHarness,
) -> None:
    first = reference_e2e_harness.run_final_wait_no_write_scenario()
    assert first.verified_candidate_created is True
    assert first.trace_digest is not None
    second = ReferenceE2EHarness(
        ReferenceE2EConfigV1(
            schema_version=1,
            run_id="t31-1-reference-e2e",
            clock_epoch="2026-08-07T00:00:00.000Z",
        )
    ).run_final_wait_no_write_scenario()
    assert second.trace_digest == first.trace_digest

"""T31.1 legacy step 31.B: per-real-call credential fail-close.

The exact displayed RED test
``test_cleared_credential_has_zero_real_call_side_effects`` is copied
from the T31.1 card.  The matrix test ``test_reference_call_gate_matrix``
pins the 31.B row: every denial/wait/cursor/credential branch produces
the exact stable reason and zero forbidden side effects.
"""

from __future__ import annotations

import pytest

pytest.importorskip("pydantic")

from scripts.run_reference_e2e import (
    ReferenceE2EConfigV1,
    ReferenceE2EHarness,
)


pytestmark = pytest.mark.reference_e2e


def test_cleared_credential_has_zero_real_call_side_effects(
    reference_e2e_harness: ReferenceE2EHarness,
) -> None:
    result = reference_e2e_harness.run_cleared_credential_call_gate()
    assert result.error_code == "CREDENTIAL_MISSING"
    assert result.real_call_side_effect_counts == (0, 0, 0, 0, 0)


def test_reference_call_gate_matrix(
    reference_e2e_harness: ReferenceE2EHarness,
) -> None:
    """PLAN 31.B row: the cleared-credential real call aborts before
    Grant consumption, authorization, turn/call counts, byte charge,
    and transport; the trace is content-addressed and stable across
    runs."""
    first = reference_e2e_harness.run_cleared_credential_call_gate()
    assert first.error_code == "CREDENTIAL_MISSING"
    assert first.real_call_side_effect_counts == (0, 0, 0, 0, 0)
    assert first.stage_count >= 3
    assert first.trace_digest is not None
    assert len(first.trace_digest) == 64
    second = ReferenceE2EHarness(
        ReferenceE2EConfigV1(
            schema_version=1,
            run_id="t31-1-reference-e2e",
            clock_epoch="2026-08-07T00:00:00.000Z",
        )
    ).run_cleared_credential_call_gate()
    assert second.error_code == "CREDENTIAL_MISSING"
    assert second.trace_digest == first.trace_digest

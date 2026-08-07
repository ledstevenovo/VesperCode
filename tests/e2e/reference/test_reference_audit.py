"""T31.1 legacy step 31.C: redacted monotonic audit and retention cleanup.

The audit scenario drives the production ``AuditRepository`` over a
temporary control database: appends redact secrets away (a secret
payload is rejected with zero rows), per-Run sequences increase
monotonically, and the retention cleanup of an ended Run's audit
never deletes the durable unresolved recovery evidence (SPEC 4.7 /
AC-21).  The matrix test pins the 31.C audit row: the content
addressed trace is stable across two runs of the same config.
"""

from __future__ import annotations

import pytest

pytest.importorskip("pydantic")

from scripts.run_reference_e2e import (
    ReferenceE2EConfigV1,
    ReferenceE2EHarness,
)


pytestmark = pytest.mark.reference_e2e


def test_recovery_audit_is_redacted_monotonic_and_cleanup_preserves_evidence(
    reference_e2e_harness: ReferenceE2EHarness,
) -> None:
    result = reference_e2e_harness.run_recovery_audit_scenario()
    assert result.audit_event_count == 2
    assert result.audit_sequences_monotonic is True
    assert result.secret_payload_rejected is True
    assert result.audit_retention_cleared is True
    assert result.unresolved_evidence_preserved is True


def test_reference_audit_matrix(
    reference_e2e_harness: ReferenceE2EHarness,
) -> None:
    """PLAN 31.C audit row: the audit trace is content-addressed and
    stable across runs under the declared volatility allowlist."""
    first = reference_e2e_harness.run_recovery_audit_scenario()
    assert first.audit_event_count == 2
    assert first.audit_sequences_monotonic is True
    assert first.stage_count >= 5
    assert first.trace_digest is not None
    assert len(first.trace_digest) == 64
    second = ReferenceE2EHarness(
        ReferenceE2EConfigV1(
            schema_version=1,
            run_id="t31-1-reference-e2e",
            clock_epoch="2026-08-07T00:00:00.000Z",
        )
    ).run_recovery_audit_scenario()
    assert second.audit_event_count == 2
    assert second.trace_digest == first.trace_digest


def test_harness_never_writes_memory_evidence(
    reference_e2e_harness: ReferenceE2EHarness,
) -> None:
    """The reference terminal scenario fabricates no memory evidence:
    the control database's memory table stays empty (Tasks 22.A-22.C
    memory evidence is consumed by downstream tasks, not invented by
    the harness)."""
    result = reference_e2e_harness.run_recovery_audit_scenario()
    assert result.audit_event_count >= 2
    assert result.memory_entries == 0

"""T32.1 legacy step 32.C: credential recheck real-call gate tests.

Every real call re-probes and re-reads the sole credential store BEFORE
Grant consumption, authorization, turn/call counting, or transport
(SPEC §4.4.4/AC-13): a cleared/missing credential stops with the stable
``CREDENTIAL_MISSING`` code and an unsafe backend with
``CREDENTIAL_BACKEND_UNSAFE`` — both with zero consumption, record,
count, charge, transport, and network deltas.
"""

from __future__ import annotations

import pytest

pytest.importorskip("pydantic")

from scripts.run_mechanism_demo import MechanismHarness, RealCallProbeTraceV1


@pytest.fixture
def mechanism_harness() -> MechanismHarness:
    return MechanismHarness()


def _probe(harness: MechanismHarness, probe_id: str) -> RealCallProbeTraceV1:
    trace = harness.run_step("real-call-gate")
    probes = {probe.probe_id: probe for probe in trace.real_call_probes}
    return probes[probe_id]


def test_missing_or_cleared_credential_stops_before_every_side_effect(
    mechanism_harness: MechanismHarness,
) -> None:
    probe = _probe(mechanism_harness, "credential-missing")
    assert probe.gate_error_code == "CREDENTIAL_MISSING"
    assert (
        probe.authorization_record_count
        == probe.turn_count
        == probe.call_count
        == probe.charge_bytes
        == probe.transport_count
        == probe.network_count
        == 0
    )


def test_unsafe_backend_stops_before_every_side_effect(
    mechanism_harness: MechanismHarness,
) -> None:
    probe = _probe(mechanism_harness, "credential-backend-unsafe")
    assert probe.gate_error_code == "CREDENTIAL_BACKEND_UNSAFE"
    assert (
        probe.authorization_record_count
        == probe.turn_count
        == probe.call_count
        == probe.charge_bytes
        == probe.transport_count
        == probe.network_count
        == 0
    )


def test_credential_recheck_precedes_grant_consumption_and_counting(
    mechanism_harness: MechanismHarness,
) -> None:
    """The credential gate fires before the disclosure grant is
    consumed and before any turn/call counting: even a perfectly valid
    seeded grant stays untouched when the credential is missing or the
    backend is unsafe (SPEC §4.4.4 step 4 precedes step 5)."""
    trace = mechanism_harness.run_step("real-call-gate")
    probes = {probe.probe_id: probe for probe in trace.real_call_probes}
    for probe_id in ("credential-missing", "credential-backend-unsafe"):
        probe = probes[probe_id]
        assert probe.gate_error_code is not None
        assert probe.charge_bytes == 0
        assert probe.authorization_record_count == 0
        assert probe.turn_count == 0
        assert probe.call_count == 0
        assert probe.transport_count == 0
        assert probe.network_count == 0

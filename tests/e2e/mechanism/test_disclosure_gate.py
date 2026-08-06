"""T32.1 legacy step 32.C: disclosure real-call gate mechanism tests.

A real-call attempt without a valid DisclosureGrant stops before every
authorization, count, charge, transport, and network side effect (SPEC
§4.4.3/§10.4 item 6/AC-13): a nonexistent grant, an expired grant, and a
grant whose scope does not cover the request's source path each abort
with the production stable code and zero side effects, while the exact
authorized probe is the only path that passes the gate and performs
exactly one transport through the declared counting stub (zero real
network).
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


def test_missing_disclosure_stops_before_every_real_call_side_effect(
    mechanism_harness: MechanismHarness,
) -> None:
    probe = _probe(mechanism_harness, "missing-disclosure")
    # The production orchestrator maps a nonexistent grant to its closed
    # control-plane consistency code (the ledger outcome GRANT_NOT_FOUND
    # is a control-plane violation), and the gate stops before every
    # side effect (SPEC §10.4 item 6).
    assert probe.gate_error_code == "INTERNAL_ERROR"
    assert (
        probe.authorization_record_count
        == probe.turn_count
        == probe.call_count
        == probe.charge_bytes
        == probe.transport_count
        == probe.network_count
        == 0
    )


def test_expired_grant_stops_with_stable_code_and_zero_side_effects(
    mechanism_harness: MechanismHarness,
) -> None:
    probe = _probe(mechanism_harness, "grant-expired")
    assert probe.gate_error_code == "DISCLOSURE_GRANT_EXPIRED"
    assert (
        probe.authorization_record_count
        == probe.turn_count
        == probe.call_count
        == probe.charge_bytes
        == probe.transport_count
        == probe.network_count
        == 0
    )


def test_scope_exceeded_grant_stops_with_stable_code_and_zero_side_effects(
    mechanism_harness: MechanismHarness,
) -> None:
    probe = _probe(mechanism_harness, "scope-exceeded")
    assert probe.gate_error_code == "DISCLOSURE_SCOPE_EXCEEDED"
    assert (
        probe.authorization_record_count
        == probe.turn_count
        == probe.call_count
        == probe.charge_bytes
        == probe.transport_count
        == probe.network_count
        == 0
    )


def test_authorized_probe_is_the_only_path_past_the_gate(
    mechanism_harness: MechanismHarness,
) -> None:
    probe = _probe(mechanism_harness, "authorized")
    assert probe.gate_error_code is None
    assert probe.authorization_record_count == 1
    assert probe.turn_count == 1
    assert probe.call_count == 1
    assert probe.charge_bytes > 0
    assert probe.transport_count == 1
    # The declared counting stub is the only adapter: zero real network.
    assert probe.network_count == 0


def test_failing_disclosure_probes_precede_the_authorized_probe_in_order(
    mechanism_harness: MechanismHarness,
) -> None:
    trace = mechanism_harness.run_step("real-call-gate")
    assert [probe.probe_id for probe in trace.real_call_probes] == [
        "missing-disclosure",
        "grant-expired",
        "scope-exceeded",
        "credential-missing",
        "credential-backend-unsafe",
        "authorized",
    ]
    for probe in trace.real_call_probes[:-1]:
        assert probe.gate_error_code is not None
        assert probe.authorization_record_count == 0
        assert probe.transport_count == 0
        assert probe.network_count == 0

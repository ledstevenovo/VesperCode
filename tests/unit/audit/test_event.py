"""T23.1 legacy step 23.A: closed redacted event vocabulary tests.

Pins the closed event-type allowlist, the immutable ``AuditEventV1``
value shape, the closed bounded payload variants (extra-field, literal,
length, and evidence-reference rejections), the redact-and-minimize
function (allowlisted keys per event type, forbidden
body/secret/request/response fields, missing/empty/over-limit/secret
values, evidence-reference bounds, invalid closed facts), and the
canonical payload storage round-trip.  Storage, sequencing, projection,
and retention stay out of scope (GREEN-4).
"""

from __future__ import annotations

from typing import cast

import pytest

# The vocabulary consumes pydantic runtime contracts; the hash-locked
# gate toolchain installs no runtime dependencies, so this module skips
# cleanly there (formal env runs it fully).
pytest.importorskip("pydantic")

from pydantic import ValidationError

from vespercode.audit.event import (
    ActionPayloadV1,
    AuditEventTypeV1,
    AuditEventV1,
    AuditPayloadErrorV1,
    LifecyclePayloadV1,
    LLMCallPayloadV1,
    RecoveryPayloadV1,
    StopEvidencePayloadV1,
    parse_payload,
    redact_payload,
    serialize_payload,
)
from vespercode.canonical.timestamp_v1 import CanonicalTimestampV1

_CREATED_AT = CanonicalTimestampV1("2026-08-06T09:00:00.000Z")

_BOUNDED_PAYLOAD: dict[str, dict[str, str]] = {
    "LIFECYCLE": {"status": "RUNNING", "phase": "PREFLIGHT"},
    "ACTION": {"action_type": "read_file", "policy_decision": "ALLOW"},
    "POLICY_DECISION": {"decision": "DENY", "reason_code": "PATCH_PATH_NOT_EDITABLE"},
    "FINAL_WRITEBACK_APPROVAL": {"approval_id": "approval-1", "status": "APPROVED"},
    "DISCLOSURE_GRANT": {"grant_id": "grant-1", "status": "ACTIVE"},
    "DISCLOSURE_AUTHORIZATION": {"category": "FILE", "byte_count": "1024"},
    "CHECK_RESULT": {"check_kind": "TARGET_TESTS", "status": "PASS"},
    "RECOVERY": {"transaction_id": "tx-1", "disposition": "COMMITTED"},
    "STOP_EVIDENCE": {"reason_code": "TURN_LIMIT"},
    "LLM_CALL": {"outcome": "COMPLETED"},
}


def _call() -> LLMCallPayloadV1:
    return LLMCallPayloadV1(kind="LLM_CALL", outcome="COMPLETED")


def test_audit_event_is_closed_and_immutable() -> None:
    event = AuditEventV1(
        run_id="run-1",
        sequence=1,
        event_type="LLM_CALL",
        redacted_payload=_call(),
        created_at=_CREATED_AT,
    )
    assert event.run_id == "run-1"
    assert event.sequence == 1
    assert event.event_type == "LLM_CALL"
    assert isinstance(event.redacted_payload, LLMCallPayloadV1)
    assert event.redacted_payload.outcome == "COMPLETED"
    assert event.created_at == _CREATED_AT
    with pytest.raises(ValidationError):
        event.sequence = "2"  # type: ignore[assignment]
    with pytest.raises(ValidationError):
        AuditEventV1(
            run_id="",
            sequence=1,
            event_type="LLM_CALL",
            redacted_payload=_call(),
            created_at=_CREATED_AT,
        )
    with pytest.raises(ValidationError):
        AuditEventV1(
            run_id="run-1",
            sequence=0,
            event_type="LLM_CALL",
            redacted_payload=_call(),
            created_at=_CREATED_AT,
        )
    with pytest.raises(ValidationError):
        AuditEventV1(
            run_id="run-1",
            sequence=1,
            event_type="MODEL_OUTPUT",  # type: ignore[arg-type]
            redacted_payload=_call(),
            created_at=_CREATED_AT,
        )
    with pytest.raises(ValidationError):
        AuditEventV1(
            run_id="run-1",
            sequence=1,
            event_type="LLM_CALL",
            redacted_payload=_call(),
            created_at=_CREATED_AT,
            extra_field="x",  # type: ignore[call-arg]
        )


def test_event_type_must_equal_the_payload_kind() -> None:
    # A Recovery payload smuggled under a non-RECOVERY event type (or any
    # other type/kind mismatch) never constructs: the event type must
    # equal the redacted payload kind, so recovery facts can never be
    # hidden behind a forged type.
    with pytest.raises(ValidationError):
        AuditEventV1(
            run_id="run-1",
            sequence=1,
            event_type="ACTION",
            redacted_payload=_call(),
            created_at=_CREATED_AT,
        )


def test_payload_variants_are_closed_and_bounded() -> None:
    # Extra fields, unknown literals, and over-limit values never parse.
    with pytest.raises(ValidationError):
        LLMCallPayloadV1(
            kind="LLM_CALL",  # type: ignore[call-arg]
            outcome="COMPLETED",
            request_body="source text",
        )
    with pytest.raises(ValidationError):
        LLMCallPayloadV1(
            kind="LLM_CALL",
            outcome="PENDING",  # type: ignore[arg-type]
        )
    with pytest.raises(ValidationError):
        ActionPayloadV1(kind="ACTION", action_type="x" * 65, policy_decision="ALLOW")
    with pytest.raises(ValidationError):
        RecoveryPayloadV1(
            kind="RECOVERY",
            transaction_id="tx-1",
            disposition="UNKNOWN",  # type: ignore[arg-type]
        )
    with pytest.raises(ValidationError):
        LifecyclePayloadV1(
            kind="LIFECYCLE",
            status="PAUSED",  # type: ignore[arg-type]
        )
    # Evidence references are bounded, non-empty, and secret-free.
    with pytest.raises(ValidationError):
        LifecyclePayloadV1(
            kind="LIFECYCLE",
            status="RUNNING",
            phase="PREFLIGHT",
            evidence_refs=("ref",) * 9,
        )
    with pytest.raises(ValidationError):
        LifecyclePayloadV1(
            kind="LIFECYCLE",
            status="RUNNING",
            phase="PREFLIGHT",
            evidence_refs=("x" * 129,),
        )
    with pytest.raises(ValidationError):
        LifecyclePayloadV1(
            kind="LIFECYCLE",
            status="RUNNING",
            phase="PREFLIGHT",
            evidence_refs=("",),
        )
    with pytest.raises(ValidationError):
        LifecyclePayloadV1(
            kind="LIFECYCLE",
            status="RUNNING",
            phase="PREFLIGHT",
            evidence_refs=("rotate " + "API_KEY" + "=sk-1",),
        )
    bounded = LifecyclePayloadV1(
        kind="LIFECYCLE",
        status="RUNNING",
        phase="PREFLIGHT",
        evidence_refs=("ref-1",),
    )
    assert bounded.evidence_refs == ("ref-1",)


def test_redact_payload_accepts_only_bounded_allowlisted_facts() -> None:
    for event_type, payload in _BOUNDED_PAYLOAD.items():
        redacted = redact_payload(cast(AuditEventTypeV1, event_type), payload)
        assert redacted.kind == event_type
    # The optional lifecycle phase may be absent.
    no_phase = redact_payload("LIFECYCLE", {"status": "RUNNING"})
    assert isinstance(no_phase, LifecyclePayloadV1)
    assert no_phase.phase is None
    redacted = redact_payload(
        "LLM_CALL", {"outcome": "COMPLETED"}, evidence_refs=("ref-1", "ref-2")
    )
    assert redacted.evidence_refs == ("ref-1", "ref-2")


def test_redact_payload_rejects_forbidden_fields_and_values() -> None:
    for key in (
        "request_body",
        "api_key",
        "response_body",
        "raw_output",
        "output",
        "secret",
        "token",
        "request",
        "response",
        "body",
        "content",
        "stdout",
        "stderr",
        "prompt",
        "completion",
        "messages",
        "authorization",
        "credentials",
        "password",
    ):
        with pytest.raises(AuditPayloadErrorV1):
            redact_payload("LLM_CALL", {key: "inert-sentinel"})
    # A key that is not allowlisted for this event type is rejected.
    with pytest.raises(AuditPayloadErrorV1):
        redact_payload("LIFECYCLE", {"outcome": "COMPLETED"})
    with pytest.raises(AuditPayloadErrorV1):
        redact_payload("LLM_CALL", {"random_field": "x"})
    # Missing required fields, empty/over-limit values, secrets, and invalid
    # closed facts are all rejected with the stable closed error.
    with pytest.raises(AuditPayloadErrorV1):
        redact_payload("LLM_CALL", {})
    with pytest.raises(AuditPayloadErrorV1):
        redact_payload("LLM_CALL", {"outcome": ""})
    with pytest.raises(AuditPayloadErrorV1):
        redact_payload("LLM_CALL", {"outcome": "x" * 513})
    with pytest.raises(AuditPayloadErrorV1):
        redact_payload("LLM_CALL", {"outcome": "rotate " + "API_KEY" + "=sk-1"})
    with pytest.raises(AuditPayloadErrorV1):
        redact_payload("LLM_CALL", {"outcome": "PENDING"})
    # Lone surrogates (accepted by StrictStr) fail closed with the
    # canonical-encoding rejection instead of leaking raw exceptions.
    with pytest.raises(AuditPayloadErrorV1):
        redact_payload("LLM_CALL", {"outcome": "\ud800"})
    # Evidence-reference violations fail closed as well.
    with pytest.raises(AuditPayloadErrorV1):
        redact_payload("LLM_CALL", {"outcome": "COMPLETED"}, evidence_refs=("r",) * 9)
    with pytest.raises(AuditPayloadErrorV1):
        redact_payload("LLM_CALL", {"outcome": "COMPLETED"}, evidence_refs=("x" * 129,))
    with pytest.raises(AuditPayloadErrorV1):
        redact_payload("LLM_CALL", {"outcome": "COMPLETED"}, evidence_refs=("",))
    with pytest.raises(AuditPayloadErrorV1):
        redact_payload("LLM_CALL", {"outcome": "COMPLETED"}, evidence_refs=("\udfff",))


def test_payload_storage_round_trip_is_canonical() -> None:
    for event_type, payload in _BOUNDED_PAYLOAD.items():
        redacted = redact_payload(
            cast(AuditEventTypeV1, event_type), payload, ("ref-1",)
        )
        text = serialize_payload(redacted)
        parsed = parse_payload(text)
        assert parsed == redacted
        assert serialize_payload(parsed) == text
    # The optional absent phase is omitted (SPEC 0.1 has no null value) and
    # parses back to the same closed variant.
    no_phase = redact_payload("LIFECYCLE", {"status": "RUNNING"})
    assert isinstance(no_phase, LifecyclePayloadV1)
    storage_text = serialize_payload(no_phase)
    assert '"phase"' not in storage_text
    parsed_no_phase = parse_payload(storage_text)
    assert isinstance(parsed_no_phase, LifecyclePayloadV1)
    assert parsed_no_phase.phase is None
    # Unknown stored kinds fail closed.
    with pytest.raises(ValueError):
        parse_payload('{"kind": "MODEL_OUTPUT"}')
    with pytest.raises(ValueError):
        parse_payload('["LIFECYCLE"]')
    # The stored variant is the exact bounded value, never the raw input.
    stored = serialize_payload(
        StopEvidencePayloadV1(kind="STOP_EVIDENCE", reason_code="TURN_LIMIT")
    )
    assert "request_body" not in stored
    assert "api_key" not in stored
    assert parse_payload(stored) == StopEvidencePayloadV1(
        kind="STOP_EVIDENCE", reason_code="TURN_LIMIT"
    )

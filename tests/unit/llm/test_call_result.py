"""T16.1 legacy step 16.A: closed ``LLMCallResultV1`` status combination tests.

Pins every closed combination of SPEC §4.4.4: Mock results bind
``authorization_record_ref=ABSENT`` and never ``DELIVERY_UNKNOWN``; OpenAI
results bind a PRESENT authorization record; ``SUCCEEDED`` requires a
PRESENT response digest with an ABSENT error and every other status
requires the exact reverse.  Also pins the closed ref/digest/error forms
(64-hex response digest, bounded ids and stable error codes), unknown/
missing/type-confused fields, and frozen immutability.  Construction of a
result from a response or adapter failure belongs to Task 25.C; this
module owns only the closed contract (GREEN-4).
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Literal

import pytest

# The closed result contract consumes pydantic runtime contracts; the
# hash-locked gate toolchain installs no runtime dependencies, so this
# module skips cleanly there (formal env runs it fully).
pytest.importorskip("pydantic")

from pydantic import ValidationError

from vespercode.contracts.optional import AbsentV1
from vespercode.governance.request_sources import (
    RequestContentSegmentV1,
    RequestMessageV1,
)
from vespercode.llm.call_result import (
    LLMCallResultV1,
    PresentAuthorizationRecordRefV1,
    PresentLLMCallErrorV1,
    PresentResponseDigestV1,
)
from vespercode.llm.prepared_request import prepare_mock_request
from vespercode.profiles.llm import MockLLMProfileV1, load_llm_profile

_MOCK_BUILTIN = (
    Path(__file__).resolve().parents[3]
    / "src/vespercode/profiles/builtin/mock-deterministic-v1.json"
)
_PROFILE_DIGEST = "3fd39f821cae060b3bd0b382bfcd4843cbb465269b1487200582d4bb4346e4a9"
_REQUEST_DIGEST = "a" * 64
_RESPONSE_DIGEST = "b" * 64


def mock_profile() -> MockLLMProfileV1:
    """The frozen packaged built-in Mock profile (digest-verified)."""
    loaded = load_llm_profile(_MOCK_BUILTIN.read_bytes())
    assert isinstance(loaded, MockLLMProfileV1)
    return loaded


def _typed_messages() -> tuple[RequestMessageV1, ...]:
    """A minimal valid message sequence for one Mock request."""
    return (
        RequestMessageV1(
            role="SYSTEM",
            segments=(
                RequestContentSegmentV1(
                    source_category="HARNESS_PROTOCOL",
                    source_path=AbsentV1(kind="ABSENT"),
                    content="VesperCode v1 protocol.",
                    content_digest=hashlib.sha256(
                        b"VesperCode v1 protocol."
                    ).hexdigest(),
                    byte_count=len(b"VesperCode v1 protocol."),
                ),
            ),
        ),
    )


def _mock_request_digest() -> str:
    """The digest of one real prepared Mock request (identity-bound)."""
    return prepare_mock_request(mock_profile(), _typed_messages()).digest


def _mock_result(
    *,
    status: Literal[
        "NOT_ATTEMPTED", "SUCCEEDED", "FAILED", "DELIVERY_UNKNOWN"
    ] = "SUCCEEDED",
    response_digest: str | None = "b" * 64,
    error_code: str | None = None,
) -> LLMCallResultV1:
    """One closed Mock result; override status/digest/error as needed."""
    response = (
        AbsentV1(kind="ABSENT")
        if response_digest is None
        else PresentResponseDigestV1(kind="PRESENT", value=response_digest)
    )
    error = (
        AbsentV1(kind="ABSENT")
        if error_code is None
        else PresentLLMCallErrorV1(kind="PRESENT", stable_error_code=error_code)
    )
    return LLMCallResultV1(
        schema_version=1,
        mode="MOCK",
        llm_profile_digest=_PROFILE_DIGEST,
        request_digest=_mock_request_digest(),
        authorization_record_ref=AbsentV1(kind="ABSENT"),
        status=status,
        response_digest=response,
        error=error,
    )


def test_profile_digest_binds_the_packaged_profile() -> None:
    """The pinned profile digest is the frozen packaged Mock identity."""
    assert _PROFILE_DIGEST == mock_profile().digest


def test_mock_succeeded_requires_present_response_and_absent_error() -> None:
    result = _mock_result()
    assert result.status == "SUCCEEDED"
    assert result.response_digest.kind == "PRESENT"
    assert result.error.kind == "ABSENT"
    # Missing response digest with SUCCEEDED rejects.
    with pytest.raises(ValidationError):
        _mock_result(response_digest=None)
    # Error present with SUCCEEDED rejects.
    with pytest.raises(ValidationError):
        _mock_result(error_code="LLM_CALL_FAILED")


def test_mock_failed_requires_present_error_and_absent_response() -> None:
    result = _mock_result(
        status="FAILED", response_digest=None, error_code="LLM_CALL_FAILED"
    )
    assert result.status == "FAILED"
    assert result.response_digest.kind == "ABSENT"
    assert result.error.kind == "PRESENT"
    with pytest.raises(ValidationError):
        _mock_result(status="FAILED", error_code="LLM_CALL_FAILED")
    with pytest.raises(ValidationError):
        _mock_result(status="FAILED", response_digest=None)


def test_mock_result_rejects_authorization_record_ref_and_delivery_unknown() -> None:
    with pytest.raises(ValidationError):
        LLMCallResultV1(
            schema_version=1,
            mode="MOCK",
            llm_profile_digest=_PROFILE_DIGEST,
            request_digest=_mock_request_digest(),
            authorization_record_ref=PresentAuthorizationRecordRefV1(
                kind="PRESENT", authorization_record_id="authz-1"
            ),
            status="SUCCEEDED",
            response_digest=PresentResponseDigestV1(
                kind="PRESENT", value=_RESPONSE_DIGEST
            ),
            error=AbsentV1(kind="ABSENT"),
        )
    with pytest.raises(ValidationError):
        _mock_result(status="DELIVERY_UNKNOWN", error_code="LLM_CALL_FAILED")


def test_openai_result_requires_present_authorization_record() -> None:
    openai_digest = "c" * 64
    valid = LLMCallResultV1(
        schema_version=1,
        mode="OPENAI",
        llm_profile_digest="cb46690ef08202e120b71823d3de8ae1c31c903af6b0129984a9a4e893dd3f9c",
        request_digest=openai_digest,
        authorization_record_ref=PresentAuthorizationRecordRefV1(
            kind="PRESENT", authorization_record_id="authz-1"
        ),
        status="FAILED",
        response_digest=AbsentV1(kind="ABSENT"),
        error=PresentLLMCallErrorV1(
            kind="PRESENT", stable_error_code="LLM_CALL_FAILED"
        ),
    )
    assert valid.mode == "OPENAI"
    with pytest.raises(ValidationError):
        LLMCallResultV1(
            schema_version=1,
            mode="OPENAI",
            llm_profile_digest="cb46690ef08202e120b71823d3de8ae1c31c903af6b0129984a9a4e893dd3f9c",
            request_digest=openai_digest,
            authorization_record_ref=AbsentV1(kind="ABSENT"),
            status="FAILED",
            response_digest=AbsentV1(kind="ABSENT"),
            error=PresentLLMCallErrorV1(
                kind="PRESENT", stable_error_code="LLM_CALL_FAILED"
            ),
        )
    # OpenAI may use DELIVERY_UNKNOWN (unlike Mock).
    unknown = LLMCallResultV1(
        schema_version=1,
        mode="OPENAI",
        llm_profile_digest="cb46690ef08202e120b71823d3de8ae1c31c903af6b0129984a9a4e893dd3f9c",
        request_digest=openai_digest,
        authorization_record_ref=PresentAuthorizationRecordRefV1(
            kind="PRESENT", authorization_record_id="authz-1"
        ),
        status="DELIVERY_UNKNOWN",
        response_digest=AbsentV1(kind="ABSENT"),
        error=PresentLLMCallErrorV1(
            kind="PRESENT", stable_error_code="LLM_CALL_FAILED"
        ),
    )
    assert unknown.status == "DELIVERY_UNKNOWN"


def test_closed_forms_reject_boundary_spellings() -> None:
    # Response digest must be exactly 64 lowercase hex.
    for bad_digest in ("0" * 63, "0" * 65, "A" * 64, "x" * 64, ""):
        with pytest.raises(ValidationError):
            _mock_result(response_digest=bad_digest)
    # Empty and oversized authorization-record ids reject.
    with pytest.raises(ValidationError):
        LLMCallResultV1(
            schema_version=1,
            mode="OPENAI",
            llm_profile_digest="cb46690ef08202e120b71823d3de8ae1c31c903af6b0129984a9a4e893dd3f9c",
            request_digest="c" * 64,
            authorization_record_ref=PresentAuthorizationRecordRefV1(
                kind="PRESENT", authorization_record_id=""
            ),
            status="FAILED",
            response_digest=AbsentV1(kind="ABSENT"),
            error=PresentLLMCallErrorV1(
                kind="PRESENT", stable_error_code="LLM_CALL_FAILED"
            ),
        )
    # Empty and oversized stable error codes reject.
    with pytest.raises(ValidationError):
        _mock_result(status="FAILED", error_code="")
    with pytest.raises(ValidationError):
        _mock_result(status="FAILED", error_code="E" * 65)


def test_result_rejects_unknown_missing_and_type_confused_fields() -> None:
    valid = _mock_result()
    with pytest.raises(ValidationError):
        LLMCallResultV1.model_validate(
            {
                **valid.model_dump(),
                "extra": 1,
            }
        )
    with pytest.raises(ValidationError):
        LLMCallResultV1.model_validate(valid.model_dump() | {"status": "PENDING"})
    for missing in ("mode", "llm_profile_digest", "request_digest", "status"):
        dropped = valid.model_dump()
        del dropped[missing]
        with pytest.raises(ValidationError):
            LLMCallResultV1.model_validate(dropped)
    with pytest.raises(ValidationError):
        LLMCallResultV1.model_validate(valid.model_dump() | {"schema_version": True})
    with pytest.raises(ValidationError):
        LLMCallResultV1.model_validate(valid.model_dump() | {"schema_version": "1"})


def test_result_is_frozen_and_body_free() -> None:
    result = _mock_result()
    with pytest.raises(ValidationError):
        setattr(result, "status", "FAILED")
    dumped = result.model_dump()
    # The result carries only digest/ref facts, never response text.
    assert "text" not in dumped
    assert "content" not in dumped
    assert dumped["request_digest"] == _mock_request_digest()

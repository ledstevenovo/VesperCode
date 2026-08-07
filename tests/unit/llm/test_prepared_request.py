"""T16.1 legacy step 16.A: closed Mock/OpenAI prepared-request contracts.

Pins the mutually exclusive prepared-request variants (the Mock variant
never carries OpenAI transport fields and the OpenAI variant never carries
Mock script fields), the exact §0.1 request digests and mode-specific
``canonical_byte_count`` (Mock = the canonical ``MockAdapterPayloadV1``
byte length; OpenAI = the serializer's final UTF-8 request-body byte
length), the frozen-profile binding of every mode-specific field, the
source/path/byte identity contract, and the closed call-result status
combinations (Mock must bind ``authorization_record_ref=ABSENT`` and never
``DELIVERY_UNKNOWN``; ``SUCCEEDED`` requires a PRESENT response digest and
an ABSENT error).  ``test_prepared_request_profile_matrix`` implements the
operative 16.A matrix row (PLAN Registry line 11389): "Mock request/result
excludes OpenAI transport fields; OpenAI request/result excludes Mock
fields; malformed response, cross-mode field, unknown endpoint, or extra
field is rejected."  Provider transport, credentials, Grant/authorization
access, request charging, and network clients remain out of scope
(GREEN-4).
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Literal

import pytest

# The closed request contracts consume pydantic runtime contracts; the
# hash-locked gate toolchain installs no runtime dependencies, so this
# module skips cleanly there (formal env runs it fully).
pytest.importorskip("pydantic")

from pydantic import ValidationError

from vespercode.canonical.digest import domain_digest
from vespercode.canonical.json_v1 import CanonicalValueV1, canonical_json_bytes
from vespercode.canonical.path_v1 import CanonicalRelativePathV1
from vespercode.contracts.optional import AbsentV1, PresentV1
from vespercode.governance.request_sources import (
    RequestContentSegmentV1,
    RequestMessageV1,
)
from vespercode.llm.base import ModelResponse
from vespercode.llm.call_result import (
    LLMCallResultV1,
    PresentAuthorizationRecordRefV1,
    PresentLLMCallErrorV1,
    PresentResponseDigestV1,
)
from vespercode.llm.mock_adapter import MockLLMAdapter, MockScriptMismatchError
from vespercode.llm.prepared_request import (
    MockPreparedModelRequestV1,
    OpenAIPreparedModelRequestV1,
    prepare_mock_request,
    prepare_openai_request,
)
from vespercode.profiles.llm import (
    MockLLMProfileV1,
    OpenAILLMProfileV1,
    load_llm_profile,
)

_MOCK_BUILTIN = (
    Path(__file__).resolve().parents[3]
    / "src/vespercode/profiles/builtin/mock-deterministic-v1.json"
)
_OPENAI_BUILTIN = (
    Path(__file__).resolve().parents[3]
    / "src/vespercode/profiles/builtin/openai-single-turn-v1.json"
)
_MOCK_SCRIPT_ID = "mock-deterministic-response-v1"
_MOCK_SCRIPT_DIGEST = "3be1c2165c5cf2e4d271a489809e1a7c443fcf452b66bb9a743022ee4f0894da"


def mock_profile() -> MockLLMProfileV1:
    """The frozen packaged built-in Mock profile (digest-verified)."""
    loaded = load_llm_profile(_MOCK_BUILTIN.read_bytes())
    assert isinstance(loaded, MockLLMProfileV1)
    return loaded


def openai_profile() -> OpenAILLMProfileV1:
    """The frozen packaged built-in OpenAI profile (digest-verified)."""
    loaded = load_llm_profile(_OPENAI_BUILTIN.read_bytes())
    assert isinstance(loaded, OpenAILLMProfileV1)
    return loaded


# ---------------------------------------------------------------------------
# Independent canonical forms (public canonical API only; the request
# contract binds exactly these byte shapes, recomputed here in the test so
# the implementation cannot silently drift from the §0.1 identity).
# ---------------------------------------------------------------------------


def _segment_canonical(
    segment: RequestContentSegmentV1,
) -> dict[str, CanonicalValueV1]:
    """One segment in the canonical payload/digest value shape (§4.4.4)."""
    source_path: CanonicalValueV1
    if segment.source_path.kind == "ABSENT":
        source_path = {"kind": "ABSENT"}
    else:
        source_path = {"kind": "PRESENT", "value": segment.source_path.value.value}
    return {
        "source_category": segment.source_category,
        "source_path": source_path,
        "content": segment.content,
        "content_digest": segment.content_digest,
        "byte_count": segment.byte_count,
    }


def _messages_canonical(
    messages: tuple[RequestMessageV1, ...],
) -> tuple[dict[str, CanonicalValueV1], ...]:
    """The ordered messages in canonical digest shape (segment order kept)."""
    return tuple(
        {
            "role": message.role,
            "segments": tuple(_segment_canonical(seg) for seg in message.segments),
        }
        for message in messages
    )


def _mock_payload_canonical(
    script_id: str,
    script_digest: str,
    messages: tuple[RequestMessageV1, ...],
) -> dict[str, CanonicalValueV1]:
    """The canonical ``MockAdapterPayloadV1`` value (SPEC §4.4.4)."""
    return {
        "schema_version": 1,
        "script_id": script_id,
        "script_digest": script_digest,
        "messages": _messages_canonical(messages),
    }


def _segment(
    category: Literal[
        "HARNESS_PROTOCOL", "TASK", "FILE_CONTENT", "TOOL_RESULT", "MEMORY", "FEEDBACK"
    ],
    content: str,
    *,
    path: str | None = None,
) -> RequestContentSegmentV1:
    """One closed segment with the exact content digest and bytes."""
    raw = content.encode("utf-8")
    source_path = (
        AbsentV1(kind="ABSENT")
        if path is None
        else PresentV1(kind="PRESENT", value=CanonicalRelativePathV1(path))
    )
    return RequestContentSegmentV1(
        source_category=category,
        source_path=source_path,
        content=content,
        content_digest=hashlib.sha256(raw).hexdigest(),
        byte_count=len(raw),
    )


def _message(
    role: Literal["SYSTEM", "USER"], *segments: RequestContentSegmentV1
) -> RequestMessageV1:
    """One ordered request message."""
    return RequestMessageV1(role=role, segments=segments)


def _mock_messages() -> tuple[RequestMessageV1, ...]:
    """A small closed two-message sequence exercising both path shapes."""
    return (
        _message("SYSTEM", _segment("HARNESS_PROTOCOL", "VesperCode v1 protocol.")),
        _message(
            "USER",
            _segment("TASK", "Fix the failing test."),
            _segment(
                "FILE_CONTENT",
                "def example():\n    return 0\n",
                path="src/example.py",
            ),
        ),
    )


def valid_mock_request(
    *,
    script_id: str = _MOCK_SCRIPT_ID,
    script_digest: str = _MOCK_SCRIPT_DIGEST,
    messages: tuple[RequestMessageV1, ...] | None = None,
) -> dict[str, object]:
    """One digest-consistent Mock prepared-request dict (SPEC §4.4.4)."""
    profile = mock_profile()
    final_messages = _mock_messages() if messages is None else messages
    payload = _mock_payload_canonical(script_id, script_digest, final_messages)
    canonical_byte_count = len(canonical_json_bytes(payload))
    digest = domain_digest(
        "MockPreparedModelRequestV1",
        1,
        {
            "schema_version": 1,
            "mode": "MOCK",
            "llm_profile_digest": profile.digest,
            "script_id": script_id,
            "script_digest": script_digest,
            "messages": _messages_canonical(final_messages),
            "canonical_byte_count": canonical_byte_count,
        },
    )
    return {
        "schema_version": 1,
        "mode": "MOCK",
        "llm_profile_digest": profile.digest,
        "script_id": script_id,
        "script_digest": script_digest,
        "messages": final_messages,
        "canonical_byte_count": canonical_byte_count,
        "digest": digest,
    }


def _openai_body_dict(
    *,
    model: str,
    messages: tuple[RequestMessageV1, ...],
    max_output_tokens: int,
    temperature_milli: int | None = None,
    top_p_milli: int | None = None,
    seed: int | None = None,
) -> dict[str, object]:
    """The serializer's exact vendor body dict (segment contents joined)."""
    body_messages: list[dict[str, object]] = []
    for message in messages:
        content = "".join(seg.content for seg in message.segments)
        body_messages.append(
            {
                "role": "system" if message.role == "SYSTEM" else "user",
                "content": content,
            }
        )
    body: dict[str, object] = {
        "model": model,
        "messages": tuple(body_messages),
        "max_output_tokens": max_output_tokens,
    }
    if temperature_milli is not None:
        body["temperature"] = temperature_milli / 1000
    if top_p_milli is not None:
        body["top_p"] = top_p_milli / 1000
    if seed is not None:
        body["seed"] = seed
    body["response_format"] = {"type": "json_object"}
    return body


def _openai_body_bytes(body: dict[str, object]) -> bytes:
    """The serializer's exact final UTF-8 request-body bytes.

    Deterministic compact JSON with sorted keys and no whitespace (the
    same encoding the implementation hands to the transport; float values
    carry the exact ``value_milli / 1000`` vendor parameters).
    """
    import json

    return json.dumps(
        body, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


def valid_openai_request(
    *,
    messages: tuple[RequestMessageV1, ...] | None = None,
    temperature_milli: int | None = None,
    top_p_milli: int | None = None,
    seed: int | None = None,
) -> dict[str, object]:
    """One digest-consistent OpenAI prepared-request dict (SPEC §4.4.4)."""
    profile = openai_profile()
    fixed = profile.fixed_parameters
    final_messages = _mock_messages() if messages is None else messages
    body = _openai_body_dict(
        model=profile.model,
        messages=final_messages,
        max_output_tokens=fixed.max_output_tokens,
        temperature_milli=temperature_milli,
        top_p_milli=top_p_milli,
        seed=seed,
    )
    canonical_byte_count = len(_openai_body_bytes(body))
    digest = domain_digest(
        "OpenAIPreparedModelRequestV1",
        1,
        {
            "schema_version": 1,
            "mode": "OPENAI",
            "llm_profile_digest": profile.digest,
            "provider": profile.provider,
            "endpoint_id": profile.endpoint_id,
            "model": profile.model,
            "request_serializer_version": profile.request_serializer_version,
            "messages": _messages_canonical(final_messages),
            "fixed_parameters": {
                "schema_version": fixed.schema_version,
                "max_output_tokens": fixed.max_output_tokens,
                "temperature": fixed.temperature.model_dump(),
                "top_p": fixed.top_p.model_dump(),
                "seed": fixed.seed.model_dump(),
                "response_format": fixed.response_format,
            },
            "redaction_profile_id": profile.redaction_profile_id,
            "canonical_byte_count": canonical_byte_count,
        },
    )
    return {
        "schema_version": 1,
        "mode": "OPENAI",
        "llm_profile_digest": profile.digest,
        "provider": profile.provider,
        "endpoint_id": profile.endpoint_id,
        "model": profile.model,
        "request_serializer_version": profile.request_serializer_version,
        "messages": final_messages,
        "fixed_parameters": {
            "schema_version": fixed.schema_version,
            "max_output_tokens": fixed.max_output_tokens,
            "temperature": fixed.temperature.model_dump(),
            "top_p": fixed.top_p.model_dump(),
            "seed": fixed.seed.model_dump(),
            "response_format": fixed.response_format,
        },
        "redaction_profile_id": profile.redaction_profile_id,
        "canonical_byte_count": canonical_byte_count,
        "digest": digest,
    }


# ---------------------------------------------------------------------------
# 16.A exact RED (verbatim from the PLAN card): the Mock variant must
# reject every OpenAI transport field at the parse boundary.
# ---------------------------------------------------------------------------


def test_mock_request_rejects_openai_transport_fields() -> None:
    with pytest.raises(ValidationError):
        MockPreparedModelRequestV1.model_validate(
            valid_mock_request() | {"endpoint_id": "OPENAI_PUBLIC_API_V1"}
        )


# ---------------------------------------------------------------------------
# 16.A matrix (PLAN Registry 16.A row, operative authority): Mock
# request/result excludes OpenAI transport fields; OpenAI request/result
# excludes Mock fields; malformed response, cross-mode field, unknown
# endpoint, or extra field is rejected.
# ---------------------------------------------------------------------------


def test_prepared_request_profile_matrix() -> None:
    # --- Mock variant rejects every OpenAI transport field ---
    for openai_field in (
        {"provider": "openai"},
        {"endpoint_id": "OPENAI_PUBLIC_API_V1"},
        {"model": "gpt-4.1-mini"},
        {"request_serializer_version": "1"},
        {
            "fixed_parameters": {
                "schema_version": 1,
                "max_output_tokens": 8192,
                "temperature": {"kind": "ABSENT"},
                "top_p": {"kind": "ABSENT"},
                "seed": {"kind": "ABSENT"},
                "response_format": "JSON_OBJECT",
            }
        },
        {"redaction_profile_id": "NO_CONTENT_REDACTION_V1"},
    ):
        with pytest.raises(ValidationError):
            MockPreparedModelRequestV1.model_validate(
                valid_mock_request() | openai_field
            )

    # --- OpenAI variant rejects every Mock script field ---
    for mock_field in (
        {"script_id": "mock-deterministic-response-v1"},
        {"script_digest": _MOCK_SCRIPT_DIGEST},
    ):
        with pytest.raises(ValidationError):
            OpenAIPreparedModelRequestV1.model_validate(
                valid_openai_request() | mock_field
            )

    # --- unknown endpoint / wrong provider / extra fields reject ---
    with pytest.raises(ValidationError):
        OpenAIPreparedModelRequestV1.model_validate(
            valid_openai_request() | {"endpoint_id": "EVIL_API_V1"}
        )
    with pytest.raises(ValidationError):
        OpenAIPreparedModelRequestV1.model_validate(
            valid_openai_request() | {"provider": "anthropic"}
        )
    with pytest.raises(ValidationError):
        MockPreparedModelRequestV1.model_validate(
            valid_mock_request() | {"extra": "field"}
        )
    with pytest.raises(ValidationError):
        OpenAIPreparedModelRequestV1.model_validate(
            valid_openai_request() | {"extra": "field"}
        )

    # --- missing fields and type-confused schema_version reject ---
    for request in (valid_mock_request(), valid_openai_request()):
        for missing in (
            "schema_version",
            "mode",
            "llm_profile_digest",
            "messages",
            "canonical_byte_count",
            "digest",
        ):
            dropped = dict(request)
            del dropped[missing]
            with pytest.raises(ValidationError):
                if request["mode"] == "MOCK":
                    MockPreparedModelRequestV1.model_validate(dropped)
                else:
                    OpenAIPreparedModelRequestV1.model_validate(dropped)
        for bad_version in ("1", 1.0, True, 2):
            with pytest.raises(ValidationError):
                if request["mode"] == "MOCK":
                    MockPreparedModelRequestV1.model_validate(
                        dict(request, schema_version=bad_version)
                    )
                else:
                    OpenAIPreparedModelRequestV1.model_validate(
                        dict(request, schema_version=bad_version)
                    )

    # --- digest drift and canonical_byte_count drift reject both modes ---
    with pytest.raises(ValidationError):
        MockPreparedModelRequestV1.model_validate(
            dict(valid_mock_request(), digest="0" * 64)
        )
    with pytest.raises(ValidationError):
        MockPreparedModelRequestV1.model_validate(
            dict(valid_mock_request(), canonical_byte_count=1)
        )
    with pytest.raises(ValidationError):
        OpenAIPreparedModelRequestV1.model_validate(
            dict(valid_openai_request(), digest="0" * 64)
        )
    with pytest.raises(ValidationError):
        OpenAIPreparedModelRequestV1.model_validate(
            dict(valid_openai_request(), canonical_byte_count=1)
        )

    # --- message/source contract violations reject before any request ---
    with pytest.raises(ValidationError):
        MockPreparedModelRequestV1.model_validate(valid_mock_request(messages=()))
    with pytest.raises(ValidationError):
        OpenAIPreparedModelRequestV1.model_validate(valid_openai_request(messages=()))
    # FILE_CONTENT without a canonical path rejects in both modes.
    bad_file = _message(
        "USER", _segment("FILE_CONTENT", "def example():\n    return 0\n")
    )
    with pytest.raises(ValidationError):
        MockPreparedModelRequestV1.model_validate(
            valid_mock_request(messages=(_mock_messages()[0], bad_file))
        )
    with pytest.raises(ValidationError):
        OpenAIPreparedModelRequestV1.model_validate(
            valid_openai_request(messages=(_mock_messages()[0], bad_file))
        )

    # --- malformed response rows (closed ModelResponse) ---
    with pytest.raises(ValidationError):
        ModelResponse.model_validate(
            {
                "schema_version": 1,
                "text": "",
                "text_digest": hashlib.sha256(b"").hexdigest(),
                "byte_count": 0,
            }
        )
    with pytest.raises(ValidationError):
        ModelResponse.model_validate(
            {
                "schema_version": 1,
                "text": "{}",
                "text_digest": "0" * 64,
                "byte_count": 2,
            }
        )
    with pytest.raises(ValidationError):
        ModelResponse.model_validate(
            {
                "schema_version": 1,
                "text": "{}",
                "text_digest": hashlib.sha256(b"{}").hexdigest(),
                "byte_count": 3,
            }
        )
    with pytest.raises(ValidationError):
        ModelResponse.model_validate(
            {
                "schema_version": 1,
                "text": "{}",
                "text_digest": hashlib.sha256(b"{}").hexdigest(),
                "byte_count": 2,
                "extra": 1,
            }
        )
    oversized = "x" * 65537
    with pytest.raises(ValidationError):
        ModelResponse.model_validate(
            {
                "schema_version": 1,
                "text": oversized,
                "text_digest": hashlib.sha256(oversized.encode("utf-8")).hexdigest(),
                "byte_count": 65537,
            }
        )
    response_text = '{"schema_version":1,"action_type":"list_files"}'
    response = ModelResponse(
        schema_version=1,
        text=response_text,
        text_digest=hashlib.sha256(response_text.encode("utf-8")).hexdigest(),
        byte_count=len(response_text.encode("utf-8")),
    )
    assert response.byte_count == len(response_text.encode("utf-8"))

    # --- closed call-result status combinations (SPEC §4.4.4) ---
    profile = mock_profile()
    mock_request = MockPreparedModelRequestV1.model_validate(valid_mock_request())
    assert mock_request.mode == "MOCK"
    valid_mock_result = LLMCallResultV1(
        schema_version=1,
        mode="MOCK",
        llm_profile_digest=profile.digest,
        request_digest=mock_request.digest,
        authorization_record_ref=AbsentV1(kind="ABSENT"),
        status="SUCCEEDED",
        response_digest=PresentResponseDigestV1(
            kind="PRESENT", value=response.text_digest
        ),
        error=AbsentV1(kind="ABSENT"),
    )
    assert valid_mock_result.status == "SUCCEEDED"
    # Mock must never bind an authorization record.
    with pytest.raises(ValidationError):
        LLMCallResultV1(
            schema_version=1,
            mode="MOCK",
            llm_profile_digest=profile.digest,
            request_digest=mock_request.digest,
            authorization_record_ref=PresentAuthorizationRecordRefV1(
                kind="PRESENT", authorization_record_id="authz-1"
            ),
            status="SUCCEEDED",
            response_digest=PresentResponseDigestV1(
                kind="PRESENT", value=response.text_digest
            ),
            error=AbsentV1(kind="ABSENT"),
        )
    # Mock must never use DELIVERY_UNKNOWN.
    with pytest.raises(ValidationError):
        LLMCallResultV1(
            schema_version=1,
            mode="MOCK",
            llm_profile_digest=profile.digest,
            request_digest=mock_request.digest,
            authorization_record_ref=AbsentV1(kind="ABSENT"),
            status="DELIVERY_UNKNOWN",
            response_digest=AbsentV1(kind="ABSENT"),
            error=PresentLLMCallErrorV1(
                kind="PRESENT", stable_error_code="LLM_CALL_FAILED"
            ),
        )
    # OpenAI must bind an authorization record.
    openai_request = OpenAIPreparedModelRequestV1.model_validate(valid_openai_request())
    with pytest.raises(ValidationError):
        LLMCallResultV1(
            schema_version=1,
            mode="OPENAI",
            llm_profile_digest=openai_profile().digest,
            request_digest=openai_request.digest,
            authorization_record_ref=AbsentV1(kind="ABSENT"),
            status="FAILED",
            response_digest=AbsentV1(kind="ABSENT"),
            error=PresentLLMCallErrorV1(
                kind="PRESENT", stable_error_code="LLM_CALL_FAILED"
            ),
        )
    # SUCCEEDED requires response PRESENT and error ABSENT; every other
    # status requires response ABSENT and error PRESENT.
    with pytest.raises(ValidationError):
        LLMCallResultV1(
            schema_version=1,
            mode="MOCK",
            llm_profile_digest=profile.digest,
            request_digest=mock_request.digest,
            authorization_record_ref=AbsentV1(kind="ABSENT"),
            status="SUCCEEDED",
            response_digest=AbsentV1(kind="ABSENT"),
            error=AbsentV1(kind="ABSENT"),
        )
    with pytest.raises(ValidationError):
        LLMCallResultV1(
            schema_version=1,
            mode="MOCK",
            llm_profile_digest=profile.digest,
            request_digest=mock_request.digest,
            authorization_record_ref=AbsentV1(kind="ABSENT"),
            status="FAILED",
            response_digest=PresentResponseDigestV1(
                kind="PRESENT", value=response.text_digest
            ),
            error=PresentLLMCallErrorV1(
                kind="PRESENT", stable_error_code="LLM_CALL_FAILED"
            ),
        )
    # A FAILED Mock result with ABSENT auth ref and the exact combination
    # is closed and valid.
    failed_mock = LLMCallResultV1(
        schema_version=1,
        mode="MOCK",
        llm_profile_digest=profile.digest,
        request_digest=mock_request.digest,
        authorization_record_ref=AbsentV1(kind="ABSENT"),
        status="FAILED",
        response_digest=AbsentV1(kind="ABSENT"),
        error=PresentLLMCallErrorV1(
            kind="PRESENT", stable_error_code="LLM_CALL_FAILED"
        ),
    )
    assert failed_mock.status == "FAILED"


# ---------------------------------------------------------------------------
# Deterministic request identity (GREEN-2): same frozen profile/messages
# produce the same digest and canonical_byte_count; script, message, or
# source changes change the digest.
# ---------------------------------------------------------------------------


def test_prepared_request_identity_is_deterministic() -> None:
    first = valid_mock_request()
    second = valid_mock_request()
    assert first["digest"] == second["digest"]
    assert first["canonical_byte_count"] == second["canonical_byte_count"]

    changed_script = valid_mock_request(
        script_id="other-script-v1",
        script_digest="f" * 64,
    )
    assert changed_script["digest"] != first["digest"]
    assert changed_script["canonical_byte_count"] != first["canonical_byte_count"]

    changed_message = valid_mock_request(
        messages=(
            _mock_messages()[0],
            _message(
                "USER",
                _segment("TASK", "A different instruction."),
                _segment(
                    "FILE_CONTENT",
                    "def example():\n    return 1\n",
                    path="src/example.py",
                ),
            ),
        )
    )
    assert changed_message["digest"] != first["digest"]

    first_openai = valid_openai_request()
    second_openai = valid_openai_request()
    assert first_openai["digest"] == second_openai["digest"]
    assert first_openai["canonical_byte_count"] == second_openai["canonical_byte_count"]
    changed_openai = valid_openai_request(temperature_milli=500)
    assert changed_openai["digest"] != first_openai["digest"]
    assert (
        changed_openai["canonical_byte_count"] != first_openai["canonical_byte_count"]
    )


# ---------------------------------------------------------------------------
# Frozen-profile construction (GREEN-2): prepare each mode from the frozen
# profile/messages; every mode-specific field is bound by the profile.
# ---------------------------------------------------------------------------


def test_prepare_mock_request_binds_frozen_profile() -> None:
    profile = mock_profile()
    messages = _mock_messages()
    request = prepare_mock_request(profile, messages)
    assert request.mode == "MOCK"
    assert request.llm_profile_digest == profile.digest
    assert request.script_id == profile.script_id
    assert request.script_digest == profile.script_digest
    assert len(request.messages) == 2
    # The request dict built independently validates byte-identically.
    rebuilt = MockPreparedModelRequestV1.model_validate(valid_mock_request())
    assert rebuilt.digest == request.digest
    assert rebuilt.canonical_byte_count == request.canonical_byte_count


def test_prepare_openai_request_binds_frozen_profile() -> None:
    profile = openai_profile()
    request = prepare_openai_request(profile, _mock_messages())
    assert request.mode == "OPENAI"
    assert request.llm_profile_digest == profile.digest
    assert request.provider == "openai"
    assert request.endpoint_id == "OPENAI_PUBLIC_API_V1"
    assert request.model == "gpt-4.1-mini"
    assert request.request_serializer_version == "1"
    assert request.redaction_profile_id == "NO_CONTENT_REDACTION_V1"
    assert request.fixed_parameters.max_output_tokens == 8192
    rebuilt = OpenAIPreparedModelRequestV1.model_validate(valid_openai_request())
    assert rebuilt.digest == request.digest
    assert rebuilt.canonical_byte_count == request.canonical_byte_count


# ---------------------------------------------------------------------------
# Deterministic Mock adapter behavior (GREEN-2): byte-identical offline
# output selected only by the frozen script identity and request digest.
# ---------------------------------------------------------------------------


def test_mock_adapter_output_is_byte_identical() -> None:
    request = prepare_mock_request(mock_profile(), _mock_messages())
    adapter = MockLLMAdapter()
    first = adapter.generate(request)
    second = adapter.generate(request)
    assert first.text == second.text
    assert first.text_digest == second.text_digest
    assert first.byte_count == second.byte_count
    assert first.byte_count == len(first.text.encode("utf-8"))


def test_mock_adapter_rejects_unknown_script_identity() -> None:
    foreign = MockPreparedModelRequestV1.model_validate(
        valid_mock_request(script_id="other-script-v1", script_digest="f" * 64)
    )
    with pytest.raises(MockScriptMismatchError):
        MockLLMAdapter().generate(foreign)

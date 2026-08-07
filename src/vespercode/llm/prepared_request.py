"""T16.1 legacy step 16.A: closed Mock/OpenAI prepared-request contracts.

Defines the mutually exclusive prepared-request variants of SPEC §4.4.4 —
the Mock variant carries only the frozen Mock script identity and the
OpenAI variant carries only the frozen OpenAI transport facts, so every
cross-mode, unknown, extra, or mutable field rejects at the parse
boundary — together with ``MockAdapterPayloadV1`` (the complete payload
the Mock adapter interprets), the mode-specific ``canonical_byte_count``
(Mock = the canonical payload byte length; OpenAI = the serializer's exact
final UTF-8 request-body byte length), the §0.1 request digests binding
every other exact field, and the frozen-profile construction entry points
``prepare_mock_request``/``prepare_openai_request``.  The segment
source/path/byte identity contract of Task 15.A is re-validated before any
request exists.  Provider transport, credentials, Grant/authorization
access, request charging, and network clients remain out of scope
(GREEN-4).
"""

from __future__ import annotations

import json
from typing import Annotated, Literal, TypeAlias

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    Strict,
    StrictStr,
    field_validator,
    model_validator,
)

from vespercode.canonical.digest import domain_digest
from vespercode.canonical.json_v1 import (
    CanonicalValueV1,
    canonical_json_bytes,
)
from vespercode.contracts.evidence import _DIGEST_RE
from vespercode.contracts.optional import AbsentV1
from vespercode.governance.request_sources import (
    RequestContentSegmentV1,
    RequestMessageV1,
    validate_segment_sources,
)
from vespercode.profiles.editable import _reject_coerced_schema_version
from vespercode.profiles.llm import (
    MockLLMProfileV1,
    OpenAILLMProfileV1,
    OpenAIFixedParametersV1,
)

_MAX_MESSAGES = 128
_MAX_REQUEST_BYTES = 65536
_MAX_OUTPUT_TOKENS = 8192
_SIGNED_64_BIT_MAX = 2**63 - 1
_SIGNED_64_BIT_MIN = -(2**63)


def _require_digest_form(value: str) -> str:
    """Reject any spelling that is not exactly 64 lowercase hex chars."""
    if _DIGEST_RE.fullmatch(value) is None:
        raise ValueError("must be exactly 64 lowercase hexadecimal characters")
    return value


class MockAdapterPayloadV1(BaseModel):
    """SPEC §4.4.4: the complete payload the Mock adapter interprets.

    Carries exactly the frozen Mock script identity and the ordered
    request messages; its canonical JSON bytes are the Mock-mode
    ``canonical_byte_count`` and no provider/endpoint/model/credential
    field can ever exist here (GREEN-4).
    """

    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal[1]
    script_id: StrictStr
    script_digest: StrictStr
    messages: Annotated[
        tuple[RequestMessageV1, ...], Field(min_length=1, max_length=_MAX_MESSAGES)
    ]

    @field_validator("schema_version", mode="before")
    @classmethod
    def _schema_version_is_exact_int(cls, value: object) -> object:
        return _reject_coerced_schema_version(value)

    @field_validator("script_digest")
    @classmethod
    def _digest_has_exact_form(cls, value: str) -> str:
        return _require_digest_form(value)


class MockPreparedModelRequestV1(BaseModel):
    """SPEC §4.4.4: the closed ``mode=MOCK`` prepared request.

    Every field is required; ``canonical_byte_count`` must equal the
    canonical ``MockAdapterPayloadV1`` byte length and ``digest`` the §0.1
    identity of every other exact field (excluding itself), so a drift in
    profile binding, script identity, messages, sources, or size rejects
    before the request exists.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal[1]
    mode: Literal["MOCK"]
    llm_profile_digest: StrictStr
    script_id: StrictStr
    script_digest: StrictStr
    messages: Annotated[
        tuple[RequestMessageV1, ...], Field(min_length=1, max_length=_MAX_MESSAGES)
    ]
    canonical_byte_count: Annotated[int, Strict(), Field(ge=1, le=_MAX_REQUEST_BYTES)]
    digest: StrictStr

    @field_validator("schema_version", mode="before")
    @classmethod
    def _schema_version_is_exact_int(cls, value: object) -> object:
        return _reject_coerced_schema_version(value)

    @field_validator("llm_profile_digest", "script_digest", "digest")
    @classmethod
    def _digests_have_exact_form(cls, value: str) -> str:
        return _require_digest_form(value)

    @model_validator(mode="after")
    def _payload_size_and_digest_bind_every_field(
        self,
    ) -> MockPreparedModelRequestV1:
        # The segment source/path/byte identity contract is re-validated
        # before any request exists (SPEC §4.4.4; Task 15.A vocabulary).
        validate_segment_sources(self.messages)
        payload = MockAdapterPayloadV1(
            schema_version=1,
            script_id=self.script_id,
            script_digest=self.script_digest,
            messages=self.messages,
        )
        expected_bytes = len(canonical_json_bytes(_mock_payload_canonical(payload)))
        if self.canonical_byte_count != expected_bytes:
            raise ValueError(
                "canonical_byte_count must equal the canonical "
                "MockAdapterPayloadV1 byte length"
            )
        if self.digest != _compute_mock_request_digest(self):
            raise ValueError(
                "digest must equal the §0.1 identity of every other exact field"
            )
        return self


class PresentBodyTemperatureV1(BaseModel):
    """One ``PRESENT`` body temperature in vendor units, 0.0..2.0."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    kind: Literal["PRESENT"]
    value: Annotated[float, Strict(), Field(ge=0.0, le=2.0)]


class PresentBodyTopPV1(BaseModel):
    """One ``PRESENT`` body top-p in vendor units, 0.0..1.0."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    kind: Literal["PRESENT"]
    value: Annotated[float, Strict(), Field(ge=0.0, le=1.0)]


class PresentBodySeedV1(BaseModel):
    """One ``PRESENT`` body seed (signed 64-bit integer)."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    kind: Literal["PRESENT"]
    value: Annotated[int, Strict(), Field(ge=_SIGNED_64_BIT_MIN, le=_SIGNED_64_BIT_MAX)]


OptionalBodyTemperatureV1: TypeAlias = Annotated[
    AbsentV1 | PresentBodyTemperatureV1, Field(discriminator="kind")
]
"""The body's closed ``ABSENT``/``PRESENT(value: 0.0..2.0)`` temperature."""

OptionalBodyTopPV1: TypeAlias = Annotated[
    AbsentV1 | PresentBodyTopPV1, Field(discriminator="kind")
]
"""The body's closed ``ABSENT``/``PRESENT(value: 0.0..1.0)`` top-p."""

OptionalBodySeedV1: TypeAlias = Annotated[
    AbsentV1 | PresentBodySeedV1, Field(discriminator="kind")
]
"""The body's closed ``ABSENT``/``PRESENT(value: signed 64-bit)`` seed."""


class OpenAIRequestBodyMessageV1(BaseModel):
    """One vendor message: lowercase role plus the concatenated content."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    role: Literal["system", "user"]
    content: StrictStr


class OpenAIResponseFormatV1(BaseModel):
    """The fixed ``{"type": "json_object"}`` vendor response format."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    type: Literal["json_object"]


class OpenAIRequestBodyV1(BaseModel):
    """The exact closed vendor request body the serializer produces.

    Only the vendor fields exist here: ``model``, the ordered messages
    (each message's segments concatenated in order with no implicit
    separator and no source metadata), the frozen ``max_output_tokens``,
    the ``ABSENT``/``PRESENT`` optional vendor parameters (mapped from
    ``value_milli / 1000``), and the fixed JSON-object response format
    (SPEC §4.4.4: "不把来源元数据写入 HTTP 正文").
    """

    model_config = ConfigDict(extra="forbid", frozen=True)
    model: StrictStr
    messages: Annotated[
        tuple[OpenAIRequestBodyMessageV1, ...],
        Field(min_length=1, max_length=_MAX_MESSAGES),
    ]
    max_output_tokens: Annotated[int, Strict(), Field(ge=1, le=_MAX_OUTPUT_TOKENS)]
    temperature: OptionalBodyTemperatureV1
    top_p: OptionalBodyTopPV1
    seed: OptionalBodySeedV1
    response_format: OpenAIResponseFormatV1


class OpenAIPreparedModelRequestV1(BaseModel):
    """SPEC §4.4.4: the closed ``mode=OPENAI`` prepared request.

    Every field is required and every mode-specific fact comes from the
    frozen ``OpenAILLMProfileV1``; ``canonical_byte_count`` must equal the
    serializer's exact final UTF-8 request-body byte length and ``digest``
    the §0.1 identity of every other exact field, so endpoint/model/
    serializer/script/source/size drift rejects before the request exists.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal[1]
    mode: Literal["OPENAI"]
    llm_profile_digest: StrictStr
    provider: Literal["openai"]
    endpoint_id: Literal["OPENAI_PUBLIC_API_V1"]
    model: StrictStr
    request_serializer_version: StrictStr
    messages: Annotated[
        tuple[RequestMessageV1, ...], Field(min_length=1, max_length=_MAX_MESSAGES)
    ]
    fixed_parameters: OpenAIFixedParametersV1
    redaction_profile_id: Literal["NO_CONTENT_REDACTION_V1"]
    canonical_byte_count: Annotated[int, Strict(), Field(ge=1, le=_MAX_REQUEST_BYTES)]
    digest: StrictStr

    @field_validator("schema_version", mode="before")
    @classmethod
    def _schema_version_is_exact_int(cls, value: object) -> object:
        return _reject_coerced_schema_version(value)

    @field_validator("llm_profile_digest", "digest")
    @classmethod
    def _digests_have_exact_form(cls, value: str) -> str:
        return _require_digest_form(value)

    @model_validator(mode="after")
    def _body_size_and_digest_bind_every_field(
        self,
    ) -> OpenAIPreparedModelRequestV1:
        validate_segment_sources(self.messages)
        if self.canonical_byte_count != len(_openai_body_bytes(self)):
            raise ValueError(
                "canonical_byte_count must equal the serializer's exact final "
                "UTF-8 request-body byte length"
            )
        if self.digest != _compute_openai_request_digest(self):
            raise ValueError(
                "digest must equal the §0.1 identity of every other exact field"
            )
        return self


PreparedModelRequestV1: TypeAlias = Annotated[
    MockPreparedModelRequestV1 | OpenAIPreparedModelRequestV1,
    Field(discriminator="mode"),
]
"""SPEC §4.2.1/§4.4.4: the closed union; ``mode`` selects the variant."""


# ---------------------------------------------------------------------------
# Canonical value shapes (the sole digest/byte binding of each variant).
# ---------------------------------------------------------------------------


def _segment_canonical(seg: RequestContentSegmentV1) -> dict[str, CanonicalValueV1]:
    """One segment in canonical digest shape (SPEC §4.4.4, AC-26)."""
    path: CanonicalValueV1
    if seg.source_path.kind == "ABSENT":
        path = {"kind": "ABSENT"}
    else:
        path = {"kind": "PRESENT", "value": seg.source_path.value.value}
    return {
        "source_category": seg.source_category,
        "source_path": path,
        "content": seg.content,
        "content_digest": seg.content_digest,
        "byte_count": seg.byte_count,
    }


def _messages_canonical(
    messages: tuple[RequestMessageV1, ...],
) -> tuple[dict[str, CanonicalValueV1], ...]:
    """The ordered messages in canonical digest shape (order kept)."""
    return tuple(
        {
            "role": message.role,
            "segments": tuple(_segment_canonical(seg) for seg in message.segments),
        }
        for message in messages
    )


def _mock_payload_canonical(
    payload: MockAdapterPayloadV1,
) -> dict[str, CanonicalValueV1]:
    """The canonical ``MockAdapterPayloadV1`` value (SPEC §4.4.4)."""
    return {
        "schema_version": payload.schema_version,
        "script_id": payload.script_id,
        "script_digest": payload.script_digest,
        "messages": _messages_canonical(payload.messages),
    }


def _fixed_parameters_canonical(
    fixed: OpenAIFixedParametersV1,
) -> dict[str, CanonicalValueV1]:
    """The profile's frozen fixed parameters in canonical digest shape."""
    return {
        "schema_version": fixed.schema_version,
        "max_output_tokens": fixed.max_output_tokens,
        "temperature": fixed.temperature.model_dump(),
        "top_p": fixed.top_p.model_dump(),
        "seed": fixed.seed.model_dump(),
        "response_format": fixed.response_format,
    }


def _compute_mock_request_digest(request: MockPreparedModelRequestV1) -> str:
    """The §0.1 identity of every Mock request field except the digest."""
    return domain_digest(
        "MockPreparedModelRequestV1",
        1,
        {
            "schema_version": request.schema_version,
            "mode": request.mode,
            "llm_profile_digest": request.llm_profile_digest,
            "script_id": request.script_id,
            "script_digest": request.script_digest,
            "messages": _messages_canonical(request.messages),
            "canonical_byte_count": request.canonical_byte_count,
        },
    )


def _compute_openai_request_digest(request: OpenAIPreparedModelRequestV1) -> str:
    """The §0.1 identity of every OpenAI request field except the digest."""
    return domain_digest(
        "OpenAIPreparedModelRequestV1",
        1,
        {
            "schema_version": request.schema_version,
            "mode": request.mode,
            "llm_profile_digest": request.llm_profile_digest,
            "provider": request.provider,
            "endpoint_id": request.endpoint_id,
            "model": request.model,
            "request_serializer_version": request.request_serializer_version,
            "messages": _messages_canonical(request.messages),
            "fixed_parameters": _fixed_parameters_canonical(request.fixed_parameters),
            "redaction_profile_id": request.redaction_profile_id,
            "canonical_byte_count": request.canonical_byte_count,
        },
    )


def _openai_body_dict_from_facts(
    *,
    model: str,
    messages: tuple[RequestMessageV1, ...],
    fixed: OpenAIFixedParametersV1,
) -> dict[str, object]:
    """The serializer's exact vendor body dict (segment contents joined).

    Each message's segments are concatenated in order with no implicit
    separator and no source metadata; ``ABSENT`` optional fixed parameters
    are omitted from the wire body and ``PRESENT`` parameters map
    ``value_milli / 1000`` to the vendor float (T06.3 behavior 3).
    """
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
        "max_output_tokens": fixed.max_output_tokens,
    }
    if fixed.temperature.kind == "PRESENT":
        body["temperature"] = fixed.temperature.value_milli / 1000
    if fixed.top_p.kind == "PRESENT":
        body["top_p"] = fixed.top_p.value_milli / 1000
    if fixed.seed.kind == "PRESENT":
        body["seed"] = fixed.seed.value
    body["response_format"] = {"type": "json_object"}
    return body


def _openai_body_dict(request: OpenAIPreparedModelRequestV1) -> dict[str, object]:
    """The serializer's exact vendor body dict for one prepared request."""
    return _openai_body_dict_from_facts(
        model=request.model,
        messages=request.messages,
        fixed=request.fixed_parameters,
    )


def _encode_body_bytes(body: dict[str, object]) -> bytes:
    """Deterministic compact UTF-8 JSON with sorted keys and no whitespace.

    Byte-identical to the canonical encoder for every canonical-encodable
    value; floats carry the exact vendor parameters.  This is the exact
    byte sequence handed to the transport, so its length is the
    OpenAI-mode ``canonical_byte_count``.
    """
    return json.dumps(
        body,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


def _openai_body_bytes(request: OpenAIPreparedModelRequestV1) -> bytes:
    """The serializer's exact final UTF-8 request-body bytes."""
    return _encode_body_bytes(_openai_body_dict(request))


# ---------------------------------------------------------------------------
# Frozen-profile construction entry points.
# ---------------------------------------------------------------------------


def prepare_mock_request(
    profile: MockLLMProfileV1,
    messages: tuple[RequestMessageV1, ...],
) -> MockPreparedModelRequestV1:
    """Prepare one ``MOCK`` request from the frozen Mock profile.

    Every Mock identity field (profile digest, script id, script digest)
    comes from the frozen profile and the payload byte count/digest are
    recomputed before the request is constructed; the model validator
    re-verifies both before a request exists.
    """
    payload = MockAdapterPayloadV1(
        schema_version=1,
        script_id=profile.script_id,
        script_digest=profile.script_digest,
        messages=messages,
    )
    canonical_byte_count = len(canonical_json_bytes(_mock_payload_canonical(payload)))
    digest = domain_digest(
        "MockPreparedModelRequestV1",
        1,
        {
            "schema_version": 1,
            "mode": "MOCK",
            "llm_profile_digest": profile.digest,
            "script_id": profile.script_id,
            "script_digest": profile.script_digest,
            "messages": _messages_canonical(messages),
            "canonical_byte_count": canonical_byte_count,
        },
    )
    return MockPreparedModelRequestV1(
        schema_version=1,
        mode="MOCK",
        llm_profile_digest=profile.digest,
        script_id=profile.script_id,
        script_digest=profile.script_digest,
        messages=messages,
        canonical_byte_count=canonical_byte_count,
        digest=digest,
    )


def prepare_openai_request(
    profile: OpenAILLMProfileV1,
    messages: tuple[RequestMessageV1, ...],
) -> OpenAIPreparedModelRequestV1:
    """Prepare one ``OPENAI`` request from the frozen OpenAI profile.

    Every transport fact (provider, endpoint, model, serializer version,
    fixed parameters, redaction profile) comes from the frozen profile;
    the body byte count/digest are recomputed before the request is
    constructed; the model validator re-verifies both before a request
    exists.
    """
    canonical_byte_count = len(
        _encode_body_bytes(
            _openai_body_dict_from_facts(
                model=profile.model,
                messages=messages,
                fixed=profile.fixed_parameters,
            )
        )
    )
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
            "messages": _messages_canonical(messages),
            "fixed_parameters": _fixed_parameters_canonical(profile.fixed_parameters),
            "redaction_profile_id": profile.redaction_profile_id,
            "canonical_byte_count": canonical_byte_count,
        },
    )
    return OpenAIPreparedModelRequestV1(
        schema_version=1,
        mode="OPENAI",
        llm_profile_digest=profile.digest,
        provider=profile.provider,
        endpoint_id=profile.endpoint_id,
        model=profile.model,
        request_serializer_version=profile.request_serializer_version,
        messages=messages,
        fixed_parameters=profile.fixed_parameters,
        redaction_profile_id=profile.redaction_profile_id,
        canonical_byte_count=canonical_byte_count,
        digest=digest,
    )

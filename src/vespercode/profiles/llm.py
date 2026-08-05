"""T06.3 legacy step 6.C: closed Mock and OpenAI LLM profiles.

``MockLLMProfileV1`` and ``OpenAILLMProfileV1`` are the immutable,
mutually exclusive profile variants of SPEC §4.1: Mock data can never
carry OpenAI configuration and OpenAI data can never carry Mock script
fields, so every cross-mode, unknown, extra, or mutable field rejects
deterministically before a profile exists.  ``load_llm_profile`` loads
packaged bytes into the closed ``LLMProfileManifestV1`` union and verifies
the §0.1 digest of every variant, giving each built-in resource exactly
one integrity identity.  Endpoint resolution, request serialization,
credential access, and adapter calls remain out of scope (GREEN-4).
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
    TypeAdapter,
    field_validator,
    model_validator,
)

from src.vespercode.canonical.digest import domain_digest
from src.vespercode.canonical.json_v1 import CanonicalValueV1
from src.vespercode.contracts.evidence import _DIGEST_RE
from src.vespercode.contracts.optional import AbsentV1
from src.vespercode.profiles.editable import _reject_coerced_schema_version

# The exact frozen packaged profile identities (SPEC §4.1; the packaged
# built-in bytes in src/vespercode/profiles/builtin/ are the single source
# of truth and the digest binds every exact value): Mock adapter_version
# "1", script_id "mock-deterministic-response-v1", script_digest
# "3be1c216…94da" (the §0.1 MockScriptV1 identity over {schema_version: 1,
# profile_id: "mock-deterministic-v1", script_id}); OpenAI model
# "gpt-4.1-mini", adapter_version "1", request_serializer_version "1",
# fixed_parameters {max_output_tokens 8192, all optionals ABSENT,
# response_format "JSON_OBJECT"}, redaction_profile_id
# "NO_CONTENT_REDACTION_V1".

Signed64BitIntegerV1 = Annotated[int, Strict(), Field(ge=-(2**63), le=2**63 - 1)]
"""SPEC §4.1: the signed 64-bit integer value domain."""


class PresentTemperatureMilliV1(BaseModel):
    """SPEC §4.1: ``PRESENT`` temperature in milli-degrees, 0..2000."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    kind: Literal["PRESENT"]
    value_milli: Annotated[int, Strict(), Field(ge=0, le=2000)]


class PresentTopPMilliV1(BaseModel):
    """SPEC §4.1: ``PRESENT`` top-p in milli-percent, 0..1000."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    kind: Literal["PRESENT"]
    value_milli: Annotated[int, Strict(), Field(ge=0, le=1000)]


class PresentIntegerParameterV1(BaseModel):
    """SPEC §4.1: ``PRESENT`` signed 64-bit integer parameter."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    kind: Literal["PRESENT"]
    value: Signed64BitIntegerV1


OptionalTemperatureMilliV1: TypeAlias = Annotated[
    AbsentV1 | PresentTemperatureMilliV1, Field(discriminator="kind")
]
"""SPEC §4.1: ``ABSENT`` or ``PRESENT(value_milli: 0..2000)``."""

OptionalTopPMilliV1: TypeAlias = Annotated[
    AbsentV1 | PresentTopPMilliV1, Field(discriminator="kind")
]
"""SPEC §4.1: ``ABSENT`` or ``PRESENT(value_milli: 0..1000)``."""

OptionalIntegerParameterV1: TypeAlias = Annotated[
    AbsentV1 | PresentIntegerParameterV1, Field(discriminator="kind")
]
"""SPEC §4.1: ``ABSENT`` or ``PRESENT(value: signed 64-bit integer)``."""


class OpenAIFixedParametersV1(BaseModel):
    """SPEC §4.1: the closed OpenAI request fixed parameters.

    Every field is required; each optional parameter is an explicit
    ``ABSENT``/``PRESENT`` closed union so no field is ever silently
    defaulted, and the serializer maps ``value_milli / 1000`` to the
    vendor parameter.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal[1]
    max_output_tokens: Annotated[int, Strict(), Field(ge=1, le=8192)]
    temperature: OptionalTemperatureMilliV1
    top_p: OptionalTopPMilliV1
    seed: OptionalIntegerParameterV1
    response_format: Literal["JSON_OBJECT"]

    @field_validator("schema_version", mode="before")
    @classmethod
    def _schema_version_is_exact_int(cls, value: object) -> object:
        return _reject_coerced_schema_version(value)


def _require_digest_form(value: str) -> str:
    """Reject any spelling that is not exactly 64 lowercase hex chars."""
    if _DIGEST_RE.fullmatch(value) is None:
        raise ValueError("must be exactly 64 lowercase hexadecimal characters")
    return value


class MockLLMProfileV1(BaseModel):
    """SPEC §4.1: the immutable built-in Mock LLM profile.

    Carries exactly the Mock identity fields; any OpenAI configuration
    field rejects, and the digest must equal the §0.1 identity of every
    other exact field, so each packaged resource has one integrity
    identity.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal[1]
    profile_id: Literal["mock-deterministic-v1"]
    mode: Literal["MOCK"]
    adapter_version: StrictStr
    script_id: StrictStr
    script_digest: StrictStr
    digest: StrictStr

    @field_validator("schema_version", mode="before")
    @classmethod
    def _schema_version_is_exact_int(cls, value: object) -> object:
        return _reject_coerced_schema_version(value)

    @field_validator("script_digest", "digest")
    @classmethod
    def _digests_have_exact_form(cls, value: str) -> str:
        return _require_digest_form(value)

    @model_validator(mode="after")
    def _digest_binds_every_field(self) -> MockLLMProfileV1:
        if self.digest != _compute_mock_digest(self):
            raise ValueError(
                "digest must equal the §0.1 identity of every other exact field"
            )
        return self


class OpenAILLMProfileV1(BaseModel):
    """SPEC §4.1: the immutable built-in OpenAI LLM profile.

    Carries exactly the OpenAI identity fields; any Mock script field
    rejects, and the digest must equal the §0.1 identity of every other
    exact field.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal[1]
    profile_id: Literal["openai-single-turn-v1"]
    mode: Literal["OPENAI"]
    provider: Literal["openai"]
    endpoint_id: Literal["OPENAI_PUBLIC_API_V1"]
    model: StrictStr
    adapter_version: StrictStr
    request_serializer_version: StrictStr
    fixed_parameters: OpenAIFixedParametersV1
    redaction_profile_id: Literal["NO_CONTENT_REDACTION_V1"]
    digest: StrictStr

    @field_validator("schema_version", mode="before")
    @classmethod
    def _schema_version_is_exact_int(cls, value: object) -> object:
        return _reject_coerced_schema_version(value)

    @field_validator("digest")
    @classmethod
    def _digest_has_exact_form(cls, value: str) -> str:
        return _require_digest_form(value)

    @model_validator(mode="after")
    def _digest_binds_every_field(self) -> OpenAILLMProfileV1:
        if self.digest != _compute_openai_digest(self):
            raise ValueError(
                "digest must equal the §0.1 identity of every other exact field"
            )
        return self


LLMProfileManifestV1: TypeAlias = Annotated[
    MockLLMProfileV1 | OpenAILLMProfileV1, Field(discriminator="mode")
]
"""SPEC §4.1: ``MOCK`` or ``OPENAI``, mutually exclusive by mode."""


def _mock_body(profile: MockLLMProfileV1) -> dict[str, CanonicalValueV1]:
    """The canonical digest value body: every exact field except the digest."""
    return {
        "schema_version": profile.schema_version,
        "profile_id": profile.profile_id,
        "mode": profile.mode,
        "adapter_version": profile.adapter_version,
        "script_id": profile.script_id,
        "script_digest": profile.script_digest,
    }


def _openai_body(profile: OpenAILLMProfileV1) -> dict[str, CanonicalValueV1]:
    """The canonical digest value body: every exact field except the digest."""
    fixed = profile.fixed_parameters
    return {
        "schema_version": profile.schema_version,
        "profile_id": profile.profile_id,
        "mode": profile.mode,
        "provider": profile.provider,
        "endpoint_id": profile.endpoint_id,
        "model": profile.model,
        "adapter_version": profile.adapter_version,
        "request_serializer_version": profile.request_serializer_version,
        "fixed_parameters": {
            "schema_version": fixed.schema_version,
            "max_output_tokens": fixed.max_output_tokens,
            "temperature": fixed.temperature.model_dump(),
            "top_p": fixed.top_p.model_dump(),
            "seed": fixed.seed.model_dump(),
            "response_format": fixed.response_format,
        },
        "redaction_profile_id": profile.redaction_profile_id,
    }


def _compute_mock_digest(profile: MockLLMProfileV1) -> str:
    """The §0.1 identity of every exact Mock profile field except digest."""
    return domain_digest(
        "MockLLMProfileV1", profile.schema_version, _mock_body(profile)
    )


def _compute_openai_digest(profile: OpenAILLMProfileV1) -> str:
    """The §0.1 identity of every exact OpenAI profile field except digest."""
    return domain_digest(
        "OpenAILLMProfileV1", profile.schema_version, _openai_body(profile)
    )


def load_llm_profile(raw: bytes) -> LLMProfileManifestV1:
    """Load packaged LLM profile bytes into the closed union.

    The input must be UTF-8 JSON of exactly one variant's fields; missing,
    extra, cross-mode, unknown, or drifted fields reject deterministically,
    and the variant's §0.1 digest is verified before a profile exists.
    """
    try:
        obj = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("LLM profile must be valid UTF-8 JSON") from exc
    return TypeAdapter(LLMProfileManifestV1).validate_python(obj)

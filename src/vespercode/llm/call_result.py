"""T16.1 legacy step 16.A: the closed ``LLMCallResultV1`` status contract.

Defines the closed optional refs/digest/error unions and the
``LLMCallResultV1`` status combinations of SPEC §4.4.4: Mock results must
bind ``authorization_record_ref=ABSENT`` and may never use
``DELIVERY_UNKNOWN``; OpenAI results must bind a PRESENT authorization
record; ``SUCCEEDED`` requires ``response_digest=PRESENT`` with
``error=ABSENT`` and every other status requires the exact reverse — any
inconsistent mode/status/ref combination rejects before the result can be
published (SPEC §4.2.8 ``INTERNAL_ERROR`` protection).  Construction of a
result from a response or adapter failure belongs to Task 25.C; this
module owns only the closed contract and its combination validation.
"""

from __future__ import annotations

from typing import Annotated, Literal, TypeAlias

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictStr,
    field_validator,
    model_validator,
)

from vespercode.contracts.evidence import _DIGEST_RE
from vespercode.contracts.optional import AbsentV1
from vespercode.profiles.editable import _reject_coerced_schema_version

_MAX_IDENTIFIER_CHARS = 128
_MAX_ERROR_CODE_CHARS = 64


class PresentAuthorizationRecordRefV1(BaseModel):
    """The closed ``PRESENT`` authorization-record reference (§4.4.4)."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    kind: Literal["PRESENT"]
    authorization_record_id: Annotated[
        StrictStr, Field(min_length=1, max_length=_MAX_IDENTIFIER_CHARS)
    ]


OptionalAuthorizationRecordRefV1: TypeAlias = Annotated[
    AbsentV1 | PresentAuthorizationRecordRefV1, Field(discriminator="kind")
]
"""SPEC §4.4.4: ``ABSENT`` or ``PRESENT(authorization_record_id)``."""


class PresentResponseDigestV1(BaseModel):
    """The closed ``PRESENT`` response digest (64 lowercase hex SHA-256)."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    kind: Literal["PRESENT"]
    value: StrictStr

    @field_validator("value")
    @classmethod
    def _digest_has_exact_form(cls, value: str) -> str:
        if _DIGEST_RE.fullmatch(value) is None:
            raise ValueError("must be exactly 64 lowercase hexadecimal characters")
        return value


OptionalResponseDigestV1: TypeAlias = Annotated[
    AbsentV1 | PresentResponseDigestV1, Field(discriminator="kind")
]
"""SPEC §4.4.4: ``ABSENT`` or ``PRESENT(value: 64 lowercase hex)``."""


class PresentLLMCallErrorV1(BaseModel):
    """The closed ``PRESENT`` stable LLM call error code (§4.4.4)."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    kind: Literal["PRESENT"]
    stable_error_code: Annotated[
        StrictStr, Field(min_length=1, max_length=_MAX_ERROR_CODE_CHARS)
    ]


OptionalLLMCallErrorV1: TypeAlias = Annotated[
    AbsentV1 | PresentLLMCallErrorV1, Field(discriminator="kind")
]
"""SPEC §4.4.4: ``ABSENT`` or ``PRESENT(stable_error_code)``."""


class LLMCallResultV1(BaseModel):
    """SPEC §4.4.4: one closed, body-free call result.

    The mode, profile digest, and request digest bind the exact prepared
    request that was called; the closed status combinations are enforced
    so an inconsistent result can never be published (the control plane
    blocks it with ``INTERNAL_ERROR`` per SPEC §4.2.8).
    """

    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal[1]
    mode: Literal["MOCK", "OPENAI"]
    llm_profile_digest: StrictStr
    request_digest: StrictStr
    authorization_record_ref: OptionalAuthorizationRecordRefV1
    status: Literal["NOT_ATTEMPTED", "SUCCEEDED", "FAILED", "DELIVERY_UNKNOWN"]
    response_digest: OptionalResponseDigestV1
    error: OptionalLLMCallErrorV1

    @field_validator("schema_version", mode="before")
    @classmethod
    def _schema_version_is_exact_int(cls, value: object) -> object:
        return _reject_coerced_schema_version(value)

    @field_validator("llm_profile_digest", "request_digest")
    @classmethod
    def _digests_have_exact_form(cls, value: str) -> str:
        if _DIGEST_RE.fullmatch(value) is None:
            raise ValueError("must be exactly 64 lowercase hexadecimal characters")
        return value

    @model_validator(mode="after")
    def _closed_status_combinations(self) -> LLMCallResultV1:
        if self.mode == "MOCK":
            if self.authorization_record_ref.kind != "ABSENT":
                raise ValueError(
                    "Mock call results must bind authorization_record_ref=ABSENT"
                )
            if self.status == "DELIVERY_UNKNOWN":
                raise ValueError("Mock call results must never use DELIVERY_UNKNOWN")
        elif self.authorization_record_ref.kind != "PRESENT":
            raise ValueError(
                "OpenAI call results must bind authorization_record_ref=PRESENT"
            )
        if self.status == "SUCCEEDED":
            if self.response_digest.kind != "PRESENT" or self.error.kind != "ABSENT":
                raise ValueError(
                    "SUCCEEDED requires response_digest=PRESENT and error=ABSENT"
                )
        elif self.response_digest.kind != "ABSENT" or self.error.kind != "PRESENT":
            raise ValueError(
                "non-SUCCEEDED results require response_digest=ABSENT and error=PRESENT"
            )
        return self

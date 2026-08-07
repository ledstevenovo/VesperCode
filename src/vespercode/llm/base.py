"""T16.1 legacy step 16.A: the low-level single-turn LLM adapter contract.

``LLMAdapter.generate`` is the one-call protocol of SPEC §4.2.1 and
``ModelResponse`` is the closed, immutable model-output container: the
exact raw output text, its plain SHA-256 (the ``response_digest`` value of
SPEC §4.4.4), and the exact UTF-8 byte count, all bound at the parse
boundary so a malformed or unbounded response can never exist.  The
concrete Mock/OpenAI adapters, request preparation, serialization,
credentials, Grants, and network clients remain out of scope (GREEN-4).
"""

from __future__ import annotations

import hashlib
from typing import Annotated, Literal, Protocol

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    Strict,
    StrictStr,
    field_validator,
    model_validator,
)

from vespercode.contracts.evidence import _DIGEST_RE
from vespercode.llm.prepared_request import PreparedModelRequestV1
from vespercode.profiles.editable import _reject_coerced_schema_version

# The closed bound on one model response text: the request-side 64 KiB
# bound of SPEC §5.1 applied symmetrically to the response ("responses and
# failures remain bounded", card GREEN-2); the action parser owns semantic
# validity.
_MAX_RESPONSE_TEXT_BYTES = 65536


class ModelResponse(BaseModel):
    """SPEC §4.2.1/§4.4.4: one closed, byte-identical model output.

    ``text`` is the exact raw model output; ``text_digest`` is the plain
    SHA-256 of its UTF-8 bytes and ``byte_count`` the same byte length;
    both must be declared exactly, so a response whose digest, size, or
    bound does not bind its exact bytes is rejected before it exists.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal[1]
    text: StrictStr
    text_digest: StrictStr
    byte_count: Annotated[int, Strict(), Field(ge=1, le=_MAX_RESPONSE_TEXT_BYTES)]

    @field_validator("schema_version", mode="before")
    @classmethod
    def _schema_version_is_exact_int(cls, value: object) -> object:
        return _reject_coerced_schema_version(value)

    @field_validator("text_digest")
    @classmethod
    def _digest_has_exact_form(cls, value: str) -> str:
        if _DIGEST_RE.fullmatch(value) is None:
            raise ValueError("must be exactly 64 lowercase hexadecimal characters")
        return value

    @model_validator(mode="after")
    def _digest_and_bytes_bind_the_text(self) -> ModelResponse:
        raw = self.text.encode("utf-8")
        if self.text_digest != hashlib.sha256(raw).hexdigest():
            raise ValueError("text_digest must bind the exact response text bytes")
        if self.byte_count != len(raw):
            raise ValueError(
                "byte_count must equal the exact response text byte length"
            )
        return self


class LLMAdapter(Protocol):
    """SPEC §4.2.1: the one-call adapter protocol over the closed union.

    Each concrete adapter accepts exactly its mode variant
    (``MockLLMAdapter`` the ``MOCK`` variant, the bound OpenAI adapter the
    ``OPENAI`` variant); the control plane verifies
    adapter/profile/request consistency before any call.  v1 performs at
    most one non-retried transport call per ``generate`` (SPEC §4.2.8:
    ``LLM_CALL_FAILED`` and stop, never auto-retry).
    """

    def generate(self, request: PreparedModelRequestV1) -> ModelResponse: ...

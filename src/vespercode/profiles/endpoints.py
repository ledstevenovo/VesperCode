"""T06.3 legacy step 6.D: the trusted OpenAI endpoint map.

``OpenAIEndpointV1`` is the immutable, closed trusted endpoint record of
SPEC §4.1 — exactly ``OPENAI_PUBLIC_API_V1`` / ``https`` /
``api.openai.com`` / ``443`` / ``/v1`` — and ``OpenAIEndpointRegistry``
resolves only that built-in identifier.  Raw user URLs, ``base_url``,
config overrides, unknown ids, and alternate records reject without any
network access; transport code derives ``https://api.openai.com:443/v1``
internally from the five trusted fields and never adds a shared
``base_url`` field.  HTTP request preparation, URL overrides, credential
management, and network calls remain out of scope (GREEN-4).
"""

from __future__ import annotations

from typing import Final, Literal

from pydantic import BaseModel, ConfigDict, field_validator

OPENAI_PUBLIC_ENDPOINT_ID: Final = "OPENAI_PUBLIC_API_V1"


def _reject_coerced_port(value: object) -> object:
    """Reject bool/float/string spelling of the integer effective port.

    Pydantic lax mode would otherwise coerce ``443.0`` into the
    ``Literal[443]`` field; the closed T05.1 convention pins Strict on
    scalar fields, so every type-confused spelling rejects
    deterministically.
    """
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError("effective_port must be the decimal integer 443")
    return value


class OpenAIEndpointV1(BaseModel):
    """The sole trusted OpenAI endpoint record (SPEC §4.1, §4.4.3).

    Every field is a closed literal and unknown fields reject, so a raw
    URL, ``base_url``, or alternate record can never exist; the record is
    frozen and carries exactly the five trusted components.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)
    endpoint_id: Literal["OPENAI_PUBLIC_API_V1"]
    scheme: Literal["https"]
    host: Literal["api.openai.com"]
    effective_port: Literal[443]
    base_path: Literal["/v1"]

    @field_validator("effective_port", mode="before")
    @classmethod
    def _effective_port_is_exact_int(cls, value: object) -> object:
        return _reject_coerced_port(value)


class UnknownEndpointError(ValueError):
    """One closed rejection for an endpoint id outside the trusted map."""


class OpenAIEndpointRegistry:
    """The read-only built-in endpoint map (SPEC §4.1 behavior 2).

    Resolves exactly the frozen ``OPENAI_PUBLIC_API_V1`` identifier to the
    immutable trusted record; any other id, URL, or override raises
    ``UnknownEndpointError`` without network access or mutation.
    """

    _TRUSTED_ENDPOINT: Final = OpenAIEndpointV1(
        endpoint_id=OPENAI_PUBLIC_ENDPOINT_ID,
        scheme="https",
        host="api.openai.com",
        effective_port=443,
        base_path="/v1",
    )

    @classmethod
    def resolve(cls, endpoint_id: str) -> OpenAIEndpointV1:
        """Resolve *endpoint_id* to the trusted endpoint record.

        Only the exact built-in identifier resolves; raw user URLs,
        ``base_url`` values, unknown ids, and alternate records reject
        deterministically and no network access ever occurs.
        """
        if endpoint_id != OPENAI_PUBLIC_ENDPOINT_ID:
            raise UnknownEndpointError(
                f"unknown endpoint id {endpoint_id!r}: only the built-in "
                f"{OPENAI_PUBLIC_ENDPOINT_ID} resolves"
            )
        return cls._TRUSTED_ENDPOINT

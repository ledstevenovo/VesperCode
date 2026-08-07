"""T16.1 legacy step 16.B: exact segment-to-OpenAI body serialization.

``serialize_openai_request`` maps one authorized
``OpenAIPreparedModelRequestV1`` into the exact closed
``OpenAIRequestBodyV1``: each message's segments are concatenated in order
with no implicit separator and no source metadata (SPEC §4.4.4), the
frozen ``max_output_tokens`` and fixed JSON-object response format pass
through, and the ``ABSENT``/``PRESENT`` optional fixed parameters map
``value_milli / 1000`` to the vendor float values (T06.3 behavior 3).
``openai_request_body_bytes`` returns the exact final UTF-8 request-body
bytes the transport sends — the byte length that must equal the
request's ``canonical_byte_count``.  Credential, Grant, and network
behavior remain out of scope (GREEN-4).
"""

from __future__ import annotations

from vespercode.contracts.optional import AbsentV1
from vespercode.llm.prepared_request import (
    OpenAIRequestBodyMessageV1,
    OpenAIRequestBodyV1,
    OpenAIResponseFormatV1,
    OptionalBodySeedV1,
    OptionalBodyTemperatureV1,
    OptionalBodyTopPV1,
    OpenAIPreparedModelRequestV1,
    PresentBodySeedV1,
    PresentBodyTemperatureV1,
    PresentBodyTopPV1,
    _openai_body_bytes,
)


def serialize_openai_request(
    request: OpenAIPreparedModelRequestV1,
) -> OpenAIRequestBodyV1:
    """Serialize *request* into the exact closed vendor request body.

    Every message's segment contents are joined in order with no implicit
    separator; source categories, paths, digests, and byte counts never
    enter the body (SPEC §4.4.4 "不把来源元数据写入 HTTP 正文").
    """
    messages = tuple(
        OpenAIRequestBodyMessageV1(
            role="system" if message.role == "SYSTEM" else "user",
            content="".join(segment.content for segment in message.segments),
        )
        for message in request.messages
    )
    fixed = request.fixed_parameters
    temperature: OptionalBodyTemperatureV1
    if fixed.temperature.kind == "ABSENT":
        temperature = AbsentV1(kind="ABSENT")
    else:
        temperature = PresentBodyTemperatureV1(
            kind="PRESENT", value=fixed.temperature.value_milli / 1000
        )
    top_p: OptionalBodyTopPV1
    if fixed.top_p.kind == "ABSENT":
        top_p = AbsentV1(kind="ABSENT")
    else:
        top_p = PresentBodyTopPV1(kind="PRESENT", value=fixed.top_p.value_milli / 1000)
    seed: OptionalBodySeedV1
    if fixed.seed.kind == "ABSENT":
        seed = AbsentV1(kind="ABSENT")
    else:
        seed = PresentBodySeedV1(kind="PRESENT", value=fixed.seed.value)
    return OpenAIRequestBodyV1(
        model=request.model,
        messages=messages,
        max_output_tokens=fixed.max_output_tokens,
        temperature=temperature,
        top_p=top_p,
        seed=seed,
        response_format=OpenAIResponseFormatV1(type="json_object"),
    )


def openai_request_body_bytes(
    request: OpenAIPreparedModelRequestV1,
) -> bytes:
    """The exact final UTF-8 request-body bytes the transport sends.

    Byte-identical to the length the request contract binds as
    ``canonical_byte_count`` (the shared encoder lives in the
    prepared-request module so the two can never drift).
    """
    return _openai_body_bytes(request)

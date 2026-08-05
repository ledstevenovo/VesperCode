"""T16.1 legacy step 16.B: the single-call trusted OpenAI adapter.

``OpenAILLMAdapter`` is unbound and cannot generate; ``bind`` accepts only
a Task 15.E ``DisclosureAuthorizationRecordV1`` plus a fresh Task 27.B
``SecretCredentialV1`` wrapper supplied for this call and returns the
bound adapter.  ``BoundOpenAILLMAdapterV1.generate`` verifies the request
is exactly the authorized request, derives the sole trusted URL from the
built-in ``OpenAIEndpointV1`` map (never a custom URL, environment
credential, alternate endpoint, retry policy, or redirect replay), sends
the exact serialized body once through the injectable transport, and
returns only ``ModelResponse`` or raises one bounded typed
``OpenAITransportFailure`` — responses and failures stay bounded and
redacted, and a cross-origin redirect fails with ``LLM_ENDPOINT_MISMATCH``
without a second send (SPEC §4.4.4, §6.3; card GREEN-1..GREEN-4).
"""

from __future__ import annotations

import hashlib
import json
from typing import Annotated, Final, Literal, Mapping, Protocol, TypeAlias

from pydantic import BaseModel, ConfigDict, Field, Strict, field_validator

from src.vespercode.credentials.port import SecretCredentialV1
from src.vespercode.governance.disclosure_ledger import (
    DisclosureAuthorizationRecordV1,
)
from src.vespercode.llm.base import ModelResponse, _MAX_RESPONSE_TEXT_BYTES
from src.vespercode.llm.openai_serializer import openai_request_body_bytes
from src.vespercode.llm.prepared_request import OpenAIPreparedModelRequestV1
from src.vespercode.profiles.endpoints import (
    OpenAIEndpointRegistry,
    OpenAIEndpointV1,
)

# The one chat-completions path appended to the trusted base path.  The
# URL is always derived from the built-in endpoint record — never from
# environment, config, requests, or DNS text (SPEC §4.4.3).
_CHAT_COMPLETIONS_PATH: Final = "/chat/completions"
# One closed bound on the raw transport response body and one fixed read
# timeout on the real transport (bounded responses; the orchestrator's
# budgets apply upstream).
_MAX_RAW_RESPONSE_BODY_BYTES: Final = 1024 * 1024
_READ_TIMEOUT_SECONDS: Final = 60


class LLMTransportError(ValueError):
    """One bounded typed transport-level failure (network, timeout, I/O).

    The message is static and bounded; transports must never carry a
    secret, request body, or URL into it.
    """


class LLMTransportResultV1(BaseModel):
    """One bounded transport result: status, ordered headers, and body.

    The adapter enforces the closed status/body/parse bounds after the
    result; the raw body is never logged or included in a failure.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)
    status_code: Annotated[int, Strict(), Field(ge=100, le=599)]
    headers: tuple[tuple[str, str], ...]
    body: bytes

    @field_validator("status_code", mode="before")
    @classmethod
    def _status_code_is_exact_int(cls, value: object) -> object:
        if not isinstance(value, int) or isinstance(value, bool):
            raise ValueError("status_code must be an integer HTTP status")
        return value


class LLMTransportV1(Protocol):
    """The injectable one-call transport port (SPEC §6.1 test doubles).

    ``post`` performs exactly one attempt; the adapter never retries and
    never follows redirects.  The real transport sends to the URL derived
    from the trusted endpoint record only.
    """

    def post(
        self,
        url: str,
        headers: Mapping[str, str],
        body: bytes,
    ) -> LLMTransportResultV1: ...


OpenAITransportErrorCodeV1: TypeAlias = Literal[
    "LLM_CALL_FAILED",
    "LLM_ENDPOINT_MISMATCH",
    "INTERNAL_ERROR",
]
"""The closed adapter-failure codes (SPEC §4.2.8; the control plane maps
them into ``LLMCallResultV1`` per Task 25.C)."""


class OpenAITransportFailure(ValueError):
    """One bounded typed OpenAI adapter failure.

    The message is exactly the stable error code — never a body, secret,
    URL, or response text — so failures stay redacted by construction.
    """

    def __init__(self, error_code: OpenAITransportErrorCodeV1) -> None:
        super().__init__(error_code)
        self.error_code = error_code


class _HttpxLLMTransport:
    """The real transport: one streaming httpx POST, no redirect follow.

    The client is constructed inside the call with ``follow_redirects=False``
    so a redirect is returned as a plain status the adapter rejects; the
    body is streamed and the read aborts as soon as the closed raw-body
    bound is exceeded, so a hostile peer can never force unbounded memory
    (card GREEN-2 "bounded responses"); the httpx import is lazy so the
    adapter module never imports a network client at module load (gate
    environment boundary, T18.1 precedent).
    """

    def post(
        self,
        url: str,
        headers: Mapping[str, str],
        body: bytes,
    ) -> LLMTransportResultV1:
        try:
            status_code, response_headers, response_body = _stream_bounded_httpx(
                url, headers, body
            )
        except LLMTransportError:
            raise
        except Exception as exc:  # noqa: BLE001 - network/timeout/I/O fail closed
            raise LLMTransportError("transport call failed") from exc
        return LLMTransportResultV1(
            status_code=status_code,
            headers=response_headers,
            body=response_body,
        )


def _stream_bounded_httpx(
    url: str,
    headers: Mapping[str, str],
    body: bytes,
) -> tuple[int, tuple[tuple[str, str], ...], bytes]:
    """One streaming POST that aborts once the closed raw-body bound is hit.

    The httpx import is lazy so the adapter module never imports a network
    client at module load (gate environment boundary, T18.1 precedent);
    the streamed read accumulates chunks and aborts with the bounded
    transport error as soon as the raw-body bound is exceeded.
    """
    try:
        import httpx
    except Exception as exc:  # noqa: BLE001 - fail closed, no network use
        raise LLMTransportError("httpx is not available") from exc
    with httpx.Client(timeout=_READ_TIMEOUT_SECONDS, follow_redirects=False) as client:
        with client.stream(
            "POST", url, headers=dict(headers), content=body
        ) as response:
            chunks: list[bytes] = []
            total = 0
            for chunk in response.iter_bytes():
                total += len(chunk)
                if total > _MAX_RAW_RESPONSE_BODY_BYTES:
                    raise LLMTransportError("response body exceeds the closed bound")
                chunks.append(chunk)
            return (
                response.status_code,
                tuple(response.headers.items()),
                b"".join(chunks),
            )


class OpenAILLMAdapter:
    """The unbound OpenAI adapter (SPEC §4.2.1; card GREEN-1).

    The adapter carries only the injectable transport (the real httpx
    transport when none is supplied) and cannot generate: ``bind`` is the
    sole path to a ``BoundOpenAILLMAdapterV1``.
    """

    def __init__(self, transport: LLMTransportV1 | None = None) -> None:
        self._transport = transport if transport is not None else _HttpxLLMTransport()

    def bind(
        self,
        authorization: DisclosureAuthorizationRecordV1,
        credential: SecretCredentialV1,
    ) -> BoundOpenAILLMAdapterV1:
        """Bind the Task 15.E authorization and fresh Task 27.B secret.

        The trusted endpoint is resolved from the built-in map only; the
        bound adapter never accepts a base URL, alternate endpoint, retry
        policy, or environment credential (card GREEN-2 boundary).
        """
        endpoint = OpenAIEndpointRegistry.resolve(authorization.endpoint_id)
        return BoundOpenAILLMAdapterV1(
            transport=self._transport,
            authorization=authorization,
            credential=credential,
            endpoint=endpoint,
        )


class BoundOpenAILLMAdapterV1:
    """One freshly bound adapter: at most one non-retried trusted call.

    ``generate`` verifies the request is exactly the authorized request
    (SPEC §4.4.4: the record proves the exact request was authorized
    before the call), derives the sole trusted URL from the built-in
    endpoint record, reveals the fresh credential once for the header
    (never logged), sends the exact serialized body exactly once, and
    returns only ``ModelResponse`` or one bounded typed failure.
    """

    __slots__ = ("_transport", "_authorization", "_credential", "_endpoint")

    def __init__(
        self,
        *,
        transport: LLMTransportV1,
        authorization: DisclosureAuthorizationRecordV1,
        credential: SecretCredentialV1,
        endpoint: OpenAIEndpointV1,
    ) -> None:
        self._transport = transport
        self._authorization = authorization
        self._credential = credential
        self._endpoint = endpoint

    def generate(self, request: OpenAIPreparedModelRequestV1) -> ModelResponse:
        """Call the sole trusted endpoint once and return the response.

        A request/authorization identity mismatch fails closed before any
        transport attempt; a cross-origin redirect fails with
        ``LLM_ENDPOINT_MISMATCH`` and is never followed or re-sent; every
        other transport, HTTP, parse, or bound violation fails with
        ``LLM_CALL_FAILED`` — all with zero retries (SPEC §4.4.4, §4.2.8).
        """
        if request.digest != self._authorization.request_digest:
            raise OpenAITransportFailure("INTERNAL_ERROR")
        if request.endpoint_id != self._authorization.endpoint_id:
            # SPEC §4.4.4: an OpenAI endpoint/effective-target mismatch is
            # always LLM_ENDPOINT_MISMATCH.  Unreachable through bind()
            # (which resolves the authorization's endpoint through the
            # built-in registry) and the request's closed Literal, but kept
            # as defense-in-depth before any transport attempt.
            raise OpenAITransportFailure("LLM_ENDPOINT_MISMATCH")
        url = (
            f"{self._endpoint.scheme}://{self._endpoint.host}:"
            f"{self._endpoint.effective_port}{self._endpoint.base_path}"
            f"{_CHAT_COMPLETIONS_PATH}"
        )
        body = openai_request_body_bytes(request)
        headers = {
            "Authorization": f"Bearer {self._credential.reveal()}",
            "Content-Type": "application/json",
        }
        try:
            result = self._transport.post(url, headers, body)
        except Exception as exc:  # noqa: BLE001 - fail closed, no retry
            raise OpenAITransportFailure("LLM_CALL_FAILED") from exc
        if 300 <= result.status_code < 400:
            # A redirect — same- or cross-origin — means the request was
            # not delivered to the trusted endpoint; never follow it and
            # never send the body a second time (SPEC §4.4.4).
            raise OpenAITransportFailure("LLM_ENDPOINT_MISMATCH")
        if result.status_code != 200:
            raise OpenAITransportFailure("LLM_CALL_FAILED")
        if len(result.body) > _MAX_RAW_RESPONSE_BODY_BYTES:
            raise OpenAITransportFailure("LLM_CALL_FAILED")
        return _parse_openai_response(result.body)


def _parse_openai_response(raw: bytes) -> ModelResponse:
    """Parse one bounded vendor response into the closed ``ModelResponse``.

    Any malformed, empty, unknown, or oversized content fails closed with
    the bounded typed failure; the response text is bounded to the closed
    64 KiB response contract.
    """
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise OpenAITransportFailure("LLM_CALL_FAILED") from exc
    if not isinstance(payload, dict):
        raise OpenAITransportFailure("LLM_CALL_FAILED")
    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices:
        raise OpenAITransportFailure("LLM_CALL_FAILED")
    first = choices[0]
    if not isinstance(first, dict):
        raise OpenAITransportFailure("LLM_CALL_FAILED")
    message = first.get("message")
    if not isinstance(message, dict):
        raise OpenAITransportFailure("LLM_CALL_FAILED")
    content = message.get("content")
    if not isinstance(content, str) or content == "":
        raise OpenAITransportFailure("LLM_CALL_FAILED")
    raw_text = content.encode("utf-8")
    if len(raw_text) > _MAX_RESPONSE_TEXT_BYTES:
        raise OpenAITransportFailure("LLM_CALL_FAILED")
    return ModelResponse(
        schema_version=1,
        text=content,
        text_digest=hashlib.sha256(raw_text).hexdigest(),
        byte_count=len(raw_text),
    )

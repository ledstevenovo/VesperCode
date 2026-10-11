"""The real OpenAI-compatible streaming v2 LLM adapter (offline-testable).

``V2OpenAICompatLLM`` implements the v2 boundary (``generate``, ``stream``,
``stream_events``) against any OpenAI-compatible ``/chat/completions``
SSE endpoint — the verified default is LongCat
(``https://api.longcat.chat/openai/v1``, model ``LongCat-2.5-Preview``;
see README "真实 key 配置").  Design boundaries:

- the transport is injectable (``V2OpenAIStreamTransport``: one POST that
  yields raw byte chunks); the real transport lazily imports httpx with
  ``follow_redirects=False`` and a fixed read timeout, mirroring the
  bounded-read discipline of the v1 adapter — but this module never
  imports a v1 contract type;
- the SSE reader is incremental (split lines, ``data:`` payloads only)
  and fails closed on the closed bounds: a stream exceeding
  ``_MAX_STREAM_BYTES`` or any transport exception maps onto the typed
  ``V2OpenAIAdapterError`` with a static message — no secret, URL,
  header, or body fragment ever reaches an exception text;
- termination is the standard double-safeguard only: a chunk carrying a
  ``finish_reason`` or the ``data: [DONE]`` sentinel ends the stream;
  the vendor-specific ``lastOne`` flag is ignored;
- LongCat's chain-of-thought travels on its own typed channel:
  ``reasoning_content`` increments are yielded as
  ``V2StreamEvent("reasoning", ...)`` (rendered muted by the TUI) and
  never mix into the action text; an empty ``content`` string (the
  observed first chunk) emits nothing;
- the API key is read once at construction from an injectable provider
  (default: the ``VESPERCODE_V2_API_KEY`` environment variable) and
  only ever placed into the Authorization header of the transport call;
  it is never printed, logged, embedded in a message body, or written
  to memory.  A missing key fails closed with configuration guidance.
"""

from __future__ import annotations

import codecs
import json
import os
from typing import Any, Callable, Iterator, Mapping, Protocol

from vespercode.llm.v2 import V2LLMRequest, V2StreamEvent

V2_OPENAI_API_KEY_ENV = "VESPERCODE_V2_API_KEY"
V2_OPENAI_BASE_URL_ENV = "VESPERCODE_V2_BASE_URL"
V2_OPENAI_MODEL_ENV = "VESPERCODE_V2_MODEL"

V2_OPENAI_DEFAULT_BASE_URL = "https://api.longcat.chat/openai/v1"
V2_OPENAI_DEFAULT_MODEL = "LongCat-2.5-Preview"

_MAX_STREAM_BYTES = 1024 * 1024
_READ_TIMEOUT_SECONDS = 60
_MAX_CONTEXT_ENTRY_CHARS = 8000

_V2_ACTION_SYSTEM_PROMPT = (
    "You are a coding agent working inside the VesperCode v2 harness. "
    "Reply with exactly one JSON object and nothing else — no markdown, "
    "no explanations: "
    '{"action_type": "REPLACE", "path": "<file>", "content": "<full new '
    'file content>"} stages one file replacement, or {"action_type": '
    '"DONE"} ends the task. Choose the smallest file edits that finish '
    "the task."
)

_V2_CONFIG_GUIDANCE = (
    "no v2 OpenAI-compatible API key is configured; set the user-level "
    f"environment variable {V2_OPENAI_API_KEY_ENV} (never commit it, never "
    "pass it on a command line or into a file), or inject an "
    "api_key_provider; see README 'Real key setup'"
)

_V2_REQUEST_TEMPLATE = {
    "stream": True,
}


class V2OpenAIAdapterError(RuntimeError):
    """One bounded typed adapter failure with a static message.

    ``code`` is exactly ``CONFIG_MISSING`` (setup guidance, no secret)
    or ``LLM_CALL_FAILED`` (any transport, HTTP, or bound failure).  The
    message never carries the key, the URL, headers, or body fragments.
    """

    def __init__(self, code: str) -> None:
        if code == "CONFIG_MISSING":
            message = _V2_CONFIG_GUIDANCE
        elif code == "LLM_CALL_FAILED":
            message = "LLM call failed"
        else:
            raise ValueError("unknown v2 OpenAI adapter error code")
        super().__init__(message)
        self.code = code


class V2OpenAIStreamTransport(Protocol):
    """The injectable streaming POST port (one attempt, no retries).

    Implementations yield the raw response body as ordered byte chunks
    after the HTTP status is verified; any failure (network, timeout,
    non-success status) is raised, never returned.
    """

    def stream_post(
        self,
        url: str,
        headers: Mapping[str, str],
        body: bytes,
    ) -> Iterator[bytes]: ...


class _HttpxStreamTransport:
    """The real transport: one streaming httpx POST, no redirect follow.

    The httpx import is lazy so this module never imports a network
    client at load time (offline unit suites import it freely); the
    client never follows redirects and applies one fixed read timeout.
    """

    def stream_post(
        self,
        url: str,
        headers: Mapping[str, str],
        body: bytes,
    ) -> Iterator[bytes]:
        try:
            import httpx
        except Exception as exc:  # noqa: BLE001 - fail closed, no network use
            raise V2OpenAIAdapterError("LLM_CALL_FAILED") from exc
        with httpx.Client(
            timeout=_READ_TIMEOUT_SECONDS, follow_redirects=False
        ) as client:
            with client.stream(
                "POST", url, headers=dict(headers), content=body
            ) as response:
                if response.status_code != 200:
                    raise V2OpenAIAdapterError("LLM_CALL_FAILED")
                for chunk in response.iter_bytes():
                    yield chunk


def _env_api_key() -> str | None:
    value = os.environ.get(V2_OPENAI_API_KEY_ENV)
    return value if value else None


class V2OpenAICompatLLM:
    """The streaming OpenAI-compatible v2 LLM boundary.

    Resolution order for every setting: explicit constructor argument,
    then the environment variable, then the verified default.
    """

    def __init__(
        self,
        *,
        api_key_provider: Callable[[], str | None] | None = None,
        base_url: str | None = None,
        model: str | None = None,
        transport: V2OpenAIStreamTransport | None = None,
    ) -> None:
        provider = api_key_provider if api_key_provider is not None else _env_api_key
        self._api_key = provider()
        if not self._api_key:
            raise V2OpenAIAdapterError("CONFIG_MISSING")
        self._base_url = (
            base_url
            or os.environ.get(V2_OPENAI_BASE_URL_ENV)
            or V2_OPENAI_DEFAULT_BASE_URL
        ).rstrip("/")
        self._model = (
            model or os.environ.get(V2_OPENAI_MODEL_ENV) or V2_OPENAI_DEFAULT_MODEL
        )
        self._transport = (
            transport if transport is not None else _HttpxStreamTransport()
        )

    # ------------------------------------------------------------------
    # the v2 boundary
    # ------------------------------------------------------------------

    def generate(self, request: V2LLMRequest) -> dict[str, Any]:
        text = "".join(self.stream(request))
        try:
            action = json.loads(text)
        except json.JSONDecodeError as exc:
            raise V2OpenAIAdapterError("LLM_CALL_FAILED") from exc
        if not isinstance(action, dict):
            raise V2OpenAIAdapterError("LLM_CALL_FAILED")
        return action

    def stream(self, request: V2LLMRequest) -> Iterator[str]:
        for event in self.stream_events(request):
            if event.kind == "content":
                yield event.text

    def stream_events(self, request: V2LLMRequest) -> Iterator[V2StreamEvent]:
        """One streaming turn: typed reasoning/content increments."""

        url = f"{self._base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        body = json.dumps(self._request_payload(request)).encode("utf-8")
        try:
            yield from self._iter_stream_events(
                self._transport.stream_post(url, headers, body)
            )
        except V2OpenAIAdapterError:
            raise
        except Exception as exc:  # noqa: BLE001 - fail closed, static message
            raise V2OpenAIAdapterError("LLM_CALL_FAILED") from exc

    # ------------------------------------------------------------------
    # request assembly and SSE reading
    # ------------------------------------------------------------------

    def _request_payload(self, request: V2LLMRequest) -> dict[str, Any]:
        context_lines = [
            f"- {entry[:_MAX_CONTEXT_ENTRY_CHARS]}"
            for entry in request.context
            if entry
        ]
        user_content = (
            request.task
            if not context_lines
            else (request.task + "\n\nContext so far:\n" + "\n".join(context_lines))
        )
        payload: dict[str, Any] = {
            "model": self._model,
            "stream": _V2_REQUEST_TEMPLATE["stream"],
            "messages": [
                {"role": "system", "content": _V2_ACTION_SYSTEM_PROMPT},
                {"role": "user", "content": user_content},
            ],
        }
        return payload

    def _iter_stream_events(
        self, byte_stream: Iterator[bytes]
    ) -> Iterator[V2StreamEvent]:
        total = 0
        decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
        line_buffer = ""
        for chunk in byte_stream:
            total += len(chunk)
            if total > _MAX_STREAM_BYTES:
                raise V2OpenAIAdapterError("LLM_CALL_FAILED")
            line_buffer += decoder.decode(chunk)
            *complete_lines, line_buffer = line_buffer.split("\n")
            for line in complete_lines:
                event = self._event_from_sse_line(line)
                if isinstance(event, _StreamEnd):
                    return
                if event is not None:
                    yield event
        line_buffer += decoder.decode(b"", final=True)
        event = self._event_from_sse_line(line_buffer)
        if not isinstance(event, _StreamEnd) and event is not None:
            yield event

    @staticmethod
    def _event_from_sse_line(line: str) -> V2StreamEvent | _StreamEnd | None:
        """One SSE line -> one event, ``_STREAM_END``, or None (skip).

        Each ``data:`` payload carries one complete JSON chunk (the
        standard OpenAI-compatible wire format).  ``finish_reason`` and
        the ``[DONE]`` sentinel are the only terminators; ``lastOne``
        is ignored.
        """

        stripped = line.rstrip("\r")
        if not stripped.startswith("data:"):
            return None
        payload = stripped[len("data:") :].strip()
        if not payload:
            return None
        if payload == "[DONE]":
            return _STREAM_END
        try:
            chunk = json.loads(payload)
        except json.JSONDecodeError:
            return None
        if not isinstance(chunk, dict):
            return None
        choices = chunk.get("choices")
        if not isinstance(choices, list) or not choices:
            return None
        first = choices[0]
        if not isinstance(first, dict):
            return None
        delta = first.get("delta")
        if not isinstance(delta, dict):
            delta = {}
        reasoning = delta.get("reasoning_content")
        if isinstance(reasoning, str) and reasoning:
            return V2StreamEvent("reasoning", reasoning)
        content = delta.get("content")
        if isinstance(content, str) and content:
            return V2StreamEvent("content", content)
        if first.get("finish_reason"):
            return _STREAM_END
        return None


class _StreamEnd:
    """The closed end-of-stream signal (never a V2StreamEvent)."""

    __slots__ = ()


_STREAM_END = _StreamEnd()

__all__ = [
    "V2_OPENAI_API_KEY_ENV",
    "V2_OPENAI_BASE_URL_ENV",
    "V2_OPENAI_DEFAULT_BASE_URL",
    "V2_OPENAI_DEFAULT_MODEL",
    "V2OpenAIAdapterError",
    "V2OpenAICompatLLM",
    "V2OpenAIStreamTransport",
]

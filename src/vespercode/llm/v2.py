"""Low-level injectable v2 LLM boundary.

The boundary is duck-typed: ``generate`` is the one-call contract the
v2 engine has always consumed; ``stream`` is the optional token-level
extension.  Protocol shape (see ``loop.v2_engine.V2StreamingLLM``):

- ``stream(request) -> Iterator[str]`` yields the model output as
  ordered text increments whose concatenation parses as the JSON
  action object the engine dispatches;
- ``stream_events(request) -> Iterator[V2StreamEvent]`` is the typed
  variant: reasoning increments (chain-of-thought, rendered muted by
  the TUI) travel on their own ``"reasoning"`` kind so they can never
  be mistaken for action content;
- the default behavior for a generate()-only LLM is
  ``stream_via_generate``: the full serialized action yielded as one
  single chunk.  ``ScriptedLLMV2`` therefore stays drop-in compatible
  with zero changes, and the engine keeps calling ``generate``-backed
  bridges exactly once per turn.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Iterator


@dataclass(frozen=True, slots=True)
class V2LLMRequest:
    run_id: str
    task: str
    context: tuple[str, ...]


_V2_STREAM_EVENT_KINDS = ("reasoning", "content")


@dataclass(frozen=True, slots=True)
class V2StreamEvent:
    """One typed streaming increment.

    ``kind`` is exactly ``"reasoning"`` (thinking increments; never
    part of the action text) or ``"content"`` (increments of the JSON
    action object).  ``text`` may be the empty string; consumers simply
    forward it.
    """

    kind: str
    text: str

    def __post_init__(self) -> None:
        if self.kind not in _V2_STREAM_EVENT_KINDS:
            raise ValueError("stream event kind must be 'reasoning' or 'content'")
        if not isinstance(self.text, str):
            raise ValueError("stream event text must be a string")


class ScriptedLLMV2:
    """Deterministic offline adapter used by the v2 runtime and tests."""

    def __init__(self, actions: list[dict[str, Any]]) -> None:
        if not actions:
            raise ValueError("scripted LLM needs at least one action")
        self._actions = [dict(action) for action in actions]
        self._index = 0
        self.requests: list[V2LLMRequest] = []

    @property
    def contexts(self) -> list[tuple[str, ...]]:
        return [request.context for request in self.requests]

    def generate(self, request: V2LLMRequest) -> dict[str, Any]:
        self.requests.append(request)
        action = self._actions[min(self._index, len(self._actions) - 1)]
        self._index += 1
        return dict(action)


def stream_via_generate(llm: Any, request: V2LLMRequest) -> Iterator[str]:
    """The default stream for a generate()-only v2 LLM.

    Calls ``generate`` exactly once and yields the full serialized
    action as one single chunk — the documented default behavior of the
    streaming protocol ("no true token streaming").  LLM authors who
    want token-level streaming implement ``stream`` (or
    ``stream_events``) directly instead.
    """

    yield json.dumps(llm.generate(request))


class ScriptedStreamLLMV2:
    """Deterministic offline streaming mock for the v2 boundary.

    Splits each scripted action's JSON serialization into fixed-size
    token chunks; the optional ``reasoning`` text is emitted as one
    typed reasoning event before the content chunks of every turn, so
    the muted-thinking TUI rendering is demoable fully offline.
    """

    def __init__(
        self,
        actions: list[dict[str, Any]],
        *,
        chunk_size: int = 5,
        reasoning: str | None = None,
    ) -> None:
        if not actions:
            raise ValueError("scripted streaming LLM needs at least one action")
        if isinstance(chunk_size, bool) or not isinstance(chunk_size, int):
            raise ValueError("chunk_size must be a positive integer")
        if chunk_size < 1:
            raise ValueError("chunk_size must be a positive integer")
        if reasoning is not None and (not isinstance(reasoning, str) or not reasoning):
            raise ValueError("reasoning must be a non-empty string or None")
        self._actions = [dict(action) for action in actions]
        self._chunk_size = chunk_size
        self._reasoning = reasoning
        self._index = 0
        self.requests: list[V2LLMRequest] = []

    @property
    def contexts(self) -> list[tuple[str, ...]]:
        return [request.context for request in self.requests]

    def _next_turn_text(self, request: V2LLMRequest) -> str:
        self.requests.append(request)
        action = self._actions[min(self._index, len(self._actions) - 1)]
        self._index += 1
        return json.dumps(action)

    @staticmethod
    def _chunks(text: str, chunk_size: int) -> Iterator[str]:
        for start in range(0, len(text), chunk_size):
            yield text[start : start + chunk_size]

    def generate(self, request: V2LLMRequest) -> dict[str, Any]:
        text = self._next_turn_text(request)
        return dict(json.loads(text))

    def stream(self, request: V2LLMRequest) -> Iterator[str]:
        text = self._next_turn_text(request)
        yield from self._chunks(text, self._chunk_size)

    def stream_events(self, request: V2LLMRequest) -> Iterator[V2StreamEvent]:
        text = self._next_turn_text(request)
        if self._reasoning is not None:
            yield V2StreamEvent("reasoning", self._reasoning)
        for chunk in self._chunks(text, self._chunk_size):
            yield V2StreamEvent("content", chunk)


__all__ = [
    "ScriptedLLMV2",
    "ScriptedStreamLLMV2",
    "V2LLMRequest",
    "V2StreamEvent",
    "stream_via_generate",
]

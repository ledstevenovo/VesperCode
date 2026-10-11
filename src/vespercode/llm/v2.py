"""Low-level injectable v2 LLM boundary."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class V2LLMRequest:
    run_id: str
    task: str
    context: tuple[str, ...]


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


__all__ = ["ScriptedLLMV2", "V2LLMRequest"]

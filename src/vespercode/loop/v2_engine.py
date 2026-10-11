"""Small v2 agent loop: context, one call, parse, dispatch, feedback, stop."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol
from uuid import uuid4

from vespercode.llm.v2 import V2LLMRequest
from vespercode.memory.v2 import V2Memory
from vespercode.tools.v2_dispatcher import V2ToolDispatcher, V2ToolResult


class V2LLM(Protocol):
    def generate(self, request: V2LLMRequest) -> dict[str, Any]: ...


class V2ActionError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class V2LoopResult:
    status: str
    stop_reason: str
    turns: int
    results: tuple[V2ToolResult, ...]
    contexts: tuple[tuple[str, ...], ...]


class V2AgentLoop:
    def __init__(
        self,
        *,
        workspace: Path,
        llm: V2LLM,
        dispatcher: V2ToolDispatcher,
        memory: V2Memory,
        max_turns: int = 20,
    ) -> None:
        if max_turns < 1:
            raise ValueError("max_turns must be positive")
        self._workspace = workspace
        self._llm = llm
        self._dispatcher = dispatcher
        self._memory = memory
        self._max_turns = max_turns

    def run(self, task: str, *, run_id: str | None = None) -> V2LoopResult:
        current_run_id = run_id or str(uuid4())
        results: list[V2ToolResult] = []
        contexts: list[tuple[str, ...]] = []
        for turn in range(1, self._max_turns + 1):
            context = tuple(entry.text for entry in self._memory.select(current_run_id))
            contexts.append(context)
            try:
                raw_action = self._llm.generate(
                    V2LLMRequest(current_run_id, task, context)
                )
            except Exception:
                result = V2ToolResult("FAILED", "LLM call failed")
                results.append(result)
                return V2LoopResult(
                    "STOPPED", "LLM_CALL_FAILED", turn, tuple(results), tuple(contexts)
                )
            try:
                action = self._parse_action(raw_action)
            except V2ActionError as exc:
                result = V2ToolResult("FAILED", str(exc), error=exc)
                results.append(result)
                self._memory.remember(current_run_id, result.message, source="feedback")
                continue
            result = self._dispatcher.dispatch(action, self._workspace)
            results.append(result)
            if result.status == "DONE":
                return V2LoopResult(
                    "SUCCEEDED", "DONE", turn, tuple(results), tuple(contexts)
                )
            self._memory.remember(current_run_id, result.message, source="feedback")
        return V2LoopResult(
            "STOPPED", "MAX_TURNS", self._max_turns, tuple(results), tuple(contexts)
        )

    @staticmethod
    def _parse_action(action: dict[str, Any]) -> dict[str, object]:
        if not isinstance(action, dict):
            raise V2ActionError("model action must be an object")
        if "action_id" in action:
            raise V2ActionError("model-supplied action_id is forbidden")
        action_type = action.get("action_type")
        if action_type not in {"REPLACE", "DONE"}:
            raise V2ActionError("unknown or missing action_type")
        return action


__all__ = ["V2ActionError", "V2AgentLoop", "V2LoopResult"]

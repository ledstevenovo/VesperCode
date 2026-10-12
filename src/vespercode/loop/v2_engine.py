"""Small v2 agent loop: context, one call, parse, dispatch, feedback, stop.

The engine consumes the v2 LLM boundary through the streaming pipeline:
a structured-event stream (``stream_events``, reasoning typed apart from
content) is preferred, then the plain text stream (``stream``), and
finally the default full-text bridge over ``generate`` — so generate()-
only boundaries such as ``ScriptedLLMV2`` stay drop-in compatible with
zero changes and one full-text chunk per turn.  Deltas reach the caller
only through the optional ``on_delta``/``on_reasoning`` callbacks; with
no callbacks attached the observable behavior is identical to the
pre-streaming loop.  Cancellation is a caller concern: an exception
raised from a callback (e.g. ``KeyboardInterrupt`` from a TUI cancel)
propagates out of ``run`` because only ``Exception``-shaped LLM
failures map onto the ``LLM_CALL_FAILED`` stop.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterator, Protocol
from uuid import uuid4

from vespercode.llm.v2 import V2LLMRequest, V2StreamEvent, stream_via_generate
from vespercode.memory.v2 import V2Memory
from vespercode.tools.v2_dispatcher import V2ToolDispatcher, V2ToolResult


class V2LLM(Protocol):
    def generate(self, request: V2LLMRequest) -> dict[str, Any]: ...


class V2StreamingLLM(V2LLM, Protocol):
    """The optional token-level streaming extension of the v2 boundary.

    ``stream`` yields the model output as ordered text increments whose
    concatenation parses as the JSON action object.
    """

    def stream(self, request: V2LLMRequest) -> Iterator[str]: ...


class V2EventStreamLLM(V2LLM, Protocol):
    """The typed streaming extension: reasoning apart from content."""

    def stream_events(self, request: V2LLMRequest) -> Iterator[V2StreamEvent]: ...


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

    def run(
        self,
        task: str,
        *,
        run_id: str | None = None,
        on_delta: Callable[[str], None] | None = None,
        on_reasoning: Callable[[str], None] | None = None,
        on_result: Callable[[int, V2ToolResult], None] | None = None,
    ) -> V2LoopResult:
        current_run_id = run_id or str(uuid4())
        results: list[V2ToolResult] = []
        contexts: list[tuple[str, ...]] = []

        def record(turn: int, result: V2ToolResult) -> None:
            results.append(result)
            if on_result is not None:
                on_result(turn, result)

        for turn in range(1, self._max_turns + 1):
            context = tuple(entry.text for entry in self._memory.select(current_run_id))
            contexts.append(context)
            try:
                output_text = self._collect_llm_output(
                    V2LLMRequest(current_run_id, task, context),
                    on_delta=on_delta,
                    on_reasoning=on_reasoning,
                )
            except Exception as exc:
                result = V2ToolResult("FAILED", "LLM call failed", error=exc)
                record(turn, result)
                return V2LoopResult(
                    "STOPPED", "LLM_CALL_FAILED", turn, tuple(results), tuple(contexts)
                )
            try:
                raw_action = self._parse_streamed_text(output_text)
                action = self._parse_action(raw_action)
            except V2ActionError as exc:
                result = V2ToolResult("FAILED", str(exc), error=exc)
                record(turn, result)
                self._memory.remember(current_run_id, result.message, source="feedback")
                continue
            result = self._dispatcher.dispatch(action, self._workspace)
            record(turn, result)
            if result.status == "DONE":
                return V2LoopResult(
                    "SUCCEEDED", "DONE", turn, tuple(results), tuple(contexts)
                )
            self._memory.remember(current_run_id, result.message, source="feedback")
        return V2LoopResult(
            "STOPPED", "MAX_TURNS", self._max_turns, tuple(results), tuple(contexts)
        )

    def _collect_llm_output(
        self,
        request: V2LLMRequest,
        *,
        on_delta: Callable[[str], None] | None,
        on_reasoning: Callable[[str], None] | None,
    ) -> str:
        """One LLM turn through the streaming pipeline.

        Resolution order: typed event stream, plain text stream, then
        the default full-text bridge over ``generate``.  Returns the
        aggregated content text only — parsing it into the action
        object happens in ``run`` so an unparseable model output feeds
        the feedback path instead of stopping as an LLM failure.
        """

        events = getattr(self._llm, "stream_events", None)
        if callable(events):
            chunks: list[str] = []
            for event in events(request):
                if event.kind == "reasoning":
                    if on_reasoning is not None:
                        on_reasoning(event.text)
                    continue
                chunks.append(event.text)
                if on_delta is not None:
                    on_delta(event.text)
            return "".join(chunks)
        stream = getattr(self._llm, "stream", None)
        if callable(stream):
            chunks = []
            for delta in stream(request):
                chunks.append(delta)
                if on_delta is not None:
                    on_delta(delta)
            return "".join(chunks)
        chunks = []
        for delta in stream_via_generate(self._llm, request):
            chunks.append(delta)
            if on_delta is not None:
                on_delta(delta)
        return "".join(chunks)

    @staticmethod
    def _parse_streamed_text(text: str) -> Any:
        try:
            return json.loads(text)
        except json.JSONDecodeError as exc:
            raise V2ActionError("streamed model output is not valid JSON") from exc

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


__all__ = [
    "V2ActionError",
    "V2AgentLoop",
    "V2EventStreamLLM",
    "V2LoopResult",
    "V2StreamingLLM",
]

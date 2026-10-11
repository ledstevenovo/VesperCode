"""v2 token-level streaming LLM boundary (phase A).

Covers the streaming protocol of the v2 LLM boundary: the documented
default bridge for generate()-only LLMs (full text yielded as one
chunk, ``ScriptedLLMV2`` stays drop-in compatible with zero changes),
the deterministic scripted streaming mock, and the v2 engine's delta
forwarding through optional callbacks — with the no-callback behavior
byte-identical to the pre-streaming loop.
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from vespercode.llm.v2 import (
    ScriptedLLMV2,
    ScriptedStreamLLMV2,
    V2LLMRequest,
    V2StreamEvent,
    stream_via_generate,
)
from vespercode.loop.v2_engine import V2AgentLoop, V2LoopResult
from vespercode.memory.v2 import V2Memory
from vespercode.tools.v2_dispatcher import InMemoryWorkspacePort, V2ToolDispatcher


def _build_loop(llm: object, max_turns: int = 5) -> V2AgentLoop:
    return V2AgentLoop(
        workspace=Path(tempfile.gettempdir()),
        llm=llm,  # type: ignore[arg-type]
        dispatcher=V2ToolDispatcher(InMemoryWorkspacePort()),
        memory=V2Memory(),
        max_turns=max_turns,
    )


_REPLACE_ACTION = {
    "action_type": "REPLACE",
    "path": "src/example.py",
    "content": "fixed body\n",
}
_SCRIPTED_ACTIONS = [_REPLACE_ACTION, {"action_type": "DONE"}]


class StreamingProtocolDefaultTests(unittest.TestCase):
    """The default bridge: generate()-only LLMs stream one full chunk."""

    def test_scripted_llm_v2_stays_stream_free(self) -> None:
        llm = ScriptedLLMV2([{"action_type": "DONE"}])

        self.assertFalse(hasattr(llm, "stream"))
        self.assertFalse(hasattr(llm, "stream_events"))

    def test_stream_via_generate_yields_full_text_in_one_chunk(self) -> None:
        llm = ScriptedLLMV2(list(_SCRIPTED_ACTIONS))
        request = V2LLMRequest("run-1", "task", ())

        chunks = list(stream_via_generate(llm, request))

        self.assertEqual(len(chunks), 1)
        self.assertEqual(json.loads(chunks[0]), _REPLACE_ACTION)
        self.assertEqual(len(llm.requests), 1)
        self.assertIs(llm.requests[0], request)

    def test_stream_via_generate_advances_the_scripted_index(self) -> None:
        llm = ScriptedLLMV2(list(_SCRIPTED_ACTIONS))
        request = V2LLMRequest("run-1", "task", ())

        first = json.loads(next(iter(stream_via_generate(llm, request))))
        second = json.loads(next(iter(stream_via_generate(llm, request))))

        self.assertEqual(first, _REPLACE_ACTION)
        self.assertEqual(second, {"action_type": "DONE"})


class ScriptedStreamLLMV2Tests(unittest.TestCase):
    """The deterministic offline streaming mock."""

    def test_stream_yields_multiple_token_chunks(self) -> None:
        llm = ScriptedStreamLLMV2([_REPLACE_ACTION], chunk_size=4)
        request = V2LLMRequest("run-1", "task", ())

        chunks = list(llm.stream(request))

        self.assertGreater(len(chunks), 1)
        self.assertTrue(all(isinstance(chunk, str) for chunk in chunks))
        self.assertEqual(json.loads("".join(chunks)), _REPLACE_ACTION)
        self.assertEqual(len(llm.requests), 1)

    def test_stream_events_type_reasoning_then_content(self) -> None:
        llm = ScriptedStreamLLMV2(
            [_REPLACE_ACTION], chunk_size=6, reasoning="inspecting the failure"
        )
        request = V2LLMRequest("run-1", "task", ())

        events = list(llm.stream_events(request))

        self.assertEqual(
            events[0], V2StreamEvent("reasoning", "inspecting the failure")
        )
        content = [event for event in events if event.kind == "content"]
        self.assertGreater(len(content), 1)
        self.assertEqual(
            "".join(event.text for event in content), json.dumps(_REPLACE_ACTION)
        )

    def test_stream_events_without_reasoning_yields_content_only(self) -> None:
        llm = ScriptedStreamLLMV2([{"action_type": "DONE"}])

        events = list(llm.stream_events(V2LLMRequest("run-1", "task", ())))

        self.assertTrue(all(event.kind == "content" for event in events))
        self.assertEqual(
            json.loads("".join(event.text for event in events)),
            {"action_type": "DONE"},
        )

    def test_generate_matches_the_streamed_aggregate(self) -> None:
        llm = ScriptedStreamLLMV2([_REPLACE_ACTION], chunk_size=3)
        request = V2LLMRequest("run-1", "task", ())

        streamed = json.loads("".join(llm.stream(request)))
        generated = llm.generate(V2LLMRequest("run-2", "task", ()))

        self.assertEqual(streamed, generated)

    def test_constructor_validation(self) -> None:
        with self.assertRaises(ValueError):
            ScriptedStreamLLMV2([])
        with self.assertRaises(ValueError):
            ScriptedStreamLLMV2([{"action_type": "DONE"}], chunk_size=0)
        with self.assertRaises(ValueError):
            ScriptedStreamLLMV2([{"action_type": "DONE"}], chunk_size=True)
        with self.assertRaises(ValueError):
            ScriptedStreamLLMV2([{"action_type": "DONE"}], reasoning="")


class _EventStreamFailureLLM:
    """Streaming LLM whose event stream raises mid-iteration."""

    def __init__(self) -> None:
        self.started = False

    def generate(self, request: object) -> dict[str, object]:
        raise AssertionError("generate must not be called")

    def stream_events(self, request: object) -> object:
        return self

    def __iter__(self) -> object:
        return self

    def __next__(self) -> V2StreamEvent:
        if not self.started:
            self.started = True
            return V2StreamEvent("content", '{"action_type": ')
        raise RuntimeError("stream blew up mid-turn")


class _PlainStreamFailureLLM:
    """stream()-only LLM whose stream raises immediately."""

    def generate(self, request: object) -> dict[str, object]:
        raise AssertionError("generate must not be called")

    def stream(self, request: object) -> object:
        raise RuntimeError("stream blew up immediately")
        yield ""  # pragma: no cover - makes this a generator function


class _CancelOnFirstDeltaLLM:
    """stream()-only LLM used to prove cancellation propagates."""

    def generate(self, request: object) -> dict[str, object]:
        raise AssertionError("generate must not be called")

    def stream(self, request: object) -> object:
        yield '{"action_type": "DONE"}'


class V2EngineStreamingTests(unittest.TestCase):
    """The engine forwards deltas through optional callbacks."""

    def test_engine_forwards_content_deltas_and_keeps_the_result_identical(
        self,
    ) -> None:
        deltas: list[str] = []
        loop = _build_loop(ScriptedStreamLLMV2(list(_SCRIPTED_ACTIONS), chunk_size=5))

        streamed = loop.run(
            "fix the example",
            run_id="run-stream",
            on_delta=deltas.append,
        )
        loop_legacy = _build_loop(ScriptedLLMV2(list(_SCRIPTED_ACTIONS)))
        legacy = loop_legacy.run("fix the example", run_id="run-legacy")

        self.assertGreater(len(deltas), 1)
        self.assertEqual(
            "".join(deltas),
            json.dumps(_REPLACE_ACTION) + json.dumps({"action_type": "DONE"}),
            "the delta stream is exactly the per-turn action JSON texts",
        )
        self.assertEqual(streamed.status, legacy.status)
        self.assertEqual(streamed.stop_reason, legacy.stop_reason)
        self.assertEqual(streamed.turns, legacy.turns)
        self.assertEqual(
            [(result.status, result.message) for result in streamed.results],
            [(result.status, result.message) for result in legacy.results],
        )

    def test_engine_reasoning_callback_receives_only_reasoning(self) -> None:
        reasoning: list[str] = []
        deltas: list[str] = []
        loop = _build_loop(
            ScriptedStreamLLMV2(
                list(_SCRIPTED_ACTIONS), chunk_size=5, reasoning="thinking it through"
            )
        )

        result = loop.run(
            "fix the example",
            run_id="run-reasoning",
            on_delta=deltas.append,
            on_reasoning=reasoning.append,
        )

        self.assertEqual(reasoning, ["thinking it through", "thinking it through"])
        self.assertTrue(
            all("thinking it through" not in delta for delta in deltas),
            "reasoning must never leak into the content channel",
        )
        self.assertEqual(result.status, "SUCCEEDED")

    def test_engine_without_callbacks_behaves_like_the_legacy_loop(self) -> None:
        loop = _build_loop(ScriptedStreamLLMV2(list(_SCRIPTED_ACTIONS), chunk_size=5))

        result = loop.run("fix the example", run_id="run-quiet")

        self.assertIsInstance(result, V2LoopResult)
        self.assertEqual(result.status, "SUCCEEDED")
        self.assertEqual(result.stop_reason, "DONE")
        self.assertEqual(result.turns, 2)

    def test_engine_generate_only_llm_keeps_legacy_single_call_behavior(
        self,
    ) -> None:
        deltas: list[str] = []
        llm = ScriptedLLMV2(list(_SCRIPTED_ACTIONS))
        loop = _build_loop(llm)

        result = loop.run("fix the example", run_id="run-gen", on_delta=deltas.append)

        self.assertEqual(result.status, "SUCCEEDED")
        self.assertEqual(len(llm.requests), 2)
        self.assertEqual(
            len(deltas), 2, "generate-only LLM streams one full chunk per turn"
        )
        self.assertEqual(json.loads(deltas[0]), _REPLACE_ACTION)

    def test_engine_event_stream_failure_maps_to_llm_call_failed(self) -> None:
        loop = _build_loop(_EventStreamFailureLLM(), max_turns=3)

        result = loop.run("explode", run_id="run-event-fail", on_delta=str.upper)

        self.assertEqual(result.status, "STOPPED")
        self.assertEqual(result.stop_reason, "LLM_CALL_FAILED")
        self.assertEqual(result.results[0].status, "FAILED")
        self.assertIn("LLM call failed", result.results[0].message)

    def test_engine_plain_stream_failure_maps_to_llm_call_failed(self) -> None:
        loop = _build_loop(_PlainStreamFailureLLM(), max_turns=3)

        result = loop.run("explode", run_id="run-plain-fail")

        self.assertEqual(result.status, "STOPPED")
        self.assertEqual(result.stop_reason, "LLM_CALL_FAILED")

    def test_engine_invalid_streamed_json_feeds_back_and_stops_on_max_turns(
        self,
    ) -> None:
        class GarbageStreamLLM:
            def generate(self, request: object) -> dict[str, object]:
                raise AssertionError("generate must not be called")

            def stream(self, request: object) -> object:
                yield "not json at all"

        loop = _build_loop(GarbageStreamLLM(), max_turns=1)

        result = loop.run("garbage", run_id="run-garbage")

        self.assertEqual(result.status, "STOPPED")
        self.assertEqual(result.stop_reason, "MAX_TURNS")
        self.assertEqual(result.results[0].status, "FAILED")
        self.assertIn("not valid JSON", result.results[0].message)

    def test_engine_cancellation_interrupt_propagates_from_the_delta_callback(
        self,
    ) -> None:
        loop = _build_loop(_CancelOnFirstDeltaLLM(), max_turns=3)

        def cancel_on_first_delta(delta: str) -> None:
            raise KeyboardInterrupt

        with self.assertRaises(KeyboardInterrupt):
            loop.run(
                "cancel me",
                run_id="run-cancel",
                on_delta=cancel_on_first_delta,
            )


class V2EngineTurnResultTests(unittest.TestCase):
    """The engine reports each turn's outcome through the optional hook."""

    def test_on_result_fires_once_per_turn_in_order(self) -> None:
        reported: list[tuple[int, str, str]] = []
        loop = _build_loop(ScriptedLLMV2(list(_SCRIPTED_ACTIONS)))

        result = loop.run(
            "fix the example",
            run_id="run-turns",
            on_result=lambda turn, res: reported.append(
                (turn, res.status, res.message)
            ),
        )

        self.assertEqual(result.status, "SUCCEEDED")
        self.assertEqual(
            reported,
            [
                (1, "SUCCESS", "replaced src/example.py"),
                (2, "DONE", "model requested stop"),
            ],
        )

    def test_on_result_fires_for_parse_failure_feedback(self) -> None:
        reported: list[tuple[int, str]] = []
        loop = _build_loop(
            ScriptedLLMV2([{"action_type": "REPLACE", "action_id": "model-owned"}]),
            max_turns=1,
        )

        result = loop.run(
            "bad model",
            run_id="run-parse-fail",
            on_result=lambda turn, res: reported.append((turn, res.status)),
        )

        self.assertEqual(result.stop_reason, "MAX_TURNS")
        self.assertEqual(reported, [(1, "FAILED")])

    def test_on_result_fires_for_llm_call_failure(self) -> None:
        reported: list[tuple[int, str, str]] = []
        loop = _build_loop(_PlainStreamFailureLLM(), max_turns=3)

        result = loop.run(
            "explode",
            run_id="run-llm-fail",
            on_result=lambda turn, res: reported.append(
                (turn, res.status, res.message)
            ),
        )

        self.assertEqual(result.stop_reason, "LLM_CALL_FAILED")
        self.assertEqual(reported, [(1, "FAILED", "LLM call failed")])


if __name__ == "__main__":
    unittest.main()

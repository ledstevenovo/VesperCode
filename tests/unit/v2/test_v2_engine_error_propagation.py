"""P1-1/M1 regression: the engine must not fold exception details away.

Before the fix, ``V2AgentLoop.run``'s broad ``except Exception`` around
the LLM call collapsed programming errors — an ``AttributeError`` from
a buggy LLM object, a broken delta callback, a ``join`` ``TypeError`` —
into a static ``LLM_CALL_FAILED`` result whose ``error`` was ``None``:
the exception class name and message were lost, even though the adjacent
``V2ActionError`` branch already propagated ``error=exc`` (an asymmetric
omission).  These tests pin the propagation contract: ``stop_reason``
stays ``LLM_CALL_FAILED`` and the static message stays ``"LLM call
failed"`` (no stop semantics move, no existing assertion breaks), but the
failure result now carries the original exception object in
``V2ToolResult.error`` so class name and message survive for triage.

The injection style deliberately mirrors the existing engine tests
(``tests/unit/v2/test_runtime.py`` BrokenLLM, ``test_v2_streaming.py``
_EventStreamFailureLLM / _PlainStreamFailureLLM / _CancelOnFirstDeltaLLM)
and uses no ``tempfile.TemporaryDirectory`` (see .round2-baseline
BASELINE.md §8): the loop never dispatches on these paths, so the
workspace path is never touched.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from vespercode.llm.v2 import ScriptedLLMV2, ScriptedStreamLLMV2, V2StreamEvent
from vespercode.loop.v2_engine import V2ActionError, V2AgentLoop
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


def _assert_llm_call_failed_with_details(
    case: unittest.TestCase,
    result: object,
    expected_message_part: str,
) -> None:
    """Assert the LLM_CALL_FAILED stop and the propagated exception.

    ``expected_message_part`` must appear in ``str(error)`` so the test
    proves the exception *message* survives, not just its class name.
    """

    case.assertEqual(result.status, "STOPPED")
    case.assertEqual(result.stop_reason, "LLM_CALL_FAILED")
    case.assertEqual(result.turns, 1)
    case.assertEqual(len(result.results), 1)
    failed = result.results[0]
    case.assertEqual(failed.status, "FAILED")
    case.assertEqual(failed.message, "LLM call failed")
    error = failed.error
    case.assertIsNotNone(
        error, "the engine must propagate the exception object, not None"
    )
    case.assertIsInstance(error, AttributeError)
    case.assertEqual(type(error).__name__, "AttributeError")
    case.assertIn(expected_message_part, str(error))


class _GenerateAttributeErrorLLM:
    """generate()-only LLM whose call raises an AttributeError."""

    def generate(self, request: object) -> dict[str, object]:
        raise AttributeError(
            "'_GenerateAttributeErrorLLM' object has no attribute 'chat'"
        )


class _StreamAttributeErrorLLM:
    """stream()-only LLM whose stream raises immediately."""

    def generate(self, request: object) -> dict[str, object]:
        raise AssertionError("generate must not be called")

    def stream(self, request: object) -> object:
        raise AttributeError("'NoneType' object has no attribute 'append'")
        yield ""  # pragma: no cover - makes this a generator function


class _EventStreamAttributeErrorLLM:
    """Event-stream LLM whose iterator raises mid-iteration."""

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
        raise AttributeError("'dict' object has no attribute 'message'")


class _GarbageStreamLLM:
    """stream()-only LLM that never yields valid JSON (control case)."""

    def generate(self, request: object) -> dict[str, object]:
        raise AssertionError("generate must not be called")

    def stream(self, request: object) -> object:
        yield "not json at all"


class ExceptionPropagationTests(unittest.TestCase):
    """Every pipeline path that hits ``except Exception`` keeps the details."""

    def test_generate_only_llm_attribute_error_is_propagated(self) -> None:
        loop = _build_loop(_GenerateAttributeErrorLLM(), max_turns=3)

        result = loop.run("explode", run_id="run-gen-attr")

        _assert_llm_call_failed_with_details(
            self,
            result,
            "'_GenerateAttributeErrorLLM' object has no attribute 'chat'",
        )

    def test_plain_stream_llm_attribute_error_is_propagated(self) -> None:
        loop = _build_loop(_StreamAttributeErrorLLM(), max_turns=3)

        result = loop.run("explode", run_id="run-stream-attr")

        _assert_llm_call_failed_with_details(
            self, result, "'NoneType' object has no attribute 'append'"
        )

    def test_event_stream_llm_attribute_error_is_propagated(self) -> None:
        loop = _build_loop(_EventStreamAttributeErrorLLM(), max_turns=3)

        result = loop.run("explode", run_id="run-events-attr")

        _assert_llm_call_failed_with_details(
            self, result, "'dict' object has no attribute 'message'"
        )

    def test_delta_callback_attribute_error_is_propagated(self) -> None:
        def broken_callback(delta: str) -> None:
            raise AttributeError("'NoneType' object has no attribute 'append'")

        loop = _build_loop(
            ScriptedStreamLLMV2([{"action_type": "DONE"}], chunk_size=4),
            max_turns=3,
        )

        result = loop.run(
            "explode", run_id="run-callback-attr", on_delta=broken_callback
        )

        _assert_llm_call_failed_with_details(
            self, result, "'NoneType' object has no attribute 'append'"
        )


class StopSemanticsGuardTests(unittest.TestCase):
    """The fix moves no stop semantics: guards that held before it."""

    def test_stop_reason_and_static_message_semantics_are_unchanged(self) -> None:
        class ProviderUnavailableLLM:
            def generate(self, request: object) -> dict[str, object]:
                raise RuntimeError("provider unavailable")

        loop = _build_loop(ProviderUnavailableLLM(), max_turns=5)

        result = loop.run("handle provider failure")

        self.assertEqual(result.status, "STOPPED")
        self.assertEqual(result.stop_reason, "LLM_CALL_FAILED")
        self.assertEqual(result.turns, 1)
        self.assertEqual(result.results[0].status, "FAILED")
        self.assertEqual(result.results[0].message, "LLM call failed")

    def test_keyboard_interrupt_still_propagates_unfolded(self) -> None:
        def cancel_on_first_delta(delta: str) -> None:
            raise KeyboardInterrupt

        loop = _build_loop(
            ScriptedStreamLLMV2([{"action_type": "DONE"}], chunk_size=4),
            max_turns=3,
        )

        with self.assertRaises(KeyboardInterrupt):
            loop.run(
                "cancel me", run_id="run-cancel-guard", on_delta=cancel_on_first_delta
            )

    def test_action_error_branch_still_carries_its_exception(self) -> None:
        loop = _build_loop(
            ScriptedLLMV2([{"action_type": "REPLACE", "action_id": "model-owned"}]),
            max_turns=1,
        )

        result = loop.run("bad model")

        self.assertEqual(result.status, "STOPPED")
        self.assertEqual(result.stop_reason, "MAX_TURNS")
        self.assertEqual(result.results[0].status, "FAILED")
        self.assertIsInstance(result.results[0].error, V2ActionError)

    def test_parse_errors_are_not_folded_into_llm_call_failed(self) -> None:
        loop = _build_loop(_GarbageStreamLLM(), max_turns=1)

        result = loop.run("garbage", run_id="run-garbage-guard")

        self.assertEqual(result.status, "STOPPED")
        self.assertEqual(result.stop_reason, "MAX_TURNS")
        self.assertIn("not valid JSON", result.results[0].message)


if __name__ == "__main__":
    unittest.main()

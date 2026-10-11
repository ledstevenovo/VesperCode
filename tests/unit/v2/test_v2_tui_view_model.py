"""The pure presentation state of the v2 streaming TUI (no textual)."""

from __future__ import annotations

import json
import unittest

from vespercode.tools.v2_dispatcher import V2ToolResult
from vespercode.tui.v2_launch import (
    DEFAULT_DEMO_TASK,
    V2TuiLaunchSpec,
    build_demo_llm_factory,
)
from vespercode.tui.v2_view_model import (
    V2_TUI_REASONING_STYLE,
    V2TuiTurnSummary,
    V2TuiViewModel,
)

_REPLACE_ACTION = {
    "action_type": "REPLACE",
    "path": "src/example.py",
    "content": "fixed body\n",
}


class V2TuiLaunchSpecTests(unittest.TestCase):
    def test_demo_factory_builds_a_streaming_scripted_llm(self) -> None:
        factory = build_demo_llm_factory()

        llm = factory()

        self.assertTrue(hasattr(llm, "stream_events"))
        self.assertTrue(hasattr(llm, "stream"))
        self.assertTrue(hasattr(llm, "generate"))

    def test_demo_task_is_non_empty(self) -> None:
        self.assertTrue(DEFAULT_DEMO_TASK)

    def test_spec_validation(self) -> None:
        import pathlib
        import tempfile

        with tempfile.TemporaryDirectory() as directory:
            workspace = pathlib.Path(directory)
            with self.assertRaises(TypeError):
                V2TuiLaunchSpec(
                    workspace=directory,  # not a Path
                    task="t",
                    max_turns=5,
                    llm_factory=build_demo_llm_factory,
                )
            with self.assertRaises(ValueError):
                V2TuiLaunchSpec(
                    workspace=workspace,
                    task="",
                    max_turns=5,
                    llm_factory=build_demo_llm_factory,
                )
            with self.assertRaises(ValueError):
                V2TuiLaunchSpec(
                    workspace=workspace,
                    task="t",
                    max_turns=0,
                    llm_factory=build_demo_llm_factory,
                )


class V2TuiViewModelStreamTests(unittest.TestCase):
    def test_deltas_accumulate_into_the_open_stream_block(self) -> None:
        vm = V2TuiViewModel()

        first = vm.handle_delta('{"action_type"')
        second = vm.handle_delta(': "REPLACE"')

        self.assertEqual(first.turn, 1)
        self.assertEqual(first.content_text, '{"action_type"')
        self.assertEqual(second.content_text, '{"action_type": "REPLACE"')
        self.assertEqual(second.reasoning_text, "")

    def test_reasoning_accumulates_separately_and_is_flagged_muted(self) -> None:
        vm = V2TuiViewModel()

        state = vm.handle_reasoning("checking protected paths")
        after_delta = vm.handle_delta('{"action_type"')

        self.assertEqual(state.reasoning_text, "checking protected paths")
        self.assertEqual(state.reasoning_style, V2_TUI_REASONING_STYLE)
        self.assertEqual(after_delta.reasoning_text, "checking protected paths")
        self.assertEqual(after_delta.content_text, '{"action_type"')

    def test_result_closes_the_block_and_summarizes_the_turn(self) -> None:
        vm = V2TuiViewModel()
        vm.handle_delta(json.dumps(_REPLACE_ACTION))

        summary = vm.handle_result(
            1, V2ToolResult("SUCCESS", "replaced src/example.py", "src/example.py")
        )

        self.assertIsInstance(summary, V2TuiTurnSummary)
        self.assertEqual(summary.turn, 1)
        self.assertEqual(summary.action_name, "REPLACE")
        self.assertIn("src/example.py", summary.params_summary)
        self.assertIn("11", summary.params_summary, "content char count is shown")
        self.assertEqual(summary.result_status, "SUCCESS")
        self.assertEqual(summary.result_message, "replaced src/example.py")
        self.assertEqual(vm.current_stream.content_text, "")
        self.assertEqual(vm.current_stream.turn, 2, "the next block opens on turn 2")

    def test_unparseable_block_reports_no_action_name(self) -> None:
        vm = V2TuiViewModel()
        vm.handle_delta("not json at all")

        summary = vm.handle_result(1, V2ToolResult("FAILED", "streamed not valid JSON"))

        self.assertEqual(summary.action_name, "UNPARSEABLE")
        self.assertEqual(summary.result_status, "FAILED")

    def test_done_turn_summarizes_without_params(self) -> None:
        vm = V2TuiViewModel()
        vm.handle_delta(json.dumps({"action_type": "DONE"}))

        summary = vm.handle_result(1, V2ToolResult("DONE", "model requested stop"))

        self.assertEqual(summary.action_name, "DONE")
        self.assertEqual(summary.params_summary, "-")

    def test_turn_out_of_order_is_accepted_and_resyncs(self) -> None:
        vm = V2TuiViewModel()
        vm.handle_delta(json.dumps({"action_type": "DONE"}))

        summary = vm.handle_result(3, V2ToolResult("DONE", "model requested stop"))

        self.assertEqual(summary.turn, 3)
        self.assertEqual(vm.current_stream.turn, 4)


class V2TuiViewModelFinishTests(unittest.TestCase):
    def test_finished_success_line_includes_staged_count(self) -> None:
        vm = V2TuiViewModel()

        status = vm.handle_finished("SUCCEEDED", "DONE", 2, staged_count=1)

        self.assertEqual(status.kind, "status")
        self.assertIn("SUCCEEDED", status.text)
        self.assertIn("DONE", status.text)
        self.assertIn("1", status.text)
        self.assertFalse(status.error)

    def test_finished_error_line_is_flagged(self) -> None:
        vm = V2TuiViewModel()

        status = vm.handle_finished("STOPPED", "LLM_CALL_FAILED", 1, staged_count=0)

        self.assertTrue(status.error)

    def test_cancelled_line(self) -> None:
        vm = V2TuiViewModel()

        status = vm.handle_cancelled()

        self.assertEqual(status.kind, "status")
        self.assertIn("cancelled", status.text.lower())
        self.assertTrue(status.error)


if __name__ == "__main__":
    unittest.main()

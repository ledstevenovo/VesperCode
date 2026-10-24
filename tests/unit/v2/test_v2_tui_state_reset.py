"""TUI state reset for new runs and cancelled runs (中#3, round-3).

The external review's probe showed a cancelled run's partial content
leaking into the next run's display: the app never resets the view
model on a new submission, and ``handle_cancelled`` never clears the
open stream buffers.  These tests pin the corrected contract:

- a new run starts from a zeroed view (turn counter, buffers, turn
  history, and the live block widget all start empty);
- the cancel path flushes the cancelled partial block *bounded* into
  the stream log, then clears the buffers and the live block, so
  cancelled content never mixes into the next run's display.

View-model cases are pure stdlib; the app wiring cases drive the real
textual pilot (skipped when textual is absent).  No network, no
credentials, no workspace writes.
"""

from __future__ import annotations

import asyncio
import importlib.util
import json
import tempfile
import threading
import unittest
from pathlib import Path
from typing import Any, Callable

from vespercode.tools.v2_dispatcher import V2ToolResult
from vespercode.tui.v2_view_model import V2TuiViewModel

_TEXTUAL_AVAILABLE = importlib.util.find_spec("textual") is not None


class ViewModelCancelResetTests(unittest.TestCase):
    """Pure presentation state: cancel clears, new runs reset to zero."""

    def test_cancelled_content_never_bleeds_into_the_next_stream(self) -> None:
        vm = V2TuiViewModel()

        vm.handle_delta("partial")
        vm.handle_cancelled()
        state = vm.handle_delta("NEW")

        self.assertEqual(state.content_text, "NEW")
        self.assertEqual(vm.current_stream.content_text, "NEW")

    def test_cancelled_reasoning_never_bleeds_either(self) -> None:
        vm = V2TuiViewModel()

        vm.handle_reasoning("think")
        vm.handle_cancelled()
        state = vm.handle_reasoning("R2")

        self.assertEqual(state.reasoning_text, "R2")

    def test_cancelled_partial_lines_are_bounded_for_the_log(self) -> None:
        vm = V2TuiViewModel()

        vm.handle_reasoning("r " * 60)
        vm.handle_delta("x" * 200)
        lines = vm.cancelled_partial_lines()

        self.assertEqual(len(lines), 2)
        for line in lines:
            self.assertLessEqual(len(line), 80, "log lines stay bounded")
        self.assertIn("reasoning", lines[0])
        self.assertIn("content", lines[1])
        self.assertNotIn("x" * 60, lines[1], "a long partial is previewed only")

        vm.handle_cancelled()
        self.assertEqual(vm.cancelled_partial_lines(), ())
        self.assertEqual(vm.current_stream.reasoning_text, "")
        self.assertEqual(vm.current_stream.content_text, "")

    def test_reset_zeroes_turn_counter_buffers_and_history(self) -> None:
        vm = V2TuiViewModel()
        vm.handle_reasoning("old think")
        vm.handle_delta(json.dumps({"action_type": "DONE"}))
        vm.handle_result(1, V2ToolResult("DONE", "model requested stop"))

        vm.reset()

        state = vm.current_stream
        self.assertEqual(state.turn, 1)
        self.assertEqual(state.reasoning_text, "")
        self.assertEqual(state.content_text, "")
        self.assertEqual(vm.turns, ())

    def test_two_consecutive_runs_do_not_leak_content_or_history(self) -> None:
        vm = V2TuiViewModel()

        vm.handle_delta(json.dumps({"action_type": "DONE"}))
        vm.handle_result(1, V2ToolResult("DONE", "model requested stop"))

        vm.reset()

        state = vm.handle_delta('{"action_')
        self.assertEqual(state.content_text, '{"action_', "no run-1 content residue")
        self.assertEqual(state.turn, 1, "the new run starts at turn 1")
        vm.handle_delta('type": "DONE"}')
        vm.handle_result(1, V2ToolResult("DONE", "model requested stop"))
        self.assertEqual(
            [turn.action_name for turn in vm.turns],
            ["DONE"],
            "run 2's history must not include run 1's turn summaries",
        )

    def test_cancel_then_normal_completion_still_summarizes_the_action(
        self,
    ) -> None:
        vm = V2TuiViewModel()

        vm.handle_delta("partial")
        vm.handle_cancelled()
        vm.handle_delta(json.dumps({"action_type": "DONE"}))

        summary = vm.handle_result(1, V2ToolResult("DONE", "model requested stop"))

        self.assertEqual(summary.action_name, "DONE")
        self.assertEqual(summary.turn, 1)
        self.assertEqual(vm.current_stream.content_text, "")
        self.assertEqual(vm.current_stream.turn, 2)
        self.assertEqual([turn.action_name for turn in vm.turns], ["DONE"])

    def test_late_result_after_cancel_summarizes_the_cleared_buffers(self) -> None:
        # Documented race boundary: a turn result already in flight via
        # call_from_thread may land after Ctrl+C cleared the buffers.
        # handle_result stays well-formed in that case — it summarizes
        # the *current* (post-cancel) buffers, so the cancelled partial
        # text never resurfaces inside a turn summary line.
        vm = V2TuiViewModel()

        vm.handle_delta("partial")
        vm.handle_cancelled()

        late = vm.handle_result(1, V2ToolResult("FAILED", "late race"))

        self.assertEqual(late.action_name, "NO_OUTPUT")
        self.assertNotIn("partial", late.params_summary)
        self.assertEqual(late.turn, 1)


class _GateStreamLLM:
    """stream()-only LLM that blocks after its piece until released."""

    def __init__(self, piece: str) -> None:
        self.piece = piece
        self.first_sent = threading.Event()
        self._release = threading.Event()

    def release(self) -> None:
        self._release.set()

    def generate(self, request: object) -> dict[str, object]:
        return {"action_type": "DONE"}

    def stream(self, request: object) -> object:
        yield self.piece
        self.first_sent.set()
        if not self._release.wait(timeout=30):
            raise TimeoutError("gate never released")
        yield ""


class _FastDoneLLM:
    """stream()-only LLM that finishes immediately with a DONE action."""

    def __init__(self) -> None:
        self.started = threading.Event()

    def generate(self, request: object) -> dict[str, object]:
        return {"action_type": "DONE"}

    def stream(self, request: object) -> object:
        self.started.set()
        yield json.dumps({"action_type": "DONE"})


class _PhaseFactory:
    """Returns one prepared LLM per agent run, in order."""

    def __init__(self, llms: list[object]) -> None:
        self._llms = list(llms)

    def __call__(self) -> object:
        return self._llms.pop(0)


async def _wait_until(predicate: Any, *, timeout: float = 15.0) -> None:
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while not predicate():
        if loop.time() > deadline:
            raise TimeoutError("the awaited condition never became true")
        await asyncio.sleep(0.05)


@unittest.skipUnless(_TEXTUAL_AVAILABLE, "textual is not installed")
class V2TuiAppStateResetWiringTests(unittest.IsolatedAsyncioTestCase):
    """The textual app wiring: reset on submit, bounded flush on cancel."""

    @staticmethod
    def _build_app(directory: str, factory: Callable[[], object]):
        from vespercode.tui.v2_app import V2StreamingTuiApp

        return V2StreamingTuiApp(
            workspace=Path(directory),
            task="state reset wiring",
            max_turns=5,
            llm_factory=factory,
        )

    async def test_restart_after_cancel_shows_no_residue(self) -> None:
        from textual.widgets import RichLog, Static

        cancelled_run = _GateStreamLLM("partial")
        restarted_run = _GateStreamLLM("NEW")
        with tempfile.TemporaryDirectory() as directory:
            app = self._build_app(
                directory, _PhaseFactory([cancelled_run, restarted_run])
            )
            async with app.run_test() as pilot:
                await pilot.press("enter")
                await _wait_until(cancelled_run.first_sent.is_set, timeout=10)
                await pilot.press("ctrl+c")
                cancelled_run.release()
                await _wait_until(app.run_finished.is_set, timeout=10)

                self.assertEqual(
                    str(app.query_one("#current-block", Static).content),
                    "",
                    "the cancelled partial block must leave the live view",
                )
                self.assertIn(
                    "cancel",
                    str(app.query_one("#status", Static).content).lower(),
                )

                await pilot.press("enter")
                await _wait_until(restarted_run.first_sent.is_set, timeout=10)

                self.assertEqual(
                    app.view_model.current_stream.content_text,
                    "NEW",
                    "the restarted run must not inherit cancelled content",
                )
                self.assertEqual(
                    str(app.query_one("#current-block", Static).content),
                    "› NEW",
                )
                log_text = "".join(
                    strip.text for strip in app.query_one("#stream-log", RichLog).lines
                ).replace("\n", "")
                self.assertIn("partial", log_text)

                await pilot.press("ctrl+c")
                restarted_run.release()
                await _wait_until(app.run_finished.is_set, timeout=10)

    async def test_two_consecutive_runs_keep_the_history_per_run(self) -> None:
        from textual.widgets import Static

        run_one = _FastDoneLLM()
        run_two = _FastDoneLLM()
        with tempfile.TemporaryDirectory() as directory:
            app = self._build_app(directory, _PhaseFactory([run_one, run_two]))
            async with app.run_test() as pilot:
                await pilot.press("enter")
                await _wait_until(run_one.started.is_set, timeout=10)
                await _wait_until(app.run_finished.is_set, timeout=10)
                self.assertIn(
                    "SUCCEEDED", str(app.query_one("#status", Static).content)
                )

                await pilot.press("enter")
                await _wait_until(run_two.started.is_set, timeout=10)
                await _wait_until(app.run_finished.is_set, timeout=10)

                self.assertEqual(
                    [turn.action_name for turn in app.view_model.turns],
                    ["DONE"],
                    "run 2's history must start empty, not append run 1's turns",
                )

    async def test_cancel_interleaved_with_normal_runs_recovers_cleanly(self) -> None:
        from textual.widgets import Static

        normal_run_one = _FastDoneLLM()
        cancelled_run = _GateStreamLLM("partial")
        normal_run_two = _FastDoneLLM()
        with tempfile.TemporaryDirectory() as directory:
            app = self._build_app(
                directory,
                _PhaseFactory([normal_run_one, cancelled_run, normal_run_two]),
            )
            async with app.run_test() as pilot:
                await pilot.press("enter")
                await _wait_until(normal_run_one.started.is_set, timeout=10)
                await _wait_until(app.run_finished.is_set, timeout=10)

                await pilot.press("enter")
                await _wait_until(cancelled_run.first_sent.is_set, timeout=10)
                await pilot.press("ctrl+c")
                cancelled_run.release()
                await _wait_until(app.run_finished.is_set, timeout=10)

                await pilot.press("enter")
                await _wait_until(normal_run_two.started.is_set, timeout=10)
                await _wait_until(app.run_finished.is_set, timeout=10)

                status = str(app.query_one("#status", Static).content)
                self.assertIn("SUCCEEDED", status)
                self.assertEqual(
                    [turn.action_name for turn in app.view_model.turns],
                    ["DONE"],
                    "a cancelled run between two normal ones must not leak turns",
                )


if __name__ == "__main__":
    unittest.main()

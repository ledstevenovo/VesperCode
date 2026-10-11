"""The streaming TUI app (textual-backed; skipped when textual is absent).

These tests exercise the real textual widgets through the headless test
pilot: token streaming into the live block, per-turn summaries (guardrail
denial included), and the Ctrl+C cancellation path.
"""

from __future__ import annotations

import asyncio
import importlib.util
import json
import tempfile
import threading
import unittest
from pathlib import Path
from typing import Any

from vespercode.tui.v2_launch import build_demo_llm_factory

_TEXTUAL_AVAILABLE = importlib.util.find_spec("textual") is not None

_REPLACE_ACTION = {
    "action_type": "REPLACE",
    "path": "src/example.py",
    "content": "fixed body\n",
}


class _GateStreamLLM:
    """stream()-only LLM that blocks after the first delta until released."""

    def __init__(self) -> None:
        self.first_sent = threading.Event()
        self._release = threading.Event()

    def release(self) -> None:
        self._release.set()

    def generate(self, request: object) -> dict[str, object]:
        return {"action_type": "DONE"}

    def stream(self, request: object) -> object:
        yield '{"action_'
        self.first_sent.set()
        if not self._release.wait(timeout=30):
            raise TimeoutError("cancel gate never released")
        yield 'type": "DONE"}'


async def _wait_until(predicate: Any, *, timeout: float = 15.0) -> None:
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while not predicate():
        if loop.time() > deadline:
            raise TimeoutError("the awaited condition never became true")
        await asyncio.sleep(0.05)


@unittest.skipUnless(_TEXTUAL_AVAILABLE, "textual is not installed")
class V2TuiAppTests(unittest.IsolatedAsyncioTestCase):
    async def test_demo_run_streams_tokens_and_summarizes_turns(self) -> None:
        from textual.widgets import Input, RichLog, Static

        from vespercode.tui.v2_app import V2StreamingTuiApp

        with tempfile.TemporaryDirectory() as directory:
            app = V2StreamingTuiApp(
                workspace=Path(directory),
                task="fix the failing example",
                max_turns=5,
                llm_factory=build_demo_llm_factory(),
            )
            async with app.run_test() as pilot:
                self.assertEqual(
                    app.query_one("#task-input", Input).value,
                    "fix the failing example",
                )
                await pilot.press("enter")
                await _wait_until(app.run_finished.is_set)

                status = str(app.query_one("#status", Static).content)
                self.assertIn("SUCCEEDED", status)
                self.assertIn("DONE", status)

                view = app.view_model
                self.assertEqual(
                    [turn.action_name for turn in view.turns],
                    ["REPLACE", "REPLACE", "DONE"],
                )
                self.assertEqual(
                    [turn.result_status for turn in view.turns],
                    ["DENIED", "SUCCESS", "DONE"],
                    "the guardrail denial must be visible as a turn summary",
                )

                stream_log = app.query_one("#stream-log", RichLog)
                # RichLog wraps long lines; drop the wrap newlines only.
                stream_text = "".join(strip.text for strip in stream_log.lines).replace(
                    "\n", ""
                )
                self.assertIn(json.dumps(_REPLACE_ACTION), stream_text)
                self.assertIn("replaced src/example.py", stream_text)
                self.assertIn("protected", stream_text)

    async def test_ctrl_c_cancels_the_running_turn(self) -> None:
        from textual.widgets import Static

        from vespercode.tui.v2_app import V2StreamingTuiApp

        gate = _GateStreamLLM()
        with tempfile.TemporaryDirectory() as directory:
            app = V2StreamingTuiApp(
                workspace=Path(directory),
                task="cancel me",
                max_turns=5,
                llm_factory=lambda: gate,
            )
            async with app.run_test() as pilot:
                await pilot.press("enter")
                await _wait_until(gate.first_sent.is_set, timeout=10)

                await pilot.press("ctrl+c")
                gate.release()
                await _wait_until(app.run_finished.is_set, timeout=10)

                status = str(app.query_one("#status", Static).content).lower()
                self.assertIn("cancel", status)


if __name__ == "__main__":
    unittest.main()

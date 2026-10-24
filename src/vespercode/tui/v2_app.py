"""The v2 token-level streaming TUI (textual app; lazily imported).

``V2StreamingTuiApp`` renders one v2 agent run live: model output
streams token by token into the current turn's block (chain-of-thought
reasoning in the muted style, action JSON as normal text), and each
turn's outcome flushes the block into the log with a summary line —
action name, bounded parameter summary, and the dispatcher result
(guardrail denials included).  ``Ctrl+C`` cancels the running turn:
the worker's delta callbacks check a cancel event and raise
``KeyboardInterrupt``, which the engine propagates (only
``Exception``-shaped LLM failures map onto ``LLM_CALL_FAILED``); the
worker body's ``try/finally`` restores the input and posts the
cancellation status, so the widget tree is never left inconsistent:
the cancelled partial block is flushed into the log as a bounded
preview and cleared, and every new submission resets the view model,
so content never bleeds across runs.
Writes stay staged in memory — the TUI never mutates the workspace
outside the approval-gated writeback services.

The engine loop runs on a textual thread worker; every UI mutation is
marshalled through ``call_from_thread`` onto the UI thread, and the
pure ``V2TuiViewModel`` keeps the presentation logic testable offline
without a terminal.
"""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Any, Callable

from rich.text import Text
from textual import work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.widgets import Footer, Header, Input, RichLog, Static

from vespercode.loop.v2_engine import V2AgentLoop, V2LoopResult
from vespercode.memory.v2 import V2Memory
from vespercode.tools.v2_dispatcher import (
    InMemoryWorkspacePort,
    V2ToolDispatcher,
    V2ToolResult,
)
from vespercode.tui.v2_launch import V2TuiLaunchSpec
from vespercode.tui.v2_view_model import (
    V2_TUI_ERROR_STYLE,
    V2_TUI_REASONING_STYLE,
    V2_TUI_STATUS_STYLE,
    V2_TUI_TURN_STYLE,
    V2TuiStreamState,
    V2TuiTurnSummary,
    V2TuiViewModel,
)

_STREAM_PREFIX = "▌ "
_CONTENT_PREFIX = "› "
_TURN_PREFIX = "● "
_CANCELLED_PREFIX = "✕ "


class V2StreamingTuiApp(App[None]):
    """One workspace, one streaming agent run at a time."""

    CSS = """
    #status { height: 1; padding: 0 1; }
    #stream-log { border: round $accent; height: 1fr; padding: 0 1; }
    #current-block { height: auto; max-height: 8; padding: 0 1; }
    #task-input { border: round $primary; }
    """

    BINDINGS = [
        Binding("ctrl+c", "cancel_run", "Cancel run"),
        Binding("ctrl+q", "quit", "Quit", priority=True),
    ]

    def __init__(
        self,
        *,
        workspace: Path,
        task: str,
        max_turns: int,
        llm_factory: Callable[[], Any],
    ) -> None:
        super().__init__()
        self._spec = V2TuiLaunchSpec(
            workspace=workspace,
            task=task,
            max_turns=max_turns,
            llm_factory=llm_factory,
        )
        self._view = V2TuiViewModel()
        self._cancel_event = threading.Event()
        self._run_active = False
        self.run_finished = threading.Event()
        self._staged_count = 0

    # ------------------------------------------------------------------
    # composition
    # ------------------------------------------------------------------

    @property
    def view_model(self) -> V2TuiViewModel:
        return self._view

    def compose(self) -> ComposeResult:
        yield Header()
        yield Static("idle — press Enter to run the task", id="status")
        yield RichLog(id="stream-log", markup=False, wrap=True, max_lines=5000)
        yield Static("", id="current-block")
        yield Input(value=self._spec.task, placeholder="task", id="task-input")
        yield Footer()

    def on_mount(self) -> None:
        self.query_one("#task-input", Input).focus()

    # ------------------------------------------------------------------
    # run lifecycle (thread worker + UI-thread renderers)
    # ------------------------------------------------------------------

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if self._run_active:
            return
        self._run_active = True
        self._cancel_event.clear()
        self.run_finished.clear()
        self._staged_count = 0
        self._view.reset()
        self.query_one("#current-block", Static).update(Text(""))
        event.input.disabled = True
        task = event.input.value.strip() or self._spec.task
        self._start_agent(task)

    @work(thread=True, group="v2-run", exclusive=True, exit_on_error=False)
    def _start_agent(self, task: str) -> None:
        port = InMemoryWorkspacePort()
        try:
            loop = V2AgentLoop(
                workspace=self._spec.workspace,
                llm=self._spec.llm_factory(),
                dispatcher=V2ToolDispatcher(port),
                memory=V2Memory(),
                max_turns=self._spec.max_turns,
            )
            result = loop.run(
                task,
                on_delta=self._worker_delta,
                on_reasoning=self._worker_reasoning,
                on_result=self._worker_result,
            )
            self._staged_count = len(port.files)
            self.call_from_thread(self._render_finished, result)
        except KeyboardInterrupt:
            self.call_from_thread(self._render_cancelled)
        except Exception as exc:  # noqa: BLE001 - the TUI reports, never crashes
            self.call_from_thread(self._render_error, exc)
        finally:
            self.call_from_thread(self._finish_run)

    def action_cancel_run(self) -> None:
        self._cancel_event.set()
        self._write_status("cancelling after the current delta…", error=True)

    # worker-thread callbacks: cancel check first, then marshal to the UI

    def _check_cancel(self) -> None:
        if self._cancel_event.is_set():
            raise KeyboardInterrupt

    def _worker_delta(self, text: str) -> None:
        self._check_cancel()
        self.call_from_thread(self._render_stream, self._view.handle_delta(text))

    def _worker_reasoning(self, text: str) -> None:
        self._check_cancel()
        self.call_from_thread(self._render_stream, self._view.handle_reasoning(text))

    def _worker_result(self, turn: int, result: V2ToolResult) -> None:
        self.call_from_thread(
            self._render_result, self._view.handle_result(turn, result)
        )

    # UI-thread renderers

    def _render_stream(self, state: V2TuiStreamState) -> None:
        lines: list[Text] = []
        if state.reasoning_text:
            lines.append(
                Text(
                    f"{_STREAM_PREFIX}{state.reasoning_text}",
                    style=V2_TUI_REASONING_STYLE,
                )
            )
        lines.append(Text(f"{_CONTENT_PREFIX}{state.content_text}"))
        self._write_status(
            f"streaming turn {state.turn}… (Ctrl+C cancels)", error=False
        )
        self.query_one("#current-block", Static).update(Text("\n").join(lines))

    def _render_result(self, summary: V2TuiTurnSummary) -> None:
        log = self.query_one("#stream-log", RichLog)
        self._flush_current_block(log)
        log.write(
            Text(
                f"{_TURN_PREFIX}turn {summary.turn} {summary.action_name} "
                f"[{summary.params_summary}] → {summary.result_status}: "
                f"{summary.result_message}",
                style=V2_TUI_TURN_STYLE,
            )
        )

    def _render_finished(self, result: V2LoopResult) -> None:
        event = self._view.handle_finished(
            result.status,
            result.stop_reason,
            result.turns,
            staged_count=self._staged_count,
        )
        self._write_status(event.text, error=event.error)

    def _render_cancelled(self) -> None:
        partial = self._view.cancelled_partial_lines()
        event = self._view.handle_cancelled()
        log = self.query_one("#stream-log", RichLog)
        for line in partial:
            log.write(
                Text(
                    f"{_CANCELLED_PREFIX}{line}",
                    style=V2_TUI_REASONING_STYLE,
                )
            )
        self.query_one("#current-block", Static).update(Text(""))
        self._write_status(event.text, error=event.error)

    def _render_error(self, exc: Exception) -> None:
        self._write_status(f"run failed to start: {type(exc).__name__}", error=True)

    def _finish_run(self) -> None:
        task_input = self.query_one("#task-input", Input)
        task_input.disabled = False
        task_input.focus()
        self._run_active = False
        self.run_finished.set()

    def _write_status(self, text: str, *, error: bool) -> None:
        self.query_one("#status", Static).update(
            Text(text, style=V2_TUI_ERROR_STYLE if error else V2_TUI_STATUS_STYLE)
        )

    def _flush_current_block(self, log: RichLog) -> None:
        current = self.query_one("#current-block", Static)
        content = str(current.content or "")
        for line in content.splitlines():
            if line.strip():
                log.write(Text(line))
        current.update(Text(""))


def run_v2_tui(spec: object) -> int:
    """Build and run the streaming TUI for one launch spec."""

    if not isinstance(spec, V2TuiLaunchSpec):
        raise TypeError("spec must be a V2TuiLaunchSpec")
    app = V2StreamingTuiApp(
        workspace=spec.workspace,
        task=spec.task,
        max_turns=spec.max_turns,
        llm_factory=spec.llm_factory,
    )
    app.run()
    return 0


__all__ = ["V2StreamingTuiApp", "run_v2_tui"]

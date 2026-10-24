"""Pure presentation state of the v2 streaming TUI (no textual import).

The view model is the whole TUI brain minus the widget tree: it turns
engine callbacks (content deltas, reasoning deltas, per-turn results,
the final outcome) into bounded render events the textual app marshals
onto the UI thread.  One open stream block exists per turn — content
and reasoning accumulate separately (reasoning is flagged with the
muted style) — and the turn's result closes the block with a summary
line: action name, bounded parameter summary, result status and
message.  Cancellation clears the open block (bounded preview lines
are exposed for the log first), and a new run resets the whole view
state, so content never bleeds across runs.  The live stream renders
only a bounded window of the most recent output (the newest delta is
always fully visible), so per-delta handling is amortized constant
work and one render costs O(window); the full text stays buffered in
the parts lists, so the turn summary still parses the whole stream.
Being pure state, it is fully testable offline without a terminal.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from vespercode.tools.v2_dispatcher import V2ToolResult

V2_TUI_REASONING_STYLE = "dim italic"
"""The muted style tag for chain-of-thought reasoning lines."""

V2_TUI_STATUS_STYLE = "bold cyan"
V2_TUI_ERROR_STYLE = "bold red"
V2_TUI_TURN_STYLE = "green"

_V2_TUI_MAX_SUMMARY_CHARS = 160
_V2_TUI_MAX_RAW_PREVIEW_CHARS = 48
_V2_TUI_MAX_STREAM_WINDOW_CHARS = 2000
"""Default visible-stream window: the newest delta is always fully
visible and older content is trimmed beyond this many characters; the
full text stays buffered for the turn summary."""


@dataclass(frozen=True, slots=True)
class V2TuiStreamState:
    """The accumulated open stream block of the current turn."""

    turn: int
    reasoning_text: str
    content_text: str
    reasoning_style: str = V2_TUI_REASONING_STYLE


@dataclass(frozen=True, slots=True)
class V2TuiTurnSummary:
    """The bounded per-turn line: action name / params / result."""

    turn: int
    action_name: str
    params_summary: str
    result_status: str
    result_message: str


@dataclass(frozen=True, slots=True)
class V2TuiStatusEvent:
    """The final status line of a run (success, stop, or cancellation)."""

    kind: str
    text: str
    error: bool


def _bounded(text: str, limit: int = _V2_TUI_MAX_SUMMARY_CHARS) -> str:
    if len(text) <= limit:
        return text
    return text[: limit - 1] + "…"


def _oneline(text: str) -> str:
    return text.replace("\r", " ").replace("\n", " ")


class V2TuiViewModel:
    """Aggregates streaming engine callbacks into render-ready events."""

    def __init__(self, window_chars: int = _V2_TUI_MAX_STREAM_WINDOW_CHARS) -> None:
        self._window_chars = window_chars
        self._stream_turn = 1
        self._reasoning_parts: list[str] = []
        self._content_parts: list[str] = []
        self._reasoning_window = ""
        self._content_window = ""
        self._turns: list[V2TuiTurnSummary] = []

    # ------------------------------------------------------------------
    # engine callbacks (called on the UI thread by the app)
    # ------------------------------------------------------------------

    def handle_delta(self, text: str) -> V2TuiStreamState:
        self._content_parts.append(text)
        self._content_window = self._window_append(self._content_window, text)
        return self.current_stream

    def handle_reasoning(self, text: str) -> V2TuiStreamState:
        self._reasoning_parts.append(text)
        self._reasoning_window = self._window_append(self._reasoning_window, text)
        return self.current_stream

    def _window_append(self, window: str, text: str) -> str:
        """Extend a visible window by one delta, trimming old content.

        The newest delta always stays fully visible: a delta at least as
        long as the window fills it by itself, and a shorter delta is
        never cut.  Older content is trimmed only once the window
        overflows, so the per-delta cost is O(window) instead of
        rejoining the whole buffer on every delta.
        """
        if len(text) >= self._window_chars:
            return text
        window += text
        if len(window) > self._window_chars:
            window = window[-self._window_chars :]
        return window

    def handle_result(self, turn: int, result: V2ToolResult) -> V2TuiTurnSummary:
        content_text = "".join(self._content_parts)
        action_name, params_summary = self._summarize_action(content_text)
        summary = V2TuiTurnSummary(
            turn=turn,
            action_name=action_name,
            params_summary=params_summary,
            result_status=result.status,
            result_message=_bounded(result.message),
        )
        self._turns.append(summary)
        self._reasoning_parts = []
        self._content_parts = []
        self._reasoning_window = ""
        self._content_window = ""
        self._stream_turn = turn + 1
        return summary

    def handle_finished(
        self, status: str, stop_reason: str, turns: int, *, staged_count: int
    ) -> V2TuiStatusEvent:
        return V2TuiStatusEvent(
            kind="status",
            text=(
                f"run {status} stop={stop_reason} turns={turns} "
                f"staged (not written): {staged_count}"
            ),
            error=status != "SUCCEEDED",
        )

    def handle_cancelled(self) -> V2TuiStatusEvent:
        self._reasoning_parts = []
        self._content_parts = []
        self._reasoning_window = ""
        self._content_window = ""
        return V2TuiStatusEvent(
            kind="status",
            text=(
                f"run cancelled at turn {self._stream_turn} "
                "(staged writes kept in memory only)"
            ),
            error=True,
        )

    def reset(self) -> None:
        """Zero the view state for a new run (turn, buffers, history)."""
        self._stream_turn = 1
        self._reasoning_parts = []
        self._content_parts = []
        self._reasoning_window = ""
        self._content_window = ""
        self._turns = []

    # ------------------------------------------------------------------
    # projections
    # ------------------------------------------------------------------

    def cancelled_partial_lines(self) -> tuple[str, ...]:
        """Bounded log lines for the open partial block.

        ``handle_cancelled`` drops the open block's buffers; this
        projection captures what was in them as one bounded preview
        line per channel, so the app can flush the cancelled partial
        into the stream log without unbounded text.  Call it before
        ``handle_cancelled`` clears the buffers.
        """
        lines: list[str] = []
        reasoning = _oneline("".join(self._reasoning_parts))
        if reasoning:
            preview = _bounded(reasoning, _V2_TUI_MAX_RAW_PREVIEW_CHARS)
            lines.append(f"cancelled reasoning: {preview}")
        content = _oneline("".join(self._content_parts))
        if content:
            preview = _bounded(content, _V2_TUI_MAX_RAW_PREVIEW_CHARS)
            lines.append(f"cancelled content: {preview}")
        return tuple(lines)

    @property
    def current_stream(self) -> V2TuiStreamState:
        return V2TuiStreamState(
            turn=self._stream_turn,
            reasoning_text=self._reasoning_window,
            content_text=self._content_window,
        )

    @property
    def turns(self) -> tuple[V2TuiTurnSummary, ...]:
        return tuple(self._turns)

    @staticmethod
    def _summarize_action(content_text: str) -> tuple[str, str]:
        if not content_text:
            return "NO_OUTPUT", "-"
        try:
            action = json.loads(content_text)
        except json.JSONDecodeError:
            preview = _bounded(
                content_text.replace("\n", " "), _V2_TUI_MAX_RAW_PREVIEW_CHARS
            )
            return "UNPARSEABLE", f"raw≈{preview!r}"
        if not isinstance(action, dict):
            return "UNPARSEABLE", "-"
        action_type = action.get("action_type")
        name = action_type if isinstance(action_type, str) else "UNKNOWN"
        params: list[str] = []
        path = action.get("path")
        if isinstance(path, str):
            params.append(f"path={path}")
        content = action.get("content")
        if isinstance(content, str):
            params.append(f"content={len(content)} chars")
        return name, (" ".join(params) if params else "-")


__all__ = [
    "V2_TUI_REASONING_STYLE",
    "V2TuiStatusEvent",
    "V2TuiStreamState",
    "V2TuiTurnSummary",
    "V2TuiViewModel",
]

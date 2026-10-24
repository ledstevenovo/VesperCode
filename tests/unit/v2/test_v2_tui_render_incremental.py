"""Bounded TUI stream rendering (低#6, round 3) — amortized-cost contract.

The pre-fix view model rejoined the whole parts buffer on every delta
(``current_stream`` was O(total) per call, so N deltas cost O(N^2)
materialized characters).  The contract under test:

* per-delta handling is amortized O(1)-class work — constant in the
  total stream length — and one render costs O(visible window);
* the live stream shows a bounded window of the most recent output:
  the newest delta always stays fully visible, older content is
  trimmed once the window overflows;
* the turn summary still parses the FULL streamed text (the window is
  a rendering bound, not a data bound).

Honesty note (per the round-3 contract): these claims are backed by
instrumented counters only — the number of characters materialized per
delta render, which is the work the old full-join path did on every
call — never by wall-clock timing, and they are not an asymptotic
proof.

Counter definition: ``len(state.content_text)`` per ``handle_delta``
call.  Pre-fix that is the full re-joined prefix length (grows without
bound as the turn streams); post-fix it is capped by the window
constant.
"""

import json
import unittest

from vespercode.tools.v2_dispatcher import V2ToolResult
from vespercode.tui.v2_view_model import V2TuiViewModel

# The default visible-window bound (the ``_V2_TUI_MAX_STREAM_WINDOW_CHARS``
# constant in the view model).  It is pinned behaviourally here — the
# constant-free property (per-delta materialization stops growing with the
# stream length) is asserted in the quadratic test via these literals, and
# test_default_window_trims_a_long_stream pins the exact default value.
_DEFAULT_WINDOW_CHARS = 2000


class StreamWindowTests(unittest.TestCase):
    def test_delta_materialization_work_is_bounded_not_quadratic(self):
        vm = V2TuiViewModel()
        deltas = 5000
        chunk = "abcdefgh"
        total_materialized = 0
        worst_delta = 0
        state = None
        for _ in range(deltas):
            state = vm.handle_delta(chunk)
            materialized = len(state.content_text)
            total_materialized += materialized
            worst_delta = max(worst_delta, materialized)
        # Post-fix: every render is capped by the window constant, so the
        # total work is linear (<= deltas * window) and each delta's
        # materialization is bounded by the window — pre-fix the per-delta
        # count grows without bound (deltas * chunk at the last one) and the
        # total is quadratic (deltas^2 * chunk / 2).
        self.assertLessEqual(
            worst_delta,
            _DEFAULT_WINDOW_CHARS,
            msg=(
                "per-delta materialization is unbounded: "
                f"{worst_delta} > {_DEFAULT_WINDOW_CHARS}"
            ),
        )
        self.assertLessEqual(
            total_materialized,
            deltas * _DEFAULT_WINDOW_CHARS,
            msg=(
                "total materialized characters is quadratic: "
                f"{total_materialized} > {deltas * _DEFAULT_WINDOW_CHARS}"
            ),
        )
        # The visible window holds exactly the most recent window-sized tail
        # of the full stream (40000 chars streamed, window 2000 = 250 chunks).
        self.assertEqual(state.content_text, chunk * 250)

    def test_visible_window_trims_old_content_and_keeps_the_newest(self):
        vm = V2TuiViewModel(window_chars=16)
        state = vm.handle_delta("a" * 24)
        # A single delta larger than the window still shows in full.
        self.assertEqual(state.content_text, "a" * 24)
        state = vm.handle_delta("bbbb")
        # Older content is trimmed to keep the window at its bound; the
        # newest delta stays fully visible.
        self.assertEqual(state.content_text, "a" * 12 + "bbbb")
        state = vm.handle_delta("c" * 40)
        # An oversized delta fills the whole window by itself.
        self.assertEqual(state.content_text, "c" * 40)
        state = vm.handle_delta("d")
        # The next normal delta shrinks the window back to its bound.
        self.assertEqual(state.content_text, "c" * 15 + "d")

    def test_default_window_trims_a_long_stream(self):
        vm = V2TuiViewModel()
        vm.handle_delta("a" * 2000)
        state = vm.handle_delta("b" * 200)
        self.assertEqual(state.content_text, "a" * 1800 + "b" * 200)
        self.assertEqual(len(state.content_text), 2000)

    def test_reasoning_channel_gets_the_same_window(self):
        vm = V2TuiViewModel(window_chars=8)
        vm.handle_reasoning("r" * 30)
        state = vm.handle_reasoning("s")
        self.assertEqual(state.reasoning_text, "r" * 7 + "s")
        self.assertEqual(state.content_text, "")

    def test_turn_summary_sees_full_text_even_when_the_window_is_trimmed(self):
        vm = V2TuiViewModel()
        action = {"action_type": "DONE", "content": "x" * 3000}
        raw = json.dumps(action)
        for start in range(0, len(raw), 100):
            vm.handle_delta(raw[start : start + 100])
        # The visible window has trimmed the head of the stream...
        state = vm.current_stream
        self.assertLess(len(state.content_text), len(raw))
        # ...but the turn summary still parses the FULL streamed text, and
        # result handling clears the window together with the buffers.
        summary = vm.handle_result(1, V2ToolResult("DONE", "model requested stop"))
        self.assertEqual(summary.action_name, "DONE")
        self.assertIn("content=3000 chars", summary.params_summary)
        self.assertEqual(vm.current_stream.content_text, "")

    def test_cancel_and_reset_clear_the_visible_windows(self):
        vm = V2TuiViewModel(window_chars=16)
        vm.handle_delta("partial" * 4)
        vm.handle_cancelled()
        self.assertEqual(vm.current_stream.content_text, "")
        vm.handle_delta("n" * 40)
        vm.reset()
        self.assertEqual(vm.current_stream.content_text, "")
        self.assertEqual(vm.current_stream.reasoning_text, "")
        self.assertEqual(vm.current_stream.turn, 1)


if __name__ == "__main__":
    unittest.main()

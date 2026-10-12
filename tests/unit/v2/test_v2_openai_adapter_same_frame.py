"""Regression tests: one SSE delta may carry several fields at once (P0-1).

The frame handler in ``v2_openai_adapter`` used two independent early
returns, so a delta carrying BOTH ``reasoning_content`` and ``content``
silently dropped the content, and a delta carrying ``content`` together
with ``finish_reason`` dropped the ``finish_reason``.  These tests pin
the fixed contract: every field of a frame is processed, the increments
of one frame are emitted in order (reasoning first, then content), and
a frame carrying ``finish_reason`` ends the stream only AFTER its
increments are emitted.  Everything drives the real adapter through an
injected fake transport — no network, no credentials, no filesystem.
"""

from __future__ import annotations

import json
import unittest

from vespercode.llm.v2 import V2LLMRequest
from vespercode.llm.v2_openai_adapter import V2OpenAICompatLLM


def _sse(payload: str) -> bytes:
    return f"data: {payload}\n\n".encode("utf-8")


def _delta_frame(delta: dict, **choice_extra: object) -> bytes:
    """One SSE frame; ``choice_extra`` lands beside ``delta`` in choices[0].

    ``ensure_ascii=False`` keeps non-ASCII payload text as raw UTF-8
    bytes so the multi-byte reassembly tests split real multi-byte
    sequences, not ``\\uXXXX`` escapes.
    """

    choice: dict = {"delta": delta}
    choice.update(choice_extra)
    return _sse(json.dumps({"choices": [choice]}, ensure_ascii=False))


def _done() -> bytes:
    return b"data: [DONE]\n\n"


class _FakeTransport:
    """Replays preset byte chunks; records the request for assertions."""

    def __init__(self, chunks: list[bytes]) -> None:
        self.chunks = chunks
        self.calls: list[tuple[str, dict, bytes]] = []

    def stream_post(self, url: str, headers: dict, body: bytes) -> object:
        self.calls.append((url, dict(headers), body))
        yield from self.chunks


def _adapter(chunks: list[bytes]) -> V2OpenAICompatLLM:
    return V2OpenAICompatLLM(
        api_key_provider=lambda: "stub-key-not-a-secret",
        transport=_FakeTransport(chunks),
    )


def _request() -> V2LLMRequest:
    return V2LLMRequest("run-p0-1", "fix the example", ())


class SameFrameDualFieldTests(unittest.TestCase):
    """One delta carrying BOTH reasoning_content and content."""

    def test_both_fields_of_one_frame_are_aggregated(self) -> None:
        chunks = [
            _delta_frame({"reasoning_content": "let me think", "content": "AAA"}),
            _delta_frame({"content": "BBB"}),
            _done(),
        ]

        events = list(_adapter(chunks).stream_events(_request()))

        content = "".join(e.text for e in events if e.kind == "content")
        reasoning = "".join(e.text for e in events if e.kind == "reasoning")
        self.assertEqual(content, "AAABBB")
        self.assertEqual(reasoning, "let me think")
        self.assertEqual(
            [(event.kind, event.text) for event in events],
            [
                ("reasoning", "let me think"),
                ("content", "AAA"),
                ("content", "BBB"),
            ],
        )

    def test_dual_field_frame_survives_json_key_order(self) -> None:
        chunks = [
            _delta_frame({"content": "BODY1", "reasoning_content": "THOUGHT1"}),
            _delta_frame({"content": "BODY2"}),
            _done(),
        ]

        events = list(_adapter(chunks).stream_events(_request()))

        self.assertEqual(
            [(event.kind, event.text) for event in events],
            [
                ("reasoning", "THOUGHT1"),
                ("content", "BODY1"),
                ("content", "BODY2"),
            ],
        )
        self.assertEqual(
            "".join(e.text for e in events if e.kind == "content"), "BODY1BODY2"
        )

    def test_dual_field_stream_channel_yields_parseable_action(self) -> None:
        chunks = [
            _delta_frame({"reasoning_content": "think", "content": '{"action_'}),
            _delta_frame({"content": 'type": "DONE"}'}),
            _done(),
        ]

        text = "".join(_adapter(chunks).stream(_request()))

        self.assertEqual(text, '{"action_type": "DONE"}')
        self.assertEqual(json.loads(text), {"action_type": "DONE"})

    def test_dual_field_frame_with_empty_content_emits_reasoning_only(
        self,
    ) -> None:
        chunks = [
            _delta_frame({"reasoning_content": "think", "content": ""}),
            _delta_frame({"content": "X"}),
            _done(),
        ]

        events = list(_adapter(chunks).stream_events(_request()))

        self.assertEqual(
            [(event.kind, event.text) for event in events],
            [("reasoning", "think"), ("content", "X")],
        )

    def test_lastone_is_still_ignored_on_a_dual_field_frame(self) -> None:
        chunks = [
            _delta_frame({"reasoning_content": "r", "content": "c"}, lastOne=True),
            _delta_frame({"content": "d"}),
            _done(),
        ]

        events = list(_adapter(chunks).stream_events(_request()))

        self.assertEqual(
            [(event.kind, event.text) for event in events],
            [
                ("reasoning", "r"),
                ("content", "c"),
                ("content", "d"),
            ],
        )


class SameFrameFinishReasonTests(unittest.TestCase):
    """One delta carrying content AND finish_reason together."""

    def test_content_and_finish_reason_both_apply(self) -> None:
        chunks = [
            _delta_frame({"content": '{"action'}),
            _delta_frame({"content": '_type": "DONE"}'}, finish_reason="stop"),
            _delta_frame({"content": "TRAILING-AFTER-FINISH"}),
            _done(),
        ]

        deltas = list(_adapter(chunks).stream(_request()))

        self.assertEqual(deltas, ['{"action', '_type": "DONE"}'])

    def test_dual_field_and_finish_reason_in_one_frame(self) -> None:
        chunks = [
            _delta_frame(
                {"reasoning_content": "final thought", "content": '{"action_type": "DONE"}'},
                finish_reason="stop",
            ),
            _delta_frame({"content": "NEVER-ARRIVES"}),
            _done(),
        ]

        events = list(_adapter(chunks).stream_events(_request()))

        self.assertEqual(
            [(event.kind, event.text) for event in events],
            [
                ("reasoning", "final thought"),
                ("content", '{"action_type": "DONE"}'),
            ],
        )


class MultibyteUtf8ReassemblyTests(unittest.TestCase):
    """Multi-byte UTF-8 must survive splitting across frames/chunks."""

    def test_cjk_multibyte_split_across_byte_chunks(self) -> None:
        frame = _delta_frame({"content": "你好世界"})
        head = 'data: {"choices": [{"delta": {"content": "你'.encode("utf-8")
        mid = len(head) + 1  # inside 好's 3-byte sequence (after its first byte)
        chunks = [frame[:mid], frame[mid:], _done()]

        content = "".join(_adapter(chunks).stream(_request()))

        self.assertEqual(content, "你好世界")

    def test_four_byte_emoji_split_across_byte_chunks(self) -> None:
        frame = _delta_frame({"content": "ok🆒!"})
        head = 'data: {"choices": [{"delta": {"content": "ok'.encode("utf-8")
        mid = len(head) + 2  # inside the 4-byte emoji (after its second byte)
        chunks = [frame[:mid], frame[mid:], _done()]

        content = "".join(_adapter(chunks).stream(_request()))

        self.assertEqual(content, "ok🆒!")

    def test_multibyte_text_split_across_delta_frames_parses(self) -> None:
        chunks = [
            _delta_frame({"content": '{"备注": "你'}),
            _delta_frame({"content": '好"}'}),
            _done(),
        ]

        text = "".join(_adapter(chunks).stream(_request()))

        self.assertEqual(json.loads(text), {"备注": "你好"})


if __name__ == "__main__":
    unittest.main()

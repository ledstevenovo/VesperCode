"""Stream-termination fail-closed contract for the v2 OpenAI adapter.

Round-3 external review defect 高#2: an SSE stream whose bytes are
exhausted without EVER carrying a termination marker (a chunk's
``finish_reason`` or the ``data: [DONE]`` sentinel) is a truncated
stream.  Such a stream must fail closed with
``V2OpenAIAdapterError("LLM_CALL_FAILED")`` — the aggregated content of
an unterminated stream must never complete as normal output.  The
scenario classes below pin both the new fail-closed contract (EOF /
empty / non-data-only streams with no marker) and the preserved
double-safeguard semantics: ``finish_reason`` alone or ``[DONE]`` alone
suffices, trailing events after a marker stay ignored, a marker in the
final residual line (no trailing newline) terminates, and multi-byte
UTF-8 split across chunks still reassembles.  Everything drives the
real adapter through an injected fake transport — no network, no
credentials, no filesystem.
"""

from __future__ import annotations

import json
import unittest

from vespercode.llm.v2 import V2LLMRequest
from vespercode.llm.v2_openai_adapter import (
    V2OpenAIAdapterError,
    V2OpenAICompatLLM,
)


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
    return V2LLMRequest("run-r3-eof", "fix the example", ())


class UnterminatedStreamFailsClosedTests(unittest.TestCase):
    """EOF without any termination marker must fail closed (高#2)."""

    def test_unterminated_delta_stream_at_eof_raises_llm_call_failed(
        self,
    ) -> None:
        # The T0 red-baseline probe shape (.round3-baseline/probe_a_eof.py):
        # two legal delta frames, no finish_reason, no [DONE] — EOF.
        chunks = [
            _delta_frame({"content": "AAA"}),
            _delta_frame({"content": "BBB"}),
        ]

        with self.assertRaises(V2OpenAIAdapterError) as caught:
            list(_adapter(chunks).stream_events(_request()))

        self.assertEqual(caught.exception.code, "LLM_CALL_FAILED")
        self.assertEqual(str(caught.exception), "LLM call failed")

    def test_unterminated_stream_yields_increments_then_fails_at_eof(
        self,
    ) -> None:
        # Fail-closed means the stream never COMPLETES normally; the
        # increments observed before EOF are not a success return.
        chunks = [
            _delta_frame({"content": "AAA"}),
            _delta_frame({"content": "BBB"}),
        ]
        collected: list[str] = []

        with self.assertRaises(V2OpenAIAdapterError) as caught:
            for delta in _adapter(chunks).stream(_request()):
                collected.append(delta)

        self.assertEqual(caught.exception.code, "LLM_CALL_FAILED")
        self.assertEqual(collected, ["AAA", "BBB"])

    def test_unterminated_stream_with_reasoning_raises_after_emitting(
        self,
    ) -> None:
        # The reasoning channel never acts as a terminator; an
        # unterminated stream that only emitted reasoning still fails.
        chunks = [
            _delta_frame({"reasoning_content": "thinking"}),
            _delta_frame({"content": "body"}),
        ]
        kinds: list[tuple[str, str]] = []

        with self.assertRaises(V2OpenAIAdapterError) as caught:
            for event in _adapter(chunks).stream_events(_request()):
                kinds.append((event.kind, event.text))

        self.assertEqual(caught.exception.code, "LLM_CALL_FAILED")
        self.assertEqual(
            kinds,
            [("reasoning", "thinking"), ("content", "body")],
        )

    def test_non_data_lines_only_stream_raises(self) -> None:
        # Keep-alive comments, event lines, and malformed JSON lines
        # carry no termination marker; a stream of only them is
        # unterminated and fails closed.
        chunks = [
            b": keep-alive comment\n\n",
            b"event: ping\n\n",
            b"data: not-json-at-all\n\n",
        ]

        with self.assertRaises(V2OpenAIAdapterError) as caught:
            list(_adapter(chunks).stream_events(_request()))

        self.assertEqual(caught.exception.code, "LLM_CALL_FAILED")

    def test_empty_stream_raises(self) -> None:
        # Zero bytes, zero frames: EOF before anything — unterminated.
        with self.assertRaises(V2OpenAIAdapterError) as caught:
            list(_adapter([]).stream_events(_request()))

        self.assertEqual(caught.exception.code, "LLM_CALL_FAILED")

    def test_zero_byte_chunk_stream_raises(self) -> None:
        # A transport that yields one zero-length chunk is still an
        # empty (unterminated) byte stream.
        with self.assertRaises(V2OpenAIAdapterError) as caught:
            list(_adapter([b""]).stream_events(_request()))

        self.assertEqual(caught.exception.code, "LLM_CALL_FAILED")


class TerminatedStreamAggregatesTests(unittest.TestCase):
    """Preserved double-safeguard semantics (regression pins)."""

    def test_finish_reason_without_done_marker_aggregates(self) -> None:
        # ② finish_reason alone terminates: the stream completes
        # normally and the aggregated content is returned.
        chunks = [
            _delta_frame({"content": '{"action'}),
            _delta_frame({"content": '_type": "DONE"}'}, finish_reason="stop"),
        ]

        deltas = list(_adapter(chunks).stream(_request()))

        self.assertEqual(deltas, ['{"action', '_type": "DONE"}'])

    def test_done_without_finish_reason_aggregates(self) -> None:
        # ③ [DONE] alone terminates: normal completion, no error.
        chunks = [
            _delta_frame({"content": '{"action_type": "DONE"}'}),
            _done(),
        ]

        deltas = list(_adapter(chunks).stream(_request()))

        self.assertEqual(deltas, ['{"action_type": "DONE"}'])

    def test_events_after_done_marker_are_ignored(self) -> None:
        # ④ round-2 TRAILING-AFTER-FINISH semantics: after the first
        # termination marker later frames are ignored, not an error.
        chunks = [
            _delta_frame({"content": "HEAD"}),
            _done(),
            _delta_frame({"content": "TRAILING-AFTER-DONE"}),
            _done(),
        ]

        deltas = list(_adapter(chunks).stream(_request()))

        self.assertEqual(deltas, ["HEAD"])

    def test_done_marker_in_final_residual_line_without_newline(
        self,
    ) -> None:
        # ⑤ the terminator arrives in the last residual line with no
        # trailing newline: the stream still ends normally.
        chunks = [
            _delta_frame({"content": "AAA"}),
            b"data: [DONE]",
        ]

        deltas = list(_adapter(chunks).stream(_request()))

        self.assertEqual(deltas, ["AAA"])

    def test_residual_line_with_content_and_finish_reason_emits_and_ends(
        self,
    ) -> None:
        # ⑤ variant: the final residual line carries BOTH a content
        # increment and finish_reason — the increment is emitted and
        # the stream ends normally (no fail-closed raise at EOF).
        chunks = [
            _delta_frame({"content": "AA"}),
            _delta_frame({"content": "BB"}, finish_reason="stop")[:-1],
        ]

        deltas = list(_adapter(chunks).stream(_request()))

        self.assertEqual(deltas, ["AA", "BB"])

    def test_multibyte_utf8_split_across_chunks_with_done(self) -> None:
        # ⑦ multi-byte UTF-8 split across byte chunks plus [DONE]:
        # reassembly stays exact and the stream ends normally.
        frame = _delta_frame({"content": "你好世界"})
        head = 'data: {"choices": [{"delta": {"content": "你'.encode("utf-8")
        mid = len(head) + 1  # inside 好's 3-byte sequence (after its first byte)
        chunks = [frame[:mid], frame[mid:], _done()]

        content = "".join(_adapter(chunks).stream(_request()))

        self.assertEqual(content, "你好世界")

    def test_multibyte_utf8_split_frame_with_finish_reason_ends_normally(
        self,
    ) -> None:
        # ⑦ variant: a frame carrying content AND finish_reason is
        # split inside a 4-byte emoji; reassembly stays exact, the
        # finish_reason terminates, and no error is raised.
        frame = _delta_frame({"content": "ok🆒!"}, finish_reason="stop")
        head = 'data: {"choices": [{"delta": {"content": "ok'.encode("utf-8")
        mid = len(head) + 2  # inside the 4-byte emoji (after its second byte)
        chunks = [frame[:mid], frame[mid:]]

        content = "".join(_adapter(chunks).stream(_request()))

        self.assertEqual(content, "ok🆒!")


if __name__ == "__main__":
    unittest.main()

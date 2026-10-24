"""The OpenAI-compatible streaming v2 adapter (offline, injectable transport).

Every test drives the adapter through a fake transport that replays
preset SSE chunks — no network, no credentials, fully deterministic.
The API key never appears in this file: the key path is exercised with
a stub provider literal and the missing-key path with an empty
environment.
"""

from __future__ import annotations

import json
import os
import unittest
from unittest import mock

from vespercode.llm.v2 import V2LLMRequest
from vespercode.llm.v2_openai_adapter import (
    V2_OPENAI_API_KEY_ENV,
    V2_OPENAI_DEFAULT_BASE_URL,
    V2_OPENAI_DEFAULT_MODEL,
    V2OpenAIAdapterError,
    V2OpenAICompatLLM,
)


def _sse(payload: str) -> bytes:
    return f"data: {payload}\n\n".encode("utf-8")


def _content_chunk(text: str, *, extra: dict | None = None) -> bytes:
    delta: dict = {"content": text}
    if extra:
        delta.update(extra)
    return _sse(json.dumps({"choices": [{"delta": delta}]}))


def _reasoning_chunk(text: str) -> bytes:
    return _sse(json.dumps({"choices": [{"delta": {"reasoning_content": text}}]}))


class _FakeTransport:
    """Replays preset byte chunks; records the request for assertions."""

    def __init__(
        self,
        chunks: list[bytes] | None = None,
        *,
        exception: Exception | None = None,
    ) -> None:
        self.chunks = chunks or []
        self.exception = exception
        self.calls: list[tuple[str, dict, bytes]] = []

    def stream_post(self, url: str, headers: dict, body: bytes) -> object:
        self.calls.append((url, dict(headers), body))
        if self.exception is not None:
            raise self.exception
        yield from self.chunks


def _request(context: tuple[str, ...] = ()) -> V2LLMRequest:
    return V2LLMRequest("run-c", "fix the example", context)


def _adapter(transport: _FakeTransport, **kwargs: object) -> V2OpenAICompatLLM:
    defaults = {"api_key_provider": lambda: "stub-key-not-a-secret"}
    return V2OpenAICompatLLM(
        transport=transport,
        **{**defaults, **kwargs},  # type: ignore[arg-type]
    )


class V2OpenAIAdapterStreamTests(unittest.TestCase):
    def test_content_deltas_stream_in_order_and_aggregate(self) -> None:
        transport = _FakeTransport(
            [
                _content_chunk('{"action_'),
                _content_chunk('type": '),
                _content_chunk('"DONE"}'),
                b"data: [DONE]\n\n",
            ]
        )
        adapter = _adapter(transport)

        deltas = list(adapter.stream(_request()))

        self.assertEqual(deltas, ['{"action_', 'type": ', '"DONE"}'])

    def test_reasoning_travels_on_its_own_typed_channel(self) -> None:
        transport = _FakeTransport(
            [
                _reasoning_chunk("thinking "),
                _reasoning_chunk("hard"),
                _content_chunk('{"action_type": "DONE"}'),
                b"data: [DONE]\n\n",
            ]
        )
        adapter = _adapter(transport)

        events = list(adapter.stream_events(_request()))

        self.assertEqual(
            [(event.kind, event.text) for event in events],
            [
                ("reasoning", "thinking "),
                ("reasoning", "hard"),
                ("content", '{"action_type": "DONE"}'),
            ],
        )

    def test_empty_first_content_chunk_is_not_emitted(self) -> None:
        transport = _FakeTransport(
            [
                _content_chunk(""),
                _content_chunk('{"action'),
                _content_chunk('_type": "DONE"}'),
                b"data: [DONE]\n\n",
            ]
        )
        adapter = _adapter(transport)

        deltas = list(adapter.stream(_request()))

        self.assertEqual(deltas, ['{"action', '_type": "DONE"}'])

    def test_done_terminates_even_with_trailing_data(self) -> None:
        transport = _FakeTransport(
            [
                _content_chunk('{"action_type": "DONE"}'),
                b"data: [DONE]\n\n",
                _content_chunk("after-done"),
                b"data: [DONE]\n\n",
            ]
        )
        adapter = _adapter(transport)

        deltas = list(adapter.stream(_request()))

        self.assertEqual(deltas, ['{"action_type": "DONE"}'])

    def test_finish_reason_terminates_without_done_marker(self) -> None:
        transport = _FakeTransport(
            [
                _content_chunk('{"action'),
                _sse(json.dumps({"choices": [{"delta": {}, "finish_reason": "stop"}]})),
                _content_chunk("never-arrives"),
            ]
        )
        adapter = _adapter(transport)

        deltas = list(adapter.stream(_request()))

        self.assertEqual(deltas, ['{"action'])

    def test_lastone_field_is_ignored_as_a_terminator(self) -> None:
        transport = _FakeTransport(
            [
                _sse(
                    json.dumps(
                        {
                            "choices": [
                                {
                                    "delta": {"content": '{"action'},
                                    "lastOne": False,
                                }
                            ]
                        }
                    )
                ),
                _sse(
                    json.dumps(
                        {
                            "choices": [
                                {
                                    "delta": {"content": '_type": "DONE"}'},
                                    "lastOne": True,
                                }
                            ]
                        }
                    )
                ),
                b"data: [DONE]\n\n",
            ]
        )
        adapter = _adapter(transport)

        deltas = list(adapter.stream(_request()))

        self.assertEqual(deltas, ['{"action', '_type": "DONE"}'])

    def test_eof_without_any_termination_marker_fails_closed(self) -> None:
        # Round-3 contract correction (external review 高#2): a stream
        # that exhausts without EVER carrying ``finish_reason`` or the
        # ``data: [DONE]`` sentinel is truncated and must fail closed
        # as ``LLM_CALL_FAILED`` per SPEC.md "Real adapter" (the
        # fail-closed-on-exhaustion sentence).  The previous lenient
        # expectation — content returned with no terminator — was the
        # defect under fix; see .round3-baseline/t1-evidence.md for the
        # itemized contract-correction disclosure.
        transport = _FakeTransport([_content_chunk('{"action_type": "DONE"}')])
        adapter = _adapter(transport)

        with self.assertRaises(V2OpenAIAdapterError) as caught:
            list(adapter.stream(_request()))

        self.assertEqual(caught.exception.code, "LLM_CALL_FAILED")

    def test_malformed_data_lines_are_skipped(self) -> None:
        transport = _FakeTransport(
            [
                b"data: not-json-at-all\n\n",
                b": keep-alive comment\n\n",
                b"event: ping\n\n",
                _content_chunk('{"action_type": "DONE"}'),
                b"data: [DONE]\n\n",
            ]
        )
        adapter = _adapter(transport)

        deltas = list(adapter.stream(_request()))

        self.assertEqual(deltas, ['{"action_type": "DONE"}'])

    def test_generate_aggregates_and_parses_the_action(self) -> None:
        transport = _FakeTransport(
            [
                _content_chunk('{"action_type": '),
                _content_chunk('"DONE"}'),
                b"data: [DONE]\n\n",
            ]
        )
        adapter = _adapter(transport)

        action = adapter.generate(_request())

        self.assertEqual(action, {"action_type": "DONE"})

    def test_stream_exceeding_the_closed_byte_bound_fails(self) -> None:
        transport = _FakeTransport([_content_chunk("x" * 32), _content_chunk("y" * 32)])
        adapter = _adapter(transport)

        with mock.patch("vespercode.llm.v2_openai_adapter._MAX_STREAM_BYTES", 48):
            with self.assertRaises(V2OpenAIAdapterError) as caught:
                list(adapter.stream(_request()))

        self.assertEqual(caught.exception.code, "LLM_CALL_FAILED")

    def test_transport_timeout_maps_to_llm_call_failed(self) -> None:
        transport = _FakeTransport(exception=TimeoutError("read timed out"))
        adapter = _adapter(transport)

        with self.assertRaises(V2OpenAIAdapterError) as caught:
            list(adapter.stream(_request()))

        self.assertEqual(caught.exception.code, "LLM_CALL_FAILED")


class V2OpenAIAdapterConfigTests(unittest.TestCase):
    def test_request_shape_url_headers_and_body(self) -> None:
        transport = _FakeTransport([b"data: [DONE]\n\n"])
        adapter = _adapter(
            transport, base_url="https://gateway.example/v1", model="stub-model"
        )

        list(adapter.stream(_request(("earlier feedback",))))

        url, headers, body = transport.calls[0]
        self.assertEqual(url, "https://gateway.example/v1/chat/completions")
        self.assertEqual(headers["Authorization"], "Bearer stub-key-not-a-secret")
        self.assertEqual(headers["Content-Type"], "application/json")
        payload = json.loads(body.decode("utf-8"))
        self.assertEqual(payload["model"], "stub-model")
        self.assertTrue(payload["stream"] is True)
        roles = [message["role"] for message in payload["messages"]]
        self.assertEqual(roles, ["system", "user"])
        self.assertIn("fix the example", payload["messages"][1]["content"])
        self.assertIn("earlier feedback", payload["messages"][1]["content"])

    def test_missing_api_key_fails_closed_with_guidance(self) -> None:
        with mock.patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(V2OpenAIAdapterError) as caught:
                V2OpenAICompatLLM(
                    api_key_provider=lambda: None, transport=_FakeTransport()
                )

        self.assertEqual(caught.exception.code, "CONFIG_MISSING")
        self.assertIn(V2_OPENAI_API_KEY_ENV, str(caught.exception))

    def test_env_fallbacks_for_base_url_and_model(self) -> None:
        transport = _FakeTransport([b"data: [DONE]\n\n"])
        environment = {
            "VESPERCODE_V2_BASE_URL": "https://env-gateway.example/v1",
            "VESPERCODE_V2_MODEL": "env-model",
        }
        with mock.patch.dict(os.environ, environment, clear=True):
            adapter = V2OpenAICompatLLM(
                api_key_provider=lambda: "stub-key-not-a-secret",
                transport=transport,
            )
            list(adapter.stream(_request()))

        url, _, body = transport.calls[0]
        self.assertEqual(url, "https://env-gateway.example/v1/chat/completions")
        self.assertEqual(json.loads(body)["model"], "env-model")

    def test_explicit_arguments_override_the_environment(self) -> None:
        transport = _FakeTransport([b"data: [DONE]\n\n"])
        environment = {
            "VESPERCODE_V2_BASE_URL": "https://env-gateway.example/v1",
            "VESPERCODE_V2_MODEL": "env-model",
        }
        with mock.patch.dict(os.environ, environment, clear=True):
            adapter = _adapter(
                transport,
                base_url="https://flag.example/v1",
                model="flag-model",
            )
            list(adapter.stream(_request()))

        url, _, body = transport.calls[0]
        self.assertEqual(url, "https://flag.example/v1/chat/completions")
        self.assertEqual(json.loads(body)["model"], "flag-model")

    def test_defaults_match_the_verified_longcat_endpoint(self) -> None:
        transport = _FakeTransport([b"data: [DONE]\n\n"])
        with mock.patch.dict(os.environ, {}, clear=True):
            adapter = V2OpenAICompatLLM(
                api_key_provider=lambda: "stub-key-not-a-secret",
                transport=transport,
            )
            list(adapter.stream(_request()))

        url, _, body = transport.calls[0]
        self.assertEqual(url, V2_OPENAI_DEFAULT_BASE_URL + "/chat/completions")
        self.assertEqual(json.loads(body)["model"], V2_OPENAI_DEFAULT_MODEL)

    def test_v1_contract_types_are_never_imported(self) -> None:
        import vespercode.llm.v2_openai_adapter as module

        with open(module.__file__, encoding="utf-8") as stream:
            source = stream.read()
        for forbidden in (
            "from vespercode.llm.base import",
            "from vespercode.llm.openai_adapter import",
            "from vespercode.credentials.port import",
            "from vespercode.profiles.endpoints import",
        ):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()

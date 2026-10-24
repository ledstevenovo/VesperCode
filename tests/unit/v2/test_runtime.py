from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from vespercode.llm.v2 import ScriptedLLMV2
from vespercode.loop.v2_engine import V2AgentLoop, V2ActionError
from vespercode.memory.v2 import V2Memory
from vespercode.tools.v2_dispatcher import InMemoryWorkspacePort, V2ToolDispatcher


class V2RuntimeTests(unittest.TestCase):
    def test_memory_rejects_secret_like_feedback(self) -> None:
        memory = V2Memory()

        for text in (
            "api_key=top-secret",
            "access_token=top-secret",
            "Bearer top-secret",
            "password: top-secret",
            "-----BEGIN RSA PRIVATE KEY-----",
        ):
            with self.assertRaises(ValueError):
                memory.remember("run-a", text, source="feedback")

    def test_llm_failure_stops_without_an_implicit_retry(self) -> None:
        class BrokenLLM:
            def generate(self, request: object) -> dict[str, object]:
                raise RuntimeError("provider unavailable")

        with tempfile.TemporaryDirectory() as directory:
            loop = V2AgentLoop(
                workspace=Path(directory),
                llm=BrokenLLM(),
                dispatcher=V2ToolDispatcher(InMemoryWorkspacePort()),
                memory=V2Memory(),
                max_turns=5,
            )
            result = loop.run("handle provider failure")

        self.assertEqual(result.status, "STOPPED")
        self.assertEqual(result.stop_reason, "LLM_CALL_FAILED")
        self.assertEqual(result.turns, 1)
        self.assertEqual(result.results[0].status, "FAILED")
        self.assertIn("LLM call failed", result.results[0].message)

    def test_dangerous_action_is_blocked_and_feedback_drives_recovery(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            llm = ScriptedLLMV2(
                [
                    {
                        "action_type": "REPLACE",
                        "path": "tests/test_example.py",
                        "content": "bad",
                    },
                    {
                        "action_type": "REPLACE",
                        "path": "src/example.py",
                        "content": "fixed",
                    },
                    {"action_type": "DONE"},
                ]
            )
            port = InMemoryWorkspacePort()
            loop = V2AgentLoop(
                workspace=workspace,
                llm=llm,
                dispatcher=V2ToolDispatcher(port),
                memory=V2Memory(),
                max_turns=5,
            )

            result = loop.run("fix the failing example")

        self.assertEqual(result.status, "SUCCEEDED")
        self.assertEqual(result.turns, 3)
        self.assertEqual(result.results[0].status, "DENIED")
        self.assertIn("protected", result.results[0].message)
        self.assertEqual(result.results[1].status, "SUCCESS")
        self.assertEqual(port.files["src/example.py"], "fixed")
        self.assertGreaterEqual(len(llm.contexts[1]), len(llm.contexts[0]))

    def test_memory_is_scoped_to_the_run_and_stop_is_deterministic(self) -> None:
        memory = V2Memory()
        memory.remember("run-a", "failure: calculator", source="feedback")
        memory.remember("run-b", "secret from another run", source="feedback")

        with tempfile.TemporaryDirectory() as directory:
            loop = V2AgentLoop(
                workspace=Path(directory),
                llm=ScriptedLLMV2([{"action_type": "DONE"}]),
                dispatcher=V2ToolDispatcher(InMemoryWorkspacePort()),
                memory=memory,
                max_turns=2,
            )
            result = loop.run("continue", run_id="run-a")

        self.assertEqual(result.status, "SUCCEEDED")
        self.assertEqual(result.turns, 1)
        self.assertIn("failure: calculator", result.contexts[0])
        self.assertNotIn("secret from another run", result.contexts[0])

    def test_invalid_model_action_is_reported_and_max_turns_stops(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            loop = V2AgentLoop(
                workspace=Path(directory),
                llm=ScriptedLLMV2(
                    [{"action_type": "REPLACE", "action_id": "model-owned"}]
                ),
                dispatcher=V2ToolDispatcher(InMemoryWorkspacePort()),
                memory=V2Memory(),
                max_turns=1,
            )
            result = loop.run("bad model")

        self.assertEqual(result.status, "STOPPED")
        self.assertEqual(result.stop_reason, "MAX_TURNS")
        self.assertEqual(result.results[0].status, "FAILED")
        self.assertIsInstance(result.results[0].error, V2ActionError)

    def test_unknown_action_fields_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            loop = V2AgentLoop(
                workspace=Path(directory),
                llm=ScriptedLLMV2(
                    [
                        {
                            "action_type": "REPLACE",
                            "path": "src/a.py",
                            "content": "x",
                            "shell": "no",
                        }
                    ]
                ),
                dispatcher=V2ToolDispatcher(InMemoryWorkspacePort()),
                memory=V2Memory(),
                max_turns=1,
            )
            result = loop.run("reject extras")

        self.assertEqual(result.status, "STOPPED")
        self.assertEqual(result.results[0].status, "FAILED")

    def test_done_action_cannot_carry_write_fields(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            loop = V2AgentLoop(
                workspace=Path(directory),
                llm=ScriptedLLMV2([{"action_type": "DONE", "path": "src/a.py"}]),
                dispatcher=V2ToolDispatcher(InMemoryWorkspacePort()),
                memory=V2Memory(),
                max_turns=1,
            )
            result = loop.run("reject done extras")

        self.assertEqual(result.status, "STOPPED")
        self.assertEqual(result.results[0].status, "FAILED")


if __name__ == "__main__":
    unittest.main()

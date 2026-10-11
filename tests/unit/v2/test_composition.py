from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import vespercode
from vespercode.llm.v2 import ScriptedLLMV2
from vespercode.runtime_v2 import V2Harness, V2HarnessConfig
from scripts.run_v2_demo import run_demo


class V2CompositionTests(unittest.TestCase):
    def test_unexpected_loop_failure_stops_the_persisted_run(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            harness = V2Harness(V2HarnessConfig(root, root / "control"))
            try:
                run_ids: list[str] = []
                original_create_run = harness.database.create_run

                def capture_run(workspace_path: str) -> str:
                    run_id = original_create_run(workspace_path)
                    run_ids.append(run_id)
                    return run_id

                with patch.object(harness.database, "create_run", side_effect=capture_run):
                    with patch(
                        "vespercode.runtime_v2.V2AgentLoop.run",
                        side_effect=RuntimeError("unexpected loop failure"),
                    ):
                        with self.assertRaisesRegex(RuntimeError, "unexpected loop"):
                            harness.run("fail", ScriptedLLMV2([{"action_type": "DONE"}]))
                rows = harness.database.get_run(run_ids[0])
            finally:
                harness.close()

        self.assertIsNotNone(rows)
        self.assertEqual(rows["status"], "STOPPED")
        self.assertIsNone(rows["phase"])
    def test_package_identity_exposes_v2_alpha_and_legacy_version(self) -> None:
        self.assertEqual(vespercode.__version__, "0.2.0a0")
        self.assertEqual(vespercode.V2_VERSION, "0.2.0a0")
        self.assertEqual(vespercode.LEGACY_VERSION, "0.1.0")

    def test_composition_creates_run_enters_loop_and_records_terminal_state(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            harness = V2Harness(V2HarnessConfig(root, root / "control"))
            try:
                result = harness.run(
                    "finish",
                    ScriptedLLMV2([{"action_type": "DONE"}]),
                )
                row = harness.database.get_run(result.run_id)
            finally:
                harness.close()

        assert row is not None
        self.assertEqual(row["status"], "SUCCEEDED")
        self.assertIsNone(row["phase"])
        self.assertEqual(row["revision"], 3)
        self.assertEqual(result.database_path.name, "vespercode-v2.sqlite")

    def test_repeatable_demo_has_block_recovery_and_completion(self) -> None:
        first = run_demo()
        second = run_demo()

        self.assertEqual(first["status"], "SUCCEEDED")
        self.assertEqual(first["turns"], 3)
        self.assertEqual(first["corrected_paths"], ["src/example.py"])
        self.assertEqual(first["stages"][0]["status"], "DENIED")
        self.assertEqual(first["stages"][1]["status"], "SUCCESS")
        self.assertEqual(first["status"], second["status"])
        self.assertEqual(first["turns"], second["turns"])
        self.assertEqual(first["stages"], second["stages"])


if __name__ == "__main__":
    unittest.main()

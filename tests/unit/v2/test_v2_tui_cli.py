"""The ``vespercode-v2 tui`` command surface (offline, injectable)."""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from vespercode.cli_v2 import V2CliComposition
from vespercode.llm.v2_openai_adapter import V2OpenAICompatLLM
from vespercode.tui.v2_launch import DEFAULT_DEMO_TASK, V2TuiLaunchSpec

_REPO_ROOT = Path(__file__).resolve().parents[3]

_LAZY_IMPORT_PROOF = (
    "import sys\n"
    "class _BlockTextual:\n"
    "    def find_spec(self, name, path=None, target=None):\n"
    "        if name == 'textual' or name.startswith('textual.'):\n"
    "            raise ImportError('textual is blocked in this proof')\n"
    "        return None\n"
    "sys.meta_path.insert(0, _BlockTextual())\n"
    "import vespercode.cli_v2\n"
    "import vespercode.tui\n"
    "import vespercode.tui.v2_launch\n"
    "import vespercode.tui.v2_view_model\n"
    "print('lazy-import-ok')\n"
)


class V2TuiCliTests(unittest.TestCase):
    @staticmethod
    def _recording_launcher(specs: list[V2TuiLaunchSpec]):
        def launcher(spec: V2TuiLaunchSpec) -> int:
            specs.append(spec)
            return 0

        return launcher

    def test_tui_command_builds_the_scripted_demo_spec(self) -> None:
        specs: list[V2TuiLaunchSpec] = []
        cli = V2CliComposition(tui_launcher=self._recording_launcher(specs))
        with tempfile.TemporaryDirectory() as directory:
            code = cli.run(["tui", "--workspace", directory])

        self.assertEqual(code, 0)
        self.assertEqual(len(specs), 1)
        spec = specs[0]
        self.assertIsInstance(spec.workspace, Path)
        self.assertEqual(spec.task, DEFAULT_DEMO_TASK)
        self.assertEqual(spec.max_turns, 20)
        llm = spec.llm_factory()
        self.assertTrue(hasattr(llm, "stream_events"))

    def test_tui_command_honors_task_and_max_turns(self) -> None:
        specs: list[V2TuiLaunchSpec] = []
        cli = V2CliComposition(tui_launcher=self._recording_launcher(specs))
        with tempfile.TemporaryDirectory() as directory:
            code = cli.run(
                [
                    "tui",
                    "--workspace",
                    directory,
                    "--task",
                    "custom task",
                    "--max-turns",
                    "3",
                ]
            )

        self.assertEqual(code, 0)
        self.assertEqual(specs[0].task, "custom task")
        self.assertEqual(specs[0].max_turns, 3)

    def test_tui_command_requires_an_existing_workspace(self) -> None:
        cli = V2CliComposition(tui_launcher=lambda spec: 0)
        with self.assertRaises(SystemExit) as caught:
            cli.run(["tui", "--workspace", "Z:/definitely/not/here"])

        self.assertEqual(caught.exception.code, 2)

    def test_tui_command_rejects_an_empty_task(self) -> None:
        cli = V2CliComposition(tui_launcher=lambda spec: 0)
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(SystemExit):
                cli.run(["tui", "--workspace", directory, "--task", ""])

    def test_launcher_exception_propagates_as_a_failure_code(self) -> None:
        def failing_launcher(spec: V2TuiLaunchSpec) -> int:
            raise RuntimeError("no terminal here")

        cli = V2CliComposition(tui_launcher=failing_launcher)
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(RuntimeError):
                cli.run(["tui", "--workspace", directory])

    def test_tui_openai_option_builds_the_real_adapter(self) -> None:
        specs: list[V2TuiLaunchSpec] = []
        cli = V2CliComposition(tui_launcher=self._recording_launcher(specs))
        environment = {
            "VESPERCODE_V2_BASE_URL": "",
            "VESPERCODE_V2_MODEL": "",
            "VESPERCODE_V2_API_KEY": "",
        }
        with mock.patch.dict(os.environ, environment, clear=True):
            os.environ["VESPERCODE_V2_API_KEY"] = "stub-key-not-a-secret"
            try:
                with tempfile.TemporaryDirectory() as directory:
                    code = cli.run(
                        [
                            "tui",
                            "--workspace",
                            directory,
                            "--llm",
                            "openai",
                            "--base-url",
                            "https://flag.example/v1",
                            "--model",
                            "flag-model",
                        ]
                    )
            finally:
                os.environ.pop("VESPERCODE_V2_API_KEY", None)

        self.assertEqual(code, 0)
        llm = specs[0].llm_factory()
        self.assertIsInstance(llm, V2OpenAICompatLLM)

    def test_tui_openai_option_without_a_key_fails_with_guidance(self) -> None:
        cli = V2CliComposition(tui_launcher=lambda spec: 0)
        environment = {"VESPERCODE_V2_API_KEY": ""}
        with mock.patch.dict(os.environ, environment, clear=True):
            with tempfile.TemporaryDirectory() as directory:
                code = cli.run(["tui", "--workspace", directory, "--llm", "openai"])

        self.assertEqual(code, 1)

    def test_tui_scripted_option_needs_no_key(self) -> None:
        specs: list[V2TuiLaunchSpec] = []
        cli = V2CliComposition(tui_launcher=self._recording_launcher(specs))
        with mock.patch.dict(os.environ, {}, clear=True):
            with tempfile.TemporaryDirectory() as directory:
                code = cli.run(["tui", "--workspace", directory, "--llm", "scripted"])

        self.assertEqual(code, 0)
        self.assertTrue(hasattr(specs[0].llm_factory(), "stream_events"))

    def test_core_modules_import_without_textual_installed(self) -> None:
        """The TUI ships lazily: the CLI core never imports textual."""
        import os

        environment = dict(os.environ)
        environment["PYTHONPATH"] = str(_REPO_ROOT / "src")
        completed = subprocess.run(
            [sys.executable, "-c", _LAZY_IMPORT_PROOF],
            capture_output=True,
            text=True,
            env=environment,
            timeout=120,
        )

        self.assertEqual(
            completed.returncode,
            0,
            f"stderr: {completed.stderr}",
        )
        self.assertIn("lazy-import-ok", completed.stdout)


if __name__ == "__main__":
    unittest.main()

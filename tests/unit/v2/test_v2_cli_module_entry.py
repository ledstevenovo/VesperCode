"""The module entry point of the v2 CLI (``python -m vespercode.cli_v2``).

``README.md`` documents ``python -m vespercode.cli_v2 <command>`` as the
source-checkout form of the ``vespercode-v2`` console script.  Before this
test file existed ``src/vespercode/cli_v2.py`` had no ``__main__`` guard, so
every one of those documented invocations was a silent no-op: the module was
imported, nothing ran, and the process exited 0 with empty stdout.

A real subprocess is the only way to observe ``python -m`` behavior, so these
tests launch one with a hard timeout (a hanging interactive surface can never
hang the suite) and only use the non-interactive ``--help`` / usage-error
forms.  Nothing here imports ``textual`` at any level, so this file adds no
skip to a textual-free baseline.
"""

from __future__ import annotations

import os
import subprocess
import sys
import unittest
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[3]
_SRC = _REPO_ROOT / "src"
_TIMEOUT_SECONDS = 60

#: The closed subcommand set README documents for ``python -m vespercode.cli_v2``.
_DOCUMENTED_COMMANDS = (
    "run",
    "status",
    "writeback",
    "recovery",
    "credential-status",
    "disclosure-status",
    "serve",
    "tui",
)


def _run_module(*args: str) -> "subprocess.CompletedProcess[str]":
    """Run ``python -m vespercode.cli_v2 <args>`` with a hard timeout."""

    environment = dict(os.environ)
    environment["PYTHONPATH"] = str(_SRC)
    environment["PYTHONIOENCODING"] = "utf-8"
    return subprocess.run(
        [sys.executable, "-m", "vespercode.cli_v2", *args],
        cwd=str(_REPO_ROOT),
        env=environment,
        capture_output=True,
        text=True,
        timeout=_TIMEOUT_SECONDS,
    )


class V2CliModuleEntryTests(unittest.TestCase):
    """``python -m vespercode.cli_v2`` must behave like ``vespercode-v2``."""

    def test_help_writes_usage_to_stdout(self) -> None:
        completed = _run_module("--help")

        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertNotEqual(
            completed.stdout.strip(),
            "",
            "python -m vespercode.cli_v2 --help produced no stdout (no-op module)",
        )
        self.assertIn("vespercode-v2", completed.stdout)

    def test_help_lists_every_documented_subcommand(self) -> None:
        completed = _run_module("--help")

        self.assertEqual(completed.returncode, 0, completed.stderr)
        for command in _DOCUMENTED_COMMANDS:
            with self.subTest(command=command):
                self.assertIn(command, completed.stdout)

    def test_missing_command_is_a_usage_error(self) -> None:
        completed = _run_module()

        self.assertEqual(completed.returncode, 2, completed.stderr)
        self.assertEqual(completed.stdout, "")
        self.assertNotEqual(
            completed.stderr.strip(),
            "",
            "python -m vespercode.cli_v2 with no command must report a usage error",
        )


if __name__ == "__main__":
    unittest.main()

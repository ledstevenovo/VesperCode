"""Route B / B3: the closed local v2 CLI surface.

``vespercode.cli_v2`` is the standard-library-only v2 command line: a
closed argparse grammar (no shell, argv passthrough, provider URL, or
secret options exist), bounded typed arguments, preview-by-default
writeback and recovery with explicit ``--apply`` switches, bounded
non-revealing projections, and an injectable composition (LLM factory,
shell factory, server launcher, output streams) that keeps every test
offline and deterministic.  The legacy v1 ``vespercode`` CLI is a
separate frozen module and is never imported here.
"""

from __future__ import annotations

import argparse
import io
import tempfile
import unittest
from pathlib import Path

from vespercode.cli_v2 import (
    V2_CLI_DEFAULT_PORT,
    V2CliComposition,
    build_v2_cli_parser,
)
from vespercode.contracts.v2_writeback import JournalEntryV2
from vespercode.credentials.v2_port import V2CredentialSecret
from vespercode.governance.v2_disclosure import DisclosurePathScopeV2
from vespercode.llm.v2 import ScriptedLLMV2
from vespercode.shell_v2 import V2LocalShell

_FORBIDDEN_OPTIONS = (
    # No shell, argv passthrough, or provider-connection surface exists:
    # --provider is deliberately absent because the only provider-shaped
    # argument is the bounded identifier of the non-revealing
    # credential-status lookup (never a URL, endpoint, or secret).
    "--provider-url",
    "--secret",
    "--api-key",
    "--url",
    "--endpoint",
    "--credential",
    "--token",
    "--shell",
    "--exec",
    "--policy",
    "--profile",
)


def _llm_factory() -> ScriptedLLMV2:
    return ScriptedLLMV2(
        [
            {
                "action_type": "REPLACE",
                "path": "src/example.py",
                "content": "corrected body",
            },
            {"action_type": "DONE"},
        ]
    )


class V2CliWorkspaceTests(unittest.TestCase):
    def setUp(self) -> None:
        self._directory = tempfile.TemporaryDirectory()
        # A cleanup (not tearDown) so every shell closes before the
        # directory is deleted on Windows (cleanups run LIFO).
        self.addCleanup(self._directory.cleanup)
        self.workspace = Path(self._directory.name) / "workspace"
        (self.workspace / "src").mkdir(parents=True)
        (self.workspace / "src" / "example.py").write_text(
            "old body", encoding="utf-8"
        )
        self.out = io.StringIO()
        self.errors = io.StringIO()
        self.launches: list[tuple[object, str, int]] = []

    def _composition(self, **overrides) -> V2CliComposition:
        parameters: dict[str, object] = {
            "llm_factory": _llm_factory,
            "stream": self.out,
            "error_stream": self.errors,
            "web_launcher": self._launcher,
        }
        parameters.update(overrides)
        return V2CliComposition(**parameters)  # type: ignore[arg-type]

    def _launcher(self, app: object, host: str, port: int) -> object:
        self.launches.append((app, host, port))
        return None

    def _shell_factory_with_transaction(
        self, workspace: Path, max_turns: int
    ):
        def factory(workspace: Path, max_turns: int) -> V2LocalShell:
            shell = V2LocalShell(
                workspace=workspace,
                llm_factory=_llm_factory,
            )
            if not shell.pending_transaction_ids():
                database = shell.database
                run_id = database.create_run(str(workspace))
                snapshot_id = database.create_snapshot(run_id)
                candidate_id = database.create_candidate(run_id, snapshot_id)
                approval_id = database.create_writeback_approval(
                    run_id=run_id,
                    candidate_id=candidate_id,
                    candidate_revision=0,
                )
                database.begin_writeback_transaction(
                    run_id=run_id,
                    candidate_id=candidate_id,
                    candidate_revision=0,
                    approval_id=approval_id,
                    entries=(
                        JournalEntryV2(
                            0, "src/recovered.py", "CREATE", "recovered", None
                        ),
                    ),
                )
            return shell

        return factory

    # ------------------------------------------------------------------
    # closed grammar
    # ------------------------------------------------------------------

    def test_the_parser_grammar_is_closed(self) -> None:
        parser = build_v2_cli_parser()
        subparsers_action = next(
            action
            for action in parser._actions
            if isinstance(action, argparse._SubParsersAction)
        )
        commands = set(subparsers_action.choices)
        self.assertEqual(
            commands,
            {
                "run",
                "status",
                "writeback",
                "recovery",
                "credential-status",
                "disclosure-status",
                "serve",
                "tui",
            },
        )
        options: set[str] = set()
        for subparser in subparsers_action.choices.values():
            for action in subparser._actions:
                options.update(action.option_strings)
        for forbidden in _FORBIDDEN_OPTIONS:
            self.assertNotIn(forbidden, options)

    def test_unknown_and_forbidden_arguments_reject(self) -> None:
        composition = self._composition()
        for argv in (
            ["run", "--workspace", str(self.workspace), "--task", "t", "--secret", "x"],
            ["run", "--workspace", str(self.workspace), "--task", "t", "--provider-url", "http://x"],
            ["run", "--task", "t"],
            ["run", "--workspace", str(self.workspace), "--task", ""],
            ["run", "--workspace", str(self.workspace), "--task", "t", "--max-turns", "0"],
            ["status", "--workspace", str(self.workspace), "--run-id", "../evil"],
            ["serve", "--host", "0.0.0.0"],
            ["serve", "--port", "99999"],
            ["serve", "--port", "abc"],
            ["totally-unknown-command"],
        ):
            with self.assertRaises(SystemExit) as caught:
                composition.run(argv)
            self.assertEqual(caught.exception.code, 2, argv)

    def test_workspace_must_be_an_existing_directory(self) -> None:
        composition = self._composition()
        with self.assertRaises(SystemExit) as caught:
            composition.run(
                [
                    "run",
                    "--workspace",
                    str(self.workspace / "missing"),
                    "--task",
                    "t",
                ]
            )
        self.assertEqual(caught.exception.code, 2)

    # ------------------------------------------------------------------
    # run / status projections
    # ------------------------------------------------------------------

    def test_run_projects_the_run_without_writing_files(self) -> None:
        composition = self._composition()

        code = composition.run(
            ["run", "--workspace", str(self.workspace), "--task", "repair it"]
        )

        self.assertEqual(code, 0)
        output = self.out.getvalue()
        self.assertIn("run_id:", output)
        self.assertIn("loop_status: SUCCEEDED", output)
        self.assertIn("stop_reason: DONE", output)
        self.assertIn("candidate_id:", output)
        self.assertEqual(
            (self.workspace / "src" / "example.py").read_text(encoding="utf-8"),
            "old body",
        )

    def test_run_without_an_llm_boundary_fails_closed(self) -> None:
        composition = self._composition(llm_factory=None)

        code = composition.run(
            ["run", "--workspace", str(self.workspace), "--task", "repair it"]
        )

        self.assertEqual(code, 1)
        self.assertIn("NO_LLM_BOUNDARY", self.errors.getvalue())
        self.assertEqual(self.out.getvalue(), "")

    def test_status_projects_recorded_runs(self) -> None:
        composition = self._composition()
        composition.run(
            ["run", "--workspace", str(self.workspace), "--task", "repair it"]
        )
        self.out.seek(0)
        self.out.truncate(0)

        code = composition.run(["status", "--workspace", str(self.workspace)])

        self.assertEqual(code, 0)
        output = self.out.getvalue()
        self.assertIn("status=SUCCEEDED", output)

        code = composition.run(
            ["status", "--workspace", str(self.workspace), "--run-id", "no-such-run"]
        )
        self.assertEqual(code, 1)

    # ------------------------------------------------------------------
    # writeback: preview by default, explicit apply
    # ------------------------------------------------------------------

    def test_writeback_previews_by_default_and_writes_nothing(self) -> None:
        composition = self._composition()

        code = composition.run(
            [
                "writeback",
                "--workspace",
                str(self.workspace),
                "--task",
                "repair it",
            ]
        )

        self.assertEqual(code, 0)
        output = self.out.getvalue()
        self.assertIn("staged writes: 1", output)
        self.assertIn("src/example.py", output)
        self.assertIn("approval: not created", output)
        self.assertEqual(
            (self.workspace / "src" / "example.py").read_text(encoding="utf-8"),
            "old body",
        )

    def test_writeback_apply_writes_the_file_and_reports_the_transaction(
        self,
    ) -> None:
        composition = self._composition()

        code = composition.run(
            [
                "writeback",
                "--workspace",
                str(self.workspace),
                "--task",
                "repair it",
                "--apply",
            ]
        )

        self.assertEqual(code, 0)
        output = self.out.getvalue()
        self.assertIn("approval_id:", output)
        self.assertIn("writeback: COMMITTED", output)
        self.assertEqual(
            (self.workspace / "src" / "example.py").read_text(encoding="utf-8"),
            "corrected body",
        )

    # ------------------------------------------------------------------
    # recovery: preview by default, explicit apply
    # ------------------------------------------------------------------

    def test_recovery_lists_pending_transactions(self) -> None:
        composition = self._composition(
            shell_factory=self._shell_factory_with_transaction(
                self.workspace, max_turns=20
            )
        )

        code = composition.run(["recovery", "--workspace", str(self.workspace)])

        self.assertEqual(code, 0)
        output = self.out.getvalue()
        self.assertIn("pending transactions: 1", output)

    def test_recovery_previews_without_applying_by_default(self) -> None:
        composition = self._composition(
            shell_factory=self._shell_factory_with_transaction(
                self.workspace, max_turns=20
            )
        )
        header = composition.run(["recovery", "--workspace", str(self.workspace)])
        self.assertEqual(header, 0)
        transaction_id_line = next(
            line
            for line in self.out.getvalue().splitlines()
            if line.startswith("transaction: ")
        )
        transaction_id = transaction_id_line.split(" ", 1)[1]

        code = composition.run(
            [
                "recovery",
                "--workspace",
                str(self.workspace),
                "--transaction-id",
                transaction_id,
            ]
        )

        self.assertEqual(code, 0)
        output = self.out.getvalue()
        self.assertIn("state: PREPARED", output)
        self.assertIn("src/recovered.py", output)
        self.assertFalse((self.workspace / "src" / "recovered.py").exists())

    def test_recovery_apply_completes_the_transaction(self) -> None:
        composition = self._composition(
            shell_factory=self._shell_factory_with_transaction(
                self.workspace, max_turns=20
            )
        )
        composition.run(["recovery", "--workspace", str(self.workspace)])
        transaction_id_line = next(
            line
            for line in self.out.getvalue().splitlines()
            if line.startswith("transaction: ")
        )
        transaction_id = transaction_id_line.split(" ", 1)[1]

        code = composition.run(
            [
                "recovery",
                "--workspace",
                str(self.workspace),
                "--transaction-id",
                transaction_id,
                "--apply",
            ]
        )

        self.assertEqual(code, 0)
        self.assertIn("recovery: APPLIED", self.out.getvalue())
        self.assertEqual(
            (self.workspace / "src" / "recovered.py").read_text(encoding="utf-8"),
            "recovered",
        )

    def test_recovery_apply_requires_an_explicit_transaction(self) -> None:
        composition = self._composition()
        with self.assertRaises(SystemExit) as caught:
            composition.run(
                ["recovery", "--workspace", str(self.workspace), "--apply"]
            )
        self.assertEqual(caught.exception.code, 2)

    # ------------------------------------------------------------------
    # non-revealing credential / disclosure projections
    # ------------------------------------------------------------------

    def test_credential_status_never_prints_the_secret(self) -> None:
        def factory(workspace: Path, max_turns: int) -> V2LocalShell:
            from vespercode.credentials.v2_port import (
                InMemoryV2CredentialProvider,
            )

            port = InMemoryV2CredentialProvider()
            port.set(
                "openai",
                V2CredentialSecret.from_hidden_input("sk-cli-super-secret"),
            )
            return V2LocalShell(
                workspace=workspace, credential_port=port
            )

        composition = self._composition(shell_factory=factory)

        code = composition.run(
            [
                "credential-status",
                "--workspace",
                str(self.workspace),
                "--provider",
                "openai",
            ]
        )

        self.assertEqual(code, 0)
        output = self.out.getvalue()
        self.assertIn("provider: openai", output)
        self.assertIn("configured: yes", output)
        self.assertNotIn("sk-cli-super-secret", output)
        self.assertNotIn("sk-", output)

    def test_disclosure_status_prints_bounded_control_facts(self) -> None:
        composition = self._composition()
        shell = V2LocalShell(workspace=self.workspace)
        self.addCleanup(shell.close)
        database = shell.database
        run_id = database.create_run(str(self.workspace))
        disclosure_id = database.create_disclosure(run_id)
        from vespercode.profiles.v2_reference import ReferenceProfileRecordV2

        record = ReferenceProfileRecordV2(
            reference_profile_id="ref-profile-cli",
            profile_revision=0,
            python_version="3.12",
            pytest_version="8.4.2",
            ruff_version="0.16.1",
            mypy_version="2.3.0",
        )
        database.create_reference_profile(record)
        database.create_disclosure_grant(
            run_id=run_id,
            disclosure_id=disclosure_id,
            reference_profile_id=record.reference_profile_id,
            reference_profile_revision=record.profile_revision,
            expires_at="2999-01-01T00:00:00+00:00",
            byte_budget=2048,
            allowed_source_categories=("FILE_CONTENT",),
            allowed_source_paths=(DisclosurePathScopeV2("ROOT", ""),),
        )
        shell.close()

        code = composition.run(
            ["disclosure-status", "--workspace", str(self.workspace)]
        )

        self.assertEqual(code, 0)
        output = self.out.getvalue()
        self.assertIn("grant ", output)
        self.assertIn("status=PENDING", output)
        self.assertIn("budget=2048", output)
        self.assertIn("consumed=0", output)
        self.assertNotIn("sk-", output)

    # ------------------------------------------------------------------
    # serve composition
    # ------------------------------------------------------------------

    def test_serve_composes_the_local_web_app_on_loopback(self) -> None:
        composition = self._composition()

        code = composition.run(
            ["serve", "--workspace", str(self.workspace)]
        )

        self.assertEqual(code, 0)
        self.assertEqual(len(self.launches), 1)
        app, host, port = self.launches[0]
        self.assertEqual(host, "127.0.0.1")
        self.assertEqual(port, V2_CLI_DEFAULT_PORT)

    def test_serve_accepts_only_the_literal_loopback_host(self) -> None:
        composition = self._composition()
        with self.assertRaises(SystemExit) as caught:
            composition.run(
                [
                    "serve",
                    "--workspace",
                    str(self.workspace),
                    "--host",
                    "localhost",
                ]
            )
        self.assertEqual(caught.exception.code, 2)
        self.assertEqual(self.launches, [])


if __name__ == "__main__":
    unittest.main()

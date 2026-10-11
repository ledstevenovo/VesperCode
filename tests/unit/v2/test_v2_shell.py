"""Route B / B3: the local v2 services shell over V2Harness and B2 ports.

``V2LocalShell`` is the shared domain surface under the v2 CLI and the v2
local WebUI: it composes a real ``V2Harness`` (real v2 database, real
boundary-checked disk port) plus the B2 injectable credential port, and
projects bounded, non-revealing facts only.  These tests pin the shell
contract against real Route A services and a real temporary workspace:
runs are created and staged, approvals are explicit and revision-bound,
writeback writes real files, recovery drives durable transactions, and
credential/disclosure projections never carry a secret value.
"""

from __future__ import annotations

import dataclasses
import tempfile
import unittest
from pathlib import Path

from vespercode.contracts.v2_writeback import JournalEntryV2
from vespercode.credentials.v2_port import (
    InMemoryV2CredentialProvider,
    V2CredentialSecret,
)
from vespercode.governance.v2_disclosure import DisclosurePathScopeV2
from vespercode.llm.v2 import ScriptedLLMV2
from vespercode.profiles.v2_reference import ReferenceProfileRecordV2
from vespercode.shell_v2 import (
    V2DisclosureGrantSummaryV2,
    V2LocalShell,
    V2RunStartOutcomeV2,
    V2RunSummaryV2,
    V2ShellError,
)
from vespercode.storage.v2_database import V2_DATABASE_FILENAME


def _scripted_llm_factory():
    """One fresh deterministic LLM boundary per run (the injectable seam)."""

    def factory() -> ScriptedLLMV2:
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

    return factory


def _staging_llm_factory(path: str):
    def factory() -> ScriptedLLMV2:
        return ScriptedLLMV2(
            [
                {"action_type": "REPLACE", "path": path, "content": "evil"},
                {"action_type": "DONE"},
            ]
        )

    return factory


class V2LocalShellTests(unittest.TestCase):
    def setUp(self) -> None:
        self._directory = tempfile.TemporaryDirectory()
        # Registered as a cleanup (not tearDown) so shell connections close
        # first on Windows: cleanups run LIFO after tearDown.
        self.addCleanup(self._directory.cleanup)
        self.root = Path(self._directory.name)
        self.workspace = self.root / "workspace"
        (self.workspace / "src").mkdir(parents=True)
        (self.workspace / "src" / "example.py").write_text(
            "old body", encoding="utf-8"
        )
        self.credential_port = InMemoryV2CredentialProvider()

    def _shell(self, **overrides) -> V2LocalShell:
        parameters: dict[str, object] = {
            "workspace": self.workspace,
            "llm_factory": _scripted_llm_factory(),
            "credential_port": self.credential_port,
        }
        parameters.update(overrides)
        shell = V2LocalShell(**parameters)  # type: ignore[arg-type]
        self.addCleanup(shell.close)
        return shell

    # ------------------------------------------------------------------
    # run projection
    # ------------------------------------------------------------------

    def test_start_run_creates_a_run_and_stages_a_candidate(self) -> None:
        shell = self._shell()

        outcome = shell.start_run("repair the example")

        self.assertIsInstance(outcome, V2RunStartOutcomeV2)
        self.assertEqual(outcome.loop_status, "SUCCEEDED")
        self.assertEqual(outcome.stop_reason, "DONE")
        self.assertEqual(outcome.candidate_revision, 0)
        run = shell.run_detail(outcome.run_id)
        assert run is not None
        self.assertEqual(run.status, "SUCCEEDED")
        self.assertEqual(run.run_id, outcome.run_id)

    def test_start_run_without_an_llm_boundary_fails_closed(self) -> None:
        shell = self._shell(llm_factory=None)

        with self.assertRaises(V2ShellError) as caught:
            shell.start_run("repair the example")

        self.assertEqual(caught.exception.code, "NO_LLM_BOUNDARY")
        # The closed failure leaves no run behind.
        self.assertEqual(shell.recent_runs(), ())

    def test_recent_runs_and_run_detail_are_bounded_projections(self) -> None:
        shell = self._shell()
        outcome = shell.start_run("repair the example")

        runs = shell.recent_runs()

        self.assertEqual(len(runs), 1)
        self.assertIsInstance(runs[0], V2RunSummaryV2)
        self.assertEqual(runs[0].run_id, outcome.run_id)
        self.assertEqual(runs[0].status, "SUCCEEDED")
        # CREATED -> RUNNING -> SUCCEEDED advanced the run revision to 3.
        self.assertEqual(runs[0].revision, 3)
        self.assertIsNone(runs[0].phase)
        self.assertIsNone(shell.run_detail("00000000-0000-0000-0000-000000000000"))
        with self.assertRaises(ValueError):
            shell.recent_runs(limit=0)

    def test_unknown_run_detail_returns_none(self) -> None:
        shell = self._shell()
        self.assertIsNone(shell.run_detail("not-a-known-run"))

    # ------------------------------------------------------------------
    # writeback approval (explicit, revision-bound)
    # ------------------------------------------------------------------

    def test_create_writeback_approval_returns_a_pending_approval_id(self) -> None:
        shell = self._shell()
        outcome = shell.start_run("repair the example")

        approval_id = shell.create_writeback_approval(
            run_id=outcome.run_id,
            candidate_id=outcome.candidate_id,
            candidate_revision=outcome.candidate_revision,
        )

        approval = shell.database.get_writeback_approval(approval_id)
        assert approval is not None
        self.assertEqual(str(approval["status"]), "PENDING")

    def test_create_writeback_approval_rejects_unknown_and_mismatched_bindings(
        self,
    ) -> None:
        shell = self._shell()
        outcome = shell.start_run("repair the example")

        with self.assertRaises(V2ShellError) as caught:
            shell.create_writeback_approval(
                run_id="00000000-0000-0000-0000-000000000000",
                candidate_id=outcome.candidate_id,
                candidate_revision=0,
            )
        self.assertEqual(caught.exception.code, "UNKNOWN_RUN")

        with self.assertRaises(V2ShellError) as caught:
            shell.create_writeback_approval(
                run_id=outcome.run_id,
                candidate_id="00000000-0000-0000-0000-000000000000",
                candidate_revision=0,
            )
        self.assertEqual(caught.exception.code, "UNKNOWN_CANDIDATE")

        # A candidate from a different run is a mismatch, not a lookup miss.
        other = shell.start_run("second task")
        with self.assertRaises(V2ShellError) as caught:
            shell.create_writeback_approval(
                run_id=other.run_id,
                candidate_id=outcome.candidate_id,
                candidate_revision=0,
            )
        self.assertEqual(caught.exception.code, "RUN_CANDIDATE_MISMATCH")

    def test_create_writeback_approval_rejects_a_stale_revision(self) -> None:
        shell = self._shell()
        outcome = shell.start_run("repair the example")
        shell.database.advance_candidate(outcome.candidate_id, 0)

        with self.assertRaises(V2ShellError) as caught:
            shell.create_writeback_approval(
                run_id=outcome.run_id,
                candidate_id=outcome.candidate_id,
                candidate_revision=0,
            )
        self.assertEqual(caught.exception.code, "STALE_CANDIDATE_REVISION")

    def test_candidate_revision_projects_none_for_unknown_or_foreign(self) -> None:
        shell = self._shell()
        outcome = shell.start_run("repair the example")

        self.assertEqual(
            shell.candidate_revision(outcome.run_id, outcome.candidate_id), 0
        )
        self.assertIsNone(
            shell.candidate_revision(outcome.run_id, "unknown-candidate")
        )
        other = shell.start_run("second task")
        self.assertIsNone(
            shell.candidate_revision(other.run_id, outcome.candidate_id)
        )

    # ------------------------------------------------------------------
    # real writeback (Route A services, real disk)
    # ------------------------------------------------------------------

    def test_request_writeback_commits_the_staged_content_to_real_disk(
        self,
    ) -> None:
        shell = self._shell()
        outcome = shell.start_run("repair the example")
        approval_id = shell.create_writeback_approval(
            run_id=outcome.run_id,
            candidate_id=outcome.candidate_id,
            candidate_revision=outcome.candidate_revision,
        )

        result = shell.request_writeback(
            run_id=outcome.run_id,
            candidate_id=outcome.candidate_id,
            candidate_revision=outcome.candidate_revision,
            approval_id=approval_id,
        )

        self.assertEqual(result.status, "COMMITTED")
        self.assertEqual(
            (self.workspace / "src" / "example.py").read_text(encoding="utf-8"),
            "corrected body",
        )

    def test_request_writeback_with_a_stale_revision_writes_nothing(self) -> None:
        shell = self._shell()
        outcome = shell.start_run("repair the example")
        approval_id = shell.create_writeback_approval(
            run_id=outcome.run_id,
            candidate_id=outcome.candidate_id,
            candidate_revision=outcome.candidate_revision,
        )
        shell.database.advance_candidate(outcome.candidate_id, 0)

        result = shell.request_writeback(
            run_id=outcome.run_id,
            candidate_id=outcome.candidate_id,
            candidate_revision=0,
            approval_id=approval_id,
        )

        self.assertEqual(result.status, "STALE")
        self.assertEqual(
            (self.workspace / "src" / "example.py").read_text(encoding="utf-8"),
            "old body",
        )

    def test_request_writeback_without_staged_content_fails_closed(self) -> None:
        shell = self._shell()
        outcome = shell.start_run("repair the example")
        approval_id = shell.create_writeback_approval(
            run_id=outcome.run_id,
            candidate_id=outcome.candidate_id,
            candidate_revision=outcome.candidate_revision,
        )
        # A fresh shell over the same control database has no in-process
        # staging: writeback must refuse rather than write empty content.
        fresh = V2LocalShell(
            workspace=self.workspace,
            control_root=self.workspace / ".vespercode",
            credential_port=self.credential_port,
        )
        self.addCleanup(fresh.close)

        with self.assertRaises(V2ShellError) as caught:
            fresh.request_writeback(
                run_id=outcome.run_id,
                candidate_id=outcome.candidate_id,
                candidate_revision=0,
                approval_id=approval_id,
            )
        self.assertEqual(caught.exception.code, "NOTHING_STAGED")
        self.assertEqual(
            (self.workspace / "src" / "example.py").read_text(encoding="utf-8"),
            "old body",
        )

    def test_writeback_into_the_control_directory_is_denied(self) -> None:
        shell = self._shell(
            llm_factory=_staging_llm_factory(".vespercode/evil.txt"),
        )
        outcome = shell.start_run("repair the example")
        approval_id = shell.create_writeback_approval(
            run_id=outcome.run_id,
            candidate_id=outcome.candidate_id,
            candidate_revision=outcome.candidate_revision,
        )

        result = shell.request_writeback(
            run_id=outcome.run_id,
            candidate_id=outcome.candidate_id,
            candidate_revision=outcome.candidate_revision,
            approval_id=approval_id,
        )

        self.assertEqual(result.status, "DENIED")
        self.assertFalse((self.workspace / ".vespercode" / "evil.txt").exists())

    # ------------------------------------------------------------------
    # durable recovery (Route A services)
    # ------------------------------------------------------------------

    def _pending_transaction(self, shell: V2LocalShell) -> str:
        """Create a durable non-terminal transaction over the real port."""

        database = shell.database
        run_id = database.create_run(str(self.workspace))
        snapshot_id = database.create_snapshot(run_id)
        candidate_id = database.create_candidate(run_id, snapshot_id)
        approval_id = database.create_writeback_approval(
            run_id=run_id, candidate_id=candidate_id, candidate_revision=0
        )
        transaction_id = database.begin_writeback_transaction(
            run_id=run_id,
            candidate_id=candidate_id,
            candidate_revision=0,
            approval_id=approval_id,
            entries=(
                JournalEntryV2(0, "src/recovered.py", "CREATE", "recovered", None),
            ),
        )
        return transaction_id

    def test_pending_transaction_ids_and_recovery_preview(self) -> None:
        shell = self._shell()
        transaction_id = self._pending_transaction(shell)

        self.assertEqual(shell.pending_transaction_ids(), (transaction_id,))

        preview = shell.recovery_preview(transaction_id)

        self.assertEqual(preview.transaction_id, transaction_id)
        self.assertEqual(preview.transaction_state, "PREPARED")
        self.assertFalse(preview.blocked)
        self.assertEqual(preview.items[0].state, "PENDING")

    def test_recovery_apply_completes_the_transaction_on_real_disk(self) -> None:
        shell = self._shell()
        transaction_id = self._pending_transaction(shell)

        outcome = shell.recovery_apply(transaction_id)

        self.assertEqual(outcome.status, "APPLIED")
        self.assertEqual(
            (self.workspace / "src" / "recovered.py").read_text(encoding="utf-8"),
            "recovered",
        )
        self.assertEqual(shell.pending_transaction_ids(), ())

    def test_recovery_rejects_unknown_and_terminal_transactions(self) -> None:
        shell = self._shell()
        transaction_id = self._pending_transaction(shell)

        with self.assertRaises(V2ShellError) as caught:
            shell.recovery_preview("not-a-transaction")
        self.assertEqual(caught.exception.code, "UNKNOWN_TRANSACTION")
        with self.assertRaises(V2ShellError) as caught:
            shell.recovery_apply("not-a-transaction")
        self.assertEqual(caught.exception.code, "UNKNOWN_TRANSACTION")

        shell.recovery_apply(transaction_id)
        with self.assertRaises(V2ShellError) as caught:
            shell.recovery_preview(transaction_id)
        self.assertEqual(caught.exception.code, "NOT_RECOVERABLE")
        with self.assertRaises(V2ShellError) as caught:
            shell.recovery_apply(transaction_id)
        self.assertEqual(caught.exception.code, "NOT_RECOVERABLE")

    # ------------------------------------------------------------------
    # non-revealing credential / disclosure projections
    # ------------------------------------------------------------------

    def test_credential_status_projects_no_secret_value(self) -> None:
        self.credential_port.set(
            "openai", V2CredentialSecret.from_hidden_input("sk-super-secret")
        )
        shell = self._shell()

        status = shell.credential_status("openai")

        self.assertEqual(status.provider, "openai")
        self.assertTrue(status.configured)
        self.assertIsNotNone(status.updated_at)
        # The bounded projection carries only the three safe fields.
        self.assertEqual(
            {field.name for field in dataclasses.fields(status)},
            {"provider", "configured", "updated_at"},
        )
        with self.assertRaises(V2ShellError) as caught:
            shell.credential_status("not a provider!")
        self.assertEqual(caught.exception.code, "INVALID_PROVIDER")

    def test_disclosure_grant_summaries_are_bounded_control_facts(self) -> None:
        shell = self._shell()
        database = shell.database
        run_id = database.create_run(str(self.workspace))
        disclosure_id = database.create_disclosure(run_id)
        record = ReferenceProfileRecordV2(
            reference_profile_id="ref-profile-local",
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
            byte_budget=1024,
            allowed_source_categories=("FILE_CONTENT",),
            allowed_source_paths=(DisclosurePathScopeV2("ROOT", ""),),
        )

        summaries = shell.disclosure_grant_summaries()

        self.assertEqual(len(summaries), 1)
        summary = summaries[0]
        self.assertIsInstance(summary, V2DisclosureGrantSummaryV2)
        self.assertEqual(summary.run_id, run_id)
        self.assertEqual(summary.status, "PENDING")
        self.assertEqual(summary.byte_budget, 1024)
        self.assertEqual(summary.consumed_bytes, 0)
        self.assertEqual(
            {field.name for field in dataclasses.fields(summary)},
            {
                "grant_id",
                "disclosure_id",
                "run_id",
                "status",
                "expires_at",
                "byte_budget",
                "consumed_bytes",
            },
        )
        with self.assertRaises(ValueError):
            shell.disclosure_grant_summaries(limit=0)

    def test_shell_control_database_lives_under_the_workspace(self) -> None:
        shell = self._shell()
        self.assertEqual(
            shell.database_path,
            self.workspace / ".vespercode" / V2_DATABASE_FILENAME,
        )


if __name__ == "__main__":
    unittest.main()

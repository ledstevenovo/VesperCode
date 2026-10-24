"""Route A / A4: real local-disk workspace port and harness composition.

``LocalDiskWorkspacePort`` is the production workspace authority: writes
are atomic (temp file + fsync + link/replace), boundary-checked, and
rechecked immediately before mutation.  ``V2Harness`` composes it with
the writeback and recovery services while the loop keeps staging into
``InMemoryWorkspacePort`` so unit behavior stays deterministic.  The
final tests prove restart-safe recovery against the real filesystem.
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

from vespercode.contracts.v2_writeback import (
    PlannedWriteV2,
    V2WorkspacePort,
    WritebackRequestV2,
    WriteOperationV2,
)
from vespercode.llm.v2 import ScriptedLLMV2
from vespercode.runtime_v2 import V2Harness, V2HarnessConfig
from vespercode.storage.v2_database import V2_DATABASE_FILENAME
from vespercode.workspace.v2_disk import LocalDiskWorkspacePort

IS_WINDOWS = sys.platform == "win32"


def _plan(
    action: str, path: str, content: str, original: str | None = None
) -> PlannedWriteV2:
    return PlannedWriteV2(WriteOperationV2(action, path, content), original)


class FlakyDiskPort:
    """Fault injection over the real disk port."""

    def __init__(self, inner: LocalDiskWorkspacePort, fail_on_apply: int) -> None:
        self._inner = inner
        self._fail_on_apply = fail_on_apply
        self.apply_calls = 0

    def read_text(self, path: str) -> str | None:
        return self._inner.read_text(path)

    def exists(self, path: str) -> bool:
        return self._inner.exists(path)

    def validate(self, operation: WriteOperationV2) -> None:
        self._inner.validate(operation)

    def apply(self, planned: PlannedWriteV2) -> None:
        self.apply_calls += 1
        if self.apply_calls == self._fail_on_apply:
            raise OSError("injected disk fault")
        self._inner.apply(planned)

    def remove_expected(self, path: str, expected_content: str) -> None:
        self._inner.remove_expected(path, expected_content)


class LocalDiskWorkspacePortTests(unittest.TestCase):
    def setUp(self) -> None:
        self._directory = tempfile.TemporaryDirectory()
        self.workspace = Path(self._directory.name)
        self.port = LocalDiskWorkspacePort(self.workspace)
        (self.workspace / "src").mkdir()
        (self.workspace / "src" / "app.py").write_text(
            "original\n", encoding="utf-8", newline=""
        )

    def tearDown(self) -> None:
        self._directory.cleanup()

    def test_satisfies_the_workspace_port_protocol(self) -> None:
        self.assertIsInstance(self.port, V2WorkspacePort)

    def test_create_and_replace_write_exact_bytes_atomically(self) -> None:
        self.port.apply(_plan("CREATE", "src/new.py", "alpha\nbeta"))
        self.assertEqual(
            (self.workspace / "src" / "new.py").read_bytes(), b"alpha\nbeta"
        )
        self.port.apply(_plan("REPLACE", "src/new.py", "second", "alpha\nbeta"))
        self.assertEqual((self.workspace / "src" / "new.py").read_bytes(), b"second")

    def test_read_text_and_exists_round_trip(self) -> None:
        self.assertEqual(self.port.read_text("src/app.py"), "original\n")
        self.assertTrue(self.port.exists("src/app.py"))
        self.assertIsNone(self.port.read_text("src/missing.py"))
        self.assertFalse(self.port.exists("src/missing.py"))

    def test_strict_action_semantics_fail_closed(self) -> None:
        with self.assertRaises(Exception):
            self.port.apply(_plan("CREATE", "src/app.py", "x"))
        with self.assertRaises(Exception):
            self.port.apply(_plan("REPLACE", "src/missing.py", "x", "absent"))
        with self.assertRaises(Exception):
            self.port.apply(_plan("CREATE", "src", "x"))
        self.assertEqual(
            (self.workspace / "src" / "app.py").read_bytes(), b"original\n"
        )

    def test_remove_expected_deletes_only_matching_regular_files(self) -> None:
        self.port.apply(_plan("CREATE", "src/tmp.py", "x"))
        self.port.remove_expected("src/tmp.py", "x")
        self.assertFalse((self.workspace / "src" / "tmp.py").exists())
        with self.assertRaises(Exception):
            self.port.remove_expected("src/missing.py", "x")
        with self.assertRaises(Exception):
            self.port.remove_expected("src", "x")
        with self.assertRaises(Exception):
            # Changed bytes are refused instead of deleted.
            self.port.remove_expected("src/app.py", "changed bytes")

    def test_no_temp_files_are_left_behind_after_apply(self) -> None:
        self.port.apply(_plan("CREATE", "src/clean.py", "x"))
        self.port.apply(_plan("REPLACE", "src/app.py", "y", "original\n"))
        leftovers = [
            p.name
            for p in (self.workspace / "src").iterdir()
            if p.name.endswith(".tmp")
        ]
        self.assertEqual(leftovers, [])

    def test_unicode_content_round_trips(self) -> None:
        content = "# 注释\nprint('héllo')\n"
        self.port.apply(_plan("CREATE", "src/uni.py", content))
        self.assertEqual(self.port.read_text("src/uni.py"), content)

    @unittest.skipUnless(IS_WINDOWS, "junction reparse point is Windows-specific")
    def test_apply_refuses_targets_inside_a_junction(self) -> None:
        try:
            import _winapi  # noqa: PLC0415 - Windows-only private hook
        except ImportError:
            self.skipTest("_winapi is unavailable")
        outside = Path(tempfile.mkdtemp(prefix="vesper-outside-"))
        junction = self.workspace / "junction"
        try:
            try:
                _winapi.CreateJunction(str(outside), str(junction))
            except OSError:
                self.skipTest("junction creation is unavailable")
            with self.assertRaises(Exception):
                self.port.apply(_plan("CREATE", "junction/new.py", "escape"))
            self.assertFalse((outside / "new.py").exists())
        finally:
            import os

            try:
                os.rmdir(junction)
            except OSError:
                pass
            outside.rmdir()


class V2HarnessWritebackTests(unittest.TestCase):
    def setUp(self) -> None:
        self._directory = tempfile.TemporaryDirectory()
        self.root = Path(self._directory.name)
        self.workspace = self.root / "workspace"
        (self.workspace / "src").mkdir(parents=True)

    def tearDown(self) -> None:
        self._directory.cleanup()

    def _config(self) -> V2HarnessConfig:
        return V2HarnessConfig(self.workspace, self.root / "control", max_turns=5)

    def test_default_composition_uses_real_disk_writeback(self) -> None:
        harness = V2Harness(self._config())
        try:
            from vespercode.tools.v2_dispatcher import InMemoryWorkspacePort

            self.assertIsInstance(harness.workspace_port, InMemoryWorkspacePort)
            self.assertIsInstance(harness.disk_port, LocalDiskWorkspacePort)
            self.assertIsNotNone(harness.writeback_service)
            self.assertIsNotNone(harness.recovery_service)
        finally:
            harness.close()

    def test_loop_stages_in_memory_and_writeback_lands_on_real_disk(self) -> None:
        harness = V2Harness(self._config())
        try:
            result = harness.run(
                "repair the example",
                ScriptedLLMV2(
                    [
                        {
                            "action_type": "REPLACE",
                            "path": "tests/test_example.py",
                            "content": "blocked",
                        },
                        {
                            "action_type": "REPLACE",
                            "path": "src/example.py",
                            "content": "corrected body",
                        },
                        {"action_type": "DONE"},
                    ]
                ),
            )
            self.assertEqual(result.loop.status, "SUCCEEDED")
            # Staged only: the dangerous path was denied, the safe path staged.
            self.assertEqual(
                harness.workspace_port.files, {"src/example.py": "corrected body"}
            )
            self.assertFalse((self.workspace / "src" / "example.py").exists())

            identity = harness.stage_candidate(result.run_id)
            approval_id = harness.database.create_writeback_approval(
                run_id=result.run_id,
                candidate_id=identity.candidate_id,
                candidate_revision=identity.revision,
            )
            request = WritebackRequestV2(
                run_id=result.run_id,
                candidate_id=identity.candidate_id,
                candidate_revision=identity.revision,
                approval_id=approval_id,
                operations=harness.staged_operations(),
            )
            outcome = harness.writeback_service.request_writeback(request)

            self.assertEqual(outcome.status, "COMMITTED")
            self.assertEqual(
                (self.workspace / "src" / "example.py").read_text(encoding="utf-8"),
                "corrected body",
            )
            approval = harness.database.get_writeback_approval(approval_id)
            assert approval is not None
            self.assertEqual(approval["status"], "CONSUMED")
            transaction = harness.database.get_transaction(outcome.transaction_id)
            assert transaction is not None
            self.assertEqual(transaction["state"], "COMMITTED")
        finally:
            harness.close()

    def test_missing_parent_directory_is_a_prewrite_mismatch(self) -> None:
        harness = V2Harness(self._config())
        try:
            result = harness.run(
                "task",
                ScriptedLLMV2(
                    [
                        {
                            "action_type": "REPLACE",
                            "path": "deep/nested/new.py",
                            "content": "body",
                        },
                        {"action_type": "DONE"},
                    ]
                ),
            )
            identity = harness.stage_candidate(result.run_id)
            approval_id = harness.database.create_writeback_approval(
                run_id=result.run_id,
                candidate_id=identity.candidate_id,
                candidate_revision=identity.revision,
            )
            outcome = harness.writeback_service.request_writeback(
                WritebackRequestV2(
                    run_id=result.run_id,
                    candidate_id=identity.candidate_id,
                    candidate_revision=identity.revision,
                    approval_id=approval_id,
                    operations=harness.staged_operations(),
                )
            )
            # The parent directory does not exist and writeback never
            # creates directories: the request must be rejected as a
            # mismatch BEFORE the approval is consumed or a journal exists.
            self.assertEqual(outcome.status, "MISMATCH")
            self.assertIsNone(outcome.transaction_id)
            approval = harness.database.get_writeback_approval(approval_id)
            assert approval is not None
            self.assertEqual(approval["status"], "PENDING")
            self.assertFalse((self.workspace / "deep").exists())
        finally:
            harness.close()

    def test_writeback_without_an_approval_writes_nothing(self) -> None:
        harness = V2Harness(self._config())
        try:
            result = harness.run("task", ScriptedLLMV2([{"action_type": "DONE"}]))
            identity = harness.stage_candidate(result.run_id)
            harness.workspace_port.replace("src/ghost.py", "ghost")
            request = WritebackRequestV2(
                run_id=result.run_id,
                candidate_id=identity.candidate_id,
                candidate_revision=identity.revision,
                approval_id="no-such-approval",
                operations=harness.staged_operations(),
            )
            outcome = harness.writeback_service.request_writeback(request)
            self.assertEqual(outcome.status, "DENIED")
            self.assertFalse((self.workspace / "src" / "ghost.py").exists())
        finally:
            harness.close()

    def test_injected_in_memory_disk_port_keeps_the_flow_deterministic(self) -> None:
        from vespercode.tools.v2_dispatcher import InMemoryWorkspacePort

        disk_port = InMemoryWorkspacePort()
        disk_port.replace("src/example.py", "old body")
        harness = V2Harness(self._config(), disk_port=disk_port)
        try:
            result = harness.run(
                "task",
                ScriptedLLMV2(
                    [
                        {
                            "action_type": "REPLACE",
                            "path": "src/example.py",
                            "content": "new body",
                        },
                        {"action_type": "DONE"},
                    ]
                ),
            )
            identity = harness.stage_candidate(result.run_id)
            approval_id = harness.database.create_writeback_approval(
                run_id=result.run_id,
                candidate_id=identity.candidate_id,
                candidate_revision=identity.revision,
            )
            outcome = harness.writeback_service.request_writeback(
                WritebackRequestV2(
                    run_id=result.run_id,
                    candidate_id=identity.candidate_id,
                    candidate_revision=identity.revision,
                    approval_id=approval_id,
                    operations=harness.staged_operations(),
                )
            )
            self.assertEqual(outcome.status, "COMMITTED")
            self.assertEqual(disk_port.files["src/example.py"], "new body")
        finally:
            harness.close()

    def test_crashed_writeback_is_recovered_after_a_restart(self) -> None:
        harness = V2Harness(self._config())
        transaction_id: str | None = None
        try:
            result = harness.run(
                "task",
                ScriptedLLMV2(
                    [
                        {
                            "action_type": "REPLACE",
                            "path": "src/one.py",
                            "content": "one",
                        },
                        {
                            "action_type": "REPLACE",
                            "path": "src/two.py",
                            "content": "two",
                        },
                        {"action_type": "DONE"},
                    ]
                ),
            )
            identity = harness.stage_candidate(result.run_id)
            approval_id = harness.database.create_writeback_approval(
                run_id=result.run_id,
                candidate_id=identity.candidate_id,
                candidate_revision=identity.revision,
            )
            for path, content in harness.workspace_port.files.items():
                (self.workspace / path).write_text("placeholder", encoding="utf-8")
            flaky = FlakyDiskPort(harness.disk_port, fail_on_apply=2)
            from vespercode.persistence.v2_writeback import V2WritebackService

            flaky_service = V2WritebackService(
                harness.database, flaky, workspace=self.workspace
            )
            outcome = flaky_service.request_writeback(
                WritebackRequestV2(
                    run_id=result.run_id,
                    candidate_id=identity.candidate_id,
                    candidate_revision=identity.revision,
                    approval_id=approval_id,
                    operations=harness.staged_operations(),
                )
            )
            self.assertEqual(outcome.status, "FAILED")
            transaction_id = outcome.transaction_id
            self.assertEqual(
                (self.workspace / "src" / "one.py").read_text(encoding="utf-8"), "one"
            )
            self.assertEqual(
                (self.workspace / "src" / "two.py").read_text(encoding="utf-8"),
                "placeholder",
            )
        finally:
            harness.close()

        # Restart: a brand-new harness over the same control database and
        # workspace recovers the durable UNRESOLVED transaction.
        restarted = V2Harness(self._config())
        try:
            self.assertEqual(
                restarted.recovery_service.pending_transaction_ids(), (transaction_id,)
            )
            outcome = restarted.recovery_service.apply(transaction_id)
            self.assertEqual(outcome.status, "APPLIED")
            self.assertEqual(
                (self.workspace / "src" / "one.py").read_text(encoding="utf-8"), "one"
            )
            self.assertEqual(
                (self.workspace / "src" / "two.py").read_text(encoding="utf-8"), "two"
            )
            self.assertEqual(restarted.recovery_service.pending_transaction_ids(), ())
        finally:
            restarted.close()

    def test_database_path_is_reported_by_run_results(self) -> None:
        harness = V2Harness(self._config())
        try:
            result = harness.run("task", ScriptedLLMV2([{"action_type": "DONE"}]))
            self.assertEqual(result.database_path.name, V2_DATABASE_FILENAME)
        finally:
            harness.close()


if __name__ == "__main__":
    unittest.main()

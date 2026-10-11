"""Route A regression: REPLACE must not overwrite externally changed bytes.

The writeback preflight observes and journals the original bytes, but the
publication point is the only place where an external modification between
preflight and write can still be detected.  These tests inject exactly that
race — the target is rewritten by an "external process" after the preflight
read and before publication — and pin the fail-closed contract:

- the unsafe overwrite never happens (the external bytes survive),
- the outcome is FAILED with a durable UNRESOLVED transaction
  (MISMATCH is reserved for preflight rejections that consume nothing;
  a publish-time race happens after the approval was consumed atomically
  with the journal, so the auditable path is FAILED/UNRESOLVED),
- the approval stays consumed and the journal stays readable,
- recovery blocks on drift instead of guessing.

The planned-write API used by the port-level tests is imported lazily so
the behavioral regressions above still run (and fail) before the API
exists, keeping the RED evidence behavioral rather than a collection error.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from vespercode.contracts.v2_writeback import (
    JournalEntryV2,
    WritebackRequestV2,
    WriteOperationV2,
)
from vespercode.persistence.v2_recovery import V2RecoveryService
from vespercode.persistence.v2_writeback import V2WritebackService
from vespercode.storage.v2_database import (
    V2_DATABASE_FILENAME,
    initialize_v2_database,
    open_v2_database,
)
from vespercode.tools.v2_dispatcher import InMemoryWorkspacePort
from vespercode.workspace.v2_disk import LocalDiskWorkspacePort


def _planned(action: str, path: str, content: str, original: str | None):
    """Build a planned write; deferred import keeps RED behavioral."""

    from vespercode.contracts.v2_writeback import PlannedWriteV2

    return PlannedWriteV2(WriteOperationV2(action, path, content), original)


class RacingInMemoryPort:
    """Rewrites staged bytes after preflight, before publication."""

    def __init__(self, inner: InMemoryWorkspacePort, sabotage: dict[str, str]) -> None:
        self._inner = inner
        self._sabotage = sabotage
        self.sabotaged: list[str] = []

    def read_text(self, path: str) -> str | None:
        return self._inner.read_text(path)

    def exists(self, path: str) -> bool:
        return self._inner.exists(path)

    def validate(self, operation: WriteOperationV2) -> None:
        self._inner.validate(operation)

    def apply(self, write: object) -> None:
        operation = (
            write if isinstance(write, WriteOperationV2) else write.operation  # type: ignore[attr-defined]
        )
        if operation.path in self._sabotage and operation.path not in self.sabotaged:
            self.sabotaged.append(operation.path)
            self._inner.files[operation.path] = self._sabotage[operation.path]
        return self._inner.apply(write)

    def remove_expected(self, path: str, expected_content: str) -> None:
        if path in self._sabotage and path not in self.sabotaged:
            self.sabotaged.append(path)
            self._inner.files[path] = self._sabotage[path]
        return self._inner.remove_expected(path, expected_content)


class RacingDiskPort:
    """Rewrites real files after preflight, before publication."""

    def __init__(
        self,
        inner: LocalDiskWorkspacePort,
        workspace: Path,
        sabotage: dict[str, str],
    ) -> None:
        self._inner = inner
        self._workspace = workspace
        self._sabotage = sabotage
        self.sabotaged: list[str] = []

    def read_text(self, path: str) -> str | None:
        return self._inner.read_text(path)

    def exists(self, path: str) -> bool:
        return self._inner.exists(path)

    def validate(self, operation: WriteOperationV2) -> None:
        self._inner.validate(operation)

    def apply(self, write: object) -> None:
        operation = (
            write if isinstance(write, WriteOperationV2) else write.operation  # type: ignore[attr-defined]
        )
        if operation.path in self._sabotage and operation.path not in self.sabotaged:
            self.sabotaged.append(operation.path)
            target = self._workspace / Path(*operation.path.split("/"))
            target.write_text(
                self._sabotage[operation.path], encoding="utf-8", newline=""
            )
        return self._inner.apply(write)

    def remove_expected(self, path: str, expected_content: str) -> None:
        if path in self._sabotage and path not in self.sabotaged:
            self.sabotaged.append(path)
            target = self._workspace / Path(*path.split("/"))
            target.write_text(
                self._sabotage[path], encoding="utf-8", newline=""
            )
        return self._inner.remove_expected(path, expected_content)


class ReplaceContentGuardTests(unittest.TestCase):
    def setUp(self) -> None:
        self._directory = tempfile.TemporaryDirectory()
        self.root = Path(self._directory.name)
        self.workspace = self.root / "workspace"
        (self.workspace / "src").mkdir(parents=True)
        self.database_path = self.root / "control" / V2_DATABASE_FILENAME
        initialize_v2_database(self.database_path)
        self.database = open_v2_database(self.database_path)

    def tearDown(self) -> None:
        self.database.close()
        self._directory.cleanup()

    def _request(
        self, operations: tuple[WriteOperationV2, ...]
    ) -> tuple[WritebackRequestV2, str]:
        run_id = self.database.create_run(str(self.workspace))
        snapshot_id = self.database.create_snapshot(run_id)
        candidate_id = self.database.create_candidate(run_id, snapshot_id)
        approval_id = self.database.create_writeback_approval(
            run_id=run_id, candidate_id=candidate_id, candidate_revision=0
        )
        request = WritebackRequestV2(
            run_id=run_id,
            candidate_id=candidate_id,
            candidate_revision=0,
            approval_id=approval_id,
            operations=operations,
        )
        return request, approval_id

    def test_replace_refuses_external_change_between_preflight_and_publish_in_memory(
        self,
    ) -> None:
        port = InMemoryWorkspacePort()
        port.replace("src/old.py", "old body")
        racing = RacingInMemoryPort(port, {"src/old.py": "EXTERNAL EDIT"})
        service = V2WritebackService(self.database, racing, workspace=self.workspace)
        request, approval_id = self._request(
            (WriteOperationV2("REPLACE", "src/old.py", "new body"),)
        )

        outcome = service.request_writeback(request)

        self.assertEqual(outcome.status, "FAILED")
        self.assertIsNotNone(outcome.transaction_id)
        # Zero unsafe overwrite: the external edit survives.
        self.assertEqual(port.files["src/old.py"], "EXTERNAL EDIT")
        transaction = self.database.get_transaction(outcome.transaction_id)
        assert transaction is not None
        self.assertEqual(transaction["state"], "UNRESOLVED")
        approval = self.database.get_writeback_approval(approval_id)
        assert approval is not None
        self.assertEqual(approval["status"], "CONSUMED")
        self.assertNotEqual(
            self.database.get_transaction_journal(outcome.transaction_id), []
        )
        # Recovery must not guess over the externally modified bytes.
        recovery = V2RecoveryService(self.database, port)
        preview = recovery.preview(outcome.transaction_id)
        self.assertTrue(preview.blocked)
        self.assertEqual(preview.items[0].state, "DRIFTED")
        self.assertEqual(recovery.apply(outcome.transaction_id).status, "BLOCKED")
        self.assertEqual(recovery.rollback(outcome.transaction_id).status, "BLOCKED")
        self.assertEqual(port.files["src/old.py"], "EXTERNAL EDIT")

    def test_replace_refuses_external_change_between_preflight_and_publish_on_disk(
        self,
    ) -> None:
        target = self.workspace / "src" / "old.py"
        target.write_text("old body", encoding="utf-8", newline="")
        port = LocalDiskWorkspacePort(self.workspace)
        racing = RacingDiskPort(port, self.workspace, {"src/old.py": "EXTERNAL EDIT"})
        service = V2WritebackService(self.database, racing, workspace=self.workspace)
        request, approval_id = self._request(
            (WriteOperationV2("REPLACE", "src/old.py", "new body"),)
        )

        outcome = service.request_writeback(request)

        self.assertEqual(outcome.status, "FAILED")
        self.assertIsNotNone(outcome.transaction_id)
        self.assertEqual(target.read_bytes(), b"EXTERNAL EDIT")
        transaction = self.database.get_transaction(outcome.transaction_id)
        assert transaction is not None
        self.assertEqual(transaction["state"], "UNRESOLVED")
        approval = self.database.get_writeback_approval(approval_id)
        assert approval is not None
        self.assertEqual(approval["status"], "CONSUMED")
        # No temporary publish file is left behind by the refused write.
        leftovers = [
            item.name
            for item in (self.workspace / "src").iterdir()
            if item.name.endswith(".tmp")
        ]
        self.assertEqual(leftovers, [])
        recovery = V2RecoveryService(self.database, port)
        preview = recovery.preview(outcome.transaction_id)
        self.assertTrue(preview.blocked)
        self.assertEqual(preview.items[0].state, "DRIFTED")

    def test_create_target_appeared_race_is_refused_without_clobbering(self) -> None:
        port = LocalDiskWorkspacePort(self.workspace)
        racing = RacingDiskPort(port, self.workspace, {"src/ghost.py": "EXTERNAL CREATE"})
        service = V2WritebackService(self.database, racing, workspace=self.workspace)
        request, approval_id = self._request(
            (WriteOperationV2("CREATE", "src/ghost.py", "new body"),)
        )

        outcome = service.request_writeback(request)

        self.assertEqual(outcome.status, "FAILED")
        self.assertIsNotNone(outcome.transaction_id)
        ghost = self.workspace / "src" / "ghost.py"
        self.assertEqual(ghost.read_bytes(), b"EXTERNAL CREATE")
        transaction = self.database.get_transaction(outcome.transaction_id)
        assert transaction is not None
        self.assertEqual(transaction["state"], "UNRESOLVED")
        approval = self.database.get_writeback_approval(approval_id)
        assert approval is not None
        self.assertEqual(approval["status"], "CONSUMED")

    def test_disk_apply_compares_expected_original_before_publishing(self) -> None:
        from vespercode.contracts.v2_writeback import WorkspaceContentMismatchError

        target = self.workspace / "src" / "old.py"
        target.write_text("old body", encoding="utf-8", newline="")
        port = LocalDiskWorkspacePort(self.workspace)

        with self.assertRaises(WorkspaceContentMismatchError):
            port.apply(
                _planned("REPLACE", "src/old.py", "new body", "different original")
            )
        self.assertEqual(target.read_bytes(), b"old body")
        self.assertEqual(
            [item.name for item in (self.workspace / "src").iterdir() if item.name.endswith(".tmp")],
            [],
        )

        port.apply(_planned("REPLACE", "src/old.py", "new body", "old body"))
        self.assertEqual(target.read_bytes(), b"new body")

    def test_in_memory_apply_compares_expected_original_before_publishing(self) -> None:
        from vespercode.contracts.v2_writeback import WorkspaceContentMismatchError

        port = InMemoryWorkspacePort()
        port.replace("src/old.py", "old body")

        with self.assertRaises(WorkspaceContentMismatchError):
            port.apply(_planned("REPLACE", "src/old.py", "new body", "different"))
        self.assertEqual(port.files["src/old.py"], "old body")

        port.apply(_planned("REPLACE", "src/old.py", "new body", "old body"))
        self.assertEqual(port.files["src/old.py"], "new body")

    def test_rollback_restore_is_bound_to_the_applied_content(self) -> None:
        port = InMemoryWorkspacePort()
        port.replace("src/old.py", "old body")
        port.replace("src/keep.py", "keep original")
        request, _ = self._request(
            (
                WriteOperationV2("REPLACE", "src/old.py", "new body"),
                WriteOperationV2("REPLACE", "src/keep.py", "keep new"),
            )
        )

        class FailSecondApply:
            def __init__(self, inner: InMemoryWorkspacePort) -> None:
                self._inner = inner
                self.calls = 0

            def read_text(self, path: str) -> str | None:
                return self._inner.read_text(path)

            def exists(self, path: str) -> bool:
                return self._inner.exists(path)

            def validate(self, operation: WriteOperationV2) -> None:
                self._inner.validate(operation)

            def apply(self, write: object) -> None:
                self.calls += 1
                if self.calls == 2:
                    raise OSError("injected fault between the two writes")
                self._inner.apply(write)

            def remove_expected(self, path: str, expected_content: str) -> None:
                self._inner.remove_expected(path, expected_content)

        flaky = FailSecondApply(port)
        service = V2WritebackService(self.database, flaky, workspace=self.workspace)
        outcome = service.request_writeback(request)
        self.assertEqual(outcome.status, "FAILED")
        assert outcome.transaction_id is not None
        # First write landed; the fault stopped the second.
        self.assertEqual(port.files["src/old.py"], "new body")
        self.assertEqual(port.files["src/keep.py"], "keep original")

        recovery = V2RecoveryService(self.database, port)
        rolled = recovery.rollback(outcome.transaction_id)

        self.assertEqual(rolled.status, "ROLLED_BACK")
        # The restore of the APPLIED entry expects the applied bytes and
        # rewrites the original; the PENDING entry is left untouched.
        self.assertEqual(port.files["src/old.py"], "old body")
        self.assertEqual(port.files["src/keep.py"], "keep original")
        transaction = self.database.get_transaction(outcome.transaction_id)
        assert transaction is not None
        self.assertEqual(transaction["state"], "ROLLED_BACK")

    def _applied_create_transaction(self, path: str, content: str) -> str:
        """Journal a CREATE, mark it UNRESOLVED, and leave the write applied."""
        run_id = self.database.create_run(str(self.workspace))
        snapshot_id = self.database.create_snapshot(run_id)
        candidate_id = self.database.create_candidate(run_id, snapshot_id)
        approval_id = self.database.create_writeback_approval(
            run_id=run_id, candidate_id=candidate_id, candidate_revision=0
        )
        transaction_id = self.database.begin_writeback_transaction(
            run_id=run_id,
            candidate_id=candidate_id,
            candidate_revision=0,
            approval_id=approval_id,
            entries=(JournalEntryV2(0, path, "CREATE", content, None),),
        )
        assert self.database.transition_transaction(
            transaction_id, from_state="PREPARED", to_state="WRITING"
        )
        assert self.database.transition_transaction(
            transaction_id, from_state="WRITING", to_state="UNRESOLVED"
        )
        return transaction_id

    def test_rollback_refuses_to_delete_an_externally_changed_create_on_disk(
        self,
    ) -> None:
        transaction_id = self._applied_create_transaction(
            "src/ghost.py", "applied body"
        )
        # Simulate a crash after the write landed: the created file holds
        # exactly the journaled bytes at recovery observation time.
        ghost = self.workspace / "src" / "ghost.py"
        ghost.write_text("applied body", encoding="utf-8", newline="")
        port = LocalDiskWorkspacePort(self.workspace)
        racing = RacingDiskPort(port, self.workspace, {"src/ghost.py": "EXTERNAL EDIT"})
        recovery = V2RecoveryService(self.database, racing)
        preview = recovery.preview(transaction_id)
        self.assertEqual(preview.items[0].state, "APPLIED")
        self.assertFalse(preview.blocked)

        outcome = recovery.rollback(transaction_id)

        self.assertEqual(outcome.status, "FAILED")
        # The external edit survives: rollback must not delete changed bytes.
        self.assertEqual(ghost.read_bytes(), b"EXTERNAL EDIT")
        transaction = self.database.get_transaction(transaction_id)
        assert transaction is not None
        self.assertEqual(transaction["state"], "UNRESOLVED")

    def test_rollback_refuses_to_delete_an_externally_changed_create_in_memory(
        self,
    ) -> None:
        transaction_id = self._applied_create_transaction(
            "src/ghost.py", "applied body"
        )
        port = InMemoryWorkspacePort()
        port.replace("src/ghost.py", "applied body")
        racing = RacingInMemoryPort(port, {"src/ghost.py": "EXTERNAL EDIT"})
        recovery = V2RecoveryService(self.database, racing)
        preview = recovery.preview(transaction_id)
        self.assertEqual(preview.items[0].state, "APPLIED")

        outcome = recovery.rollback(transaction_id)

        self.assertEqual(outcome.status, "FAILED")
        self.assertEqual(port.files["src/ghost.py"], "EXTERNAL EDIT")
        transaction = self.database.get_transaction(transaction_id)
        assert transaction is not None
        self.assertEqual(transaction["state"], "UNRESOLVED")

    def test_disk_remove_expected_compares_bytes_before_deleting(self) -> None:
        from vespercode.contracts.v2_writeback import WorkspaceContentMismatchError

        target = self.workspace / "src" / "ghost.py"
        target.write_text("applied body", encoding="utf-8", newline="")
        port = LocalDiskWorkspacePort(self.workspace)

        with self.assertRaises(WorkspaceContentMismatchError):
            port.remove_expected("src/ghost.py", "different bytes")
        self.assertEqual(target.read_bytes(), b"applied body")

        with self.assertRaises(WorkspaceContentMismatchError):
            port.remove_expected("src/missing.py", "applied body")

        port.remove_expected("src/ghost.py", "applied body")
        self.assertFalse(target.exists())

    def test_in_memory_remove_expected_compares_bytes_before_deleting(self) -> None:
        from vespercode.contracts.v2_writeback import WorkspaceContentMismatchError

        port = InMemoryWorkspacePort()
        port.replace("src/ghost.py", "applied body")

        with self.assertRaises(WorkspaceContentMismatchError):
            port.remove_expected("src/ghost.py", "different bytes")
        self.assertEqual(port.files["src/ghost.py"], "applied body")

        with self.assertRaises(WorkspaceContentMismatchError):
            port.remove_expected("src/missing.py", "applied body")

        port.remove_expected("src/ghost.py", "applied body")
        self.assertNotIn("src/ghost.py", port.files)


if __name__ == "__main__":
    unittest.main()

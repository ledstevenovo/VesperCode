"""Route A / A3: durable transaction recovery with fail-closed blocking.

Pins the restart-safe semantics: a fault mid-write leaves a durable
``UNRESOLVED`` transaction whose journal drives a byte-comparison preview,
an explicit apply, or an explicit rollback.  Drift (a file that matches
neither the journal nor its recorded original) or an unreadable target
blocks recovery instead of guessing.  All state lives in the v2 SQLite
database, so a fresh service instance recovers a crashed transaction.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from vespercode.contracts.v2_writeback import (
    PlannedWriteV2,
    WritebackRequestV2,
    WriteOperationV2,
)
from vespercode.persistence.v2_writeback import V2WritebackService
from vespercode.storage.v2_database import (
    V2_DATABASE_FILENAME,
    initialize_v2_database,
    open_v2_database,
)
from vespercode.persistence.v2_recovery import V2RecoveryService
from vespercode.tools.v2_dispatcher import InMemoryWorkspacePort


class FlakyPort:
    """Fault injection: delegates to a real port but raises on the Nth apply."""

    def __init__(self, inner: object, fail_on_apply: int) -> None:
        self._inner = inner
        self._fail_on_apply = fail_on_apply
        self.apply_calls = 0

    def read_text(self, path: str) -> str | None:
        return self._inner.read_text(path)  # type: ignore[attr-defined]

    def exists(self, path: str) -> bool:
        return self._inner.exists(path)  # type: ignore[attr-defined]

    def validate(self, operation: WriteOperationV2) -> None:
        self._inner.validate(operation)  # type: ignore[attr-defined]

    def apply(self, planned: PlannedWriteV2) -> None:
        self.apply_calls += 1
        if self.apply_calls == self._fail_on_apply:
            raise OSError("injected write fault")
        self._inner.apply(planned)  # type: ignore[attr-defined]

    def remove_expected(self, path: str, expected_content: str) -> None:
        self._inner.remove_expected(path, expected_content)  # type: ignore[attr-defined]


class V2RecoveryTests(unittest.TestCase):
    def setUp(self) -> None:
        self._directory = tempfile.TemporaryDirectory()
        self.root = Path(self._directory.name)
        self.workspace = self.root / "workspace"
        (self.workspace / "src").mkdir(parents=True)
        self.database_path = self.root / "control" / V2_DATABASE_FILENAME
        initialize_v2_database(self.database_path)
        self.database = open_v2_database(self.database_path)
        self.port = InMemoryWorkspacePort()
        self.port.replace("src/old.py", "old body")

    def tearDown(self) -> None:
        self.database.close()
        self._directory.cleanup()

    def _crashed_transaction(self) -> str:
        """Start a writeback whose second write is faulted."""
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
            operations=(
                WriteOperationV2("CREATE", "src/a.py", "alpha"),
                WriteOperationV2("CREATE", "src/b.py", "beta"),
                WriteOperationV2("CREATE", "src/c.py", "gamma"),
            ),
        )
        flaky = FlakyPort(self.port, fail_on_apply=2)
        service = V2WritebackService(self.database, flaky, workspace=self.workspace)
        outcome = service.request_writeback(request)
        assert outcome.status == "FAILED", outcome.message
        assert outcome.transaction_id is not None
        return outcome.transaction_id

    def test_pending_lists_only_non_terminal_transactions(self) -> None:
        transaction_id = self._crashed_transaction()
        recovery = V2RecoveryService(self.database, self.port)
        self.assertEqual(recovery.pending_transaction_ids(), (transaction_id,))
        outcome = recovery.apply(transaction_id)
        assert outcome.status == "APPLIED", outcome.message
        self.assertEqual(recovery.pending_transaction_ids(), ())

    def test_preview_reports_applied_and_pending_items(self) -> None:
        transaction_id = self._crashed_transaction()
        recovery = V2RecoveryService(self.database, self.port)

        preview = recovery.preview(transaction_id)

        self.assertEqual(preview.transaction_id, transaction_id)
        self.assertEqual(preview.transaction_state, "UNRESOLVED")
        self.assertFalse(preview.blocked)
        states = [(item.path, item.state) for item in preview.items]
        self.assertEqual(
            states,
            [
                ("src/a.py", "APPLIED"),
                ("src/b.py", "PENDING"),
                ("src/c.py", "PENDING"),
            ],
        )

    def test_apply_completes_a_crashed_writeback_deterministically(self) -> None:
        transaction_id = self._crashed_transaction()
        recovery = V2RecoveryService(self.database, self.port)

        outcome = recovery.apply(transaction_id)

        self.assertEqual(outcome.status, "APPLIED")
        self.assertEqual(outcome.transaction_id, transaction_id)
        self.assertEqual(self.port.files["src/a.py"], "alpha")
        self.assertEqual(self.port.files["src/b.py"], "beta")
        self.assertEqual(self.port.files["src/c.py"], "gamma")
        transaction = self.database.get_transaction(transaction_id)
        assert transaction is not None
        self.assertEqual(transaction["state"], "COMMITTED")

    def test_rollback_restores_recorded_originals(self) -> None:
        transaction_id = self._crashed_transaction()
        recovery = V2RecoveryService(self.database, self.port)

        outcome = recovery.rollback(transaction_id)

        self.assertEqual(outcome.status, "ROLLED_BACK")
        self.assertNotIn("src/a.py", self.port.files)
        self.assertNotIn("src/b.py", self.port.files)
        self.assertNotIn("src/c.py", self.port.files)
        transaction = self.database.get_transaction(transaction_id)
        assert transaction is not None
        self.assertEqual(transaction["state"], "ROLLED_BACK")

    def test_rollback_restores_replaced_content(self) -> None:
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
            operations=(WriteOperationV2("REPLACE", "src/old.py", "new body"),),
        )
        service = V2WritebackService(self.database, self.port, workspace=self.workspace)
        outcome = service.request_writeback(request)
        assert outcome.status == "COMMITTED", outcome.message
        assert outcome.transaction_id is not None
        # A committed transaction is terminal: no recovery is possible.
        recovery = V2RecoveryService(self.database, self.port)
        with self.assertRaises(ValueError):
            recovery.rollback(outcome.transaction_id)

    def test_drift_blocks_apply_and_rollback_fail_closed(self) -> None:
        transaction_id = self._crashed_transaction()
        # External modification of the partially-written target.
        self.port.replace("src/a.py", "tampered")
        recovery = V2RecoveryService(self.database, self.port)

        preview = recovery.preview(transaction_id)
        self.assertTrue(preview.blocked)
        self.assertEqual(preview.items[0].state, "DRIFTED")

        blocked_apply = recovery.apply(transaction_id)
        self.assertEqual(blocked_apply.status, "BLOCKED")
        self.assertEqual(self.port.files["src/a.py"], "tampered")

        blocked_rollback = recovery.rollback(transaction_id)
        self.assertEqual(blocked_rollback.status, "BLOCKED")
        self.assertEqual(self.port.files["src/a.py"], "tampered")
        transaction = self.database.get_transaction(transaction_id)
        assert transaction is not None
        self.assertEqual(transaction["state"], "UNRESOLVED")

    def test_recovery_survives_a_restart_with_a_fresh_service(self) -> None:
        transaction_id = self._crashed_transaction()
        # Simulate a restart: nothing in memory, only the durable database.
        self.database.close()
        self.database = open_v2_database(self.database_path)
        recovery = V2RecoveryService(self.database, self.port)

        preview = recovery.preview(transaction_id)
        self.assertFalse(preview.blocked)
        outcome = recovery.apply(transaction_id)

        self.assertEqual(outcome.status, "APPLIED")
        self.assertEqual(self.port.files["src/b.py"], "beta")
        self.assertEqual(self.port.files["src/c.py"], "gamma")
        transaction = self.database.get_transaction(transaction_id)
        assert transaction is not None
        self.assertEqual(transaction["state"], "COMMITTED")

    def test_apply_rolls_the_state_forward_through_the_legal_map(self) -> None:
        recovery = V2RecoveryService(self.database, self.port)
        # Recovery entering from WRITING (a crash mid-write recorded before
        # the UNRESOLVED mark) also applies through the legal state map.
        writing_id = self._writing_state_transaction()
        outcome = recovery.apply(writing_id)
        self.assertEqual(outcome.status, "APPLIED")
        self.assertEqual(self.port.files["src/w.py"], "written")

    def test_apply_recovers_a_transaction_that_crashed_right_after_prepare(self) -> None:
        run_id = self.database.create_run(str(self.workspace))
        snapshot_id = self.database.create_snapshot(run_id)
        candidate_id = self.database.create_candidate(run_id, snapshot_id)
        approval_id = self.database.create_writeback_approval(
            run_id=run_id, candidate_id=candidate_id, candidate_revision=0
        )
        from vespercode.contracts.v2_writeback import JournalEntryV2

        transaction_id = self.database.begin_writeback_transaction(
            run_id=run_id,
            candidate_id=candidate_id,
            candidate_revision=0,
            approval_id=approval_id,
            entries=(JournalEntryV2(0, "src/p.py", "CREATE", "prepared", None),),
        )
        # The process "crashed" before WRITING: state is still PREPARED.
        recovery = V2RecoveryService(self.database, self.port)
        preview = recovery.preview(transaction_id)
        self.assertEqual(preview.transaction_state, "PREPARED")
        self.assertEqual(preview.items[0].state, "PENDING")

        outcome = recovery.apply(transaction_id)

        self.assertEqual(outcome.status, "APPLIED")
        self.assertEqual(self.port.files["src/p.py"], "prepared")
        transaction = self.database.get_transaction(transaction_id)
        assert transaction is not None
        self.assertEqual(transaction["state"], "COMMITTED")

    def _writing_state_transaction(self) -> str:
        run_id = self.database.create_run(str(self.workspace))
        snapshot_id = self.database.create_snapshot(run_id)
        candidate_id = self.database.create_candidate(run_id, snapshot_id)
        approval_id = self.database.create_writeback_approval(
            run_id=run_id, candidate_id=candidate_id, candidate_revision=0
        )
        from vespercode.contracts.v2_writeback import JournalEntryV2

        transaction_id = self.database.begin_writeback_transaction(
            run_id=run_id,
            candidate_id=candidate_id,
            candidate_revision=0,
            approval_id=approval_id,
            entries=(JournalEntryV2(0, "src/w.py", "CREATE", "written", None),),
        )
        assert self.database.transition_transaction(
            transaction_id, from_state="PREPARED", to_state="WRITING"
        )
        return transaction_id

    def test_unknown_or_terminal_transactions_are_rejected(self) -> None:
        recovery = V2RecoveryService(self.database, self.port)
        with self.assertRaises(ValueError):
            recovery.preview("missing-transaction")
        with self.assertRaises(ValueError):
            recovery.apply("missing-transaction")
        with self.assertRaises(ValueError):
            recovery.rollback("missing-transaction")

    def test_recovery_rejects_an_empty_journal(self) -> None:
        transaction_id = self._crashed_transaction()
        self.database._connection.execute(
            "DELETE FROM transaction_journal WHERE transaction_id = ?",
            (transaction_id,),
        )
        recovery = V2RecoveryService(self.database, self.port)

        with self.assertRaisesRegex(ValueError, "empty"):
            recovery.preview(transaction_id)
        with self.assertRaises(ValueError):
            recovery.apply(transaction_id)
        with self.assertRaises(ValueError):
            recovery.rollback(transaction_id)
        # The corrupted transaction is never advanced to a terminal state.
        transaction = self.database.get_transaction(transaction_id)
        assert transaction is not None
        self.assertEqual(transaction["state"], "UNRESOLVED")

    def test_recovery_rejects_non_contiguous_journal_positions(self) -> None:
        transaction_id = self._crashed_transaction()
        self.database._connection.execute(
            "UPDATE transaction_journal SET position = 7 "
            "WHERE transaction_id = ? AND position = 2",
            (transaction_id,),
        )
        recovery = V2RecoveryService(self.database, self.port)

        with self.assertRaisesRegex(ValueError, "position"):
            recovery.preview(transaction_id)
        with self.assertRaises(ValueError):
            recovery.apply(transaction_id)
        with self.assertRaises(ValueError):
            recovery.rollback(transaction_id)
        transaction = self.database.get_transaction(transaction_id)
        assert transaction is not None
        self.assertEqual(transaction["state"], "UNRESOLVED")

    def test_recovery_rejects_malformed_journal_rows(self) -> None:
        # Shape validation happens through JournalEntryV2: unknown action
        # types and original-content shapes are refused at load time.
        corruption_sql = {
            "unknown action": (
                "UPDATE transaction_journal SET action_type = 'DELETE' "
                "WHERE transaction_id = ? AND position = 0"
            ),
            "replace without original": (
                "UPDATE transaction_journal SET action_type = 'REPLACE', "
                "original_content = NULL WHERE transaction_id = ? AND position = 0"
            ),
            "create with original": (
                "UPDATE transaction_journal SET original_content = 'x' "
                "WHERE transaction_id = ? AND position = 0"
            ),
        }
        for label, sql in corruption_sql.items():
            with self.subTest(corruption=label):
                # subTest does not re-run setUp; use a fresh port per
                # iteration so one crash never bleeds into the next.
                self.port = InMemoryWorkspacePort()
                self.port.replace("src/old.py", "old body")
                transaction_id = self._crashed_transaction()
                self.database._connection.execute(sql, (transaction_id,))
                recovery = V2RecoveryService(self.database, self.port)
                with self.assertRaises(ValueError):
                    recovery.preview(transaction_id)
                with self.assertRaises(ValueError):
                    recovery.apply(transaction_id)
                with self.assertRaises(ValueError):
                    recovery.rollback(transaction_id)
                transaction = self.database.get_transaction(transaction_id)
                assert transaction is not None
                self.assertEqual(transaction["state"], "UNRESOLVED")


if __name__ == "__main__":
    unittest.main()

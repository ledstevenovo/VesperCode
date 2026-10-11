"""Route A / A0: frozen v2 writeback interfaces.

These tests pin the vocabulary and value-object contracts that the real
filesystem writeback and recovery services must keep stable: the write
action vocabulary, the durable transaction state machine names, journal
entry shapes, writeback requests/outcomes, and the workspace port protocol.
"""

from __future__ import annotations

import unittest
from typing import Any

from vespercode.contracts.v2_writeback import (
    ACTIVE_TRANSACTION_STATES,
    ALLOWED_WRITE_ACTION_TYPES,
    TERMINAL_TRANSACTION_STATES,
    JournalEntryV2,
    PlannedWriteV2,
    RecoveryItemV2,
    RecoveryOutcomeV2,
    RecoveryPreviewV2,
    TransactionStateV2,
    V2WorkspacePort,
    WritebackOutcomeV2,
    WritebackRequestV2,
    WritebackStatusV2,
    WriteOperationV2,
)


class WriteVocabularyTests(unittest.TestCase):
    def test_write_action_vocabulary_is_frozen_to_create_and_replace(self) -> None:
        self.assertEqual(ALLOWED_WRITE_ACTION_TYPES, frozenset({"CREATE", "REPLACE"}))

    def test_transaction_state_machine_names_are_frozen(self) -> None:
        self.assertEqual(
            {state.value for state in TransactionStateV2},
            {"PREPARED", "WRITING", "COMMITTED", "UNRESOLVED", "ROLLED_BACK"},
        )
        self.assertEqual(
            ACTIVE_TRANSACTION_STATES,
            frozenset({"PREPARED", "WRITING", "UNRESOLVED"}),
        )
        self.assertEqual(
            TERMINAL_TRANSACTION_STATES,
            frozenset({"COMMITTED", "ROLLED_BACK"}),
        )
        self.assertEqual(
            ACTIVE_TRANSACTION_STATES | TERMINAL_TRANSACTION_STATES,
            {state.value for state in TransactionStateV2},
        )

    def test_writeback_status_vocabulary_is_frozen(self) -> None:
        self.assertEqual(
            {status.value for status in WritebackStatusV2},
            {"COMMITTED", "DENIED", "STALE", "MISMATCH", "FAILED"},
        )


class WriteOperationContractTests(unittest.TestCase):
    def test_rejects_unknown_or_invalid_shapes(self) -> None:
        invalid: tuple[dict[str, Any], ...] = (
            {"action_type": "DELETE", "path": "src/a.py", "content": "x"},
            {"action_type": "replace", "path": "src/a.py", "content": "x"},
            {"action_type": "CREATE", "path": "", "content": "x"},
            {"action_type": "CREATE", "path": "src/../a.py", "content": "x"},
            {"action_type": "CREATE", "path": "src//a.py", "content": "x"},
            {"action_type": "CREATE", "path": "src/./a.py", "content": "x"},
            {"action_type": "CREATE", "path": "src\\a.py", "content": "x"},
            {"action_type": "CREATE", "path": "/abs/a.py", "content": "x"},
            {"action_type": "CREATE", "path": "C:/a.py", "content": "x"},
            {"action_type": "CREATE", "path": "./a.py", "content": "x"},
            {"action_type": "CREATE", "path": "a\x00b.py", "content": "x"},
            {"action_type": "CREATE", "path": "src/\na.py", "content": "x"},
            {"action_type": "CREATE", "path": "src/a.py", "content": None},
            {"action_type": "CREATE", "path": "src/a.py", "content": b"bytes"},
            {"action_type": None, "path": "src/a.py", "content": "x"},
            {"action_type": "CREATE", "path": 7, "content": "x"},
        )
        for kwargs in invalid:
            with self.assertRaises(ValueError, msg=repr(kwargs)):
                WriteOperationV2(**kwargs)

    def test_accepts_canonical_relative_paths_and_any_text(self) -> None:
        op = WriteOperationV2("REPLACE", "src/example.py", "print('ok')\n")
        self.assertEqual(op.action_type, "REPLACE")
        self.assertEqual(op.path, "src/example.py")
        self.assertEqual(op.content, "print('ok')\n")

        empty = WriteOperationV2("CREATE", "src/empty.py", "")
        self.assertEqual(empty.content, "")

        deep = WriteOperationV2("CREATE", "docs/notes/a b.md", "hello")
        self.assertEqual(deep.path, "docs/notes/a b.md")

    def test_operations_are_immutable(self) -> None:
        op = WriteOperationV2("CREATE", "src/a.py", "x")
        with self.assertRaises(Exception):
            op.path = "src/b.py"  # type: ignore[misc]


class JournalEntryContractTests(unittest.TestCase):
    def test_create_entries_have_no_original_content(self) -> None:
        entry = JournalEntryV2(0, "src/a.py", "CREATE", "new", None)
        self.assertIsNone(entry.original_content)

    def test_replace_entries_carry_the_observed_original(self) -> None:
        entry = JournalEntryV2(1, "src/b.py", "REPLACE", "new", "old")
        self.assertEqual(entry.original_content, "old")

    def test_rejects_invalid_positions_and_shapes(self) -> None:
        invalid: tuple[dict[str, Any], ...] = (
            {"position": -1, "path": "src/a.py", "action_type": "CREATE", "content": "x", "original_content": None},
            {"position": True, "path": "src/a.py", "action_type": "CREATE", "content": "x", "original_content": None},
            {"position": 0, "path": "", "action_type": "CREATE", "content": "x", "original_content": None},
            {"position": 0, "path": "src/a.py", "action_type": "DELETE", "content": "x", "original_content": None},
            {"position": 0, "path": "src/a.py", "action_type": "REPLACE", "content": "x", "original_content": None},
            {"position": 0, "path": "src/a.py", "action_type": "CREATE", "content": None, "original_content": None},
        )
        for kwargs in invalid:
            with self.assertRaises(ValueError, msg=repr(kwargs)):
                JournalEntryV2(**kwargs)


class WritebackRequestContractTests(unittest.TestCase):
    def _operation(self) -> WriteOperationV2:
        return WriteOperationV2("CREATE", "src/a.py", "content")

    def test_request_binds_run_candidate_revision_and_approval(self) -> None:
        request = WritebackRequestV2(
            run_id="run-1",
            candidate_id="candidate-1",
            candidate_revision=3,
            approval_id="approval-1",
            operations=(self._operation(),),
        )
        self.assertEqual(request.candidate_revision, 3)
        self.assertEqual(request.operations, (self._operation(),))

    def test_request_requires_at_least_one_operation(self) -> None:
        with self.assertRaisesRegex(ValueError, "operation"):
            WritebackRequestV2("run-1", "candidate-1", 0, "approval-1", ())

    def test_request_rejects_invalid_revisions_and_empty_ids(self) -> None:
        with self.assertRaisesRegex(ValueError, "revision"):
            WritebackRequestV2("run-1", "candidate-1", -1, "approval-1", (self._operation(),))
        for bad_id in ("", "  "):
            with self.assertRaises(ValueError):
                WritebackRequestV2(bad_id, "candidate-1", 0, "approval-1", (self._operation(),))
            with self.assertRaises(ValueError):
                WritebackRequestV2("run-1", bad_id, 0, "approval-1", (self._operation(),))
            with self.assertRaises(ValueError):
                WritebackRequestV2("run-1", "candidate-1", 0, bad_id, (self._operation(),))


class WritebackOutcomeContractTests(unittest.TestCase):
    def test_outcomes_carry_status_transaction_and_message(self) -> None:
        outcome = WritebackOutcomeV2("COMMITTED", "transaction-1", "2 write(s) committed")
        self.assertEqual(outcome.status, "COMMITTED")
        self.assertEqual(outcome.transaction_id, "transaction-1")

        denied = WritebackOutcomeV2("DENIED", None, "protected path")
        self.assertIsNone(denied.transaction_id)

    def test_recovery_preview_and_outcome_shapes(self) -> None:
        item = RecoveryItemV2(0, "src/a.py", "CREATE", "PENDING")
        preview = RecoveryPreviewV2("transaction-1", "UNRESOLVED", (item,), False)
        self.assertFalse(preview.blocked)

        blocked = RecoveryPreviewV2(
            "transaction-1",
            "UNRESOLVED",
            (RecoveryItemV2(0, "src/a.py", "CREATE", "DRIFTED"),),
            True,
        )
        self.assertTrue(blocked.blocked)

        outcome = RecoveryOutcomeV2("APPLIED", "transaction-1", "recovery applied")
        self.assertEqual(outcome.status, "APPLIED")


class PlannedWriteContractTests(unittest.TestCase):
    """A planned write binds a REPLACE to the exact bytes it may overwrite."""

    def test_replace_plans_bind_the_expected_original(self) -> None:
        plan = PlannedWriteV2(WriteOperationV2("REPLACE", "src/a.py", "new"), "old")
        self.assertEqual(plan.expected_original, "old")
        self.assertEqual(plan.operation.content, "new")

    def test_create_plans_must_not_expect_original_content(self) -> None:
        with self.assertRaises(ValueError):
            PlannedWriteV2(WriteOperationV2("CREATE", "src/a.py", "new"), "old")
        allowed = PlannedWriteV2(WriteOperationV2("CREATE", "src/a.py", "new"), None)
        self.assertIsNone(allowed.expected_original)

    def test_replace_plans_require_an_expected_original(self) -> None:
        with self.assertRaises(ValueError):
            PlannedWriteV2(WriteOperationV2("REPLACE", "src/a.py", "new"), None)

    def test_plans_require_a_write_operation(self) -> None:
        with self.assertRaises(ValueError):
            PlannedWriteV2("REPLACE", "old")  # type: ignore[arg-type]

    def test_journal_entries_build_their_publish_plan(self) -> None:
        entry = JournalEntryV2(1, "src/b.py", "REPLACE", "new body", "old body")
        plan = entry.planned()
        self.assertEqual(plan.operation.action_type, "REPLACE")
        self.assertEqual(plan.operation.path, "src/b.py")
        self.assertEqual(plan.operation.content, "new body")
        self.assertEqual(plan.expected_original, "old body")

    def test_restore_plans_invert_the_expectation(self) -> None:
        entry = JournalEntryV2(1, "src/b.py", "REPLACE", "new body", "old body")
        restore = entry.planned_restore()
        # Undoing an applied write expects the applied bytes on disk and
        # publishes the recorded original.
        self.assertEqual(restore.operation.content, "old body")
        self.assertEqual(restore.expected_original, "new body")

    def test_create_entries_have_no_restore_plan(self) -> None:
        entry = JournalEntryV2(0, "src/a.py", "CREATE", "new", None)
        with self.assertRaises(ValueError):
            entry.planned_restore()


class WorkspacePortProtocolTests(unittest.TestCase):
    def test_a_minimal_implementation_satisfies_the_port_protocol(self) -> None:
        class FakePort:
            def read_text(self, path: str) -> str | None:
                return None

            def exists(self, path: str) -> bool:
                return False

            def validate(self, operation: WriteOperationV2) -> None:
                return None

            def apply(self, planned: PlannedWriteV2) -> None:
                return None

            def remove_expected(self, path: str, expected_content: str) -> None:
                return None

        self.assertIsInstance(FakePort(), V2WorkspacePort)

    def test_objects_missing_port_methods_do_not_satisfy_the_protocol(self) -> None:
        class NotAPort:
            def read_text(self, path: str) -> str | None:
                return None

        self.assertNotIsInstance(NotAPort(), V2WorkspacePort)

    def test_the_protocol_requires_a_non_mutating_validate(self) -> None:
        class PortWithoutValidate:
            def read_text(self, path: str) -> str | None:
                return None

            def exists(self, path: str) -> bool:
                return False

            def apply(self, planned: PlannedWriteV2) -> None:
                return None

            def remove_expected(self, path: str, expected_content: str) -> None:
                return None

        self.assertNotIsInstance(PortWithoutValidate(), V2WorkspacePort)

    def test_the_protocol_requires_a_content_bound_removal(self) -> None:
        class PortWithPlainRemove:
            def read_text(self, path: str) -> str | None:
                return None

            def exists(self, path: str) -> bool:
                return False

            def validate(self, operation: WriteOperationV2) -> None:
                return None

            def apply(self, planned: PlannedWriteV2) -> None:
                return None

            def remove(self, path: str) -> None:
                return None

        # An unbound removal can delete externally changed bytes, so the
        # frozen protocol must not accept it.
        self.assertNotIsInstance(PortWithPlainRemove(), V2WorkspacePort)


if __name__ == "__main__":
    unittest.main()

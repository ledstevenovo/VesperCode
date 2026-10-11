"""Route A / A2: durable v2 transaction records in the v2 database.

Pins the schema version 3 additions (the durable journal), the atomic
approval-consuming transaction begin, the legal transaction state machine,
and fail-closed rejection of databases written by the older v2 schema.
"""

from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from vespercode.contracts.v2_writeback import JournalEntryV2
from vespercode.storage.v2_database import (
    V2_DATABASE_FILENAME,
    V2DatabaseError,
    V2_SCHEMA_VERSION,
    initialize_v2_database,
    open_v2_database,
)


class V2TransactionDatabaseTests(unittest.TestCase):
    def setUp(self) -> None:
        self._directory = tempfile.TemporaryDirectory()
        self.root = Path(self._directory.name)
        self.database_path = self.root / V2_DATABASE_FILENAME
        initialize_v2_database(self.database_path)
        self.database = open_v2_database(self.database_path)

    def tearDown(self) -> None:
        self.database.close()
        self._directory.cleanup()

    def _approved_candidate(self, revision: int = 0) -> tuple[str, str, str]:
        run_id = self.database.create_run(str(self.root))
        snapshot_id = self.database.create_snapshot(run_id)
        candidate_id = self.database.create_candidate(run_id, snapshot_id, revision=revision)
        approval_id = self.database.create_writeback_approval(
            run_id=run_id,
            candidate_id=candidate_id,
            candidate_revision=revision,
        )
        return run_id, candidate_id, approval_id

    @staticmethod
    def _entries() -> tuple[JournalEntryV2, ...]:
        return (
            JournalEntryV2(0, "src/new.py", "CREATE", "new body", None),
            JournalEntryV2(1, "src/old.py", "REPLACE", "new body", "old body"),
        )

    def test_fresh_database_is_schema_version_3_with_a_durable_journal(self) -> None:
        self.assertEqual(V2_SCHEMA_VERSION, 3)
        tables = {
            str(row[0])
            for row in self.database._connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
        self.assertIn("transaction_journal", tables)
        journal_columns = {
            str(row[1])
            for row in self.database._connection.execute(
                "PRAGMA table_info(transaction_journal)"
            )
        }
        self.assertLessEqual(
            {
                "transaction_id",
                "position",
                "path",
                "action_type",
                "content",
                "original_content",
            },
            journal_columns,
        )

    def test_begin_writeback_consumes_the_approval_and_journals_entries(self) -> None:
        run_id, candidate_id, approval_id = self._approved_candidate()
        entries = self._entries()

        transaction_id = self.database.begin_writeback_transaction(
            run_id=run_id,
            candidate_id=candidate_id,
            candidate_revision=0,
            approval_id=approval_id,
            entries=entries,
        )

        transaction = self.database.get_transaction(transaction_id)
        self.assertIsNotNone(transaction)
        assert transaction is not None
        self.assertEqual(transaction["state"], "PREPARED")
        self.assertEqual(transaction["candidate_id"], candidate_id)
        journal = self.database.get_transaction_journal(transaction_id)
        self.assertEqual([row["position"] for row in journal], [0, 1])
        self.assertEqual(journal[0]["path"], "src/new.py")
        self.assertIsNone(journal[0]["original_content"])
        self.assertEqual(journal[1]["original_content"], "old body")
        approval = self.database.get_writeback_approval(approval_id)
        self.assertIsNotNone(approval)
        assert approval is not None
        self.assertEqual(approval["status"], "CONSUMED")
        self.assertIsNotNone(approval["consumed_at"])

    def test_begin_writeback_is_one_shot_for_the_approval(self) -> None:
        run_id, candidate_id, approval_id = self._approved_candidate()
        self.database.begin_writeback_transaction(
            run_id=run_id,
            candidate_id=candidate_id,
            candidate_revision=0,
            approval_id=approval_id,
            entries=self._entries(),
        )
        with self.assertRaisesRegex(V2DatabaseError, "approval"):
            self.database.begin_writeback_transaction(
                run_id=run_id,
                candidate_id=candidate_id,
                candidate_revision=0,
                approval_id=approval_id,
                entries=self._entries(),
            )

    def test_begin_writeback_rejects_a_stale_candidate_revision(self) -> None:
        run_id, candidate_id, approval_id = self._approved_candidate(revision=0)
        self.assertTrue(self.database.advance_candidate(candidate_id, 0))
        with self.assertRaisesRegex(V2DatabaseError, "stale"):
            self.database.begin_writeback_transaction(
                run_id=run_id,
                candidate_id=candidate_id,
                candidate_revision=0,
                approval_id=approval_id,
                entries=self._entries(),
            )
        approval = self.database.get_writeback_approval(approval_id)
        assert approval is not None
        self.assertEqual(approval["status"], "PENDING")

    def test_begin_writeback_rejects_a_mismatched_approval(self) -> None:
        run_id, candidate_id, _ = self._approved_candidate()
        other_run, other_candidate, _ = self._approved_candidate()
        other_approval = self.database.create_writeback_approval(
            run_id=other_run,
            candidate_id=other_candidate,
            candidate_revision=0,
        )
        with self.assertRaisesRegex(V2DatabaseError, "approval"):
            self.database.begin_writeback_transaction(
                run_id=run_id,
                candidate_id=candidate_id,
                candidate_revision=0,
                approval_id=other_approval,
                entries=self._entries(),
            )

    def test_transaction_transitions_follow_the_frozen_state_machine(self) -> None:
        run_id, candidate_id, approval_id = self._approved_candidate()
        transaction_id = self.database.begin_writeback_transaction(
            run_id=run_id,
            candidate_id=candidate_id,
            candidate_revision=0,
            approval_id=approval_id,
            entries=self._entries(),
        )

        self.assertTrue(
            self.database.transition_transaction(
                transaction_id, from_state="PREPARED", to_state="WRITING"
            )
        )
        self.assertTrue(
            self.database.transition_transaction(
                transaction_id, from_state="WRITING", to_state="UNRESOLVED"
            )
        )
        self.assertTrue(
            self.database.transition_transaction(
                transaction_id, from_state="UNRESOLVED", to_state="WRITING"
            )
        )
        self.assertTrue(
            self.database.transition_transaction(
                transaction_id, from_state="WRITING", to_state="COMMITTED"
            )
        )

    def test_terminal_states_are_final_and_illegal_jumps_are_rejected(self) -> None:
        run_id, candidate_id, approval_id = self._approved_candidate()
        transaction_id = self.database.begin_writeback_transaction(
            run_id=run_id,
            candidate_id=candidate_id,
            candidate_revision=0,
            approval_id=approval_id,
            entries=self._entries(),
        )
        self.database.transition_transaction(
            transaction_id, from_state="PREPARED", to_state="WRITING"
        )
        self.database.transition_transaction(
            transaction_id, from_state="WRITING", to_state="COMMITTED"
        )
        self.assertFalse(
            self.database.transition_transaction(
                transaction_id, from_state="WRITING", to_state="UNRESOLVED"
            )
        )
        with self.assertRaises(V2DatabaseError):
            self.database.transition_transaction(
                transaction_id, from_state="COMMITTED", to_state="ROLLED_BACK"
            )
        with self.assertRaises(V2DatabaseError):
            self.database.transition_transaction(
                transaction_id, from_state="PREPARED", to_state="COMMITTED"
            )

    def test_prepared_transactions_can_rollback_before_any_write(self) -> None:
        run_id, candidate_id, approval_id = self._approved_candidate()
        transaction_id = self.database.begin_writeback_transaction(
            run_id=run_id,
            candidate_id=candidate_id,
            candidate_revision=0,
            approval_id=approval_id,
            entries=self._entries(),
        )
        self.assertTrue(
            self.database.transition_transaction(
                transaction_id, from_state="PREPARED", to_state="ROLLED_BACK"
            )
        )

    def test_list_transactions_reports_active_and_terminal_sets(self) -> None:
        run_id, candidate_id, approval_id = self._approved_candidate()
        first = self.database.begin_writeback_transaction(
            run_id=run_id,
            candidate_id=candidate_id,
            candidate_revision=0,
            approval_id=approval_id,
            entries=self._entries(),
        )
        second_run, second_candidate, second_approval = self._approved_candidate()
        second = self.database.begin_writeback_transaction(
            run_id=second_run,
            candidate_id=second_candidate,
            candidate_revision=0,
            approval_id=second_approval,
            entries=self._entries(),
        )
        self.database.transition_transaction(
            first, from_state="PREPARED", to_state="ROLLED_BACK"
        )

        active = self.database.list_transactions_in_states(
            ("PREPARED", "WRITING", "UNRESOLVED")
        )
        self.assertEqual([row["transaction_id"] for row in active], [second])
        terminal = self.database.list_transactions_in_states(("COMMITTED", "ROLLED_BACK"))
        self.assertEqual([row["transaction_id"] for row in terminal], [first])

    def test_an_older_v2_schema_version_is_rejected_on_open(self) -> None:
        legacy = self.root / "legacy-v2.sqlite"
        initialize_v2_database(legacy)
        connection = sqlite3.connect(legacy)
        connection.execute("DELETE FROM v2_schema_meta")
        connection.execute("INSERT INTO v2_schema_meta VALUES (2, 'relaxed_identity_v2')")
        connection.commit()
        connection.close()
        with self.assertRaisesRegex(V2DatabaseError, "invalid"):
            open_v2_database(legacy)

    def _replace_table(self, table: str, malformed_sql: str) -> None:
        """Recreate one table with a missing column, keeping valid metadata."""
        connection = self.database._connection
        connection.execute(f"DROP TABLE {table}")
        connection.execute(malformed_sql)

    def _assert_open_and_initialize_reject_table(self, table: str) -> None:
        try:
            opened = open_v2_database(self.database_path)
        except V2DatabaseError:
            pass
        else:
            opened.close()
            self.fail(f"open_v2_database accepted a malformed {table} table")
        with self.assertRaisesRegex(V2DatabaseError, table):
            initialize_v2_database(self.database_path)

    def test_malformed_transaction_journal_is_rejected_on_open_and_initialize(
        self,
    ) -> None:
        # Pin: the journal columns are part of the frozen schema contract.
        self._replace_table(
            "transaction_journal",
            "CREATE TABLE transaction_journal ("
            " transaction_id TEXT NOT NULL, position INTEGER NOT NULL,"
            " path TEXT NOT NULL, action_type TEXT NOT NULL, content TEXT NOT NULL,"
            " PRIMARY KEY (transaction_id, position))",
        )
        self._assert_open_and_initialize_reject_table("transaction_journal")

    def test_malformed_actions_table_is_rejected_on_open_and_initialize(self) -> None:
        self._replace_table(
            "actions",
            "CREATE TABLE actions ("
            " action_id TEXT PRIMARY KEY, run_id TEXT NOT NULL,"
            " action_type TEXT NOT NULL,"
            " created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)",
        )
        self._assert_open_and_initialize_reject_table("actions")

    def test_malformed_disclosures_table_is_rejected_on_open_and_initialize(
        self,
    ) -> None:
        self._replace_table(
            "disclosures",
            "CREATE TABLE disclosures ("
            " disclosure_id TEXT PRIMARY KEY, run_id TEXT NOT NULL,"
            " created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)",
        )
        self._assert_open_and_initialize_reject_table("disclosures")

    def test_malformed_artifacts_table_is_rejected_on_open_and_initialize(
        self,
    ) -> None:
        self._replace_table(
            "artifacts",
            "CREATE TABLE artifacts ("
            " artifact_id TEXT PRIMARY KEY, run_id TEXT NOT NULL,"
            " kind TEXT NOT NULL,"
            " created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)",
        )
        self._assert_open_and_initialize_reject_table("artifacts")


if __name__ == "__main__":
    unittest.main()

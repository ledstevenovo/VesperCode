from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from vespercode.storage.v2_database import (
    V2_DATABASE_FILENAME,
    V2DatabaseError,
    initialize_v2_database,
    open_v2_database,
)


class V2DatabaseTests(unittest.TestCase):
    def test_new_database_uses_v2_schema_and_uuid_run_ids(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            database_path = root / V2_DATABASE_FILENAME
            initialize_v2_database(database_path)
            database = open_v2_database(database_path)
            try:
                run_id = database.create_run(str(root))
                row = database.get_run(run_id)
                self.assertIsNotNone(row)
                self.assertEqual(row["run_id"], run_id)
                self.assertEqual(row["revision"], 1)
                self.assertNotIn("digest", row.keys())
            finally:
                database.close()

    def test_revision_change_invalidates_old_writeback_subject(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            database_path = root / V2_DATABASE_FILENAME
            initialize_v2_database(database_path)
            database = open_v2_database(database_path)
            try:
                run_id = database.create_run(str(root))
                snapshot_id = database.create_snapshot(run_id, snapshot_id="snapshot-1")
                candidate_id = database.create_candidate(
                    run_id, snapshot_id=snapshot_id, revision=1
                )
                approval_id = database.create_writeback_approval(
                    run_id=run_id,
                    candidate_id=candidate_id,
                    candidate_revision=1,
                )
                self.assertTrue(database.advance_candidate(candidate_id, 1))
                self.assertFalse(
                    database.consume_writeback_approval(
                        approval_id,
                        candidate_id=candidate_id,
                        candidate_revision=1,
                    )
                )
                current_approval_id = database.create_writeback_approval(
                    run_id=run_id,
                    candidate_id=candidate_id,
                    candidate_revision=2,
                )
                self.assertTrue(
                    database.consume_writeback_approval(
                        current_approval_id,
                        candidate_id=candidate_id,
                        candidate_revision=2,
                    )
                )
            finally:
                database.close()

    def test_v1_database_is_not_reused_as_v2(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            database_path = Path(directory) / V2_DATABASE_FILENAME
            import sqlite3

            connection = sqlite3.connect(database_path)
            connection.execute("CREATE TABLE schema_migrations (version INTEGER)")
            connection.commit()
            connection.close()

            with self.assertRaisesRegex(V2DatabaseError, "read-only"):
                initialize_v2_database(database_path)

    def test_mixed_v1_and_v2_markers_are_also_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            database_path = Path(directory) / V2_DATABASE_FILENAME
            import sqlite3

            connection = sqlite3.connect(database_path)
            connection.execute("CREATE TABLE schema_migrations (version INTEGER)")
            connection.execute(
                "CREATE TABLE v2_schema_meta (version INTEGER PRIMARY KEY, name TEXT)"
            )
            connection.commit()
            connection.close()

            with self.assertRaisesRegex(V2DatabaseError, "read-only"):
                initialize_v2_database(database_path)

    def test_writeback_approval_requires_candidate_from_the_same_run(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            database_path = root / V2_DATABASE_FILENAME
            initialize_v2_database(database_path)
            database = open_v2_database(database_path)
            try:
                first_run = database.create_run(str(root / "first"))
                second_run = database.create_run(str(root / "second"))
                snapshot_id = database.create_snapshot(first_run)
                candidate_id = database.create_candidate(first_run, snapshot_id)

                with self.assertRaisesRegex(V2DatabaseError, "run"):
                    database.create_writeback_approval(
                        run_id=second_run,
                        candidate_id=candidate_id,
                        candidate_revision=0,
                    )
            finally:
                database.close()

    def test_candidate_requires_snapshot_from_the_same_run(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            database_path = root / V2_DATABASE_FILENAME
            initialize_v2_database(database_path)
            database = open_v2_database(database_path)
            try:
                first_run = database.create_run(str(root / "first"))
                second_run = database.create_run(str(root / "second"))
                snapshot_id = database.create_snapshot(first_run)

                with self.assertRaisesRegex(V2DatabaseError, "run"):
                    database.create_candidate(second_run, snapshot_id)
            finally:
                database.close()

    def test_negative_revisions_are_rejected_at_database_boundary(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            database_path = root / V2_DATABASE_FILENAME
            initialize_v2_database(database_path)
            database = open_v2_database(database_path)
            try:
                run_id = database.create_run(str(root))
                with self.assertRaisesRegex(V2DatabaseError, "revision"):
                    database.create_snapshot(run_id, revision=-1)
            finally:
                database.close()

    def test_transaction_requires_candidate_from_the_same_run(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            database_path = root / V2_DATABASE_FILENAME
            initialize_v2_database(database_path)
            database = open_v2_database(database_path)
            try:
                first_run = database.create_run(str(root / "first"))
                second_run = database.create_run(str(root / "second"))
                snapshot_id = database.create_snapshot(first_run)
                candidate_id = database.create_candidate(first_run, snapshot_id)
                with self.assertRaisesRegex(V2DatabaseError, "transaction"):
                    database.create_transaction(second_run, candidate_id)
            finally:
                database.close()

    def test_approval_creation_rejects_stale_candidate_revision(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            database_path = root / V2_DATABASE_FILENAME
            initialize_v2_database(database_path)
            database = open_v2_database(database_path)
            try:
                run_id = database.create_run(str(root))
                snapshot_id = database.create_snapshot(run_id)
                candidate_id = database.create_candidate(
                    run_id, snapshot_id, revision=2
                )
                with self.assertRaisesRegex(V2DatabaseError, "stale"):
                    database.create_writeback_approval(run_id, candidate_id, 1)
            finally:
                database.close()

    def test_incomplete_v2_schema_is_rejected_on_open(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            database_path = Path(directory) / V2_DATABASE_FILENAME
            import sqlite3

            connection = sqlite3.connect(database_path)
            connection.execute(
                "CREATE TABLE v2_schema_meta (version INTEGER PRIMARY KEY, name TEXT)"
            )
            connection.execute(
                "INSERT INTO v2_schema_meta VALUES (2, 'relaxed_identity_v2')"
            )
            connection.commit()
            connection.close()

            with self.assertRaisesRegex(V2DatabaseError, "incomplete"):
                open_v2_database(database_path)


if __name__ == "__main__":
    unittest.main()

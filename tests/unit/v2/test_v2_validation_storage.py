"""Route B / B1: durable v2 validation/reference storage in the v3 schema.

The v1 validation plane persisted digest-bound manifests in the legacy
twelve-migration database.  This slice adds the v2 storage boundary to
the existing v3 schema only: three new tables (``reference_profiles``,
``candidate_diffs``, ``validation_runs``) with strict column validation
on open and initialize, no migration of any v1 row, and fail-closed
creation rules — a validation run or candidate diff may only be recorded
for a candidate of the same run at its current revision, and evidence
rows are keyed by the five control-plane facts.  The Route A
transaction/writeback/recovery invariants are untouched.
"""

from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from vespercode.candidate.v2_candidate import CandidateControlIdentityV2
from vespercode.contracts.v2_validation import (
    ValidationBindingV2,
    ValidationResultV2,
    verify_evidence_binding,
)
from vespercode.profiles.v2_reference import ReferenceProfileRecordV2
from vespercode.storage.v2_database import (
    V2_DATABASE_FILENAME,
    V2DatabaseError,
    V2_SCHEMA_VERSION,
    initialize_v2_database,
    open_v2_database,
)


class V2ValidationStorageTests(unittest.TestCase):
    def setUp(self) -> None:
        self._directory = tempfile.TemporaryDirectory()
        self.root = Path(self._directory.name)
        self.database_path = self.root / V2_DATABASE_FILENAME
        initialize_v2_database(self.database_path)
        self.database = open_v2_database(self.database_path)

    def tearDown(self) -> None:
        self.database.close()
        self._directory.cleanup()

    def _candidate(self, revision: int = 0) -> tuple[str, str]:
        run_id = self.database.create_run(str(self.root))
        snapshot_id = self.database.create_snapshot(run_id)
        candidate_id = self.database.create_candidate(
            run_id, snapshot_id, revision=revision
        )
        return run_id, candidate_id

    def _profile(self, revision: int = 0) -> ReferenceProfileRecordV2:
        record = ReferenceProfileRecordV2(
            f"profile-{revision}", revision, "3.12.4", "8.4.2", "0.16.1", "2.3.0"
        )
        self.database.create_reference_profile(record)
        return record

    def _validation_run(self, run_id: str, candidate_id: str, revision: int = 0) -> str:
        return self.database.create_validation_run(
            run_id=run_id,
            candidate_id=candidate_id,
            candidate_revision=revision,
            reference_profile_id="profile-0",
            reference_profile_revision=0,
        )

    def test_fresh_database_gains_the_b1_tables_in_the_v3_schema(self) -> None:
        self.assertEqual(V2_SCHEMA_VERSION, 3)
        tables = {
            str(row[0])
            for row in self.database._connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
        for table in ("reference_profiles", "candidate_diffs", "validation_runs"):
            self.assertIn(table, tables)

    def test_malformed_b1_tables_are_rejected_on_open_and_initialize(self) -> None:
        malformed = (
            (
                "reference_profiles",
                "CREATE TABLE reference_profiles ("
                " reference_profile_id TEXT NOT NULL,"
                " profile_revision INTEGER NOT NULL,"
                " python_version TEXT NOT NULL,"
                " pytest_version TEXT NOT NULL,"
                " ruff_version TEXT NOT NULL,"
                " created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,"
                " PRIMARY KEY (reference_profile_id, profile_revision))",
            ),
            (
                "candidate_diffs",
                "CREATE TABLE candidate_diffs ("
                " diff_id TEXT PRIMARY KEY, run_id TEXT NOT NULL,"
                " candidate_id TEXT NOT NULL,"
                " candidate_revision INTEGER NOT NULL,"
                " created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)",
            ),
            (
                "validation_runs",
                "CREATE TABLE validation_runs ("
                " validation_run_id TEXT PRIMARY KEY, run_id TEXT NOT NULL,"
                " candidate_id TEXT NOT NULL,"
                " candidate_revision INTEGER NOT NULL,"
                " reference_profile_id TEXT NOT NULL,"
                " reference_profile_revision INTEGER NOT NULL,"
                " status TEXT NOT NULL DEFAULT 'PENDING',"
                " created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)",
            ),
        )
        for table, malformed_sql in malformed:
            with self.subTest(table=table):
                directory = tempfile.TemporaryDirectory()
                try:
                    path = Path(directory.name) / V2_DATABASE_FILENAME
                    initialize_v2_database(path)
                    raw = sqlite3.connect(path)
                    try:
                        raw.execute("PRAGMA foreign_keys = OFF")
                        raw.execute(f"DROP TABLE {table}")
                        raw.execute(malformed_sql)
                        raw.commit()
                    finally:
                        raw.close()
                    with self.assertRaisesRegex(V2DatabaseError, table):
                        open_v2_database(path)
                    with self.assertRaisesRegex(V2DatabaseError, table):
                        initialize_v2_database(path)
                finally:
                    directory.cleanup()

    def test_reference_profile_round_trip_and_duplicate_rejection(self) -> None:
        record = self._profile(revision=0)

        loaded = self.database.get_reference_profile("profile-0", 0)
        self.assertEqual(loaded, record)
        self.assertIsNone(self.database.get_reference_profile("profile-0", 1))
        self.assertIsNone(self.database.get_reference_profile("profile-9", 0))

        with self.assertRaisesRegex(V2DatabaseError, "exists"):
            self.database.create_reference_profile(record)
        # A new revision of the same profile is a distinct record.
        self._profile(revision=1)
        self.assertIsNotNone(self.database.get_reference_profile("profile-1", 1))

    def test_candidate_control_projection_fails_closed_on_corrupt_rows(
        self,
    ) -> None:
        run_id, candidate_id = self._candidate()
        control = self.database.get_candidate_control(candidate_id)
        self.assertIsInstance(control, CandidateControlIdentityV2)
        assert control is not None
        self.assertEqual(control.candidate_id, candidate_id)
        self.assertEqual(control.status, "ACTIVE")
        self.assertEqual(control.revision, 0)

        self.database.close()
        raw = sqlite3.connect(self.database_path)
        try:
            raw.execute(
                "UPDATE candidates SET status = 'OPEN' WHERE candidate_id = ?",
                (candidate_id,),
            )
            raw.commit()
        finally:
            raw.close()
        self.database = open_v2_database(self.database_path)
        with self.assertRaises(ValueError):
            self.database.get_candidate_control(candidate_id)
        self.assertIsNone(self.database.get_candidate_control("missing"))

    def test_candidate_diff_binding_checks(self) -> None:
        run_id, candidate_id = self._candidate()
        artifact_id = self.database.create_artifact(
            run_id, "FINAL_DIFF", "artifacts/diff.json"
        )

        diff_id = self.database.create_candidate_diff(
            run_id=run_id,
            candidate_id=candidate_id,
            candidate_revision=0,
            artifact_id=artifact_id,
        )
        record = self.database.get_candidate_diff(candidate_id, 0)
        self.assertIsNotNone(record)
        assert record is not None
        self.assertEqual(
            (
                record.diff_id,
                record.candidate_id,
                record.candidate_revision,
                record.artifact_id,
            ),
            (diff_id, candidate_id, 0, artifact_id),
        )
        self.assertIsNone(self.database.get_candidate_diff(candidate_id, 1))

        # Cross-run candidate binding fails closed.
        other_run, other_candidate = self._candidate()
        with self.assertRaisesRegex(V2DatabaseError, "mismatch"):
            self.database.create_candidate_diff(
                run_id=other_run,
                candidate_id=candidate_id,
                candidate_revision=0,
                artifact_id=artifact_id,
            )
        # Stale revision fails closed.
        with self.assertRaisesRegex(V2DatabaseError, "stale"):
            self.database.create_candidate_diff(
                run_id=run_id,
                candidate_id=candidate_id,
                candidate_revision=1,
                artifact_id=artifact_id,
            )
        # A foreign-run artifact fails closed.
        foreign_artifact = self.database.create_artifact(
            other_run, "FINAL_DIFF", "artifacts/other.json"
        )
        self.assertTrue(self.database.advance_candidate(candidate_id, 0))
        with self.assertRaisesRegex(V2DatabaseError, "mismatch"):
            self.database.create_candidate_diff(
                run_id=run_id,
                candidate_id=candidate_id,
                candidate_revision=1,
                artifact_id=foreign_artifact,
            )
        # One authoritative diff per candidate revision: re-recording the
        # same (candidate, revision) rejects even at the current revision.
        second_run, second_candidate = self._candidate()
        second_artifact = self.database.create_artifact(
            second_run, "FINAL_DIFF", "artifacts/second.json"
        )
        self.database.create_candidate_diff(
            run_id=second_run,
            candidate_id=second_candidate,
            candidate_revision=0,
            artifact_id=second_artifact,
        )
        with self.assertRaisesRegex(V2DatabaseError, "already recorded"):
            self.database.create_candidate_diff(
                run_id=second_run,
                candidate_id=second_candidate,
                candidate_revision=0,
                artifact_id=second_artifact,
            )
        # The advanced revision accepts a fresh diff record.
        next_artifact = self.database.create_artifact(
            run_id, "FINAL_DIFF", "artifacts/diff-2.json"
        )
        advanced_diff = self.database.create_candidate_diff(
            run_id=run_id,
            candidate_id=candidate_id,
            candidate_revision=1,
            artifact_id=next_artifact,
        )
        self.assertEqual(
            self.database.get_candidate_diff(candidate_id, 1).diff_id,  # type: ignore[union-attr]
            advanced_diff,
        )

    def test_validation_run_binding_checks(self) -> None:
        run_id, candidate_id = self._candidate()
        self._profile(revision=0)

        # Unknown reference profile fails closed.
        with self.assertRaisesRegex(V2DatabaseError, "profile"):
            self.database.create_validation_run(
                run_id=run_id,
                candidate_id=candidate_id,
                candidate_revision=0,
                reference_profile_id="profile-9",
                reference_profile_revision=0,
            )
        # Unknown profile revision fails closed.
        with self.assertRaisesRegex(V2DatabaseError, "profile"):
            self.database.create_validation_run(
                run_id=run_id,
                candidate_id=candidate_id,
                candidate_revision=0,
                reference_profile_id="profile-0",
                reference_profile_revision=5,
            )
        # Cross-run candidate fails closed.
        other_run, _ = self._candidate()
        with self.assertRaisesRegex(V2DatabaseError, "mismatch"):
            self.database.create_validation_run(
                run_id=other_run,
                candidate_id=candidate_id,
                candidate_revision=0,
                reference_profile_id="profile-0",
                reference_profile_revision=0,
            )
        # Stale candidate revision fails closed.
        with self.assertRaisesRegex(V2DatabaseError, "stale"):
            self.database.create_validation_run(
                run_id=run_id,
                candidate_id=candidate_id,
                candidate_revision=1,
                reference_profile_id="profile-0",
                reference_profile_revision=0,
            )

        validation_run_id = self._validation_run(run_id, candidate_id)
        run_record = self.database.get_validation_run(validation_run_id)
        self.assertIsNotNone(run_record)
        assert run_record is not None
        self.assertEqual(run_record.status, "PENDING")
        self.assertEqual(run_record.error, None)
        self.assertEqual(
            run_record.binding(),
            ValidationBindingV2(
                run_id=run_id,
                candidate_id=candidate_id,
                candidate_revision=0,
                reference_profile_id="profile-0",
                reference_profile_revision=0,
            ),
        )
        self.assertIsNone(self.database.get_validation_run("missing"))

    def test_record_validation_result_completes_once_with_bounded_outcomes(
        self,
    ) -> None:
        run_id, candidate_id = self._candidate()
        self._profile(revision=0)
        validation_run_id = self._validation_run(run_id, candidate_id)

        # Malformed outcomes fail closed before any mutation.
        for status, error in (
            ("FAILED", None),
            ("FAILED", ""),
            ("FAILED", "x" * 513),
            ("PASSED", "unexpected message"),
            ("RUNNING", None),
            ("PENDING", None),
        ):
            with self.assertRaisesRegex(
                V2DatabaseError,
                "status|error",
                msg=repr((status, error[:8] if error else error)),
            ):
                self.database.record_validation_result(validation_run_id, status, error)

        self.assertTrue(
            self.database.record_validation_result(validation_run_id, "PASSED", None)
        )
        completed = self.database.get_validation_run(validation_run_id)
        assert completed is not None
        self.assertEqual(completed.status, "PASSED")
        self.assertIsNone(completed.error)

        # One-shot: a completed run never records another outcome.
        self.assertFalse(
            self.database.record_validation_result(validation_run_id, "PASSED", None)
        )
        # Unknown runs report False rather than mutating anything.
        self.assertFalse(
            self.database.record_validation_result("missing", "PASSED", None)
        )

        failed_run = self._validation_run(run_id, candidate_id)
        self.assertTrue(
            self.database.record_validation_result(
                failed_run, "FAILED", "collected 2 errors"
            )
        )
        failed = self.database.get_validation_run(failed_run)
        assert failed is not None
        self.assertEqual(failed.status, "FAILED")
        self.assertEqual(failed.error, "collected 2 errors")

    def _assert_stays_pending(self, validation_run_id: str) -> None:
        record = self.database.get_validation_run(validation_run_id)
        self.assertIsNotNone(record)
        assert record is not None
        self.assertEqual(record.status, "PENDING")
        self.assertIsNone(record.error)

    def test_stale_candidate_revision_blocks_result_terminalization(self) -> None:
        run_id, candidate_id = self._candidate()
        self._profile(revision=0)
        validation_run_id = self._validation_run(run_id, candidate_id)

        # A candidate revision advance mid-validation makes the run's
        # recorded binding stale; terminalizing it would leave misleading
        # terminal evidence for a revision that is no longer current.
        self.assertTrue(self.database.advance_candidate(candidate_id, 0))

        with self.assertRaisesRegex(V2DatabaseError, "stale"):
            self.database.record_validation_result(validation_run_id, "PASSED", None)
        self._assert_stays_pending(validation_run_id)

        # The same staleness rejects a FAILED outcome.
        with self.assertRaisesRegex(V2DatabaseError, "stale"):
            self.database.record_validation_result(
                validation_run_id, "FAILED", "collected 2 errors"
            )
        self._assert_stays_pending(validation_run_id)

        # Malformed outcomes still fail closed before the currency checks.
        with self.assertRaisesRegex(V2DatabaseError, "status|error"):
            self.database.record_validation_result(validation_run_id, "FAILED", None)
        with self.assertRaisesRegex(V2DatabaseError, "status|error"):
            self.database.record_validation_result(
                validation_run_id, "PASSED", "unexpected message"
            )
        self._assert_stays_pending(validation_run_id)

        # A fresh run against the current revision still terminalizes.
        fresh_run = self._validation_run(run_id, candidate_id, revision=1)
        self.assertTrue(
            self.database.record_validation_result(fresh_run, "PASSED", None)
        )
        fresh = self.database.get_validation_run(fresh_run)
        assert fresh is not None
        self.assertEqual(fresh.status, "PASSED")

    def test_run_ownership_drift_blocks_result_terminalization(self) -> None:
        run_id, candidate_id = self._candidate()
        self._profile(revision=0)
        validation_run_id = self._validation_run(run_id, candidate_id)

        # Repoint the candidate at another run directly (no API path
        # does this); the validation run's binding no longer owns the
        # candidate, so its outcome must not be terminalized.
        other_run, _ = self._candidate()
        self.database.close()
        raw = sqlite3.connect(self.database_path)
        try:
            raw.execute(
                "UPDATE candidates SET run_id = ? WHERE candidate_id = ?",
                (other_run, candidate_id),
            )
            raw.commit()
        finally:
            raw.close()
        self.database = open_v2_database(self.database_path)

        with self.assertRaisesRegex(V2DatabaseError, "belongs"):
            self.database.record_validation_result(validation_run_id, "PASSED", None)
        self._assert_stays_pending(validation_run_id)

    def test_missing_reference_profile_blocks_result_terminalization(self) -> None:
        run_id, candidate_id = self._candidate()
        self._profile(revision=0)
        validation_run_id = self._validation_run(run_id, candidate_id)

        # Profile revisions are immutable through the API (re-declaration
        # rejects, no update or delete path exists), so removing the
        # referenced row requires direct database access.  A terminal
        # record citing a missing profile revision would be misleading.
        self.database.close()
        raw = sqlite3.connect(self.database_path)
        try:
            raw.execute("PRAGMA foreign_keys = OFF")
            raw.execute(
                "DELETE FROM reference_profiles WHERE"
                " reference_profile_id = 'profile-0'"
            )
            raw.commit()
        finally:
            raw.close()
        self.database = open_v2_database(self.database_path)

        with self.assertRaisesRegex(V2DatabaseError, "profile"):
            self.database.record_validation_result(validation_run_id, "PASSED", None)
        self._assert_stays_pending(validation_run_id)

    def test_corrupted_reference_profile_blocks_result_terminalization(self) -> None:
        run_id, candidate_id = self._candidate()
        self._profile(revision=0)
        validation_run_id = self._validation_run(run_id, candidate_id)

        # A profile row that exists but no longer revalidates as a
        # ReferenceProfileRecordV2 must not be terminalized against.
        self.database.close()
        raw = sqlite3.connect(self.database_path)
        try:
            raw.execute(
                "UPDATE reference_profiles SET python_version = '' WHERE"
                " reference_profile_id = 'profile-0'"
            )
            raw.commit()
        finally:
            raw.close()
        self.database = open_v2_database(self.database_path)

        with self.assertRaisesRegex(V2DatabaseError, "corrupted"):
            self.database.record_validation_result(validation_run_id, "PASSED", None)
        self._assert_stays_pending(validation_run_id)

    def test_validation_rows_fail_closed_on_corrupted_shapes(self) -> None:
        run_id, candidate_id = self._candidate()
        profile = self._profile(revision=0)
        validation_run_id = self._validation_run(run_id, candidate_id)

        self.database.close()
        raw = sqlite3.connect(self.database_path)
        try:
            raw.execute("PRAGMA ignore_check_constraints = ON")
            raw.execute(
                "UPDATE validation_runs SET status = 'WEIRD' WHERE"
                " validation_run_id = ?",
                (validation_run_id,),
            )
            raw.commit()
        finally:
            raw.close()
        self.database = open_v2_database(self.database_path)
        with self.assertRaises(ValueError):
            self.database.get_validation_run(validation_run_id)

        self.database.close()
        raw = sqlite3.connect(self.database_path)
        try:
            raw.execute(
                "UPDATE reference_profiles SET python_version = '' WHERE"
                " reference_profile_id = ?",
                (profile.reference_profile_id,),
            )
            raw.commit()
        finally:
            raw.close()
        self.database = open_v2_database(self.database_path)
        with self.assertRaises(ValueError):
            self.database.get_reference_profile(
                profile.reference_profile_id, profile.profile_revision
            )

    def test_revision_advance_invalidates_old_references_durably(self) -> None:
        run_id, candidate_id = self._candidate()
        self._profile(revision=0)
        validation_run_id = self._validation_run(run_id, candidate_id)
        artifact_id = self.database.create_artifact(
            run_id, "FINAL_DIFF", "artifacts/diff.json"
        )
        self.database.create_candidate_diff(
            run_id=run_id,
            candidate_id=candidate_id,
            candidate_revision=0,
            artifact_id=artifact_id,
        )

        # The old result can still be recorded as bookkeeping ...
        self.assertTrue(
            self.database.record_validation_result(validation_run_id, "PASSED", None)
        )
        # ... but the content mutation advances the revision ...
        self.assertTrue(self.database.advance_candidate(candidate_id, 0))
        control = self.database.get_candidate_control(candidate_id)
        assert control is not None
        self.assertEqual(control.revision, 1)

        # ... and new control-plane references to the stale revision fail.
        with self.assertRaisesRegex(V2DatabaseError, "stale"):
            self._validation_run(run_id, candidate_id, revision=0)
        with self.assertRaisesRegex(V2DatabaseError, "stale"):
            self.database.create_candidate_diff(
                run_id=run_id,
                candidate_id=candidate_id,
                candidate_revision=0,
                artifact_id=artifact_id,
            )

        # The recorded old-revision evidence no longer binds to the
        # current candidate state.
        run_record = self.database.get_validation_run(validation_run_id)
        assert run_record is not None
        result = ValidationResultV2(
            validation_run_id=run_record.validation_run_id,
            run_id=run_record.run_id,
            candidate_id=run_record.candidate_id,
            candidate_revision=run_record.candidate_revision,
            reference_profile_id=run_record.reference_profile_id,
            reference_profile_revision=run_record.reference_profile_revision,
            status=run_record.status,
            error=run_record.error,
        )
        current = ValidationBindingV2(
            run_id=run_id,
            candidate_id=candidate_id,
            candidate_revision=control.revision,
            reference_profile_id="profile-0",
            reference_profile_revision=0,
        )
        with self.assertRaises(ValueError):
            verify_evidence_binding(result, run=run_record, expected=current)

    def test_no_v1_rows_are_migrated_by_the_b1_schema(self) -> None:
        # A v1 database stays read-only legacy: the initializer refuses it.
        legacy = self.root / "legacy-v1.sqlite"
        connection = sqlite3.connect(legacy)
        connection.execute("CREATE TABLE schema_migrations (version INTEGER)")
        connection.commit()
        connection.close()
        with self.assertRaisesRegex(V2DatabaseError, "read-only"):
            initialize_v2_database(legacy)

    def test_ids_stay_opaque_in_every_b1_table(self) -> None:
        run_id, candidate_id = self._candidate()
        profile = self._profile(revision=0)
        validation_run_id = self._validation_run(run_id, candidate_id)

        run_record = self.database.get_validation_run(validation_run_id)
        assert run_record is not None
        for value in (
            run_id,
            candidate_id,
            profile.reference_profile_id,
            validation_run_id,
        ):
            self.assertNotRegex(value, r"^[0-9a-f]{64}$")
            self.assertNotIn("digest", value.lower())


if __name__ == "__main__":
    unittest.main()

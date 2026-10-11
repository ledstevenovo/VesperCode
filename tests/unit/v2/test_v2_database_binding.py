"""Route B / B4b-02A: the production database-backed execution binding.

``DatabaseBackedExecutionBinding`` (``execution/v2_database_binding.py``)
is the production-shaped read-only ``V2ExecutionBindingPort`` over a REAL
``V2Database``: it resolves the cited (run, candidate) pair to the
candidate's CURRENT revision and extends the binding gate to the B1
validation run — the request must cite a ``validation_run_id`` (an
uncited request rejects with the closed ``VALIDATION_BINDING_REQUIRED``
code), the cited validation run must belong to the same run, the same
candidate, at the CURRENT candidate revision, under the request's own
reference profile id/revision, whose ``reference_profiles`` row must
still exist and revalidate, and the validation must be terminal
``PASSED`` — a ``PENDING`` or ``FAILED`` validation, a foreign or stale
one, or a corrupt or missing control row rejects with a closed code
BEFORE the readiness port is consulted and with ZERO executor calls.

The binding is read-only: it never mutates the control plane (no
approval consumption, no validation result creation, no candidate
advancement) and never fabricates facts — an unresolved or corrupt
record is a closed rejection, never fake data.  This suite drives the
adapter directly AND through the whole ``V2ExecutionService`` over a
real v2 control database (run, snapshot, candidate, reference profile,
and validation run rows), including a fresh-process reopen that proves
the adapter resolves durable committed state, not in-memory fixtures.
No Docker, network, or third-party package is involved: the readiness
and executor edges are the deterministic B4a fakes.
"""

from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from vespercode.execution.v2_database_binding import (
    DatabaseBackedExecutionBinding,
)
from vespercode.execution.v2_execution import (
    EXECUTION_MESSAGES_V2,
    ExecutionActionRequestV2,
    ExecutionBindingOutcomeV2,
    V2ExecutionBindingPort,
)
from vespercode.execution.v2_executor import (
    FakeV2Executor,
    FakeV2Readiness,
    V2ExecutionService,
)
from vespercode.execution.v2_profile import (
    EXECUTION_MAX_OUTPUT_BYTES_V2,
    ExecutionProfileRecordV2,
)
from vespercode.profiles.v2_reference import ReferenceProfileRecordV2
from vespercode.storage.v2_database import (
    V2_DATABASE_FILENAME,
    initialize_v2_database,
    open_v2_database,
)

_REPO_ROOT = Path(__file__).resolve().parents[3]
_SRC_ROOT = _REPO_ROOT / "src"

# Every v2 table the read-only proof snapshots: the binding must leave
# each one byte-for-byte unchanged.
_V2_TABLES = (
    "v2_schema_meta",
    "runs",
    "snapshots",
    "candidates",
    "actions",
    "disclosures",
    "artifacts",
    "writeback_approvals",
    "transactions",
    "transaction_journal",
    "reference_profiles",
    "candidate_diffs",
    "validation_runs",
    "provider_endpoints",
    "disclosure_grants",
    "disclosure_grant_categories",
    "disclosure_grant_scopes",
    "disclosure_authorizations",
    "disclosure_authorization_sources",
)


def _profile() -> ExecutionProfileRecordV2:
    """The bound execution profile: the B1 reference profile revision."""

    return ExecutionProfileRecordV2(
        execution_profile_id="exec-profile-1",
        execution_profile_revision=4,
        reference_profile_id="reference-1",
        reference_profile_revision=3,
        image_reference="vespercode-validation-image",
        network_disabled=True,
        non_root_user="10001:10001",
        read_only_rootfs=True,
        all_capabilities_dropped=True,
        docker_socket_mounted=False,
        workspace_mount_read_only=True,
        timeout_seconds=120,
        max_output_bytes=EXECUTION_MAX_OUTPUT_BYTES_V2,
    )


def _reference_profile(revision: int = 3) -> ReferenceProfileRecordV2:
    return ReferenceProfileRecordV2(
        "reference-1",
        revision,
        "3.12.4",
        "8.4.2",
        "0.16.1",
        "2.3.0",
    )


class DatabaseBackedExecutionBindingTests(unittest.TestCase):
    """The production binding over a real v2 control database."""

    def setUp(self) -> None:
        self._directory = tempfile.TemporaryDirectory()
        self.root = Path(self._directory.name)
        self.database_path = self.root / V2_DATABASE_FILENAME
        initialize_v2_database(self.database_path)
        self.database = open_v2_database(self.database_path)
        self.run_id = self.database.create_run(str(self.root))
        snapshot_id = self.database.create_snapshot(self.run_id)
        self.candidate_id = self.database.create_candidate(
            self.run_id, snapshot_id
        )
        self.database.create_reference_profile(_reference_profile())
        self.validation_run_id = self.database.create_validation_run(
            run_id=self.run_id,
            candidate_id=self.candidate_id,
            candidate_revision=0,
            reference_profile_id="reference-1",
            reference_profile_revision=3,
        )
        self.assertTrue(
            self.database.record_validation_result(
                self.validation_run_id, "PASSED"
            )
        )
        self.binding = DatabaseBackedExecutionBinding(self.database)
        self.readiness = FakeV2Readiness()
        self.executor = FakeV2Executor()
        self.service = V2ExecutionService(
            _profile(), self.binding, self.readiness, self.executor
        )

    def tearDown(self) -> None:
        self.database.close()
        self._directory.cleanup()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _request(
        self,
        *,
        run_id: str | None = None,
        candidate_id: str | None = None,
        candidate_revision: int | None = None,
        validation_run_id: str | None = None,
        reference_profile_revision: int | None = None,
    ) -> ExecutionActionRequestV2:
        bound_candidate = (
            self.candidate_id if candidate_id is None else candidate_id
        )
        bound_revision = 0 if candidate_revision is None else candidate_revision
        values: dict[str, object] = {
            "request_id": "exec-request-db-1",
            "execution_profile_id": "exec-profile-1",
            "execution_profile_revision": 4,
            "reference_profile_id": "reference-1",
            "reference_profile_revision": (
                3 if reference_profile_revision is None
                else reference_profile_revision
            ),
            "run_id": self.run_id if run_id is None else run_id,
            "candidate_id": bound_candidate,
            "candidate_revision": bound_revision,
            "action_kind": "VALIDATE_CANDIDATE",
            "argv": ("vespercode-validate", bound_candidate, str(bound_revision)),
            "validation_run_id": validation_run_id,
        }
        return ExecutionActionRequestV2(**values)  # type: ignore[arg-type]

    def _cited_request(self) -> ExecutionActionRequestV2:
        return self._request(validation_run_id=self.validation_run_id)

    def _passed_validation(self, revision: int = 0) -> str:
        """A new terminal-PASSED validation run for a given revision."""

        identifier = self.database.create_validation_run(
            run_id=self.run_id,
            candidate_id=self.candidate_id,
            candidate_revision=revision,
            reference_profile_id="reference-1",
            reference_profile_revision=3,
        )
        self.assertTrue(
            self.database.record_validation_result(identifier, "PASSED")
        )
        return identifier

    def _snapshot_tables(self) -> dict[str, list[tuple]]:
        """The full row content of every v2 table, for the read-only proof."""

        snapshot: dict[str, list[tuple]] = {}
        for table in _V2_TABLES:
            rows = self.database._connection.execute(
                f"SELECT * FROM {table}"
            ).fetchall()
            snapshot[table] = [tuple(row) for row in rows]
        return snapshot

    def _tamper(self, sql: str, parameters: tuple) -> None:
        """Corrupt a row through a raw connection (no CHECK bypass needed)."""

        self.database.close()
        raw = sqlite3.connect(self.database_path)
        try:
            raw.execute("PRAGMA foreign_keys = OFF")
            raw.execute(sql, parameters)
            raw.commit()
        finally:
            raw.close()
        self.database = open_v2_database(self.database_path)
        self.binding = DatabaseBackedExecutionBinding(self.database)
        self.service = V2ExecutionService(
            _profile(), self.binding, self.readiness, self.executor
        )

    # ------------------------------------------------------------------
    # Port contract
    # ------------------------------------------------------------------

    def test_the_adapter_implements_the_binding_port(self) -> None:
        self.assertIsInstance(self.binding, V2ExecutionBindingPort)

    def test_the_adapter_requires_a_v2_database(self) -> None:
        for bad in (None, "database", self.database_path, object()):
            with self.subTest(bad=type(bad).__name__):
                with self.assertRaises(ValueError):
                    DatabaseBackedExecutionBinding(bad)  # type: ignore[arg-type]

    # ------------------------------------------------------------------
    # The valid current binding
    # ------------------------------------------------------------------

    def test_a_valid_current_binding_resolves_with_the_passed_validation(
        self,
    ) -> None:
        outcome = self.binding.lookup_execution_binding(
            self.run_id,
            self.candidate_id,
            self.validation_run_id,
            "reference-1",
            3,
        )
        self.assertIsInstance(outcome, ExecutionBindingOutcomeV2)
        self.assertEqual(outcome.kind, "RESOLVED")
        facts = outcome.facts
        assert facts is not None
        self.assertEqual(facts.run_id, self.run_id)
        self.assertEqual(facts.candidate_id, self.candidate_id)
        self.assertEqual(facts.candidate_revision, 0)
        assert facts.validation is not None
        self.assertEqual(
            facts.validation.validation_run_id, self.validation_run_id
        )
        self.assertEqual(facts.validation.run_id, self.run_id)
        self.assertEqual(facts.validation.candidate_id, self.candidate_id)
        self.assertEqual(facts.validation.candidate_revision, 0)
        self.assertEqual(facts.validation.reference_profile_id, "reference-1")
        self.assertEqual(facts.validation.reference_profile_revision, 3)
        self.assertEqual(facts.validation.status, "PASSED")

    def test_a_valid_current_binding_executes_exactly_once(self) -> None:
        outcome = self.service.execute(self._cited_request())
        self.assertEqual(outcome.status, "SUCCEEDED")
        self.assertIsNone(outcome.error_code)
        self.assertEqual(outcome.message, EXECUTION_MESSAGES_V2["SUCCEEDED"])
        self.assertEqual(len(self.readiness.checks), 1)
        self.assertEqual(len(self.executor.calls), 1)

    # ------------------------------------------------------------------
    # The citation is required (the production shape)
    # ------------------------------------------------------------------

    def test_an_uncited_validation_run_rejects_before_readiness(self) -> None:
        outcome = self.service.execute(self._request())
        self.assertEqual(outcome.status, "FAILED")
        self.assertEqual(outcome.error_code, "VALIDATION_BINDING_REQUIRED")
        self.assertEqual(
            outcome.message,
            EXECUTION_MESSAGES_V2["VALIDATION_BINDING_REQUIRED"],
        )
        self.assertEqual(self.readiness.checks, [])
        self.assertEqual(self.executor.calls, [])

    def test_the_adapter_itself_requires_a_citation(self) -> None:
        # Defense in depth, pinned at the port: the production service
        # now rejects an uncited request before the binding port is
        # consulted, so the adapter's own fail-closed citation rule
        # is pinned here by a direct port call.
        outcome = self.binding.lookup_execution_binding(
            self.run_id,
            self.candidate_id,
            None,
            "reference-1",
            3,
        )
        self.assertEqual(outcome.kind, "VALIDATION_REQUIRED")
        self.assertIsNone(outcome.facts)

    # ------------------------------------------------------------------
    # Unknown / foreign run and candidate
    # ------------------------------------------------------------------

    def test_an_unknown_run_rejects_before_readiness(self) -> None:
        outcome = self.service.execute(
            self._request(
                run_id="run-missing",
                validation_run_id=self.validation_run_id,
            )
        )
        self.assertEqual(outcome.status, "FAILED")
        self.assertEqual(outcome.error_code, "EXECUTION_BINDING_NOT_FOUND")
        self.assertEqual(self.readiness.checks, [])
        self.assertEqual(self.executor.calls, [])

    def test_an_unknown_candidate_rejects_before_readiness(self) -> None:
        outcome = self.service.execute(
            self._request(
                candidate_id="cand-missing",
                validation_run_id=self.validation_run_id,
            )
        )
        self.assertEqual(outcome.status, "FAILED")
        self.assertEqual(outcome.error_code, "EXECUTION_BINDING_NOT_FOUND")
        self.assertEqual(self.readiness.checks, [])
        self.assertEqual(self.executor.calls, [])

    def test_a_candidate_from_a_foreign_run_rejects(self) -> None:
        other_run = self.database.create_run(str(self.root))
        other_snapshot = self.database.create_snapshot(other_run)
        other_candidate = self.database.create_candidate(
            other_run, other_snapshot
        )
        outcome = self.service.execute(
            self._request(
                candidate_id=other_candidate,
                validation_run_id=self.validation_run_id,
            )
        )
        self.assertEqual(outcome.status, "FAILED")
        self.assertEqual(outcome.error_code, "EXECUTION_BINDING_NOT_FOUND")
        self.assertEqual(self.readiness.checks, [])
        self.assertEqual(self.executor.calls, [])

    def test_an_unknown_validation_run_rejects_before_readiness(self) -> None:
        outcome = self.service.execute(
            self._request(validation_run_id="valid-missing")
        )
        self.assertEqual(outcome.status, "FAILED")
        self.assertEqual(outcome.error_code, "VALIDATION_BINDING_NOT_FOUND")
        self.assertEqual(self.readiness.checks, [])
        self.assertEqual(self.executor.calls, [])

    def test_a_validation_from_a_foreign_run_rejects(self) -> None:
        other_run = self.database.create_run(str(self.root))
        other_snapshot = self.database.create_snapshot(other_run)
        other_candidate = self.database.create_candidate(
            other_run, other_snapshot
        )
        other_validation = self.database.create_validation_run(
            run_id=other_run,
            candidate_id=other_candidate,
            candidate_revision=0,
            reference_profile_id="reference-1",
            reference_profile_revision=3,
        )
        self.assertTrue(
            self.database.record_validation_result(other_validation, "PASSED")
        )
        outcome = self.service.execute(
            self._request(validation_run_id=other_validation)
        )
        self.assertEqual(outcome.status, "FAILED")
        self.assertEqual(outcome.error_code, "VALIDATION_BINDING_NOT_FOUND")
        self.assertEqual(self.readiness.checks, [])
        self.assertEqual(self.executor.calls, [])

    # ------------------------------------------------------------------
    # Stale candidate revisions
    # ------------------------------------------------------------------

    def test_a_stale_candidate_revision_rejects_before_readiness(self) -> None:
        # The candidate advanced, and a NEW validation passed at the
        # current revision — a request still citing the OLD revision is
        # stale: the resolved facts carry the current revision, and the
        # service comparison rejects with the closed STALE code.
        self.assertTrue(
            self.database.advance_candidate(self.candidate_id, 0)
        )
        current_validation = self._passed_validation(revision=1)
        outcome = self.service.execute(
            self._request(validation_run_id=current_validation)
        )
        self.assertEqual(outcome.status, "FAILED")
        self.assertEqual(outcome.error_code, "EXECUTION_BINDING_STALE")
        self.assertEqual(
            outcome.message, EXECUTION_MESSAGES_V2["EXECUTION_BINDING_STALE"]
        )
        self.assertEqual(self.readiness.checks, [])
        self.assertEqual(self.executor.calls, [])
        # The request citing the current revision executes.
        accepted = self.service.execute(
            self._request(
                candidate_revision=1,
                validation_run_id=current_validation,
            )
        )
        self.assertEqual(accepted.status, "SUCCEEDED")

    def test_a_validation_of_a_stale_revision_rejects(self) -> None:
        # The candidate advanced AFTER the validation passed: the
        # recorded PASSED validation is no longer evidence for the
        # current revision and must not resolve.
        self.assertTrue(
            self.database.advance_candidate(self.candidate_id, 0)
        )
        outcome = self.service.execute(
            self._request(
                candidate_revision=1,
                validation_run_id=self.validation_run_id,
            )
        )
        self.assertEqual(outcome.status, "FAILED")
        self.assertEqual(outcome.error_code, "VALIDATION_BINDING_NOT_FOUND")
        self.assertEqual(self.readiness.checks, [])
        self.assertEqual(self.executor.calls, [])

    # ------------------------------------------------------------------
    # Pending / failed validations
    # ------------------------------------------------------------------

    def test_a_pending_validation_rejects_before_readiness(self) -> None:
        pending_validation = self.database.create_validation_run(
            run_id=self.run_id,
            candidate_id=self.candidate_id,
            candidate_revision=0,
            reference_profile_id="reference-1",
            reference_profile_revision=3,
        )
        # Left PENDING: no terminal result is ever recorded.
        outcome = self.service.execute(
            self._request(validation_run_id=pending_validation)
        )
        self.assertEqual(outcome.status, "FAILED")
        self.assertEqual(outcome.error_code, "VALIDATION_BINDING_NOT_PASSED")
        self.assertEqual(
            outcome.message,
            EXECUTION_MESSAGES_V2["VALIDATION_BINDING_NOT_PASSED"],
        )
        self.assertEqual(self.readiness.checks, [])
        self.assertEqual(self.executor.calls, [])

    def test_a_failed_validation_rejects_before_readiness(self) -> None:
        failed_validation = self.database.create_validation_run(
            run_id=self.run_id,
            candidate_id=self.candidate_id,
            candidate_revision=0,
            reference_profile_id="reference-1",
            reference_profile_revision=3,
        )
        self.assertTrue(
            self.database.record_validation_result(
                failed_validation, "FAILED", "2 checks failed"
            )
        )
        outcome = self.service.execute(
            self._request(validation_run_id=failed_validation)
        )
        self.assertEqual(outcome.status, "FAILED")
        self.assertEqual(outcome.error_code, "VALIDATION_BINDING_NOT_PASSED")
        self.assertEqual(self.readiness.checks, [])
        self.assertEqual(self.executor.calls, [])

    # ------------------------------------------------------------------
    # Reference profile binding
    # ------------------------------------------------------------------

    def test_a_reference_profile_revision_mismatch_rejects(self) -> None:
        # The request (and the bound execution profile) cite revision 3;
        # a PASSED validation recorded under a DIFFERENT revision of the
        # same reference profile must not resolve for this request.
        self.database.create_reference_profile(_reference_profile(4))
        other_validation = self.database.create_validation_run(
            run_id=self.run_id,
            candidate_id=self.candidate_id,
            candidate_revision=0,
            reference_profile_id="reference-1",
            reference_profile_revision=4,
        )
        self.assertTrue(
            self.database.record_validation_result(other_validation, "PASSED")
        )
        outcome = self.service.execute(
            self._request(validation_run_id=other_validation)
        )
        self.assertEqual(outcome.status, "FAILED")
        self.assertEqual(outcome.error_code, "VALIDATION_BINDING_NOT_FOUND")
        self.assertEqual(self.readiness.checks, [])
        self.assertEqual(self.executor.calls, [])

    def test_a_validation_whose_profile_row_is_missing_rejects(self) -> None:
        # The validation cites a reference profile revision whose row a
        # foreign writer removed: the terminal record names
        # configuration that can no longer be read, so it must not
        # resolve (the adapter fails closed at the port).
        self.database.create_reference_profile(_reference_profile(5))
        orphan_validation = self.database.create_validation_run(
            run_id=self.run_id,
            candidate_id=self.candidate_id,
            candidate_revision=0,
            reference_profile_id="reference-1",
            reference_profile_revision=5,
        )
        self.assertTrue(
            self.database.record_validation_result(orphan_validation, "PASSED")
        )
        self._tamper(
            "DELETE FROM reference_profiles WHERE profile_revision = ?",
            (5,),
        )
        outcome = self.binding.lookup_execution_binding(
            self.run_id,
            self.candidate_id,
            orphan_validation,
            "reference-1",
            5,
        )
        self.assertEqual(outcome.kind, "VALIDATION_NOT_FOUND")
        # Through the service, the request's own profile binding (5)
        # does not match the bound execution profile (3), so the
        # service's earlier profile gate rejects first — with the same
        # zero downstream calls.
        service_outcome = self.service.execute(
            self._request(
                reference_profile_revision=5,
                validation_run_id=orphan_validation,
            )
        )
        self.assertEqual(
            service_outcome.error_code, "PROFILE_BINDING_MISMATCH"
        )
        self.assertEqual(self.readiness.checks, [])
        self.assertEqual(self.executor.calls, [])

    # ------------------------------------------------------------------
    # Corrupted rows
    # ------------------------------------------------------------------

    def test_a_corrupted_validation_row_rejects_before_readiness(self) -> None:
        # A foreign writer blanked the reference profile id: the row no
        # longer revalidates as a B1 validation run record.
        self._tamper(
            "UPDATE validation_runs SET reference_profile_id = ''"
            " WHERE validation_run_id = ?",
            (self.validation_run_id,),
        )
        outcome = self.service.execute(self._cited_request())
        self.assertEqual(outcome.status, "FAILED")
        self.assertEqual(outcome.error_code, "VALIDATION_BINDING_NOT_FOUND")
        self.assertEqual(self.readiness.checks, [])
        self.assertEqual(self.executor.calls, [])

    def test_a_corrupted_candidate_row_rejects_before_readiness(self) -> None:
        # A foreign writer set a lifecycle status outside the closed
        # vocabulary: the candidates row no longer revalidates.
        self._tamper(
            "UPDATE candidates SET status = 'OPEN' WHERE candidate_id = ?",
            (self.candidate_id,),
        )
        outcome = self.service.execute(self._cited_request())
        self.assertEqual(outcome.status, "FAILED")
        self.assertEqual(outcome.error_code, "EXECUTION_BINDING_NOT_FOUND")
        self.assertEqual(self.readiness.checks, [])
        self.assertEqual(self.executor.calls, [])

    def test_a_corrupted_reference_profile_row_rejects(self) -> None:
        # A foreign writer blanked a declared version: the profile row
        # no longer revalidates as a B1 reference profile record, so
        # the validation that cites it cannot resolve.
        self._tamper(
            "UPDATE reference_profiles SET python_version = ''"
            " WHERE reference_profile_id = ? AND profile_revision = 3",
            ("reference-1",),
        )
        outcome = self.service.execute(self._cited_request())
        self.assertEqual(outcome.status, "FAILED")
        self.assertEqual(outcome.error_code, "VALIDATION_BINDING_NOT_FOUND")
        self.assertEqual(self.readiness.checks, [])
        self.assertEqual(self.executor.calls, [])

    # ------------------------------------------------------------------
    # Read-only proof
    # ------------------------------------------------------------------

    def test_the_binding_is_read_only(self) -> None:
        before = self._snapshot_tables()
        # Every lookup shape, accepted and rejected alike.
        self.binding.lookup_execution_binding(
            self.run_id,
            self.candidate_id,
            self.validation_run_id,
            "reference-1",
            3,
        )
        self.binding.lookup_execution_binding(
            "run-missing",
            self.candidate_id,
            self.validation_run_id,
            "reference-1",
            3,
        )
        self.binding.lookup_execution_binding(
            self.run_id, self.candidate_id, None, "reference-1", 3,
        )
        self.binding.lookup_execution_binding(
            self.run_id,
            self.candidate_id,
            "valid-missing",
            "reference-1",
            3,
        )
        self.service.execute(self._cited_request())
        self.service.execute(self._request(validation_run_id="valid-x"))
        after = self._snapshot_tables()
        self.assertEqual(before, after)

    # ------------------------------------------------------------------
    # Fresh-process reopen
    # ------------------------------------------------------------------

    def test_a_fresh_process_reopens_and_resolves_the_same_binding(
        self,
    ) -> None:
        # A brand-new interpreter, a brand-new database connection, and
        # a brand-new adapter must resolve the same committed binding —
        # the adapter reads durable control-plane state, never an
        # in-memory fixture or process-global cache.
        self.database.close()
        script = (
            "import json, sys\n"
            "from pathlib import Path\n"
            "from vespercode.execution.v2_database_binding import"
            " DatabaseBackedExecutionBinding\n"
            "from vespercode.storage.v2_database import open_v2_database\n"
            "database = open_v2_database(Path(sys.argv[1]))\n"
            "try:\n"
            "    binding = DatabaseBackedExecutionBinding(database)\n"
            "    outcome = binding.lookup_execution_binding(\n"
            "        sys.argv[2], sys.argv[3], sys.argv[4],\n"
            "        sys.argv[5], int(sys.argv[6]),\n"
            "    )\n"
            "    facts = outcome.facts\n"
            "    print(json.dumps({\n"
            "        'kind': outcome.kind,\n"
            "        'revision': (None if facts is None"
            " else facts.candidate_revision),\n"
            "        'status': (None if facts is None"
            " or facts.validation is None\n"
            "                   else facts.validation.status),\n"
            "    }))\n"
            "finally:\n"
            "    database.close()\n"
        )
        completed = subprocess.run(
            [
                sys.executable,
                "-c",
                script,
                str(self.database_path),
                self.run_id,
                self.candidate_id,
                self.validation_run_id,
                "reference-1",
                "3",
            ],
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
            cwd=str(_REPO_ROOT),
            env={**os.environ, "PYTHONPATH": str(_SRC_ROOT)},
        )
        self.assertEqual(
            completed.returncode,
            0,
            f"fresh-process probe failed: {completed.stderr}",
        )
        report = json.loads(completed.stdout.strip())
        self.assertEqual(report["kind"], "RESOLVED")
        self.assertEqual(report["revision"], 0)
        self.assertEqual(report["status"], "PASSED")
        # The original process's adapter resolves it too after reopen.
        self.database = open_v2_database(self.database_path)
        self.binding = DatabaseBackedExecutionBinding(self.database)
        outcome = self.binding.lookup_execution_binding(
            self.run_id,
            self.candidate_id,
            self.validation_run_id,
            "reference-1",
            3,
        )
        self.assertEqual(outcome.kind, "RESOLVED")


if __name__ == "__main__":
    unittest.main()

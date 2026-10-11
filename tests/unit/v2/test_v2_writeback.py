"""Route A / A2: explicit, approval-bound atomic writeback.

Pins the fail-closed contract of ``V2WritebackService``: writes reach the
port only after candidate freshness, approval, policy, and strict
CREATE/REPLACE target checks all pass; the approval is consumed exactly
once; a fault mid-write leaves a durable ``UNRESOLVED`` transaction for
recovery instead of guessing.  Deterministic tests run against the
in-memory port; the real disk port is covered in the harness tests.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from vespercode.contracts.v2_writeback import (
    PlannedWriteV2,
    V2WorkspacePort,
    WritebackRequestV2,
    WriteOperationV2,
)
from vespercode.storage.v2_database import (
    V2_DATABASE_FILENAME,
    initialize_v2_database,
    open_v2_database,
)
from vespercode.persistence.v2_writeback import V2WritebackService


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


class V2WritebackServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self._directory = tempfile.TemporaryDirectory()
        self.root = Path(self._directory.name)
        self.workspace = self.root / "workspace"
        self.workspace.mkdir()
        self.database_path = self.root / "control" / V2_DATABASE_FILENAME
        initialize_v2_database(self.database_path)
        self.database = open_v2_database(self.database_path)
        from vespercode.tools.v2_dispatcher import InMemoryWorkspacePort

        self.port = InMemoryWorkspacePort()
        self.port.replace("src/old.py", "old body")
        self.service = V2WritebackService(
            self.database, self.port, workspace=self.workspace
        )

    def tearDown(self) -> None:
        self.database.close()
        self._directory.cleanup()

    def _request(
        self,
        operations: tuple[WriteOperationV2, ...],
        *,
        candidate_revision: int = 0,
        approval_id: str | None = None,
    ) -> tuple[WritebackRequestV2, str, str, str]:
        run_id = self.database.create_run(str(self.workspace))
        snapshot_id = self.database.create_snapshot(run_id)
        candidate_id = self.database.create_candidate(
            run_id, snapshot_id, revision=candidate_revision
        )
        if approval_id is None:
            approval_id = self.database.create_writeback_approval(
                run_id=run_id,
                candidate_id=candidate_id,
                candidate_revision=candidate_revision,
            )
        request = WritebackRequestV2(
            run_id=run_id,
            candidate_id=candidate_id,
            candidate_revision=candidate_revision,
            approval_id=approval_id,
            operations=operations,
        )
        return request, run_id, candidate_id, approval_id

    def test_committed_writeback_applies_create_and_replace(self) -> None:
        operations = (
            WriteOperationV2("CREATE", "src/new.py", "new body"),
            WriteOperationV2("REPLACE", "src/old.py", "replaced body"),
        )
        request, _, _, _ = self._request(operations)

        outcome = self.service.request_writeback(request)

        self.assertEqual(outcome.status, "COMMITTED")
        self.assertIsNotNone(outcome.transaction_id)
        self.assertEqual(self.port.files["src/new.py"], "new body")
        self.assertEqual(self.port.files["src/old.py"], "replaced body")
        transaction = self.database.get_transaction(outcome.transaction_id)
        assert transaction is not None
        self.assertEqual(transaction["state"], "COMMITTED")

    def test_stale_candidate_revision_writes_nothing_and_keeps_the_approval(self) -> None:
        operations = (WriteOperationV2("CREATE", "src/new.py", "new body"),)
        request, _, candidate_id, approval_id = self._request(operations)
        self.database.advance_candidate(candidate_id, 0)

        outcome = self.service.request_writeback(request)

        self.assertEqual(outcome.status, "STALE")
        self.assertIsNone(outcome.transaction_id)
        self.assertNotIn("src/new.py", self.port.files)
        approval = self.database.get_writeback_approval(approval_id)
        assert approval is not None
        self.assertEqual(approval["status"], "PENDING")

    def test_unknown_or_consumed_approval_is_denied_with_zero_writes(self) -> None:
        operations = (WriteOperationV2("CREATE", "src/new.py", "new body"),)
        request, _, _, _ = self._request(operations)

        first = self.service.request_writeback(request)
        self.assertEqual(first.status, "COMMITTED")
        self.assertEqual(self.port.files["src/new.py"], "new body")
        del self.port.files["src/new.py"]

        second = self.service.request_writeback(request)
        self.assertEqual(second.status, "DENIED")
        self.assertIsNone(second.transaction_id)
        self.assertNotIn("src/new.py", self.port.files)

        missing = WritebackRequestV2(
            run_id=request.run_id,
            candidate_id=request.candidate_id,
            candidate_revision=request.candidate_revision,
            approval_id="missing-approval",
            operations=operations,
        )
        third = self.service.request_writeback(missing)
        self.assertEqual(third.status, "DENIED")
        self.assertNotIn("src/new.py", self.port.files)

    def test_policy_denied_paths_never_reach_the_port(self) -> None:
        operations = (
            WriteOperationV2("CREATE", "src/ok.py", "ok"),
            WriteOperationV2("CREATE", "tests/evil.py", "no"),
        )
        request, _, _, _ = self._request(operations)

        outcome = self.service.request_writeback(request)

        self.assertEqual(outcome.status, "DENIED")
        self.assertIsNone(outcome.transaction_id)
        self.assertNotIn("src/ok.py", self.port.files)
        self.assertNotIn("tests/evil.py", self.port.files)

    def test_sensitive_paths_are_denied_before_any_write(self) -> None:
        operations = (WriteOperationV2("CREATE", ".env", "LEAKED=1"),)
        request, _, _, _ = self._request(operations)

        outcome = self.service.request_writeback(request)

        self.assertEqual(outcome.status, "DENIED")
        self.assertNotIn(".env", self.port.files)

    def test_duplicate_target_paths_are_denied(self) -> None:
        operations = (
            WriteOperationV2("CREATE", "src/a.py", "one"),
            WriteOperationV2("CREATE", "src/a.py", "two"),
        )
        request, _, _, approval_id = self._request(operations)

        outcome = self.service.request_writeback(request)

        self.assertEqual(outcome.status, "DENIED")
        self.assertIsNone(outcome.transaction_id)
        approval = self.database.get_writeback_approval(approval_id)
        assert approval is not None
        self.assertEqual(approval["status"], "PENDING")

    def test_target_mismatches_leave_zero_writes(self) -> None:
        create_on_existing = (WriteOperationV2("CREATE", "src/old.py", "x"),)
        request, _, _, approval_id = self._request(create_on_existing)
        outcome = self.service.request_writeback(request)
        self.assertEqual(outcome.status, "MISMATCH")
        self.assertEqual(self.port.files["src/old.py"], "old body")
        approval = self.database.get_writeback_approval(approval_id)
        assert approval is not None
        self.assertEqual(approval["status"], "PENDING")
        self.assertEqual(
            self.database.list_transactions_in_states(
                ("PREPARED", "WRITING", "UNRESOLVED", "COMMITTED", "ROLLED_BACK")
            ),
            [],
        )

        replace_on_missing = (WriteOperationV2("REPLACE", "src/missing.py", "x"),)
        request_two, _, _, _ = self._request(replace_on_missing)
        outcome_two = self.service.request_writeback(request_two)
        self.assertEqual(outcome_two.status, "MISMATCH")

    def test_injected_fault_marks_unresolved_and_reports_partial_state(self) -> None:
        operations = (
            WriteOperationV2("CREATE", "src/a.py", "one"),
            WriteOperationV2("CREATE", "src/b.py", "two"),
        )
        request, _, _, _ = self._request(operations)
        flaky = FlakyPort(self.port, fail_on_apply=2)
        service = V2WritebackService(self.database, flaky, workspace=self.workspace)

        outcome = service.request_writeback(request)

        self.assertEqual(outcome.status, "FAILED")
        self.assertIsNotNone(outcome.transaction_id)
        transaction = self.database.get_transaction(outcome.transaction_id)
        assert transaction is not None
        self.assertEqual(transaction["state"], "UNRESOLVED")
        # The first write landed; the fault stopped the second.
        self.assertEqual(self.port.files["src/a.py"], "one")
        self.assertNotIn("src/b.py", self.port.files)

    def test_approval_is_consumed_once_across_concurrent_style_requests(self) -> None:
        operations = (WriteOperationV2("CREATE", "src/a.py", "one"),)
        request, _, _, approval_id = self._request(operations)
        flaky = FlakyPort(self.port, fail_on_apply=1)
        service = V2WritebackService(self.database, flaky, workspace=self.workspace)

        failed = service.request_writeback(request)
        self.assertEqual(failed.status, "FAILED")
        approval = self.database.get_writeback_approval(approval_id)
        assert approval is not None
        self.assertEqual(approval["status"], "CONSUMED")

        retry = self.service.request_writeback(request)
        self.assertEqual(retry.status, "DENIED")

    def test_in_memory_port_satisfies_the_workspace_port_protocol(self) -> None:
        self.assertIsInstance(self.port, V2WorkspacePort)

    def test_service_requires_the_database_port_and_workspace(self) -> None:
        from vespercode.persistence.v2_writeback import V2WritebackService as Service

        with self.assertRaises(TypeError):
            Service(self.database, self.port)  # type: ignore[call-arg]
        with self.assertRaises(ValueError):
            Service(self.database, self.port, workspace=self.workspace / "missing-dir")


if __name__ == "__main__":
    unittest.main()

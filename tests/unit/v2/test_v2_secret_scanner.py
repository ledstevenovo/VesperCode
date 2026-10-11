"""Route A / RA-08: secret-like content never enters the writeback journal.

The writeback journal persists staged content into the local v2 control
database.  The path policy keeps sensitive FILES out, but an ordinary
``src/*.py`` can still carry a credential, so a deterministic conservative
scanner runs at the pre-journal boundary: a hit is DENIED before any port
write, before the approval is consumed, and before a transaction or journal
row exists.  The refusal message and the scanner's marker kinds never
contain the matched secret material itself.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from vespercode.contracts.v2_writeback import (
    WritebackRequestV2,
    WriteOperationV2,
)
from vespercode.governance.v2_secret_scanner import find_secret_marker
from vespercode.persistence.v2_writeback import V2WritebackService
from vespercode.storage.v2_database import (
    V2_DATABASE_FILENAME,
    initialize_v2_database,
    open_v2_database,
)
from vespercode.tools.v2_dispatcher import InMemoryWorkspacePort


class SecretScannerTests(unittest.TestCase):
    def test_assignment_markers_are_detected(self) -> None:
        for text in (
            'API_KEY = "abc123"',
            "apikey=value",
            "api-key: value",
            "client_secret = x",
            "secret=x",
            "ACCESS_TOKEN: t",
            "refresh_token=1",
            "auth_token: 1",
            "token = os.environ['TOKEN']",  # credential-loading code
            "password = 'hunter2'",
            "passwd: x",
            "pwd=x",
        ):
            with self.subTest(text=text[:24]):
                self.assertIsNotNone(find_secret_marker(text))

    def test_bearer_and_pem_markers_are_detected(self) -> None:
        for text in (
            "Authorization: Bearer abc.def.ghi",
            "authorization: bearer X",
            "header bearer X",
            "-----BEGIN RSA PRIVATE KEY-----",
            "-----begin ec private key-----",
            "-----BEGIN OPENSSH PRIVATE KEY-----",
            "-----BEGIN PRIVATE KEY-----",
            "-----BEGIN ENCRYPTED PRIVATE KEY-----",
        ):
            with self.subTest(text=text[:32]):
                self.assertIsNotNone(find_secret_marker(text))

    def test_provider_token_forms_are_detected(self) -> None:
        for text in (
            "ghp_" + "A" * 36,
            "github_pat_" + "A" * 40,
            "xoxb-" + "1234567890abcdef",
            "sk-ant-api03-" + "x" * 40,
            "sk-proj-" + "x" * 40,
            "sk_live_" + "a" * 24,
            "rk_test_" + "a" * 24,
            "AKIA" + "ABCDEFGH12ABCDEF",
            "AIza" + "a" * 35,
            "npm_" + "a" * 32,
            "ey" + "j" + "a" * 20 + "." + "b" * 20 + "." + "c" * 15,
        ):
            with self.subTest(text=text[:20]):
                self.assertIsNotNone(find_secret_marker(text))

    def test_clean_content_is_allowed(self) -> None:
        for text in (
            "print('hello')\n",
            "value = compute(x)",
            "tokenizer = AutoTokenizer.from_pretrained(name)",
            "secrets = []  # plural word, no assignment marker",
            "the answer is 42",
            "# 注释\nprint('héllo')\n",
            "x\r\ny",
            "",
        ):
            with self.subTest(text=text[:24]):
                self.assertIsNone(find_secret_marker(text))

    def test_markers_never_contain_the_secret(self) -> None:
        # The returned marker is a fixed spelling or a safe label; the
        # matched token material itself is never returned.
        marker = find_secret_marker("ghp_" + "S" * 40)
        self.assertNotIn("S" * 40, marker)
        marker = find_secret_marker("password = 'hunter2'")
        self.assertNotIn("hunter2", marker)


class WritebackSecretBoundaryTests(unittest.TestCase):
    def setUp(self) -> None:
        self._directory = tempfile.TemporaryDirectory()
        self.root = Path(self._directory.name)
        self.workspace = self.root / "workspace"
        self.workspace.mkdir()
        self.database_path = self.root / "control" / V2_DATABASE_FILENAME
        initialize_v2_database(self.database_path)
        self.database = open_v2_database(self.database_path)
        self.port = InMemoryWorkspacePort()
        self.port.replace("src/old.py", "old body")
        self.service = V2WritebackService(
            self.database, self.port, workspace=self.workspace
        )

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

    def test_writeback_refuses_secret_content_before_journaling(self) -> None:
        request, approval_id = self._request(
            (
                WriteOperationV2("CREATE", "src/clean.py", "print('ok')\n"),
                WriteOperationV2("REPLACE", "src/old.py", 'API_KEY = "abc123"'),
            )
        )

        outcome = self.service.request_writeback(request)

        self.assertEqual(outcome.status, "DENIED")
        self.assertIsNone(outcome.transaction_id)
        # Zero workspace writes: the clean CREATE never landed either.
        self.assertNotIn("src/clean.py", self.port.files)
        self.assertEqual(self.port.files["src/old.py"], "old body")
        # The approval is untouched and nothing was journaled.
        approval = self.database.get_writeback_approval(approval_id)
        assert approval is not None
        self.assertEqual(approval["status"], "PENDING")
        self.assertEqual(
            self.database.list_transactions_in_states(
                ("PREPARED", "WRITING", "UNRESOLVED", "COMMITTED", "ROLLED_BACK")
            ),
            [],
        )

    def test_writeback_refuses_secret_original_before_journaling(self) -> None:
        # The REPLACE target on disk already contains a credential; the
        # journal must not copy those bytes into the database.
        self.port.replace("src/old.py", 'password = "hunter2"')
        request, approval_id = self._request(
            (WriteOperationV2("REPLACE", "src/old.py", "clean replacement"),)
        )

        outcome = self.service.request_writeback(request)

        self.assertEqual(outcome.status, "DENIED")
        self.assertIsNone(outcome.transaction_id)
        self.assertEqual(self.port.files["src/old.py"], 'password = "hunter2"')
        approval = self.database.get_writeback_approval(approval_id)
        assert approval is not None
        self.assertEqual(approval["status"], "PENDING")
        self.assertEqual(
            self.database.list_transactions_in_states(
                ("PREPARED", "WRITING", "UNRESOLVED", "COMMITTED", "ROLLED_BACK")
            ),
            [],
        )

    def test_secret_refusal_message_does_not_leak_the_value(self) -> None:
        request, _ = self._request(
            (WriteOperationV2("REPLACE", "src/old.py", 'api_key = "sk-live-abc123"'),)
        )

        outcome = self.service.request_writeback(request)

        self.assertEqual(outcome.status, "DENIED")
        self.assertNotIn("sk-live-abc123", outcome.message)


if __name__ == "__main__":
    unittest.main()

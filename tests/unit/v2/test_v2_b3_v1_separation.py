"""Route B / B3: v1 governance, CLI, and web authority stay out of the v2
local integration layer.

The v1 CLI (``vespercode.cli``), the v1 loopback web security and app
composition (``vespercode.web.security``, ``vespercode.web.app``, and
the route modules), and every v1 digest-bound governance module remain
in the repository as read-only legacy, but no v2 CLI or WebUI decision
may flow through them.  This guard pins that boundary statically: the
Route B3 production modules must not import any v1 authority module,
must not derive digest-based identity, and must stay standard-library
plus v2-only (no pydantic, no FastAPI).  It reads sources only — no v1
code is imported in the v2 test process at all.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[3]
_SRC_ROOT = _REPO_ROOT / "src" / "vespercode"

_B3_MODULES = (
    "cli_v2.py",
    "shell_v2.py",
    "web/v2_app.py",
    "web/v2_forms.py",
    "web/v2_security.py",
    "web/v2_server.py",
)

# The v1 authority modules: the legacy CLI/composition surface, the v1
# loopback web plane, and the digest-bound governance/storage/credential
# modules.  None of these may be imported by a B3 module for any v2
# decision.
_V1_AUTHORITY_MODULES = (
    "vespercode.cli",
    "vespercode.cli_composition",
    "vespercode.canonical.digest",
    "vespercode.canonical.json_v1",
    "vespercode.canonical.path_v1",
    "vespercode.canonical.timestamp_v1",
    "vespercode.contracts.action",
    "vespercode.contracts.evidence",
    "vespercode.contracts.location",
    "vespercode.contracts.optional",
    "vespercode.contracts.run",
    "vespercode.credentials.port",
    "vespercode.credentials.service",
    "vespercode.credentials.wincred_store",
    "vespercode.governance.disclosure_decision",
    "vespercode.governance.disclosure_ledger",
    "vespercode.governance.disclosure_revocation",
    "vespercode.governance.disclosure_scope",
    "vespercode.governance.disclosure_subject",
    "vespercode.governance.policy",
    "vespercode.governance.request_sources",
    "vespercode.governance.writeback_approval",
    "vespercode.governance.writeback_decision",
    "vespercode.governance.writeback_subject",
    "vespercode.profiles.editable",
    "vespercode.profiles.endpoints",
    "vespercode.profiles.llm",
    "vespercode.profiles.registry",
    "vespercode.storage.connection",
    "vespercode.storage.idempotency",
    "vespercode.storage.run_repository",
    "vespercode.web.app",
    "vespercode.web.security",
    "vespercode.web.local_composition",
    "vespercode.web.routes_audit",
    "vespercode.web.routes_credentials",
    "vespercode.web.routes_disclosure",
    "vespercode.web.routes_memory",
    "vespercode.web.routes_operations",
    "vespercode.web.routes_recovery",
    "vespercode.web.routes_runs",
    "vespercode.web.routes_writeback",
    "vespercode.web.disclosure_workflow",
    "vespercode.web.writeback_workflow",
    "vespercode.web.run_lifecycle_workflow",
    "vespercode.web.run_workflows",
)

# The v1 demo application is also out of bounds for v2 decisions.
_V1_AUTHORITY_MODULES += ("vespercode.demo.app",)


class B3V1SeparationTests(unittest.TestCase):
    def test_b3_modules_exist(self) -> None:
        for relative in _B3_MODULES:
            self.assertTrue(
                (_SRC_ROOT / relative).is_file(),
                f"missing B3 module: {relative}",
            )

    def test_b3_modules_do_not_import_v1_authority(self) -> None:
        pattern = "|".join(re.escape(module) for module in _V1_AUTHORITY_MODULES)
        import_line = re.compile(rf"^\s*(?:from|import)\s+({pattern})\b", re.MULTILINE)
        for relative in _B3_MODULES:
            source = (_SRC_ROOT / relative).read_text(encoding="utf-8")
            match = import_line.search(source)
            self.assertIsNone(
                match,
                f"{relative} imports v1 authority module: "
                f"{match.group(1) if match else ''}",
            )

    def test_b3_modules_derive_no_digest_identity(self) -> None:
        digest_import = re.compile(r"^\s*(?:from|import)\s+hashlib\b", re.MULTILINE)
        for relative in _B3_MODULES:
            source = (_SRC_ROOT / relative).read_text(encoding="utf-8")
            self.assertIsNone(
                digest_import.search(source),
                f"{relative} imports hashlib; v2 integration identity "
                "must not be digest-derived",
            )

    def test_b3_modules_are_standard_library_and_v2_only(self) -> None:
        third_party = re.compile(
            r"^\s*(?:from|import)\s+(pydantic|fastapi|uvicorn|httpx|jinja2|docker)\b",
            re.MULTILINE,
        )
        for relative in _B3_MODULES:
            source = (_SRC_ROOT / relative).read_text(encoding="utf-8")
            self.assertIsNone(
                third_party.search(source),
                f"{relative} imports a third-party package; the v2 local "
                "integration layer is standard-library only",
            )


if __name__ == "__main__":
    unittest.main()

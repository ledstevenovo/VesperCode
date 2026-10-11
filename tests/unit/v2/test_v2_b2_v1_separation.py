"""Route B / B2 (+ B4b-02C1): v1 digest authority and digest identity
stay out of the v2 disclosure/provider/credential plane.

The v1 disclosure/provider/credential modules (the digest-bound grant
ledger, the pydantic credential port, the v1 endpoint manifests) remain
in the repository as read-only legacy, but no v2 authorization decision
may flow through them.  This guard pins that boundary statically: the
Route B2 production modules must not import any v1 digest-bound module,
and — per the Route B2 constraint — must not import hashlib or derive
any digest-based identity at all.  It reads sources only; no v1 code is
imported in the v2 test process.

B4b-02C1 extends the guarded plane with the two production edges the
C1 slice adds behind the same ports: the OS credential adapter
(``credentials/v2_os_store.py``) and the real provider transport
adapter (``providers/v2_transport.py``).  Their optional third-party
imports (the Windows Credential Manager API, httpx) stay function-local
and lazy — pinned separately by each module's own import-isolation
tests — and neither module gains a socket, subprocess, or v1 authority
edge here.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[3]
_SRC_ROOT = _REPO_ROOT / "src" / "vespercode"

_B2_MODULES = (
    "credentials/v2_os_store.py",
    "credentials/v2_port.py",
    "governance/v2_disclosure.py",
    "profiles/v2_endpoints.py",
    "providers/v2_call.py",
    "providers/v2_transport.py",
)

# The v1 disclosure/provider/credential authority modules.  None of these
# may be imported by a B2 module for an identity or authorization
# decision.
_V1_AUTHORITY_MODULES = (
    "vespercode.canonical.digest",
    "vespercode.canonical.json_v1",
    "vespercode.canonical.path_v1",
    "vespercode.canonical.timestamp_v1",
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
    "vespercode.governance.request_sources",
    "vespercode.profiles.editable",
    "vespercode.profiles.endpoints",
    "vespercode.profiles.llm",
    "vespercode.profiles.registry",
    "vespercode.storage.connection",
    "vespercode.storage.idempotency",
)


class B2V1SeparationTests(unittest.TestCase):
    def test_b2_modules_exist(self) -> None:
        for relative in _B2_MODULES:
            self.assertTrue(
                (_SRC_ROOT / relative).is_file(),
                f"missing B2 module: {relative}",
            )

    def test_b2_modules_do_not_import_v1_authority(self) -> None:
        pattern = "|".join(re.escape(module) for module in _V1_AUTHORITY_MODULES)
        import_line = re.compile(rf"^\s*(?:from|import)\s+({pattern})\b", re.MULTILINE)
        for relative in _B2_MODULES:
            source = (_SRC_ROOT / relative).read_text(encoding="utf-8")
            match = import_line.search(source)
            self.assertIsNone(
                match,
                f"{relative} imports v1 authority module: "
                f"{match.group(1) if match else ''}",
            )

    def test_b2_modules_derive_no_digest_identity(self) -> None:
        digest_import = re.compile(r"^\s*(?:from|import)\s+hashlib\b", re.MULTILINE)
        for relative in _B2_MODULES:
            source = (_SRC_ROOT / relative).read_text(encoding="utf-8")
            self.assertIsNone(
                digest_import.search(source),
                f"{relative} imports hashlib; v2 authorization identity "
                "must not be digest-derived",
            )


if __name__ == "__main__":
    unittest.main()

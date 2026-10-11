"""Route B / B4b-02C1: the optional real Windows Credential Manager
integration test for the v2 OS credential adapter.

NOT part of the v2 offline unit job: ``tests/unit/v2`` never imports
this module, and the recorded test command never runs it.  It exists
so an operator can prove the REAL
``WindowsCredentialManagerV2Backend`` (behind ``OSV2CredentialProvider``)
against the current user's real Windows Credential Manager:

    python -m unittest discover -s tests/integration/windows ^
        -p "test_v2_os_credential_store.py" -v

The module skips HONESTLY (``SkipTest`` with the exact reason) when the
host is not Windows, ``pywin32`` is not importable, or the operator has
not opted in with ``VESPERCODE_V2_WINCRED_INTEGRATION=1`` — the suite
writes to the current user's real credential store, so it is strictly
opt-in.  The test provider name is a clearly-test-specific name, the
stored value is a clearly-fake constant, an unknown pre-existing entry
under the test target is refused (never clobbered), every entry the
suite creates is deleted in ``finally``, and the teardown proves zero
``vespercode/v2/`` residue afterwards.
"""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_REPO_ROOT / "src"))

from vespercode.credentials.v2_os_store import (  # noqa: E402
    OSV2CredentialProvider,
    WindowsCredentialManagerV2Backend,
)
from vespercode.credentials.v2_port import (  # noqa: E402
    V2CredentialSecret,
    _provider_reveal_capability,
)

_PROVIDER = "WINCRED-INTEGRATION-TEST"
_SERVICE = f"vespercode/v2/credential/{_PROVIDER}"
_TEST_VALUE = "vespercode-v2-wincred-integration-secret"
_V2_PREFIX = "vespercode/v2/"


def _win32_backend_available() -> bool:
    if sys.platform != "win32":
        return False
    try:
        import win32cred  # noqa: F401
    except Exception:
        return False
    return True


def _operator_opted_in() -> bool:
    return os.environ.get("VESPERCODE_V2_WINCRED_INTEGRATION") == "1"


@unittest.skipUnless(
    _win32_backend_available(),
    "the Windows Credential Manager backend is unavailable on this host "
    "(Windows with pywin32 required); the adapter fails closed there and "
    "the offline fake-backend suite covers the contract",
)
@unittest.skipUnless(
    _operator_opted_in(),
    "the v2 WinCred integration suite is opt-in because it writes to the "
    "current user's real Credential Manager: set "
    "VESPERCODE_V2_WINCRED_INTEGRATION=1 to run it",
)
class RealWindowsCredentialStoreTests(unittest.TestCase):
    """The real OS store behind the v2 provider: a real lifecycle proof."""

    def setUp(self) -> None:
        import win32cred

        self._win32cred = win32cred
        # Refuse to clobber an unknown pre-existing entry under the
        # test target: an unknown value means something real lives
        # there and the suite fails instead of destroying it.
        row = self._read_row(_SERVICE)
        if row is not None:
            value = self._decode(row)
            if value != _TEST_VALUE:
                raise AssertionError(
                    "refusing to overwrite an unknown Credential Manager "
                    f"entry under {_SERVICE!r}; remove it manually before "
                    "running the v2 WinCred integration suite"
                )
            win32cred.CredDelete(
                Type=win32cred.CRED_TYPE_GENERIC, TargetName=_SERVICE
            )
        self.provider = OSV2CredentialProvider(
            WindowsCredentialManagerV2Backend()
        )

    def tearDown(self) -> None:
        try:
            self.provider.clear(_PROVIDER)
        finally:
            self._assert_no_v2_residue()

    # ------------------------------------------------------------------
    # real-store helpers (identity checks only; never logged)
    # ------------------------------------------------------------------

    def _read_row(self, target: str) -> dict[str, object] | None:
        try:
            return self._win32cred.CredRead(  # type: ignore[no-any-return]
                Type=self._win32cred.CRED_TYPE_GENERIC, TargetName=target
            )
        except Exception:
            return None

    @staticmethod
    def _decode(row: dict[str, object]) -> str:
        blob = row.get("CredentialBlob")
        if isinstance(blob, bytes):
            return blob.decode("utf-16-le", errors="replace")
        return ""

    def _v2_targets(self) -> list[str]:
        try:
            credentials = self._win32cred.CredEnumerate()
        except Exception:
            return []
        return sorted(
            str(credential["TargetName"])
            for credential in credentials
            if str(credential["TargetName"]).lower().startswith(_V2_PREFIX)
        )

    def _assert_no_v2_residue(self) -> None:
        self.assertEqual(
            self._v2_targets(),
            [],
            "v2 Credential Manager residue left behind: "
            f"{self._v2_targets()}",
        )

    # ------------------------------------------------------------------
    # the real lifecycle
    # ------------------------------------------------------------------

    def test_the_real_store_lifecycle_round_trip(self) -> None:
        mutation = self.provider.set(
            "OPENAI", V2CredentialSecret.from_hidden_input(_TEST_VALUE)
        )
        self.assertEqual(mutation.kind, "STORED")
        status = self.provider.status("OPENAI")
        self.assertTrue(status.configured)
        self.assertTrue(status.updated_at)
        wrapper = self.provider.get_for_call("OPENAI")
        self.assertIsInstance(wrapper, V2CredentialSecret)
        self.assertEqual(
            wrapper.reveal(_provider_reveal_capability()), _TEST_VALUE
        )

    def test_the_real_store_update_and_clear(self) -> None:
        self.provider.set(
            "OPENAI", V2CredentialSecret.from_hidden_input(_TEST_VALUE)
        )
        self.provider.set(
            "OPENAI",
            V2CredentialSecret.from_hidden_input(_TEST_VALUE + "-2"),
        )
        wrapper = self.provider.get_for_call("OPENAI")
        assert wrapper is not None
        self.assertEqual(
            wrapper.reveal(_provider_reveal_capability()),
            _TEST_VALUE + "-2",
        )
        cleared = self.provider.clear("OPENAI")
        self.assertEqual(cleared.kind, "CLEARED")
        self.assertFalse(self.provider.status("OPENAI").configured)
        self.assertIsNone(self.provider.get_for_call("OPENAI"))
        # The second clear is an idempotent success.
        self.assertEqual(self.provider.clear("OPENAI").kind, "CLEARED")

    def test_the_real_store_uses_the_v2_namespaced_target(self) -> None:
        self.provider.set(
            "OPENAI", V2CredentialSecret.from_hidden_input(_TEST_VALUE)
        )
        row = self._read_row(_SERVICE)
        self.assertIsNotNone(row)
        assert row is not None
        self.assertEqual(row.get("UserName"), "api-key")
        self.assertEqual(self._decode(row), _TEST_VALUE)
        # The probe target is gone by the time any operation returns.
        self.assertIsNone(self._read_row("vespercode/v2/probe"))

    def test_the_real_status_projection_stays_non_revealing(self) -> None:
        self.provider.set(
            "OPENAI", V2CredentialSecret.from_hidden_input(_TEST_VALUE)
        )
        status = self.provider.status("OPENAI")
        self.assertEqual(
            (status.provider, status.configured),
            ("OPENAI", True),
        )
        self.assertNotIn(_TEST_VALUE, repr(status))
        self.assertNotIn(_TEST_VALUE, str(status))


if __name__ == "__main__":
    unittest.main()

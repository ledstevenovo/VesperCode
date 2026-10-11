"""Route B / B4b-02C1: the production OS credential adapter behind the v2 port.

The v1 credential plane (``credentials/port.py``,
``credentials/service.py``, ``credentials/wincred_store.py``) is
pydantic-bound, closed to the single ``OPENAI`` provider, and backed by
the verified Windows Credential Manager; it remains untouched
read-only legacy and nothing here imports it or reuses it as the v2
authority.

The v2 OS credential adapter is the production implementation of the
B2 ``V2CredentialProviderPort`` over the target platform's secure OS
credential store.  Its pieces:

- an injectable OS backend port (``V2OSCredentialBackendPort``) whose
  real implementation is the Windows Credential Manager backend
  (``WindowsCredentialManagerV2Backend``) with lazy, function-local
  ``win32cred``/``pywintypes`` imports — the module itself imports
  nothing platform-specific at module scope, so it loads on any host;
- fail-closed safety: every operation first proves the backend
  (identity in the closed backend-id set plus a real write/read/delete
  capability cycle of the backend's own probe target), an unavailable
  or unsafe backend raises the closed ``V2OSCredentialStoreError``
  with a static message — never a fallback backend, never a secret,
  never a length, never a derivative;
- the v2 namespaced targets ``vespercode/v2/credential/<provider>``
  under the current user's store are disjoint from the probe target
  ``vespercode/v2/probe`` by construction (the provider grammar
  excludes ``/``), so no provider name can alias the probe or another
  service;
- ``set`` stores through the storage-reveal seam (the raw value
  exists only between the capability-gated extraction and the backend
  write), re-verifies the backend after the write, and retains
  nothing; ``get_for_call`` re-probes and reads fresh (no cache);
  ``status`` reads metadata only (the stored value is never decoded
  on the status path) and reports provider/configured/update-time
  only; ``clear`` deletes idempotently.

The unit tests below run the adapter over a deterministic fake backend
(the offline contract); the real backend is exercised only by the
opt-in Windows integration suite
(``tests/integration/windows/test_v2_os_credential_store.py``),
which skips honestly when Windows, pywin32, or the operator opt-in is
missing.  No network, shell, Docker, or file credential store exists
on this path.
"""

from __future__ import annotations

import ast
import sys
import unittest
from dataclasses import fields
from pathlib import Path

from vespercode.credentials.v2_os_store import (
    OS_CREDENTIAL_STORE_ERROR_CODES_V2,
    OSV2CredentialProvider,
    V2OSCredentialBackendPort,
    V2OSCredentialStoreError,
    WindowsCredentialManagerV2Backend,
    default_v2_os_credential_backend,
)
from vespercode.credentials.v2_port import (
    V2CredentialError,
    V2CredentialMutation,
    V2CredentialProviderPort,
    V2CredentialSecret,
    V2CredentialStatus,
    _provider_reveal_capability,
)

_REPO_ROOT = Path(__file__).resolve().parents[3]
_SRC_ROOT = _REPO_ROOT / "src" / "vespercode"
_SECRET = "v2-os-store-test-secret-0001"
_OPENAI_SERVICE = "vespercode/v2/credential/OPENAI"
_PROBE_SERVICE = "vespercode/v2/probe"


class FakeOSBackend:
    """Deterministic simulation of the OS credential store (test double).

    Models the semantics the provider relies on: every operation is
    gated by the same closed errors the real backend raises, the probe
    cycle writes/reads/deletes its own probe target without polluting
    the credential-operation counters, metadata reads never decode the
    stored value, and an identity mismatch fails closed.
    """

    def __init__(
        self,
        *,
        probe_failure: str | None = None,
        unavailable: bool = False,
        backend_id_value: str = "WINDOWS_CREDENTIAL_MANAGER",
    ) -> None:
        self.entries: dict[str, tuple[str, str, int]] = {}
        self.probe_calls = 0
        self.write_calls: list[tuple[str, str]] = []
        self.metadata_reads = 0
        self.value_reads = 0
        self.deletes: list[str] = []
        self._probe_failure = probe_failure
        self._unavailable = unavailable
        self._backend_id = backend_id_value
        self._clock_ms = 1_700_000_000_000

    def _gate(self) -> None:
        if self._unavailable:
            raise V2OSCredentialStoreError("CREDENTIAL_BACKEND_UNAVAILABLE")
        if self._probe_failure == "UNSAFE":
            raise V2OSCredentialStoreError("CREDENTIAL_BACKEND_UNSAFE")

    def backend_id(self) -> str:
        if self._unavailable:
            raise V2OSCredentialStoreError("CREDENTIAL_BACKEND_UNAVAILABLE")
        return self._backend_id

    def probe_cycle(self) -> None:
        self._gate()
        self.entries[_PROBE_SERVICE] = (
            "capability-probe",
            "vespercode-v2-probe",
            self._clock_ms,
        )
        healthy = self.entries[_PROBE_SERVICE][1] == "vespercode-v2-probe"
        self.entries.pop(_PROBE_SERVICE, None)
        self.probe_calls += 1
        if not healthy:
            raise V2OSCredentialStoreError("CREDENTIAL_BACKEND_UNSAFE")

    def write(self, service: str, username: str, secret: str) -> None:
        self._gate()
        self._clock_ms += 1_000
        self.entries[service] = (username, secret, self._clock_ms)
        self.write_calls.append((service, username))

    def read_metadata(self, service: str, username: str) -> int | None:
        self._gate()
        self.metadata_reads += 1
        entry = self.entries.get(service)
        if entry is None:
            return None
        stored_username, _, last_written_ms = entry
        if stored_username != username:
            raise V2OSCredentialStoreError("CREDENTIAL_STORE_FAILED")
        return last_written_ms

    def read_value(self, service: str, username: str) -> str | None:
        self._gate()
        self.value_reads += 1
        entry = self.entries.get(service)
        if entry is None:
            return None
        stored_username, value, _ = entry
        if stored_username != username:
            raise V2OSCredentialStoreError("CREDENTIAL_STORE_FAILED")
        if not isinstance(value, str):
            # A malformed stored value fails closed, exactly like the
            # real backend's undecodable blob.
            raise V2OSCredentialStoreError("CREDENTIAL_STORE_FAILED")
        return value

    def delete(self, service: str) -> None:
        self._gate()
        self.deletes.append(service)
        self.entries.pop(service, None)


class OSV2CredentialProviderContractTests(unittest.TestCase):
    def test_the_provider_implements_the_v2_credential_port(self) -> None:
        provider = OSV2CredentialProvider(FakeOSBackend())
        self.assertIsInstance(provider, V2CredentialProviderPort)

    def test_a_non_conforming_backend_rejects_at_construction(self) -> None:
        class _NotABackend:
            pass

        for backend in (_NotABackend(), "not-a-backend"):
            with self.subTest(backend=backend):
                with self.assertRaises(V2CredentialError):
                    OSV2CredentialProvider(backend)  # type: ignore[arg-type]


class OSV2CredentialProviderTests(unittest.TestCase):
    def setUp(self) -> None:
        self.backend = FakeOSBackend()
        self.provider = OSV2CredentialProvider(self.backend)

    def test_set_status_get_for_call_clear_round_trip(self) -> None:
        mutation = self.provider.set(
            "OPENAI", V2CredentialSecret.from_hidden_input(_SECRET)
        )
        self.assertEqual(mutation, V2CredentialMutation("STORED", "OPENAI"))
        self.assertEqual(
            self.backend.write_calls, [(_OPENAI_SERVICE, "api-key")]
        )
        status = self.provider.status("OPENAI")
        self.assertEqual(status.provider, "OPENAI")
        self.assertTrue(status.configured)
        self.assertIsInstance(status.updated_at, str)
        self.assertTrue(status.updated_at)
        wrapper = self.provider.get_for_call("OPENAI")
        self.assertIsInstance(wrapper, V2CredentialSecret)
        self.assertEqual(wrapper.reveal(_provider_reveal_capability()), _SECRET)
        cleared = self.provider.clear("OPENAI")
        self.assertEqual(cleared, V2CredentialMutation("CLEARED", "OPENAI"))
        self.assertIsNone(self.provider.get_for_call("OPENAI"))
        after = self.provider.status("OPENAI")
        self.assertFalse(after.configured)
        self.assertIsNone(after.updated_at)

    def test_set_updates_an_existing_credential_in_place(self) -> None:
        self.provider.set(
            "OPENAI", V2CredentialSecret.from_hidden_input("first-secret")
        )
        first = self.provider.status("OPENAI")
        self.provider.set(
            "OPENAI", V2CredentialSecret.from_hidden_input("second-secret")
        )
        second = self.provider.status("OPENAI")
        self.assertTrue(second.configured)
        self.assertNotEqual(first.updated_at, second.updated_at)
        wrapper = self.provider.get_for_call("OPENAI")
        assert wrapper is not None
        self.assertEqual(
            wrapper.reveal(_provider_reveal_capability()), "second-secret"
        )

    def test_a_missing_credential_is_none_without_error(self) -> None:
        self.assertIsNone(self.provider.get_for_call("OPENAI"))
        status = self.provider.status("OPENAI")
        self.assertEqual(
            status,
            V2CredentialStatus(provider="OPENAI", configured=False, updated_at=None),
        )

    def test_clear_is_idempotent(self) -> None:
        self.provider.set(
            "OPENAI", V2CredentialSecret.from_hidden_input(_SECRET)
        )
        self.provider.clear("OPENAI")
        deletes = len(self.backend.deletes)
        second = self.provider.clear("OPENAI")
        self.assertEqual(second, V2CredentialMutation("CLEARED", "OPENAI"))
        self.assertEqual(len(self.backend.deletes), deletes)

    def test_set_validates_the_provider_name_and_secret_wrapper(self) -> None:
        with self.assertRaises(V2CredentialError):
            self.provider.set(
                "not a provider!",  # type: ignore[arg-type]
                V2CredentialSecret.from_hidden_input(_SECRET),
            )
        with self.assertRaises(V2CredentialError):
            self.provider.set("OPENAI", "raw-secret")  # type: ignore[arg-type]
        self.assertEqual(self.backend.write_calls, [])
        self.assertEqual(self.backend.probe_calls, 0)

    def test_status_reads_metadata_only_never_the_stored_value(self) -> None:
        self.provider.set(
            "OPENAI", V2CredentialSecret.from_hidden_input(_SECRET)
        )
        self.backend.value_reads = 0
        self.backend.metadata_reads = 0
        status = self.provider.status("OPENAI")
        self.assertTrue(status.configured)
        self.assertEqual(self.backend.metadata_reads, 1)
        self.assertEqual(self.backend.value_reads, 0)
        self.assertNotIn(_SECRET, repr(status))
        self.assertNotIn(_SECRET, str(status))

    def test_the_status_projection_is_the_closed_shape(self) -> None:
        self.provider.set(
            "OPENAI", V2CredentialSecret.from_hidden_input(_SECRET)
        )
        status = self.provider.status("OPENAI")
        self.assertEqual(
            {field.name for field in fields(V2CredentialStatus)},
            {"provider", "configured", "updated_at"},
        )
        for name in ("provider", "configured", "updated_at"):
            self.assertNotIn(_SECRET, str(getattr(status, name)), name)

    def test_every_operation_proves_the_backend_first(self) -> None:
        self.provider.set(
            "OPENAI", V2CredentialSecret.from_hidden_input(_SECRET)
        )
        before = self.backend.probe_calls
        self.provider.status("OPENAI")
        self.provider.get_for_call("OPENAI")
        self.provider.clear("OPENAI")
        self.provider.set(
            "OPENAI", V2CredentialSecret.from_hidden_input(_SECRET)
        )
        # set probes before AND after the write; the others probe once each.
        self.assertEqual(self.backend.probe_calls, before + 5)

    def test_an_unsafe_backend_fails_closed_on_every_operation(self) -> None:
        backend = FakeOSBackend(probe_failure="UNSAFE")
        provider = OSV2CredentialProvider(backend)
        operations = (
            lambda: provider.set(
                "OPENAI", V2CredentialSecret.from_hidden_input(_SECRET)
            ),
            lambda: provider.get_for_call("OPENAI"),
            lambda: provider.status("OPENAI"),
            lambda: provider.clear("OPENAI"),
        )
        for operation in operations:
            with self.subTest(operation=operation):
                with self.assertRaises(V2OSCredentialStoreError) as caught:
                    operation()
                self.assertEqual(
                    caught.exception.code, "CREDENTIAL_BACKEND_UNSAFE"
                )
                self.assertNotIn(_SECRET, str(caught.exception))
                self.assertNotIn(_SECRET, repr(caught.exception))
        self.assertEqual(backend.write_calls, [])
        self.assertEqual(backend.entries, {})

    def test_an_unavailable_backend_fails_closed_on_every_operation(self) -> None:
        backend = FakeOSBackend(unavailable=True)
        provider = OSV2CredentialProvider(backend)
        operations = (
            lambda: provider.set(
                "OPENAI", V2CredentialSecret.from_hidden_input(_SECRET)
            ),
            lambda: provider.get_for_call("OPENAI"),
            lambda: provider.status("OPENAI"),
            lambda: provider.clear("OPENAI"),
        )
        for operation in operations:
            with self.subTest(operation=operation):
                with self.assertRaises(V2OSCredentialStoreError) as caught:
                    operation()
                self.assertEqual(
                    caught.exception.code, "CREDENTIAL_BACKEND_UNAVAILABLE"
                )
                self.assertNotIn(_SECRET, str(caught.exception))
        self.assertEqual(backend.write_calls, [])
        self.assertEqual(backend.entries, {})

    def test_an_unknown_backend_identity_is_unsafe(self) -> None:
        backend = FakeOSBackend(backend_id_value="SOME_FILE_STORE")
        provider = OSV2CredentialProvider(backend)
        with self.assertRaises(V2OSCredentialStoreError) as caught:
            provider.status("OPENAI")
        self.assertEqual(caught.exception.code, "CREDENTIAL_BACKEND_UNSAFE")
        # the identity check happens before any capability probe.
        self.assertEqual(backend.probe_calls, 0)

    def test_a_malformed_stored_value_fails_closed(self) -> None:
        self.provider.set(
            "OPENAI", V2CredentialSecret.from_hidden_input(_SECRET)
        )
        for hostile_value in ("", 12345, None):
            with self.subTest(hostile_value=hostile_value):
                self.backend.entries[_OPENAI_SERVICE] = (
                    "api-key",
                    hostile_value,  # type: ignore[arg-type]
                    12345,
                )
                with self.assertRaises(V2OSCredentialStoreError) as caught:
                    self.provider.get_for_call("OPENAI")
                self.assertEqual(
                    caught.exception.code, "CREDENTIAL_STORE_FAILED"
                )

    def test_a_foreign_entry_identity_fails_closed(self) -> None:
        self.backend.entries[_OPENAI_SERVICE] = (
            "someone-else",
            "their-value",
            12345,
        )
        for operation in (
            lambda: self.provider.get_for_call("OPENAI"),
            lambda: self.provider.status("OPENAI"),
        ):
            with self.subTest(operation=operation):
                with self.assertRaises(V2OSCredentialStoreError) as caught:
                    operation()
                self.assertEqual(
                    caught.exception.code, "CREDENTIAL_STORE_FAILED"
                )
                self.assertNotIn("their-value", str(caught.exception))

    def test_the_credential_service_name_is_disjoint_from_the_probe_service(
        self,
    ) -> None:
        self.provider.set(
            "probe", V2CredentialSecret.from_hidden_input(_SECRET)
        )
        services = {service for service, _ in self.backend.write_calls}
        self.assertIn("vespercode/v2/credential/probe", services)
        self.assertNotIn(_PROBE_SERVICE, services)
        for service in services:
            self.assertTrue(service.startswith("vespercode/v2/credential/"))

    def test_the_probe_leaves_no_residue(self) -> None:
        self.provider.set(
            "OPENAI", V2CredentialSecret.from_hidden_input(_SECRET)
        )
        self.assertEqual(set(self.backend.entries), {_OPENAI_SERVICE})
        self.provider.clear("OPENAI")
        self.assertEqual(self.backend.entries, {})

    def test_the_provider_holds_no_secret_state(self) -> None:
        self.provider.set(
            "OPENAI", V2CredentialSecret.from_hidden_input(_SECRET)
        )
        self.provider.get_for_call("OPENAI")
        for name in dir(self.provider):
            if name.startswith("__"):
                continue
            attribute = getattr(self.provider, name, None)
            if isinstance(attribute, str):
                self.assertNotIn(_SECRET, attribute, name)
        self.assertNotIn(_SECRET, repr(self.provider))

    def test_the_closed_error_vocabulary_is_pinned(self) -> None:
        self.assertEqual(
            OS_CREDENTIAL_STORE_ERROR_CODES_V2,
            frozenset(
                {
                    "CREDENTIAL_BACKEND_UNAVAILABLE",
                    "CREDENTIAL_BACKEND_UNSAFE",
                    "CREDENTIAL_STORE_FAILED",
                }
            ),
        )
        for code in OS_CREDENTIAL_STORE_ERROR_CODES_V2:
            with self.subTest(code=code):
                error = V2OSCredentialStoreError(code)
                self.assertEqual(error.code, code)
                self.assertTrue(str(error))
                self.assertLessEqual(len(str(error)), 120)
        with self.assertRaises(ValueError):
            V2OSCredentialStoreError("NOT_A_CLOSED_CODE")


class PlatformDefaultBackendTests(unittest.TestCase):
    def test_the_platform_default_backend_is_closed(self) -> None:
        backend = default_v2_os_credential_backend()
        if sys.platform == "win32":
            self.assertIsInstance(backend, WindowsCredentialManagerV2Backend)
            self.assertEqual(backend.backend_id(), "WINDOWS_CREDENTIAL_MANAGER")
        else:
            self.assertNotIsInstance(backend, WindowsCredentialManagerV2Backend)
            with self.assertRaises(V2OSCredentialStoreError) as caught:
                backend.backend_id()
            self.assertEqual(
                caught.exception.code, "CREDENTIAL_BACKEND_UNAVAILABLE"
            )

    def test_the_backend_port_is_runtime_checkable(self) -> None:
        self.assertIsInstance(FakeOSBackend(), V2OSCredentialBackendPort)


def _module_level_import_names(relative: str) -> set[str]:
    tree = ast.parse((_SRC_ROOT / relative).read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in tree.body:
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            names.add(node.module or "")
    return names


def _all_import_names(relative: str) -> set[str]:
    tree = ast.parse((_SRC_ROOT / relative).read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            names.add(node.module or "")
    return names


class ImportIsolationTests(unittest.TestCase):
    def test_platform_libraries_never_import_at_module_scope(self) -> None:
        module_level = _module_level_import_names("credentials/v2_os_store.py")
        for forbidden in ("win32cred", "pywintypes", "keyring"):
            self.assertNotIn(forbidden, module_level)
        # The real Windows backend still reaches them — lazily, inside
        # function bodies, so importing the adapter never loads a
        # platform library on any host.
        all_imports = _all_import_names("credentials/v2_os_store.py")
        self.assertIn("win32cred", all_imports)
        self.assertIn("pywintypes", all_imports)

    def test_the_os_store_never_imports_sockets_subprocess_or_v1_credentials(
        self,
    ) -> None:
        all_imports = _all_import_names("credentials/v2_os_store.py")
        for forbidden in ("socket", "subprocess", "os"):
            self.assertNotIn(forbidden, all_imports)
        for forbidden in (
            "vespercode.credentials.port",
            "vespercode.credentials.service",
            "vespercode.credentials.wincred_store",
        ):
            self.assertNotIn(forbidden, all_imports)


if __name__ == "__main__":
    unittest.main()

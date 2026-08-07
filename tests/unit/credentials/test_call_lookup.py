"""T27.1 legacy step 27.A: fresh per-call get-for-call lookup tests.

SPEC §4.8 behavior 6: ``get_for_call("OPENAI")`` re-verifies the actual
backend and reads the current entry on every call — it never reuses a
startup/PREFLIGHT "configured" state, caches a secret, or skips the
backend probe.  Missing and cleared entries fail closed with
``CREDENTIAL_MISSING`` before any caller-visible side effect.
"""

from __future__ import annotations

import pytest

# The credential contracts are pydantic runtime contracts; the hash-locked
# gate toolchain does not install runtime dependencies, so this module skips
# cleanly there instead of failing at collection (formal env runs it fully).
pytest.importorskip("pydantic")

from vespercode.canonical.timestamp_v1 import CanonicalTimestampV1
from vespercode.contracts.optional import AbsentV1, PresentV1
from vespercode.credentials.port import (
    CredentialBackendProbeV1,
    CredentialBackendUnsafeError,
    CredentialErrorV1,
    CredentialMissingV1,
    CredentialProviderClosedError,
    CredentialStatusV1,
    CredentialStoreFailedError,
    CredentialStoreMutationV1,
    SecretCredentialV1,
)
from vespercode.credentials.service import CredentialService


class _FakeCredentialStore:
    """In-memory store with per-call probe/read counters and failure knobs."""

    def __init__(self, *, fail_read: bool = False) -> None:
        self.fail_read = fail_read
        self.probe_calls = 0
        self.read_calls = 0
        self.probe_safe = True
        self._stored: str | None = None

    def probe_backend(self) -> CredentialBackendProbeV1:
        self.probe_calls += 1
        if not self.probe_safe:
            raise CredentialBackendUnsafeError(
                "credential backend is not Windows Credential Manager"
            )
        return CredentialBackendProbeV1(
            schema_version=1,
            backend_id="WINDOWS_CREDENTIAL_MANAGER",
            capability="READ_WRITE_DELETE",
        )

    def _guard(self, provider: object) -> None:
        if provider != "OPENAI":
            raise CredentialProviderClosedError(
                "credential provider is closed to OPENAI"
            )

    def set(
        self, provider: str, secret: SecretCredentialV1
    ) -> CredentialStoreMutationV1:
        self._guard(provider)
        self._stored = secret.reveal()
        return CredentialStoreMutationV1(schema_version=1, kind="STORED")

    def get_for_call(self, provider: str) -> SecretCredentialV1 | CredentialMissingV1:
        self._guard(provider)
        self.read_calls += 1
        if self.fail_read:
            raise CredentialStoreFailedError("credential store read failed")
        if self._stored is None:
            return CredentialMissingV1(schema_version=1, kind="MISSING")
        return SecretCredentialV1.from_hidden_input(self._stored)

    def status(self, provider: str) -> CredentialStatusV1:
        self._guard(provider)
        if self._stored is None:
            return CredentialStatusV1(
                schema_version=1,
                provider="OPENAI",
                configured=False,
                updated_at=AbsentV1(kind="ABSENT"),
            )
        return CredentialStatusV1(
            schema_version=1,
            provider="OPENAI",
            configured=True,
            updated_at=PresentV1[CanonicalTimestampV1](
                kind="PRESENT", value=CanonicalTimestampV1("2026-08-05T13:03:46.753Z")
            ),
        )

    def clear(self, provider: str) -> CredentialStoreMutationV1:
        self._guard(provider)
        self._stored = None
        return CredentialStoreMutationV1(schema_version=1, kind="CLEARED")


def test_get_for_call_reads_fresh_every_time() -> None:
    store = _FakeCredentialStore()
    service = CredentialService(store)
    service.set("OPENAI", SecretCredentialV1.from_hidden_input("inert-sentinel-value"))
    first = service.get_for_call("OPENAI")
    second = service.get_for_call("OPENAI")
    assert isinstance(first, SecretCredentialV1)
    assert isinstance(second, SecretCredentialV1)
    assert first.reveal() == second.reveal() == "inert-sentinel-value"
    # The set probed once; each call re-probed and re-read — no caching.
    assert store.probe_calls == 3
    assert store.read_calls == 2


def test_get_for_call_reprobes_before_every_read() -> None:
    store = _FakeCredentialStore()
    service = CredentialService(store)
    service.set("OPENAI", SecretCredentialV1.from_hidden_input("inert-sentinel-value"))
    assert isinstance(service.get_for_call("OPENAI"), SecretCredentialV1)
    store.probe_safe = False  # the backend degrades after the first successful read
    error = service.get_for_call("OPENAI")
    assert isinstance(error, CredentialErrorV1)
    assert error.error_code == "CREDENTIAL_BACKEND_UNSAFE"
    assert store.read_calls == 1  # the unsafe probe blocked the second read


def test_get_for_call_returns_the_current_secret() -> None:
    store = _FakeCredentialStore()
    service = CredentialService(store)
    service.set("OPENAI", SecretCredentialV1.from_hidden_input("first-value"))
    service.update("OPENAI", SecretCredentialV1.from_hidden_input("second-value"))
    got = service.get_for_call("OPENAI")
    assert isinstance(got, SecretCredentialV1)
    assert got.reveal() == "second-value"


def test_get_for_call_after_clear_is_missing() -> None:
    store = _FakeCredentialStore()
    service = CredentialService(store)
    service.set("OPENAI", SecretCredentialV1.from_hidden_input("inert-sentinel-value"))
    service.clear("OPENAI")
    error = service.get_for_call("OPENAI")
    assert isinstance(error, CredentialErrorV1)
    assert error.error_code == "CREDENTIAL_MISSING"


def test_get_for_call_never_reuses_configured_state() -> None:
    store = _FakeCredentialStore()
    service = CredentialService(store)
    service.set("OPENAI", SecretCredentialV1.from_hidden_input("inert-sentinel-value"))
    assert service.status("OPENAI").configured is True
    service.clear("OPENAI")
    # The earlier "configured" observation must not satisfy a later call.
    error = service.get_for_call("OPENAI")
    assert isinstance(error, CredentialErrorV1)
    assert error.error_code == "CREDENTIAL_MISSING"
    assert store.read_calls == 1


def test_get_for_call_on_fresh_store_is_missing() -> None:
    store = _FakeCredentialStore()
    service = CredentialService(store)
    error = service.get_for_call("OPENAI")
    assert isinstance(error, CredentialErrorV1)
    assert error.error_code == "CREDENTIAL_MISSING"


def test_get_for_call_store_read_failure_is_typed() -> None:
    store = _FakeCredentialStore(fail_read=True)
    service = CredentialService(store)
    error = service.get_for_call("OPENAI")
    assert isinstance(error, CredentialErrorV1)
    assert error.error_code == "CREDENTIAL_STORE_FAILED"

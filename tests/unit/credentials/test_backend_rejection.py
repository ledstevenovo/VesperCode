"""T27.1 legacy step 27.A: unsafe-backend rejection tests.

SPEC §4.8 behavior 3: when the credential backend degrades to anything
other than the verified Windows Credential Manager, every lifecycle
operation must return ``CREDENTIAL_BACKEND_UNSAFE`` and store nothing —
there is no fallback, cache, print, or transport path.
"""

from __future__ import annotations

import pytest

# The credential contracts are pydantic runtime contracts; the hash-locked
# gate toolchain does not install runtime dependencies, so this module skips
# cleanly there instead of failing at collection (formal env runs it fully).
pytest.importorskip("pydantic")

from vespercode.credentials.port import (
    CredentialBackendProbeV1,
    CredentialBackendUnsafeError,
    CredentialErrorV1,
    CredentialMissingV1,
    CredentialStatusV1,
    CredentialStoreMutationV1,
    SecretCredentialV1,
)
from vespercode.credentials.service import CredentialService


class _UnsafeCredentialStore:
    """A store whose backend probe always fails as unsafe.

    Any lifecycle method on this store raises ``AssertionError``: the
    probe must precede the operation, so a safe contract never reaches
    the store at all.
    """

    def __init__(self) -> None:
        self.probe_calls = 0
        self.set_calls = 0
        self.read_calls = 0
        self.clear_calls = 0

    def probe_backend(self) -> CredentialBackendProbeV1:
        self.probe_calls += 1
        raise CredentialBackendUnsafeError(
            "credential backend is not Windows Credential Manager"
        )

    def set(
        self, provider: str, secret: SecretCredentialV1
    ) -> CredentialStoreMutationV1:
        self.set_calls += 1
        raise AssertionError("an unsafe backend must never be written to")

    def get_for_call(self, provider: str) -> SecretCredentialV1 | CredentialMissingV1:
        self.read_calls += 1
        raise AssertionError("an unsafe backend must never be read from")

    def status(self, provider: str) -> CredentialStatusV1:
        raise AssertionError("an unsafe backend must never be queried")

    def clear(self, provider: str) -> CredentialStoreMutationV1:
        self.clear_calls += 1
        raise AssertionError("an unsafe backend must never be cleared")


def _service() -> tuple[_UnsafeCredentialStore, CredentialService]:
    store = _UnsafeCredentialStore()
    return store, CredentialService(store)


def test_set_rejects_unsafe_backend_without_storing() -> None:
    store, service = _service()
    result = service.set(
        "OPENAI", SecretCredentialV1.from_hidden_input("inert-sentinel-value")
    )
    assert result.kind == "FAILED"
    assert result.error.kind == "PRESENT"
    assert result.error.value.error_code == "CREDENTIAL_BACKEND_UNSAFE"
    assert store.set_calls == 0
    assert store.probe_calls == 1


def test_update_rejects_unsafe_backend_without_storing() -> None:
    store, service = _service()
    result = service.update(
        "OPENAI", SecretCredentialV1.from_hidden_input("inert-sentinel-value")
    )
    assert result.kind == "FAILED"
    assert result.error.kind == "PRESENT"
    assert result.error.value.error_code == "CREDENTIAL_BACKEND_UNSAFE"
    assert store.set_calls == 0


def test_clear_rejects_unsafe_backend_without_deleting() -> None:
    store, service = _service()
    result = service.clear("OPENAI")
    assert result.kind == "FAILED"
    assert result.error.kind == "PRESENT"
    assert result.error.value.error_code == "CREDENTIAL_BACKEND_UNSAFE"
    assert store.clear_calls == 0


def test_get_for_call_rejects_unsafe_backend_without_reading() -> None:
    store, service = _service()
    error = service.get_for_call("OPENAI")
    assert isinstance(error, CredentialErrorV1)
    assert error.error_code == "CREDENTIAL_BACKEND_UNSAFE"
    assert store.read_calls == 0


def test_status_raises_on_unsafe_backend() -> None:
    store, service = _service()
    with pytest.raises(CredentialBackendUnsafeError):
        service.status("OPENAI")
    assert store.probe_calls == 1


def test_every_rejection_is_preceded_by_exactly_one_probe() -> None:
    store, service = _service()
    service.set("OPENAI", SecretCredentialV1.from_hidden_input("inert-sentinel-value"))
    service.update(
        "OPENAI", SecretCredentialV1.from_hidden_input("inert-sentinel-value")
    )
    service.clear("OPENAI")
    service.get_for_call("OPENAI")
    with pytest.raises(CredentialBackendUnsafeError):
        service.status("OPENAI")
    assert store.probe_calls == 5
    assert store.set_calls == 0
    assert store.read_calls == 0
    assert store.clear_calls == 0

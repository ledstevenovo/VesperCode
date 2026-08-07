"""T27.1 legacy step 27.A: credential lifecycle service mutation tests.

``CredentialService`` probes the verified store before every lifecycle
operation, stores/overwrites/clears through the injectable port, and maps
backend/store failures into the closed typed-result vocabulary of SPEC
§4.8 (``CREDENTIAL_BACKEND_UNSAFE``, ``CREDENTIAL_STORE_FAILED``,
``CREDENTIAL_CLEAR_FAILED``, ``CREDENTIAL_MISSING``) with bounded
redacted messages.
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
    CredentialClearFailedError,
    CredentialMissingV1,
    CredentialProviderClosedError,
    CredentialSecretInvalidError,
    CredentialStatusV1,
    CredentialStoreFailedError,
    CredentialStoreMutationV1,
    SecretCredentialV1,
)
from vespercode.credentials.service import CredentialService


class _FakeCredentialStore:
    """Minimal in-memory store for service mutation tests."""

    def __init__(self, *, fail_set: bool = False, fail_clear: bool = False) -> None:
        self.fail_set = fail_set
        self.fail_clear = fail_clear
        self.probe_calls = 0
        self.set_calls = 0
        self.clear_calls = 0
        self.events: list[str] = []
        self.stored: str | None = None

    def probe_backend(self) -> CredentialBackendProbeV1:
        self.probe_calls += 1
        self.events.append("probe")
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
        self.set_calls += 1
        self.events.append("set")
        if self.fail_set:
            raise CredentialStoreFailedError("credential store write failed")
        self.stored = secret.reveal()
        return CredentialStoreMutationV1(schema_version=1, kind="STORED")

    def get_for_call(self, provider: str) -> SecretCredentialV1 | CredentialMissingV1:
        self._guard(provider)
        if self.stored is None:
            return CredentialMissingV1(schema_version=1, kind="MISSING")
        return SecretCredentialV1.from_hidden_input(self.stored)

    def status(self, provider: str) -> CredentialStatusV1:
        self._guard(provider)
        if self.stored is None:
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
        self.clear_calls += 1
        self.events.append("clear")
        if self.fail_clear:
            raise CredentialClearFailedError("credential store clear failed")
        self.stored = None
        return CredentialStoreMutationV1(schema_version=1, kind="CLEARED")


def test_set_stores_secret_and_reports_stored() -> None:
    store = _FakeCredentialStore()
    service = CredentialService(store)
    secret = SecretCredentialV1.from_hidden_input("inert-sentinel-value")
    result = service.set("OPENAI", secret)
    assert result.kind == "STORED"
    assert result.error.kind == "ABSENT"
    assert store.stored == "inert-sentinel-value"
    assert store.probe_calls == 1
    assert store.set_calls == 1


def test_set_probes_the_verified_store_before_writing() -> None:
    store = _FakeCredentialStore()
    service = CredentialService(store)
    service.set("OPENAI", SecretCredentialV1.from_hidden_input("inert-sentinel-value"))
    assert store.events == ["probe", "set"]


def test_update_overwrites_the_previous_secret() -> None:
    store = _FakeCredentialStore()
    service = CredentialService(store)
    assert (
        service.set("OPENAI", SecretCredentialV1.from_hidden_input("first-value")).kind
        == "STORED"
    )
    assert (
        service.update(
            "OPENAI", SecretCredentialV1.from_hidden_input("second-value")
        ).kind
        == "STORED"
    )
    assert store.stored == "second-value"
    got = service.get_for_call("OPENAI")
    assert isinstance(got, SecretCredentialV1)
    assert got.reveal() == "second-value"


def test_clear_removes_and_reports_cleared() -> None:
    store = _FakeCredentialStore()
    service = CredentialService(store)
    assert (
        service.set(
            "OPENAI", SecretCredentialV1.from_hidden_input("inert-sentinel-value")
        ).kind
        == "STORED"
    )
    result = service.clear("OPENAI")
    assert result.kind == "CLEARED"
    assert result.error.kind == "ABSENT"
    assert store.stored is None
    assert service.status("OPENAI").configured is False


def test_clear_of_absent_entry_is_cleared() -> None:
    store = _FakeCredentialStore()
    service = CredentialService(store)
    assert service.clear("OPENAI").kind == "CLEARED"


def test_set_store_failure_returns_typed_failed_result() -> None:
    store = _FakeCredentialStore(fail_set=True)
    service = CredentialService(store)
    result = service.set(
        "OPENAI", SecretCredentialV1.from_hidden_input("inert-sentinel-value")
    )
    assert result.kind == "FAILED"
    assert result.error.kind == "PRESENT"
    assert result.error.value.error_code == "CREDENTIAL_STORE_FAILED"
    assert store.stored is None


def test_clear_failure_returns_typed_failed_result() -> None:
    store = _FakeCredentialStore(fail_clear=True)
    service = CredentialService(store)
    result = service.clear("OPENAI")
    assert result.kind == "FAILED"
    assert result.error.kind == "PRESENT"
    assert result.error.value.error_code == "CREDENTIAL_CLEAR_FAILED"


def test_provider_closure_rejects_every_non_openai_spelling() -> None:
    service = CredentialService(_FakeCredentialStore())
    secret = SecretCredentialV1.from_hidden_input("inert-sentinel-value")
    for bad_provider in ("openai", "ANTHROPIC", "", " OPENAI", "OPENAI "):
        with pytest.raises(CredentialProviderClosedError):
            service.set(bad_provider, secret)  # type: ignore[arg-type]
        with pytest.raises(CredentialProviderClosedError):
            service.update(bad_provider, secret)  # type: ignore[arg-type]
        with pytest.raises(CredentialProviderClosedError):
            service.clear(bad_provider)  # type: ignore[arg-type]
        with pytest.raises(CredentialProviderClosedError):
            service.status(bad_provider)  # type: ignore[arg-type]
        with pytest.raises(CredentialProviderClosedError):
            service.get_for_call(bad_provider)  # type: ignore[arg-type]
    for non_string_provider in (None, 1, True, b"OPENAI"):
        with pytest.raises(CredentialProviderClosedError):
            service.status(non_string_provider)  # type: ignore[arg-type]


def test_invalid_secret_input_is_rejected() -> None:
    for bad_value in ("", None, 42, b"bytes"):
        with pytest.raises(CredentialSecretInvalidError):
            SecretCredentialV1.from_hidden_input(bad_value)

"""T27.1 legacy step 27.A: redacted credential status and lifecycle matrix.

SPEC §4.8 closes the credential lifecycle to the single ``OPENAI``
provider and requires status to expose only configured/provider/update
time — never the secret, its length, or a derivative.  The exact card RED
test and the full backend lifecycle matrix (Expected 27.A: 0) live here;
the closed schemas of every port result reject unknown, missing, and
type-confused fields at the parse boundary (SPEC §0.1, T05.1 convention).
"""

from __future__ import annotations

import pytest

# The credential contracts are pydantic runtime contracts; the hash-locked
# gate toolchain does not install runtime dependencies, so this module skips
# cleanly there instead of failing at collection (formal env runs it fully).
pytest.importorskip("pydantic")

from pydantic import ValidationError

from vespercode.canonical.timestamp_v1 import CanonicalTimestampV1
from vespercode.contracts.optional import AbsentV1, PresentV1
from vespercode.credentials.port import (
    CredentialBackendProbeV1,
    CredentialBackendUnsafeError,
    CredentialClearFailedError,
    CredentialErrorV1,
    CredentialMissingV1,
    CredentialMutationResultV1,
    CredentialProviderClosedError,
    CredentialSecretInvalidError,
    CredentialStatusV1,
    CredentialStoreFailedError,
    CredentialStoreMutationV1,
    SecretCredentialV1,
)
from vespercode.credentials.service import CredentialService

_FIXED_INSTANT = "2026-08-05T13:03:46.753Z"


class FakeCredentialStore:
    """In-memory fake port with probe counters and failure injection.

    Mirrors the WinCred store contract: probe precedes every service
    operation, set overwrites, clear of an absent entry is idempotent
    ``CLEARED``, and the status carries only configured/provider/time.
    """

    def __init__(
        self,
        *,
        probe_safe: bool = True,
        fail_set: bool = False,
        fail_read: bool = False,
        fail_clear: bool = False,
    ) -> None:
        self.probe_safe = probe_safe
        self.fail_set = fail_set
        self.fail_read = fail_read
        self.fail_clear = fail_clear
        self.probe_calls = 0
        self.set_calls = 0
        self.read_calls = 0
        self.clear_calls = 0
        self.events: list[str] = []
        self._stored: str | None = None
        self._last_written_ms = 1785935542980

    @property
    def stored_value(self) -> str | None:
        """The stored hidden value, for in-memory assertions only."""
        return self._stored

    def probe_backend(self) -> CredentialBackendProbeV1:
        self.probe_calls += 1
        self.events.append("probe")
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
        self.set_calls += 1
        self.events.append("set")
        if self.fail_set:
            raise CredentialStoreFailedError("credential store write failed")
        self._stored = secret.reveal()
        self._last_written_ms += 1
        return CredentialStoreMutationV1(schema_version=1, kind="STORED")

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
                kind="PRESENT",
                value=CanonicalTimestampV1.from_epoch_milliseconds(
                    self._last_written_ms
                ),
            ),
        )

    def get_for_call(self, provider: str) -> SecretCredentialV1 | CredentialMissingV1:
        self._guard(provider)
        self.read_calls += 1
        self.events.append("read")
        if self.fail_read:
            raise CredentialStoreFailedError("credential store read failed")
        if self._stored is None:
            return CredentialMissingV1(schema_version=1, kind="MISSING")
        return SecretCredentialV1.from_hidden_input(self._stored)

    def clear(self, provider: str) -> CredentialStoreMutationV1:
        self._guard(provider)
        self.clear_calls += 1
        self.events.append("clear")
        if self.fail_clear:
            raise CredentialClearFailedError("credential store clear failed")
        self._stored = None
        return CredentialStoreMutationV1(schema_version=1, kind="CLEARED")


@pytest.fixture
def credential_service() -> CredentialService:
    return CredentialService(FakeCredentialStore())


def test_credential_status_never_contains_secret_or_derivative(
    credential_service: CredentialService,
) -> None:
    secret = SecretCredentialV1.from_hidden_input("inert-sentinel-value")
    assert credential_service.set("OPENAI", secret).kind == "STORED"
    rendered = credential_service.status("OPENAI").model_dump_json()
    assert "inert-sentinel-value" not in rendered
    assert "length" not in rendered
    assert "digest" not in rendered


def test_credential_backend_lifecycle_matrix(
    credential_service: CredentialService,
) -> None:
    """SPEC §4.8 lifecycle matrix over the verified fake store (Expected 27.A: 0)."""
    # A fresh store is not configured and its status reveals nothing.
    fresh = credential_service.status("OPENAI")
    assert fresh.configured is False
    assert fresh.provider == "OPENAI"
    assert fresh.updated_at.kind == "ABSENT"
    # set stores and reports STORED without an error.
    secret = SecretCredentialV1.from_hidden_input("inert-sentinel-value")
    stored = credential_service.set("OPENAI", secret)
    assert stored.kind == "STORED"
    assert stored.error.kind == "ABSENT"
    assert credential_service.status("OPENAI").configured is True
    assert credential_service.status("OPENAI").updated_at.kind == "PRESENT"
    # update overwrites the previous entry with the new secret.
    second = SecretCredentialV1.from_hidden_input("inert-sentinel-value-2")
    assert credential_service.update("OPENAI", second).kind == "STORED"
    got = credential_service.get_for_call("OPENAI")
    assert isinstance(got, SecretCredentialV1)
    assert got.reveal() == second.reveal()
    # clear removes the entry and reports CLEARED; status returns to absent.
    assert credential_service.clear("OPENAI").kind == "CLEARED"
    assert credential_service.status("OPENAI").configured is False
    assert credential_service.status("OPENAI").updated_at.kind == "ABSENT"
    # clear of an already-absent entry is idempotent.
    assert credential_service.clear("OPENAI").kind == "CLEARED"
    # get_for_call after clear fails closed with CREDENTIAL_MISSING.
    missing = credential_service.get_for_call("OPENAI")
    assert isinstance(missing, CredentialErrorV1)
    assert missing.error_code == "CREDENTIAL_MISSING"
    # Provider closure: every lifecycle method rejects any provider other
    # than the exact string "OPENAI".
    for bad_provider in ("openai", "ANTHROPIC", "", " OPENAI", "OPENAI "):
        with pytest.raises(CredentialProviderClosedError):
            credential_service.set(bad_provider, secret)  # type: ignore[arg-type]
        with pytest.raises(CredentialProviderClosedError):
            credential_service.update(bad_provider, secret)  # type: ignore[arg-type]
        with pytest.raises(CredentialProviderClosedError):
            credential_service.clear(bad_provider)  # type: ignore[arg-type]
        with pytest.raises(CredentialProviderClosedError):
            credential_service.status(bad_provider)  # type: ignore[arg-type]
        with pytest.raises(CredentialProviderClosedError):
            credential_service.get_for_call(bad_provider)  # type: ignore[arg-type]
    for non_string_provider in (None, 1, True, b"OPENAI"):
        with pytest.raises(CredentialProviderClosedError):
            credential_service.status(non_string_provider)  # type: ignore[arg-type]


def test_status_schema_is_closed() -> None:
    """Every missing, unknown, extra, or type-confused status row rejects."""
    for bad in (
        {},  # missing fields
        {
            "schema_version": 1,
            "provider": "OPENAI",
            "configured": False,
            "updated_at": {"kind": "ABSENT"},
            "extra": 1,
        },
        {
            "schema_version": 1,
            "provider": "openai",
            "configured": False,
            "updated_at": {"kind": "ABSENT"},
        },
        {
            "schema_version": 1,
            "provider": "OPENAI",
            "configured": "true",
            "updated_at": {"kind": "ABSENT"},
        },
        {
            "schema_version": 1,
            "provider": "OPENAI",
            "configured": 1,
            "updated_at": {"kind": "ABSENT"},
        },
        {
            "schema_version": "1",
            "provider": "OPENAI",
            "configured": False,
            "updated_at": {"kind": "ABSENT"},
        },
        {
            "schema_version": True,
            "provider": "OPENAI",
            "configured": False,
            "updated_at": {"kind": "ABSENT"},
        },
        {
            "schema_version": 1.0,
            "provider": "OPENAI",
            "configured": False,
            "updated_at": {"kind": "ABSENT"},
        },
        {
            "schema_version": 1,
            "provider": "OPENAI",
            "configured": False,
            "updated_at": {"kind": "PRESENT"},
        },
        {
            "schema_version": 1,
            "provider": "OPENAI",
            "configured": False,
            "updated_at": {"kind": "PRESENT", "value": _FIXED_INSTANT},
        },
        {
            "schema_version": 1,
            "provider": "OPENAI",
            "configured": False,
            "updated_at": {"kind": "PRESENT", "value": {"value": "not-a-timestamp"}},
        },
        {
            "schema_version": 1,
            "provider": "OPENAI",
            "configured": False,
            "updated_at": {"kind": "ABSENT"},
            "extra2": None,
        },
    ):
        with pytest.raises(ValidationError):
            CredentialStatusV1.model_validate(bad)
    # The legal row round-trips deterministically.
    status = CredentialStatusV1(
        schema_version=1,
        provider="OPENAI",
        configured=True,
        updated_at=PresentV1[CanonicalTimestampV1](
            kind="PRESENT", value=CanonicalTimestampV1(_FIXED_INSTANT)
        ),
    )
    assert CredentialStatusV1.model_validate(status.model_dump()) == status


def test_mutation_result_schema_is_closed() -> None:
    """FAILED mutations carry a typed error; successes carry none."""
    for bad in (
        {},
        {"kind": "STORED"},  # missing error union
        {"kind": "FAILED", "error": {"kind": "ABSENT"}},
        {"kind": "STORED", "error": {"kind": "PRESENT", "value": {}}},
        {"kind": "STORED", "error": {"kind": "ABSENT"}, "extra": 1},
        {
            "kind": "FAILED",
            "error": {
                "kind": "PRESENT",
                "value": {"schema_version": 1, "error_code": "OTHER", "message": "x"},
            },
        },
        {
            "kind": "FAILED",
            "error": {
                "kind": "PRESENT",
                "value": {"error_code": "CREDENTIAL_MISSING", "message": "x"},
            },
        },
        {"kind": "PARTIAL", "error": {"kind": "ABSENT"}},
    ):
        with pytest.raises(ValidationError):
            CredentialMutationResultV1.model_validate(bad)
    stored = CredentialMutationResultV1(
        schema_version=1, kind="STORED", error=AbsentV1(kind="ABSENT")
    )
    assert stored.model_dump() == {
        "schema_version": 1,
        "kind": "STORED",
        "error": {"kind": "ABSENT"},
    }
    failed = CredentialMutationResultV1(
        schema_version=1,
        kind="FAILED",
        error=PresentV1[CredentialErrorV1](
            kind="PRESENT",
            value=CredentialErrorV1(
                schema_version=1,
                error_code="CREDENTIAL_BACKEND_UNSAFE",
                message="credential backend is not the verified Windows Credential Manager",
            ),
        ),
    )
    assert failed.kind == "FAILED"
    assert failed.error.kind == "PRESENT"
    assert failed.error.value.error_code == "CREDENTIAL_BACKEND_UNSAFE"


def test_error_schema_is_closed() -> None:
    for bad in (
        {},
        {"schema_version": 1, "error_code": "CREDENTIAL_MISSING"},  # missing message
        {"schema_version": 1, "error_code": "UNKNOWN_CODE", "message": "x"},
        {"schema_version": 1, "error_code": 1, "message": "x"},
        {"schema_version": "1", "error_code": "CREDENTIAL_MISSING", "message": "x"},
        {
            "schema_version": 1,
            "error_code": "CREDENTIAL_MISSING",
            "message": "x",
            "extra": 1,
        },
    ):
        with pytest.raises(ValidationError):
            CredentialErrorV1.model_validate(bad)


def test_probe_and_store_result_schemas_are_closed() -> None:
    for bad in (
        {},
        {"backend_id": "WINDOWS_CREDENTIAL_MANAGER"},
        {
            "backend_id": "PLAINTEXT_FILE",
            "capability": "READ_WRITE_DELETE",
        },
        {"backend_id": "WINDOWS_CREDENTIAL_MANAGER", "capability": "READ"},
        {
            "schema_version": True,
            "backend_id": "WINDOWS_CREDENTIAL_MANAGER",
            "capability": "READ_WRITE_DELETE",
        },
    ):
        with pytest.raises(ValidationError):
            CredentialBackendProbeV1.model_validate(bad)
    for bad in ({}, {"kind": "DELETED"}, {"schema_version": True, "kind": "STORED"}):
        with pytest.raises(ValidationError):
            CredentialStoreMutationV1.model_validate(bad)
    for bad in ({}, {"kind": "ABSENT"}, {"schema_version": True, "kind": "MISSING"}):
        with pytest.raises(ValidationError):
            CredentialMissingV1.model_validate(bad)


def test_secret_wrapper_is_a_closed_value() -> None:
    """The wrapper is closed, non-serializable, non-comparable, and redacted."""
    secret = SecretCredentialV1.from_hidden_input("inert-sentinel-value")
    assert "inert-sentinel-value" not in repr(secret)
    with pytest.raises(TypeError):
        secret.model_dump()
    with pytest.raises(TypeError):
        secret.model_dump_json()
    # Direct construction and empty validation payloads are closed: only
    # ``from_hidden_input`` can wrap hidden input.
    with pytest.raises(ValidationError):
        SecretCredentialV1(_hidden_value="direct")  # type: ignore[call-arg]
    with pytest.raises(ValidationError):
        SecretCredentialV1.model_validate({"value": "inert-sentinel-value"})
    with pytest.raises(ValidationError):
        SecretCredentialV1.model_validate({})
    with pytest.raises(TypeError):
        hash(secret)
    # A wrapper with no hidden value fails closed on reveal.
    with pytest.raises(CredentialSecretInvalidError):
        SecretCredentialV1.model_construct().reveal()

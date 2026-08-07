"""T27.1 legacy step 27.A: redaction and non-revealing wrapper tests.

SPEC §4.8 and AC-08: credential entry, status, update, clear, backend
probe, exceptions, and logs must never expose the secret or a derivative.
The wrapper is non-serializable and non-comparable; the credential
modules emit no log records at all; and every public result carries only
closed codes and bounded static messages.
"""

from __future__ import annotations

import copy
import hashlib
import pickle

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
    CredentialClearFailedError,
    CredentialErrorV1,
    CredentialMissingV1,
    CredentialProviderClosedError,
    CredentialSecretInvalidError,
    CredentialStatusV1,
    CredentialStoreFailedError,
    CredentialStoreMutationV1,
    SecretCredentialV1,
)
from vespercode.credentials.service import CredentialService

_SECRET_VALUE = "inert-sentinel-value"


class _SafeCredentialStore:
    """Minimal in-memory store whose lifecycle succeeds."""

    def __init__(self) -> None:
        self._stored: str | None = None

    def probe_backend(self) -> CredentialBackendProbeV1:
        return CredentialBackendProbeV1(
            schema_version=1,
            backend_id="WINDOWS_CREDENTIAL_MANAGER",
            capability="READ_WRITE_DELETE",
        )

    def set(
        self, provider: str, secret: SecretCredentialV1
    ) -> CredentialStoreMutationV1:
        self._stored = secret.reveal()
        return CredentialStoreMutationV1(schema_version=1, kind="STORED")

    def get_for_call(self, provider: str) -> SecretCredentialV1 | CredentialMissingV1:
        if self._stored is None:
            return CredentialMissingV1(schema_version=1, kind="MISSING")
        return SecretCredentialV1.from_hidden_input(self._stored)

    def status(self, provider: str) -> CredentialStatusV1:
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
        self._stored = None
        return CredentialStoreMutationV1(schema_version=1, kind="CLEARED")


class _FailingCredentialStore(_SafeCredentialStore):
    """A store whose every write fails with a typed store error."""

    def set(
        self, provider: str, secret: SecretCredentialV1
    ) -> CredentialStoreMutationV1:
        raise CredentialStoreFailedError("credential store write failed")


def test_secret_repr_and_str_are_redacted() -> None:
    secret = SecretCredentialV1.from_hidden_input(_SECRET_VALUE)
    assert _SECRET_VALUE not in repr(secret)
    assert _SECRET_VALUE not in str(secret)
    assert _SECRET_VALUE not in f"{secret!r}"
    assert _SECRET_VALUE not in f"{secret}"


def test_secret_is_not_serializable() -> None:
    secret = SecretCredentialV1.from_hidden_input(_SECRET_VALUE)
    with pytest.raises(TypeError):
        secret.model_dump()
    with pytest.raises(TypeError):
        secret.model_dump(mode="json")
    with pytest.raises(TypeError):
        secret.model_dump_json()
    with pytest.raises(TypeError):
        pickle.dumps(secret)
    with pytest.raises(TypeError):
        copy.copy(secret)
    with pytest.raises(TypeError):
        copy.deepcopy(secret)


def test_secret_is_not_comparable_or_hashable() -> None:
    secret = SecretCredentialV1.from_hidden_input(_SECRET_VALUE)
    other = SecretCredentialV1.from_hidden_input("another-sentinel-value")
    with pytest.raises(TypeError):
        secret == other
    with pytest.raises(TypeError):
        secret != other
    with pytest.raises(TypeError):
        hash(secret)
    with pytest.raises(TypeError):
        {secret: 1}
    with pytest.raises(TypeError):
        secret in (other,)


def test_secret_wrapper_exposes_no_metadata_accessors() -> None:
    secret = SecretCredentialV1.from_hidden_input(_SECRET_VALUE)
    assert not hasattr(secret, "length")
    assert not hasattr(secret, "digest")
    assert not hasattr(secret, "size")
    assert not hasattr(secret, "value")


def test_closed_exception_messages_never_contain_secret() -> None:
    for exc in (
        CredentialProviderClosedError("credential provider is closed to OPENAI"),
        CredentialSecretInvalidError("credential secret must be a non-empty string"),
        CredentialBackendUnsafeError(
            "credential backend is not Windows Credential Manager"
        ),
        CredentialStoreFailedError("credential store write failed"),
        CredentialClearFailedError("credential store clear failed"),
    ):
        assert _SECRET_VALUE not in str(exc)
        assert _SECRET_VALUE not in repr(exc)


def test_lifecycle_emits_no_logs_and_results_never_expose_secret(
    caplog: pytest.LogCaptureFixture,
) -> None:
    secret = SecretCredentialV1.from_hidden_input(_SECRET_VALUE)
    digest = hashlib.sha256(_SECRET_VALUE.encode("utf-8")).hexdigest()

    safe = _SafeCredentialStore()
    service = CredentialService(safe)
    stored = service.set("OPENAI", secret)
    status_json = service.status("OPENAI").model_dump_json()
    got = service.get_for_call("OPENAI")
    assert isinstance(got, SecretCredentialV1)
    assert got.reveal() == _SECRET_VALUE

    failing = _FailingCredentialStore()
    failed_service = CredentialService(failing)
    failed = failed_service.set("OPENAI", secret)
    missing = failed_service.get_for_call("OPENAI")

    outputs = (
        stored.model_dump_json(),
        status_json,
        failed.model_dump_json(),
        service.clear("OPENAI").model_dump_json(),
    )
    for output in outputs:
        assert _SECRET_VALUE not in output
        assert digest not in output
    assert isinstance(missing, CredentialErrorV1)
    assert _SECRET_VALUE not in missing.model_dump_json()
    # The credential modules emit no log records at all.
    assert caplog.records == []


def test_status_exposes_no_secret_derivative() -> None:
    safe = _SafeCredentialStore()
    service = CredentialService(safe)
    service.set("OPENAI", SecretCredentialV1.from_hidden_input(_SECRET_VALUE))
    rendered = service.status("OPENAI").model_dump_json()
    assert _SECRET_VALUE not in rendered
    assert hashlib.sha256(_SECRET_VALUE.encode("utf-8")).hexdigest() not in rendered
    assert "length" not in rendered
    assert "digest" not in rendered

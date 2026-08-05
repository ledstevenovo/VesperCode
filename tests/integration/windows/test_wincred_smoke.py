"""T27.1 legacy step 27.B: real Windows Credential Manager lifecycle tests.

Runs only under ``-m windows_integration`` on the project Windows host.
Proves the sole WinCred store port with real set/status/get-for-call/
clear operations against the current user's Credential Manager using
clearly fake values, and deletes every generated entry in ``finally``.
The module teardown enumerates the real Credential Manager and verifies
zero VesperCode credential residue — a failed clear or probe cleanup
fails the module instead of leaving a credential behind.
"""

from __future__ import annotations

import keyring
import keyring.backends.null as keyring_null
import pytest
import win32cred  # type: ignore[import-untyped]

from collections.abc import Iterator
from typing import Final

from src.vespercode.credentials.port import (
    CredentialBackendProbeV1,
    CredentialBackendUnsafeError,
    CredentialErrorV1,
    CredentialMissingV1,
    CredentialProviderClosedError,
    SecretCredentialV1,
)
from src.vespercode.credentials.service import CredentialService
from src.vespercode.credentials.wincred_store import WindowsCredentialManagerStore

pytestmark = pytest.mark.windows_integration

_VESPERCODE_PREFIX: Final = "vespercode/v1/"


def generated_test_secret() -> SecretCredentialV1:
    """A clearly fake, deterministic value for the real WinCred proof.

    This is never a real key: the value is fixed and obviously
    non-secret, and every test deletes the generated entry before it
    ends.
    """
    return SecretCredentialV1.from_hidden_input("vespercode-wincred-test-secret-v1")


_KNOWN_TEST_VALUES: Final = frozenset(
    {
        "vespercode-wincred-test-secret-v1",
        "vespercode-wincred-test-secret-v2",
        "vespercode-capability-probe-v1",
    }
)


def _vespercode_target_names() -> tuple[str, ...]:
    """All current-user Credential Manager targets under our versioned prefix."""
    return tuple(
        sorted(
            str(credential["TargetName"])
            for credential in win32cred.CredEnumerate()
            if str(credential["TargetName"]).lower().startswith(_VESPERCODE_PREFIX)
        )
    )


def _stored_value(target: str) -> str:
    """The UTF-16-LE decoded value of one target, for identity checks only."""
    credential = win32cred.CredRead(Type=win32cred.CRED_TYPE_GENERIC, TargetName=target)
    blob = credential["CredentialBlob"]
    return blob.decode("utf-16-le") if isinstance(blob, bytes) else ""


def _refuse_non_generated_entries() -> None:
    """Never clobber a real configured credential under our versioned prefix.

    The module may only delete entries whose stored value is a known
    generated test value; an unknown value means a real user key exists
    and the module fails closed instead of destroying it.
    """
    for target in _vespercode_target_names():
        if _stored_value(target) not in _KNOWN_TEST_VALUES:
            raise AssertionError(
                f"refusing to overwrite a non-generated Credential Manager "
                f"entry {target!r}; remove it manually before running 27.B"
            )


def _delete_generated_test_entries() -> None:
    """Delete only entries whose stored value is a known generated test value."""
    for target in _vespercode_target_names():
        if _stored_value(target) in _KNOWN_TEST_VALUES:
            win32cred.CredDelete(Type=win32cred.CRED_TYPE_GENERIC, TargetName=target)


@pytest.fixture
def wincred_store() -> WindowsCredentialManagerStore:
    return WindowsCredentialManagerStore()


@pytest.fixture(scope="module", autouse=True)
def _clean_module_lifecycle() -> Iterator[None]:
    """Cleanup before and residue proof after the module.

    Setup refuses to touch any non-generated entry (a real configured
    key blocks the module) and deletes only stale generated test
    entries; teardown deletes the generated entries again and then
    proves zero ``vespercode/v1/`` residue in the real Credential
    Manager.
    """
    _refuse_non_generated_entries()
    _delete_generated_test_entries()
    yield
    _delete_generated_test_entries()
    assert _vespercode_target_names() == (), "VesperCode credential residue remains"


def test_wincred_smoke_clears_generated_test_entry(
    wincred_store: WindowsCredentialManagerStore,
) -> None:
    secret = generated_test_secret()
    try:
        assert wincred_store.set("OPENAI", secret).kind == "STORED"
        assert wincred_store.status("OPENAI").configured is True
        assert isinstance(wincred_store.get_for_call("OPENAI"), SecretCredentialV1)
    finally:
        wincred_store.clear("OPENAI")
    assert wincred_store.status("OPENAI").configured is False


def test_wincred_real_lifecycle_matrix(
    wincred_store: WindowsCredentialManagerStore,
) -> None:
    """Real set/status/overwrite/get-for-call/clear matrix (Expected 27.B: 0)."""
    probe = wincred_store.probe_backend()
    assert probe.backend_id == "WINDOWS_CREDENTIAL_MANAGER"
    assert probe.capability == "READ_WRITE_DELETE"
    first = generated_test_secret()
    second = SecretCredentialV1.from_hidden_input("vespercode-wincred-test-secret-v2")
    try:
        assert wincred_store.status("OPENAI").configured is False
        assert wincred_store.set("OPENAI", first).kind == "STORED"
        status = wincred_store.status("OPENAI")
        assert status.configured is True
        assert status.provider == "OPENAI"
        assert status.updated_at.kind == "PRESENT"
        got = wincred_store.get_for_call("OPENAI")
        assert isinstance(got, SecretCredentialV1)
        assert got.reveal() == first.reveal()
        # Overwrite with a second fake value and read it back fresh.
        assert wincred_store.set("OPENAI", second).kind == "STORED"
        overwritten = wincred_store.get_for_call("OPENAI")
        assert isinstance(overwritten, SecretCredentialV1)
        assert overwritten.reveal() == second.reveal()
        # Clear, then verify absence and a closed missing read.
        assert wincred_store.clear("OPENAI").kind == "CLEARED"
        assert wincred_store.status("OPENAI").configured is False
        missing = wincred_store.get_for_call("OPENAI")
        assert isinstance(missing, CredentialMissingV1)
        # Clear of an already-absent entry is idempotent.
        assert wincred_store.clear("OPENAI").kind == "CLEARED"
    finally:
        wincred_store.clear("OPENAI")
    assert wincred_store.status("OPENAI").configured is False


def test_wincred_service_real_lifecycle(
    wincred_store: WindowsCredentialManagerStore,
) -> None:
    """The composed service over the real store proves the typed lifecycle."""
    service = CredentialService(wincred_store)
    secret = generated_test_secret()
    try:
        assert service.set("OPENAI", secret).kind == "STORED"
        assert service.status("OPENAI").configured is True
        got = service.get_for_call("OPENAI")
        assert isinstance(got, SecretCredentialV1)
        assert got.reveal() == secret.reveal()
    finally:
        assert service.clear("OPENAI").kind == "CLEARED"
    assert service.status("OPENAI").configured is False
    missing = service.get_for_call("OPENAI")
    assert isinstance(missing, CredentialErrorV1)
    assert missing.error_code == "CREDENTIAL_MISSING"


def test_wincred_unsafe_backend_refuses_every_operation(
    monkeypatch: pytest.MonkeyPatch,
    wincred_store: WindowsCredentialManagerStore,
) -> None:
    """A non-WinCred keyring backend fails closed with zero storage."""
    monkeypatch.setattr(
        keyring,
        "get_keyring",
        lambda: keyring_null.Keyring(),  # type: ignore[no-untyped-call]
    )
    with pytest.raises(CredentialBackendUnsafeError):
        wincred_store.probe_backend()
    service = CredentialService(wincred_store)
    result = service.set("OPENAI", generated_test_secret())
    assert result.kind == "FAILED"
    assert result.error.kind == "PRESENT"
    assert result.error.value.error_code == "CREDENTIAL_BACKEND_UNSAFE"
    error = service.get_for_call("OPENAI")
    assert isinstance(error, CredentialErrorV1)
    assert error.error_code == "CREDENTIAL_BACKEND_UNSAFE"
    with pytest.raises(CredentialBackendUnsafeError):
        service.status("OPENAI")
    cleared = service.clear("OPENAI")
    assert cleared.kind == "FAILED"
    assert cleared.error.kind == "PRESENT"
    assert cleared.error.value.error_code == "CREDENTIAL_BACKEND_UNSAFE"
    monkeypatch.undo()
    # Nothing was stored anywhere: the real store still reports absent.
    assert wincred_store.status("OPENAI").configured is False


def test_wincred_probe_writes_no_residue(
    wincred_store: WindowsCredentialManagerStore,
) -> None:
    """The capability probe deletes its own generated entry."""
    probe = wincred_store.probe_backend()
    assert probe.backend_id == "WINDOWS_CREDENTIAL_MANAGER"
    assert _vespercode_target_names() == ()


def test_wincred_store_closes_provider(
    wincred_store: WindowsCredentialManagerStore,
) -> None:
    with pytest.raises(CredentialProviderClosedError):
        wincred_store.set("ANTHROPIC", generated_test_secret())
    with pytest.raises(CredentialProviderClosedError):
        wincred_store.status("")
    with pytest.raises(CredentialProviderClosedError):
        wincred_store.get_for_call("openai")
    with pytest.raises(CredentialProviderClosedError):
        wincred_store.clear("OPENAI ")


def test_wincred_set_fails_closed_when_post_write_probe_fails(
    monkeypatch: pytest.MonkeyPatch,
    wincred_store: WindowsCredentialManagerStore,
) -> None:
    """SPEC §4.8 behavior 2: a failed post-write verification reports failure.

    The write landed but the verification failed, so the caller sees a
    typed failure (fail closed) while the entry remains clearable; the
    generated entry is removed before the test ends.
    """
    real_probe = wincred_store.probe_backend
    probe_count = 0

    def failing_post_write_probe() -> CredentialBackendProbeV1:
        nonlocal probe_count
        probe_count += 1
        if probe_count == 2:
            raise CredentialBackendUnsafeError(
                "credential backend is not Windows Credential Manager"
            )
        return real_probe()

    monkeypatch.setattr(wincred_store, "probe_backend", failing_post_write_probe)
    with pytest.raises(CredentialBackendUnsafeError):
        wincred_store.set("OPENAI", generated_test_secret())
    monkeypatch.undo()
    try:
        assert wincred_store.status("OPENAI").configured is True
    finally:
        wincred_store.clear("OPENAI")
    assert wincred_store.status("OPENAI").configured is False

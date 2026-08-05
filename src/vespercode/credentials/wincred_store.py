"""T27.1 legacy step 27.B: the sole Windows Credential Manager store port.

``WindowsCredentialManagerStore`` maps one versioned OPENAI target to the
current user's Windows Credential Manager through the Win32 API
(``win32cred``) with explicit local-machine persistence, and proves
backend identity (the environment credential library must resolve to
keyring's ``WinVaultKeyring`` — Windows Credential Manager) plus a real
write/read/delete capability cycle before every mutation and fresh
get-for-call read.  The capability probe deletes its own generated entry
in ``finally``; every lifecycle method probes first, and ``set``
re-verifies the backend after the write (SPEC §4.8 behavior 2).  There is
no cache, fallback backend, environment/file import, printing, or network
call (GREEN-2/4).  The secret value is written through the Win32 API and
never enters any message, log, or result.
"""

from __future__ import annotations

import datetime
from dataclasses import dataclass
from typing import Final

import keyring
import keyring.backends.Windows as keyring_windows
import pywintypes  # type: ignore[import-untyped]
import win32cred  # type: ignore[import-untyped]

from src.vespercode.canonical.timestamp_v1 import CanonicalTimestampV1
from src.vespercode.contracts.optional import AbsentV1, PresentV1
from src.vespercode.credentials.port import (
    OPENAI_PROVIDER,
    CredentialBackendProbeV1,
    CredentialBackendUnsafeError,
    CredentialClearFailedError,
    CredentialMissingV1,
    CredentialProviderClosedError,
    CredentialStatusV1,
    CredentialStoreFailedError,
    CredentialStoreMutationV1,
    SecretCredentialV1,
)

_OPENAI_TARGET_SERVICE: Final = "vespercode/v1/openai"
_OPENAI_TARGET_USERNAME: Final = "api-key"
_PROBE_SERVICE: Final = "vespercode/v1/probe"
_PROBE_USERNAME: Final = "capability-probe"
_PROBE_VALUE: Final = "vespercode-capability-probe-v1"
_CRED_NOT_FOUND: Final = 1168  # ERROR_NOT_FOUND from the Win32 Credential API
_MANDATORY_ROW_KEYS: Final = frozenset({"CredentialBlob", "LastWritten", "UserName"})


@dataclass(frozen=True)
class _CredentialEntryV1:
    """One decoded current-user Credential Manager entry (never logged)."""

    value: str
    last_written_ms: int


class WindowsCredentialManagerStore:
    """Sole WinCred implementation of every ``CredentialStorePortV1`` method.

    The versioned OPENAI target is ``vespercode/v1/openai`` under the
    current user's Credential Manager with ``CRED_PERSIST_LOCAL_MACHINE``
    (per-user store, survives reboot, never roams).  Reads decode the
    UTF-16-LE credential blob written by this store; a mismatched
    username or malformed blob fails closed as a store failure.
    """

    def probe_backend(self) -> CredentialBackendProbeV1:
        """Verify backend identity and write/read/delete capability (GREEN-1)."""
        resolved = keyring.get_keyring()
        if not isinstance(resolved, keyring_windows.WinVaultKeyring):
            raise CredentialBackendUnsafeError(
                "credential backend is not Windows Credential Manager"
            )
        try:
            self._probe_credential_cycle()
        except CredentialBackendUnsafeError:
            raise
        except Exception as exc:
            raise CredentialBackendUnsafeError(
                "credential backend capability probe failed"
            ) from exc
        return CredentialBackendProbeV1(
            schema_version=1,
            backend_id="WINDOWS_CREDENTIAL_MANAGER",
            capability="READ_WRITE_DELETE",
        )

    def _probe_credential_cycle(self) -> None:
        """Write/read/delete one probe credential; always delete it in ``finally``."""
        try:
            self._write_credential(_PROBE_SERVICE, _PROBE_USERNAME, _PROBE_VALUE)
            entry = self._read_entry(_PROBE_SERVICE, _PROBE_USERNAME)
            if entry is None or entry.value != _PROBE_VALUE:
                raise CredentialBackendUnsafeError(
                    "credential backend capability probe mismatch"
                )
        finally:
            self._delete_credential_best_effort(_PROBE_SERVICE)

    @staticmethod
    def _guard_provider(provider: str) -> None:
        if provider != OPENAI_PROVIDER:
            raise CredentialProviderClosedError(
                "credential provider is closed to OPENAI"
            )

    def set(
        self, provider: str, secret: SecretCredentialV1
    ) -> CredentialStoreMutationV1:
        """Probe, write, then re-verify the backend after the write (SPEC §4.8)."""
        self._guard_provider(provider)
        self.probe_backend()
        try:
            self._write_credential(
                _OPENAI_TARGET_SERVICE, _OPENAI_TARGET_USERNAME, secret.reveal()
            )
        except Exception as exc:
            raise CredentialStoreFailedError("credential store write failed") from exc
        self.probe_backend()
        return CredentialStoreMutationV1(schema_version=1, kind="STORED")

    def status(self, provider: str) -> CredentialStatusV1:
        """Configured flag, provider, and last-written time only — never the value."""
        self._guard_provider(provider)
        self.probe_backend()
        last_written_ms = self._read_metadata(
            _OPENAI_TARGET_SERVICE, _OPENAI_TARGET_USERNAME
        )
        if last_written_ms is None:
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
                value=CanonicalTimestampV1.from_epoch_milliseconds(last_written_ms),
            ),
        )

    def get_for_call(self, provider: str) -> SecretCredentialV1 | CredentialMissingV1:
        """Re-probe and read the current entry fresh; never reuse configured state."""
        self._guard_provider(provider)
        self.probe_backend()
        entry = self._read_entry(_OPENAI_TARGET_SERVICE, _OPENAI_TARGET_USERNAME)
        if entry is None:
            return CredentialMissingV1(schema_version=1, kind="MISSING")
        return SecretCredentialV1.from_hidden_input(entry.value)

    def clear(self, provider: str) -> CredentialStoreMutationV1:
        """Delete the entry; an already-absent entry clears idempotently."""
        self._guard_provider(provider)
        self.probe_backend()
        present = (
            self._read_metadata(_OPENAI_TARGET_SERVICE, _OPENAI_TARGET_USERNAME)
            is not None
        )
        if not present:
            return CredentialStoreMutationV1(schema_version=1, kind="CLEARED")
        try:
            self._delete_credential(_OPENAI_TARGET_SERVICE)
        except Exception as exc:
            raise CredentialClearFailedError("credential store clear failed") from exc
        return CredentialStoreMutationV1(schema_version=1, kind="CLEARED")

    @staticmethod
    def _write_credential(service: str, username: str, secret: str) -> None:
        win32cred.CredWrite(
            dict(
                Type=win32cred.CRED_TYPE_GENERIC,
                TargetName=service,
                UserName=username,
                CredentialBlob=secret,
                Persist=win32cred.CRED_PERSIST_LOCAL_MACHINE,
            ),
            0,
        )

    @staticmethod
    def _read_row(service: str) -> dict[str, object] | None:
        """One raw Credential Manager row, or None when the entry is absent."""
        try:
            credential = win32cred.CredRead(
                Type=win32cred.CRED_TYPE_GENERIC, TargetName=service
            )
        except pywintypes.error as exc:
            if exc.winerror == _CRED_NOT_FOUND:
                return None
            raise CredentialStoreFailedError("credential store read failed") from exc
        missing = _MANDATORY_ROW_KEYS - set(credential.keys())
        if missing:
            raise CredentialStoreFailedError("credential store entry is malformed")
        return credential  # type: ignore[no-any-return]

    @staticmethod
    def _last_written_ms(last_written: object) -> int:
        """Canonical epoch milliseconds of a Credential Manager ``LastWritten``."""
        if not isinstance(last_written, datetime.datetime):
            raise CredentialStoreFailedError("credential store entry is malformed")
        if last_written.tzinfo is None:
            last_written = last_written.replace(tzinfo=datetime.timezone.utc)
        return int(last_written.timestamp() * 1000)

    @staticmethod
    def _read_metadata(service: str, expected_username: str) -> int | None:
        """Last-written epoch milliseconds of the entry, or None when absent.

        Identity and metadata only — the credential blob is never
        decoded on this path, so status/readiness checks do not read
        the secret (SPEC §4.1 behavior 12).
        """
        credential = WindowsCredentialManagerStore._read_row(service)
        if credential is None:
            return None
        if credential["UserName"] != expected_username:
            raise CredentialStoreFailedError("credential store entry identity mismatch")
        return WindowsCredentialManagerStore._last_written_ms(credential["LastWritten"])

    @staticmethod
    def _read_entry(service: str, expected_username: str) -> _CredentialEntryV1 | None:
        """The decoded entry value plus last-written time, or None when absent."""
        credential = WindowsCredentialManagerStore._read_row(service)
        if credential is None:
            return None
        blob = credential["CredentialBlob"]
        if not isinstance(blob, bytes):
            raise CredentialStoreFailedError("credential store entry is malformed")
        if credential["UserName"] != expected_username:
            raise CredentialStoreFailedError("credential store entry identity mismatch")
        try:
            value = blob.decode("utf-16-le")
        except UnicodeDecodeError as exc:
            raise CredentialStoreFailedError(
                "credential store entry is malformed"
            ) from exc
        return _CredentialEntryV1(
            value=value,
            last_written_ms=WindowsCredentialManagerStore._last_written_ms(
                credential["LastWritten"]
            ),
        )

    @staticmethod
    def _delete_credential(service: str) -> None:
        win32cred.CredDelete(Type=win32cred.CRED_TYPE_GENERIC, TargetName=service)

    @classmethod
    def _delete_credential_best_effort(cls, service: str) -> None:
        try:
            cls._delete_credential(service)
        except Exception:
            pass  # residue is caught by the module-level Credential Manager check

"""Route B / B4b-02C1: the production OS credential adapter behind the v2 port.

The v1 credential plane (``credentials/port.py``,
``credentials/service.py``, ``credentials/wincred_store.py``) is
pydantic-bound, closed to the single ``OPENAI`` provider, and keyed to
the ``vespercode/v1/`` target namespace; it remains untouched
read-only legacy.  Nothing here imports it, and the v1 credential
service is never the v2 authority: this adapter is an independent
implementation of the B2 ``V2CredentialProviderPort`` over the target
platform's secure OS credential store, under its own
``vespercode/v2/`` target namespace.

Structure and security properties:

- **Injectable backend port.** ``V2OSCredentialBackendPort`` is the
  narrow OS-store edge (backend identity, a write/read/delete probe
  cycle, write, metadata-only read, value read, delete).
  ``OSV2CredentialProvider`` implements the credential port over any
  conforming backend; the offline unit tests inject a deterministic
  fake, and the optional Windows integration suite exercises the real
  backend against the current user's real store.

- **Optional platform imports stay function-local.** The module
  imports only the standard library (and the v2 port) at module
  scope.  The real Windows backend imports ``win32cred`` and
  ``pywintypes`` lazily inside its methods, so importing this module
  never loads a platform library on any host and the v2 wheel stays
  standard-library only; a host without the optional library simply
  fails closed with ``CREDENTIAL_BACKEND_UNAVAILABLE``.

- **Fail closed, always.** Every operation first proves the backend:
  its identity must be in the closed backend-id set (only
  ``WINDOWS_CREDENTIAL_MANAGER``), and a real write/read/delete
  capability cycle of the backend's own probe target must succeed.  An
  unavailable or unsafe backend raises the closed
  ``V2OSCredentialStoreError`` with a static message — never a
  fallback backend, never the secret, its length, or any derivative.
  ``set`` re-verifies the backend after the write; there is no cache,
  no environment/file import, no printing, and no network call.

- **The raw value exists in one write frame only.** ``set`` obtains
  the raw value solely through the storage-reveal seam minted by
  ``credentials/v2_port`` (``_storage_reveal_capability``, granted
  only to this module); it flows from that extraction directly into
  the backend write and nowhere else — no log line, no database row,
  no exception text, no retained state.  ``get_for_call`` re-probes
  and reads the stored value fresh, wraps it, and hands out only the
  wrapper; the provider call boundary alone can reveal it.

- **Non-revealing status.** ``status`` reads metadata only (the
  stored value is never decoded on the status path) and reports the
  provider name, the configured flag, and the OS entry's last-written
  time — nothing else.

- **Disjoint v2 targets.** Credentials live under
  ``vespercode/v2/credential/<provider>`` with the ``api-key``
  username; the backend's capability probe uses
  ``vespercode/v2/probe``.  The provider-name grammar excludes ``/``,
  so no provider name can alias the probe target or any other
  service, and a stored entry whose username does not match fails
  closed as a store failure (a foreign entry is never read as ours).
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from typing import Any, Protocol, runtime_checkable

from vespercode.credentials.v2_port import (
    V2CredentialError,
    V2CredentialMutation,
    V2CredentialSecret,
    V2CredentialStatus,
    _provider_name,
    _storage_reveal_capability,
)

OS_CREDENTIAL_BACKEND_IDS_V2 = frozenset({"WINDOWS_CREDENTIAL_MANAGER"})
"""The closed identity set of backends a provider may trust."""

OS_CREDENTIAL_STORE_ERROR_CODES_V2 = frozenset(
    {
        "CREDENTIAL_BACKEND_UNAVAILABLE",
        "CREDENTIAL_BACKEND_UNSAFE",
        "CREDENTIAL_STORE_FAILED",
    }
)
"""The closed error-code vocabulary of the OS credential adapter."""

_STORE_MESSAGES: dict[str, str] = {
    "CREDENTIAL_BACKEND_UNAVAILABLE": (
        "the OS credential backend is unavailable on this host"
    ),
    "CREDENTIAL_BACKEND_UNSAFE": ("the OS credential backend cannot be proven safe"),
    "CREDENTIAL_STORE_FAILED": "the OS credential store operation failed",
}

_CREDENTIAL_SERVICE_PREFIX = "vespercode/v2/credential/"
_CREDENTIAL_USERNAME = "api-key"
_PROBE_SERVICE = "vespercode/v2/probe"
_PROBE_USERNAME = "capability-probe"
_PROBE_VALUE = "vespercode-v2-capability-probe"
_CRED_NOT_FOUND = 1168  # ERROR_NOT_FOUND from the Win32 Credential API
_MANDATORY_ROW_KEYS = frozenset({"CredentialBlob", "LastWritten", "UserName"})


class V2OSCredentialStoreError(RuntimeError):
    """One closed OS-store infrastructure failure.

    The message is the bounded static text of the closed code — never
    a secret, a stored value, a service name, or an OS error string —
    so an infrastructure failure stays redacted by construction.  This
    is deliberately NOT a ``V2CredentialError``: a broken backend is an
    infrastructure failure that propagates loudly (the credential-port
    error type stays the port's own closed rejection vocabulary), and
    the provider call service lets it propagate BEFORE the one-shot
    consume, so a failing store never burns an authorization.
    """

    def __init__(self, code: str) -> None:
        if code not in OS_CREDENTIAL_STORE_ERROR_CODES_V2:
            raise ValueError("unknown v2 OS credential store error code")
        super().__init__(_STORE_MESSAGES[code])
        self.code = code


@runtime_checkable
class V2OSCredentialBackendPort(Protocol):
    """The narrow OS credential backend edge (injectable for tests).

    Implementations talk to one platform's secure OS credential
    store under the current user.  ``backend_id`` returns the closed
    identity; ``probe_cycle`` proves write/read/delete capability on
    the backend's own probe target (cleaning it up); ``write`` stores
    a raw value under a service/username; ``read_metadata`` returns
    the entry's last-written epoch milliseconds without decoding the
    value; ``read_value`` returns the stored value or ``None``;
    ``delete`` removes the entry.  Failures raise the closed
    ``V2OSCredentialStoreError``.
    """

    def backend_id(self) -> str: ...

    def probe_cycle(self) -> None: ...

    def write(self, service: str, username: str, secret: str) -> None: ...

    def read_metadata(self, service: str, username: str) -> int | None: ...

    def read_value(self, service: str, username: str) -> str | None: ...

    def delete(self, service: str) -> None: ...


class WindowsCredentialManagerV2Backend:
    """The real Windows Credential Manager backend (lazy pywin32 imports).

    Every Win32 API access goes through ``_win32``, which first
    requires the ``win32`` platform and then imports ``win32cred``
    and ``pywintypes`` lazily — so the module (and the adapter, and the
    wheel) never imports a platform library until a real store
    operation runs, and a host without pywin32 fails closed with
    ``CREDENTIAL_BACKEND_UNAVAILABLE``.  Entries are generic
    credentials under the current user with
    ``CRED_PERSIST_LOCAL_MACHINE`` (per-user store, survives reboot,
    never roams); values are written as UTF-16-LE blobs by the Win32
    API and decoded symmetrically on read.  The probe cycle writes,
    reads back, and deletes its own probe entry, always cleaning up in
    ``finally``.
    """

    __slots__ = ()

    def backend_id(self) -> str:
        return "WINDOWS_CREDENTIAL_MANAGER"

    @staticmethod
    def _win32() -> tuple[Any, Any]:
        if sys.platform != "win32":
            raise V2OSCredentialStoreError("CREDENTIAL_BACKEND_UNAVAILABLE")
        try:
            import win32cred  # type: ignore[import-untyped]
            import pywintypes  # type: ignore[import-untyped]
        except Exception as exc:  # noqa: BLE001 - fail closed, no store use
            raise V2OSCredentialStoreError("CREDENTIAL_BACKEND_UNAVAILABLE") from exc
        return win32cred, pywintypes

    def probe_cycle(self) -> None:
        win32cred, _ = self._win32()
        try:
            self.write(_PROBE_SERVICE, _PROBE_USERNAME, _PROBE_VALUE)
            value = self.read_value(_PROBE_SERVICE, _PROBE_USERNAME)
            if value != _PROBE_VALUE:
                raise V2OSCredentialStoreError("CREDENTIAL_BACKEND_UNSAFE")
        finally:
            self._delete_best_effort(_PROBE_SERVICE)

    def write(self, service: str, username: str, secret: str) -> None:
        win32cred, _ = self._win32()
        try:
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
        except V2OSCredentialStoreError:
            raise
        except Exception as exc:  # noqa: BLE001 - fail closed, no OS text
            raise V2OSCredentialStoreError("CREDENTIAL_STORE_FAILED") from exc

    def read_metadata(self, service: str, username: str) -> int | None:
        row = self._read_row(service)
        if row is None:
            return None
        self._require_row_shape(row)
        if row["UserName"] != username:
            raise V2OSCredentialStoreError("CREDENTIAL_STORE_FAILED")
        return _last_written_epoch_ms(row["LastWritten"])

    def read_value(self, service: str, username: str) -> str | None:
        row = self._read_row(service)
        if row is None:
            return None
        self._require_row_shape(row)
        if row["UserName"] != username:
            raise V2OSCredentialStoreError("CREDENTIAL_STORE_FAILED")
        blob = row["CredentialBlob"]
        if not isinstance(blob, bytes):
            raise V2OSCredentialStoreError("CREDENTIAL_STORE_FAILED")
        try:
            return blob.decode("utf-16-le")
        except UnicodeDecodeError as exc:
            raise V2OSCredentialStoreError("CREDENTIAL_STORE_FAILED") from exc

    def delete(self, service: str) -> None:
        win32cred, _ = self._win32()
        try:
            win32cred.CredDelete(Type=win32cred.CRED_TYPE_GENERIC, TargetName=service)
        except V2OSCredentialStoreError:
            raise
        except Exception as exc:  # noqa: BLE001 - fail closed, no OS text
            raise V2OSCredentialStoreError("CREDENTIAL_STORE_FAILED") from exc

    def _read_row(self, service: str) -> dict[str, object] | None:
        win32cred, pywintypes = self._win32()
        try:
            row = win32cred.CredRead(
                Type=win32cred.CRED_TYPE_GENERIC, TargetName=service
            )
        except pywintypes.error as exc:
            if exc.winerror == _CRED_NOT_FOUND:
                return None
            raise V2OSCredentialStoreError("CREDENTIAL_STORE_FAILED") from exc
        except V2OSCredentialStoreError:
            raise
        except Exception as exc:  # noqa: BLE001 - fail closed, no OS text
            raise V2OSCredentialStoreError("CREDENTIAL_STORE_FAILED") from exc
        return row  # type: ignore[no-any-return]

    @staticmethod
    def _require_row_shape(row: dict[str, object]) -> None:
        if _MANDATORY_ROW_KEYS - set(row.keys()):
            raise V2OSCredentialStoreError("CREDENTIAL_STORE_FAILED")

    def _delete_best_effort(self, service: str) -> None:
        try:
            self.delete(service)
        except Exception:
            pass  # probe residue is caught by the next probe cycle


def _last_written_epoch_ms(last_written: object) -> int:
    if not isinstance(last_written, datetime):
        raise V2OSCredentialStoreError("CREDENTIAL_STORE_FAILED")
    stamped = last_written
    if stamped.tzinfo is None:
        stamped = stamped.replace(tzinfo=timezone.utc)
    return int(stamped.timestamp() * 1000)


class _UnavailableV2OSCredentialBackend:
    """The closed placeholder backend for hosts with no supported OS store.

    Every operation — including the identity probe — fails closed
    with ``CREDENTIAL_BACKEND_UNAVAILABLE``; there is no fallback
    backend, no file store, no environment import, and no in-memory
    substitute.
    """

    __slots__ = ()

    def backend_id(self) -> str:
        raise V2OSCredentialStoreError("CREDENTIAL_BACKEND_UNAVAILABLE")

    def probe_cycle(self) -> None:
        raise V2OSCredentialStoreError("CREDENTIAL_BACKEND_UNAVAILABLE")

    def write(self, service: str, username: str, secret: str) -> None:
        raise V2OSCredentialStoreError("CREDENTIAL_BACKEND_UNAVAILABLE")

    def read_metadata(self, service: str, username: str) -> int | None:
        raise V2OSCredentialStoreError("CREDENTIAL_BACKEND_UNAVAILABLE")

    def read_value(self, service: str, username: str) -> str | None:
        raise V2OSCredentialStoreError("CREDENTIAL_BACKEND_UNAVAILABLE")

    def delete(self, service: str) -> None:
        raise V2OSCredentialStoreError("CREDENTIAL_BACKEND_UNAVAILABLE")


def default_v2_os_credential_backend() -> V2OSCredentialBackendPort:
    """Resolve the platform's default OS credential backend, closed.

    Windows resolves to the real Windows Credential Manager backend
    (constructed lazily — no platform library is imported here); every
    other platform resolves to the unavailable placeholder, whose
    operations all fail closed.
    """

    if sys.platform == "win32":
        return WindowsCredentialManagerV2Backend()
    return _UnavailableV2OSCredentialBackend()


class OSV2CredentialProvider:
    """The production OS-backed v2 credential provider (fail closed).

    Implements the B2 ``V2CredentialProviderPort`` over the injectable
    OS backend (default: this platform's real backend).  Holds no
    secret state at all — no cache, no in-process copy — so every
    ``get_for_call`` re-proves the backend and reads the current entry
    fresh, and ``set``'s raw value exists only between the
    storage-reveal extraction and the backend write.
    """

    __slots__ = ("_backend",)

    def __init__(self, backend: V2OSCredentialBackendPort | None = None) -> None:
        resolved = (
            backend if backend is not None else default_v2_os_credential_backend()
        )
        if not isinstance(resolved, V2OSCredentialBackendPort):
            raise V2CredentialError(
                "backend must implement the v2 OS credential backend port"
            )
        self._backend = resolved

    def set(self, provider: str, secret: V2CredentialSecret) -> V2CredentialMutation:
        """Probe, write through the storage seam, then re-verify the backend."""

        name = _provider_name(provider)
        if not isinstance(secret, V2CredentialSecret):
            raise V2CredentialError("secret must be a V2CredentialSecret")
        self._probe()
        self._backend.write(
            self._service(name),
            _CREDENTIAL_USERNAME,
            secret.reveal_for_storage(_storage_reveal_capability()),
        )
        self._probe()
        return V2CredentialMutation("STORED", name)

    def get_for_call(self, provider: str) -> V2CredentialSecret | None:
        """Re-probe and read the current entry fresh; return only the wrapper."""

        name = _provider_name(provider)
        self._probe()
        value = self._backend.read_value(self._service(name), _CREDENTIAL_USERNAME)
        if value is None:
            return None
        if not isinstance(value, str) or not value:
            # A malformed or empty stored entry fails closed; it is
            # never handed out as a usable credential.
            raise V2OSCredentialStoreError("CREDENTIAL_STORE_FAILED")
        return V2CredentialSecret.from_hidden_input(value)

    def status(self, provider: str) -> V2CredentialStatus:
        """The non-revealing status: metadata only, never the stored value."""

        name = _provider_name(provider)
        self._probe()
        metadata = self._backend.read_metadata(
            self._service(name), _CREDENTIAL_USERNAME
        )
        if metadata is None:
            return V2CredentialStatus(provider=name, configured=False, updated_at=None)
        if isinstance(metadata, bool) or not isinstance(metadata, int):
            raise V2OSCredentialStoreError("CREDENTIAL_STORE_FAILED")
        updated_at = datetime.fromtimestamp(
            metadata / 1000, tz=timezone.utc
        ).isoformat()
        return V2CredentialStatus(provider=name, configured=True, updated_at=updated_at)

    def clear(self, provider: str) -> V2CredentialMutation:
        """Delete the entry; an already-absent entry clears idempotently."""

        name = _provider_name(provider)
        self._probe()
        service = self._service(name)
        present = self._backend.read_metadata(service, _CREDENTIAL_USERNAME) is not None
        if present:
            self._backend.delete(service)
        return V2CredentialMutation("CLEARED", name)

    @staticmethod
    def _service(provider: str) -> str:
        return f"{_CREDENTIAL_SERVICE_PREFIX}{provider}"

    def _probe(self) -> None:
        """Prove the backend is the trusted OS store before trusting it."""

        try:
            backend_id = self._backend.backend_id()
        except V2OSCredentialStoreError:
            raise
        except Exception as exc:  # noqa: BLE001 - fail closed, no backend text
            raise V2OSCredentialStoreError("CREDENTIAL_BACKEND_UNAVAILABLE") from exc
        if backend_id not in OS_CREDENTIAL_BACKEND_IDS_V2:
            raise V2OSCredentialStoreError("CREDENTIAL_BACKEND_UNSAFE")
        try:
            self._backend.probe_cycle()
        except V2OSCredentialStoreError:
            raise
        except Exception as exc:  # noqa: BLE001 - fail closed, no backend text
            raise V2OSCredentialStoreError("CREDENTIAL_BACKEND_UNSAFE") from exc


__all__ = (
    "OSV2CredentialProvider",
    "OS_CREDENTIAL_BACKEND_IDS_V2",
    "OS_CREDENTIAL_STORE_ERROR_CODES_V2",
    "V2OSCredentialBackendPort",
    "V2OSCredentialStoreError",
    "WindowsCredentialManagerV2Backend",
    "default_v2_os_credential_backend",
)

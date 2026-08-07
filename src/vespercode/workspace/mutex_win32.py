"""T09.1 legacy step 9.B: cross-process workspace mutex lease.

``WorkspaceMutex.acquire`` derives one stable Windows named mutex from the
workspace identity digest and returns an explicit ``WorkspaceLeaseV1``
that owns the acquired handle until ``WorkspaceMutex.release``.  Same-
workspace processes exclude each other across process boundaries; a
crashed owner is recovered through the kernel's abandoned-mutex semantics
and is reported explicitly on the lease; different workspaces derive
different mutex names and stay independent; every acquire is bounded by
``timeout_ms`` and fails closed on timeout or error.  Release is
idempotent and closes the owned handle exactly once per acquisition.

Handle ownership is tracked in a per-process registry keyed by a unique
lease id, not by the lease instance: every release goes through the
registry, so no matter how the lease (or any copy of it) is released,
exactly one ``CloseHandle`` happens and a stale handle value can never be
closed twice or close an unrelated kernel object.
"""

from __future__ import annotations

import ctypes
import threading
from typing import Final, Literal

from ctypes import wintypes

from pydantic import (
    BaseModel,
    ConfigDict,
    PrivateAttr,
    StrictBool,
    StrictStr,
    field_validator,
)

from vespercode.canonical.clock import SystemClockV1
from vespercode.canonical.timestamp_v1 import CanonicalTimestampV1
from vespercode.contracts.evidence import _DIGEST_RE
from vespercode.workspace.identity_win32 import WorkspaceIdentityV1

_WAIT_OBJECT_0: Final = 0
_WAIT_ABANDONED: Final = 0x00000080
_WAIT_TIMEOUT: Final = 0x00000102
_MUTEX_NAME_PREFIX: Final = "Local\\VesperCode.WorkspaceLeaseV1."

# Per-process handle ownership: lease id -> owned OS handle value.  The
# registry, not any lease instance, is the single authority on which
# handle is still owned, so an acquired handle is closed exactly once.
_OWNED_HANDLES: dict[int, int] = {}
_REGISTRY_LOCK = threading.Lock()
_NEXT_LEASE_ID = 1


def _next_lease_id() -> int:
    global _NEXT_LEASE_ID
    with _REGISTRY_LOCK:
        lease_id = _NEXT_LEASE_ID
        _NEXT_LEASE_ID += 1
        return lease_id


class WorkspaceMutexError(Exception):
    """Closed failure for mutex naming, waiting, release, or cleanup."""


class WorkspaceMutexTimeoutError(WorkspaceMutexError):
    """The bounded acquire window elapsed without ownership."""


def _kernel32() -> ctypes.WinDLL:
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateMutexW.argtypes = [
        ctypes.c_void_p,
        wintypes.BOOL,
        wintypes.LPCWSTR,
    ]
    kernel32.CreateMutexW.restype = wintypes.HANDLE
    kernel32.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    kernel32.WaitForSingleObject.restype = wintypes.DWORD
    kernel32.ReleaseMutex.argtypes = [wintypes.HANDLE]
    kernel32.ReleaseMutex.restype = wintypes.BOOL
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL
    return kernel32


def _require_sha256_hex(value: str) -> str:
    if _DIGEST_RE.fullmatch(value) is None:
        raise ValueError("digest must be exactly 64 lowercase hexadecimal characters")
    return value


def _require_canonical_timestamp(value: str) -> str:
    CanonicalTimestampV1.parse(value)
    return value


class WorkspaceLeaseV1(BaseModel):
    """One explicit lease that owns the acquired mutex handle.

    The lease binds the identity digest, the exact mutex name, the
    canonical acquisition timestamp, and the abandoned-recovery fact.
    The OS handle is private; ownership is tracked per lease id in the
    module registry, so ``WorkspaceMutex.release`` closes the owned
    handle exactly once no matter which lease instance (or copy) is
    released, and every later release is an idempotent no-op.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal[1]
    identity_digest: StrictStr
    mutex_name: StrictStr
    acquired_at: StrictStr
    recovered_from_abandoned: StrictBool
    _handle: int = PrivateAttr(default=-1)
    _released: bool = PrivateAttr(default=False)
    _lease_id: int = PrivateAttr(default=-1)

    @field_validator("schema_version", mode="before")
    @classmethod
    def _schema_version_is_exact_int(cls, value: object) -> object:
        if not isinstance(value, int) or isinstance(value, bool):
            raise ValueError("schema_version must be the decimal integer 1")
        return value

    @field_validator("identity_digest")
    @classmethod
    def _digest_has_exact_form(cls, value: str) -> str:
        return _require_sha256_hex(value)

    @field_validator("acquired_at")
    @classmethod
    def _timestamp_has_exact_form(cls, value: str) -> str:
        return _require_canonical_timestamp(value)


class WorkspaceMutex:
    """The workspace-identity-derived named mutex (SPEC §4.1 behavior 6)."""

    @staticmethod
    def acquire(identity: WorkspaceIdentityV1, timeout_ms: int) -> WorkspaceLeaseV1:
        """Acquire the identity-derived mutex within the bounded window.

        Returns one explicit lease owning the acquired handle; raises
        ``WorkspaceMutexTimeoutError`` when the window elapses and
        ``WorkspaceMutexError`` for invalid input, identity drift, or
        Win32 failures.  An abandoned owner is recovered by the kernel
        and reported explicitly on the lease.
        """
        if not isinstance(timeout_ms, int) or isinstance(timeout_ms, bool):
            raise WorkspaceMutexError("timeout_ms must be a decimal integer")
        if timeout_ms < 0:
            raise WorkspaceMutexError("timeout_ms must not be negative")
        try:
            identity.verify_integrity()
        except ValueError as error:
            raise WorkspaceMutexError("the workspace identity is not sealed") from error
        name = _MUTEX_NAME_PREFIX + identity.digest
        kernel32 = _kernel32()
        handle = kernel32.CreateMutexW(None, False, name)
        if handle is None:
            raise WorkspaceMutexError(f"CreateMutexW failed: {ctypes.get_last_error()}")
        wait = kernel32.WaitForSingleObject(handle, timeout_ms)
        if wait not in (_WAIT_OBJECT_0, _WAIT_ABANDONED):
            if not kernel32.CloseHandle(handle):
                raise WorkspaceMutexError("mutex handle cleanup could not be verified")
            if wait == _WAIT_TIMEOUT:
                raise WorkspaceMutexTimeoutError(
                    f"workspace mutex {name!r} not acquired within {timeout_ms} ms"
                )
            raise WorkspaceMutexError(
                f"WaitForSingleObject failed: {ctypes.get_last_error()}"
            )
        lease_id = _next_lease_id()
        with _REGISTRY_LOCK:
            _OWNED_HANDLES[lease_id] = int(handle)
        lease = WorkspaceLeaseV1.model_validate(
            {
                "schema_version": 1,
                "identity_digest": identity.digest,
                "mutex_name": name,
                "acquired_at": SystemClockV1().now().value,
                "recovered_from_abandoned": wait == _WAIT_ABANDONED,
            }
        )
        object.__setattr__(lease, "_handle", int(handle))
        object.__setattr__(lease, "_lease_id", lease_id)
        return lease

    @staticmethod
    def release(lease: WorkspaceLeaseV1) -> None:
        """Explicitly release the lease's mutex handle (idempotent).

        The close always goes through the per-process ownership
        registry, so the exact owned handle is closed exactly once per
        acquisition: a second release of the same lease, or a release of
        any copy of the lease, is an idempotent no-op and can never
        close a stale or reused handle value.  A failed close raises
        ``WorkspaceMutexError`` so cleanup can never be silently lost.
        """
        if lease._released:  # noqa: SLF001 - private flag owned by this module
            return
        lease_id = lease._lease_id  # noqa: SLF001
        with _REGISTRY_LOCK:
            owned = _OWNED_HANDLES.get(lease_id)
            if owned is None:
                # The ownership was already released through another
                # instance sharing this lease id: nothing is owned
                # anymore and nothing may be closed.
                _mark_released(lease)
                return
            if not _kernel32().CloseHandle(wintypes.HANDLE(owned)):
                # Keep the registry entry so a retry can still close the
                # owned handle; the release is not silently lost.
                raise WorkspaceMutexError("mutex handle cleanup could not be verified")
            del _OWNED_HANDLES[lease_id]
        _mark_released(lease)


def _mark_released(lease: WorkspaceLeaseV1) -> None:
    object.__setattr__(lease, "_released", True)
    object.__setattr__(lease, "_handle", -1)

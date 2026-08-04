"""T01.2 step 1.D: real cross-process Win32 workspace mutex probes."""

from __future__ import annotations

import ctypes
import multiprocessing
import os
import re
import time
from dataclasses import dataclass
from multiprocessing.synchronize import Event
from queue import Empty

from ctypes import wintypes

_WAIT_OBJECT_0 = 0
_WAIT_ABANDONED = 0x00000080
_WAIT_TIMEOUT = 0x00000102
_VALID_DIGEST = re.compile(r"[0-9a-f]{64}")


@dataclass(frozen=True)
class WorkspaceMutexProbeResultV1:
    workspace_identity_digest: str
    contender_count: int
    maximum_concurrent_holders: int
    timeout_count: int
    cleanup_verified: bool


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


def _mutex_name(workspace_identity_digest: str) -> str:
    if _VALID_DIGEST.fullmatch(workspace_identity_digest) is None:
        raise ValueError(
            "workspace_identity_digest must be 64 lowercase hex characters"
        )
    return f"Local\\VesperCode.WorkspaceLeaseV1.{workspace_identity_digest}"


def _abandon_owner(name: str, acquired: Event) -> None:
    handle = _kernel32().CreateMutexW(None, False, name)
    if handle is None:
        return
    if _kernel32().WaitForSingleObject(handle, 2_000) == _WAIT_OBJECT_0:
        acquired.set()
        os._exit(0)
    _kernel32().CloseHandle(handle)


def _recover_abandoned_owner(name: str) -> bool:
    kernel32 = _kernel32()
    handle = kernel32.CreateMutexW(None, False, name)
    if handle is None:
        return False
    try:
        if kernel32.WaitForSingleObject(handle, 2_000) != _WAIT_ABANDONED:
            return False
        return bool(kernel32.ReleaseMutex(handle))
    finally:
        kernel32.CloseHandle(handle)


def _contender(
    name: str,
    timeout_ms: int,
    hold_ms: int,
    start: Event,
    current_holders: multiprocessing.sharedctypes.Synchronized[int],
    maximum_holders: multiprocessing.sharedctypes.Synchronized[int],
    counter_lock: multiprocessing.synchronize.Lock,
    outcomes: multiprocessing.queues.Queue[tuple[str, bool]],
) -> None:
    start.wait(5)
    kernel32 = _kernel32()
    handle = kernel32.CreateMutexW(None, False, name)
    if handle is None:
        outcomes.put(("ERROR", False))
        return
    acquired = False
    released = False
    closed = False
    try:
        wait = kernel32.WaitForSingleObject(handle, timeout_ms)
        if wait in (_WAIT_OBJECT_0, _WAIT_ABANDONED):
            acquired = True
            with counter_lock:
                current_holders.value += 1
                maximum_holders.value = max(
                    maximum_holders.value, current_holders.value
                )
            time.sleep(hold_ms / 1_000)
            with counter_lock:
                current_holders.value -= 1
            released = bool(kernel32.ReleaseMutex(handle))
            outcomes.put(("ABANDONED" if wait == _WAIT_ABANDONED else "HELD", released))
        elif wait == _WAIT_TIMEOUT:
            outcomes.put(("TIMEOUT", True))
        else:
            outcomes.put(("ERROR", False))
    finally:
        if acquired and not released:
            outcomes.put(("ERROR", False))
        closed = bool(kernel32.CloseHandle(handle))
        if not closed:
            outcomes.put(("ERROR", False))


def probe_workspace_mutex(
    workspace_identity_digest: str,
    contender_count: int,
    timeout_ms: int,
) -> WorkspaceMutexProbeResultV1:
    """Observe a digest-bound Windows mutex with competing child processes."""
    if contender_count < 2:
        raise ValueError("contender_count must be at least two")
    if timeout_ms < 0:
        raise ValueError("timeout_ms must not be negative")
    name = _mutex_name(workspace_identity_digest)
    context = multiprocessing.get_context("spawn")
    kernel32 = _kernel32()
    keeper = kernel32.CreateMutexW(None, False, name)
    keeper_closed = False
    try:
        abandoned_acquired = context.Event()
        abandoned_owner = context.Process(
            target=_abandon_owner,
            args=(name, abandoned_acquired),
        )
        abandoned_owner.start()
        if not abandoned_acquired.wait(5):
            abandoned_owner.join(5)
            keeper_closed = bool(kernel32.CloseHandle(keeper))
            return WorkspaceMutexProbeResultV1(
                workspace_identity_digest,
                contender_count,
                0,
                0,
                keeper_closed,
            )
        abandoned_owner.join(5)
        abandoned_observed = _recover_abandoned_owner(name)
    finally:
        if not keeper_closed:
            keeper_closed = bool(kernel32.CloseHandle(keeper))
    start = context.Event()
    current_holders = context.Value("i", 0)
    maximum_holders = context.Value("i", 0)
    counter_lock = context.Lock()
    outcomes = context.Queue()
    hold_ms = 100 if timeout_ms <= 100 else 20
    contenders = [
        context.Process(
            target=_contender,
            args=(
                name,
                timeout_ms,
                hold_ms,
                start,
                current_holders,
                maximum_holders,
                counter_lock,
                outcomes,
            ),
        )
        for _ in range(contender_count)
    ]
    for contender in contenders:
        contender.start()
    start.set()
    for contender in contenders:
        contender.join(10)
    observed: list[tuple[str, bool]] = []
    for _ in contenders:
        try:
            observed.append(outcomes.get(timeout=2))
        except Empty:
            observed.append(("ERROR", False))
    all_exited = all(contender.exitcode == 0 for contender in contenders)
    timeout_count = sum(status == "TIMEOUT" for status, _ in observed)
    cleanup_verified = (
        all_exited
        and abandoned_owner.exitcode == 0
        and abandoned_observed
        and all(ok for _, ok in observed)
        and current_holders.value == 0
        and maximum_holders.value == 1
        and keeper_closed
    )
    return WorkspaceMutexProbeResultV1(
        workspace_identity_digest=workspace_identity_digest,
        contender_count=contender_count,
        maximum_concurrent_holders=maximum_holders.value,
        timeout_count=timeout_count,
        cleanup_verified=cleanup_verified,
    )

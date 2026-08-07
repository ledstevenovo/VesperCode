"""T09.1 legacy step 9.B: real cross-process workspace mutex tests.

Runs only under ``-m windows_integration`` on the project Windows host.
Proves that exactly one process owns the identity-derived named mutex,
that a contender child process times out with zero workspace mutation,
that release permits a later acquire, that an abandoned owner is
recovered explicitly, and that different workspaces stay independent.
Every child process exits cleanly and every handle is closed.
"""

from __future__ import annotations

import ctypes
import hashlib
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Final, Literal

import pytest

from ctypes import wintypes

from vespercode.workspace.identity_win32 import (
    WorkspaceIdentityV1,
    resolve_workspace_identity,
)
from vespercode.workspace.mutex_win32 import WorkspaceLeaseV1, WorkspaceMutex

pytestmark = pytest.mark.windows_integration

_REPO_ROOT: Final = Path(__file__).resolve().parents[3]
_MUTEX_PREFIX: Final = "Local\\VesperCode.WorkspaceLeaseV1."

_CHILD_ACQUIRE_SCRIPT: Final = """
import json
import sys

from vespercode.workspace.identity_win32 import WorkspaceIdentityV1
from vespercode.workspace.mutex_win32 import (
    WorkspaceMutex,
    WorkspaceMutexTimeoutError,
)

identity = WorkspaceIdentityV1.model_validate(json.loads(sys.stdin.read()))
timeout_ms = int(sys.argv[1])
try:
    lease = WorkspaceMutex.acquire(identity, timeout_ms=timeout_ms)
except WorkspaceMutexTimeoutError:
    sys.stdout.write("TIMED_OUT")
    sys.exit(0)
except Exception:
    sys.stdout.write("ERROR")
    sys.exit(0)
else:
    WorkspaceMutex.release(lease)
    sys.stdout.write("ACQUIRED")
    sys.exit(0)
"""

_CHILD_ABANDON_SCRIPT: Final = """
import json
import os
import sys

from vespercode.workspace.identity_win32 import WorkspaceIdentityV1
from vespercode.workspace.mutex_win32 import WorkspaceMutex

identity = WorkspaceIdentityV1.model_validate(json.loads(sys.stdin.read()))
lease = WorkspaceMutex.acquire(identity, timeout_ms=2000)
del lease
os._exit(0)
"""


@dataclass(frozen=True)
class ChildAcquireResultV1:
    """One child-process acquire outcome: ACQUIRED, TIMED_OUT, or ERROR."""

    kind: Literal["ACQUIRED", "TIMED_OUT", "ERROR"]


def child_process_try_acquire(
    identity: WorkspaceIdentityV1, timeout_ms: int
) -> ChildAcquireResultV1:
    """Run one fresh child process that tries to acquire the mutex."""
    completed = subprocess.run(
        [sys.executable, "-c", _CHILD_ACQUIRE_SCRIPT, str(timeout_ms)],
        input=identity.model_dump_json(),
        capture_output=True,
        text=True,
        cwd=_REPO_ROOT,
        timeout=30,
        check=False,
    )
    output = completed.stdout.strip()
    if output == "ACQUIRED":
        return ChildAcquireResultV1("ACQUIRED")
    if output == "TIMED_OUT":
        return ChildAcquireResultV1("TIMED_OUT")
    return ChildAcquireResultV1("ERROR")


def child_process_abandon(identity: WorkspaceIdentityV1) -> None:
    """Run one child that acquires the mutex and exits without release."""
    completed = subprocess.run(
        [sys.executable, "-c", _CHILD_ABANDON_SCRIPT],
        input=identity.model_dump_json(),
        capture_output=True,
        text=True,
        cwd=_REPO_ROOT,
        timeout=30,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr


def _workspace_snapshot_digest(root: Path) -> str:
    """A deterministic digest of every object name and byte under *root*."""
    hasher = hashlib.sha256()
    for path in sorted(root.rglob("*")):
        relative = str(path.relative_to(root)).replace("\\", "/")
        hasher.update(relative.encode("utf-8"))
        if path.is_file():
            hasher.update(path.read_bytes())
    return hasher.hexdigest()


def _populate(root: Path) -> None:
    (root / "safe.txt").write_text("safe\n", encoding="utf-8")
    (root / "ordinary.txt").write_text("ordinary\n", encoding="utf-8")


@pytest.fixture
def workspace_identity() -> Iterator[WorkspaceIdentityV1]:
    """One disposable workspace that stays alive for the whole test.

    Generator fixture: the cleanup runs at teardown, so the mutation-
    evidence digests observe a real directory during the test.
    """
    root = Path(tempfile.mkdtemp(prefix="vesper_mutex_"))
    _populate(root)
    try:
        yield resolve_workspace_identity(root)
    finally:
        shutil.rmtree(root, ignore_errors=True)
        assert not root.exists(), "workspace residue remains"


@pytest.fixture
def second_workspace_identity() -> Iterator[WorkspaceIdentityV1]:
    root = Path(tempfile.mkdtemp(prefix="vesper_mutex_other_"))
    _populate(root)
    try:
        yield resolve_workspace_identity(root)
    finally:
        shutil.rmtree(root, ignore_errors=True)
        assert not root.exists(), "workspace residue remains"


def test_second_process_cannot_acquire_same_workspace_mutex(
    workspace_identity: WorkspaceIdentityV1,
) -> None:
    first = WorkspaceMutex.acquire(workspace_identity, timeout_ms=1000)
    try:
        assert (
            child_process_try_acquire(workspace_identity, timeout_ms=50).kind
            == "TIMED_OUT"
        )
    finally:
        WorkspaceMutex.release(first)


def test_named_mutex_timeout_recovery_matrix(
    workspace_identity: WorkspaceIdentityV1,
    second_workspace_identity: WorkspaceIdentityV1,
) -> None:
    """Timeout/recovery matrix (Expected 9.B: 0) — every 9.B row pinned.

    Rows follow the PLAN registry 9.B authority: one process acquires; a
    second process times out without workspace mutation; release permits
    a later acquire; abandoned-owner recovery is explicit and leaves one
    owner.
    """
    root = Path(workspace_identity.canonical_absolute_path)
    snapshot_before = _workspace_snapshot_digest(root)

    # One process acquires the lease with the exact identity binding.
    first = WorkspaceMutex.acquire(workspace_identity, timeout_ms=1000)
    assert isinstance(first, WorkspaceLeaseV1)
    assert first.identity_digest == workspace_identity.digest
    assert first.mutex_name == _MUTEX_PREFIX + workspace_identity.digest
    assert first.recovered_from_abandoned is False

    # A second process times out and the workspace is not mutated.
    assert (
        child_process_try_acquire(workspace_identity, timeout_ms=50).kind == "TIMED_OUT"
    )
    assert _workspace_snapshot_digest(root) == snapshot_before

    # Release permits a later acquire (same process re-acquires).
    WorkspaceMutex.release(first)
    later = WorkspaceMutex.acquire(workspace_identity, timeout_ms=1000)
    assert later.identity_digest == workspace_identity.digest

    # A zero timeout contends immediately and fails closed.  (Windows
    # mutexes are re-entrant for the owning thread, so the zero-timeout
    # contention must come from a fresh child process.)
    assert (
        child_process_try_acquire(workspace_identity, timeout_ms=0).kind == "TIMED_OUT"
    )
    WorkspaceMutex.release(later)

    # Explicit release is idempotent: a second release is a no-op.
    WorkspaceMutex.release(later)

    # Abandoned-owner recovery: a crashed owner leaves the mutex abandoned;
    # the next acquire recovers it explicitly and release leaves one owner.
    # A named mutex object dies with its last handle, so the recovering
    # process must already hold a handle (as a waiting contender would)
    # while the owner crashes — that is exactly the production shape.
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateMutexW.argtypes = [
        ctypes.c_void_p,
        wintypes.BOOL,
        wintypes.LPCWSTR,
    ]
    kernel32.CreateMutexW.restype = wintypes.HANDLE
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL
    contender_handle = kernel32.CreateMutexW(
        None, False, _MUTEX_PREFIX + workspace_identity.digest
    )
    assert contender_handle is not None
    try:
        child_process_abandon(workspace_identity)
        recovered = WorkspaceMutex.acquire(workspace_identity, timeout_ms=2000)
        assert recovered.recovered_from_abandoned is True
        WorkspaceMutex.release(recovered)
        after_recovery = WorkspaceMutex.acquire(workspace_identity, timeout_ms=1000)
        assert after_recovery.recovered_from_abandoned is False
        WorkspaceMutex.release(after_recovery)
    finally:
        assert bool(kernel32.CloseHandle(contender_handle))

    # Different workspaces stay independent: both hold concurrently.
    other = WorkspaceMutex.acquire(second_workspace_identity, timeout_ms=1000)
    second = WorkspaceMutex.acquire(workspace_identity, timeout_ms=1000)
    assert other.mutex_name != second.mutex_name
    WorkspaceMutex.release(second)
    WorkspaceMutex.release(other)

    # Handle ownership is registry-tracked per lease id: releasing a
    # copied lease closes the owned handle exactly once, and releasing
    # the original afterwards is an idempotent no-op — a stale copy can
    # never close a reused handle value.
    copied = WorkspaceMutex.acquire(workspace_identity, timeout_ms=1000)
    alias = copied.model_copy()
    WorkspaceMutex.release(alias)
    WorkspaceMutex.release(copied)
    reacquired = WorkspaceMutex.acquire(workspace_identity, timeout_ms=1000)
    assert reacquired.recovered_from_abandoned is False
    WorkspaceMutex.release(reacquired)
    # The reverse order (original first, then the copy) is equally safe.
    copied = WorkspaceMutex.acquire(workspace_identity, timeout_ms=1000)
    alias = copied.model_copy()
    WorkspaceMutex.release(copied)
    WorkspaceMutex.release(alias)
    reacquired = WorkspaceMutex.acquire(workspace_identity, timeout_ms=1000)
    assert reacquired.recovered_from_abandoned is False
    WorkspaceMutex.release(reacquired)

    # The workspace is still byte-identical after the full matrix.
    assert _workspace_snapshot_digest(root) == snapshot_before

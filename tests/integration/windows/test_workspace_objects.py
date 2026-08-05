"""T09.1 legacy step 9.A: real Win32 workspace-object identity tests.

Runs only under ``-m windows_integration`` on the project Windows host.
Proves handle-derived final-object identity and every closed rejection
(reparse, hard link, ADS, case alias, identity drift, unsupported volume,
ACL failure) against a disposable NTFS workspace, and deletes every
generated object in ``finally`` so the module leaves zero residue.
"""

from __future__ import annotations

import ctypes
import os
import shutil
import subprocess
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Final

import pytest
import win32api  # type: ignore[import-untyped]
import win32security  # type: ignore[import-untyped]

from ctypes import wintypes

from src.vespercode.canonical.path_v1 import CanonicalRelativePathV1
from src.vespercode.workspace.identity_win32 import (
    WorkspaceIdentityV1,
    WorkspaceObjectRejectedV1,
    resolve_workspace_identity,
)
from src.vespercode.workspace.object_win32 import (
    FinalObjectIdentityV1,
    inspect_workspace_object,
)

pytestmark = pytest.mark.windows_integration

_READ_CONTROL: Final = 0x00020000
_WRITE_DACL: Final = 0x00040000
_FILE_READ_ATTRIBUTES: Final = 0x00000080
_GENERIC_ALL: Final = 0x10000000
_FILE_FLAG_BACKUP_SEMANTICS: Final = 0x02000000
_FILE_SHARE_ALL: Final = 0x00000007
_OPEN_EXISTING: Final = 3
_INVALID_HANDLE: Final = ctypes.c_void_p(-1).value


def _make_junction(link: Path, target: Path) -> None:
    """Create a real NTFS junction (no admin rights required)."""
    result = subprocess.run(
        ["cmd", "/c", "mklink", "/J", str(link), str(target)],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr


def _kernel32() -> ctypes.WinDLL:
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateFileW.argtypes = [
        wintypes.LPCWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
        ctypes.c_void_p,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.HANDLE,
    ]
    kernel32.CreateFileW.restype = wintypes.HANDLE
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL
    return kernel32


def _open_read_control(path: Path) -> bool:
    """True exactly when a READ_CONTROL handle to *path* can be opened."""
    handle = _kernel32().CreateFileW(
        str(path),
        _READ_CONTROL | _FILE_READ_ATTRIBUTES,
        _FILE_SHARE_ALL,
        None,
        _OPEN_EXISTING,
        _FILE_FLAG_BACKUP_SEMANTICS,
        None,
    )
    if handle == _INVALID_HANDLE:
        return False
    _kernel32().CloseHandle(handle)
    return True


@contextmanager
def _deny_read_control(path: Path) -> Iterator[None]:
    """Deny the current user READ_CONTROL, then restore the permissive DACL.

    The full-rights handle is opened while the DACL is permissive; the
    restore goes through that pre-opened handle so the deny can never
    block cleanup (the owner's rights do not include READ_CONTROL
    implicitly).
    """
    process_token = win32security.OpenProcessToken(
        win32api.GetCurrentProcess(), win32security.TOKEN_QUERY
    )
    try:
        user_sid = win32security.GetTokenInformation(
            process_token, win32security.TokenUser
        )[0]
    finally:
        win32api.CloseHandle(process_token)
    system_sid, _, _ = win32security.LookupAccountName(None, "SYSTEM")
    permissive = win32security.ACL()
    permissive.AddAccessAllowedAce(win32security.ACL_REVISION, _GENERIC_ALL, user_sid)
    permissive.AddAccessAllowedAce(win32security.ACL_REVISION, _GENERIC_ALL, system_sid)
    deny = win32security.ACL()
    deny.AddAccessDeniedAce(win32security.ACL_REVISION, _READ_CONTROL, user_sid)
    handle = _kernel32().CreateFileW(
        str(path),
        _READ_CONTROL | _WRITE_DACL | _FILE_READ_ATTRIBUTES,
        _FILE_SHARE_ALL,
        None,
        _OPEN_EXISTING,
        _FILE_FLAG_BACKUP_SEMANTICS,
        None,
    )
    assert handle != _INVALID_HANDLE, "cannot open the ACL probe target"
    try:
        win32security.SetSecurityInfo(
            handle,
            win32security.SE_FILE_OBJECT,
            win32security.DACL_SECURITY_INFORMATION,
            None,
            None,
            deny,
            None,
        )
        yield
    finally:
        win32security.SetSecurityInfo(
            handle,
            win32security.SE_FILE_OBJECT,
            win32security.DACL_SECURITY_INFORMATION,
            None,
            None,
            permissive,
            None,
        )
        _kernel32().CloseHandle(handle)


def _populate_workspace(root: Path) -> None:
    (root / "safe.txt").write_text("safe\n", encoding="utf-8")
    (root / "ordinary-directory").mkdir()
    nested = root / "nested"
    nested.mkdir()
    (nested / "deep.txt").write_text("deep\n", encoding="utf-8")


@pytest.fixture
def workspace_identity() -> Iterator[WorkspaceIdentityV1]:
    """One disposable NTFS workspace with a sealed real root identity."""
    root = Path(tempfile.mkdtemp(prefix="vesper_object_"))
    _populate_workspace(root)
    try:
        yield resolve_workspace_identity(root)
    finally:
        shutil.rmtree(root, ignore_errors=True)
        assert not root.exists(), "workspace residue remains"


@pytest.fixture
def reparse_path(workspace_identity: WorkspaceIdentityV1) -> CanonicalRelativePathV1:
    """A real junction inside the workspace (reparse tag 0xA0000003)."""
    root = Path(workspace_identity.canonical_absolute_path)
    _make_junction(root / "reparse-link", root / "safe.txt")
    return CanonicalRelativePathV1("reparse-link")


def test_reparse_final_object_is_rejected(
    workspace_identity: WorkspaceIdentityV1,
    reparse_path: CanonicalRelativePathV1,
) -> None:
    with pytest.raises(WorkspaceObjectRejectedV1) as error:
        inspect_workspace_object(workspace_identity, reparse_path)
    assert error.value.error_code == "UNSUPPORTED_WORKSPACE_OBJECT"


def test_workspace_object_sentinel_matrix(
    workspace_identity: WorkspaceIdentityV1,
) -> None:
    """Sentinel matrix (Expected 9.A: 0) — every 9.A rejection row pinned.

    Rows follow the PLAN registry 9.A authority: reparse final object,
    non-directory, identity drift, case alias, unsupported volume, or ACL
    failure is rejected; an exact stable directory handle passes.  ADS and
    hard-link rows are added from GREEN-2 (SPEC §1.4.3).
    """
    root = Path(workspace_identity.canonical_absolute_path)
    inspector_identity = inspect_workspace_object(
        workspace_identity, CanonicalRelativePathV1("ordinary-directory")
    )
    # An exact stable directory handle passes with every fact sealed.
    assert isinstance(inspector_identity, FinalObjectIdentityV1)
    assert inspector_identity.object_kind == "DIRECTORY"
    assert inspector_identity.link_count == 1
    assert inspector_identity.reparse_tag == 0
    assert inspector_identity.acl_observable is True
    assert inspector_identity.root_ancestry_proven is True
    assert inspector_identity.volume_serial_number == (
        workspace_identity.volume_serial_number
    )
    inspector_identity.verify_integrity()
    # An exact stable file handle passes with kind FILE.
    file_identity = inspect_workspace_object(
        workspace_identity, CanonicalRelativePathV1("safe.txt")
    )
    assert file_identity.object_kind == "FILE"
    file_identity.verify_integrity()

    # Reparse final object is rejected (the RED target row).
    _make_junction(root / "reparse-link", root / "safe.txt")
    with pytest.raises(WorkspaceObjectRejectedV1) as error:
        inspect_workspace_object(
            workspace_identity, CanonicalRelativePathV1("reparse-link")
        )
    assert error.value.error_code == "UNSUPPORTED_WORKSPACE_OBJECT"

    # Hard link (link count 2) is rejected for regular files.
    os.link(root / "safe.txt", root / "hard-copy.txt")
    with pytest.raises(WorkspaceObjectRejectedV1) as error:
        inspect_workspace_object(
            workspace_identity, CanonicalRelativePathV1("hard-copy.txt")
        )
    assert error.value.error_code == "UNSUPPORTED_WORKSPACE_OBJECT"

    # A named alternate data stream makes the base object unsupported.
    with open(str(root / "safe.txt") + ":secret", "w", encoding="utf-8") as stream:
        stream.write("hidden")
    with pytest.raises(WorkspaceObjectRejectedV1) as error:
        inspect_workspace_object(
            workspace_identity, CanonicalRelativePathV1("safe.txt")
        )
    assert error.value.error_code == "UNSUPPORTED_WORKSPACE_OBJECT"

    # A case alias of an existing object is rejected by final-path identity.
    with pytest.raises(WorkspaceObjectRejectedV1) as error:
        inspect_workspace_object(
            workspace_identity, CanonicalRelativePathV1("Safe.txt")
        )
    assert error.value.error_code == "PATH_ALIAS_COLLISION"

    # An identity whose volume drifts from the live root is rejected.
    drifted_volume = workspace_identity.model_copy(
        update={"volume_serial_number": workspace_identity.volume_serial_number + 1}
    )
    with pytest.raises(WorkspaceObjectRejectedV1) as error:
        inspect_workspace_object(drifted_volume, CanonicalRelativePathV1("safe.txt"))
    assert error.value.error_code == "WORKSPACE_OBJECT_VOLUME_MISMATCH"

    # An identity whose final object file id drifts is rejected.
    drifted_id = workspace_identity.model_copy(
        update={"final_object_file_id_128_hex": "0" * 32}
    )
    with pytest.raises(WorkspaceObjectRejectedV1) as error:
        inspect_workspace_object(drifted_id, CanonicalRelativePathV1("safe.txt"))
    assert error.value.error_code == "WORKSPACE_OBJECT_IDENTITY_UNPROVEN"

    # Real identity drift: the root directory is replaced by a new object.
    moved = root.parent / (root.name + "_moved")
    if moved.exists():
        shutil.rmtree(moved, ignore_errors=True)
    os.rename(root, moved)
    replaced = root.parent / root.name
    replaced.mkdir()
    try:
        with pytest.raises(WorkspaceObjectRejectedV1) as error:
            inspect_workspace_object(
                workspace_identity, CanonicalRelativePathV1("safe.txt")
            )
        assert error.value.error_code == "WORKSPACE_OBJECT_IDENTITY_UNPROVEN"
    finally:
        os.rmdir(replaced)
        os.rename(moved, root)

    # An unreadable ACL (READ_CONTROL denied) makes the object unprovable.
    acl_target = root / "acl.txt"
    acl_target.write_text("acl\n", encoding="utf-8")
    with _deny_read_control(acl_target):
        assert _open_read_control(acl_target) is False
        with pytest.raises(WorkspaceObjectRejectedV1) as error:
            inspect_workspace_object(
                workspace_identity, CanonicalRelativePathV1("acl.txt")
            )
        assert error.value.error_code == "WORKSPACE_OBJECT_ACL_UNPROVEN"

    # A file root is rejected by resolve (non-directory final object).
    with pytest.raises(WorkspaceObjectRejectedV1) as error:
        resolve_workspace_identity(root / "safe.txt")
    assert error.value.error_code == "WORKSPACE_ROOT_NOT_DIRECTORY"

    # A missing root is rejected by resolve.
    with pytest.raises(WorkspaceObjectRejectedV1) as error:
        resolve_workspace_identity(root / "does-not-exist")
    assert error.value.error_code == "WORKSPACE_ROOT_NOT_FOUND"

    # A reparse root is rejected by resolve.
    _make_junction(root / "reparse-root", root / "nested")
    with pytest.raises(WorkspaceObjectRejectedV1) as error:
        resolve_workspace_identity(root / "reparse-root")
    assert error.value.error_code == "UNSUPPORTED_WORKSPACE_OBJECT"

    # A root directory carrying a named alternate data stream is rejected.
    ads_root = root / "ads-root"
    ads_root.mkdir()
    with open(str(ads_root) + ":secret", "w", encoding="utf-8") as stream:
        stream.write("hidden")
    with pytest.raises(WorkspaceObjectRejectedV1) as error:
        resolve_workspace_identity(ads_root)
    assert error.value.error_code == "UNSUPPORTED_WORKSPACE_OBJECT"

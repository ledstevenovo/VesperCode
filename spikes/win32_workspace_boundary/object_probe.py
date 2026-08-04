"""T01.2 step 1.C: handle-derived Win32 workspace-object probes.

This module observes objects only.  It deliberately does not acquire a
workspace lease and does not decide the aggregate feasibility gate.
"""

from __future__ import annotations

import ctypes
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from ctypes import wintypes

from spikes.win32_workspace_boundary.evaluator import (
    BoundaryObservationSequenceV1,
    BoundaryObservationV1,
)

_FILE_READ_ATTRIBUTES = 0x0080
_READ_CONTROL = 0x00020000
_FILE_SHARE_READ = 0x00000001
_FILE_SHARE_WRITE = 0x00000002
_FILE_SHARE_DELETE = 0x00000004
_OPEN_EXISTING = 3
_FILE_FLAG_BACKUP_SEMANTICS = 0x02000000
_FILE_FLAG_OPEN_REPARSE_POINT = 0x00200000
_FILE_ID_INFO = 18
_FILE_ATTRIBUTE_TAG_INFO = 9
_SE_FILE_OBJECT = 1
_OWNER_SECURITY_INFORMATION = 0x00000001
_GROUP_SECURITY_INFORMATION = 0x00000002
_DACL_SECURITY_INFORMATION = 0x00000004
_INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value
_DEVICE_NAMES = frozenset({"CON", "PRN", "AUX", "NUL", "COM1", "LPT1"})


class _FileIdInfo(ctypes.Structure):
    _fields_ = [
        ("volume_serial_number", ctypes.c_longlong),
        ("file_id", ctypes.c_ubyte * 16),
    ]


class _ByHandleFileInformation(ctypes.Structure):
    _fields_ = [
        ("file_attributes", wintypes.DWORD),
        ("creation_time", wintypes.FILETIME),
        ("last_access_time", wintypes.FILETIME),
        ("last_write_time", wintypes.FILETIME),
        ("volume_serial_number", wintypes.DWORD),
        ("file_size_high", wintypes.DWORD),
        ("file_size_low", wintypes.DWORD),
        ("number_of_links", wintypes.DWORD),
        ("file_index_high", wintypes.DWORD),
        ("file_index_low", wintypes.DWORD),
    ]


class _FileAttributeTagInfo(ctypes.Structure):
    _fields_ = [("file_attributes", wintypes.DWORD), ("reparse_tag", wintypes.DWORD)]


@dataclass(frozen=True)
class WorkspaceObjectIdentityV1:
    """The identity obtained from a Win32 handle, never path text alone."""

    canonical_absolute_path: str
    volume_serial_number: int
    file_id_128: bytes
    object_kind: Literal["FILE", "DIRECTORY"]
    link_count: int
    reparse_tag: int


@dataclass(frozen=True)
class WorkspaceBoundaryCaseV1:
    """One probe path, relative to the workspace unless it is unsafe syntax."""

    code: str
    lexical_path: str


@dataclass(frozen=True)
class BoundaryCaseManifestV1:
    """Closed, ordered collection of workspace-boundary probe paths."""

    cases: tuple[WorkspaceBoundaryCaseV1, ...]


@dataclass(frozen=True)
class WorkspaceObjectProbeResultV1:
    observations: BoundaryObservationSequenceV1
    cleanup_verified: bool


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
    kernel32.GetFileInformationByHandleEx.argtypes = [
        wintypes.HANDLE,
        ctypes.c_int,
        ctypes.c_void_p,
        wintypes.DWORD,
    ]
    kernel32.GetFileInformationByHandleEx.restype = wintypes.BOOL
    kernel32.GetFileInformationByHandle.argtypes = [
        wintypes.HANDLE,
        ctypes.POINTER(_ByHandleFileInformation),
    ]
    kernel32.GetFileInformationByHandle.restype = wintypes.BOOL
    kernel32.GetFinalPathNameByHandleW.argtypes = [
        wintypes.HANDLE,
        wintypes.LPWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
    ]
    kernel32.GetFinalPathNameByHandleW.restype = wintypes.DWORD
    return kernel32


def _open_handle(path: Path, *, open_reparse_point: bool) -> wintypes.HANDLE:
    flags = _FILE_FLAG_BACKUP_SEMANTICS
    if open_reparse_point:
        flags |= _FILE_FLAG_OPEN_REPARSE_POINT
    handle = _kernel32().CreateFileW(
        str(path),
        _FILE_READ_ATTRIBUTES | _READ_CONTROL,
        _FILE_SHARE_READ | _FILE_SHARE_WRITE | _FILE_SHARE_DELETE,
        None,
        _OPEN_EXISTING,
        flags,
        None,
    )
    if handle == _INVALID_HANDLE_VALUE:
        raise OSError(ctypes.get_last_error(), f"cannot open {path}")
    return wintypes.HANDLE(handle)


def _close_handle(handle: wintypes.HANDLE) -> bool:
    return bool(_kernel32().CloseHandle(handle))


def _acl_is_observable(handle: wintypes.HANDLE) -> bool:
    advapi32 = ctypes.WinDLL("advapi32", use_last_error=True)
    security_descriptor = ctypes.c_void_p()
    get_security_info = advapi32.GetSecurityInfo
    get_security_info.argtypes = [
        wintypes.HANDLE,
        ctypes.c_int,
        wintypes.DWORD,
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.POINTER(ctypes.c_void_p),
    ]
    get_security_info.restype = wintypes.DWORD
    result = get_security_info(
        handle,
        _SE_FILE_OBJECT,
        _OWNER_SECURITY_INFORMATION
        | _GROUP_SECURITY_INFORMATION
        | _DACL_SECURITY_INFORMATION,
        None,
        None,
        None,
        None,
        ctypes.byref(security_descriptor),
    )
    if result != 0:
        return False
    try:
        return security_descriptor.value is not None
    finally:
        if security_descriptor.value is not None:
            ctypes.WinDLL("kernel32", use_last_error=True).LocalFree(
                security_descriptor
            )


def _identity_from_handle(handle: wintypes.HANDLE) -> WorkspaceObjectIdentityV1:
    kernel32 = _kernel32()
    file_id = _FileIdInfo()
    if not kernel32.GetFileInformationByHandleEx(
        handle, _FILE_ID_INFO, ctypes.byref(file_id), ctypes.sizeof(file_id)
    ):
        raise OSError(
            ctypes.get_last_error(), "GetFileInformationByHandleEx(FileIdInfo)"
        )
    basic = _ByHandleFileInformation()
    if not kernel32.GetFileInformationByHandle(handle, ctypes.byref(basic)):
        raise OSError(ctypes.get_last_error(), "GetFileInformationByHandle")
    tag_info = _FileAttributeTagInfo()
    if not kernel32.GetFileInformationByHandleEx(
        handle,
        _FILE_ATTRIBUTE_TAG_INFO,
        ctypes.byref(tag_info),
        ctypes.sizeof(tag_info),
    ):
        raise OSError(
            ctypes.get_last_error(),
            "GetFileInformationByHandleEx(FileAttributeTagInfo)",
        )
    buffer = ctypes.create_unicode_buffer(32768)
    length = kernel32.GetFinalPathNameByHandleW(handle, buffer, len(buffer), 0)
    if length == 0 or length >= len(buffer):
        raise OSError(ctypes.get_last_error(), "GetFinalPathNameByHandleW")
    final_path = buffer.value.removeprefix("\\\\?\\")
    object_kind: Literal["FILE", "DIRECTORY"] = (
        "DIRECTORY" if basic.file_attributes & 0x10 else "FILE"
    )
    return WorkspaceObjectIdentityV1(
        canonical_absolute_path=os.path.normcase(os.path.abspath(final_path)),
        volume_serial_number=int(file_id.volume_serial_number),
        file_id_128=bytes(file_id.file_id),
        object_kind=object_kind,
        link_count=int(basic.number_of_links),
        reparse_tag=int(tag_info.reparse_tag),
    )


def _unsafe_code(raw_path: str) -> str | None:
    if raw_path.startswith(("\\\\", "//")):
        return "UNC_OBJECT_REJECTED"
    if ":" in raw_path:
        return "ADS_OBJECT_REJECTED"
    if raw_path.upper() in _DEVICE_NAMES:
        return "DEVICE_OBJECT_REJECTED"
    return None


def _unproven_observation(code: str, lexical_path: str) -> BoundaryObservationV1:
    return BoundaryObservationV1(
        code=code,
        lexical_path=lexical_path,
        final_path="",
        expected_volume_serial=0,
        observed_volume_serial=0,
        expected_file_id_128=b"",
        observed_file_id_128=b"",
        object_kind="FILE",
        link_count=0,
        reparse_tag=0,
        acl_observable=False,
    )


def _observation_for_case(
    workspace: Path,
    case: WorkspaceBoundaryCaseV1,
    seen_identities: set[tuple[int, bytes]],
) -> tuple[BoundaryObservationV1, bool]:
    unsafe_code = _unsafe_code(case.lexical_path)
    if unsafe_code is not None:
        return _unproven_observation(unsafe_code, case.lexical_path), True
    candidate = workspace / case.lexical_path
    lexical_handle = _open_handle(candidate, open_reparse_point=True)
    closed_lexical = False
    final_handle: wintypes.HANDLE | None = None
    closed_final = False
    try:
        lexical_identity = _identity_from_handle(lexical_handle)
        acl_observable = _acl_is_observable(lexical_handle)
        if lexical_identity.reparse_tag != 0:
            final_handle = _open_handle(candidate, open_reparse_point=False)
            final_identity = _identity_from_handle(final_handle)
        else:
            final_identity = lexical_identity
        identity_key = (
            final_identity.volume_serial_number,
            final_identity.file_id_128,
        )
        if lexical_identity.reparse_tag != 0:
            code = "REPARSE_OBJECT_REJECTED"
        elif final_identity.link_count != 1:
            code = "HARD_LINK_OBJECT_REJECTED"
        elif identity_key in seen_identities:
            code = "COLLISION_OBJECT_REJECTED"
        elif final_identity.object_kind == "DIRECTORY":
            code = "DIRECTORY_OBJECT_OBSERVED"
        else:
            code = "FILE_OBJECT_OBSERVED"
        seen_identities.add(identity_key)
        return (
            BoundaryObservationV1(
                code=code,
                lexical_path=str(candidate),
                final_path=final_identity.canonical_absolute_path,
                expected_volume_serial=final_identity.volume_serial_number,
                observed_volume_serial=final_identity.volume_serial_number,
                expected_file_id_128=final_identity.file_id_128,
                observed_file_id_128=final_identity.file_id_128,
                object_kind=final_identity.object_kind,
                link_count=final_identity.link_count,
                reparse_tag=lexical_identity.reparse_tag,
                acl_observable=acl_observable,
            ),
            True,
        )
    finally:
        if final_handle is not None:
            closed_final = _close_handle(final_handle)
        closed_lexical = _close_handle(lexical_handle)
        if not closed_lexical or (final_handle is not None and not closed_final):
            raise OSError("Win32 handle cleanup could not be verified")


def probe_workspace_objects(
    workspace: Path,
    case_manifest: BoundaryCaseManifestV1,
) -> WorkspaceObjectProbeResultV1:
    """Probe ordered workspace cases with real Win32 handles and close them."""
    if not workspace.is_dir():
        raise ValueError("workspace must be an existing directory")
    if not case_manifest.cases:
        raise ValueError("case manifest must contain at least one case")
    observations: list[BoundaryObservationV1] = []
    seen_identities: set[tuple[int, bytes]] = set()
    cleanup_verified = True
    for case in case_manifest.cases:
        try:
            observation, closed = _observation_for_case(
                workspace, case, seen_identities
            )
        except OSError:
            observation = _unproven_observation("IDENTITY_UNPROVEN", case.lexical_path)
            closed = False
        observations.append(observation)
        cleanup_verified = cleanup_verified and closed
    return WorkspaceObjectProbeResultV1(tuple(observations), cleanup_verified)

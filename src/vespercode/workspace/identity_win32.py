"""T09.1 legacy step 9.A: handle-derived Win32 workspace identity.

``resolve_workspace_identity`` opens the locator directory with a real
Win32 handle and seals one ``WorkspaceIdentityV1`` binding the canonical
absolute path, volume identity, and final directory object identity
(SPEC §0.1: "工作区身份绑定规范绝对路径、卷标识和最终目录对象身份");
path text alone never authorizes.  The root final object must exist, must
not be a reparse point, and must be a directory — those failures raise
the closed ``WorkspaceObjectRejectedV1`` with a stable code.  The root's
link count and ACL observability are recorded as sealed facts of the
identity (the digest binds them), so a drift or unprovable ACL is
observable at every consumption point; 9.A also rejects objects whose ACL
is unobservable.

``WorkspaceIdentityV1`` is the sealed root identity consumed by 9.B (mutex
naming), 9.C (Git preflight binding), and 9.D (path authorization).  The
digest is the SPEC §0.1 identity of every preceding field and is verified
explicitly at every consumption point (``verify_integrity``), never
silently trusted.
"""

from __future__ import annotations

import ctypes
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Final, Literal, NoReturn

from ctypes import wintypes

from pydantic import (
    BaseModel,
    ConfigDict,
    StrictBool,
    StrictStr,
    field_validator,
    model_validator,
)

from vespercode.canonical.digest import domain_digest
from vespercode.canonical.json_v1 import CanonicalValueV1
from vespercode.contracts.evidence import _DIGEST_RE

_FILE_READ_ATTRIBUTES: Final = 0x00000080
_READ_CONTROL: Final = 0x00020000
_FILE_SHARE_READ: Final = 0x00000001
_FILE_SHARE_WRITE: Final = 0x00000002
_FILE_SHARE_DELETE: Final = 0x00000004
_OPEN_EXISTING: Final = 3
_FILE_FLAG_BACKUP_SEMANTICS: Final = 0x02000000
_FILE_FLAG_OPEN_REPARSE_POINT: Final = 0x00200000
_FILE_ID_INFO: Final = 18
_FILE_ATTRIBUTE_TAG_INFO: Final = 9
_FILE_ATTRIBUTE_DIRECTORY: Final = 0x00000010
_SE_FILE_OBJECT: Final = 1
_OWNER_SECURITY_INFORMATION: Final = 0x00000001
_GROUP_SECURITY_INFORMATION: Final = 0x00000002
_DACL_SECURITY_INFORMATION: Final = 0x00000004
_INVALID_HANDLE_VALUE: Final = ctypes.c_void_p(-1).value
_ERROR_FILE_NOT_FOUND: Final = 2
_ERROR_PATH_NOT_FOUND: Final = 3
_ERROR_ACCESS_DENIED: Final = 5
_ERROR_HANDLE_EOF: Final = 38

WorkspaceObjectRejectionCodeV1 = Literal[
    # 9.A: unsupported reparse/ADS/hard-link/kind final object.
    "UNSUPPORTED_WORKSPACE_OBJECT",
    # 9.A: the final object cannot be opened or its identity cannot be
    # proven (including identity drift between the sealed root and the
    # live directory).
    "WORKSPACE_OBJECT_NOT_FOUND",
    "WORKSPACE_OBJECT_IDENTITY_UNPROVEN",
    # 9.A: the object lives on a different volume than the sealed root.
    "WORKSPACE_OBJECT_VOLUME_MISMATCH",
    # 9.A: the ACL is not observable through a READ_CONTROL handle.
    "WORKSPACE_OBJECT_ACL_UNPROVEN",
    # 9.A/9.D: the lexical spelling aliases an existing final object.
    "PATH_ALIAS_COLLISION",
    # 9.A: the final object lies outside the root's final directory.
    "PATH_OUTSIDE_WORKSPACE",
    # 9.A resolve: the locator does not resolve to an existing object.
    "WORKSPACE_ROOT_NOT_FOUND",
    # 9.A resolve: the final object is not a directory.
    "WORKSPACE_ROOT_NOT_DIRECTORY",
]


class WorkspaceObjectRejectedV1(Exception):
    """One closed rejection with a stable code for an unprovable object.

    Lexical identity alone never authorizes: every rejection carries the
    deterministic code the caller can bind into stable failure evidence.
    """

    def __init__(self, error_code: WorkspaceObjectRejectionCodeV1, reason: str) -> None:
        super().__init__(f"{error_code}: {reason}")
        self.error_code = error_code
        self.reason = reason


def _reject(error_code: WorkspaceObjectRejectionCodeV1, reason: str) -> NoReturn:
    raise WorkspaceObjectRejectedV1(error_code, reason)


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
class _HandleIdentityV1:
    """The raw facts observed through one Win32 handle."""

    final_path: str
    volume_serial_number: int
    file_id_128_hex: str
    object_kind: Literal["FILE", "DIRECTORY"]
    link_count: int
    reparse_tag: int


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
    """Open one object with FILE_READ_ATTRIBUTES for identity observation."""
    flags = _FILE_FLAG_BACKUP_SEMANTICS
    if open_reparse_point:
        flags |= _FILE_FLAG_OPEN_REPARSE_POINT
    handle = _kernel32().CreateFileW(
        str(path),
        _FILE_READ_ATTRIBUTES,
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


def _identity_from_handle(handle: wintypes.HANDLE) -> _HandleIdentityV1:
    """Seal the exact facts observable through one open handle."""
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
        "DIRECTORY" if basic.file_attributes & _FILE_ATTRIBUTE_DIRECTORY else "FILE"
    )
    return _HandleIdentityV1(
        final_path=final_path,
        # FILE_ID_INFO reports the volume serial as an unsigned 64-bit
        # value; mask the signed c_longlong back to its true identity.
        volume_serial_number=int(file_id.volume_serial_number) & 0xFFFFFFFFFFFFFFFF,
        file_id_128_hex=bytes(file_id.file_id).hex(),
        object_kind=object_kind,
        link_count=int(basic.number_of_links),
        reparse_tag=int(tag_info.reparse_tag),
    )


def _acl_is_observable(path: Path) -> bool:
    """True exactly when the object's ACL can be read through a handle.

    A separate READ_CONTROL handle is opened and the security descriptor
    is fetched; an access-denied open (an ACL that denies READ_CONTROL to
    the current user) or a failed descriptor read makes the ACL
    unprovable and the caller rejects the object.
    """
    kernel32 = _kernel32()
    handle = kernel32.CreateFileW(
        str(path),
        _FILE_READ_ATTRIBUTES | _READ_CONTROL,
        _FILE_SHARE_READ | _FILE_SHARE_WRITE | _FILE_SHARE_DELETE,
        None,
        _OPEN_EXISTING,
        _FILE_FLAG_BACKUP_SEMANTICS,
        None,
    )
    if handle == _INVALID_HANDLE_VALUE:
        return False
    try:
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
                kernel32.LocalFree(security_descriptor)
    finally:
        _close_handle_or_reject(wintypes.HANDLE(handle))


class _Win32FindStreamData(ctypes.Structure):
    _fields_ = [
        ("stream_size", ctypes.c_longlong),
        ("stream_name", wintypes.WCHAR * 296),
    ]


_FIND_FIRST_STREAM_FAILED: Final = wintypes.HANDLE(-1).value
_FIND_STREAM_INFO_LEVEL_FIND_STREAM_ID: Final = 0


def _has_named_alternate_data_stream(path: Path) -> bool:
    """True when the object carries a named stream beyond the base data.

    Fails closed on unprovable stream state: a stream-less directory
    legitimately fails ``FindFirstStreamW`` with ERROR_HANDLE_EOF (38) or
    ERROR_FILE_NOT_FOUND (2), which reports False; any other enumeration
    failure reports True so the caller rejects the object instead of
    sealing a possibly-unsound "no named streams" fact.
    """
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.FindFirstStreamW.argtypes = [
        wintypes.LPCWSTR,
        ctypes.c_int,
        ctypes.c_void_p,
        wintypes.DWORD,
    ]
    kernel32.FindFirstStreamW.restype = wintypes.HANDLE
    kernel32.FindNextStreamW.argtypes = [wintypes.HANDLE, ctypes.c_void_p]
    kernel32.FindNextStreamW.restype = wintypes.BOOL
    kernel32.FindClose.argtypes = [wintypes.HANDLE]
    kernel32.FindClose.restype = wintypes.BOOL
    data = _Win32FindStreamData()
    handle = kernel32.FindFirstStreamW(
        str(path),
        _FIND_STREAM_INFO_LEVEL_FIND_STREAM_ID,
        ctypes.byref(data),
        0,
    )
    if handle == _FIND_FIRST_STREAM_FAILED:
        return ctypes.get_last_error() not in (_ERROR_HANDLE_EOF, _ERROR_FILE_NOT_FOUND)
    try:
        if data.stream_name != "::$DATA":
            return True
        while kernel32.FindNextStreamW(handle, ctypes.byref(data)):
            if data.stream_name != "::$DATA":
                return True
        # A False FindNextStreamW is a failure: only the legitimate
        # end-of-stream errors may seal "no more named streams"; any
        # other failure reports True so the caller rejects fail-closed.
        if ctypes.get_last_error() not in (_ERROR_HANDLE_EOF, _ERROR_FILE_NOT_FOUND):
            return True
        return False
    finally:
        kernel32.FindClose(handle)


def _reject_coerced_schema_version(value: object) -> object:
    """Reject bool/float/string spellings of the integer schema version."""
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError("schema_version must be the decimal integer 1")
    return value


def _require_32_hex(value: str) -> str:
    if len(value) != 32 or any(
        character not in "0123456789abcdef" for character in value
    ):
        raise ValueError("file id must be exactly 32 lowercase hexadecimal characters")
    return value


def _require_sha256_hex(value: str) -> str:
    if _DIGEST_RE.fullmatch(value) is None:
        raise ValueError("digest must be exactly 64 lowercase hexadecimal characters")
    return value


def _identity_digest_body(identity: WorkspaceIdentityV1) -> dict[str, CanonicalValueV1]:
    """The canonical digest value body: every exact field except the digest."""
    return {
        "canonical_absolute_path": identity.canonical_absolute_path,
        "volume_serial_number": identity.volume_serial_number,
        "final_object_file_id_128_hex": identity.final_object_file_id_128_hex,
        "final_object_kind": identity.final_object_kind,
        "link_count": identity.link_count,
        "acl_observable": identity.acl_observable,
    }


def digest_workspace_identity(identity: WorkspaceIdentityV1) -> str:
    """The SPEC §0.1 identity of every exact field except the digest."""
    return domain_digest(
        "WorkspaceIdentityV1",
        identity.schema_version,
        _identity_digest_body(identity),
    )


class WorkspaceIdentityV1(BaseModel):
    """The sealed handle-derived workspace root identity (SPEC §0.1).

    All fields are required and unknown fields reject; ``digest`` is the
    §0.1 identity of every preceding field and is re-verified at every
    consumption point.  Construction validates the digest form only so
    that drift can be observed and rejected deterministically.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal[1]
    canonical_absolute_path: StrictStr
    volume_serial_number: int
    final_object_file_id_128_hex: StrictStr
    final_object_kind: Literal["FILE", "DIRECTORY"]
    link_count: int
    acl_observable: StrictBool
    digest: StrictStr

    @field_validator("schema_version", mode="before")
    @classmethod
    def _schema_version_is_exact_int(cls, value: object) -> object:
        return _reject_coerced_schema_version(value)

    @field_validator("volume_serial_number", "link_count", mode="before")
    @classmethod
    def _exact_non_negative_int(cls, value: object) -> object:
        if not isinstance(value, int) or isinstance(value, bool):
            raise ValueError("integer fields must be exact decimal integers")
        if value < 0:
            raise ValueError("integer fields must not be negative")
        return value

    @field_validator("final_object_file_id_128_hex")
    @classmethod
    def _file_id_has_exact_form(cls, value: str) -> str:
        return _require_32_hex(value)

    @field_validator("digest")
    @classmethod
    def _digest_has_exact_form(cls, value: str) -> str:
        return _require_sha256_hex(value)

    @model_validator(mode="after")
    def _root_is_a_directory(self) -> WorkspaceIdentityV1:
        if self.final_object_kind != "DIRECTORY":
            raise ValueError("the workspace root identity must seal a directory")
        return self

    def verify_integrity(self) -> None:
        """Fail closed unless the digest still binds every other field."""
        if self.digest != digest_workspace_identity(self):
            raise ValueError(
                "workspace identity digest no longer binds its exact fields"
            )


def _close_handle_or_reject(handle: wintypes.HANDLE) -> None:
    """Close one handle; a failed close is a stable closed rejection.

    Cleanup failures must never escape as a raw OSError that could mask
    the in-flight closed rejection (GREEN-2 stable closed errors).
    """
    if not _close_handle(handle):
        _reject(
            "WORKSPACE_OBJECT_IDENTITY_UNPROVEN",
            "Win32 handle cleanup could not be verified",
        )


def resolve_workspace_identity(locator: Path) -> WorkspaceIdentityV1:
    """Resolve one sealed workspace identity from a real Win32 handle.

    The final object must exist, must not be a reparse point, and must
    be a directory; the sealed identity then binds the canonical
    absolute path, the volume serial number, the 128-bit final object
    file id, the link count, and ACL observability — path text alone
    never authorizes.
    """
    path = Path(locator)
    try:
        handle = _open_handle(path, open_reparse_point=True)
    except OSError as error:
        if error.errno in (_ERROR_FILE_NOT_FOUND, _ERROR_PATH_NOT_FOUND):
            _reject("WORKSPACE_ROOT_NOT_FOUND", f"{path} does not exist")
        _reject("WORKSPACE_OBJECT_IDENTITY_UNPROVEN", f"cannot open {path}")
    try:
        try:
            facts = _identity_from_handle(handle)
        except OSError as error:
            raise WorkspaceObjectRejectedV1(
                "WORKSPACE_OBJECT_IDENTITY_UNPROVEN", str(error)
            ) from error
    finally:
        _close_handle_or_reject(handle)
    if facts.reparse_tag != 0:
        _reject(
            "UNSUPPORTED_WORKSPACE_OBJECT",
            f"workspace root {path} is a reparse point",
        )
    if facts.object_kind != "DIRECTORY":
        _reject(
            "WORKSPACE_ROOT_NOT_DIRECTORY", f"workspace root {path} is not a directory"
        )
    if _has_named_alternate_data_stream(path):
        _reject(
            "UNSUPPORTED_WORKSPACE_OBJECT",
            f"workspace root {path} carries a named alternate data stream",
        )
    draft = WorkspaceIdentityV1.model_validate(
        {
            "schema_version": 1,
            "canonical_absolute_path": os.path.normcase(
                os.path.abspath(facts.final_path)
            ),
            "volume_serial_number": facts.volume_serial_number,
            "final_object_file_id_128_hex": facts.file_id_128_hex,
            "final_object_kind": facts.object_kind,
            "link_count": facts.link_count,
            "acl_observable": _acl_is_observable(path),
            "digest": "0" * 64,
        }
    )
    return draft.model_copy(update={"digest": digest_workspace_identity(draft)})

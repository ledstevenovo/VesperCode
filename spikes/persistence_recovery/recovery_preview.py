"""T03.2 legacy step 3.E: read-only recovery preview and three-value disposition.

Produces one immutable :class:`GateRecoveryPreviewV1` per transaction by
observing the current workspace bytes and Win32 object identity, running
every path record through the closed classifier (legacy step 3.D), and
mapping the complete classification set through the closed disposition
matrix to exactly ``COMMITTED``, ``ROLLED_BACK``, or ``UNRESOLVED``.
The preview is strictly read-only: it never writes the workspace, the
durable transaction log, or any backup, and always binds
``workspace_write_count == 0``.

Disposition matrix (pinned by the matrix tests, consistent with SPEC
4.6 item 10 and AC-29):

1. Any ``EXTERNAL_CHANGE`` or ``UNPROVABLE`` classification makes the
   transaction ``UNRESOLVED`` — an unsafe state is never coerced into a
   terminal safe disposition.
2. Every path at ``POSTIMAGE`` is ``COMMITTED`` (all postimages
   provably matched; the apply redoes the write-after verification).
3. Every path at ``PREIMAGE``/``ABSENT``, or a ``POSTIMAGE`` new file
   whose record is a ``CREATE`` (preimage ABSENT) — provably restorable
   to ABSENT under AC-29's exact-postimage rule — is ``ROLLED_BACK``.
4. Any other mixed state (a replaced ``REPLACE`` path next to unapplied
   paths) is contradictory and ``UNRESOLVED``.

Fail-closed record handling (documented decision): a missing, unreadable,
tampered, or workspace-mismatched durable record raises ``ValueError``
from the existing :func:`load_transaction` boundary and never produces a
preview disposition; an unreadable record cannot prove any terminal
state and must not be treated as active-unknown by the preview.

This module owns observation collection and the three-value preview
only (legacy step 3.E boundary); explicit recovery application and the
real-environment GO gate remain out of scope (legacy steps 3.F/3.G).
"""

from __future__ import annotations

import ctypes
import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from ctypes import wintypes

from spikes.persistence_recovery.observation import (
    GatePathClassificationV1,
    GatePathObservationV1,
    classify_gate_path,
)
from spikes.persistence_recovery.protocol import (
    GatePathRecordV1,
    load_transaction,
)

GateRecoveryDispositionV1 = Literal["COMMITTED", "ROLLED_BACK", "UNRESOLVED"]

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
_FILE_BASIC_INFO = 0
_INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value
_ERROR_FILE_NOT_FOUND = 2
_ERROR_PATH_NOT_FOUND = 3
_DIRECTORY_ATTRIBUTE = 0x10


class _FileIdInfo(ctypes.Structure):
    _fields_ = [
        ("volume_serial_number", ctypes.c_longlong),
        ("file_id", ctypes.c_ubyte * 16),
    ]


class _FileAttributeTagInfo(ctypes.Structure):
    _fields_ = [("file_attributes", wintypes.DWORD), ("reparse_tag", wintypes.DWORD)]


class _FileBasicInfo(ctypes.Structure):
    _fields_ = [
        ("creation_time", ctypes.c_longlong),
        ("last_access_time", ctypes.c_longlong),
        ("last_write_time", ctypes.c_longlong),
        ("change_time", ctypes.c_longlong),
        ("file_attributes", wintypes.DWORD),
    ]


@dataclass(frozen=True)
class GatePathClassificationEntryV1:
    """One immutable (path, classification) pair bound into a preview."""

    path: str
    classification: GatePathClassificationV1


GatePathClassificationSequenceV1 = tuple[GatePathClassificationEntryV1, ...]


@dataclass(frozen=True)
class GateRecoveryPreviewV1:
    """Immutable read-only recovery preview of one transaction.

    ``disposition`` is exactly ``COMMITTED``, ``ROLLED_BACK``, or
    ``UNRESOLVED``; ``path_classifications`` covers every path record;
    ``workspace_write_count`` is the literal zero-writes proof of this
    preview (the preview itself never writes).
    """

    transaction_id: str
    disposition: GateRecoveryDispositionV1
    path_classifications: GatePathClassificationSequenceV1
    workspace_write_count: Literal[0]


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
    return kernel32


def _open_handle(path: Path) -> wintypes.HANDLE:
    handle = _kernel32().CreateFileW(
        str(path),
        _FILE_READ_ATTRIBUTES | _READ_CONTROL,
        _FILE_SHARE_READ | _FILE_SHARE_WRITE | _FILE_SHARE_DELETE,
        None,
        _OPEN_EXISTING,
        _FILE_FLAG_BACKUP_SEMANTICS | _FILE_FLAG_OPEN_REPARSE_POINT,
        None,
    )
    if handle == _INVALID_HANDLE_VALUE:
        raise OSError(ctypes.get_last_error(), f"cannot open {path}")
    return wintypes.HANDLE(handle)


def _identity_from_handle(handle: wintypes.HANDLE) -> tuple[int, bytes]:
    file_id = _FileIdInfo()
    if not _kernel32().GetFileInformationByHandleEx(
        handle, _FILE_ID_INFO, ctypes.byref(file_id), ctypes.sizeof(file_id)
    ):
        raise OSError(
            ctypes.get_last_error(), "GetFileInformationByHandleEx(FileIdInfo)"
        )
    return int(file_id.volume_serial_number), bytes(file_id.file_id)


def _reparse_tag_from_handle(handle: wintypes.HANDLE) -> int:
    tag_info = _FileAttributeTagInfo()
    if not _kernel32().GetFileInformationByHandleEx(
        handle,
        _FILE_ATTRIBUTE_TAG_INFO,
        ctypes.byref(tag_info),
        ctypes.sizeof(tag_info),
    ):
        raise OSError(
            ctypes.get_last_error(),
            "GetFileInformationByHandleEx(FileAttributeTagInfo)",
        )
    return int(tag_info.reparse_tag)


def _is_directory_handle(handle: wintypes.HANDLE) -> bool:
    basic = _FileBasicInfo()
    if not _kernel32().GetFileInformationByHandleEx(
        handle, _FILE_BASIC_INFO, ctypes.byref(basic), ctypes.sizeof(basic)
    ):
        raise OSError(
            ctypes.get_last_error(), "GetFileInformationByHandleEx(FileBasicInfo)"
        )
    return bool(basic.file_attributes & _DIRECTORY_ATTRIBUTE)


def _confined_target(workspace: Path, path: str) -> Path:
    workspace_resolved = Path(workspace).resolve()
    relative = Path(path)
    if relative.is_absolute() or any(part == ".." for part in relative.parts):
        raise ValueError(f"observation path escapes the workspace: {path!r}")
    target = (workspace_resolved / relative).resolve()
    if not target.is_relative_to(workspace_resolved):
        raise ValueError(f"observation path escapes the workspace: {path!r}")
    if target == workspace_resolved:
        raise ValueError(f"observation path is the workspace root: {path!r}")
    return target


def observe_workspace_path(workspace: Path, path: str) -> GatePathObservationV1:
    """Observe the current real NTFS object at *path* under *workspace*.

    Returns one immutable :class:`GatePathObservationV1` without ever
    writing or deleting anything.  A missing path is ``ABSENT``; a
    reparse point or directory is a supported non-FILE kind; a regular
    file carries its content digest plus the Win32 volume serial and
    file id pair; every open/identity/read/close failure fails closed
    with ``supported=False`` so the classifier reports ``UNPROVABLE``.
    """
    target = _confined_target(workspace, path)
    result: GatePathObservationV1 | None = None
    handle: wintypes.HANDLE | None = None
    try:
        handle = _open_handle(target)
    except OSError as exc:
        error = exc.errno
        if error in (_ERROR_FILE_NOT_FOUND, _ERROR_PATH_NOT_FOUND):
            result = GatePathObservationV1(
                path=path,
                content_digest="",
                volume_serial=0,
                file_id_128=b"",
                object_kind="ABSENT",
                supported=True,
            )
        else:
            result = GatePathObservationV1(
                path=path,
                content_digest="",
                volume_serial=0,
                file_id_128=b"",
                object_kind="ABSENT",
                supported=False,
            )
    if result is not None:
        return result
    assert handle is not None
    try:
        volume_serial, file_id = _identity_from_handle(handle)
        if _reparse_tag_from_handle(handle) != 0:
            result = GatePathObservationV1(
                path=path,
                content_digest="",
                volume_serial=volume_serial,
                file_id_128=file_id,
                object_kind="SPECIAL",
                supported=True,
            )
        elif _is_directory_handle(handle):
            result = GatePathObservationV1(
                path=path,
                content_digest="",
                volume_serial=volume_serial,
                file_id_128=file_id,
                object_kind="DIRECTORY",
                supported=True,
            )
        else:
            try:
                content_digest = _sha256_hex(target.read_bytes())
            except OSError:
                result = GatePathObservationV1(
                    path=path,
                    content_digest="",
                    volume_serial=volume_serial,
                    file_id_128=file_id,
                    object_kind="FILE",
                    supported=False,
                )
            else:
                result = GatePathObservationV1(
                    path=path,
                    content_digest=content_digest,
                    volume_serial=volume_serial,
                    file_id_128=file_id,
                    object_kind="FILE",
                    supported=True,
                )
    except OSError:
        result = GatePathObservationV1(
            path=path,
            content_digest="",
            volume_serial=0,
            file_id_128=b"",
            object_kind="ABSENT",
            supported=False,
        )
    finally:
        if handle is not None and not _kernel32().CloseHandle(handle):
            # A handle that cannot be closed makes the observation
            # untrustworthy; fail closed on the classification.
            result = GatePathObservationV1(
                path=path,
                content_digest="",
                volume_serial=0,
                file_id_128=b"",
                object_kind="ABSENT",
                supported=False,
            )
    assert result is not None
    return result


def _disposition_for(
    classifications: tuple[tuple[GatePathRecordV1, GatePathClassificationV1], ...],
) -> GateRecoveryDispositionV1:
    if any(
        classification in ("EXTERNAL_CHANGE", "UNPROVABLE")
        for _, classification in classifications
    ):
        return "UNRESOLVED"
    if all(classification == "POSTIMAGE" for _, classification in classifications):
        return "COMMITTED"
    if all(
        classification in ("PREIMAGE", "ABSENT")
        or (classification == "POSTIMAGE" and record.operation == "CREATE")
        for record, classification in classifications
    ):
        return "ROLLED_BACK"
    return "UNRESOLVED"


def preview_recovery(workspace: Path, transaction_id: str) -> GateRecoveryPreviewV1:
    """Produce one immutable read-only recovery preview for *transaction_id*.

    Loads the durable record (failing closed on missing, unreadable,
    tampered, or mismatched records), observes every path record against
    the current workspace bytes/identity, classifies each through the
    closed classifier, and maps the complete classification set through
    the closed disposition matrix.  Nothing is ever written.
    """
    resolved = Path(workspace).resolve()
    transaction = load_transaction(transaction_id)
    if os.path.normcase(str(transaction.workspace)) != os.path.normcase(str(resolved)):
        raise ValueError("transaction record does not belong to the given workspace")
    if not transaction.records:
        raise ValueError("transaction record carries no path records")
    classifications = tuple(
        (
            record,
            classify_gate_path(record, observe_workspace_path(resolved, record.path)),
        )
        for record in transaction.records
    )
    disposition = _disposition_for(classifications)
    return GateRecoveryPreviewV1(
        transaction_id=transaction_id,
        disposition=disposition,
        path_classifications=tuple(
            GatePathClassificationEntryV1(
                path=record.path,
                classification=classification,
            )
            for record, classification in classifications
        ),
        workspace_write_count=0,
    )


def compute_preview_digest(preview: GateRecoveryPreviewV1) -> str:
    """The deterministic identity of one immutable preview.

    Binds the transaction id, disposition, every path classification,
    and the literal zero-write count; any drift in any bound field
    changes the digest.
    """
    return _sha256_hex(_canonical_json_bytes(_preview_to_json(preview)))


def _preview_to_json(preview: GateRecoveryPreviewV1) -> dict[str, object]:
    return {
        "transaction_id": preview.transaction_id,
        "disposition": preview.disposition,
        "path_classifications": [
            {"path": entry.path, "classification": entry.classification}
            for entry in preview.path_classifications
        ],
        "workspace_write_count": preview.workspace_write_count,
    }


def _canonical_json_bytes(obj: object) -> bytes:
    return json.dumps(
        obj,
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
        separators=(",", ": "),
    ).encode("utf-8")


def _sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()

"""T03.2 legacy step 3.F: explicit recovery application tests.

Covers preview-digest binding, workspace-mutex ownership, exact
safe-case writes only (COMMITTED terminal record, zero-change
ROLLED_BACK, and the AC-29 safe ABSENT deletion of a postimage-matching
new file), and fail-closed preservation of externally replaced,
unknown, unprovable, or UNRESOLVED objects without any deletion or
overwrite.
"""

from __future__ import annotations

import ctypes
import hashlib
import os
import shutil
import tempfile
import dataclasses
import threading
from pathlib import Path
from typing import Iterator

import pytest

from ctypes import wintypes

from spikes.persistence_recovery import recovery_apply
from spikes.persistence_recovery.faults import (
    PersistenceFaultPointV1,
    apply_transaction,
)
from spikes.persistence_recovery.protocol import (
    FixedClock,
    GatePreimageV1,
    GateTransactionRejectionV1,
    GateWriteEntryV1,
    NoFaultPort,
    load_transaction,
    prepare_transaction,
    transaction_record_path,
    transaction_root,
)
from spikes.persistence_recovery.recovery_apply import (
    GateRecoveryCommandV1,
    GateRecoveryResultV1,
    apply_recovery,
)
from spikes.persistence_recovery.recovery_preview import (
    compute_preview_digest,
    observe_workspace_path,
    preview_recovery,
)

_FAR_DEADLINE = 1 << 62
_INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value
_TEMP_WORKSPACES: list[Path] = []

_PRE_A = b"original a\n"
_PRE_B = b"original b\n"
_POST_A = b"post a\n"
_POST_B = b"post b\n"
_FOREIGN = b"foreign external bytes\n"


def fresh_workspace(prefix: str) -> Path:
    """One fresh disposable workspace with a ``src`` directory."""
    path = Path(tempfile.mkdtemp(prefix=prefix))
    (path / "src").mkdir()
    _TEMP_WORKSPACES.append(path)
    return path


@pytest.fixture(autouse=True)
def _cleanup_temp_state() -> Iterator[None]:
    """Remove every workspace and durable record created by this test."""
    yield
    for path in _TEMP_WORKSPACES:
        shutil.rmtree(path, ignore_errors=True)
    _TEMP_WORKSPACES.clear()
    root = transaction_root()
    if root.is_dir():
        for artifact in list(root.glob("*.json")) + list(root.glob("*.tmp")):
            artifact.unlink(missing_ok=True)


def replace_entry(
    workspace: Path,
    rel: str,
    preimage_bytes: bytes,
    postimage: bytes,
) -> GateWriteEntryV1:
    """One REPLACE entry bound to the real observed identity of *rel*."""
    observed = observe_workspace_path(workspace, rel)
    assert observed.supported and observed.object_kind == "FILE"
    assert observed.content_digest == hashlib.sha256(preimage_bytes).hexdigest()
    return GateWriteEntryV1(
        path=rel,
        operation="REPLACE",
        preimage=GatePreimageV1(
            kind="PRESENT",
            raw_bytes_digest=observed.content_digest,
            volume_serial=observed.volume_serial,
            file_id_128=observed.file_id_128,
        ),
        postimage=postimage,
        backup_ref=f"apply/{rel}.bin",
    )


def create_entry(rel: str, postimage: bytes) -> GateWriteEntryV1:
    return GateWriteEntryV1(
        path=rel,
        operation="CREATE",
        preimage=GatePreimageV1(kind="ABSENT"),
        postimage=postimage,
        backup_ref="",
    )


def prepare_and(
    workspace: Path,
    entries: tuple[GateWriteEntryV1, ...],
    fault: PersistenceFaultPointV1 | None = None,
) -> str:
    """Prepare *entries* and optionally stop the apply at *fault*."""
    result = prepare_transaction(
        workspace,
        entries,
        _FAR_DEADLINE,
        FixedClock(0),
        NoFaultPort(),
    )
    assert not isinstance(result, GateTransactionRejectionV1)
    if fault is not None:
        apply_transaction(result.transaction_id, fault, FixedClock(0))
    return result.transaction_id


def bound_command(workspace: Path, transaction_id: str) -> GateRecoveryCommandV1:
    """One explicit command bound to the current preview of *transaction_id*."""
    preview = preview_recovery(workspace, transaction_id)
    return GateRecoveryCommandV1(
        workspace=workspace,
        transaction_id=transaction_id,
        preview_digest=compute_preview_digest(preview),
        explicit_apply=True,
    )


def command_for_external_create() -> GateRecoveryCommandV1:
    """One explicit command for a CREATE whose new file was externally
    replaced with unknown bytes (the RED scenario)."""
    workspace = fresh_workspace("vesper-apply-red-")
    transaction_id = prepare_and(
        workspace,
        (create_entry("src/b.py", _POST_B),),
        PersistenceFaultPointV1("TERMINAL", "BEFORE", 0),
    )
    (workspace / "src" / "b.py").write_bytes(_FOREIGN)
    return bound_command(workspace, transaction_id)


def test_apply_never_deletes_externally_replaced_create() -> None:
    result = apply_recovery(command_for_external_create())
    assert result.disposition == "UNRESOLVED"


def test_apply_preserves_externally_replaced_create_bytes() -> None:
    workspace = fresh_workspace("vesper-apply-preserve-")
    transaction_id = prepare_and(
        workspace,
        (create_entry("src/b.py", _POST_B),),
        PersistenceFaultPointV1("TERMINAL", "BEFORE", 0),
    )
    target = workspace / "src" / "b.py"
    target.write_bytes(_FOREIGN)
    before = target.read_bytes()
    result = apply_recovery(bound_command(workspace, transaction_id))
    assert result.disposition == "UNRESOLVED"
    assert result.changed_paths == ()
    assert target.read_bytes() == before == _FOREIGN


def test_apply_preserves_externally_replaced_replace() -> None:
    workspace = fresh_workspace("vesper-apply-replace-")
    (workspace / "src" / "a.py").write_bytes(_PRE_A)
    transaction_id = prepare_and(
        workspace,
        (replace_entry(workspace, "src/a.py", _PRE_A, _POST_A),),
        PersistenceFaultPointV1("TERMINAL", "BEFORE", 0),
    )
    target = workspace / "src" / "a.py"
    target.write_bytes(_FOREIGN)
    result = apply_recovery(bound_command(workspace, transaction_id))
    assert result.disposition == "UNRESOLVED"
    assert result.changed_paths == ()
    assert target.read_bytes() == _FOREIGN


def test_apply_committed_terminates_committed_record(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    (workspace / "src").mkdir(parents=True)
    (workspace / "src" / "a.py").write_bytes(_PRE_A)
    (workspace / "src" / "b.py").write_bytes(_PRE_B)
    transaction_id = prepare_and(
        workspace,
        (
            create_entry("src/a.py", _POST_A),
            replace_entry(workspace, "src/b.py", _PRE_B, _POST_B),
        ),
        PersistenceFaultPointV1("TERMINAL", "BEFORE", 0),
    )
    result = apply_recovery(bound_command(workspace, transaction_id))
    assert result.disposition == "COMMITTED"
    assert result.changed_paths == ()
    transaction = load_transaction(transaction_id)
    assert transaction.state == "COMMITTED"
    assert all(record.durable_state == "VERIFIED" for record in transaction.records)
    assert (workspace / "src" / "a.py").read_bytes() == _POST_A
    assert (workspace / "src" / "b.py").read_bytes() == _POST_B


def test_apply_rolled_back_zero_change(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    (workspace / "src").mkdir(parents=True)
    (workspace / "src" / "b.py").write_bytes(_PRE_B)
    transaction_id = prepare_and(
        workspace,
        (replace_entry(workspace, "src/b.py", _PRE_B, _POST_B),),
    )
    result = apply_recovery(bound_command(workspace, transaction_id))
    assert result.disposition == "ROLLED_BACK"
    assert result.changed_paths == ()
    transaction = load_transaction(transaction_id)
    assert transaction.state == "ROLLED_BACK"
    assert all(record.durable_state == "ROLLED_BACK" for record in transaction.records)
    assert (workspace / "src" / "b.py").read_bytes() == _PRE_B


def test_apply_safely_deletes_postimage_matching_create(tmp_path: Path) -> None:
    """The AC-29 safe ABSENT rollback: only a new file that still exactly
    matches this transaction's postimage is deleted; the untouched
    REPLACE path stays at its preimage."""
    workspace = tmp_path / "workspace"
    (workspace / "src").mkdir(parents=True)
    (workspace / "src" / "b.py").write_bytes(_PRE_B)
    transaction_id = prepare_and(
        workspace,
        (
            create_entry("src/a.py", _POST_A),
            replace_entry(workspace, "src/b.py", _PRE_B, _POST_B),
        ),
        PersistenceFaultPointV1("PROGRESS", "BEFORE", 1),
    )
    result = apply_recovery(bound_command(workspace, transaction_id))
    assert result.disposition == "ROLLED_BACK"
    assert result.changed_paths == ("src/a.py",)
    assert not (workspace / "src" / "a.py").exists()
    assert (workspace / "src" / "b.py").read_bytes() == _PRE_B
    transaction = load_transaction(transaction_id)
    assert transaction.state == "ROLLED_BACK"


def test_apply_rejects_stale_preview_digest(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    (workspace / "src").mkdir(parents=True)
    transaction_id = prepare_and(
        workspace,
        (create_entry("src/b.py", _POST_B),),
        PersistenceFaultPointV1("TERMINAL", "BEFORE", 0),
    )
    stale = bound_command(workspace, transaction_id)
    target = workspace / "src" / "b.py"
    target.write_bytes(_FOREIGN)
    before = target.read_bytes()
    result = apply_recovery(stale)
    assert result.disposition == "UNRESOLVED"
    assert result.changed_paths == ()
    assert target.read_bytes() == before == _FOREIGN


def test_apply_unresolved_preview_writes_nothing(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    (workspace / "src").mkdir(parents=True)
    (workspace / "src" / "a.py").write_bytes(_PRE_A)
    transaction_id = prepare_and(
        workspace,
        (
            replace_entry(workspace, "src/a.py", _PRE_A, _POST_A),
            create_entry("src/b.py", _POST_B),
        ),
        PersistenceFaultPointV1("REPLACE", "BEFORE", 2),
    )
    target = workspace / "src" / "a.py"
    result = apply_recovery(bound_command(workspace, transaction_id))
    assert result.disposition == "UNRESOLVED"
    assert result.changed_paths == ()
    assert target.read_bytes() == _POST_A
    assert not (workspace / "src" / "b.py").exists()


def test_apply_preserves_unprovable_locked_object(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    (workspace / "src").mkdir(parents=True)
    (workspace / "src" / "b.py").write_bytes(_PRE_B)
    transaction_id = prepare_and(
        workspace,
        (replace_entry(workspace, "src/b.py", _PRE_B, _POST_B),),
        PersistenceFaultPointV1("TERMINAL", "BEFORE", 0),
    )
    kernel32 = _kernel32()
    handle = kernel32.CreateFileW(
        str(workspace / "src" / "b.py"), 0x80000000, 0, None, 3, 0, None
    )
    assert handle != _INVALID_HANDLE_VALUE
    try:
        result = apply_recovery(bound_command(workspace, transaction_id))
    finally:
        assert bool(kernel32.CloseHandle(handle))
    assert result.disposition == "UNRESOLVED"
    assert result.changed_paths == ()
    assert (workspace / "src" / "b.py").read_bytes() == _POST_B


def test_apply_rejects_terminal_record(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    (workspace / "src").mkdir(parents=True)
    (workspace / "src" / "b.py").write_bytes(_PRE_B)
    transaction_id = prepare_and(
        workspace,
        (replace_entry(workspace, "src/b.py", _PRE_B, _POST_B),),
        PersistenceFaultPointV1("TERMINAL", "AFTER", 0),
    )
    with pytest.raises(ValueError, match="terminal"):
        apply_recovery(bound_command(workspace, transaction_id))


def test_apply_rejects_workspace_mismatch(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    (workspace / "src").mkdir(parents=True)
    (workspace / "src" / "b.py").write_bytes(_PRE_B)
    transaction_id = prepare_and(
        workspace,
        (replace_entry(workspace, "src/b.py", _PRE_B, _POST_B),),
        PersistenceFaultPointV1("TERMINAL", "BEFORE", 0),
    )
    preview = preview_recovery(workspace, transaction_id)
    other = tmp_path / "other"
    other.mkdir()
    with pytest.raises(ValueError, match="does not belong"):
        apply_recovery(
            GateRecoveryCommandV1(
                workspace=other,
                transaction_id=transaction_id,
                preview_digest=compute_preview_digest(preview),
                explicit_apply=True,
            )
        )


def test_apply_rejects_invalid_command_bindings(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    (workspace / "src").mkdir(parents=True)
    (workspace / "src" / "b.py").write_bytes(_PRE_B)
    transaction_id = prepare_and(
        workspace,
        (replace_entry(workspace, "src/b.py", _PRE_B, _POST_B),),
    )
    implicit = dataclasses.replace(
        GateRecoveryCommandV1(
            workspace=workspace,
            transaction_id=transaction_id,
            preview_digest="00" * 32,
            explicit_apply=True,
        ),
        explicit_apply=False,  # type: ignore[arg-type]
    )
    with pytest.raises(ValueError, match="explicit_apply"):
        apply_recovery(implicit)
    with pytest.raises(ValueError, match="preview_digest"):
        apply_recovery(
            GateRecoveryCommandV1(
                workspace=workspace,
                transaction_id=transaction_id,
                preview_digest="not-a-digest",
                explicit_apply=True,
            )
        )


def test_apply_result_digest_is_deterministic(tmp_path: Path) -> None:
    def one_run(root: Path) -> GateRecoveryResultV1:
        workspace = root / "workspace"
        (workspace / "src").mkdir(parents=True)
        (workspace / "src" / "b.py").write_bytes(_PRE_B)
        transaction_id = prepare_and(
            workspace,
            (replace_entry(workspace, "src/b.py", _PRE_B, _POST_B),),
        )
        return apply_recovery(bound_command(workspace, transaction_id))

    first = one_run(tmp_path / "first")
    second = one_run(tmp_path / "second")
    assert first == second
    assert len(first.evidence_digest) == 64


def _mutex_name(workspace: Path) -> str:
    digest = hashlib.sha256(
        os.path.normcase(os.path.abspath(str(workspace))).encode("utf-8")
    ).hexdigest()
    return f"Local\\VesperCode.WorkspaceLeaseV1.{digest}"


def _kernel32() -> ctypes.WinDLL:
    """One local kernel32 ABI wiring site for the test-side Win32 probes."""
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


def test_apply_requires_the_workspace_mutex(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(recovery_apply, "_MUTEX_WAIT_TIMEOUT_MS", 50)
    workspace = tmp_path / "workspace"
    (workspace / "src").mkdir(parents=True)
    (workspace / "src" / "b.py").write_bytes(_PRE_B)
    transaction_id = prepare_and(
        workspace,
        (replace_entry(workspace, "src/b.py", _PRE_B, _POST_B),),
        PersistenceFaultPointV1("TERMINAL", "BEFORE", 0),
    )
    command = bound_command(workspace, transaction_id)
    held = threading.Event()
    release = threading.Event()

    def holder() -> None:
        kernel32 = _kernel32()
        handle = kernel32.CreateMutexW(None, False, _mutex_name(workspace))
        assert handle
        assert kernel32.WaitForSingleObject(handle, 2_000) in (0, 0x80)
        held.set()
        assert release.wait(5)
        assert kernel32.ReleaseMutex(handle)
        assert kernel32.CloseHandle(handle)

    thread = threading.Thread(target=holder)
    thread.start()
    assert held.wait(5)
    try:
        with pytest.raises(RuntimeError, match="held by another process"):
            apply_recovery(command)
    finally:
        release.set()
        thread.join(5)
    result = apply_recovery(command)
    assert result.disposition == "COMMITTED"


def test_apply_releases_the_workspace_mutex(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    (workspace / "src").mkdir(parents=True)
    (workspace / "src" / "b.py").write_bytes(_PRE_B)
    transaction_id = prepare_and(
        workspace,
        (replace_entry(workspace, "src/b.py", _PRE_B, _POST_B),),
        PersistenceFaultPointV1("TERMINAL", "BEFORE", 0),
    )
    assert apply_recovery(bound_command(workspace, transaction_id)).disposition == (
        "COMMITTED"
    )
    kernel32 = _kernel32()
    handle = kernel32.CreateMutexW(None, False, _mutex_name(workspace))
    assert handle
    assert kernel32.WaitForSingleObject(handle, 2_000) == 0
    assert kernel32.ReleaseMutex(handle)
    assert kernel32.CloseHandle(handle)


def test_apply_never_changes_unresolved_paths(tmp_path: Path) -> None:
    """Intent cannot be inferred without a bound preview and unresolved
    paths remain immutable: an externally replaced object is preserved
    byte-for-byte and the durable record is not rewritten."""
    workspace = tmp_path / "workspace"
    (workspace / "src").mkdir(parents=True)
    (workspace / "src" / "a.py").write_bytes(_PRE_A)
    transaction_id = prepare_and(
        workspace,
        (
            replace_entry(workspace, "src/a.py", _PRE_A, _POST_A),
            create_entry("src/b.py", _POST_B),
        ),
        PersistenceFaultPointV1("REPLACE", "BEFORE", 2),
    )
    record_before = transaction_record_path(transaction_id).read_bytes()
    (workspace / "src" / "a.py").write_bytes(_FOREIGN)
    result = apply_recovery(bound_command(workspace, transaction_id))
    assert result.disposition == "UNRESOLVED"
    assert (workspace / "src" / "a.py").read_bytes() == _FOREIGN
    assert not (workspace / "src" / "b.py").exists()
    assert transaction_record_path(transaction_id).read_bytes() == record_before

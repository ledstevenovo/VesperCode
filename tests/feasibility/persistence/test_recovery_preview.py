"""T03.2 legacy step 3.E: read-only recovery preview tests.

Covers the byte-for-byte read-only proof, the closed three-value
disposition matrix over every mixed-path byte state, fail-closed record
handling, the immutable preview binding, and the real-NTFS object
observer.  Every preview call must leave workspace bytes, the durable
transaction log, and backups untouched and always bind
``workspace_write_count == 0``.
"""

from __future__ import annotations

import ctypes
import hashlib
import json
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterator

import pytest

from ctypes import wintypes

from spikes.persistence_recovery.faults import (
    PersistenceFaultPointV1,
    apply_transaction,
)
from spikes.persistence_recovery.protocol import (
    FixedClock,
    GatePreimageV1,
    GateTransactionRejectionV1,
    GateTransactionV1,
    GateWriteEntryV1,
    NoFaultPort,
    prepare_transaction,
    save_transaction,
    transaction_record_path,
    transaction_root,
)
from spikes.persistence_recovery.recovery_preview import (
    GateRecoveryDispositionV1,
    GateRecoveryPreviewV1,
    compute_preview_digest,
    observe_workspace_path,
    preview_recovery,
)

_FAR_DEADLINE = 1 << 62
_INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value
_TEMP_WORKSPACES: list[Path] = []

_PRE = b"original b\n"
_POST_B = b"post b\n"
_POST_A = b"post a\n"
_POST_C = b"post c\n"


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


def snapshot_digest(workspace: Path, transaction_id: str) -> str:
    """Digest of every workspace file plus the durable transaction record."""
    payload = bytearray()
    for path in sorted(workspace.rglob("*")):
        if path.is_file():
            payload += path.read_bytes()
    record = transaction_record_path(transaction_id)
    if record.is_file():
        payload += record.read_bytes()
    return hashlib.sha256(bytes(payload)).hexdigest()


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
        backup_ref=f"preview/{rel}.bin",
    )


def create_entry(rel: str, postimage: bytes) -> GateWriteEntryV1:
    return GateWriteEntryV1(
        path=rel,
        operation="CREATE",
        preimage=GatePreimageV1(kind="ABSENT"),
        postimage=postimage,
        backup_ref="",
    )


def prepared_replace_transaction(
    workspace: Path,
) -> GateTransactionV1:
    """One PREPARED single-REPLACE transaction over the seeded preimage."""
    (workspace / "src" / "b.py").write_bytes(_PRE)
    result = prepare_transaction(
        workspace,
        (replace_entry(workspace, "src/b.py", _PRE, _POST_B),),
        _FAR_DEADLINE,
        FixedClock(0),
        NoFaultPort(),
    )
    assert not isinstance(result, GateTransactionRejectionV1)
    return result


@dataclass(frozen=True)
class PreviewFixture:
    """One fully applied workspace plus its before-preview snapshot digest."""

    workspace: Path
    transaction_id: str
    _before_digest: str

    def before_digest(self) -> str:
        return self._before_digest

    def after_digest(self) -> str:
        return snapshot_digest(self.workspace, self.transaction_id)


@pytest.fixture
def preview_fixture(tmp_path: Path) -> Iterator[PreviewFixture]:
    workspace = tmp_path / "workspace"
    (workspace / "src").mkdir(parents=True)
    (workspace / "src" / "b.py").write_bytes(_PRE)
    result = prepare_transaction(
        workspace,
        (replace_entry(workspace, "src/b.py", _PRE, _POST_B),),
        _FAR_DEADLINE,
        FixedClock(0),
        NoFaultPort(),
    )
    assert not isinstance(result, GateTransactionRejectionV1)
    apply_transaction(
        result.transaction_id,
        PersistenceFaultPointV1("TERMINAL", "BEFORE", 0),
        FixedClock(0),
    )
    yield PreviewFixture(
        workspace=workspace,
        transaction_id=result.transaction_id,
        _before_digest=snapshot_digest(workspace, result.transaction_id),
    )


def test_preview_is_byte_for_byte_read_only(preview_fixture: PreviewFixture) -> None:
    preview_recovery(preview_fixture.workspace, preview_fixture.transaction_id)
    assert preview_fixture.after_digest() == preview_fixture.before_digest()


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
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL
    return kernel32


def _open_exclusive(path: Path) -> wintypes.HANDLE:
    """Open *path* with zero sharing so every other open fails."""
    handle = _kernel32().CreateFileW(str(path), 0x80000000, 0, None, 3, 0, None)
    assert handle != _INVALID_HANDLE_VALUE
    return wintypes.HANDLE(handle)


def _run_matrix_row(
    root: Path,
    index: int,
    spec: list[tuple[str, str, bytes | None, bytes]],
    fault: PersistenceFaultPointV1 | None,
    mutation: Callable[[Path], wintypes.HANDLE | None] | None,
) -> GateRecoveryPreviewV1:
    """Run one real-NTFS matrix row and return its immutable preview."""
    workspace = root / f"row-{index}"
    (workspace / "src").mkdir(parents=True)
    entries: list[GateWriteEntryV1] = []
    for rel, operation, preimage_bytes, postimage in spec:
        if operation == "CREATE":
            entries.append(create_entry(rel, postimage))
        else:
            (workspace / rel).write_bytes(preimage_bytes or b"")
            entries.append(
                replace_entry(workspace, rel, preimage_bytes or b"", postimage)
            )
    result = prepare_transaction(
        workspace,
        tuple(entries),
        _FAR_DEADLINE,
        FixedClock(0),
        NoFaultPort(),
    )
    assert not isinstance(result, GateTransactionRejectionV1)
    if fault is not None:
        apply_transaction(result.transaction_id, fault, FixedClock(0))
    holder: wintypes.HANDLE | None = None
    try:
        if mutation is not None:
            holder = mutation(workspace)
        return preview_recovery(workspace, result.transaction_id)
    finally:
        if holder is not None:
            assert bool(_kernel32().CloseHandle(holder))


def test_recovery_preview_disposition_matrix(tmp_path: Path) -> None:
    """Every closed mixed-path byte state maps to one disposition with zero
    writes: all-postimage is COMMITTED, all at preimage (or a provably
    restorable postimage CREATE) is ROLLED_BACK, and any external,
    unprovable, or REPLACE-mixed state is UNRESOLVED."""
    rows: list[
        tuple[
            list[tuple[str, str, bytes | None, bytes]],
            PersistenceFaultPointV1 | None,
            Callable[[Path], wintypes.HANDLE | None] | None,
            GateRecoveryDispositionV1,
        ]
    ] = [
        # Unapplied CREATE+REPLACE: ABSENT + PREIMAGE -> ROLLED_BACK.
        (
            [
                ("src/a.py", "CREATE", None, _POST_A),
                ("src/b.py", "REPLACE", _PRE, _POST_B),
            ],
            None,
            None,
            "ROLLED_BACK",
        ),
        # Three-file mixed CREATE/REPLACE fully applied -> COMMITTED.
        (
            [
                ("src/a.py", "REPLACE", b"original a\n", _POST_A),
                ("src/b.py", "CREATE", None, _POST_B),
                ("src/c.py", "REPLACE", b"original c\n", _POST_C),
            ],
            PersistenceFaultPointV1("TERMINAL", "BEFORE", 0),
            None,
            "COMMITTED",
        ),
        # Applied CREATE plus untouched REPLACE: POSTIMAGE-CREATE + PREIMAGE
        # is provably restorable to ABSENT -> ROLLED_BACK (AC-29 safe
        # ABSENT rollback).
        (
            [
                ("src/a.py", "CREATE", None, _POST_A),
                ("src/b.py", "REPLACE", _PRE, _POST_B),
            ],
            PersistenceFaultPointV1("PROGRESS", "BEFORE", 1),
            None,
            "ROLLED_BACK",
        ),
        # Applied REPLACE plus absent CREATE: POSTIMAGE-REPLACE + ABSENT is
        # a contradictory mixed state -> UNRESOLVED.
        (
            [
                ("src/a.py", "REPLACE", b"original a\n", _POST_A),
                ("src/b.py", "CREATE", None, _POST_B),
            ],
            PersistenceFaultPointV1("REPLACE", "BEFORE", 2),
            None,
            "UNRESOLVED",
        ),
        # Externally overwritten new file -> UNRESOLVED, never coerced.
        (
            [("src/b.py", "CREATE", None, _POST_B)],
            PersistenceFaultPointV1("TERMINAL", "BEFORE", 0),
            lambda workspace: _write_foreign(workspace, "src/b.py"),
            "UNRESOLVED",
        ),
        # Directory replacing the target -> EXTERNAL_CHANGE -> UNRESOLVED.
        (
            [("src/b.py", "REPLACE", _PRE, _POST_B)],
            PersistenceFaultPointV1("TERMINAL", "BEFORE", 0),
            lambda workspace: _replace_with_directory(workspace, "src/b.py"),
            "UNRESOLVED",
        ),
        # Locked (unobservable) target -> UNPROVABLE -> UNRESOLVED.
        (
            [("src/b.py", "REPLACE", _PRE, _POST_B)],
            PersistenceFaultPointV1("TERMINAL", "BEFORE", 0),
            lambda workspace: _open_exclusive(workspace / "src" / "b.py"),
            "UNRESOLVED",
        ),
        # A deleted REPLACE target (PRESENT preimage, object missing) is
        # an EXTERNAL_CHANGE -> UNRESOLVED.
        (
            [("src/b.py", "REPLACE", _PRE, _POST_B)],
            PersistenceFaultPointV1("TERMINAL", "BEFORE", 0),
            lambda workspace: _delete_target(workspace, "src/b.py"),
            "UNRESOLVED",
        ),
    ]
    for index, (spec, fault, mutation, expected) in enumerate(rows, start=1):
        preview = _run_matrix_row(tmp_path, index, spec, fault, mutation)
        assert preview.disposition == expected, (spec, preview)
        assert preview.workspace_write_count == 0, (spec, preview)


def _write_foreign(workspace: Path, rel: str) -> None:
    (workspace / rel).write_bytes(b"foreign external bytes\n")


def _replace_with_directory(workspace: Path, rel: str) -> None:
    target = workspace / rel
    target.unlink()
    target.mkdir()


def _delete_target(workspace: Path, rel: str) -> None:
    (workspace / rel).unlink()


def test_preview_read_only_for_rolled_back_state(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    (workspace / "src").mkdir(parents=True)
    (workspace / "src" / "b.py").write_bytes(_PRE)
    result = prepare_transaction(
        workspace,
        (replace_entry(workspace, "src/b.py", _PRE, _POST_B),),
        _FAR_DEADLINE,
        FixedClock(0),
        NoFaultPort(),
    )
    assert not isinstance(result, GateTransactionRejectionV1)
    before = snapshot_digest(workspace, result.transaction_id)
    preview = preview_recovery(workspace, result.transaction_id)
    assert preview.disposition == "ROLLED_BACK"
    assert snapshot_digest(workspace, result.transaction_id) == before


def test_preview_read_only_for_unresolved_state(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    (workspace / "src").mkdir(parents=True)
    (workspace / "src" / "b.py").write_bytes(_PRE)
    result = prepare_transaction(
        workspace,
        (replace_entry(workspace, "src/b.py", _PRE, _POST_B),),
        _FAR_DEADLINE,
        FixedClock(0),
        NoFaultPort(),
    )
    assert not isinstance(result, GateTransactionRejectionV1)
    apply_transaction(
        result.transaction_id,
        PersistenceFaultPointV1("TERMINAL", "BEFORE", 0),
        FixedClock(0),
    )
    _write_foreign(workspace, "src/b.py")
    before = snapshot_digest(workspace, result.transaction_id)
    preview = preview_recovery(workspace, result.transaction_id)
    assert preview.disposition == "UNRESOLVED"
    assert snapshot_digest(workspace, result.transaction_id) == before


def test_preview_fails_closed_on_missing_record(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    with pytest.raises(ValueError, match="no durable transaction record"):
        preview_recovery(workspace, "txn-missing-preview")


def test_preview_fails_closed_on_tampered_record(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    (workspace / "src").mkdir(parents=True)
    transaction = prepared_replace_transaction(workspace)
    record_path = transaction_record_path(transaction.transaction_id)
    data = json.loads(record_path.read_bytes())
    digest = data["records"][0]["postimage_digest"]
    flipped = ("0" if digest[0] != "0" else "1") + digest[1:]
    data["records"][0]["postimage_digest"] = flipped
    record_path.write_bytes(json.dumps(data).encode("utf-8"))
    before = snapshot_digest(workspace, transaction.transaction_id)
    with pytest.raises(ValueError, match="postimage bytes that do not match"):
        preview_recovery(workspace, transaction.transaction_id)
    assert snapshot_digest(workspace, transaction.transaction_id) == before


def test_preview_fails_closed_on_workspace_mismatch(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    (workspace / "src").mkdir(parents=True)
    transaction = prepared_replace_transaction(workspace)
    other = tmp_path / "other-workspace"
    other.mkdir()
    with pytest.raises(ValueError, match="does not belong"):
        preview_recovery(other, transaction.transaction_id)


def test_preview_fails_closed_on_empty_records(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    empty = GateTransactionV1(
        transaction_id="txn-empty-preview",
        workspace=workspace.resolve(),
        state="PREPARED",
        deadline_ms=_FAR_DEADLINE,
        prepared_at_ms=0,
        updated_at_ms=0,
        workspace_write_count=0,
        records=(),
    )
    save_transaction(empty)
    with pytest.raises(ValueError, match="no path records"):
        preview_recovery(workspace, "txn-empty-preview")


def test_preview_binds_transaction_and_every_path(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    (workspace / "src").mkdir(parents=True)
    (workspace / "src" / "b.py").write_bytes(_PRE)
    result = prepare_transaction(
        workspace,
        (
            create_entry("src/a.py", _POST_A),
            replace_entry(workspace, "src/b.py", _PRE, _POST_B),
        ),
        _FAR_DEADLINE,
        FixedClock(0),
        NoFaultPort(),
    )
    assert not isinstance(result, GateTransactionRejectionV1)
    preview = preview_recovery(workspace, result.transaction_id)
    assert preview.transaction_id == result.transaction_id
    assert tuple(
        (entry.path, entry.classification) for entry in preview.path_classifications
    ) == (
        ("src/a.py", "ABSENT"),
        ("src/b.py", "PREIMAGE"),
    )
    with pytest.raises(Exception):
        preview.path_classifications = ()  # type: ignore[misc]


def test_preview_digest_is_deterministic_and_binding(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    (workspace / "src").mkdir(parents=True)
    transaction = prepared_replace_transaction(workspace)
    first = preview_recovery(workspace, transaction.transaction_id)
    second = preview_recovery(workspace, transaction.transaction_id)
    assert compute_preview_digest(first) == compute_preview_digest(second)
    apply_transaction(
        transaction.transaction_id,
        PersistenceFaultPointV1("TERMINAL", "BEFORE", 0),
        FixedClock(0),
    )
    changed = preview_recovery(workspace, transaction.transaction_id)
    assert changed.disposition == "COMMITTED"
    assert compute_preview_digest(changed) != compute_preview_digest(first)


def test_preview_on_terminal_record_is_read_only(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    (workspace / "src").mkdir(parents=True)
    transaction = prepared_replace_transaction(workspace)
    apply_transaction(
        transaction.transaction_id,
        PersistenceFaultPointV1("TERMINAL", "AFTER", 0),
        FixedClock(0),
    )
    before = snapshot_digest(workspace, transaction.transaction_id)
    preview = preview_recovery(workspace, transaction.transaction_id)
    assert preview.disposition == "COMMITTED"
    assert snapshot_digest(workspace, transaction.transaction_id) == before


def test_observer_classifies_real_ntfs_objects(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    (workspace / "src").mkdir(parents=True)
    (workspace / "src" / "b.py").write_bytes(_PRE)
    absent = observe_workspace_path(workspace, "src/missing.py")
    assert absent.object_kind == "ABSENT" and absent.supported
    file_obs = observe_workspace_path(workspace, "src/b.py")
    assert file_obs.object_kind == "FILE" and file_obs.supported
    assert file_obs.content_digest == hashlib.sha256(_PRE).hexdigest()
    assert file_obs.volume_serial != 0 and len(file_obs.file_id_128) > 0
    dir_obs = observe_workspace_path(workspace, "src")
    assert dir_obs.object_kind == "DIRECTORY" and dir_obs.supported
    holder = _open_exclusive(workspace / "src" / "b.py")
    try:
        locked = observe_workspace_path(workspace, "src/b.py")
        assert locked.supported is False
    finally:
        assert bool(_kernel32().CloseHandle(holder))

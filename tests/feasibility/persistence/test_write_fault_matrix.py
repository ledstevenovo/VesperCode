"""T03.1 legacy step 3.B: deterministic write fault matrix tests.

Covers the complete immutable fault sequence, deterministic
interruption at every before/after PREPARED/WRITING/replace/progress/
terminal point, and the durable classifiable observation left by every
interruption.
"""

from __future__ import annotations

import dataclasses
import hashlib
import shutil
import tempfile
from pathlib import Path
from typing import Iterator

import pytest

from spikes.persistence_recovery.faults import (
    GatePersistenceResultV1,
    PersistenceFaultPointV1,
    apply_transaction,
    persistence_fault_sequence,
)
from spikes.persistence_recovery.protocol import (
    FixedClock,
    GatePreimageV1,
    GateTransactionV1,
    GateWriteEntryV1,
    NoFaultPort,
    PersistenceFaultInjectedError,
    load_transaction,
    prepare_transaction,
    save_transaction,
    transaction_root,
)

_ORIGINAL = {
    "src/b.py": b"original b\n",
    "src/c.py": b"original c\n",
}
_POST = {
    "src/a.py": b"post a\n",
    "src/b.py": b"post b\n",
    "src/c.py": b"post c\n",
}
_PREIMAGE_VOLUME = 7
_PREIMAGE_FILE_ID = b"\x07" * 16

_TEMP_WORKSPACES: list[Path] = []


def workspace() -> Path:
    """One fresh disposable workspace with a ``src`` directory."""
    path = Path(tempfile.mkdtemp(prefix="vesper-fault-ws-"))
    (path / "src").mkdir()
    _TEMP_WORKSPACES.append(path)
    return path


def clock() -> FixedClock:
    """One deterministic fixed clock."""
    return FixedClock(fixed_now_ms=200)


def faults() -> NoFaultPort:
    """One deterministic no-fault injection port."""
    return NoFaultPort()


class ArmedFaultPort:
    """A deterministic fault port that interrupts exactly one armed point."""

    def __init__(self, point: PersistenceFaultPointV1) -> None:
        self._point = point

    def raise_at(self, point: PersistenceFaultPointV1) -> None:
        if point == self._point:
            raise PersistenceFaultInjectedError(f"armed fault point: {point}")


def _seed_workspace(path: Path) -> None:
    """Seed the REPLACE targets with their original preimage bytes."""
    for relative, content in _ORIGINAL.items():
        (path / relative).write_bytes(content)


def three_path_entries(workspace_path: Path) -> tuple[GateWriteEntryV1, ...]:
    """One CREATE plus two REPLACE entries whose preimage digests match the
    seeded workspace bytes."""
    return (
        GateWriteEntryV1(
            path="src/a.py",
            operation="CREATE",
            preimage=GatePreimageV1(kind="ABSENT"),
            postimage=_POST["src/a.py"],
            backup_ref="",
        ),
        GateWriteEntryV1(
            path="src/b.py",
            operation="REPLACE",
            preimage=GatePreimageV1(
                kind="PRESENT",
                raw_bytes_digest=hashlib.sha256(_ORIGINAL["src/b.py"]).hexdigest(),
                volume_serial=_PREIMAGE_VOLUME,
                file_id_128=_PREIMAGE_FILE_ID,
            ),
            postimage=_POST["src/b.py"],
            backup_ref="txn-backup/0002.bin",
        ),
        GateWriteEntryV1(
            path="src/c.py",
            operation="REPLACE",
            preimage=GatePreimageV1(
                kind="PRESENT",
                raw_bytes_digest=hashlib.sha256(_ORIGINAL["src/c.py"]).hexdigest(),
                volume_serial=_PREIMAGE_VOLUME,
                file_id_128=_PREIMAGE_FILE_ID,
            ),
            postimage=_POST["src/c.py"],
            backup_ref="txn-backup/0003.bin",
        ),
    )


def three_path_transaction() -> GateTransactionV1:
    """One fresh seeded workspace with a prepared three-path transaction."""
    ws = workspace()
    _seed_workspace(ws)
    prepared = prepare_transaction(ws, three_path_entries(ws), 1_000, clock(), faults())
    assert isinstance(prepared, GateTransactionV1)
    return prepared


@dataclasses.dataclass(frozen=True)
class RunAllFaultsResult:
    missing_fault_points: tuple[PersistenceFaultPointV1, ...]


def run_all_replace_faults(transaction: GateTransactionV1) -> RunAllFaultsResult:
    """For every apply-side fault point, run a fresh PREPARED transaction
    stopped at that point and verify every path keeps one durable,
    classifiable observation; return the points where some path lacked
    one.  PREPARED points are injected through prepare_transaction's
    fault port and are covered by dedicated tests."""
    missing: list[PersistenceFaultPointV1] = []
    for point in persistence_fault_sequence(len(transaction.records)):
        if point.kind == "PREPARED":
            continue
        fresh = _fresh_transaction(transaction)
        result = apply_transaction(fresh.transaction_id, point, clock())
        assert result.fault_point == point
        if not _all_paths_durably_classifiable(fresh.workspace, fresh.transaction_id):
            missing.append(point)
    return RunAllFaultsResult(missing_fault_points=tuple(missing))


def _fresh_transaction(transaction: GateTransactionV1) -> GateTransactionV1:
    """A fresh PREPARED transaction with the same entries on a new workspace."""
    entries = tuple(
        GateWriteEntryV1(
            path=record.path,
            operation=record.operation,
            preimage=record.preimage,
            postimage=record.postimage,
            backup_ref=record.backup_ref,
        )
        for record in transaction.records
    )
    ws = workspace()
    _seed_workspace(ws)
    prepared = prepare_transaction(
        ws, entries, transaction.deadline_ms, clock(), faults()
    )
    assert isinstance(prepared, GateTransactionV1)
    return prepared


def _all_paths_durably_classifiable(workspace_path: Path, transaction_id: str) -> bool:
    """True when every path has a complete durable record and its current
    bytes (or absence) are consistent with that record's preimage or
    postimage evidence, so a classifier can always produce a definite
    classification and no write was skipped, corrupted, or deleted."""
    try:
        transaction = load_transaction(transaction_id)
    except ValueError:
        return False
    for record in transaction.records:
        target = workspace_path / record.path
        if not target.exists():
            if record.preimage.kind != "ABSENT":
                return False
            continue
        try:
            digest = hashlib.sha256(target.read_bytes()).hexdigest()
        except OSError:
            return False
        if digest not in (record.postimage_digest, record.preimage.raw_bytes_digest):
            return False
    return True


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


def _path_state(workspace_path: Path, path: str) -> str:
    """One closed byte-state token: ABSENT, ORIG, POST, or OTHER."""
    target = workspace_path / path
    if not target.exists():
        return "ABSENT"
    current = target.read_bytes()
    if current == _POST[path]:
        return "POST"
    if current == _ORIGINAL.get(path, b""):
        return "ORIG"
    return "OTHER"


def test_interruption_after_each_replace_has_durable_observation() -> None:
    assert run_all_replace_faults(three_path_transaction()).missing_fault_points == ()


def test_apply_requires_prepared_transaction() -> None:
    with pytest.raises(ValueError):
        apply_transaction(
            "txn-does-not-exist", PersistenceFaultPointV1("WRITING", "BEFORE"), clock()
        )
    transaction = three_path_transaction()
    terminal = PersistenceFaultPointV1("TERMINAL", "AFTER")
    apply_transaction(transaction.transaction_id, terminal, clock())
    with pytest.raises(ValueError):
        apply_transaction(transaction.transaction_id, terminal, clock())


def test_apply_rejects_prepared_fault_points() -> None:
    transaction = three_path_transaction()
    with pytest.raises(ValueError):
        apply_transaction(
            transaction.transaction_id,
            PersistenceFaultPointV1("PREPARED", "BEFORE"),
            clock(),
        )


def test_apply_completes_through_terminal_point() -> None:
    transaction = three_path_transaction()
    result = apply_transaction(
        transaction.transaction_id,
        PersistenceFaultPointV1("TERMINAL", "AFTER"),
        clock(),
    )
    assert isinstance(result, GatePersistenceResultV1)
    assert result.final_state == "COMMITTED"
    assert result.workspace_write_count == 3
    reloaded = load_transaction(transaction.transaction_id)
    assert reloaded.state == "COMMITTED"
    assert reloaded.workspace_write_count == 3
    assert all(record.durable_state == "REPLACED" for record in reloaded.records)
    assert all(
        _path_state(transaction.workspace, record.path) == "POST"
        for record in reloaded.records
    )
    with pytest.raises(dataclasses.FrozenInstanceError):
        result.final_state = "UNRESOLVED"  # type: ignore[misc]


def test_apply_is_deterministic_across_fresh_runs() -> None:
    """Same point on fresh equivalent transactions yields identical outcomes
    (transaction ids are content-addressed per workspace and therefore
    differ between the two fresh runs)."""
    point = PersistenceFaultPointV1("PROGRESS", "AFTER", 2)
    first = apply_transaction(three_path_transaction().transaction_id, point, clock())
    second = apply_transaction(three_path_transaction().transaction_id, point, clock())
    assert first.fault_point == second.fault_point
    assert first.final_state == second.final_state
    assert first.workspace_write_count == second.workspace_write_count


def _tamper_first_record_path(transaction: GateTransactionV1, path: str) -> str:
    """Rewrite the durable record with a tampered first path and return the
    transaction id (the write-time confinement guard must still fail)."""
    tampered_records = tuple(
        dataclasses.replace(record, path=path) if record.sequence == 1 else record
        for record in transaction.records
    )
    tampered = dataclasses.replace(transaction, records=tampered_records)
    save_transaction(tampered)
    return transaction.transaction_id


def test_apply_rejects_escaping_path() -> None:
    """A hand-tampered durable record escaping the workspace fails closed at
    write time with a deterministic persistence error."""
    transaction = three_path_transaction()
    transaction_id = _tamper_first_record_path(transaction, "..\\evil.txt")
    with pytest.raises(ValueError):
        apply_transaction(
            transaction_id,
            PersistenceFaultPointV1("TERMINAL", "AFTER"),
            clock(),
        )


def test_apply_rejects_workspace_root_target() -> None:
    """A hand-tampered record targeting the workspace root itself fails
    closed before any replace."""
    transaction = three_path_transaction()
    transaction_id = _tamper_first_record_path(transaction, ".")
    with pytest.raises(ValueError):
        apply_transaction(
            transaction_id,
            PersistenceFaultPointV1("TERMINAL", "AFTER"),
            clock(),
        )


def test_apply_rejects_missing_parent_directory() -> None:
    ws = workspace()
    deep = GateWriteEntryV1(
        path="src/nested/deep.py",
        operation="CREATE",
        preimage=GatePreimageV1(kind="ABSENT"),
        postimage=b"deep\n",
        backup_ref="",
    )
    prepared = prepare_transaction(ws, (deep,), 1_000, clock(), faults())
    assert isinstance(prepared, GateTransactionV1)
    with pytest.raises(ValueError):
        apply_transaction(
            prepared.transaction_id,
            PersistenceFaultPointV1("TERMINAL", "AFTER"),
            clock(),
        )


def test_prepared_fault_points_leave_deterministic_state() -> None:
    before = PersistenceFaultPointV1("PREPARED", "BEFORE")
    ws_before = workspace()
    _seed_workspace(ws_before)
    with pytest.raises(PersistenceFaultInjectedError):
        prepare_transaction(
            ws_before,
            three_path_entries(ws_before),
            1_000,
            clock(),
            ArmedFaultPort(before),
        )
    assert not list(transaction_root().glob("*.json"))
    assert _path_state(ws_before, "src/b.py") == "ORIG"

    after = PersistenceFaultPointV1("PREPARED", "AFTER")
    ws_after = workspace()
    _seed_workspace(ws_after)
    with pytest.raises(PersistenceFaultInjectedError):
        prepare_transaction(
            ws_after,
            three_path_entries(ws_after),
            1_000,
            clock(),
            ArmedFaultPort(after),
        )
    records = sorted(transaction_root().glob("*.json"))
    assert len(records) == 1
    transaction = load_transaction(records[0].stem)
    assert transaction.state == "PREPARED"
    assert _path_state(ws_after, "src/b.py") == "ORIG"
    assert _path_state(ws_after, "src/a.py") == "ABSENT"


def test_fault_point_validation_is_closed() -> None:
    with pytest.raises(ValueError):
        PersistenceFaultPointV1("REPLACE", "BEFORE", 0)
    with pytest.raises(ValueError):
        PersistenceFaultPointV1("REPLACE", "BEFORE", -1)
    with pytest.raises(ValueError):
        PersistenceFaultPointV1("PREPARED", "BEFORE", 1)


def test_replace_fault_vocabulary_matrix() -> None:
    """The complete ordered fault sequence for every path cardinality."""
    for count in (1, 2, 3):
        sequence = persistence_fault_sequence(count)
        assert isinstance(sequence, tuple)
        expected: list[PersistenceFaultPointV1] = [
            PersistenceFaultPointV1("PREPARED", "BEFORE"),
            PersistenceFaultPointV1("PREPARED", "AFTER"),
            PersistenceFaultPointV1("WRITING", "BEFORE"),
            PersistenceFaultPointV1("WRITING", "AFTER"),
        ]
        for index in range(1, count + 1):
            expected.append(PersistenceFaultPointV1("REPLACE", "BEFORE", index))
            expected.append(PersistenceFaultPointV1("REPLACE", "AFTER", index))
            expected.append(PersistenceFaultPointV1("PROGRESS", "BEFORE", index))
            expected.append(PersistenceFaultPointV1("PROGRESS", "AFTER", index))
        expected.append(PersistenceFaultPointV1("TERMINAL", "BEFORE"))
        expected.append(PersistenceFaultPointV1("TERMINAL", "AFTER"))
        assert sequence == tuple(expected)
        assert len(sequence) == 6 + 4 * count
    for bad_count in (0, 4):
        with pytest.raises(ValueError):
            persistence_fault_sequence(bad_count)


def test_fault_point_leftover_state_matrix() -> None:
    """Every interruption point leaves the exact durable state: transaction
    state, per-path durable states, workspace byte states, the in-memory
    replace count at the stop, and the durably persisted write count
    (which lags until the next progress/terminal write, SPEC 4.6 item 8)."""
    rows: list[
        tuple[
            PersistenceFaultPointV1,
            str,
            tuple[str, str, str],
            tuple[str, str, str],
            int,
            int,
        ]
    ] = [
        (
            PersistenceFaultPointV1("WRITING", "BEFORE"),
            "PREPARED",
            ("NOT_STARTED", "NOT_STARTED", "NOT_STARTED"),
            ("ABSENT", "ORIG", "ORIG"),
            0,
            0,
        ),
        (
            PersistenceFaultPointV1("WRITING", "AFTER"),
            "WRITING",
            ("NOT_STARTED", "NOT_STARTED", "NOT_STARTED"),
            ("ABSENT", "ORIG", "ORIG"),
            0,
            0,
        ),
        (
            PersistenceFaultPointV1("REPLACE", "BEFORE", 1),
            "WRITING",
            ("NOT_STARTED", "NOT_STARTED", "NOT_STARTED"),
            ("ABSENT", "ORIG", "ORIG"),
            0,
            0,
        ),
        (
            PersistenceFaultPointV1("REPLACE", "AFTER", 1),
            "WRITING",
            ("NOT_STARTED", "NOT_STARTED", "NOT_STARTED"),
            ("POST", "ORIG", "ORIG"),
            1,
            0,
        ),
        (
            PersistenceFaultPointV1("PROGRESS", "BEFORE", 1),
            "WRITING",
            ("NOT_STARTED", "NOT_STARTED", "NOT_STARTED"),
            ("POST", "ORIG", "ORIG"),
            1,
            0,
        ),
        (
            PersistenceFaultPointV1("PROGRESS", "AFTER", 1),
            "WRITING",
            ("REPLACED", "NOT_STARTED", "NOT_STARTED"),
            ("POST", "ORIG", "ORIG"),
            1,
            1,
        ),
        (
            PersistenceFaultPointV1("REPLACE", "BEFORE", 2),
            "WRITING",
            ("REPLACED", "NOT_STARTED", "NOT_STARTED"),
            ("POST", "ORIG", "ORIG"),
            1,
            1,
        ),
        (
            PersistenceFaultPointV1("REPLACE", "AFTER", 2),
            "WRITING",
            ("REPLACED", "NOT_STARTED", "NOT_STARTED"),
            ("POST", "POST", "ORIG"),
            2,
            1,
        ),
        (
            PersistenceFaultPointV1("PROGRESS", "BEFORE", 2),
            "WRITING",
            ("REPLACED", "NOT_STARTED", "NOT_STARTED"),
            ("POST", "POST", "ORIG"),
            2,
            1,
        ),
        (
            PersistenceFaultPointV1("PROGRESS", "AFTER", 2),
            "WRITING",
            ("REPLACED", "REPLACED", "NOT_STARTED"),
            ("POST", "POST", "ORIG"),
            2,
            2,
        ),
        (
            PersistenceFaultPointV1("REPLACE", "BEFORE", 3),
            "WRITING",
            ("REPLACED", "REPLACED", "NOT_STARTED"),
            ("POST", "POST", "ORIG"),
            2,
            2,
        ),
        (
            PersistenceFaultPointV1("REPLACE", "AFTER", 3),
            "WRITING",
            ("REPLACED", "REPLACED", "NOT_STARTED"),
            ("POST", "POST", "POST"),
            3,
            2,
        ),
        (
            PersistenceFaultPointV1("PROGRESS", "BEFORE", 3),
            "WRITING",
            ("REPLACED", "REPLACED", "NOT_STARTED"),
            ("POST", "POST", "POST"),
            3,
            2,
        ),
        (
            PersistenceFaultPointV1("PROGRESS", "AFTER", 3),
            "WRITING",
            ("REPLACED", "REPLACED", "REPLACED"),
            ("POST", "POST", "POST"),
            3,
            3,
        ),
        (
            PersistenceFaultPointV1("TERMINAL", "BEFORE"),
            "WRITING",
            ("REPLACED", "REPLACED", "REPLACED"),
            ("POST", "POST", "POST"),
            3,
            3,
        ),
        (
            PersistenceFaultPointV1("TERMINAL", "AFTER"),
            "COMMITTED",
            ("REPLACED", "REPLACED", "REPLACED"),
            ("POST", "POST", "POST"),
            3,
            3,
        ),
    ]
    for point, state, durable, byte_states, result_count, durable_count in rows:
        transaction = three_path_transaction()
        result = apply_transaction(transaction.transaction_id, point, clock())
        assert result.final_state == state, point
        assert result.workspace_write_count == result_count, point
        reloaded = load_transaction(transaction.transaction_id)
        assert reloaded.state == state, point
        assert tuple(record.durable_state for record in reloaded.records) == durable, (
            point
        )
        assert reloaded.workspace_write_count == durable_count, point
        assert (
            tuple(
                _path_state(transaction.workspace, record.path)
                for record in reloaded.records
            )
            == byte_states
        ), point

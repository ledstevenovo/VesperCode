"""T03.1 legacy step 3.A: durable persistence transaction protocol tests.

Covers the closed rejection matrix (cardinality, create count, sorted
order, preimage binding, active-transaction state), the injected
PREPARED fault points, and durable valid PREPARED record creation
without any workspace mutation.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import shutil
import tempfile
from pathlib import Path
from typing import Callable, Iterator

import pytest

from spikes.persistence_recovery.protocol import (
    FixedClock,
    GatePathRecordV1,
    GatePreimageV1,
    GateTransactionRejectionV1,
    GateTransactionV1,
    GateWriteEntryV1,
    GateWriteEntrySequenceV1,
    NoFaultPort,
    PersistenceFaultInjectedError,
    PersistenceFaultPointV1,
    compute_transaction_id,
    load_transaction,
    prepare_transaction,
    transaction_record_path,
    transaction_root,
)

_PREIMAGE_DIGEST = "11" * 32
_PREIMAGE_VOLUME = 7
_PREIMAGE_FILE_ID = b"\x07" * 16
_BACKUP_REF = "txn-backup/0001.bin"

_TEMP_WORKSPACES: list[Path] = []


def workspace() -> Path:
    """One fresh disposable workspace with a ``src`` directory."""
    path = Path(tempfile.mkdtemp(prefix="vesper-txn-ws-"))
    (path / "src").mkdir()
    _TEMP_WORKSPACES.append(path)
    return path


def clock() -> FixedClock:
    """One deterministic fixed clock."""
    return FixedClock(fixed_now_ms=100)


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


def create_entry(path: str, postimage: bytes = b"a = 1\n") -> GateWriteEntryV1:
    """One CREATE entry with a typed ABSENT preimage."""
    return GateWriteEntryV1(
        path=path,
        operation="CREATE",
        preimage=GatePreimageV1(kind="ABSENT"),
        postimage=postimage,
        backup_ref="",
    )


def replace_entry(path: str, postimage: bytes = b"b = 2\n") -> GateWriteEntryV1:
    """One REPLACE entry with a typed PRESENT preimage and backup reference."""
    return GateWriteEntryV1(
        path=path,
        operation="REPLACE",
        preimage=GatePreimageV1(
            kind="PRESENT",
            raw_bytes_digest=_PREIMAGE_DIGEST,
            volume_serial=_PREIMAGE_VOLUME,
            file_id_128=_PREIMAGE_FILE_ID,
        ),
        postimage=postimage,
        backup_ref=_BACKUP_REF,
    )


def two_create_entries() -> GateWriteEntrySequenceV1:
    """Two sorted CREATE entries (invalid: more than one new file)."""
    return (create_entry("src/a.py"), create_entry("src/b.py"))


def three_path_entries() -> GateWriteEntrySequenceV1:
    """One sorted CREATE plus two sorted REPLACE entries."""
    return (
        create_entry("src/a.py", b"a = 1\n"),
        replace_entry("src/b.py", b"b = 2\n"),
        replace_entry("src/c.py", b"c = 3\n"),
    )


def four_entries() -> GateWriteEntrySequenceV1:
    """Four sorted entries (invalid cardinality)."""
    return (
        create_entry("src/a.py"),
        replace_entry("src/b.py"),
        replace_entry("src/c.py"),
        replace_entry("src/d.py"),
    )


def unsorted_entries() -> GateWriteEntrySequenceV1:
    """Two entries in descending path order."""
    return (replace_entry("src/z.py"), create_entry("src/a.py"))


def duplicate_path_entries() -> GateWriteEntrySequenceV1:
    """Two entries naming the same path."""
    return (
        create_entry("src/a.py"),
        replace_entry("src/a.py"),
    )


def create_with_present_preimage() -> GateWriteEntrySequenceV1:
    """A CREATE entry bound to a PRESENT preimage (invalid preimage)."""
    entry = create_entry("src/a.py")
    return (
        dataclasses.replace(
            entry,
            preimage=GatePreimageV1(
                kind="PRESENT",
                raw_bytes_digest=_PREIMAGE_DIGEST,
                volume_serial=_PREIMAGE_VOLUME,
                file_id_128=_PREIMAGE_FILE_ID,
            ),
        ),
    )


def replace_with_absent_preimage() -> GateWriteEntrySequenceV1:
    """A REPLACE entry bound to an ABSENT preimage (invalid preimage)."""
    entry = replace_entry("src/b.py")
    return (dataclasses.replace(entry, preimage=GatePreimageV1(kind="ABSENT")),)


def replace_without_backup() -> GateWriteEntrySequenceV1:
    """A REPLACE entry with no backup reference (invalid preimage)."""
    entry = replace_entry("src/b.py")
    return (dataclasses.replace(entry, backup_ref=""),)


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


def _durable_records() -> list[Path]:
    root = transaction_root()
    if not root.is_dir():
        return []
    return sorted(root.glob("*.json"))


def _workspace_entries(path: Path) -> list[Path]:
    return sorted(child for child in path.rglob("*") if child.is_file())


def _rejecting(entries: GateWriteEntrySequenceV1) -> GateTransactionRejectionV1:
    """One deterministic rejection result narrowed to the closed rejection type."""
    result = prepare_transaction(workspace(), entries, 1_000, clock(), faults())
    assert isinstance(result, GateTransactionRejectionV1)
    return result


def test_prepare_rejects_two_create_operations() -> None:
    assert _rejecting(two_create_entries()).error_code == "TOO_MANY_CREATES"


def test_prepare_rejects_empty_entries() -> None:
    result = _rejecting(())
    assert result.error_code == "INVALID_CARDINALITY"


def test_prepare_rejects_four_entries() -> None:
    result = _rejecting(four_entries())
    assert result.error_code == "INVALID_CARDINALITY"


def test_prepare_rejects_unsorted_entries() -> None:
    result = _rejecting(unsorted_entries())
    assert result.error_code == "UNSORTED_ENTRIES"


def test_prepare_rejects_duplicate_paths() -> None:
    result = _rejecting(duplicate_path_entries())
    assert result.error_code == "UNSORTED_ENTRIES"


def test_prepare_rejects_create_with_present_preimage() -> None:
    result = _rejecting(create_with_present_preimage())
    assert result.error_code == "INVALID_PREIMAGE"


def test_prepare_rejects_replace_with_absent_preimage() -> None:
    result = _rejecting(replace_with_absent_preimage())
    assert result.error_code == "INVALID_PREIMAGE"


def test_prepare_rejects_replace_without_backup_reference() -> None:
    result = _rejecting(replace_without_backup())
    assert result.error_code == "INVALID_PREIMAGE"


def test_prepare_rejects_active_transaction_for_workspace() -> None:
    ws = workspace()
    entries = three_path_entries()
    prepared = prepare_transaction(ws, entries, 1_000, clock(), faults())
    assert isinstance(prepared, GateTransactionV1)
    second = prepare_transaction(ws, entries, 1_000, clock(), faults())
    assert isinstance(second, GateTransactionRejectionV1)
    assert second.error_code == "INVALID_STATE"


def test_prepare_allows_identical_transaction_for_other_workspace() -> None:
    ws_one = workspace()
    ws_two = workspace()
    entries = three_path_entries()
    first = prepare_transaction(ws_one, entries, 1_000, clock(), faults())
    second = prepare_transaction(ws_two, entries, 1_000, clock(), faults())
    assert isinstance(first, GateTransactionV1)
    assert isinstance(second, GateTransactionV1)
    assert first.transaction_id != second.transaction_id


def test_rejection_vocabulary_matrix() -> None:
    """Every closed rejection fires before persistence, with zero writes."""
    cases: list[tuple[GateWriteEntrySequenceV1, str]] = [
        ((), "INVALID_CARDINALITY"),
        (four_entries(), "INVALID_CARDINALITY"),
        (two_create_entries(), "TOO_MANY_CREATES"),
        (unsorted_entries(), "UNSORTED_ENTRIES"),
        (duplicate_path_entries(), "UNSORTED_ENTRIES"),
        (create_with_present_preimage(), "INVALID_PREIMAGE"),
        (replace_with_absent_preimage(), "INVALID_PREIMAGE"),
        (replace_without_backup(), "INVALID_PREIMAGE"),
        ((create_entry(""),), "INVALID_PREIMAGE"),
        ((create_entry("."),), "INVALID_PREIMAGE"),
        ((create_entry("C:/evil.txt"),), "INVALID_PREIMAGE"),
        ((replace_entry("..\\evil.txt"),), "INVALID_PREIMAGE"),
    ]
    for entries, expected in cases:
        ws = workspace()
        result = prepare_transaction(ws, entries, 1_000, clock(), faults())
        assert isinstance(result, GateTransactionRejectionV1)
        assert result.error_code == expected
        assert result.workspace_write_count == 0
        assert _durable_records() == [], f"rejection {expected} persisted a record"
        assert _workspace_entries(ws) == [], f"rejection {expected} mutated workspace"


def test_prepare_rejects_degenerate_paths_before_persistence() -> None:
    """Empty, dot, absolute, and parent-escaping paths can never become a
    PREPARED transaction (a partially specified transaction cannot become
    PREPARED)."""
    degenerate = (
        ("empty path", (create_entry(""),)),
        ("dot path", (create_entry("."),)),
        ("absolute path", (create_entry("C:/evil.txt"),)),
        ("drive-relative path", (create_entry("C:evil.txt"),)),
        ("parent-escaping path", (replace_entry("..\\evil.txt"),)),
    )
    for label, entries in degenerate:
        ws = workspace()
        result = prepare_transaction(ws, entries, 1_000, clock(), faults())
        assert isinstance(result, GateTransactionRejectionV1), label
        assert result.error_code == "INVALID_PREIMAGE", label
        assert _durable_records() == [], f"{label} persisted a record"
        assert _workspace_entries(ws) == [], f"{label} mutated the workspace"


def test_prepare_accepts_one_to_three_sorted_entries() -> None:
    single_create = prepare_transaction(
        workspace(), (create_entry("src/a.py"),), 1_000, clock(), faults()
    )
    single_replace = prepare_transaction(
        workspace(), (replace_entry("src/b.py"),), 1_000, clock(), faults()
    )
    two_replaces = prepare_transaction(
        workspace(),
        (replace_entry("src/a.py"), replace_entry("src/b.py")),
        1_000,
        clock(),
        faults(),
    )
    three_paths = prepare_transaction(
        workspace(), three_path_entries(), 1_000, clock(), faults()
    )
    for transaction in (single_create, single_replace, two_replaces, three_paths):
        assert isinstance(transaction, GateTransactionV1)
        assert transaction.state == "PREPARED"


def test_valid_prepare_persists_durable_records() -> None:
    ws = workspace()
    entries = three_path_entries()
    transaction = prepare_transaction(ws, entries, 1_000, clock(), faults())
    assert isinstance(transaction, GateTransactionV1)
    assert transaction.state == "PREPARED"
    assert transaction.prepared_at_ms == 100
    assert transaction.updated_at_ms == 100
    assert transaction.workspace_write_count == 0
    assert len(transaction.records) == 3
    assert tuple(record.sequence for record in transaction.records) == (1, 2, 3)
    assert tuple(record.path for record in transaction.records) == (
        "src/a.py",
        "src/b.py",
        "src/c.py",
    )
    assert all(record.durable_state == "NOT_STARTED" for record in transaction.records)
    for record, entry in zip(transaction.records, entries, strict=True):
        assert record.postimage_digest == hashlib.sha256(entry.postimage).hexdigest()
        assert record.preimage == entry.preimage
        assert record.backup_ref == entry.backup_ref
    assert _durable_records() == [transaction_record_path(transaction.transaction_id)]
    assert load_transaction(transaction.transaction_id) == transaction
    assert _workspace_entries(ws) == [], "prepare must not mutate the workspace"


def test_prepare_records_are_immutable() -> None:
    transaction = prepare_transaction(
        workspace(), three_path_entries(), 1_000, clock(), faults()
    )
    assert isinstance(transaction, GateTransactionV1)
    with pytest.raises(dataclasses.FrozenInstanceError):
        transaction.state = "WRITING"  # type: ignore[misc]
    record = transaction.records[0]
    assert isinstance(record, GatePathRecordV1)
    with pytest.raises(dataclasses.FrozenInstanceError):
        record.durable_state = "REPLACED"  # type: ignore[misc]


def test_transaction_id_is_deterministic_content_addressed() -> None:
    ws = workspace()
    entries = three_path_entries()
    assert compute_transaction_id(ws, entries, 1_000) == compute_transaction_id(
        ws, entries, 1_000
    )
    assert compute_transaction_id(ws, entries, 1_000) != compute_transaction_id(
        ws, entries, 2_000
    )
    assert compute_transaction_id(ws, entries, 1_000) != compute_transaction_id(
        workspace(), entries, 1_000
    )
    other_entries = (create_entry("src/a.py"), replace_entry("src/b.py"))
    assert compute_transaction_id(ws, entries, 1_000) != compute_transaction_id(
        ws, other_entries, 1_000
    )


def test_prepare_prepared_fault_before_persists_nothing() -> None:
    ws = workspace()
    point = PersistenceFaultPointV1(kind="PREPARED", position="BEFORE")
    with pytest.raises(PersistenceFaultInjectedError):
        prepare_transaction(
            ws, three_path_entries(), 1_000, clock(), ArmedFaultPort(point)
        )
    assert _durable_records() == []
    assert _workspace_entries(ws) == []


def test_prepare_prepared_fault_after_persists_record() -> None:
    ws = workspace()
    point = PersistenceFaultPointV1(kind="PREPARED", position="AFTER")
    with pytest.raises(PersistenceFaultInjectedError):
        prepare_transaction(
            ws, three_path_entries(), 1_000, clock(), ArmedFaultPort(point)
        )
    records = _durable_records()
    assert len(records) == 1
    transaction = load_transaction(records[0].stem)
    assert transaction.state == "PREPARED"
    assert transaction.workspace == ws.resolve()
    assert _workspace_entries(ws) == [], (
        "interrupted prepare must not mutate the workspace"
    )


def test_load_transaction_missing_fails_closed() -> None:
    with pytest.raises(ValueError):
        load_transaction("txn-does-not-exist")


def _record_at(raw: dict[str, object], index: int) -> dict[str, object]:
    records = raw["records"]
    assert isinstance(records, list)
    record = records[index]
    assert isinstance(record, dict)
    return record


def _tamper_record_json(
    transaction: GateTransactionV1, mutate: Callable[[dict[str, object]], None]
) -> None:
    """Rewrite the durable record JSON with one mutation applied."""
    path = transaction_record_path(transaction.transaction_id)
    raw = json.loads(path.read_bytes().decode("utf-8"))
    mutate(raw)
    path.write_bytes(
        json.dumps(raw, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8")
    )


def test_load_rejects_record_with_forged_transaction_id() -> None:
    transaction = prepare_transaction(
        workspace(), three_path_entries(), 1_000, clock(), faults()
    )
    assert isinstance(transaction, GateTransactionV1)

    def forge(raw: dict[str, object]) -> None:
        raw["transaction_id"] = "txn-forged"

    _tamper_record_json(transaction, forge)
    # The file is still named by the original id, so the embedded id no
    # longer matches its filename and the record must fail closed.
    with pytest.raises(ValueError):
        load_transaction(transaction.transaction_id)


def test_load_rejects_record_with_mismatched_postimage_digest() -> None:
    transaction = prepare_transaction(
        workspace(), three_path_entries(), 1_000, clock(), faults()
    )
    assert isinstance(transaction, GateTransactionV1)

    def drift_digest(raw: dict[str, object]) -> None:
        _record_at(raw, 0)["postimage_digest"] = "00" * 32

    _tamper_record_json(transaction, drift_digest)
    with pytest.raises(ValueError):
        load_transaction(transaction.transaction_id)


def test_load_rejects_record_with_inconsistent_preimage() -> None:
    transaction = prepare_transaction(
        workspace(), three_path_entries(), 1_000, clock(), faults()
    )
    assert isinstance(transaction, GateTransactionV1)

    def drop_digest(raw: dict[str, object]) -> None:
        # records[1] is the first REPLACE record with a PRESENT preimage.
        preimage = _record_at(raw, 1)["preimage"]
        assert isinstance(preimage, dict)
        preimage["raw_bytes_digest"] = ""

    _tamper_record_json(transaction, drop_digest)
    with pytest.raises(ValueError):
        load_transaction(transaction.transaction_id)

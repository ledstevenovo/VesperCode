"""T03.1 legacy step 3.B: deterministic write fault matrix.

Applies sorted CREATE/REPLACE entries through temp, flush, replace,
progress, and terminal durable writes while exposing the complete
immutable :data:`PersistenceFaultSequenceV1`, with deterministic
interruption points before and after every required state write and
replace so that each interruption leaves one durable, classifiable
observation.  This module owns sorted write mechanics and injected
interruption points only: deadline policy, external-change safety, and
recovery disposition remain out of scope (legacy steps 3.C/3.D).

Interruption semantics: every :func:`apply_transaction` call stops at
its armed fault point and reports the durable state at the stop; arming
the final TERMINAL_AFTER point stops on the completed COMMITTED
transaction.  PREPARED points are injected through
``prepare_transaction``'s :class:`FaultPort` (legacy step 3.A) and are
rejected here.  Each durable state write is atomic (temp + flush +
fsync + :func:`os.replace`) and each workspace target is replaced
atomically, so no interruption can corrupt or half-write either.
"""

from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from pathlib import Path

from spikes.persistence_recovery.protocol import (
    ClockPort,
    FaultPointKindV1,
    FaultPointPositionV1,
    GatePathRecordV1,
    GateTransactionV1,
    PersistenceFaultPointV1,
    TransactionStateV1,
    _fsync_parent_directory,
    load_transaction,
    save_transaction,
)

__all__ = [
    "PersistenceFaultPointV1",
    "PersistenceFaultSequenceV1",
    "GatePersistenceResultV1",
    "apply_transaction",
    "persistence_fault_sequence",
]

PersistenceFaultSequenceV1 = tuple[PersistenceFaultPointV1, ...]


@dataclass(frozen=True)
class GatePersistenceResultV1:
    """Immutable report of one deterministically stopped apply run.

    ``final_state`` is the durable transaction state at the stop and
    ``workspace_write_count`` the number of completed workspace file
    replaces; both are the last durably persisted facts and are never
    an authority over current file bytes (SPEC 4.6 item 8).
    """

    transaction_id: str
    fault_point: PersistenceFaultPointV1
    final_state: TransactionStateV1
    workspace_write_count: int


def persistence_fault_sequence(record_count: int) -> PersistenceFaultSequenceV1:
    """The complete ordered immutable tuple of all required fault points for
    a transaction with *record_count* paths: before/after every PREPARED,
    WRITING, per-path replace, per-path progress, and terminal durable
    write, in the protocol's canonical order.
    """
    if not 1 <= record_count <= 3:
        raise ValueError("record_count must be 1..3 for the closed fault matrix")
    points: list[PersistenceFaultPointV1] = [
        PersistenceFaultPointV1("PREPARED", "BEFORE"),
        PersistenceFaultPointV1("PREPARED", "AFTER"),
        PersistenceFaultPointV1("WRITING", "BEFORE"),
        PersistenceFaultPointV1("WRITING", "AFTER"),
    ]
    for sequence in range(1, record_count + 1):
        points.append(PersistenceFaultPointV1("REPLACE", "BEFORE", sequence))
        points.append(PersistenceFaultPointV1("REPLACE", "AFTER", sequence))
        points.append(PersistenceFaultPointV1("PROGRESS", "BEFORE", sequence))
        points.append(PersistenceFaultPointV1("PROGRESS", "AFTER", sequence))
    points.append(PersistenceFaultPointV1("TERMINAL", "BEFORE"))
    points.append(PersistenceFaultPointV1("TERMINAL", "AFTER"))
    return tuple(points)


def apply_transaction(
    transaction_id: str,
    fault_point: PersistenceFaultPointV1,
    clock: ClockPort,
) -> GatePersistenceResultV1:
    """Apply one PREPARED transaction through temp/flush/replace/progress/
    terminal durable writes and deterministically stop at *fault_point*.

    The armed point that matches the first protocol step halts the run;
    a point outside this transaction's sequence never matches and the
    run completes.  Every state write and workspace replace is atomic,
    so each interruption leaves one durable, classifiable observation
    per path.
    """
    if fault_point.kind == "PREPARED":
        raise ValueError(
            "PREPARED fault points are injected through prepare_transaction's "
            "FaultPort, never through apply_transaction"
        )
    transaction = load_transaction(transaction_id)
    if transaction.state != "PREPARED":
        raise ValueError(
            "apply_transaction requires a PREPARED transaction, "
            f"found {transaction.state}"
        )
    _require_sorted_records(transaction)

    def stop_at(
        kind: FaultPointKindV1,
        position: FaultPointPositionV1,
        sequence: int,
        write_count: int,
    ) -> GatePersistenceResultV1 | None:
        if fault_point == PersistenceFaultPointV1(kind, position, sequence):
            return GatePersistenceResultV1(
                transaction_id=transaction_id,
                fault_point=fault_point,
                final_state=transaction.state,
                workspace_write_count=write_count,
            )
        return None

    stopped = stop_at("WRITING", "BEFORE", 0, 0)
    if stopped is not None:
        return stopped
    transaction = _rewrite_state(transaction, "WRITING", clock)
    stopped = stop_at("WRITING", "AFTER", 0, 0)
    if stopped is not None:
        return stopped
    write_count = 0
    for record in transaction.records:
        stopped = stop_at("REPLACE", "BEFORE", record.sequence, write_count)
        if stopped is not None:
            return stopped
        _replace_workspace_file(transaction.workspace, record)
        write_count += 1
        stopped = stop_at("REPLACE", "AFTER", record.sequence, write_count)
        if stopped is not None:
            return stopped
        _verify_replaced_bytes(transaction.workspace, record)
        stopped = stop_at("PROGRESS", "BEFORE", record.sequence, write_count)
        if stopped is not None:
            return stopped
        transaction = _write_progress(transaction, record.sequence, write_count, clock)
        stopped = stop_at("PROGRESS", "AFTER", record.sequence, write_count)
        if stopped is not None:
            return stopped
    _verify_all_postimages(transaction)
    stopped = stop_at("TERMINAL", "BEFORE", 0, write_count)
    if stopped is not None:
        return stopped
    transaction = _rewrite_state(transaction, "COMMITTED", clock, write_count)
    stopped = stop_at("TERMINAL", "AFTER", 0, write_count)
    if stopped is not None:
        return stopped
    return GatePersistenceResultV1(
        transaction_id=transaction_id,
        fault_point=fault_point,
        final_state="COMMITTED",
        workspace_write_count=write_count,
    )


def _require_sorted_records(transaction: GateTransactionV1) -> None:
    paths = [record.path for record in transaction.records]
    if any(left >= right for left, right in zip(paths, paths[1:])):
        raise ValueError("durable path records must be sorted by path")


def _rewrite_state(
    transaction: GateTransactionV1,
    state: TransactionStateV1,
    clock: ClockPort,
    write_count: int | None = None,
) -> GateTransactionV1:
    updated = GateTransactionV1(
        transaction_id=transaction.transaction_id,
        workspace=transaction.workspace,
        state=state,
        deadline_ms=transaction.deadline_ms,
        prepared_at_ms=transaction.prepared_at_ms,
        updated_at_ms=clock.now_ms(),
        workspace_write_count=(
            transaction.workspace_write_count if write_count is None else write_count
        ),
        records=transaction.records,
    )
    save_transaction(updated)
    return updated


def _write_progress(
    transaction: GateTransactionV1,
    sequence: int,
    write_count: int,
    clock: ClockPort,
) -> GateTransactionV1:
    records = tuple(
        GatePathRecordV1(
            path=record.path,
            operation=record.operation,
            sequence=record.sequence,
            preimage=record.preimage,
            postimage_digest=record.postimage_digest,
            postimage=record.postimage,
            durable_state=(
                "REPLACED" if record.sequence == sequence else record.durable_state
            ),
            backup_ref=record.backup_ref,
        )
        for record in transaction.records
    )
    updated = GateTransactionV1(
        transaction_id=transaction.transaction_id,
        workspace=transaction.workspace,
        state=transaction.state,
        deadline_ms=transaction.deadline_ms,
        prepared_at_ms=transaction.prepared_at_ms,
        updated_at_ms=clock.now_ms(),
        workspace_write_count=write_count,
        records=records,
    )
    save_transaction(updated)
    return updated


def _replace_workspace_file(workspace: Path, record: GatePathRecordV1) -> None:
    target = _confined_target(workspace, record.path)
    tmp = target.with_name(target.name + ".vesper-tmp")
    with tmp.open("wb") as handle:
        handle.write(record.postimage)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(tmp, target)
    _fsync_parent_directory(target)


def _verify_replaced_bytes(workspace: Path, record: GatePathRecordV1) -> None:
    target = _confined_target(workspace, record.path)
    digest = hashlib.sha256(target.read_bytes()).hexdigest()
    if digest != record.postimage_digest:
        raise ValueError(
            f"writeback mismatch for {record.path}: observed bytes do not "
            "match the recorded postimage"
        )


def _verify_all_postimages(transaction: GateTransactionV1) -> None:
    for record in transaction.records:
        _verify_replaced_bytes(transaction.workspace, record)


def _confined_target(workspace: Path, path: str) -> Path:
    workspace_resolved = Path(workspace).resolve()
    relative = Path(path)
    if relative.is_absolute() or any(part == ".." for part in relative.parts):
        raise ValueError(f"write path escapes the workspace: {path!r}")
    target = (workspace_resolved / relative).resolve()
    if not target.is_relative_to(workspace_resolved):
        raise ValueError(f"write path escapes the workspace: {path!r}")
    if target == workspace_resolved:
        raise ValueError(f"write target is the workspace root: {path!r}")
    if not target.parent.is_dir():
        raise ValueError(f"write target parent directory missing: {target.parent}")
    return target

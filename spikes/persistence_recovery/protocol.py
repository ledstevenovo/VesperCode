"""T03.1 legacy step 3.A: durable persistence transaction protocol.

Defines and durably records the sorted one-to-three-path
PREPARED/WRITING/terminal transaction protocol without applying recovery.
This module owns entry validation, durable immutable transaction/path
record creation, and closed state invariants only: it never replaces
workspace files, evaluates deadlines, classifies recovery, or inspects
real object identities (legacy steps 3.B/3.C/3.D and successor scope).

Durable records are stored in one fixed per-user temp root (the spike
artifact-store analog; the production ACL-restricted local-app-data store
is Task 26.D scope).  Every durable write is atomic: temp file in the
record root, flush, fsync, then :func:`os.replace`, so an interruption at
any injected fault point leaves one complete, classifiable record.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Protocol, cast

TransactionStateV1 = Literal[
    "PREPARED", "WRITING", "COMMITTED", "ROLLED_BACK", "UNRESOLVED"
]
PathWriteStateV1 = Literal["NOT_STARTED", "REPLACED", "VERIFIED", "ROLLED_BACK"]
PreimageKindV1 = Literal["ABSENT", "PRESENT"]
WriteOperationV1 = Literal["CREATE", "REPLACE"]
TransactionRejectionCodeV1 = Literal[
    "TOO_MANY_CREATES",
    "INVALID_CARDINALITY",
    "UNSORTED_ENTRIES",
    "INVALID_PREIMAGE",
    "INVALID_STATE",
]

FaultPointKindV1 = Literal["PREPARED", "WRITING", "REPLACE", "PROGRESS", "TERMINAL"]
FaultPointPositionV1 = Literal["BEFORE", "AFTER"]

_TRANSACTION_ROOT_NAME = "vespercode-gate-persistence"
_HEX_CHARS = frozenset("0123456789abcdef")
_SCHEMA_VERSION = 1


class ClockPort(Protocol):
    """Injected deterministic clock: the sole current-time source."""

    def now_ms(self) -> int: ...


class FaultPort(Protocol):
    """Injected deterministic interruption port for the PREPARED record write.

    A port raises :class:`PersistenceFaultInjectedError` when the named
    point is armed and returns otherwise.
    """

    def raise_at(self, point: PersistenceFaultPointV1) -> None: ...


class PersistenceFaultInjectedError(Exception):
    """Deterministic crash-like interruption at an armed fault point."""


@dataclass(frozen=True)
class PersistenceFaultPointV1:
    """One deterministic interruption point in the persistence protocol.

    ``kind`` is the durable event being guarded (PREPARED/WRITING/REPLACE/
    PROGRESS/TERMINAL), ``position`` is BEFORE or AFTER that event, and
    ``sequence`` is the 1-based sorted path sequence for REPLACE/PROGRESS
    (0 for the protocol-level events).
    """

    kind: FaultPointKindV1
    position: FaultPointPositionV1
    sequence: int = 0

    def __post_init__(self) -> None:
        if self.sequence < 0:
            raise ValueError("fault point sequence must be non-negative")
        if self.kind in ("REPLACE", "PROGRESS") and self.sequence == 0:
            raise ValueError(f"fault point kind {self.kind!r} requires a path sequence")
        if self.kind not in ("REPLACE", "PROGRESS") and self.sequence != 0:
            raise ValueError(
                f"fault point kind {self.kind!r} cannot carry a path sequence"
            )


@dataclass(frozen=True)
class FixedClock:
    """Deterministic clock port that always reports one fixed epoch millisecond."""

    fixed_now_ms: int

    def now_ms(self) -> int:
        return self.fixed_now_ms


class NoFaultPort:
    """Default fault-injection port that never interrupts."""

    def raise_at(self, point: PersistenceFaultPointV1) -> None:
        return None


@dataclass(frozen=True)
class GatePreimageV1:
    """Typed preimage evidence: an ABSENT sentinel or a PRESENT digest+identity.

    ABSENT is a typed sentinel (never an empty-file digest); PRESENT
    carries the raw-bytes digest plus the Win32 object identity pair so
    that byte-plus-identity classification (legacy step 3.D) can fail
    closed on replaced or unprovable objects.
    """

    kind: PreimageKindV1
    raw_bytes_digest: str = ""
    volume_serial: int = 0
    file_id_128: bytes = b""


@dataclass(frozen=True)
class GateWriteEntryV1:
    """One immutable sorted write entry with its complete postimage bytes."""

    path: str
    operation: WriteOperationV1
    preimage: GatePreimageV1
    postimage: bytes
    backup_ref: str = ""


GateWriteEntrySequenceV1 = tuple[GateWriteEntryV1, ...]


@dataclass(frozen=True)
class GatePathRecordV1:
    """The immutable durable per-path record of one transaction.

    ``sequence`` is the 1-based sorted position; ``postimage_digest`` is
    the SHA-256 of the embedded ``postimage`` bytes; ``durable_state`` is
    the last durably persisted progress fact and is never an authority
    over current file bytes (SPEC 4.6 item 8).
    """

    path: str
    operation: WriteOperationV1
    sequence: int
    preimage: GatePreimageV1
    postimage_digest: str
    postimage: bytes
    durable_state: PathWriteStateV1
    backup_ref: str


GatePathRecordSequenceV1 = tuple[GatePathRecordV1, ...]


@dataclass(frozen=True)
class GateTransactionV1:
    """Immutable durable transaction facts for one workspace."""

    transaction_id: str
    workspace: Path
    state: TransactionStateV1
    deadline_ms: int
    prepared_at_ms: int
    updated_at_ms: int
    workspace_write_count: int
    records: GatePathRecordSequenceV1


@dataclass(frozen=True)
class GateTransactionRejectionV1:
    """Closed rejection: these facts can never become a PREPARED transaction."""

    error_code: TransactionRejectionCodeV1
    workspace_write_count: Literal[0]


def transaction_root() -> Path:
    """The fixed per-user durable-record root (spike artifact-store analog)."""
    return Path(tempfile.gettempdir()) / _TRANSACTION_ROOT_NAME


def transaction_record_path(transaction_id: str) -> Path:
    """The exact durable record file for one transaction id."""
    return transaction_root() / f"{transaction_id}.json"


def compute_transaction_id(
    workspace: Path, entries: GateWriteEntrySequenceV1, deadline_ms: int
) -> str:
    """Deterministic content-addressed transaction id.

    Identical workspace, entries, and deadline always yield the identical
    id; any change to workspace identity or entry bytes yields a new id.
    """
    payload = _canonical_json_bytes(
        {
            # normcase keeps Windows spellings of one directory (C:\\Work vs
            # c:\\work) content-addressing to the same transaction identity.
            "workspace": os.path.normcase(str(Path(workspace).resolve())),
            "deadline_ms": deadline_ms,
            "entries": [_entry_to_json(entry) for entry in entries],
        }
    )
    return "txn-" + hashlib.sha256(payload).hexdigest()[:16]


def prepare_transaction(
    workspace: Path,
    entries: GateWriteEntrySequenceV1,
    deadline_ms: int,
    clock: ClockPort,
    faults: FaultPort,
) -> GateTransactionV1 | GateTransactionRejectionV1:
    """Validate one-to-three sorted write entries and durably create the
    immutable PREPARED transaction/path records.

    Every rejection fires before any durable write and before any
    workspace mutation, in the closed order: cardinality, create count,
    sorted order, preimage binding, active-transaction state.  The
    PREPARED record write is the first durable event and is guarded by
    the injected PREPARED_BEFORE/PREPARED_AFTER fault points.
    """
    if not 1 <= len(entries) <= 3:
        return _reject("INVALID_CARDINALITY")
    if sum(1 for entry in entries if entry.operation == "CREATE") > 1:
        return _reject("TOO_MANY_CREATES")
    for left, right in zip(entries, entries[1:]):
        if not left.path < right.path:
            return _reject("UNSORTED_ENTRIES")
    for entry in entries:
        if not _entry_path_valid(entry) or not _entry_preimage_valid(entry):
            return _reject("INVALID_PREIMAGE")
    resolved_workspace = Path(workspace).resolve()
    if _active_transaction_exists(resolved_workspace):
        return _reject("INVALID_STATE")
    now_ms = clock.now_ms()
    records = tuple(
        GatePathRecordV1(
            path=entry.path,
            operation=entry.operation,
            sequence=sequence,
            preimage=entry.preimage,
            postimage_digest=_sha256_hex(entry.postimage),
            postimage=entry.postimage,
            durable_state="NOT_STARTED",
            backup_ref=entry.backup_ref,
        )
        for sequence, entry in enumerate(entries, start=1)
    )
    transaction = GateTransactionV1(
        transaction_id=compute_transaction_id(resolved_workspace, entries, deadline_ms),
        workspace=resolved_workspace,
        state="PREPARED",
        deadline_ms=deadline_ms,
        prepared_at_ms=now_ms,
        updated_at_ms=now_ms,
        workspace_write_count=0,
        records=records,
    )
    faults.raise_at(PersistenceFaultPointV1(kind="PREPARED", position="BEFORE"))
    save_transaction(transaction)
    faults.raise_at(PersistenceFaultPointV1(kind="PREPARED", position="AFTER"))
    return transaction


def load_transaction(transaction_id: str) -> GateTransactionV1:
    """Read the immutable durable transaction record for *transaction_id*.

    Raises ``ValueError`` deterministically when the record is missing or
    unreadable, so every reader fails closed on incomplete durable state.
    """
    path = transaction_record_path(transaction_id)
    if not path.is_file():
        raise ValueError(f"no durable transaction record for {transaction_id}")
    try:
        raw = json.loads(path.read_bytes().decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError, OSError) as exc:
        raise ValueError(
            f"unreadable durable transaction record for {transaction_id}"
        ) from exc
    transaction = _transaction_from_json(raw)
    if transaction.transaction_id != transaction_id:
        raise ValueError(
            "durable transaction record embeds a transaction id that does "
            f"not match its filename: {transaction.transaction_id!r}"
        )
    return transaction


def _reject(error_code: TransactionRejectionCodeV1) -> GateTransactionRejectionV1:
    return GateTransactionRejectionV1(
        error_code=error_code,
        workspace_write_count=0,
    )


def _entry_path_valid(entry: GateWriteEntryV1) -> bool:
    """True when the entry names a usable workspace-relative target path.

    Empty, ``.``, ``..``, absolute, drive-relative, and ``..``-segment
    paths cannot identify a target inside the workspace, so such an
    entry has an invalid write binding and is rejected with
    INVALID_PREIMAGE before persistence (a partially specified
    transaction cannot become PREPARED).
    """
    path = entry.path
    if not path or path in (".", ".."):
        return False
    relative = Path(path)
    if (
        relative.is_absolute()
        or relative.drive
        or any(part == ".." for part in relative.parts)
    ):
        return False
    return True


def _entry_preimage_valid(entry: GateWriteEntryV1) -> bool:
    preimage = entry.preimage
    if entry.operation == "CREATE":
        return (
            preimage.kind == "ABSENT"
            and preimage.raw_bytes_digest == ""
            and preimage.volume_serial == 0
            and len(preimage.file_id_128) == 0
            and entry.backup_ref == ""
        )
    if preimage.kind != "PRESENT":
        return False
    if not _is_digest(preimage.raw_bytes_digest):
        return False
    if preimage.volume_serial == 0 or len(preimage.file_id_128) == 0:
        return False
    if not entry.backup_ref:
        return False
    return True


def _active_transaction_exists(workspace: Path) -> bool:
    """True when this workspace already owns a non-terminal transaction.

    An unreadable record cannot prove an active transaction and is
    skipped; only complete records participate in the state check.
    """
    root = transaction_root()
    if not root.is_dir():
        return False
    resolved = os.path.normcase(str(workspace))
    for path in sorted(root.glob("*.json")):
        try:
            transaction = _transaction_from_json(
                json.loads(path.read_bytes().decode("utf-8"))
            )
        except (ValueError, json.JSONDecodeError, UnicodeDecodeError, OSError):
            continue
        if os.path.normcase(str(transaction.workspace)) == resolved and (
            transaction.state in ("PREPARED", "WRITING", "UNRESOLVED")
        ):
            return True
    return False


def save_transaction(transaction: GateTransactionV1) -> None:
    """Atomically persist one complete transaction record.

    The write is temp-file + flush + fsync + :func:`os.replace` + parent
    directory sync (where available), so any interruption at an injected
    fault point leaves either the previous complete record or the new
    complete record, never a partial one.
    """
    root = transaction_root()
    root.mkdir(parents=True, exist_ok=True)
    payload = _canonical_json_bytes(_transaction_to_json(transaction))
    tmp = root / f".{transaction.transaction_id}.tmp"
    with tmp.open("wb") as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(tmp, transaction_record_path(transaction.transaction_id))
    _fsync_parent_directory(transaction_record_path(transaction.transaction_id))


def _fsync_parent_directory(path: Path) -> None:
    """Persist a completed rename by syncing directory metadata where the
    platform can open a directory handle (POSIX); a no-op on Windows."""
    if os.name != "posix":
        return
    descriptor = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _canonical_json_bytes(obj: object) -> bytes:
    """Serialize *obj* to deterministic UTF-8 JSON with stable key order."""
    return json.dumps(
        obj,
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
        separators=(",", ": "),
    ).encode("utf-8")


def _sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _is_digest(value: str) -> bool:
    return len(value) == 64 and all(char in _HEX_CHARS for char in value)


def _b64encode(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def _b64decode(value: str) -> bytes:
    try:
        return base64.b64decode(value, validate=True)
    except (ValueError, TypeError) as exc:
        raise ValueError("invalid base64 field in durable transaction record") from exc


def _preimage_to_json(preimage: GatePreimageV1) -> dict[str, object]:
    return {
        "kind": preimage.kind,
        "raw_bytes_digest": preimage.raw_bytes_digest,
        "volume_serial": preimage.volume_serial,
        "file_id_128_b64": _b64encode(preimage.file_id_128),
    }


def _entry_to_json(entry: GateWriteEntryV1) -> dict[str, object]:
    return {
        "path": entry.path,
        "operation": entry.operation,
        "preimage": _preimage_to_json(entry.preimage),
        "postimage_b64": _b64encode(entry.postimage),
        "backup_ref": entry.backup_ref,
    }


def _record_to_json(record: GatePathRecordV1) -> dict[str, object]:
    return {
        "path": record.path,
        "operation": record.operation,
        "sequence": record.sequence,
        "preimage": _preimage_to_json(record.preimage),
        "postimage_digest": record.postimage_digest,
        "postimage_b64": _b64encode(record.postimage),
        "durable_state": record.durable_state,
        "backup_ref": record.backup_ref,
    }


def _transaction_to_json(transaction: GateTransactionV1) -> dict[str, object]:
    return {
        "schema_version": _SCHEMA_VERSION,
        "transaction_id": transaction.transaction_id,
        "workspace": str(transaction.workspace),
        "state": transaction.state,
        "deadline_ms": transaction.deadline_ms,
        "prepared_at_ms": transaction.prepared_at_ms,
        "updated_at_ms": transaction.updated_at_ms,
        "workspace_write_count": transaction.workspace_write_count,
        "records": [_record_to_json(record) for record in transaction.records],
    }


def _transaction_from_json(data: dict[str, object]) -> GateTransactionV1:
    if _require_int(data, "schema_version") != _SCHEMA_VERSION:
        raise ValueError("unsupported transaction record schema version")
    state = _require_str(data, "state")
    if state not in ("PREPARED", "WRITING", "COMMITTED", "ROLLED_BACK", "UNRESOLVED"):
        raise ValueError(f"invalid transaction state {state!r}")
    return GateTransactionV1(
        transaction_id=_require_str(data, "transaction_id"),
        workspace=Path(_require_str(data, "workspace")),
        state=cast(TransactionStateV1, state),
        deadline_ms=_require_int(data, "deadline_ms"),
        prepared_at_ms=_require_int(data, "prepared_at_ms"),
        updated_at_ms=_require_int(data, "updated_at_ms"),
        workspace_write_count=_require_int(data, "workspace_write_count"),
        records=tuple(
            _record_from_json(record) for record in _require_list(data, "records")
        ),
    )


def _record_from_json(data: dict[str, object]) -> GatePathRecordV1:
    operation = _require_str(data, "operation")
    if operation not in ("CREATE", "REPLACE"):
        raise ValueError(f"invalid write operation {operation!r}")
    durable_state = _require_str(data, "durable_state")
    if durable_state not in ("NOT_STARTED", "REPLACED", "VERIFIED", "ROLLED_BACK"):
        raise ValueError(f"invalid path write state {durable_state!r}")
    postimage_digest = _require_str(data, "postimage_digest")
    postimage = _b64decode(_require_str(data, "postimage_b64"))
    if _sha256_hex(postimage) != postimage_digest:
        raise ValueError(
            f"durable path record for {_require_str(data, 'path')!r} embeds "
            "postimage bytes that do not match its recorded digest"
        )
    return GatePathRecordV1(
        path=_require_str(data, "path"),
        operation=cast(WriteOperationV1, operation),
        sequence=_require_int(data, "sequence"),
        preimage=_preimage_from_json(_require_dict(data, "preimage")),
        postimage_digest=postimage_digest,
        postimage=postimage,
        durable_state=cast(PathWriteStateV1, durable_state),
        backup_ref=_require_str(data, "backup_ref"),
    )


def _preimage_from_json(data: dict[str, object]) -> GatePreimageV1:
    kind = _require_str(data, "kind")
    if kind not in ("ABSENT", "PRESENT"):
        raise ValueError(f"invalid preimage kind {kind!r}")
    preimage = GatePreimageV1(
        kind=cast(PreimageKindV1, kind),
        raw_bytes_digest=_require_str(data, "raw_bytes_digest"),
        volume_serial=_require_int(data, "volume_serial"),
        file_id_128=_b64decode(_require_str(data, "file_id_128_b64")),
    )
    if not _preimage_consistent(preimage):
        raise ValueError("durable path record embeds an inconsistent preimage")
    return preimage


def _preimage_consistent(preimage: GatePreimageV1) -> bool:
    """Kind-consistency: ABSENT carries no evidence, PRESENT carries a valid
    digest and identity pair."""
    if preimage.kind == "ABSENT":
        return (
            preimage.raw_bytes_digest == ""
            and preimage.volume_serial == 0
            and len(preimage.file_id_128) == 0
        )
    return (
        _is_digest(preimage.raw_bytes_digest)
        and preimage.volume_serial != 0
        and len(preimage.file_id_128) > 0
    )


def _require_str(data: dict[str, object], key: str) -> str:
    value = data.get(key)
    if not isinstance(value, str):
        raise ValueError(f"transaction record missing string field {key!r}")
    return value


def _require_int(data: dict[str, object], key: str) -> int:
    value = data.get(key)
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError(f"transaction record missing integer field {key!r}")
    return value


def _require_list(data: dict[str, object], key: str) -> list[dict[str, object]]:
    value = data.get(key)
    if not isinstance(value, list):
        raise ValueError(f"transaction record missing list field {key!r}")
    result: list[dict[str, object]] = []
    for item in value:
        if not isinstance(item, dict):
            raise ValueError(f"transaction record list field {key!r} must be objects")
        result.append(item)
    return result


def _require_dict(data: dict[str, object], key: str) -> dict[str, object]:
    value = data.get(key)
    if not isinstance(value, dict):
        raise ValueError(f"transaction record missing object field {key!r}")
    return value

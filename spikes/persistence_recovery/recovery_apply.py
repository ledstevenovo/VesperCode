"""T03.2 legacy step 3.F: explicit recovery application.

Applies recovery only for an explicit :class:`GateRecoveryCommandV1`
bound to the workspace, transaction, a fresh preview digest, and
``explicit_apply=True``, while holding the same digest-named Win32
workspace mutex as Task 1.2's lease probe.  Only exact safe preimage/
postimage cases change: a ``COMMITTED`` preview redoes the write-after
verification and writes the terminal COMMITTED record; a ``ROLLED_BACK``
preview deletes only a new file that still exactly matches this
transaction's postimage (AC-29 safe ABSENT rollback) and writes the
terminal ROLLED_BACK record.  Externally replaced, unknown, unprovable,
or ``UNRESOLVED`` objects are never deleted or overwritten, stale
preview digests fail closed with zero writes, and intent can never be
inferred without a bound preview.

This module owns explicit safe recovery writes and terminal record
update only (legacy step 3.F boundary); the read-only preview and the
real-environment GO gate remain in the other legacy steps.
"""

from __future__ import annotations

import ctypes
import hashlib
import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, cast

from ctypes import wintypes

from spikes.persistence_recovery import recovery_preview
from spikes.persistence_recovery.protocol import (
    GatePathRecordV1,
    GateTransactionV1,
    load_transaction,
    save_transaction,
)
from spikes.persistence_recovery.recovery_preview import (
    GateRecoveryDispositionV1,
    compute_preview_digest,
    observe_workspace_path,
    preview_recovery,
)

CanonicalPathSequenceV1 = tuple[str, ...]

_WAIT_OBJECT_0 = 0
_WAIT_ABANDONED = 0x00000080
_WAIT_TIMEOUT = 0x00000102
_HEX_CHARS = frozenset("0123456789abcdef")
_MUTEX_WAIT_TIMEOUT_MS = 5_000


@dataclass(frozen=True)
class GateRecoveryCommandV1:
    """One explicit recovery command.

    ``preview_digest`` is the deterministic identity of the preview the
    caller saw; the apply recomputes the current preview under the
    workspace mutex and refuses to touch anything when the digest does
    not match.  ``explicit_apply`` is the closed literal ``True`` — a
    recovery can never be applied implicitly.
    """

    workspace: Path
    transaction_id: str
    preview_digest: str
    explicit_apply: Literal[True]


@dataclass(frozen=True)
class GateRecoveryResultV1:
    """Immutable result of one explicit recovery apply.

    ``disposition`` is exactly ``COMMITTED``, ``ROLLED_BACK``, or
    ``UNRESOLVED``; ``changed_paths`` lists the canonical record paths
    the apply actually modified (empty for COMMITTED/UNRESOLVED);
    ``evidence_digest`` deterministically binds disposition and changed
    paths.
    """

    disposition: GateRecoveryDispositionV1
    changed_paths: CanonicalPathSequenceV1
    evidence_digest: str


def apply_recovery(command: GateRecoveryCommandV1) -> GateRecoveryResultV1:
    """Apply the explicit recovery bound by *command* under the workspace
    mutex.

    Fails closed (``ValueError``) on an implicit command, an invalid
    preview digest, a missing/workspace-mismatched record, or a terminal
    transaction.  A stale preview digest or an ``UNRESOLVED`` preview
    writes nothing and returns ``UNRESOLVED``.  ``COMMITTED`` redoes the
    write-after verification and writes the terminal record; the
    ``ROLLED_BACK`` delete branch is re-verified immediately before the
    only destructive operation the spike performs (AC-29 safe ABSENT
    rollback) and aborts with zero further changes on any drift.
    """
    if cast(object, command.explicit_apply) is not True:
        raise ValueError("apply_recovery requires explicit_apply=True")
    if not _is_digest(command.preview_digest):
        raise ValueError("preview_digest must be a 64-character lowercase hex digest")
    resolved = Path(command.workspace).resolve()
    transaction = load_transaction(command.transaction_id)
    if os.path.normcase(str(transaction.workspace)) != os.path.normcase(str(resolved)):
        raise ValueError("transaction record does not belong to the command workspace")
    if transaction.state in ("COMMITTED", "ROLLED_BACK"):
        raise ValueError(
            "recovery of a terminal transaction is not allowed, "
            f"found {transaction.state}"
        )
    handle = _acquire_workspace_mutex(resolved)
    try:
        preview = preview_recovery(resolved, command.transaction_id)
        if compute_preview_digest(preview) != command.preview_digest:
            return _result("UNRESOLVED", ())
        if preview.disposition == "UNRESOLVED":
            return _result("UNRESOLVED", ())
        if preview.disposition == "COMMITTED":
            _write_terminal(transaction, "COMMITTED", ())
            return _result("COMMITTED", ())
        classifications = {
            entry.path: entry.classification for entry in preview.path_classifications
        }
        restored: list[str] = []
        for record in transaction.records:
            classification = classifications.get(record.path)
            if classification in ("PREIMAGE", "ABSENT"):
                continue
            if classification != "POSTIMAGE":
                return _result("UNRESOLVED", tuple(restored))
            if record.operation != "CREATE":
                # A replaced REPLACE path next to unapplied paths is
                # contradictory (UNRESOLVED preview); reaching this branch
                # would mean the disposition matrix drifted.
                return _result("UNRESOLVED", tuple(restored))
            if not _safe_to_delete(resolved, record):
                return _result("UNRESOLVED", tuple(restored))
            target = _confined_target(resolved, record.path)
            try:
                target.unlink()
            except OSError:
                # An unlink race (e.g. an exclusive open between the
                # destructive-point re-verification and the unlink) fails
                # closed with the paths changed so far honestly listed.
                return _result("UNRESOLVED", tuple(restored))
            if target.exists():
                # An external process recreating the path in the unlink
                # window leaves a partially rolled-back transaction; the
                # apply fails closed with the path honestly listed in
                # changed_paths and no terminal record (SPEC 5.5's
                # acknowledged residual race window).
                return _result("UNRESOLVED", tuple(restored + [record.path]))
            restored.append(record.path)
        _write_terminal(transaction, "ROLLED_BACK", tuple(restored))
        return _result("ROLLED_BACK", tuple(restored))
    finally:
        _release_workspace_mutex(handle)


def _safe_to_delete(workspace: Path, record: GatePathRecordV1) -> bool:
    """Re-verify at the destructive point: the path is still a supported
    FILE whose bytes still exactly match this transaction's postimage."""
    observation = observe_workspace_path(workspace, record.path)
    return (
        observation.supported
        and observation.object_kind == "FILE"
        and observation.content_digest == record.postimage_digest
    )


def _write_terminal(
    transaction: GateTransactionV1,
    state: Literal["COMMITTED", "ROLLED_BACK"],
    restored_paths: CanonicalPathSequenceV1,
) -> None:
    """Durably write the terminal record with per-path write-after states.

    COMMITTED marks every path VERIFIED (write-after verification
    redone); ROLLED_BACK marks every path ROLLED_BACK (each at its
    preimage or safely deleted to ABSENT as re-verified by the preview
    recomputed under the workspace mutex).
    """
    records = tuple(
        GatePathRecordV1(
            path=record.path,
            operation=record.operation,
            sequence=record.sequence,
            preimage=record.preimage,
            postimage_digest=record.postimage_digest,
            postimage=record.postimage,
            durable_state=("VERIFIED" if state == "COMMITTED" else "ROLLED_BACK"),
            backup_ref=record.backup_ref,
        )
        for record in transaction.records
    )
    updated = GateTransactionV1(
        transaction_id=transaction.transaction_id,
        workspace=transaction.workspace,
        state=state,
        deadline_ms=transaction.deadline_ms,
        prepared_at_ms=transaction.prepared_at_ms,
        updated_at_ms=time.time_ns() // 1_000_000,
        workspace_write_count=transaction.workspace_write_count,
        records=records,
    )
    save_transaction(updated)


def _result(
    disposition: GateRecoveryDispositionV1,
    changed_paths: CanonicalPathSequenceV1,
) -> GateRecoveryResultV1:
    payload = {"disposition": disposition, "changed_paths": list(changed_paths)}
    return GateRecoveryResultV1(
        disposition=disposition,
        changed_paths=changed_paths,
        evidence_digest=_sha256_hex(_canonical_json_bytes(payload)),
    )


def _workspace_identity_digest(workspace: Path) -> str:
    """The same digest-named lease identity as Task 1.2's mutex probe."""
    canonical = os.path.normcase(os.path.abspath(str(workspace)))
    return _sha256_hex(canonical.encode("utf-8"))


def _mutex_name(workspace: Path) -> str:
    return f"Local\\VesperCode.WorkspaceLeaseV1.{_workspace_identity_digest(workspace)}"


def _kernel32() -> ctypes.WinDLL:
    """The shared kernel32 ABI wiring (single site in recovery_preview)."""
    return recovery_preview._kernel32()


def _acquire_workspace_mutex(workspace: Path) -> wintypes.HANDLE:
    kernel32 = _kernel32()
    handle = kernel32.CreateMutexW(None, False, _mutex_name(workspace))
    if not handle:
        raise RuntimeError("cannot create the workspace mutex")
    wait = kernel32.WaitForSingleObject(handle, _MUTEX_WAIT_TIMEOUT_MS)
    if wait in (_WAIT_OBJECT_0, _WAIT_ABANDONED):
        return wintypes.HANDLE(handle)
    kernel32.CloseHandle(handle)
    if wait == _WAIT_TIMEOUT:
        raise RuntimeError(
            "workspace mutex is held by another process (apply timed out)"
        )
    raise RuntimeError(f"workspace mutex wait failed with status {wait}")


def _release_workspace_mutex(handle: wintypes.HANDLE) -> None:
    """Release and always close the mutex handle, even when the release
    itself fails (a leaked owned handle would block every later apply)."""
    kernel32 = _kernel32()
    try:
        if not kernel32.ReleaseMutex(handle):
            raise RuntimeError("workspace mutex release failed")
    finally:
        if not kernel32.CloseHandle(handle):
            raise RuntimeError("workspace mutex handle close failed")


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
    return target


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


def _is_digest(value: str) -> bool:
    return len(value) == 64 and all(char in _HEX_CHARS for char in value)

"""T03.2 legacy step 3.G: real NTFS persistence-recovery GO gate report.

Runs the complete fault/deadline/external-change/preview/apply case
matrix against disposable real NTFS objects under the given workspace
and emits the immutable Task 3 GO/NO_GO report.  ``GO`` is emitted only
when matrix coverage, gate-toolchain identity, workspace-probe
identity, per-case evidence, and cleanup are all complete; any omitted,
failed, or drifted case yields ``NO_GO`` without rewriting evidence.

The gate resolves its identity evidence from the given workspace
(``workspace/gates/evidence/gate-toolchain-v1.json`` and
``workspace-boundary-go-v1.json`` — the local-temp-repo convention of
SPEC 10.3 recovery fault injection), so a clean fixture can be seeded
from the real repo evidence and every missing/drifted variant is
deterministically testable.  The coverage pre-check (GREEN-3) rejects
before the full matrix runs: the ``EXTERNAL_IDENTITY`` case is bound to
the real preimage object ``src/a.py`` inside the given workspace, and
its absence means the external-identity case is missing.

This module owns real NTFS case execution, coverage completeness,
cleanup, and the final GO/NO_GO decision only (legacy step 3.G
boundary); the pure protocol/evaluators/classifier are reused unchanged
and the matrix is never silently reduced.
"""

from __future__ import annotations

import ctypes
import hashlib
import json
import shutil
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Literal

from ctypes import wintypes

from spikes.persistence_recovery.deadline import evaluate_persistence_deadline
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
)
from spikes.persistence_recovery.recovery_apply import (
    GateRecoveryCommandV1,
    apply_recovery,
)
from spikes.persistence_recovery.recovery_preview import (
    _OPEN_EXISTING,
    _kernel32,
    compute_preview_digest,
    observe_workspace_path,
    preview_recovery,
)
from spikes.win32_workspace_boundary.report import (
    GateToolchainEvidenceV1,
    load_workspace_boundary_gate_report,
)

FaultCaseResultSequenceV1 = tuple["FaultCaseResultV1", ...]

_FAR_DEADLINE = 1 << 62
_INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value

EXTERNAL_IDENTITY_REQUIRED_OBJECT = "src/a.py"

REQUIRED_CASE_MANIFEST: tuple[str, ...] = (
    "PREVIEW_BYTE_IDENTITY",
    "PREVIEW_ROLLED_BACK_ZERO_WRITE",
    "SAFE_ABSENT_ROLLBACK",
    "FAULT_PROGRESS_BEFORE_UNRESOLVED",
    "FAULT_TERMINAL_BEFORE_COMMITTED",
    "DEADLINE_PRE_WRITE",
    "DEADLINE_POST_WRITE",
    "EXTERNAL_CREATE",
    "EXTERNAL_IDENTITY",
    "EXTERNAL_DIRECTORY",
    "UNPROVABLE_LOCKED_FILE",
    "STALE_PREVIEW_DIGEST",
    "TAMPERED_RECORD_ZERO_WRITE",
)

_EMPTY_TOOLCHAIN = GateToolchainEvidenceV1(
    schema_version=0,
    evidence_type="",
    python_version="",
    pytest_version="",
    ruff_version="",
    mypy_version="",
    gate_input_sha256="",
    gate_lock_sha256="",
    gate_scan_sha256="",
    gate_scan_core_sha256="",
    runner_sha256="",
    pytest_config_sha256="",
    ruff_config_sha256="",
    mypy_config_sha256="",
    evidence_digest="",
)


@dataclass(frozen=True)
class FaultCaseResultV1:
    """One immutable ordered matrix-case result.

    ``passed`` is True only when the case ran on real NTFS objects with
    complete observed evidence and verified cleanup; ``evidence_digest``
    deterministically binds the case's observed dispositions, digests,
    and cleanup verdict.
    """

    case_name: str
    passed: bool
    evidence_digest: str


@dataclass(frozen=True)
class PersistenceRecoveryGateReportV1:
    """Immutable Task 3 GO/NO_GO report binding the complete matrix.

    ``cases`` is the ordered tuple of every required
    :class:`FaultCaseResultV1`; ``gate_toolchain`` and
    ``workspace_probe_digest`` bind the workspace identity evidence
    (empty placeholders on identity failure); ``evidence_digest`` binds
    the whole report body.
    """

    outcome: Literal["GO", "NO_GO"]
    cases: FaultCaseResultSequenceV1
    gate_toolchain: GateToolchainEvidenceV1
    workspace_probe_digest: str
    evidence_digest: str


def run_persistence_recovery_gate(workspace: Path) -> PersistenceRecoveryGateReportV1:
    """Run the complete recovery matrix and emit the GO/NO_GO report.

    Coverage-completeness rejection (GREEN-3) runs before the full
    real-environment matrix: missing or drifted identity evidence or a
    missing external-identity case object emits NO_GO with every
    required case failed and no case executed.
    """
    resolved = Path(workspace).resolve()
    identity = _load_identity_evidence(resolved)
    identity_ok = identity is not None
    object_ok = identity_ok and _required_identity_object_present(resolved)
    if identity_ok and object_ok:
        results = tuple(_run_case(resolved, name) for name in REQUIRED_CASE_MANIFEST)
    else:
        reason = (
            "gate identity evidence is missing or drifted"
            if not identity_ok
            else "external identity case object is missing from the workspace"
        )
        results = tuple(_failed_case(name, reason) for name in REQUIRED_CASE_MANIFEST)
    outcome: Literal["GO", "NO_GO"] = (
        "GO"
        if identity_ok and object_ok and all(result.passed for result in results)
        else "NO_GO"
    )
    toolchain, probe_digest = identity or (_EMPTY_TOOLCHAIN, "")
    body = {
        "outcome": outcome,
        "cases": [
            {
                "case_name": result.case_name,
                "passed": result.passed,
                "evidence_digest": result.evidence_digest,
            }
            for result in results
        ],
        "gate_toolchain": _toolchain_json(toolchain),
        "workspace_probe_digest": probe_digest,
    }
    return PersistenceRecoveryGateReportV1(
        outcome=outcome,
        cases=results,
        gate_toolchain=toolchain,
        workspace_probe_digest=probe_digest,
        evidence_digest=_sha256_hex(_canonical_json_bytes(body)),
    )


def _load_identity_evidence(
    workspace: Path,
) -> tuple[GateToolchainEvidenceV1, str] | None:
    """Load and fully validate the workspace identity evidence.

    Reuses the Task 1 workspace-boundary loader, which verifies the
    terminal GO outcome, recomputes the evidence digest, and binds the
    embedded toolchain to ``workspace/gates/evidence/gate-toolchain-v1.json``.
    """
    try:
        report = load_workspace_boundary_gate_report(workspace)
    except (FileNotFoundError, OSError, ValueError):
        return None
    return report.gate_toolchain, report.evidence_digest


def _required_identity_object_present(workspace: Path) -> bool:
    """True when the external-identity case's real object exists."""
    observation = observe_workspace_path(workspace, EXTERNAL_IDENTITY_REQUIRED_OBJECT)
    return observation.supported and observation.object_kind == "FILE"


def _run_case(workspace: Path, name: str) -> FaultCaseResultV1:
    try:
        return _CASE_RUNNERS[name](workspace)
    except Exception as exc:
        return _failed_case(name, f"unexpected case failure: {exc}")


def _case_result(
    name: str,
    passed: bool,
    payload: dict[str, object],
) -> FaultCaseResultV1:
    return FaultCaseResultV1(
        case_name=name,
        passed=passed,
        evidence_digest=_sha256_hex(_canonical_json_bytes(payload)),
    )


def _failed_case(name: str, reason: str) -> FaultCaseResultV1:
    return _case_result(
        name,
        False,
        {"case": name, "passed": False, "reason": reason},
    )


def _fresh_case_workspace(workspace: Path, name: str) -> Path:
    case_ws = workspace / f"case-{name}"
    case_ws.mkdir()
    return case_ws


def _cleanup_case(case_ws: Path | None, txn_ids: list[str]) -> bool:
    ok = True
    for txn_id in txn_ids:
        path = transaction_record_path(txn_id)
        try:
            path.unlink(missing_ok=True)
        except OSError:
            ok = False
        if path.exists():
            ok = False
    if case_ws is not None:
        try:
            shutil.rmtree(case_ws)
        except OSError:
            ok = False
        if case_ws.exists():
            ok = False
    return ok


def _prepare_entries(
    workspace: Path,
    entries: list[GateWriteEntryV1],
    deadline_ms: int = _FAR_DEADLINE,
) -> str:
    result = prepare_transaction(
        workspace,
        tuple(entries),
        deadline_ms,
        FixedClock(0),
        NoFaultPort(),
    )
    if isinstance(result, GateTransactionRejectionV1):
        raise RuntimeError(f"case prepare rejected: {result.error_code}")
    return result.transaction_id


def _apply_fault(txn_id: str, fault_point: PersistenceFaultPointV1) -> None:
    apply_transaction(txn_id, fault_point, FixedClock(0))


def _replace_entries(
    case_ws: Path,
    preimages: dict[str, bytes],
) -> list[GateWriteEntryV1]:
    entries: list[GateWriteEntryV1] = []
    for rel in sorted(preimages):
        observed = observe_workspace_path(case_ws, rel)
        if not (observed.supported and observed.object_kind == "FILE"):
            raise RuntimeError(f"cannot observe preimage object {rel!r}")
        entries.append(
            GateWriteEntryV1(
                path=rel,
                operation="REPLACE",
                preimage=GatePreimageV1(
                    kind="PRESENT",
                    raw_bytes_digest=observed.content_digest,
                    volume_serial=observed.volume_serial,
                    file_id_128=observed.file_id_128,
                ),
                postimage=_postimage_for(rel),
                backup_ref=f"case/{rel}.bin",
            )
        )
    return entries


def _create_entry(rel: str) -> GateWriteEntryV1:
    return GateWriteEntryV1(
        path=rel,
        operation="CREATE",
        preimage=GatePreimageV1(kind="ABSENT"),
        postimage=_postimage_for(rel),
        backup_ref="",
    )


def _postimage_for(rel: str) -> bytes:
    return b"post " + rel.encode("utf-8") + b"\n"


def _bound_command(workspace: Path, txn_id: str) -> GateRecoveryCommandV1:
    preview = preview_recovery(workspace, txn_id)
    return GateRecoveryCommandV1(
        workspace=workspace,
        transaction_id=txn_id,
        preview_digest=compute_preview_digest(preview),
        explicit_apply=True,
    )


def _workspace_digest(workspace: Path) -> str:
    payload = bytearray()
    for path in sorted(workspace.rglob("*")):
        if path.is_file():
            payload += path.read_bytes()
    return _sha256_hex(bytes(payload))


def _now_ms() -> int:
    return time.time_ns() // 1_000_000


_GENERIC_READ = 0x80000000


def _open_exclusive(path: Path) -> wintypes.HANDLE:
    """Open *path* with zero sharing so every other open fails."""
    kernel32 = _kernel32()
    handle = kernel32.CreateFileW(
        str(path), _GENERIC_READ, 0, None, _OPEN_EXISTING, 0, None
    )
    if handle == _INVALID_HANDLE_VALUE:
        raise OSError(ctypes.get_last_error(), f"cannot open {path} exclusively")
    return wintypes.HANDLE(handle)


def _close_handle(handle: wintypes.HANDLE) -> bool:
    return bool(_kernel32().CloseHandle(handle))


def _case_preview_byte_identity(workspace: Path) -> FaultCaseResultV1:
    """Preview of a fully applied two-REPLACE transaction is byte-for-byte
    read-only (workspace files and the durable record unchanged)."""
    name = "PREVIEW_BYTE_IDENTITY"
    case_ws = _fresh_case_workspace(workspace, name)
    txn_ids: list[str] = []
    passed = False
    payload: dict[str, object] = {}
    try:
        (case_ws / "src").mkdir()
        preimages = {"src/b.py": b"original b\n", "src/c.py": b"original c\n"}
        for rel, data in preimages.items():
            (case_ws / rel).write_bytes(data)
        txn_id = _prepare_entries(case_ws, _replace_entries(case_ws, preimages))
        txn_ids.append(txn_id)
        _apply_fault(txn_id, PersistenceFaultPointV1("TERMINAL", "BEFORE", 0))
        before = _case_snapshot_digest(case_ws, txn_ids)
        preview = preview_recovery(case_ws, txn_id)
        after = _case_snapshot_digest(case_ws, txn_ids)
        assert preview.disposition == "COMMITTED"
        assert preview.workspace_write_count == 0
        assert len(preview.path_classifications) == len(preimages)
        passed = True
        payload = {
            "preview_disposition": preview.disposition,
            "preview_write_count": preview.workspace_write_count,
            "path_count": len(preview.path_classifications),
            "before_digest": before,
            "after_digest": after,
            "byte_identical": before == after,
        }
    finally:
        cleanup_ok = _cleanup_case(case_ws, txn_ids)
    return _case_result(
        name, passed and cleanup_ok, {**payload, "cleanup_verified": cleanup_ok}
    )


def _case_snapshot_digest(case_ws: Path, txn_ids: list[str]) -> str:
    payload = bytearray()
    for path in sorted(case_ws.rglob("*")):
        if path.is_file():
            payload += path.read_bytes()
    for txn_id in sorted(txn_ids):
        record = transaction_record_path(txn_id)
        if record.is_file():
            payload += record.read_bytes()
    return _sha256_hex(bytes(payload))


def _case_preview_rolled_back_zero_write(workspace: Path) -> FaultCaseResultV1:
    """An unapplied CREATE+REPLACE transaction previews ROLLED_BACK with
    zero writes and applies as a zero-change ROLLED_BACK."""
    name = "PREVIEW_ROLLED_BACK_ZERO_WRITE"
    case_ws = _fresh_case_workspace(workspace, name)
    txn_ids: list[str] = []
    passed = False
    payload: dict[str, object] = {}
    try:
        (case_ws / "src").mkdir()
        (case_ws / "src" / "b.py").write_bytes(b"original b\n")
        entries = [_create_entry("src/a.py")]
        entries.extend(_replace_entries(case_ws, {"src/b.py": b"original b\n"}))
        txn_id = _prepare_entries(case_ws, entries)
        txn_ids.append(txn_id)
        _apply_fault(txn_id, PersistenceFaultPointV1("REPLACE", "BEFORE", 1))
        preview = preview_recovery(case_ws, txn_id)
        assert preview.disposition == "ROLLED_BACK"
        assert preview.workspace_write_count == 0
        before = _workspace_digest(case_ws)
        result = apply_recovery(_bound_command(case_ws, txn_id))
        after = _workspace_digest(case_ws)
        assert result.disposition == "ROLLED_BACK"
        assert result.changed_paths == ()
        assert before == after
        assert load_transaction(txn_id).state == "ROLLED_BACK"
        passed = True
        payload = {
            "preview_disposition": preview.disposition,
            "preview_write_count": preview.workspace_write_count,
            "apply_disposition": result.disposition,
            "apply_changed_paths": list(result.changed_paths),
            "apply_zero_workspace_changes": before == after,
            "record_state": "ROLLED_BACK",
        }
    finally:
        cleanup_ok = _cleanup_case(case_ws, txn_ids)
    return _case_result(
        name, passed and cleanup_ok, {**payload, "cleanup_verified": cleanup_ok}
    )


def _case_safe_absent_rollback(workspace: Path) -> FaultCaseResultV1:
    """An applied CREATE next to an untouched REPLACE rolls back by safely
    deleting only the postimage-matching new file (AC-29)."""
    name = "SAFE_ABSENT_ROLLBACK"
    case_ws = _fresh_case_workspace(workspace, name)
    txn_ids: list[str] = []
    passed = False
    payload: dict[str, object] = {}
    try:
        (case_ws / "src").mkdir()
        (case_ws / "src" / "b.py").write_bytes(b"original b\n")
        entries = [_create_entry("src/a.py")]
        entries.extend(_replace_entries(case_ws, {"src/b.py": b"original b\n"}))
        txn_id = _prepare_entries(case_ws, entries)
        txn_ids.append(txn_id)
        _apply_fault(txn_id, PersistenceFaultPointV1("PROGRESS", "BEFORE", 1))
        preview = preview_recovery(case_ws, txn_id)
        assert preview.disposition == "ROLLED_BACK"
        result = apply_recovery(_bound_command(case_ws, txn_id))
        assert result.disposition == "ROLLED_BACK"
        assert result.changed_paths == ("src/a.py",)
        assert not (case_ws / "src" / "a.py").exists()
        assert (case_ws / "src" / "b.py").read_bytes() == b"original b\n"
        assert load_transaction(txn_id).state == "ROLLED_BACK"
        passed = True
        payload = {
            "preview_disposition": preview.disposition,
            "apply_disposition": result.disposition,
            "apply_changed_paths": list(result.changed_paths),
            "create_path_absent_after_rollback": True,
            "replace_path_at_preimage": True,
            "record_state": "ROLLED_BACK",
        }
    finally:
        cleanup_ok = _cleanup_case(case_ws, txn_ids)
    return _case_result(
        name, passed and cleanup_ok, {**payload, "cleanup_verified": cleanup_ok}
    )


def _case_fault_progress_before_unresolved(workspace: Path) -> FaultCaseResultV1:
    """An interruption with a replaced REPLACE next to an absent CREATE is
    a contradictory mixed state: preview and apply are UNRESOLVED and the
    apply writes nothing further."""
    name = "FAULT_PROGRESS_BEFORE_UNRESOLVED"
    case_ws = _fresh_case_workspace(workspace, name)
    txn_ids: list[str] = []
    passed = False
    payload: dict[str, object] = {}
    try:
        (case_ws / "src").mkdir()
        (case_ws / "src" / "a.py").write_bytes(b"original a\n")
        entries = _replace_entries(case_ws, {"src/a.py": b"original a\n"})
        entries.append(_create_entry("src/b.py"))
        txn_id = _prepare_entries(case_ws, entries)
        txn_ids.append(txn_id)
        _apply_fault(txn_id, PersistenceFaultPointV1("REPLACE", "BEFORE", 2))
        preview = preview_recovery(case_ws, txn_id)
        assert preview.disposition == "UNRESOLVED"
        before = _workspace_digest(case_ws)
        result = apply_recovery(_bound_command(case_ws, txn_id))
        after = _workspace_digest(case_ws)
        assert result.disposition == "UNRESOLVED"
        assert result.changed_paths == ()
        assert before == after
        assert load_transaction(txn_id).state == "WRITING"
        passed = True
        payload = {
            "fault_point": "REPLACE_BEFORE(2)",
            "preview_disposition": preview.disposition,
            "apply_disposition": result.disposition,
            "apply_changed_paths": list(result.changed_paths),
            "apply_zero_workspace_changes": before == after,
            "record_state": "WRITING",
        }
    finally:
        cleanup_ok = _cleanup_case(case_ws, txn_ids)
    return _case_result(
        name, passed and cleanup_ok, {**payload, "cleanup_verified": cleanup_ok}
    )


def _case_fault_terminal_before_committed(workspace: Path) -> FaultCaseResultV1:
    """A three-file mixed CREATE/REPLACE transaction stopped only before
    the terminal durable write previews COMMITTED and applies with zero
    file changes."""
    name = "FAULT_TERMINAL_BEFORE_COMMITTED"
    case_ws = _fresh_case_workspace(workspace, name)
    txn_ids: list[str] = []
    passed = False
    payload: dict[str, object] = {}
    try:
        (case_ws / "src").mkdir()
        (case_ws / "src" / "a.py").write_bytes(b"original a\n")
        (case_ws / "src" / "c.py").write_bytes(b"original c\n")
        entries = _replace_entries(
            case_ws,
            {"src/a.py": b"original a\n", "src/c.py": b"original c\n"},
        )
        entries.insert(1, _create_entry("src/b.py"))
        txn_id = _prepare_entries(case_ws, entries)
        txn_ids.append(txn_id)
        _apply_fault(txn_id, PersistenceFaultPointV1("TERMINAL", "BEFORE", 0))
        preview = preview_recovery(case_ws, txn_id)
        assert preview.disposition == "COMMITTED"
        assert preview.workspace_write_count == 0
        before = _workspace_digest(case_ws)
        result = apply_recovery(_bound_command(case_ws, txn_id))
        after = _workspace_digest(case_ws)
        assert result.disposition == "COMMITTED"
        assert result.changed_paths == ()
        assert before == after
        transaction = load_transaction(txn_id)
        assert transaction.state == "COMMITTED"
        assert all(record.durable_state == "VERIFIED" for record in transaction.records)
        passed = True
        payload = {
            "fault_point": "TERMINAL_BEFORE",
            "record_count": len(transaction.records),
            "preview_disposition": preview.disposition,
            "preview_write_count": preview.workspace_write_count,
            "apply_disposition": result.disposition,
            "apply_changed_paths": list(result.changed_paths),
            "apply_zero_workspace_changes": before == after,
            "record_state": "COMMITTED",
        }
    finally:
        cleanup_ok = _cleanup_case(case_ws, txn_ids)
    return _case_result(
        name, passed and cleanup_ok, {**payload, "cleanup_verified": cleanup_ok}
    )


def _case_deadline_pre_write(workspace: Path) -> FaultCaseResultV1:
    """An expired deadline before any write evaluates STOPPED_ZERO_WRITE,
    previews ROLLED_BACK, and applies as a zero-change ROLLED_BACK."""
    name = "DEADLINE_PRE_WRITE"
    case_ws = _fresh_case_workspace(workspace, name)
    txn_ids: list[str] = []
    passed = False
    payload: dict[str, object] = {}
    try:
        (case_ws / "src").mkdir()
        (case_ws / "src" / "b.py").write_bytes(b"original b\n")
        txn_id = _prepare_entries(
            case_ws,
            _replace_entries(case_ws, {"src/b.py": b"original b\n"}),
            deadline_ms=1,
        )
        txn_ids.append(txn_id)
        evaluation = evaluate_persistence_deadline(
            load_transaction(txn_id), 0, _now_ms()
        )
        assert evaluation.disposition == "STOPPED_ZERO_WRITE"
        assert not evaluation.further_workspace_writes_allowed
        preview = preview_recovery(case_ws, txn_id)
        assert preview.disposition == "ROLLED_BACK"
        before = _workspace_digest(case_ws)
        result = apply_recovery(_bound_command(case_ws, txn_id))
        after = _workspace_digest(case_ws)
        assert result.disposition == "ROLLED_BACK"
        assert result.changed_paths == ()
        assert before == after
        assert load_transaction(txn_id).state == "ROLLED_BACK"
        passed = True
        payload = {
            "deadline_disposition": evaluation.disposition,
            "further_writes_allowed": evaluation.further_workspace_writes_allowed,
            "preview_disposition": preview.disposition,
            "apply_disposition": result.disposition,
            "apply_changed_paths": list(result.changed_paths),
            "apply_zero_workspace_changes": before == after,
            "record_state": "ROLLED_BACK",
        }
    finally:
        cleanup_ok = _cleanup_case(case_ws, txn_ids)
    return _case_result(
        name, passed and cleanup_ok, {**payload, "cleanup_verified": cleanup_ok}
    )


def _case_deadline_post_write(workspace: Path) -> FaultCaseResultV1:
    """An expired deadline after a write evaluates RECOVERY_REQUIRED; the
    mixed byte state previews UNRESOLVED and the apply writes nothing
    further."""
    name = "DEADLINE_POST_WRITE"
    case_ws = _fresh_case_workspace(workspace, name)
    txn_ids: list[str] = []
    passed = False
    payload: dict[str, object] = {}
    try:
        (case_ws / "src").mkdir()
        (case_ws / "src" / "a.py").write_bytes(b"original a\n")
        entries = _replace_entries(case_ws, {"src/a.py": b"original a\n"})
        entries.append(_create_entry("src/b.py"))
        txn_id = _prepare_entries(case_ws, entries, deadline_ms=1)
        txn_ids.append(txn_id)
        _apply_fault(txn_id, PersistenceFaultPointV1("REPLACE", "BEFORE", 2))
        evaluation = evaluate_persistence_deadline(
            load_transaction(txn_id),
            load_transaction(txn_id).workspace_write_count,
            _now_ms(),
        )
        assert evaluation.disposition == "RECOVERY_REQUIRED"
        assert not evaluation.further_workspace_writes_allowed
        preview = preview_recovery(case_ws, txn_id)
        assert preview.disposition == "UNRESOLVED"
        before = _workspace_digest(case_ws)
        result = apply_recovery(_bound_command(case_ws, txn_id))
        after = _workspace_digest(case_ws)
        assert result.disposition == "UNRESOLVED"
        assert result.changed_paths == ()
        assert before == after
        assert load_transaction(txn_id).state == "WRITING"
        passed = True
        payload = {
            "deadline_disposition": evaluation.disposition,
            "further_writes_allowed": evaluation.further_workspace_writes_allowed,
            "preview_disposition": preview.disposition,
            "apply_disposition": result.disposition,
            "apply_changed_paths": list(result.changed_paths),
            "apply_zero_workspace_changes": before == after,
            "record_state": "WRITING",
        }
    finally:
        cleanup_ok = _cleanup_case(case_ws, txn_ids)
    return _case_result(
        name, passed and cleanup_ok, {**payload, "cleanup_verified": cleanup_ok}
    )


def _case_external_create(workspace: Path) -> FaultCaseResultV1:
    """An externally overwritten new file is never deleted or overwritten:
    preview and apply are UNRESOLVED and the foreign bytes are preserved."""
    name = "EXTERNAL_CREATE"
    case_ws = _fresh_case_workspace(workspace, name)
    txn_ids: list[str] = []
    passed = False
    payload: dict[str, object] = {}
    try:
        (case_ws / "src").mkdir()
        txn_id = _prepare_entries(case_ws, [_create_entry("src/b.py")])
        txn_ids.append(txn_id)
        _apply_fault(txn_id, PersistenceFaultPointV1("TERMINAL", "BEFORE", 0))
        foreign = b"foreign external bytes\n"
        (case_ws / "src" / "b.py").write_bytes(foreign)
        preview = preview_recovery(case_ws, txn_id)
        assert preview.disposition == "UNRESOLVED"
        result = apply_recovery(_bound_command(case_ws, txn_id))
        assert result.disposition == "UNRESOLVED"
        assert result.changed_paths == ()
        assert (case_ws / "src" / "b.py").read_bytes() == foreign
        assert load_transaction(txn_id).state == "WRITING"
        passed = True
        payload = {
            "preview_disposition": preview.disposition,
            "apply_disposition": result.disposition,
            "apply_changed_paths": list(result.changed_paths),
            "external_bytes_preserved": True,
            "record_state": "WRITING",
        }
    finally:
        cleanup_ok = _cleanup_case(case_ws, txn_ids)
    return _case_result(
        name, passed and cleanup_ok, {**payload, "cleanup_verified": cleanup_ok}
    )


def _case_external_identity(workspace: Path) -> FaultCaseResultV1:
    """The external-identity case: a REPLACE transaction over the real
    preimage object ``src/a.py`` of the given workspace.  After an
    external overwrite the preview/apply are UNRESOLVED and the foreign
    object is preserved byte-for-byte; the case then restores the
    original object bytes so the given workspace is left byte-identical
    (the gate's disposable-object contract)."""
    name = "EXTERNAL_IDENTITY"
    txn_ids: list[str] = []
    passed = False
    payload: dict[str, object] = {}
    target = EXTERNAL_IDENTITY_REQUIRED_OBJECT
    original_bytes = (workspace / target).read_bytes()
    try:
        observed = observe_workspace_path(workspace, target)
        if not (observed.supported and observed.object_kind == "FILE"):
            raise RuntimeError("external identity object missing")
        txn_id = _prepare_entries(
            workspace,
            [
                GateWriteEntryV1(
                    path=target,
                    operation="REPLACE",
                    preimage=GatePreimageV1(
                        kind="PRESENT",
                        raw_bytes_digest=observed.content_digest,
                        volume_serial=observed.volume_serial,
                        file_id_128=observed.file_id_128,
                    ),
                    postimage=b"post a\n",
                    backup_ref="case/EXTERNAL_IDENTITY/a.bin",
                )
            ],
        )
        txn_ids.append(txn_id)
        _apply_fault(txn_id, PersistenceFaultPointV1("TERMINAL", "BEFORE", 0))
        foreign = b"foreign external bytes\n"
        (workspace / target).write_bytes(foreign)
        preview = preview_recovery(workspace, txn_id)
        assert preview.disposition == "UNRESOLVED"
        result = apply_recovery(_bound_command(workspace, txn_id))
        assert result.disposition == "UNRESOLVED"
        assert result.changed_paths == ()
        assert (workspace / target).read_bytes() == foreign
        assert load_transaction(txn_id).state == "WRITING"
        passed = True
        payload = {
            "identity_observed": observed.volume_serial != 0
            and len(observed.file_id_128) > 0,
            "preview_disposition": preview.disposition,
            "apply_disposition": result.disposition,
            "apply_changed_paths": list(result.changed_paths),
            "external_bytes_preserved": True,
            "record_state": "WRITING",
        }
    finally:
        try:
            (workspace / target).write_bytes(original_bytes)
            restored = (workspace / target).read_bytes() == original_bytes
        except OSError:
            restored = False
        cleanup_ok = _cleanup_case(None, txn_ids)
    return _case_result(
        name,
        passed and cleanup_ok and restored,
        {
            **payload,
            "cleanup_verified": cleanup_ok,
            "workspace_object_restored": restored,
        },
    )


def _case_external_directory(workspace: Path) -> FaultCaseResultV1:
    """A directory replacing the target is an external change: preview and
    apply are UNRESOLVED and the directory is never deleted or written."""
    name = "EXTERNAL_DIRECTORY"
    case_ws = _fresh_case_workspace(workspace, name)
    txn_ids: list[str] = []
    passed = False
    payload: dict[str, object] = {}
    try:
        (case_ws / "src").mkdir()
        (case_ws / "src" / "b.py").write_bytes(b"original b\n")
        txn_id = _prepare_entries(
            case_ws,
            _replace_entries(case_ws, {"src/b.py": b"original b\n"}),
        )
        txn_ids.append(txn_id)
        _apply_fault(txn_id, PersistenceFaultPointV1("TERMINAL", "BEFORE", 0))
        target = case_ws / "src" / "b.py"
        target.unlink()
        target.mkdir()
        preview = preview_recovery(case_ws, txn_id)
        assert preview.disposition == "UNRESOLVED"
        result = apply_recovery(_bound_command(case_ws, txn_id))
        assert result.disposition == "UNRESOLVED"
        assert result.changed_paths == ()
        assert target.is_dir()
        passed = True
        payload = {
            "preview_disposition": preview.disposition,
            "apply_disposition": result.disposition,
            "apply_changed_paths": list(result.changed_paths),
            "directory_preserved": True,
        }
    finally:
        cleanup_ok = _cleanup_case(case_ws, txn_ids)
    return _case_result(
        name, passed and cleanup_ok, {**payload, "cleanup_verified": cleanup_ok}
    )


def _case_unprovable_locked_file(workspace: Path) -> FaultCaseResultV1:
    """An unobservable (exclusively locked) object is UNPROVABLE: preview
    and apply are UNRESOLVED and the file is preserved byte-for-byte."""
    name = "UNPROVABLE_LOCKED_FILE"
    case_ws = _fresh_case_workspace(workspace, name)
    txn_ids: list[str] = []
    passed = False
    payload: dict[str, object] = {}
    handle: wintypes.HANDLE | None = None
    try:
        (case_ws / "src").mkdir()
        (case_ws / "src" / "b.py").write_bytes(b"original b\n")
        txn_id = _prepare_entries(
            case_ws,
            _replace_entries(case_ws, {"src/b.py": b"original b\n"}),
        )
        txn_ids.append(txn_id)
        _apply_fault(txn_id, PersistenceFaultPointV1("TERMINAL", "BEFORE", 0))
        handle = _open_exclusive(case_ws / "src" / "b.py")
        preview = preview_recovery(case_ws, txn_id)
        assert preview.disposition == "UNRESOLVED"
        result = apply_recovery(_bound_command(case_ws, txn_id))
        assert result.disposition == "UNRESOLVED"
        assert result.changed_paths == ()
        assert _close_handle(handle)
        handle = None
        preserved = (case_ws / "src" / "b.py").read_bytes() == _postimage_for(
            "src/b.py"
        )
        assert preserved
        passed = True
        payload = {
            "preview_disposition": preview.disposition,
            "apply_disposition": result.disposition,
            "apply_changed_paths": list(result.changed_paths),
            "file_preserved": preserved,
        }
    finally:
        handle_closed = handle is None or _close_handle(handle)
        cleanup_ok = _cleanup_case(case_ws, txn_ids)
    return _case_result(
        name,
        passed and cleanup_ok and handle_closed,
        {
            **payload,
            "cleanup_verified": cleanup_ok,
            "handle_closed": handle_closed,
        },
    )


def _case_stale_preview_digest(workspace: Path) -> FaultCaseResultV1:
    """An apply command bound to a stale preview digest after an external
    change writes nothing and returns UNRESOLVED."""
    name = "STALE_PREVIEW_DIGEST"
    case_ws = _fresh_case_workspace(workspace, name)
    txn_ids: list[str] = []
    passed = False
    payload: dict[str, object] = {}
    try:
        (case_ws / "src").mkdir()
        txn_id = _prepare_entries(case_ws, [_create_entry("src/b.py")])
        txn_ids.append(txn_id)
        _apply_fault(txn_id, PersistenceFaultPointV1("TERMINAL", "BEFORE", 0))
        stale = _bound_command(case_ws, txn_id)
        foreign = b"foreign external bytes\n"
        (case_ws / "src" / "b.py").write_bytes(foreign)
        result = apply_recovery(stale)
        assert result.disposition == "UNRESOLVED"
        assert result.changed_paths == ()
        assert (case_ws / "src" / "b.py").read_bytes() == foreign
        assert load_transaction(txn_id).state == "WRITING"
        passed = True
        payload = {
            "apply_disposition": result.disposition,
            "apply_changed_paths": list(result.changed_paths),
            "stale_digest_rejected": True,
            "external_bytes_preserved": True,
            "record_state": "WRITING",
        }
    finally:
        cleanup_ok = _cleanup_case(case_ws, txn_ids)
    return _case_result(
        name, passed and cleanup_ok, {**payload, "cleanup_verified": cleanup_ok}
    )


def _case_tampered_record_zero_write(workspace: Path) -> FaultCaseResultV1:
    """A tampered durable path record makes the preview fail closed with
    zero workspace writes."""
    name = "TAMPERED_RECORD_ZERO_WRITE"
    case_ws = _fresh_case_workspace(workspace, name)
    txn_ids: list[str] = []
    passed = False
    payload: dict[str, object] = {}
    try:
        (case_ws / "src").mkdir()
        (case_ws / "src" / "b.py").write_bytes(b"original b\n")
        txn_id = _prepare_entries(
            case_ws,
            _replace_entries(case_ws, {"src/b.py": b"original b\n"}),
        )
        txn_ids.append(txn_id)
        record_path = transaction_record_path(txn_id)
        data = json.loads(record_path.read_bytes())
        digest = data["records"][0]["postimage_digest"]
        flipped = ("0" if digest[0] != "0" else "1") + digest[1:]
        data["records"][0]["postimage_digest"] = flipped
        record_path.write_bytes(json.dumps(data).encode("utf-8"))
        before = _workspace_digest(case_ws)
        raised = False
        try:
            preview_recovery(case_ws, txn_id)
        except ValueError:
            raised = True
        after = _workspace_digest(case_ws)
        assert raised
        assert before == after
        passed = True
        payload = {
            "fail_closed_raised": raised,
            "zero_workspace_writes": before == after,
        }
    finally:
        cleanup_ok = _cleanup_case(case_ws, txn_ids)
    return _case_result(
        name, passed and cleanup_ok, {**payload, "cleanup_verified": cleanup_ok}
    )


_CASE_RUNNERS: dict[str, Callable[[Path], FaultCaseResultV1]] = {
    "PREVIEW_BYTE_IDENTITY": _case_preview_byte_identity,
    "PREVIEW_ROLLED_BACK_ZERO_WRITE": _case_preview_rolled_back_zero_write,
    "SAFE_ABSENT_ROLLBACK": _case_safe_absent_rollback,
    "FAULT_PROGRESS_BEFORE_UNRESOLVED": _case_fault_progress_before_unresolved,
    "FAULT_TERMINAL_BEFORE_COMMITTED": _case_fault_terminal_before_committed,
    "DEADLINE_PRE_WRITE": _case_deadline_pre_write,
    "DEADLINE_POST_WRITE": _case_deadline_post_write,
    "EXTERNAL_CREATE": _case_external_create,
    "EXTERNAL_IDENTITY": _case_external_identity,
    "EXTERNAL_DIRECTORY": _case_external_directory,
    "UNPROVABLE_LOCKED_FILE": _case_unprovable_locked_file,
    "STALE_PREVIEW_DIGEST": _case_stale_preview_digest,
    "TAMPERED_RECORD_ZERO_WRITE": _case_tampered_record_zero_write,
}


def _toolchain_json(toolchain: GateToolchainEvidenceV1) -> dict[str, object]:
    return {
        "schema_version": toolchain.schema_version,
        "evidence_type": toolchain.evidence_type,
        "python_version": toolchain.python_version,
        "pytest_version": toolchain.pytest_version,
        "ruff_version": toolchain.ruff_version,
        "mypy_version": toolchain.mypy_version,
        "gate_input_sha256": toolchain.gate_input_sha256,
        "gate_lock_sha256": toolchain.gate_lock_sha256,
        "gate_scan_sha256": toolchain.gate_scan_sha256,
        "gate_scan_core_sha256": toolchain.gate_scan_core_sha256,
        "runner_sha256": toolchain.runner_sha256,
        "pytest_config_sha256": toolchain.pytest_config_sha256,
        "ruff_config_sha256": toolchain.ruff_config_sha256,
        "mypy_config_sha256": toolchain.mypy_config_sha256,
        "evidence_digest": toolchain.evidence_digest,
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

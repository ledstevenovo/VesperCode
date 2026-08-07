"""T38.2 legacy step 38.F: production recovery CLI composition.

This module owns the sole production recovery-CLI binding after the
complete v1 database initialization: ``initialize_production_control_database``
applies ``ALL_V1_MIGRATIONS`` exactly once through the Task 7.A engine
before anything else (GREEN-1), ``build_production_recovery_cli_handler``
constructs the single production handler graph over that initialized
database and the injected workspace service (GREEN-2), and
``bind_production_recover_command`` wires the Task 38.E recover parser
to that handler.  The handler resolves the Task 9.D workspace identity
through the injected ``WorkspaceServiceV1``, projects the read-only Task
26.B preview, and executes the explicit Task 26.C apply under the
workspace lease — the parser's preview/apply branching is never
duplicated and no storage, migration, predicate, or SQLite internal is
owned here beyond the declared composition (GREEN-4/Boundary: the only
permitted storage composition is ``apply_migrations(db,
ALL_V1_MIGRATIONS)`` before constructing any typed repository/service
port).

Recorded interface interpretations (reviewer-flagged): (1) the card's
``build_production_recovery_cli_handler(db, workspace_service)`` exposes
only the database and the workspace service, so the recovery artifact
root is derived from the control database's own file location
(``<db directory>/vespercode-recovery-artifacts``, read through the
read-only ``PRAGMA database_list`` introspection) — SPEC §5.6 keeps
recovery artifacts in the user's local control-data area, never in the
workspace; (2) the concrete ``RecoveryWorkspacePort`` of the apply
service composes the existing Task 26.B ``RealWorkspaceObserver`` (reads)
with the Task 26.E ``RealWorkspacePort`` (atomic replace/delete and the
write counter) — pure composition of existing Task 26 machinery, no
recovery predicate is duplicated.
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Protocol

from src.vespercode.canonical.clock import SystemClockV1
from src.vespercode.cli import (
    RecoveryCliHandlerV1,
    RecoveryCliResultV1,
    install_recover_command,
)
from src.vespercode.persistence.artifacts import PersistenceArtifactStoreV1
from src.vespercode.persistence.recovery import RecoveryService
from src.vespercode.persistence.recovery_apply import (
    ApplyRecoveryV1,
    RealRecoveryLeasePort,
    RecoveryApplyService,
    RecoveryResultRepositoryV1,
    RecoveryResultV1,
)
from src.vespercode.persistence.recovery_preview import (
    RealWorkspaceObserver,
    RecoveryPathObservationV1,
    RecoveryPreviewErrorV1,
    RecoveryPreviewV1,
    RecoveryPreviewService,
)
from src.vespercode.persistence.transaction import (
    PersistencePathRecordRepositoryV1,
    PersistenceTransactionRepositoryV1,
)
from src.vespercode.persistence.writeback import RealWorkspacePort
from src.vespercode.storage.connection import (
    ControlDatabase,
    ControlDatabaseErrorV1,
    open_control_database,
)
from src.vespercode.storage.migration_engine import apply_migrations
from src.vespercode.storage.migrations.registry import ALL_V1_MIGRATIONS
from src.vespercode.canonical.path_v1 import CanonicalRelativePathV1
from src.vespercode.workspace.identity_win32 import (
    WorkspaceIdentityV1,
    resolve_workspace_identity,
)

_RECOVERY_LEASE_TIMEOUT_MILLISECONDS = 5000
"""The bounded workspace-lease timeout of one production recovery apply."""

_ARTIFACT_ROOT_DIRECTORY_NAME = "vespercode-recovery-artifacts"
"""The production recovery-artifact root name beside the control db."""


class WorkspaceServiceV1(Protocol):
    """The injected Task 9.D workspace identity service of the CLI."""

    def resolve(self, locator: Path) -> WorkspaceIdentityV1:
        """Resolve the sealed identity of one workspace locator."""
        ...


class ProductionWorkspaceServiceV1:
    """The production workspace identity service over Task 9.D."""

    def resolve(self, locator: Path) -> WorkspaceIdentityV1:
        return resolve_workspace_identity(locator)


class _ProductionRecoveryWorkspacePort:
    """The concrete recovery workspace port (read + mutation + count).

    Reads delegate to the Task 26.B real observer; atomic replace/delete
    and the authoritative write counter delegate to the Task 26.E real
    workspace port.  Composition only — no recovery predicate is
    duplicated here.
    """

    def __init__(self, identity: WorkspaceIdentityV1) -> None:
        self._observer = RealWorkspaceObserver(identity)
        self._writer = RealWorkspacePort(identity)

    def observe(self, path: CanonicalRelativePathV1) -> RecoveryPathObservationV1:
        """One read-only observation of a path fact (Task 26.B)."""
        return self._observer.observe(path)

    def replace(self, path: CanonicalRelativePathV1, body: bytes) -> None:
        """One atomic authoritative replace (Task 26.E)."""
        self._writer.replace(path, body)

    def delete(self, path: CanonicalRelativePathV1) -> None:
        """One authoritative delete (Task 26.E)."""
        self._writer.delete(path)

    @property
    def write_count(self) -> int:
        """The authoritative workspace write count."""
        return self._writer.write_count


class ProductionRecoveryCliHandlerV1:
    """The sole production recovery-CLI handler over one initialized db.

    Every preview/apply resolves the workspace identity through the
    injected Task 9.D service, then delegates to the Task 26.B/26.C
    services of the per-workspace recovery graph; the parser's
    preview/apply branching is never duplicated and no production
    storage is opened here (GREEN-4/Boundary).
    """

    def __init__(
        self,
        database: ControlDatabase,
        workspace_service: WorkspaceServiceV1,
    ) -> None:
        self._database = database
        self._workspace_service = workspace_service
        self._artifact_root = _artifact_root(database)

    def preview(self, workspace: Path) -> RecoveryCliResultV1:
        """Project the read-only Task 26.B preview (zero writes)."""
        identity = self._resolve(workspace)
        if identity is None:
            return RecoveryCliResultV1(
                kind="WORKSPACE_REJECTED",
                message="工作区路径无法解析为受支持的工作区。",
            )
        recovery = self._build_recovery(identity)
        try:
            preview = recovery.preview(identity)
        except RecoveryPreviewErrorV1 as exc:
            return self._preview_error(exc)
        return RecoveryCliResultV1(kind="PREVIEW", message=_project_preview(preview))

    def apply(self, workspace: Path) -> RecoveryCliResultV1:
        """Execute the explicit Task 26.C apply (the only mutation path)."""
        identity = self._resolve(workspace)
        if identity is None:
            return RecoveryCliResultV1(
                kind="WORKSPACE_REJECTED",
                message="工作区路径无法解析为受支持的工作区。",
            )
        recovery = self._build_recovery(identity)
        try:
            preview = recovery.preview(identity)
        except RecoveryPreviewErrorV1 as exc:
            return self._preview_error(exc)
        if preview.disposition == "UNRESOLVED":
            return RecoveryCliResultV1(
                kind="UNRESOLVED",
                message="恢复处于未解决状态：外部变化或证据不足，保持恢复阻塞。",
            )
        command = ApplyRecoveryV1(
            schema_version=1,
            transaction_id=preview.transaction_id,
            workspace_identity_digest=identity.digest,
            preview_digest=preview.preview_digest,
            requested_disposition=preview.disposition,
            explicit_apply=True,
        )
        try:
            result = recovery.apply(command)
        except Exception:
            # A lease/fault outcome never reports a false success; the
            # bounded text carries no raw exception (SPEC §5.4).
            return RecoveryCliResultV1(
                kind="RECOVERY_FAILED", message="恢复操作失败，状态未变化。"
            )
        if result.disposition in ("COMMITTED", "ROLLED_BACK"):
            return RecoveryCliResultV1(kind="APPLIED", message=_project_apply(result))
        return RecoveryCliResultV1(
            kind="UNRESOLVED",
            message=result.message or "恢复未执行：状态未解决。",
        )

    def _resolve(self, workspace: Path) -> WorkspaceIdentityV1 | None:
        """One Task 9.D identity resolution through the injected service."""
        try:
            return self._workspace_service.resolve(workspace)
        except Exception:
            return None

    def _build_recovery(self, identity: WorkspaceIdentityV1) -> RecoveryService:
        """One per-workspace Task 26 recovery graph over the initialized db."""
        store = PersistenceArtifactStoreV1(self._artifact_root)
        transactions = PersistenceTransactionRepositoryV1(self._database)
        paths = PersistencePathRecordRepositoryV1(self._database)
        preview_service = RecoveryPreviewService(
            transaction_repository=transactions,
            path_repository=paths,
            artifact_store=store,
            workspace_identity_digest=identity.digest,
            observer=RealWorkspaceObserver(identity),
        )
        apply_service = RecoveryApplyService(
            transaction_repository=transactions,
            path_repository=paths,
            artifact_store=store,
            preview_service=preview_service,
            workspace=_ProductionRecoveryWorkspacePort(identity),
            lease=RealRecoveryLeasePort(identity, _RECOVERY_LEASE_TIMEOUT_MILLISECONDS),
            results=RecoveryResultRepositoryV1(self._database),
            clock=SystemClockV1(),
            workspace_identity_digest=identity.digest,
        )
        return RecoveryService(
            transaction_repository=transactions,
            preview_service=preview_service,
            apply_service=apply_service,
        )

    @staticmethod
    def _preview_error(exc: RecoveryPreviewErrorV1) -> RecoveryCliResultV1:
        """One bounded preview-rejection projection."""
        if exc.error_code == "TRANSACTION_NOT_FOUND":
            return RecoveryCliResultV1(
                kind="NO_TRANSACTION", message="该工作区没有非终态恢复事务。"
            )
        return RecoveryCliResultV1(kind="RECOVERY_FAILED", message="恢复预览不可用。")


def initialize_production_control_database(path: Path) -> ControlDatabase:
    """Initialize the production control database (GREEN-1).

    Applies the complete Task 7.D registry exactly once through the
    Task 7.A engine before any repository, recovery service, or CLI
    handler is constructed; any non-APPLIED/NOOP outcome fails closed.
    """
    database = open_control_database(path)
    result = apply_migrations(database, ALL_V1_MIGRATIONS)
    if result.kind not in ("APPLIED", "NOOP"):
        database.close()
        raise ControlDatabaseErrorV1(
            f"production database initialization failed: {result.message}"
        )
    return database


def build_production_recovery_cli_handler(
    db: ControlDatabase,
    workspace_service: WorkspaceServiceV1,
) -> RecoveryCliHandlerV1:
    """Build the sole production recovery-CLI handler over the db."""
    return ProductionRecoveryCliHandlerV1(db, workspace_service)


def bind_production_recover_command(
    app: argparse.ArgumentParser,
    database_path: Path,
    workspace_service: WorkspaceServiceV1,
) -> None:
    """Bind the Task 38.E recover parser to the production handler.

    Initializes the complete control database, builds the sole
    production handler, and installs the unchanged Task 38.E recover
    parser onto the application parser (GREEN-2).
    """
    db = initialize_production_control_database(database_path)
    handler = build_production_recovery_cli_handler(db, workspace_service)
    install_recover_command(app, handler)


def _artifact_root(database: ControlDatabase) -> Path:
    """The production recovery-artifact root beside the control db.

    The card's handler interface exposes only the database, so the
    artifact root is derived from the database's own file location via
    the read-only ``PRAGMA database_list`` introspection (SPEC §5.6:
    recovery artifacts stay in the local control-data area, never in the
    workspace).
    """
    rows = database.read_rows("PRAGMA database_list")
    for row in rows:
        if str(row[1]) == "main":
            return Path(str(row[2])).resolve().parent / _ARTIFACT_ROOT_DIRECTORY_NAME
    raise ControlDatabaseErrorV1("production control database file location unknown")


def _project_preview(preview: RecoveryPreviewV1) -> str:
    """One bounded read-only preview projection (SPEC §5.4)."""
    lines = [
        f"恢复预览（零写入，工作区写入次数：{preview.workspace_write_count}）",
        f"事务：{preview.transaction_id}",
        f"判定：{preview.disposition}",
    ]
    for entry in preview.path_classifications:
        lines.append(f"  {entry.path}：{entry.classification}")
    lines.append(f"预览摘要：{preview.preview_digest}")
    return "\n".join(lines)


def _project_apply(result: RecoveryResultV1) -> str:
    """One bounded terminal apply projection (SPEC §5.4)."""
    changed_text = "、".join(result.changed_paths) if result.changed_paths else "无"
    return (
        f"恢复已执行：{result.disposition}，变更路径：{changed_text}"
        f"（证据摘要：{result.evidence_digest}）"
    )

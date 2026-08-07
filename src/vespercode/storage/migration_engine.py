"""T07.1 legacy step 7.A: domain-independent SQLite migration engine.

``MigrationV1`` is a closed injected descriptor (version, name, checksum,
apply callable); ``apply_migrations`` applies a tuple of such migrations
in strict version order inside one explicit immediate transaction so the
whole batch is atomic and idempotent, rejecting duplicate/gap descriptors
and applied-checksum drift before any domain mutation.  The engine owns
no application-domain DDL and cannot know any domain schema (GREEN-4).
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Callable, Literal, TypeAlias

from pydantic import BaseModel, ConfigDict, StrictStr

from vespercode.canonical.clock import SystemClockV1
from vespercode.canonical.digest import domain_digest
from vespercode.contracts.evidence import DigestV1
from vespercode.storage.connection import (
    ControlDatabase,
    ControlTransactionV1,
)

_SCHEMA_MIGRATIONS_DDL: str = (
    "CREATE TABLE IF NOT EXISTS schema_migrations ("
    " version INTEGER PRIMARY KEY,"
    " name TEXT NOT NULL UNIQUE,"
    " checksum TEXT NOT NULL,"
    " applied_at TEXT NOT NULL"
    ")"
)
"""The only history table this engine bootstraps (PLAN storage registry).

Exact columns: ``(version PRIMARY KEY, name UNIQUE, checksum, applied_at)``
per PLAN.md storage-class row for Migration history.
"""

_SYSTEM_CLOCK = SystemClockV1()

MigrationApplyV1: TypeAlias = Callable[[ControlTransactionV1], None]
"""The injected closed migration runner: executes one migration's DDL."""

MigrationResultKindV1: TypeAlias = Literal[
    "APPLIED",
    "NOOP",
    "DUPLICATE_VERSION",
    "VERSION_GAP",
    "MIGRATION_CHECKSUM_MISMATCH",
    "MIGRATION_FAILED",
]


class MigrationResultV1(BaseModel):
    """One closed migration-batch outcome with a stable reason."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    kind: MigrationResultKindV1
    message: StrictStr


class MigrationChecksumDriftErrorV1(ValueError):
    """Closed internal rejection for applied-checksum drift."""


def _require_positive_version(version: int) -> None:
    if not isinstance(version, int) or isinstance(version, bool) or version < 1:
        raise ValueError("migration version must be a positive integer")


def _require_non_empty_name(name: str) -> None:
    if not isinstance(name, str) or name == "":
        raise ValueError("migration name must be non-empty")


@dataclass(frozen=True)
class MigrationV1:
    """One closed injected migration descriptor (domain-independent).

    The checksum is the exact ``DigestV1`` identity of the descriptor's
    version/name/DDL, so any later change to an already-applied migration
    is detected as drift and fails closed on the next run.
    """

    version: int
    name: str
    checksum: DigestV1
    apply: MigrationApplyV1

    def __post_init__(self) -> None:
        _require_positive_version(self.version)
        _require_non_empty_name(self.name)
        if not callable(self.apply):
            raise ValueError("migration apply must be a callable")


def migration_checksum(version: int, name: str, ddl: str) -> str:
    """Deterministic SPEC 0.1 binding digest of one migration descriptor.

    The same version/name/DDL bytes always produce the same checksum, so a
    domain migration module that changes its DDL text after it was applied
    is detected as applied-checksum drift on the next run.
    """
    _require_positive_version(version)
    _require_non_empty_name(name)
    payload_digest = hashlib.sha256(ddl.encode("utf-8")).hexdigest()
    return domain_digest(
        "MigrationDescriptorV1",
        1,
        {
            "version": version,
            "name": name,
            "ddl_sha256": payload_digest,
        },
    )


def apply_migrations(
    db: ControlDatabase,
    migrations: tuple[MigrationV1, ...],
) -> MigrationResultV1:
    """Apply the injected migrations in strict order, atomically and idempotently.

    Duplicate/gap descriptors fail closed before any transaction;
    applied-checksum drift and any apply exception roll back the whole
    batch together (schema and history); exact replay is a no-op.
    """
    seen: set[int] = set()
    for index, migration in enumerate(migrations):
        if migration.version in seen:
            return MigrationResultV1(
                kind="DUPLICATE_VERSION",
                message="migration versions must be unique",
            )
        seen.add(migration.version)
        if migration.version != index + 1:
            return MigrationResultV1(
                kind="VERSION_GAP",
                message="migration versions must be contiguous from 1",
            )

    applied_count = 0
    try:
        with db.immediate_transaction() as tx:
            # The schema_migrations history bootstrap is part of the engine
            # (PLAN storage registry) and runs inside the same batch
            # transaction, so bootstrap and apply stay atomic together.
            tx.execute(_SCHEMA_MIGRATIONS_DDL)
            for migration in migrations:
                recorded = tx.execute(
                    "SELECT name, checksum FROM schema_migrations WHERE version = ?",
                    (migration.version,),
                ).fetchone()
                if recorded is not None:
                    if str(recorded[1]) != migration.checksum.value:
                        raise MigrationChecksumDriftErrorV1(
                            f"applied checksum drifted for version {migration.version}"
                        )
                    continue
                migration.apply(tx)
                tx.execute(
                    "INSERT INTO schema_migrations"
                    " (version, name, checksum, applied_at)"
                    " VALUES (?, ?, ?, ?)",
                    (
                        migration.version,
                        migration.name,
                        migration.checksum.value,
                        _SYSTEM_CLOCK.now().value,
                    ),
                )
                applied_count += 1
    except MigrationChecksumDriftErrorV1 as exc:
        return MigrationResultV1(
            kind="MIGRATION_CHECKSUM_MISMATCH",
            message=str(exc),
        )
    except Exception as exc:
        # The transaction context manager already rolled back schema and
        # history together; only the closed outcome remains.
        return MigrationResultV1(kind="MIGRATION_FAILED", message=str(exc))
    if applied_count:
        return MigrationResultV1(
            kind="APPLIED",
            message=f"applied {applied_count} migration(s)",
        )
    return MigrationResultV1(
        kind="NOOP",
        message="all migrations already applied with matching checksums",
    )

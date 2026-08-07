"""T07.4 legacy step 7.D: the sole complete v1 migration registry.

This module composes exactly the twelve declared immutable domain
migration constants into ``ALL_V1_MIGRATIONS`` and owns composition only:
it contains no DDL statements, no repositories, no product behavior, no
fixture tables, and no read-only introspection.  ``compose_v1_migrations``
fails closed on any missing, duplicate, gapped, reordered, early/late,
wrong-owner, unexpected, or checksum-drifted composition before the
complete tuple is accepted; the exact table-delta/final-set owner map
exists only in the task's test module and is neither imported nor
duplicated here.
"""

from __future__ import annotations

from vespercode.contracts.evidence import DigestV1
from vespercode.storage.migration_engine import MigrationV1
from vespercode.storage.migrations.v0001_run_wait import RUN_WAIT_V1_MIGRATION
from vespercode.storage.migrations.v0002_idempotency import IDEMPOTENCY_V1_MIGRATION
from vespercode.storage.migrations.v0003_disclosure_grants import (
    DISCLOSURE_GRANTS_V1_MIGRATION,
)
from vespercode.storage.migrations.v0004_disclosure_authorizations import (
    DISCLOSURE_AUTHORIZATIONS_V1_MIGRATION,
)
from vespercode.storage.migrations.v0005_memory import MEMORY_V1_MIGRATION
from vespercode.storage.migrations.v0006_audit import AUDIT_V1_MIGRATION
from vespercode.storage.migrations.v0007_agent_turns import (
    AGENT_TURNS_V1_MIGRATION,
)
from vespercode.storage.migrations.v0008_feedback import FEEDBACK_V1_MIGRATION
from vespercode.storage.migrations.v0009_actions import ACTIONS_V1_MIGRATION
from vespercode.storage.migrations.v0010_writeback_approvals import (
    WRITEBACK_APPROVALS_V1_MIGRATION,
)
from vespercode.storage.migrations.v0011_persistence import (
    PERSISTENCE_V1_MIGRATION,
)
from vespercode.storage.migrations.v0012_recovery import RECOVERY_V1_MIGRATION


class MigrationRegistryError(ValueError):
    """Closed rejection for an invalid v1 migration registry composition."""


_EXPECTED_V1_COMPOSITION: tuple[tuple[int, str, str], ...] = (
    (
        1,
        "run_wait_v1",
        "5216bd9b9d9616439ac3e8a0c06378a6da08c4bf81530689d7fb23462dc5a7af",
    ),
    (
        2,
        "idempotency_v1",
        "5f193a4d1609241604aa6c716513bd84690f01da6c9fb94bbf397f9e6b732247",
    ),
    (
        3,
        "disclosure_grants_v1",
        "4e031a38f2afc181f97382e0e5f43f0387e187613e1359296fa7c126d686325e",
    ),
    (
        4,
        "disclosure_authorizations_v1",
        "b23aec406e60115f91c67a9551c3579cbd72e2b5b9f3b488fc07c63e8b1cf234",
    ),
    (
        5,
        "memory_v1",
        "952eab31451a85bfee0ef467b6aa52575ac6172178711903af240384a7d495cc",
    ),
    (
        6,
        "audit_v1",
        "ce918ce8a007f9fd3e04c6515c6b36ddc7c18e2f37668b81e6682da78ba4e319",
    ),
    (
        7,
        "agent_turns_v1",
        "d89feb1b7ce573b5b110045d373af207691ecb84c5ebd85ae7cacf3aba2d78e1",
    ),
    (
        8,
        "feedback_v1",
        "4514ff337056a15e582fc3520540f425a7952dbd0c759b82ea0ee9827f17fff4",
    ),
    (
        9,
        "actions_v1",
        "404b5855832a219da6112295e29644987c4bf7089256fb97f0bb991f33f14ff8",
    ),
    (
        10,
        "writeback_approvals_v1",
        "6d417e3e5416c586c243dbcddaed5a78261f1aa9126dd8cab4b3443e3ef80a95",
    ),
    (
        11,
        "persistence_v1",
        "eabdd22806190cb19f4e0a6933329ac66662b62ce86f3a30e6a45ab1fabfab75",
    ),
    (
        12,
        "recovery_v1",
        "59c88dc66657289028cc5100f917e9bd50d483e3acf4c5c37f301c961651405d",
    ),
)
"""The declared composition contract: ``(version, name, descriptor checksum)``.

The checksum facts are the exact ``DigestV1`` values of the twelve
immutable domain migration descriptors, so a drifted, swapped, or
tampered descriptor fails closed at composition.
"""


def compose_v1_migrations(
    migrations: tuple[MigrationV1, ...],
) -> tuple[MigrationV1, ...]:
    """Validate and return the complete v1 registry tuple, failing closed.

    Every invalid composition raises ``MigrationRegistryError`` with a
    stable code prefix: ``MIGRATION_SET_INVALID`` (non-descriptor entry),
    ``MIGRATION_SET_DUPLICATE`` (duplicate version or name),
    ``MIGRATION_UNEXPECTED`` (version outside 1..12),
    ``MIGRATION_NAME_MISMATCH`` (wrong-owner name for a declared version),
    ``MIGRATION_CHECKSUM_DRIFT`` (descriptor checksum differs from the
    declared composition), ``MIGRATION_SET_INCOMPLETE`` (missing or gapped
    version), and ``MIGRATION_ORDER_INVALID`` (complete set not in the
    exact version order).
    """
    expected_by_version = {
        version: (name, checksum)
        for version, name, checksum in _EXPECTED_V1_COMPOSITION
    }
    seen_versions: set[int] = set()
    seen_names: set[str] = set()
    for migration in migrations:
        if not isinstance(migration, MigrationV1):
            raise MigrationRegistryError(
                "MIGRATION_SET_INVALID: every entry must be a MigrationV1"
            )
        if migration.version in seen_versions:
            raise MigrationRegistryError(
                "MIGRATION_SET_DUPLICATE: "
                f"duplicate migration version {migration.version}"
            )
        if migration.name in seen_names:
            raise MigrationRegistryError(
                f"MIGRATION_SET_DUPLICATE: duplicate migration name {migration.name!r}"
            )
        declared = expected_by_version.get(migration.version)
        if declared is None:
            raise MigrationRegistryError(
                "MIGRATION_UNEXPECTED: "
                f"version {migration.version} is not a declared v1 migration"
            )
        expected_name, expected_checksum = declared
        if migration.name != expected_name:
            raise MigrationRegistryError(
                "MIGRATION_NAME_MISMATCH: version "
                f"{migration.version} must be named {expected_name!r}, "
                f"not {migration.name!r}"
            )
        if not isinstance(migration.checksum, DigestV1):
            raise MigrationRegistryError(
                "MIGRATION_SET_INVALID: descriptor checksum must be a DigestV1"
            )
        if migration.checksum.value != expected_checksum:
            raise MigrationRegistryError(
                "MIGRATION_CHECKSUM_DRIFT: descriptor checksum drifted "
                f"for version {migration.version}"
            )
        seen_versions.add(migration.version)
        seen_names.add(migration.name)

    missing = {version for version, _, _ in _EXPECTED_V1_COMPOSITION} - seen_versions
    if missing:
        raise MigrationRegistryError(
            "MIGRATION_SET_INCOMPLETE: missing required migration "
            f"version(s) {sorted(missing)}"
        )
    for index, migration in enumerate(migrations):
        if migration.version != index + 1:
            raise MigrationRegistryError(
                "MIGRATION_ORDER_INVALID: migration versions must appear "
                f"in exact order 1..12 (version {migration.version} at "
                f"position {index + 1})"
            )
    return tuple(migrations)


ALL_V1_MIGRATIONS: tuple[MigrationV1, ...] = compose_v1_migrations(
    (
        RUN_WAIT_V1_MIGRATION,
        IDEMPOTENCY_V1_MIGRATION,
        DISCLOSURE_GRANTS_V1_MIGRATION,
        DISCLOSURE_AUTHORIZATIONS_V1_MIGRATION,
        MEMORY_V1_MIGRATION,
        AUDIT_V1_MIGRATION,
        AGENT_TURNS_V1_MIGRATION,
        FEEDBACK_V1_MIGRATION,
        ACTIONS_V1_MIGRATION,
        WRITEBACK_APPROVALS_V1_MIGRATION,
        PERSISTENCE_V1_MIGRATION,
        RECOVERY_V1_MIGRATION,
    )
)
"""The sole complete v1 migration registry: exactly twelve descriptors.

Validated once at import time; any composition drift fails closed before
the tuple is exported.
"""

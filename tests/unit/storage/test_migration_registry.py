"""T07.4 legacy step 7.D: complete v1 migration registry tests.

The two displayed probes (exact RED) pin missing-migration rejection and
exact per-prefix/final SQLite table ownership through read-only
introspection; the fail-closed matrix pins every other invalid-composition
class (duplicate, gapped, reordered, early/late, wrong-owner, unexpected,
checksum-drifted) and the probe's sensitivity to undeclared, omitted,
repeated, or moved tables.  The exact table-delta/final-set owner map
exists only in this module; the production registry neither contains nor
imports it (GREEN-4).

The two displayed probe bodies match the corrected card except two
ruff-forced line collapses (redundant-paren removal and line joins, T14.1
ruff-wrapping precedent) and the documented ``# type: ignore[attr-defined]``
on the fixture ``execute`` call (T24.1 exact-RED mypy-deviation
precedent).
"""

from __future__ import annotations

import re
import sqlite3
from collections.abc import Iterator
from dataclasses import replace
from pathlib import Path

import pytest

# The registry consumes pydantic runtime contracts (MigrationV1, DigestV1);
# the hash-locked gate toolchain installs no runtime dependencies, so this
# module skips cleanly there (formal env runs it fully).
pytest.importorskip("pydantic")

from src.vespercode.contracts.evidence import DigestV1
from src.vespercode.storage.connection import (
    ControlDatabase,
    ControlTransactionV1,
    open_control_database,
)
from src.vespercode.storage.migration_engine import (
    MigrationResultV1,
    MigrationV1,
    apply_migrations,
)
from src.vespercode.storage.migrations.registry import (
    ALL_V1_MIGRATIONS,
    MigrationRegistryError,
    compose_v1_migrations,
)
from src.vespercode.storage.migrations.v0001_run_wait import RUN_WAIT_V1_MIGRATION
from src.vespercode.storage.migrations.v0002_idempotency import IDEMPOTENCY_V1_MIGRATION
from src.vespercode.storage.migrations.v0003_disclosure_grants import (
    DISCLOSURE_GRANTS_V1_MIGRATION,
)
from src.vespercode.storage.migrations.v0004_disclosure_authorizations import (
    DISCLOSURE_AUTHORIZATIONS_V1_MIGRATION,
)
from src.vespercode.storage.migrations.v0005_memory import MEMORY_V1_MIGRATION
from src.vespercode.storage.migrations.v0006_audit import AUDIT_V1_MIGRATION
from src.vespercode.storage.migrations.v0007_agent_turns import (
    AGENT_TURNS_V1_MIGRATION,
)
from src.vespercode.storage.migrations.v0008_feedback import FEEDBACK_V1_MIGRATION
from src.vespercode.storage.migrations.v0009_actions import ACTIONS_V1_MIGRATION
from src.vespercode.storage.migrations.v0010_writeback_approvals import (
    WRITEBACK_APPROVALS_V1_MIGRATION,
)
from src.vespercode.storage.migrations.v0011_persistence import (
    PERSISTENCE_V1_MIGRATION,
)
from src.vespercode.storage.migrations.v0012_recovery import RECOVERY_V1_MIGRATION


class _RegistryControlDatabase(ControlDatabase):
    """ControlDatabase plus the read-only ``execute`` seam the card probe uses.

    The card's schema-owner probe calls ``execute`` on the fixture; the
    connection wrapper exposes the autocommit read-only query through
    ``read_rows``, so this test-local subclass only adds the name.  The
    displayed probe's parameter annotation is the base ``ControlDatabase``,
    so the call carries the documented ``# type: ignore[attr-defined]``
    (T24.1 exact-RED mypy-deviation precedent).
    """

    def execute(
        self,
        sql: str,
        parameters: tuple[object, ...] = (),
    ) -> list[sqlite3.Row]:
        return self.read_rows(sql, parameters)


@pytest.fixture
def empty_control_database(tmp_path: Path) -> Iterator[_RegistryControlDatabase]:
    database = _RegistryControlDatabase(
        open_control_database(tmp_path / "registry.db")._connection
    )
    yield database
    database.close()


def expected_v1_domain_migrations() -> tuple[MigrationV1, ...]:
    """The exact immutable v1 domain migration producer set, in version order."""
    return (
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


def create_table_targets(statements: list[str]) -> set[str]:
    """The exact CREATE TABLE targets of the traced statements."""
    return {
        match.group(1)
        for statement in statements
        for match in re.finditer(r"CREATE TABLE ([a-z_]+)", statement)
    }


def no_if_not_exists_for_domain_tables(statements: list[str]) -> bool:
    """No domain CREATE TABLE uses ``IF NOT EXISTS`` (replay must fail loudly).

    The engine's own ``schema_migrations`` bootstrap is the only allowed
    ``IF NOT EXISTS`` statement and is excluded by name.
    """
    return not any(
        "CREATE TABLE IF NOT EXISTS" in statement
        and "schema_migrations" not in statement
        for statement in statements
    )


def test_registry_rejects_missing_required_domain_migration() -> None:
    incomplete = tuple(
        migration
        for migration in expected_v1_domain_migrations()
        if migration.name != "feedback_v1"
    )
    with pytest.raises(MigrationRegistryError, match="MIGRATION_SET_INCOMPLETE"):
        compose_v1_migrations(incomplete)


EXPECTED_V1_TABLE_DELTAS_BY_VERSION = {
    1: {"run_config_snapshots", "runs", "wait_contexts"},
    2: {"idempotency_events"},
    3: {"disclosure_grant_subjects", "disclosure_grants"},
    4: {"disclosure_authorizations"},
    5: {"memory_entries"},
    6: {"audit_events"},
    7: {"agent_turns", "run_turn_call_counters"},
    8: {"feedback_records"},
    9: {"action_records"},
    10: {"writeback_approval_subjects", "writeback_approvals"},
    11: {"persistence_transactions", "persistence_path_records"},
    12: {"recovery_results"},
}


def test_registry_prefixes_match_exact_schema_owner_map(
    empty_control_database: ControlDatabase,
) -> None:
    before: set[str] = set()
    for version in range(1, 13):
        statements: list[str] = []
        empty_control_database.set_trace_callback(statements.append)
        apply_migrations(
            empty_control_database,
            ALL_V1_MIGRATIONS[:version],
        )
        empty_control_database.set_trace_callback(None)
        domain_create_targets = create_table_targets(statements) - {"schema_migrations"}
        assert domain_create_targets == (EXPECTED_V1_TABLE_DELTAS_BY_VERSION[version])
        assert no_if_not_exists_for_domain_tables(statements)
        after = {
            row[0]
            for row in empty_control_database.execute(  # type: ignore[attr-defined]
                "SELECT name FROM sqlite_schema "
                "WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
            )
        }
        framework_delta = {"schema_migrations"} if version == 1 else set()
        assert after - before == (
            EXPECTED_V1_TABLE_DELTAS_BY_VERSION[version] | framework_delta
        )
        before = after

    expected_final = {"schema_migrations"} | set().union(
        *EXPECTED_V1_TABLE_DELTAS_BY_VERSION.values()
    )
    assert len(expected_final) == 19
    assert before == expected_final


def test_registry_complete_composition_is_exact() -> None:
    """GREEN-1: versions 1..12, expected names/order, unique checksums."""
    expected = expected_v1_domain_migrations()
    assert ALL_V1_MIGRATIONS == expected
    assert [migration.version for migration in ALL_V1_MIGRATIONS] == list(range(1, 13))
    assert [migration.name for migration in ALL_V1_MIGRATIONS] == [
        "run_wait_v1",
        "idempotency_v1",
        "disclosure_grants_v1",
        "disclosure_authorizations_v1",
        "memory_v1",
        "audit_v1",
        "agent_turns_v1",
        "feedback_v1",
        "actions_v1",
        "writeback_approvals_v1",
        "persistence_v1",
        "recovery_v1",
    ]
    checksums = [migration.checksum.value for migration in ALL_V1_MIGRATIONS]
    assert len(set(checksums)) == 12
    composed = compose_v1_migrations(expected)
    assert composed == expected
    assert isinstance(composed, tuple)


def _noop_apply(tx: ControlTransactionV1) -> None:
    """Synthetic apply that must never execute (composition rejects first)."""


@pytest.mark.parametrize(
    ("label", "tampered", "code"),
    [
        (
            "missing-version-3",
            tuple(
                migration
                for migration in expected_v1_domain_migrations()
                if migration.version != 3
            ),
            "MIGRATION_SET_INCOMPLETE",
        ),
        (
            "gap-version-2",
            tuple(
                migration
                for migration in expected_v1_domain_migrations()
                if migration.version != 2
            ),
            "MIGRATION_SET_INCOMPLETE",
        ),
        (
            "duplicate-version",
            (
                expected_v1_domain_migrations()[0],
                expected_v1_domain_migrations()[0],
                *expected_v1_domain_migrations()[2:],
            ),
            "MIGRATION_SET_DUPLICATE",
        ),
        (
            "duplicate-name",
            (
                expected_v1_domain_migrations()[0],
                replace(
                    expected_v1_domain_migrations()[1],
                    name="run_wait_v1",
                ),
                *expected_v1_domain_migrations()[2:],
            ),
            "MIGRATION_SET_DUPLICATE",
        ),
        (
            "reordered",
            (
                expected_v1_domain_migrations()[1],
                expected_v1_domain_migrations()[0],
                *expected_v1_domain_migrations()[2:],
            ),
            "MIGRATION_ORDER_INVALID",
        ),
        (
            "late-version-13",
            (
                *expected_v1_domain_migrations(),
                MigrationV1(
                    version=13,
                    name="synthetic_v13",
                    checksum=DigestV1(value="f" * 64),
                    apply=_noop_apply,
                ),
            ),
            "MIGRATION_UNEXPECTED",
        ),
        (
            "wrong-owner-name",
            (
                *expected_v1_domain_migrations()[:7],
                replace(
                    expected_v1_domain_migrations()[7],
                    name="actions_v1",
                ),
                *expected_v1_domain_migrations()[8:],
            ),
            "MIGRATION_NAME_MISMATCH",
        ),
        (
            "checksum-drift",
            (
                *expected_v1_domain_migrations()[:7],
                replace(
                    expected_v1_domain_migrations()[7],
                    checksum=DigestV1(value="0" * 64),
                ),
                *expected_v1_domain_migrations()[8:],
            ),
            "MIGRATION_CHECKSUM_DRIFT",
        ),
    ],
)
def test_registry_fail_closed_composition_matrix(
    label: str,
    tampered: tuple[MigrationV1, ...],
    code: str,
) -> None:
    """GREEN-2: every invalid composition class fails closed with its code."""
    with pytest.raises(MigrationRegistryError, match=code):
        compose_v1_migrations(tampered)


def test_registry_rejects_non_digest_checksum() -> None:
    """A descriptor carrying a non-DigestV1 checksum fails closed.

    ``MigrationV1`` validates version/name/apply only, so a dynamic caller
    can construct a descriptor whose checksum is not a ``DigestV1``; the
    registry rejects it with the stable code instead of dereferencing
    ``.value`` on the wrong type.
    """
    invalid = MigrationV1(
        version=8,
        name="feedback_v1",
        checksum="not-a-digest",  # type: ignore[arg-type]
        apply=_noop_apply,
    )
    with pytest.raises(MigrationRegistryError, match="MIGRATION_SET_INVALID"):
        compose_v1_migrations(
            (
                *expected_v1_domain_migrations()[:7],
                invalid,
                *expected_v1_domain_migrations()[8:],
            )
        )


def test_registry_rejects_non_descriptor_entry() -> None:
    """A non-descriptor entry fails closed with MIGRATION_SET_INVALID.

    The registry validates every entry defensively even though the typed
    interface only accepts ``MigrationV1`` descriptors; a dynamic caller
    passing a non-descriptor is rejected before any other check.
    """
    with pytest.raises(MigrationRegistryError, match="MIGRATION_SET_INVALID"):
        compose_v1_migrations(("not-a-migration",))  # type: ignore[arg-type]


def test_early_version_below_one_cannot_be_composed() -> None:
    """An early version below 1 fails closed at the descriptor boundary.

    ``MigrationV1.__post_init__`` requires a positive version (Task 7.A
    engine validation), so no version 0 or negative descriptor can ever
    reach the registry composition — the early class is closed before
    ``compose_v1_migrations``.
    """
    with pytest.raises(ValueError, match="positive integer"):
        MigrationV1(
            version=0,
            name="synthetic_v0",
            checksum=DigestV1(value="e" * 64),
            apply=_noop_apply,
        )


def test_schema_owner_probe_fails_closed_on_tampered_ownership(
    tmp_path: Path,
) -> None:
    """GREEN-3: the exact-delta probe fails closed on tampered table ownership.

    A tampered migration that adds, omits, or moves a table past the
    declared owner version makes the read-only per-prefix delta diverge
    from the test-only owner map; a repeated already-owned table fails the
    engine closed with the whole prefix rolled back.
    """

    def _prefix_delta(
        database_path: Path,
        migrations: tuple[MigrationV1, ...],
    ) -> tuple[MigrationResultV1, set[str]]:
        database = open_control_database(database_path)
        try:
            statements: list[str] = []
            database.set_trace_callback(statements.append)
            result = apply_migrations(database, migrations)
            database.set_trace_callback(None)
            return result, create_table_targets(statements) - {"schema_migrations"}
        finally:
            database.close()

    def _with_extra_table(migration: MigrationV1, ddl: str) -> MigrationV1:
        def _apply(tx: ControlTransactionV1) -> None:
            migration.apply(tx)
            tx.execute(ddl)

        return replace(migration, apply=_apply)

    prefix7 = ALL_V1_MIGRATIONS[:6]

    # Introduces an undeclared table at v0007.
    undeclared = _with_extra_table(
        AGENT_TURNS_V1_MIGRATION,
        "CREATE TABLE probe_undeclared (id INTEGER PRIMARY KEY)",
    )
    result, delta = _prefix_delta(
        tmp_path / "undeclared.db",
        (*prefix7, undeclared),
    )
    assert result.kind == "APPLIED"
    assert delta != EXPECTED_V1_TABLE_DELTAS_BY_VERSION[7]

    # Omits a declared table at v0007.
    def _apply_omitted(tx: ControlTransactionV1) -> None:
        tx.execute("CREATE TABLE agent_turns (turn_id TEXT PRIMARY KEY)")

    omitted = replace(AGENT_TURNS_V1_MIGRATION, apply=_apply_omitted)
    result, delta = _prefix_delta(tmp_path / "omitted.db", (*prefix7, omitted))
    assert result.kind == "APPLIED"
    assert delta != EXPECTED_V1_TABLE_DELTAS_BY_VERSION[7]

    # Moves a v0008-owned table earlier, into v0007.
    moved_early = _with_extra_table(
        AGENT_TURNS_V1_MIGRATION,
        "CREATE TABLE feedback_records (id INTEGER PRIMARY KEY)",
    )
    result, delta = _prefix_delta(tmp_path / "moved.db", (*prefix7, moved_early))
    assert result.kind == "APPLIED"
    assert delta != EXPECTED_V1_TABLE_DELTAS_BY_VERSION[7]

    # Repeats an already-owned table at v0009: the engine fails closed and
    # the whole batch transaction rolls back (zero tables, no partial
    # mutation — the Task 7.A whole-batch atomicity contract).
    repeated = _with_extra_table(
        ACTIONS_V1_MIGRATION,
        "CREATE TABLE feedback_records (id INTEGER PRIMARY KEY)",
    )
    database_path = tmp_path / "repeated.db"
    result, _ = _prefix_delta(
        database_path,
        (*ALL_V1_MIGRATIONS[:8], repeated),
    )
    assert result.kind == "MIGRATION_FAILED"
    database = open_control_database(database_path)
    try:
        after = {
            str(row[0])
            for row in database.read_rows(
                "SELECT name FROM sqlite_schema"
                " WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
            )
        }
    finally:
        database.close()
    assert after == set()


def test_registry_owns_composition_only() -> None:
    """GREEN-4: registry.py has no DDL, no table names, no test-only map."""
    source = _registry_source()
    assert "CREATE TABLE" not in source
    assert "sqlite_schema" not in source
    # The immutable producer modules are consumed by module name (their file
    # names embed domain words), and the composition contract legitimately
    # carries the twelve migration names (``writeback_approvals_v1`` embeds
    # the word ``writeback_approvals``).  The no-table-name check therefore
    # inspects only string literals with the composition's own migration
    # names removed: no table name may appear in any other string the
    # production code carries (docstrings, error messages, or data).
    literal_text = "".join(re.findall(r'"[^"]*"', source))
    for migration in ALL_V1_MIGRATIONS:
        literal_text = literal_text.replace(migration.name, "")
    expected_tables: set[str] = set()
    for delta in EXPECTED_V1_TABLE_DELTAS_BY_VERSION.values():
        expected_tables |= delta
    for table in expected_tables:
        assert table not in literal_text
    assert "test_migration_registry" not in source
    assert "EXPECTED_V1_TABLE_DELTAS" not in source


def _registry_source() -> str:
    root = Path(__file__).resolve().parents[3]
    registry_path = (
        root / "src" / "vespercode" / "storage" / "migrations" / "registry.py"
    )
    return registry_path.read_text(encoding="utf-8")

"""T07.1 legacy step 7.A: explicit control-database connection policy.

``open_control_database`` opens the local control database in autocommit
mode with explicit control flags (``foreign_keys`` on, ``busy_timeout``
set) so every write goes through an explicit ``BEGIN IMMEDIATE``
transaction identity; the ``schema_migrations`` history bootstrap belongs
to the migration engine.  Domain schemas, repositories, and the final
migration registry remain out of scope (GREEN-4).
"""

from __future__ import annotations

import sqlite3
from contextlib import AbstractContextManager
from pathlib import Path
from types import TracebackType
from typing import Callable, Literal, Sequence

_BUSY_TIMEOUT_MILLISECONDS = 5000


class ControlDatabaseErrorV1(ValueError):
    """Closed rejection for an invalid control-database operation."""


class ControlTransactionErrorV1(ControlDatabaseErrorV1):
    """Closed rejection for an invalid explicit transaction operation."""


class ControlTransactionV1(AbstractContextManager["ControlTransactionV1"]):
    """One explicit ``BEGIN IMMEDIATE`` transaction on the shared connection.

    Commits on clean exit and rolls back when the body raises, so a whole
    batch of statements is atomic.  ``BEGIN IMMEDIATE`` serializes writers,
    which is what lets exactly one competing decision win.
    """

    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection

    def __enter__(self) -> ControlTransactionV1:
        try:
            self._connection.execute("BEGIN IMMEDIATE")
        except sqlite3.OperationalError as exc:
            raise ControlTransactionErrorV1(
                "cannot begin an immediate transaction"
            ) from exc
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> Literal[False]:
        if exc_type is None:
            self._connection.commit()
        else:
            self._connection.rollback()
        return False

    def execute(
        self,
        sql: str,
        parameters: Sequence[object] = (),
    ) -> sqlite3.Cursor:
        """Execute one statement inside this explicit transaction."""
        return self._connection.execute(sql, parameters)


class ControlDatabase:
    """One SQLite control database with explicit transaction semantics."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection

    def immediate_transaction(self) -> AbstractContextManager[ControlTransactionV1]:
        """Open one explicit ``BEGIN IMMEDIATE`` transaction identity."""
        return ControlTransactionV1(self._connection)

    def read_rows(
        self,
        sql: str,
        parameters: Sequence[object] = (),
    ) -> list[sqlite3.Row]:
        """Run one read-only query in autocommit mode (no transaction)."""
        return self._connection.execute(sql, parameters).fetchall()

    def recorded_migrations(self) -> tuple[tuple[int, str, str], ...]:
        """The recorded migration history ordered by version."""
        rows = self.read_rows(
            "SELECT version, name, checksum FROM schema_migrations ORDER BY version"
        )
        return tuple((int(row[0]), str(row[1]), str(row[2])) for row in rows)

    def replace_recorded_migration_checksum(self, version: int, checksum: str) -> None:
        """Replace one recorded migration checksum (history seam).

        Used by the checksum-drift contract tests to inject a drifted
        history; fails closed when the version is not recorded.
        """
        cursor = self._connection.execute(
            "UPDATE schema_migrations SET checksum = ? WHERE version = ?",
            (checksum, version),
        )
        if cursor.rowcount != 1:
            raise ControlDatabaseErrorV1(f"version {version} is not recorded")

    def set_trace_callback(self, callback: Callable[[str], object] | None) -> None:
        """Attach a statement trace (read-only introspection seam)."""
        self._connection.set_trace_callback(callback)

    def close(self) -> None:
        """Close the underlying SQLite connection."""
        self._connection.close()


def open_control_database(path: Path) -> ControlDatabase:
    """Open the local control database with explicit control flags.

    The connection runs in autocommit mode (``isolation_level=None``) so
    every write is explicitly transactional, with foreign keys enforced
    and a bounded busy timeout for competing writers.  The
    ``schema_migrations`` history bootstrap belongs to the migration
    engine (Task 7.A storage registry), not to connection policy.
    """
    if not isinstance(path, Path):
        raise ControlDatabaseErrorV1("control database path must be a Path")
    connection = sqlite3.connect(str(path), isolation_level=None)
    try:
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute(f"PRAGMA busy_timeout = {_BUSY_TIMEOUT_MILLISECONDS}")
    except Exception:
        connection.close()
        raise
    return ControlDatabase(connection)

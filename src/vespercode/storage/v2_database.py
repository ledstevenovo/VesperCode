"""Independent v2 SQLite control database.

The v1 database and its migration history remain readable legacy artifacts.
This module creates a fresh v2 database whose identifiers are ordinary opaque
references.  Revision columns provide the small control-plane change check
needed by approvals; they are not content authentication.
"""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator, Sequence

from vespercode.candidate.v2_candidate import (
    CandidateControlIdentityV2,
    CandidateDiffRecordV2,
)
from vespercode.contracts.v2_identity import (
    new_action_id,
    new_approval_id,
    new_artifact_id,
    new_authorization_id,
    new_candidate_id,
    new_diff_id,
    new_disclosure_id,
    new_grant_id,
    new_run_id,
    new_snapshot_id,
    new_transaction_id,
    new_validation_run_id,
)
from vespercode.contracts.v2_validation import (
    MAX_VALIDATION_ERROR_CHARS,
    ValidationRunRecordV2,
)
from vespercode.contracts.v2_writeback import JournalEntryV2
from vespercode.governance.v2_disclosure import (
    MAX_DISCLOSURE_CHARGE_BYTES_V2,
    MIN_DISCLOSURE_CHARGE_BYTES_V2,
    DisclosureAuthorizationOutcomeV2,
    DisclosureAuthorizationRecordV2,
    DisclosureConsumeOutcomeV2,
    DisclosureGrantRecordV2,
    DisclosurePathScopeV2,
    DisclosureScopeErrorV2,
    DisclosureSourceV2,
    authorization_payload_key,
    canonicalize_disclosure_sources,
    check_disclosure_request_sources,
    disclosure_consume_outcome_message,
    disclosure_outcome_message,
    grant_is_expired,
)
from vespercode.profiles.v2_endpoints import ProviderEndpointRecordV2
from vespercode.profiles.v2_reference import ReferenceProfileRecordV2

V2_DATABASE_FILENAME = "vespercode-v2.sqlite"
V2_SCHEMA_VERSION = 3
_V2_TABLES = frozenset(
    {
        "v2_schema_meta",
        "runs",
        "snapshots",
        "candidates",
        "actions",
        "disclosures",
        "artifacts",
        "writeback_approvals",
        "transactions",
        "transaction_journal",
        "reference_profiles",
        "candidate_diffs",
        "validation_runs",
        "provider_endpoints",
        "disclosure_grants",
        "disclosure_grant_categories",
        "disclosure_grant_scopes",
        "disclosure_authorizations",
        "disclosure_authorization_sources",
    }
)
_V2_REQUIRED_COLUMNS = {
    "v2_schema_meta": {"version", "name"},
    "runs": {"run_id", "workspace_path", "status", "phase", "revision"},
    "snapshots": {"snapshot_id", "run_id", "revision"},
    "candidates": {"candidate_id", "run_id", "snapshot_id", "revision"},
    "actions": {"action_id", "run_id", "action_type", "status", "created_at"},
    "disclosures": {"disclosure_id", "run_id", "status", "created_at"},
    "artifacts": {"artifact_id", "run_id", "kind", "location", "created_at"},
    "writeback_approvals": {
        "approval_id",
        "run_id",
        "candidate_id",
        "candidate_revision",
        "status",
    },
    "transactions": {
        "transaction_id",
        "run_id",
        "candidate_id",
        "state",
        "updated_at",
    },
    "transaction_journal": {
        "transaction_id",
        "position",
        "path",
        "action_type",
        "content",
        "original_content",
    },
    "reference_profiles": {
        "reference_profile_id",
        "profile_revision",
        "python_version",
        "pytest_version",
        "ruff_version",
        "mypy_version",
        "created_at",
    },
    "candidate_diffs": {
        "diff_id",
        "run_id",
        "candidate_id",
        "candidate_revision",
        "artifact_id",
        "created_at",
    },
    "validation_runs": {
        "validation_run_id",
        "run_id",
        "candidate_id",
        "candidate_revision",
        "reference_profile_id",
        "reference_profile_revision",
        "status",
        "error",
        "created_at",
        "updated_at",
    },
    "provider_endpoints": {
        "endpoint_id",
        "provider",
        "reference_profile_id",
        "reference_profile_revision",
        "created_at",
    },
    "disclosure_grants": {
        "grant_id",
        "disclosure_id",
        "run_id",
        "reference_profile_id",
        "reference_profile_revision",
        "expires_at",
        "byte_budget",
        "consumed_bytes",
        "status",
        "created_at",
        "updated_at",
    },
    "disclosure_grant_categories": {
        "grant_id",
        "position",
        "category",
    },
    "disclosure_grant_scopes": {
        "grant_id",
        "position",
        "scope_kind",
        "scope_path",
    },
    "disclosure_authorizations": {
        "authorization_id",
        "grant_id",
        "run_id",
        "request_id",
        "endpoint_id",
        "charge_bytes",
        "status",
        "created_at",
        "consumed_at",
    },
    "disclosure_authorization_sources": {
        "authorization_id",
        "position",
        "category",
        "source_path",
    },
}

_RUN_TRANSITIONS = {
    ("CREATED", "RUNNING"),
    ("RUNNING", "SUCCEEDED"),
    ("RUNNING", "STOPPED"),
}

# Route A / A3 durable transaction state machine. PREPARED -> WRITING ->
# COMMITTED is the happy path; faults mark UNRESOLVED; recovery may re-drive
# the write or roll back. Terminal states are final.
_TRANSACTION_TRANSITIONS = {
    ("PREPARED", "WRITING"),
    ("PREPARED", "ROLLED_BACK"),
    ("WRITING", "COMMITTED"),
    ("WRITING", "UNRESOLVED"),
    ("WRITING", "ROLLED_BACK"),
    ("UNRESOLVED", "WRITING"),
    ("UNRESOLVED", "COMMITTED"),
    ("UNRESOLVED", "ROLLED_BACK"),
}
_ACTIVE_TRANSACTION_STATES = ("PREPARED", "WRITING", "UNRESOLVED")
_TERMINAL_TRANSACTION_STATES = ("COMMITTED", "ROLLED_BACK")


class V2DatabaseError(ValueError):
    """Closed rejection for a v2 database path or schema mismatch."""


def _require_revision(value: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise V2DatabaseError("revision must be a non-negative integer")
    return value

_DDL = (
    "CREATE TABLE IF NOT EXISTS v2_schema_meta ("
    " version INTEGER PRIMARY KEY, name TEXT NOT NULL)",
    "CREATE TABLE IF NOT EXISTS runs ("
    " run_id TEXT PRIMARY KEY, workspace_path TEXT NOT NULL,"
    " status TEXT NOT NULL, phase TEXT, revision INTEGER NOT NULL DEFAULT 1 CHECK (revision >= 0),"
    " created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,"
    " updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)",
    "CREATE TABLE IF NOT EXISTS snapshots ("
    " snapshot_id TEXT PRIMARY KEY, run_id TEXT NOT NULL REFERENCES runs(run_id),"
    " revision INTEGER NOT NULL DEFAULT 0 CHECK (revision >= 0), created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)",
    "CREATE TABLE IF NOT EXISTS candidates ("
    " candidate_id TEXT PRIMARY KEY, run_id TEXT NOT NULL REFERENCES runs(run_id),"
    " snapshot_id TEXT NOT NULL REFERENCES snapshots(snapshot_id),"
    " revision INTEGER NOT NULL DEFAULT 0 CHECK (revision >= 0), status TEXT NOT NULL DEFAULT 'ACTIVE',"
    " created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,"
    " updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)",
    "CREATE TABLE IF NOT EXISTS actions ("
    " action_id TEXT PRIMARY KEY, run_id TEXT NOT NULL REFERENCES runs(run_id),"
    " action_type TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'RECEIVED',"
    " created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)",
    "CREATE TABLE IF NOT EXISTS disclosures ("
    " disclosure_id TEXT PRIMARY KEY, run_id TEXT NOT NULL REFERENCES runs(run_id),"
    " status TEXT NOT NULL DEFAULT 'PENDING', created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)",
    "CREATE TABLE IF NOT EXISTS artifacts ("
    " artifact_id TEXT PRIMARY KEY, run_id TEXT NOT NULL REFERENCES runs(run_id),"
    " kind TEXT NOT NULL, location TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)",
    "CREATE TABLE IF NOT EXISTS writeback_approvals ("
    " approval_id TEXT PRIMARY KEY, run_id TEXT NOT NULL REFERENCES runs(run_id),"
    " candidate_id TEXT NOT NULL REFERENCES candidates(candidate_id),"
    " candidate_revision INTEGER NOT NULL CHECK (candidate_revision >= 0), status TEXT NOT NULL DEFAULT 'PENDING',"
    " created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, consumed_at TEXT)",
    "CREATE TABLE IF NOT EXISTS transactions ("
    " transaction_id TEXT PRIMARY KEY, run_id TEXT NOT NULL REFERENCES runs(run_id),"
    " candidate_id TEXT NOT NULL REFERENCES candidates(candidate_id),"
    " state TEXT NOT NULL DEFAULT 'PREPARED' CHECK (state IN"
    " ('PREPARED','WRITING','COMMITTED','UNRESOLVED','ROLLED_BACK')),"
    " created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,"
    " updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)",
    "CREATE TABLE IF NOT EXISTS transaction_journal ("
    " transaction_id TEXT NOT NULL REFERENCES transactions(transaction_id),"
    " position INTEGER NOT NULL, path TEXT NOT NULL, action_type TEXT NOT NULL,"
    " content TEXT NOT NULL, original_content TEXT,"
    " PRIMARY KEY (transaction_id, position))",
    # Route B / B1 tables: control-plane identity for reference profiles,
    # candidate diffs, and validation runs.  They join the v3 schema in
    # place (no new schema version, no migration of v1 rows); the strict
    # column validation above rejects any malformed variant on open.
    "CREATE TABLE IF NOT EXISTS reference_profiles ("
    " reference_profile_id TEXT NOT NULL,"
    " profile_revision INTEGER NOT NULL CHECK (profile_revision >= 0),"
    " python_version TEXT NOT NULL, pytest_version TEXT NOT NULL,"
    " ruff_version TEXT NOT NULL, mypy_version TEXT NOT NULL,"
    " created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,"
    " PRIMARY KEY (reference_profile_id, profile_revision))",
    "CREATE TABLE IF NOT EXISTS candidate_diffs ("
    " diff_id TEXT PRIMARY KEY, run_id TEXT NOT NULL REFERENCES runs(run_id),"
    " candidate_id TEXT NOT NULL REFERENCES candidates(candidate_id),"
    " candidate_revision INTEGER NOT NULL CHECK (candidate_revision >= 0),"
    " artifact_id TEXT NOT NULL REFERENCES artifacts(artifact_id),"
    " created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,"
    " UNIQUE (candidate_id, candidate_revision))",
    "CREATE TABLE IF NOT EXISTS validation_runs ("
    " validation_run_id TEXT PRIMARY KEY,"
    " run_id TEXT NOT NULL REFERENCES runs(run_id),"
    " candidate_id TEXT NOT NULL REFERENCES candidates(candidate_id),"
    " candidate_revision INTEGER NOT NULL CHECK (candidate_revision >= 0),"
    " reference_profile_id TEXT NOT NULL,"
    " reference_profile_revision INTEGER NOT NULL"
    " CHECK (reference_profile_revision >= 0),"
    " status TEXT NOT NULL DEFAULT 'PENDING'"
    " CHECK (status IN ('PENDING','PASSED','FAILED')),"
    " error TEXT CHECK (error IS NULL OR length(error) <= 512),"
    " created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,"
    " updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,"
    " FOREIGN KEY (reference_profile_id, reference_profile_revision)"
    " REFERENCES reference_profiles"
    " (reference_profile_id, profile_revision))",
    # Route B / B2 tables: the disclosure/provider/credential control
    # plane. They join the v3 schema in place (no new schema version, no
    # migration of v1 rows), keyed by opaque IDs and revisions only; no
    # digest column exists and no credential value is ever stored.
    "CREATE TABLE IF NOT EXISTS provider_endpoints ("
    " endpoint_id TEXT PRIMARY KEY, provider TEXT NOT NULL,"
    " reference_profile_id TEXT NOT NULL, reference_profile_revision INTEGER"
    " NOT NULL CHECK (reference_profile_revision >= 0),"
    " created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)",
    "CREATE TABLE IF NOT EXISTS disclosure_grants ("
    " grant_id TEXT PRIMARY KEY, disclosure_id TEXT NOT NULL UNIQUE"
    " REFERENCES disclosures(disclosure_id),"
    " run_id TEXT NOT NULL REFERENCES runs(run_id),"
    " reference_profile_id TEXT NOT NULL, reference_profile_revision INTEGER"
    " NOT NULL CHECK (reference_profile_revision >= 0),"
    " expires_at TEXT NOT NULL, byte_budget INTEGER NOT NULL"
    " CHECK (byte_budget >= 1), consumed_bytes INTEGER NOT NULL DEFAULT 0"
    " CHECK (consumed_bytes >= 0),"
    " status TEXT NOT NULL DEFAULT 'PENDING' CHECK (status IN"
    " ('PENDING','ACTIVE','REVOKED','EXPIRED','EXHAUSTED')),"
    " created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,"
    " updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)",
    "CREATE TABLE IF NOT EXISTS disclosure_grant_categories ("
    " grant_id TEXT NOT NULL REFERENCES disclosure_grants(grant_id),"
    " position INTEGER NOT NULL CHECK (position >= 0),"
    " category TEXT NOT NULL,"
    " PRIMARY KEY (grant_id, position), UNIQUE (grant_id, category))",
    "CREATE TABLE IF NOT EXISTS disclosure_grant_scopes ("
    " grant_id TEXT NOT NULL REFERENCES disclosure_grants(grant_id),"
    " position INTEGER NOT NULL CHECK (position >= 0),"
    " scope_kind TEXT NOT NULL CHECK (scope_kind IN"
    " ('ROOT','FILE','DIRECTORY')),"
    " scope_path TEXT NOT NULL, PRIMARY KEY (grant_id, position),"
    " UNIQUE (grant_id, scope_kind, scope_path))",
    "CREATE TABLE IF NOT EXISTS disclosure_authorizations ("
    " authorization_id TEXT PRIMARY KEY, grant_id TEXT NOT NULL"
    " REFERENCES disclosure_grants(grant_id),"
    " run_id TEXT NOT NULL REFERENCES runs(run_id),"
    " request_id TEXT NOT NULL, endpoint_id TEXT NOT NULL"
    " REFERENCES provider_endpoints(endpoint_id),"
    " charge_bytes INTEGER NOT NULL CHECK (charge_bytes >= 1),"
    " status TEXT NOT NULL DEFAULT 'AUTHORIZED'"
    " CHECK (status IN ('AUTHORIZED','CONSUMED')),"
    " created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,"
    " consumed_at TEXT, UNIQUE (grant_id, request_id))",
    "CREATE TABLE IF NOT EXISTS disclosure_authorization_sources ("
    " authorization_id TEXT NOT NULL REFERENCES"
    " disclosure_authorizations(authorization_id),"
    " position INTEGER NOT NULL CHECK (position >= 0),"
    " category TEXT NOT NULL, source_path TEXT,"
    " PRIMARY KEY (authorization_id, position))",
)


class V2Database:
    """Tiny transactional repository for v2 control records."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        self._connection.execute("BEGIN IMMEDIATE")
        try:
            yield self._connection
        except BaseException:
            self._connection.rollback()
            raise
        else:
            self._connection.commit()

    def create_run(self, workspace_path: str, run_id: str | None = None) -> str:
        identifier = run_id or new_run_id()
        with self.transaction() as connection:
            connection.execute(
                "INSERT INTO runs (run_id, workspace_path, status, phase) "
                "VALUES (?, ?, 'CREATED', NULL)",
                (identifier, workspace_path),
            )
        return identifier

    def get_run(self, run_id: str) -> sqlite3.Row | None:
        return self._connection.execute(
            "SELECT * FROM runs WHERE run_id = ?", (run_id,)
        ).fetchone()

    def list_runs(self, limit: int = 50) -> list[sqlite3.Row]:
        """Project the most recent runs (bounded, newest first).

        Route B / B3 read helper for the local integration surface: the
        limit is fail-closed (1..500) and the projection carries only the
        bounded run columns — never workspace content.
        """

        if isinstance(limit, bool) or not isinstance(limit, int):
            raise V2DatabaseError("run list limit must be an integer")
        if not 1 <= limit <= 500:
            raise V2DatabaseError("run list limit must be between 1 and 500")
        return list(
            self._connection.execute(
                "SELECT run_id, status, phase, revision FROM runs "
                "ORDER BY created_at DESC, run_id LIMIT ?",
                (limit,),
            ).fetchall()
        )

    def transition_run(
        self,
        run_id: str,
        *,
        expected_revision: int,
        status: str,
        phase: str | None,
    ) -> bool:
        """Apply one legal status transition with an optimistic revision CAS."""

        row = self.get_run(run_id)
        if row is None:
            return False
        if (str(row["status"]), status) not in _RUN_TRANSITIONS:
            return False
        if status == "RUNNING" and phase is None:
            return False
        if status != "RUNNING" and phase is not None:
            return False
        with self.transaction() as connection:
            cursor = connection.execute(
                "UPDATE runs SET status = ?, phase = ?, revision = revision + 1, "
                "updated_at = CURRENT_TIMESTAMP WHERE run_id = ? AND revision = ?",
                (status, phase, run_id, expected_revision),
            )
            return cursor.rowcount == 1

    def transition_run_latest(
        self, run_id: str, *, status: str, phase: str | None
    ) -> bool:
        """Atomically transition using the row's current revision."""

        with self.transaction() as connection:
            row = connection.execute(
                "SELECT status, revision FROM runs WHERE run_id = ?", (run_id,)
            ).fetchone()
            if row is None or (str(row[0]), status) not in _RUN_TRANSITIONS:
                return False
            if (status == "RUNNING") != (phase is not None):
                return False
            cursor = connection.execute(
                "UPDATE runs SET status = ?, phase = ?, revision = revision + 1, "
                "updated_at = CURRENT_TIMESTAMP WHERE run_id = ? AND revision = ?",
                (status, phase, run_id, int(row[1])),
            )
            return cursor.rowcount == 1

    def create_snapshot(
        self, run_id: str, snapshot_id: str | None = None, revision: int = 0
    ) -> str:
        revision = _require_revision(revision)
        identifier = snapshot_id or new_snapshot_id()
        with self.transaction() as connection:
            connection.execute(
                "INSERT INTO snapshots (snapshot_id, run_id, revision) VALUES (?, ?, ?)",
                (identifier, run_id, revision),
            )
        return identifier

    def create_candidate(
        self,
        run_id: str,
        snapshot_id: str,
        revision: int = 0,
        candidate_id: str | None = None,
    ) -> str:
        revision = _require_revision(revision)
        identifier = candidate_id or new_candidate_id()
        with self.transaction() as connection:
            snapshot = connection.execute(
                "SELECT run_id FROM snapshots WHERE snapshot_id = ?",
                (snapshot_id,),
            ).fetchone()
            if snapshot is None or str(snapshot[0]) != run_id:
                raise V2DatabaseError("candidate run/snapshot mismatch")
            connection.execute(
                "INSERT INTO candidates (candidate_id, run_id, snapshot_id, revision) "
                "VALUES (?, ?, ?, ?)",
                (identifier, run_id, snapshot_id, revision),
            )
        return identifier

    def advance_candidate(self, candidate_id: str, expected_revision: int) -> bool:
        with self.transaction() as connection:
            cursor = connection.execute(
                "UPDATE candidates SET revision = revision + 1, "
                "updated_at = CURRENT_TIMESTAMP WHERE candidate_id = ? AND revision = ?",
                (candidate_id, expected_revision),
            )
            return cursor.rowcount == 1

    def create_action(
        self, run_id: str, action_type: str, action_id: str | None = None
    ) -> str:
        identifier = action_id or new_action_id()
        with self.transaction() as connection:
            connection.execute(
                "INSERT INTO actions (action_id, run_id, action_type) VALUES (?, ?, ?)",
                (identifier, run_id, action_type),
            )
        return identifier

    def create_disclosure(self, run_id: str, disclosure_id: str | None = None) -> str:
        identifier = disclosure_id or new_disclosure_id()
        with self.transaction() as connection:
            connection.execute(
                "INSERT INTO disclosures (disclosure_id, run_id) VALUES (?, ?)",
                (identifier, run_id),
            )
        return identifier

    def create_artifact(
        self, run_id: str, kind: str, location: str, artifact_id: str | None = None
    ) -> str:
        identifier = artifact_id or new_artifact_id()
        with self.transaction() as connection:
            connection.execute(
                "INSERT INTO artifacts (artifact_id, run_id, kind, location) "
                "VALUES (?, ?, ?, ?)",
                (identifier, run_id, kind, location),
            )
        return identifier

    def create_writeback_approval(
        self,
        run_id: str,
        candidate_id: str,
        candidate_revision: int,
        approval_id: str | None = None,
    ) -> str:
        candidate_revision = _require_revision(candidate_revision)
        identifier = approval_id or new_approval_id()
        with self.transaction() as connection:
            candidate = connection.execute(
                "SELECT run_id FROM candidates WHERE candidate_id = ?",
                (candidate_id,),
            ).fetchone()
            if candidate is None or str(candidate[0]) != run_id:
                raise V2DatabaseError("writeback approval run/candidate mismatch")
            current_revision = connection.execute(
                "SELECT revision FROM candidates WHERE candidate_id = ?",
                (candidate_id,),
            ).fetchone()
            if current_revision is None or int(current_revision[0]) != candidate_revision:
                raise V2DatabaseError("writeback approval revision is stale")
            connection.execute(
                "INSERT INTO writeback_approvals "
                "(approval_id, run_id, candidate_id, candidate_revision) "
                "VALUES (?, ?, ?, ?)",
                (identifier, run_id, candidate_id, candidate_revision),
            )
        return identifier

    def consume_writeback_approval(
        self, approval_id: str, candidate_id: str, candidate_revision: int
    ) -> bool:
        with self.transaction() as connection:
            cursor = connection.execute(
                "UPDATE writeback_approvals SET status = 'CONSUMED', "
                "consumed_at = CURRENT_TIMESTAMP WHERE approval_id = ? "
                "AND candidate_id = ? AND candidate_revision = ? AND status = 'PENDING' "
                "AND EXISTS (SELECT 1 FROM candidates "
                "WHERE candidates.candidate_id = writeback_approvals.candidate_id "
                "AND candidates.revision = writeback_approvals.candidate_revision)",
                (approval_id, candidate_id, candidate_revision),
            )
            return cursor.rowcount == 1

    def create_transaction(
        self, run_id: str, candidate_id: str, transaction_id: str | None = None
    ) -> str:
        identifier = transaction_id or new_transaction_id()
        with self.transaction() as connection:
            candidate = connection.execute(
                "SELECT run_id FROM candidates WHERE candidate_id = ?",
                (candidate_id,),
            ).fetchone()
            if candidate is None or str(candidate[0]) != run_id:
                raise V2DatabaseError("transaction run/candidate mismatch")
            connection.execute(
                "INSERT INTO transactions (transaction_id, run_id, candidate_id) "
                "VALUES (?, ?, ?)",
                (identifier, run_id, candidate_id),
            )
        return identifier

    def get_candidate(self, candidate_id: str) -> sqlite3.Row | None:
        return self._connection.execute(
            "SELECT * FROM candidates WHERE candidate_id = ?", (candidate_id,)
        ).fetchone()

    def get_writeback_approval(self, approval_id: str) -> sqlite3.Row | None:
        return self._connection.execute(
            "SELECT * FROM writeback_approvals WHERE approval_id = ?", (approval_id,)
        ).fetchone()

    def get_transaction(self, transaction_id: str) -> sqlite3.Row | None:
        return self._connection.execute(
            "SELECT * FROM transactions WHERE transaction_id = ?", (transaction_id,)
        ).fetchone()

    def get_transaction_journal(self, transaction_id: str) -> list[sqlite3.Row]:
        return list(
            self._connection.execute(
                "SELECT * FROM transaction_journal WHERE transaction_id = ? "
                "ORDER BY position",
                (transaction_id,),
            ).fetchall()
        )

    def list_transactions_in_states(
        self, states: Sequence[str] = _ACTIVE_TRANSACTION_STATES
    ) -> list[sqlite3.Row]:
        if not states:
            return []
        placeholders = ",".join("?" for _ in states)
        return list(
            self._connection.execute(
                f"SELECT * FROM transactions WHERE state IN ({placeholders}) "
                "ORDER BY created_at, transaction_id",
                tuple(states),
            ).fetchall()
        )

    def transition_transaction(
        self, transaction_id: str, *, from_state: str, to_state: str
    ) -> bool:
        """Apply one legal transaction-state change with a state CAS."""

        if (from_state, to_state) not in _TRANSACTION_TRANSITIONS:
            raise V2DatabaseError(
                f"illegal transaction transition: {from_state} -> {to_state}"
            )
        with self.transaction() as connection:
            cursor = connection.execute(
                "UPDATE transactions SET state = ?, updated_at = CURRENT_TIMESTAMP "
                "WHERE transaction_id = ? AND state = ?",
                (to_state, transaction_id, from_state),
            )
            return cursor.rowcount == 1

    def begin_writeback_transaction(
        self,
        *,
        run_id: str,
        candidate_id: str,
        candidate_revision: int,
        approval_id: str,
        entries: Sequence[JournalEntryV2],
        transaction_id: str | None = None,
    ) -> str:
        """Atomically consume the approval and journal the write plan.

        In one SQLite transaction: re-verify the candidate (same run, current
        revision), re-verify the approval (pending, same candidate and
        revision), consume it, and insert the PREPARED transaction plus its
        journal rows.  Any rejection leaves the approval untouched and no
        transaction behind.
        """

        candidate_revision = _require_revision(candidate_revision)
        if not entries:
            raise V2DatabaseError("a writeback transaction requires journal entries")
        identifier = transaction_id or new_transaction_id()
        with self.transaction() as connection:
            candidate = connection.execute(
                "SELECT run_id, revision FROM candidates WHERE candidate_id = ?",
                (candidate_id,),
            ).fetchone()
            if candidate is None or str(candidate[0]) != run_id:
                raise V2DatabaseError("transaction run/candidate mismatch")
            if int(candidate[1]) != candidate_revision:
                raise V2DatabaseError("candidate revision is stale")
            approval = connection.execute(
                "SELECT candidate_id, candidate_revision, status "
                "FROM writeback_approvals WHERE approval_id = ?",
                (approval_id,),
            ).fetchone()
            if approval is None:
                raise V2DatabaseError("writeback approval is missing")
            if str(approval[0]) != candidate_id or int(approval[1]) != candidate_revision:
                raise V2DatabaseError(
                    "writeback approval does not match the candidate"
                )
            if str(approval[2]) != "PENDING":
                raise V2DatabaseError("writeback approval is not pending")
            consumed = connection.execute(
                "UPDATE writeback_approvals SET status = 'CONSUMED', "
                "consumed_at = CURRENT_TIMESTAMP WHERE approval_id = ? "
                "AND status = 'PENDING'",
                (approval_id,),
            )
            if consumed.rowcount != 1:
                raise V2DatabaseError("writeback approval could not be consumed")
            connection.execute(
                "INSERT INTO transactions (transaction_id, run_id, candidate_id, state) "
                "VALUES (?, ?, ?, 'PREPARED')",
                (identifier, run_id, candidate_id),
            )
            for entry in entries:
                connection.execute(
                    "INSERT INTO transaction_journal "
                    "(transaction_id, position, path, action_type, content, "
                    "original_content) VALUES (?, ?, ?, ?, ?, ?)",
                    (
                        identifier,
                        entry.position,
                        entry.path,
                        entry.action_type,
                        entry.content,
                        entry.original_content,
                    ),
                )
        return identifier

    # ------------------------------------------------------------------
    # Route B / B1: candidate control, reference profile, candidate
    # diff, and validation run storage.  These records are control-plane
    # facts keyed by opaque IDs and revisions; no content digest is ever
    # stored or consulted as authorization.
    # ------------------------------------------------------------------

    def get_candidate_control(self, candidate_id: str) -> CandidateControlIdentityV2 | None:
        """Project the candidates row into its control identity record.

        The row's bounded status and non-negative revision are
        revalidated at read time, so a corrupted or foreign-written row
        fails closed here instead of flowing into a consumer.
        """

        row = self._connection.execute(
            "SELECT candidate_id, snapshot_id, revision, status FROM candidates"
            " WHERE candidate_id = ?",
            (candidate_id,),
        ).fetchone()
        if row is None:
            return None
        return CandidateControlIdentityV2(
            candidate_id=str(row[0]),
            snapshot_id=str(row[1]),
            revision=int(row[2]),
            status=str(row[3]),
        )

    def create_reference_profile(self, record: ReferenceProfileRecordV2) -> None:
        """Store one declared reference profile revision, fail closed.

        The (id, revision) key is immutable once declared: re-declaring
        the same key rejects instead of silently overwriting the
        configuration that earlier validation runs recorded.
        """

        if not isinstance(record, ReferenceProfileRecordV2):
            raise V2DatabaseError("record must be a ReferenceProfileRecordV2")
        with self.transaction() as connection:
            existing = connection.execute(
                "SELECT 1 FROM reference_profiles WHERE reference_profile_id = ?"
                " AND profile_revision = ?",
                (record.reference_profile_id, record.profile_revision),
            ).fetchone()
            if existing is not None:
                raise V2DatabaseError(
                    "reference profile revision already exists"
                )
            connection.execute(
                "INSERT INTO reference_profiles"
                " (reference_profile_id, profile_revision, python_version,"
                " pytest_version, ruff_version, mypy_version)"
                " VALUES (?, ?, ?, ?, ?, ?)",
                (
                    record.reference_profile_id,
                    record.profile_revision,
                    record.python_version,
                    record.pytest_version,
                    record.ruff_version,
                    record.mypy_version,
                ),
            )

    def get_reference_profile(
        self, reference_profile_id: str, profile_revision: int
    ) -> ReferenceProfileRecordV2 | None:
        profile_revision = _require_revision(profile_revision)
        row = self._connection.execute(
            "SELECT reference_profile_id, profile_revision, python_version,"
            " pytest_version, ruff_version, mypy_version"
            " FROM reference_profiles WHERE reference_profile_id = ?"
            " AND profile_revision = ?",
            (reference_profile_id, profile_revision),
        ).fetchone()
        if row is None:
            return None
        return ReferenceProfileRecordV2(
            reference_profile_id=str(row[0]),
            profile_revision=int(row[1]),
            python_version=str(row[2]),
            pytest_version=str(row[3]),
            ruff_version=str(row[4]),
            mypy_version=str(row[5]),
        )

    def create_candidate_diff(
        self,
        *,
        run_id: str,
        candidate_id: str,
        candidate_revision: int,
        artifact_id: str,
        diff_id: str | None = None,
    ) -> str:
        """Record one diff artifact for the candidate's current revision.

        Fail-closed order: the candidate must belong to the same run, the
        candidate revision must be current, and the artifact must belong
        to the same run.  One authoritative diff exists per candidate
        revision: re-recording the same revision rejects, because a
        changed diff must advance the revision instead of silently
        replacing the association.
        """

        candidate_revision = _require_revision(candidate_revision)
        identifier = diff_id or new_diff_id()
        with self.transaction() as connection:
            candidate = connection.execute(
                "SELECT run_id, revision FROM candidates WHERE candidate_id = ?",
                (candidate_id,),
            ).fetchone()
            if candidate is None or str(candidate[0]) != run_id:
                raise V2DatabaseError("candidate run mismatch")
            if int(candidate[1]) != candidate_revision:
                raise V2DatabaseError("candidate revision is stale")
            artifact = connection.execute(
                "SELECT run_id FROM artifacts WHERE artifact_id = ?",
                (artifact_id,),
            ).fetchone()
            if artifact is None or str(artifact[0]) != run_id:
                raise V2DatabaseError("artifact run mismatch")
            existing = connection.execute(
                "SELECT 1 FROM candidate_diffs WHERE candidate_id = ?"
                " AND candidate_revision = ?",
                (candidate_id, candidate_revision),
            ).fetchone()
            if existing is not None:
                raise V2DatabaseError(
                    "a candidate diff revision is already recorded"
                )
            connection.execute(
                "INSERT INTO candidate_diffs"
                " (diff_id, run_id, candidate_id, candidate_revision, artifact_id)"
                " VALUES (?, ?, ?, ?, ?)",
                (identifier, run_id, candidate_id, candidate_revision, artifact_id),
            )
        return identifier

    def get_candidate_diff(
        self, candidate_id: str, candidate_revision: int
    ) -> CandidateDiffRecordV2 | None:
        candidate_revision = _require_revision(candidate_revision)
        row = self._connection.execute(
            "SELECT diff_id, candidate_id, candidate_revision, artifact_id"
            " FROM candidate_diffs WHERE candidate_id = ?"
            " AND candidate_revision = ?",
            (candidate_id, candidate_revision),
        ).fetchone()
        if row is None:
            return None
        return CandidateDiffRecordV2(
            diff_id=str(row[0]),
            candidate_id=str(row[1]),
            candidate_revision=int(row[2]),
            artifact_id=str(row[3]),
        )

    def create_validation_run(
        self,
        *,
        run_id: str,
        candidate_id: str,
        candidate_revision: int,
        reference_profile_id: str,
        reference_profile_revision: int,
        validation_run_id: str | None = None,
    ) -> str:
        """Create one PENDING validation run for a current candidate.

        Fail-closed order: the candidate must belong to the same run, the
        candidate revision must be current (a stale revision would
        validate an out-of-date state), and the referenced profile
        revision must exist.  The row is keyed by all five control-plane
        facts plus its own opaque ``validation_run_id``.
        """

        candidate_revision = _require_revision(candidate_revision)
        reference_profile_revision = _require_revision(reference_profile_revision)
        identifier = validation_run_id or new_validation_run_id()
        with self.transaction() as connection:
            candidate = connection.execute(
                "SELECT run_id, revision FROM candidates WHERE candidate_id = ?",
                (candidate_id,),
            ).fetchone()
            if candidate is None or str(candidate[0]) != run_id:
                raise V2DatabaseError("validation run/candidate mismatch")
            if int(candidate[1]) != candidate_revision:
                raise V2DatabaseError("candidate revision is stale")
            profile = connection.execute(
                "SELECT 1 FROM reference_profiles WHERE reference_profile_id = ?"
                " AND profile_revision = ?",
                (reference_profile_id, reference_profile_revision),
            ).fetchone()
            if profile is None:
                raise V2DatabaseError(
                    "reference profile revision is unknown"
                )
            connection.execute(
                "INSERT INTO validation_runs"
                " (validation_run_id, run_id, candidate_id, candidate_revision,"
                " reference_profile_id, reference_profile_revision, status, error)"
                " VALUES (?, ?, ?, ?, ?, ?, 'PENDING', NULL)",
                (
                    identifier,
                    run_id,
                    candidate_id,
                    candidate_revision,
                    reference_profile_id,
                    reference_profile_revision,
                ),
            )
        return identifier

    def get_validation_run(self, validation_run_id: str) -> ValidationRunRecordV2 | None:
        """Load one validation run record, revalidating its shape.

        The bounded status, error shape, and non-negative revisions are
        checked again at read time, so a corrupted row fails closed
        instead of surfacing as usable evidence.
        """

        row = self._connection.execute(
            "SELECT validation_run_id, run_id, candidate_id, candidate_revision,"
            " reference_profile_id, reference_profile_revision, status, error"
            " FROM validation_runs WHERE validation_run_id = ?",
            (validation_run_id,),
        ).fetchone()
        if row is None:
            return None
        return ValidationRunRecordV2(
            validation_run_id=str(row[0]),
            run_id=str(row[1]),
            candidate_id=str(row[2]),
            candidate_revision=int(row[3]),
            reference_profile_id=str(row[4]),
            reference_profile_revision=int(row[5]),
            status=str(row[6]),
            error=None if row[7] is None else str(row[7]),
        )

    def record_validation_result(
        self, validation_run_id: str, status: str, error: str | None = None
    ) -> bool:
        """Complete one PENDING validation run with a bounded outcome.

        Malformed outcomes (unknown status, an error on a PASSED run, a
        missing or oversized error on a FAILED run) reject before any
        mutation.  Completion is transactional and currency-checked:
        inside one SQLite transaction the run must still be ``PENDING``,
        the candidate must still belong to the validation run's run at
        the recorded revision, and the referenced reference profile
        revision must still exist and revalidate as a record — otherwise
        no terminal evidence is written: the call rejects fail-closed
        and the run stays ``PENDING``.  Completion is one-shot: a run
        that already carries a terminal status never records another
        outcome, and an unknown validation run returns False without
        touching anything.
        """

        if status not in ("PASSED", "FAILED"):
            raise V2DatabaseError(
                "validation result status must be 'PASSED' or 'FAILED'"
            )
        if status == "FAILED":
            if not isinstance(error, str) or not error:
                raise V2DatabaseError(
                    "FAILED validation results require a non-empty error message"
                )
            if len(error) > MAX_VALIDATION_ERROR_CHARS:
                raise V2DatabaseError(
                    "validation result error message exceeds the bounded length"
                )
        elif error is not None:
            raise V2DatabaseError(
                "only FAILED validation results carry an error message"
            )
        with self.transaction() as connection:
            run = connection.execute(
                "SELECT run_id, candidate_id, candidate_revision,"
                " reference_profile_id, reference_profile_revision, status"
                " FROM validation_runs WHERE validation_run_id = ?",
                (validation_run_id,),
            ).fetchone()
            if run is None:
                return False
            if str(run[5]) != "PENDING":
                return False
            # The candidate must still belong to the same run at the
            # recorded revision; a stale binding would make the terminal
            # record misleading evidence for a non-current state.
            candidate = connection.execute(
                "SELECT run_id, revision FROM candidates WHERE candidate_id = ?",
                (str(run[1]),),
            ).fetchone()
            if candidate is None or str(candidate[0]) != str(run[0]):
                raise V2DatabaseError(
                    "the validation candidate no longer belongs to the run"
                )
            if int(candidate[1]) != int(run[2]):
                raise V2DatabaseError("candidate revision is stale")
            # The referenced reference profile revision must still exist
            # and revalidate; profile revisions are immutable through the
            # API, so a missing or corrupted row means the terminal
            # record would cite configuration that can no longer be read.
            profile = connection.execute(
                "SELECT reference_profile_id, profile_revision, python_version,"
                " pytest_version, ruff_version, mypy_version"
                " FROM reference_profiles WHERE reference_profile_id = ?"
                " AND profile_revision = ?",
                (str(run[3]), int(run[4])),
            ).fetchone()
            if profile is None:
                raise V2DatabaseError("reference profile revision is missing")
            try:
                ReferenceProfileRecordV2(
                    reference_profile_id=str(profile[0]),
                    profile_revision=int(profile[1]),
                    python_version=str(profile[2]),
                    pytest_version=str(profile[3]),
                    ruff_version=str(profile[4]),
                    mypy_version=str(profile[5]),
                )
            except (TypeError, ValueError) as exc:
                raise V2DatabaseError(
                    "reference profile revision is corrupted"
                ) from exc
            cursor = connection.execute(
                "UPDATE validation_runs SET status = ?, error = ?,"
                " updated_at = CURRENT_TIMESTAMP WHERE validation_run_id = ?"
                " AND status = 'PENDING'",
                (status, error, validation_run_id),
            )
            return cursor.rowcount == 1

    # ------------------------------------------------------------------
    # Route B / B2: disclosure grants, per-request authorizations, and
    # provider endpoints.  All control-plane facts keyed by opaque IDs
    # and revisions; no digest is stored or consulted, and no
    # credential value ever enters these tables.
    # ------------------------------------------------------------------

    def _endpoint_record(
        self, connection: sqlite3.Connection, endpoint_id: str
    ) -> ProviderEndpointRecordV2 | None:
        row = connection.execute(
            "SELECT endpoint_id, provider, reference_profile_id,"
            " reference_profile_revision FROM provider_endpoints"
            " WHERE endpoint_id = ?",
            (endpoint_id,),
        ).fetchone()
        if row is None:
            return None
        return ProviderEndpointRecordV2(
            endpoint_id=str(row[0]),
            provider=str(row[1]),
            reference_profile_id=str(row[2]),
            reference_profile_revision=int(row[3]),
        )

    def create_provider_endpoint(self, record: ProviderEndpointRecordV2) -> None:
        """Store one declared provider endpoint, immutable per endpoint id.

        Re-declaring an existing endpoint id rejects instead of
        silently rebinding it to a different provider or profile — a
        changed endpoint is a new endpoint id.
        """

        if not isinstance(record, ProviderEndpointRecordV2):
            raise V2DatabaseError("record must be a ProviderEndpointRecordV2")
        with self.transaction() as connection:
            existing = connection.execute(
                "SELECT 1 FROM provider_endpoints WHERE endpoint_id = ?",
                (record.endpoint_id,),
            ).fetchone()
            if existing is not None:
                raise V2DatabaseError("provider endpoint already exists")
            connection.execute(
                "INSERT INTO provider_endpoints"
                " (endpoint_id, provider, reference_profile_id,"
                " reference_profile_revision) VALUES (?, ?, ?, ?)",
                (
                    record.endpoint_id,
                    record.provider,
                    record.reference_profile_id,
                    record.reference_profile_revision,
                ),
            )

    def get_provider_endpoint(
        self, endpoint_id: str
    ) -> ProviderEndpointRecordV2 | None:
        """Load one provider endpoint record, revalidating its shape."""

        return self._endpoint_record(self._connection, endpoint_id)

    def _grant_record(
        self, connection: sqlite3.Connection, grant_id: str
    ) -> DisclosureGrantRecordV2 | None:
        """Project a grant row (and its category/scope children) into its
        record, revalidating every field so a corrupted or
        foreign-written row fails closed at read time."""

        row = connection.execute(
            "SELECT grant_id, disclosure_id, run_id, reference_profile_id,"
            " reference_profile_revision, expires_at, byte_budget,"
            " consumed_bytes, status FROM disclosure_grants WHERE grant_id = ?",
            (grant_id,),
        ).fetchone()
        if row is None:
            return None
        categories = tuple(
            str(child[0])
            for child in connection.execute(
                "SELECT category FROM disclosure_grant_categories"
                " WHERE grant_id = ? ORDER BY position",
                (grant_id,),
            )
        )
        scopes = tuple(
            DisclosurePathScopeV2(str(child[0]), str(child[1]))
            for child in connection.execute(
                "SELECT scope_kind, scope_path FROM disclosure_grant_scopes"
                " WHERE grant_id = ? ORDER BY position",
                (grant_id,),
            )
        )
        return DisclosureGrantRecordV2(
            grant_id=str(row[0]),
            disclosure_id=str(row[1]),
            run_id=str(row[2]),
            reference_profile_id=str(row[3]),
            reference_profile_revision=int(row[4]),
            expires_at=str(row[5]),
            byte_budget=int(row[6]),
            consumed_bytes=int(row[7]),
            allowed_source_categories=categories,
            allowed_source_paths=scopes,
            status=str(row[8]),
        )

    def create_disclosure_grant(
        self,
        *,
        run_id: str,
        disclosure_id: str,
        reference_profile_id: str,
        reference_profile_revision: int,
        expires_at: str,
        byte_budget: int,
        allowed_source_categories: Sequence[str],
        allowed_source_paths: Sequence[DisclosurePathScopeV2],
        grant_id: str | None = None,
    ) -> str:
        """Create one PENDING grant bound to an approved disclosure subject.

        Fail-closed order: the record shape validates first (opaque
        ids, non-negative revision, ISO-8601 expiry, bounded budget,
        canonical categories/scopes); the disclosure must exist and
        belong to the same run; the referenced reference profile
        revision must exist; and one grant exists per disclosure
        subject.  The grant starts ``PENDING`` — explicit user approval
        (``activate_disclosure_grant``) is required before it
        authorizes anything.
        """

        identifier = grant_id or new_grant_id()
        try:
            record = DisclosureGrantRecordV2(
                grant_id=identifier,
                disclosure_id=disclosure_id,
                run_id=run_id,
                reference_profile_id=reference_profile_id,
                reference_profile_revision=reference_profile_revision,
                expires_at=expires_at,
                byte_budget=byte_budget,
                consumed_bytes=0,
                allowed_source_categories=tuple(allowed_source_categories),
                allowed_source_paths=tuple(allowed_source_paths),
                status="PENDING",
            )
        except (TypeError, ValueError) as exc:
            raise V2DatabaseError(
                f"disclosure grant record is invalid: {exc}"
            ) from exc
        with self.transaction() as connection:
            disclosure = connection.execute(
                "SELECT run_id FROM disclosures WHERE disclosure_id = ?",
                (record.disclosure_id,),
            ).fetchone()
            if disclosure is None or str(disclosure[0]) != record.run_id:
                raise V2DatabaseError("disclosure grant run/disclosure mismatch")
            profile = connection.execute(
                "SELECT 1 FROM reference_profiles WHERE reference_profile_id = ?"
                " AND profile_revision = ?",
                (
                    record.reference_profile_id,
                    record.reference_profile_revision,
                ),
            ).fetchone()
            if profile is None:
                raise V2DatabaseError("reference profile revision is unknown")
            existing = connection.execute(
                "SELECT 1 FROM disclosure_grants WHERE disclosure_id = ?",
                (record.disclosure_id,),
            ).fetchone()
            if existing is not None:
                raise V2DatabaseError(
                    "a disclosure grant already exists for this disclosure"
                )
            connection.execute(
                "INSERT INTO disclosure_grants"
                " (grant_id, disclosure_id, run_id, reference_profile_id,"
                " reference_profile_revision, expires_at, byte_budget,"
                " consumed_bytes, status)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, 0, 'PENDING')",
                (
                    record.grant_id,
                    record.disclosure_id,
                    record.run_id,
                    record.reference_profile_id,
                    record.reference_profile_revision,
                    record.expires_at,
                    record.byte_budget,
                ),
            )
            for position, category in enumerate(record.allowed_source_categories):
                connection.execute(
                    "INSERT INTO disclosure_grant_categories"
                    " (grant_id, position, category) VALUES (?, ?, ?)",
                    (record.grant_id, position, category),
                )
            for position, scope in enumerate(record.allowed_source_paths):
                connection.execute(
                    "INSERT INTO disclosure_grant_scopes"
                    " (grant_id, position, scope_kind, scope_path)"
                    " VALUES (?, ?, ?, ?)",
                    (record.grant_id, position, scope.kind, scope.path),
                )
        return record.grant_id

    def get_disclosure_grant(self, grant_id: str) -> DisclosureGrantRecordV2 | None:
        """Load one grant record, revalidating its shape at read time."""

        return self._grant_record(self._connection, grant_id)

    def get_disclosure_grant_by_disclosure(
        self, disclosure_id: str
    ) -> DisclosureGrantRecordV2 | None:
        """Load the (unique) grant created from one disclosure subject."""

        row = self._connection.execute(
            "SELECT grant_id FROM disclosure_grants WHERE disclosure_id = ?",
            (disclosure_id,),
        ).fetchone()
        if row is None:
            return None
        return self._grant_record(self._connection, str(row[0]))

    def activate_disclosure_grant(self, grant_id: str) -> bool:
        """Apply the explicit user approval: ``PENDING`` -> ``ACTIVE``."""

        with self.transaction() as connection:
            cursor = connection.execute(
                "UPDATE disclosure_grants SET status = 'ACTIVE',"
                " updated_at = CURRENT_TIMESTAMP WHERE grant_id = ?"
                " AND status = 'PENDING'",
                (grant_id,),
            )
            return cursor.rowcount == 1

    def revoke_disclosure_grant(self, grant_id: str) -> bool:
        """Revoke a ``PENDING`` or ``ACTIVE`` grant; revocation is terminal."""

        with self.transaction() as connection:
            cursor = connection.execute(
                "UPDATE disclosure_grants SET status = 'REVOKED',"
                " updated_at = CURRENT_TIMESTAMP WHERE grant_id = ?"
                " AND status IN ('PENDING','ACTIVE')",
                (grant_id,),
            )
            return cursor.rowcount == 1

    def list_disclosure_grants(
        self, limit: int = 100
    ) -> list[DisclosureGrantRecordV2]:
        """Project grant records (bounded, oldest first), fail closed.

        Route B / B3 read helper for the local integration surface: the
        limit is fail-closed (1..500) and every row revalidates through
        the same record projection the authorization path uses.
        """

        if isinstance(limit, bool) or not isinstance(limit, int):
            raise V2DatabaseError("grant list limit must be an integer")
        if not 1 <= limit <= 500:
            raise V2DatabaseError("grant list limit must be between 1 and 500")
        rows = list(
            self._connection.execute(
                "SELECT grant_id FROM disclosure_grants "
                "ORDER BY created_at, grant_id LIMIT ?",
                (limit,),
            ).fetchall()
        )
        records = []
        for row in rows:
            record = self._grant_record(self._connection, str(row[0]))
            if record is not None:
                records.append(record)
        return records

    def _authorization_record(
        self, connection: sqlite3.Connection, authorization_id: str
    ) -> DisclosureAuthorizationRecordV2 | None:
        """Project an authorization row and its sources into its record."""

        row = connection.execute(
            "SELECT authorization_id, grant_id, run_id, request_id,"
            " endpoint_id, charge_bytes, status FROM disclosure_authorizations"
            " WHERE authorization_id = ?",
            (authorization_id,),
        ).fetchone()
        if row is None:
            return None
        sources = tuple(
            DisclosureSourceV2(
                str(child[0]), None if child[1] is None else str(child[1])
            )
            for child in connection.execute(
                "SELECT category, source_path FROM"
                " disclosure_authorization_sources WHERE authorization_id = ?"
                " ORDER BY position",
                (authorization_id,),
            )
        )
        return DisclosureAuthorizationRecordV2(
            authorization_id=str(row[0]),
            grant_id=str(row[1]),
            run_id=str(row[2]),
            request_id=str(row[3]),
            endpoint_id=str(row[4]),
            charge_bytes=int(row[5]),
            status=str(row[6]),
            sources=sources,
        )

    def get_disclosure_authorization(
        self, authorization_id: str
    ) -> DisclosureAuthorizationRecordV2 | None:
        """Load one authorization record, revalidating its shape."""

        return self._authorization_record(self._connection, authorization_id)

    def authorize_disclosure_request(
        self,
        *,
        grant_id: str,
        run_id: str,
        request_id: str,
        endpoint_id: str,
        charge_bytes: int,
        sources: Sequence[DisclosureSourceV2],
        now: datetime | None = None,
        authorization_id: str | None = None,
    ) -> DisclosureAuthorizationOutcomeV2:
        """Charge one request against its grant, atomically or not at all.

        In one SQLite transaction the ledger revalidates every fact
        before any row is written: the grant must exist, belong to the
        request's run, be ``ACTIVE`` (``PENDING`` means the user has not
        approved it; ``REVOKED``/``EXPIRED``/``EXHAUSTED`` are terminal
        rejections), and be unexpired — a stale grant is flipped to
        ``EXPIRED`` and rejected in the same commit; the endpoint must
        exist and its reference profile id/revision must match the
        grant's binding; an existing authorization under the same
        ``(grant_id, request_id)`` is an exact-replay return (no second
        charge) or a replay conflict (changed payload, zero charge);
        the requested sources must fit the granted categories and path
        scopes; and the cumulative budget must cover the charge.  Only
        then are the authorization row, its source rows, and the grant's
        new consumed total (flipping to ``EXHAUSTED`` when the budget
        is fully consumed) written together.  Every rejection leaves
        zero charge and zero authorization rows.
        """

        if (
            isinstance(charge_bytes, bool)
            or not isinstance(charge_bytes, int)
            or not (
                MIN_DISCLOSURE_CHARGE_BYTES_V2
                <= charge_bytes
                <= MAX_DISCLOSURE_CHARGE_BYTES_V2
            )
        ):
            raise V2DatabaseError("charge_bytes is outside the bounded range")
        requested = canonicalize_disclosure_sources(sources)
        current = now if now is not None else datetime.now(timezone.utc)
        identifier = authorization_id or new_authorization_id()
        try:
            prepared = DisclosureAuthorizationRecordV2(
                authorization_id=identifier,
                grant_id=grant_id,
                run_id=run_id,
                request_id=request_id,
                endpoint_id=endpoint_id,
                charge_bytes=charge_bytes,
                status="AUTHORIZED",
                sources=requested,
            )
        except (TypeError, ValueError) as exc:
            raise V2DatabaseError(
                f"disclosure authorization record is invalid: {exc}"
            ) from exc

        def outcome(
            kind: str,
            authorization: DisclosureAuthorizationRecordV2 | None,
            consumed: int,
        ) -> DisclosureAuthorizationOutcomeV2:
            return DisclosureAuthorizationOutcomeV2(
                kind=kind,
                authorization=authorization,
                consumed_bytes=consumed,
                message=disclosure_outcome_message(kind),
            )

        with self.transaction() as connection:
            grant = self._grant_record(connection, grant_id)
            if grant is None:
                return outcome("GRANT_NOT_FOUND", None, 0)
            if grant.run_id != run_id:
                return outcome("RUN_MISMATCH", None, grant.consumed_bytes)
            if grant.status == "PENDING":
                return outcome("GRANT_PENDING", None, grant.consumed_bytes)
            if grant.status == "REVOKED":
                return outcome("GRANT_REVOKED", None, grant.consumed_bytes)
            if grant.status == "EXHAUSTED":
                return outcome("GRANT_EXHAUSTED", None, grant.consumed_bytes)
            if grant.status == "EXPIRED":
                return outcome("GRANT_EXPIRED", None, grant.consumed_bytes)
            if grant_is_expired(grant, current):
                connection.execute(
                    "UPDATE disclosure_grants SET status = 'EXPIRED',"
                    " updated_at = CURRENT_TIMESTAMP WHERE grant_id = ?"
                    " AND status = 'ACTIVE'",
                    (grant_id,),
                )
                return outcome("GRANT_EXPIRED", None, grant.consumed_bytes)
            endpoint = self._endpoint_record(connection, endpoint_id)
            if endpoint is None:
                return outcome("ENDPOINT_NOT_FOUND", None, grant.consumed_bytes)
            if (
                endpoint.reference_profile_id != grant.reference_profile_id
                or endpoint.reference_profile_revision
                != grant.reference_profile_revision
            ):
                return outcome(
                    "PROFILE_MISMATCH", None, grant.consumed_bytes
                )
            existing = connection.execute(
                "SELECT authorization_id FROM disclosure_authorizations"
                " WHERE grant_id = ? AND request_id = ?",
                (grant_id, request_id),
            ).fetchone()
            if existing is not None:
                previous = self._authorization_record(
                    connection, str(existing[0])
                )
                previous_key = authorization_payload_key(
                    previous.run_id,
                    previous.endpoint_id,
                    previous.charge_bytes,
                    previous.sources,
                )
                requested_key = authorization_payload_key(
                    run_id, endpoint_id, charge_bytes, requested
                )
                if previous_key == requested_key:
                    return outcome("REPLAY", previous, grant.consumed_bytes)
                return outcome(
                    "REPLAY_CONFLICT", None, grant.consumed_bytes
                )
            try:
                check_disclosure_request_sources(
                    grant.allowed_source_categories,
                    grant.allowed_source_paths,
                    requested,
                )
            except DisclosureScopeErrorV2:
                return outcome("SCOPE_EXCEEDED", None, grant.consumed_bytes)
            if grant.consumed_bytes + charge_bytes > grant.byte_budget:
                return outcome("BUDGET_EXCEEDED", None, grant.consumed_bytes)
            new_consumed = grant.consumed_bytes + charge_bytes
            connection.execute(
                "INSERT INTO disclosure_authorizations"
                " (authorization_id, grant_id, run_id, request_id,"
                " endpoint_id, charge_bytes, status)"
                " VALUES (?, ?, ?, ?, ?, ?, 'AUTHORIZED')",
                (
                    prepared.authorization_id,
                    grant_id,
                    run_id,
                    request_id,
                    endpoint_id,
                    charge_bytes,
                ),
            )
            for position, source in enumerate(requested):
                connection.execute(
                    "INSERT INTO disclosure_authorization_sources"
                    " (authorization_id, position, category, source_path)"
                    " VALUES (?, ?, ?, ?)",
                    (
                        prepared.authorization_id,
                        position,
                        source.category,
                        source.path,
                    ),
                )
            connection.execute(
                "UPDATE disclosure_grants SET consumed_bytes = ?,"
                " status = CASE WHEN ? >= byte_budget THEN 'EXHAUSTED'"
                " ELSE status END, updated_at = CURRENT_TIMESTAMP"
                " WHERE grant_id = ?",
                (new_consumed, new_consumed, grant_id),
            )
            return outcome("AUTHORIZED", prepared, new_consumed)

    def consume_disclosure_authorization(
        self,
        *,
        authorization_id: str,
        grant_id: str,
        run_id: str,
        request_id: str,
        now: datetime | None = None,
    ) -> DisclosureConsumeOutcomeV2:
        """Consume one authorization one-shot, revalidating everything.

        Inside one SQLite transaction (the authoritative gate the
        provider call boundary relies on): load the authorization row
        and require the exact control binding (``authorization_id``,
        ``grant_id``, ``run_id``, ``request_id``) and the ``AUTHORIZED``
        status; load the grant and require it to still be ``ACTIVE``
        and unexpired as of ``now`` — the explicit, deterministic
        consume-time clock the caller injects, so a revocation or an
        expiry crossing between an earlier read and this consume rejects
        the consume; and re-verify the endpoint row still exists and
        its reference profile id/revision still match the grant's
        binding (tamper evidence — those rows are immutable through
        every API path).  Only then does the one-shot ``AUTHORIZED`` ->
        ``CONSUMED`` update commit.  A lost race or a state change
        returns a closed outcome kind and consumes nothing; corrupted
        or missing control rows reject with ``V2DatabaseError`` and the
        transaction rolls back.
        """

        current = now if now is not None else datetime.now(timezone.utc)

        def consume_outcome(kind: str) -> DisclosureConsumeOutcomeV2:
            return DisclosureConsumeOutcomeV2(
                kind=kind,
                message=disclosure_consume_outcome_message(kind),
            )

        with self.transaction() as connection:
            row = connection.execute(
                "SELECT grant_id, run_id, request_id, endpoint_id, status"
                " FROM disclosure_authorizations WHERE authorization_id = ?",
                (authorization_id,),
            ).fetchone()
            if row is None:
                return consume_outcome("NOT_AUTHORIZED")
            if (
                str(row[0]) != grant_id
                or str(row[1]) != run_id
                or str(row[2]) != request_id
                or str(row[4]) != "AUTHORIZED"
            ):
                return consume_outcome("NOT_AUTHORIZED")
            grant = self._grant_record(connection, grant_id)
            if grant is None:
                raise V2DatabaseError(
                    "the authorization's grant is missing"
                )
            if grant.status != "ACTIVE" or grant_is_expired(grant, current):
                return consume_outcome("GRANT_NOT_ACTIVE")
            endpoint = self._endpoint_record(connection, str(row[3]))
            if endpoint is None:
                raise V2DatabaseError(
                    "the authorization's provider endpoint is missing"
                )
            if (
                endpoint.reference_profile_id != grant.reference_profile_id
                or endpoint.reference_profile_revision
                != grant.reference_profile_revision
            ):
                raise V2DatabaseError(
                    "the endpoint profile binding no longer matches the grant"
                )
            cursor = connection.execute(
                "UPDATE disclosure_authorizations SET status = 'CONSUMED',"
                " consumed_at = CURRENT_TIMESTAMP WHERE authorization_id = ?"
                " AND status = 'AUTHORIZED'",
                (authorization_id,),
            )
            if cursor.rowcount != 1:
                return consume_outcome("NOT_AUTHORIZED")
            return consume_outcome("CONSUMED")

    def close(self) -> None:
        self._connection.close()


def _connect_v2_database(path: Path) -> V2Database:
    if not isinstance(path, Path):
        raise V2DatabaseError("v2 database path must be a Path")
    connection = sqlite3.connect(str(path), isolation_level=None)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA busy_timeout = 5000")
    return V2Database(connection)


def open_v2_database(path: Path) -> V2Database:
    database = _connect_v2_database(path)
    connection = database._connection
    if path.exists():
        tables = {
            str(row[0])
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
        if "schema_migrations" in tables:
            database.close()
            raise V2DatabaseError("v1 database is read-only")
        if tables and "v2_schema_meta" not in tables:
            database.close()
            raise V2DatabaseError("v2 database metadata is missing")
        if "v2_schema_meta" in tables:
            if tables != _V2_TABLES:
                database.close()
                raise V2DatabaseError("v2 database schema is incomplete")
            marker = [tuple(row) for row in connection.execute(
                "SELECT version, name FROM v2_schema_meta"
            ).fetchall()]
            if marker != [(V2_SCHEMA_VERSION, "relaxed_identity_v2")]:
                database.close()
                raise V2DatabaseError("v2 database metadata is invalid")
            for table, columns in _V2_REQUIRED_COLUMNS.items():
                actual = {
                    str(row[1])
                    for row in connection.execute(f"PRAGMA table_info({table})")
                }
                if not columns <= actual:
                    database.close()
                    raise V2DatabaseError(f"v2 table {table} is incomplete")
        else:
            database.close()
            if tables:
                raise V2DatabaseError("v2 database metadata is missing")
            raise V2DatabaseError("v2 database is not initialized")
    return database


def initialize_v2_database(path: Path) -> None:
    """Create a fresh v2 schema without reading or rewriting a v1 database."""

    if not isinstance(path, Path):
        raise V2DatabaseError("v2 database path must be a Path")
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.is_dir():
        raise V2DatabaseError("v2 database path must not be a directory")
    if path.exists():
        raw = sqlite3.connect(str(path))
        try:
            tables = {
                str(row[0])
                for row in raw.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table'"
                )
            }
        finally:
            raw.close()
        if tables:
            validated = open_v2_database(path)
            validated.close()
            return
    database = _connect_v2_database(path)
    try:
        with database.transaction() as connection:
            existing_tables = {
                str(row[0])
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table'"
                )
            }
            if "schema_migrations" in existing_tables:
                raise V2DatabaseError(
                    "v1 database is read-only; choose a new v2 database path"
                )
            for statement in _DDL:
                connection.execute(statement)
            version_row = connection.execute(
                "SELECT version FROM v2_schema_meta ORDER BY version DESC LIMIT 1"
            ).fetchone()
            if version_row is not None and int(version_row[0]) != V2_SCHEMA_VERSION:
                raise V2DatabaseError("v2 database schema version mismatch")
            connection.execute(
                "INSERT OR IGNORE INTO v2_schema_meta (version, name) VALUES (?, ?)",
                (V2_SCHEMA_VERSION, "relaxed_identity_v2"),
            )
    finally:
        database.close()


def default_v2_database_path(control_root: Path) -> Path:
    """Return the explicit v2 database path for a control-data directory."""

    if not isinstance(control_root, Path):
        raise TypeError("v2 control root must be a Path")
    return control_root / V2_DATABASE_FILENAME


__all__ = [
    "V2_DATABASE_FILENAME",
    "V2DatabaseError",
    "V2_SCHEMA_VERSION",
    "V2Database",
    "default_v2_database_path",
    "initialize_v2_database",
    "open_v2_database",
]

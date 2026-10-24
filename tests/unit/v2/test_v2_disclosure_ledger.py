"""Route B / B2: the durable v2 disclosure ledger in the v3 schema.

The v1 disclosure ledger (``governance/disclosure_ledger.py``) charges
requests against digest-bound grants in the legacy twelve-migration
database.  This slice adds the v2 ledger to the existing v3 schema only:
six new tables (``disclosure_grants`` and its category/scope children,
``disclosure_authorizations`` and its source children, and
``provider_endpoints``) with strict column validation on open and
initialize, no migration of any v1 row, and fail-closed authorization:
the grant must be explicitly user-approved (``PENDING`` -> ``ACTIVE``),
unexpired, unrevoked, and under budget; the endpoint's reference profile
binding must match the grant's; sources must fit the granted categories
and path scopes; and the cumulative byte budget check, the replay check,
and the authorization insert commit atomically in one transaction.  The
Route A/B1 tables and their tests are untouched.
"""

from __future__ import annotations

import sqlite3
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from vespercode.governance.v2_disclosure import (
    DisclosurePathScopeV2,
    DisclosureSourceV2,
)
from vespercode.profiles.v2_endpoints import ProviderEndpointRecordV2
from vespercode.profiles.v2_reference import ReferenceProfileRecordV2
from vespercode.storage.v2_database import (
    V2_DATABASE_FILENAME,
    V2DatabaseError,
    V2_SCHEMA_VERSION,
    initialize_v2_database,
    open_v2_database,
)

_FUTURE = "2030-01-01T00:00:00+00:00"


class V2DisclosureLedgerTests(unittest.TestCase):
    def setUp(self) -> None:
        self._directory = tempfile.TemporaryDirectory()
        self.root = Path(self._directory.name)
        self.database_path = self.root / V2_DATABASE_FILENAME
        initialize_v2_database(self.database_path)
        self.database = open_v2_database(self.database_path)
        self._profile(revision=3)

    def tearDown(self) -> None:
        self.database.close()
        self._directory.cleanup()

    # ------------------------------------------------------------------
    # Fixture helpers
    # ------------------------------------------------------------------

    def _profile(self, *, revision: int = 3, profile_id: str = "profile-1") -> None:
        self.database.create_reference_profile(
            ReferenceProfileRecordV2(
                profile_id, revision, "3.12.4", "8.4.2", "0.16.1", "2.3.0"
            )
        )

    def _grant(
        self,
        *,
        budget: int = 1000,
        categories: tuple[str, ...] = ("FILE_CONTENT", "TASK"),
        scopes: tuple[DisclosurePathScopeV2, ...] | None = None,
        expires_at: str = _FUTURE,
        profile_id: str = "profile-1",
        profile_revision: int = 3,
        approve: bool = True,
    ) -> tuple[str, str, str]:
        run_id = self.database.create_run(str(self.root))
        disclosure_id = self.database.create_disclosure(run_id)
        grant_id = self.database.create_disclosure_grant(
            run_id=run_id,
            disclosure_id=disclosure_id,
            reference_profile_id=profile_id,
            reference_profile_revision=profile_revision,
            expires_at=expires_at,
            byte_budget=budget,
            allowed_source_categories=categories,
            allowed_source_paths=scopes
            if scopes is not None
            else (DisclosurePathScopeV2("FILE", "src/app.py"),),
        )
        if approve:
            self.assertTrue(self.database.activate_disclosure_grant(grant_id))
        return run_id, disclosure_id, grant_id

    def _endpoint(
        self,
        *,
        endpoint_id: str = "endpoint-1",
        provider: str = "OPENAI",
        profile_id: str = "profile-1",
        profile_revision: int = 3,
    ) -> str:
        self.database.create_provider_endpoint(
            ProviderEndpointRecordV2(
                endpoint_id, provider, profile_id, profile_revision
            )
        )
        return endpoint_id

    def _sources(
        self, *pairs: tuple[str, str | None]
    ) -> tuple[DisclosureSourceV2, ...]:
        return tuple(DisclosureSourceV2(category, path) for category, path in pairs)

    def _authorize(
        self,
        grant_id: str,
        run_id: str,
        *,
        request_id: str = "request-1",
        charge: int = 10,
        sources: tuple[DisclosureSourceV2, ...] | None = None,
        endpoint_id: str = "endpoint-1",
        now: datetime | None = None,
    ):
        if sources is None:
            sources = self._sources(("FILE_CONTENT", "src/app.py"))
        return self.database.authorize_disclosure_request(
            grant_id=grant_id,
            run_id=run_id,
            request_id=request_id,
            endpoint_id=endpoint_id,
            charge_bytes=charge,
            sources=sources,
            now=now,
        )

    # ------------------------------------------------------------------
    # Schema contract
    # ------------------------------------------------------------------

    def test_fresh_database_gains_the_b2_tables_in_the_v3_schema(self) -> None:
        self.assertEqual(V2_SCHEMA_VERSION, 3)
        tables = {
            str(row[0])
            for row in self.database._connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
        for table in (
            "disclosure_grants",
            "disclosure_grant_categories",
            "disclosure_grant_scopes",
            "disclosure_authorizations",
            "disclosure_authorization_sources",
            "provider_endpoints",
        ):
            self.assertIn(table, tables)

    def test_malformed_b2_tables_are_rejected_on_open_and_initialize(self) -> None:
        malformed = (
            (
                "disclosure_grants",
                "CREATE TABLE disclosure_grants ("
                " grant_id TEXT PRIMARY KEY, disclosure_id TEXT NOT NULL,"
                " run_id TEXT NOT NULL, reference_profile_id TEXT NOT NULL,"
                " reference_profile_revision INTEGER NOT NULL,"
                " expires_at TEXT NOT NULL, byte_budget INTEGER NOT NULL,"
                " consumed_bytes INTEGER NOT NULL DEFAULT 0,"
                " created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)",
            ),
            (
                "disclosure_grant_categories",
                "CREATE TABLE disclosure_grant_categories ("
                " grant_id TEXT NOT NULL, position INTEGER NOT NULL)",
            ),
            (
                "disclosure_grant_scopes",
                "CREATE TABLE disclosure_grant_scopes ("
                " grant_id TEXT NOT NULL, position INTEGER NOT NULL,"
                " scope_kind TEXT NOT NULL)",
            ),
            (
                "disclosure_authorizations",
                "CREATE TABLE disclosure_authorizations ("
                " authorization_id TEXT PRIMARY KEY, grant_id TEXT NOT NULL,"
                " run_id TEXT NOT NULL, request_id TEXT NOT NULL,"
                " charge_bytes INTEGER NOT NULL,"
                " created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)",
            ),
            (
                "disclosure_authorization_sources",
                "CREATE TABLE disclosure_authorization_sources ("
                " authorization_id TEXT NOT NULL, position INTEGER NOT NULL,"
                " category TEXT NOT NULL)",
            ),
            (
                "provider_endpoints",
                "CREATE TABLE provider_endpoints ("
                " endpoint_id TEXT PRIMARY KEY, provider TEXT NOT NULL,"
                " reference_profile_id TEXT NOT NULL)",
            ),
        )
        for table, malformed_sql in malformed:
            with self.subTest(table=table):
                directory = tempfile.TemporaryDirectory()
                try:
                    path = Path(directory.name) / V2_DATABASE_FILENAME
                    initialize_v2_database(path)
                    raw = sqlite3.connect(path)
                    try:
                        raw.execute("PRAGMA foreign_keys = OFF")
                        raw.execute(f"DROP TABLE {table}")
                        raw.execute(malformed_sql)
                        raw.commit()
                    finally:
                        raw.close()
                    with self.assertRaisesRegex(V2DatabaseError, table):
                        open_v2_database(path)
                    with self.assertRaisesRegex(V2DatabaseError, table):
                        initialize_v2_database(path)
                finally:
                    directory.cleanup()

    def test_no_v1_rows_are_migrated_by_the_b2_schema(self) -> None:
        # A v1 database (schema_migrations table) still refuses to open as v2.
        legacy_path = self.root / "legacy.sqlite"
        raw = sqlite3.connect(legacy_path)
        try:
            raw.execute("CREATE TABLE schema_migrations (version INTEGER)")
            raw.commit()
        finally:
            raw.close()
        with self.assertRaisesRegex(V2DatabaseError, "read-only"):
            open_v2_database(legacy_path)

    # ------------------------------------------------------------------
    # Grant lifecycle
    # ------------------------------------------------------------------

    def test_grant_creation_binds_the_disclosure_run_and_profile(self) -> None:
        run_id = self.database.create_run(str(self.root))
        disclosure_id = self.database.create_disclosure(run_id)
        other_run = self.database.create_run(str(self.root))
        with self.assertRaisesRegex(V2DatabaseError, "disclosure"):
            self.database.create_disclosure_grant(
                run_id=other_run,
                disclosure_id=disclosure_id,
                reference_profile_id="profile-1",
                reference_profile_revision=3,
                expires_at=_FUTURE,
                byte_budget=100,
                allowed_source_categories=("TASK",),
                allowed_source_paths=(DisclosurePathScopeV2("ROOT", ""),),
            )
        with self.assertRaisesRegex(V2DatabaseError, "profile"):
            self.database.create_disclosure_grant(
                run_id=run_id,
                disclosure_id=disclosure_id,
                reference_profile_id="profile-1",
                reference_profile_revision=99,
                expires_at=_FUTURE,
                byte_budget=100,
                allowed_source_categories=("TASK",),
                allowed_source_paths=(DisclosurePathScopeV2("ROOT", ""),),
            )

    def test_grants_start_pending_and_activate_exactly_once(self) -> None:
        run_id, disclosure_id, grant_id = self._grant(approve=False)
        grant = self.database.get_disclosure_grant(grant_id)
        self.assertEqual(grant.status, "PENDING")
        self.assertEqual(grant.consumed_bytes, 0)
        self.assertTrue(self.database.activate_disclosure_grant(grant_id))
        self.assertEqual(self.database.get_disclosure_grant(grant_id).status, "ACTIVE")
        # A second approval is a rejected transition.
        self.assertFalse(self.database.activate_disclosure_grant(grant_id))
        self.assertEqual(
            self.database.get_disclosure_grant_by_disclosure(disclosure_id).grant_id,
            grant_id,
        )

    def test_revocation_is_terminal_from_pending_or_active(self) -> None:
        run_id, _, grant_id = self._grant(approve=False)
        self.assertTrue(self.database.revoke_disclosure_grant(grant_id))
        self.assertEqual(self.database.get_disclosure_grant(grant_id).status, "REVOKED")
        self.assertFalse(self.database.revoke_disclosure_grant(grant_id))
        run_id, _, grant_id = self._grant(approve=True)
        self.assertTrue(self.database.revoke_disclosure_grant(grant_id))
        self.assertFalse(self.database.activate_disclosure_grant(grant_id))

    def test_one_grant_exists_per_disclosure_subject(self) -> None:
        run_id, disclosure_id, _ = self._grant()
        with self.assertRaisesRegex(V2DatabaseError, "disclosure"):
            self.database.create_disclosure_grant(
                run_id=run_id,
                disclosure_id=disclosure_id,
                reference_profile_id="profile-1",
                reference_profile_revision=3,
                expires_at=_FUTURE,
                byte_budget=100,
                allowed_source_categories=("TASK",),
                allowed_source_paths=(DisclosurePathScopeV2("ROOT", ""),),
            )

    def test_corrupted_grant_rows_fail_closed_on_read(self) -> None:
        _, _, grant_id = self._grant()
        # Corrupt an unchecked column: the read-path projection must
        # revalidate the record shape and fail closed.
        raw = self.database._connection
        raw.execute(
            "UPDATE disclosure_grants SET expires_at = 'never' WHERE grant_id = ?",
            (grant_id,),
        )
        with self.assertRaises(ValueError):
            self.database.get_disclosure_grant(grant_id)

    # ------------------------------------------------------------------
    # Authorization
    # ------------------------------------------------------------------

    def test_authorize_charges_an_active_grant_atomically(self) -> None:
        run_id, _, grant_id = self._grant(budget=1000)
        endpoint_id = self._endpoint()
        outcome = self._authorize(grant_id, run_id)
        self.assertEqual(outcome.kind, "AUTHORIZED")
        self.assertIsNotNone(outcome.authorization)
        self.assertEqual(outcome.authorization.grant_id, grant_id)
        self.assertEqual(outcome.authorization.run_id, run_id)
        self.assertEqual(outcome.authorization.request_id, "request-1")
        self.assertEqual(outcome.authorization.endpoint_id, endpoint_id)
        self.assertEqual(outcome.authorization.charge_bytes, 10)
        self.assertEqual(outcome.authorization.status, "AUTHORIZED")
        self.assertEqual(outcome.consumed_bytes, 10)
        grant = self.database.get_disclosure_grant(grant_id)
        self.assertEqual(grant.consumed_bytes, 10)
        self.assertEqual(grant.status, "ACTIVE")
        stored = self.database.get_disclosure_authorization(
            outcome.authorization.authorization_id
        )
        self.assertEqual(stored, outcome.authorization)

    def test_authorize_requires_explicit_user_approval(self) -> None:
        run_id, _, grant_id = self._grant(approve=False)
        self._endpoint()
        outcome = self._authorize(grant_id, run_id)
        self.assertEqual(outcome.kind, "GRANT_PENDING")
        self.assertIsNone(outcome.authorization)
        self.assertEqual(outcome.consumed_bytes, 0)
        self.assertEqual(self.database.get_disclosure_grant(grant_id).consumed_bytes, 0)

    def test_authorize_rejects_revoked_and_unknown_grants_with_zero_charge(
        self,
    ) -> None:
        run_id, _, grant_id = self._grant()
        self._endpoint()
        self.assertTrue(self.database.revoke_disclosure_grant(grant_id))
        outcome = self._authorize(grant_id, run_id)
        self.assertEqual(outcome.kind, "GRANT_REVOKED")
        self.assertIsNone(outcome.authorization)
        self.assertEqual(outcome.consumed_bytes, 0)
        unknown = self._authorize("grant-missing", run_id)
        self.assertEqual(unknown.kind, "GRANT_NOT_FOUND")
        self.assertIsNone(unknown.authorization)
        self.assertEqual(unknown.consumed_bytes, 0)

    def test_authorize_expires_a_stale_grant_lazily_and_keeps_it_rejected(
        self,
    ) -> None:
        run_id, _, grant_id = self._grant(expires_at="2020-01-01T00:00:00+00:00")
        self._endpoint()
        outcome = self._authorize(
            grant_id, run_id, now=datetime(2026, 10, 11, tzinfo=timezone.utc)
        )
        self.assertEqual(outcome.kind, "GRANT_EXPIRED")
        self.assertIsNone(outcome.authorization)
        self.assertEqual(outcome.consumed_bytes, 0)
        grant = self.database.get_disclosure_grant(grant_id)
        self.assertEqual(grant.status, "EXPIRED")
        self.assertEqual(grant.consumed_bytes, 0)
        # A second attempt stays rejected without re-flipping anything.
        again = self._authorize(
            grant_id, run_id, now=datetime(2026, 10, 12, tzinfo=timezone.utc)
        )
        self.assertEqual(again.kind, "GRANT_EXPIRED")

    def test_authorize_rejects_cross_run_requests(self) -> None:
        run_id, _, grant_id = self._grant()
        self._endpoint()
        other_run = self.database.create_run(str(self.root))
        outcome = self._authorize(grant_id, other_run)
        self.assertEqual(outcome.kind, "RUN_MISMATCH")
        self.assertIsNone(outcome.authorization)
        self.assertEqual(self.database.get_disclosure_grant(grant_id).consumed_bytes, 0)

    def test_authorize_requires_a_known_endpoint_and_matching_profile(self) -> None:
        run_id, _, grant_id = self._grant()
        self._endpoint()
        outcome = self._authorize(grant_id, run_id, endpoint_id="endpoint-missing")
        self.assertEqual(outcome.kind, "ENDPOINT_NOT_FOUND")
        self.assertIsNone(outcome.authorization)
        # The endpoint declares a different profile revision than the grant.
        self._endpoint(
            endpoint_id="endpoint-stale", profile_revision=2, profile_id="other"
        )
        stale = self._authorize(grant_id, run_id, endpoint_id="endpoint-stale")
        self.assertEqual(stale.kind, "PROFILE_MISMATCH")
        self.assertIsNone(stale.authorization)
        self.assertEqual(self.database.get_disclosure_grant(grant_id).consumed_bytes, 0)

    def test_authorize_enforces_the_source_category_and_path_scope(self) -> None:
        run_id, _, grant_id = self._grant()
        self._endpoint()
        for sources in (
            self._sources(("MEMORY", None)),
            self._sources(("FILE_CONTENT", "docs/app.py")),
            self._sources(("FILE_CONTENT", "src/app.py.bak")),
        ):
            with self.subTest(sources=sources):
                outcome = self._authorize(grant_id, run_id, sources=sources)
                self.assertEqual(outcome.kind, "SCOPE_EXCEEDED")
                self.assertIsNone(outcome.authorization)
                self.assertEqual(
                    self.database.get_disclosure_grant(grant_id).consumed_bytes, 0
                )
        # In-scope categories and paths authorize.
        ok = self._authorize(
            grant_id, run_id, sources=self._sources(("FILE_CONTENT", "src/app.py"))
        )
        self.assertEqual(ok.kind, "AUTHORIZED")
        # A directory scope admits the directory itself and descendants only.
        run_id, _, grant_id = self._grant(
            scopes=(DisclosurePathScopeV2("DIRECTORY", "src"),)
        )
        self.assertEqual(
            self._authorize(
                grant_id, run_id, sources=self._sources(("FILE_CONTENT", "src"))
            ).kind,
            "AUTHORIZED",
        )
        self.assertEqual(
            self._authorize(
                grant_id,
                run_id,
                request_id="request-2",
                sources=self._sources(("FILE_CONTENT", "src/lib/mod.py")),
            ).kind,
            "AUTHORIZED",
        )
        self.assertEqual(
            self._authorize(
                grant_id,
                run_id,
                request_id="request-3",
                sources=self._sources(("FILE_CONTENT", "src2/app.py")),
            ).kind,
            "SCOPE_EXCEEDED",
        )
        # A ROOT scope admits any path.
        run_id, _, grant_id = self._grant(scopes=(DisclosurePathScopeV2("ROOT", ""),))
        self.assertEqual(
            self._authorize(
                grant_id,
                run_id,
                sources=self._sources(("FILE_CONTENT", "any/where.py")),
            ).kind,
            "AUTHORIZED",
        )

    def test_authorize_enforces_the_cumulative_byte_budget_atomically(self) -> None:
        run_id, _, grant_id = self._grant(budget=100)
        self._endpoint()
        first = self._authorize(grant_id, run_id, charge=60)
        self.assertEqual(first.kind, "AUTHORIZED")
        self.assertEqual(first.consumed_bytes, 60)
        # A second large request loses the budget race: zero charge, no row.
        second = self._authorize(grant_id, run_id, request_id="request-2", charge=60)
        self.assertEqual(second.kind, "BUDGET_EXCEEDED")
        self.assertIsNone(second.authorization)
        self.assertEqual(second.consumed_bytes, 60)
        grant = self.database.get_disclosure_grant(grant_id)
        self.assertEqual(grant.consumed_bytes, 60)
        self.assertEqual(grant.status, "ACTIVE")
        # A fitting request still authorizes against the remainder.
        third = self._authorize(grant_id, run_id, request_id="request-3", charge=40)
        self.assertEqual(third.kind, "AUTHORIZED")
        self.assertEqual(third.consumed_bytes, 100)
        self.assertEqual(
            self.database.get_disclosure_grant(grant_id).status, "EXHAUSTED"
        )
        # The exhausted grant rejects further requests with zero charge.
        fourth = self._authorize(grant_id, run_id, request_id="request-4", charge=1)
        self.assertEqual(fourth.kind, "GRANT_EXHAUSTED")
        self.assertEqual(fourth.consumed_bytes, 100)
        self.assertEqual(
            self.database.get_disclosure_grant(grant_id).consumed_bytes, 100
        )

    def test_authorize_replays_an_exact_request_without_a_second_charge(self) -> None:
        run_id, _, grant_id = self._grant(budget=1000)
        self._endpoint()
        sources = self._sources(("FILE_CONTENT", "src/app.py"))
        first = self._authorize(grant_id, run_id, charge=25, sources=sources)
        replay = self._authorize(grant_id, run_id, charge=25, sources=sources)
        self.assertEqual(replay.kind, "REPLAY")
        self.assertEqual(replay.authorization, first.authorization)
        self.assertEqual(replay.consumed_bytes, 25)
        self.assertEqual(
            self.database.get_disclosure_grant(grant_id).consumed_bytes, 25
        )
        # A different payload under the same request id is a conflict.
        conflict = self._authorize(grant_id, run_id, charge=26, sources=sources)
        self.assertEqual(conflict.kind, "REPLAY_CONFLICT")
        self.assertIsNone(conflict.authorization)
        self.assertEqual(
            self.database.get_disclosure_grant(grant_id).consumed_bytes, 25
        )
        conflict = self._authorize(
            grant_id,
            run_id,
            charge=25,
            sources=self._sources(("FILE_CONTENT", "src/app.py"), ("TASK", None)),
        )
        self.assertEqual(conflict.kind, "REPLAY_CONFLICT")
        # A different request id legitimately charges again.
        other = self._authorize(grant_id, run_id, request_id="request-2", charge=25)
        self.assertEqual(other.kind, "AUTHORIZED")
        self.assertEqual(
            self.database.get_disclosure_grant(grant_id).consumed_bytes, 50
        )

    def test_consume_is_one_shot_and_bound_to_its_grant_run_and_request(self) -> None:
        run_id, _, grant_id = self._grant()
        self._endpoint()
        outcome = self._authorize(grant_id, run_id)
        authorization_id = outcome.authorization.authorization_id
        binding = {
            "authorization_id": authorization_id,
            "grant_id": grant_id,
            "run_id": run_id,
            "request_id": "request-1",
        }
        for overrides in (
            {"grant_id": "grant-wrong"},
            {"run_id": "run-wrong"},
            {"request_id": "request-wrong"},
        ):
            with self.subTest(overrides=overrides):
                consume = self.database.consume_disclosure_authorization(
                    **{**binding, **overrides}
                )
                self.assertEqual(consume.kind, "NOT_AUTHORIZED")
        unknown = self.database.consume_disclosure_authorization(
            authorization_id="auth-missing",
            grant_id=grant_id,
            run_id=run_id,
            request_id="request-1",
        )
        self.assertEqual(unknown.kind, "NOT_AUTHORIZED")
        consume = self.database.consume_disclosure_authorization(
            authorization_id=authorization_id,
            grant_id=grant_id,
            run_id=run_id,
            request_id="request-1",
        )
        self.assertEqual(consume.kind, "CONSUMED")
        self.assertEqual(
            self.database.get_disclosure_authorization(authorization_id).status,
            "CONSUMED",
        )
        # The second consume loses the one-shot CAS.
        again = self.database.consume_disclosure_authorization(
            authorization_id=authorization_id,
            grant_id=grant_id,
            run_id=run_id,
            request_id="request-1",
        )
        self.assertEqual(again.kind, "NOT_AUTHORIZED")
        # An already-consumed authorization no longer replays as chargeable.
        replay = self._authorize(grant_id, run_id)
        self.assertEqual(replay.kind, "REPLAY")
        self.assertEqual(replay.authorization.status, "CONSUMED")

    def test_consume_rejects_when_the_grant_was_revoked_after_the_read(self) -> None:
        run_id, _, grant_id = self._grant()
        self._endpoint()
        authorization_id = self._authorize(
            grant_id, run_id
        ).authorization.authorization_id
        # The grant is revoked between the caller's read and the consume.
        self.assertTrue(self.database.revoke_disclosure_grant(grant_id))
        consume = self.database.consume_disclosure_authorization(
            authorization_id=authorization_id,
            grant_id=grant_id,
            run_id=run_id,
            request_id="request-1",
        )
        self.assertEqual(consume.kind, "GRANT_NOT_ACTIVE")
        # The rejection consumes nothing: the authorization stays AUTHORIZED.
        self.assertEqual(
            self.database.get_disclosure_authorization(authorization_id).status,
            "AUTHORIZED",
        )

    def test_consume_rechecks_expiry_at_the_consume_time_clock(self) -> None:
        run_id, _, grant_id = self._grant(expires_at="2030-01-01T00:00:00+00:00")
        self._endpoint()
        authorized = self._authorize(
            grant_id, run_id, now=datetime(2029, 6, 1, tzinfo=timezone.utc)
        )
        self.assertEqual(authorized.kind, "AUTHORIZED")
        authorization_id = authorized.authorization.authorization_id
        # Time crosses the expiry between the authorization and the consume.
        consume = self.database.consume_disclosure_authorization(
            authorization_id=authorization_id,
            grant_id=grant_id,
            run_id=run_id,
            request_id="request-1",
            now=datetime(2031, 6, 1, tzinfo=timezone.utc),
        )
        self.assertEqual(consume.kind, "GRANT_NOT_ACTIVE")
        self.assertEqual(
            self.database.get_disclosure_authorization(authorization_id).status,
            "AUTHORIZED",
        )

    def test_consume_rejects_fail_closed_when_the_endpoint_row_was_tampered(
        self,
    ) -> None:
        run_id, _, grant_id = self._grant()
        self._endpoint()
        authorization_id = self._authorize(
            grant_id, run_id
        ).authorization.authorization_id
        connection = self.database._connection
        connection.execute("PRAGMA foreign_keys = OFF")
        connection.execute(
            "DELETE FROM provider_endpoints WHERE endpoint_id = 'endpoint-1'"
        )
        connection.execute("PRAGMA foreign_keys = ON")
        with self.assertRaisesRegex(V2DatabaseError, "endpoint"):
            self.database.consume_disclosure_authorization(
                authorization_id=authorization_id,
                grant_id=grant_id,
                run_id=run_id,
                request_id="request-1",
            )
        self.assertEqual(
            self.database.get_disclosure_authorization(authorization_id).status,
            "AUTHORIZED",
        )

    def test_consume_rejects_fail_closed_when_the_profile_binding_drifts(
        self,
    ) -> None:
        run_id, _, grant_id = self._grant()
        self._endpoint()
        authorization_id = self._authorize(
            grant_id, run_id
        ).authorization.authorization_id
        # The grant's profile binding is repointed by direct SQL (no API
        # path exists); the terminal consume must reject fail-closed.
        self.database._connection.execute(
            "UPDATE disclosure_grants SET reference_profile_id = 'other'"
            " WHERE grant_id = ?",
            (grant_id,),
        )
        with self.assertRaisesRegex(V2DatabaseError, "profile"):
            self.database.consume_disclosure_authorization(
                authorization_id=authorization_id,
                grant_id=grant_id,
                run_id=run_id,
                request_id="request-1",
            )
        self.assertEqual(
            self.database.get_disclosure_authorization(authorization_id).status,
            "AUTHORIZED",
        )

    def test_authorize_rejects_malformed_commands_before_any_charge(self) -> None:
        run_id, _, grant_id = self._grant()
        self._endpoint()
        with self.assertRaises(V2DatabaseError):
            self._authorize(grant_id, run_id, charge=0)
        with self.assertRaises(V2DatabaseError):
            self._authorize(grant_id, run_id, charge=65537)
        with self.assertRaises(ValueError):
            self._authorize(grant_id, run_id, sources=())
        self.assertEqual(self.database.get_disclosure_grant(grant_id).consumed_bytes, 0)

    # ------------------------------------------------------------------
    # Provider endpoints
    # ------------------------------------------------------------------

    def test_endpoint_records_round_trip_and_are_immutable(self) -> None:
        endpoint_id = self._endpoint()
        loaded = self.database.get_provider_endpoint(endpoint_id)
        self.assertEqual(
            loaded,
            ProviderEndpointRecordV2("endpoint-1", "OPENAI", "profile-1", 3),
        )
        self.assertIsNone(self.database.get_provider_endpoint("endpoint-missing"))
        with self.assertRaisesRegex(V2DatabaseError, "endpoint"):
            self.database.create_provider_endpoint(
                ProviderEndpointRecordV2("endpoint-1", "OPENAI", "profile-1", 3)
            )
        # A new endpoint id with a different profile is a distinct record.
        self._endpoint(endpoint_id="endpoint-2", profile_id="other", profile_revision=0)
        self.assertEqual(
            self.database.get_provider_endpoint("endpoint-2").reference_profile_id,
            "other",
        )


if __name__ == "__main__":
    unittest.main()

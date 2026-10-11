"""Route B / B2: v2 disclosure grant/authorization contracts and pure policy.

The v1 disclosure plane (``governance/disclosure_ledger.py``,
``governance/disclosure_scope.py``, ``governance/disclosure_decision.py``)
closes every authorization over SHA-256 request/subject digests.  Those
modules remain untouched read-only legacy; nothing here imports them.

The v2 disclosure control plane keys every record by opaque IDs and
non-negative revisions instead: a grant is keyed by ``grant_id`` and the
``disclosure_id`` of the user-approval subject it was created from, and
carries the run, the bound reference profile id/revision, an ISO-8601
expiry, a byte budget, the allowed source categories, and the allowed
path scopes; a per-request authorization is keyed by
``authorization_id`` plus the grant/run/request/endpoint references, its
requested sources, its byte charge, and a one-shot consumed state.  No
digest of any payload is computed, stored, or consulted.
"""

from __future__ import annotations

import unittest
from datetime import datetime, timezone

from vespercode.governance.v2_disclosure import (
    DISCLOSURE_AUTHORIZATION_OUTCOMES_V2,
    DISCLOSURE_AUTHORIZATION_STATUSES_V2,
    DISCLOSURE_GRANT_STATUSES_V2,
    DISCLOSURE_SOURCE_CATEGORIES_V2,
    MAX_DISCLOSURE_BUDGET_BYTES_V2,
    MAX_DISCLOSURE_CHARGE_BYTES_V2,
    MIN_DISCLOSURE_BUDGET_BYTES_V2,
    MIN_DISCLOSURE_CHARGE_BYTES_V2,
    DisclosureAuthorizationRecordV2,
    DisclosureGrantRecordV2,
    DisclosurePathScopeV2,
    DisclosureScopeErrorV2,
    DisclosureSourceV2,
    authorization_payload_key,
    canonicalize_disclosure_categories,
    canonicalize_disclosure_scopes,
    canonicalize_disclosure_sources,
    check_disclosure_request_sources,
    disclosure_authorization_from_mapping,
    disclosure_grant_from_mapping,
    disclosure_scope_matches,
    grant_is_expired,
)


def _grant(**overrides: object) -> DisclosureGrantRecordV2:
    values: dict[str, object] = {
        "grant_id": "grant-1",
        "disclosure_id": "disclosure-1",
        "run_id": "run-1",
        "reference_profile_id": "profile-1",
        "reference_profile_revision": 2,
        "expires_at": "2030-01-01T00:00:00+00:00",
        "byte_budget": 1000,
        "consumed_bytes": 0,
        "allowed_source_categories": ("FILE_CONTENT", "TASK"),
        "allowed_source_paths": (DisclosurePathScopeV2("FILE", "src/app.py"),),
        "status": "PENDING",
    }
    values.update(overrides)
    return DisclosureGrantRecordV2(**values)  # type: ignore[arg-type]


def _authorization(**overrides: object) -> DisclosureAuthorizationRecordV2:
    values: dict[str, object] = {
        "authorization_id": "auth-1",
        "grant_id": "grant-1",
        "run_id": "run-1",
        "request_id": "request-1",
        "endpoint_id": "endpoint-1",
        "charge_bytes": 16,
        "status": "AUTHORIZED",
        "sources": (DisclosureSourceV2("FILE_CONTENT", "src/app.py"),),
    }
    values.update(overrides)
    return DisclosureAuthorizationRecordV2(**values)  # type: ignore[arg-type]


class DisclosureVocabularyTests(unittest.TestCase):
    def test_the_status_and_outcome_vocabularies_are_the_closed_sets(self) -> None:
        self.assertEqual(
            DISCLOSURE_GRANT_STATUSES_V2,
            frozenset({"PENDING", "ACTIVE", "REVOKED", "EXPIRED", "EXHAUSTED"}),
        )
        self.assertEqual(
            DISCLOSURE_AUTHORIZATION_STATUSES_V2,
            frozenset({"AUTHORIZED", "CONSUMED"}),
        )
        self.assertEqual(
            DISCLOSURE_AUTHORIZATION_OUTCOMES_V2,
            frozenset(
                {
                    "AUTHORIZED",
                    "REPLAY",
                    "REPLAY_CONFLICT",
                    "GRANT_NOT_FOUND",
                    "GRANT_PENDING",
                    "GRANT_REVOKED",
                    "GRANT_EXPIRED",
                    "GRANT_EXHAUSTED",
                    "RUN_MISMATCH",
                    "ENDPOINT_NOT_FOUND",
                    "PROFILE_MISMATCH",
                    "SCOPE_EXCEEDED",
                    "BUDGET_EXCEEDED",
                }
            ),
        )

    def test_the_source_categories_match_the_v1_control_vocabulary(self) -> None:
        self.assertEqual(
            DISCLOSURE_SOURCE_CATEGORIES_V2,
            frozenset(
                {
                    "HARNESS_PROTOCOL",
                    "TASK",
                    "FILE_CONTENT",
                    "TOOL_RESULT",
                    "MEMORY",
                    "FEEDBACK",
                }
            ),
        )
        self.assertEqual(MIN_DISCLOSURE_CHARGE_BYTES_V2, 1)
        self.assertEqual(MAX_DISCLOSURE_CHARGE_BYTES_V2, 65536)
        self.assertEqual(MIN_DISCLOSURE_BUDGET_BYTES_V2, 1)
        self.assertGreater(MAX_DISCLOSURE_BUDGET_BYTES_V2, MAX_DISCLOSURE_CHARGE_BYTES_V2)


class DisclosureScopeTests(unittest.TestCase):
    def test_scope_value_objects_require_the_closed_kinds_and_canonical_paths(
        self,
    ) -> None:
        for kind in ("ROOT", "FILE", "DIRECTORY"):
            self.assertIn(kind, {"ROOT", "FILE", "DIRECTORY"})
        with self.assertRaises(ValueError):
            DisclosurePathScopeV2("BOGUS", "")
        # ROOT carries no path; FILE/DIRECTORY require a canonical one.
        with self.assertRaises(ValueError):
            DisclosurePathScopeV2("ROOT", "src/app.py")
        with self.assertRaises(ValueError):
            DisclosurePathScopeV2("FILE", "")
        for bad_path in (
            "/absolute.py",
            "src\\app.py",
            "src//app.py",
            "src/../app.py",
            "./app.py",
            "src/app.py/",
            "c:src/app.py",
            "src/app\x00.py",
        ):
            with self.subTest(bad_path=bad_path):
                with self.assertRaises(ValueError):
                    DisclosurePathScopeV2("FILE", bad_path)
                with self.assertRaises(ValueError):
                    DisclosurePathScopeV2("DIRECTORY", bad_path)

    def test_root_scope_matches_any_canonical_path(self) -> None:
        scopes = canonicalize_disclosure_scopes(
            [DisclosurePathScopeV2("ROOT", "")]
        )
        self.assertTrue(disclosure_scope_matches("any/path.py", scopes))

    def test_file_scope_matches_only_its_exact_path(self) -> None:
        scopes = canonicalize_disclosure_scopes(
            [DisclosurePathScopeV2("FILE", "src/app.py")]
        )
        self.assertTrue(disclosure_scope_matches("src/app.py", scopes))
        self.assertFalse(disclosure_scope_matches("src/app.py.bak", scopes))
        self.assertFalse(disclosure_scope_matches("src/app2.py", scopes))
        self.assertFalse(disclosure_scope_matches("docs/src/app.py", scopes))

    def test_directory_scope_matches_itself_and_true_descendants_only(self) -> None:
        scopes = canonicalize_disclosure_scopes(
            [DisclosurePathScopeV2("DIRECTORY", "src")]
        )
        self.assertTrue(disclosure_scope_matches("src", scopes))
        self.assertTrue(disclosure_scope_matches("src/lib/app.py", scopes))
        self.assertFalse(disclosure_scope_matches("src2/app.py", scopes))
        self.assertFalse(disclosure_scope_matches("sr", scopes))
        self.assertFalse(disclosure_scope_matches("docs/src", scopes))

    def test_scope_canonicalization_rejects_duplicates_and_mixed_root(self) -> None:
        with self.assertRaises(ValueError):
            canonicalize_disclosure_scopes(
                [
                    DisclosurePathScopeV2("FILE", "a.py"),
                    DisclosurePathScopeV2("FILE", "a.py"),
                ]
            )
        with self.assertRaises(ValueError):
            canonicalize_disclosure_scopes(
                [
                    DisclosurePathScopeV2("ROOT", ""),
                    DisclosurePathScopeV2("FILE", "a.py"),
                ]
            )
        with self.assertRaises(ValueError):
            canonicalize_disclosure_scopes([])

    def test_scope_canonicalization_orders_deterministically(self) -> None:
        scopes = canonicalize_disclosure_scopes(
            [
                DisclosurePathScopeV2("DIRECTORY", "z"),
                DisclosurePathScopeV2("FILE", "b.py"),
                DisclosurePathScopeV2("FILE", "a.py"),
                DisclosurePathScopeV2("DIRECTORY", "a"),
            ]
        )
        self.assertEqual(
            scopes,
            (
                DisclosurePathScopeV2("FILE", "a.py"),
                DisclosurePathScopeV2("FILE", "b.py"),
                DisclosurePathScopeV2("DIRECTORY", "a"),
                DisclosurePathScopeV2("DIRECTORY", "z"),
            ),
        )

    def test_category_canonicalization_rejects_unknown_and_empty(self) -> None:
        self.assertEqual(
            canonicalize_disclosure_categories(["TASK", "FILE_CONTENT"]),
            ("FILE_CONTENT", "TASK"),
        )
        with self.assertRaises(ValueError):
            canonicalize_disclosure_categories([])
        with self.assertRaises(ValueError):
            canonicalize_disclosure_categories(["TASK", "BOGUS"])
        with self.assertRaises(ValueError):
            canonicalize_disclosure_categories(["TASK", "TASK"])


class DisclosureGrantRecordTests(unittest.TestCase):
    def test_a_valid_grant_record_holds_every_control_key(self) -> None:
        grant = _grant(status="ACTIVE", consumed_bytes=40)
        self.assertEqual(grant.grant_id, "grant-1")
        self.assertEqual(grant.disclosure_id, "disclosure-1")
        self.assertEqual(grant.run_id, "run-1")
        self.assertEqual(grant.reference_profile_id, "profile-1")
        self.assertEqual(grant.reference_profile_revision, 2)
        self.assertEqual(grant.expires_at, "2030-01-01T00:00:00+00:00")
        self.assertEqual(grant.byte_budget, 1000)
        self.assertEqual(grant.consumed_bytes, 40)
        self.assertEqual(grant.allowed_source_categories, ("FILE_CONTENT", "TASK"))
        self.assertEqual(
            grant.allowed_source_paths,
            (DisclosurePathScopeV2("FILE", "src/app.py"),),
        )

    def test_grant_records_reject_out_of_vocabulary_shapes(self) -> None:
        for overrides in (
            {"status": "OPEN"},
            {"status": 1},
            {"byte_budget": MIN_DISCLOSURE_BUDGET_BYTES_V2 - 1},
            {"byte_budget": MAX_DISCLOSURE_BUDGET_BYTES_V2 + 1},
            {"consumed_bytes": -1},
            {"reference_profile_revision": -1},
            {"expires_at": "not-a-timestamp"},
            {"allowed_source_categories": ()},
            {"allowed_source_categories": ("BOGUS",)},
            {"allowed_source_paths": ()},
            {"grant_id": ""},
            {"grant_id": "x" * 300},
            {"disclosure_id": " "},
            {"run_id": 7},
        ):
            with self.subTest(overrides=overrides):
                with self.assertRaises(ValueError):
                    _grant(**overrides)

    def test_grant_from_mapping_parses_exact_fields_only(self) -> None:
        grant = _grant()
        data = {
            "grant_id": "grant-1",
            "disclosure_id": "disclosure-1",
            "run_id": "run-1",
            "reference_profile_id": "profile-1",
            "reference_profile_revision": 2,
            "expires_at": "2030-01-01T00:00:00+00:00",
            "byte_budget": 1000,
            "consumed_bytes": 0,
            "allowed_source_categories": ("FILE_CONTENT", "TASK"),
            "allowed_source_paths": (DisclosurePathScopeV2("FILE", "src/app.py"),),
            "status": "PENDING",
        }
        self.assertEqual(disclosure_grant_from_mapping(data), grant)

    def test_grant_from_mapping_rejects_v1_digest_shaped_payloads(self) -> None:
        v1_shaped = {
            "grant_id": "grant-1",
            "disclosure_id": "disclosure-1",
            "run_id": "run-1",
            "reference_profile_id": "profile-1",
            "reference_profile_revision": 2,
            "expires_at": "2030-01-01T00:00:00+00:00",
            "byte_budget": 1000,
            "consumed_bytes": 0,
            "allowed_source_categories": ("FILE_CONTENT",),
            "allowed_source_paths": (DisclosurePathScopeV2("ROOT", ""),),
            "status": "PENDING",
            "schema_version": 1,
            "subject_digest": "0" * 64,
        }
        with self.assertRaises(ValueError):
            disclosure_grant_from_mapping(v1_shaped)

    def test_grant_from_mapping_rejects_missing_fields(self) -> None:
        with self.assertRaises(ValueError):
            disclosure_grant_from_mapping({"grant_id": "grant-1"})
        with self.assertRaises(ValueError):
            disclosure_grant_from_mapping("not-a-mapping")  # type: ignore[arg-type]


class DisclosureAuthorizationRecordTests(unittest.TestCase):
    def test_source_shapes_follow_the_path_rules(self) -> None:
        self.assertEqual(
            canonicalize_disclosure_sources(
                [DisclosureSourceV2("FILE_CONTENT", "src/app.py")]
            ),
            (DisclosureSourceV2("FILE_CONTENT", "src/app.py"),),
        )
        self.assertEqual(
            canonicalize_disclosure_sources([DisclosureSourceV2("TASK", None)]),
            (DisclosureSourceV2("TASK", None),),
        )
        # FILE_CONTENT requires a path; other categories forbid one.
        with self.assertRaises(ValueError):
            DisclosureSourceV2("FILE_CONTENT", None)
        with self.assertRaises(ValueError):
            DisclosureSourceV2("TASK", "src/app.py")
        with self.assertRaises(ValueError):
            DisclosureSourceV2("BOGUS", None)
        with self.assertRaises(ValueError):
            DisclosureSourceV2("FILE_CONTENT", "/absolute.py")
        with self.assertRaises(ValueError):
            canonicalize_disclosure_sources([])

    def test_a_valid_authorization_record_holds_every_control_key(self) -> None:
        record = _authorization(status="CONSUMED")
        self.assertEqual(record.authorization_id, "auth-1")
        self.assertEqual(record.grant_id, "grant-1")
        self.assertEqual(record.run_id, "run-1")
        self.assertEqual(record.request_id, "request-1")
        self.assertEqual(record.endpoint_id, "endpoint-1")
        self.assertEqual(record.charge_bytes, 16)
        self.assertEqual(record.status, "CONSUMED")

    def test_authorization_records_reject_out_of_vocabulary_shapes(self) -> None:
        for overrides in (
            {"status": "PENDING"},
            {"charge_bytes": MIN_DISCLOSURE_CHARGE_BYTES_V2 - 1},
            {"charge_bytes": MAX_DISCLOSURE_CHARGE_BYTES_V2 + 1},
            {"sources": ()},
            {"request_id": ""},
            {"endpoint_id": ""},
            {"grant_id": None},
        ):
            with self.subTest(overrides=overrides):
                with self.assertRaises(ValueError):
                    _authorization(**overrides)

    def test_authorization_from_mapping_parses_exact_fields_only(self) -> None:
        record = _authorization()
        data = {
            "authorization_id": "auth-1",
            "grant_id": "grant-1",
            "run_id": "run-1",
            "request_id": "request-1",
            "endpoint_id": "endpoint-1",
            "charge_bytes": 16,
            "status": "AUTHORIZED",
            "sources": (DisclosureSourceV2("FILE_CONTENT", "src/app.py"),),
        }
        self.assertEqual(disclosure_authorization_from_mapping(data), record)

    def test_authorization_from_mapping_rejects_v1_digest_shaped_payloads(self) -> None:
        v1_shaped = {
            "authorization_id": "auth-1",
            "grant_id": "grant-1",
            "run_id": "run-1",
            "request_id": "request-1",
            "endpoint_id": "endpoint-1",
            "charge_bytes": 16,
            "status": "AUTHORIZED",
            "sources": (DisclosureSourceV2("FILE_CONTENT", "src/app.py"),),
            "request_digest": "f" * 64,
        }
        with self.assertRaises(ValueError):
            disclosure_authorization_from_mapping(v1_shaped)


class DisclosurePolicyTests(unittest.TestCase):
    def test_grant_expiry_is_a_pure_timestamp_comparison(self) -> None:
        grant = _grant(expires_at="2030-01-01T00:00:00+00:00")
        self.assertTrue(
            grant_is_expired(grant, datetime(2030, 1, 1, 0, 0, 1, tzinfo=timezone.utc))
        )
        self.assertFalse(
            grant_is_expired(grant, datetime(2029, 12, 31, 23, 59, 59, tzinfo=timezone.utc))
        )
        # Naive timestamps are read as UTC; the Z spelling parses too.
        self.assertFalse(grant_is_expired(grant, datetime(2029, 6, 1)))
        self.assertTrue(grant_is_expired(grant, datetime(2030, 6, 1)))
        z_grant = _grant(expires_at="2030-01-01T00:00:00Z")
        self.assertFalse(grant_is_expired(z_grant, datetime(2029, 6, 1)))
        self.assertTrue(grant_is_expired(z_grant, datetime(2030, 6, 1)))

    def test_check_request_sources_allows_only_granted_categories_and_paths(self) -> None:
        allowed_categories = canonicalize_disclosure_categories(
            ["FILE_CONTENT", "TASK"]
        )
        allowed_scopes = canonicalize_disclosure_scopes(
            [DisclosurePathScopeV2("DIRECTORY", "src")]
        )
        check_disclosure_request_sources(
            allowed_categories,
            allowed_scopes,
            canonicalize_disclosure_sources(
                [
                    DisclosureSourceV2("FILE_CONTENT", "src/app.py"),
                    DisclosureSourceV2("TASK", None),
                ]
            ),
        )
        with self.assertRaises(DisclosureScopeErrorV2) as caught:
            check_disclosure_request_sources(
                allowed_categories,
                allowed_scopes,
                canonicalize_disclosure_sources(
                    [DisclosureSourceV2("MEMORY", None)]
                ),
            )
        self.assertEqual(caught.exception.error_code, "SOURCE_CATEGORY")
        with self.assertRaises(DisclosureScopeErrorV2) as caught:
            check_disclosure_request_sources(
                allowed_categories,
                allowed_scopes,
                canonicalize_disclosure_sources(
                    [DisclosureSourceV2("FILE_CONTENT", "docs/app.py")]
                ),
            )
        self.assertEqual(caught.exception.error_code, "SOURCE_PATH")

    def test_the_payload_key_compares_every_command_fact(self) -> None:
        sources = canonicalize_disclosure_sources(
            [DisclosureSourceV2("FILE_CONTENT", "src/app.py")]
        )
        base = authorization_payload_key("run-1", "endpoint-1", 16, sources)
        self.assertEqual(base, authorization_payload_key("run-1", "endpoint-1", 16, sources))
        self.assertNotEqual(
            base, authorization_payload_key("run-2", "endpoint-1", 16, sources)
        )
        self.assertNotEqual(
            base, authorization_payload_key("run-1", "endpoint-2", 16, sources)
        )
        self.assertNotEqual(
            base, authorization_payload_key("run-1", "endpoint-1", 17, sources)
        )
        other_sources = canonicalize_disclosure_sources(
            [DisclosureSourceV2("TASK", None)]
        )
        self.assertNotEqual(
            base, authorization_payload_key("run-1", "endpoint-1", 16, other_sources)
        )
        # Source order is part of the payload identity.
        reordered = tuple(
            reversed(
                canonicalize_disclosure_sources(
                    [
                        DisclosureSourceV2("FILE_CONTENT", "src/app.py"),
                        DisclosureSourceV2("TASK", None),
                    ]
                )
            )
        )
        forward = canonicalize_disclosure_sources(
            [
                DisclosureSourceV2("FILE_CONTENT", "src/app.py"),
                DisclosureSourceV2("TASK", None),
            ]
        )
        self.assertNotEqual(
            authorization_payload_key("run-1", "endpoint-1", 16, forward),
            authorization_payload_key("run-1", "endpoint-1", 16, reordered),
        )


if __name__ == "__main__":
    unittest.main()

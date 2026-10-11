"""Route B / B3: the typed form contracts of the v2 local WebUI.

``vespercode.web.v2_forms`` owns the closed, allowlisted form shapes of
every v2 local WebUI endpoint: each contract names its exact field set,
each field has a closed typed parser (bounded identifiers, decimal
revisions, bounded task text, the literal confirmation, the CSRF token
form), and any extra, missing, duplicated, or malformed field is a
closed rejection that the app turns into an HTTP error before any
domain call.  The URL-encoded body parser enforces the same closed
shape (no duplicate fields, bounded field count).
"""

from __future__ import annotations

import unittest

from vespercode.web.v2_forms import (
    V2_CONFIRM_LITERAL,
    V2_TASK_MAX_CHARS,
    V2FormContract,
    V2FormError,
    V2_WRITEBACK_APPROVE_FORM,
    V2_WRITEBACK_APPLY_FORM,
    parse_v2_urlencoded,
)


class V2WritebackApproveFormTests(unittest.TestCase):
    def test_a_well_formed_form_parses_to_typed_values(self) -> None:
        parsed = V2_WRITEBACK_APPROVE_FORM.parse(
            {
                "run_id": "01234567-89ab-cdef-0123-456789abcdef",
                "candidate_id": "fedcba98-7654-3210-fedc-ba9876543210",
                "candidate_revision": "0",
                "confirm": "CONFIRM",
                "csrf_token": "ab" * 32,
            }
        )

        self.assertEqual(parsed["candidate_revision"], 0)
        self.assertIsInstance(parsed["candidate_revision"], int)
        self.assertEqual(parsed["confirm"], "CONFIRM")
        self.assertEqual(parsed["csrf_token"], "ab" * 32)

    def test_unknown_and_missing_fields_reject_with_closed_codes(self) -> None:
        base = {
            "run_id": "run-1",
            "candidate_id": "candidate-1",
            "candidate_revision": "3",
            "confirm": "CONFIRM",
            "csrf_token": "ab" * 32,
        }
        with self.assertRaises(V2FormError) as caught:
            V2_WRITEBACK_APPROVE_FORM.parse({**base, "extra": "x"})
        self.assertEqual(caught.exception.code, "UNKNOWN_FIELD")

        partial = dict(base)
        del partial["confirm"]
        with self.assertRaises(V2FormError) as caught:
            V2_WRITEBACK_APPROVE_FORM.parse(partial)
        self.assertEqual(caught.exception.code, "MISSING_FIELD")

    def test_malformed_values_reject_with_closed_codes(self) -> None:
        base = {
            "run_id": "run-1",
            "candidate_id": "candidate-1",
            "candidate_revision": "3",
            "confirm": "CONFIRM",
            "csrf_token": "ab" * 32,
        }
        malformed = {
            "run_id": "../escape",
            "candidate_id": "id with spaces",
            "candidate_revision": "3.5",
            "confirm": "yes",
            "csrf_token": "nothex",
        }
        for field, code in (
            ("run_id", "INVALID_IDENTIFIER"),
            ("candidate_id", "INVALID_IDENTIFIER"),
            ("candidate_revision", "INVALID_REVISION"),
            ("confirm", "INVALID_CONFIRMATION"),
            ("csrf_token", "INVALID_TOKEN"),
        ):
            with self.assertRaises(V2FormError) as caught:
                V2_WRITEBACK_APPROVE_FORM.parse({**base, field: malformed[field]})
            self.assertEqual(caught.exception.code, code, field)

    def test_revisions_are_closed_non_negative_decimals(self) -> None:
        base = {
            "run_id": "run-1",
            "candidate_id": "candidate-1",
            "candidate_revision": "0",
            "confirm": "CONFIRM",
            "csrf_token": "ab" * 32,
        }
        for bad in ("-1", "1e3", " 4", "4 ", "٠", "0x10", "99999999999999"):
            with self.assertRaises(V2FormError):
                V2_WRITEBACK_APPROVE_FORM.parse(
                    {**base, "candidate_revision": bad}
                )
        parsed = V2_WRITEBACK_APPROVE_FORM.parse(
            {**base, "candidate_revision": "42"}
        )
        self.assertEqual(parsed["candidate_revision"], 42)


class V2WritebackApplyFormTests(unittest.TestCase):
    def test_the_apply_form_binds_the_approval_id(self) -> None:
        parsed = V2_WRITEBACK_APPLY_FORM.parse(
            {
                "run_id": "run-1",
                "candidate_id": "candidate-1",
                "candidate_revision": "0",
                "approval_id": "approval-1",
                "confirm": "CONFIRM",
                "csrf_token": "ab" * 32,
            }
        )
        self.assertEqual(parsed["approval_id"], "approval-1")
        self.assertEqual(
            set(parsed),
            {
                "run_id",
                "candidate_id",
                "candidate_revision",
                "approval_id",
                "confirm",
                "csrf_token",
            },
        )

    def test_no_policy_or_profile_override_fields_exist(self) -> None:
        for contract in (V2_WRITEBACK_APPROVE_FORM, V2_WRITEBACK_APPLY_FORM):
            names = {name for name, _ in contract.fields}
            self.assertNotIn("policy", names)
            self.assertNotIn("profile", names)
            self.assertNotIn("path", names)
            self.assertNotIn("content", names)


class V2ContractConstructionTests(unittest.TestCase):
    def test_contracts_reject_duplicate_field_names(self) -> None:
        with self.assertRaises(ValueError):
            V2FormContract(
                endpoint="broken",
                fields=(
                    ("run_id", "identifier"),
                    ("run_id", "identifier"),
                ),
            )

    def test_unknown_field_kinds_reject(self) -> None:
        with self.assertRaises(ValueError):
            V2FormContract(
                endpoint="broken",
                fields=(("run_id", "not-a-kind"),),
            )

    def test_the_confirmation_literal_and_task_bound_are_closed(self) -> None:
        self.assertEqual(V2_CONFIRM_LITERAL, "CONFIRM")
        self.assertEqual(V2_TASK_MAX_CHARS, 4096)


class ParseV2UrlencodedTests(unittest.TestCase):
    def test_a_plain_body_parses_to_flat_fields(self) -> None:
        self.assertEqual(
            parse_v2_urlencoded("a=1&b=hello+world"),
            {"a": "1", "b": "hello world"},
        )

    def test_duplicate_fields_reject(self) -> None:
        with self.assertRaises(V2FormError) as caught:
            parse_v2_urlencoded("a=1&a=2")
        self.assertEqual(caught.exception.code, "DUPLICATE_FIELD")

    def test_excessive_field_counts_reject(self) -> None:
        with self.assertRaises(V2FormError) as caught:
            parse_v2_urlencoded("&".join(f"f{i}=1" for i in range(200)))
        self.assertEqual(caught.exception.code, "FORM_MALFORMED")


if __name__ == "__main__":
    unittest.main()

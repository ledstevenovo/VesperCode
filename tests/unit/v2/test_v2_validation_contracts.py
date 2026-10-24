"""Route B / B1: v2 validation run/result and reference profile contracts.

The v1 validation plane closes every record over SHA-256 identities:
``validation/manifest.py`` self-binds a manifest digest,
``validation/formal.py`` only accepts evidence whose digest chain
matches, and ``profiles/reference.py`` verifies a manifest against
frozen gate digests.  Those modules remain untouched read-only legacy.

The v2 contracts replace that with control-plane keys: a validation run
and its result are keyed by run, candidate, candidate revision, and the
reference profile id/revision that executed them, with a bounded status
and a bounded error message.  A reference profile record is keyed by
``reference_profile_id`` plus ``profile_revision`` and carries declared
tool metadata as plain configuration — never a digest identity.
Acceptance of evidence is a pure fail-closed binding check.
"""

from __future__ import annotations

import unittest
from dataclasses import replace

from vespercode.candidate.v2_candidate import (
    CandidateControlIdentityV2,
    advance_candidate_revision,
)
from vespercode.contracts.v2_validation import (
    MAX_VALIDATION_ERROR_CHARS,
    VALIDATION_RUN_STATUSES_V2,
    ValidationBindingV2,
    ValidationRunRecordV2,
    ValidationResultV2,
    validation_result_from_mapping,
    validation_run_from_mapping,
    verify_evidence_binding,
)
from vespercode.profiles.v2_reference import (
    ReferenceProfileRecordV2,
    reference_profile_from_mapping,
)


def _run_record(**overrides: object) -> ValidationRunRecordV2:
    values: dict[str, object] = {
        "validation_run_id": "val-1",
        "run_id": "run-1",
        "candidate_id": "cand-1",
        "candidate_revision": 2,
        "reference_profile_id": "profile-1",
        "reference_profile_revision": 0,
        "status": "PENDING",
        "error": None,
    }
    values.update(overrides)
    return ValidationRunRecordV2(**values)


def _result(**overrides: object) -> ValidationResultV2:
    values: dict[str, object] = {
        "validation_run_id": "val-1",
        "run_id": "run-1",
        "candidate_id": "cand-1",
        "candidate_revision": 2,
        "reference_profile_id": "profile-1",
        "reference_profile_revision": 0,
        "status": "PASSED",
        "error": None,
    }
    values.update(overrides)
    return ValidationResultV2(**values)


class ValidationRecordShapeTests(unittest.TestCase):
    def test_run_record_carries_the_five_keys_and_bounded_status(self) -> None:
        run = _run_record()

        self.assertEqual(
            (
                run.run_id,
                run.candidate_id,
                run.candidate_revision,
                run.reference_profile_id,
                run.reference_profile_revision,
            ),
            ("run-1", "cand-1", 2, "profile-1", 0),
        )
        self.assertEqual(run.status, "PENDING")
        self.assertIsNone(run.error)
        self.assertEqual(
            VALIDATION_RUN_STATUSES_V2,
            frozenset({"PENDING", "PASSED", "FAILED"}),
        )
        for forbidden in (
            "digest",
            "reference_profile_digest",
            "snapshot_tree_digest",
            "manifest_id",
            "formal_result_digest",
        ):
            self.assertFalse(hasattr(run, forbidden), forbidden)

    def test_run_record_rejects_malformed_fields(self) -> None:
        bad: tuple[dict[str, object], ...] = (
            {"run_id": ""},
            {"candidate_id": "   "},
            {"candidate_revision": -1},
            {"candidate_revision": True},
            {"candidate_revision": "2"},
            {"reference_profile_id": ""},
            {"reference_profile_revision": -2},
            {"status": "RUNNING"},
            {"status": ""},
            {"error": 7},
        )
        for overrides in bad:
            with self.assertRaises(ValueError, msg=repr(overrides)):
                _run_record(**overrides)
        # An error message is required exactly for FAILED outcomes and is
        # bounded; a non-empty bounded message on FAILED is valid.
        with self.assertRaises(ValueError):
            _run_record(status="FAILED", error=None)
        with self.assertRaises(ValueError):
            _run_record(status="FAILED", error="")
        for status in ("PENDING", "PASSED"):
            with self.assertRaises(ValueError, msg=status):
                _run_record(status=status, error="boom")
        with self.assertRaises(ValueError):
            _run_record(status="FAILED", error="x" * (MAX_VALIDATION_ERROR_CHARS + 1))
        self.assertEqual(
            len(
                _run_record(
                    status="FAILED", error="x" * MAX_VALIDATION_ERROR_CHARS
                ).error
            ),
            MAX_VALIDATION_ERROR_CHARS,
        )

    def test_result_record_is_terminal_only(self) -> None:
        self.assertEqual(_result().status, "PASSED")
        failed = _result(status="FAILED", error="collected 2 errors")
        self.assertEqual(failed.error, "collected 2 errors")
        with self.assertRaises(ValueError):
            _result(status="PENDING")
        with self.assertRaises(ValueError):
            _result(status="FAILED", error="x" * (MAX_VALIDATION_ERROR_CHARS + 1))

    def test_binding_record_rejects_malformed_fields(self) -> None:
        bad: tuple[dict[str, object], ...] = (
            {"run_id": ""},
            {"candidate_id": "   "},
            {"candidate_revision": -1},
            {"candidate_revision": False},
            {"reference_profile_id": ""},
            {"reference_profile_revision": -3},
        )
        for overrides in bad:
            with self.assertRaises(ValueError, msg=repr(overrides)):
                ValidationBindingV2(
                    **{
                        **{
                            "run_id": "run-1",
                            "candidate_id": "cand-1",
                            "candidate_revision": 2,
                            "reference_profile_id": "profile-1",
                            "reference_profile_revision": 0,
                        },
                        **overrides,
                    }
                )

    def test_run_and_result_from_mapping_reject_unknown_and_missing_fields(
        self,
    ) -> None:
        good_run = {
            "validation_run_id": "val-1",
            "run_id": "run-1",
            "candidate_id": "cand-1",
            "candidate_revision": 2,
            "reference_profile_id": "profile-1",
            "reference_profile_revision": 0,
            "status": "PASSED",
            "error": None,
        }
        run = validation_run_from_mapping(good_run)
        self.assertEqual(run.status, "PASSED")
        with self.assertRaisesRegex(ValueError, "unknown"):
            validation_run_from_mapping({**good_run, "manifest_id": "a" * 64})
        with self.assertRaisesRegex(ValueError, "missing"):
            validation_run_from_mapping(
                {key: value for key, value in good_run.items() if key != "run_id"}
            )

        good_result = {**good_run, "status": "FAILED", "error": "boom"}
        result = validation_result_from_mapping(good_result)
        self.assertEqual(result.error, "boom")
        with self.assertRaisesRegex(ValueError, "unknown"):
            validation_result_from_mapping({**good_result, "digest": "a" * 64})
        with self.assertRaises(ValueError):
            validation_result_from_mapping(["not", "a", "mapping"])


class ValidationEvidenceBindingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.candidate = CandidateControlIdentityV2("cand-1", "snap-1", 2, "ACTIVE")
        self.profile = ReferenceProfileRecordV2(
            "profile-1", 0, "3.12.4", "8.4.2", "0.16.1", "2.3.0"
        )
        self.binding = ValidationBindingV2("run-1", "cand-1", 2, "profile-1", 0)
        self.run = _run_record()
        self.result = _result()

    def test_matching_binding_accepts_evidence(self) -> None:
        verify_evidence_binding(self.result, run=self.run, expected=self.binding)

    def test_evidence_from_another_candidate_run_or_profile_is_rejected(self) -> None:
        mismatches: tuple[dict[str, object], ...] = (
            {"run_id": "run-2"},
            {"candidate_id": "cand-2"},
            {"candidate_revision": 3},
            {"reference_profile_id": "profile-2"},
            {"reference_profile_revision": 1},
        )
        for overrides in mismatches:
            with self.assertRaisesRegex(
                ValueError, "does not match", msg=repr(overrides)
            ):
                verify_evidence_binding(
                    self.result,
                    run=self.run,
                    expected=replace(self.binding, **overrides),
                )

    def test_a_result_from_another_validation_run_is_rejected(self) -> None:
        other_run = _run_record(validation_run_id="val-2")
        with self.assertRaisesRegex(ValueError, "does not belong"):
            verify_evidence_binding(self.result, run=other_run, expected=self.binding)

    def test_a_result_rebound_to_other_keys_is_rejected(self) -> None:
        rebound = _result(candidate_id="cand-2")
        with self.assertRaisesRegex(ValueError, "disagrees"):
            verify_evidence_binding(rebound, run=self.run, expected=self.binding)

    def test_revision_advance_invalidates_references_without_identity_regeneration(
        self,
    ) -> None:
        # Mutating content does not regenerate any identity digest: the
        # candidate id and snapshot reference are unchanged, only the
        # revision advances.
        mutated = advance_candidate_revision(self.candidate)
        self.assertEqual(mutated.candidate_id, "cand-1")
        self.assertEqual(mutated.snapshot_id, "snap-1")
        self.assertEqual(mutated.revision, 3)

        # Old evidence is stale against the current candidate state.
        current_binding = ValidationBindingV2("run-1", "cand-1", 3, "profile-1", 0)
        with self.assertRaisesRegex(ValueError, "does not match"):
            verify_evidence_binding(self.result, run=self.run, expected=current_binding)

        # Evidence recorded against the new revision is accepted.
        new_run = _run_record(
            validation_run_id="val-2", candidate_revision=3, status="PASSED"
        )
        new_result = _result(validation_run_id="val-2", candidate_revision=3)
        verify_evidence_binding(new_result, run=new_run, expected=current_binding)


class ReferenceProfileRecordTests(unittest.TestCase):
    def test_profile_record_declares_metadata_as_configuration(self) -> None:
        profile = ReferenceProfileRecordV2(
            "profile-1", 2, "3.12.4", "8.4.2", "0.16.1", "2.3.0"
        )

        self.assertEqual(profile.reference_profile_id, "profile-1")
        self.assertEqual(profile.profile_revision, 2)
        self.assertEqual(profile.python_version, "3.12.4")
        self.assertEqual(profile.pytest_version, "8.4.2")
        # Declared metadata is plain configuration, not digest identity.
        for forbidden in (
            "digest",
            "requirements_lock_digest",
            "docker_image_digest",
            "editable_path_policy",
            "schema_version",
        ):
            self.assertFalse(hasattr(profile, forbidden), forbidden)

    def test_profile_record_rejects_malformed_fields(self) -> None:
        cases: tuple[tuple[object, ...], ...] = (
            ("", 0, "3.12.4", "8.4.2", "0.16.1", "2.3.0"),
            ("p", -1, "3.12.4", "8.4.2", "0.16.1", "2.3.0"),
            ("p", True, "3.12.4", "8.4.2", "0.16.1", "2.3.0"),
            ("p", 0, "", "8.4.2", "0.16.1", "2.3.0"),
            ("p", 0, "3.12.4", "  ", "0.16.1", "2.3.0"),
            ("p", 0, "3.12.4", "8.4.2", None, "2.3.0"),
            (None, 0, "3.12.4", "8.4.2", "0.16.1", "2.3.0"),
        )
        for case in cases:
            with self.assertRaises(ValueError, msg=repr(case)):
                ReferenceProfileRecordV2(*case)

    def test_profile_from_mapping_rejects_v1_manifest_shaped_payloads(self) -> None:
        good = {
            "reference_profile_id": "profile-1",
            "profile_revision": 0,
            "python_version": "3.12.4",
            "pytest_version": "8.4.2",
            "ruff_version": "0.16.1",
            "mypy_version": "2.3.0",
        }
        profile = reference_profile_from_mapping(good)
        self.assertEqual(profile.python_version, "3.12.4")

        # A v1 ReferenceProfileManifestV1-shaped payload is not a v2
        # reference profile record; its digest fields are unknown here
        # and none of them is accepted as authority.
        v1_manifest = {
            "schema_version": 1,
            "profile_id": "python-src-py312-v1",
            "requirements_lock_digest": "a" * 64,
            "docker_image_digest": "a" * 64,
            "digest": "a" * 64,
        }
        with self.assertRaisesRegex(ValueError, "fields"):
            reference_profile_from_mapping(v1_manifest)
        with self.assertRaisesRegex(ValueError, "unknown"):
            reference_profile_from_mapping({**good, "digest": "a" * 64})
        with self.assertRaisesRegex(ValueError, "missing"):
            reference_profile_from_mapping(
                {key: value for key, value in good.items() if key != "profile_revision"}
            )


if __name__ == "__main__":
    unittest.main()

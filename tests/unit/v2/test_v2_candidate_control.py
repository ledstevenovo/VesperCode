"""Route B / B1: v2 candidate control identity and diff records.

The v1 candidate plane binds a candidate's semantic identity to content
digests: ``trees/candidate.py`` derives a content-addressed tree,
``candidate/identity.py`` closes a three-root digest binding, and
``candidate/final_diff.py`` seals preimage/postimage digests into every
diff entry.  Those modules remain untouched read-only legacy.

This slice adds the v2 replacement vocabulary: a candidate control
identity is an opaque ``candidate_id`` plus a snapshot reference, a
non-negative control-plane ``revision``, and a bounded lifecycle
``status``; a diff record associates a diff artifact with one candidate
revision through ordinary ``diff_id``/``artifact_id`` references.  No
content digest authenticates anything, so mutating staged content never
requires regenerating an identity value — only advancing the revision.
"""

from __future__ import annotations

import unittest

from vespercode.candidate.v2_candidate import (
    CANDIDATE_CONTROL_STATUSES_V2,
    CandidateControlIdentityV2,
    CandidateDiffRecordV2,
    advance_candidate_revision,
    candidate_control_from_mapping,
    candidate_diff_from_mapping,
)
from vespercode.contracts.v2_identity import (
    new_artifact_id,
    new_candidate_id,
    new_diff_id,
    new_snapshot_id,
)


class CandidateControlIdentityTests(unittest.TestCase):
    def test_control_identity_carries_opaque_ids_revision_and_bounded_status(
        self,
    ) -> None:
        identity = CandidateControlIdentityV2(
            candidate_id=new_candidate_id(),
            snapshot_id=new_snapshot_id(),
            revision=0,
            status="ACTIVE",
        )

        self.assertEqual(identity.revision, 0)
        self.assertEqual(identity.status, "ACTIVE")
        self.assertEqual(CANDIDATE_CONTROL_STATUSES_V2, frozenset({"ACTIVE", "SUPERSEDED"}))
        # No content digest is carried as identity or authorization.
        for forbidden in (
            "digest",
            "candidate_digest",
            "snapshot_tree_digest",
            "candidate_tree_digest",
            "final_diff_digest",
        ):
            self.assertFalse(hasattr(identity, forbidden), forbidden)

    def test_ids_are_opaque_lookup_keys(self) -> None:
        # Any non-empty string is a usable lookup key; the record never
        # interprets or re-derives an identifier from content.
        identity = CandidateControlIdentityV2(
            candidate_id="lookup-key-1",
            snapshot_id="snap-1",
            revision=7,
            status="SUPERSEDED",
        )

        self.assertEqual(identity.candidate_id, "lookup-key-1")
        self.assertEqual(identity.revision, 7)
        self.assertEqual(identity.status, "SUPERSEDED")

    def test_control_identity_rejects_malformed_fields(self) -> None:
        cases: tuple[tuple[object, ...], ...] = (
            ("", "s", 0, "ACTIVE"),
            ("   ", "s", 0, "ACTIVE"),
            ("c", "", 0, "ACTIVE"),
            ("c", "s", -1, "ACTIVE"),
            ("c", "s", True, "ACTIVE"),
            ("c", "s", 1.5, "ACTIVE"),
            ("c", "s", "0", "ACTIVE"),
            ("c", "s", 0, "OPEN"),
            ("c", "s", 0, ""),
            ("c", "s", 0, 3),
            (123, "s", 0, "ACTIVE"),
        )
        for case in cases:
            with self.assertRaises(ValueError, msg=repr(case)):
                CandidateControlIdentityV2(*case)
        with self.assertRaises(ValueError):
            CandidateControlIdentityV2("x" * 257, "s", 0, "ACTIVE")

    def test_advance_bumps_the_revision_and_keeps_the_candidate_id(self) -> None:
        identity = CandidateControlIdentityV2("cand-1", "snap-1", 4, "ACTIVE")

        advanced = advance_candidate_revision(identity)

        # A content mutation advances the control-plane revision; the
        # candidate identity itself never has to be regenerated.
        self.assertEqual(advanced.candidate_id, "cand-1")
        self.assertEqual(advanced.snapshot_id, "snap-1")
        self.assertEqual(advanced.revision, 5)
        self.assertEqual(advanced.status, "ACTIVE")
        self.assertEqual(identity.revision, 4)

    def test_from_mapping_requires_the_exact_field_set(self) -> None:
        good = {
            "candidate_id": "cand-1",
            "snapshot_id": "snap-1",
            "revision": 0,
            "status": "ACTIVE",
        }
        identity = candidate_control_from_mapping(good)
        self.assertEqual(identity.candidate_id, "cand-1")
        self.assertEqual(identity.revision, 0)

        with self.assertRaisesRegex(ValueError, "missing"):
            candidate_control_from_mapping(
                {key: value for key, value in good.items() if key != "snapshot_id"}
            )
        # v1-style digest fields are unknown here and never authority.
        with self.assertRaisesRegex(ValueError, "unknown"):
            candidate_control_from_mapping({**good, "digest": "a" * 64})
        with self.assertRaisesRegex(ValueError, "unknown"):
            candidate_control_from_mapping(
                {**good, "candidate_tree_digest": "a" * 64}
            )
        with self.assertRaises(ValueError):
            candidate_control_from_mapping(("candidate_id", "c"))


class CandidateDiffRecordTests(unittest.TestCase):
    def test_diff_record_binds_candidate_revision_and_artifact_by_plain_ids(
        self,
    ) -> None:
        record = CandidateDiffRecordV2(
            diff_id=new_diff_id(),
            candidate_id=new_candidate_id(),
            candidate_revision=3,
            artifact_id=new_artifact_id(),
        )

        self.assertEqual(record.candidate_revision, 3)
        # Association happens through ordinary IDs and a revision only.
        for forbidden in (
            "digest",
            "postimage_digest",
            "preimage",
            "snapshot_tree_digest",
            "final_diff_digest",
            "postimage_text_metadata",
        ):
            self.assertFalse(hasattr(record, forbidden), forbidden)

    def test_diff_record_rejects_malformed_fields(self) -> None:
        cases: tuple[tuple[object, ...], ...] = (
            ("", "c", 0, "a"),
            ("d", "c", -1, "a"),
            ("d", "c", True, "a"),
            ("d", "c", 0.5, "a"),
            ("d", "c", 0, ""),
            ("d", "c", 0, "   "),
            ("d", "", 0, "a"),
            (None, "c", 0, "a"),
        )
        for case in cases:
            with self.assertRaises(ValueError, msg=repr(case)):
                CandidateDiffRecordV2(*case)
        with self.assertRaises(ValueError):
            CandidateDiffRecordV2("d", "c", 0, "a" * 257)

    def test_diff_from_mapping_rejects_v1_final_diff_shaped_payloads(self) -> None:
        good = {
            "diff_id": "diff-1",
            "candidate_id": "cand-1",
            "candidate_revision": 0,
            "artifact_id": "artifact-1",
        }
        record = candidate_diff_from_mapping(good)
        self.assertEqual(record.artifact_id, "artifact-1")

        # A v1 FinalDiffV1-shaped payload is not a v2 diff record.
        v1_shaped = {
            "schema_version": 1,
            "snapshot_tree_digest": "a" * 64,
            "entries": (),
            "added_and_replacement_text_bytes": 0,
            "digest": "a" * 64,
        }
        with self.assertRaises(ValueError):
            candidate_diff_from_mapping(v1_shaped)
        with self.assertRaisesRegex(ValueError, "unknown"):
            candidate_diff_from_mapping({**good, "postimage_digest": "a" * 64})
        with self.assertRaisesRegex(ValueError, "missing"):
            candidate_diff_from_mapping(
                {key: value for key, value in good.items() if key != "artifact_id"}
            )


if __name__ == "__main__":
    unittest.main()

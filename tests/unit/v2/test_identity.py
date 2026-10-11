from __future__ import annotations

import unittest

from vespercode.contracts.v2_identity import (
    ActionInstanceV2,
    CandidateIdentityV2,
    FinalWritebackSubjectV2,
    new_approval_id,
    new_run_id,
)


class V2IdentityTests(unittest.TestCase):
    def test_generated_ids_are_opaque_uuid_references(self) -> None:
        first = new_run_id()
        second = new_run_id()

        self.assertNotEqual(first, second)
        self.assertRegex(first, r"^[0-9a-f-]{36}$")
        self.assertRegex(second, r"^[0-9a-f-]{36}$")

    def test_candidate_identity_has_revision_not_content_digest(self) -> None:
        identity = CandidateIdentityV2(
            candidate_id=new_approval_id(),
            snapshot_id=new_run_id(),
            revision=3,
        )

        self.assertEqual(identity.revision, 3)
        self.assertFalse(hasattr(identity, "candidate_digest"))
        with self.assertRaises(ValueError):
            CandidateIdentityV2(
                candidate_id=new_approval_id(),
                snapshot_id=new_run_id(),
                revision=-1,
            )

    def test_action_and_writeback_subject_use_reference_ids(self) -> None:
        action = ActionInstanceV2(action_id=new_run_id(), action_type="READ_FILE")
        subject = FinalWritebackSubjectV2(
            subject_id=new_run_id(),
            candidate_id=new_run_id(),
            expires_at="2026-10-10T12:00:00Z",
        )

        self.assertEqual(action.action_type, "READ_FILE")
        self.assertEqual(len(subject.candidate_id), 36)
        self.assertFalse(hasattr(action, "semantic_digest"))
        self.assertFalse(hasattr(subject, "subject_digest"))


if __name__ == "__main__":
    unittest.main()

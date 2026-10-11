from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from vespercode.governance.relaxed_policy import (
    ActionRequestV2,
    DecisionV2,
    RelaxedPolicyV2,
)


class RelaxedPolicyTests(unittest.TestCase):
    def test_allows_edit_inside_workspace_src(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            decision = RelaxedPolicyV2().evaluate(
                ActionRequestV2(
                    action_type="REPLACE",
                    path="src/example.py",
                    workspace=workspace,
                )
            )

        self.assertEqual(decision, DecisionV2.ALLOW)

    def test_denies_escape_sensitive_and_protected_paths(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            policy = RelaxedPolicyV2()
            cases = (
                "../outside.py",
                ".env",
                "tests/test_example.py",
                "pyproject.toml",
            )

            decisions = [
                policy.evaluate(
                    ActionRequestV2(
                        action_type="REPLACE",
                        path=path,
                        workspace=workspace,
                    )
                )
                for path in cases
            ]

        self.assertEqual(decisions, [DecisionV2.DENY] * len(cases))

    def test_rejects_noncanonical_paths_and_allows_protected_reads(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            policy = RelaxedPolicyV2()

            rejected = [
                "src//example.py",
                "./src/example.py",
                "src/../README.md",
                "src\\example.py",
                "C:/src/example.py",
            ]
            rejected_decisions = [
                policy.evaluate(
                    ActionRequestV2("REPLACE", path, workspace)
                )
                for path in rejected
            ]
            read_decision = policy.evaluate(
                ActionRequestV2("READ_FILE", "pyproject.toml", workspace)
            )

        self.assertEqual(rejected_decisions, [DecisionV2.DENY] * len(rejected))
        self.assertEqual(read_decision, DecisionV2.ALLOW)

    def test_rejects_symlink_escape_before_any_write_authorization(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            outside = workspace.parent / f"{workspace.name}-outside"
            outside.mkdir()
            try:
                (workspace / "src").mkdir()
                link = workspace / "src" / "linked"
                try:
                    link.symlink_to(outside, target_is_directory=True)
                except (OSError, NotImplementedError):
                    self.skipTest("symlink creation is unavailable")

                decision = RelaxedPolicyV2().evaluate(
                    ActionRequestV2("REPLACE", "src/linked/secret.py", workspace)
                )
            finally:
                for child in outside.iterdir():
                    child.unlink()
                outside.rmdir()

        self.assertEqual(decision, DecisionV2.DENY)

    def test_protected_and_sensitive_paths_are_case_insensitive(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            policy = RelaxedPolicyV2()
            decisions = [
                policy.evaluate(ActionRequestV2("REPLACE", "TESTS/example.py", workspace)),
                policy.evaluate(ActionRequestV2("REPLACE", "PyProject.TOML", workspace)),
                policy.evaluate(ActionRequestV2("REPLACE", ".ENV", workspace)),
                policy.evaluate(ActionRequestV2("REPLACE", "src", workspace)),
            ]

        self.assertEqual(decisions, [DecisionV2.DENY] * 4)


if __name__ == "__main__":
    unittest.main()

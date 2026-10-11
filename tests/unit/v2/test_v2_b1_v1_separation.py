"""Route B / B1: v1 digest authority stays out of the v2 identity plane.

The v1 candidate/validation/reference modules remain in the repository as
read-only legacy, but no v2 identity decision may flow through them.
This guard pins that boundary statically: the Route B1 production
modules (and the v2 storage module that persists their records) must not
import any v1 digest-bound module.  It reads sources only — no import of
v1 code happens in the v2 test process at all.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[3]
_SRC_ROOT = _REPO_ROOT / "src" / "vespercode"

_B1_MODULES = (
    "candidate/v2_candidate.py",
    "contracts/v2_validation.py",
    "profiles/v2_reference.py",
    "storage/v2_database.py",
)

# The v1 digest/identity authority modules. None of these may be
# imported by a v2 module for an identity or authorization decision.
_V1_AUTHORITY_MODULES = (
    "vespercode.candidate.identity",
    "vespercode.candidate.final_diff",
    "vespercode.candidate.patch_engine",
    "vespercode.candidate.unified_diff",
    "vespercode.canonical.digest",
    "vespercode.canonical.json_v1",
    "vespercode.canonical.path_v1",
    "vespercode.canonical.timestamp_v1",
    "vespercode.contracts.action",
    "vespercode.contracts.evidence",
    "vespercode.contracts.location",
    "vespercode.contracts.optional",
    "vespercode.contracts.run",
    "vespercode.profiles.editable",
    "vespercode.profiles.endpoints",
    "vespercode.profiles.llm",
    "vespercode.profiles.reference",
    "vespercode.profiles.registry",
    "vespercode.trees.candidate",
    "vespercode.trees.content_store",
    "vespercode.trees.snapshot",
    "vespercode.trees.text_classifier",
    "vespercode.validation.baseline",
    "vespercode.validation.check_result",
    "vespercode.validation.failure_fingerprint",
    "vespercode.validation.formal",
    "vespercode.validation.formal_execution",
    "vespercode.validation.formal_plan",
    "vespercode.validation.manifest",
    "vespercode.validation.pytest_evidence",
    "vespercode.validation.pytest_reporter",
    "vespercode.validation.python_adapter",
)


class B1V1SeparationTests(unittest.TestCase):
    def test_b1_modules_exist(self) -> None:
        for relative in _B1_MODULES:
            self.assertTrue(
                (_SRC_ROOT / relative).is_file(),
                f"missing B1 module: {relative}",
            )

    def test_b1_modules_do_not_import_v1_authority(self) -> None:
        pattern = "|".join(re.escape(module) for module in _V1_AUTHORITY_MODULES)
        import_line = re.compile(rf"^\s*(?:from|import)\s+({pattern})\b", re.MULTILINE)
        for relative in _B1_MODULES:
            source = (_SRC_ROOT / relative).read_text(encoding="utf-8")
            match = import_line.search(source)
            self.assertIsNone(
                match,
                f"{relative} imports v1 authority module: "
                f"{match.group(1) if match else ''}",
            )


if __name__ == "__main__":
    unittest.main()

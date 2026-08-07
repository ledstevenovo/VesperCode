"""T33.1 legacy step 33.A: wheel digest and RECORD integrity tests.

The domain pins the independently verified SHA-256 evidence (GREEN-2):
the adjacent lowercase evidence matches a fresh recomputation from the
exact wheel bytes, the RECORD lists exactly the member set with a
correct sha256/size per member, and the dist directory holds exactly
one versioned wheel and one evidence file (Expected 33.A).
"""

from __future__ import annotations

import base64
import hashlib
import re
from typing import Final

import pytest

from scripts.run_package_smoke import WheelArchive

pytestmark = pytest.mark.package_smoke

_SHA256_HEX_RE: Final = re.compile(r"[0-9a-f]{64}")
"""The closed lowercase SHA-256 hex evidence form."""


def test_wheel_sha256_evidence_is_independent_and_adjacent(
    built_wheel: WheelArchive,
) -> None:
    """The published evidence matches a fresh independent recomputation
    from the exact wheel bytes and sits adjacent to the wheel (GREEN-2).
    """
    recomputed = hashlib.sha256(built_wheel.wheel_path.read_bytes()).hexdigest()
    assert built_wheel.sha256 == recomputed
    assert built_wheel.evidence_path is not None
    assert built_wheel.evidence_path.name == built_wheel.wheel_path.name + ".sha256"
    assert built_wheel.evidence_path.is_file()
    assert built_wheel.evidence_sha256 == recomputed
    assert _SHA256_HEX_RE.fullmatch(built_wheel.evidence_sha256) is not None


def test_wheel_record_integrity(built_wheel: WheelArchive) -> None:
    """Every RECORD row binds the exact member bytes: the recorded
    sha256 and size match an independent recomputation per member, and
    RECORD lists exactly the wheel member set (Expected 33.A RECORD).
    """
    recorded = {entry.path for entry in built_wheel.record_entries}
    assert recorded == set(built_wheel.member_names)
    for entry in built_wheel.record_entries:
        data = built_wheel.member_bytes(entry.path)
        if entry.path.endswith(".dist-info/RECORD"):
            # the RECORD's own row carries no digest (self-reference)
            assert entry.sha256 is None
            continue
        assert entry.sha256 is not None, entry.path
        assert entry.size is not None, entry.path
        assert entry.size == len(data), entry.path
        expected = (
            base64.urlsafe_b64encode(hashlib.sha256(data).digest())
            .rstrip(b"=")
            .decode("ascii")
        )
        assert entry.sha256 == expected, entry.path


def test_dist_contains_exactly_one_wheel_and_evidence(
    built_wheel: WheelArchive,
) -> None:
    """The dist directory holds exactly one versioned wheel and exactly
    one adjacent evidence file (Expected 33.A: one wheel).
    """
    wheels = list(built_wheel.wheel_path.parent.glob("vespercode-*.whl"))
    assert wheels == [built_wheel.wheel_path]
    evidences = list(built_wheel.wheel_path.parent.glob("vespercode-*.whl.sha256"))
    assert evidences == [built_wheel.evidence_path]

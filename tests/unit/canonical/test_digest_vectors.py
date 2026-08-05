"""T04.2 legacy step 4.B: exact CTV vectors and digest matrix tests."""

from __future__ import annotations

import pytest

from src.vespercode.canonical.digest import DomainDigestErrorV1, domain_digest
from src.vespercode.canonical.json_v1 import (
    CanonicalJsonErrorV1,
    CanonicalValueV1,
    canonical_json_bytes,
)


def test_ctv_01_exact_bytes_and_digest() -> None:
    value: dict[str, CanonicalValueV1] = {
        "tags": (),
        "schema_version": 1,
        "optional_note": {"kind": "ABSENT"},
        "label": "x",
    }
    assert (
        canonical_json_bytes(value)
        == b'{"label":"x","optional_note":{"kind":"ABSENT"},"schema_version":1,"tags":[]}'
    )
    assert (
        domain_digest("CanonicalizationProbeV1", 1, value)
        == "1923bd578b2110ae145622050b4b6d10171c4b8fca4a383be06fa9f78d1ca782"
    )


def test_canonical_digest_vector_matrix() -> None:
    """SPEC §0.1 CTV-01—CTV-07 vectors owned by the canonical encoder.

    Schema-field closure for unknown or omitted fields (CTV-04) is enforced
    by the closed-schema consumers, not by the schema-agnostic encoder; the
    null-value row rejects here at the type level before any digest.
    """
    ctv01: dict[str, CanonicalValueV1] = {
        "tags": (),
        "schema_version": 1,
        "optional_note": {"kind": "ABSENT"},
        "label": "x",
    }
    ctv01_digest = "1923bd578b2110ae145622050b4b6d10171c4b8fca4a383be06fa9f78d1ca782"
    assert domain_digest("CanonicalizationProbeV1", 1, ctv01) == ctv01_digest
    # CTV-02: the same values in a different key order must produce the
    # identical canonical bytes and digest.
    reordered: dict[str, CanonicalValueV1] = {
        "optional_note": {"kind": "ABSENT"},
        "label": "x",
        "tags": (),
        "schema_version": 1,
    }
    assert canonical_json_bytes(reordered) == canonical_json_bytes(ctv01)
    assert domain_digest("CanonicalizationProbeV1", 1, reordered) == ctv01_digest
    # CTV-03: PRESENT with an empty string is a distinct value; the digest
    # must differ from CTV-01.
    present: dict[str, CanonicalValueV1] = {
        "label": "x",
        "optional_note": {"kind": "PRESENT", "value": ""},
        "schema_version": 1,
        "tags": (),
    }
    present_digest = domain_digest("CanonicalizationProbeV1", 1, present)
    assert (
        present_digest
        == "a9242ff2226e5d78c5efb1f8fb9adfe6c5a5c217d104c14691c38d3b95d10a3f"
    )
    assert present_digest != ctv01_digest
    # CTV-04: a null optional_note value is outside the closed domain and is
    # rejected before any digest is produced.
    null_value: dict[str, object] = {
        "label": "x",
        "optional_note": None,
        "schema_version": 1,
        "tags": (),
    }
    with pytest.raises(CanonicalJsonErrorV1):
        canonical_json_bytes(null_value)  # type: ignore[arg-type]
    with pytest.raises(CanonicalJsonErrorV1):
        domain_digest("CanonicalizationProbeV1", 1, null_value)  # type: ignore[arg-type]
    # CTV-05: the mixed label encodes with the exact escape set and raw
    # UTF-8 for every other scalar; bytes and digest are pinned exactly.
    label = '中文"\\\n/é'
    ctv05: dict[str, CanonicalValueV1] = {
        "label": label,
        "optional_note": {"kind": "ABSENT"},
        "schema_version": 1,
        "tags": (),
    }
    ctv05_hex = (
        "7b226c6162656c223a22e4b8ade696875c225c5c5c6e2f65cc81222c"
        "226f7074696f6e616c5f6e6f7465223a7b226b696e64223a22414253"
        "454e54227d2c22736368656d615f76657273696f6e223a312c227461"
        "6773223a5b5d7d"
    )
    assert canonical_json_bytes(ctv05).hex() == ctv05_hex
    assert (
        domain_digest("CanonicalizationProbeV1", 1, ctv05)
        == "1c757fec0a18509fe01156d8e7e359cc948d9abf1abcac0c999e00e15ed56a3a"
    )
    # CTV-06: a canonical timestamp string is encoded as raw UTF-8 bytes
    # under the CanonicalTimeProbeV1 domain (timestamp-form validation is
    # owned by legacy step 4.C).
    ctv06: dict[str, CanonicalValueV1] = {
        "schema_version": 1,
        "expires_at": "2026-07-24T09:30:15.123Z",
    }
    ctv06_hex = (
        "7b22657870697265735f6174223a22323032362d30372d3234543039"
        "3a33303a31352e3132335a222c22736368656d615f76657273696f6e"
        "223a317d"
    )
    assert canonical_json_bytes(ctv06).hex() == ctv06_hex
    assert (
        domain_digest("CanonicalTimeProbeV1", 1, ctv06)
        == "277d8e57122ba6ce91dfe28d5b724b2e5b0a85c3b9e33e951b19adcd86786125"
    )
    # CTV-07 (encoder-owned part): a lone surrogate must be rejected before
    # any digest is produced; timestamp-form rejection is owned by 4.C.
    surrogate: dict[str, CanonicalValueV1] = {
        "label": "\ud800",
        "optional_note": {"kind": "ABSENT"},
        "schema_version": 1,
        "tags": (),
    }
    with pytest.raises(CanonicalJsonErrorV1):
        domain_digest("CanonicalizationProbeV1", 1, surrogate)


def test_domain_and_version_separation() -> None:
    """Different object types or schema versions never share a digest."""
    value: dict[str, CanonicalValueV1] = {
        "label": "x",
        "optional_note": {"kind": "ABSENT"},
        "schema_version": 1,
        "tags": (),
    }
    same = domain_digest("CanonicalizationProbeV1", 1, value)
    reordered: dict[str, CanonicalValueV1] = {
        "tags": (),
        "schema_version": 1,
        "optional_note": {"kind": "ABSENT"},
        "label": "x",
    }
    assert domain_digest("CanonicalizationProbeV1", 1, reordered) == same
    assert domain_digest("CanonicalizationProbeV1", 2, value) != same
    assert domain_digest("CanonicalTimeProbeV1", 1, value) != same
    changed: dict[str, CanonicalValueV1] = {
        "label": "y",
        "optional_note": {"kind": "ABSENT"},
        "schema_version": 1,
        "tags": (),
    }
    assert domain_digest("CanonicalizationProbeV1", 1, changed) != same
    assert len(same) == 64
    assert all(character in "0123456789abcdef" for character in same)


def test_domain_digest_rejects_invalid_identity() -> None:
    value: dict[str, CanonicalValueV1] = {"label": "x"}
    with pytest.raises(DomainDigestErrorV1):
        domain_digest("", 1, value)
    with pytest.raises(DomainDigestErrorV1):
        domain_digest("CanonicalizationProbeV1", -1, value)
    with pytest.raises(DomainDigestErrorV1):
        domain_digest("CanonicalizationProbeV1", 1, "x")  # type: ignore[arg-type]
    # A lone surrogate inside the value is a value-level rejection that
    # propagates before any digest is produced.
    surrogate: dict[str, CanonicalValueV1] = {"label": "\ud800"}
    with pytest.raises(CanonicalJsonErrorV1):
        domain_digest("CanonicalizationProbeV1", 1, surrogate)

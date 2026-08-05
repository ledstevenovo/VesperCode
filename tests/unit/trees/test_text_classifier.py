"""T10.1 legacy step 10.B: shared supported-text byte classification tests.

Every file tool and candidate operation classifies raw bytes exactly once
through the pure ``classify_supported_text`` contract under the SPEC §4.2.2
and §4.3 rules: zero or one UTF-8 BOM, strict UTF-8 scalar decoding, no
U+0000, uniform LF or uniform CRLF (no bare CR, no mixed newlines), and a
final newline.  Invalid encoding, binary data, mixed newlines, missing
final newline, empty input, and any other combination that cannot uniquely
construct ``TextMetadataV1`` return the closed ``NON_TEXT_FILE`` variant
instead of normalizing bytes.  Content storage, tree construction,
normalization, and filesystem path reads remain out of scope (GREEN-4).
"""

from __future__ import annotations

import pytest

# The classifier contracts are pydantic runtime models; the hash-locked gate
# toolchain does not install runtime dependencies, so this module skips
# cleanly there instead of failing at collection (formal env runs it fully).
pytest.importorskip("pydantic")

from pydantic import TypeAdapter, ValidationError

from src.vespercode.trees.text_classifier import (
    NonTextFileV1,
    SupportedTextFileV1,
    TextFileClassificationV1,
    TextMetadataV1,
    classify_supported_text,
)


def test_mixed_newlines_are_non_text() -> None:
    assert classify_supported_text(b"a\\r\\nb\\n").kind == "NON_TEXT_FILE"


def test_text_byte_classification_matrix() -> None:
    """SPEC §4.2.2/§4.3 byte-classification matrix (Expected 10.B: 0).

    UTF-8 / UTF-8-BOM / LF / CRLF / final-newline cases classify exactly;
    invalid UTF-8, binary, mixed-newline, bare-CR, U+0000, BOM-only, and
    missing-final-newline cases remain valid ``NON_TEXT_FILE`` entries.
    """
    supported: tuple[tuple[bytes, str, str], ...] = (
        (b"x\n", "UTF8", "LF"),
        (b"a\nb\n", "UTF8", "LF"),
        ("你好\n".encode("utf-8"), "UTF8", "LF"),
        ("你好世界\n".encode("utf-8"), "UTF8", "LF"),
        (b"x\r\n", "UTF8", "CRLF"),
        (b"a\r\nb\r\n", "UTF8", "CRLF"),
        ("你好\r\n".encode("utf-8"), "UTF8", "CRLF"),
        (b"\xef\xbb\xbfx\n", "UTF8_BOM", "LF"),
        (b"\xef\xbb\xbfa\nb\n", "UTF8_BOM", "LF"),
        (b"\xef\xbb\xbf" + "你好\n".encode("utf-8"), "UTF8_BOM", "LF"),
        (b"\xef\xbb\xbfx\r\n", "UTF8_BOM", "CRLF"),
        (b"\xef\xbb\xbfa\r\nb\r\n", "UTF8_BOM", "CRLF"),
        # zero-or-one BOM: the second BOM is content (U+FEFF is a valid scalar).
        (b"\xef\xbb\xbf\xef\xbb\xbfx\n", "UTF8_BOM", "LF"),
        (b"\n", "UTF8", "LF"),
        (b"\r\n", "UTF8", "CRLF"),
    )
    for raw, encoding, newline in supported:
        classification = classify_supported_text(raw)
        assert classification.kind == "TEXT_FILE"
        assert isinstance(classification, SupportedTextFileV1)
        profile = classification.text_profile.value
        assert profile.encoding == encoding
        assert profile.newline == newline
        assert profile.final_newline is True
    rejected: tuple[bytes, ...] = (
        b"",  # empty file
        b"\xef\xbb\xbf",  # BOM only, no body
        b"x",  # no final newline
        b"x\r",  # bare CR
        b"a\r\nb\n",  # mixed CRLF then LF
        b"a\nb\r\n",  # mixed LF then CRLF
        b"x\r\n\r",  # bare CR after a CRLF
        b"x\r\n\n",  # CRLF then LF
        b"\x00\n",  # U+0000
        b"\xef\xbb\xbf\x00\n",  # BOM plus U+0000
        b"\xef\xbb\xbfx",  # BOM, valid body, no final newline
        b"\xff",  # invalid UTF-8
        b"\xff\xfe",  # UTF-16 LE BOM, invalid UTF-8
        b"\xc3\x28",  # invalid UTF-8 continuation
        b"\xed\xa0\x80",  # UTF-8 surrogate bytes, not a scalar value
        b"\x89PNG\r\n\x1a\n",  # PNG signature, binary bytes
    )
    for raw in rejected:
        classification = classify_supported_text(raw)
        assert classification.kind == "NON_TEXT_FILE"
        assert isinstance(classification, NonTextFileV1)


def test_text_metadata_closed_schema() -> None:
    valid = TextMetadataV1.model_validate(
        {"encoding": "UTF8", "newline": "CRLF", "final_newline": True}
    )
    assert valid.encoding == "UTF8" and valid.newline == "CRLF"
    assert valid.final_newline is True
    invalid: tuple[dict[str, object], ...] = (
        {"encoding": "UTF16", "newline": "LF", "final_newline": True},
        {"encoding": "UTF8", "newline": "MIXED", "final_newline": True},
        {"encoding": "UTF8", "newline": "LF", "final_newline": False},
        {"encoding": "UTF8", "newline": "LF", "final_newline": "true"},
        {"encoding": "UTF8", "newline": "LF"},  # missing final_newline
        {"encoding": "UTF8", "newline": "LF", "final_newline": True, "extra": 1},
    )
    for payload in invalid:
        with pytest.raises(ValidationError):
            TextMetadataV1.model_validate(payload)


def test_classification_union_closed_schema() -> None:
    adapter: TypeAdapter[TextFileClassificationV1] = TypeAdapter(
        TextFileClassificationV1
    )
    non_text = adapter.validate_python({"kind": "NON_TEXT_FILE"})
    assert non_text.kind == "NON_TEXT_FILE"
    assert isinstance(non_text, NonTextFileV1)
    text = adapter.validate_python(
        {
            "kind": "TEXT_FILE",
            "text_profile": {
                "kind": "PRESENT",
                "value": {
                    "encoding": "UTF8_BOM",
                    "newline": "LF",
                    "final_newline": True,
                },
            },
        }
    )
    assert text.kind == "TEXT_FILE"
    assert isinstance(text, SupportedTextFileV1)
    invalid: tuple[dict[str, object], ...] = (
        {"kind": "BINARY"},  # unknown kind
        {"kind": "TEXT_FILE"},  # TEXT_FILE without its profile
        {"kind": "TEXT_FILE", "text_profile": {"kind": "ABSENT"}},  # ABSENT profile
        {
            "kind": "TEXT_FILE",
            "text_profile": {
                "kind": "PRESENT",
                "value": {"encoding": "UTF8", "newline": "LF"},
            },
        },  # profile missing final_newline
    )
    for payload in invalid:
        with pytest.raises(ValidationError):
            adapter.validate_python(payload)


def test_classification_is_pure_and_immutable() -> None:
    raw = b"x\n"
    first = classify_supported_text(raw)
    second = classify_supported_text(raw)
    assert first == second
    assert raw == b"x\n"  # input bytes never changed
    assert isinstance(first, SupportedTextFileV1)
    with pytest.raises(ValidationError):
        first.text_profile.value.encoding = "UTF8_BOM"
    with pytest.raises(ValidationError):
        first.text_profile = first.text_profile

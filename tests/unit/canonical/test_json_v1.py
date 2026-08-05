"""T04.2 legacy step 4.B: canonical JSON byte encoding tests."""

from __future__ import annotations

import pytest

from src.vespercode.canonical.json_v1 import (
    CanonicalJsonErrorV1,
    CanonicalValueV1,
    canonical_json_bytes,
)


def test_object_keys_sort_by_code_point() -> None:
    assert canonical_json_bytes({"b": 1, "a": 2}) == b'{"a":2,"b":1}'


def test_bool_and_int_are_distinct_scalars() -> None:
    assert canonical_json_bytes(True) == b"true"
    assert canonical_json_bytes(False) == b"false"
    assert canonical_json_bytes(1) == b"1"
    assert canonical_json_bytes(-7) == b"-7"


def test_escape_set_is_exact() -> None:
    assert (
        canonical_json_bytes({"s": '"\\\b\t\n\f\r'})
        == b'{"s":"\\"\\\\\\b\\t\\n\\f\\r"}'
    )


def test_control_characters_use_lowercase_hex_escapes() -> None:
    assert (
        canonical_json_bytes({"s": "\x00\x0b\x1f"}) == b'{"s":"\\u0000\\u000b\\u001f"}'
    )


def test_other_scalars_are_emitted_as_raw_utf8() -> None:
    assert (
        canonical_json_bytes({"s": "/\u2028\u2029\u007f"})
        == b'{"s":"/\xe2\x80\xa8\xe2\x80\xa9\x7f"}'
    )
    assert canonical_json_bytes({"s": "中文"}) == b'{"s":"\xe4\xb8\xad\xe6\x96\x87"}'
    assert canonical_json_bytes({"s": "\U0001f600"}) == b'{"s":"\xf0\x9f\x98\x80"}'


def test_surrogate_pair_reduces_to_scalar() -> None:
    # The UTF-16 surrogate pair for U+1F600 must first reduce to the
    # scalar and then encode as raw UTF-8 rather than reject.
    assert canonical_json_bytes({"s": "\ud83d\ude00"}) == b'{"s":"\xf0\x9f\x98\x80"}'


def test_lone_surrogates_are_rejected() -> None:
    for bad in ("\ud800", "\udc00", "\ud800x", "a\ud800", "x\udfff"):
        with pytest.raises(CanonicalJsonErrorV1):
            canonical_json_bytes({"s": bad})


def test_forbidden_values_are_rejected() -> None:
    bad_values: tuple[object, ...] = (
        None,
        1.5,
        [1, 2],
        {1, 2},
        b"x",
        {"k": None},
        {"k": 1.5},
        {"k": []},
        {"k": {1: "x"}},
    )
    for bad in bad_values:
        with pytest.raises(CanonicalJsonErrorV1):
            canonical_json_bytes(bad)  # type: ignore[arg-type]


def test_empty_and_nested_containers() -> None:
    assert canonical_json_bytes({}) == b"{}"
    assert canonical_json_bytes(()) == b"[]"
    value: dict[str, CanonicalValueV1] = {
        "a": (1, (2, "x"), ()),
        "z": {"m": (), "n": {}},
    }
    assert canonical_json_bytes(value) == b'{"a":[1,[2,"x"],[]],"z":{"m":[],"n":{}}}'


def test_mapping_with_non_string_key_is_rejected() -> None:
    with pytest.raises(CanonicalJsonErrorV1):
        canonical_json_bytes({1: "x"})  # type: ignore[dict-item]

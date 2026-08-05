"""T04.2 legacy step 4.B: v1 canonical JSON byte encoding.

Encodes every closed ``CanonicalValueV1`` value into the one exact UTF-8
byte representation defined by SPEC §0.1: no whitespace, decimal integers,
object keys sorted by code point without normalization, the fixed escape
set for ``"``/``\\`` and U+0000—U+001F, and raw UTF-8 for every other
Unicode scalar (never ``\\uXXXX`` or ``\\/``).  Lone surrogates and every
value outside the closed domain are rejected deterministically before any
byte is produced; a legal UTF-16 surrogate pair is reduced to its scalar
first.  Time, paths, file scanning, and tool-version selection remain out
of scope (GREEN-4).
"""

from __future__ import annotations

from typing import Mapping, TypeAlias

CanonicalArrayV1: TypeAlias = tuple["CanonicalValueV1", ...]
CanonicalValueV1: TypeAlias = (
    str | int | bool | CanonicalArrayV1 | Mapping[str, "CanonicalValueV1"]
)


class CanonicalJsonErrorV1(ValueError):
    """Closed rejection for a value outside the canonical JSON domain."""


_ESCAPES: dict[str, str] = {
    '"': '\\"',
    "\\": "\\\\",
    "\b": "\\b",
    "\t": "\\t",
    "\n": "\\n",
    "\f": "\\f",
    "\r": "\\r",
}
_HIGH_SURROGATE_START = 0xD800
_HIGH_SURROGATE_END = 0xDBFF
_LOW_SURROGATE_START = 0xDC00
_LOW_SURROGATE_END = 0xDFFF
_SCALAR_BASE = 0x10000


def _encode_string(value: str) -> str:
    pieces: list[str] = []
    index = 0
    length = len(value)
    while index < length:
        character = value[index]
        code = ord(character)
        if _HIGH_SURROGATE_START <= code <= _LOW_SURROGATE_END:
            if (
                code <= _HIGH_SURROGATE_END
                and index + 1 < length
                and _LOW_SURROGATE_START <= ord(value[index + 1]) <= _LOW_SURROGATE_END
            ):
                low = ord(value[index + 1])
                scalar = (
                    _SCALAR_BASE
                    + ((code - _HIGH_SURROGATE_START) << 10)
                    + (low - _LOW_SURROGATE_START)
                )
                pieces.append(chr(scalar))
                index += 2
                continue
            raise CanonicalJsonErrorV1("lone surrogate is not a Unicode scalar")
        if character in _ESCAPES:
            pieces.append(_ESCAPES[character])
        elif code < 0x20:
            pieces.append(f"\\u{code:04x}")
        else:
            pieces.append(character)
        index += 1
    return '"' + "".join(pieces) + '"'


def _encode(value: CanonicalValueV1) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, str):
        return _encode_string(value)
    if isinstance(value, Mapping):
        for key in value:
            if not isinstance(key, str):
                raise CanonicalJsonErrorV1("mapping keys must be strings")
        body = ",".join(
            _encode_string(key) + ":" + _encode(item)
            for key, item in sorted(value.items())
        )
        return "{" + body + "}"
    if isinstance(value, tuple):
        return "[" + ",".join(_encode(item) for item in value) + "]"
    raise CanonicalJsonErrorV1(f"forbidden value type: {type(value).__name__}")


def canonical_json_bytes(value: CanonicalValueV1) -> bytes:
    """Encode *value* into the sole canonical UTF-8 byte representation."""
    return _encode(value).encode("utf-8")

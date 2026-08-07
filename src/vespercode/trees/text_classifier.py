"""T10.1 legacy step 10.B: shared supported-text byte classification.

Every file tool and candidate operation classifies raw bytes exactly once
through this pure ``classify_supported_text`` contract under the SPEC
§4.2.2 and §4.3 rules: zero or one UTF-8 BOM, strict UTF-8 decoding to a
Unicode scalar value sequence, no U+0000, uniform LF or uniform CRLF (no
bare CR, no mixed newlines), and a final newline so ``TextMetadataV1`` is
uniquely constructible.  Invalid encoding, binary data, mixed newlines,
missing final newline, empty input, and any other unsupported combination
return the closed ``NON_TEXT_FILE`` variant instead of normalizing bytes.
Content storage, tree construction, normalization, and filesystem path
reads remain out of scope (GREEN-4).
"""

from __future__ import annotations

from typing import Annotated, Literal, TypeAlias

from pydantic import BaseModel, ConfigDict, Field

from vespercode.contracts.optional import PresentV1

_UTF8_BOM = b"\xef\xbb\xbf"
_LF_BYTES = b"\n"
_CRLF_BYTES = b"\r\n"
_LF_BYTE = 0x0A
_CR_BYTE = 0x0D


class TextMetadataV1(BaseModel):
    """SPEC §4.3: exact supported-text byte classification metadata."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    encoding: Literal["UTF8", "UTF8_BOM"]
    newline: Literal["LF", "CRLF"]
    final_newline: Literal[True]


class SupportedTextFileV1(BaseModel):
    """SPEC §4.2.2: the ``TEXT_FILE`` classification variant."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    kind: Literal["TEXT_FILE"]
    text_profile: PresentV1[TextMetadataV1]


class NonTextFileV1(BaseModel):
    """SPEC §4.2.2: the ``NON_TEXT_FILE`` classification variant.

    The name only means "does not satisfy the v1 supported-text contract";
    it does not claim the file is binary and is not a repository admission
    rejection.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)
    kind: Literal["NON_TEXT_FILE"]


TextFileClassificationV1: TypeAlias = Annotated[
    SupportedTextFileV1 | NonTextFileV1, Field(discriminator="kind")
]
"""SPEC §4.2.2: ``TEXT_FILE`` or ``NON_TEXT_FILE`` for one raw byte input."""


def classify_supported_text(raw_bytes: bytes) -> TextFileClassificationV1:
    """Classify ``raw_bytes`` exactly once under the v1 supported-text rules.

    Pure function: reads nothing, writes nothing, and never changes or
    normalizes its input bytes.
    """
    if raw_bytes.startswith(_UTF8_BOM):
        encoding: Literal["UTF8", "UTF8_BOM"] = "UTF8_BOM"
        body = raw_bytes[len(_UTF8_BOM) :]
    else:
        encoding = "UTF8"
        body = raw_bytes
    try:
        decoded = body.decode("utf-8")
    except UnicodeDecodeError:
        return NonTextFileV1(kind="NON_TEXT_FILE")
    if "\x00" in decoded:
        return NonTextFileV1(kind="NON_TEXT_FILE")
    has_crlf = False
    has_lf = False
    index = 0
    while index < len(body):
        if body[index] == _LF_BYTE:
            has_lf = True
            index += 1
        elif body[index] == _CR_BYTE:
            if index + 1 < len(body) and body[index + 1] == _LF_BYTE:
                has_crlf = True
                index += 2
            else:
                return NonTextFileV1(kind="NON_TEXT_FILE")  # bare CR
        else:
            index += 1
    if has_crlf and has_lf:
        return NonTextFileV1(kind="NON_TEXT_FILE")  # mixed CRLF and LF
    newline: Literal["LF", "CRLF"] = "CRLF" if has_crlf else "LF"
    final_newline_bytes = _CRLF_BYTES if newline == "CRLF" else _LF_BYTES
    if not body.endswith(final_newline_bytes):
        return NonTextFileV1(kind="NON_TEXT_FILE")  # missing final newline
    return SupportedTextFileV1(
        kind="TEXT_FILE",
        text_profile=PresentV1(
            kind="PRESENT",
            value=TextMetadataV1(
                encoding=encoding, newline=newline, final_newline=True
            ),
        ),
    )

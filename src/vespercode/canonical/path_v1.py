"""T04.2 legacy step 4.D: lexical canonical relative path validation.

``CanonicalRelativePathV1`` is the sole string contract for repository
locations: a non-empty ``/``-separated relative path with no leading or
trailing slash, no ``.``/``..``/empty segments, no absolute, UNC, drive,
ADS, device, or backslash forms, no trailing dot/space segments, no
reserved device names, and no Windows case-fold or Unicode normalization
collision between two distinct segments.  Validation is purely lexical
with one closed deterministic error code per rejected form: no
normalization, no case folding of the stored value, no filesystem access,
and no alias resolution.  Final-object identity, ancestry, alias, reparse,
ADS, and link authorization remain Tasks 9.A and 9.D (GREEN-4).
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Final, Literal

PathRejectionCodeV1 = Literal[
    "PATH_NOT_STRING",
    "PATH_EMPTY",
    "PATH_ROOT",
    "PATH_UNC",
    "PATH_ABSOLUTE",
    "PATH_DRIVE",
    "PATH_ADS",
    "PATH_BACKSLASH",
    "PATH_INVALID_CHARACTER",
    "PATH_EMPTY_SEGMENT",
    "PATH_DOT",
    "PATH_PARENT",
    "PATH_TRAILING_DOT_OR_SPACE",
    "PATH_RESERVED_NAME",
    "PATH_CASE_COLLISION",
    "PATH_UNICODE_COLLISION",
]

_DRIVE_PREFIX_RE: Final = re.compile(r"^[A-Za-z]:")
_RESERVED_DEVICE_NAMES: Final = frozenset(
    name.casefold()
    for name in {"CON", "PRN", "AUX", "NUL"}
    | {f"COM{index}" for index in range(1, 10)}
    | {f"LPT{index}" for index in range(1, 10)}
)
_INVALID_CHARACTERS: Final = frozenset('<>"|?*')


class CanonicalPathErrorV1(ValueError):
    """Closed rejection for an unsupported lexical path form."""

    def __init__(self, error_code: PathRejectionCodeV1, value: str) -> None:
        super().__init__(f"{error_code}: {value!r}")
        self.error_code = error_code
        self.value = value


def _reject(error_code: PathRejectionCodeV1, value: str) -> None:
    raise CanonicalPathErrorV1(error_code, value)


def _validate(value: str) -> None:
    if not isinstance(value, str):
        _reject("PATH_NOT_STRING", repr(value))
    if value == "":
        _reject("PATH_EMPTY", value)
    if value in (".", "./", "/"):
        _reject("PATH_ROOT", value)
    if value.startswith("//"):
        _reject("PATH_UNC", value)
    if value.startswith("/"):
        _reject("PATH_ABSOLUTE", value)
    if _DRIVE_PREFIX_RE.match(value) is not None:
        _reject("PATH_DRIVE", value)
    if ":" in value:
        _reject("PATH_ADS", value)
    if "\\" in value:
        _reject("PATH_BACKSLASH", value)
    for character in value:
        if character in _INVALID_CHARACTERS or ord(character) < 0x20:
            _reject("PATH_INVALID_CHARACTER", value)
    segments = value.split("/")
    if any(segment == "" for segment in segments):
        _reject("PATH_EMPTY_SEGMENT", value)
    if any(segment == "." for segment in segments):
        _reject("PATH_DOT", value)
    if any(segment == ".." for segment in segments):
        _reject("PATH_PARENT", value)
    if any(segment.endswith((".", " ")) for segment in segments):
        _reject("PATH_TRAILING_DOT_OR_SPACE", value)
    for segment in segments:
        base = segment.split(".", 1)[0].casefold()
        if base in _RESERVED_DEVICE_NAMES:
            _reject("PATH_RESERVED_NAME", value)
    _check_collisions(segments, value)


def _check_collisions(segments: list[str], value: str) -> None:
    """Reject two distinct segments that Windows case-fold or NFC collide.

    Identical repeated segments (``a/a``) remain valid; only two distinct
    spellings that Windows treats as one object are ambiguous and rejected.
    """
    folded_seen: dict[str, str] = {}
    for segment in segments:
        folded = segment.casefold()
        if folded in folded_seen and folded_seen[folded] != segment:
            _reject("PATH_CASE_COLLISION", value)
        folded_seen[folded] = segment
    normalized_seen: dict[str, str] = {}
    for segment in segments:
        normalized = unicodedata.normalize("NFC", segment)
        if normalized in normalized_seen and normalized_seen[normalized] != segment:
            _reject("PATH_UNICODE_COLLISION", value)
        normalized_seen[normalized] = segment


@dataclass(frozen=True)
class CanonicalRelativePathV1:
    """One validated canonical repository-relative path.

    ``value`` is always canonical: the accepted lexical input is stored
    verbatim and every unsupported form is rejected before construction.
    """

    value: str

    def __post_init__(self) -> None:
        _validate(self.value)


def validate_canonical_relative_path(value: str) -> CanonicalRelativePathV1:
    """Validate one lexical string into the sole canonical representation."""
    return CanonicalRelativePathV1(value)

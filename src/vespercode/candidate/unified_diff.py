"""T12.1 legacy step 12.A: strict UNIFIED_DIFF_V1 parser.

``parse_unified_diff_v1`` parses the complete no-BOM UTF-8/LF
``UNIFIED_DIFF_V1`` grammar into one closed parsed patch or returns one
closed parse failure without deriving any candidate state.  The grammar is
deliberately closed: only standard ``--- a/path`` / ``+++ b/path`` headers
(``--- /dev/null`` for new files), strict ``@@ -old +new @@`` hunks, and
LF-only content with a final newline are accepted.  DELETE, RENAME,
case-only path changes, mode/rename/binary extended headers, timestamps,
no-newline markers, duplicate or colliding entry paths, malformed
headers/ranges/hunks, document-level encoding violations (BOM, CR, NUL),
and any trailing unparsed bytes all reject with a deterministic closed
failure (``PATCH_SCHEMA_INVALID`` for malformed forms,
``UNSUPPORTED_PATCH_OPERATION`` for recognized-but-unsupported operation
forms).  Tree reads, old-byte matching, edit application, candidate
limits, path authorization, and revision publication remain out of scope
(GREEN-4).

Recorded strictness interpretation: header paths must contain no
whitespace, so a timestamp (or any trailing content) on a file header is
never silently absorbed into the path — it rejects closed instead.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Literal

from pydantic import BaseModel, ConfigDict, StrictStr, field_validator, model_validator

from vespercode.canonical.path_v1 import (
    CanonicalPathErrorV1,
    CanonicalRelativePathV1,
)

PatchParseErrorCodeV1 = Literal["PATCH_SCHEMA_INVALID", "UNSUPPORTED_PATCH_OPERATION"]
"""The closed parse-failure codes: malformed form, or a recognized but
unsupported operation form (delete, rename, mode, binary)."""

_HUNK_HEADER_RE = re.compile(r"^@@ -([0-9]+(?:,[0-9]+)?) \+([0-9]+(?:,[0-9]+)?) @@$")
_RANGE_RE = re.compile(r"^([0-9]+)(?:,([0-9]+))?$")

_OLD_DEV_NULL = "/dev/null"
_HEADER_OLD_PREFIX = "--- "
_HEADER_NEW_PREFIX = "+++ "
_OLD_A_PREFIX = "a/"
_NEW_B_PREFIX = "b/"

# Git's extended diff headers that v1 rejects as unsupported operations.
_KNOWN_EXTENDED_HEADERS: frozenset[str] = frozenset(
    {
        "old mode ",
        "new mode ",
        "new file mode ",
        "deleted file mode ",
        "rename from ",
        "rename to ",
        "copy from ",
        "copy to ",
        "similarity index ",
        "dissimilarity index ",
        "index ",
        "GIT binary patch",
    }
)


class UnifiedDiffHunkLineV1(BaseModel):
    """One hunk content line: the closed prefix kind plus its exact text."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    kind: Literal["CONTEXT", "DELETE", "ADD"]
    text: StrictStr


class UnifiedDiffHunkV1(BaseModel):
    """One strict hunk: declared ranges plus exactly matching content lines.

    ``old_count`` must equal the number of context and delete lines and
    ``new_count`` the number of context and add lines; a hunk always has at
    least one line; a positive count requires a positive 1-based start (a
    zero start is legal only with a zero count, e.g. ``-0,0`` for a new
    file or a pure insertion before line 1).
    """

    model_config = ConfigDict(extra="forbid", frozen=True)
    old_start: int
    old_count: int
    new_start: int
    new_count: int
    lines: tuple[UnifiedDiffHunkLineV1, ...]

    @field_validator("old_start", "old_count", "new_start", "new_count", mode="before")
    @classmethod
    def _exact_decimal(cls, value: object) -> object:
        if not isinstance(value, int) or isinstance(value, bool):
            raise ValueError("hunk range fields must be exact decimal integers")
        return value

    @model_validator(mode="after")
    def _require_exact_closed_ranges(self) -> UnifiedDiffHunkV1:
        if not self.lines:
            raise ValueError("a hunk must contain at least one content line")
        old_lines = sum(1 for line in self.lines if line.kind in ("CONTEXT", "DELETE"))
        new_lines = sum(1 for line in self.lines if line.kind in ("CONTEXT", "ADD"))
        if self.old_count != old_lines:
            raise ValueError("old_count must equal the context and delete lines")
        if self.new_count != new_lines:
            raise ValueError("new_count must equal the context and add lines")
        if self.old_count > 0 and self.old_start < 1:
            raise ValueError("a positive old count requires a 1-based old start")
        if self.new_count > 0 and self.new_start < 1:
            raise ValueError("a positive new count requires a 1-based new start")
        return self


class ParsedPatchEntryV1(BaseModel):
    """One parsed file entry: operation, exact header paths, and hunks.

    ``path`` is the canonical new-side path; ``old_path``/``new_path`` keep
    the exact header strings (``a/<path>`` / ``b/<path>`` or ``/dev/null``).
    """

    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal[1]
    operation: Literal["CREATE", "REPLACE"]
    path: CanonicalRelativePathV1
    old_path: StrictStr
    new_path: StrictStr
    hunks: tuple[UnifiedDiffHunkV1, ...]

    @field_validator("schema_version", mode="before")
    @classmethod
    def _schema_version_is_exact_int(cls, value: object) -> object:
        if not isinstance(value, int) or isinstance(value, bool):
            raise ValueError("schema_version must be the decimal integer 1")
        return value

    @model_validator(mode="after")
    def _require_at_least_one_hunk(self) -> ParsedPatchEntryV1:
        if not self.hunks:
            raise ValueError("a patch entry must contain at least one hunk")
        if self.operation == "CREATE":
            for hunk in self.hunks:
                if (hunk.old_start, hunk.old_count) != (0, 0):
                    raise ValueError(
                        "CREATE entries must declare an empty old side in every hunk"
                    )
        return self


class ParsedPatchV1(BaseModel):
    """One closed parsed patch: the ordered unique entry tuple."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    kind: Literal["PATCH_PARSED"]
    entries: tuple[ParsedPatchEntryV1, ...]


class PatchParseFailureV1(BaseModel):
    """One closed parse failure: the stable code and a bounded reason."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    kind: Literal["PATCH_PARSE_FAILED"]
    error_code: PatchParseErrorCodeV1
    reason: StrictStr


class _UnsupportedPatchOperation(Exception):
    """Internal signal: a recognized but unsupported operation form.

    Raised inside the grammar walk and converted by the parse entry point
    into the single closed ``UNSUPPORTED_PATCH_OPERATION`` failure, so the
    parser always returns a result and never leaks internal exceptions.
    """

    def __init__(self, operation: str) -> None:
        super().__init__(f"unsupported patch operation: {operation}")
        self.operation = operation


def parse_unified_diff_v1(patch_text: str) -> ParsedPatchV1 | PatchParseFailureV1:
    """Parse the complete strict UNIFIED_DIFF_V1 grammar or fail closed.

    Pure function: reads nothing, writes nothing, and derives no candidate
    state; the same input always returns the same closed result.
    """
    if not isinstance(patch_text, str):
        raise TypeError("patch text must be a no-BOM UTF-8 str")
    document_failure = _document_failure(patch_text)
    if document_failure is not None:
        return document_failure
    # The final newline is required, so the split always ends with "".
    body = patch_text.split("\n")[:-1]
    entries: list[ParsedPatchEntryV1] = []
    index = 0
    try:
        while index < len(body):
            if not body[index].startswith(_HEADER_OLD_PREFIX):
                return _failure(
                    "PATCH_SCHEMA_INVALID",
                    "expected a --- file header at line " + str(index + 1),
                )
            parsed = _parse_entry(body, index)
            if parsed is None:
                return _failure(
                    "PATCH_SCHEMA_INVALID",
                    "malformed file entry starting at line " + str(index + 1),
                )
            entry, index = parsed
            entries.append(entry)
            if index == len(body):
                break
            if body[index] == "":
                # One blank line separates file entries; the next line must
                # be another header, so a trailing blank line is unparsed.
                index += 1
                if index == len(body):
                    return _failure(
                        "PATCH_SCHEMA_INVALID",
                        "the patch ends with a trailing blank line",
                    )
                continue
            return _failure(
                "PATCH_SCHEMA_INVALID",
                "unexpected content after a file entry at line " + str(index + 1),
            )
    except _UnsupportedPatchOperation as error:
        return _failure("UNSUPPORTED_PATCH_OPERATION", str(error))
    uniqueness_failure = _entry_uniqueness_failure(entries)
    if uniqueness_failure is not None:
        return uniqueness_failure
    return ParsedPatchV1(kind="PATCH_PARSED", entries=tuple(entries))


def _document_failure(patch_text: str) -> PatchParseFailureV1 | None:
    """One closed document-level encoding failure, or None."""
    if patch_text == "":
        return _failure("PATCH_SCHEMA_INVALID", "the patch document is empty")
    if patch_text.startswith("﻿"):
        return _failure(
            "PATCH_SCHEMA_INVALID", "the patch document must be no-BOM UTF-8"
        )
    if "\r" in patch_text:
        return _failure(
            "PATCH_SCHEMA_INVALID", "the patch document must use LF line endings only"
        )
    if "\x00" in patch_text:
        return _failure(
            "PATCH_SCHEMA_INVALID", "the patch document must not contain NUL bytes"
        )
    if not patch_text.endswith("\n"):
        return _failure(
            "PATCH_SCHEMA_INVALID", "the patch document must end with a final newline"
        )
    return None


def _parse_entry(body: list[str], index: int) -> tuple[ParsedPatchEntryV1, int] | None:
    """Parse one file entry at *index*; return the entry and the next index."""
    old_header = body[index]
    if index + 1 >= len(body) or not body[index + 1].startswith(_HEADER_NEW_PREFIX):
        return None
    new_header = body[index + 1]
    headers = _parse_headers(old_header, new_header)
    if headers is None:
        return None
    old_path, new_path, path, operation = headers
    index += 2
    hunks: list[UnifiedDiffHunkV1] = []
    previous_end: int | None = None
    while index < len(body):
        if body[index].startswith("@@ -"):
            parsed_hunk = _parse_hunk(body, index)
            if parsed_hunk is None:
                return None
            hunk, index = parsed_hunk
            if previous_end is not None and hunk.old_start < previous_end:
                return None  # overlapping ranges cannot chain exactly
            previous_end = hunk.old_start + hunk.old_count
            hunks.append(hunk)
        elif _is_known_extended_header(body[index]):
            # A mode/rename/binary extended header before or between hunks
            # is an unsupported operation form, not a malformed line.
            raise _UnsupportedPatchOperation(body[index].split(" ", 1)[0])
        else:
            break
    if not hunks:
        return None
    return (
        ParsedPatchEntryV1(
            schema_version=1,
            operation=operation,
            path=path,
            old_path=old_path,
            new_path=new_path,
            hunks=tuple(hunks),
        ),
        index,
    )


def _parse_headers(
    old_header: str, new_header: str
) -> tuple[str, str, CanonicalRelativePathV1, Literal["CREATE", "REPLACE"]] | None:
    """Parse the two file headers into (old, new, canonical path, operation).

    Returns ``None`` when any header is malformed (schema-invalid form);
    recognized-but-unsupported operation forms (DELETE, RENAME, case-only
    changes) raise the closed unsupported-operation signal.
    """
    if old_header == _HEADER_OLD_PREFIX + _OLD_DEV_NULL:
        old_path = _OLD_DEV_NULL
        operation: Literal["CREATE", "REPLACE"] = "CREATE"
    elif old_header.startswith(_HEADER_OLD_PREFIX + _OLD_A_PREFIX):
        old_path = old_header[len(_HEADER_OLD_PREFIX) :]
        operation = "REPLACE"
    else:
        return None
    if new_header == _HEADER_NEW_PREFIX + "/dev/null":
        if operation == "CREATE":
            return None  # /dev/null on both sides is not a file change
        raise _UnsupportedPatchOperation("DELETE")
    if not new_header.startswith(_HEADER_NEW_PREFIX + _NEW_B_PREFIX):
        return None
    new_path = new_header[len(_HEADER_NEW_PREFIX) :]
    path = _canonical_header_path(new_path[len(_NEW_B_PREFIX) :])
    if path is None:
        return None
    if operation == "REPLACE" and old_path != _OLD_A_PREFIX + path.value:
        # Any old-side path that differs from the new-side path — including
        # a case-only spelling change — is a rename-family form.
        raise _UnsupportedPatchOperation("RENAME")
    return old_path, new_path, path, operation


def _canonical_header_path(value: str) -> CanonicalRelativePathV1 | None:
    """Validate one header path under the strict grammar.

    Header paths may contain no whitespace (a timestamp or any trailing
    content can never be absorbed into the path), must be non-empty, and
    must be canonical repository-relative paths.
    """
    if value == "":
        return None
    for character in value:
        if character.isspace():
            return None
    try:
        return CanonicalRelativePathV1(value)
    except CanonicalPathErrorV1:
        return None


def _parse_hunk(body: list[str], index: int) -> tuple[UnifiedDiffHunkV1, int] | None:
    """Parse one hunk header and its exact content lines."""
    match = _HUNK_HEADER_RE.fullmatch(body[index])
    if match is None:
        return None
    old_range = _parse_range(match.group(1))
    new_range = _parse_range(match.group(2))
    if old_range is None or new_range is None:
        return None
    old_start, old_count = old_range
    new_start, new_count = new_range
    if old_count > 0 and old_start < 1:
        return None
    if new_count > 0 and new_start < 1:
        return None
    index += 1
    lines: list[UnifiedDiffHunkLineV1] = []
    while index < len(body):
        line = body[index]
        if line == "" or line.startswith("@@ -") or line.startswith(_HEADER_OLD_PREFIX):
            break
        if line.startswith(" "):
            lines.append(UnifiedDiffHunkLineV1(kind="CONTEXT", text=line[1:]))
        elif line.startswith("-"):
            lines.append(UnifiedDiffHunkLineV1(kind="DELETE", text=line[1:]))
        elif line.startswith("+"):
            lines.append(UnifiedDiffHunkLineV1(kind="ADD", text=line[1:]))
        elif _is_known_extended_header(line):
            # A mode/rename/binary extended header inside an entry is an
            # unsupported operation form, not a malformed line.
            raise _UnsupportedPatchOperation(line.split(" ", 1)[0])
        else:
            return None
        index += 1
    if not lines:
        return None
    if old_count != sum(1 for line in lines if line.kind in ("CONTEXT", "DELETE")):
        return None
    if new_count != sum(1 for line in lines if line.kind in ("CONTEXT", "ADD")):
        return None
    return (
        UnifiedDiffHunkV1(
            old_start=old_start,
            old_count=old_count,
            new_start=new_start,
            new_count=new_count,
            lines=tuple(lines),
        ),
        index,
    )


def _parse_range(text: str) -> tuple[int, int] | None:
    """Parse ``start`` or ``start,count`` (count defaults to 1)."""
    match = _RANGE_RE.fullmatch(text)
    if match is None:
        return None
    start = int(match.group(1))
    count = int(match.group(2)) if match.group(2) is not None else 1
    return start, count


def _is_known_extended_header(line: str) -> bool:
    """True for git extended headers v1 rejects as unsupported operations."""
    return any(line.startswith(prefix) for prefix in _KNOWN_EXTENDED_HEADERS)


def _entry_uniqueness_failure(
    entries: list[ParsedPatchEntryV1],
) -> PatchParseFailureV1 | None:
    """Reject duplicate, case-colliding, or Unicode-colliding entry paths."""
    exact: set[str] = set()
    folded: dict[str, str] = {}
    normalized: dict[str, str] = {}
    for entry in entries:
        path = entry.path.value
        if path in exact:
            return _failure(
                "PATCH_SCHEMA_INVALID", "duplicate entry path " + repr(path)
            )
        exact.add(path)
        key = path.casefold()
        if key in folded and folded[key] != path:
            return _failure(
                "PATCH_SCHEMA_INVALID",
                f"entry paths {folded[key]!r} and {path!r} case-collide",
            )
        folded[key] = path
        key = unicodedata.normalize("NFC", path)
        if key in normalized and normalized[key] != path:
            return _failure(
                "PATCH_SCHEMA_INVALID",
                f"entry paths {normalized[key]!r} and {path!r} unicode-collide",
            )
        normalized[key] = path
    return None


def _failure(error_code: PatchParseErrorCodeV1, reason: str) -> PatchParseFailureV1:
    return PatchParseFailureV1(
        kind="PATCH_PARSE_FAILED", error_code=error_code, reason=reason
    )

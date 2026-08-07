"""T11.1 legacy step 11.A: closed file-tool result contracts.

The three file tools share one closed result vocabulary under SPEC §4.2.2:
each tool has its own SUCCESS payload variant and one shared typed ERROR
variant with a stable ``error_code`` and bounded message; list entries use
the closed ``DIRECTORY | TEXT_FILE | NON_TEXT_FILE`` variants with their
exact size/text-profile combinations; and the two distinct canonical
cursor schemas bind the visible tree digest, the cursor-free query digest,
the next scan position, and a self digest that the owning tool computes at
issuance and re-verifies on every continuation (tampering fails closed as
``CONTINUATION_INVALID``, tree drift as ``CONTINUATION_STALE``).  The
shared bounded-read helpers live here because scalar-boundary artifact
truncation and newline-aware line splitting are result-contract properties
(GREEN-2).  Filesystem access, policy, shell, arbitrary path dispatch, and
tool dispatch remain out of scope (GREEN-4).
"""

from __future__ import annotations

from typing import Annotated, Final, Literal, TypeAlias

from pydantic import (
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    StrictBool,
    StrictStr,
    field_validator,
    model_validator,
)

from vespercode.canonical.digest import domain_digest
from vespercode.canonical.path_v1 import CanonicalRelativePathV1
from vespercode.contracts.evidence import _DIGEST_RE
from vespercode.contracts.optional import AbsentV1, PresentV1
from vespercode.trees.text_classifier import TextMetadataV1

FileToolErrorCodeV1 = Literal[
    "FILE_NOT_FOUND",
    "FILE_NOT_TEXT",
    "READ_RANGE_OUT_OF_BOUNDS",
    "PATH_NOT_DIRECTORY",
    "PATH_NOT_FOUND",
    "CONTINUATION_INVALID",
    "CONTINUATION_STALE",
]
"""Closed tool-level failure codes (SPEC §4.2.2/§4.2.8 vocabulary)."""

RESULT_BODY_BYTES_V1: Final = 32768
"""SPEC §5.1: one model-visible tool result body never exceeds 32 KiB."""


def _reject_non_exact_int(value: object) -> object:
    """Reject bool/float/str coercion before pydantic can widen an integer."""
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError("value must be an exact decimal integer")
    return value


def _reject_negative_int(value: object) -> object:
    if isinstance(value, int) and not isinstance(value, bool) and value < 0:
        raise ValueError("value must not be negative")
    return value


NonNegativeIntV1 = Annotated[
    int, BeforeValidator(_reject_non_exact_int), BeforeValidator(_reject_negative_int)
]
"""One exact non-negative decimal integer (bools rejected before coercion)."""


class FileToolErrorV1(BaseModel):
    """Closed typed tool failure: a stable code plus a bounded message."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    kind: Literal["ERROR"]
    error_code: FileToolErrorCodeV1
    bounded_message: StrictStr

    @field_validator("bounded_message")
    @classmethod
    def _bounded_message_is_non_empty(cls, value: str) -> str:
        if value == "":
            raise ValueError("bounded_message must be non-empty")
        return value


def file_tool_error(
    error_code: FileToolErrorCodeV1, bounded_message: str
) -> FileToolErrorV1:
    """One closed typed tool failure with a stable code and bounded message."""
    return FileToolErrorV1(
        kind="ERROR", error_code=error_code, bounded_message=bounded_message
    )


def validate_cursor_binding(
    *,
    family: Literal["list", "search"],
    computed_self_digest: str,
    claimed_self_digest: str,
    computed_query_digest: str,
    claimed_query_digest: str,
    visible_tree_digest: str,
    tree_digest: str,
) -> FileToolErrorV1 | None:
    """Bind one continuation before serving (SPEC §4.2.8).

    The precedence is fixed: an internally tampered cursor (self digest,
    query digest, or position) returns ``CONTINUATION_INVALID``, while a
    consistently bound cursor whose visible tree no longer matches returns
    ``CONTINUATION_STALE`` — both with zero partial results.
    """
    if computed_self_digest != claimed_self_digest:
        return file_tool_error(
            "CONTINUATION_INVALID",
            f"the {family} cursor's self-digest does not bind its fields",
        )
    if computed_query_digest != claimed_query_digest:
        return file_tool_error(
            "CONTINUATION_INVALID",
            f"the {family} cursor's query digest does not match this query",
        )
    if visible_tree_digest != tree_digest:
        return file_tool_error(
            "CONTINUATION_STALE",
            "the visible tree changed since this cursor was issued",
        )
    return None


def bounded_utf8_text(text: str, limit: int) -> str:
    """Truncate *text* to at most *limit* UTF-8 bytes at a scalar boundary.

    Pure and deterministic: the cut never splits a multi-byte UTF-8 scalar,
    so the result always decodes back to the exact same string.
    """
    raw = text.encode("utf-8")
    if len(raw) <= limit:
        return text
    cut = raw[:limit]
    while cut:
        try:
            return cut.decode("utf-8")
        except UnicodeDecodeError:
            cut = cut[:-1]
    return ""


def split_text_lines(text: str, terminator: str) -> list[str]:
    """Split one decoded supported-text body into its lines.

    A supported text file always ends with one final newline (T10.1), so
    the empty tail after the final terminator is the terminator itself, not
    an extra line.
    """
    lines = text.split(terminator)
    if lines and lines[-1] == "":
        lines.pop()
    return lines


class ReadFileSuccessV1(BaseModel):
    """SPEC §4.2.2 ``ReadFileResult``: the bounded read payload."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    kind: Literal["SUCCESS"]
    path: CanonicalRelativePathV1
    file_digest: str
    start_line: int
    end_line: int
    eof: StrictBool
    text: str

    @field_validator("file_digest")
    @classmethod
    def _file_digest_is_sha256_hex(cls, value: str) -> str:
        if _DIGEST_RE.fullmatch(value) is None:
            raise ValueError(
                "file_digest must be exactly 64 lowercase hexadecimal characters"
            )
        return value

    @field_validator("start_line", "end_line", mode="before")
    @classmethod
    def _lines_are_positive_exact_ints(cls, value: object) -> object:
        if not isinstance(value, int) or isinstance(value, bool):
            raise ValueError("lines must be exact decimal integers")
        if value < 1:
            raise ValueError("lines are 1-based and must be at least 1")
        return value

    @model_validator(mode="after")
    def _end_line_never_precedes_start_line(self) -> ReadFileSuccessV1:
        if self.end_line < self.start_line:
            raise ValueError("end_line must not precede start_line")
        return self


class ListFilesEntryDirectoryV1(BaseModel):
    """SPEC §4.2.2 ``DIRECTORY`` list entry: no size or text profile."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    kind: Literal["DIRECTORY"]
    path: CanonicalRelativePathV1
    size_bytes: AbsentV1
    text_profile: AbsentV1


class ListFilesEntryTextFileV1(BaseModel):
    """SPEC §4.2.2 ``TEXT_FILE`` list entry: exact size and text metadata."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    kind: Literal["TEXT_FILE"]
    path: CanonicalRelativePathV1
    size_bytes: PresentV1[NonNegativeIntV1]
    text_profile: PresentV1[TextMetadataV1]


class ListFilesEntryNonTextFileV1(BaseModel):
    """SPEC §4.2.2 ``NON_TEXT_FILE`` list entry: exact size, no profile."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    kind: Literal["NON_TEXT_FILE"]
    path: CanonicalRelativePathV1
    size_bytes: PresentV1[NonNegativeIntV1]
    text_profile: AbsentV1


ListFilesEntryV1: TypeAlias = Annotated[
    ListFilesEntryDirectoryV1 | ListFilesEntryTextFileV1 | ListFilesEntryNonTextFileV1,
    Field(discriminator="kind"),
]
"""SPEC §4.2.2 ``ListFilesEntryV1``: the closed three-variant list row."""


class ListFilesCursorV1(BaseModel):
    """SPEC §4.2.2 ``ListFilesCursorV1``: one canonical list continuation.

    The self ``digest`` binds every other field under the §0.1 domain;
    the owning tool computes it at issuance and re-verifies it on every
    continuation, so a tampered cursor is rejected with
    ``CONTINUATION_INVALID`` before any row is served.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal[1]
    cursor_type: Literal["LIST_FILES_CURSOR_V1"]
    visible_tree_digest: str
    query_digest: str
    next_directory_rank: Literal[0, 1]
    next_canonical_path: CanonicalRelativePathV1
    digest: str

    @field_validator("schema_version", mode="before")
    @classmethod
    def _schema_version_is_exact_int(cls, value: object) -> object:
        if not isinstance(value, int) or isinstance(value, bool):
            raise ValueError("schema_version must be the decimal integer 1")
        return value

    @field_validator("next_directory_rank", mode="before")
    @classmethod
    def _rank_is_exact(cls, value: object) -> object:
        if not isinstance(value, int) or isinstance(value, bool):
            raise ValueError("next_directory_rank must be the exact integer 0 or 1")
        return value

    @field_validator("visible_tree_digest", "query_digest", "digest")
    @classmethod
    def _digests_are_sha256_hex(cls, value: str) -> str:
        if _DIGEST_RE.fullmatch(value) is None:
            raise ValueError(
                "digests must be exactly 64 lowercase hexadecimal characters"
            )
        return value


def list_files_cursor_digest(cursor: ListFilesCursorV1) -> str:
    """Recompute the §0.1 self-digest a list cursor must bind."""
    return domain_digest(
        "ListFilesCursorV1",
        1,
        {
            "schema_version": 1,
            "cursor_type": "LIST_FILES_CURSOR_V1",
            "visible_tree_digest": cursor.visible_tree_digest,
            "query_digest": cursor.query_digest,
            "next_directory_rank": cursor.next_directory_rank,
            "next_canonical_path": cursor.next_canonical_path.value,
        },
    )


OptionalListFilesCursorV1: TypeAlias = Annotated[
    AbsentV1 | PresentV1[ListFilesCursorV1], Field(discriminator="kind")
]
"""SPEC §4.2.2 ``OptionalListFilesCursorV1``."""


class ListFilesSuccessV1(BaseModel):
    """SPEC §4.2.2 ``ListFilesResult``: entries, truncation, and cursor."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    kind: Literal["SUCCESS"]
    entries: tuple[ListFilesEntryV1, ...]
    truncated: StrictBool
    next_cursor: OptionalListFilesCursorV1

    @model_validator(mode="after")
    def _truncation_agrees_with_cursor(self) -> ListFilesSuccessV1:
        if self.truncated != (self.next_cursor.kind == "PRESENT"):
            raise ValueError(
                "truncated must be true exactly when next_cursor is PRESENT"
            )
        return self


class SearchTextMatchV1(BaseModel):
    """SPEC §4.2.2 ``SearchTextResult`` match: path and 1-based line/column."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    path: CanonicalRelativePathV1
    line: int
    column: int
    excerpt: str

    @field_validator("line", "column", mode="before")
    @classmethod
    def _positions_are_positive_exact_ints(cls, value: object) -> object:
        if not isinstance(value, int) or isinstance(value, bool):
            raise ValueError("line and column must be exact decimal integers")
        if value < 1:
            raise ValueError("line and column are 1-based and must be at least 1")
        return value


class SearchTextCursorV1(BaseModel):
    """SPEC §4.2.2 ``SearchTextCursorV1``: one canonical search continuation.

    The self ``digest`` binds every other field under the §0.1 domain;
    the owning tool computes it at issuance and re-verifies it on every
    continuation, so a tampered cursor is rejected with
    ``CONTINUATION_INVALID`` before any match is served.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal[1]
    cursor_type: Literal["SEARCH_TEXT_CURSOR_V1"]
    visible_tree_digest: str
    query_digest: str
    next_canonical_path: CanonicalRelativePathV1
    next_match_index: NonNegativeIntV1
    digest: str

    @field_validator("schema_version", mode="before")
    @classmethod
    def _schema_version_is_exact_int(cls, value: object) -> object:
        if not isinstance(value, int) or isinstance(value, bool):
            raise ValueError("schema_version must be the decimal integer 1")
        return value

    @field_validator("visible_tree_digest", "query_digest", "digest")
    @classmethod
    def _digests_are_sha256_hex(cls, value: str) -> str:
        if _DIGEST_RE.fullmatch(value) is None:
            raise ValueError(
                "digests must be exactly 64 lowercase hexadecimal characters"
            )
        return value


def search_text_cursor_digest(cursor: SearchTextCursorV1) -> str:
    """Recompute the §0.1 self-digest a search cursor must bind."""
    return domain_digest(
        "SearchTextCursorV1",
        1,
        {
            "schema_version": 1,
            "cursor_type": "SEARCH_TEXT_CURSOR_V1",
            "visible_tree_digest": cursor.visible_tree_digest,
            "query_digest": cursor.query_digest,
            "next_canonical_path": cursor.next_canonical_path.value,
            "next_match_index": cursor.next_match_index,
        },
    )


OptionalSearchTextCursorV1: TypeAlias = Annotated[
    AbsentV1 | PresentV1[SearchTextCursorV1], Field(discriminator="kind")
]
"""SPEC §4.2.2 ``OptionalSearchTextCursorV1``."""


class SearchTextSuccessV1(BaseModel):
    """SPEC §4.2.2 ``SearchTextResult``: matches, cursor, and skip count."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    kind: Literal["SUCCESS"]
    matches: tuple[SearchTextMatchV1, ...]
    truncated: StrictBool
    next_cursor: OptionalSearchTextCursorV1
    skipped_non_text_count: NonNegativeIntV1

    @model_validator(mode="after")
    def _truncation_agrees_with_cursor(self) -> SearchTextSuccessV1:
        if self.truncated != (self.next_cursor.kind == "PRESENT"):
            raise ValueError(
                "truncated must be true exactly when next_cursor is PRESENT"
            )
        return self


ReadFileResultV1: TypeAlias = Annotated[
    ReadFileSuccessV1 | FileToolErrorV1, Field(discriminator="kind")
]
"""SPEC §4.2.2: one closed read outcome (SUCCESS payload or typed error)."""

ListFilesResultV1: TypeAlias = Annotated[
    ListFilesSuccessV1 | FileToolErrorV1, Field(discriminator="kind")
]
"""SPEC §4.2.2: one closed list outcome (SUCCESS payload or typed error)."""

SearchTextResultV1: TypeAlias = Annotated[
    SearchTextSuccessV1 | FileToolErrorV1, Field(discriminator="kind")
]
"""SPEC §4.2.2: one closed search outcome (SUCCESS payload or typed error)."""

FileToolResultV1: TypeAlias = ListFilesResultV1 | ReadFileResultV1 | SearchTextResultV1
"""Task 11.A/11.B: the closed file-tool result union for dispatch."""

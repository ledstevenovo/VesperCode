"""T11.1 legacy step 11.A: closed file-tool action schemas.

The three file actions are closed pydantic schemas under SPEC §4.2.2:
every field is required, unknown fields and wrong types (including bool
coercion to integers and integers to booleans) are rejected, each range
bound is enforced before any tool execution, and the ``ListFilesQueryV1``
/ ``SearchTextQueryV1`` digests bind exactly the cursor-free query fields
so a continuation can never change the query identity it carries.  The
actions carry no path-policy, phase, or dispatch fields — those remain
with the Run's frozen policy and the dispatcher (GREEN-4).
"""

from __future__ import annotations

import unicodedata
from typing import Literal, TypeAlias

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    field_validator,
    model_validator,
)

from vespercode.canonical.digest import domain_digest
from vespercode.canonical.json_v1 import CanonicalValueV1
from vespercode.canonical.path_v1 import CanonicalRelativePathV1
from vespercode.contracts.location import RepositoryLocationV1
from vespercode.tools.file_results import (
    OptionalListFilesCursorV1,
    OptionalSearchTextCursorV1,
)


def _canonical_location(location: RepositoryLocationV1) -> CanonicalValueV1:
    """One §0.1 canonical value for a repository location."""
    if location.kind == "ROOT":
        return {"kind": "ROOT"}
    return {"kind": "PATH", "path": location.path.value}


class ListFilesActionV1(BaseModel):
    """SPEC §4.2.2 ``ListFilesAction``: root, recursion, page bound, cursor."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal[1]
    action_type: Literal["list_files"]
    root: RepositoryLocationV1
    recursive: StrictBool
    max_entries: int
    cursor: OptionalListFilesCursorV1

    @field_validator("schema_version", mode="before")
    @classmethod
    def _schema_version_is_exact_int(cls, value: object) -> object:
        if not isinstance(value, int) or isinstance(value, bool):
            raise ValueError("schema_version must be the decimal integer 1")
        return value

    @field_validator("max_entries", mode="before")
    @classmethod
    def _max_entries_bounds(cls, value: object) -> object:
        if not isinstance(value, int) or isinstance(value, bool):
            raise ValueError("max_entries must be an exact decimal integer")
        if not 1 <= value <= 500:
            raise ValueError("max_entries must be within 1..500")
        return value


class ReadFileActionV1(BaseModel):
    """SPEC §4.2.2 ``ReadFileAction``: one bounded line-range read."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal[1]
    action_type: Literal["read_file"]
    path: CanonicalRelativePathV1
    start_line: int
    line_count: int
    max_bytes: int

    @field_validator("schema_version", mode="before")
    @classmethod
    def _schema_version_is_exact_int(cls, value: object) -> object:
        if not isinstance(value, int) or isinstance(value, bool):
            raise ValueError("schema_version must be the decimal integer 1")
        return value

    @field_validator("start_line", mode="before")
    @classmethod
    def _start_line_is_positive(cls, value: object) -> object:
        if not isinstance(value, int) or isinstance(value, bool):
            raise ValueError("start_line must be an exact decimal integer")
        if value < 1:
            raise ValueError("start_line must be at least 1")
        return value

    @field_validator("line_count", mode="before")
    @classmethod
    def _line_count_bounds(cls, value: object) -> object:
        if not isinstance(value, int) or isinstance(value, bool):
            raise ValueError("line_count must be an exact decimal integer")
        if not 1 <= value <= 400:
            raise ValueError("line_count must be within 1..400")
        return value

    @field_validator("max_bytes", mode="before")
    @classmethod
    def _max_bytes_bounds(cls, value: object) -> object:
        if not isinstance(value, int) or isinstance(value, bool):
            raise ValueError("max_bytes must be an exact decimal integer")
        if not 1 <= value <= 32768:
            raise ValueError("max_bytes must be within 1..32768")
        return value


class SearchTextActionV1(BaseModel):
    """SPEC §4.2.2 ``SearchTextAction``: literal query, roots, matching, cursor."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal[1]
    action_type: Literal["search_text"]
    query: str
    roots: tuple[RepositoryLocationV1, ...] = Field(min_length=1, max_length=8)
    case_sensitive: StrictBool
    context_lines: int
    max_results: int
    cursor: OptionalSearchTextCursorV1

    @field_validator("schema_version", mode="before")
    @classmethod
    def _schema_version_is_exact_int(cls, value: object) -> object:
        if not isinstance(value, int) or isinstance(value, bool):
            raise ValueError("schema_version must be the decimal integer 1")
        return value

    @field_validator("query", mode="before")
    @classmethod
    def _query_is_literal_utf8_1_256_bytes(cls, value: object) -> object:
        if not isinstance(value, str):
            raise ValueError("query must be a literal UTF-8 string")
        try:
            byte_size = len(value.encode("utf-8"))
        except UnicodeEncodeError as error:
            raise ValueError(
                "query must be a strict-UTF-8 encodable literal string"
            ) from error
        if not 1 <= byte_size <= 256:
            raise ValueError("query must be 1..256 UTF-8 bytes")
        return value

    @field_validator("context_lines", mode="before")
    @classmethod
    def _context_lines_bounds(cls, value: object) -> object:
        if not isinstance(value, int) or isinstance(value, bool):
            raise ValueError("context_lines must be an exact decimal integer")
        if not 0 <= value <= 2:
            raise ValueError("context_lines must be within 0..2")
        return value

    @field_validator("max_results", mode="before")
    @classmethod
    def _max_results_bounds(cls, value: object) -> object:
        if not isinstance(value, int) or isinstance(value, bool):
            raise ValueError("max_results must be an exact decimal integer")
        if not 1 <= value <= 100:
            raise ValueError("max_results must be within 1..100")
        return value

    @model_validator(mode="after")
    def _roots_are_unique_and_non_aliasing(self) -> SearchTextActionV1:
        paths = [root.path.value for root in self.roots if root.kind == "PATH"]
        if len(paths) != len(set(paths)):
            raise ValueError("search roots must not repeat a path")
        if "ROOT" in {root.kind for root in self.roots} and len(self.roots) != 1:
            raise ValueError("ROOT must be the only search root when present")
        folded: dict[str, str] = {}
        normalized: dict[str, str] = {}
        composed: dict[str, str] = {}
        for path in paths:
            key = path.casefold()
            if key in folded and folded[key] != path:
                raise ValueError(
                    f"search roots {folded[key]!r} and {path!r} alias under "
                    "case folding"
                )
            folded[key] = path
            key = unicodedata.normalize("NFC", path)
            if key in normalized and normalized[key] != path:
                raise ValueError(
                    f"search roots {normalized[key]!r} and {path!r} alias under NFC"
                )
            normalized[key] = path
            key = unicodedata.normalize("NFC", path).casefold()
            if key in composed and composed[key] != path:
                raise ValueError(
                    f"search roots {composed[key]!r} and {path!r} alias under "
                    "NFC-then-casefold"
                )
            composed[key] = path
        return self


FileToolActionV1: TypeAlias = ListFilesActionV1 | ReadFileActionV1 | SearchTextActionV1
"""Task 11.A: the closed file-tool action union for parsing and dispatch."""


def list_files_query_digest(action: ListFilesActionV1) -> str:
    """SPEC §4.2.2 ``ListFilesQueryV1.digest``: the cursor-free query identity.

    Binds exactly the query fields of the action — never the cursor, so a
    continuation cannot change the query it carries.
    """
    return domain_digest(
        "ListFilesQueryV1",
        1,
        {
            "schema_version": 1,
            "root": _canonical_location(action.root),
            "recursive": action.recursive,
            "max_entries": action.max_entries,
        },
    )


def search_text_query_digest(action: SearchTextActionV1) -> str:
    """SPEC §4.2.2 ``SearchTextQueryV1.digest``: the cursor-free query identity.

    Binds exactly the query fields of the action — never the cursor, so a
    continuation cannot change the query it carries.
    """
    return domain_digest(
        "SearchTextQueryV1",
        1,
        {
            "schema_version": 1,
            "query": action.query,
            "roots": tuple(_canonical_location(root) for root in action.roots),
            "case_sensitive": action.case_sensitive,
            "context_lines": action.context_lines,
            "max_results": action.max_results,
        },
    )

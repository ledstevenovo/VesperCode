"""T11.1 legacy step 11.B: stable paged discovery over one immutable tree.

``list_files`` observes the bound ``ReadableTreeV1`` protocol only: every
entry is derived from the visible tree's raw bytes (shared T10.1
classifier), sorted by the stable ``(directory_rank, canonical_path)``
key, bounded by ``max_entries`` and the 32 KiB result body, and continued
with the canonical list cursor.  The cursor binds the visible tree digest,
the cursor-free query digest, the next scan position, and its own digest;
a tampered cursor is rejected with ``CONTINUATION_INVALID`` and a tree
drift with ``CONTINUATION_STALE``, both with zero partial rows.
Filesystem access, arbitrary paths, shell execution, policy mutation, and
cross-tool cursor reuse remain out of scope (GREEN-4).
"""

from __future__ import annotations

from typing import Literal

from vespercode.canonical.json_v1 import CanonicalValueV1, canonical_json_bytes
from vespercode.canonical.path_v1 import CanonicalRelativePathV1
from vespercode.contracts.location import RepositoryLocationV1
from vespercode.contracts.optional import AbsentV1, PresentV1
from vespercode.tools.file_actions import ListFilesActionV1, list_files_query_digest
from vespercode.tools.file_results import (
    RESULT_BODY_BYTES_V1,
    FileToolErrorV1,
    ListFilesCursorV1,
    ListFilesEntryDirectoryV1,
    ListFilesEntryNonTextFileV1,
    ListFilesEntryTextFileV1,
    ListFilesEntryV1,
    ListFilesResultV1,
    ListFilesSuccessV1,
    file_tool_error,
    list_files_cursor_digest,
    validate_cursor_binding,
)
from vespercode.trees.readable import ReadableTreeV1
from vespercode.trees.text_classifier import classify_supported_text


def list_files(tree: ReadableTreeV1, action: ListFilesActionV1) -> ListFilesResultV1:
    """List the visible tree's entries in stable ``(rank, path)`` order.

    Directories (rank 0) come first, then every file (rank 1) sorted by
    canonical path only; the page is bounded by ``max_entries`` and the
    32 KiB result body, and a bound continuation reproduces the unpaged
    result exactly without duplicates or omissions.
    """
    if action.cursor.kind == "PRESENT":
        invalid = _validate_list_cursor(tree, action, action.cursor.value)
        if invalid is not None:
            return invalid
    scope = _scope_entries(tree, action.root)
    if scope is None:
        return file_tool_error(
            "PATH_NOT_DIRECTORY",
            f"{_path_label(action.root)!r} is not a directory of the visible tree",
        )
    directories, files = scope
    if not action.recursive:
        directories = tuple(
            path for path in directories if _is_direct_child(path, action.root)
        )
        files = tuple(path for path in files if _is_direct_child(path, action.root))
    directory_entries = tuple(
        ListFilesEntryDirectoryV1(
            kind="DIRECTORY",
            path=path,
            size_bytes=AbsentV1(kind="ABSENT"),
            text_profile=AbsentV1(kind="ABSENT"),
        )
        for path in directories
    )
    file_entries = _file_entries(tree, files)
    if isinstance(file_entries, FileToolErrorV1):
        return file_entries
    entries: tuple[ListFilesEntryV1, ...] = (*directory_entries, *file_entries)
    if action.cursor.kind == "PRESENT":
        cursor = action.cursor.value
        key = (cursor.next_directory_rank, cursor.next_canonical_path.value)
        entries = tuple(
            entry for entry in entries if (_entry_rank(entry), entry.path.value) >= key
        )
    return _page(tree, entries, action)


def _entry_rank(entry: ListFilesEntryV1) -> Literal[0, 1]:
    """SPEC §4.2.2: directories rank 0, both file kinds rank 1."""
    if isinstance(entry, ListFilesEntryDirectoryV1):
        return 0
    return 1


def _page(
    tree: ReadableTreeV1,
    entries: tuple[ListFilesEntryV1, ...],
    action: ListFilesActionV1,
) -> ListFilesResultV1:
    page: list[ListFilesEntryV1] = []
    total_bytes = 0
    for entry in entries:
        item_bytes = _entry_canonical_bytes(entry)
        if page and total_bytes + item_bytes > RESULT_BODY_BYTES_V1:
            break
        page.append(entry)
        total_bytes += item_bytes
        if len(page) >= action.max_entries:
            break
    if len(page) == len(entries):
        return ListFilesSuccessV1(
            kind="SUCCESS",
            entries=tuple(page),
            truncated=False,
            next_cursor=AbsentV1(kind="ABSENT"),
        )
    next_entry = entries[len(page)]
    next_cursor = _issue_list_cursor(
        tree.digest, list_files_query_digest(action), next_entry
    )
    return ListFilesSuccessV1(
        kind="SUCCESS",
        entries=tuple(page),
        truncated=True,
        next_cursor=PresentV1(kind="PRESENT", value=next_cursor),
    )


def _issue_list_cursor(
    tree_digest: str,
    query_digest: str,
    next_entry: ListFilesEntryV1,
) -> ListFilesCursorV1:
    """One canonical cursor bound to the next unreturned entry's position."""
    draft = ListFilesCursorV1(
        schema_version=1,
        cursor_type="LIST_FILES_CURSOR_V1",
        visible_tree_digest=tree_digest,
        query_digest=query_digest,
        next_directory_rank=_entry_rank(next_entry),
        next_canonical_path=next_entry.path,
        digest="0" * 64,
    )
    return draft.model_copy(update={"digest": list_files_cursor_digest(draft)})


def _validate_list_cursor(
    tree: ReadableTreeV1,
    action: ListFilesActionV1,
    cursor: ListFilesCursorV1,
) -> FileToolErrorV1 | None:
    """Bind identity before serving (precedence lives in one shared helper)."""
    return validate_cursor_binding(
        family="list",
        computed_self_digest=list_files_cursor_digest(cursor),
        claimed_self_digest=cursor.digest,
        computed_query_digest=list_files_query_digest(action),
        claimed_query_digest=cursor.query_digest,
        visible_tree_digest=cursor.visible_tree_digest,
        tree_digest=tree.digest,
    )


def _scope_entries(
    tree: ReadableTreeV1,
    root: RepositoryLocationV1,
) -> (
    tuple[tuple[CanonicalRelativePathV1, ...], tuple[CanonicalRelativePathV1, ...]]
    | None
):
    """The root-scoped directory/file rows, stable-sorted by canonical path.

    ``ROOT`` covers the whole tree; a ``PATH`` root must be an existing
    directory (SPEC §4.2.2), otherwise ``None`` closes as
    ``PATH_NOT_DIRECTORY``.
    """
    directories = tuple(sorted(tree.list_directories(), key=lambda path: path.value))
    files = tuple(sorted(tree.list_file_paths(), key=lambda path: path.value))
    if root.kind == "ROOT":
        return directories, files
    prefix = root.path.value + "/"
    if root.path.value not in {path.value for path in directories}:
        return None
    return (
        tuple(path for path in directories if path.value.startswith(prefix)),
        tuple(path for path in files if path.value.startswith(prefix)),
    )


def _path_label(location: RepositoryLocationV1) -> str:
    """The root path for PATH locations, a stable label for ROOT."""
    if location.kind == "PATH":
        return location.path.value
    return "the repository root"


def _is_direct_child(path: CanonicalRelativePathV1, root: RepositoryLocationV1) -> bool:
    """True when *path* is an immediate child of the listing root."""
    if root.kind == "ROOT":
        return "/" not in path.value
    remainder = path.value[len(root.path.value) + 1 :]
    return "/" not in remainder


def _file_entries(
    tree: ReadableTreeV1, files: tuple[CanonicalRelativePathV1, ...]
) -> tuple[ListFilesEntryV1, ...] | FileToolErrorV1:
    """One closed list row per tree file, classified from its raw bytes."""
    entries: list[ListFilesEntryV1] = []
    for path in files:
        try:
            raw = tree.read_bytes(path)
        except KeyError:
            return file_tool_error(
                "FILE_NOT_FOUND",
                f"the enumerated tree file {path.value!r} is no longer readable",
            )
        classification = classify_supported_text(raw)
        if classification.kind == "TEXT_FILE":
            entries.append(
                ListFilesEntryTextFileV1(
                    kind="TEXT_FILE",
                    path=path,
                    size_bytes=PresentV1(kind="PRESENT", value=len(raw)),
                    text_profile=classification.text_profile,
                )
            )
        else:
            entries.append(
                ListFilesEntryNonTextFileV1(
                    kind="NON_TEXT_FILE",
                    path=path,
                    size_bytes=PresentV1(kind="PRESENT", value=len(raw)),
                    text_profile=AbsentV1(kind="ABSENT"),
                )
            )
    return tuple(entries)


def _entry_canonical_bytes(entry: ListFilesEntryV1) -> int:
    """The §0.1 canonical JSON byte length of one closed list row.

    The 32 KiB result body bound is measured over exactly these payload
    bytes, so the bound is deterministic and serialization-independent.
    """
    if isinstance(entry, ListFilesEntryDirectoryV1):
        value: CanonicalValueV1 = {
            "kind": "DIRECTORY",
            "path": entry.path.value,
            "size_bytes": {"kind": "ABSENT"},
            "text_profile": {"kind": "ABSENT"},
        }
    elif isinstance(entry, ListFilesEntryTextFileV1):
        metadata = entry.text_profile.value
        value = {
            "kind": "TEXT_FILE",
            "path": entry.path.value,
            "size_bytes": {"kind": "PRESENT", "value": entry.size_bytes.value},
            "text_profile": {
                "kind": "PRESENT",
                "value": {
                    "encoding": metadata.encoding,
                    "newline": metadata.newline,
                    "final_newline": metadata.final_newline,
                },
            },
        }
    else:
        value = {
            "kind": "NON_TEXT_FILE",
            "path": entry.path.value,
            "size_bytes": {"kind": "PRESENT", "value": entry.size_bytes.value},
            "text_profile": {"kind": "ABSENT"},
        }
    return len(canonical_json_bytes(value))

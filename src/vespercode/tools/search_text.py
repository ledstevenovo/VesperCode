"""T11.1 legacy step 11.B: stable literal search over one immutable tree.

``search_text`` observes the bound ``ReadableTreeV1`` protocol only: the
files covered by all roots are deduplicated and sorted by canonical path,
then every supported text file is scanned in increasing ``(line, column)``
order for the literal query; non-text files actually checked and skipped
before the continuation point each count once in
``skipped_non_text_count``; excerpts stay within 1024 no-BOM UTF-8 bytes
truncated only at Unicode scalar boundaries; the 32 KiB result body bound
truncates with a bound canonical cursor.  The cursor binds the visible
tree digest, the cursor-free query digest, the next scan position, and its
own digest; a tampered cursor is rejected with ``CONTINUATION_INVALID``
and a tree drift with ``CONTINUATION_STALE``, both with zero partial
results.  Filesystem access, arbitrary paths, shell execution, policy
mutation, and cross-tool cursor reuse remain out of scope (GREEN-4).
"""

from __future__ import annotations

from src.vespercode.canonical.json_v1 import CanonicalValueV1, canonical_json_bytes
from src.vespercode.canonical.path_v1 import CanonicalRelativePathV1
from src.vespercode.contracts.location import RepositoryLocationV1
from src.vespercode.contracts.optional import AbsentV1, PresentV1
from src.vespercode.tools.file_actions import (
    SearchTextActionV1,
    search_text_query_digest,
)
from src.vespercode.tools.file_results import (
    RESULT_BODY_BYTES_V1,
    FileToolErrorV1,
    SearchTextCursorV1,
    SearchTextMatchV1,
    SearchTextResultV1,
    SearchTextSuccessV1,
    bounded_utf8_text,
    file_tool_error,
    search_text_cursor_digest,
    split_text_lines,
    validate_cursor_binding,
)
from src.vespercode.trees.readable import ReadableTreeV1
from src.vespercode.trees.text_classifier import classify_supported_text

_EXCERPT_BYTES = 1024
_UTF8_BOM = b"\xef\xbb\xbf"


def search_text(tree: ReadableTreeV1, action: SearchTextActionV1) -> SearchTextResultV1:
    """Search the visible tree for the literal query in stable order.

    Overlapping roots never duplicate matches or skipped counts; a page
    stops only on the ``max_results`` cap or the 32 KiB body bound, and a
    bound continuation reproduces the unpaged result exactly.
    """
    if action.cursor.kind == "PRESENT":
        invalid = _validate_search_cursor(tree, action, action.cursor.value)
        if invalid is not None:
            return invalid
    resolved = _resolve_search_files(tree, action.roots)
    if isinstance(resolved, FileToolErrorV1):
        return resolved
    files = resolved
    cursor_path: str | None = None
    cursor_index = 0
    resume_at = 0
    if action.cursor.kind == "PRESENT":
        cursor_path = action.cursor.value.next_canonical_path.value
        cursor_index = action.cursor.value.next_match_index
        if cursor_path not in files:
            return file_tool_error(
                "CONTINUATION_INVALID",
                "the search cursor's file position is not a file of the visible tree",
            )
        resume_at = files.index(cursor_path)
    matches: list[SearchTextMatchV1] = []
    total_bytes = 0
    skipped = 0
    file_index = resume_at
    next_cursor_value: SearchTextCursorV1 | None = None
    while file_index < len(files):
        path = CanonicalRelativePathV1(files[file_index])
        try:
            raw = tree.read_bytes(path)
        except KeyError:
            return file_tool_error(
                "FILE_NOT_FOUND",
                f"the enumerated tree file {path.value!r} is no longer readable",
            )
        classification = classify_supported_text(raw)
        if classification.kind != "TEXT_FILE":
            skipped += 1
            file_index += 1
            continue
        metadata = classification.text_profile.value
        body = raw[len(_UTF8_BOM) :] if metadata.encoding == "UTF8_BOM" else raw
        decoded = body.decode("utf-8")
        terminator = "\r\n" if metadata.newline == "CRLF" else "\n"
        lines = split_text_lines(decoded, terminator)
        file_matches = _match_file(path, lines, terminator, action)
        from_index = cursor_index if cursor_path == path.value else 0
        if from_index > len(file_matches):
            return file_tool_error(
                "CONTINUATION_INVALID",
                f"the search cursor's match index {from_index} exceeds the "
                f"{len(file_matches)} matches of {path.value!r}",
            )
        for match_index, match in enumerate(
            file_matches[from_index:], start=from_index
        ):
            item_bytes = _match_canonical_bytes(match)
            if len(matches) >= action.max_results or (
                matches and total_bytes + item_bytes > RESULT_BODY_BYTES_V1
            ):
                next_cursor_value = _issue_search_cursor(
                    tree, action, path, match_index
                )
                break
            matches.append(match)
            total_bytes += item_bytes
        else:
            # The file's matches all fit: advance to the next file so the
            # scan position always moves, even past zero-match files.
            file_index += 1
            continue
        break
    if next_cursor_value is None:
        return SearchTextSuccessV1(
            kind="SUCCESS",
            matches=tuple(matches),
            truncated=False,
            next_cursor=AbsentV1(kind="ABSENT"),
            skipped_non_text_count=skipped,
        )
    return SearchTextSuccessV1(
        kind="SUCCESS",
        matches=tuple(matches),
        truncated=True,
        next_cursor=PresentV1(kind="PRESENT", value=next_cursor_value),
        skipped_non_text_count=skipped,
    )


def _match_file(
    path: CanonicalRelativePathV1,
    lines: list[str],
    terminator: str,
    action: SearchTextActionV1,
) -> tuple[SearchTextMatchV1, ...]:
    """All literal occurrences of the query in one file's lines.

    Matching is per line (a query containing a newline can never match) and
    non-overlapping; for case-insensitive queries both sides are folded
    with Unicode case folding and the reported column is the folded match
    start, 1-based.
    """
    query = action.query.casefold() if not action.case_sensitive else action.query
    matches: list[SearchTextMatchV1] = []
    for line_index, line in enumerate(lines):
        source = line.casefold() if not action.case_sensitive else line
        start = 0
        while True:
            column = source.find(query, start)
            if column < 0:
                break
            matches.append(
                SearchTextMatchV1(
                    path=path,
                    line=line_index + 1,
                    column=column + 1,
                    excerpt=_excerpt(lines, line_index, action, terminator),
                )
            )
            start = column + len(query)
    return tuple(matches)


def _excerpt(
    lines: list[str],
    line_index: int,
    action: SearchTextActionV1,
    terminator: str,
) -> str:
    """The matching line plus the requested context lines, bounded.

    SPEC §4.2.2: at most 1024 no-BOM UTF-8 bytes, truncated only at a
    Unicode scalar boundary; the cut is deterministic.
    """
    start = max(0, line_index - action.context_lines)
    end = min(len(lines), line_index + 1 + action.context_lines)
    text = terminator.join(lines[start:end]) + terminator
    return bounded_utf8_text(text, _EXCERPT_BYTES)


def _match_canonical_bytes(match: SearchTextMatchV1) -> int:
    """The §0.1 canonical JSON byte length of one search match."""
    value: CanonicalValueV1 = {
        "path": match.path.value,
        "line": match.line,
        "column": match.column,
        "excerpt": match.excerpt,
    }
    return len(canonical_json_bytes(value))


def _resolve_search_files(
    tree: ReadableTreeV1, roots: tuple[RepositoryLocationV1, ...]
) -> tuple[str, ...] | FileToolErrorV1:
    """Every file covered by the roots, deduplicated and sorted by path.

    A ``PATH`` root may be a supported file or an existing directory (SPEC
    §4.2.2); a missing path fails closed as ``PATH_NOT_FOUND`` and a
    directly-rooted non-text file still scans (zero matches, one skip).
    """
    directories = {path.value for path in tree.list_directories()}
    file_paths = {path.value for path in tree.list_file_paths()}
    selected: set[str] = set()
    for root in roots:
        if root.kind == "ROOT":
            selected.update(file_paths)
            continue
        path = root.path.value
        if path in file_paths:
            selected.add(path)
        elif path in directories:
            selected.update(
                possible_path
                for possible_path in file_paths
                if possible_path.startswith(path + "/")
            )
        else:
            return file_tool_error(
                "PATH_NOT_FOUND",
                f"search root {path!r} is not a file or directory of the visible tree",
            )
    return tuple(sorted(selected))


def _issue_search_cursor(
    tree: ReadableTreeV1,
    action: SearchTextActionV1,
    path: CanonicalRelativePathV1,
    match_index: int,
) -> SearchTextCursorV1:
    """One canonical cursor bound to the next unreturned match position."""
    draft = SearchTextCursorV1(
        schema_version=1,
        cursor_type="SEARCH_TEXT_CURSOR_V1",
        visible_tree_digest=tree.digest,
        query_digest=search_text_query_digest(action),
        next_canonical_path=path,
        next_match_index=match_index,
        digest="0" * 64,
    )
    return draft.model_copy(update={"digest": search_text_cursor_digest(draft)})


def _validate_search_cursor(
    tree: ReadableTreeV1,
    action: SearchTextActionV1,
    cursor: SearchTextCursorV1,
) -> FileToolErrorV1 | None:
    """Bind identity before serving (precedence lives in one shared helper)."""
    return validate_cursor_binding(
        family="search",
        computed_self_digest=search_text_cursor_digest(cursor),
        claimed_self_digest=cursor.digest,
        computed_query_digest=search_text_query_digest(action),
        claimed_query_digest=cursor.query_digest,
        visible_tree_digest=cursor.visible_tree_digest,
        tree_digest=tree.digest,
    )

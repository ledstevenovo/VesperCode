"""T11.1 legacy step 11.B: literal text search behavior tests.

``search_text`` scans the visible immutable tree only (SPEC §4.2.2): all
roots' covered files are deduplicated and sorted by canonical path, then
each ``TEXT_FILE`` is scanned in increasing ``(line, column)`` order for
the literal query; ``NON_TEXT_FILE`` files actually checked and skipped
before the continuation point each count once in
``skipped_non_text_count``; excerpts stay within 1024 no-BOM UTF-8 bytes
truncated only at Unicode scalar boundaries; the 32 KiB result body bound
truncates with a bound cursor; and every tampered cursor or tree drift
fails closed with zero partial results.  Filesystem access, arbitrary
paths, shell execution, policy mutation, and cross-tool cursor reuse
remain out of scope (GREEN-4).
"""

from __future__ import annotations

import pytest

# The file-tool contracts are pydantic runtime models; the hash-locked gate
# toolchain does not install runtime dependencies, so this module skips
# cleanly there instead of failing at collection (formal env runs it fully).
pytest.importorskip("pydantic")

from pydantic import ValidationError

from vespercode.canonical.path_v1 import CanonicalRelativePathV1
from vespercode.contracts.optional import AbsentV1, PresentV1
from vespercode.tools.file_actions import SearchTextActionV1
from vespercode.tools.file_results import (
    FileToolErrorV1,
    OptionalSearchTextCursorV1,
    SearchTextCursorV1,
    SearchTextMatchV1,
    SearchTextSuccessV1,
)
from vespercode.tools.search_text import search_text
from vespercode.trees.readable import ReadableTreeV1


class SearchTree:
    """Protocol-only immutable fake tree implementing ``ReadableTreeV1``."""

    def __init__(self, files: dict[str, bytes], *, digest: str = "d" * 64) -> None:
        self._files = dict(files)
        self._digest = digest

    @property
    def digest(self) -> str:
        return self._digest

    def list_directories(self) -> tuple[CanonicalRelativePathV1, ...]:
        directories: set[str] = set()
        for path in self._files:
            segments = path.split("/")
            for index in range(1, len(segments)):
                directories.add("/".join(segments[:index]))
        return tuple(
            sorted(
                (CanonicalRelativePathV1(value) for value in directories),
                key=lambda path: path.value,
            )
        )

    def list_file_paths(self) -> tuple[CanonicalRelativePathV1, ...]:
        return tuple(
            sorted(
                (CanonicalRelativePathV1(value) for value in self._files),
                key=lambda path: path.value,
            )
        )

    def read_bytes(self, path: CanonicalRelativePathV1) -> bytes:
        if path.value not in self._files:
            raise KeyError(f"no file at {path.value!r} in the search tree")
        return self._files[path.value]

    def with_drifted_digest(self) -> SearchTree:
        """A tree with identical bytes but a different sealed identity."""
        return SearchTree(self._files, digest="e" * 64)


def _search_action(
    *,
    query: str = "needle",
    roots: tuple[dict[str, object], ...] = ({"kind": "ROOT"},),
    case_sensitive: bool = True,
    context_lines: int = 0,
    max_results: int = 100,
    cursor: OptionalSearchTextCursorV1 = AbsentV1(kind="ABSENT"),
) -> SearchTextActionV1:
    return SearchTextActionV1.model_validate(
        {
            "schema_version": 1,
            "action_type": "search_text",
            "query": query,
            "roots": roots,
            "case_sensitive": case_sensitive,
            "context_lines": context_lines,
            "max_results": max_results,
            "cursor": cursor,
        }
    )


def _positions(result: SearchTextSuccessV1) -> tuple[tuple[str, int, int], ...]:
    return tuple((m.path.value, m.line, m.column) for m in result.matches)


def test_search_literal_match_positions_and_order() -> None:
    tree = SearchTree(
        {
            "z.py": b"needle z\n",
            "a.py": b"a needle here\n",
            "src/b.py": b"middle needle\n",
        }
    )
    result = search_text(
        tree,
        _search_action(query="needle", roots=({"kind": "ROOT"},)),
    )
    assert result.kind == "SUCCESS"
    assert result.truncated is False
    assert _positions(result) == (
        ("a.py", 1, 3),
        ("src/b.py", 1, 8),
        ("z.py", 1, 1),
    )
    # context_lines=0 excerpts are exactly the match line with its terminator.
    assert tuple(m.excerpt for m in result.matches) == (
        "a needle here\n",
        "middle needle\n",
        "needle z\n",
    )


def test_search_multiple_matches_per_line_advance() -> None:
    tree = SearchTree({"src/a.py": b"needle x needle y needle\n"})
    result = search_text(tree, _search_action(query="needle"))
    assert result.kind == "SUCCESS"
    # Non-overlapping occurrences on one line, columns ascending.
    assert _positions(result) == (
        ("src/a.py", 1, 1),
        ("src/a.py", 1, 10),
        ("src/a.py", 1, 19),
    )


def test_search_case_sensitivity_and_unicode_folding() -> None:
    tree = SearchTree(
        {
            "src/a.py": b"NEEDLE upper\n",
            "src/b.py": "Straße\n".encode("utf-8"),
        }
    )
    sensitive = search_text(tree, _search_action(query="needle"))
    assert sensitive.kind == "SUCCESS"
    assert sensitive.matches == ()
    folded = search_text(
        tree,
        _search_action(query="needle", case_sensitive=False),
    )
    assert folded.kind == "SUCCESS"
    assert _positions(folded) == (("src/a.py", 1, 1),)
    folded_german = search_text(
        tree,
        _search_action(query="STRASSE", case_sensitive=False),
    )
    assert folded_german.kind == "SUCCESS"
    assert _positions(folded_german) == (("src/b.py", 1, 1),)


def test_search_excerpt_context_lines_and_no_bom() -> None:
    tree = SearchTree(
        {
            "src/a.py": (
                b"before one\nbefore two\nthe needle line\nafter one\nafter two\n"
            )
        }
    )
    bare = search_text(tree, _search_action(query="needle", context_lines=0))
    assert bare.kind == "SUCCESS"
    assert bare.matches[0].excerpt == "the needle line\n"
    with_context = search_text(tree, _search_action(query="needle", context_lines=2))
    assert with_context.kind == "SUCCESS"
    assert with_context.matches[0].excerpt == (
        "before one\nbefore two\nthe needle line\nafter one\nafter two\n"
    )
    bom = SearchTree({"src/bom.py": b"\xef\xbb\xbfneedle bom\n"})
    bom_result = search_text(bom, _search_action(query="needle"))
    assert bom_result.kind == "SUCCESS"
    # The excerpt is always BOM-free and the BOM never matches.
    assert bom_result.matches[0].excerpt == "needle bom\n"


def test_search_excerpt_bounded_at_1024_scalar_boundary() -> None:
    long_line = ("你好" * 700 + " needle tail\n").encode("utf-8")
    tree = SearchTree({"src/long.py": long_line})
    result = search_text(tree, _search_action(query="needle"))
    assert result.kind == "SUCCESS"
    excerpt = result.matches[0].excerpt
    raw = excerpt.encode("utf-8")
    assert len(raw) <= 1024
    # The truncation never splits a UTF-8 scalar and the cut happens
    # mid-line (the full match line is 4200+ bytes).
    raw.decode("utf-8")
    assert "tail" not in excerpt


def test_search_non_text_root_counts_skipped_once() -> None:
    tree = SearchTree({"assets/blob.bin": b"\x89PNG\r\n\x1a\n"})
    result = search_text(
        tree,
        _search_action(roots=({"kind": "PATH", "path": {"value": "assets/blob.bin"}},)),
    )
    assert result.kind == "SUCCESS"
    assert result.matches == ()
    assert result.truncated is False
    assert result.skipped_non_text_count == 1


def test_search_text_file_and_directory_roots() -> None:
    tree = SearchTree(
        {
            "src/a.py": b"needle a\n",
            "src/pkg/b.py": b"needle b\n",
            "other/c.py": b"needle c\n",
        }
    )
    file_root = search_text(
        tree,
        _search_action(roots=({"kind": "PATH", "path": {"value": "src/a.py"}},)),
    )
    assert file_root.kind == "SUCCESS"
    assert _positions(file_root) == (("src/a.py", 1, 1),)
    dir_root = search_text(
        tree,
        _search_action(roots=({"kind": "PATH", "path": {"value": "src"}},)),
    )
    assert dir_root.kind == "SUCCESS"
    assert _positions(dir_root) == (("src/a.py", 1, 1), ("src/pkg/b.py", 1, 1))


def test_search_overlapping_roots_deduplicate() -> None:
    tree = SearchTree(
        {
            "src/a.py": b"needle a\n",
            "src/pkg/b.py": b"needle b\n",
            "assets/blob.bin": b"\x89PNG\r\n\x1a\n",
        }
    )
    result = search_text(
        tree,
        _search_action(
            roots=(
                {"kind": "PATH", "path": {"value": "src"}},
                {"kind": "PATH", "path": {"value": "src/pkg"}},
                {"kind": "PATH", "path": {"value": "src/a.py"}},
                {"kind": "PATH", "path": {"value": "assets"}},
            )
        ),
    )
    assert result.kind == "SUCCESS"
    assert _positions(result) == (("src/a.py", 1, 1), ("src/pkg/b.py", 1, 1))
    # Overlapping roots never duplicate matches or skipped counts.
    assert result.skipped_non_text_count == 1


def test_search_missing_root_fails_closed() -> None:
    tree = SearchTree({"src/a.py": b"needle\n"})
    result = search_text(
        tree,
        _search_action(roots=({"kind": "PATH", "path": {"value": "missing"}},)),
    )
    assert result.kind == "ERROR"
    assert result.error_code == "PATH_NOT_FOUND"


def test_search_no_match_text_is_complete() -> None:
    tree = SearchTree({"src/a.py": b"nothing here\n"})
    result = search_text(tree, _search_action(query="needle"))
    assert result.kind == "SUCCESS"
    assert result.matches == ()
    assert result.truncated is False
    assert result.next_cursor.kind == "ABSENT"
    assert result.skipped_non_text_count == 0


def test_search_32k_body_bound_truncates_and_continues() -> None:
    lines = ("needle " + "x" * 1100 + "\n") * 40
    tree = SearchTree({"src/huge.py": lines.encode("utf-8")})
    first = search_text(
        tree,
        _search_action(query="needle", max_results=100, context_lines=0),
    )
    assert first.kind == "SUCCESS"
    assert first.truncated is True
    assert 1 <= len(first.matches) < 40
    collected: list[SearchTextMatchV1] = []
    cursor: OptionalSearchTextCursorV1 = first.next_cursor
    collected.extend(first.matches)
    pages = 1
    while cursor.kind == "PRESENT":
        page = search_text(
            tree,
            _search_action(
                query="needle",
                max_results=100,
                context_lines=0,
                cursor=cursor,
            ),
        )
        assert page.kind == "SUCCESS"
        collected.extend(page.matches)
        cursor = page.next_cursor
        pages += 1
        assert pages < 100
    assert len(collected) == 40
    assert tuple((m.path.value, m.line, m.column) for m in collected) == tuple(
        ("src/huge.py", index + 1, 1) for index in range(40)
    )


def test_search_skipped_accounting_never_double_counts_across_pages() -> None:
    tree = SearchTree(
        {
            "a.py": b"needle a\n",
            "b.blob": b"\x89PNG\r\n\x1a\n",
            "c.py": b"needle c\n",
            "d.blob": b"\x89PNG\r\n\x1a\n",
            "e.py": b"needle e\n",
        }
    )
    total_skipped = 0
    cursor: OptionalSearchTextCursorV1 = AbsentV1(kind="ABSENT")
    while True:
        page = search_text(
            tree, _search_action(query="needle", max_results=1, cursor=cursor)
        )
        assert page.kind == "SUCCESS"
        total_skipped += page.skipped_non_text_count
        if page.truncated:
            assert page.next_cursor.kind == "PRESENT"
            cursor = page.next_cursor
        else:
            assert page.next_cursor.kind == "ABSENT"
            break
    assert total_skipped == 2


def test_search_cursor_tamper_matrix() -> None:
    tree = SearchTree({"src/a.py": b"needle one\nneedle two\n"})
    first = search_text(tree, _search_action(query="needle", max_results=1))
    assert first.kind == "SUCCESS" and first.truncated is True
    cursor = first.next_cursor
    assert cursor.kind == "PRESENT"
    issued = cursor.value

    def run_with(value: SearchTextCursorV1) -> FileToolErrorV1:
        result = search_text(
            tree,
            _search_action(
                query="needle",
                max_results=1,
                cursor=PresentV1(kind="PRESENT", value=value),
            ),
        )
        assert result.kind == "ERROR"
        return result

    assert (
        run_with(issued.model_copy(update={"digest": "f" * 64})).error_code
        == "CONTINUATION_INVALID"
    )
    assert (
        run_with(issued.model_copy(update={"query_digest": "f" * 64})).error_code
        == "CONTINUATION_INVALID"
    )
    assert (
        run_with(issued.model_copy(update={"next_match_index": 5})).error_code
        == "CONTINUATION_INVALID"
    )
    assert (
        run_with(issued.model_copy(update={"visible_tree_digest": "f" * 64})).error_code
        == "CONTINUATION_INVALID"
    )
    # A consistently bound cursor issued by the drifted tree is stale here.
    drifted_first = search_text(
        tree.with_drifted_digest(), _search_action(query="needle", max_results=1)
    )
    assert drifted_first.kind == "SUCCESS" and drifted_first.truncated is True
    drifted_cursor = drifted_first.next_cursor
    assert drifted_cursor.kind == "PRESENT"
    stale = search_text(
        tree,
        _search_action(query="needle", max_results=1, cursor=drifted_cursor),
    )
    assert stale.kind == "ERROR"
    assert stale.error_code == "CONTINUATION_STALE"


def test_search_result_schemas_are_closed() -> None:
    with pytest.raises(ValidationError):
        SearchTextMatchV1.model_validate(
            {"path": "src/a.py", "line": 1, "column": 0, "excerpt": "x\n", "extra": 1}
        )
    with pytest.raises(ValidationError):
        SearchTextMatchV1.model_validate(
            {"path": "src/a.py", "line": True, "column": 1, "excerpt": "x\n"}
        )
    with pytest.raises(ValidationError):
        SearchTextSuccessV1.model_validate(
            {
                "kind": "SUCCESS",
                "matches": (),
                "truncated": True,
                "next_cursor": {"kind": "ABSENT"},
                "skipped_non_text_count": 0,
            }
        )
    with pytest.raises(ValidationError):
        SearchTextSuccessV1.model_validate(
            {
                "kind": "SUCCESS",
                "matches": (),
                "truncated": False,
                "next_cursor": {"kind": "PRESENT", "value": None},
                "skipped_non_text_count": 0,
            }
        )


def test_search_consumes_only_the_readable_tree_protocol() -> None:
    def consume(tree: ReadableTreeV1) -> tuple[tuple[str, int, int], ...]:
        result = search_text(
            tree,
            _search_action(query="needle"),
        )
        assert result.kind == "SUCCESS"
        return _positions(result)

    fake = SearchTree({"src/a.py": b"needle\n"})
    assert isinstance(fake, ReadableTreeV1)
    assert consume(fake) == (("src/a.py", 1, 1),)

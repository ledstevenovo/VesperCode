"""T11.1 legacy step 11.B: stable paged List and canonical cursor tests.

The displayed RED test proves paged List/Search discovery reproduces the
unpaged results exactly without duplicates; the cursor-integrity matrix
(PLAN registry 11.B) proves protocol-only fake-tree paged and unpaged
results are identical and ordered without importing any postimage-tree
module, that each cursor binds the visible tree digest, the cursor-free
query digest, the next scan position, and its own digest, and that a
tampered cursor returns ``CONTINUATION_INVALID`` while a tree drift
returns ``CONTINUATION_STALE`` — both with zero partial results.
Filesystem access, arbitrary paths, shell execution, policy mutation, and
cross-tool cursor reuse remain out of scope (GREEN-4).
"""

from __future__ import annotations

from typing import cast

import pytest

# The file-tool contracts are pydantic runtime models; the hash-locked gate
# toolchain does not install runtime dependencies, so this module skips
# cleanly there instead of failing at collection (formal env runs it fully).
pytest.importorskip("pydantic")

from pydantic import ValidationError

from vespercode.canonical.path_v1 import CanonicalRelativePathV1
from vespercode.contracts.location import PathLocationV1, RootLocationV1
from vespercode.contracts.optional import AbsentV1, PresentV1
from vespercode.tools.file_actions import ListFilesActionV1, SearchTextActionV1
from vespercode.tools.file_results import (
    FileToolErrorV1,
    ListFilesCursorV1,
    ListFilesEntryV1,
    OptionalListFilesCursorV1,
    OptionalSearchTextCursorV1,
    SearchTextCursorV1,
    SearchTextMatchV1,
)
from vespercode.tools.list_files import list_files
from vespercode.tools.search_text import search_text
from vespercode.trees.readable import ReadableTreeV1

_FIXTURE_FILES: dict[str, bytes] = {
    "README.md": b"needle here\nplain line\nneedle again\n",
    "src/a.py": b"import needle\n\nx = 1\n",
    "src/b.py": b"NEEDLE uppercase\n",
    "src/pkg/c.py": b"alpha needle beta needle\n",
    "assets/logo.png": b"\x89PNG\r\n\x1a\n",
}


class DiscoveryTree:
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
            raise KeyError(f"no file at {path.value!r} in the discovery tree")
        return self._files[path.value]

    def with_drifted_digest(self) -> DiscoveryTree:
        """A tree with identical bytes but a different sealed identity."""
        return DiscoveryTree(self._files, digest="e" * 64)


class DiscoveryFixture:
    """One discovery tree plus paged and unpaged list/search collection."""

    def __init__(self) -> None:
        self.tree = DiscoveryTree(_FIXTURE_FILES)

    def _list_action(
        self, max_entries: int, cursor: OptionalListFilesCursorV1
    ) -> ListFilesActionV1:
        return ListFilesActionV1(
            schema_version=1,
            action_type="list_files",
            root=RootLocationV1(kind="ROOT"),
            recursive=True,
            max_entries=max_entries,
            cursor=cursor,
        )

    def _search_action(
        self, max_results: int, cursor: OptionalSearchTextCursorV1
    ) -> SearchTextActionV1:
        return SearchTextActionV1(
            schema_version=1,
            action_type="search_text",
            query="needle",
            roots=(RootLocationV1(kind="ROOT"),),
            case_sensitive=True,
            context_lines=0,
            max_results=max_results,
            cursor=cursor,
        )

    def collect_list_pages(self, limit: int) -> tuple[ListFilesEntryV1, ...]:
        entries: list[ListFilesEntryV1] = []
        cursor: OptionalListFilesCursorV1 = AbsentV1(kind="ABSENT")
        pages = 0
        while True:
            result = list_files(self.tree, self._list_action(limit, cursor))
            assert result.kind == "SUCCESS"
            entries.extend(result.entries)
            if result.truncated:
                assert result.next_cursor.kind == "PRESENT"
                cursor = result.next_cursor
            else:
                assert result.next_cursor.kind == "ABSENT"
                break
            pages += 1
            assert pages < 1000
        return tuple(entries)

    def list_unpaged(self) -> tuple[ListFilesEntryV1, ...]:
        result = list_files(self.tree, self._list_action(500, AbsentV1(kind="ABSENT")))
        assert result.kind == "SUCCESS"
        assert result.truncated is False
        assert result.next_cursor.kind == "ABSENT"
        return result.entries

    def collect_search_pages(self, limit: int) -> tuple[SearchTextMatchV1, ...]:
        matches: list[SearchTextMatchV1] = []
        cursor: OptionalSearchTextCursorV1 = AbsentV1(kind="ABSENT")
        pages = 0
        while True:
            result = search_text(self.tree, self._search_action(limit, cursor))
            assert result.kind == "SUCCESS"
            matches.extend(result.matches)
            if result.truncated:
                assert result.next_cursor.kind == "PRESENT"
                cursor = result.next_cursor
            else:
                assert result.next_cursor.kind == "ABSENT"
                break
            pages += 1
            assert pages < 1000
        return tuple(matches)

    def search_unpaged(self) -> tuple[SearchTextMatchV1, ...]:
        result = search_text(
            self.tree, self._search_action(100, AbsentV1(kind="ABSENT"))
        )
        assert result.kind == "SUCCESS"
        assert result.truncated is False
        assert result.next_cursor.kind == "ABSENT"
        return result.matches

    def search_skipped_total(self) -> int:
        skipped = 0
        cursor: OptionalSearchTextCursorV1 = AbsentV1(kind="ABSENT")
        while True:
            result = search_text(self.tree, self._search_action(2, cursor))
            assert result.kind == "SUCCESS"
            skipped += result.skipped_non_text_count
            if result.truncated:
                assert result.next_cursor.kind == "PRESENT"
                cursor = result.next_cursor
            else:
                return skipped


@pytest.fixture
def discovery_fixture() -> DiscoveryFixture:
    return DiscoveryFixture()


def test_paged_discovery_equals_unpaged_without_duplicates(
    discovery_fixture: DiscoveryFixture,
) -> None:
    assert (
        discovery_fixture.collect_list_pages(limit=2)
        == discovery_fixture.list_unpaged()
    )
    assert (
        discovery_fixture.collect_search_pages(limit=2)
        == discovery_fixture.search_unpaged()
    )


def test_list_search_cursor_integrity_matrix(
    discovery_fixture: DiscoveryFixture,
) -> None:
    """PLAN registry 11.B: paged/unpaged equality, ordering, tamper closure.

    A single page size of two forces a multi-page traversal; the collected
    pages must equal the unpaged results exactly (no duplicates, no
    omissions) and the cursor must bind tree digest, query digest, next
    position, and its own digest.  Tampering any bound field returns
    ``CONTINUATION_INVALID``; a cursor issued by a drifted tree returns
    ``CONTINUATION_STALE``; both return zero partial results.
    """
    fixture = discovery_fixture
    # Paged and unpaged list entries agree exactly, in stable order.
    paged_list = fixture.collect_list_pages(limit=2)
    unpaged_list = fixture.list_unpaged()
    assert paged_list == unpaged_list
    assert len(paged_list) == 8
    kinds = tuple(entry.kind for entry in paged_list)
    assert kinds == (
        "DIRECTORY",
        "DIRECTORY",
        "DIRECTORY",
        "TEXT_FILE",
        "NON_TEXT_FILE",
        "TEXT_FILE",
        "TEXT_FILE",
        "TEXT_FILE",
    )
    assert tuple(entry.path.value for entry in paged_list) == (
        "assets",
        "src",
        "src/pkg",
        "README.md",
        "assets/logo.png",
        "src/a.py",
        "src/b.py",
        "src/pkg/c.py",
    )
    # Paged and unpaged search matches agree exactly, in stable order.
    paged_search = fixture.collect_search_pages(limit=2)
    unpaged_search = fixture.search_unpaged()
    assert paged_search == unpaged_search
    assert tuple((m.path.value, m.line, m.column) for m in paged_search) == (
        ("README.md", 1, 1),
        ("README.md", 3, 1),
        ("src/a.py", 1, 8),
        ("src/pkg/c.py", 1, 7),
        ("src/pkg/c.py", 1, 19),
    )
    # Non-text accounting: pages never double-count a skipped file.
    assert fixture.search_skipped_total() == 1

    # --- List cursor tamper rows: zero partial results each. ---
    first_list = list_files(
        fixture.tree, fixture._list_action(2, AbsentV1(kind="ABSENT"))
    )
    assert first_list.kind == "SUCCESS" and first_list.truncated is True
    cursor = first_list.next_cursor
    assert cursor.kind == "PRESENT"
    issued = cursor.value

    def list_with(cursor_value: ListFilesCursorV1) -> FileToolErrorV1:
        result = list_files(
            fixture.tree,
            fixture._list_action(2, PresentV1(kind="PRESENT", value=cursor_value)),
        )
        assert result.kind == "ERROR"
        return result

    tampered_digest = list_with(issued.model_copy(update={"digest": "f" * 64}))
    assert tampered_digest.error_code == "CONTINUATION_INVALID"
    tampered_query = list_with(issued.model_copy(update={"query_digest": "f" * 64}))
    assert tampered_query.error_code == "CONTINUATION_INVALID"
    tampered_position = list_with(
        issued.model_copy(
            update={"next_canonical_path": CanonicalRelativePathV1("src/a.py")}
        )
    )
    assert tampered_position.error_code == "CONTINUATION_INVALID"
    tampered_tree = list_with(
        issued.model_copy(update={"visible_tree_digest": "f" * 64})
    )
    assert tampered_tree.error_code == "CONTINUATION_INVALID"
    # Tree drift: a cursor issued by the drifted tree is consistently bound
    # but stale against the current visible tree.
    drifted_first = list_files(
        fixture.tree.with_drifted_digest(),
        fixture._list_action(2, AbsentV1(kind="ABSENT")),
    )
    assert drifted_first.kind == "SUCCESS" and drifted_first.truncated is True
    drifted_cursor = drifted_first.next_cursor
    assert drifted_cursor.kind == "PRESENT"
    stale = list_files(
        fixture.tree,
        fixture._list_action(2, PresentV1(kind="PRESENT", value=drifted_cursor.value)),
    )
    assert stale.kind == "ERROR"
    assert stale.error_code == "CONTINUATION_STALE"
    # Every tampered or stale continuation returned zero rows.
    for rejected in (
        tampered_digest,
        tampered_query,
        tampered_position,
        tampered_tree,
        stale,
    ):
        assert rejected.kind == "ERROR"
        assert not hasattr(rejected, "entries")

    # --- Search cursor tamper rows: zero partial results each. ---
    first_search = search_text(
        fixture.tree, fixture._search_action(2, AbsentV1(kind="ABSENT"))
    )
    assert first_search.kind == "SUCCESS" and first_search.truncated is True
    search_cursor = first_search.next_cursor
    assert search_cursor.kind == "PRESENT"
    issued_search = search_cursor.value

    def search_with(cursor_value: SearchTextCursorV1) -> FileToolErrorV1:
        result = search_text(
            fixture.tree,
            fixture._search_action(2, PresentV1(kind="PRESENT", value=cursor_value)),
        )
        assert result.kind == "ERROR"
        return result

    assert (
        search_with(issued_search.model_copy(update={"digest": "f" * 64})).error_code
        == "CONTINUATION_INVALID"
    )
    assert (
        search_with(
            issued_search.model_copy(update={"query_digest": "f" * 64})
        ).error_code
        == "CONTINUATION_INVALID"
    )
    assert (
        search_with(issued_search.model_copy(update={"next_match_index": 1})).error_code
        == "CONTINUATION_INVALID"
    )
    assert (
        search_with(
            issued_search.model_copy(update={"visible_tree_digest": "f" * 64})
        ).error_code
        == "CONTINUATION_INVALID"
    )
    drifted_search = search_text(
        fixture.tree.with_drifted_digest(),
        fixture._search_action(2, AbsentV1(kind="ABSENT")),
    )
    assert drifted_search.kind == "SUCCESS" and drifted_search.truncated is True
    drifted_search_cursor = drifted_search.next_cursor
    assert drifted_search_cursor.kind == "PRESENT"
    stale_search = search_text(
        fixture.tree,
        fixture._search_action(
            2, PresentV1(kind="PRESENT", value=drifted_search_cursor.value)
        ),
    )
    assert stale_search.kind == "ERROR"
    assert stale_search.error_code == "CONTINUATION_STALE"

    # Cross-tool cursor reuse is rejected by the closed action schema (the
    # cast deliberately forces a type-mismatched cursor through).
    with pytest.raises(ValidationError):
        fixture._list_action(
            2,
            cast(
                OptionalListFilesCursorV1,
                PresentV1(kind="PRESENT", value=issued_search),
            ),
        )
    with pytest.raises(ValidationError):
        fixture._search_action(
            2,
            cast(
                OptionalSearchTextCursorV1,
                PresentV1(kind="PRESENT", value=issued),
            ),
        )


def test_list_entries_follow_directory_rank_then_path_order() -> None:
    tree = DiscoveryTree(
        {
            "z.txt": b"z\n",
            "a.txt": b"a\n",
            "src/pkg/deep.py": b"x = 1\n",
        }
    )
    result = list_files(
        tree,
        ListFilesActionV1(
            schema_version=1,
            action_type="list_files",
            root=RootLocationV1(kind="ROOT"),
            recursive=True,
            max_entries=500,
            cursor=AbsentV1(kind="ABSENT"),
        ),
    )
    assert result.kind == "SUCCESS"
    assert result.truncated is False
    assert tuple(e.path.value for e in result.entries) == (
        "src",
        "src/pkg",
        "a.txt",
        "src/pkg/deep.py",
        "z.txt",
    )


def test_list_root_path_scope_and_recursive_modes() -> None:
    tree = DiscoveryTree(_FIXTURE_FILES)
    # PATH root: only descendants of src, directories first.
    src_recursive = list_files(
        tree,
        ListFilesActionV1(
            schema_version=1,
            action_type="list_files",
            root=PathLocationV1(kind="PATH", path=CanonicalRelativePathV1("src")),
            recursive=True,
            max_entries=500,
            cursor=AbsentV1(kind="ABSENT"),
        ),
    )
    assert src_recursive.kind == "SUCCESS"
    assert tuple(e.path.value for e in src_recursive.entries) == (
        "src/pkg",
        "src/a.py",
        "src/b.py",
        "src/pkg/c.py",
    )
    # Non-recursive PATH root: only the direct children of src.
    src_direct = list_files(
        tree,
        ListFilesActionV1(
            schema_version=1,
            action_type="list_files",
            root=PathLocationV1(kind="PATH", path=CanonicalRelativePathV1("src")),
            recursive=False,
            max_entries=500,
            cursor=AbsentV1(kind="ABSENT"),
        ),
    )
    assert src_direct.kind == "SUCCESS"
    assert tuple(e.path.value for e in src_direct.entries) == (
        "src/pkg",
        "src/a.py",
        "src/b.py",
    )
    # Non-recursive ROOT: only the repository root's direct children.
    root_direct = list_files(
        tree,
        ListFilesActionV1(
            schema_version=1,
            action_type="list_files",
            root=RootLocationV1(kind="ROOT"),
            recursive=False,
            max_entries=500,
            cursor=AbsentV1(kind="ABSENT"),
        ),
    )
    assert root_direct.kind == "SUCCESS"
    assert tuple(e.path.value for e in root_direct.entries) == (
        "assets",
        "src",
        "README.md",
    )


def test_list_path_root_that_is_not_a_directory_fails_closed() -> None:
    tree = DiscoveryTree(_FIXTURE_FILES)
    for path in ("README.md", "missing"):
        result = list_files(
            tree,
            ListFilesActionV1(
                schema_version=1,
                action_type="list_files",
                root=PathLocationV1(kind="PATH", path=CanonicalRelativePathV1(path)),
                recursive=True,
                max_entries=500,
                cursor=AbsentV1(kind="ABSENT"),
            ),
        )
        assert result.kind == "ERROR"
        assert result.error_code == "PATH_NOT_DIRECTORY"


def test_list_entry_variants_and_size_bytes_are_exact() -> None:
    tree = DiscoveryTree(_FIXTURE_FILES)
    result = list_files(
        tree,
        ListFilesActionV1(
            schema_version=1,
            action_type="list_files",
            root=RootLocationV1(kind="ROOT"),
            recursive=True,
            max_entries=500,
            cursor=AbsentV1(kind="ABSENT"),
        ),
    )
    assert result.kind == "SUCCESS"
    by_path = {e.path.value: e for e in result.entries}
    directory = by_path["src"]
    assert directory.kind == "DIRECTORY"
    assert directory.size_bytes.kind == "ABSENT"
    assert directory.text_profile.kind == "ABSENT"
    text_file = by_path["src/a.py"]
    assert text_file.kind == "TEXT_FILE"
    assert text_file.size_bytes.value == len(_FIXTURE_FILES["src/a.py"])
    assert text_file.text_profile.value.encoding == "UTF8"
    assert text_file.text_profile.value.newline == "LF"
    non_text = by_path["assets/logo.png"]
    assert non_text.kind == "NON_TEXT_FILE"
    assert non_text.size_bytes.value == len(_FIXTURE_FILES["assets/logo.png"])
    assert non_text.text_profile.kind == "ABSENT"


def test_list_byte_bound_truncates_and_continues() -> None:
    files = {f"src/dir{index:03d}/file{index:03d}.txt": b"x\n" for index in range(300)}
    tree = DiscoveryTree(files)
    first = list_files(
        tree,
        ListFilesActionV1(
            schema_version=1,
            action_type="list_files",
            root=RootLocationV1(kind="ROOT"),
            recursive=True,
            max_entries=500,
            cursor=AbsentV1(kind="ABSENT"),
        ),
    )
    # 300 files plus their 301 ancestor directories: the byte bound stops
    # the first page well before the 601 entries, and continuation covers
    # everything exactly once.
    assert first.kind == "SUCCESS"
    assert first.truncated is True
    assert len(first.entries) < 601
    collected: list[ListFilesEntryV1] = []
    cursor: OptionalListFilesCursorV1 = first.next_cursor
    collected.extend(first.entries)
    pages = 1
    while cursor.kind == "PRESENT":
        page = list_files(
            tree,
            ListFilesActionV1(
                schema_version=1,
                action_type="list_files",
                root=RootLocationV1(kind="ROOT"),
                recursive=True,
                max_entries=500,
                cursor=cursor,
            ),
        )
        assert page.kind == "SUCCESS"
        collected.extend(page.entries)
        cursor = page.next_cursor
        pages += 1
        assert pages < 100
    assert len(collected) == 601
    assert len({e.path.value for e in collected}) == 601


def test_list_search_succeed_on_the_bound_snapshot_protocol() -> None:
    fake = DiscoveryTree(_FIXTURE_FILES)
    assert isinstance(fake, ReadableTreeV1)

    def consume(tree: ReadableTreeV1) -> tuple[int, int]:
        listed = list_files(
            tree,
            ListFilesActionV1(
                schema_version=1,
                action_type="list_files",
                root=RootLocationV1(kind="ROOT"),
                recursive=True,
                max_entries=500,
                cursor=AbsentV1(kind="ABSENT"),
            ),
        )
        searched = search_text(
            tree,
            SearchTextActionV1(
                schema_version=1,
                action_type="search_text",
                query="needle",
                roots=(RootLocationV1(kind="ROOT"),),
                case_sensitive=True,
                context_lines=0,
                max_results=100,
                cursor=AbsentV1(kind="ABSENT"),
            ),
        )
        assert listed.kind == "SUCCESS" and searched.kind == "SUCCESS"
        return len(listed.entries), len(searched.matches)

    assert consume(fake) == (8, 5)

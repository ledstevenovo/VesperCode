"""T32.1 legacy step 32.B: production paged List/Search continuation tests.

The production Task 11.B tools page over the fixed mechanism tree with
exact cursor identity: paged equals unpaged with no duplicates or
omissions; an internally tampered cursor returns ``CONTINUATION_INVALID``
and a consistently bound cursor against a drifted visible tree returns
``CONTINUATION_STALE`` — both with zero payload (SPEC §4.2.8/AC-17).
"""

from __future__ import annotations

import pytest

pytest.importorskip("pydantic")

from vespercode.canonical.path_v1 import CanonicalRelativePathV1
from vespercode.contracts.location import RootLocationV1
from vespercode.contracts.optional import AbsentV1, PresentV1
from vespercode.tools.file_actions import (
    ListFilesActionV1,
    SearchTextActionV1,
    list_files_query_digest,
    search_text_query_digest,
)
from vespercode.tools.file_results import (
    FileToolErrorV1,
    ListFilesEntryV1,
    ListFilesSuccessV1,
    OptionalListFilesCursorV1,
    OptionalSearchTextCursorV1,
    SearchTextMatchV1,
    SearchTextSuccessV1,
    list_files_cursor_digest,
    search_text_cursor_digest,
)
from vespercode.tools.list_files import list_files
from vespercode.tools.search_text import search_text
from vespercode.trees.readable import ReadableTreeV1

from scripts.run_mechanism_demo import MechanismHarness


@pytest.fixture
def mechanism_harness() -> MechanismHarness:
    return MechanismHarness()


def _list_action(
    max_entries: int, cursor: OptionalListFilesCursorV1
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
    max_results: int, cursor: OptionalSearchTextCursorV1
) -> SearchTextActionV1:
    return SearchTextActionV1(
        schema_version=1,
        action_type="search_text",
        query="return",
        roots=(RootLocationV1(kind="ROOT"),),
        case_sensitive=True,
        context_lines=0,
        max_results=max_results,
        cursor=cursor,
    )


def _paged_list(tree: ReadableTreeV1) -> tuple[ListFilesEntryV1, ...]:
    collected: list[ListFilesEntryV1] = []
    cursor: OptionalListFilesCursorV1 = AbsentV1(kind="ABSENT")
    while True:
        page = list_files(tree, _list_action(2, cursor))
        assert isinstance(page, ListFilesSuccessV1)
        collected.extend(page.entries)
        if page.next_cursor.kind == "ABSENT":
            return tuple(collected)
        cursor = page.next_cursor
    return tuple(collected)


def _paged_search(tree: ReadableTreeV1) -> tuple[SearchTextMatchV1, ...]:
    collected: list[SearchTextMatchV1] = []
    cursor: OptionalSearchTextCursorV1 = AbsentV1(kind="ABSENT")
    while True:
        page = search_text(tree, _search_action(2, cursor))
        assert isinstance(page, SearchTextSuccessV1)
        collected.extend(page.matches)
        if page.next_cursor.kind == "ABSENT":
            return tuple(collected)
        cursor = page.next_cursor
    return tuple(collected)


def test_paged_list_equals_unpaged_with_exact_cursor_identity(
    mechanism_harness: MechanismHarness,
) -> None:
    tree, _other = mechanism_harness.paged_trees
    unpaged = list_files(tree, _list_action(500, AbsentV1(kind="ABSENT")))
    assert isinstance(unpaged, ListFilesSuccessV1)
    assert not unpaged.truncated
    assert unpaged.next_cursor.kind == "ABSENT"
    paged = _paged_list(tree)
    assert [entry.path.value for entry in paged] == [
        entry.path.value for entry in unpaged.entries
    ]
    # Exact cursor identity: the issued cursor's self-digest binds every
    # field and the query digest binds the cursor-free query.
    first = list_files(tree, _list_action(2, AbsentV1(kind="ABSENT")))
    assert isinstance(first, ListFilesSuccessV1)
    assert first.truncated
    assert first.next_cursor.kind == "PRESENT"
    cursor = first.next_cursor.value
    assert cursor.digest == list_files_cursor_digest(cursor)
    assert cursor.query_digest == list_files_query_digest(
        _list_action(2, AbsentV1(kind="ABSENT"))
    )


def test_paged_search_equals_unpaged_with_exact_cursor_identity(
    mechanism_harness: MechanismHarness,
) -> None:
    tree, _other = mechanism_harness.paged_trees
    unpaged = search_text(tree, _search_action(100, AbsentV1(kind="ABSENT")))
    assert isinstance(unpaged, SearchTextSuccessV1)
    paged = _paged_search(tree)
    assert [(m.path.value, m.line, m.column) for m in paged] == [
        (m.path.value, m.line, m.column) for m in unpaged.matches
    ]
    first = search_text(tree, _search_action(2, AbsentV1(kind="ABSENT")))
    assert isinstance(first, SearchTextSuccessV1)
    assert first.truncated
    assert first.next_cursor.kind == "PRESENT"
    cursor = first.next_cursor.value
    assert cursor.digest == search_text_cursor_digest(cursor)
    assert cursor.query_digest == search_text_query_digest(
        _search_action(2, AbsentV1(kind="ABSENT"))
    )


def test_tampered_list_cursor_returns_zero_payload(
    mechanism_harness: MechanismHarness,
) -> None:
    tree, _other = mechanism_harness.paged_trees
    first = list_files(tree, _list_action(2, AbsentV1(kind="ABSENT")))
    assert isinstance(first, ListFilesSuccessV1)
    assert first.next_cursor.kind == "PRESENT"
    tampered = first.next_cursor.value.model_copy(
        update={"next_canonical_path": CanonicalRelativePathV1("zzz")}
    )
    result = list_files(
        tree, _list_action(2, PresentV1(kind="PRESENT", value=tampered))
    )
    assert isinstance(result, FileToolErrorV1)
    assert result.error_code == "CONTINUATION_INVALID"
    assert not hasattr(result, "entries")


def test_tampered_search_cursor_returns_zero_payload(
    mechanism_harness: MechanismHarness,
) -> None:
    tree, _other = mechanism_harness.paged_trees
    first = search_text(tree, _search_action(2, AbsentV1(kind="ABSENT")))
    assert isinstance(first, SearchTextSuccessV1)
    assert first.next_cursor.kind == "PRESENT"
    tampered = first.next_cursor.value.model_copy(update={"next_match_index": 99})
    result = search_text(
        tree, _search_action(2, PresentV1(kind="PRESENT", value=tampered))
    )
    assert isinstance(result, FileToolErrorV1)
    assert result.error_code == "CONTINUATION_INVALID"
    assert not hasattr(result, "matches")


def test_list_cursor_against_drifted_tree_returns_zero_payload(
    mechanism_harness: MechanismHarness,
) -> None:
    tree, drifted = mechanism_harness.paged_trees
    first = list_files(tree, _list_action(2, AbsentV1(kind="ABSENT")))
    assert isinstance(first, ListFilesSuccessV1)
    assert first.next_cursor.kind == "PRESENT"
    result = list_files(drifted, _list_action(2, first.next_cursor))
    assert isinstance(result, FileToolErrorV1)
    assert result.error_code == "CONTINUATION_STALE"
    assert not hasattr(result, "entries")


def test_search_cursor_against_drifted_tree_returns_zero_payload(
    mechanism_harness: MechanismHarness,
) -> None:
    tree, drifted = mechanism_harness.paged_trees
    first = search_text(tree, _search_action(2, AbsentV1(kind="ABSENT")))
    assert isinstance(first, SearchTextSuccessV1)
    assert first.next_cursor.kind == "PRESENT"
    result = search_text(drifted, _search_action(2, first.next_cursor))
    assert isinstance(result, FileToolErrorV1)
    assert result.error_code == "CONTINUATION_STALE"
    assert not hasattr(result, "matches")

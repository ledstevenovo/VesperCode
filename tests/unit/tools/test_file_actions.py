"""T11.1 legacy step 11.A: closed file-tool action schema tests.

The three file actions are closed pydantic schemas under SPEC §4.2.2:
every field is required, unknown fields and wrong types (including bool
coercion to integers and integers to booleans) are rejected, and each
range bound (``max_entries`` 1..500, ``start_line`` >=1, ``line_count``
1..400, ``max_bytes`` 1..32768, ``query`` 1..256 UTF-8 bytes, roots 1..8
unique non-aliasing, ``context_lines`` 0..2, ``max_results`` 1..100) is
enforced before any tool execution.  The query digests bind exactly the
cursor-free query fields (SPEC §4.2.2 ``ListFilesQueryV1`` /
``SearchTextQueryV1``) and can never be changed by a continuation.
"""

from __future__ import annotations

import pytest

# The file-tool contracts are pydantic runtime models; the hash-locked gate
# toolchain does not install runtime dependencies, so this module skips
# cleanly there instead of failing at collection (formal env runs it fully).
pytest.importorskip("pydantic")

from pydantic import ValidationError

from vespercode.canonical.path_v1 import CanonicalRelativePathV1
from vespercode.tools.file_actions import (
    ListFilesActionV1,
    ReadFileActionV1,
    SearchTextActionV1,
    list_files_query_digest,
    search_text_query_digest,
)
from vespercode.tools.file_results import (
    ListFilesCursorV1,
    SearchTextCursorV1,
)


def _list_action(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "schema_version": 1,
        "action_type": "list_files",
        "root": {"kind": "ROOT"},
        "recursive": True,
        "max_entries": 10,
        "cursor": {"kind": "ABSENT"},
    }
    base.update(overrides)
    return base


def _read_action(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "schema_version": 1,
        "action_type": "read_file",
        "path": {"value": "src/a.py"},
        "start_line": 1,
        "line_count": 10,
        "max_bytes": 4096,
    }
    base.update(overrides)
    return base


def _search_action(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "schema_version": 1,
        "action_type": "search_text",
        "query": "needle",
        "roots": ({"kind": "ROOT"},),
        "case_sensitive": True,
        "context_lines": 1,
        "max_results": 20,
        "cursor": {"kind": "ABSENT"},
    }
    base.update(overrides)
    return base


def _list_cursor() -> dict[str, object]:
    return {
        "schema_version": 1,
        "cursor_type": "LIST_FILES_CURSOR_V1",
        "visible_tree_digest": "a" * 64,
        "query_digest": "b" * 64,
        "next_directory_rank": 0,
        "next_canonical_path": {"value": "src"},
        "digest": "c" * 64,
    }


def _search_cursor() -> dict[str, object]:
    return {
        "schema_version": 1,
        "cursor_type": "SEARCH_TEXT_CURSOR_V1",
        "visible_tree_digest": "a" * 64,
        "query_digest": "b" * 64,
        "next_canonical_path": {"value": "src/a.py"},
        "next_match_index": 0,
        "digest": "c" * 64,
    }


def test_list_files_action_closed_schema_matrix() -> None:
    assert ListFilesActionV1.model_validate(_list_action()) is not None
    assert (
        ListFilesActionV1.model_validate(
            _list_action(root={"kind": "PATH", "path": {"value": "src"}})
        )
        is not None
    )
    assert (
        ListFilesActionV1.model_validate(
            _list_action(cursor={"kind": "PRESENT", "value": _list_cursor()})
        )
        is not None
    )
    # unknown, missing, and wrong-typed fields are rejected.
    for bad in (
        _list_action(unexpected=True),
        {key: value for key, value in _list_action().items() if key != "max_entries"},
        _list_action(action_type="read_file"),
        _list_action(recursive=1),
        _list_action(recursive="yes"),
        _list_action(max_entries=True),
        _list_action(max_entries=0),
        _list_action(max_entries=501),
        _list_action(max_entries="10"),
        _list_action(root={"kind": "PATH"}),
        _list_action(cursor={"kind": "PRESENT", "value": _search_cursor()}),
    ):
        with pytest.raises(ValidationError):
            ListFilesActionV1.model_validate(bad)


def test_read_file_action_closed_schema_matrix() -> None:
    assert ReadFileActionV1.model_validate(_read_action()) is not None
    for bad in (
        _read_action(unexpected=True),
        {key: value for key, value in _read_action().items() if key != "path"},
        _read_action(action_type="list_files"),
        _read_action(path={"value": ""}),
        _read_action(path={"value": "/abs"}),
        _read_action(start_line=0),
        _read_action(start_line=True),
        _read_action(line_count=0),
        _read_action(line_count=401),
        _read_action(line_count=True),
        _read_action(max_bytes=0),
        _read_action(max_bytes=32769),
        _read_action(max_bytes=True),
        _read_action(path=None),
    ):
        with pytest.raises(ValidationError):
            ReadFileActionV1.model_validate(bad)


def test_search_text_action_closed_schema_matrix() -> None:
    assert SearchTextActionV1.model_validate(_search_action()) is not None
    # ROOT must be the only root when present; empty, duplicate, and
    # case/NFC-aliasing root sets are rejected before any execution.
    assert (
        SearchTextActionV1.model_validate(
            _search_action(roots=({"kind": "PATH", "path": {"value": "src"}},))
        )
        is not None
    )
    for bad in (
        _search_action(unexpected=True),
        {key: value for key, value in _search_action().items() if key != "query"},
        _search_action(roots=()),
        _search_action(
            roots=tuple({"kind": "PATH", "path": {"value": f"d{i}"}} for i in range(9))
        ),
        _search_action(
            roots=({"kind": "ROOT"}, {"kind": "PATH", "path": {"value": "src"}})
        ),
        _search_action(
            roots=(
                {"kind": "PATH", "path": {"value": "src"}},
                {"kind": "PATH", "path": {"value": "src"}},
            )
        ),
        _search_action(
            roots=(
                {"kind": "PATH", "path": {"value": "src"}},
                {"kind": "PATH", "path": {"value": "SRC"}},
            )
        ),
        _search_action(
            roots=(
                {"kind": "PATH", "path": {"value": "é"}},
                {"kind": "PATH", "path": {"value": "é"}},
            )
        ),
        # NFC-then-casefold aliasing: É and e + combining acute collide.
        _search_action(
            roots=(
                {"kind": "PATH", "path": {"value": "É"}},
                {"kind": "PATH", "path": {"value": "é"}},
            )
        ),
        _search_action(query=""),
        _search_action(query="x" * 257),
        _search_action(query="你" * 100),
        _search_action(query=True),
        _search_action(case_sensitive=1),
        _search_action(case_sensitive="yes"),
        _search_action(context_lines=3),
        _search_action(context_lines=True),
        _search_action(max_results=0),
        _search_action(max_results=101),
        _search_action(max_results=True),
        _search_action(cursor={"kind": "PRESENT", "value": _list_cursor()}),
    ):
        with pytest.raises(ValidationError):
            SearchTextActionV1.model_validate(bad)


def test_actions_are_frozen_and_reject_extra_fields() -> None:
    action = ListFilesActionV1.model_validate(_list_action())
    # Frozen closed schema: every field assignment fails closed.
    with pytest.raises(ValidationError):
        action.recursive = False
    with pytest.raises(ValidationError):
        action.max_entries = 5
    with pytest.raises(ValidationError):
        action.model_validate(action.model_dump() | {"unexpected": True})


def test_list_query_digest_binds_only_cursor_free_query_fields() -> None:
    base = ListFilesActionV1.model_validate(_list_action())
    same = ListFilesActionV1.model_validate(_list_action())
    different_root = ListFilesActionV1.model_validate(
        _list_action(root={"kind": "PATH", "path": {"value": "src"}})
    )
    different_recursive = ListFilesActionV1.model_validate(
        _list_action(recursive=False)
    )
    different_entries = ListFilesActionV1.model_validate(_list_action(max_entries=25))
    with_cursor = ListFilesActionV1.model_validate(
        _list_action(cursor={"kind": "PRESENT", "value": _list_cursor()})
    )
    assert list_files_query_digest(base) == list_files_query_digest(same)
    # The cursor is never part of the query identity.
    assert list_files_query_digest(base) == list_files_query_digest(with_cursor)
    for changed in (different_root, different_recursive, different_entries):
        assert list_files_query_digest(base) != list_files_query_digest(changed)
    assert len(list_files_query_digest(base)) == 64


def test_search_query_digest_binds_only_cursor_free_query_fields() -> None:
    base = SearchTextActionV1.model_validate(_search_action())
    same = SearchTextActionV1.model_validate(_search_action())
    different_query = SearchTextActionV1.model_validate(_search_action(query="other"))
    different_case = SearchTextActionV1.model_validate(
        _search_action(case_sensitive=False)
    )
    different_context = SearchTextActionV1.model_validate(
        _search_action(context_lines=0)
    )
    different_results = SearchTextActionV1.model_validate(_search_action(max_results=5))
    different_roots = SearchTextActionV1.model_validate(
        _search_action(roots=({"kind": "PATH", "path": {"value": "src"}},))
    )
    with_cursor = SearchTextActionV1.model_validate(
        _search_action(cursor={"kind": "PRESENT", "value": _search_cursor()})
    )
    assert search_text_query_digest(base) == search_text_query_digest(same)
    assert search_text_query_digest(base) == search_text_query_digest(with_cursor)
    for changed in (
        different_query,
        different_case,
        different_context,
        different_results,
        different_roots,
    ):
        assert search_text_query_digest(base) != search_text_query_digest(changed)
    assert len(search_text_query_digest(base)) == 64


def test_file_tool_query_digests_are_domain_separated() -> None:
    list_digest = list_files_query_digest(
        ListFilesActionV1.model_validate(_list_action())
    )
    search_digest = search_text_query_digest(
        SearchTextActionV1.model_validate(_search_action())
    )
    assert list_digest != search_digest


def test_list_cursor_schema_is_closed() -> None:
    assert ListFilesCursorV1.model_validate(_list_cursor()) is not None
    for bad in (
        _list_cursor() | {"digest": "short"},
        _list_cursor() | {"next_directory_rank": 2},
        _list_cursor() | {"next_directory_rank": True},
        _list_cursor() | {"visible_tree_digest": "x" * 64},
        _list_cursor() | {"cursor_type": "SEARCH_TEXT_CURSOR_V1"},
        _list_cursor() | {"next_canonical_path": {"value": "not-canonical/../x"}},
        _list_cursor() | {"schema_version": True},
        _list_cursor() | {"unexpected": 1},
    ):
        with pytest.raises(ValidationError):
            ListFilesCursorV1.model_validate(bad)


def test_search_cursor_schema_is_closed() -> None:
    assert SearchTextCursorV1.model_validate(_search_cursor()) is not None
    for bad in (
        _search_cursor() | {"digest": "short"},
        _search_cursor() | {"next_match_index": -1},
        _search_cursor() | {"next_match_index": True},
        _search_cursor() | {"next_canonical_path": ""},
        _search_cursor() | {"visible_tree_digest": "x" * 64},
        _search_cursor() | {"cursor_type": "LIST_FILES_CURSOR_V1"},
        _search_cursor() | {"unexpected": 1},
    ):
        with pytest.raises(ValidationError):
            SearchTextCursorV1.model_validate(bad)


def test_cursor_models_are_frozen() -> None:
    value = ListFilesCursorV1.model_validate(_list_cursor())
    with pytest.raises(ValidationError):
        value.digest = "f" * 64
    with pytest.raises(ValidationError):
        value.next_canonical_path = CanonicalRelativePathV1("other")

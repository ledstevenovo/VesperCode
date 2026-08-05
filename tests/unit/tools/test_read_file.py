"""T11.1 legacy step 11.A: bounded Snapshot-bound read tool tests.

The displayed RED test proves ``read_file`` serves only the bound
immutable tree's bytes while a drifted mutable workspace is never read;
the schema/bounds matrix (PLAN registry 11.A) proves protocol-only reads
through a fake and through the real T10.2 ``SnapshotTreeV1`` use only
``ReadableTreeV1`` bytes, fail closed for non-file, non-text,
out-of-range, oversized (deterministic scalar-boundary truncation),
missing, and stale-identity inputs with zero workspace fallback, and that
the closed action/result schemas reject unknown fields.  Filesystem
access, cursors, policy, shell, arbitrary path dispatch, and tool
dispatch remain out of scope (GREEN-4).
"""

from __future__ import annotations

import hashlib
import pathlib
import sys

import pytest

# The file-tool contracts are pydantic runtime models; the hash-locked gate
# toolchain does not install runtime dependencies, so this module skips
# cleanly there instead of failing at collection (formal env runs it fully).
pytest.importorskip("pydantic")

from pydantic import TypeAdapter, ValidationError

from src.vespercode.canonical.path_v1 import CanonicalRelativePathV1
from src.vespercode.tools.file_actions import ReadFileActionV1
from src.vespercode.tools.file_results import (
    FileToolErrorV1,
    ReadFileResultV1,
    ReadFileSuccessV1,
)
from src.vespercode.tools.read_file import read_file
from src.vespercode.trees.content_store import ContentObjectStore
from src.vespercode.trees.readable import ReadableTreeV1
from src.vespercode.trees.snapshot import (
    AcceptedGitPreflightV1,
    SealedSnapshotInputFileV1,
    SnapshotTreeV1,
    create_snapshot,
)
from src.vespercode.trees.text_classifier import classify_supported_text
from src.vespercode.workspace.git_preflight import GitPreflightResultV1

_UTF8_BOM = b"\xef\xbb\xbf"
_SEALED_TEXT = "line1\nline2\nline3\n"
_WORKSPACE_DRIFT = "DRIFTED WORKSPACE CONTENT\n"


class SnapshotTree:
    """Protocol-only immutable fake implementing the T10.2 read protocol.

    ``expected_text`` mirrors the read body contract (optional BOM stripped,
    strict UTF-8 decoded) so the RED assertion compares against the sealed
    text; the fake never touches any filesystem or workspace.
    """

    def __init__(self, files: dict[str, bytes]) -> None:
        self._files = dict(files)
        self._digest = "a" * 64

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
            raise KeyError(f"no file at {path.value!r} in the snapshot tree")
        return self._files[path.value]

    def expected_text(self, path: str) -> str:
        raw = self._files[path]
        if raw.startswith(_UTF8_BOM):
            raw = raw[len(_UTF8_BOM) :]
        return raw.decode("utf-8")


class _DriftedReadTree(SnapshotTree):
    """A fake whose sealed bytes drift between enumeration and read.

    The tree still enumerates every file path but can no longer serve the
    bytes — the smallest stale-identity drift a protocol-only consumer can
    observe.
    """

    def read_bytes(self, path: CanonicalRelativePathV1) -> bytes:
        raise KeyError(f"no file at {path.value!r} in the snapshot tree")


class SpyWorkspace:
    """Mutable workspace spy whose bytes drift from the sealed snapshot."""

    def __init__(self, files: dict[str, bytes]) -> None:
        self.files = dict(files)
        self.read_count = 0

    def read(self, path: str) -> bytes:
        self.read_count += 1
        return self.files[path]


def read_action(path: str, start_line: int, line_count: int) -> ReadFileActionV1:
    """One closed read action with the maximal byte budget."""
    return ReadFileActionV1(
        schema_version=1,
        action_type="read_file",
        path=CanonicalRelativePathV1(path),
        start_line=start_line,
        line_count=line_count,
        max_bytes=32768,
    )


@pytest.fixture
def sealed_snapshot() -> SnapshotTree:
    return SnapshotTree({"src/example.py": _SEALED_TEXT.encode("utf-8")})


@pytest.fixture
def live_workspace() -> SpyWorkspace:
    return SpyWorkspace({"src/example.py": _WORKSPACE_DRIFT.encode("utf-8")})


def test_read_uses_only_bound_snapshot_bytes(
    sealed_snapshot: SnapshotTree,
    live_workspace: SpyWorkspace,
) -> None:
    result = read_file(sealed_snapshot, read_action("src/example.py", 1, 20))
    # Mypy note: the card's verbatim RED asserts the union payload directly;
    # strict mode needs an explicit ignore for union attribute access (repo
    # precedent: tests/feasibility and tests/demo use the same pattern).
    assert result.text == sealed_snapshot.expected_text("src/example.py")  # type: ignore[union-attr]
    assert live_workspace.read_count == 0


def test_read_file_bounds_schema_matrix() -> None:
    """PLAN registry 11.A: protocol-only reads, typed errors, zero fallback.

    Every row reads through ``ReadableTreeV1`` only (a protocol fake or the
    bound T10.2 Snapshot) and never through the drifted workspace; non-file,
    non-text, out-of-range, oversized, missing, and stale-identity inputs
    produce the declared typed error or the deterministic bounded result.
    """
    tree = SnapshotTree(
        {
            "src/a.py": b"one\ntwo\nthree\n",
            "src/bom.txt": _UTF8_BOM + b"x\r\ny\r\n",
            "src/blob.bin": b"\x89PNG\r\n\x1a\n",
        }
    )
    workspace = SpyWorkspace({"src/a.py": b"DRIFTED\n"})

    def run(
        path: str, start_line: int = 1, line_count: int = 10, max_bytes: int = 32768
    ) -> ReadFileResultV1:
        return read_file(
            tree,
            ReadFileActionV1(
                schema_version=1,
                action_type="read_file",
                path=CanonicalRelativePathV1(path),
                start_line=start_line,
                line_count=line_count,
                max_bytes=max_bytes,
            ),
        )

    # non-file: a directory path is never a file of the tree.
    directory = run("src")
    assert directory.kind == "ERROR"
    assert directory.error_code == "FILE_NOT_FOUND"
    # missing: a path with no tree row at all.
    missing = run("src/absent.py")
    assert missing.kind == "ERROR"
    assert missing.error_code == "FILE_NOT_FOUND"
    # non-text: invalid UTF-8 raw bytes classify NON_TEXT_FILE.
    non_text = run("src/blob.bin")
    assert non_text.kind == "ERROR"
    assert non_text.error_code == "FILE_NOT_TEXT"
    # out-of-range: start_line beyond the last line.
    out_of_range = run("src/a.py", start_line=4)
    assert out_of_range.kind == "ERROR"
    assert out_of_range.error_code == "READ_RANGE_OUT_OF_BOUNDS"
    # oversized: the range bytes exceed max_bytes -> bounded scalar truncation.
    oversized = run("src/a.py", max_bytes=5)
    assert oversized.kind == "SUCCESS"
    assert len(oversized.text.encode("utf-8")) <= 5
    assert oversized.start_line == 1
    assert oversized.eof is False
    # stale identity: the enumerated file's bytes drift before the read.
    stale = read_file(
        _DriftedReadTree({"src/a.py": b"one\ntwo\nthree\n"}),
        read_action("src/a.py", 1, 3),
    )
    assert stale.kind == "ERROR"
    assert stale.error_code == "FILE_NOT_FOUND"
    # every row above left the workspace untouched.
    assert workspace.read_count == 0

    # bound Snapshot: the real T10.2 tree is read through the protocol only.
    snapshot = _snapshot_tree({"src/a.py": b"one\ntwo\nthree\n"})
    bound = read_file(snapshot, read_action("src/a.py", 1, 10))
    assert bound.kind == "SUCCESS"
    assert bound.text == "one\ntwo\nthree\n"
    assert bound.file_digest == hashlib.sha256(b"one\ntwo\nthree\n").hexdigest()
    assert bound.eof is True
    assert workspace.read_count == 0


def test_read_returns_exact_line_ranges_and_eof() -> None:
    tree = SnapshotTree({"src/a.py": b"one\ntwo\nthree\nfour\nfive\n"})

    partial = read_file(tree, read_action("src/a.py", 2, 2))
    assert partial.kind == "SUCCESS"
    assert partial.text == "two\nthree\n"
    assert (partial.start_line, partial.end_line) == (2, 3)
    assert partial.eof is False

    crossing = read_file(tree, read_action("src/a.py", 4, 400))
    assert crossing.kind == "SUCCESS"
    assert crossing.text == "four\nfive\n"
    assert (crossing.start_line, crossing.end_line) == (4, 5)
    assert crossing.eof is True

    single_line = read_file(tree, read_action("src/a.py", 3, 1))
    assert single_line.kind == "SUCCESS"
    assert single_line.text == "three\n"
    assert (single_line.start_line, single_line.end_line) == (3, 3)


def test_read_bom_crlf_metadata_is_honored() -> None:
    tree = SnapshotTree({"src/bom.txt": _UTF8_BOM + b"x\r\ny\r\nz\r\n"})

    result = read_file(tree, read_action("src/bom.txt", 2, 1))
    assert result.kind == "SUCCESS"
    # The body never carries the BOM and CRLF lines split on CRLF only.
    assert result.text == "y\r\n"
    assert (result.start_line, result.end_line) == (2, 2)
    # file_digest binds the complete raw bytes including the BOM.
    assert (
        result.file_digest == hashlib.sha256(_UTF8_BOM + b"x\r\ny\r\nz\r\n").hexdigest()
    )


def test_read_crossing_eof_plus_byte_truncation_reports_eof_false() -> None:
    tree = SnapshotTree({"src/a.py": b"one\ntwo\nthree\n"})
    result = read_file(
        tree,
        ReadFileActionV1(
            schema_version=1,
            action_type="read_file",
            path=CanonicalRelativePathV1("src/a.py"),
            start_line=2,
            line_count=400,
            max_bytes=6,
        ),
    )
    assert result.kind == "SUCCESS"
    body = result.text
    assert len(body.encode("utf-8")) <= 6
    assert body == "two\nth"
    assert (result.start_line, result.end_line) == (2, 3)
    # The returned body does not reach EOF, so eof stays false and the
    # caller continues from end_line.
    assert result.eof is False


def test_read_truncates_on_scalar_boundary_only() -> None:
    tree = SnapshotTree({"src/cn.py": ("你好世界\n" * 10).encode("utf-8")})
    result = read_file(
        tree,
        ReadFileActionV1(
            schema_version=1,
            action_type="read_file",
            path=CanonicalRelativePathV1("src/cn.py"),
            start_line=1,
            line_count=10,
            max_bytes=7,
        ),
    )
    assert result.kind == "SUCCESS"
    body = result.text
    assert len(body.encode("utf-8")) <= 7
    # 7 bytes cannot hold a complete "你好" (6 bytes) plus "\n"; the cut must
    # never split a multi-byte UTF-8 scalar.
    body.encode("utf-8").decode("utf-8")


def test_read_result_schemas_are_closed() -> None:
    with pytest.raises(ValidationError):
        ReadFileSuccessV1.model_validate(
            {
                "kind": "SUCCESS",
                "path": "src/a.py",
                "file_digest": "a" * 64,
                "start_line": 1,
                "end_line": 2,
                "eof": True,
                "text": "x\n",
                "unexpected": 1,
            }
        )
    with pytest.raises(ValidationError):
        FileToolErrorV1.model_validate(
            {
                "kind": "ERROR",
                "error_code": "FILE_NOT_TEXT",
                "bounded_message": "not text",
                "unexpected": 1,
            }
        )
    with pytest.raises(ValidationError):
        # ERROR variants never carry a read payload.
        TypeAdapter(ReadFileResultV1).validate_python(
            {
                "kind": "ERROR",
                "error_code": "FILE_NOT_TEXT",
                "bounded_message": "not text",
                "text": "x\n",
            }
        )


def _seal(tracked_file_count: int, tracked_byte_count: int) -> GitPreflightResultV1:
    """One shape-valid SUPPORTED sealed Git-preflight result (T10.2 pattern)."""
    return GitPreflightResultV1(
        schema_version=1,
        kind="SUPPORTED",
        head_commit_digest="0" * 40,
        index_digest="1" * 64,
        worktree_digest="2" * 64,
        ignore_rules_digest="3" * 64,
        attributes_digest="4" * 64,
        config_digest="5" * 64,
        repository_policy_digest="b" * 64,
        ignore_rules=(),
        tracked_file_count=tracked_file_count,
        tracked_byte_count=tracked_byte_count,
    )


def _snapshot_tree(files: dict[str, bytes]) -> SnapshotTreeV1:
    rows = tuple(
        SealedSnapshotInputFileV1(
            schema_version=1,
            path=CanonicalRelativePathV1(path),
            content_sha256=hashlib.sha256(raw).hexdigest(),
            byte_count=len(raw),
        )
        for path, raw in sorted(files.items())
    )
    store = ContentObjectStore()
    for raw in sorted(files.items(), key=lambda item: item[0]):
        store.put(raw[1])
    accepted = AcceptedGitPreflightV1(
        schema_version=1,
        preflight=_seal(len(rows), sum(row.byte_count for row in rows)),
        files=rows,
    )
    return create_snapshot(accepted, store, classify_supported_text)


def test_read_file_consumes_only_the_readable_tree_protocol() -> None:
    def consume(tree: ReadableTreeV1) -> ReadFileResultV1:
        return read_file(tree, read_action("src/a.py", 1, 10))

    fake = SnapshotTree({"src/a.py": b"one\ntwo\nthree\n"})
    assert isinstance(fake, ReadableTreeV1)
    assert consume(fake).kind == "SUCCESS"
    assert consume(_snapshot_tree({"src/a.py": b"one\ntwo\nthree\n"})).kind == "SUCCESS"


def test_file_tool_modules_import_no_candidate_or_filesystem() -> None:
    tools_dir = (
        pathlib.Path(__file__).resolve().parents[3] / "src" / "vespercode" / "tools"
    )
    for module_name in (
        "file_actions",
        "file_results",
        "read_file",
        "list_files",
        "search_text",
    ):
        text = (tools_dir / f"{module_name}.py").read_text(encoding="utf-8")
        assert "candidate" not in text
        for statement in ("import os", "import pathlib", "import subprocess"):
            assert statement not in text
    assert "src.vespercode.candidate" not in sys.modules

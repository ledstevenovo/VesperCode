"""T10.2 legacy step 10.C: SnapshotTree read protocol and verification tests.

Unit surface with synthetic sealed inputs: the minimal ``ReadableTreeV1``
protocol compatibility, the exact ``digest``/``root_digest`` aliasing,
deterministic canonical directory/file-path enumeration and exact byte
reads, every construction-time drift rejection, the closed
``verify_snapshot`` drift matrix, and the bounded read-only proof — the
tree can only be observed through the immutable protocol surface and can
never mutate (GREEN-2/3/4).  The real sealed-preflight parity matrix lives
in ``tests/integration/windows/test_snapshot_from_preflight.py``.
"""

from __future__ import annotations

import hashlib

import pytest

# The Snapshot contracts are pydantic runtime models; the hash-locked gate
# toolchain does not install runtime dependencies, so this module skips
# cleanly there instead of failing at collection (formal env runs it fully).
pytest.importorskip("pydantic")

from pydantic import ValidationError

from vespercode.canonical.path_v1 import CanonicalRelativePathV1
from vespercode.trees.content_store import ContentObjectStore
from vespercode.trees.readable import ReadableTreeV1
from vespercode.trees.snapshot import (
    AcceptedGitPreflightV1,
    SealedSnapshotInputFileV1,
    SnapshotIntegrityError,
    SnapshotIntegrityResultV1,
    SnapshotTreeV1,
    create_snapshot,
    verify_snapshot,
)
from vespercode.trees.text_classifier import classify_supported_text
from vespercode.workspace.git_preflight import GitPreflightResultV1

_A = "a" * 64
_B = "b" * 64


def _seal(*, tracked_file_count: int, tracked_byte_count: int) -> GitPreflightResultV1:
    """One shape-valid SUPPORTED sealed Git-preflight result."""
    return GitPreflightResultV1(
        schema_version=1,
        kind="SUPPORTED",
        head_commit_digest="0" * 40,
        index_digest="1" * 64,
        worktree_digest="2" * 64,
        ignore_rules_digest="3" * 64,
        attributes_digest="4" * 64,
        config_digest="5" * 64,
        repository_policy_digest=_A,
        ignore_rules=(),
        tracked_file_count=tracked_file_count,
        tracked_byte_count=tracked_byte_count,
    )


def _accepted(
    files: tuple[tuple[str, bytes], ...],
) -> AcceptedGitPreflightV1:
    """One accepted preflight whose table matches the given raw files."""
    return AcceptedGitPreflightV1(
        schema_version=1,
        preflight=_seal(
            tracked_file_count=len(files),
            tracked_byte_count=sum(len(raw) for _, raw in files),
        ),
        files=tuple(
            SealedSnapshotInputFileV1(
                schema_version=1,
                path=CanonicalRelativePathV1(path),
                content_sha256=hashlib.sha256(raw).hexdigest(),
                byte_count=len(raw),
            )
            for path, raw in files
        ),
    )


def _stored(files: tuple[tuple[str, bytes], ...]) -> ContentObjectStore:
    store = ContentObjectStore()
    for _, raw in files:
        store.put(raw)
    return store


_FILES: tuple[tuple[str, bytes], ...] = (
    ("README.md", b"readme\n"),
    ("pyproject.toml", b'[project]\nname = "x"\n'),
    ("src/a.py", b"def a():\n    return 1\n"),
    ("src/pkg/b.py", b"# b\nvalue = 2\n"),
)


def _snapshot() -> SnapshotTreeV1:
    return create_snapshot(_accepted(_FILES), _stored(_FILES), classify_supported_text)


def test_snapshot_satisfies_the_minimal_read_protocol() -> None:
    snapshot = _snapshot()
    assert isinstance(snapshot, ReadableTreeV1)

    def consume(tree: ReadableTreeV1) -> tuple[str, int, int, bytes]:
        return (
            tree.digest,
            len(tree.list_directories()),
            len(tree.list_file_paths()),
            tree.read_bytes(CanonicalRelativePathV1("src/a.py")),
        )

    digest, directory_count, file_count, first = consume(snapshot)
    assert digest == snapshot.root_digest
    assert directory_count == 2
    assert file_count == 4
    assert first == b"def a():\n    return 1\n"


def test_snapshot_digest_aliases_root_digest_exactly() -> None:
    snapshot = _snapshot()
    assert snapshot.digest == snapshot.root_digest
    assert isinstance(snapshot.digest, str)
    assert len(snapshot.root_digest) == 64
    again = _snapshot()
    assert again == snapshot
    assert again.digest == snapshot.digest
    # The digest is bound to the policy and every sealed row: a drifted
    # policy binding with the original digest claim fails verification.
    other = _snapshot()
    drifted = SnapshotTreeV1.model_validate(
        {
            "root_digest": other.root_digest,
            "repository_policy_digest": _B,
            "entries": _entries_dicts(),
            "file_bytes": _file_bytes(),
        }
    )
    result = verify_snapshot(drifted, _stored(_FILES))
    assert result.status == "FAILED"
    assert result.failure_code == "ROOT_DIGEST_DRIFT"


def test_snapshot_exposes_deterministic_paths_and_exact_bytes() -> None:
    snapshot = _snapshot()
    assert snapshot.list_directories() == (
        CanonicalRelativePathV1("src"),
        CanonicalRelativePathV1("src/pkg"),
    )
    assert snapshot.list_file_paths() == (
        CanonicalRelativePathV1("README.md"),
        CanonicalRelativePathV1("pyproject.toml"),
        CanonicalRelativePathV1("src/a.py"),
        CanonicalRelativePathV1("src/pkg/b.py"),
    )
    for path, raw in _FILES:
        assert snapshot.read_bytes(CanonicalRelativePathV1(path)) == raw
    with pytest.raises(KeyError):
        snapshot.read_bytes(CanonicalRelativePathV1("src"))  # a directory
    with pytest.raises(KeyError):
        snapshot.read_bytes(CanonicalRelativePathV1("missing.py"))
    # Two independent constructions from the same sealed inputs are identical.
    assert _snapshot() == snapshot


def test_snapshot_binds_text_metadata_exactly() -> None:
    snapshot = _snapshot()
    entries = {entry.path.value: entry for entry in snapshot.entries}
    a = entries["src/a.py"]
    assert a.kind == "TEXT_FILE"
    assert a.size_bytes == len(b"def a():\n    return 1\n")
    assert a.text_profile.kind == "PRESENT"
    assert a.text_profile.value.encoding == "UTF8"
    assert a.text_profile.value.newline == "LF"
    assert a.text_profile.value.final_newline is True
    assert (
        a.content_ref.sha256 == hashlib.sha256(b"def a():\n    return 1\n").hexdigest()
    )
    directory = entries["src"]
    assert directory.kind == "DIRECTORY"


def test_create_snapshot_rejects_sealed_count_drift() -> None:
    accepted = AcceptedGitPreflightV1(
        schema_version=1,
        preflight=_seal(
            tracked_file_count=5, tracked_byte_count=sum(len(raw) for _, raw in _FILES)
        ),
        files=tuple(
            SealedSnapshotInputFileV1(
                schema_version=1,
                path=CanonicalRelativePathV1(path),
                content_sha256=hashlib.sha256(raw).hexdigest(),
                byte_count=len(raw),
            )
            for path, raw in _FILES
        ),
    )
    with pytest.raises(SnapshotIntegrityError, match="PREFLIGHT_COUNT_DRIFT"):
        create_snapshot(accepted, _stored(_FILES), classify_supported_text)


def test_create_snapshot_rejects_sealed_byte_total_drift() -> None:
    accepted = AcceptedGitPreflightV1(
        schema_version=1,
        preflight=_seal(
            tracked_file_count=len(_FILES),
            tracked_byte_count=sum(len(raw) for _, raw in _FILES) + 1,
        ),
        files=tuple(
            SealedSnapshotInputFileV1(
                schema_version=1,
                path=CanonicalRelativePathV1(path),
                content_sha256=hashlib.sha256(raw).hexdigest(),
                byte_count=len(raw),
            )
            for path, raw in _FILES
        ),
    )
    with pytest.raises(SnapshotIntegrityError, match="PREFLIGHT_BYTES_DRIFT"):
        create_snapshot(accepted, _stored(_FILES), classify_supported_text)


def test_create_snapshot_rejects_path_order_drift() -> None:
    files = tuple(reversed(_FILES))
    with pytest.raises(SnapshotIntegrityError, match="PATH_ORDER_DRIFT"):
        create_snapshot(_accepted(files), _stored(_FILES), classify_supported_text)


def test_create_snapshot_rejects_duplicate_path_drift() -> None:
    duplicate = (*_FILES[:-1], _FILES[0])
    with pytest.raises(SnapshotIntegrityError, match="PATH_ORDER_DRIFT"):
        create_snapshot(
            _accepted(duplicate), _stored(duplicate), classify_supported_text
        )


def test_create_snapshot_rejects_file_also_directory_drift() -> None:
    # A sealed file row that is also the directory of another file row is
    # structurally impossible (git cannot track one path as both) and must
    # reject creation exactly like verification rejects it.
    impossible = (
        ("src", b"package marker\n"),
        ("src/a.py", b"def a():\n    return 1\n"),
    )
    with pytest.raises(SnapshotIntegrityError, match="PATH_ORDER_DRIFT"):
        create_snapshot(
            _accepted(impossible), _stored(impossible), classify_supported_text
        )


def test_create_snapshot_rejects_protected_input_drift() -> None:
    # A sensitive path that a real SUPPORTED seal could never contain.
    sensitive = (
        (".env", b"TOKEN=secret\n"),
        ("src/a.py", b"def a():\n    return 1\n"),
    )
    with pytest.raises(SnapshotIntegrityError, match="PROTECTED_INPUT_DRIFT"):
        create_snapshot(
            _accepted(sensitive), _stored(sensitive), classify_supported_text
        )
    # Windows case-colliding paths that a real seal could never contain.
    collision = (
        ("src/A.py", b"one\n"),
        ("src/a.py", b"two\n"),
    )
    with pytest.raises(SnapshotIntegrityError, match="PROTECTED_INPUT_DRIFT"):
        create_snapshot(
            _accepted(collision), _stored(collision), classify_supported_text
        )


def test_create_snapshot_rejects_object_identity_drift() -> None:
    # Missing object: a fresh store backs none of the sealed identities.
    with pytest.raises(SnapshotIntegrityError, match="PREFLIGHT_OBJECT_DRIFT"):
        create_snapshot(
            _accepted(_FILES), ContentObjectStore(), classify_supported_text
        )
    # Corrupted object: the stored bytes no longer match their identity.
    corrupt = ContentObjectStore()
    refs = [corrupt.put(raw) for _, raw in _FILES]
    corrupt.inject_corruption(refs[0], b"tampered bytes\n")
    with pytest.raises(SnapshotIntegrityError, match="PREFLIGHT_OBJECT_DRIFT"):
        create_snapshot(_accepted(_FILES), corrupt, classify_supported_text)


def test_accepted_preflight_rejects_non_supported_seals() -> None:
    rejected = GitPreflightResultV1(
        schema_version=1,
        kind="REJECTED",
        error_code="UNSUPPORTED_REPOSITORY",
        reason="probe",
        tracked_file_count=0,
        tracked_byte_count=0,
    )
    with pytest.raises(ValidationError):
        AcceptedGitPreflightV1(schema_version=1, preflight=rejected, files=())
    with pytest.raises(ValidationError):
        AcceptedGitPreflightV1(
            schema_version=1,
            preflight=_seal(tracked_file_count=0, tracked_byte_count=0),
            files=(
                SealedSnapshotInputFileV1(
                    schema_version=1,
                    path=CanonicalRelativePathV1("src/a.py"),
                    content_sha256="not-a-digest",
                    byte_count=1,
                ),
            ),
        )


def test_verify_snapshot_intact_for_exact_seal() -> None:
    snapshot = _snapshot()
    result = verify_snapshot(snapshot, _stored(_FILES))
    assert result.status == "INTACT"
    assert isinstance(result, SnapshotIntegrityResultV1)
    assert result.failure_code is None
    assert result.reason is None
    # Verification is deterministic and reads nothing but the sealed inputs.
    assert verify_snapshot(snapshot, _stored(_FILES)) == result


def test_verify_snapshot_drift_matrix() -> None:
    """Every size/order/content/object/policy drift fails closed."""
    intact = _snapshot()
    store = _stored(_FILES)
    rows = (
        # Order drift: interleaved entries are not directories-then-files.
        (
            "PATH_ORDER_DRIFT",
            SnapshotTreeV1.model_validate(
                {
                    "root_digest": intact.root_digest,
                    "repository_policy_digest": _A,
                    "entries": _entries_dicts(interleaved=True),
                    "file_bytes": _file_bytes(),
                }
            ),
            store,
        ),
        # Path drift: a file path appears in multiple rows.
        (
            "PATH_ORDER_DRIFT",
            SnapshotTreeV1.model_validate(
                {
                    "root_digest": intact.root_digest,
                    "repository_policy_digest": _A,
                    "entries": _entries_dicts(duplicate_file=True),
                    "file_bytes": _file_bytes(),
                }
            ),
            store,
        ),
        # Path drift: a directory row that is not a file-path ancestor.
        (
            "PATH_ORDER_DRIFT",
            SnapshotTreeV1.model_validate(
                {
                    "root_digest": intact.root_digest,
                    "repository_policy_digest": _A,
                    "entries": _entries_dicts(extra_directory=True),
                    "file_bytes": _file_bytes(),
                }
            ),
            store,
        ),
        # Path drift: a path appears as both a directory and a file.
        (
            "PATH_ORDER_DRIFT",
            SnapshotTreeV1.model_validate(
                {
                    "root_digest": intact.root_digest,
                    "repository_policy_digest": _A,
                    "entries": _entries_dicts(overlap_directory_file=True),
                    "file_bytes": _file_bytes(),
                }
            ),
            store,
        ),
        # Size drift: the declared size disagrees with the sealed bytes.
        (
            "SIZE_DRIFT",
            _tree_with(
                first_size=99,
                first_sha=_A,
                first_bytes=b"def a():\n    return 1\n",
            ),
            store,
        ),
        # Content drift: the sealed bytes do not hash to the content ref.
        (
            "CONTENT_DRIFT",
            _tree_with(
                first_size=len(b"def a():\n    return 1\n"),
                first_sha=hashlib.sha256(b"def a():\n    return 1\n").hexdigest(),
                first_bytes=b"X" * len(b"def a():\n    return 1\n"),
            ),
            store,
        ),
        # Content drift: a sealed content path appears in multiple rows.
        (
            "CONTENT_DRIFT",
            SnapshotTreeV1.model_validate(
                {
                    "root_digest": intact.root_digest,
                    "repository_policy_digest": _A,
                    "entries": _entries_dicts(),
                    "file_bytes": (
                        ("README.md", b"TAMPERED!!"),
                        ("README.md", b"readme\n"),
                        ("pyproject.toml", b'[project]\nname = "x"\n'),
                        ("src/a.py", b"def a():\n    return 1\n"),
                        ("src/pkg/b.py", b"# b\nvalue = 2\n"),
                    ),
                }
            ),
            store,
        ),
        # Content drift: the sealed content rows do not match the entries.
        (
            "CONTENT_DRIFT",
            SnapshotTreeV1.model_validate(
                {
                    "root_digest": intact.root_digest,
                    "repository_policy_digest": _A,
                    "entries": _entries_dicts(),
                    "file_bytes": (),
                }
            ),
            store,
        ),
        # Object drift: the store no longer backs the sealed identities.
        (
            "OBJECT_MISSING",
            intact,
            ContentObjectStore(),
        ),
        # Object drift: the store object was corrupted.
        (
            "OBJECT_MISSING",
            intact,
            _corrupted_store(),
        ),
        # Policy drift: the repository policy binding is malformed.
        (
            "POLICY_DRIFT",
            SnapshotTreeV1.model_validate(
                {
                    "root_digest": intact.root_digest,
                    "repository_policy_digest": "not-a-digest",
                    "entries": _entries_dicts(),
                    "file_bytes": _file_bytes(),
                }
            ),
            store,
        ),
        # Root digest drift: the claimed digest does not bind the tree.
        (
            "ROOT_DIGEST_DRIFT",
            SnapshotTreeV1.model_validate(
                {
                    "root_digest": _B,
                    "repository_policy_digest": _A,
                    "entries": _entries_dicts(),
                    "file_bytes": _file_bytes(),
                }
            ),
            store,
        ),
    )
    for expected_code, tree, backing_store in rows:
        result = verify_snapshot(tree, backing_store)
        assert result.status == "FAILED"
        assert result.failure_code == expected_code
        assert result.reason
    # The intact tree still verifies against its real store.
    assert verify_snapshot(intact, store).status == "INTACT"


def test_create_snapshot_rejects_non_utf8_path_input() -> None:
    # A lone-surrogate path can never come from a real SUPPORTED seal (git
    # output is strict-UTF-8 decoded) and must reject creation closed.
    impossible = (
        ("src/a.py", b"def a():\n    return 1\n"),
        ("src/\ud800", b"marker\n"),
    )
    with pytest.raises(SnapshotIntegrityError, match="PROTECTED_INPUT_DRIFT"):
        create_snapshot(
            _accepted(impossible), _stored(impossible), classify_supported_text
        )


def test_verify_snapshot_rejects_non_utf8_path_closed() -> None:
    """verify_snapshot never raises: a non-canonically-encodable tree fails
    closed with ROOT_DIGEST_DRIFT instead of a raw CanonicalJsonErrorV1."""
    surrogate = _snapshot()
    entries = list(_entries_dicts())
    entries.append(
        {
            "kind": "TEXT_FILE",
            "path": {"value": "src/\ud800"},
            "size_bytes": 7,
            "content_ref": {
                "sha256": hashlib.sha256(b"marker\n").hexdigest(),
                "byte_count": 7,
            },
            "text_profile": {
                "kind": "PRESENT",
                "value": {"encoding": "UTF8", "newline": "LF", "final_newline": True},
            },
        }
    )
    bytes_rows = [*_file_bytes(), ("src/\ud800", b"marker\n")]
    tree = SnapshotTreeV1.model_validate(
        {
            "root_digest": surrogate.root_digest,
            "repository_policy_digest": _A,
            "entries": entries,
            "file_bytes": bytes_rows,
        }
    )
    backing = _stored(_FILES)
    backing.put(b"marker\n")
    result = verify_snapshot(tree, backing)
    assert result.status == "FAILED"
    assert result.failure_code == "ROOT_DIGEST_DRIFT"


def test_verify_snapshot_result_closed_schema() -> None:
    intact = SnapshotIntegrityResultV1.model_validate(
        {"schema_version": 1, "status": "INTACT"}
    )
    assert intact.status == "INTACT"
    failed = SnapshotIntegrityResultV1.model_validate(
        {
            "schema_version": 1,
            "status": "FAILED",
            "failure_code": "ROOT_DIGEST_DRIFT",
            "reason": "probe",
        }
    )
    assert failed.failure_code == "ROOT_DIGEST_DRIFT"
    invalid: tuple[dict[str, object], ...] = (
        {"schema_version": 1, "status": "INTACT", "failure_code": "POLICY_DRIFT"},
        {"schema_version": 1, "status": "FAILED"},
        {"schema_version": 1, "status": "FAILED", "failure_code": "UNKNOWN_CODE"},
        {"schema_version": 1, "status": "MAYBE"},
        {"schema_version": 1, "status": "INTACT", "extra": 1},
    )
    for payload in invalid:
        with pytest.raises(ValidationError):
            SnapshotIntegrityResultV1.model_validate(payload)


def test_snapshot_is_immutable_and_only_boundedly_readable() -> None:
    """The tree can only be observed through the bounded read protocol."""
    snapshot = _snapshot()
    # Frozen sealed value: every field assignment fails closed.
    with pytest.raises(ValidationError):
        snapshot.root_digest = _B
    with pytest.raises(ValidationError):
        snapshot.repository_policy_digest = _B
    with pytest.raises(ValidationError):
        snapshot.entries = ()
    with pytest.raises(ValidationError):
        snapshot.file_bytes = ()
    # The protocol surface has no mutation method and no setter.
    assert not hasattr(snapshot, "put")
    assert not hasattr(snapshot, "mutate")
    assert not hasattr(snapshot, "write")
    assert not hasattr(snapshot, "delete")
    assert not hasattr(snapshot, "set_digest")
    # Nested sealed values are frozen tuples of frozen models.
    with pytest.raises(ValidationError):
        snapshot.entries[0].path = CanonicalRelativePathV1("other")
    # read_bytes is a pure exact-byte read: repeated reads never change.
    before = _snapshot()
    assert (
        before.read_bytes(CanonicalRelativePathV1("src/a.py"))
        == b"def a():\n    return 1\n"
    )
    assert before == _snapshot()


def _entries_dicts(
    *,
    interleaved: bool = False,
    duplicate_file: bool = False,
    extra_directory: bool = False,
    overlap_directory_file: bool = False,
) -> tuple[dict[str, object], ...]:
    """Canonical-shape entry dicts matching ``_FILES``."""
    dirs: tuple[dict[str, object], ...] = (
        {"kind": "DIRECTORY", "path": {"value": "src"}},
        {"kind": "DIRECTORY", "path": {"value": "src/pkg"}},
    )
    if extra_directory:
        dirs = (*dirs, {"kind": "DIRECTORY", "path": {"value": "docs"}})
    a: dict[str, object] = {
        "kind": "TEXT_FILE",
        "path": {"value": "src/a.py"},
        "size_bytes": len(b"def a():\n    return 1\n"),
        "content_ref": {
            "sha256": hashlib.sha256(b"def a():\n    return 1\n").hexdigest(),
            "byte_count": len(b"def a():\n    return 1\n"),
        },
        "text_profile": {
            "kind": "PRESENT",
            "value": {"encoding": "UTF8", "newline": "LF", "final_newline": True},
        },
    }
    b = {
        "kind": "TEXT_FILE",
        "path": {"value": "src/pkg/b.py"},
        "size_bytes": len(b"# b\nvalue = 2\n"),
        "content_ref": {
            "sha256": hashlib.sha256(b"# b\nvalue = 2\n").hexdigest(),
            "byte_count": len(b"# b\nvalue = 2\n"),
        },
        "text_profile": {
            "kind": "PRESENT",
            "value": {"encoding": "UTF8", "newline": "LF", "final_newline": True},
        },
    }
    c = {
        "kind": "TEXT_FILE",
        "path": {"value": "pyproject.toml"},
        "size_bytes": len(b'[project]\nname = "x"\n'),
        "content_ref": {
            "sha256": hashlib.sha256(b'[project]\nname = "x"\n').hexdigest(),
            "byte_count": len(b'[project]\nname = "x"\n'),
        },
        "text_profile": {
            "kind": "PRESENT",
            "value": {"encoding": "UTF8", "newline": "LF", "final_newline": True},
        },
    }
    d = {
        "kind": "TEXT_FILE",
        "path": {"value": "README.md"},
        "size_bytes": len(b"readme\n"),
        "content_ref": {
            "sha256": hashlib.sha256(b"readme\n").hexdigest(),
            "byte_count": len(b"readme\n"),
        },
        "text_profile": {
            "kind": "PRESENT",
            "value": {"encoding": "UTF8", "newline": "LF", "final_newline": True},
        },
    }
    files = (d, c, a, b)  # canonical path order
    if duplicate_file:
        files = (d, c, a, a)
    if overlap_directory_file:
        # "src" appears as both a directory row and a file row.
        return (
            *dirs,
            {
                "kind": "TEXT_FILE",
                "path": {"value": "src"},
                "size_bytes": 4,
                "content_ref": {
                    "sha256": hashlib.sha256(b"src\n").hexdigest(),
                    "byte_count": 4,
                },
                "text_profile": {
                    "kind": "PRESENT",
                    "value": {
                        "encoding": "UTF8",
                        "newline": "LF",
                        "final_newline": True,
                    },
                },
            },
            *files,
        )
    if interleaved:
        return (files[0], dirs[0], *files[1:])
    return (*dirs, *files)


def _file_bytes() -> tuple[tuple[str, bytes], ...]:
    return tuple((path, raw) for path, raw in _FILES)


def _tree_with(
    *, first_size: int, first_sha: str, first_bytes: bytes
) -> SnapshotTreeV1:
    """One tree whose ``src/a.py`` row declares drifted size/content facts."""
    intact = _snapshot()
    entries = list(_entries_dicts())
    # Directories first (src, src/pkg), then README.md, pyproject.toml,
    # src/a.py, src/pkg/b.py.
    a_index = 4
    entries[a_index] = {
        "kind": "TEXT_FILE",
        "path": {"value": "src/a.py"},
        "size_bytes": first_size,
        "content_ref": {"sha256": first_sha, "byte_count": first_size},
        "text_profile": {
            "kind": "PRESENT",
            "value": {"encoding": "UTF8", "newline": "LF", "final_newline": True},
        },
    }
    bytes_rows = list(_file_bytes())
    a_bytes_index = 2  # (README.md, pyproject.toml, src/a.py, src/pkg/b.py)
    bytes_rows[a_bytes_index] = ("src/a.py", first_bytes)
    return SnapshotTreeV1.model_validate(
        {
            "root_digest": intact.root_digest,
            "repository_policy_digest": _A,
            "entries": entries,
            "file_bytes": bytes_rows,
        }
    )


def _corrupted_store() -> ContentObjectStore:
    store = ContentObjectStore()
    refs = [store.put(raw) for _, raw in _FILES]
    store.inject_corruption(refs[0], b"tampered bytes\n")
    return store

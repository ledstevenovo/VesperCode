"""T18.2 legacy step 18.B: fresh candidate materialization unit domain.

The closed allocation/materialization contracts run deterministically
offline: fresh-root uniqueness and identity binding, the exact-byte write
and reverify path, every closed ``MaterializationError`` branch
(missing/corrupt object, path escape, link, writable source, reuse),
cleanup-on-preflight-failure, and the sealed materialized identity
schemas (GREEN-1, GREEN-2, GREEN-4).
"""

from __future__ import annotations

import hashlib
import shutil
import subprocess
import tempfile
from collections.abc import Iterator
from pathlib import Path

import pytest

pytest.importorskip("pydantic")

from pydantic import ValidationError

from vespercode.canonical.path_v1 import CanonicalRelativePathV1
from vespercode.contracts.optional import AbsentV1, PresentV1
from vespercode.execution.materialization import (
    AuthorizedExecutionRootV1,
    MaterializationError,
    MaterializedCandidateV1,
    MaterializedFileV1,
    _require_authorized_path,
    allocate_execution_root,
    digest_materialized_candidate,
    is_non_reusable_name,
    materialize_candidate,
)
from vespercode.trees.candidate import (
    CandidatePostimageV1,
    CandidateTreeV1,
    derive_candidate_revision,
    root_candidate_revision,
)
from vespercode.trees.content_store import ContentObjectRefV1, ContentObjectStore
from vespercode.trees.snapshot import (
    SealedSnapshotInputFileV1,
    SnapshotDirectoryEntryV1,
    SnapshotEntryV1,
    SnapshotFileEntryV1,
    SnapshotTreeV1,
    _root_digest,
)
from vespercode.trees.text_classifier import (
    TextMetadataV1,
    classify_supported_text,
)
from vespercode.execution.cleanup import finalize_execution
from vespercode.execution.docker_executor import RawExecutionResultV1

_POLICY_DIGEST = "b857afca63e50a888ee183bd7ac8c7f739be7b60a94fc4f9c55c0a606db144ab"


class _Base:
    """One module-scoped scratch base removed at teardown."""

    path = Path(tempfile.mkdtemp(prefix="vesper-t182-unit-materialize-"))


@pytest.fixture(scope="module", autouse=True)
def _remove_scratch_base() -> Iterator[None]:
    yield
    shutil.rmtree(_Base.path, ignore_errors=True)


def tiny_candidate() -> CandidateTreeV1:
    """One small sealed candidate: two overlay files over an empty snapshot."""
    store = ContentObjectStore()
    rows: list[SealedSnapshotInputFileV1] = []
    for rel, raw in (
        ("src/a.py", b"def a():\n    return 1\n"),
        ("src/b.py", b"def b():\n    return 2\n"),
    ):
        ref = store.put(raw)
        rows.append(
            SealedSnapshotInputFileV1(
                schema_version=1,
                path=CanonicalRelativePathV1(rel),
                content_sha256=ref.sha256,
                byte_count=ref.byte_count,
            )
        )
    rows.sort(key=lambda row: row.path.value)
    directory_values = {
        "/".join(row.path.value.split("/")[:index])
        for row in rows
        for index in range(1, len(row.path.value.split("/")))
    }
    entries: list[SnapshotEntryV1] = [
        SnapshotDirectoryEntryV1(kind="DIRECTORY", path=CanonicalRelativePathV1(value))
        for value in sorted(directory_values)
    ]
    for row in rows:
        ref = ContentObjectRefV1(sha256=row.content_sha256, byte_count=row.byte_count)
        classification = classify_supported_text(store.get(ref))
        if classification.kind == "TEXT_FILE":
            text_profile: PresentV1[TextMetadataV1] | AbsentV1 = (
                classification.text_profile
            )
        else:
            text_profile = AbsentV1(kind="ABSENT")
        entries.append(
            SnapshotFileEntryV1(
                kind=classification.kind,
                path=row.path,
                size_bytes=row.byte_count,
                content_ref=ref,
                text_profile=text_profile,
            )
        )
    snapshot = SnapshotTreeV1(
        root_digest=_root_digest(_POLICY_DIGEST, tuple(entries)),
        repository_policy_digest=_POLICY_DIGEST,
        entries=tuple(entries),
        file_bytes=tuple(
            (
                row.path.value,
                store.get(
                    ContentObjectRefV1(
                        sha256=row.content_sha256, byte_count=row.byte_count
                    )
                ),
            )
            for row in rows
        ),
    )
    revision = derive_candidate_revision(
        root_candidate_revision(snapshot, store),
        (
            CandidatePostimageV1(
                schema_version=1,
                operation="REPLACE",
                path=CanonicalRelativePathV1("src/a.py"),
                raw_bytes=b"def a():\n    return 1\n# candidate\n",
            ),
        ),
    )
    return revision.tree


def fresh_root() -> AuthorizedExecutionRootV1:
    return allocate_execution_root(_Base.path)


def test_allocate_execution_root_is_fresh_unique_and_identity_bound() -> None:
    first = fresh_root()
    second = fresh_root()
    assert first.root_id != second.root_id
    assert first.root_path != second.root_path
    assert Path(first.root_path).name == first.root_id
    marker = Path(first.root_path) / ".vespercode-execution-root"
    assert marker.read_bytes() == first.root_id.encode("ascii")
    # Only the marker exists in a fresh root.
    assert sorted(entry.name for entry in Path(first.root_path).iterdir()) == [
        ".vespercode-execution-root"
    ]


def test_materialize_writes_exact_bytes_and_reverifies() -> None:
    candidate = tiny_candidate()
    materialized = materialize_candidate(candidate, fresh_root())
    assert materialized.candidate_digest == candidate.digest
    assert materialized.snapshot_tree_digest == candidate.snapshot.root_digest
    assert [row.path for row in materialized.files] == [
        "src/a.py",
        "src/b.py",
    ]
    for row in materialized.files:
        expected = candidate.read_bytes(CanonicalRelativePathV1(row.path))
        disk = (Path(materialized.root_path) / row.path).read_bytes()
        assert disk == expected
        assert hashlib.sha256(disk).hexdigest() == row.sha256
        assert len(disk) == row.byte_count
    # The sealed digest self-binds (a tampered materialization rejects).
    tampered = materialized.model_copy(update={"files": materialized.files[1:]})
    with pytest.raises(ValidationError):
        MaterializedCandidateV1.model_validate(tampered.model_dump())


def test_materialization_cleanup_on_preflight_failure_leaves_no_root() -> None:
    root = fresh_root()
    with pytest.raises(MaterializationError, match="CONTENT_DIGEST_MISMATCH"):
        materialize_candidate(candidate_with_drifted_overlay(), root)
    # Cleanup on preflight failure: the partial root is fully removed.
    assert not Path(root.root_path).exists()


def candidate_with_drifted_overlay() -> CandidateTreeV1:
    candidate = tiny_candidate()
    for entry in candidate.overlay:
        if entry.path.value == "src/a.py":
            candidate.store.inject_corruption(entry.content_ref, b"drifted-bytes")
            return candidate
    raise AssertionError("the overlay must contain the a.py row")


def test_materialization_error_codes_are_closed() -> None:
    candidate = tiny_candidate()
    # Missing object: a store that cannot return the sealed overlay object.
    missing = candidate.model_copy(update={"store": ContentObjectStore()})
    with pytest.raises(MaterializationError, match="OBJECT_MISSING"):
        materialize_candidate(missing, fresh_root())
    # Corrupt object: drift behind a sealed identity.
    with pytest.raises(MaterializationError, match="CONTENT_DIGEST_MISMATCH"):
        materialize_candidate(candidate_with_drifted_overlay(), fresh_root())
    # Path escape: a non-absolute root path and a parent-segment path.
    with pytest.raises(MaterializationError, match="PATH_ESCAPE"):
        materialize_candidate(
            candidate, AuthorizedExecutionRootV1(root_id="0" * 32, root_path="rel")
        )
    with pytest.raises(MaterializationError, match="PATH_ESCAPE"):
        materialize_candidate(
            candidate,
            AuthorizedExecutionRootV1(
                root_id="0" * 32, root_path=str(_Base.path / ".." / "escape")
            ),
        )
    # Writable source: a directory with no identity marker.
    foreign = _Base.path / "foreign"
    foreign.mkdir()
    with pytest.raises(MaterializationError, match="WRITABLE_SOURCE"):
        materialize_candidate(
            candidate,
            AuthorizedExecutionRootV1(root_id="0" * 32, root_path=str(foreign)),
        )
    # Link: a junction where the root must be a real directory.
    target = _Base.path / "link-target"
    target.mkdir()
    link = _Base.path / "link-root"
    try:
        _make_junction(link, target)
    except OSError:
        pytest.skip("junction creation is not available on this host")
    with pytest.raises(MaterializationError, match="LINK_FOUND"):
        materialize_candidate(
            candidate, AuthorizedExecutionRootV1(root_id="0" * 32, root_path=str(link))
        )
    # Reuse: a root that already holds materialized content.
    reused = fresh_root()
    materialize_candidate(candidate, reused)
    with pytest.raises(MaterializationError, match="ROOT_REUSE"):
        materialize_candidate(candidate, reused)


def test_materialization_rejects_the_reserved_marker_path() -> None:
    # The execution-root marker name is a reserved path: a candidate row
    # carrying it can never overwrite the identity marker.  The guard is
    # case-insensitive (Windows filesystems are case-insensitive, so a
    # case variant would open the very same marker file).
    with pytest.raises(MaterializationError, match="PATH_ESCAPE"):
        _require_authorized_path(".vespercode-execution-root")
    with pytest.raises(MaterializationError, match="PATH_ESCAPE"):
        _require_authorized_path(".VESPERCODE-EXECUTION-ROOT")
    # Non-marker paths still pass the lexical guard.
    _require_authorized_path("src/a.py")


def test_forged_marker_bound_root_is_never_a_writable_source() -> None:
    # A root that is lexically well-formed and marker-bound but was never
    # allocated by this module is rejected: the name+marker pair alone
    # cannot prove provenance.
    forged_id = "f" * 32
    forged = _Base.path / forged_id
    forged.mkdir()
    (forged / ".vespercode-execution-root").write_bytes(forged_id.encode("ascii"))
    with pytest.raises(MaterializationError, match="WRITABLE_SOURCE"):
        materialize_candidate(
            tiny_candidate(),
            AuthorizedExecutionRootV1(root_id=forged_id, root_path=str(forged)),
        )


def test_cleanup_refuses_a_forged_materialization_root() -> None:
    # A forged MaterializedCandidateV1 naming an arbitrary directory is
    # never removed: cleanup accepts only allocator-registered roots.
    candidate = tiny_candidate()
    materialized = materialize_candidate(
        candidate, allocate_execution_root(_Base.path)
    )
    forged_dir = _Base.path / "forged-cleanup-target"
    forged_dir.mkdir()
    forged = materialized.model_copy(update={"root_path": str(forged_dir)})
    raw = RawExecutionResultV1(
        schema_version=1,
        request_id="req-1",
        container_id="container-1",
        exit_code=0,
        stdout=b"",
        stderr=b"",
        output_bytes=0,
        timed_out=False,
        output_limit_exceeded=False,
        container_stopped=False,
        error_code=None,
    )
    result = finalize_execution(raw, candidate, forged)
    assert result.materialization_removed is False
    assert forged_dir.exists()


def test_injected_cleanup_factory_failure_is_a_closed_cleanup_failure() -> None:
    # An injected client factory that raises is a closed cleanup failure:
    # the cleanup verdict reports the residual container and never raises
    # out of the cleanup contract.
    candidate = tiny_candidate()
    materialized = materialize_candidate(
        candidate, allocate_execution_root(_Base.path)
    )
    raw = RawExecutionResultV1(
        schema_version=1,
        request_id="req-1",
        container_id="container-1",
        exit_code=0,
        stdout=b"",
        stderr=b"",
        output_bytes=0,
        timed_out=False,
        output_limit_exceeded=False,
        container_stopped=False,
        error_code=None,
    )

    def _boom() -> object:
        raise RuntimeError("injected cleanup factory failure")

    result = finalize_execution(raw, candidate, materialized, client_factory=_boom)
    assert result.container_removed is False
    assert result.materialization_removed is True
    assert result.workspace_unchanged is True
    assert result.residual_artifact is not None


def test_materialized_schema_contracts() -> None:
    row = MaterializedFileV1(path="src/a.py", sha256="0" * 64, byte_count=3)
    assert row.byte_count == 3
    for payload in [
        {"path": "", "sha256": "0" * 64, "byte_count": 3},
        {"path": "src/a.py", "sha256": "0" * 63, "byte_count": 3},
        {"path": "src/a.py", "sha256": "0" * 64, "byte_count": -1},
        {"path": "src/a.py", "sha256": "0" * 64, "byte_count": True},
        {"path": "src/a.py", "sha256": "0" * 64, "byte_count": 3, "extra": 1},
    ]:
        with pytest.raises(ValidationError):
            MaterializedFileV1.model_validate(payload)
    digest = digest_materialized_candidate("0" * 32, "1" * 64, "2" * 64, (row,))
    assert len(digest) == 64
    materialized = MaterializedCandidateV1(
        schema_version=1,
        root_id="0" * 32,
        root_path=str(_Base.path / "x"),
        candidate_digest="1" * 64,
        snapshot_tree_digest="2" * 64,
        files=(row,),
        pre_execution_root_digest=digest,
    )
    assert materialized.pre_execution_root_digest == digest
    with pytest.raises(ValidationError):
        MaterializedCandidateV1.model_validate(
            {
                "schema_version": True,
                "root_id": "0" * 32,
                "root_path": str(_Base.path / "x"),
                "candidate_digest": "1" * 64,
                "snapshot_tree_digest": "2" * 64,
                "files": (row,),
                "pre_execution_root_digest": digest,
            }
        )


def test_authorized_execution_root_contract() -> None:
    root = AuthorizedExecutionRootV1(root_id="ab" * 16, root_path="C:/tmp/root")
    assert root.root_id == "ab" * 16
    for payload in [
        {"root_id": "0" * 31, "root_path": "C:/tmp/root"},
        {"root_id": "0" * 33, "root_path": "C:/tmp/root"},
        {"root_id": "0" * 32, "root_path": "C:/tmp/root", "extra": 1},
        {"root_id": "0" * 32, "root_path": ""},
        {"root_id": "0" * 32, "root_path": "C:/tmp/root", "root_id2": "1" * 32},
    ]:
        with pytest.raises(ValidationError):
            AuthorizedExecutionRootV1.model_validate(payload)


def test_non_reusable_name_registry() -> None:
    assert is_non_reusable_name("0" * 32) is False
    from vespercode.execution import materialization as module

    module.register_non_reusable_name("0" * 32)
    assert is_non_reusable_name("0" * 32) is True


def _make_junction(link: Path, target: Path) -> None:
    """Create a real NTFS junction (no admin rights required)."""
    proc = subprocess.run(
        ["cmd", "/c", "mklink", "/J", str(link), str(target)],
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        raise OSError(proc.stderr.strip() or "mklink /J failed")

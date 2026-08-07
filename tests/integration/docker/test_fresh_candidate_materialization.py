"""T18.2 legacy step 18.B: fresh identity-bound candidate materialization.

The card's exact RED test and the 18.B materialization integrity matrix:
one fresh identity-bound execution root per invocation, every verified
CandidateTree content object written to its exact authorized path and
bytes, and every missing/corrupt object, path escape, link, writable
source, or root reuse rejected with the closed ``MaterializationError``
before any container can start (GREEN-1..GREEN-4).

The candidate under test is a real tree built from the frozen reference
fixture bytes (T02.1): the sealed SnapshotTree holds the four fixture
files, and the overlay REPLACEs ``src/vesper_fixture/calculator.py`` with
the corrected candidate bytes, so every materialization row binds real
sealed content and the executor-side byte proof (isolation test) compares
against the same candidate identity.
"""

from __future__ import annotations

import hashlib
import shutil
import tempfile
from pathlib import Path
from collections.abc import Iterator

import pytest

# The materialization contracts are pydantic runtime contracts; the
# hash-locked gate toolchain does not install runtime dependencies, so
# this module skips cleanly there instead of failing at collection
# (formal env runs it fully).
pytest.importorskip("pydantic")

from vespercode.canonical.path_v1 import CanonicalRelativePathV1
from vespercode.contracts.evidence import _DIGEST_RE
from vespercode.contracts.optional import AbsentV1, PresentV1
from vespercode.execution.materialization import (
    AuthorizedExecutionRootV1,
    MaterializationError,
    allocate_execution_root,
    materialize_candidate,
)
from vespercode.profiles.reference import load_reference_profile
from vespercode.trees.candidate import (
    CandidatePostimageV1,
    CandidateTreeV1,
    derive_candidate_revision,
    root_candidate_revision,
)
from vespercode.trees.content_store import (
    ContentObjectRefV1,
    ContentObjectStore,
)
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

pytestmark = pytest.mark.docker_integration

# The frozen reference fixture (T02.1) and its packaged manifest identity.
_FIXTURE_FILES = (
    "pyproject.toml",
    "requirements.lock",
    "src/vesper_fixture/calculator.py",
    "tests/test_calculator.py",
)
_CALCULATOR_PATH = "src/vesper_fixture/calculator.py"


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def packaged_reference_profile_bytes() -> bytes:
    """The packaged production manifest bytes (the frozen GO identity)."""
    return (
        _repo_root()
        / "src"
        / "vespercode"
        / "profiles"
        / "builtin"
        / "reference-profile-v1.json"
    ).read_bytes()


def frozen_policy_digest() -> str:
    """The frozen T06.2 editable-path-policy digest of the packaged manifest."""
    manifest = load_reference_profile(packaged_reference_profile_bytes())
    return manifest.editable_path_policy.digest


def corrected_calculator_bytes() -> bytes:
    """The candidate overlay bytes: the fixture calculator with the defect
    fixed (``add`` returns the sum)."""
    original = (_repo_root() / "reference" / "fixture" / _CALCULATOR_PATH).read_bytes()
    fixed = original.replace(b"    return left - right\n", b"    return left + right\n")
    assert fixed != original, "the fixture defect line must exist"
    return fixed


def build_fixture_candidate() -> CandidateTreeV1:
    """One real candidate tree over the frozen reference fixture bytes.

    The sealed SnapshotTree holds the four fixture files with their exact
    bytes and text metadata; the overlay REPLACEs the calculator with the
    corrected candidate bytes, so ``candidate.read_bytes`` returns exact
    sealed content for every materialization row.
    """
    fixture = _repo_root() / "reference" / "fixture"
    store = ContentObjectStore()
    rows: list[SealedSnapshotInputFileV1] = []
    for rel in _FIXTURE_FILES:
        raw = (fixture / rel).read_bytes()
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
    policy_digest = frozen_policy_digest()
    snapshot = SnapshotTreeV1(
        root_digest=_root_digest(policy_digest, tuple(entries)),
        repository_policy_digest=policy_digest,
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
                path=CanonicalRelativePathV1(_CALCULATOR_PATH),
                raw_bytes=corrected_calculator_bytes(),
            ),
        ),
    )
    return revision.tree


def candidate_with_corrupt_object() -> CandidateTreeV1:
    """The smallest corrupted content object: the overlay's store object
    replaced with different bytes behind its own sealed identity."""
    candidate = build_fixture_candidate()
    for entry in candidate.overlay:
        if entry.path.value == _CALCULATOR_PATH:
            candidate.store.inject_corruption(entry.content_ref, b"corrupted-bytes")
            return candidate
    raise AssertionError("the overlay must contain the calculator row")


# Fresh roots are allocated under one module-scoped base directory that is
# removed at module teardown, so no execution root ever outlives the module.
_MODULE_ROOT_BASE = Path(tempfile.mkdtemp(prefix="vesper-t182-materialize-"))


@pytest.fixture(scope="module", autouse=True)
def _remove_module_root_bases() -> Iterator[None]:
    yield
    shutil.rmtree(_MODULE_ROOT_BASE, ignore_errors=True)


def fresh_root() -> AuthorizedExecutionRootV1:
    """One fresh identity-bound execution root under the module base."""
    return allocate_execution_root(_MODULE_ROOT_BASE)


def test_materialization_rejects_content_object_digest_drift() -> None:
    with pytest.raises(MaterializationError, match="CONTENT_DIGEST_MISMATCH"):
        materialize_candidate(candidate_with_corrupt_object(), fresh_root())


def test_candidate_materialization_integrity_matrix() -> None:
    """18.B matrix (PLAN 18.B): each invocation gets a fresh tree with exact
    ordered paths/bytes/digests; missing/corrupt object, path escape, link,
    writable source, or reuse is rejected before container start.
    """
    # Fresh tree per invocation: two allocations are distinct roots and both
    # materialize the exact same candidate bytes.
    candidate = build_fixture_candidate()
    first = materialize_candidate(candidate, fresh_root())
    second = materialize_candidate(candidate, fresh_root())
    assert first.root_id != second.root_id
    assert first.root_path != second.root_path
    assert first.files == second.files
    # The pre-execution root digest is identity-bound: the same bytes in two
    # different fresh roots are two different sealed materializations.
    assert first.pre_execution_root_digest != second.pre_execution_root_digest

    # Exact ordered paths/bytes/digests: every tree file is materialized at
    # its canonical path with byte-identical content and sealed identity.
    materialized = materialize_candidate(candidate, fresh_root())
    assert materialized.candidate_digest == candidate.digest
    assert materialized.snapshot_tree_digest == candidate.snapshot.root_digest
    assert [row.path for row in materialized.files] == [
        path.value for path in candidate.list_file_paths()
    ]
    for row in materialized.files:
        expected = candidate.read_bytes(CanonicalRelativePathV1(row.path))
        disk = (Path(materialized.root_path) / row.path).read_bytes()
        assert disk == expected, row.path
        assert hashlib.sha256(disk).hexdigest() == row.sha256, row.path
        assert len(disk) == row.byte_count, row.path
        assert _DIGEST_RE.fullmatch(row.sha256) is not None, row.path
    assert materialized.pre_execution_root_digest != candidate.digest

    # Missing object: a store that cannot return the sealed overlay object.
    missing_candidate = build_fixture_candidate().model_copy(
        update={"store": ContentObjectStore()}
    )
    with pytest.raises(MaterializationError, match="OBJECT_MISSING"):
        materialize_candidate(missing_candidate, fresh_root())

    # Corrupt object: the exact RED failure, in-matrix.
    with pytest.raises(MaterializationError, match="CONTENT_DIGEST_MISMATCH"):
        materialize_candidate(candidate_with_corrupt_object(), fresh_root())

    # Path escape: a root whose path is not an absolute canonical path.
    with pytest.raises(MaterializationError, match="PATH_ESCAPE"):
        materialize_candidate(
            candidate,
            AuthorizedExecutionRootV1(root_id="0" * 32, root_path="relative/root"),
        )
    with pytest.raises(MaterializationError, match="PATH_ESCAPE"):
        materialize_candidate(
            candidate,
            AuthorizedExecutionRootV1(
                root_id="0" * 32,
                root_path=str(Path(_MODULE_ROOT_BASE) / ".." / "escaped"),
            ),
        )

    # Link: a root path that is itself a link is not an execution root.
    link_target = _MODULE_ROOT_BASE / "link-target"
    link_target.mkdir()
    link_root = _MODULE_ROOT_BASE / "link-root"
    try:
        _make_junction(link_root, link_target)
    except OSError:
        pytest.skip("junction creation is not available on this host")
    with pytest.raises(MaterializationError, match="LINK_FOUND"):
        materialize_candidate(
            candidate,
            AuthorizedExecutionRootV1(root_id="0" * 32, root_path=str(link_root)),
        )

    # Writable source: a root that was not allocated by this module (its
    # identity marker is missing) could have been written by any process.
    foreign_root = _MODULE_ROOT_BASE / "foreign-root"
    foreign_root.mkdir()
    with pytest.raises(MaterializationError, match="WRITABLE_SOURCE"):
        materialize_candidate(
            candidate,
            AuthorizedExecutionRootV1(root_id="0" * 32, root_path=str(foreign_root)),
        )

    # Reuse: a root that already holds materialized content is rejected.
    reused_root = fresh_root()
    materialize_candidate(candidate, reused_root)
    with pytest.raises(MaterializationError, match="ROOT_REUSE"):
        materialize_candidate(candidate, reused_root)


def _make_junction(link: Path, target: Path) -> None:
    """Create a real NTFS junction (no admin rights required)."""
    import subprocess

    proc = subprocess.run(
        ["cmd", "/c", "mklink", "/J", str(link), str(target)],
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        raise OSError(proc.stderr.strip() or "mklink /J failed")

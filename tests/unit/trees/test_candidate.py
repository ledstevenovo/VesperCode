"""T12.1 legacy step 12.B: immutable CandidateTree overlay tests.

The exact RED test (a child revision derives from complete staged
postimages while the parent revision and tree stay unchanged), the
complete overlay integrity matrix (registry 12.B: REPLACE and CREATE
produce ordered immutable overlays that structurally satisfy T10.2's
``ReadableTreeV1`` without importing T11.1; parent stays unchanged;
duplicate/missing object/digest drift fails closed; identical inputs
yield identical Candidate identity), and the domain assertions for the
closed postimage/revision/tree contracts.  Patch parsing, path
authorization, transactional publication, FinalDiff, and policy
decisions remain out of scope (GREEN-4).
"""

from __future__ import annotations

import ast
import hashlib
from pathlib import Path

import pytest

# The candidate contracts are pydantic runtime models; the hash-locked
# gate toolchain does not install runtime dependencies, so this module
# skips cleanly there instead of failing at collection (formal env runs it
# fully).
pytest.importorskip("pydantic")

from pydantic import ValidationError

from vespercode.canonical.path_v1 import CanonicalRelativePathV1
from vespercode.trees.candidate import (
    CandidateIntegrityError,
    CandidateOverlayEntryV1,
    CandidatePostimageV1,
    CandidatePostimageSequenceV1,
    CandidateRevisionV1,
    CandidateTreeV1,
    derive_candidate_revision,
    digest_candidate_tree,
    root_candidate_revision,
)
from vespercode.trees.content_store import ContentObjectRefV1, ContentObjectStore
from vespercode.trees.readable import ReadableTreeV1
from vespercode.trees.snapshot import (
    AcceptedGitPreflightV1,
    SealedSnapshotInputFileV1,
    create_snapshot,
)
from vespercode.trees.text_classifier import classify_supported_text
from vespercode.workspace.git_preflight import GitPreflightResultV1

_A = "a" * 64

_FILES: tuple[tuple[str, bytes], ...] = (
    ("README.md", b"readme\n"),
    ("src/a.py", b"x = 1\n"),
    ("src/pkg/b.py", b"value = 2\n"),
)


def canonical_path(value: str) -> CanonicalRelativePathV1:
    """One canonical repository-relative path test value."""
    return CanonicalRelativePathV1(value)


def replace_postimage(path: str, raw: bytes) -> CandidatePostimageV1:
    """One staged REPLACE postimage with complete raw bytes."""
    return CandidatePostimageV1(
        schema_version=1, operation="REPLACE", path=canonical_path(path), raw_bytes=raw
    )


def create_postimage(path: str, raw: bytes) -> CandidatePostimageV1:
    """One staged CREATE postimage with complete raw bytes."""
    return CandidatePostimageV1(
        schema_version=1, operation="CREATE", path=canonical_path(path), raw_bytes=raw
    )


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


def _accepted(files: tuple[tuple[str, bytes], ...]) -> AcceptedGitPreflightV1:
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
                path=canonical_path(path),
                content_sha256=hashlib.sha256(raw).hexdigest(),
                byte_count=len(raw),
            )
            for path, raw in files
        ),
    )


@pytest.fixture
def parent_revision() -> CandidateRevisionV1:
    """One root candidate revision whose tree is the sealed snapshot."""
    store = ContentObjectStore()
    for _, raw in _FILES:
        store.put(raw)
    snapshot = create_snapshot(_accepted(_FILES), store, classify_supported_text)
    return root_candidate_revision(snapshot, store)


def test_child_revision_does_not_mutate_parent(
    parent_revision: CandidateRevisionV1,
) -> None:
    child = derive_candidate_revision(
        parent_revision, (replace_postimage("src/a.py", b"x = 2\n"),)
    )
    assert child.tree.read_bytes(canonical_path("src/a.py")) == b"x = 2\n"
    assert parent_revision.tree.read_bytes(canonical_path("src/a.py")) == b"x = 1\n"


def test_candidate_overlay_integrity_matrix(
    parent_revision: CandidateRevisionV1,
) -> None:
    """Registry 12.B: ordered immutable overlays, structural ReadableTreeV1
    compatibility, parent independence, closed drift failures, and
    identical-input identity."""
    snapshot = parent_revision.tree.snapshot
    parent_digest_before = parent_revision.tree.digest

    # --- REPLACE produces an ordered immutable overlay. ---
    replaced = derive_candidate_revision(
        parent_revision, (replace_postimage("src/a.py", b"x = 2\n"),)
    )
    assert isinstance(replaced.tree, ReadableTreeV1)
    assert replaced.tree.read_bytes(canonical_path("src/a.py")) == b"x = 2\n"
    assert replaced.tree.list_file_paths() == (
        canonical_path("README.md"),
        canonical_path("src/a.py"),
        canonical_path("src/pkg/b.py"),
    )
    assert replaced.tree.list_directories() == (
        canonical_path("src"),
        canonical_path("src/pkg"),
    )
    assert replaced.tree.digest != parent_revision.tree.digest
    assert isinstance(replaced.tree.digest, str)
    assert len(replaced.tree.digest) == 64

    # --- CREATE adds the file and its ancestor directories. ---
    created = derive_candidate_revision(
        parent_revision, (create_postimage("src/pkg/new.py", b"fresh = 1\n"),)
    )
    assert isinstance(created.tree, ReadableTreeV1)
    assert created.tree.read_bytes(canonical_path("src/pkg/new.py")) == b"fresh = 1\n"
    assert created.tree.list_file_paths() == (
        canonical_path("README.md"),
        canonical_path("src/a.py"),
        canonical_path("src/pkg/b.py"),
        canonical_path("src/pkg/new.py"),
    )
    # The new directory ancestor is present and ordered.
    assert created.tree.list_directories() == (
        canonical_path("src"),
        canonical_path("src/pkg"),
    )
    # A directory path is not a file path and cannot be read as bytes.
    with pytest.raises(KeyError):
        created.tree.read_bytes(canonical_path("src"))

    # --- The parent stays unchanged in digest and bytes. ---
    assert parent_revision.tree.digest == parent_digest_before
    assert parent_revision.tree.read_bytes(canonical_path("src/a.py")) == b"x = 1\n"
    assert replaced.tree.snapshot is parent_revision.tree.snapshot

    # --- Duplicate staged postimages reject closed. ---
    with pytest.raises(CandidateIntegrityError, match="POSTIMAGE_DUPLICATE_PATH"):
        derive_candidate_revision(
            parent_revision,
            (
                replace_postimage("src/a.py", b"x = 2\n"),
                replace_postimage("src/a.py", b"x = 3\n"),
            ),
        )

    # --- CREATE on an existing path rejects closed. ---
    with pytest.raises(CandidateIntegrityError, match="POSTIMAGE_PATH_EXISTS"):
        derive_candidate_revision(
            parent_revision, (create_postimage("src/a.py", b"x = 9\n"),)
        )

    # --- CREATE under an existing file rejects closed (a file can never
    # be a directory of another path). ---
    with pytest.raises(CandidateIntegrityError, match="POSTIMAGE_PATH_EXISTS"):
        derive_candidate_revision(
            parent_revision, (create_postimage("src/a.py/x", b"x = 9\n"),)
        )

    # --- CREATE of a Windows case-colliding path rejects closed. ---
    with pytest.raises(CandidateIntegrityError, match="POSTIMAGE_PATH_EXISTS"):
        derive_candidate_revision(
            parent_revision, (create_postimage("src/A.py", b"x = 9\n"),)
        )

    # --- CREATE under a Unicode-normalization-aliased ancestor file
    # rejects closed (src/\u00e9.py/x would be a descendant of the
    # NFD-spelled file src/e\u0301.py under NFC normalization). ---
    nfd_store = ContentObjectStore()
    nfd_files: tuple[tuple[str, bytes], ...] = (
        ("src/a.py", b"x = 1\n"),
        ("src/e\u0301.py", b"y = 1\n"),
    )
    for _, raw in nfd_files:
        nfd_store.put(raw)
    nfd_snapshot = create_snapshot(
        _accepted(nfd_files), nfd_store, classify_supported_text
    )
    nfd_parent = root_candidate_revision(nfd_snapshot, nfd_store)
    with pytest.raises(CandidateIntegrityError, match="POSTIMAGE_PATH_EXISTS"):
        derive_candidate_revision(
            nfd_parent, (create_postimage("src/\u00e9.py/x", b"z = 1\n"),)
        )

    # --- REPLACE on a missing path rejects closed. ---
    with pytest.raises(CandidateIntegrityError, match="POSTIMAGE_PATH_NOT_FOUND"):
        derive_candidate_revision(
            parent_revision, (replace_postimage("src/missing.py", b"x = 9\n"),)
        )

    # --- Missing store objects fail closed at read time. ---
    unbacked_ref = ContentObjectRefV1(sha256="0" * 64, byte_count=5)
    unbacked_overlay = (
        CandidateOverlayEntryV1(
            schema_version=1,
            operation="REPLACE",
            path=canonical_path("src/a.py"),
            content_ref=unbacked_ref,
        ),
    )
    unbacked_tree = CandidateTreeV1(
        schema_version=1,
        snapshot=snapshot,
        store=ContentObjectStore(),
        overlay=unbacked_overlay,
        digest=digest_candidate_tree(snapshot.root_digest, unbacked_overlay),
    )
    with pytest.raises(CandidateIntegrityError):
        unbacked_tree.read_bytes(canonical_path("src/a.py"))
    # Other paths still read from the sealed snapshot.
    assert unbacked_tree.read_bytes(canonical_path("README.md")) == b"readme\n"

    # --- Drifted store bytes fail closed at read time. ---
    drifting_store = ContentObjectStore()
    for _, raw in _FILES:
        drifting_store.put(raw)
    drifting_root = root_candidate_revision(snapshot, drifting_store)
    drifted = derive_candidate_revision(
        drifting_root, (replace_postimage("src/a.py", b"x = 2\n"),)
    )
    # The derive stored the postimage bytes; corrupt the stored object
    # behind the overlay ref so the sealed identity no longer matches.
    drifting_store.inject_corruption(
        ContentObjectRefV1(sha256=hashlib.sha256(b"x = 2\n").hexdigest(), byte_count=6),
        b"TAMPERED!\n",
    )
    with pytest.raises(CandidateIntegrityError):
        drifted.tree.read_bytes(canonical_path("src/a.py"))

    # --- A claimed digest that does not bind the overlay rejects. ---
    with pytest.raises(ValidationError):
        CandidateTreeV1(
            schema_version=1,
            snapshot=snapshot,
            store=ContentObjectStore(),
            overlay=unbacked_overlay,
            digest="0" * 64,
        )
    # An unsorted or duplicate overlay rejects at construction.
    duplicate_overlay = (
        CandidateOverlayEntryV1(
            schema_version=1,
            operation="REPLACE",
            path=canonical_path("src/a.py"),
            content_ref=ContentObjectRefV1(
                sha256=hashlib.sha256(b"x = 2\n").hexdigest(), byte_count=6
            ),
        ),
        CandidateOverlayEntryV1(
            schema_version=1,
            operation="REPLACE",
            path=canonical_path("src/a.py"),
            content_ref=ContentObjectRefV1(
                sha256=hashlib.sha256(b"x = 3\n").hexdigest(), byte_count=6
            ),
        ),
    )
    with pytest.raises(ValidationError):
        CandidateTreeV1(
            schema_version=1,
            snapshot=snapshot,
            store=ContentObjectStore(),
            overlay=duplicate_overlay,
            digest=digest_candidate_tree(snapshot.root_digest, duplicate_overlay),
        )

    # --- Identical inputs yield identical Candidate identity. ---
    again = derive_candidate_revision(
        parent_revision, (replace_postimage("src/a.py", b"x = 2\n"),)
    )
    assert again.tree.digest == replaced.tree.digest
    assert again.revision_id == replaced.revision_id
    assert again.candidate_digest == replaced.candidate_digest
    assert again.tree.overlay == replaced.tree.overlay

    # --- A derived chain replaces the overlay entry for the same path. ---
    third = derive_candidate_revision(
        replaced, (replace_postimage("src/a.py", b"x = 3\n"),)
    )
    assert third.tree.read_bytes(canonical_path("src/a.py")) == b"x = 3\n"
    assert replaced.tree.read_bytes(canonical_path("src/a.py")) == b"x = 2\n"
    # The chain stays parent-independent: replaced is untouched by third.
    assert replaced.tree.digest == again.tree.digest

    # --- Zero postimages derive a child with an unchanged tree. ---
    empty: CandidatePostimageSequenceV1 = ()
    noop = derive_candidate_revision(parent_revision, empty)
    assert noop.tree.digest == parent_revision.tree.digest
    assert noop.revision_id != parent_revision.revision_id


def test_candidate_revision_binds_tree_identity_and_audit_chain() -> None:
    store = ContentObjectStore()
    for _, raw in _FILES:
        store.put(raw)
    snapshot = create_snapshot(_accepted(_FILES), store, classify_supported_text)
    root = root_candidate_revision(snapshot, store)
    assert isinstance(root, CandidateRevisionV1)
    assert root.parent_revision_id is None
    assert root.candidate_digest == root.tree.digest
    assert root.tree.snapshot is snapshot
    child = derive_candidate_revision(
        root, (replace_postimage("src/a.py", b"x = 2\n"),)
    )
    assert child.parent_revision_id == root.revision_id
    assert child.revision_id != root.revision_id
    assert child.candidate_digest == child.tree.digest
    # Audit fields never enter the tree identity.
    assert child.tree.digest != root.tree.digest
    # Two roots over the same snapshot agree.
    again = root_candidate_revision(snapshot, store)
    assert again == root
    assert again.candidate_digest == root.candidate_digest


def test_candidate_revision_and_postimage_schemas_are_closed() -> None:
    invalid_postimage: tuple[dict[str, object], ...] = (
        {"schema_version": 1, "operation": "REPLACE", "path": {"value": "src/a.py"}},
        {
            "schema_version": 1,
            "operation": "DELETE",
            "path": {"value": "src/a.py"},
            "raw_bytes": b"x",
        },
        {"schema_version": 1, "operation": "REPLACE", "raw_bytes": b"x"},
        {
            "schema_version": "1",
            "operation": "REPLACE",
            "path": {"value": "src/a.py"},
            "raw_bytes": b"x",
        },
        {
            "schema_version": 1,
            "operation": "REPLACE",
            "path": {"value": "src/a.py"},
            "raw_bytes": b"x",
            "extra": 1,
        },
    )
    for payload in invalid_postimage:
        with pytest.raises(ValidationError):
            CandidatePostimageV1.model_validate(payload)
    valid = replace_postimage("src/a.py", b"x = 2\n")
    with pytest.raises(ValidationError):
        valid.operation = "CREATE"  # frozen


def test_candidate_tree_imports_no_t11_modules() -> None:
    """The overlay tree structurally satisfies ReadableTreeV1 without any
    T11.1 (tools) import — AST-pinned over the module source."""
    source = Path("src/vespercode/trees/candidate.py").read_text(encoding="utf-8")
    parsed = ast.parse(source)
    imported: list[str] = []
    for node in ast.walk(parsed):
        if isinstance(node, ast.ImportFrom) and node.module:
            imported.append(node.module)
        elif isinstance(node, ast.Import):
            imported.extend(alias.name for alias in node.names)
    assert not any(
        name == "vespercode.tools" or name.startswith("vespercode.tools.")
        for name in imported
    )


def test_candidate_tree_reads_exact_snapshot_bytes_outside_overlay() -> None:
    store = ContentObjectStore()
    for _, raw in _FILES:
        store.put(raw)
    snapshot = create_snapshot(_accepted(_FILES), store, classify_supported_text)
    root = root_candidate_revision(snapshot, store)
    child = derive_candidate_revision(
        root, (replace_postimage("src/a.py", b"x = 2\n"),)
    )
    # Untouched paths read the exact sealed snapshot bytes.
    assert child.tree.read_bytes(canonical_path("src/pkg/b.py")) == b"value = 2\n"
    assert child.tree.read_bytes(canonical_path("README.md")) == b"readme\n"
    with pytest.raises(KeyError):
        child.tree.read_bytes(canonical_path("src/missing.py"))

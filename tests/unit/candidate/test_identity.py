"""T12.1 legacy step 12.D: CandidateIdentityV1 three-root binding tests.

The exact RED test (identical Snapshot/CandidateTree/FinalDiff roots
restore the identical identity digest), the complete restoration matrix
(registry 12.D: revision metadata does not affect identity; any
base/path/postimage change does; restoring exact bound facts restores the
original digest; a claimed mismatched digest is rejected), and the domain
assertions for the closed identity contract.  Patch application, revision
publication, writeback approval, mutable workspace access, deletion,
rename, and binary changes remain out of scope (GREEN-4).
"""

from __future__ import annotations

import hashlib
from typing import Literal

import pytest

# The identity contracts are pydantic runtime models; the hash-locked gate
# toolchain does not install runtime dependencies, so this module skips
# cleanly there instead of failing at collection (formal env runs it
# fully).
pytest.importorskip("pydantic")

from pydantic import ValidationError

from vespercode.candidate.final_diff import recompute_final_diff
from vespercode.candidate.identity import (
    CandidateIdentityV1,
    bind_revision_identity,
    build_candidate_identity,
)
from vespercode.canonical.path_v1 import CanonicalRelativePathV1
from vespercode.profiles.editable import EditablePathPolicyV1
from vespercode.profiles.registry import build_profile_registry
from vespercode.trees.candidate import (
    CandidatePostimageV1,
    CandidateTreeV1,
    derive_candidate_revision,
    root_candidate_revision,
)
from vespercode.trees.content_store import ContentObjectStore
from vespercode.trees.snapshot import (
    AcceptedGitPreflightV1,
    SealedSnapshotInputFileV1,
    SnapshotTreeV1,
    create_snapshot,
)
from vespercode.trees.text_classifier import classify_supported_text
from vespercode.workspace.git_preflight import GitPreflightResultV1

_FILES: tuple[tuple[str, bytes], ...] = (
    ("README.md", b"readme\n"),
    ("src/a.py", b"x = 1\n"),
    ("src/b.py", b"y = 1\n"),
    ("src/c.py", b"z = 1\n"),
    ("src/d.py", b"w = 1\n"),
)


def canonical_path(value: str) -> CanonicalRelativePathV1:
    """One canonical repository-relative path test value."""
    return CanonicalRelativePathV1(value)


def staged(
    path: str, raw: bytes, operation: Literal["CREATE", "REPLACE"] = "REPLACE"
) -> CandidatePostimageV1:
    """One staged postimage with complete raw bytes."""
    return CandidatePostimageV1(
        schema_version=1,
        operation=operation,
        path=canonical_path(path),
        raw_bytes=raw,
    )


def _seal(
    *,
    tracked_file_count: int,
    tracked_byte_count: int,
    repository_policy_digest: str,
) -> GitPreflightResultV1:
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
        repository_policy_digest=repository_policy_digest,
        ignore_rules=(),
        tracked_file_count=tracked_file_count,
        tracked_byte_count=tracked_byte_count,
    )


def _accepted(
    files: tuple[tuple[str, bytes], ...], repository_policy_digest: str
) -> AcceptedGitPreflightV1:
    """One accepted preflight whose table matches the given raw files."""
    return AcceptedGitPreflightV1(
        schema_version=1,
        preflight=_seal(
            tracked_file_count=len(files),
            tracked_byte_count=sum(len(raw) for _, raw in files),
            repository_policy_digest=repository_policy_digest,
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


def _reference_policy() -> EditablePathPolicyV1:
    """The frozen built-in editable policy (SPEC §1.4.1)."""
    return (
        build_profile_registry()
        .resolve_reference("python-src-py312-v1")
        .editable_path_policy
    )


def _snapshot(
    files: tuple[tuple[str, bytes], ...] = _FILES,
    policy_digest: str | None = None,
) -> tuple[SnapshotTreeV1, ContentObjectStore]:
    """One sealed snapshot bound to the real policy digest (or a drift)."""
    policy = _reference_policy()
    digest = policy_digest if policy_digest is not None else policy.digest
    store = ContentObjectStore()
    for _, raw in files:
        store.put(raw)
    return create_snapshot(
        _accepted(files, digest), store, classify_supported_text
    ), store


def _candidate(
    snapshot: SnapshotTreeV1,
    store: ContentObjectStore,
    *,
    replace: tuple[tuple[str, bytes], ...] = (("src/a.py", b"x = 2\n"),),
    create: tuple[tuple[str, bytes], ...] = (("src/new.py", b"fresh = 1\n"),),
) -> CandidateTreeV1:
    """One candidate tree with the given staged replaces and creates."""
    root = root_candidate_revision(snapshot, store)
    postimages = tuple(staged(path, raw) for path, raw in replace) + tuple(
        staged(path, raw, operation="CREATE") for path, raw in create
    )
    return derive_candidate_revision(root, postimages).tree


@pytest.fixture
def policy() -> EditablePathPolicyV1:
    return _reference_policy()


@pytest.fixture
def snapshot() -> SnapshotTreeV1:
    return _snapshot()[0]


@pytest.fixture
def candidate() -> CandidateTreeV1:
    snapshot, store = _snapshot()
    return _candidate(snapshot, store)


def test_candidate_identity_ignores_revision_metadata(
    snapshot: SnapshotTreeV1,
    candidate: CandidateTreeV1,
    policy: EditablePathPolicyV1,
) -> None:
    final_diff = recompute_final_diff(snapshot, candidate, policy)
    left = build_candidate_identity(
        snapshot.root_digest, candidate.digest, final_diff.digest
    )
    right = build_candidate_identity(
        snapshot.root_digest, candidate.digest, final_diff.digest
    )
    assert left.digest == right.digest


def test_candidate_identity_restoration_matrix(
    snapshot: SnapshotTreeV1,
    candidate: CandidateTreeV1,
    policy: EditablePathPolicyV1,
) -> None:
    """Registry 12.D: revision metadata never enters the identity; any
    base/path/postimage change does; restoring the exact bound facts
    restores the original digest; a claimed mismatched digest rejects."""
    final_diff = recompute_final_diff(snapshot, candidate, policy)
    original = build_candidate_identity(
        snapshot.root_digest, candidate.digest, final_diff.digest
    )

    # --- Revision metadata does not affect identity. ---
    store = ContentObjectStore()
    for _, raw in _FILES:
        store.put(raw)
    root = root_candidate_revision(snapshot, store)
    noop = derive_candidate_revision(root, ())
    assert root.revision_id != noop.revision_id
    assert root.parent_revision_id != noop.parent_revision_id
    assert root.tree.digest == noop.tree.digest
    root_diff = recompute_final_diff(snapshot, root.tree, policy)
    root_identity = build_candidate_identity(
        snapshot.root_digest, root.tree.digest, root_diff.digest
    )
    noop_identity = build_candidate_identity(
        snapshot.root_digest, noop.tree.digest, root_diff.digest
    )
    # Different revision metadata, identical three roots: identical
    # identity — audit fields are never inputs of the identity function.
    assert noop_identity.digest == root_identity.digest
    assert root.candidate_digest == noop.candidate_digest
    # The changed candidate tree has a different identity (path change).
    assert root_identity.digest != original.digest

    # --- Any base change changes the identity. ---
    drifted_base = build_candidate_identity(
        "b" * 64, candidate.digest, final_diff.digest
    )
    assert drifted_base.digest != original.digest

    # --- Any candidate-tree (path/postimage) change changes the identity. ---
    drifted_tree = build_candidate_identity(
        snapshot.root_digest, "c" * 64, final_diff.digest
    )
    assert drifted_tree.digest != original.digest

    # --- Any FinalDiff change changes the identity. ---
    drifted_diff = build_candidate_identity(
        snapshot.root_digest, candidate.digest, "d" * 64
    )
    assert drifted_diff.digest != original.digest

    # --- Restoring the exact bound facts restores the original digest. ---
    restored = build_candidate_identity(
        snapshot.root_digest, candidate.digest, final_diff.digest
    )
    assert restored.digest == original.digest
    assert restored == original

    # --- A claimed mismatched digest is rejected. ---
    with pytest.raises(ValidationError):
        CandidateIdentityV1.model_validate(
            {
                "schema_version": 1,
                "snapshot_tree_digest": snapshot.root_digest,
                "candidate_tree_digest": candidate.digest,
                "final_diff_digest": final_diff.digest,
                "digest": "0" * 64,
            }
        )

    # --- Same tree with a different revision chain restores the same
    # three-root identity (the tree layer identity is deterministic). ---
    again_store = ContentObjectStore()
    for _, raw in _FILES:
        again_store.put(raw)
    again = _candidate(
        snapshot,
        again_store,
        replace=(("src/a.py", b"x = 2\n"),),
        create=(("src/new.py", b"fresh = 1\n"),),
    )
    assert again.digest == candidate.digest
    again_diff = recompute_final_diff(snapshot, again, policy)
    assert again_diff.digest == final_diff.digest
    assert (
        build_candidate_identity(
            snapshot.root_digest, again.digest, again_diff.digest
        ).digest
        == original.digest
    )


def test_bind_revision_identity_sets_candidate_digest_to_identity() -> None:
    """SPEC §4.3: the run-level candidate_digest exactly equals
    ``CandidateIdentityV1.digest`` after the Task 12.D binding, while the
    audit chain and the immutable tree stay untouched."""
    snapshot, store = _snapshot()
    root = root_candidate_revision(snapshot, store)
    child = derive_candidate_revision(root, (staged("src/a.py", b"x = 2\n"),))
    final_diff = recompute_final_diff(snapshot, child.tree, _reference_policy())
    bound = bind_revision_identity(child, final_diff.digest)
    identity = build_candidate_identity(
        snapshot.root_digest, child.tree.digest, final_diff.digest
    )
    assert bound.candidate_digest == identity.digest
    assert bound.revision_id == child.revision_id
    assert bound.parent_revision_id == child.parent_revision_id
    assert bound.tree is child.tree
    # Binding the same revision to a different FinalDiff digest changes
    # only the candidate digest — the identity follows the bound diff.
    other = build_candidate_identity(snapshot.root_digest, child.tree.digest, "d" * 64)
    re_bound = bind_revision_identity(child, "d" * 64)
    assert re_bound.candidate_digest == other.digest


def test_candidate_identity_schema_is_closed() -> None:
    """The identity rejects unknown, missing, and type-confused fields."""
    valid = build_candidate_identity("0" * 64, "1" * 64, "2" * 64)
    assert isinstance(valid, CandidateIdentityV1)
    assert len(valid.digest) == 64
    invalid: tuple[dict[str, object], ...] = (
        {
            "schema_version": 1,
            "candidate_tree_digest": "1" * 64,
            "final_diff_digest": "2" * 64,
            "digest": valid.digest,
        },
        {
            "schema_version": 1,
            "snapshot_tree_digest": "0" * 64,
            "candidate_tree_digest": "1" * 64,
            "final_diff_digest": "2" * 64,
        },
        {
            "schema_version": 1,
            "snapshot_tree_digest": "0" * 64,
            "candidate_tree_digest": "1" * 64,
            "final_diff_digest": "2" * 64,
            "digest": "short",
        },
        {
            "schema_version": "1",
            "snapshot_tree_digest": "0" * 64,
            "candidate_tree_digest": "1" * 64,
            "final_diff_digest": "2" * 64,
            "digest": valid.digest,
        },
        {
            "schema_version": 1,
            "snapshot_tree_digest": "0" * 64,
            "candidate_tree_digest": "1" * 64,
            "final_diff_digest": "2" * 64,
            "digest": valid.digest,
            "extra": 1,
        },
    )
    for payload in invalid:
        with pytest.raises(ValidationError):
            CandidateIdentityV1.model_validate(payload)
    with pytest.raises(ValidationError):
        valid.digest = "3" * 64  # frozen

"""T12.1 legacy step 12.D: FinalDiffV1 recomputation tests.

The complete Snapshot-to-candidate structured CREATE/REPLACE diff
recomputation: exact preimages/postimages, byte counts, deterministic
path order, the sole-editable-policy revalidation, the closed rejection
matrix (policy binding drift, non-editable entries, candidate hard caps,
non-text state), and the closed FinalDiff schema contracts.  Patch
application, revision publication, writeback approval, mutable workspace
access, deletion, rename, and binary changes remain out of scope
(GREEN-4).
"""

from __future__ import annotations

import hashlib

import pytest

# The FinalDiff contracts are pydantic runtime models; the hash-locked
# gate toolchain does not install runtime dependencies, so this module
# skips cleanly there instead of failing at collection (formal env runs it
# fully).
pytest.importorskip("pydantic")

from pydantic import ValidationError

from vespercode.candidate.final_diff import (
    FinalDiffEntryV1,
    FinalDiffPreimageV1,
    FinalDiffRejectedError,
    FinalDiffV1,
    recompute_final_diff,
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


def staged(path: str, raw: bytes, operation: str = "REPLACE") -> CandidatePostimageV1:
    """One staged postimage with complete raw bytes."""
    return CandidatePostimageV1(
        schema_version=1,
        operation=operation,  # type: ignore[arg-type]
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


def _policy() -> EditablePathPolicyV1:
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
    policy = _policy()
    digest = policy_digest if policy_digest is not None else policy.digest
    store = ContentObjectStore()
    for _, raw in files:
        store.put(raw)
    return create_snapshot(
        _accepted(files, digest), store, classify_supported_text
    ), store


def _tree(
    snapshot: SnapshotTreeV1,
    store: ContentObjectStore,
    postimages: tuple[CandidatePostimageV1, ...],
) -> CandidateTreeV1:
    """One candidate tree derived from the given staged postimages."""
    return derive_candidate_revision(
        root_candidate_revision(snapshot, store), postimages
    ).tree


def _fixture() -> tuple[SnapshotTreeV1, CandidateTreeV1, EditablePathPolicyV1]:
    """One standard fixture: snapshot, a mixed REPLACE/CREATE candidate,
    and the frozen built-in policy."""
    policy = _policy()
    snapshot, store = _snapshot()
    tree = _tree(
        snapshot,
        store,
        (
            staged("src/a.py", b"x = 2\n"),
            staged("src/new.py", b"fresh = 1\n", operation="CREATE"),
        ),
    )
    return snapshot, tree, policy


def test_recompute_final_diff_binds_complete_create_replace_diff() -> None:
    """Registry 12.D: the complete structured net diff with exact
    preimages/postimages, byte counts, and deterministic path order."""
    snapshot, tree, policy = _fixture()
    final_diff = recompute_final_diff(snapshot, tree, policy)
    assert isinstance(final_diff, FinalDiffV1)
    assert final_diff.schema_version == 1
    assert final_diff.snapshot_tree_digest == snapshot.root_digest
    # Entries sorted by canonical path, CREATE/REPLACE mixed.
    assert [entry.path.value for entry in final_diff.entries] == [
        "src/a.py",
        "src/new.py",
    ]
    replace_entry = final_diff.entries[0]
    assert replace_entry.operation == "REPLACE"
    assert replace_entry.preimage.kind == "PRESENT"
    assert (
        replace_entry.preimage.content_digest == hashlib.sha256(b"x = 1\n").hexdigest()
    )
    preimage_metadata = replace_entry.preimage.text_metadata
    assert preimage_metadata is not None
    assert preimage_metadata.encoding == "UTF8"
    assert preimage_metadata.newline == "LF"
    assert preimage_metadata.final_newline is True
    assert replace_entry.postimage_digest == hashlib.sha256(b"x = 2\n").hexdigest()
    assert replace_entry.postimage_text_metadata.encoding == "UTF8"
    create_entry = final_diff.entries[1]
    assert create_entry.operation == "CREATE"
    assert create_entry.preimage.kind == "ABSENT"
    assert create_entry.preimage.content_digest is None
    assert create_entry.preimage.text_metadata is None
    assert create_entry.postimage_digest == hashlib.sha256(b"fresh = 1\n").hexdigest()
    # The byte total is the sum of the complete postimage raw bytes.
    assert final_diff.added_and_replacement_text_bytes == len(b"x = 2\n") + len(
        b"fresh = 1\n"
    )
    # The digest binds the snapshot root and every field (64-hex).
    assert len(final_diff.digest) == 64
    assert isinstance(final_diff.digest, str)


def test_recompute_final_diff_is_deterministic() -> None:
    snapshot, tree, policy = _fixture()
    first = recompute_final_diff(snapshot, tree, policy)
    second = recompute_final_diff(snapshot, tree, policy)
    assert first == second
    assert first.digest == second.digest
    # Rebuilding the same candidate state from a fresh store restores the
    # exact FinalDiff digest.
    again_snapshot, again_store = _snapshot()
    again_tree = _tree(
        again_snapshot,
        again_store,
        (
            staged("src/a.py", b"x = 2\n"),
            staged("src/new.py", b"fresh = 1\n", operation="CREATE"),
        ),
    )
    assert again_tree.digest == tree.digest
    again = recompute_final_diff(again_snapshot, again_tree, policy)
    assert again.digest == first.digest


def test_recompute_final_diff_empty_candidate_is_zero_entries() -> None:
    policy = _policy()
    snapshot, store = _snapshot()
    root = root_candidate_revision(snapshot, store)
    final_diff = recompute_final_diff(snapshot, root.tree, policy)
    assert final_diff.entries == ()
    assert final_diff.added_and_replacement_text_bytes == 0
    # The empty candidate still binds the snapshot root deterministically.
    assert final_diff.snapshot_tree_digest == snapshot.root_digest
    assert recompute_final_diff(snapshot, root.tree, policy) == final_diff


def test_recompute_final_diff_ignores_unchanged_paths() -> None:
    """A staged postimage equal to the snapshot bytes is not an entry."""
    policy = _policy()
    snapshot, store = _snapshot()
    tree = _tree(
        snapshot,
        store,
        (staged("src/a.py", b"x = 1\n"),),  # byte-identical REPLACE
    )
    final_diff = recompute_final_diff(snapshot, tree, policy)
    assert final_diff.entries == ()
    assert final_diff.added_and_replacement_text_bytes == 0


def test_recompute_final_diff_ignores_unchanged_non_text_paths() -> None:
    """A legitimately tracked NON_TEXT_FILE the candidate never touched is
    not an entry and never fails the diff closed (SPEC §4.3: an empty
    candidate yields ``entries=[]`` with byte total 0)."""
    policy = _policy()
    snapshot, store = _snapshot(
        (("src/a.py", b"x = 1\n"), ("src/bin.dat", b"\x00\x02"))
    )
    root = root_candidate_revision(snapshot, store)
    final_diff = recompute_final_diff(snapshot, root.tree, policy)
    assert final_diff.entries == ()
    assert final_diff.added_and_replacement_text_bytes == 0
    # Even a candidate that edits only a text file leaves the untouched
    # non-text asset out of the diff.
    edited = _tree(snapshot, store, (staged("src/a.py", b"x = 2\n"),))
    edited_diff = recompute_final_diff(snapshot, edited, policy)
    assert [entry.path.value for entry in edited_diff.entries] == ["src/a.py"]


def test_recompute_final_diff_rejects_policy_binding_drift() -> None:
    policy = _policy()
    drifted_snapshot, store = _snapshot(policy_digest="b" * 64)
    tree = _tree(drifted_snapshot, store, (staged("src/a.py", b"x = 2\n"),))
    with pytest.raises(FinalDiffRejectedError, match="TREE_INTEGRITY_FAILED"):
        recompute_final_diff(drifted_snapshot, tree, policy)


def test_recompute_final_diff_rejects_unrelated_snapshot() -> None:
    """A passed snapshot that is not the candidate tree's sealed snapshot
    cannot bound the diff (limits/preimages would compare wrong bases)."""
    policy = _policy()
    snapshot, store = _snapshot()
    tree = _tree(snapshot, store, (staged("src/a.py", b"x = 2\n"),))
    other_snapshot, _ = _snapshot(
        (("README.md", b"readme\n"), ("src/a.py", b"x = 1\n"), ("src/e.py", b"v = 1\n"))
    )
    assert other_snapshot.root_digest != snapshot.root_digest
    with pytest.raises(FinalDiffRejectedError, match="TREE_INTEGRITY_FAILED"):
        recompute_final_diff(other_snapshot, tree, policy)


def test_recompute_final_diff_rejects_non_editable_entries() -> None:
    policy = _policy()
    snapshot, store = _snapshot()
    tree = _tree(
        snapshot,
        store,
        (staged("docs/x.md", b"doc\n", operation="CREATE"),),
    )
    with pytest.raises(FinalDiffRejectedError, match="PATCH_PATH_NOT_EDITABLE"):
        recompute_final_diff(snapshot, tree, policy)


def test_recompute_final_diff_rejects_over_four_changed_files() -> None:
    policy = _policy()
    snapshot, store = _snapshot()
    tree = _tree(
        snapshot,
        store,
        (
            staged("src/a.py", b"x = 2\n"),
            staged("src/b.py", b"y = 2\n"),
            staged("src/c.py", b"z = 2\n"),
            staged("src/d.py", b"w = 2\n"),
        ),
    )
    with pytest.raises(FinalDiffRejectedError, match="PATCH_LIMIT_EXCEEDED"):
        recompute_final_diff(snapshot, tree, policy)


def test_recompute_final_diff_rejects_byte_total_over_limit() -> None:
    policy = _policy()
    huge_base = b"x = 0\n" + b"p\n" * 74997  # 150000 bytes
    huge_postimage = b"x = 1\n" + b"p\n" * 74997  # 150000 bytes, changed line 1
    snapshot, store = _snapshot((("src/a.py", huge_base),))
    tree = _tree(snapshot, store, (staged("src/a.py", huge_postimage),))
    with pytest.raises(FinalDiffRejectedError, match="PATCH_LIMIT_EXCEEDED"):
        recompute_final_diff(snapshot, tree, policy)


def test_recompute_final_diff_rejects_non_text_postimage_state() -> None:
    policy = _policy()
    snapshot, store = _snapshot()
    tree = _tree(snapshot, store, (staged("src/a.py", b"\x00\x01"),))
    with pytest.raises(FinalDiffRejectedError, match="TREE_INTEGRITY_FAILED"):
        recompute_final_diff(snapshot, tree, policy)


def test_final_diff_schemas_are_closed() -> None:
    """Unknown, missing, and type-confused fields reject; CREATE must bind
    ABSENT and REPLACE must bind PRESENT; entries are bounded, unique,
    sorted, and digest-bound."""
    snapshot, tree, policy = _fixture()
    final_diff = recompute_final_diff(snapshot, tree, policy)
    invalid: tuple[dict[str, object], ...] = (
        {
            "schema_version": 1,
            "snapshot_tree_digest": snapshot.root_digest,
            "entries": final_diff.entries,
            "added_and_replacement_text_bytes": 0,
            "digest": final_diff.digest,
            "extra": 1,
        },
        {
            "schema_version": 1,
            "snapshot_tree_digest": snapshot.root_digest,
            "entries": final_diff.entries,
            "added_and_replacement_text_bytes": 0,
        },
        {
            "schema_version": 1,
            "snapshot_tree_digest": snapshot.root_digest,
            "entries": final_diff.entries,
            "added_and_replacement_text_bytes": 0,
            "digest": "0" * 64,
        },
        {
            "schema_version": 1,
            "snapshot_tree_digest": "0" * 64,
            "entries": final_diff.entries,
            "added_and_replacement_text_bytes": 0,
            "digest": final_diff.digest,
        },
        {
            "schema_version": "1",
            "snapshot_tree_digest": snapshot.root_digest,
            "entries": final_diff.entries,
            "added_and_replacement_text_bytes": 0,
            "digest": final_diff.digest,
        },
        {
            "schema_version": 1,
            "snapshot_tree_digest": snapshot.root_digest,
            "entries": final_diff.entries,
            "added_and_replacement_text_bytes": -1,
            "digest": final_diff.digest,
        },
    )
    for payload in invalid:
        with pytest.raises(ValidationError):
            FinalDiffV1.model_validate(payload)
    # Entry schema: CREATE must bind ABSENT, REPLACE must bind PRESENT.
    with pytest.raises(ValidationError):
        FinalDiffEntryV1.model_validate(
            {
                "operation": "CREATE",
                "path": {"value": "src/a.py"},
                "preimage": {
                    "kind": "PRESENT",
                    "content_digest": "0" * 64,
                    "text_metadata": {
                        "encoding": "UTF8",
                        "newline": "LF",
                        "final_newline": True,
                    },
                },
                "postimage_digest": "1" * 64,
                "postimage_text_metadata": {
                    "encoding": "UTF8",
                    "newline": "LF",
                    "final_newline": True,
                },
            }
        )
    with pytest.raises(ValidationError):
        FinalDiffEntryV1.model_validate(
            {
                "operation": "REPLACE",
                "path": {"value": "src/a.py"},
                "preimage": {"kind": "ABSENT"},
                "postimage_digest": "1" * 64,
                "postimage_text_metadata": {
                    "encoding": "UTF8",
                    "newline": "LF",
                    "final_newline": True,
                },
            }
        )
    # Preimage schema: ABSENT carries no value fields.
    with pytest.raises(ValidationError):
        FinalDiffPreimageV1.model_validate(
            {
                "kind": "ABSENT",
                "content_digest": "0" * 64,
                "text_metadata": {
                    "encoding": "UTF8",
                    "newline": "LF",
                    "final_newline": True,
                },
            }
        )
    with pytest.raises(ValidationError):
        FinalDiffPreimageV1.model_validate({"kind": "MAYBE"})
    # The recomputed diff validates as a closed model.
    rebuilt = FinalDiffV1.model_validate(
        {
            "schema_version": 1,
            "snapshot_tree_digest": final_diff.snapshot_tree_digest,
            "entries": final_diff.entries,
            "added_and_replacement_text_bytes": final_diff.added_and_replacement_text_bytes,
            "digest": final_diff.digest,
        }
    )
    assert rebuilt == final_diff

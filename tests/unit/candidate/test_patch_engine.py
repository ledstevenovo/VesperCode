"""T12.1 legacy step 12.C: atomic exact candidate patch transaction tests.

The exact RED test (a mixed legal/non-editable patch yields
``PATCH_PATH_NOT_EDITABLE`` and zero candidate side effects), the complete
atomicity/priority/limit matrix (registry 12.C: any illegal
path/operation/encoding/size/count/byte limit rejects the whole patch with
zero Candidate objects; rejection priority is deterministic; exact legal
input commits once), and the domain assertions for the closed action,
context, outcome, and publisher contracts.  FinalDiff construction,
candidate semantic identity, deletion, rename, mode, and binary support
remain out of scope (GREEN-4).
"""

from __future__ import annotations

import hashlib

import pytest

# The patch-engine contracts are pydantic runtime models; the hash-locked
# gate toolchain does not install runtime dependencies, so this module
# skips cleanly there instead of failing at collection (formal env runs it
# fully).
pytest.importorskip("pydantic")

from pydantic import ValidationError

from vespercode.canonical.path_v1 import CanonicalRelativePathV1
from vespercode.candidate.patch_engine import (
    ApplyCandidatePatchAction,
    CandidatePatchContextV1,
    CandidatePatchOutcomeV1,
    apply_candidate_patch,
    patch_path_fact_for_action,
)
from vespercode.profiles.registry import build_profile_registry
from vespercode.trees.candidate import (
    CandidatePostimageV1,
    CandidateRevisionV1,
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
from vespercode.workspace.path_guard import IgnoreRuleV1, ignore_rules_digest


def stage_replace(path: str, raw: bytes) -> CandidatePostimageV1:
    """One staged REPLACE postimage with complete raw bytes."""
    return CandidatePostimageV1(
        schema_version=1, operation="REPLACE", path=canonical_path(path), raw_bytes=raw
    )


def canonical_path(value: str) -> CanonicalRelativePathV1:
    """One canonical repository-relative path test value."""
    return CanonicalRelativePathV1(value)


def patch_action(base_digest: str, patch_text: str) -> ApplyCandidatePatchAction:
    """One closed apply-candidate-patch action over strict patch text."""
    return ApplyCandidatePatchAction(
        schema_version=1,
        action_type="apply_candidate_patch",
        base_candidate_digest=base_digest,
        patch_format="UNIFIED_DIFF_V1",
        patch_text=patch_text,
    )


def valid_replace_patch() -> str:
    """One complete strict REPLACE patch for ``src/a.py`` (x = 1 -> x = 2)."""
    return "--- a/src/a.py\n+++ b/src/a.py\n@@ -1,1 +1,1 @@\n-x = 1\n+x = 2\n"


def replace_src_a_and_readme_patch() -> str:
    """One strict two-entry patch: REPLACE src/a.py and REPLACE README.md."""
    return (
        valid_replace_patch()
        + "\n"
        + "--- a/README.md\n"
        + "+++ b/README.md\n"
        + "@@ -1,1 +1,1 @@\n"
        + "-readme\n"
        + "+readme v2\n"
    )


class SpyCandidatePublisher:
    """One observable publisher port: counts and records publications."""

    def __init__(self) -> None:
        self.publish_count = 0
        self.published: list[CandidateRevisionV1] = []

    def publish(self, revision: CandidateRevisionV1) -> None:
        self.publish_count += 1
        self.published.append(revision)


_FILES: tuple[tuple[str, bytes], ...] = (
    ("README.md", b"readme\n"),
    ("src/a.py", b"x = 1\n"),
    ("src/b.py", b"y = 1\n"),
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


def _reference_policy_digest() -> str:
    """The frozen built-in editable policy digest (SPEC §1.4.1)."""
    return (
        build_profile_registry()
        .resolve_reference("python-src-py312-v1")
        .editable_path_policy.digest
    )


def _context(
    files: tuple[tuple[str, bytes], ...] = _FILES,
    *,
    policy_digest: str | None = None,
    ignore_rules: tuple[IgnoreRuleV1, ...] = (),
    current: CandidateRevisionV1 | None = None,
) -> tuple[CandidatePatchContextV1, SnapshotTreeV1, ContentObjectStore]:
    """One candidate context: sealed snapshot, real frozen policy, spy
    publisher, and the given ignore rules."""
    reference = build_profile_registry().resolve_reference("python-src-py312-v1")
    digest = (
        policy_digest
        if policy_digest is not None
        else reference.editable_path_policy.digest
    )
    store = ContentObjectStore()
    for _, raw in files:
        store.put(raw)
    snapshot = create_snapshot(_accepted(files, digest), store, classify_supported_text)
    revision = (
        current if current is not None else root_candidate_revision(snapshot, store)
    )
    context = CandidatePatchContextV1(
        current=revision,
        snapshot=snapshot,
        reference=reference,
        publisher=SpyCandidatePublisher(),
        ignore_rules=ignore_rules,
        ignore_rules_digest=ignore_rules_digest(ignore_rules),
    )
    return context, snapshot, store


@pytest.fixture
def candidate_context() -> CandidatePatchContextV1:
    """One candidate context over the standard sealed fixture snapshot."""
    return _context()[0]


@pytest.fixture
def candidate_publisher() -> SpyCandidatePublisher:
    return SpyCandidatePublisher()


def test_mixed_legal_and_noneditable_patch_has_no_candidate_side_effect(
    candidate_context: CandidatePatchContextV1,
    candidate_publisher: SpyCandidatePublisher,
) -> None:
    outcome = apply_candidate_patch(
        patch_action(
            candidate_context.current.candidate_digest, replace_src_a_and_readme_patch()
        ),
        candidate_context.current,
        candidate_context.with_publisher(candidate_publisher),
    )
    assert outcome.error_code == "PATCH_PATH_NOT_EDITABLE"
    assert candidate_publisher.publish_count == 0


def test_patch_atomicity_priority_limit_matrix() -> None:
    """Registry 12.C: whole-patch rejection with zero Candidate objects for
    every illegal path/operation/encoding/size/count/byte form, stable
    rejection priority, and exactly one publication for legal input."""
    # --- Exact legal input commits once. ---
    context, _, _ = _context()
    spy = SpyCandidatePublisher()
    outcome = apply_candidate_patch(
        patch_action(context.current.candidate_digest, valid_replace_patch()),
        context.current,
        context.with_publisher(spy),
    )
    assert outcome.kind == "PUBLISHED"
    assert outcome.error_code is None
    assert spy.publish_count == 1
    assert outcome.revision is not None
    assert outcome.candidate_tree_digest == outcome.revision.tree.digest
    assert outcome.revision.tree.read_bytes(canonical_path("src/a.py")) == b"x = 2\n"

    # --- Mixed legal/non-editable entries reject the whole patch. ---
    context, _, _ = _context()
    spy = SpyCandidatePublisher()
    outcome = apply_candidate_patch(
        patch_action(
            context.current.candidate_digest, replace_src_a_and_readme_patch()
        ),
        context.current,
        context.with_publisher(spy),
    )
    assert outcome.kind == "REJECTED"
    assert outcome.error_code == "PATCH_PATH_NOT_EDITABLE"
    assert spy.publish_count == 0
    # The legal src/a.py entry is not applied either.
    assert context.current.tree.read_bytes(canonical_path("src/a.py")) == b"x = 1\n"

    # --- Protected artifacts keep priority over the editable gate. ---
    protected_patch = (
        "--- a/tests/test_a.py\n"
        "+++ b/tests/test_a.py\n"
        "@@ -1,1 +1,1 @@\n"
        "-def test_a():\n"
        "+def test_a():\n"
    )
    context, _, _ = _context()
    spy = SpyCandidatePublisher()
    outcome = apply_candidate_patch(
        patch_action(context.current.candidate_digest, protected_patch),
        context.current,
        context.with_publisher(spy),
    )
    assert outcome.error_code == "PROTECTED_ARTIFACT_CHANGED"
    assert spy.publish_count == 0

    # --- Sensitive paths keep the top path priority (also protected and
    # non-editable here). ---
    sensitive_patch = (
        "--- a/tests/.env\n+++ b/tests/.env\n@@ -1,1 +1,1 @@\n-TOKEN=old\n+TOKEN=new\n"
    )
    context, _, _ = _context()
    spy = SpyCandidatePublisher()
    outcome = apply_candidate_patch(
        patch_action(context.current.candidate_digest, sensitive_patch),
        context.current,
        context.with_publisher(spy),
    )
    assert outcome.error_code == "SENSITIVE_PATH"
    assert spy.publish_count == 0

    # --- A stale base candidate rejects before any path check. ---
    context, _, _ = _context()
    spy = SpyCandidatePublisher()
    outcome = apply_candidate_patch(
        patch_action("0" * 64, valid_replace_patch()),
        context.current,
        context.with_publisher(spy),
    )
    assert outcome.error_code == "STALE_CANDIDATE"
    assert spy.publish_count == 0

    # --- Hunk context mismatch rejects the whole patch. ---
    mismatched = "--- a/src/a.py\n+++ b/src/a.py\n@@ -1,1 +1,1 @@\n-x = 999\n+x = 2\n"
    context, _, _ = _context()
    spy = SpyCandidatePublisher()
    outcome = apply_candidate_patch(
        patch_action(context.current.candidate_digest, mismatched),
        context.current,
        context.with_publisher(spy),
    )
    assert outcome.error_code == "PATCH_CONTEXT_MISMATCH"
    assert spy.publish_count == 0

    # --- A hunk whose declared position is offset (no fuzzy apply). ---
    offset = "--- a/src/a.py\n+++ b/src/a.py\n@@ -2,1 +2,1 @@\n-x = 1\n+x = 2\n"
    context, _, _ = _context()
    spy = SpyCandidatePublisher()
    outcome = apply_candidate_patch(
        patch_action(context.current.candidate_digest, offset),
        context.current,
        context.with_publisher(spy),
    )
    assert outcome.error_code == "PATCH_CONTEXT_MISMATCH"
    assert spy.publish_count == 0

    # --- A zero-count hunk whose virtual position lies beyond EOF is not
    # an EOF insertion — the declared position must stay within the base.
    # ---
    beyond_eof = "--- a/src/a.py\n+++ b/src/a.py\n@@ -99,0 +99,1 @@\n+x = 2\n"
    context, _, _ = _context()
    spy = SpyCandidatePublisher()
    outcome = apply_candidate_patch(
        patch_action(context.current.candidate_digest, beyond_eof),
        context.current,
        context.with_publisher(spy),
    )
    assert outcome.error_code == "PATCH_CONTEXT_MISMATCH"
    assert spy.publish_count == 0

    # --- Unsupported operation forms (DELETE) reject closed. ---
    delete_patch = "--- a/src/a.py\n+++ /dev/null\n@@ -1,1 +0,0 @@\n-x = 1\n"
    context, _, _ = _context()
    spy = SpyCandidatePublisher()
    outcome = apply_candidate_patch(
        patch_action(context.current.candidate_digest, delete_patch),
        context.current,
        context.with_publisher(spy),
    )
    assert outcome.error_code == "UNSUPPORTED_PATCH_OPERATION"
    assert spy.publish_count == 0

    # --- Trailing bytes are a schema-invalid parse failure. ---
    context, _, _ = _context()
    spy = SpyCandidatePublisher()
    outcome = apply_candidate_patch(
        patch_action(
            context.current.candidate_digest, valid_replace_patch() + "\ntrailing"
        ),
        context.current,
        context.with_publisher(spy),
    )
    assert outcome.error_code == "PATCH_SCHEMA_INVALID"
    assert spy.publish_count == 0

    # --- Document-level encoding violations reject closed. ---
    crlf_patch = valid_replace_patch().replace("\n", "\r\n")
    context, _, _ = _context()
    spy = SpyCandidatePublisher()
    outcome = apply_candidate_patch(
        patch_action(context.current.candidate_digest, crlf_patch),
        context.current,
        context.with_publisher(spy),
    )
    assert outcome.error_code == "PATCH_SCHEMA_INVALID"
    assert spy.publish_count == 0

    # --- CREATE on an existing path is a collision rejection. ---
    create_existing = "--- /dev/null\n+++ b/src/a.py\n@@ -0,0 +1,1 @@\n+x = 2\n"
    context, _, _ = _context()
    spy = SpyCandidatePublisher()
    outcome = apply_candidate_patch(
        patch_action(context.current.candidate_digest, create_existing),
        context.current,
        context.with_publisher(spy),
    )
    assert outcome.error_code == "PATH_EXISTS"
    assert spy.publish_count == 0

    # --- CREATE of the editable root itself is not editable (SPEC §1.4.1:
    # file entries must not equal the directory root itself). ---
    create_root = "--- /dev/null\n+++ b/src\n@@ -0,0 +1,1 @@\n+x = 2\n"
    context, _, _ = _context()
    spy = SpyCandidatePublisher()
    outcome = apply_candidate_patch(
        patch_action(context.current.candidate_digest, create_root),
        context.current,
        context.with_publisher(spy),
    )
    assert outcome.error_code == "PATCH_PATH_NOT_EDITABLE"
    assert spy.publish_count == 0

    # --- CREATE on a directory path is a collision rejection. ---
    context, _, _ = _context()
    spy = SpyCandidatePublisher()
    seeded = apply_candidate_patch(
        patch_action(
            context.current.candidate_digest,
            "--- /dev/null\n+++ b/src/pkg/new.py\n@@ -0,0 +1,1 @@\n+fresh = 1\n",
        ),
        context.current,
        context.with_publisher(spy),
    )
    assert seeded.kind == "PUBLISHED"
    assert seeded.revision is not None
    # The published revision is the new current: the context must be
    # re-derived from it (a stale context whose ``current`` is the
    # pre-seed revision rejects with STALE_CANDIDATE before any path
    # check), so the collision case uses a fresh seeded context.
    seeded_context, _, _ = _context(current=seeded.revision)
    spy = SpyCandidatePublisher()
    create_on_dir = "--- /dev/null\n+++ b/src/pkg\n@@ -0,0 +1,1 @@\n+x = 2\n"
    outcome = apply_candidate_patch(
        patch_action(seeded.revision.candidate_digest, create_on_dir),
        seeded.revision,
        seeded_context.with_publisher(spy),
    )
    assert outcome.error_code == "PATH_EXISTS"
    assert spy.publish_count == 0

    # --- CREATE under an existing file is a collision rejection (a file
    # can never be a directory of another path). ---
    context, _, _ = _context()
    spy = SpyCandidatePublisher()
    create_under_file = "--- /dev/null\n+++ b/src/a.py/x\n@@ -0,0 +1,1 @@\n+x = 2\n"
    outcome = apply_candidate_patch(
        patch_action(context.current.candidate_digest, create_under_file),
        context.current,
        context.with_publisher(spy),
    )
    assert outcome.error_code == "PATH_EXISTS"
    assert spy.publish_count == 0

    # --- CREATE of a Windows case-colliding path is a collision
    # rejection. ---
    context, _, _ = _context()
    spy = SpyCandidatePublisher()
    create_case_alias = "--- /dev/null\n+++ b/src/A.py\n@@ -0,0 +1,1 @@\n+x = 2\n"
    outcome = apply_candidate_patch(
        patch_action(context.current.candidate_digest, create_case_alias),
        context.current,
        context.with_publisher(spy),
    )
    assert outcome.error_code == "PATH_EXISTS"
    assert spy.publish_count == 0

    # --- CREATE under a case-aliased ancestor file is a collision
    # rejection (src/A.py is the Windows alias of the existing file
    # src/a.py, so src/A.py/x would be a file's descendant). ---
    context, _, _ = _context()
    spy = SpyCandidatePublisher()
    create_under_alias = "--- /dev/null\n+++ b/src/A.py/x\n@@ -0,0 +1,1 @@\n+x = 2\n"
    outcome = apply_candidate_patch(
        patch_action(context.current.candidate_digest, create_under_alias),
        context.current,
        context.with_publisher(spy),
    )
    assert outcome.error_code == "PATH_EXISTS"
    assert spy.publish_count == 0

    # --- REPLACE on a missing path cannot match any base bytes. ---
    replace_missing = (
        "--- a/src/missing.py\n+++ b/src/missing.py\n@@ -1,1 +1,1 @@\n-x = 1\n+x = 2\n"
    )
    context, _, _ = _context()
    spy = SpyCandidatePublisher()
    outcome = apply_candidate_patch(
        patch_action(context.current.candidate_digest, replace_missing),
        context.current,
        context.with_publisher(spy),
    )
    assert outcome.error_code == "PATCH_CONTEXT_MISMATCH"
    assert spy.publish_count == 0

    # --- CREATE of an ignored path rejects. ---
    ignored_context, _, _ = _context(
        ignore_rules=(
            IgnoreRuleV1(
                schema_version=1,
                source="GITIGNORE",
                base_directory="",
                pattern="*.pyc",
                negated=False,
                directory_only=False,
            ),
        )
    )
    spy = SpyCandidatePublisher()
    create_ignored = "--- /dev/null\n+++ b/src/gen.pyc\n@@ -0,0 +1,1 @@\n+x = 2\n"
    outcome = apply_candidate_patch(
        patch_action(ignored_context.current.candidate_digest, create_ignored),
        ignored_context.current,
        ignored_context.with_publisher(spy),
    )
    assert outcome.error_code == "PATH_IGNORED"
    assert spy.publish_count == 0

    # --- Policy binding drift is a tree-integrity failure. ---
    drifted_context, _, _ = _context(policy_digest="b" * 64)
    spy = SpyCandidatePublisher()
    outcome = apply_candidate_patch(
        patch_action(drifted_context.current.candidate_digest, valid_replace_patch()),
        drifted_context.current,
        drifted_context.with_publisher(spy),
    )
    assert outcome.error_code == "TREE_INTEGRITY_FAILED"
    assert spy.publish_count == 0

    # --- A context snapshot that is not the current candidate's sealed
    # snapshot is a tree-integrity failure. ---
    other_context, other_snapshot, _ = _context()
    mismatched_context = CandidatePatchContextV1(
        current=drifted_context.current,
        snapshot=other_snapshot,
        reference=drifted_context.reference,
        publisher=drifted_context.publisher,
        ignore_rules=drifted_context.ignore_rules,
        ignore_rules_digest=drifted_context.ignore_rules_digest,
    )
    spy = SpyCandidatePublisher()
    outcome = apply_candidate_patch(
        patch_action(drifted_context.current.candidate_digest, valid_replace_patch()),
        drifted_context.current,
        mismatched_context.with_publisher(spy),
    )
    assert outcome.error_code == "TREE_INTEGRITY_FAILED"
    assert spy.publish_count == 0

    # --- REPLACE of a non-text base is an unsupported operation. ---
    binary_context, _, _ = _context(
        (("src/a.py", b"\x00\x01\x02"), ("src/b.py", b"y = 1\n"))
    )
    spy = SpyCandidatePublisher()
    outcome = apply_candidate_patch(
        patch_action(binary_context.current.candidate_digest, valid_replace_patch()),
        binary_context.current,
        binary_context.with_publisher(spy),
    )
    assert outcome.error_code == "UNSUPPORTED_PATCH_OPERATION"
    assert spy.publish_count == 0

    # --- Replacing the BOM line of a BOM file would lose the BOM. ---
    bom_context, _, _ = _context(
        (("src/a.py", b"\xef\xbb\xbfx = 1\n"), ("src/b.py", b"y = 1\n"))
    )
    spy = SpyCandidatePublisher()
    bom_patch = (
        "--- a/src/a.py\n+++ b/src/a.py\n@@ -1,1 +1,1 @@\n-\ufeffx = 1\n+y = 2\n"
    )
    outcome = apply_candidate_patch(
        patch_action(bom_context.current.candidate_digest, bom_patch),
        bom_context.current,
        bom_context.with_publisher(spy),
    )
    assert outcome.error_code == "UNSUPPORTED_PATCH_OPERATION"
    assert spy.publish_count == 0

    # --- A BOM-preserving replacement of a BOM file commits once. ---
    bom_context, _, _ = _context(
        (("src/a.py", b"\xef\xbb\xbfx = 1\n"), ("src/b.py", b"y = 1\n"))
    )
    spy = SpyCandidatePublisher()
    bom_keep_patch = (
        "--- a/src/a.py\n+++ b/src/a.py\n@@ -1,1 +1,1 @@\n-\ufeffx = 1\n+\ufeffx = 2\n"
    )
    outcome = apply_candidate_patch(
        patch_action(bom_context.current.candidate_digest, bom_keep_patch),
        bom_context.current,
        bom_context.with_publisher(spy),
    )
    assert outcome.kind == "PUBLISHED"
    assert spy.publish_count == 1
    assert outcome.revision is not None
    assert (
        outcome.revision.tree.read_bytes(canonical_path("src/a.py"))
        == b"\xef\xbb\xbfx = 2\n"
    )

    # --- A CRLF-base replacement preserves CRLF and commits once. ---
    crlf_context, _, _ = _context(
        (("src/a.py", b"x = 1\r\n"), ("src/b.py", b"y = 1\n"))
    )
    spy = SpyCandidatePublisher()
    outcome = apply_candidate_patch(
        patch_action(crlf_context.current.candidate_digest, valid_replace_patch()),
        crlf_context.current,
        crlf_context.with_publisher(spy),
    )
    assert outcome.kind == "PUBLISHED"
    assert spy.publish_count == 1
    assert outcome.revision is not None
    assert outcome.revision.tree.read_bytes(canonical_path("src/a.py")) == b"x = 2\r\n"

    # --- A CREATE commits once with the new directory and file. ---
    create_context, _, _ = _context()
    spy = SpyCandidatePublisher()
    create_new = "--- /dev/null\n+++ b/src/pkg/new.py\n@@ -0,0 +1,1 @@\n+fresh = 1\n"
    outcome = apply_candidate_patch(
        patch_action(create_context.current.candidate_digest, create_new),
        create_context.current,
        create_context.with_publisher(spy),
    )
    assert outcome.kind == "PUBLISHED"
    assert spy.publish_count == 1
    assert outcome.revision is not None
    assert (
        outcome.revision.tree.read_bytes(canonical_path("src/pkg/new.py"))
        == b"fresh = 1\n"
    )
    assert canonical_path("src/pkg") in outcome.revision.tree.list_directories()

    # --- Cumulative limits: a fourth net-changed file rejects. ---
    context, _, _ = _context()
    busy = derive_candidate_revision(
        context.current,
        (
            stage_replace("src/a.py", b"x = 2\n"),
            stage_replace("src/b.py", b"y = 2\n"),
            stage_replace("README.md", b"readme v2\n"),
        ),
    )
    # The busy revision is the current candidate: the context is
    # re-derived from it (a stale context rejects before the limits).
    busy_context, _, _ = _context(current=busy)
    spy = SpyCandidatePublisher()
    fourth = "--- /dev/null\n+++ b/src/c.py\n@@ -0,0 +1,1 @@\n+z = 1\n"
    outcome = apply_candidate_patch(
        patch_action(busy.candidate_digest, fourth),
        busy,
        busy_context.with_publisher(spy),
    )
    assert outcome.error_code == "PATCH_LIMIT_EXCEEDED"
    assert spy.publish_count == 0

    # --- Cumulative limits: a second new file rejects. ---
    context, _, _ = _context()
    spy = SpyCandidatePublisher()
    two_new = (
        "--- /dev/null\n"
        "+++ b/src/c.py\n"
        "@@ -0,0 +1,1 @@\n"
        "+z = 1\n"
        "\n"
        "--- /dev/null\n"
        "+++ b/src/d.py\n"
        "@@ -0,0 +1,1 @@\n"
        "+z = 2\n"
    )
    outcome = apply_candidate_patch(
        patch_action(context.current.candidate_digest, two_new),
        context.current,
        context.with_publisher(spy),
    )
    assert outcome.error_code == "PATCH_LIMIT_EXCEEDED"
    assert spy.publish_count == 0

    # --- Cumulative byte limit: two ~70 KiB postimages exceed 128 KiB. ---
    big_one = b"x = 0\n" + b"p\n" * 34997  # 70000 bytes
    big_two = b"y = 0\n" + b"p\n" * 34997  # 70000 bytes
    big_context, _, _ = _context((("src/a.py", big_one), ("src/b.py", big_two)))
    spy = SpyCandidatePublisher()
    big_patch = (
        "--- a/src/a.py\n"
        "+++ b/src/a.py\n"
        "@@ -1,1 +1,1 @@\n"
        "-x = 0\n"
        "+x = 1\n"
        "\n"
        "--- a/src/b.py\n"
        "+++ b/src/b.py\n"
        "@@ -1,1 +1,1 @@\n"
        "-y = 0\n"
        "+y = 1\n"
    )
    outcome = apply_candidate_patch(
        patch_action(big_context.current.candidate_digest, big_patch),
        big_context.current,
        big_context.with_publisher(spy),
    )
    assert outcome.error_code == "PATCH_LIMIT_EXCEEDED"
    assert spy.publish_count == 0

    # --- Single-file limit: a postimage above 128 KiB rejects. ---
    huge = b"x = 0\n" + b"p\n" * 74997  # 150000 bytes
    huge_context, _, _ = _context((("src/a.py", huge),))
    spy = SpyCandidatePublisher()
    huge_patch = "--- a/src/a.py\n+++ b/src/a.py\n@@ -1,1 +1,1 @@\n-x = 0\n+x = 1\n"
    outcome = apply_candidate_patch(
        patch_action(huge_context.current.candidate_digest, huge_patch),
        huge_context.current,
        huge_context.with_publisher(spy),
    )
    assert outcome.error_code == "PATCH_LIMIT_EXCEEDED"
    assert spy.publish_count == 0


def test_patch_engine_rejects_an_illegal_entry_in_every_entry_position() -> None:
    """The first failing entry determines the deterministic rejection."""
    for index in range(2):
        first = valid_replace_patch()
        second = (
            "--- a/README.md\n+++ b/README.md\n@@ -1,1 +1,1 @@\n-readme\n+readme v2\n"
        )
        entries = (first, second) if index == 0 else (second, first)
        patch_text = "\n".join([entries[0], entries[1]])
        context, _, _ = _context()
        spy = SpyCandidatePublisher()
        outcome = apply_candidate_patch(
            patch_action(context.current.candidate_digest, patch_text),
            context.current,
            context.with_publisher(spy),
        )
        assert outcome.kind == "REJECTED"
        assert outcome.error_code == "PATCH_PATH_NOT_EDITABLE"
        assert spy.publish_count == 0
        assert context.current.tree.read_bytes(canonical_path("src/a.py")) == b"x = 1\n"


def test_patch_engine_rejects_a_misdeclared_new_side_start() -> None:
    """A hunk whose new-side start does not match the actual postimage
    position never applies: the patch claims a position it does not
    produce."""
    context, _, _ = _context()
    forged = (
        "--- a/src/a.py\n"
        "+++ b/src/a.py\n"
        "@@ -1,1 +99,1 @@\n"
        "-x = 1\n"
        "+x = 2\n"
    )
    outcome = apply_candidate_patch(
        patch_action(context.current.candidate_digest, forged),
        context.current,
        context.with_publisher(SpyCandidatePublisher()),
    )
    assert outcome.error_code == "PATCH_CONTEXT_MISMATCH"
    # A forged zero-count new position is rejected the same way.
    forged_zero = (
        "--- a/src/a.py\n"
        "+++ b/src/a.py\n"
        "@@ -1 +99,0 @@\n"
        "-x = 1\n"
    )
    zero_outcome = apply_candidate_patch(
        patch_action(context.current.candidate_digest, forged_zero),
        context.current,
        context.with_publisher(SpyCandidatePublisher()),
    )
    assert zero_outcome.error_code == "PATCH_CONTEXT_MISMATCH"


def test_patch_engine_applies_git_standard_pure_deletion_hunks() -> None:
    """Zero-count new ranges use git's 0-based deletion-point convention:
    deleting a file's first, middle, or last line applies exactly."""
    context, _, _ = _context(
        (("src/a.py", b"line1\nline2\nline3\n"), ("src/b.py", b"y = 1\n"))
    )
    cases = (
        (
            "--- a/src/a.py\n+++ b/src/a.py\n@@ -1 +0,0 @@\n-line1\n",
            b"line2\nline3\n",
        ),
        (
            "--- a/src/a.py\n+++ b/src/a.py\n@@ -2 +1,0 @@\n-line2\n",
            b"line1\nline3\n",
        ),
        (
            "--- a/src/a.py\n+++ b/src/a.py\n@@ -3 +2,0 @@\n-line3\n",
            b"line1\nline2\n",
        ),
    )
    for patch_text, expected in cases:
        spy = SpyCandidatePublisher()
        outcome = apply_candidate_patch(
            patch_action(context.current.candidate_digest, patch_text),
            context.current,
            context.with_publisher(spy),
        )
        assert outcome.kind == "PUBLISHED", (patch_text, outcome)
        assert outcome.revision is not None
        assert (
            outcome.revision.tree.read_bytes(canonical_path("src/a.py")) == expected
        )
        assert spy.publish_count == 1


def test_apply_rejects_a_context_current_that_differs_from_the_named_candidate() -> None:
    """The frozen context's ``current`` must be the exact named candidate:
    a mismatched context current rejects before any path or publish."""
    context, _, _ = _context()
    other_context, _, _ = _context((("src/a.py", b"x = 9\n"),))
    outcome = apply_candidate_patch(
        patch_action(context.current.candidate_digest, valid_replace_patch()),
        context.current,
        other_context.with_publisher(SpyCandidatePublisher()),
    )
    assert outcome.error_code == "STALE_CANDIDATE"


def test_patch_path_fact_for_action_derives_the_deterministic_fact() -> None:
    """The pre-policy fact is derived from the action and the frozen
    context, never taken from a caller-supplied value."""
    context, _, _ = _context()
    assert (
        patch_path_fact_for_action(
            patch_action(context.current.candidate_digest, valid_replace_patch()),
            context.current,
            context,
        )
        == "OK"
    )
    # A non-editable path yields its stable pre-policy fact.
    assert (
        patch_path_fact_for_action(
            patch_action(
                context.current.candidate_digest, replace_src_a_and_readme_patch()
            ),
            context.current,
            context,
        )
        == "PATCH_PATH_NOT_EDITABLE"
    )
    # An unparseable patch fails closed as a tree-integrity fact.
    assert (
        patch_path_fact_for_action(
            patch_action(context.current.candidate_digest, "not a diff"),
            context.current,
            context,
        )
        == "TREE_INTEGRITY_FAILED"
    )


def test_patch_engine_matches_hunks_exactly_across_multiple_hunks() -> None:
    """Two chained hunks apply exactly; a drifted second hunk rejects."""
    context, _, _ = _context(
        (("src/a.py", b"x = 1\ny = 2\nz = 3\n"), ("src/b.py", b"y = 1\n"))
    )
    spy = SpyCandidatePublisher()
    two_hunks = (
        "--- a/src/a.py\n"
        "+++ b/src/a.py\n"
        "@@ -1,1 +1,1 @@\n"
        "-x = 1\n"
        "+x = 10\n"
        "@@ -3,1 +3,1 @@\n"
        "-z = 3\n"
        "+z = 30\n"
    )
    outcome = apply_candidate_patch(
        patch_action(context.current.candidate_digest, two_hunks),
        context.current,
        context.with_publisher(spy),
    )
    assert outcome.kind == "PUBLISHED"
    assert spy.publish_count == 1
    assert outcome.revision is not None
    assert (
        outcome.revision.tree.read_bytes(canonical_path("src/a.py"))
        == b"x = 10\ny = 2\nz = 30\n"
    )


def test_apply_candidate_patch_action_schema_is_closed() -> None:
    """The action envelope rejects unknown, missing, and type-confused
    fields and the SPEC §4.2.2 bounds (patch_format literal, <=128 KiB
    UTF-8 patch text, 64-hex base digest)."""
    invalid: tuple[dict[str, object], ...] = (
        {
            "schema_version": 1,
            "action_type": "apply_candidate_patch",
            "base_candidate_digest": "0" * 64,
            "patch_format": "GNU_DIFF_V1",
            "patch_text": "--- a/src/a.py\n",
        },
        {
            "schema_version": 1,
            "action_type": "apply_candidate_patch",
            "base_candidate_digest": "not-a-digest",
            "patch_format": "UNIFIED_DIFF_V1",
            "patch_text": "--- a/src/a.py\n",
        },
        {
            "schema_version": 1,
            "action_type": "apply_candidate_patch",
            "base_candidate_digest": "0" * 64,
            "patch_format": "UNIFIED_DIFF_V1",
            "patch_text": "x" * 131073,
        },
        {
            "schema_version": 1,
            "action_type": "list_files",
            "base_candidate_digest": "0" * 64,
            "patch_format": "UNIFIED_DIFF_V1",
            "patch_text": "--- a/src/a.py\n",
        },
        {
            "schema_version": 1,
            "base_candidate_digest": "0" * 64,
            "patch_format": "UNIFIED_DIFF_V1",
            "patch_text": "--- a/src/a.py\n",
        },
        {
            "schema_version": "1",
            "action_type": "apply_candidate_patch",
            "base_candidate_digest": "0" * 64,
            "patch_format": "UNIFIED_DIFF_V1",
            "patch_text": "--- a/src/a.py\n",
        },
        {
            "schema_version": 1,
            "action_type": "apply_candidate_patch",
            "base_candidate_digest": "0" * 64,
            "patch_format": "UNIFIED_DIFF_V1",
            "patch_text": "--- a/src/a.py\n",
            "extra": 1,
        },
        {
            "schema_version": 1,
            "action_type": "apply_candidate_patch",
            "base_candidate_digest": "0" * 64,
            "patch_format": "UNIFIED_DIFF_V1",
            "patch_text": "\ud800",
        },
    )
    for payload in invalid:
        with pytest.raises(ValidationError):
            ApplyCandidatePatchAction.model_validate(payload)
    # A lone surrogate patch text cannot be UTF-8 encoded.
    with pytest.raises(ValidationError):
        ApplyCandidatePatchAction.model_validate(
            {
                "schema_version": 1,
                "action_type": "apply_candidate_patch",
                "base_candidate_digest": "0" * 64,
                "patch_format": "UNIFIED_DIFF_V1",
                "patch_text": "--- a/src/a.py\n\ud800",
            }
        )


def test_candidate_patch_outcome_schema_is_closed() -> None:
    """PUBLISHED requires the revision and digest; REJECTED requires the
    stable code and reason; contradictions reject before publication."""
    invalid: tuple[dict[str, object], ...] = (
        {"kind": "PUBLISHED"},
        {"kind": "REJECTED"},
        {"kind": "PUBLISHED", "error_code": "X", "reason": "y"},
        {"kind": "REJECTED", "error_code": "X"},
        {"kind": "MAYBE", "error_code": "X", "reason": "y"},
    )
    for payload in invalid:
        with pytest.raises(ValidationError):
            CandidatePatchOutcomeV1.model_validate(payload)


def test_candidate_patch_context_is_frozen_and_publisher_switchable() -> None:
    context, _, _ = _context()
    spy = SpyCandidatePublisher()
    switched = context.with_publisher(spy)
    assert switched.publisher is spy
    assert context.publisher is not spy
    assert switched.current is context.current
    assert switched.snapshot is context.snapshot
    assert switched.reference is context.reference
    # Sealed ignore facts must match their digest.
    with pytest.raises(ValueError):
        CandidatePatchContextV1(
            current=context.current,
            snapshot=context.snapshot,
            reference=context.reference,
            publisher=spy,
            ignore_rules=(),
            ignore_rules_digest="0" * 64,
        )

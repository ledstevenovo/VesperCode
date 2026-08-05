"""T10.2 legacy step 10.C (Windows): real sealed-preflight Snapshot parity.

Runs only under ``-m windows_integration`` on the project Windows host.
Proves ``create_snapshot`` against a real Git repository: the exact
SUPPORTED sealed preflight plus the frozen path-to-content-identity table
builds one immutable deterministic ``SnapshotTreeV1`` that structurally
satisfies ``ReadableTreeV1``, exposes identical ``digest``/``root_digest``,
and returns deterministic directory/file paths and exact bytes, while
every preflight-identity, object-digest, path-order, and protected-input
drift rejects creation (registry row 10.C).  The disposable repository is
deleted in teardown.
"""

from __future__ import annotations

import os
import shutil
import stat
import subprocess
import tempfile
from collections.abc import Iterator
from pathlib import Path
from typing import Final

import pytest

from src.vespercode.canonical.path_v1 import CanonicalRelativePathV1
from src.vespercode.profiles.registry import build_profile_registry
from src.vespercode.trees.content_store import ContentObjectStore
from src.vespercode.trees.readable import ReadableTreeV1
from src.vespercode.contracts.optional import PresentV1
from src.vespercode.trees.snapshot import (
    AcceptedGitPreflightV1,
    SealedSnapshotInputFileV1,
    SnapshotFileEntryV1,
    SnapshotIntegrityError,
    SnapshotTreeV1,
    SupportedTextClassifierV1,
    create_snapshot,
    verify_snapshot,
)
from src.vespercode.trees.text_classifier import classify_supported_text
from src.vespercode.workspace.git_preflight import (
    GitPreflightResultV1,
    run_git_snapshot_prechecks,
)
from src.vespercode.workspace.identity_win32 import resolve_workspace_identity

pytestmark = pytest.mark.windows_integration

_GIT_BASE_ARGS: Final = (
    "-c",
    "core.quotepath=false",
    "--no-pager",
    "--no-optional-locks",
)


def test_snapshot_rejects_preflight_object_identity_drift() -> None:
    with pytest.raises(SnapshotIntegrityError, match="PREFLIGHT_OBJECT_DRIFT"):
        create_snapshot(drifted_preflight(), store(), classifier())


def classifier() -> SupportedTextClassifierV1:
    """One pure shared Task 10.B supported-text classifier."""
    return classify_supported_text


def store() -> ContentObjectStore:
    """One fresh empty content object store."""
    return ContentObjectStore()


def drifted_preflight() -> AcceptedGitPreflightV1:
    """One accepted sealed preflight whose single sealed object identity is
    not backed by a fresh store: the smallest sealed-identity mismatch."""
    return AcceptedGitPreflightV1(
        schema_version=1,
        preflight=_supported_seal(tracked_file_count=1, tracked_byte_count=6),
        files=(
            SealedSnapshotInputFileV1(
                schema_version=1,
                path=CanonicalRelativePathV1("src/a.py"),
                content_sha256="a" * 64,
                byte_count=6,
            ),
        ),
    )


def _supported_seal(
    *, tracked_file_count: int, tracked_byte_count: int
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
        repository_policy_digest="6" * 64,
        ignore_rules=(),
        tracked_file_count=tracked_file_count,
        tracked_byte_count=tracked_byte_count,
    )


def _git_env(home: str) -> dict[str, str]:
    return {
        "PATH": os.environ.get("PATH", ""),
        "SYSTEMROOT": os.environ.get("SYSTEMROOT", ""),
        "TEMP": os.environ.get("TEMP", home),
        "TMP": os.environ.get("TMP", home),
        "HOME": home,
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CONFIG_GLOBAL": "",
        "GIT_CONFIG_SYSTEM": "",
        "GIT_TERMINAL_PROMPT": "0",
        "LC_ALL": "C",
        "LANG": "C",
    }


def _force_rmtree(root: Path) -> None:
    """Delete one repository tree including git's read-only loose objects."""
    for path in root.rglob("*"):
        if path.is_file():
            os.chmod(path, stat.S_IWRITE)
    shutil.rmtree(root, ignore_errors=True)


class _SealedRealRepo:
    """One real repository with a real handle-derived identity.

    The fixture plays the Run-coordinator role: after the SUPPORTED seal
    proves the tracked worktree bytes equal their HEAD blobs, it reads
    those verified bytes once, stores them in the Task 10.A store, and
    freezes the path-to-content-identity table (SPEC §4.1 behavior 9
    "已验证的 tracked 工作区原始字节"); Snapshot construction itself
    never rereads the workspace.
    """

    def __init__(self, root: Path) -> None:
        self.root = root
        self._home = root / ".git-home"
        self._home.mkdir(exist_ok=True)
        self.git("init", "-q")
        (root / "src").mkdir()
        (root / "src" / "a.py").write_text("def a():\n    return 1\n", encoding="utf-8")
        (root / "src" / "b.py").write_text("# b\nvalue = 2\n", encoding="utf-8")
        (root / "pyproject.toml").write_text(
            '[project]\nname = "integration"\n', encoding="utf-8"
        )
        (root / "requirements.lock").write_text("pytest==8.4.2\n", encoding="utf-8")
        (root / "README.md").write_text("snapshot fixture\n", encoding="utf-8")
        (root / ".gitignore").write_text(".git-home/\n", encoding="utf-8")
        self.git("add", ".")
        self.git(
            "-c",
            "user.name=Fixture",
            "-c",
            "user.email=fixture@example.com",
            "commit",
            "-q",
            "-m",
            "initial",
        )
        self.identity = resolve_workspace_identity(root)
        self.reference_manifest = build_profile_registry().resolve_reference(
            "python-src-py312-v1"
        )

    def git(self, *args: str) -> None:
        completed = subprocess.run(
            ["git", *_GIT_BASE_ARGS, *args],
            cwd=self.root,
            env=_git_env(str(self._home)),
            capture_output=True,
            text=True,
            check=False,
        )
        assert completed.returncode == 0, completed.stderr

    def tracked_files(self) -> list[tuple[str, bytes]]:
        """The tracked worktree paths and their verified raw bytes."""
        completed = subprocess.run(
            ["git", *_GIT_BASE_ARGS, "ls-files"],
            cwd=self.root,
            env=_git_env(str(self._home)),
            capture_output=True,
            text=True,
            check=False,
        )
        assert completed.returncode == 0, completed.stderr
        rows: list[tuple[str, bytes]] = []
        for line in completed.stdout.splitlines():
            path = line.strip()
            if path:
                rows.append((path, (self.root / path).read_bytes()))
        return rows


@pytest.fixture
def sealed_real_repo() -> Iterator[_SealedRealRepo]:
    root = Path(tempfile.mkdtemp(prefix="vesper_snapshot_real_"))
    try:
        yield _SealedRealRepo(root)
    finally:
        _force_rmtree(root)
        assert not root.exists(), "repository residue remains"


def test_snapshot_integrity_matrix(sealed_real_repo: _SealedRealRepo) -> None:
    """Registry row 10.C: the exact §5.1 sealed Snapshot matrix.

    Exact sealed preflight inputs build one immutable deterministic
    Snapshot that structurally satisfies ``ReadableTreeV1``, exposes
    identical ``digest``/``root_digest``, and returns deterministic
    directory/file paths and exact bytes; preflight identity, object
    digest, path order, and protected-input drift each reject creation.
    """
    supported = run_git_snapshot_prechecks(
        sealed_real_repo.identity, sealed_real_repo.reference_manifest
    )
    assert supported.kind == "SUPPORTED"
    store = ContentObjectStore()
    rows: list[tuple[str, str, int]] = []
    for path, raw in sealed_real_repo.tracked_files():
        ref = store.put(raw)
        rows.append((path, ref.sha256, ref.byte_count))
    accepted = _accepted_from(supported, rows)

    # Exact inputs: one immutable deterministic Snapshot.
    snapshot = create_snapshot(accepted, store, classifier())
    assert isinstance(snapshot, SnapshotTreeV1)
    assert isinstance(snapshot, ReadableTreeV1)
    assert snapshot.digest == snapshot.root_digest
    paths = [path for path, _, _ in rows]
    assert snapshot.list_file_paths() == tuple(
        sorted(
            (CanonicalRelativePathV1(path) for path in paths),
            key=lambda path: path.value,
        )
    )
    assert snapshot.list_directories() == (CanonicalRelativePathV1("src"),)
    for path, raw in sealed_real_repo.tracked_files():
        assert snapshot.read_bytes(CanonicalRelativePathV1(path)) == raw
    again = create_snapshot(accepted, store, classifier())
    assert again == snapshot
    assert again.root_digest == snapshot.root_digest
    assert verify_snapshot(snapshot, store).status == "INTACT"

    # Preflight identity drift: the sealed count does not bind the table.
    dropped = _accepted_from(supported, rows[:-1])
    with pytest.raises(SnapshotIntegrityError, match="PREFLIGHT_COUNT_DRIFT"):
        create_snapshot(dropped, store, classifier())
    # Preflight identity drift: the sealed byte total does not bind the table.
    tampered_bytes = list(rows)
    path, sha, count = tampered_bytes[0]
    tampered_bytes[0] = (path, sha, count + 1)
    with pytest.raises(SnapshotIntegrityError, match="PREFLIGHT_BYTES_DRIFT"):
        create_snapshot(_accepted_from(supported, tampered_bytes), store, classifier())
    # Object digest drift: a corrupted store object rejects creation.
    corrupt_store = ContentObjectStore()
    for path, raw in sealed_real_repo.tracked_files():
        ref = corrupt_store.put(raw)
        if path == paths[0]:
            corrupt_store.inject_corruption(ref, b"tampered bytes\n")
    with pytest.raises(SnapshotIntegrityError, match="PREFLIGHT_OBJECT_DRIFT"):
        create_snapshot(accepted, corrupt_store, classifier())
    # Path order drift: an unsorted table rejects creation.
    unsorted = list(reversed(rows))
    with pytest.raises(SnapshotIntegrityError, match="PATH_ORDER_DRIFT"):
        create_snapshot(_accepted_from(supported, unsorted), store, classifier())
    # Protected-input drift: a sensitive path a real seal could never contain.
    # The replacement keeps the sealed count and byte total binding so the
    # protected-input check is the first (and only) failure.
    sensitive = list(rows)
    original_path, sha, count = sensitive[0]
    sensitive[0] = (".env", sha, count)
    assert original_path != ".env"
    with pytest.raises(SnapshotIntegrityError, match="PROTECTED_INPUT_DRIFT"):
        create_snapshot(_accepted_from(supported, sensitive), store, classifier())


def test_snapshot_from_real_preflight_binds_policy_and_text_metadata(
    sealed_real_repo: _SealedRealRepo,
) -> None:
    """The sealed policy digest and Task 10.B text metadata survive exactly."""
    supported = run_git_snapshot_prechecks(
        sealed_real_repo.identity, sealed_real_repo.reference_manifest
    )
    assert supported.kind == "SUPPORTED"
    store = ContentObjectStore()
    rows: list[tuple[str, str, int]] = []
    for path, raw in sealed_real_repo.tracked_files():
        ref = store.put(raw)
        rows.append((path, ref.sha256, ref.byte_count))
    snapshot = create_snapshot(_accepted_from(supported, rows), store, classifier())
    assert snapshot.repository_policy_digest == (
        sealed_real_repo.reference_manifest.editable_path_policy.digest
    )
    for entry in snapshot.entries:
        if not isinstance(entry, SnapshotFileEntryV1):
            continue
        if not isinstance(entry.text_profile, PresentV1):
            continue
        metadata = entry.text_profile.value
        assert metadata.encoding in ("UTF8", "UTF8_BOM")
        # The fixture's text-mode write translates LF to CRLF on Windows;
        # uniform CRLF is supported text, and the exact classification of
        # the sealed bytes is what the tree must bind.
        assert metadata.newline in ("LF", "CRLF")
        assert metadata.final_newline is True
        assert entry.size_bytes == entry.content_ref.byte_count
    assert verify_snapshot(snapshot, store).status == "INTACT"


def _accepted_from(
    supported: GitPreflightResultV1, rows: list[tuple[str, str, int]]
) -> AcceptedGitPreflightV1:
    """One accepted preflight from a real SUPPORTED seal and a real table."""
    return AcceptedGitPreflightV1(
        schema_version=1,
        preflight=supported,
        files=tuple(
            SealedSnapshotInputFileV1(
                schema_version=1,
                path=CanonicalRelativePathV1(path),
                content_sha256=sha,
                byte_count=count,
            )
            for path, sha, count in rows
        ),
    )

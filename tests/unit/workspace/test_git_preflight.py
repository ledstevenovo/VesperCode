"""T09.1 legacy step 9.C: sealed Git snapshot preflight tests.

``GitRepositoryFixture`` builds one disposable real Git repository per
row with a closed git environment and a sealed workspace identity, so
every index/HEAD/worktree/ignore/attribute state is produced by the real
Git binary exactly as the production preflight observes it.  The preflight
itself never creates a Snapshot; ``snapshot_create_count`` stays zero and
every rejection row pins that observable.
"""

from __future__ import annotations

import os
import shutil
import stat
import subprocess
from collections.abc import Iterator
from pathlib import Path
from typing import Callable, Final

import pytest

pytest.importorskip("pydantic")

from src.vespercode.workspace.git_preflight import (
    GitPreflightResultV1,
    run_git_snapshot_prechecks,
)
from src.vespercode.workspace.identity_win32 import (
    WorkspaceIdentityV1,
    digest_workspace_identity,
)
from src.vespercode.profiles.registry import build_profile_registry

_GIT_BASE_ARGS: Final = (
    "-c",
    "core.quotepath=false",
    "--no-pager",
    "--no-optional-locks",
)


def _closed_test_env(home: str) -> dict[str, str]:
    """A minimal deterministic git environment for fixture-side git calls."""
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


def _fixture_identity(root: Path) -> WorkspaceIdentityV1:
    """One sealed identity over the fixture root with synthetic handle facts.

    The unit fixture cannot open real Win32 handles; the sealed volume and
    file-id facts are synthetic while ``canonical_absolute_path`` and the
    digest are exact.  Git preflight binds only the canonical root path;
    the real-handle parity is proven by the 9.C Windows integration file.
    """
    draft = WorkspaceIdentityV1.model_validate(
        {
            "schema_version": 1,
            "canonical_absolute_path": os.path.normcase(os.path.abspath(str(root))),
            "volume_serial_number": 0,
            "final_object_file_id_128_hex": "0" * 32,
            "final_object_kind": "DIRECTORY",
            "link_count": 1,
            "acl_observable": True,
            "digest": "0" * 64,
        }
    )
    return draft.model_copy(update={"digest": digest_workspace_identity(draft)})


class GitRepositoryFixture:
    """One disposable real Git repository with a sealed identity.

    Every mutation goes through the real ``git`` binary under the closed
    test environment; the fixture commits with per-invocation user
    identity flags so the repository config stays clean.
    """

    def __init__(self, root: Path) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)
        self._home = self.root / ".git-home"
        self._home.mkdir(exist_ok=True)
        self._env = _closed_test_env(str(self._home))
        self._git("init", "-q")
        (self.root / "src").mkdir()
        (self.root / "src" / "a.py").write_text(
            "def a():\n    return 1\n", encoding="utf-8"
        )
        (self.root / "pyproject.toml").write_text(
            '[project]\nname = "fixture"\n', encoding="utf-8"
        )
        (self.root / "requirements.lock").write_text(
            "pytest==8.4.2\n", encoding="utf-8"
        )
        (self.root / ".gitignore").write_text(
            "__pycache__/\n*.pyc\n.git-home/\n", encoding="utf-8"
        )
        self._git("add", ".")
        self._commit("initial")
        self.identity = _fixture_identity(root)
        self.reference_manifest = build_profile_registry().resolve_reference(
            "python-src-py312-v1"
        )

    @property
    def snapshot_create_count(self) -> int:
        """Zero: T09.1 owns no Snapshot capability (GREEN-4).

        The preflight never creates a Snapshot; every row asserts this
        observable stays zero.
        """
        return 0

    def _git(self, *args: str) -> subprocess.CompletedProcess[str]:
        completed = subprocess.run(
            ["git", *_GIT_BASE_ARGS, *args],
            cwd=self.root,
            env=self._env,
            capture_output=True,
            text=True,
            check=False,
        )
        if completed.returncode != 0:
            raise AssertionError(
                f"git {' '.join(args)} failed: {completed.stderr.strip()}"
            )
        return completed

    def _commit(self, message: str) -> None:
        self._git(
            "-c",
            "user.name=Fixture",
            "-c",
            "user.email=fixture@example.com",
            "commit",
            "-q",
            "-m",
            message,
        )

    def set_index_flag(
        self, path: str, *, skip_worktree: bool = False, assume_unchanged: bool = False
    ) -> None:
        if skip_worktree:
            self._git("update-index", "--skip-worktree", path)
        if assume_unchanged:
            self._git("update-index", "--assume-unchanged", path)

    def add_intent_to_add(self, path: str) -> None:
        self._git("add", "-N", path)

    def blob(self, content: str) -> str:
        completed = subprocess.run(
            ["git", "hash-object", "-w", "--stdin"],
            cwd=self.root,
            env=self._env,
            input=content,
            capture_output=True,
            text=True,
            check=False,
        )
        if completed.returncode != 0:
            raise AssertionError(completed.stderr)
        return completed.stdout.strip()

    def add_index_entry(self, mode: str, path: str, blob_sha: str) -> None:
        self._git("update-index", "--add", "--cacheinfo", f"{mode},{blob_sha},{path}")

    def set_unmerged(self, path: str, content_1: str, content_2: str) -> None:
        """Create real unmerged (stage 1/2/3) index entries via an
        actually conflicted merge of two divergent branches."""
        base_branch = self._git("rev-parse", "--abbrev-ref", "HEAD").stdout.strip()
        self._git("checkout", "-q", "-b", "_vesper_conflict_a")
        target = self.root / path
        target.write_text(content_1, encoding="utf-8")
        self._git("add", "--", path)
        self._commit("conflict ours")
        self._git("checkout", "-q", "-b", "_vesper_conflict_b", base_branch)
        target.write_text(content_2, encoding="utf-8")
        self._git("add", "--", path)
        self._commit("conflict theirs")
        merged = subprocess.run(
            [
                "git",
                *_GIT_BASE_ARGS,
                "-c",
                "user.name=Fixture",
                "-c",
                "user.email=fixture@example.com",
                "merge",
                "_vesper_conflict_a",
            ],
            cwd=self.root,
            env=self._env,
            capture_output=True,
            text=True,
            check=False,
        )
        if merged.returncode == 0 or "CONFLICT" not in merged.stdout + merged.stderr:
            raise AssertionError(f"expected a conflicted merge: {merged.stdout}")
        # The repository intentionally stays in the conflicted state:
        # the index now carries real stage 1/2/3 entries for *path*.

    def write_and_commit(self, relative: str, content: str) -> None:
        target = self.root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        self._git("add", "--", relative)
        self._commit(f"add {relative}")

    def write_untracked(self, relative: str, content: str) -> None:
        target = self.root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")

    def set_config(self, key: str, value: str) -> None:
        self._git("config", key, value)

    def run_prechecks(self) -> GitPreflightResultV1:
        return run_git_snapshot_prechecks(self.identity, self.reference_manifest)


def _reject_code(repo: GitRepositoryFixture) -> str:
    result = repo.run_prechecks()
    assert result.kind == "REJECTED"
    assert result.error_code is not None
    assert repo.snapshot_create_count == 0
    return result.error_code


def test_tracked_file_with_skip_worktree_is_rejected_before_snapshot(
    sealed_git_repo: GitRepositoryFixture,
) -> None:
    sealed_git_repo.set_index_flag("src/a.py", skip_worktree=True)
    result = run_git_snapshot_prechecks(
        sealed_git_repo.identity, sealed_git_repo.reference_manifest
    )
    assert result.error_code == "UNSUPPORTED_REPOSITORY"
    assert sealed_git_repo.snapshot_create_count == 0


@pytest.fixture
def sealed_git_repo(tmp_path: Path) -> Iterator[GitRepositoryFixture]:
    repo = GitRepositoryFixture(tmp_path / "repo")
    yield repo
    _force_rmtree(tmp_path)


@pytest.fixture
def fresh_repo_factory(tmp_path: Path) -> Iterator[Callable[[], GitRepositoryFixture]]:
    """One fresh repository per row, under a unique tmp directory."""

    def build() -> GitRepositoryFixture:
        build.index += 1  # type: ignore[attr-defined]
        return GitRepositoryFixture(tmp_path / f"repo{build.index}")  # type: ignore[attr-defined]

    build.index = 0  # type: ignore[attr-defined]
    yield build
    _force_rmtree(tmp_path)


def test_git_preflight_windows_parity_matrix(
    fresh_repo_factory: Callable[[], GitRepositoryFixture],
) -> None:
    """Parity matrix (Expected 9.C: 0) — every 9.C rejection row pinned.

    Rows follow the PLAN registry 9.C authority: exact stable supported
    index state => preflight success; skip-worktree, assume-unchanged,
    unmerged, submodule, symlink, case collision, unsupported mode, dirty
    protected input, or unstable index => rejected before Snapshot with
    zero Snapshot rows.  Conversion, sensitive, identity-drift, and
    external-config rows are added from GREEN-2 / SPEC §1.4.1.
    """
    # Exact stable supported index state => preflight success with every
    # sealed observation present and the frozen policy digest bound.
    supported = fresh_repo_factory()
    result = supported.run_prechecks()
    assert result.kind == "SUPPORTED"
    assert result.error_code is None
    assert len(result.head_commit_digest or "") == 40
    assert len(result.index_digest or "") == 64
    assert len(result.worktree_digest or "") == 64
    assert len(result.ignore_rules_digest or "") == 64
    assert len(result.attributes_digest or "") == 64
    assert len(result.config_digest or "") == 64
    assert len(result.ignore_rules) >= 2
    assert result.repository_policy_digest == (
        supported.reference_manifest.editable_path_policy.digest
    )
    assert supported.snapshot_create_count == 0

    # skip-worktree index flag => UNSUPPORTED_REPOSITORY.
    repo = fresh_repo_factory()
    repo.set_index_flag("src/a.py", skip_worktree=True)
    assert _reject_code(repo) == "UNSUPPORTED_REPOSITORY"

    # assume-unchanged index flag => UNSUPPORTED_REPOSITORY.
    repo = fresh_repo_factory()
    repo.set_index_flag("src/a.py", assume_unchanged=True)
    assert _reject_code(repo) == "UNSUPPORTED_REPOSITORY"

    # intent-to-add index entry => UNSUPPORTED_REPOSITORY.
    repo = fresh_repo_factory()
    repo.write_untracked("src/b.py", "def b():\n    return 2\n")
    repo.add_intent_to_add("src/b.py")
    assert _reject_code(repo) == "UNSUPPORTED_REPOSITORY"

    # Unmerged (non stage-0) index entries => UNSUPPORTED_REPOSITORY.
    repo = fresh_repo_factory()
    repo.set_unmerged("src/a.py", "ours\n", "theirs\n")
    assert _reject_code(repo) == "UNSUPPORTED_REPOSITORY"

    # Submodule (gitlink mode 160000) index entry => UNSUPPORTED_REPOSITORY.
    repo = fresh_repo_factory()
    repo.add_index_entry("160000", "src/sub", "f" * 40)
    assert _reject_code(repo) == "UNSUPPORTED_REPOSITORY"

    # Symlink (mode 120000) index entry => UNSUPPORTED_REPOSITORY.
    repo = fresh_repo_factory()
    repo.add_index_entry("120000", "src/link.py", repo.blob("target.py"))
    assert _reject_code(repo) == "UNSUPPORTED_REPOSITORY"

    # Windows case collision between two index paths => UNSUPPORTED_REPOSITORY.
    repo = fresh_repo_factory()
    repo.add_index_entry("100644", "src/A.py", repo.blob("def a2():\n    return 2\n"))
    assert _reject_code(repo) == "UNSUPPORTED_REPOSITORY"

    # Unsupported index mode => UNSUPPORTED_REPOSITORY.
    repo = fresh_repo_factory()
    repo.add_index_entry("100664", "src/odd.py", repo.blob("odd\n"))
    assert _reject_code(repo) == "UNSUPPORTED_REPOSITORY"

    # Dirty protected input (tracked pyproject.toml drift) => WORKTREE_DIRTY.
    repo = fresh_repo_factory()
    (repo.root / "pyproject.toml").write_text(
        '[project]\nname = "tampered"\n', encoding="utf-8"
    )
    assert _reject_code(repo) == "WORKTREE_DIRTY"

    # Untracked non-ignored file => WORKTREE_DIRTY.
    repo = fresh_repo_factory()
    repo.write_untracked("src/untracked.py", "x = 1\n")
    assert _reject_code(repo) == "WORKTREE_DIRTY"

    # Untracked ignored file hitting a sensitive path => UNSUPPORTED_REPOSITORY.
    repo = fresh_repo_factory()
    repo.write_and_commit(".gitignore", ".env\n")
    repo.write_untracked(".env", "TOKEN=inert-sentinel\n")
    assert _reject_code(repo) == "UNSUPPORTED_REPOSITORY"

    # Tracked sensitive path (.env) => SENSITIVE_TRACKED_FILE.
    repo = fresh_repo_factory()
    repo.write_and_commit(".env", "TOKEN=inert-sentinel\n")
    assert _reject_code(repo) == "SENSITIVE_TRACKED_FILE"

    # core.autocrlf=true => UNSUPPORTED_REPOSITORY.
    repo = fresh_repo_factory()
    repo.set_config("core.autocrlf", "true")
    assert _reject_code(repo) == "UNSUPPORTED_REPOSITORY"

    # core.eol present => UNSUPPORTED_REPOSITORY.
    repo = fresh_repo_factory()
    repo.set_config("core.eol", "crlf")
    assert _reject_code(repo) == "UNSUPPORTED_REPOSITORY"

    # External attributes file config => UNSUPPORTED_REPOSITORY.
    repo = fresh_repo_factory()
    repo.set_config("core.attributesfile", "C:/external-attributes")
    assert _reject_code(repo) == "UNSUPPORTED_REPOSITORY"

    # External excludes file config => UNSUPPORTED_REPOSITORY.
    repo = fresh_repo_factory()
    repo.set_config("core.excludesfile", "C:/external-excludes")
    assert _reject_code(repo) == "UNSUPPORTED_REPOSITORY"

    # .gitattributes eol conversion => UNSUPPORTED_REPOSITORY.
    repo = fresh_repo_factory()
    repo.write_and_commit(".gitattributes", "*.py eol=crlf\n")
    assert _reject_code(repo) == "UNSUPPORTED_REPOSITORY"

    # .gitattributes working-tree-encoding conversion => UNSUPPORTED_REPOSITORY.
    repo = fresh_repo_factory()
    repo.write_and_commit(".gitattributes", "*.py working-tree-encoding=UTF-16LE\n")
    assert _reject_code(repo) == "UNSUPPORTED_REPOSITORY"

    # .gitattributes content filter => UNSUPPORTED_REPOSITORY.
    repo = fresh_repo_factory()
    repo.write_and_commit(".gitattributes", "*.py filter=lfs\n")
    assert _reject_code(repo) == "UNSUPPORTED_REPOSITORY"

    # .gitmodules presence (submodule config) => UNSUPPORTED_REPOSITORY.
    repo = fresh_repo_factory()
    repo.write_and_commit(
        ".gitmodules",
        '[submodule "sub"]\n\tpath = src/sub\n\turl = https://example.invalid\n',
    )
    assert _reject_code(repo) == "UNSUPPORTED_REPOSITORY"

    # Workspace identity drift (git root differs from the sealed identity).
    repo = fresh_repo_factory()
    drifted = repo.identity.model_copy(
        update={"canonical_absolute_path": repo.identity.canonical_absolute_path + "_x"}
    )
    drifted = drifted.model_copy(update={"digest": digest_workspace_identity(drifted)})
    result = run_git_snapshot_prechecks(drifted, repo.reference_manifest)
    assert result.kind == "REJECTED"
    assert result.error_code == "UNSUPPORTED_REPOSITORY"
    assert repo.snapshot_create_count == 0

    # Unborn HEAD (fresh repository without any commit).
    repo = fresh_repo_factory()
    unborn_root = repo.root / "fresh-unborn"
    unborn_root.mkdir()
    subprocess.run(
        ["git", "init", "-q"],
        cwd=unborn_root,
        env=repo._env,
        check=False,
    )
    unborn = _fixture_identity(unborn_root)
    result = run_git_snapshot_prechecks(unborn, repo.reference_manifest)
    assert result.kind == "REJECTED"
    assert result.error_code == "UNSUPPORTED_REPOSITORY"
    assert repo.snapshot_create_count == 0

    # Bare repository (no worktree) => UNSUPPORTED_REPOSITORY.
    repo = fresh_repo_factory()
    bare_root = repo.root / "bare.git"
    subprocess.run(
        ["git", "init", "-q", "--bare", str(bare_root)],
        env=repo._env,
        check=False,
    )
    bare_identity = _fixture_identity(bare_root)
    result = run_git_snapshot_prechecks(bare_identity, repo.reference_manifest)
    assert result.kind == "REJECTED"
    assert result.error_code == "UNSUPPORTED_REPOSITORY"
    assert repo.snapshot_create_count == 0

    # SPEC §1.4.4: tracked file count cap (5,000) => UNSUPPORTED_REPOSITORY.
    repo = fresh_repo_factory()
    bulk = repo.root / "bulk"
    bulk.mkdir()
    for index in range(5_001):
        (bulk / f"f{index:04d}.txt").write_text("x\n", encoding="utf-8")
    repo._git("add", ".")
    repo._commit("bulk files")
    assert _reject_code(repo) == "UNSUPPORTED_REPOSITORY"

    # SPEC §1.4.4: single tracked file cap (4 MiB) => UNSUPPORTED_REPOSITORY.
    repo = fresh_repo_factory()
    (repo.root / "src" / "big.bin").write_bytes(b"x" * (4 * 1024 * 1024 + 1))
    repo._git("add", ".")
    repo._commit("big file")
    assert _reject_code(repo) == "UNSUPPORTED_REPOSITORY"

    # SPEC §1.4.4: tracked byte total cap (128 MiB) => UNSUPPORTED_REPOSITORY.
    repo = fresh_repo_factory()
    chunk = b"x" * (4 * 1024 * 1024)
    for index in range(33):
        (repo.root / "src" / f"chunk{index:02d}.bin").write_bytes(chunk)
    repo._git("add", ".")
    repo._commit("bulk bytes")
    assert _reject_code(repo) == "UNSUPPORTED_REPOSITORY"


def test_observation_command_failure_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
    sealed_git_repo: GitRepositoryFixture,
) -> None:
    """A failed sealed observation raises GitPreflightError — a failed
    ``ls-files -v``/``--others``/``status`` read must never be sealed as
    empty evidence."""
    import src.vespercode.workspace.git_preflight as git_preflight

    real_git = git_preflight._git
    calls = 0

    def failing_git(
        argv: list[str], cwd: Path, env: dict[str, str]
    ) -> subprocess.CompletedProcess[str]:
        nonlocal calls
        calls += 1
        # Calls 1-5 (rev-parse x2, config, index x2) succeed; call 6 is
        # the first _git_checked observation (ls-files -v).
        if calls >= 6:
            return subprocess.CompletedProcess(
                argv, returncode=1, stdout="", stderr="probe failure"
            )
        return real_git(argv, cwd, env)

    monkeypatch.setattr(git_preflight, "_git", failing_git)
    with pytest.raises(git_preflight.GitPreflightError, match="probe failure"):
        run_git_snapshot_prechecks(
            sealed_git_repo.identity, sealed_git_repo.reference_manifest
        )


def test_unstable_index_is_rejected_before_snapshot(
    monkeypatch: pytest.MonkeyPatch,
    sealed_git_repo: GitRepositoryFixture,
) -> None:
    """The index read twice must be byte-identical; drift rejects."""
    import src.vespercode.workspace.git_preflight as git_preflight

    calls = 0

    def unstable_index_bytes(*args: object, **kwargs: object) -> bytes:
        nonlocal calls
        calls += 1
        return b"AAAA" if calls == 1 else b"BBBB"

    monkeypatch.setattr(git_preflight, "_index_bytes", unstable_index_bytes)
    result = run_git_snapshot_prechecks(
        sealed_git_repo.identity, sealed_git_repo.reference_manifest
    )
    assert result.kind == "REJECTED"
    assert result.error_code == "UNSUPPORTED_REPOSITORY"
    assert sealed_git_repo.snapshot_create_count == 0

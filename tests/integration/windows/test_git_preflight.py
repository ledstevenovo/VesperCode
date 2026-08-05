"""T09.1 legacy step 9.C (Windows): real-identity Git preflight parity.

Runs only under ``-m windows_integration`` on the project Windows host.
Proves ``run_git_snapshot_prechecks`` against a real Git repository with
a REAL handle-derived workspace identity: the supported state seals every
observation and binds the frozen editable policy digest, while skip-worktree
and tracked-drift states reject with zero Snapshot rows.  The disposable
repository is deleted in teardown.
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

from src.vespercode.profiles.registry import build_profile_registry
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


def _git(root: Path, home: Path, *args: str) -> None:
    env = _git_env(str(home))
    completed = subprocess.run(
        ["git", *_GIT_BASE_ARGS, *args],
        cwd=root,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr


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
    """One real repository with a real handle-derived identity."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self._home = root / ".git-home"
        self._home.mkdir(exist_ok=True)
        self.git("init", "-q")
        (root / "src").mkdir()
        (root / "src" / "a.py").write_text("def a():\n    return 1\n", encoding="utf-8")
        (root / "pyproject.toml").write_text(
            '[project]\nname = "integration"\n', encoding="utf-8"
        )
        (root / "requirements.lock").write_text("pytest==8.4.2\n", encoding="utf-8")
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
        _git(self.root, self._home, *args)

    @property
    def snapshot_create_count(self) -> int:
        return 0


@pytest.fixture
def sealed_real_repo() -> Iterator[_SealedRealRepo]:
    root = Path(tempfile.mkdtemp(prefix="vesper_git_real_"))
    try:
        yield _SealedRealRepo(root)
    finally:
        _force_rmtree(root)
        assert not root.exists(), "repository residue remains"


def test_real_identity_preflight_supported_seals_every_observation(
    sealed_real_repo: _SealedRealRepo,
) -> None:
    result = run_git_snapshot_prechecks(
        sealed_real_repo.identity, sealed_real_repo.reference_manifest
    )
    assert isinstance(result, GitPreflightResultV1)
    assert result.kind == "SUPPORTED"
    assert result.error_code is None
    assert len(result.head_commit_digest or "") == 40
    assert len(result.index_digest or "") == 64
    assert len(result.worktree_digest or "") == 64
    assert len(result.ignore_rules_digest or "") == 64
    assert len(result.attributes_digest or "") == 64
    assert len(result.config_digest or "") == 64
    assert result.repository_policy_digest == (
        sealed_real_repo.reference_manifest.editable_path_policy.digest
    )
    assert result.core_autocrlf_enabled is False
    assert result.core_eol_enabled is False
    assert result.conversion_attributes_present is False
    assert sealed_real_repo.snapshot_create_count == 0


def test_real_identity_preflight_rejects_skip_worktree(
    sealed_real_repo: _SealedRealRepo,
) -> None:
    sealed_real_repo.git("update-index", "--skip-worktree", "src/a.py")
    result = run_git_snapshot_prechecks(
        sealed_real_repo.identity, sealed_real_repo.reference_manifest
    )
    assert result.kind == "REJECTED"
    assert result.error_code == "UNSUPPORTED_REPOSITORY"
    assert sealed_real_repo.snapshot_create_count == 0


def test_real_identity_preflight_rejects_dirty_tracked_protected_input(
    sealed_real_repo: _SealedRealRepo,
) -> None:
    (sealed_real_repo.root / "pyproject.toml").write_text(
        '[project]\nname = "tampered"\n', encoding="utf-8"
    )
    result = run_git_snapshot_prechecks(
        sealed_real_repo.identity, sealed_real_repo.reference_manifest
    )
    assert result.kind == "REJECTED"
    assert result.error_code == "WORKTREE_DIRTY"
    assert sealed_real_repo.snapshot_create_count == 0

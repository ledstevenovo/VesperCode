"""T33.1 legacy step 33.B: isolated pipx installation tests.

The domain pins the fresh project-specific pipx home/bin/app data
(GREEN-1): the install lands inside the isolated root, the packaged
entry point exists in the isolated bin directory, and the installed
package's own RECORD binds the exact 33.A wheel bytes (never a
rebuilt, mutated, or source-tree copy).
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Final

import pytest

from scripts.run_package_smoke import (
    InstalledPackage,
    PackageSmokeErrorV1,
    WheelArchive,
)

pytestmark = pytest.mark.package_smoke

_PROJECT_VERSION_V1: Final = "0.1.0"
"""The frozen distribution version (33.A pin, pyproject ``version``)."""

_REPO_ROOT: Final = Path(__file__).resolve().parents[3]
"""The repository root (tests/smoke/package/test_pipx_install.py)."""


def _installed_record_entries(
    package: InstalledPackage,
) -> dict[str, tuple[str, str]]:
    """The parsed RECORD of the installed package's dist-info."""
    dist_info = package.venv_dir / "Lib" / "site-packages"
    if not dist_info.is_dir():
        dist_info = package.venv_dir / "lib" / "python3.12" / "site-packages"
    record_path = dist_info / f"vespercode-{_PROJECT_VERSION_V1}.dist-info" / "RECORD"
    if not record_path.is_file():
        raise PackageSmokeErrorV1(f"installed RECORD missing: {record_path}")
    rows: dict[str, tuple[str, str]] = {}
    for line in record_path.read_text(encoding="utf-8").splitlines():
        parts = line.split(",")
        digest = parts[1]
        if digest.startswith("sha256="):
            digest = digest[len("sha256=") :]
        rows[parts[0]] = (digest, parts[2])
    return rows


def test_pipx_home_is_fresh_project_specific_and_isolated(
    clean_pipx_install: InstalledPackage,
) -> None:
    """The pipx home/bin/app data live under one fresh project-specific
    root — never shared pipx state (GREEN-1/Boundary).
    """
    assert clean_pipx_install.root.name.startswith("vespercode-pipx-")
    assert clean_pipx_install.home.is_dir()
    assert (clean_pipx_install.home / "venvs" / "vespercode").is_dir()
    assert clean_pipx_install.bin_dir.is_dir()
    assert clean_pipx_install.python.is_file()
    assert clean_pipx_install.entry_point.is_file()
    assert clean_pipx_install.installed_package_path().is_relative_to(
        clean_pipx_install.home
    )


def test_installed_package_binds_the_exact_wheel_digest(
    clean_pipx_install: InstalledPackage,
    built_wheel: WheelArchive,
) -> None:
    """The installed package's RECORD binds the exact 33.A wheel bytes:
    every member hash of the installed site-packages equals the wheel's
    own RECORD (the wheel is installed as-is, never mutated or
    source-tree substituted).
    """
    assert clean_pipx_install.wheel_digest == built_wheel.sha256
    wheel_rows = {
        entry.path: (entry.sha256, entry.size) for entry in built_wheel.record_entries
    }
    installed_rows = _installed_record_entries(clean_pipx_install)
    for path, (sha256, size) in wheel_rows.items():
        assert path in installed_rows, f"installed RECORD missing {path}"
        if sha256 is None:
            continue  # the RECORD's own row
        assert installed_rows[path][0] == sha256, path
        assert int(installed_rows[path][1]) == size, path


def test_run_package_smoke_cleans_up_in_finally(
    built_wheel: WheelArchive,
    tmp_path: Path,
) -> None:
    """The declared driver interface ``run_package_smoke(config) ->
    PackageSmokeResultV1`` completes the full installed smoke and
    removes every temp pipx/probe root in ``finally`` (GREEN-2 cleanup;
    quality focus: ``finally`` cleanup and controlled evidence access).
    """
    import tempfile

    from scripts.run_package_smoke import (
        PackageSmokeConfigV1,
        PIPX_ROOT_PREFIX_V1,
        run_package_smoke,
    )

    before = {
        entry.name
        for entry in Path(tempfile.gettempdir()).iterdir()
        if entry.name.startswith(PIPX_ROOT_PREFIX_V1)
        or entry.name.startswith("vespercode-probe-")
    }
    result = run_package_smoke(
        PackageSmokeConfigV1(
            schema_version=1,
            dist_dir=str(built_wheel.wheel_path.parent),
            require_one_wheel=True,
            report_path=str(tmp_path / "package-smoke-report.json"),
            source_root=str(_REPO_ROOT),
        )
    )
    assert result.all_ok, result.error_message
    assert result.wheel_sha256 == built_wheel.sha256
    assert result.wheel_evidence_match
    assert result.recovery_preview_zero_writes
    report = tmp_path / "package-smoke-report.json"
    assert report.is_file()
    assert report.read_text(encoding="utf-8") == result.report_text
    assert (
        result.report_digest
        == hashlib.sha256(result.report_text.encode("utf-8")).hexdigest()
    )
    after = {
        entry.name
        for entry in Path(tempfile.gettempdir()).iterdir()
        if entry.name.startswith(PIPX_ROOT_PREFIX_V1)
        or entry.name.startswith("vespercode-probe-")
    }
    assert after == before

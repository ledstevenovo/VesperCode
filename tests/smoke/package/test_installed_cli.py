"""T33.1 legacy step 33.B: clean installed CLI smoke tests.

The exact RED pins the clean installed-help smoke: the wheel installed
into the fresh isolated pipx home answers ``vespercode --help`` with
exit 0 and zero source-checkout imports (GREEN-3); the distribution
smoke matrix pins the isolated layout, the packaged entry point, the
installed-version identity binding, the zero source-fallback fact, and
the closed standalone surface (the production recover binding is the
Task 38.F composition, never the standalone entry).
"""

from __future__ import annotations

from pathlib import Path
from typing import Final

import pytest

from scripts.run_package_smoke import InstalledPackage

pytestmark = pytest.mark.package_smoke

_PROJECT_VERSION_V1: Final = "0.1.0"
"""The frozen distribution version (33.A pin, pyproject ``version``)."""

_REPO_ROOT: Final = Path(__file__).resolve().parents[3]
"""The repository root (tests/smoke/package/test_installed_cli.py)."""


def test_installed_cli_does_not_import_source_checkout(
    clean_pipx_install: InstalledPackage,
) -> None:
    result = clean_pipx_install.run("vespercode", "--help")
    assert result.exit_code == 0
    assert clean_pipx_install.source_checkout_import_count == 0


def test_installed_distribution_smoke_matrix(
    clean_pipx_install: InstalledPackage,
) -> None:
    """The exact installed-distribution smoke matrix (Expected 33.B).

    Pins the fresh isolated pipx layout, the packaged entry point, the
    installed-help proof with zero source fallback, the installed
    package/version identity under the pipx home, the closed standalone
    recover surface (production binding belongs to Task 38.F), and the
    closed serve help surface.
    """
    # --- the fresh isolated pipx layout ---
    assert clean_pipx_install.root.name.startswith("vespercode-pipx-")
    assert clean_pipx_install.home.is_dir()
    assert clean_pipx_install.venv_dir.is_dir()
    assert clean_pipx_install.entry_point.is_file()

    # --- the packaged entry point proves help ---
    help_result = clean_pipx_install.run("vespercode", "--help")
    assert help_result.exit_code == 0
    assert "serve" in help_result.output
    assert "VesperCode" in help_result.output

    # --- zero source-checkout fallback across the matrix ---
    assert clean_pipx_install.source_checkout_import_count == 0

    # --- the installed package resolves inside the pipx home ---
    installed_path = clean_pipx_install.installed_package_path()
    assert installed_path.is_relative_to(clean_pipx_install.home)
    assert not installed_path.is_relative_to(_REPO_ROOT / "src")

    # --- the installed version binds the 33.A wheel version ---
    assert clean_pipx_install.installed_version() == _PROJECT_VERSION_V1

    # --- the closed standalone surface: recover fails closed without
    # the Task 38.F production binding (never ``recover --apply``) ---
    recover = clean_pipx_install.run("vespercode", "recover", "--workspace", "C:\\repo")
    assert recover.exit_code != 0

    # --- the closed serve help surface of the installed entry ---
    serve_help = clean_pipx_install.run("vespercode", "serve", "--help")
    assert serve_help.exit_code == 0
    assert "--port" in serve_help.output
    assert "127.0.0.1" in serve_help.output

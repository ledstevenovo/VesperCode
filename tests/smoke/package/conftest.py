"""T33.1 package-smoke fixtures: the built wheel and the clean pipx
install.

``built_wheel`` builds exactly one clean wheel into the repository
``dist/`` directory with the card Build command and publishes the
adjacent lowercase SHA-256 evidence from the exact wheel bytes (33.A
GREEN-1/GREEN-2); ``clean_pipx_install`` installs that exact wheel into
a fresh project-specific isolated pipx home and cleans every temp
artifact in ``finally`` (33.B GREEN-1/Boundary).  The harness types
(``WheelArchive``, ``InstalledPackage``) are owned by
``scripts/run_package_smoke.py`` so the standalone driver and the tests
share one implementation (the demo-image smoke precedent).
"""

from __future__ import annotations

import shutil
import sys
import tempfile
from pathlib import Path
from typing import Final, Iterator

import pytest

from scripts.run_package_smoke import (
    InstalledPackage,
    PIPX_ROOT_PREFIX_V1,
    WheelArchive,
    _venv_python_of,
    build_wheel_into,
    open_wheel_archive,
    pipx_install_wheel,
)

_REPO_ROOT: Final = Path(__file__).resolve().parents[3]
"""The repository root (tests/smoke/package/conftest.py -> parents[3])."""

_DIST_DIR: Final = _REPO_ROOT / "dist"
"""The one declared wheel output directory (33.A interface)."""

_SOURCE_SRC: Final = _REPO_ROOT / "src"
"""The source checkout's package root (the fallback that must never be
imported by an installed command)."""


@pytest.fixture(scope="session")
def built_wheel() -> WheelArchive:
    """Build exactly one clean wheel and publish its SHA-256 evidence.

    Stale wheel/evidence artifacts are removed before the build so the
    dist directory holds exactly one versioned wheel (GREEN-1); the
    adjacent lowercase evidence is computed by the harness from the
    exact wheel bytes (GREEN-2).
    """
    _DIST_DIR.mkdir(parents=True, exist_ok=True)
    for stale in list(_DIST_DIR.glob("vespercode-*.whl")) + list(
        _DIST_DIR.glob("vespercode-*.whl.sha256")
    ):
        stale.unlink()
    wheel_path = build_wheel_into(_DIST_DIR)
    return open_wheel_archive(wheel_path)


@pytest.fixture(scope="session")
def clean_pipx_install(built_wheel: WheelArchive) -> Iterator[InstalledPackage]:
    """One fresh isolated pipx install of the exact 33.A wheel.

    The pipx home/bin/man data live under one project-specific temp
    root (``vespercode-pipx-*``), never shared pipx state; the venv
    interpreter and entry point come from that fresh home; the sandbox
    working directory sits outside the repository; and the whole root
    is removed in ``finally`` after every test consumed the fixture.
    """
    root = Path(tempfile.mkdtemp(prefix=PIPX_ROOT_PREFIX_V1))
    home = root / "home"
    bin_dir = root / "bin"
    man_dir = root / "man"
    sandbox = root / "sandbox"
    sandbox.mkdir()
    try:
        install = pipx_install_wheel(
            built_wheel.wheel_path,
            pipx_home=home,
            pipx_bin_dir=bin_dir,
            pipx_man_dir=man_dir,
            python=sys.executable,
        )
        assert install.exit_code == 0, install.output
        package = InstalledPackage(
            wheel_path=built_wheel.wheel_path,
            root=root,
            home=home,
            bin_dir=bin_dir,
            venv_dir=home / "venvs" / "vespercode",
            python=_venv_python_of(home),
            source_src=_SOURCE_SRC,
            sandbox=sandbox,
        )
        yield package
    finally:
        shutil.rmtree(root, ignore_errors=True)

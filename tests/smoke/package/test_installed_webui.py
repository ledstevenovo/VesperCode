"""T33.1 legacy step 33.B: installed production WebUI composition tests.

The domain pins the production WebUI composition from the installed
package (GREEN-2): the frozen governance-then-operations installer
tuple serves the formal pages and the identity-verified packaged asset
on the reserved loopback port, the fixed Demo app answers its canonical
healthz, and the read-only recovery preview projects ``NO_TRANSACTION``
with zero workspace writes — every fact collected by a probe executed
inside the pipx venv with a clean environment and a working directory
outside the repository (zero source-checkout fallback).
"""

from __future__ import annotations

from pathlib import Path
from typing import Final

import pytest

from scripts.run_package_smoke import (
    InstalledPackage,
    InstalledProbeResultV1,
    EXPECTED_HTMX_BYTE_LENGTH_V1,
    EXPECTED_RECOVERY_PREVIEW_KIND_V1,
    reserve_loopback_port,
    run_installed_webui_probe,
)

pytestmark = pytest.mark.package_smoke

_REPO_ROOT: Final = Path(__file__).resolve().parents[3]
"""The repository root (tests/smoke/package/test_installed_webui.py)."""


@pytest.fixture(scope="module")
def installed_webui_probe(
    clean_pipx_install: InstalledPackage,
    tmp_path_factory: pytest.TempPathFactory,
) -> InstalledProbeResultV1:
    """One installed production WebUI/recovery probe result.

    The probe runs once per module inside the isolated pipx venv; the
    workspace/control-data/probe directories live under a pytest temp
    root outside the repository.
    """
    base = tmp_path_factory.mktemp("vespercode-installed-webui")
    workspace = base / "workspace"
    control_db_dir = base / "control"
    probe_dir = base / "probe"
    control_db_dir.mkdir(parents=True)
    probe_dir.mkdir(parents=True)
    return run_installed_webui_probe(
        venv_python=clean_pipx_install.python,
        webui_port=reserve_loopback_port(),
        demo_port=reserve_loopback_port(),
        source_src=_REPO_ROOT / "src",
        workspace=workspace,
        control_db_dir=control_db_dir,
        probe_dir=probe_dir,
    )


def test_installed_probe_has_zero_source_checkout_fallback(
    clean_pipx_install: InstalledPackage,
    installed_webui_probe: InstalledProbeResultV1,
) -> None:
    """The probe executed from the installed venv with a clean
    environment and a working directory outside the repository: the
    resolved package lives under the pipx home, never in ``src/``
    (GREEN-2 zero source fallback).
    """
    assert installed_webui_probe.source_checkout_imported is False
    installed_path = Path(installed_webui_probe.installed_package_path)
    assert installed_path.is_relative_to(clean_pipx_install.home)
    assert not installed_path.is_relative_to(_REPO_ROOT / "src")
    assert installed_webui_probe.python_version.startswith("3.12")


def test_installed_webui_serves_formal_pages_and_packaged_asset(
    installed_webui_probe: InstalledProbeResultV1,
) -> None:
    """The production local app composes from the installed package and
    serves every formal page plus the identity-verified packaged htmx
    asset on the reserved loopback port (GREEN-2/28.C identity).
    """
    pages = {page.path: page for page in installed_webui_probe.pages}
    for path in (
        "/",
        "/credentials/openai",
        "/runs/new",
        "/runs/run-1/memory",
        "/runs/run-1/audit",
        "/runs/run-1/recovery",
    ):
        assert pages[path].status == 200, path
        assert pages[path].ok, path
        assert pages[path].content_type.startswith("text/html"), path
    asset = pages["/static/htmx.min.js"]
    assert asset.status == 200
    assert asset.content_type.startswith("application/javascript")
    assert asset.byte_length == EXPECTED_HTMX_BYTE_LENGTH_V1
    assert asset.ok
    assert all(page.ok for page in installed_webui_probe.pages)


def test_installed_demo_service_boots_with_canonical_healthz(
    installed_webui_probe: InstalledProbeResultV1,
) -> None:
    """The fixed Demo app from the installed wheel boots on the reserved
    loopback port and answers the canonical ``/healthz`` (SPEC §8.3)."""
    assert installed_webui_probe.demo_healthz_status == 200
    assert installed_webui_probe.demo_healthz_ok


def test_installed_recovery_preview_is_read_only(
    installed_webui_probe: InstalledProbeResultV1,
) -> None:
    """The production recovery preview through the installed package
    projects the closed ``NO_TRANSACTION`` outcome with zero workspace
    writes and the installed recover parser exits 0 with the bounded
    hint (GREEN-2/AC-29; never ``recover --apply``)."""
    assert installed_webui_probe.recovery_kind == EXPECTED_RECOVERY_PREVIEW_KIND_V1
    assert installed_webui_probe.recovery_workspace_zero_writes
    assert installed_webui_probe.recovery_cli_exit_code == 0
    assert installed_webui_probe.recovery_cli_hint_ok
    assert installed_webui_probe.all_ok

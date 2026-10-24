"""Route A / RA-09 + Route B / B4b-02B: the wheel package contract
covers every v2 module and the coherent v2 alpha package identity.

``tests/smoke/package/test_wheel_contents.py`` is a pytest/pipx-gated smoke
suite that cannot run in the offline v2 unit job (no pytest, no wheel
build on this line).  This contract test is the deterministic, stdlib-only
guard that runs on every push: it fails closed when a v2 production module
under ``src/vespercode`` is missing from the smoke suite's
``REQUIRED_RUNTIME_MEMBERS`` wheel-member set, or when the Hatchling wheel
configuration would not select the v2 source tree at all.  It parses files
statically — no build, no network, no pytest — so a packaging regression
is caught in the same command that runs the v2 unit suite.

B4b-02B extends the same offline guard to the v2 alpha package identity:
the pyproject version/name/python-requirement stay coherent with the
package ``__init__`` pins, the console-script table keeps exactly two
entries (the legacy ``vespercode`` entry stays the frozen v1 CLI and is
never silently presented as v2; ``vespercode-v2`` targets
``vespercode.cli_v2:main``), the version-bound entry-point metadata member
and the other package smoke suites pin the same alpha version, and the
required member set never leaks into the smoke suite's prohibited
(tests/evidence/credentials/checkout/VCS/junk) member set.
"""

from __future__ import annotations

import re
import tomllib
import unittest
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[3]
_SRC_ROOT = _REPO_ROOT / "src" / "vespercode"
_WHEEL_CONTRACT_PATH = (
    _REPO_ROOT / "tests" / "smoke" / "package" / "test_wheel_contents.py"
)
_PYPROJECT_PATH = _REPO_ROOT / "pyproject.toml"

# Every v2 production module (the alpha's active source surface).  Files
# that only exist on the v1 history line are not listed; the smoke suite
# keeps its own frozen v1 member set.  The discovery test below keeps this
# pin in lockstep with the source tree, so a new v2 module cannot appear
# without both the pin and the wheel contract growing with it.
_V2_PRODUCTION_MODULES: frozenset[str] = frozenset(
    {
        "candidate/v2_candidate.py",
        "cli_v2.py",
        "contracts/v2_identity.py",
        "contracts/v2_validation.py",
        "contracts/v2_writeback.py",
        "credentials/v2_os_store.py",
        "credentials/v2_port.py",
        "execution/v2_database_binding.py",
        "execution/v2_docker_executor.py",
        "execution/v2_docker_probe.py",
        "execution/v2_execution.py",
        "execution/v2_executor.py",
        "execution/v2_profile.py",
        "governance/relaxed_policy.py",
        "governance/v2_disclosure.py",
        "governance/v2_secret_scanner.py",
        "llm/v2.py",
        "llm/v2_openai_adapter.py",
        "loop/v2_engine.py",
        "memory/v2.py",
        "persistence/v2_recovery.py",
        "persistence/v2_writeback.py",
        "profiles/v2_endpoints.py",
        "profiles/v2_reference.py",
        "providers/v2_call.py",
        "providers/v2_transport.py",
        "runtime_v2.py",
        "shell_v2.py",
        "storage/v2_database.py",
        "tools/v2_dispatcher.py",
        "tui/v2_app.py",
        "tui/v2_launch.py",
        "tui/v2_view_model.py",
        "web/v2_app.py",
        "web/v2_forms.py",
        "web/v2_security.py",
        "web/v2_server.py",
        "workspace/v2_boundary.py",
        "workspace/v2_disk.py",
    }
)

# v2-line modules whose file names do not start with "v2".
_V2_MODULES_WITHOUT_V2_NAMES: tuple[str, ...] = (
    "cli_v2.py",
    "governance/relaxed_policy.py",
    "runtime_v2.py",
    "shell_v2.py",
)

# The coherent v2 alpha package identity (B4b-02B): the selected alpha
# version, the frozen v1 history version it must never silently
# present, and the closed two-entry console-script table.
_V2_ALPHA_VERSION = "0.2.0a0"
_LEGACY_VERSION = "0.1.0"
_CONSOLE_SCRIPTS: dict[str, str] = {
    "vespercode": "vespercode.cli:main",
    "vespercode-v2": "vespercode.cli_v2:main",
}

_SMOKE_INSTALLED_CLI_PATH = (
    _REPO_ROOT / "tests" / "smoke" / "package" / "test_installed_cli.py"
)
_SMOKE_PIPX_INSTALL_PATH = (
    _REPO_ROOT / "tests" / "smoke" / "package" / "test_pipx_install.py"
)

_MEMBER_PATTERN = re.compile(r'"vespercode/([\w./-]+)"')


def _required_runtime_members() -> frozenset[str]:
    text = _WHEEL_CONTRACT_PATH.read_text(encoding="utf-8")
    start = text.index("REQUIRED_RUNTIME_MEMBERS")
    end = text.index(")", text.index("{", start))
    return frozenset(_MEMBER_PATTERN.findall(text[start:end]))


def _frozenset_block_strings(name: str) -> frozenset[str]:
    """Every double-quoted string of one ``frozenset({...})`` block.

    The block ends at the first line that is only a closing parenthesis,
    so comment lines inside the block (which may themselves contain
    parentheses) cannot truncate the extraction.
    """
    text = _WHEEL_CONTRACT_PATH.read_text(encoding="utf-8")
    start = text.index(name)
    block: list[str] = []
    for line in text[start:].splitlines():
        block.append(line)
        if line.strip() == ")":
            break
    return frozenset(re.findall(r'"([^"]+)"', "\n".join(block)))


def _prohibited_wheel_members() -> frozenset[str]:
    """The smoke suite's closed prohibited member set, parsed offline."""
    return _frozenset_block_strings("PROHIBITED_WHEEL_MEMBERS")


def _pyproject_project() -> dict[str, object]:
    with _PYPROJECT_PATH.open("rb") as stream:
        return tomllib.load(stream)["project"]


def _discovered_v2_modules() -> frozenset[str]:
    """Every v2-named module under ``src/vespercode`` plus the extras."""
    discovered = {
        path.relative_to(_SRC_ROOT).as_posix() for path in _SRC_ROOT.rglob("v2*.py")
    }
    discovered.update(
        relative
        for relative in _V2_MODULES_WITHOUT_V2_NAMES
        if (_SRC_ROOT / relative).is_file()
    )
    return frozenset(discovered)


class V2WheelContractTests(unittest.TestCase):
    def test_every_v2_production_module_is_a_required_wheel_member(self) -> None:
        members = _required_runtime_members()
        missing = _V2_PRODUCTION_MODULES - members
        self.assertEqual(
            missing,
            frozenset(),
            f"v2 modules missing from REQUIRED_RUNTIME_MEMBERS: {sorted(missing)}",
        )

    def test_every_v2_module_exists_in_the_source_tree(self) -> None:
        for relative in _V2_PRODUCTION_MODULES:
            self.assertTrue(
                (_SRC_ROOT / relative).is_file(),
                f"declared v2 module does not exist: {relative}",
            )

    def test_hatchling_wheel_selects_the_v2_source_tree(self) -> None:
        pyproject = _PYPROJECT_PATH.read_text(encoding="utf-8")
        self.assertIn(
            'packages = ["src/vespercode"]',
            pyproject,
            "the Hatchling wheel package selection must keep the src/vespercode tree",
        )
        self.assertIn(
            "vespercode/**/*.py",
            pyproject,
            "the wheel include pattern must select every packaged Python file",
        )

    def test_the_pin_covers_every_v2_module_in_the_source_tree(self) -> None:
        discovered = _discovered_v2_modules()
        pin_only = _V2_PRODUCTION_MODULES - discovered
        tree_only = discovered - _V2_PRODUCTION_MODULES
        self.assertEqual(
            (pin_only, tree_only),
            (frozenset(), frozenset()),
            "the v2 module pin drifted from the source tree: "
            f"pin-only={sorted(pin_only)}, tree-only={sorted(tree_only)}",
        )

    def test_pyproject_declares_the_coherent_v2_alpha_identity(self) -> None:
        project = _pyproject_project()
        self.assertEqual(project["name"], "vespercode")
        self.assertEqual(project["version"], _V2_ALPHA_VERSION)
        self.assertEqual(project["requires-python"], ">=3.12,<3.13")

    def test_the_package_version_pins_stay_coherent(self) -> None:
        init_source = (_SRC_ROOT / "__init__.py").read_text(encoding="utf-8")
        self.assertIn(f'V2_VERSION = "{_V2_ALPHA_VERSION}"', init_source)
        self.assertIn("__version__ = V2_VERSION", init_source)
        self.assertIn(f'LEGACY_VERSION = "{_LEGACY_VERSION}"', init_source)
        self.assertNotEqual(_V2_ALPHA_VERSION, _LEGACY_VERSION)

    def test_console_entry_points_pin_the_v2_alpha_boundary(self) -> None:
        project = _pyproject_project()
        self.assertEqual(project["scripts"], _CONSOLE_SCRIPTS)
        # The v2 entry targets the shipped v2 CLI, which presents itself
        # as "vespercode-v2" and never imports the frozen v1 CLI; the
        # legacy entry keeps targeting the frozen v1 CLI module.
        v2_cli_source = (_SRC_ROOT / "cli_v2.py").read_text(encoding="utf-8")
        self.assertIn('prog="vespercode-v2"', v2_cli_source)
        self.assertNotIn("import vespercode.cli", v2_cli_source)
        self.assertTrue((_SRC_ROOT / "cli.py").is_file())

    def test_the_wheel_smoke_matrix_pins_both_console_entry_points(self) -> None:
        smoke = _WHEEL_CONTRACT_PATH.read_text(encoding="utf-8")
        self.assertIn(
            'assert "vespercode = vespercode.cli:main" in entry_points',
            smoke,
        )
        self.assertIn(
            'assert "vespercode-v2 = vespercode.cli_v2:main" in entry_points',
            smoke,
        )
        self.assertIn(
            'f"vespercode-{PROJECT_VERSION_V2}.dist-info/entry_points.txt"',
            smoke,
        )

    def test_the_package_smoke_suites_pin_the_same_alpha_version(self) -> None:
        for path in (
            _WHEEL_CONTRACT_PATH,
            _SMOKE_INSTALLED_CLI_PATH,
            _SMOKE_PIPX_INSTALL_PATH,
        ):
            source = path.read_text(encoding="utf-8")
            self.assertIn(
                f'= "{_V2_ALPHA_VERSION}"',
                source,
                f"{path.name} must pin the same v2 alpha version",
            )

    def test_required_members_stay_disjoint_from_the_prohibited_set(self) -> None:
        members = _required_runtime_members()
        prohibited = _prohibited_wheel_members()
        self.assertEqual(
            members & prohibited,
            frozenset(),
            "required wheel members must never appear in the smoke "
            "suite's prohibited member set (tests, source evidence, "
            "credentials, VCS data, checkout junk)",
        )

    def test_required_members_never_leak_outside_the_packaged_tree(self) -> None:
        prohibited_segments = {name.rstrip("/") for name in _prohibited_wheel_members()}
        for member in _required_runtime_members():
            first_segment = member.split("/", 1)[0]
            self.assertNotIn(
                first_segment,
                prohibited_segments,
                "required wheel member leaks a prohibited top-level "
                f"name (tests, evidence, credentials, checkout, or VCS "
                f"data): {member}",
            )
            self.assertNotIn(
                "..",
                member,
                f"required wheel member carries a traversal segment: {member}",
            )


if __name__ == "__main__":
    unittest.main()

"""Route B / B4b-02B: the v2 alpha wheel/release path stays a separate,
source-artifact-only path that never mixes with the frozen v1 release.

The frozen v1 release workflow (``.github/workflows/release.yml``) is the
historical v0.1.0 publication record: tag admission, the frozen source
commit, the frozen image digest, the protected publish environment, and
the registry image push.  It must stay byte-unchanged and must never carry
v2 identity.  The v2 alpha release path is a NEW, independent, manually
dispatched workflow (``.github/workflows/release-v2-alpha.yml``) that
verifies the ``0.2.0a0`` package identity, runs the documented offline
v2 unit suite, builds the wheel with the locked build toolchain, and
uploads the wheel plus its SHA-256 evidence as one CI artifact.  It
publishes nothing else: no GitHub Release object, no registry image, no
public deployment, no secret reference, and no write permission
anywhere — so the legacy ``vespercode`` entry point (still the frozen v1
CLI) can never be silently presented as, or confused with, the v2 alpha
identity carried by ``vespercode-v2``.

Every assertion below reads the committed files offline with the
standard library only (plus the one runtime parser pin over the shipped
v2 CLI); no workflow run, network, build tool, pytest, or pipx is
required.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

from vespercode.cli_v2 import build_v2_cli_parser

_REPO_ROOT = Path(__file__).resolve().parents[4]
_V2_ALPHA_WORKFLOW_PATH = _REPO_ROOT / ".github" / "workflows" / "release-v2-alpha.yml"
_V1_RELEASE_WORKFLOW_PATH = _REPO_ROOT / ".github" / "workflows" / "release.yml"
_CI_WORKFLOW_PATH = _REPO_ROOT / ".github" / "workflows" / "ci.yml"
_PACKAGE_SMOKE_DRIVER_PATH = _REPO_ROOT / "scripts" / "run_package_smoke.py"

_V2_ALPHA_VERSION = "0.2.0a0"
_V1_FROZEN_COMMIT = "d31bdeeafe8ad65b60fac213e23fcab9dffdd7aa"
_V1_FROZEN_IMAGE_DIGEST = (
    "cf0b6c5ccac588fccd07c3b9f050bff4daf550ac6e518fd06efb6e988ab1d823"
)
_V1_ALPHA_WHEEL_NAME = "vespercode-0.2.0a0-py3-none-any.whl"

# The exact action set the v2 alpha release path may use: checkout, CPython
# setup, and the CI artifact upload.  Any publish, registry, deployment, or
# other action fails the closed enumeration.
_ALLOWED_V2_ALPHA_ACTIONS: frozenset[str] = frozenset(
    {
        "actions/checkout@v4",
        "actions/setup-python@v5",
        "actions/upload-artifact@v4",
    }
)

# Raw-text tokens that must NEVER appear in the v2 alpha release path: the
# v1 release identity (the frozen v1 version, source commit, and image
# digest), registry/image publication spellings, the GitHub Release CLI,
# the protected publish environment, write permissions, and secret
# references.
_FORBIDDEN_V2_ALPHA_TOKENS: tuple[str, ...] = (
    "0.1.0",
    _V1_FROZEN_COMMIT,
    _V1_FROZEN_IMAGE_DIGEST,
    "ghcr",
    "docker",
    "gh release",
    "environment:",
    "contents: write",
    "packages: write",
    "${{ secrets.",
)

# v2 identity tokens that must never leak into the frozen v1 release
# workflow: the alpha version, the v2 console entry point and its target
# module, and the v2 alpha release path's own names.
_FORBIDDEN_V1_WORKFLOW_V2_TOKENS: tuple[str, ...] = (
    _V2_ALPHA_VERSION,
    "vespercode-v2",
    "cli_v2",
    "release-v2-alpha",
    "dist-v2-alpha",
)

_USES_LINE = re.compile(r"^\s*- uses: (\S+)\s*$", re.MULTILINE)


def _v2_alpha_workflow_text() -> str:
    return _V2_ALPHA_WORKFLOW_PATH.read_text(encoding="utf-8")


def _v1_release_workflow_text() -> str:
    return _V1_RELEASE_WORKFLOW_PATH.read_text(encoding="utf-8")


def _uses_actions(text: str) -> frozenset[str]:
    return frozenset(_USES_LINE.findall(text))


class V2AlphaReleaseWorkflowTests(unittest.TestCase):
    """The independent v2 alpha release workflow contract."""

    def test_the_v2_alpha_release_workflow_exists(self) -> None:
        self.assertTrue(
            _V2_ALPHA_WORKFLOW_PATH.is_file(),
            "the v2 alpha release path must be a separate workflow file "
            "(.github/workflows/release-v2-alpha.yml), never an edit of "
            "the frozen v1 release workflow",
        )

    def test_the_release_path_is_manual_dispatch_only(self) -> None:
        text = _v2_alpha_workflow_text()
        self.assertIn("workflow_dispatch:", text)
        for absent in ("push:", "pull_request", "tags:"):
            self.assertNotIn(
                absent,
                text,
                "the v2 alpha release path must not be tag- or "
                "push-triggered (a pushed v* tag would also fire the "
                "frozen v1 release workflow)",
            )

    def test_the_release_path_is_read_only_secretless_and_unpublished(
        self,
    ) -> None:
        text = _v2_alpha_workflow_text()
        lowered = text.lower()
        self.assertIn("permissions:", text)
        self.assertIn("contents: read", text)
        for forbidden in _FORBIDDEN_V2_ALPHA_TOKENS:
            self.assertNotIn(
                forbidden.lower(),
                lowered,
                f"the v2 alpha release path must not carry the forbidden "
                f"token {forbidden!r}",
            )

    def test_the_release_path_uses_only_allowlisted_actions(self) -> None:
        actions = _uses_actions(_v2_alpha_workflow_text())
        self.assertEqual(
            actions,
            _ALLOWED_V2_ALPHA_ACTIONS,
            "the v2 alpha release path may use exactly checkout, "
            "setup-python, and the CI artifact upload",
        )

    def test_the_release_path_verifies_the_alpha_identity_first(self) -> None:
        text = _v2_alpha_workflow_text()
        self.assertIn("name: Release v2 alpha", text)
        self.assertIn("preflight:", text)
        self.assertIn(f'if version != "{_V2_ALPHA_VERSION}":', text)
        self.assertIn(
            'if scripts.get("vespercode-v2") != "vespercode.cli_v2:main":',
            text,
        )
        self.assertIn(
            'if scripts.get("vespercode") != "vespercode.cli:main":',
            text,
        )
        self.assertIn(f'V2_VERSION = "{_V2_ALPHA_VERSION}"', text)

    def test_the_release_path_runs_the_documented_offline_unit_suite(self) -> None:
        text = _v2_alpha_workflow_text()
        self.assertIn("unit-test:", text)
        self.assertIn(
            "PYTHONPATH=src python -m unittest discover -s tests/unit/v2 -v",
            text,
        )

    def test_the_release_path_builds_and_smoke_installs_the_alpha_wheel(
        self,
    ) -> None:
        text = _v2_alpha_workflow_text()
        self.assertIn("runs-on: windows-latest", text)
        self.assertIn("requirements/dev.lock", text)
        self.assertIn("--require-hashes", text)
        self.assertIn(
            "python -m build --wheel --no-isolation --outdir dist-v2-alpha",
            text,
        )
        self.assertIn(_V1_ALPHA_WHEEL_NAME, text)
        self.assertIn("pip install --no-deps", text)
        self.assertIn("vespercode-v2.exe --help", text)

    def test_the_release_path_uploads_exactly_one_named_source_artifact(
        self,
    ) -> None:
        text = _v2_alpha_workflow_text()
        self.assertIn("actions/upload-artifact@v4", text)
        self.assertIn("name: v2-alpha-wheel", text)
        self.assertIn("if-no-files-found: error", text)
        self.assertIn("retention-days: 30", text)

    def test_the_release_path_evidence_follows_the_package_smoke_convention(
        self,
    ) -> None:
        text = _v2_alpha_workflow_text()
        smoke_driver = _PACKAGE_SMOKE_DRIVER_PATH.read_text(encoding="utf-8")
        self.assertIn(
            'wheel_path.with_name(wheel_path.name + ".sha256")',
            smoke_driver,
        )
        self.assertIn(
            f"{_V1_ALPHA_WHEEL_NAME}.sha256",
            text,
            "the release digest evidence must be the adjacent "
            "<wheel-name>.whl.sha256 the package smoke driver defines",
        )


class FrozenV1ReleaseWorkflowTests(unittest.TestCase):
    """The frozen v1 release workflow stays the unchanged v1 record."""

    def test_the_v1_release_workflow_stays_the_frozen_v1_publication(
        self,
    ) -> None:
        text = _v1_release_workflow_text()
        for required in (
            'RELEASE_TAG: "v0.1.0"',
            f'FROZEN_SOURCE_COMMIT: "{_V1_FROZEN_COMMIT}"',
            f"FROZEN_DIGEST: sha256:{_V1_FROZEN_IMAGE_DIGEST}",
            '- "v*"',
            "environment: release",
            "contents: write",
            "packages: write",
            "gh release create",
            "docker push",
            "python -m build --wheel --no-isolation --outdir dist-release",
            "vespercode.exe --help",
        ):
            self.assertIn(
                required,
                text,
                "the frozen v1 release workflow identity drifted",
            )

    def test_the_v1_release_workflow_carries_no_v2_identity(self) -> None:
        text = _v1_release_workflow_text().lower()
        for forbidden in _FORBIDDEN_V1_WORKFLOW_V2_TOKENS:
            self.assertNotIn(
                forbidden.lower(),
                text,
                "the frozen v1 release workflow must never be edited to "
                f"carry the v2 identity token {forbidden!r}",
            )


class CurrentCIWorkflowTests(unittest.TestCase):
    """Ordinary CI stays the secretless offline v2 unit job."""

    def test_ci_stays_the_secretless_offline_v2_unit_job(self) -> None:
        text = _CI_WORKFLOW_PATH.read_text(encoding="utf-8")
        self.assertIn("unit-test", text)
        self.assertIn(
            "PYTHONPATH=src python -m unittest discover -s tests/unit/v2 -v",
            text,
        )
        self.assertIn("contents: read", text)
        self.assertNotIn("${{ secrets.", text)
        self.assertNotIn("actions/upload-artifact", text)
        self.assertNotIn("docker", text.lower())


class V2ConsoleIdentityTests(unittest.TestCase):
    """The shipped v2 CLI presents itself as the v2 alpha entry."""

    def test_the_shipped_v2_cli_presents_itself_as_vespercode_v2(self) -> None:
        self.assertEqual(build_v2_cli_parser().prog, "vespercode-v2")


if __name__ == "__main__":
    unittest.main()

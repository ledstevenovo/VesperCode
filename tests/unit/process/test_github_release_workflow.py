"""Offline contract for the protected GitHub-native release workflow."""

from pathlib import Path


_ROOT = Path(__file__).resolve().parents[3]
_WORKFLOW = _ROOT / ".github" / "workflows" / "release.yml"


def _workflow_text() -> str:
    return _WORKFLOW.read_text(encoding="utf-8")


def test_release_workflow_has_closed_admission_and_permissions() -> None:
    text = _workflow_text()
    for required in (
        "push:",
        "tags:",
        '- "v*"',
        "environment: release",
        "contents: write",
        "packages: write",
        "concurrency:",
        "cancel-in-progress: false",
        r"^v[0-9]+\.[0-9]+\.[0-9]+$",
        "GITHUB_REF_NAME",
        "git rev-list -n 1",
        'if version != "0.1.0":',
    ):
        assert required in text


def test_release_workflow_proves_wheel_and_reference_publication() -> None:
    text = _workflow_text()
    for required in (
        "runs-on: windows-latest",
        "python -m build --wheel --no-isolation --outdir dist-release",
        "vespercode.exe --help",
        "docker/setup-docker-action@v4",
        'version: "v29.1.3"',
        "docker/setup-buildx-action@v3",
        'version: "v0.30.1"',
        "scripts/run_reference_image_smoke.py",
        "ghcr.io/ledstevenovo/vespercode-reference",
        "cf0b6c5ccac588fccd07c3b9f050bff4daf550ac6e518fd06efb6e988ab1d823",
        "docker push",
        "docker pull",
        "gh release create",
        "release-observation.json",
        "actions/upload-artifact@v4",
    ):
        assert required in text


def test_release_workflow_replays_only_an_identical_existing_release() -> None:
    text = _workflow_text()
    for required in (
        "gh release download",
        'test "${#assets[@]}" -eq 2',
        'test "$existing_wheel_sha256" = "$wheel_sha256"',
    ):
        assert required in text

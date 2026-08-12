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
        "GITHUB_REF",
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


def test_release_workflow_has_a_closed_main_only_recovery_admission() -> None:
    text = _workflow_text()
    for required in (
        "workflow_dispatch:",
        'RELEASE_TAG: "v0.1.0"',
        'FROZEN_SOURCE_COMMIT: "d31bdeeafe8ad65b60fac213e23fcab9dffdd7aa"',
        'test "$GITHUB_REF" = "refs/heads/main"',
        'test "$GITHUB_EVENT_NAME" = "workflow_dispatch"',
        "ref: ${{ env.RELEASE_TAG }}",
        'test "$(git rev-list -n 1 "$RELEASE_TAG")" = "$FROZEN_SOURCE_COMMIT"',
    ):
        assert required in text


def test_release_workflow_forces_utf8_for_the_windows_cli_smoke() -> None:
    text = _workflow_text()
    assert 'PYTHONUTF8: "1"' in text


def test_release_workflow_does_not_self_reference_workflow_env_in_job_env() -> None:
    text = _workflow_text()
    assert 'TAG_NAME: "v0.1.0"' in text
    assert "TAG_NAME: ${{ env.RELEASE_TAG }}" not in text

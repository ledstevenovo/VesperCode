"""T02.1 step 2.B: reproducible OCI build and no-self-reference proof."""

from __future__ import annotations

import hashlib
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

import pytest

from spikes.docker_reference_boundary import image_builder
from spikes.docker_reference_boundary.image_builder import (
    BUILD_PLATFORM,
    build_reference_image,
    scan_image_members_for_self_reference,
)
from spikes.docker_reference_boundary.input_contract import (
    ReferenceBuildInputV1,
    freeze_reference_build_input,
)

_FINAL_DIGEST = "ab" * 32
_FINAL_MANIFEST = b'{"schemaVersion":2}'


def reference_root() -> Path:
    return Path(__file__).resolve().parents[3]


@dataclass(frozen=True)
class BuildFixture:
    input: ReferenceBuildInputV1


@pytest.fixture(scope="module")
def build_fixture() -> BuildFixture:
    return BuildFixture(input=freeze_reference_build_input(reference_root()))


def test_final_manifest_is_absent_from_image_members(
    build_fixture: BuildFixture,
) -> None:
    result = build_reference_image(build_fixture.input)
    assert result.self_reference_scan_passed is True


def test_repeated_builds_yield_identical_manifest_digest(
    build_fixture: BuildFixture,
) -> None:
    first = build_reference_image(build_fixture.input)
    second = build_reference_image(build_fixture.input)
    assert first.local_oci_manifest_digest == second.local_oci_manifest_digest
    assert first.image_config_digest == second.image_config_digest
    assert first.recipe_digest == second.recipe_digest
    assert first.platform == second.platform == BUILD_PLATFORM
    assert first.self_reference_scan_passed is True
    assert second.self_reference_scan_passed is True


def test_evidence_binds_real_recipe_identity(
    build_fixture: BuildFixture,
) -> None:
    result = build_reference_image(build_fixture.input)
    recipe = (reference_root() / "containers" / "reference" / "Dockerfile").read_bytes()
    assert result.recipe_digest == hashlib.sha256(recipe).hexdigest()
    assert len(result.local_oci_manifest_digest) == 64
    assert len(result.image_config_digest) == 64
    assert result.platform == "linux/amd64"


def test_builder_rejects_drifted_build_input(
    build_fixture: BuildFixture,
) -> None:
    drifted = ReferenceBuildInputV1(
        base_image_digest="f" * 64,
        registry_image_digest=build_fixture.input.registry_image_digest,
        requirements_digest=build_fixture.input.requirements_digest,
        fixture_tree_digest=build_fixture.input.fixture_tree_digest,
        tool_versions_digest=build_fixture.input.tool_versions_digest,
        build_recipe_version=build_fixture.input.build_recipe_version,
    )
    with pytest.raises(ValueError, match="no longer matches"):
        build_reference_image(drifted)


def test_builder_rejects_recipe_base_image_drift(
    build_fixture: BuildFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        wrong_recipe = Path(tmp) / "Dockerfile"
        wrong_recipe.write_text(
            "FROM python:3.12-slim@sha256:" + "a" * 64 + "\n",
            encoding="utf-8",
        )
        monkeypatch.setattr(image_builder, "_recipe_path", lambda: wrong_recipe)
        with pytest.raises(ValueError, match="recipe base image digest"):
            build_reference_image(build_fixture.input)


def test_builder_rejects_drifted_buildx_version(
    build_fixture: BuildFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fake_run(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        if argv[:2] == ["docker", "buildx"] and argv[2:3] == ["version"]:
            return subprocess.CompletedProcess(
                argv,
                0,
                stdout="github.com/docker/buildx v9.9.9\n",
                stderr="",
            )
        raise AssertionError(f"unexpected subprocess call: {argv!r}")

    monkeypatch.setattr(subprocess, "run", fake_run)
    with pytest.raises(RuntimeError, match="frozen"):
        build_reference_image(build_fixture.input)


def test_layout_blob_digest_mismatch_is_rejected(tmp_path: Path) -> None:
    from spikes.docker_reference_boundary.image_builder import _read_blob

    blob_dir = tmp_path / "blobs" / "sha256"
    blob_dir.mkdir(parents=True)
    digest = "ab" * 32
    (blob_dir / digest).write_bytes(b"tampered")
    with pytest.raises(ValueError, match="digest mismatch"):
        _read_blob(tmp_path, "sha256:" + digest)


def test_scan_passes_for_clean_members() -> None:
    assert (
        scan_image_members_for_self_reference(
            members=(b"layer-one", b'{"os":"linux"}'),
            annotations=(),
            final_manifest_digest=_FINAL_DIGEST,
            final_manifest_bytes=_FINAL_MANIFEST,
        )
        is True
    )


def test_scan_rejects_digest_in_config() -> None:
    config = b'{"history":[{"created_by":"' + _FINAL_DIGEST.encode() + b'"}]}'
    assert (
        scan_image_members_for_self_reference(
            members=(config,),
            annotations=(),
            final_manifest_digest=_FINAL_DIGEST,
            final_manifest_bytes=_FINAL_MANIFEST,
        )
        is False
    )


def test_scan_rejects_digest_prefix_in_layer() -> None:
    layer = b"gzip-data-" + f"sha256:{_FINAL_DIGEST}".encode()
    assert (
        scan_image_members_for_self_reference(
            members=(layer,),
            annotations=(),
            final_manifest_digest=_FINAL_DIGEST,
            final_manifest_bytes=_FINAL_MANIFEST,
        )
        is False
    )


def test_scan_rejects_manifest_bytes_in_layer() -> None:
    assert (
        scan_image_members_for_self_reference(
            members=(_FINAL_MANIFEST,),
            annotations=(),
            final_manifest_digest=_FINAL_DIGEST,
            final_manifest_bytes=_FINAL_MANIFEST,
        )
        is False
    )


def test_scan_rejects_digest_in_annotation() -> None:
    assert (
        scan_image_members_for_self_reference(
            members=(b"layer",),
            annotations=(f"ref={_FINAL_DIGEST}",),
            final_manifest_digest=_FINAL_DIGEST,
            final_manifest_bytes=_FINAL_MANIFEST,
        )
        is False
    )


def test_scan_checks_every_member() -> None:
    assert (
        scan_image_members_for_self_reference(
            members=(b"clean-a", b"clean-b", _FINAL_DIGEST.encode()),
            annotations=(),
            final_manifest_digest=_FINAL_DIGEST,
            final_manifest_bytes=_FINAL_MANIFEST,
        )
        is False
    )

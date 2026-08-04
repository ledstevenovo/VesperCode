"""T01.2 step 1.C: real Windows workspace-object feasibility probes."""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from pathlib import Path

import pytest

from spikes.win32_workspace_boundary.object_probe import (
    BoundaryCaseManifestV1,
    WorkspaceBoundaryCaseV1,
    probe_workspace_objects,
)


@dataclass(frozen=True)
class NtfsFixture:
    root: Path
    safe_file: Path
    ordinary_file: Path
    ordinary_directory: Path
    junction: Path
    hard_link: Path
    ads_path: str


@pytest.fixture
def ntfs_fixture(tmp_path: Path) -> NtfsFixture:
    root = tmp_path / "workspace"
    root.mkdir()
    safe_file = root / "safe.txt"
    safe_file.write_text("safe\n", encoding="utf-8")
    ordinary_file = root / "ordinary.txt"
    ordinary_file.write_text("ordinary\n", encoding="utf-8")
    ordinary_directory = root / "ordinary-directory"
    ordinary_directory.mkdir()
    junction_target = root / "junction-target"
    junction_target.mkdir()
    junction = root / "junction"
    completed = subprocess.run(
        ["cmd.exe", "/d", "/c", "mklink", "/J", str(junction), str(junction_target)],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if completed.returncode != 0:
        pytest.fail(f"junction fixture could not be created: {completed.stderr}")
    hard_link = root / "ordinary-hard-link.txt"
    os.link(ordinary_file, hard_link)
    ads_path = f"{ordinary_file}:vesper-probe"
    with open(ads_path, "w", encoding="utf-8") as stream:
        stream.write("ads\n")
    return NtfsFixture(
        root=root,
        safe_file=safe_file,
        ordinary_file=ordinary_file,
        ordinary_directory=ordinary_directory,
        junction=junction,
        hard_link=hard_link,
        ads_path=ads_path,
    )


def junction_case_manifest() -> BoundaryCaseManifestV1:
    return BoundaryCaseManifestV1(
        cases=(WorkspaceBoundaryCaseV1("REPARSE_OBJECT_REJECTED", "junction"),)
    )


def test_junction_target_identity_is_observed_from_handle(
    ntfs_fixture: NtfsFixture,
) -> None:
    result = probe_workspace_objects(ntfs_fixture.root, junction_case_manifest())
    assert result.observations[0].code == "REPARSE_OBJECT_REJECTED"


def test_object_probe_closes_every_required_boundary_observation(
    ntfs_fixture: NtfsFixture,
) -> None:
    manifest = BoundaryCaseManifestV1(
        cases=(
            WorkspaceBoundaryCaseV1("FILE_OBJECT_OBSERVED", "safe.txt"),
            WorkspaceBoundaryCaseV1("DIRECTORY_OBJECT_OBSERVED", "ordinary-directory"),
            WorkspaceBoundaryCaseV1("REPARSE_OBJECT_REJECTED", "junction"),
            WorkspaceBoundaryCaseV1(
                "HARD_LINK_OBJECT_REJECTED", "ordinary-hard-link.txt"
            ),
            WorkspaceBoundaryCaseV1("ADS_OBJECT_REJECTED", ntfs_fixture.ads_path),
            WorkspaceBoundaryCaseV1("DEVICE_OBJECT_REJECTED", "NUL"),
            WorkspaceBoundaryCaseV1("UNC_OBJECT_REJECTED", r"\\localhost\vesper"),
            WorkspaceBoundaryCaseV1("COLLISION_OBJECT_REJECTED", "safe.txt"),
        )
    )
    result = probe_workspace_objects(ntfs_fixture.root, manifest)
    assert tuple(observation.code for observation in result.observations) == tuple(
        case.code for case in manifest.cases
    )
    assert {observation.object_kind for observation in result.observations} == {
        "FILE",
        "DIRECTORY",
    }
    assert all(observation.acl_observable for observation in result.observations[:4])
    assert all(
        not observation.acl_observable for observation in result.observations[4:7]
    )
    assert result.observations[7].acl_observable is True
    assert result.cleanup_verified is True


def test_object_probe_uses_handle_derived_identity_and_rejects_unproven_cleanup(
    ntfs_fixture: NtfsFixture,
) -> None:
    manifest = BoundaryCaseManifestV1(
        cases=(
            WorkspaceBoundaryCaseV1("FIRST", "ordinary.txt"),
            WorkspaceBoundaryCaseV1("SECOND", "ordinary.txt"),
        )
    )
    result = probe_workspace_objects(ntfs_fixture.root, manifest)
    first, second = result.observations
    assert first.observed_volume_serial != 0
    assert len(first.observed_file_id_128) == 16
    assert first.observed_file_id_128 == second.observed_file_id_128
    assert result.cleanup_verified is True

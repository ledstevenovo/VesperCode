"""T02.3 step 2.D: reference container isolation probe."""

from __future__ import annotations

import dataclasses
import subprocess
import types
from dataclasses import dataclass
from pathlib import Path

import pytest

from spikes.docker_reference_boundary import execution_probe
from spikes.docker_reference_boundary.execution_probe import (
    ContainerIsolationEvidenceV1,
    probe_reference_container,
)
from spikes.docker_reference_boundary.image_builder import (
    ReferenceImageBuildEvidenceV1,
    build_reference_image,
)
from spikes.docker_reference_boundary.input_contract import (
    freeze_reference_build_input,
)

FROZEN_CPU_LIMIT = 2
FROZEN_MEMORY_LIMIT_BYTES = 2147483648
FROZEN_PID_LIMIT = 256
FROZEN_NON_ROOT_UID = 10001
FROZEN_TMPFS_SPEC = "/tmp:rw,size=256m"
FROZEN_TMPFS_OPTIONS = "rw,size=256m"


@dataclass(frozen=True)
class ReferenceContainer:
    build: ReferenceImageBuildEvidenceV1
    fixture: Path


def reference_root() -> Path:
    return Path(__file__).resolve().parents[3]


@pytest.fixture(scope="module")
def reference_container() -> ReferenceContainer:
    build = build_reference_image(freeze_reference_build_input(reference_root()))
    return ReferenceContainer(
        build=build, fixture=reference_root() / "reference" / "fixture"
    )


def test_workspace_write_attempt_is_rejected(
    reference_container: ReferenceContainer,
) -> None:
    evidence = probe_reference_container(
        reference_container.build, reference_container.fixture
    )
    assert evidence.workspace_read_only is True


def test_reference_container_enforces_frozen_isolation_boundary(
    reference_container: ReferenceContainer,
) -> None:
    evidence = probe_reference_container(
        reference_container.build, reference_container.fixture
    )
    assert evidence.network_disabled is True
    assert evidence.non_root is True
    assert evidence.root_read_only is True
    assert evidence.capabilities_dropped is True
    assert evidence.docker_socket_absent is True
    assert evidence.workspace_read_only is True
    assert evidence.tmpfs_bounded is True
    assert evidence.cpu_limit == FROZEN_CPU_LIMIT
    assert evidence.memory_limit_bytes == FROZEN_MEMORY_LIMIT_BYTES
    assert evidence.pid_limit == FROZEN_PID_LIMIT
    assert evidence.cleanup_verified is True
    with pytest.raises(dataclasses.FrozenInstanceError):
        evidence.cpu_limit = 1  # type: ignore[misc]


def test_reference_run_argv_is_frozen_configuration() -> None:
    fixture = reference_root() / "reference" / "fixture"
    image_ref = "sha256:" + "ab" * 32
    argv = execution_probe._reference_run_argv(
        image_ref, fixture, ["python", "-c", "probe"]
    )
    assert argv == [
        "docker",
        "run",
        "-d",
        "--network",
        "none",
        "--user",
        "10001:10001",
        "--read-only",
        "--cap-drop",
        "ALL",
        "--tmpfs",
        FROZEN_TMPFS_SPEC,
        "--cpus",
        "2",
        "--memory",
        "2g",
        "--pids-limit",
        "256",
        "--mount",
        f"type=bind,src={execution_probe._mount_src(fixture)},dst=/workspace,ro",
        image_ref,
        "python",
        "-c",
        "probe",
    ]
    assert "docker.sock" not in " ".join(argv)


def _exact_runtime_observations() -> dict[str, object]:
    return {
        "uid": FROZEN_NON_ROOT_UID,
        "gid": FROZEN_NON_ROOT_UID,
        "cap_eff": "0000000000000000",
        "cap_prm": "0000000000000000",
        "cap_bnd": "0000000000000000",
        "interfaces": ["lo"],
        "route_entries": 0,
        "connect_external_errno": 101,
        "tmp_mounts": [
            {"fs": "tmpfs", "opts": "rw,nosuid,nodev,noexec,relatime,size=262144k"}
        ],
        "cpu_max": "200000 100000",
        "memory_max": "2147483648",
        "pids_max": "256",
        "root_write_errno": 30,
        "workspace_write_errno": 30,
        "workspace_listing": ["pyproject.toml", "requirements.lock", "src", "tests"],
        "docker_sock_var_run": False,
        "docker_sock_run": False,
    }


def _exact_config_observations() -> dict[str, object]:
    return {
        "config_user": "10001:10001",
        "network_mode": "none",
        "readonly_rootfs": True,
        "cap_drop": ["ALL"],
        "tmpfs": {"/tmp": FROZEN_TMPFS_OPTIONS},
        "nano_cpus": 2000000000,
        "memory": FROZEN_MEMORY_LIMIT_BYTES,
        "pids_limit": FROZEN_PID_LIMIT,
        "mounts": [
            {
                "Type": "bind",
                "Source": "D:/fixture",
                "Target": "/workspace",
                "ReadOnly": True,
            }
        ],
    }


def test_reference_container_boundary_matrix(monkeypatch: pytest.MonkeyPatch) -> None:
    """Exact runtime and config observations return one immutable evidence; any
    missing or false observation, a writable workspace, an unbounded resource,
    a present Docker socket, or unverified cleanup closes deterministically
    with no evidence."""
    build = ReferenceImageBuildEvidenceV1(
        local_oci_manifest_digest="ab" * 32,
        image_config_digest="cd" * 32,
        recipe_digest="ef" * 32,
        platform="linux/amd64",
        self_reference_scan_passed=True,
    )
    fixture = reference_root() / "reference" / "fixture"
    image_ref = f"sha256:{build.local_oci_manifest_digest}"
    real_ensure_frozen_image = execution_probe._ensure_frozen_image
    real_observe_container = execution_probe._observe_container

    monkeypatch.setattr(
        execution_probe, "_ensure_frozen_image", lambda build, tar: (image_ref, True)
    )
    monkeypatch.setattr(
        execution_probe, "_reproduce_frozen_layout", lambda tmp: Path("fake.tar")
    )
    monkeypatch.setattr(
        execution_probe,
        "_run_reference_container",
        lambda image_ref, fixture: "fake-container",
    )
    monkeypatch.setattr(
        execution_probe,
        "_observe_container",
        lambda container_id: _exact_runtime_observations(),
    )
    monkeypatch.setattr(
        execution_probe,
        "_inspect_container",
        lambda container_id: _exact_config_observations(),
    )
    monkeypatch.setattr(
        execution_probe, "_cleanup_container", lambda container_id: True
    )
    monkeypatch.setattr(
        execution_probe, "_cleanup_loaded_image", lambda image_ref: True
    )

    # Row 1: exact observations return one immutable closed evidence.
    result = probe_reference_container(build, fixture)
    assert result == ContainerIsolationEvidenceV1(
        network_disabled=True,
        non_root=True,
        root_read_only=True,
        capabilities_dropped=True,
        docker_socket_absent=True,
        workspace_read_only=True,
        tmpfs_bounded=True,
        cpu_limit=FROZEN_CPU_LIMIT,
        memory_limit_bytes=FROZEN_MEMORY_LIMIT_BYTES,
        pid_limit=FROZEN_PID_LIMIT,
        cleanup_verified=True,
    )
    with pytest.raises(dataclasses.FrozenInstanceError):
        result.pid_limit = 1  # type: ignore[misc]

    # Row 2: a missing runtime observation fails closed.
    missing = dict(_exact_runtime_observations())
    missing.pop("cpu_max")
    with pytest.raises(RuntimeError, match="cpu_max"):
        execution_probe._build_evidence(missing, _exact_config_observations())

    # Row 3: a writable workspace fails closed.
    writable = dict(_exact_runtime_observations())
    writable["workspace_write_errno"] = 0
    with pytest.raises(RuntimeError, match="workspace_write_errno"):
        execution_probe._build_evidence(writable, _exact_config_observations())

    # Row 4: an unbounded resource fails closed.
    for key in ("cpu_max", "memory_max", "pids_max"):
        unbounded = dict(_exact_runtime_observations())
        unbounded[key] = "max"
        with pytest.raises(RuntimeError, match=key):
            execution_probe._build_evidence(unbounded, _exact_config_observations())

    # Row 5: a present Docker socket fails closed.
    for key in ("docker_sock_var_run", "docker_sock_run"):
        socket_present = dict(_exact_runtime_observations())
        socket_present[key] = True
        with pytest.raises(RuntimeError, match=key):
            execution_probe._build_evidence(
                socket_present, _exact_config_observations()
            )

    # Row 6: a writable root filesystem fails closed.
    writable_root = dict(_exact_runtime_observations())
    writable_root["root_write_errno"] = 0
    with pytest.raises(RuntimeError, match="root_write_errno"):
        execution_probe._build_evidence(writable_root, _exact_config_observations())

    # Row 7: drifted container configuration fails closed.
    drifted_config = dict(_exact_config_observations())
    drifted_config["network_mode"] = "bridge"
    with pytest.raises(RuntimeError, match="network_mode"):
        execution_probe._build_evidence(_exact_runtime_observations(), drifted_config)

    # Row 7b: any mount beyond the single /workspace bind fails closed, so an
    # authoritative workspace, control-plane database, credential, or backup
    # path cannot be mounted.
    extra_mount_config = dict(_exact_config_observations())
    extra_mount_config["mounts"] = [
        {
            "Type": "bind",
            "Source": "D:/fixture",
            "Target": "/workspace",
            "ReadOnly": True,
        },
        {"Type": "bind", "Source": "D:/secret", "Target": "/creds", "ReadOnly": True},
    ]
    with pytest.raises(RuntimeError, match="mounts"):
        execution_probe._build_evidence(
            _exact_runtime_observations(), extra_mount_config
        )
    wrong_mount_config = dict(_exact_config_observations())
    wrong_mount_config["mounts"] = [
        {
            "Type": "bind",
            "Source": "D:/fixture",
            "Target": "/workspace",
            "ReadOnly": False,
        }
    ]
    with pytest.raises(RuntimeError, match="mounts"):
        execution_probe._build_evidence(
            _exact_runtime_observations(), wrong_mount_config
        )

    # Row 8: unverified container cleanup closes on the success path with no
    # evidence and no rejection claim.
    monkeypatch.setattr(
        execution_probe, "_cleanup_container", lambda container_id: False
    )
    with pytest.raises(RuntimeError, match="cleanup"):
        probe_reference_container(build, fixture)

    # Row 9: unverified cleanup closes on an injected-failure path before any
    # evidence or failure claim.
    monkeypatch.setattr(
        execution_probe, "_cleanup_container", lambda container_id: False
    )
    monkeypatch.setattr(
        execution_probe,
        "_observe_container",
        lambda container_id: dict(
            _exact_runtime_observations(), workspace_write_errno=0
        ),
    )
    with pytest.raises(RuntimeError, match="cleanup"):
        probe_reference_container(build, fixture)

    # Row 10: verified cleanup on an injected-failure path raises the exact
    # closed observation failure with no evidence.
    monkeypatch.setattr(
        execution_probe, "_cleanup_container", lambda container_id: True
    )
    with pytest.raises(RuntimeError, match="workspace_write_errno"):
        probe_reference_container(build, fixture)

    # Row 11: the frozen constants are the execution-profile contract.
    assert execution_probe.CPU_LIMIT == FROZEN_CPU_LIMIT
    assert execution_probe.MEMORY_LIMIT_BYTES == FROZEN_MEMORY_LIMIT_BYTES
    assert execution_probe.MEMORY_ARGV == "2g"
    assert execution_probe.PID_LIMIT == FROZEN_PID_LIMIT
    assert execution_probe.TMPFS_SPEC == FROZEN_TMPFS_SPEC
    assert execution_probe.NON_ROOT_UID == FROZEN_NON_ROOT_UID

    # Row 12: non-JSON or non-object observation output fails closed.
    def fake_docker_runner(stdout: str, *, wait_stdout: str = "0") -> object:
        def run(
            argv: list[str],
            capture_output: bool = True,
            text: bool = True,
            timeout: int | None = None,
        ) -> object:
            if argv[:2] == ["docker", "wait"]:
                return types.SimpleNamespace(
                    returncode=0, stdout=wait_stdout, stderr=""
                )
            if argv[:2] == ["docker", "logs"]:
                return types.SimpleNamespace(returncode=0, stdout=stdout, stderr="")
            raise AssertionError(f"unexpected argv: {argv}")

        return run

    monkeypatch.setattr(subprocess, "run", fake_docker_runner("not-json"))
    with pytest.raises(RuntimeError, match="not valid JSON"):
        real_observe_container("fake-container")
    monkeypatch.setattr(subprocess, "run", fake_docker_runner('"just-a-string"'))
    with pytest.raises(RuntimeError, match="must be an object"):
        real_observe_container("fake-container")

    # Row 13: a non-zero observation exit fails closed.
    monkeypatch.setattr(subprocess, "run", fake_docker_runner("{}", wait_stdout="1"))
    with pytest.raises(RuntimeError, match="exited with code 1"):
        real_observe_container("fake-container")

    # Row 14: unverified loaded-image cleanup closes on the success path.
    monkeypatch.setattr(
        execution_probe, "_cleanup_loaded_image", lambda image_ref: False
    )
    monkeypatch.setattr(
        execution_probe,
        "_observe_container",
        lambda container_id: _exact_runtime_observations(),
    )
    with pytest.raises(RuntimeError, match="cleanup"):
        probe_reference_container(build, fixture)

    # Row 15: a load reporting a drifted identity removes the drifted image
    # before failing closed, so no residue is left on the drift path.
    drifted_id = "sha256:" + "ff" * 32
    removed: list[str] = []

    def record_removed(image_ref: str) -> bool:
        removed.append(image_ref)
        return True

    monkeypatch.setattr(
        execution_probe, "_ensure_frozen_image", real_ensure_frozen_image
    )
    monkeypatch.setattr(execution_probe, "_image_id", lambda ref: None)
    monkeypatch.setattr(execution_probe, "_load_image", lambda tar: drifted_id)
    monkeypatch.setattr(execution_probe, "_cleanup_loaded_image", record_removed)
    with pytest.raises(RuntimeError, match="identity"):
        execution_probe._ensure_frozen_image(build, Path("fake.tar"))
    assert removed == [drifted_id]

"""T02.4 step 2.G: reference profile manifest and Docker boundary GO report.

``assemble_reference_gate_report`` emits GO only when build, registry,
isolation, pytest, and fingerprint evidence are complete and
identity-consistent; every missing, drifted, or transformed input yields
NO_GO without rewriting any evidence.
"""

from __future__ import annotations

import dataclasses
import json
import tempfile
from pathlib import Path

import pytest

from spikes.docker_reference_boundary import report as report_module
from spikes.docker_reference_boundary.execution_probe import (
    ContainerIsolationEvidenceV1,
)
from spikes.docker_reference_boundary.failure_fingerprint_probe import (
    CanonicalGateLocationV1,
    GateFailureFingerprintInputV1,
    GateFingerprintComparisonV1,
    compare_failure_inputs,
)
from spikes.docker_reference_boundary.image_builder import (
    ReferenceImageBuildEvidenceV1,
)
from spikes.docker_reference_boundary.input_contract import (
    ReferenceBuildInputV1,
)
from spikes.docker_reference_boundary import probe as probe_module
from spikes.docker_reference_boundary.probe import run_reference_gate
from spikes.docker_reference_boundary.pytest_reporter import (
    GatePytestEvidenceResultV1,
)
from spikes.docker_reference_boundary.registry_probe import (
    LoopbackRegistryEvidenceV1,
)
from spikes.docker_reference_boundary.report import (
    AssembleReferenceGateReportV1,
    DockerBoundaryGateReportV1,
    GateToolchainEvidenceV1,
    assemble_reference_gate_report,
    builtin_editable_path_policy,
    compute_editable_path_policy_digest,
    compute_gate_toolchain_evidence_digest,
    compute_reference_profile_manifest_digest,
    freeze_reference_profile_manifest,
    load_gate_toolchain_evidence,
    load_reference_profile_manifest,
)

_IMAGE_DIGEST = "cd" * 32
_CONFIG_DIGEST = "ef" * 32
_RECIPE_DIGEST = "12" * 32
_REQUIREMENTS_DIGEST = (
    "67a6b630fb418344bea58ed0b98c1006391bbc947b36356188a1e01fa5fe9a64"
)
_TOOL_VERSIONS_DIGEST = (
    "43d540528421603981f612ff396d2ae66610cd9be61a8450f403b61374720f0a"
)
_REGISTRY_IMAGE_DIGEST = (
    "a3d8aaa63ed8681a604f1dea0aa03f100d5895b6a58ace528858a7b332415373"
)
_NODE_ADD = "tests/test_calculator.py::test_add_returns_sum"


def reference_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _build_input() -> ReferenceBuildInputV1:
    return ReferenceBuildInputV1(
        base_image_digest="57cd7c3a7a273101a6485ba99423ee568157882804b1124b4dd04266317710de",
        registry_image_digest=_REGISTRY_IMAGE_DIGEST,
        requirements_digest=_REQUIREMENTS_DIGEST,
        fixture_tree_digest="55" * 32,
        tool_versions_digest=_TOOL_VERSIONS_DIGEST,
        build_recipe_version="1",
    )


def _build_evidence() -> ReferenceImageBuildEvidenceV1:
    return ReferenceImageBuildEvidenceV1(
        local_oci_manifest_digest=_IMAGE_DIGEST,
        image_config_digest=_CONFIG_DIGEST,
        recipe_digest=_RECIPE_DIGEST,
        platform="linux/amd64",
        self_reference_scan_passed=True,
    )


def _registry_evidence() -> LoopbackRegistryEvidenceV1:
    return LoopbackRegistryEvidenceV1(
        registry_image_digest=_REGISTRY_IMAGE_DIGEST,
        bind_host="127.0.0.1",
        assigned_port=5000,
        credentials_used=False,
        external_push_count=0,
        local_oci_manifest_digest=_IMAGE_DIGEST,
        registry_repo_digest=_IMAGE_DIGEST,
        digest_pull_repo_digest=_IMAGE_DIGEST,
        cleanup_verified=True,
    )


def _isolation_evidence() -> ContainerIsolationEvidenceV1:
    return ContainerIsolationEvidenceV1(
        network_disabled=True,
        non_root=True,
        root_read_only=True,
        capabilities_dropped=True,
        docker_socket_absent=True,
        workspace_read_only=True,
        tmpfs_bounded=True,
        cpu_limit=2,
        memory_limit_bytes=2147483648,
        pid_limit=256,
        cleanup_verified=True,
    )


def _pytest_evidence() -> GatePytestEvidenceResultV1:
    return GatePytestEvidenceResultV1(passed=True, reason="COMPLETE")


def _fingerprint() -> GateFingerprintComparisonV1:
    left = GateFailureFingerprintInputV1(
        node_id=_NODE_ADD,
        phase="CALL",
        outcome="FAIL",
        normalized_message="assert <object object at <ADDRESS>> is None",
        location=CanonicalGateLocationV1(
            relative_path="tests/test_calculator.py",
            function_name="test_add_returns_sum",
            line_number=2,
        ),
    )
    return compare_failure_inputs(left, left)


def _toolchain() -> GateToolchainEvidenceV1:
    base = GateToolchainEvidenceV1(
        schema_version=1,
        evidence_digest="",
        evidence_type="GATE_TOOLCHAIN_EVIDENCE_V1",
        gate_input_sha256="70" * 32,
        gate_lock_sha256="71" * 32,
        gate_scan_core_sha256="72" * 32,
        gate_scan_sha256="73" * 32,
        mypy_config_sha256="74" * 32,
        mypy_version="2.3.0",
        pytest_config_sha256="75" * 32,
        pytest_version="8.4.2",
        python_version="3.12.4",
        ruff_config_sha256="76" * 32,
        ruff_version="0.16.1",
        runner_sha256="77" * 32,
    )
    return dataclasses.replace(
        base, evidence_digest=compute_gate_toolchain_evidence_digest(base)
    )


def complete_command() -> AssembleReferenceGateReportV1:
    """One internally consistent command whose manifest is the exact derived
    freeze of the evidence below."""
    build_input = _build_input()
    build = _build_evidence()
    toolchain = _toolchain()
    with tempfile.TemporaryDirectory(prefix="vesper-gate-report-") as tmp:
        manifest = freeze_reference_profile_manifest(
            build_input, build, toolchain, Path(tmp) / "manifest.json"
        )
    return AssembleReferenceGateReportV1(
        manifest=manifest,
        build_input=build_input,
        build=build,
        registry=_registry_evidence(),
        isolation=_isolation_evidence(),
        pytest_evidence=_pytest_evidence(),
        fingerprint=_fingerprint(),
        gate_toolchain=toolchain,
    )


def mismatched_digest_command() -> AssembleReferenceGateReportV1:
    """One complete command whose registry RepoDigest is drifted."""
    command = complete_command()
    drifted = dataclasses.replace(command.registry, registry_repo_digest="ff" * 32)
    return dataclasses.replace(command, registry=drifted)


def _with_recomputed_manifest(
    command: AssembleReferenceGateReportV1, **fields: object
) -> AssembleReferenceGateReportV1:
    """A manifest with one drifted field and its digest recomputed, exactly
    like a real attacker would produce."""
    manifest = dataclasses.replace(command.manifest, **fields)  # type: ignore[arg-type]
    manifest = dataclasses.replace(
        manifest, digest=compute_reference_profile_manifest_digest(manifest)
    )
    return dataclasses.replace(command, manifest=manifest)


def _with_recomputed_policy(
    command: AssembleReferenceGateReportV1, **fields: object
) -> AssembleReferenceGateReportV1:
    policy = dataclasses.replace(
        command.manifest.editable_path_policy,
        **fields,  # type: ignore[arg-type]
    )
    policy = dataclasses.replace(
        policy, digest=compute_editable_path_policy_digest(policy)
    )
    manifest = dataclasses.replace(command.manifest, editable_path_policy=policy)
    manifest = dataclasses.replace(
        manifest, digest=compute_reference_profile_manifest_digest(manifest)
    )
    return dataclasses.replace(command, manifest=manifest)


def test_reference_pytest_run_argv_is_frozen_configuration() -> None:
    fixture = reference_root() / "reference" / "fixture"
    spikes = reference_root() / "spikes"
    argv = probe_module._pytest_run_argv(
        "sha256:" + "ab" * 32,
        fixture,
        spikes,
        collect_only=False,
        target_node_ids=None,
    )
    assert argv[:2] == ["docker", "run"]
    assert argv[argv.index("--network") + 1] == "none"
    assert argv[argv.index("--user") + 1] == "10001:10001"
    assert "--read-only" in argv
    assert argv[argv.index("--cap-drop") + 1] == "ALL"
    assert argv[argv.index("--workdir") + 1] == "/workspace"
    assert argv[argv.index("-p") + 1] == (
        "spikes.docker_reference_boundary.pytest_reporter"
    )
    assert argv[argv.index("-c") + 1] == "/dev/null"
    env_indexes = [index for index, arg in enumerate(argv) if arg == "--env"]
    env = dict(argv[index + 1].split("=", 1) for index in env_indexes)
    assert env["PYTHONPATH"] == "/gate:/workspace/src"
    assert env["REPORT_CHANNEL"] == "/tmp/gate-events.jsonl"
    assert env["PYTHONHASHSEED"] == "0"
    assert env["TZ"] == "UTC"
    assert env["LANG"] == "C.UTF-8"
    assert env["LC_ALL"] == "C.UTF-8"
    assert env["PYTHONDONTWRITEBYTECODE"] == "1"
    assert "docker.sock" not in " ".join(argv)
    target_argv = probe_module._pytest_run_argv(
        "sha256:" + "ab" * 32,
        fixture,
        spikes,
        collect_only=True,
        target_node_ids=("tests/test_calculator.py::test_add_returns_sum",),
    )
    assert "--collect-only" in target_argv
    assert "/workspace/tests/test_calculator.py::test_add_returns_sum" in target_argv


def test_gate_rejects_loopback_registry_digest_mismatch() -> None:
    assert (
        assemble_reference_gate_report(mismatched_digest_command()).outcome == "NO_GO"
    )


def test_complete_evidence_yields_go() -> None:
    report = assemble_reference_gate_report(complete_command())
    assert report.outcome == "GO"
    assert len(report.evidence_digest) == 64
    assert assemble_reference_gate_report(complete_command()).evidence_digest == (
        report.evidence_digest
    )


def test_reference_gate_upstream_consistency_matrix() -> None:
    """Complete matching evidence yields GO; every missing, drifted, or
    transformed input yields NO_GO with its stable reason."""
    complete = complete_command()
    assert assemble_reference_gate_report(complete).outcome == "GO"

    def no_go(command: AssembleReferenceGateReportV1, reason: str) -> None:
        result = assemble_reference_gate_report(command)
        assert result.outcome == "NO_GO", reason
        assert report_module._identity_failure_reason(command) == reason

    # The manifest's own §0.1 identity is tamper-evident.
    no_go(
        dataclasses.replace(
            complete, manifest=dataclasses.replace(complete.manifest, digest="00" * 32)
        ),
        report_module.REASON_MANIFEST_DIGEST,
    )
    # Every drifted manifest field with its digest recomputed.
    no_go(
        _with_recomputed_manifest(complete, docker_image_digest="dd" * 32),
        report_module.REASON_IMAGE,
    )
    no_go(
        _with_recomputed_manifest(complete, requirements_lock_digest="ee" * 32),
        report_module.REASON_REQUIREMENTS,
    )
    no_go(
        _with_recomputed_manifest(complete, pytest_version="9.0.0"),
        report_module.REASON_TOOL_VERSION,
    )
    no_go(
        _with_recomputed_manifest(complete, report_plugin_version="2"),
        report_module.REASON_PROFILE_VERSION,
    )
    no_go(
        _with_recomputed_manifest(complete, check_plan_version="2"),
        report_module.REASON_PROFILE_VERSION,
    )
    no_go(
        _with_recomputed_policy(complete, policy_id="NOT_BUILTIN_V1"),
        report_module.REASON_POLICY_NOT_BUILTIN,
    )
    tampered_policy = dataclasses.replace(
        complete.manifest.editable_path_policy, digest="00" * 32
    )
    tampered_manifest = dataclasses.replace(
        complete.manifest, editable_path_policy=tampered_policy
    )
    tampered_manifest = dataclasses.replace(
        tampered_manifest,
        digest=compute_reference_profile_manifest_digest(tampered_manifest),
    )
    no_go(
        dataclasses.replace(complete, manifest=tampered_manifest),
        report_module.REASON_POLICY_DIGEST,
    )
    no_go(
        _with_recomputed_policy(complete, editable_directory_roots=("src", "src2")),
        report_module.REASON_POLICY_NOT_BUILTIN,
    )
    # Registry identity transformations.
    no_go(mismatched_digest_command(), report_module.REASON_REGISTRY_DIGEST)
    no_go(
        dataclasses.replace(
            complete,
            registry=dataclasses.replace(
                complete.registry,
                credentials_used=True,  # type: ignore[arg-type]
            ),
        ),
        report_module.REASON_REGISTRY_CREDENTIALS,
    )
    no_go(
        dataclasses.replace(
            complete,
            registry=dataclasses.replace(
                complete.registry,
                external_push_count=1,  # type: ignore[arg-type]
            ),
        ),
        report_module.REASON_REGISTRY_PUSH,
    )
    no_go(
        dataclasses.replace(
            complete,
            registry=dataclasses.replace(complete.registry, cleanup_verified=False),
        ),
        report_module.REASON_REGISTRY_CLEANUP,
    )
    no_go(
        dataclasses.replace(
            complete,
            registry=dataclasses.replace(
                complete.registry, registry_image_digest="aa" * 32
            ),
        ),
        report_module.REASON_REGISTRY_IMAGE,
    )
    no_go(
        dataclasses.replace(
            complete,
            registry=dataclasses.replace(
                complete.registry, digest_pull_repo_digest="ab" * 32
            ),
        ),
        report_module.REASON_REGISTRY_DIGEST,
    )
    # Build evidence transformations.
    no_go(
        dataclasses.replace(
            complete,
            build=dataclasses.replace(complete.build, self_reference_scan_passed=False),
        ),
        report_module.REASON_SELF_REFERENCE,
    )
    no_go(
        dataclasses.replace(
            complete,
            build=dataclasses.replace(complete.build, platform="linux/arm64"),
        ),
        report_module.REASON_PLATFORM,
    )
    # Isolation evidence transformations.
    no_go(
        dataclasses.replace(
            complete,
            isolation=dataclasses.replace(complete.isolation, network_disabled=False),
        ),
        report_module.REASON_ISOLATION,
    )
    no_go(
        dataclasses.replace(
            complete,
            isolation=dataclasses.replace(
                complete.isolation, workspace_read_only=False
            ),
        ),
        report_module.REASON_ISOLATION,
    )
    no_go(
        dataclasses.replace(
            complete,
            isolation=dataclasses.replace(complete.isolation, cpu_limit=1),
        ),
        report_module.REASON_ISOLATION_LIMITS,
    )
    no_go(
        dataclasses.replace(
            complete,
            isolation=dataclasses.replace(
                complete.isolation, memory_limit_bytes=1073741824
            ),
        ),
        report_module.REASON_ISOLATION_LIMITS,
    )
    no_go(
        dataclasses.replace(
            complete,
            isolation=dataclasses.replace(complete.isolation, cleanup_verified=False),
        ),
        report_module.REASON_ISOLATION_CLEANUP,
    )
    # Pytest evidence transformations.
    no_go(
        dataclasses.replace(
            complete,
            pytest_evidence=GatePytestEvidenceResultV1(
                passed=False, reason="MISSING_END_MARKER"
            ),
        ),
        report_module.REASON_PYTEST,
    )
    # Fingerprint transformations.
    no_go(
        dataclasses.replace(
            complete,
            fingerprint=dataclasses.replace(complete.fingerprint, equal=False),
        ),
        report_module.REASON_FINGERPRINT,
    )
    no_go(
        dataclasses.replace(
            complete,
            fingerprint=dataclasses.replace(
                complete.fingerprint, left_digest="ab" * 32
            ),
        ),
        report_module.REASON_FINGERPRINT_DIGESTS,
    )
    # Toolchain transformations.
    no_go(
        dataclasses.replace(
            complete,
            gate_toolchain=dataclasses.replace(
                complete.gate_toolchain, evidence_digest="00" * 32
            ),
        ),
        report_module.REASON_TOOLCHAIN,
    )
    drifted_toolchain = dataclasses.replace(
        complete.gate_toolchain, python_version="3.12.999"
    )
    drifted_toolchain = dataclasses.replace(
        drifted_toolchain,
        evidence_digest=compute_gate_toolchain_evidence_digest(drifted_toolchain),
    )
    no_go(
        dataclasses.replace(complete, gate_toolchain=drifted_toolchain),
        report_module.REASON_TOOL_VERSION,
    )
    wrong_type_toolchain = dataclasses.replace(
        complete.gate_toolchain, evidence_type="GATE_TOOLCHAIN_EVIDENCE_V2"
    )
    wrong_type_toolchain = dataclasses.replace(
        wrong_type_toolchain,
        evidence_digest=compute_gate_toolchain_evidence_digest(wrong_type_toolchain),
    )
    no_go(
        dataclasses.replace(complete, gate_toolchain=wrong_type_toolchain),
        report_module.REASON_TOOLCHAIN_TYPE,
    )
    # The T02.1-to-T01.1 tool binding.
    no_go(
        dataclasses.replace(
            complete,
            build_input=dataclasses.replace(
                complete.build_input, tool_versions_digest="aa" * 32
            ),
        ),
        report_module.REASON_BUILD_INPUT_TOOLCHAIN,
    )


def test_freeze_writes_exact_bytes_and_round_trips(tmp_path: Path) -> None:
    manifest_path = tmp_path / "reference-profile-v1.json"
    manifest = freeze_reference_profile_manifest(
        _build_input(), _build_evidence(), _toolchain(), manifest_path
    )
    raw = manifest_path.read_bytes()
    assert raw == manifest_path.read_bytes()
    parsed = json.loads(raw.decode("utf-8"))
    assert parsed["profile_id"] == "python-src-py312-v1"
    assert parsed["schema_version"] == 1
    assert parsed["docker_execution_profile_version"] == 1
    assert parsed["docker_image_digest"] == _IMAGE_DIGEST
    assert parsed["requirements_lock_digest"] == _REQUIREMENTS_DIGEST
    assert parsed["python_version"] == "3.12.4"
    assert parsed["pytest_version"] == "8.4.2"
    assert parsed["ruff_version"] == "0.16.1"
    assert parsed["mypy_version"] == "2.3.0"
    assert parsed["editable_path_policy"]["policy_id"] == "PYTHON_SRC_ONLY_V1"
    assert parsed["editable_path_policy"]["editable_directory_roots"] == ["src"]
    assert parsed["editable_path_policy"]["allowed_operations"] == ["CREATE", "REPLACE"]
    loaded = load_reference_profile_manifest(manifest_path)
    assert loaded == manifest
    assert compute_reference_profile_manifest_digest(loaded) == loaded.digest
    assert loaded.editable_path_policy == builtin_editable_path_policy()


def test_freeze_never_writes_on_drifted_evidence(tmp_path: Path) -> None:
    manifest_path = tmp_path / "reference-profile-v1.json"
    drifted_input = dataclasses.replace(_build_input(), tool_versions_digest="aa" * 32)
    with pytest.raises(ValueError, match="tool versions"):
        freeze_reference_profile_manifest(
            drifted_input, _build_evidence(), _toolchain(), manifest_path
        )
    assert not manifest_path.exists()


def test_loaders_reject_malformed_evidence(tmp_path: Path) -> None:
    manifest_path = tmp_path / "reference-profile-v1.json"
    freeze_reference_profile_manifest(
        _build_input(), _build_evidence(), _toolchain(), manifest_path
    )
    raw = json.loads(manifest_path.read_bytes().decode("utf-8"))
    tampered = dict(raw)
    tampered.pop("digest")
    manifest_path.write_bytes(json.dumps(tampered).encode("utf-8"))
    with pytest.raises(ValueError, match="invalid field set"):
        load_reference_profile_manifest(manifest_path)
    tampered = dict(raw, digest="00" * 32)
    manifest_path.write_bytes(json.dumps(tampered).encode("utf-8"))
    with pytest.raises(ValueError, match="digest mismatch"):
        load_reference_profile_manifest(manifest_path)
    tampered = dict(raw, schema_version="1")
    manifest_path.write_bytes(json.dumps(tampered).encode("utf-8"))
    with pytest.raises(ValueError, match="schema_version"):
        load_reference_profile_manifest(manifest_path)
    tampered = dict(raw, docker_image_digest="zz" * 32)
    manifest_path.write_bytes(json.dumps(tampered).encode("utf-8"))
    with pytest.raises(ValueError, match="docker_image_digest"):
        load_reference_profile_manifest(manifest_path)
    manifest_path.write_text("not json", encoding="utf-8")
    with pytest.raises(ValueError, match="not valid JSON"):
        load_reference_profile_manifest(manifest_path)

    toolchain_path = tmp_path / "gate-toolchain-v1.json"
    toolchain = _toolchain()
    toolchain_path.write_bytes(
        json.dumps(dataclasses.asdict(toolchain)).encode("utf-8")
    )
    assert load_gate_toolchain_evidence(toolchain_path) == toolchain
    drifted = dict(dataclasses.asdict(toolchain))
    drifted.pop("evidence_digest")
    toolchain_path.write_bytes(json.dumps(drifted).encode("utf-8"))
    with pytest.raises(ValueError, match="invalid field set"):
        load_gate_toolchain_evidence(toolchain_path)
    drifted = dict(dataclasses.asdict(toolchain), evidence_digest="00" * 32)
    toolchain_path.write_bytes(json.dumps(drifted).encode("utf-8"))
    with pytest.raises(ValueError, match="digest mismatch"):
        load_gate_toolchain_evidence(toolchain_path)


@pytest.fixture(scope="module")
def real_go_report() -> DockerBoundaryGateReportV1:
    return run_reference_gate(reference_root())


def test_reference_gate_go_report_with_real_evidence(
    real_go_report: DockerBoundaryGateReportV1,
) -> None:
    report = real_go_report
    assert report.outcome == "GO"
    assert len(report.evidence_digest) == 64
    assert report.build.self_reference_scan_passed is True
    assert report.registry.credentials_used is False
    assert report.registry.external_push_count == 0
    assert report.registry.cleanup_verified is True
    assert report.isolation.cleanup_verified is True
    assert report.pytest_evidence.passed is True
    assert report.fingerprint.equal is True
    manifest_path = (
        reference_root() / "reference" / "manifest" / "reference-profile-v1.json"
    )
    assert manifest_path.is_file()
    manifest = load_reference_profile_manifest(manifest_path)
    assert compute_reference_profile_manifest_digest(manifest) == manifest.digest
    assert (
        manifest.docker_image_digest
        == report.build.local_oci_manifest_digest
        == report.registry.registry_repo_digest
        == "86443f5297b268f0cd8046b09652acb3b6b1d7e4275a743c34e7908bf1d7156d"
    )
    assert (
        manifest.requirements_lock_digest
        == "67a6b630fb418344bea58ed0b98c1006391bbc947b36356188a1e01fa5fe9a64"
    )
    assert manifest.python_version == "3.12.4"
    assert manifest.pytest_version == "8.4.2"
    assert manifest.ruff_version == "0.16.1"
    assert manifest.mypy_version == "2.3.0"
    assert manifest.editable_path_policy == builtin_editable_path_policy()

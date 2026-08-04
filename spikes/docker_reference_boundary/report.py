"""T02.4 legacy step 2.G: reference profile manifest and Docker boundary GO.

Freezes the exact ``ReferenceProfileManifestV1`` bytes from the frozen
build-input, build, and gate-toolchain evidence, and emits one immutable
``DockerBoundaryGateReportV1`` with outcome GO only when build, registry,
isolation, pytest, and fingerprint evidence are complete and
identity-consistent.  Any missing, drifted, or transformed digest produces
NO_GO without rewriting any evidence.

Owns final manifest/report bytes and the GO/NO_GO decision only.  Rebuilding,
re-running, rewriting, authenticating to, or externally publishing upstream
evidence remains out of scope: this module never touches a daemon, registry,
container, or pytest process.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from spikes.docker_reference_boundary.execution_probe import (
    ContainerIsolationEvidenceV1,
)
from spikes.docker_reference_boundary.failure_fingerprint_probe import (
    GateFingerprintComparisonV1,
)
from spikes.docker_reference_boundary.image_builder import (
    ReferenceImageBuildEvidenceV1,
)
from spikes.docker_reference_boundary.input_contract import (
    ReferenceBuildInputV1,
)
from spikes.docker_reference_boundary.pytest_reporter import (
    GATE_REPORTER_VERSION,
    GatePytestEvidenceResultV1,
    _domain_separated_digest,
)
from spikes.docker_reference_boundary.registry_probe import (
    LoopbackRegistryEvidenceV1,
)

PROFILE_ID = "python-src-py312-v1"
POLICY_ID = "PYTHON_SRC_ONLY_V1"
EDITABLE_DIRECTORY_ROOTS = ("src",)
ALLOWED_OPERATIONS = ("CREATE", "REPLACE")
CHECK_PLAN_VERSION = "1"
TOOLCHAIN_EVIDENCE_TYPE = "GATE_TOOLCHAIN_EVIDENCE_V1"

_SHA256 = hashlib.sha256
_HEX_CHARS = frozenset("0123456789abcdef")
_OPERATIONS = frozenset(("CREATE", "REPLACE"))

# Stable closed NO_GO reasons (the complete vocabulary of the GO predicate).
REASON_MANIFEST_DIGEST = "MANIFEST_DIGEST_MISMATCH"
REASON_POLICY_DIGEST = "POLICY_DIGEST_MISMATCH"
REASON_POLICY_NOT_BUILTIN = "POLICY_NOT_BUILTIN"
REASON_REQUIREMENTS = "REQUIREMENTS_DIGEST_MISMATCH"
REASON_IMAGE = "IMAGE_DIGEST_MISMATCH"
REASON_TOOL_VERSION = "TOOL_VERSION_MISMATCH"
REASON_PROFILE_VERSION = "PROFILE_VERSION_MISMATCH"
REASON_TOOLCHAIN = "TOOLCHAIN_DIGEST_MISMATCH"
REASON_BUILD_INPUT_TOOLCHAIN = "BUILD_INPUT_TOOLCHAIN_MISMATCH"
REASON_REGISTRY_IMAGE = "REGISTRY_IMAGE_MISMATCH"
REASON_REGISTRY_DIGEST = "REGISTRY_DIGEST_MISMATCH"
REASON_REGISTRY_CREDENTIALS = "REGISTRY_CREDENTIALS_USED"
REASON_REGISTRY_PUSH = "REGISTRY_EXTERNAL_PUSH"
REASON_REGISTRY_CLEANUP = "REGISTRY_CLEANUP_UNVERIFIED"
REASON_SELF_REFERENCE = "SELF_REFERENCE_SCAN_FAILED"
REASON_PLATFORM = "PLATFORM_MISMATCH"
REASON_ISOLATION = "ISOLATION_NOT_ENFORCED"
REASON_ISOLATION_LIMITS = "ISOLATION_LIMITS_DRIFTED"
REASON_ISOLATION_CLEANUP = "ISOLATION_CLEANUP_UNVERIFIED"
REASON_PYTEST = "PYTEST_EVIDENCE_INCOMPLETE"
REASON_FINGERPRINT = "FINGERPRINT_DIFFERS"
REASON_FINGERPRINT_DIGESTS = "FINGERPRINT_DIGESTS_DIFFER"
REASON_TOOLCHAIN_TYPE = "TOOLCHAIN_TYPE_MISMATCH"


@dataclass(frozen=True)
class EditablePathPolicyV1:
    """The built-in editable path policy (SPEC §1.4.1)."""

    schema_version: int
    policy_id: str
    editable_directory_roots: tuple[str, ...]
    allowed_operations: tuple[str, ...]
    digest: str


@dataclass(frozen=True)
class GateToolchainEvidenceV1:
    """One immutable gate toolchain evidence record (T01.1)."""

    schema_version: int
    evidence_digest: str
    evidence_type: str
    gate_input_sha256: str
    gate_lock_sha256: str
    gate_scan_core_sha256: str
    gate_scan_sha256: str
    mypy_config_sha256: str
    mypy_version: str
    pytest_config_sha256: str
    pytest_version: str
    python_version: str
    ruff_config_sha256: str
    ruff_version: str
    runner_sha256: str


@dataclass(frozen=True)
class ReferenceProfileManifestV1:
    """The frozen python-src-py312-v1 profile manifest (SPEC §1.4.1)."""

    schema_version: int
    profile_id: str
    requirements_lock_digest: str
    docker_image_digest: str
    docker_execution_profile_version: int
    python_version: str
    pytest_version: str
    report_plugin_version: str
    ruff_version: str
    mypy_version: str
    check_plan_version: str
    editable_path_policy: EditablePathPolicyV1
    digest: str


@dataclass(frozen=True)
class AssembleReferenceGateReportV1:
    """The closed command: every producer's evidence plus the frozen manifest."""

    manifest: ReferenceProfileManifestV1
    build_input: ReferenceBuildInputV1
    build: ReferenceImageBuildEvidenceV1
    registry: LoopbackRegistryEvidenceV1
    isolation: ContainerIsolationEvidenceV1
    pytest_evidence: GatePytestEvidenceResultV1
    fingerprint: GateFingerprintComparisonV1
    gate_toolchain: GateToolchainEvidenceV1


@dataclass(frozen=True)
class DockerBoundaryGateReportV1:
    """One immutable Docker boundary GO/NO_GO report."""

    outcome: Literal["GO", "NO_GO"]
    build_input: ReferenceBuildInputV1
    build: ReferenceImageBuildEvidenceV1
    registry: LoopbackRegistryEvidenceV1
    isolation: ContainerIsolationEvidenceV1
    pytest_evidence: GatePytestEvidenceResultV1
    fingerprint: GateFingerprintComparisonV1
    gate_toolchain: GateToolchainEvidenceV1
    evidence_digest: str


def _canonical_json_bytes(obj: object) -> bytes:
    """Deterministic compact UTF-8 JSON with sorted keys (SPEC §0.1)."""
    return json.dumps(
        obj, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def _validate_digest(value: object, field: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or not all(char in _HEX_CHARS for char in value)
    ):
        raise ValueError(f"{field} must be a 64 lowercase hex digest")
    return value


def _policy_body(policy: EditablePathPolicyV1) -> dict[str, object]:
    return {
        "schema_version": policy.schema_version,
        "policy_id": policy.policy_id,
        "editable_directory_roots": list(policy.editable_directory_roots),
        "allowed_operations": list(policy.allowed_operations),
    }


def compute_editable_path_policy_digest(policy: EditablePathPolicyV1) -> str:
    """The SPEC §0.1 identity of one editable path policy."""
    return _domain_separated_digest("EditablePathPolicyV1", 1, _policy_body(policy))


def builtin_editable_path_policy() -> EditablePathPolicyV1:
    """The sole built-in policy instance (SPEC §1.4.1)."""
    policy = EditablePathPolicyV1(
        schema_version=1,
        policy_id=POLICY_ID,
        editable_directory_roots=EDITABLE_DIRECTORY_ROOTS,
        allowed_operations=ALLOWED_OPERATIONS,
        digest="",
    )
    return dataclasses.replace(
        policy, digest=compute_editable_path_policy_digest(policy)
    )


def _manifest_body(manifest: ReferenceProfileManifestV1) -> dict[str, object]:
    return {
        "schema_version": manifest.schema_version,
        "profile_id": manifest.profile_id,
        "requirements_lock_digest": manifest.requirements_lock_digest,
        "docker_image_digest": manifest.docker_image_digest,
        "docker_execution_profile_version": manifest.docker_execution_profile_version,
        "python_version": manifest.python_version,
        "pytest_version": manifest.pytest_version,
        "report_plugin_version": manifest.report_plugin_version,
        "ruff_version": manifest.ruff_version,
        "mypy_version": manifest.mypy_version,
        "check_plan_version": manifest.check_plan_version,
        "editable_path_policy": {
            **_policy_body(manifest.editable_path_policy),
            "digest": manifest.editable_path_policy.digest,
        },
    }


def compute_reference_profile_manifest_digest(
    manifest: ReferenceProfileManifestV1,
) -> str:
    """The SPEC §0.1 identity of one frozen profile manifest."""
    return _domain_separated_digest(
        "ReferenceProfileManifestV1", 1, _manifest_body(manifest)
    )


def _tool_versions_digest(toolchain: GateToolchainEvidenceV1) -> str:
    """The T02.1 tool-version binding convention (indent-2 canonical JSON)."""
    versions = {
        "python_version": toolchain.python_version,
        "pytest_version": toolchain.pytest_version,
        "ruff_version": toolchain.ruff_version,
        "mypy_version": toolchain.mypy_version,
    }
    return _SHA256(
        json.dumps(
            versions,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
            separators=(",", ": "),
        ).encode("utf-8")
    ).hexdigest()


def compute_gate_toolchain_evidence_digest(
    toolchain: GateToolchainEvidenceV1,
) -> str:
    """The T01.1 evidence digest convention (compact canonical JSON)."""
    body = {
        key: value
        for key, value in dataclasses.asdict(toolchain).items()
        if key != "evidence_digest"
    }
    return _SHA256(_canonical_json_bytes(body)).hexdigest()


def _manifest_canonical_bytes(manifest: ReferenceProfileManifestV1) -> bytes:
    return _canonical_json_bytes(
        {**_manifest_body(manifest), "digest": manifest.digest}
    )


def derive_reference_profile_manifest(
    build_input: ReferenceBuildInputV1,
    build: ReferenceImageBuildEvidenceV1,
    gate_toolchain: GateToolchainEvidenceV1,
) -> ReferenceProfileManifestV1:
    """Derive the exact manifest the frozen evidence implies.

    Fails closed on malformed identities or a drifted T02.1-to-T01.1 tool
    binding; the derived manifest's digest is the SPEC §0.1 identity of every
    field except itself.
    """
    requirements_lock_digest = _validate_digest(
        build_input.requirements_digest, "requirements_lock_digest"
    )
    docker_image_digest = _validate_digest(
        build.local_oci_manifest_digest, "docker_image_digest"
    )
    if _tool_versions_digest(gate_toolchain) != build_input.tool_versions_digest:
        raise ValueError("build input tool versions no longer bind the gate toolchain")
    policy = builtin_editable_path_policy()
    manifest = ReferenceProfileManifestV1(
        schema_version=1,
        profile_id=PROFILE_ID,
        requirements_lock_digest=requirements_lock_digest,
        docker_image_digest=docker_image_digest,
        docker_execution_profile_version=1,
        python_version=gate_toolchain.python_version,
        pytest_version=gate_toolchain.pytest_version,
        report_plugin_version=GATE_REPORTER_VERSION,
        ruff_version=gate_toolchain.ruff_version,
        mypy_version=gate_toolchain.mypy_version,
        check_plan_version=CHECK_PLAN_VERSION,
        editable_path_policy=policy,
        digest="",
    )
    return dataclasses.replace(
        manifest, digest=compute_reference_profile_manifest_digest(manifest)
    )


def freeze_reference_profile_manifest(
    build_input: ReferenceBuildInputV1,
    build: ReferenceImageBuildEvidenceV1,
    gate_toolchain: GateToolchainEvidenceV1,
    manifest_path: Path,
) -> ReferenceProfileManifestV1:
    """Write the exact frozen manifest bytes and return the manifest.

    Never writes on failure; the manifest file is the sole frozen artifact of
    this task and is not rewritten after the GO identity is fixed.
    """
    manifest = derive_reference_profile_manifest(build_input, build, gate_toolchain)
    manifest_path = Path(manifest_path)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_bytes(_manifest_canonical_bytes(manifest))
    return manifest


def _require_exact_keys(
    obj: dict[str, object], keys: frozenset[str], what: str
) -> None:
    if set(obj) != keys:
        raise ValueError(f"{what} has an invalid field set")


def _require_str(value: object, field: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{field} must be a string")
    return value


def _require_int(value: object, field: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError(f"{field} must be an integer")
    return value


def _require_bool(value: object, field: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"{field} must be a boolean")
    return value


_MANIFEST_KEYS = frozenset(
    (
        "schema_version",
        "profile_id",
        "requirements_lock_digest",
        "docker_image_digest",
        "docker_execution_profile_version",
        "python_version",
        "pytest_version",
        "report_plugin_version",
        "ruff_version",
        "mypy_version",
        "check_plan_version",
        "editable_path_policy",
        "digest",
    )
)
_POLICY_KEYS = frozenset(
    (
        "schema_version",
        "policy_id",
        "editable_directory_roots",
        "allowed_operations",
        "digest",
    )
)
_TOOLCHAIN_KEYS = frozenset(
    (
        "schema_version",
        "evidence_digest",
        "evidence_type",
        "gate_input_sha256",
        "gate_lock_sha256",
        "gate_scan_core_sha256",
        "gate_scan_sha256",
        "mypy_config_sha256",
        "mypy_version",
        "pytest_config_sha256",
        "pytest_version",
        "python_version",
        "ruff_config_sha256",
        "ruff_version",
        "runner_sha256",
    )
)


def _parse_manifest_obj(obj: object) -> ReferenceProfileManifestV1:
    if not isinstance(obj, dict):
        raise ValueError("reference profile manifest must be a JSON object")
    _require_exact_keys(obj, _MANIFEST_KEYS, "reference profile manifest")
    policy_obj = obj["editable_path_policy"]
    if not isinstance(policy_obj, dict):
        raise ValueError("editable path policy must be a JSON object")
    _require_exact_keys(policy_obj, _POLICY_KEYS, "editable path policy")
    roots = policy_obj["editable_directory_roots"]
    operations = policy_obj["allowed_operations"]
    if not isinstance(roots, list) or not all(isinstance(root, str) for root in roots):
        raise ValueError("editable_directory_roots must be a string list")
    if (
        not isinstance(operations, list)
        or not all(isinstance(operation, str) for operation in operations)
        or any(operation not in _OPERATIONS for operation in operations)
    ):
        raise ValueError("allowed_operations must be a closed operation list")
    policy = EditablePathPolicyV1(
        schema_version=_require_int(
            policy_obj["schema_version"], "policy schema_version"
        ),
        policy_id=_require_str(policy_obj["policy_id"], "policy_id"),
        editable_directory_roots=tuple(roots),
        allowed_operations=tuple(operations),
        digest=_validate_digest(policy_obj["digest"], "policy digest"),
    )
    if compute_editable_path_policy_digest(policy) != policy.digest:
        raise ValueError("editable path policy digest mismatch")
    manifest = ReferenceProfileManifestV1(
        schema_version=_require_int(obj["schema_version"], "schema_version"),
        profile_id=_require_str(obj["profile_id"], "profile_id"),
        requirements_lock_digest=_validate_digest(
            obj["requirements_lock_digest"], "requirements_lock_digest"
        ),
        docker_image_digest=_validate_digest(
            obj["docker_image_digest"], "docker_image_digest"
        ),
        docker_execution_profile_version=_require_int(
            obj["docker_execution_profile_version"],
            "docker_execution_profile_version",
        ),
        python_version=_require_str(obj["python_version"], "python_version"),
        pytest_version=_require_str(obj["pytest_version"], "pytest_version"),
        report_plugin_version=_require_str(
            obj["report_plugin_version"], "report_plugin_version"
        ),
        ruff_version=_require_str(obj["ruff_version"], "ruff_version"),
        mypy_version=_require_str(obj["mypy_version"], "mypy_version"),
        check_plan_version=_require_str(
            obj["check_plan_version"], "check_plan_version"
        ),
        editable_path_policy=policy,
        digest=_validate_digest(obj["digest"], "manifest digest"),
    )
    if compute_reference_profile_manifest_digest(manifest) != manifest.digest:
        raise ValueError("reference profile manifest digest mismatch")
    return manifest


def load_reference_profile_manifest(path: Path) -> ReferenceProfileManifestV1:
    """Strictly parse one frozen manifest file with its §0.1 identity."""
    try:
        obj = json.loads(Path(path).read_bytes().decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError("reference profile manifest is not valid JSON") from exc
    return _parse_manifest_obj(obj)


def load_gate_toolchain_evidence(path: Path) -> GateToolchainEvidenceV1:
    """Strictly parse the T01.1 gate toolchain evidence with its digest."""
    try:
        obj = json.loads(Path(path).read_bytes().decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError("gate toolchain evidence is not valid JSON") from exc
    if not isinstance(obj, dict):
        raise ValueError("gate toolchain evidence must be a JSON object")
    _require_exact_keys(obj, _TOOLCHAIN_KEYS, "gate toolchain evidence")
    toolchain = GateToolchainEvidenceV1(
        schema_version=_require_int(obj["schema_version"], "schema_version"),
        evidence_digest=_validate_digest(obj["evidence_digest"], "evidence_digest"),
        evidence_type=_require_str(obj["evidence_type"], "evidence_type"),
        gate_input_sha256=_validate_digest(
            obj["gate_input_sha256"], "gate_input_sha256"
        ),
        gate_lock_sha256=_validate_digest(obj["gate_lock_sha256"], "gate_lock_sha256"),
        gate_scan_core_sha256=_validate_digest(
            obj["gate_scan_core_sha256"], "gate_scan_core_sha256"
        ),
        gate_scan_sha256=_validate_digest(obj["gate_scan_sha256"], "gate_scan_sha256"),
        mypy_config_sha256=_validate_digest(
            obj["mypy_config_sha256"], "mypy_config_sha256"
        ),
        mypy_version=_require_str(obj["mypy_version"], "mypy_version"),
        pytest_config_sha256=_validate_digest(
            obj["pytest_config_sha256"], "pytest_config_sha256"
        ),
        pytest_version=_require_str(obj["pytest_version"], "pytest_version"),
        python_version=_require_str(obj["python_version"], "python_version"),
        ruff_config_sha256=_validate_digest(
            obj["ruff_config_sha256"], "ruff_config_sha256"
        ),
        ruff_version=_require_str(obj["ruff_version"], "ruff_version"),
        runner_sha256=_validate_digest(obj["runner_sha256"], "runner_sha256"),
    )
    if compute_gate_toolchain_evidence_digest(toolchain) != toolchain.evidence_digest:
        raise ValueError("gate toolchain evidence digest mismatch")
    return toolchain


def _identity_failure_reason(
    command: AssembleReferenceGateReportV1,
) -> str | None:
    """The first closed identity failure, or None when every producer is
    present and mutually consistent."""
    manifest = command.manifest
    if compute_reference_profile_manifest_digest(manifest) != manifest.digest:
        return REASON_MANIFEST_DIGEST
    if (
        compute_editable_path_policy_digest(manifest.editable_path_policy)
        != manifest.editable_path_policy.digest
    ):
        return REASON_POLICY_DIGEST
    if manifest.editable_path_policy != builtin_editable_path_policy():
        return REASON_POLICY_NOT_BUILTIN
    if manifest.requirements_lock_digest != command.build_input.requirements_digest:
        return REASON_REQUIREMENTS
    if manifest.docker_image_digest != command.build.local_oci_manifest_digest:
        return REASON_IMAGE
    toolchain = command.gate_toolchain
    if (
        manifest.python_version != toolchain.python_version
        or manifest.pytest_version != toolchain.pytest_version
        or manifest.ruff_version != toolchain.ruff_version
        or manifest.mypy_version != toolchain.mypy_version
    ):
        return REASON_TOOL_VERSION
    if (
        manifest.report_plugin_version != GATE_REPORTER_VERSION
        or manifest.check_plan_version != CHECK_PLAN_VERSION
    ):
        return REASON_PROFILE_VERSION
    if compute_gate_toolchain_evidence_digest(toolchain) != toolchain.evidence_digest:
        return REASON_TOOLCHAIN
    if _tool_versions_digest(toolchain) != command.build_input.tool_versions_digest:
        return REASON_BUILD_INPUT_TOOLCHAIN
    if (
        toolchain.evidence_type != TOOLCHAIN_EVIDENCE_TYPE
        or toolchain.schema_version != 1
    ):
        return REASON_TOOLCHAIN_TYPE
    build = command.build
    if build.self_reference_scan_passed is not True:
        return REASON_SELF_REFERENCE
    if build.platform != "linux/amd64":
        return REASON_PLATFORM
    registry = command.registry
    if registry.registry_image_digest != command.build_input.registry_image_digest:
        return REASON_REGISTRY_IMAGE
    if (
        registry.local_oci_manifest_digest != build.local_oci_manifest_digest
        or registry.registry_repo_digest != build.local_oci_manifest_digest
        or registry.digest_pull_repo_digest != build.local_oci_manifest_digest
    ):
        return REASON_REGISTRY_DIGEST
    if registry.credentials_used is not False:
        return REASON_REGISTRY_CREDENTIALS
    if registry.external_push_count != 0:
        return REASON_REGISTRY_PUSH
    if registry.cleanup_verified is not True:
        return REASON_REGISTRY_CLEANUP
    isolation = command.isolation
    if (
        isolation.network_disabled is not True
        or isolation.non_root is not True
        or isolation.root_read_only is not True
        or isolation.capabilities_dropped is not True
        or isolation.docker_socket_absent is not True
        or isolation.workspace_read_only is not True
        or isolation.tmpfs_bounded is not True
    ):
        return REASON_ISOLATION
    if (
        isolation.cpu_limit != 2
        or isolation.memory_limit_bytes != 2 * 1024**3
        or isolation.pid_limit != 256
    ):
        return REASON_ISOLATION_LIMITS
    if isolation.cleanup_verified is not True:
        return REASON_ISOLATION_CLEANUP
    if command.pytest_evidence.passed is not True:
        return REASON_PYTEST
    if command.fingerprint.equal is not True:
        return REASON_FINGERPRINT
    if command.fingerprint.left_digest != command.fingerprint.right_digest:
        return REASON_FINGERPRINT_DIGESTS
    return None


def _report_body(report: DockerBoundaryGateReportV1) -> dict[str, object]:
    body = dataclasses.asdict(report)
    body.pop("evidence_digest")
    return body


def assemble_reference_gate_report(
    command: AssembleReferenceGateReportV1,
) -> DockerBoundaryGateReportV1:
    """Emit GO only when every producer identity is present and mutually
    consistent; any missing, drifted, or transformed digest emits NO_GO and
    no evidence is ever rewritten."""
    outcome: Literal["GO", "NO_GO"] = (
        "GO" if _identity_failure_reason(command) is None else "NO_GO"
    )
    report = DockerBoundaryGateReportV1(
        outcome=outcome,
        build_input=command.build_input,
        build=command.build,
        registry=command.registry,
        isolation=command.isolation,
        pytest_evidence=command.pytest_evidence,
        fingerprint=command.fingerprint,
        gate_toolchain=command.gate_toolchain,
        evidence_digest="",
    )
    digest = _domain_separated_digest(
        "DockerBoundaryGateReportV1", 1, _report_body(report)
    )
    return dataclasses.replace(report, evidence_digest=digest)

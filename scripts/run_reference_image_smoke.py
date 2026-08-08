"""T34.2 legacy step 34.A: the reference OCI reproduction and isolation smoke driver.

``run_reference_image_smoke`` reproduces the Task 2-frozen reference OCI
manifest exactly from the immutable recipe/lock/fixture/builder inputs,
compares the rebuilt and loopback-pulled manifest digests to the frozen
Task 2 digest, and proves the production executor/profile/fixture isolation
contract (non-root, no-network, read-only, bounded resources, the report
channel, the frozen fixture bytes, no self-reference, and verified
cleanup), returning the closed ``ReferenceImageSmokeResultV1`` (GREEN-1..
GREEN-4).

Identity sources: the Task 2.G GO identity is read from the packaged
production manifest (``src/vespercode/profiles/builtin/
reference-profile-v1.json``) through the T06.2 integrity loader, which
verifies the packaged bytes against the embedded frozen Task 2.G gate
identity (image digest 3e34b299…, lock 67a6b630…, tools 3.12.4/8.4.2/
0.16.1/2.3.0, profile/policy).  The ``reference/manifest/
reference-profile-v1.json`` copy was re-frozen to the same digest set
under the SPEC_PROCESS §86 determinism normalization and the loader
verifies the two copies agree; it is not read as a separate identity
source.  Every Task 2 input — recipe, dual lock, fixture, manifest,
builder, output, registry source — is read-only; any observed mismatch
fails closed (NO-GO) and never rewrites a frozen byte (GREEN-4).

The driver owns the reference-image construction and smoke evidence only:
``ensure_reference_tag`` reproduces/loads/tags the frozen identity through
the T02.1 fixed-parameter builder (SPEC §1.4.1 fixed
builder/output/media-type/compression/attestation parameters — the only
reproducible path for this recipe, whose ``COPY fixture/`` context is
assembled by that builder).  The card Build command
``docker build --pull=false -f containers/reference/Dockerfile -t
vespercode-reference:local .`` cannot run as written (the repo-root
context has no ``fixture/`` directory), recorded as a plan-level finding.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Final, Literal

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
_SRC_ROOT = _REPO_ROOT / "src"
if str(_SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(_SRC_ROOT))

from pydantic import BaseModel, ConfigDict, Strict  # noqa: E402

from spikes.docker_reference_boundary.execution_probe import (  # noqa: E402
    CPU_LIMIT,
    MEMORY_ARGV,
    NON_ROOT_GID,
    NON_ROOT_UID,
    PID_LIMIT,
    TMPFS_SPEC,
    WORKSPACE_TARGET,
    ContainerIsolationEvidenceV1,
    _ensure_frozen_image,
    _image_id,
    _reproduce_frozen_layout,
    probe_reference_container,
)
from spikes.docker_reference_boundary.image_builder import (  # noqa: E402
    ReferenceImageBuildEvidenceV1,
    build_reference_image,
)
from spikes.docker_reference_boundary.input_contract import (  # noqa: E402
    ReferenceBuildInputV1,
    freeze_reference_build_input,
)
from spikes.docker_reference_boundary.probe import (  # noqa: E402
    TARGET_TEST_NODE_ID,
    capture_reference_pytest,
)
from spikes.docker_reference_boundary.pytest_reporter import (  # noqa: E402
    GatePytestReportV1,
    validate_gate_pytest_report,
)
from spikes.docker_reference_boundary.registry_probe import (  # noqa: E402
    LoopbackRegistryDigestMismatchV1,
    LoopbackRegistryEvidenceV1,
    probe_loopback_registry,
)
from vespercode.canonical.path_v1 import CanonicalRelativePathV1  # noqa: E402
from vespercode.contracts.optional import AbsentV1, PresentV1  # noqa: E402
from vespercode.execution.docker_executor import (  # noqa: E402
    DockerExecutor,
    RawExecutionResultV1,
)
from vespercode.execution.docker_profile import (  # noqa: E402
    ExecutionRequestV1,
    _FROZEN_DOCKER_IMAGE_DIGEST,
)
from vespercode.execution.materialization import (  # noqa: E402
    MaterializedCandidateV1,
    allocate_execution_root,
    materialize_candidate,
)
from vespercode.profiles.reference import load_reference_profile  # noqa: E402
from vespercode.trees.candidate import (  # noqa: E402
    CandidatePostimageV1,
    CandidateTreeV1,
    derive_candidate_revision,
    root_candidate_revision,
)
from vespercode.trees.content_store import (  # noqa: E402
    ContentObjectRefV1,
    ContentObjectStore,
)
from vespercode.trees.snapshot import (  # noqa: E402
    SealedSnapshotInputFileV1,
    SnapshotDirectoryEntryV1,
    SnapshotEntryV1,
    SnapshotFileEntryV1,
    SnapshotTreeV1,
    _root_digest,
)
from vespercode.trees.text_classifier import (  # noqa: E402
    TextMetadataV1,
    classify_supported_text,
)

__all__ = (
    "ContainerIsolationEvidenceV1",
    "FROZEN_TASK2_MANIFEST_DIGEST_V1",
    "GatePytestReportV1",
    "LoopbackRegistryDigestMismatchV1",
    "LoopbackRegistryEvidenceV1",
    "OCIImageInspection",
    "ProductionExecutorEvidenceV1",
    "ReferenceBuildInputV1",
    "ReferenceImageBuildEvidenceV1",
    "ReferenceImageSmokeConfigV1",
    "ReferenceImageSmokeResultV1",
    "TARGET_TEST_NODE_ID",
    "build_reference_image",
    "ensure_reference_tag",
    "freeze_reference_build_input",
    "inspection_from_evidence",
    "load_reference_profile",
    "local_tagged_image_identity",
    "packaged_reference_manifest_digest",
    "probe_loopback_registry",
    "rebuild_reference_build_evidence",
    "rebuild_reference_image",
    "reference_container_isolation",
    "reference_pytest_report",
    "reference_workspace_listing",
    "run_production_executor_probe",
    "run_reference_image_smoke",
    "task2_go_digest",
    "validate_gate_pytest_report",
)

REFERENCE_IMAGE_TAG_V1: Final = "vespercode-reference:local"
"""The exact local tag of the reproduced reference image (card Build/Driver)."""

FROZEN_TASK2_MANIFEST_DIGEST_V1: Final = (
    "3e34b29997bb5174f96d05f94d4e870070171127989e427b332831389aa0b245"
)
"""The frozen Task 2 manifest digest: reproduced twice byte-identical by
the T02.1 fixed-parameter builder after the SPEC_PROCESS §86
deterministic layer normalization (frozen epoch mtimes, fixed gzip
headers, canonical manifest/config/index); bound in 15+ test constants
and the production executor/profile built-ins."""

RECIPE_RELATIVE_V1: Final = Path("containers") / "reference" / "Dockerfile"
LOCK_RELATIVE_V1: Final = Path("requirements") / "reference.lock"
FIXTURE_RELATIVE_V1: Final = Path("reference") / "fixture"
PACKAGED_MANIFEST_RELATIVE_V1: Final = (
    Path("src") / "vespercode" / "profiles" / "builtin" / "reference-profile-v1.json"
)

# The frozen fixture's one stable failing target (SPEC §4.5 baseline step 3).
TARGET_TEST_NODE_ID = TARGET_TEST_NODE_ID

# The four sealed fixture files the production executor materializes
# (mirrors the T18.2 fixture-candidate identity).
_FIXTURE_CANDIDATE_FILES: Final = (
    "pyproject.toml",
    "requirements.lock",
    "src/vesper_fixture/calculator.py",
    "tests/test_calculator.py",
)
_CALCULATOR_PATH: Final = "src/vesper_fixture/calculator.py"
_EXECUTOR_SWEEP_PREFIX: Final = "vespercode-check-"


def task2_go_digest() -> str:
    """The frozen Task 2.G GO image digest, integrity-verified.

    Loads the packaged production manifest through the T06.2 loader, which
    verifies the packaged bytes against the embedded frozen Task 2.G gate
    identity — image, lock, tools, profile, policy — before the digest is
    returned; any drift raises (NO-GO) instead of returning a drifted
    identity.
    """
    manifest = load_reference_profile(
        (_REPO_ROOT / PACKAGED_MANIFEST_RELATIVE_V1).read_bytes()
    )
    return manifest.docker_image_digest


def packaged_reference_manifest_digest() -> str:
    """The packaged reference manifest's own docker_image_digest field.

    A raw field read of the packaged manifest, validated to the exact
    64-lowercase-hex form; the frozen identity itself is verified by
    ``task2_go_digest`` through the integrity loader.
    """
    raw = json.loads(
        (_REPO_ROOT / PACKAGED_MANIFEST_RELATIVE_V1).read_bytes().decode("utf-8")
    )
    if not isinstance(raw, dict):
        raise ValueError("packaged reference manifest must be a JSON object")
    digest = raw.get("docker_image_digest")
    if (
        not isinstance(digest, str)
        or len(digest) != 64
        or any(character not in "0123456789abcdef" for character in digest)
    ):
        raise ValueError("packaged reference manifest image digest is malformed")
    return digest


@dataclass(frozen=True)
class OCIImageInspection:
    """One closed inspection of the rebuilt reference OCI image.

    ``manifest_digest`` is the local OCI manifest digest the exact RED
    test compares against the frozen Task 2 digest; the pre-implementation
    state yields an empty inspection (``manifest_digest=None``) so the
    exact RED's first task-owned assertion fails on the missing
    reproduction contract.
    """

    manifest_digest: str | None
    image_config_digest: str | None
    recipe_digest: str | None
    platform: str | None
    self_reference_scan_passed: bool | None


def inspection_from_evidence(
    build: ReferenceImageBuildEvidenceV1,
) -> OCIImageInspection:
    """Map one frozen build evidence onto the closed image inspection."""
    return OCIImageInspection(
        manifest_digest=build.local_oci_manifest_digest,
        image_config_digest=build.image_config_digest,
        recipe_digest=build.recipe_digest,
        platform=build.platform,
        self_reference_scan_passed=build.self_reference_scan_passed,
    )


def rebuild_reference_build_evidence() -> ReferenceImageBuildEvidenceV1:
    """Reproduce the frozen reference OCI build evidence.

    The smallest exact reproduction path (GREEN-3): freeze the clean
    repository input identity (fail-closed on recipe/lock/fixture/tool
    drift), then rebuild with the T02.1 fixed-parameter builder and return
    its immutable evidence.  The build consumes only the frozen recipe,
    dual lock, and fixture bytes through the immutable build input — no
    other repository state can enter the context (GREEN-1).
    """
    build_input = freeze_reference_build_input(_REPO_ROOT)
    return build_reference_image(build_input)


def rebuild_reference_image() -> OCIImageInspection:
    """Reproduce the frozen reference OCI manifest and inspect it."""
    return inspection_from_evidence(rebuild_reference_build_evidence())


def local_tagged_image_identity(tag: str) -> tuple[str | None, str | None]:
    """The daemon image id and first RepoDigest of *tag*; ``(None, None)``
    when the tag is absent or malformed."""
    proc = subprocess.run(
        ["docker", "image", "inspect", tag],
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    if proc.returncode != 0:
        return None, None
    try:
        info = json.loads(proc.stdout)[0]
    except (json.JSONDecodeError, IndexError, KeyError):
        return None, None
    repo_digests = info.get("RepoDigests") or []
    return info.get("Id"), (repo_digests[0] if repo_digests else None)


def ensure_reference_tag(tag: str, build: ReferenceImageBuildEvidenceV1) -> str:
    """Ensure *tag* names the frozen reference image identity.

    When the tag is absent, the frozen image is loaded (reproducing the
    exact OCI layout through the builder's own fixed-parameter machinery
    when the daemon does not hold it) and tagged; when the tag exists its
    id is re-verified against the frozen identity and any mismatch fails
    closed (NO-GO — a mismatched tag is never silently re-tagged).
    """
    expected_ref = f"sha256:{build.local_oci_manifest_digest}"
    observed_id, _ = local_tagged_image_identity(tag)
    if observed_id is not None:
        if observed_id != expected_ref:
            raise RuntimeError(
                f"tag {tag} names {observed_id}, not the frozen {expected_ref} (NO-GO)"
            )
        return observed_id
    if _image_id(expected_ref) is None:
        with tempfile.TemporaryDirectory(prefix="vesper-ref-smoke-") as tmp:
            output_tar = _reproduce_frozen_layout(Path(tmp))
            _ensure_frozen_image(build, output_tar)
    proc = subprocess.run(
        ["docker", "tag", expected_ref, tag],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(
            f"docker tag failed (exit {proc.returncode}): "
            + (proc.stderr or proc.stdout or "").strip()
        )
    verified_id, _ = local_tagged_image_identity(tag)
    if verified_id != expected_ref:
        raise RuntimeError("the tagged reference image identity is not verifiable")
    return verified_id


def reference_container_isolation(
    build: ReferenceImageBuildEvidenceV1, fixture: Path
) -> ContainerIsolationEvidenceV1:
    """One fresh reference container's frozen isolation evidence (T02.3)."""
    return probe_reference_container(build, fixture)


_LISTING_PAYLOAD_PREFIX: Final = "import base64;exec(base64.b64decode('"
_LISTING_SCRIPT = """\
import json, os
print(json.dumps(sorted(os.listdir("/workspace")), sort_keys=True))
"""


def _fixture_listing_argv(image_ref: str, fixture: Path) -> list[str]:
    """The frozen SPEC §1.4.5 run parameters with one listing command."""
    payload = base64.b64encode(_LISTING_SCRIPT.encode("utf-8")).decode("ascii")
    return [
        "docker",
        "run",
        "--rm",
        "--network",
        "none",
        "--user",
        f"{NON_ROOT_UID}:{NON_ROOT_GID}",
        "--read-only",
        "--cap-drop",
        "ALL",
        "--tmpfs",
        TMPFS_SPEC,
        "--cpus",
        str(CPU_LIMIT),
        "--memory",
        MEMORY_ARGV,
        "--pids-limit",
        str(PID_LIMIT),
        "--mount",
        (
            f"type=bind,src={str(fixture).replace(chr(92), '/')},"
            f"dst={WORKSPACE_TARGET},ro"
        ),
        image_ref,
        "python",
        "-c",
        f"{_LISTING_PAYLOAD_PREFIX}{payload}'))",
    ]


def reference_workspace_listing(
    build: ReferenceImageBuildEvidenceV1, fixture: Path
) -> tuple[str, ...]:
    """The sorted workspace entries served by one fresh frozen container.

    Proves the fixture bytes are mounted read-only at /workspace under the
    frozen §1.4.5 parameters (the container exits cleanly, so the root is
    writable nowhere and the listing is authoritative).
    """
    image_ref = f"sha256:{build.local_oci_manifest_digest}"
    proc = subprocess.run(
        _fixture_listing_argv(image_ref, fixture),
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    if proc.returncode != 0:
        tail = proc.stderr[-2000:] if proc.stderr else ""
        raise RuntimeError(
            f"fixture listing container failed (exit {proc.returncode}): {tail}"
        )
    try:
        listing = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError("fixture listing output is not valid JSON") from exc
    if not isinstance(listing, list) or not all(
        isinstance(entry, str) for entry in listing
    ):
        raise RuntimeError("fixture listing output must be a string list")
    return tuple(listing)


def reference_pytest_report(
    build: ReferenceImageBuildEvidenceV1,
    fixture: Path,
    root: Path,
    planned_node_ids: tuple[str, ...],
    target_node_ids: tuple[str, ...] | None = None,
    *,
    collect_only: bool = False,
) -> GatePytestReportV1:
    """One explicitly loaded pytest lifecycle in a fresh reference
    container with the fixed report channel on the bounded tmpfs (T02.4)."""
    return capture_reference_pytest(
        build,
        fixture,
        root,
        planned_node_ids,
        collect_only=collect_only,
        target_node_ids=target_node_ids,
    )


_EXECUTOR_OBSERVATION_SCRIPT = """\
import hashlib, json, os
with open("/workspace/src/vesper_fixture/calculator.py", "rb") as stream:
    calculator_sha256 = hashlib.sha256(stream.read()).hexdigest()
def write_errno(path):
    try:
        with open(path, "w", encoding="utf-8") as stream:
            stream.write("x")
        return 0
    except OSError as exc:
        return exc.errno
print(json.dumps({
    "uid": os.getuid(),
    "calculator_sha256": calculator_sha256,
    "workspace_write_errno": write_errno("/workspace/probe-write"),
}, sort_keys=True))
"""


def _executor_observation_request() -> ExecutionRequestV1:
    """One frozen production ExecutionRequest over the observation script."""
    payload = base64.b64encode(_EXECUTOR_OBSERVATION_SCRIPT.encode("utf-8")).decode(
        "ascii"
    )
    manifest = load_reference_profile(
        (_REPO_ROOT / PACKAGED_MANIFEST_RELATIVE_V1).read_bytes()
    )
    return ExecutionRequestV1.model_validate(
        {
            "schema_version": 1,
            "request_id": "req-34-a-smoke",
            "reference_profile_digest": manifest.digest,
            "docker_image_digest": _FROZEN_DOCKER_IMAGE_DIGEST,
            "docker_execution_profile_version": 1,
            "profile": {
                "schema_version": 1,
                "profile_version": 1,
                "network_mode": "none",
                "user": f"{NON_ROOT_UID}:{NON_ROOT_GID}",
                "read_only_rootfs": True,
                "capabilities_dropped": "ALL",
                "docker_socket_mounted": False,
                "workdir": "/workspace",
                "workspace_mount": {"target": "/workspace", "read_only": True},
                "tmpfs_mount": {"path": "/tmp"},
                "resources": {
                    "cpus": CPU_LIMIT,
                    "memory_bytes": 2 * 1024**3,
                    "pids_limit": PID_LIMIT,
                    "tmpfs_size_bytes": 256 * 1024**2,
                    "max_output_bytes": 4 * 1024**2,
                },
                "environment": {
                    "variables": [
                        {"name": "LANG", "value": "C.UTF-8"},
                        {"name": "LC_ALL", "value": "C.UTF-8"},
                        {"name": "PYTHONDONTWRITEBYTECODE", "value": "1"},
                        {"name": "PYTHONHASHSEED", "value": "0"},
                        {"name": "TZ", "value": "UTC"},
                    ]
                },
                "fresh_container_per_check": True,
                "pytest_plugin_autoload_disabled": True,
            },
            "argv": {
                "arguments": (
                    "python",
                    "-c",
                    f"import base64;exec(base64.b64decode('{payload}'))",
                )
            },
        }
    )


def _fixture_candidate_tree(fixture: Path) -> CandidateTreeV1:
    """One real candidate tree over the frozen fixture bytes.

    The sealed snapshot carries the four fixture files; the overlay
    REPLACEs the intentionally defective calculator with the corrected
    bytes, so the container-observed bytes prove the executor mounts the
    fresh materialized candidate tree, not the frozen fixture (SPEC
    §1.4.5 fresh-materialization contract; T18.2 pattern).
    """
    store = ContentObjectStore()
    rows: list[SealedSnapshotInputFileV1] = []
    for relative in _FIXTURE_CANDIDATE_FILES:
        raw = (fixture / relative).read_bytes()
        ref = store.put(raw)
        rows.append(
            SealedSnapshotInputFileV1(
                schema_version=1,
                path=CanonicalRelativePathV1(relative),
                content_sha256=ref.sha256,
                byte_count=ref.byte_count,
            )
        )
    rows.sort(key=lambda row: row.path.value)
    directory_values = {
        "/".join(row.path.value.split("/")[:index])
        for row in rows
        for index in range(1, len(row.path.value.split("/")))
    }
    manifest = load_reference_profile(
        (_REPO_ROOT / PACKAGED_MANIFEST_RELATIVE_V1).read_bytes()
    )
    entries: list[SnapshotEntryV1] = [
        SnapshotDirectoryEntryV1(kind="DIRECTORY", path=CanonicalRelativePathV1(value))
        for value in sorted(directory_values)
    ]
    for row in rows:
        ref = ContentObjectRefV1(sha256=row.content_sha256, byte_count=row.byte_count)
        classification = classify_supported_text(store.get(ref))
        if classification.kind == "TEXT_FILE":
            text_profile: PresentV1[TextMetadataV1] | AbsentV1 = (
                classification.text_profile
            )
        else:
            text_profile = AbsentV1(kind="ABSENT")
        entries.append(
            SnapshotFileEntryV1(
                kind=classification.kind,
                path=row.path,
                size_bytes=row.byte_count,
                content_ref=ref,
                text_profile=text_profile,
            )
        )
    snapshot = SnapshotTreeV1(
        root_digest=_root_digest(manifest.editable_path_policy.digest, tuple(entries)),
        repository_policy_digest=manifest.editable_path_policy.digest,
        entries=tuple(entries),
        file_bytes=tuple(
            (
                row.path.value,
                store.get(
                    ContentObjectRefV1(
                        sha256=row.content_sha256, byte_count=row.byte_count
                    )
                ),
            )
            for row in rows
        ),
    )
    original = (fixture / _CALCULATOR_PATH).read_bytes()
    corrected = original.replace(
        b"    return left - right\n", b"    return left + right\n"
    )
    if corrected == original:
        raise ValueError("the fixture defect line must exist")
    revision = derive_candidate_revision(
        root_candidate_revision(snapshot, store),
        (
            CandidatePostimageV1(
                schema_version=1,
                operation="REPLACE",
                path=CanonicalRelativePathV1(_CALCULATOR_PATH),
                raw_bytes=corrected,
            ),
        ),
    )
    return revision.tree


def _sweep_executor_containers() -> bool:
    """Remove every leftover executor container; True when none remain."""
    proc = subprocess.run(
        [
            "docker",
            "ps",
            "-a",
            "--filter",
            f"name={_EXECUTOR_SWEEP_PREFIX}",
            "--format",
            "{{.ID}}",
        ],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    if proc.returncode != 0:
        return False
    ok = True
    for container_id in proc.stdout.splitlines():
        cleaned = container_id.strip()
        if not cleaned:
            continue
        removed = subprocess.run(
            ["docker", "rm", "-f", cleaned],
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
        if removed.returncode != 0:
            ok = False
    return ok


@dataclass(frozen=True)
class ProductionExecutorEvidenceV1:
    """One real production-executor run over a fresh materialized
    fixture candidate."""

    exit_code: int | None
    error_code: str | None
    observed_uid: int | None
    workspace_write_errno: int | None
    observed_calculator_sha256: str | None
    expected_calculator_sha256: str | None
    candidate_bytes_match: bool
    cleanup_verified: bool


def run_production_executor_probe() -> ProductionExecutorEvidenceV1:
    """Run the real production executor over the frozen fixture candidate.

    ``DockerExecutor.execute`` creates one fresh container from the frozen
    built-in image digest and profile, re-verifies the daemon-side
    isolation configuration of that exact container, and runs the bounded
    observation argv against the fresh materialized candidate root; the
    observed uid, the EROFS workspace write, and the exact candidate bytes
    prove the production executor/profile/fixture isolation contract
    (SPEC §1.4.5).  Executor containers and the materialization root are
    removed on every exit path.
    """
    fixture = _REPO_ROOT / FIXTURE_RELATIVE_V1
    candidate = _fixture_candidate_tree(fixture)
    expected_sha256 = hashlib.sha256(
        candidate.read_bytes(CanonicalRelativePathV1(_CALCULATOR_PATH))
    ).hexdigest()
    root_base = Path(tempfile.mkdtemp(prefix="vesper-ref-smoke-exec-"))
    failure: BaseException | None = None
    materialized: MaterializedCandidateV1 | None = None
    result: RawExecutionResultV1 | None = None
    try:
        materialized = materialize_candidate(
            candidate, allocate_execution_root(root_base)
        )
        result = DockerExecutor().execute(_executor_observation_request(), materialized)
    except BaseException as exc:
        failure = exc
    cleanup_verified = _sweep_executor_containers()
    shutil.rmtree(root_base, ignore_errors=True)
    if not cleanup_verified:
        raise RuntimeError(
            "production executor container cleanup not verified"
        ) from failure
    if failure is not None:
        raise failure.with_traceback(failure.__traceback__)
    assert materialized is not None
    assert result is not None
    if result.error_code is not None:
        return ProductionExecutorEvidenceV1(
            exit_code=result.exit_code,
            error_code=result.error_code,
            observed_uid=None,
            workspace_write_errno=None,
            observed_calculator_sha256=None,
            expected_calculator_sha256=expected_sha256,
            candidate_bytes_match=False,
            cleanup_verified=cleanup_verified,
        )
    try:
        observations = json.loads(result.stdout.decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise RuntimeError("executor observation output is not valid JSON") from exc
    if not isinstance(observations, dict):
        raise RuntimeError("executor observation output must be an object")
    observed_uid = observations.get("uid")
    write_errno = observations.get("workspace_write_errno")
    observed_sha = observations.get("calculator_sha256")
    return ProductionExecutorEvidenceV1(
        exit_code=result.exit_code,
        error_code=result.error_code,
        observed_uid=observed_uid if isinstance(observed_uid, int) else None,
        workspace_write_errno=write_errno if isinstance(write_errno, int) else None,
        observed_calculator_sha256=observed_sha
        if isinstance(observed_sha, str)
        else None,
        expected_calculator_sha256=expected_sha256,
        candidate_bytes_match=observed_sha == expected_sha256,
        cleanup_verified=cleanup_verified,
    )


class ReferenceImageSmokeConfigV1(BaseModel):
    """The closed configuration of one reference-image smoke run."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal[1] = 1
    reference_image_tag: Annotated[str, Strict()] = REFERENCE_IMAGE_TAG_V1
    report_path: Annotated[str, Strict()] = (
        "tests/.tmp/reference-image-smoke-report.json"
    )


class ReferenceImageSmokeResultV1(BaseModel):
    """The closed outcome of one reference-image smoke run."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal[1]
    reference_image_tag: str
    frozen_task2_digest: str
    packaged_manifest_digest: str
    rebuilt_manifest_digest: str | None
    rebuilt_config_digest: str | None
    rebuilt_recipe_digest: str | None
    rebuilt_platform: str | None
    rebuilt_matches_frozen: bool
    rebuilt_matches_packaged: bool
    self_reference_scan_passed: bool | None
    tagged_image_id: str | None
    tagged_matches_frozen: bool
    registry_repo_digest: str | None
    digest_pull_repo_digest: str | None
    registry_three_way_match: bool
    registry_credentials_used: bool
    registry_external_push_count: int
    registry_cleanup_verified: bool
    isolation_network_disabled: bool
    isolation_non_root: bool
    isolation_root_read_only: bool
    isolation_capabilities_dropped: bool
    isolation_docker_socket_absent: bool
    isolation_workspace_read_only: bool
    isolation_tmpfs_bounded: bool
    isolation_cpu_limit: int | None
    isolation_memory_limit_bytes: int | None
    isolation_pid_limit: int | None
    isolation_cleanup_verified: bool
    workspace_listing: tuple[str, ...]
    report_plugin_passed: bool | None
    report_collected_node_count: int | None
    report_exit_code: int | None
    executor_error_code: str | None
    executor_observed_uid: int | None
    executor_workspace_write_errno: int | None
    executor_candidate_bytes_match: bool
    executor_cleanup_verified: bool
    fixture_dual_lock_identical: bool
    all_ok: bool
    report_text: str
    report_digest: str


def _finalize_report(
    result: ReferenceImageSmokeResultV1,
) -> ReferenceImageSmokeResultV1:
    """Bind the exact report bytes the driver writes.

    The report text is the canonical JSON of every field except the
    report text/digest themselves; ``report_digest`` is its SHA-256, so
    the written file is exactly the bounded bytes the result binds (the
    T32.1 report-identity convention).
    """
    payload = {
        key: value
        for key, value in result.model_dump(mode="json").items()
        if key not in {"report_text", "report_digest"}
    }
    text = json.dumps(payload, sort_keys=True, indent=2, ensure_ascii=False) + "\n"
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    return ReferenceImageSmokeResultV1(
        **{
            **result.model_dump(mode="json"),
            "report_text": text,
            "report_digest": digest,
        }
    )


def _isolation_ok(evidence: ContainerIsolationEvidenceV1) -> bool:
    """Every frozen isolation control must hold (SPEC §1.4.5)."""
    return (
        evidence.network_disabled is True
        and evidence.non_root is True
        and evidence.root_read_only is True
        and evidence.capabilities_dropped is True
        and evidence.docker_socket_absent is True
        and evidence.workspace_read_only is True
        and evidence.tmpfs_bounded is True
        and evidence.cpu_limit == CPU_LIMIT
        and evidence.memory_limit_bytes == 2 * 1024**3
        and evidence.pid_limit == PID_LIMIT
        and evidence.cleanup_verified is True
    )


def run_reference_image_smoke(
    config: ReferenceImageSmokeConfigV1,
) -> ReferenceImageSmokeResultV1:
    """Run the exact reference-image smoke and return the closed result.

    Order: bind the frozen identities before any inspection (GREEN-1),
    reproduce the manifest through the frozen builder (GREEN-3), compare
    the rebuilt, loopback-pulled, and frozen digests, then prove
    isolation, report, fixture, no-self-reference, and cleanup (GREEN-2).
    Any evidence failure is recorded in the result (all_ok False, NO-GO);
    hard probe failures propagate to the CLI error report.
    """
    frozen = task2_go_digest()
    packaged = packaged_reference_manifest_digest()
    freeze_reference_build_input(_REPO_ROOT)  # binds clean-source identity
    dual_lock_identical = (_REPO_ROOT / LOCK_RELATIVE_V1).read_bytes() == (
        _REPO_ROOT / FIXTURE_RELATIVE_V1 / "requirements.lock"
    ).read_bytes()

    evidence = rebuild_reference_build_evidence()
    inspection = inspection_from_evidence(evidence)
    rebuilt = inspection.manifest_digest
    rebuilt_matches_frozen = rebuilt is not None and rebuilt == frozen
    rebuilt_matches_packaged = rebuilt is not None and rebuilt == packaged

    tagged_id: str | None = None
    tagged_matches_frozen = False
    try:
        tagged_id = ensure_reference_tag(config.reference_image_tag, evidence)
        tagged_matches_frozen = tagged_id == f"sha256:{frozen}"
    except RuntimeError:
        tagged_matches_frozen = False

    fixture = _REPO_ROOT / FIXTURE_RELATIVE_V1
    registry = probe_loopback_registry(evidence)
    isolation = reference_container_isolation(evidence, fixture)
    listing = reference_workspace_listing(evidence, fixture)
    report = reference_pytest_report(
        evidence,
        fixture,
        _REPO_ROOT,
        (TARGET_TEST_NODE_ID,),
        target_node_ids=(TARGET_TEST_NODE_ID,),
    )
    validated = validate_gate_pytest_report(report)
    executor = run_production_executor_probe()

    three_way_match = (
        rebuilt is not None
        and registry.registry_repo_digest == rebuilt
        and registry.digest_pull_repo_digest == rebuilt
    )
    all_ok = (
        rebuilt_matches_frozen
        and rebuilt_matches_packaged
        and inspection.self_reference_scan_passed is True
        and inspection.platform == "linux/amd64"
        and tagged_matches_frozen
        and three_way_match
        and registry.credentials_used is False
        and registry.external_push_count == 0
        and registry.cleanup_verified is True
        and _isolation_ok(isolation)
        and set(listing) == {"pyproject.toml", "requirements.lock", "src", "tests"}
        and validated.passed is True
        and executor.error_code is None
        and executor.candidate_bytes_match is True
        and executor.cleanup_verified is True
    )
    return _finalize_report(
        ReferenceImageSmokeResultV1(
            schema_version=1,
            reference_image_tag=config.reference_image_tag,
            frozen_task2_digest=frozen,
            packaged_manifest_digest=packaged,
            rebuilt_manifest_digest=rebuilt,
            rebuilt_config_digest=inspection.image_config_digest,
            rebuilt_recipe_digest=inspection.recipe_digest,
            rebuilt_platform=inspection.platform,
            rebuilt_matches_frozen=rebuilt_matches_frozen,
            rebuilt_matches_packaged=rebuilt_matches_packaged,
            self_reference_scan_passed=inspection.self_reference_scan_passed,
            tagged_image_id=tagged_id,
            tagged_matches_frozen=tagged_matches_frozen,
            registry_repo_digest=registry.registry_repo_digest,
            digest_pull_repo_digest=registry.digest_pull_repo_digest,
            registry_three_way_match=three_way_match,
            registry_credentials_used=registry.credentials_used,
            registry_external_push_count=registry.external_push_count,
            registry_cleanup_verified=registry.cleanup_verified,
            isolation_network_disabled=isolation.network_disabled,
            isolation_non_root=isolation.non_root,
            isolation_root_read_only=isolation.root_read_only,
            isolation_capabilities_dropped=isolation.capabilities_dropped,
            isolation_docker_socket_absent=isolation.docker_socket_absent,
            isolation_workspace_read_only=isolation.workspace_read_only,
            isolation_tmpfs_bounded=isolation.tmpfs_bounded,
            isolation_cpu_limit=isolation.cpu_limit,
            isolation_memory_limit_bytes=isolation.memory_limit_bytes,
            isolation_pid_limit=isolation.pid_limit,
            isolation_cleanup_verified=isolation.cleanup_verified,
            workspace_listing=listing,
            report_plugin_passed=validated.passed,
            report_collected_node_count=len(report.collected_node_ids),
            report_exit_code=report.exit_code,
            executor_error_code=executor.error_code,
            executor_observed_uid=executor.observed_uid,
            executor_workspace_write_errno=executor.workspace_write_errno,
            executor_candidate_bytes_match=executor.candidate_bytes_match,
            executor_cleanup_verified=executor.cleanup_verified,
            fixture_dual_lock_identical=dual_lock_identical,
            all_ok=all_ok,
            report_text="",
            report_digest="",
        )
    )


def main(argv: list[str] | None = None) -> int:
    """CLI entry: run the smoke, write the bounded report; 0 on pass."""
    parser = argparse.ArgumentParser(description="Run the reference-image smoke.")
    parser.add_argument(
        "--reference", default=REFERENCE_IMAGE_TAG_V1, help="reference image tag"
    )
    parser.add_argument(
        "--report", default="tests/.tmp/reference-image-smoke-report.json"
    )
    args = parser.parse_args(argv)
    report_path = Path(args.report)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        config = ReferenceImageSmokeConfigV1(
            reference_image_tag=args.reference, report_path=args.report
        )
        result = run_reference_image_smoke(config)
    except Exception as exc:
        report_path.write_text(
            json.dumps(
                {
                    "error_code": "REFERENCE_IMAGE_SMOKE_FAILED",
                    "error_message": str(exc),
                    "reference_image_tag": args.reference,
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        print(f"reference image smoke FAILED: {exc}")
        return 1
    report_path.write_bytes(result.report_text.encode("utf-8"))
    print(
        f"reference image smoke: rebuilt {result.rebuilt_manifest_digest},"
        f" frozen {result.frozen_task2_digest},"
        f" all_ok {result.all_ok},"
        f" report digest {result.report_digest}"
    )
    return 0 if result.all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())

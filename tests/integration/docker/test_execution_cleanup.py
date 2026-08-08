"""T18.2 legacy step 18.D: real end-to-end execution cleanup.

One full lifecycle on the real daemon: materialize the real fixture
candidate into a fresh identity-bound root, execute one closed probe
request in one fresh frozen container, reverify the materialized bytes
after execution, remove the exact container and root, and prove zero
residue (no surviving container, no surviving root, unchanged real
workspace, no link followed) — SPEC §4.3 cleanup (GREEN-1..GREEN-4).
"""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path
from collections.abc import Iterator

import pytest

pytest.importorskip("pydantic")

from vespercode.canonical.path_v1 import CanonicalRelativePathV1
from vespercode.contracts.optional import AbsentV1, PresentV1
from vespercode.execution.cleanup import finalize_execution
from vespercode.execution.docker_executor import DockerExecutor
from vespercode.execution.docker_profile import ExecutionRequestV1
from vespercode.execution.materialization import (
    allocate_execution_root,
    materialize_candidate,
)
from vespercode.profiles.reference import load_reference_profile
from vespercode.trees.candidate import (
    CandidatePostimageV1,
    CandidateTreeV1,
    derive_candidate_revision,
    root_candidate_revision,
)
from vespercode.trees.content_store import ContentObjectRefV1, ContentObjectStore
from vespercode.trees.snapshot import (
    SealedSnapshotInputFileV1,
    SnapshotDirectoryEntryV1,
    SnapshotEntryV1,
    SnapshotFileEntryV1,
    SnapshotTreeV1,
    _root_digest,
)
from vespercode.trees.text_classifier import (
    TextMetadataV1,
    classify_supported_text,
)

pytestmark = pytest.mark.docker_integration

# The frozen T18.1 request identity (SPEC §1.4.1/§1.4.5).
_MANIFEST_DIGEST = "d0700f00f5ae2501ac9be7fbdd66d20e76c16a6c6f9ab7893c1aea71d57e927e"
_IMAGE_DIGEST = "cf0b6c5ccac588fccd07c3b9f050bff4daf550ac6e518fd06efb6e988ab1d823"

_FIXTURE_FILES = (
    "pyproject.toml",
    "requirements.lock",
    "src/vesper_fixture/calculator.py",
    "tests/test_calculator.py",
)
_CALCULATOR_PATH = "src/vesper_fixture/calculator.py"


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def packaged_reference_profile_bytes() -> bytes:
    return (
        _repo_root()
        / "src"
        / "vespercode"
        / "profiles"
        / "builtin"
        / "reference-profile-v1.json"
    ).read_bytes()


def frozen_policy_digest() -> str:
    manifest = load_reference_profile(packaged_reference_profile_bytes())
    return manifest.editable_path_policy.digest


def corrected_calculator_bytes() -> bytes:
    original = (_repo_root() / "reference" / "fixture" / _CALCULATOR_PATH).read_bytes()
    fixed = original.replace(b"    return left - right\n", b"    return left + right\n")
    assert fixed != original, "the fixture defect line must exist"
    return fixed


def build_fixture_candidate() -> CandidateTreeV1:
    """One real candidate tree over the frozen reference fixture bytes."""
    fixture = _repo_root() / "reference" / "fixture"
    store = ContentObjectStore()
    rows: list[SealedSnapshotInputFileV1] = []
    for rel in _FIXTURE_FILES:
        raw = (fixture / rel).read_bytes()
        ref = store.put(raw)
        rows.append(
            SealedSnapshotInputFileV1(
                schema_version=1,
                path=CanonicalRelativePathV1(rel),
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
    policy_digest = frozen_policy_digest()
    snapshot = SnapshotTreeV1(
        root_digest=_root_digest(policy_digest, tuple(entries)),
        repository_policy_digest=policy_digest,
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
    revision = derive_candidate_revision(
        root_candidate_revision(snapshot, store),
        (
            CandidatePostimageV1(
                schema_version=1,
                operation="REPLACE",
                path=CanonicalRelativePathV1(_CALCULATOR_PATH),
                raw_bytes=corrected_calculator_bytes(),
            ),
        ),
    )
    return revision.tree


def builtin_environment_dict() -> dict[str, object]:
    return {
        "variables": [
            {"name": "LANG", "value": "C.UTF-8"},
            {"name": "LC_ALL", "value": "C.UTF-8"},
            {"name": "PYTHONDONTWRITEBYTECODE", "value": "1"},
            {"name": "PYTHONHASHSEED", "value": "0"},
            {"name": "TZ", "value": "UTC"},
        ]
    }


def builtin_resources_dict() -> dict[str, object]:
    return {
        "cpus": 2,
        "memory_bytes": 2 * 1024**3,
        "pids_limit": 256,
        "tmpfs_size_bytes": 256 * 1024**2,
        "max_output_bytes": 4 * 1024**2,
    }


def builtin_profile_dict() -> dict[str, object]:
    return {
        "schema_version": 1,
        "profile_version": 1,
        "network_mode": "none",
        "user": "10001:10001",
        "read_only_rootfs": True,
        "capabilities_dropped": "ALL",
        "docker_socket_mounted": False,
        "workdir": "/workspace",
        "workspace_mount": {"target": "/workspace", "read_only": True},
        "tmpfs_mount": {"path": "/tmp"},
        "resources": builtin_resources_dict(),
        "environment": builtin_environment_dict(),
        "fresh_container_per_check": True,
        "pytest_plugin_autoload_disabled": True,
    }


def probe_request() -> ExecutionRequestV1:
    return ExecutionRequestV1.model_validate(
        {
            "schema_version": 1,
            "request_id": "req-18-d-e2e",
            "reference_profile_digest": _MANIFEST_DIGEST,
            "docker_image_digest": _IMAGE_DIGEST,
            "docker_execution_profile_version": 1,
            "profile": builtin_profile_dict(),
            "argv": {
                "arguments": (
                    "python",
                    "-c",
                    "import sys; sys.stdout.write('e2e-probe')",
                )
            },
        }
    )


_MODULE_ROOT_BASE = Path(tempfile.mkdtemp(prefix="vesper-t182-e2e-"))


@pytest.fixture(scope="module", autouse=True)
def _remove_module_root_bases() -> Iterator[None]:
    yield
    shutil.rmtree(_MODULE_ROOT_BASE, ignore_errors=True)


def _executor_container_ids() -> set[str]:
    """The ids of every container created by the executor's name pattern."""
    try:
        import docker  # type: ignore[import-untyped]

        client = docker.from_env()
        return {
            str(container.id)
            for container in client.containers.list(
                all=True, filters={"name": "vespercode-check"}
            )
        }
    except Exception:
        return set()


def test_full_lifecycle_removes_exact_container_and_root_with_zero_residue() -> None:
    """Materialize -> execute -> reverify -> remove, with zero residue.

    The real workspace (the reference fixture and the repo) is untouched:
    materialization reads only the sealed candidate, execution mounts only
    the fresh root read-only, and finalize removes exactly the one
    container and the one root created by this lifecycle.
    """
    import docker

    client = docker.from_env()
    before = _executor_container_ids()
    candidate = build_fixture_candidate()
    materialized = materialize_candidate(
        candidate, allocate_execution_root(_MODULE_ROOT_BASE)
    )
    root = Path(materialized.root_path)
    assert root.is_dir()

    result = DockerExecutor().execute(probe_request(), materialized)
    assert result.error_code is None
    assert result.stdout == b"e2e-probe"
    container_id = result.container_id
    assert container_id not in before

    cleanup = finalize_execution(result, candidate, materialized)
    assert cleanup.workspace_unchanged is True
    assert cleanup.container_removed is True
    assert cleanup.materialization_removed is True
    assert cleanup.residual_artifact is None

    # Zero residue: the exact container and root are gone; no other
    # container was touched; the real workspace bytes are unchanged.
    after = _executor_container_ids()
    assert after == before
    assert not root.exists()
    try:
        client.api.inspect_container(container_id)
        raise AssertionError("the exact container still exists after finalize")
    except docker.errors.NotFound:
        pass
    real_calculator = (
        _repo_root() / "reference" / "fixture" / _CALCULATOR_PATH
    ).read_bytes()
    assert b"return left - right" in real_calculator


def test_finalize_after_failed_execution_removes_stopped_container() -> None:
    """A timeout-killed execution is finalized the same way: the stopped
    exact container and the root are removed with explicit clean flags."""
    candidate = build_fixture_candidate()
    materialized = materialize_candidate(
        candidate, allocate_execution_root(_MODULE_ROOT_BASE)
    )
    request = ExecutionRequestV1.model_validate(
        {
            **probe_request().model_dump(),
            "request_id": "req-18-d-timeout",
            "argv": {"arguments": ("python", "-c", "import time; time.sleep(60)")},
        }
    )
    result = DockerExecutor(timeout_seconds=5).execute(request, materialized)
    assert result.error_code == "CHECK_TIMEOUT"
    assert result.container_stopped is True
    cleanup = finalize_execution(result, candidate, materialized)
    assert cleanup.workspace_unchanged is True
    assert cleanup.container_removed is True
    assert cleanup.materialization_removed is True
    assert cleanup.residual_artifact is None
    assert not Path(materialized.root_path).exists()

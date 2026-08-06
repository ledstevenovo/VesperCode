"""T19.1 legacy step 19.B: real frozen-container pytest report channel.

One real fresh container from the frozen reference image runs pytest with
the production report plugin loaded explicitly (``-p
vespercode.validation.pytest_reporter``); the fixed ``GATEEV1:`` stdout
channel carries exactly one complete ordered ``PytestEvidenceV1`` document
that parses independently of exit code and console text (SPEC §4.5: the
machine-readable report is the authoritative input).  The candidate seeds
the production plugin module into the read-only workspace so ``python -m
pytest`` resolves the explicit plugin import inside the offline container.
"""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path
from collections.abc import Iterator

import pytest

pytest.importorskip("pydantic")

from src.vespercode.canonical.path_v1 import CanonicalRelativePathV1
from src.vespercode.contracts.optional import AbsentV1, PresentV1
from src.vespercode.execution.docker_executor import DockerExecutor
from src.vespercode.execution.docker_profile import ExecutionRequestV1
from src.vespercode.execution.materialization import (
    MaterializedCandidateV1,
    allocate_execution_root,
    materialize_candidate,
)
from src.vespercode.profiles.reference import load_reference_profile
from src.vespercode.trees.candidate import (
    CandidateTreeV1,
    root_candidate_revision,
)
from src.vespercode.trees.content_store import ContentObjectRefV1, ContentObjectStore
from src.vespercode.trees.snapshot import (
    SealedSnapshotInputFileV1,
    SnapshotDirectoryEntryV1,
    SnapshotEntryV1,
    SnapshotFileEntryV1,
    SnapshotTreeV1,
    _root_digest,
)
from src.vespercode.trees.text_classifier import (
    TextMetadataV1,
    classify_supported_text,
)
from src.vespercode.validation.pytest_evidence import (
    PytestReportExpectationV1,
    parse_pytest_evidence,
)

pytestmark = pytest.mark.docker_integration

# The frozen T18.1 request identity (SPEC §1.4.1/§1.4.5).
_MANIFEST_DIGEST = "896416f10ed751c4a2ebf763bb3cc6ba0ac90f0ca9e411bdc39c4ca0b93c4bca"
_IMAGE_DIGEST = "385ffc69d83536e1874d73517b8b9ee2a0dce6166ca0f30c1f3b1021324ea1a8"
_MAX_OUTPUT_BYTES = 4 * 1024**2
_PLUGIN_VERSION = "1"

_NODE_FAILS = "tests/test_report_channel.py::test_fails_on_purpose"
_NODE_PASSES = "tests/test_report_channel.py::test_passes"
_PLANNED = (_NODE_FAILS, _NODE_PASSES)


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _candidate_files() -> tuple[tuple[str, bytes], ...]:
    """The seeded workspace: fixture shape + the production plugin module."""
    fixture = _repo_root() / "reference" / "fixture"
    plugin = _repo_root() / "src" / "vespercode" / "validation" / "pytest_reporter.py"
    return (
        (
            "pyproject.toml",
            b"[project]\n"
            b'name = "vesper-fixture"\n'
            b'version = "0.1.0"\n'
            b'requires-python = ">=3.12,<3.13"\n'
            b"\n"
            b"[tool.pytest.ini_options]\n"
            b'testpaths = ["tests"]\n',
        ),
        ("requirements.lock", (fixture / "requirements.lock").read_bytes()),
        (
            "tests/test_report_channel.py",
            b"def test_fails_on_purpose():\n"
            b"    assert 1 == 2\n"
            b"\n"
            b"def test_passes():\n"
            b"    assert True\n",
        ),
        ("vespercode/__init__.py", b""),
        ("vespercode/validation/__init__.py", b""),
        ("vespercode/validation/pytest_reporter.py", plugin.read_bytes()),
    )


def _policy_digest() -> str:
    manifest = load_reference_profile(
        (
            _repo_root()
            / "src"
            / "vespercode"
            / "profiles"
            / "builtin"
            / "reference-profile-v1.json"
        ).read_bytes()
    )
    return manifest.editable_path_policy.digest


def build_channel_candidate() -> CandidateTreeV1:
    """One real candidate tree over the seeded report-channel workspace."""
    store = ContentObjectStore()
    rows: list[SealedSnapshotInputFileV1] = []
    for rel, raw in _candidate_files():
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
    policy_digest = _policy_digest()
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
    return root_candidate_revision(snapshot, store).tree


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
        "max_output_bytes": _MAX_OUTPUT_BYTES,
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


def _pytest_argv(*arguments: str) -> dict[str, object]:
    return {
        "arguments": (
            "python",
            "-m",
            "pytest",
            "-p",
            "vespercode.validation.pytest_reporter",
            "-o",
            "cacheprovider=disabled",
            "--rootdir",
            "/workspace",
            *arguments,
        )
    }


def full_pytest_request(request_id: str) -> ExecutionRequestV1:
    return ExecutionRequestV1.model_validate(
        {
            "schema_version": 1,
            "request_id": request_id,
            "reference_profile_digest": _MANIFEST_DIGEST,
            "docker_image_digest": _IMAGE_DIGEST,
            "docker_execution_profile_version": 1,
            "profile": builtin_profile_dict(),
            "argv": _pytest_argv("/workspace"),
        }
    )


def collect_only_request(request_id: str) -> ExecutionRequestV1:
    return ExecutionRequestV1.model_validate(
        {
            "schema_version": 1,
            "request_id": request_id,
            "reference_profile_digest": _MANIFEST_DIGEST,
            "docker_image_digest": _IMAGE_DIGEST,
            "docker_execution_profile_version": 1,
            "profile": builtin_profile_dict(),
            "argv": _pytest_argv("--collect-only", "/workspace"),
        }
    )


# Created lazily inside the autouse fixture, so a deselected module (the
# full suite runs with docker_integration deselected) never leaks a temp
# directory.
_MODULE_ROOT_BASE: Path | None = None


@pytest.fixture(scope="module", autouse=True)
def _remove_module_residue() -> Iterator[None]:
    global _MODULE_ROOT_BASE
    base = Path(tempfile.mkdtemp(prefix="vesper-t191-channel-"))
    _MODULE_ROOT_BASE = base
    yield
    _remove_executor_containers()
    shutil.rmtree(base, ignore_errors=True)


def _remove_executor_containers() -> None:
    """Remove every container created by this module's executor runs."""
    try:
        import docker  # type: ignore[import-untyped]

        client = docker.from_env()
        for container in client.containers.list(
            all=True, filters={"name": "vespercode-check"}
        ):
            container.remove(force=True)
    except Exception:
        pass


def _materialized() -> MaterializedCandidateV1:
    assert _MODULE_ROOT_BASE is not None
    root = allocate_execution_root(_MODULE_ROOT_BASE)
    return materialize_candidate(build_channel_candidate(), root)


def _expectation(run_kind: str) -> PytestReportExpectationV1:
    return PytestReportExpectationV1(
        schema_version=1,
        run_kind=run_kind,  # type: ignore[arg-type]
        planned_node_ids=_PLANNED,
        report_plugin_version=_PLUGIN_VERSION,
    )


def test_real_container_emits_complete_ordered_pytest_report() -> None:
    """One real full pytest run emits one authoritative report channel."""
    candidate = _materialized()
    executor = DockerExecutor()
    raw = executor.execute(full_pytest_request("req-19-b-full"), candidate)
    assert raw.error_code is None, raw.error_code
    assert raw.exit_code == 1  # the seeded failure
    outcome = parse_pytest_evidence(raw.stdout, _expectation("FULL_PYTEST"))
    assert outcome.error_code is None
    assert outcome.evidence is not None
    evidence = outcome.evidence
    assert evidence.run_kind == "FULL_PYTEST"
    assert evidence.collected_node_ids == _PLANNED
    assert evidence.pytest_exit_code == 1
    assert evidence.normal_end_marker is True
    assert evidence.events[0].event_type == "SESSION_START"
    assert evidence.events[-1].event_type == "SESSION_END"
    outcomes = {
        event.outcome.value
        for event in evidence.events
        if event.event_type == "TEST_PHASE" and event.outcome.kind == "PRESENT"
    }
    assert outcomes == {"FAIL", "PASS"}
    assert len(evidence.integrity_digest) == 64


def test_real_container_console_text_does_not_override_the_channel() -> None:
    """The bounded stdout carries console text; the channel is authoritative."""
    candidate = _materialized()
    executor = DockerExecutor()
    raw = executor.execute(full_pytest_request("req-19-b-console"), candidate)
    assert raw.error_code is None
    stdout_text = raw.stdout.decode("utf-8", errors="replace")
    assert "GATEEV1:" in stdout_text
    assert "passed" in stdout_text or "failed" in stdout_text
    outcome = parse_pytest_evidence(raw.stdout, _expectation("FULL_PYTEST"))
    assert outcome.error_code is None
    assert outcome.evidence is not None
    # The events are the authority: the failing node is FAIL in CALL phase
    # with a structured exception, independent of the console text.
    failure = next(
        event
        for event in outcome.evidence.events
        if event.event_type == "TEST_PHASE"
        and event.outcome.kind == "PRESENT"
        and event.outcome.value == "FAIL"
    )
    assert failure.phase.kind == "PRESENT"
    assert failure.phase.value == "CALL"
    assert failure.exception.kind == "PRESENT"
    assert failure.exception.value.exception_type == "AssertionError"


def test_real_container_collect_only_channel() -> None:
    """A real collect-only run emits the COLLECT_ONLY run kind."""
    candidate = _materialized()
    executor = DockerExecutor()
    raw = executor.execute(collect_only_request("req-19-b-collect"), candidate)
    assert raw.error_code is None
    assert raw.exit_code == 0
    outcome = parse_pytest_evidence(raw.stdout, _expectation("COLLECT_ONLY"))
    assert outcome.error_code is None
    assert outcome.evidence is not None
    assert outcome.evidence.run_kind == "COLLECT_ONLY"
    assert outcome.evidence.collected_node_ids == _PLANNED
    assert outcome.evidence.pytest_exit_code == 0
    assert outcome.evidence.events[-1].event_type == "SESSION_END"

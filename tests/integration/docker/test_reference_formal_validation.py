"""T21.1 legacy step 21.B: real frozen-container formal validation.

One real formal sequence over the supported-normal-form reference
workspace runs the complete frozen plan in fresh frozen containers
(T18.2 boundaries): the collect-only and full pytest checks complete
with authoritative real reports (the collect defines the collection, the
full run reproduces the target's CALL/FAIL over the real fixture), then
the sequence records the closed execution failures of the Ruff and Mypy
checks because the frozen reference image carries no ruff/mypy
executables (the T20.1/T20.2-recorded environment risk: the image's
frozen ``requirements.lock`` contains pytest 8.4.2 only; the frozen
image/Dockerfile are T02.1/T18.1 evidence and cannot change).  The
evidence therefore stays complete-ordered (every frozen request executed
exactly once, nothing missing or duplicated) but non-success (the tool
rows carry ``CHECK_EXECUTION_ERROR`` raw evidence), no
``VerifiedCandidate`` can ever exist, and zero residue remains.

The Manifest is the T20.2 publication contract over a baseline-shaped
record: its identity fields bind the real sealed Snapshot, the frozen
reference profile, and the real environment digests; its evidence
digests are documented synthetic values because the frozen image cannot
produce real target-rerun/Ruff/Mypy evidence (the real baseline blocks
at the missing Ruff executable, T20.2 evidence).  The formal preflight
and execution consume only the identity fields and the frozen argv.
"""

from __future__ import annotations

import tempfile
from collections.abc import Iterator
from pathlib import Path

import pytest

pytest.importorskip("pydantic")

from src.vespercode.candidate.final_diff import recompute_final_diff
from src.vespercode.candidate.identity import bind_revision_identity
from src.vespercode.canonical.path_v1 import CanonicalRelativePathV1
from src.vespercode.contracts.evidence import DigestV1
from src.vespercode.contracts.optional import AbsentV1, PresentV1
from src.vespercode.execution.docker_executor import DockerExecutor
from src.vespercode.profiles.reference import load_reference_profile
from src.vespercode.trees.candidate import root_candidate_revision
from src.vespercode.trees.content_store import ContentObjectRefV1, ContentObjectStore
from src.vespercode.trees.snapshot import (
    SealedSnapshotInputFileV1,
    SnapshotDirectoryEntryV1,
    SnapshotEntryV1,
    SnapshotFileEntryV1,
    SnapshotTreeV1,
    _root_digest,
)
from src.vespercode.trees.text_classifier import TextMetadataV1, classify_supported_text
from src.vespercode.validation.baseline import (
    BaselineTestRecordV1,
    PassingBaselineV1,
    RuntimeCompatibleV1,
    compute_environment_whitelist_digest,
    compute_protected_artifact_set_digest,
    compute_resource_parameters_digest,
)
from src.vespercode.validation.formal_execution import execute_formal_plan
from src.vespercode.validation.formal_plan import (
    FormalValidationPlanV1,
    build_formal_validation_plan,
)
from src.vespercode.validation.manifest import (
    ManifestBindingsV1,
    ValidationManifestV1,
    create_validation_manifest,
)

pytestmark = pytest.mark.docker_integration

_ADD = "tests/test_calculator.py::test_add_returns_sum"
_MULTIPLY = "tests/test_calculator.py::test_multiply_returns_product"
_A = "a" * 64
_B = "b" * 64
_C = "c" * 64
_D = "d" * 64
_E = "e" * 64
_F = "f" * 64


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _packaged_manifest_bytes() -> bytes:
    return (
        _repo_root()
        / "src"
        / "vespercode"
        / "profiles"
        / "builtin"
        / "reference-profile-v1.json"
    ).read_bytes()


def _policy_digest() -> str:
    return load_reference_profile(
        _packaged_manifest_bytes()
    ).editable_path_policy.digest


def _supported_pyproject_bytes() -> bytes:
    """The supported-normal-form pyproject (SPEC §1.4.1 normal form)."""
    return (
        b"[project]\n"
        b'name = "vesper-fixture"\n'
        b'version = "0.1.0"\n'
        b'requires-python = ">=3.12,<3.13"\n'
        b"\n"
        b"[tool.pytest.ini_options]\n"
        b'testpaths = ["tests"]\n'
        b'pythonpath = ["src"]\n'
        b"\n"
        b"[tool.ruff]\n"
        b"line-length = 88\n"
        b"\n"
        b"[tool.mypy]\n"
        b'python_version = "3.12"\n'
        b"strict = true\n"
    )


def _seeded_workspace_files() -> tuple[tuple[str, bytes], ...]:
    """The supported-normal-form workspace: the real fixture files that
    can be included byte-identically plus the seeded report plugin."""
    fixture = _repo_root() / "reference" / "fixture"
    plugin = _repo_root() / "src" / "vespercode" / "validation" / "pytest_reporter.py"
    return (
        ("pyproject.toml", _supported_pyproject_bytes()),
        ("requirements.lock", (fixture / "requirements.lock").read_bytes()),
        (
            "src/vesper_fixture/calculator.py",
            (fixture / "src/vesper_fixture/calculator.py").read_bytes(),
        ),
        (
            "tests/test_calculator.py",
            (fixture / "tests/test_calculator.py").read_bytes(),
        ),
        ("vespercode/__init__.py", b""),
        ("vespercode/validation/__init__.py", b""),
        ("vespercode/validation/pytest_reporter.py", plugin.read_bytes()),
    )


def _sealed_snapshot(files: tuple[tuple[str, bytes], ...]) -> SnapshotTreeV1:
    """One sealed Snapshot over the given workspace bytes (T10.2)."""
    store = ContentObjectStore()
    rows: list[SealedSnapshotInputFileV1] = []
    for rel, raw in files:
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
        text_profile: PresentV1[TextMetadataV1] | AbsentV1 = (
            classification.text_profile
            if classification.kind == "TEXT_FILE"
            else AbsentV1(kind="ABSENT")
        )
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
    return SnapshotTreeV1(
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


def _record(
    node_id: str,
    status: str,
    *,
    fingerprint: str | None = None,
) -> BaselineTestRecordV1:
    return BaselineTestRecordV1(
        schema_version=1,
        node_id=node_id,
        status=status,  # type: ignore[arg-type]
        error_phase=AbsentV1(kind="ABSENT"),
        failure_fingerprint_digest=(
            PresentV1(kind="PRESENT", value=DigestV1(value=fingerprint))
            if fingerprint is not None
            else AbsentV1(kind="ABSENT")
        ),
    )


def _real_manifest(snapshot: SnapshotTreeV1) -> ValidationManifestV1:
    """One Manifest bound to the real Snapshot and the frozen profile.

    The evidence digests are documented synthetic values: the frozen
    image carries pytest 8.4.2 only, so the real baseline cannot produce
    target-rerun/Ruff/Mypy evidence (T20.2 evidence) and the formal
    execution consumes only the Manifest's identity fields.
    """
    frozen = load_reference_profile(_packaged_manifest_bytes())
    baseline = PassingBaselineV1(
        schema_version=1,
        kind="PASSING",
        plan_digest=_A,
        check_plan_version=frozen.check_plan_version,
        adapter_version="1",
        python_version=frozen.python_version,
        pytest_version=frozen.pytest_version,
        report_plugin_version=frozen.report_plugin_version,
        ruff_version=frozen.ruff_version,
        mypy_version=frozen.mypy_version,
        docker_image_digest=frozen.docker_image_digest,
        docker_execution_profile_version=1,
        reference_profile_digest=frozen.digest,
        snapshot_root_digest=snapshot.root_digest,
        repository_policy_digest=snapshot.repository_policy_digest,
        target_test_ids=(_ADD,),
        collected_node_ids=(_ADD, _MULTIPLY),
        collect_only_evidence_digests=(_A, _A),
        full_pytest_evidence_digest=_B,
        target_rerun_evidence_digest=_C,
        ruff_result_digest=_D,
        mypy_result_digest=_E,
        baseline_test_records=(
            _record(_ADD, "FAIL", fingerprint=_F),
            _record(_MULTIPLY, "PASS"),
        ),
        protected_artifact_set_digest=compute_protected_artifact_set_digest(snapshot),
        runtime_compatibility=RuntimeCompatibleV1(
            schema_version=1,
            status="COMPATIBLE",
            reference_profile_digest=frozen.digest,
            evidence_digest=_E,
        ),
    )
    return create_validation_manifest(
        baseline,
        ManifestBindingsV1(
            schema_version=1,
            resource_parameters_digest=compute_resource_parameters_digest(),
            environment_whitelist_digest=compute_environment_whitelist_digest(),
        ),
    )


def _frozen_plan(snapshot: SnapshotTreeV1) -> FormalValidationPlanV1:
    """One complete frozen formal plan over the real supported workspace."""
    manifest = _real_manifest(snapshot)
    store = ContentObjectStore()
    for _path, raw in snapshot.file_bytes:
        store.put(raw)
    revision = root_candidate_revision(snapshot, store)
    diff = recompute_final_diff(
        snapshot,
        revision.tree,
        load_reference_profile(_packaged_manifest_bytes()).editable_path_policy,
    )
    bound = bind_revision_identity(revision, diff.digest)
    result = build_formal_validation_plan(manifest, bound, diff)
    assert isinstance(result, FormalValidationPlanV1)
    return result


@pytest.fixture(scope="module", autouse=True)
def _remove_module_residue() -> Iterator[None]:
    yield
    _remove_executor_containers()


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


def _executor_container_ids() -> set[str]:
    try:
        import docker

        client = docker.from_env()
        return {
            str(container.id)
            for container in client.containers.list(
                all=True, filters={"name": "vespercode-check"}
            )
        }
    except Exception:
        return set()


def _formal_temp_dirs() -> set[str]:
    """The formal execution-root base directories in the system temp."""
    return {
        entry.name
        for entry in Path(tempfile.gettempdir()).iterdir()
        if entry.is_dir() and entry.name.startswith("vesper-formal-")
    }


def test_reference_formal_validation_completes_ordered_then_fails_closed_at_missing_tools() -> (
    None
):
    """The real four-check formal sequence over the supported workspace.

    The two pytest checks complete with authoritative real reports (the
    collect-only defines the collection; the full run reproduces the
    target's CALL/FAIL over the real fixture bytes), then the Ruff and
    Mypy checks record their closed execution failures because the
    frozen image has no ``ruff``/``mypy`` executables
    (``CHECK_EXECUTION_ERROR`` raw evidence; the documented environment
    risk — the frozen image/Dockerfile are T02.1/T18.1 evidence and
    cannot change), so the evidence is complete-ordered but non-success,
    no ``VerifiedCandidate`` can exist, and zero residue remains.
    """
    before_containers = _executor_container_ids()
    before_dirs = _formal_temp_dirs()
    snapshot = _sealed_snapshot(_seeded_workspace_files())
    plan = _frozen_plan(snapshot)
    evidence = execute_formal_plan(plan, DockerExecutor())

    # Every frozen request executed exactly once in plan order.
    assert evidence.executed_request_ids == plan.request_ids
    assert evidence.missing_request_ids == ()
    assert evidence.duplicate_request_ids == ()

    # The pytest checks parsed authoritative real reports.
    assert isinstance(evidence.evidence[0].pytest_evidence, PresentV1)
    assert evidence.evidence[0].pytest_evidence.value.run_kind == "COLLECT_ONLY"
    assert evidence.evidence[0].pytest_evidence.value.collected_node_ids == (
        _ADD,
        _MULTIPLY,
    )
    assert isinstance(evidence.evidence[1].pytest_evidence, PresentV1)
    assert evidence.evidence[1].pytest_evidence.value.run_kind == "FULL_PYTEST"

    # The tool checks failed closed at the missing executables.
    assert evidence.evidence[2].raw is not None
    assert evidence.evidence[2].raw.error_code == "CHECK_EXECUTION_ERROR"
    assert isinstance(evidence.evidence[2].tool_result, PresentV1)
    assert evidence.evidence[2].tool_result.value.status == "ERROR"
    assert evidence.evidence[3].raw is not None
    assert evidence.evidence[3].raw.error_code == "CHECK_EXECUTION_ERROR"
    assert isinstance(evidence.evidence[3].tool_result, PresentV1)
    assert evidence.evidence[3].tool_result.value.status == "ERROR"

    # The evidence is complete-ordered but explicitly non-success.
    assert evidence.complete is False

    # Zero residue: no surviving containers, no surviving roots.
    assert _executor_container_ids() == before_containers
    assert _formal_temp_dirs() == before_dirs

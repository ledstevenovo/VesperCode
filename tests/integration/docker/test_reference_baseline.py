"""T20.2 legacy step 20.B: real frozen-container Baseline execution.

One real Baseline sequence over the supported-normal-form reference
workspace runs in fresh frozen containers (T18.2 boundaries): the two
collect-only runs establish a stable collection, the full pytest run
reproduces the target's ``CALL``/``FAIL``, and the target rerun produces
the same complete ``CALL``/``FAIL`` report (digest-level fingerprint
equality is pinned by the unit matrix) — then the sequence fails closed at
the Ruff check because the frozen reference image carries no ruff/mypy
executables (the T20.1-recorded environment risk: the image's frozen
``requirements.lock`` contains pytest 8.4.2 only; the frozen
image/Dockerfile are T02.1/T18.1 evidence and cannot change).  A second
real run over the frozen fixture bytes fails closed at the first
collect-only because the fixture's pyproject.toml is invalid TOML by
design (T02.1 evidence byte) and the plugin module is absent.  Both runs
publish no manifest and leave zero residue.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from collections.abc import Iterator

import pytest

pytest.importorskip("pydantic")

from vespercode.canonical.path_v1 import CanonicalRelativePathV1
from vespercode.contracts.optional import AbsentV1, PresentV1
from vespercode.execution.docker_executor import DockerExecutor
from vespercode.profiles.reference import load_reference_profile
from vespercode.trees.content_store import ContentObjectRefV1, ContentObjectStore
from vespercode.trees.snapshot import (
    SealedSnapshotInputFileV1,
    SnapshotDirectoryEntryV1,
    SnapshotEntryV1,
    SnapshotFileEntryV1,
    SnapshotTreeV1,
    _root_digest,
)
from vespercode.trees.text_classifier import TextMetadataV1, classify_supported_text
from vespercode.validation.baseline import (
    BaselineBlockedV1,
    run_baseline,
)
from vespercode.validation.python_adapter import (
    BaselineCheckPlanV1,
    PythonProjectAdapterV1,
    SupportedProjectV1,
    TargetTestIdSequenceV1,
)

pytestmark = pytest.mark.docker_integration

_ADD = "tests/test_calculator.py::test_add_returns_sum"
_MULTIPLY = "tests/test_calculator.py::test_multiply_returns_product"


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
    manifest = load_reference_profile(_packaged_manifest_bytes())
    return manifest.editable_path_policy.digest


def _supported_pyproject_bytes() -> bytes:
    """The supported-normal-form pyproject (SPEC §1.4.1 normal form).

    The frozen reference fixture's own pyproject.toml is invalid TOML
    (``strict = True``, a T02.1 evidence byte that cannot change) and its
    tests cannot resolve ``import vesper_fixture`` under profile v1's
    frozen environment (the T02.4 probe needed PYTHONPATH and ``-c
    /dev/null``, both unavailable in profile v1); the docker-test
    workspace is the statically-supported normal form — the same shape
    T20.1's static matrix uses — with the pytest-8 ``pythonpath`` ini
    option that makes the ``src/`` layout importable under the frozen
    environment.  The frozen fixture bytes that CAN be included (the
    calculator and its tests) are byte-identical to the T02.1 evidence.
    """
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


def _real_fixture_files() -> tuple[tuple[str, bytes], ...]:
    """The frozen reference fixture bytes, byte-for-byte (T02.1 evidence)."""
    fixture = _repo_root() / "reference" / "fixture"
    return tuple(
        (rel.relative_to(fixture).as_posix(), rel.read_bytes())
        for rel in sorted(fixture.rglob("*"))
        if rel.is_file()
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


def _seeded_plan(snapshot: SnapshotTreeV1) -> BaselineCheckPlanV1:
    manifest = load_reference_profile(_packaged_manifest_bytes())
    adapter = PythonProjectAdapterV1(manifest)
    static = adapter.detect_static(snapshot, manifest)
    assert static.kind == "SUPPORTED", static.reasons
    return adapter.build_baseline_plan(
        static, TargetTestIdSequenceV1(target_test_ids=(_ADD,))
    )


def _real_fixture_plan(snapshot: SnapshotTreeV1) -> BaselineCheckPlanV1:
    """One frozen plan bound to the real fixture Snapshot.

    The real fixture is statically UNSUPPORTED under the production
    adapter (its pyproject.toml is invalid TOML — a T02.1 evidence byte),
    so the plan is bound directly from the frozen manifest identity to
    observe the real container behavior of the frozen argv over the
    frozen fixture bytes (fail closed at the first collect-only).
    """
    manifest = load_reference_profile(_packaged_manifest_bytes())
    adapter = PythonProjectAdapterV1(manifest)
    static = SupportedProjectV1(
        kind="SUPPORTED",
        profile_id=manifest.profile_id,
        reference_profile_digest=manifest.digest,
        snapshot_root_digest=snapshot.root_digest,
        repository_policy_digest=snapshot.repository_policy_digest,
    )
    return adapter.build_baseline_plan(
        static, TargetTestIdSequenceV1(target_test_ids=(_ADD,))
    )


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


def _baseline_temp_dirs() -> set[str]:
    """The run_baseline execution-root base directories in the system
    temp (``run_baseline`` allocates its own per-run base; each one must
    be removed by the finally backstop — zero residue)."""
    return {
        entry.name
        for entry in Path(tempfile.gettempdir()).iterdir()
        if entry.is_dir() and entry.name.startswith("vesper-baseline-")
    }


def test_real_baseline_stable_failures_then_fails_closed_at_undeclared_tools() -> None:
    """The real six-check sequence over the supported workspace.

    The pytest checks complete with a stable collection and complete
    CALL/FAIL reports for the target in both the full run and the target
    rerun (four real containers; the byte-identical repeated fingerprint
    comparison and the whole §4.5 predicate layer are pinned by the unit
    matrix — the real run then fails closed at the Ruff check because the
    frozen image has no ``ruff`` executable (``CHECK_EXECUTION_ERROR`` ->
    ``CHECK_ERROR``), so the predicate layer is unreachable with the
    frozen image, exactly as the documented environment risk predicts),
    no manifest publishes, and zero residue remains.
    """
    before_containers = _executor_container_ids()
    before_dirs = _baseline_temp_dirs()
    snapshot = _sealed_snapshot(_seeded_workspace_files())
    plan = _seeded_plan(snapshot)
    result = run_baseline(plan, snapshot, DockerExecutor())
    assert isinstance(result, BaselineBlockedV1)
    assert result.reason == "CHECK_ERROR"
    assert isinstance(result.violation_kind, AbsentV1)
    # The four pytest checks completed first: their evidence digests are
    # the first four refs, then the offending Ruff raw evidence.
    assert len(result.evidence_refs) == 5
    assert all(len(ref) == 64 for ref in result.evidence_refs)
    assert _executor_container_ids() == before_containers
    assert _baseline_temp_dirs() == before_dirs


def test_real_baseline_over_frozen_fixture_bytes_fails_closed_at_collect() -> None:
    """The frozen fixture bytes cannot collect under the frozen profile:
    its pyproject.toml is invalid TOML (T02.1 evidence byte) and the
    plugin module is absent, so pytest exits before any report channel
    and the baseline blocks REPORTER_INVALID with zero publication."""
    before_containers = _executor_container_ids()
    before_dirs = _baseline_temp_dirs()
    snapshot = _sealed_snapshot(_real_fixture_files())
    plan = _real_fixture_plan(snapshot)
    result = run_baseline(plan, snapshot, DockerExecutor())
    assert isinstance(result, BaselineBlockedV1)
    assert result.reason == "REPORTER_INVALID"
    assert isinstance(result.violation_kind, AbsentV1)
    assert len(result.evidence_refs) == 1
    assert all(len(ref) == 64 for ref in result.evidence_refs)
    assert _executor_container_ids() == before_containers
    assert _baseline_temp_dirs() == before_dirs

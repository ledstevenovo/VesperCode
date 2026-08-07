"""T18.2 legacy step 18.D: post-execution integrity and cleanup matrix.

The card's exact RED test (the smallest post-run byte drift in the
materialized workspace fails closed) and the 18.D cleanup link-integrity
matrix: post-run Candidate byte/identity drift, a new link/device,
incomplete teardown, or a cleanup failure fails closed with explicit
residual evidence; success requires the exact unchanged Candidate and
zero surviving container/materialization (GREEN-1..GREEN-4).
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path
from collections.abc import Iterator

import pytest

pytest.importorskip("pydantic")

from vespercode.canonical.path_v1 import CanonicalRelativePathV1
from vespercode.contracts.optional import AbsentV1, PresentV1
from vespercode.contracts.evidence import ArtifactRefV1
from vespercode.execution.cleanup import (
    finalize_execution,
)
from vespercode.execution.docker_executor import RawExecutionResultV1
from vespercode.execution.materialization import (
    MaterializedCandidateV1,
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


def candidate() -> CandidateTreeV1:
    return build_fixture_candidate()


_MODULE_ROOT_BASE = Path(tempfile.mkdtemp(prefix="vesper-t182-cleanup-"))


@pytest.fixture(scope="module", autouse=True)
def _remove_module_root_bases() -> Iterator[None]:
    yield
    shutil.rmtree(_MODULE_ROOT_BASE, ignore_errors=True)


def fresh_materialization() -> MaterializedCandidateV1:
    return materialize_candidate(
        candidate(), allocate_execution_root(_MODULE_ROOT_BASE)
    )


def raw_result(container_id: str = "0" * 64) -> RawExecutionResultV1:
    """One fabricated bounded raw result for a completed execution."""
    return RawExecutionResultV1(
        schema_version=1,
        request_id="req-18-d-1",
        container_id=container_id,
        exit_code=0,
        stdout=b"",
        stderr=b"",
        output_bytes=0,
        timed_out=False,
        output_limit_exceeded=False,
        container_stopped=False,
        error_code=None,
    )


def mutated_materialization() -> MaterializedCandidateV1:
    """The smallest post-run byte drift: one materialized file overwritten."""
    materialized = fresh_materialization()
    target = Path(materialized.root_path) / materialized.files[0].path
    target.write_bytes(target.read_bytes() + b"drift")
    return materialized


def test_post_execution_candidate_mutation_fails_closed() -> None:
    result = finalize_execution(raw_result(), candidate(), mutated_materialization())
    assert result.workspace_unchanged is False


def test_execution_cleanup_link_integrity_matrix() -> None:
    """18.D matrix (PLAN 18.D): post-run Candidate byte/identity drift,
    new link/device, incomplete teardown, or cleanup failure fails closed;
    success requires the exact unchanged Candidate and zero surviving
    container/materialization.
    """
    # --- Success: exact unchanged Candidate, exact resources removed. ---
    materialized = fresh_materialization()
    result = finalize_execution(raw_result(), candidate(), materialized)
    assert result.workspace_unchanged is True
    assert result.container_removed is True
    assert result.materialization_removed is True
    assert result.residual_artifact is None
    assert not Path(materialized.root_path).exists()

    # --- Candidate byte drift: the smallest post-run byte drift fails
    # closed with explicit residual evidence; removal still proceeds. ---
    drifted = mutated_materialization()
    drifted_result = finalize_execution(raw_result(), candidate(), drifted)
    assert drifted_result.workspace_unchanged is False
    assert drifted_result.container_removed is True
    assert drifted_result.materialization_removed is True
    assert isinstance(drifted_result.residual_artifact, ArtifactRefV1)
    assert drifted_result.residual_artifact.artifact_id.startswith("workspace:")

    # --- Candidate identity drift: a tampered materialization table fails
    # closed (the sealed digest no longer binds the rows). ---
    identity_materialized = fresh_materialization()
    tampered = identity_materialized.model_copy(
        update={"files": identity_materialized.files[1:]}
    )
    identity_result = finalize_execution(raw_result(), candidate(), tampered)
    assert identity_result.workspace_unchanged is False
    assert isinstance(identity_result.residual_artifact, ArtifactRefV1)

    # --- New link: a junction planted inside the root during execution is
    # drift; removal removes the link without following it. ---
    linked = fresh_materialization()
    link_target = _MODULE_ROOT_BASE / "link-target"
    link_target.mkdir()
    (link_target / "secret.txt").write_bytes(b"outside-bytes")
    link = Path(linked.root_path) / "evil-link"
    try:
        _make_junction(link, link_target)
    except OSError:
        pytest.skip("junction creation is not available on this host")
    linked_result = finalize_execution(raw_result(), candidate(), linked)
    assert linked_result.workspace_unchanged is False
    assert linked_result.materialization_removed is True
    assert link_target.is_dir()
    assert (link_target / "secret.txt").read_bytes() == b"outside-bytes"

    # --- New file inside an existing materialized directory: a nested
    # entry is drift (SPEC §4.5: any project-tree write is mutation). ---
    nested_file = fresh_materialization()
    (Path(nested_file.root_path) / "src" / "evil.py").write_bytes(b"evil")
    nested_file_result = finalize_execution(raw_result(), candidate(), nested_file)
    assert nested_file_result.workspace_unchanged is False
    assert nested_file_result.materialization_removed is True
    assert isinstance(nested_file_result.residual_artifact, ArtifactRefV1)

    # --- New link inside an existing materialized directory: drift, and
    # removal removes the link without following it. ---
    nested_linked = fresh_materialization()
    nested_target = _MODULE_ROOT_BASE / "nested-link-target"
    nested_target.mkdir()
    (nested_target / "secret.txt").write_bytes(b"outside-bytes")
    nested_link = Path(nested_linked.root_path) / "src" / "evil-link"
    try:
        _make_junction(nested_link, nested_target)
    except OSError:
        pytest.skip("junction creation is not available on this host")
    nested_linked_result = finalize_execution(raw_result(), candidate(), nested_linked)
    assert nested_linked_result.workspace_unchanged is False
    assert nested_linked_result.materialization_removed is True
    assert nested_target.is_dir()
    assert (nested_target / "secret.txt").read_bytes() == b"outside-bytes"

    # --- New link at a directory level: the ancestor check fails closed
    # and removal never traverses the junction. ---
    directory_linked = fresh_materialization()
    src = Path(directory_linked.root_path) / "src"
    src_original = _MODULE_ROOT_BASE / "src-original"
    src.rename(src_original)
    try:
        _make_junction(src, src_original)
    except OSError:
        pytest.skip("junction creation is not available on this host")
    directory_result = finalize_execution(raw_result(), candidate(), directory_linked)
    assert directory_result.workspace_unchanged is False
    assert directory_result.materialization_removed is True
    assert src_original.is_dir()

    # --- Incomplete teardown: an unprovable root identity is never
    # removed and the residual names the exact surviving path. ---
    unprovable = fresh_materialization()
    (Path(unprovable.root_path) / ".vespercode-execution-root").unlink()
    unprovable_result = finalize_execution(raw_result(), candidate(), unprovable)
    assert unprovable_result.materialization_removed is False
    assert Path(unprovable.root_path).exists()
    assert isinstance(unprovable_result.residual_artifact, ArtifactRefV1)
    assert unprovable_result.residual_artifact.artifact_id.startswith(
        "materialization:"
    )
    shutil.rmtree(unprovable.root_path, ignore_errors=True)

    # --- Cleanup failure: a container that survives removal is reported
    # with the residual container identity. ---
    surviving = finalize_execution(
        raw_result(container_id="f" * 64),
        candidate(),
        fresh_materialization(),
        client_factory=lambda: _FakeCleanupClient(
            inspect_present=True,
        ),
    )
    assert surviving.container_removed is False
    assert isinstance(surviving.residual_artifact, ArtifactRefV1)
    assert surviving.residual_artifact.artifact_id == f"container:{'f' * 64}"

    # --- No-container result: an execution that never created a container
    # is vacuously removed. ---
    no_container = finalize_execution(
        RawExecutionResultV1(
            schema_version=1,
            request_id="req-18-d-2",
            container_id="",
            exit_code=None,
            stdout=b"",
            stderr=b"",
            output_bytes=0,
            timed_out=False,
            output_limit_exceeded=False,
            container_stopped=False,
            error_code="CHECK_EXECUTION_ERROR",
        ),
        candidate(),
        fresh_materialization(),
        client_factory=lambda: _FakeCleanupClient(),
    )
    assert no_container.container_removed is True
    assert no_container.workspace_unchanged is True
    assert no_container.residual_artifact is None

    # --- Idempotent replay: a second finalize of an already-clean
    # execution reports the same clean verdict. ---
    replayed_materialization = fresh_materialization()
    first = finalize_execution(raw_result(), candidate(), replayed_materialization)
    second = finalize_execution(raw_result(), candidate(), replayed_materialization)
    assert first.workspace_unchanged is True
    assert first.residual_artifact is None
    assert second.workspace_unchanged is True
    assert second.container_removed is True
    assert second.materialization_removed is True
    assert second.residual_artifact is None


def _make_junction(link: Path, target: Path) -> None:
    """Create a real NTFS junction (no admin rights required)."""
    proc = subprocess.run(
        ["cmd", "/c", "mklink", "/J", str(link), str(target)],
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        raise OSError(proc.stderr.strip() or "mklink /J failed")


class _FakeCleanupAPIClient:
    def __init__(self, inspect_present: bool) -> None:
        self._inspect_present = inspect_present
        self.remove_calls: list[str] = []

    def remove_container(self, container_id: str, force: bool = False) -> object:
        self.remove_calls.append(container_id)
        return None

    def inspect_container(self, container_id: str) -> object:
        if self._inspect_present:
            return {"Id": container_id}
        raise LookupError(f"no such container {container_id}")


class _FakeCleanupClient:
    def __init__(self, inspect_present: bool = False) -> None:
        self.api = _FakeCleanupAPIClient(inspect_present=inspect_present)

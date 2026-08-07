"""T21.1 legacy step 21.A: formal-validation preflight tests.

``build_formal_validation_plan`` recomputes the exact current candidate
bytes, final-diff/protected-path state, policy identity, environment/
reference profile, Manifest, target, and collection bindings before any
execution request exists, and freezes the complete ordered collect/full
pytest/Ruff/Mypy request plan with immutable request identities,
candidate identity, bounds, argv, and expected evidence.  Every stale,
drifted, protected, or out-of-policy input yields zero execution
requests (SPEC §4.5 "检查容器调用次数均为零"); only exact current
inputs create the complete frozen plan (GREEN-1..GREEN-4).
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable

import pytest

# The formal-plan contracts are pydantic runtime models; the hash-locked
# gate toolchain does not install runtime dependencies, so this module
# skips cleanly there instead of failing at collection (formal env runs
# it fully).
pytest.importorskip("pydantic")

from vespercode.candidate.final_diff import (
    FinalDiffEntryV1,
    FinalDiffPreimageV1,
    FinalDiffV1,
    recompute_final_diff,
)
from vespercode.candidate.identity import bind_revision_identity
from vespercode.canonical.path_v1 import CanonicalRelativePathV1
from vespercode.contracts.evidence import DigestV1
from vespercode.contracts.optional import AbsentV1, PresentV1
from vespercode.profiles.reference import (
    ReferenceProfileManifestV1,
    load_reference_profile,
)
from vespercode.trees.candidate import (
    CandidatePostimageV1,
    CandidateRevisionV1,
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
from vespercode.trees.text_classifier import TextMetadataV1, classify_supported_text
from vespercode.validation.baseline import (
    BaselineTestRecordV1,
    PassingBaselineV1,
    RuntimeCompatibleV1,
    compute_environment_whitelist_digest,
    compute_protected_artifact_set_digest,
    compute_resource_parameters_digest,
)
from vespercode.validation.formal_plan import (
    FormalPlanRejectedV1,
    FormalValidationPlanV1,
    build_formal_validation_plan,
    formal_validation_plan_digest,
)
from vespercode.validation.manifest import (
    ManifestBindingsV1,
    ValidationManifestV1,
    create_validation_manifest,
    validation_manifest_digest,
)

_ADD = "tests/test_calculator.py::test_add_returns_sum"
_MULTIPLY = "tests/test_calculator.py::test_multiply_returns_product"
_A = "a" * 64
_B = "b" * 64
_C = "c" * 64
_D = "d" * 64
_E = "e" * 64
_F = "f" * 64
_ZERO = "0" * 64


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _frozen_manifest() -> ReferenceProfileManifestV1:
    return load_reference_profile(
        (
            _repo_root()
            / "src"
            / "vespercode"
            / "profiles"
            / "builtin"
            / "reference-profile-v1.json"
        ).read_bytes()
    )


def _supported_pyproject_bytes() -> bytes:
    """The supported-normal-form pyproject (SPEC §1.4.1 normal form;
    the frozen fixture bytes are T02.1 evidence and cannot change)."""
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


def _workspace_files() -> tuple[tuple[str, bytes], ...]:
    """The supported-normal-form workspace bytes (real fixture files
    byte-identical to the T02.1 evidence plus the supported pyproject)."""
    fixture = _repo_root() / "reference" / "fixture"
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
    )


def _sealed_snapshot(
    files: tuple[tuple[str, bytes], ...] | None = None,
) -> SnapshotTreeV1:
    """One sealed Snapshot over the given workspace bytes (T10.2)."""
    store = ContentObjectStore()
    rows: list[SealedSnapshotInputFileV1] = []
    for rel, raw in files or _workspace_files():
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
    policy_digest = _frozen_manifest().editable_path_policy.digest
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


def _passing_baseline(snapshot: SnapshotTreeV1) -> PassingBaselineV1:
    frozen = _frozen_manifest()
    return PassingBaselineV1(
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


def _manifest(snapshot: SnapshotTreeV1) -> ValidationManifestV1:
    """One exact-current Manifest bound to the sealed Snapshot and the
    frozen reference profile (published through the T20.2 publication
    contract so every closed invariant holds)."""
    return create_validation_manifest(
        _passing_baseline(snapshot),
        ManifestBindingsV1(
            schema_version=1,
            resource_parameters_digest=compute_resource_parameters_digest(),
            environment_whitelist_digest=compute_environment_whitelist_digest(),
        ),
    )


def _root_revision(
    snapshot: SnapshotTreeV1,
) -> tuple[CandidateRevisionV1, ContentObjectStore]:
    """The run's root candidate revision over the sealed Snapshot."""
    store = ContentObjectStore()
    for _path, raw in snapshot.file_bytes:
        store.put(raw)
    return root_candidate_revision(snapshot, store), store


def _final_diff(snapshot: SnapshotTreeV1, tree: CandidateTreeV1) -> FinalDiffV1:
    """The exact recomputed current Snapshot-to-candidate net diff."""
    return recompute_final_diff(snapshot, tree, _frozen_manifest().editable_path_policy)


def _candidate(snapshot: SnapshotTreeV1) -> tuple[CandidateRevisionV1, FinalDiffV1]:
    """The exact current identity-bound candidate revision and its diff."""
    revision, _store = _root_revision(snapshot)
    diff = _final_diff(snapshot, revision.tree)
    return bind_revision_identity(revision, diff.digest), diff


def _drifted_manifest(**tamper: object) -> ValidationManifestV1:
    """One internally consistent drifted Manifest: its digest binds its
    drifted fields exactly as a real drifted Manifest would (the
    ``model_copy`` spelling is only for the tampered-identity rows)."""
    drifted = _manifest(_sealed_snapshot()).model_copy(update=tamper)
    fields = {
        name: getattr(drifted, name) for name in ValidationManifestV1.model_fields
    }
    probe = ValidationManifestV1.model_construct(**fields)
    return ValidationManifestV1.model_validate(
        {**fields, "digest": validation_manifest_digest(probe)}
    )


def _stale_candidate() -> CandidateRevisionV1:
    """A candidate whose bound identity no longer matches the exact
    current triple (the smallest stale-candidate fixture)."""
    revision, _diff = _candidate(_sealed_snapshot())
    return revision.model_copy(update={"candidate_digest": _ZERO})


def manifest() -> ValidationManifestV1:
    """One exact-current Manifest over the supported workspace."""
    return _manifest(_sealed_snapshot())


def final_diff() -> FinalDiffV1:
    """The exact recomputed current diff of the root candidate."""
    snapshot = _sealed_snapshot()
    return _final_diff(snapshot, _root_revision(snapshot)[0].tree)


def stale_candidate() -> CandidateRevisionV1:
    """The smallest stale candidate: exact current triple except the
    bound candidate identity digest."""
    return _stale_candidate()


def test_stale_candidate_produces_zero_execution_requests() -> None:
    result = build_formal_validation_plan(manifest(), stale_candidate(), final_diff())
    assert result.error_code == "CANDIDATE_STALE"
    assert result.execution_requests == ()


def _exact_current_result() -> FormalValidationPlanV1 | FormalPlanRejectedV1:
    snapshot = _sealed_snapshot()
    revision, diff = _candidate(snapshot)
    return build_formal_validation_plan(_manifest(snapshot), revision, diff)


def test_exact_current_inputs_freeze_the_complete_ordered_plan() -> None:
    result = _exact_current_result()
    assert isinstance(result, FormalValidationPlanV1)
    assert result.error_code is None
    # The complete ordered collect/full pytest/Ruff/Mypy request plan.
    assert tuple(request.check_kind for request in result.execution_requests) == (
        "COLLECT_ONLY",
        "FULL_PYTEST",
        "RUFF",
        "MYPY",
    )
    assert result.request_ids == tuple(
        f"formal-{kind}-{ordinal}"
        for ordinal, kind in enumerate(
            ("COLLECT_ONLY", "FULL_PYTEST", "RUFF", "MYPY"), start=1
        )
    )
    # Candidate identity, bounds, and expected evidence are frozen.
    assert result.candidate_tree_digest != result.manifest_digest
    assert result.bounds.full_check_timeout_seconds == 300
    assert result.bounds.formal_validation_timeout_seconds == 600
    full_request = result.execution_requests[1]
    assert isinstance(full_request.expectation.pytest, PresentV1)
    assert full_request.expectation.pytest.value.planned_node_ids == (
        _ADD,
        _MULTIPLY,
    )
    assert result.digest == formal_validation_plan_digest(result)
    # The same exact current inputs produce the identical frozen plan.
    again = _exact_current_result()
    assert isinstance(again, FormalValidationPlanV1)
    assert again.digest == result.digest
    assert again.model_dump(exclude={"candidate_tree"}) == result.model_dump(
        exclude={"candidate_tree"}
    )


def _readme_diff(snapshot: SnapshotTreeV1) -> FinalDiffV1:
    """A passed final diff carrying an out-of-policy ``README.md`` entry."""
    diff = _final_diff(snapshot, _root_revision(snapshot)[0].tree)
    entry = FinalDiffEntryV1(
        operation="CREATE",
        path=CanonicalRelativePathV1("README.md"),
        preimage=FinalDiffPreimageV1(kind="ABSENT"),
        postimage_digest=_ZERO,
        postimage_text_metadata=TextMetadataV1(
            encoding="UTF8", newline="LF", final_newline=True
        ),
    )
    return diff.model_copy(
        update={
            "entries": (*diff.entries, entry),
            "added_and_replacement_text_bytes": diff.added_and_replacement_text_bytes
            + 7,
        }
    )


def _protected_diff(snapshot: SnapshotTreeV1) -> FinalDiffV1:
    """A passed final diff carrying a protected ``tests/**`` entry."""
    diff = _final_diff(snapshot, _root_revision(snapshot)[0].tree)
    entry = FinalDiffEntryV1(
        operation="REPLACE",
        path=CanonicalRelativePathV1("tests/test_calculator.py"),
        preimage=FinalDiffPreimageV1(
            kind="PRESENT",
            content_digest=_ZERO,
            text_metadata=TextMetadataV1(
                encoding="UTF8", newline="LF", final_newline=True
            ),
        ),
        postimage_digest=_ZERO,
        postimage_text_metadata=TextMetadataV1(
            encoding="UTF8", newline="LF", final_newline=True
        ),
    )
    return diff.model_copy(update={"entries": (*diff.entries, entry)})


def _child_candidate(snapshot: SnapshotTreeV1) -> CandidateRevisionV1:
    """One derived child revision whose tree differs from the root."""
    revision, _store = _root_revision(snapshot)
    return derive_candidate_revision(
        revision,
        (
            CandidatePostimageV1(
                schema_version=1,
                operation="REPLACE",
                path=CanonicalRelativePathV1("src/vesper_fixture/calculator.py"),
                raw_bytes=(
                    b"def add(left: int, right: int) -> int:\n    return left + right\n"
                ),
            ),
        ),
    )


def _drifted_snapshot() -> SnapshotTreeV1:
    """A second sealed Snapshot over different workspace bytes."""
    return _sealed_snapshot(
        (
            ("pyproject.toml", _supported_pyproject_bytes()),
            ("src/vesper_fixture/calculator.py", b"x = 1\n"),
            ("tests/test_calculator.py", b"def test_other() -> None:\n    pass\n"),
        )
    )


_PREFLIGHT_MATRIX: tuple[
    tuple[
        str,
        Callable[[], tuple[ValidationManifestV1, CandidateRevisionV1, FinalDiffV1]],
        str,
    ],
    ...,
] = (
    (
        "stale candidate identity",
        lambda: (
            _manifest(_sealed_snapshot()),
            _stale_candidate(),
            _final_diff(_sealed_snapshot(), _root_revision(_sealed_snapshot())[0].tree),
        ),
        "CANDIDATE_STALE",
    ),
    (
        "stale final diff",
        lambda: (
            _manifest(_sealed_snapshot()),
            _candidate(_sealed_snapshot())[0],
            _final_diff(_sealed_snapshot(), _child_candidate(_sealed_snapshot()).tree),
        ),
        "CANDIDATE_STALE",
    ),
    (
        "final diff snapshot drift",
        lambda: (
            _manifest(_sealed_snapshot()),
            _candidate(_sealed_snapshot())[0],
            _final_diff(
                _sealed_snapshot(), _root_revision(_sealed_snapshot())[0].tree
            ).model_copy(update={"snapshot_tree_digest": _ZERO}),
        ),
        "TREE_INTEGRITY_FAILED",
    ),
    (
        "candidate tree snapshot drift",
        lambda: (
            _manifest(_sealed_snapshot()),
            _candidate(_drifted_snapshot())[0],
            _final_diff(_sealed_snapshot(), _root_revision(_sealed_snapshot())[0].tree),
        ),
        "TREE_INTEGRITY_FAILED",
    ),
    (
        "repository policy drift",
        lambda: (
            _drifted_manifest(repository_policy_digest=_ZERO),
            _candidate(_sealed_snapshot())[0],
            _final_diff(_sealed_snapshot(), _root_revision(_sealed_snapshot())[0].tree),
        ),
        "TREE_INTEGRITY_FAILED",
    ),
    (
        "reference profile drift",
        lambda: (
            _drifted_manifest(reference_profile_digest=_ZERO),
            _candidate(_sealed_snapshot())[0],
            _final_diff(_sealed_snapshot(), _root_revision(_sealed_snapshot())[0].tree),
        ),
        "VALIDATION_ENVIRONMENT_CHANGED",
    ),
    (
        "resource parameters drift",
        lambda: (
            _drifted_manifest(resource_parameters_digest=_ZERO),
            _candidate(_sealed_snapshot())[0],
            _final_diff(_sealed_snapshot(), _root_revision(_sealed_snapshot())[0].tree),
        ),
        "VALIDATION_ENVIRONMENT_CHANGED",
    ),
    (
        "environment whitelist drift",
        lambda: (
            _drifted_manifest(environment_whitelist_digest=_ZERO),
            _candidate(_sealed_snapshot())[0],
            _final_diff(_sealed_snapshot(), _root_revision(_sealed_snapshot())[0].tree),
        ),
        "VALIDATION_ENVIRONMENT_CHANGED",
    ),
    (
        "protected artifact entry",
        lambda: (
            _manifest(_sealed_snapshot()),
            _candidate(_sealed_snapshot())[0],
            _protected_diff(_sealed_snapshot()),
        ),
        "PROTECTED_ARTIFACT_CHANGED",
    ),
    (
        "out-of-policy entry",
        lambda: (
            _manifest(_sealed_snapshot()),
            _candidate(_sealed_snapshot())[0],
            _readme_diff(_sealed_snapshot()),
        ),
        "PATCH_PATH_NOT_EDITABLE",
    ),
    (
        "protected artifact set drift",
        lambda: (
            _drifted_manifest(protected_artifact_set_digest=_ZERO),
            _candidate(_sealed_snapshot())[0],
            _final_diff(_sealed_snapshot(), _root_revision(_sealed_snapshot())[0].tree),
        ),
        "TREE_INTEGRITY_FAILED",
    ),
)


@pytest.mark.parametrize(
    "name, inputs, expected_code",
    _PREFLIGHT_MATRIX,
    ids=[row[0] for row in _PREFLIGHT_MATRIX],
)
def test_formal_preflight_matrix(
    name: str,
    inputs: Callable[[], tuple[ValidationManifestV1, CandidateRevisionV1, FinalDiffV1]],
    expected_code: str,
) -> None:
    """Every stale/drifted/protected/out-of-policy input yields zero
    execution requests (SPEC §4.5 zero-container-call atomicity)."""
    manifest_value, candidate_value, final_diff_value = inputs()
    result = build_formal_validation_plan(
        manifest_value, candidate_value, final_diff_value
    )
    assert isinstance(result, FormalPlanRejectedV1)
    assert result.error_code == expected_code
    assert result.execution_requests == ()

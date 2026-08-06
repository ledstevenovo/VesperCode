"""T20.2 legacy step 20.B: ``ValidationManifestV1`` publication tests.

``create_validation_manifest`` publishes exactly one immutable
``ValidationManifestV1`` from one passing Baseline and the closed
environment bindings; the manifest model re-verifies every closed
invariant (sorted target ids and records, target fingerprint presence,
digest self-binding, unknown-field rejection) and the publication fails
closed on any drifted environment binding (SPEC §4.5).
"""

from __future__ import annotations

import pytest

# The Manifest contracts are pydantic runtime models; the hash-locked gate
# toolchain does not install runtime dependencies, so this module skips
# cleanly there instead of failing at collection (formal env runs it fully).
pytest.importorskip("pydantic")

from src.vespercode.contracts.evidence import DigestV1
from src.vespercode.contracts.optional import AbsentV1, PresentV1
from src.vespercode.trees.snapshot import SnapshotTreeV1
from src.vespercode.validation.baseline import (
    BaselineTestRecordV1,
    PassingBaselineV1,
    RuntimeCompatibleV1,
    compute_environment_whitelist_digest,
    compute_protected_artifact_set_digest,
    compute_resource_parameters_digest,
)
from src.vespercode.validation.manifest import (
    ManifestBindingsV1,
    ManifestError,
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
_IMAGE_DIGEST = "385ffc69d83536e1874d73517b8b9ee2a0dce6166ca0f30c1f3b1021324ea1a8"


def _bindings() -> ManifestBindingsV1:
    return ManifestBindingsV1(
        schema_version=1,
        resource_parameters_digest=compute_resource_parameters_digest(),
        environment_whitelist_digest=compute_environment_whitelist_digest(),
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


def _passing_baseline(
    *,
    target_ids: tuple[str, ...] = (_ADD,),
    collected: tuple[str, ...] = (_ADD, _MULTIPLY),
    records: tuple[BaselineTestRecordV1, ...] | None = None,
) -> PassingBaselineV1:
    if records is None:
        records = (
            _record(_ADD, "FAIL", fingerprint=_F),
            _record(_MULTIPLY, "PASS"),
        )
    return PassingBaselineV1(
        schema_version=1,
        kind="PASSING",
        plan_digest=_A,
        check_plan_version="1",
        adapter_version="1",
        python_version="3.12.4",
        pytest_version="8.4.2",
        report_plugin_version="1",
        ruff_version="0.16.1",
        mypy_version="2.3.0",
        docker_image_digest=_IMAGE_DIGEST,
        docker_execution_profile_version=1,
        reference_profile_digest=_B,
        snapshot_root_digest=_C,
        repository_policy_digest=_D,
        target_test_ids=target_ids,
        collected_node_ids=collected,
        collect_only_evidence_digests=(_A, _A),
        full_pytest_evidence_digest=_B,
        target_rerun_evidence_digest=_C,
        ruff_result_digest=_D,
        mypy_result_digest=_E,
        baseline_test_records=records,
        protected_artifact_set_digest=compute_protected_artifact_set_digest(
            _sealed_snapshot()
        ),
        runtime_compatibility=RuntimeCompatibleV1(
            schema_version=1,
            status="COMPATIBLE",
            reference_profile_digest=_B,
            evidence_digest=_E,
        ),
    )


def _sealed_snapshot() -> SnapshotTreeV1:
    """One minimal sealed Snapshot for the protected-artifact digest."""
    from src.vespercode.canonical.path_v1 import CanonicalRelativePathV1
    from src.vespercode.trees.content_store import (
        ContentObjectRefV1,
        ContentObjectStore,
    )
    from src.vespercode.trees.snapshot import (
        SnapshotDirectoryEntryV1,
        SnapshotFileEntryV1,
        _root_digest,
    )
    from src.vespercode.trees.text_classifier import TextMetadataV1

    store = ContentObjectStore()
    pyproject_ref = store.put(b"x")
    test_ref = store.put(b"x")

    def file_entry(rel: str, ref: ContentObjectRefV1) -> SnapshotFileEntryV1:
        return SnapshotFileEntryV1(
            kind="TEXT_FILE",
            path=CanonicalRelativePathV1(rel),
            size_bytes=1,
            content_ref=ref,
            text_profile=PresentV1(
                kind="PRESENT",
                value=TextMetadataV1(
                    encoding="UTF8",
                    newline="LF",
                    final_newline=True,
                ),
            ),
        )

    entries = (
        SnapshotDirectoryEntryV1(kind="DIRECTORY", path=CanonicalRelativePathV1("src")),
        SnapshotDirectoryEntryV1(
            kind="DIRECTORY", path=CanonicalRelativePathV1("tests")
        ),
        file_entry("pyproject.toml", pyproject_ref),
        file_entry("tests/test_calculator.py", test_ref),
    )
    policy_digest = _D
    return SnapshotTreeV1(
        root_digest=_root_digest(policy_digest, entries),
        repository_policy_digest=policy_digest,
        entries=entries,
        file_bytes=(("pyproject.toml", b"x"), ("tests/test_calculator.py", b"x")),
    )


def test_create_validation_manifest_publishes_one_immutable_manifest() -> None:
    baseline = _passing_baseline()
    manifest = create_validation_manifest(baseline, _bindings())
    assert isinstance(manifest, ValidationManifestV1)
    assert manifest.schema_version == 1
    # The manifest sorts the target ids into its canonical order.
    assert manifest.target_test_ids == (_ADD,)
    assert manifest.collected_node_ids == (_ADD, _MULTIPLY)
    assert tuple(r.node_id for r in manifest.baseline_test_records) == (
        _ADD,
        _MULTIPLY,
    )
    assert manifest.reference_profile_digest == _B
    assert manifest.snapshot_tree_digest == _C
    assert manifest.repository_policy_digest == _D
    assert manifest.docker_image_digest == _IMAGE_DIGEST
    assert manifest.collect_only_evidence_digests == (_A, _A)
    assert manifest.full_pytest_evidence_digest == _B
    assert manifest.target_rerun_evidence_digest == _C
    assert manifest.ruff_result_digest == _D
    assert manifest.mypy_result_digest == _E
    assert manifest.resource_parameters_digest == _bindings().resource_parameters_digest
    assert (
        manifest.environment_whitelist_digest
        == _bindings().environment_whitelist_digest
    )
    assert len(manifest.digest) == 64
    # The digest self-binds every other field.
    assert manifest.digest == validation_manifest_digest(manifest)
    # Deterministic publication: identical inputs publish identical bytes.
    again = create_validation_manifest(baseline, _bindings())
    assert again.digest == manifest.digest
    assert again.model_dump() == manifest.model_dump()


def test_create_validation_manifest_rejects_drifted_environment_bindings() -> None:
    baseline = _passing_baseline()
    drifted_resources = ManifestBindingsV1(
        schema_version=1,
        resource_parameters_digest="0" * 64,
        environment_whitelist_digest=compute_environment_whitelist_digest(),
    )
    with pytest.raises(ManifestError) as raised:
        create_validation_manifest(baseline, drifted_resources)
    assert raised.value.error_code == "BINDING_MISMATCH"
    drifted_environment = ManifestBindingsV1(
        schema_version=1,
        resource_parameters_digest=compute_resource_parameters_digest(),
        environment_whitelist_digest="0" * 64,
    )
    with pytest.raises(ManifestError) as raised:
        create_validation_manifest(baseline, drifted_environment)
    assert raised.value.error_code == "BINDING_MISMATCH"


def test_manifest_rejects_unknown_fields_and_coerced_versions() -> None:
    from pydantic import ValidationError

    manifest = create_validation_manifest(_passing_baseline(), _bindings())
    with pytest.raises(ValidationError):
        ValidationManifestV1.model_validate({**manifest.model_dump(), "extra": "x"})
    with pytest.raises(ValidationError):
        ValidationManifestV1.model_validate(
            {**manifest.model_dump(), "schema_version": "1"}
        )
    with pytest.raises(ValidationError):
        ValidationManifestV1.model_validate(
            {**manifest.model_dump(), "digest": "short"}
        )
    with pytest.raises(ValidationError):
        ValidationManifestV1.model_validate(
            {**manifest.model_dump(), "docker_execution_profile_version": 2}
        )
    # The published identity fields reject bool/float coercion (the
    # T06.1/T05.1 strict-scalar convention).
    for coerced in (True, 1.0, "1"):
        with pytest.raises(ValidationError):
            ValidationManifestV1.model_validate(
                {
                    **manifest.model_dump(),
                    "docker_execution_profile_version": coerced,
                }
            )


def test_manifest_digest_binds_every_other_field() -> None:
    from pydantic import ValidationError

    manifest = create_validation_manifest(_passing_baseline(), _bindings())
    tampered = {**manifest.model_dump(), "digest": "0" * 64}
    with pytest.raises(ValidationError):
        ValidationManifestV1.model_validate(tampered)
    # A record whose fingerprint digest no longer matches the target's
    # PRESENT binding rotates the manifest identity and rejects.
    tampered_record = {**manifest.model_dump(mode="python")}
    records = list(tampered_record["baseline_test_records"])
    records[0] = _record(_ADD, "FAIL", fingerprint="0" * 64)
    tampered_record["baseline_test_records"] = tuple(records)
    with pytest.raises(ValidationError):
        ValidationManifestV1.model_validate(tampered_record)


def test_manifest_enforces_sorted_orders_and_closed_record_invariants() -> None:
    from pydantic import ValidationError

    # Unsorted baseline target ids are normalized into the manifest's
    # sorted canonical order (SPEC §4.5 "sorted exact node IDs").
    baseline = _passing_baseline(
        target_ids=(_MULTIPLY, _ADD),
        collected=(_ADD, _MULTIPLY),
        records=(
            _record(_ADD, "FAIL", fingerprint=_F),
            _record(_MULTIPLY, "FAIL", fingerprint=_F),
        ),
    )
    manifest = create_validation_manifest(baseline, _bindings())
    assert manifest.target_test_ids == (_ADD, _MULTIPLY)
    # A target outside the collection rejects.
    baseline = _passing_baseline(
        target_ids=(_ADD,),
        collected=(_MULTIPLY,),
        records=(_record(_MULTIPLY, "PASS"),),
    )
    with pytest.raises(ValidationError):
        create_validation_manifest(baseline, _bindings())
    # Records not covering the collection reject.
    baseline = _passing_baseline(
        collected=(_ADD, _MULTIPLY),
        records=(_record(_ADD, "FAIL", fingerprint=_F),),
    )
    with pytest.raises(ValidationError):
        create_validation_manifest(baseline, _bindings())
    # A target record without a fingerprint rejects.
    baseline = _passing_baseline(
        collected=(_ADD, _MULTIPLY),
        records=(
            _record(_ADD, "FAIL"),
            _record(_MULTIPLY, "PASS"),
        ),
    )
    with pytest.raises(ValidationError):
        create_validation_manifest(baseline, _bindings())
    # A non-target record carrying a fingerprint cannot even exist: the
    # closed record table (BaselineTestRecordV1) rejects it at the record
    # layer before any manifest (pinned in test_baseline.py).


def test_manifest_bindings_schema_is_closed() -> None:
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        ManifestBindingsV1(
            schema_version=1,
            resource_parameters_digest="short",
            environment_whitelist_digest=_A,
        )
    with pytest.raises(ValidationError):
        ManifestBindingsV1.model_validate(
            {
                "schema_version": "1",
                "resource_parameters_digest": _A,
                "environment_whitelist_digest": _A,
            }
        )

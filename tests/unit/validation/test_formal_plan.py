"""T21.1 legacy step 21.A: closed formal-plan schema tests.

The frozen plan surface proves the plan, request, bounds, and
expectation contracts are immutable and closed (unknown fields and
type-confused spellings reject), exactly ordered, identity-bound
(request ids bind their check kind), time-bound (the SPEC §5.1 exact
sub-timeouts), digest-self-bound, and deterministic — the schema
invariants ``build_formal_validation_plan`` relies on.  The builder's
exact vectors live in ``test_formal_preflight.py``.
"""

from __future__ import annotations

from pathlib import Path

import pytest

# The formal-plan contracts are pydantic runtime models; the hash-locked
# gate toolchain does not install runtime dependencies, so this module
# skips cleanly there instead of failing at collection (formal env runs
# it fully).
pytest.importorskip("pydantic")

from pydantic import ValidationError

from vespercode.canonical.path_v1 import CanonicalRelativePathV1
from vespercode.contracts.optional import AbsentV1, PresentV1
from vespercode.execution.docker_profile import ExecutionArgumentSequenceV1
from vespercode.profiles.reference import (
    ReferenceProfileManifestV1,
    load_reference_profile,
)
from vespercode.trees.candidate import root_candidate_revision
from vespercode.trees.content_store import ContentObjectRefV1, ContentObjectStore
from vespercode.trees.snapshot import (
    SnapshotDirectoryEntryV1,
    SnapshotEntryV1,
    SnapshotFileEntryV1,
    SnapshotTreeV1,
    _root_digest,
)
from vespercode.trees.text_classifier import TextMetadataV1
from vespercode.validation.formal_plan import (
    FormalPlanRejectedV1,
    FormalPytestExpectationV1,
    FormalRequestExpectationV1,
    FormalValidationBoundsV1,
    FormalValidationPlanV1,
    FormalValidationRequestV1,
    formal_validation_plan_digest,
)

_ADD = "tests/test_calculator.py::test_add_returns_sum"
_MULTIPLY = "tests/test_calculator.py::test_multiply_returns_product"
_A = "a" * 64
_B = "b" * 64
_C = "c" * 64
_D = "d" * 64
_E = "e" * 64
_ZERO = "0" * 64
_IMAGE_DIGEST = "cf0b6c5ccac588fccd07c3b9f050bff4daf550ac6e518fd06efb6e988ab1d823"
_PROFILE_DIGEST = "d0700f00f5ae2501ac9be7fbdd66d20e76c16a6c6f9ab7893c1aea71d57e927e"


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


def _sealed_snapshot() -> SnapshotTreeV1:
    """One minimal sealed Snapshot for the plan-schema surface."""
    from vespercode.trees.snapshot import SealedSnapshotInputFileV1
    from vespercode.trees.text_classifier import classify_supported_text

    store = ContentObjectStore()
    raw_files = (
        ("pyproject.toml", b"[project]\nname = 'x'\n"),
        ("src/vesper_fixture/calculator.py", b"x = 1\n"),
        ("tests/test_calculator.py", b"def test_x() -> None:\n    pass\n"),
    )
    rows: list[SealedSnapshotInputFileV1] = []
    for rel, raw in raw_files:
        ref = store.put(raw)
        rows.append(
            SealedSnapshotInputFileV1(
                schema_version=1,
                path=CanonicalRelativePathV1(rel),
                content_sha256=ref.sha256,
                byte_count=ref.byte_count,
            )
        )
    entries: list[SnapshotEntryV1] = [
        SnapshotDirectoryEntryV1(kind="DIRECTORY", path=CanonicalRelativePathV1("src")),
        SnapshotDirectoryEntryV1(
            kind="DIRECTORY", path=CanonicalRelativePathV1("tests")
        ),
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


def _argv(*arguments: str) -> ExecutionArgumentSequenceV1:
    return ExecutionArgumentSequenceV1(arguments=tuple(arguments))


def _pytest_expectation(
    run_kind: str, planned: tuple[str, ...]
) -> FormalPytestExpectationV1:
    return FormalPytestExpectationV1(
        schema_version=1,
        run_kind=run_kind,  # type: ignore[arg-type]
        planned_node_ids=planned,
        report_plugin_version="1",
    )


def _request(
    check_id: str,
    ordinal: int,
    *,
    planned: tuple[str, ...] = (_ADD, _MULTIPLY),
    tool_version: str | None = None,
) -> FormalValidationRequestV1:
    if check_id in ("COLLECT_ONLY", "FULL_PYTEST"):
        expectation = FormalRequestExpectationV1(
            schema_version=1,
            check_kind=check_id,  # type: ignore[arg-type]
            pytest=PresentV1(
                kind="PRESENT",
                value=_pytest_expectation(
                    check_id,
                    () if check_id == "COLLECT_ONLY" else planned,
                ),
            ),
            tool_version=AbsentV1(kind="ABSENT"),
        )
        argv = _argv(
            "python",
            "-m",
            "pytest",
            "-p",
            "vespercode.validation.pytest_reporter",
            "-o",
            "cacheprovider=disabled",
            "--rootdir",
            "/workspace",
            *(() if check_id == "FULL_PYTEST" else ("--collect-only",)),
            "/workspace",
        )
    else:
        expectation = FormalRequestExpectationV1(
            schema_version=1,
            check_kind=check_id,  # type: ignore[arg-type]
            pytest=AbsentV1(kind="ABSENT"),
            tool_version=PresentV1(kind="PRESENT", value=tool_version or "0.16.1"),
        )
        argv = (
            _argv("ruff", "check", "--no-cache", "/workspace")
            if check_id == "RUFF"
            else _argv(
                "mypy",
                "--no-incremental",
                "--cache-dir",
                "/tmp/mypy-cache",
                "--config-file",
                "/workspace/pyproject.toml",
                "/workspace/src",
            )
        )
    return FormalValidationRequestV1(
        schema_version=1,
        request_id=f"formal-{check_id}-{ordinal}",
        check_kind=check_id,  # type: ignore[arg-type]
        argv=argv,
        timeout_seconds=300,
        expectation=expectation,
    )


def _four_requests() -> tuple[FormalValidationRequestV1, ...]:
    return (
        _request("COLLECT_ONLY", 1, planned=()),
        _request("FULL_PYTEST", 2),
        _request("RUFF", 3),
        _request("MYPY", 4),
    )


def _plan_document() -> dict[str, object]:
    """Every exact plan field except the digest."""
    snapshot = _sealed_snapshot()
    store = ContentObjectStore()
    for _path, raw in snapshot.file_bytes:
        store.put(raw)
    tree = root_candidate_revision(snapshot, store).tree
    return {
        "schema_version": 1,
        "kind": "FROZEN",
        "error_code": None,
        "check_plan_version": "1",
        "adapter_version": "1",
        "python_version": "3.12.4",
        "pytest_version": "8.4.2",
        "report_plugin_version": "1",
        "ruff_version": "0.16.1",
        "mypy_version": "2.3.0",
        "docker_image_digest": _IMAGE_DIGEST,
        "docker_execution_profile_version": 1,
        "reference_profile_digest": _PROFILE_DIGEST,
        "snapshot_tree_digest": snapshot.root_digest,
        "repository_policy_digest": snapshot.repository_policy_digest,
        "protected_artifact_set_digest": _A,
        "resource_parameters_digest": _B,
        "environment_whitelist_digest": _C,
        "manifest_digest": _D,
        "candidate_digest": _E,
        "candidate_tree_digest": tree.digest,
        "final_diff_digest": _ZERO,
        "target_test_ids": (_ADD,),
        "collected_node_ids": (_ADD, _MULTIPLY),
        "bounds": FormalValidationBoundsV1(
            schema_version=1,
            full_check_timeout_seconds=300,
            formal_validation_timeout_seconds=600,
        ),
        "execution_requests": _four_requests(),
        "candidate_tree": tree,
    }


def _plan() -> FormalValidationPlanV1:
    """One closed plan via the digest two-pass (the model re-validates)."""
    document = _plan_document()
    probe = FormalValidationPlanV1.model_construct(**document)  # type: ignore[arg-type]
    return FormalValidationPlanV1.model_validate(
        {**document, "digest": formal_validation_plan_digest(probe)}
    )


def test_plan_is_immutable_closed_and_digest_self_bound() -> None:
    plan = _plan()
    assert plan.schema_version == 1
    assert plan.error_code is None
    assert plan.digest == formal_validation_plan_digest(plan)
    assert tuple(request.check_kind for request in plan.execution_requests) == (
        "COLLECT_ONLY",
        "FULL_PYTEST",
        "RUFF",
        "MYPY",
    )
    with pytest.raises(ValidationError):
        FormalValidationPlanV1.model_validate({**_plan_document(), "digest": _ZERO})
    with pytest.raises(ValidationError):
        FormalValidationPlanV1.model_validate(
            {**_plan_document(), "digest": _A, "unexpected": 1}
        )
    with pytest.raises(ValidationError):
        plan.__setattr__("check_plan_version", "2")


def test_plan_enforces_the_canonical_four_check_order() -> None:
    document = _plan_document()
    requests = _four_requests()
    document["execution_requests"] = (
        requests[1],
        requests[0],
        requests[2],
        requests[3],
    )
    probe = FormalValidationPlanV1.model_construct(**document)  # type: ignore[arg-type]
    with pytest.raises(ValidationError):
        FormalValidationPlanV1.model_validate(
            {**document, "digest": formal_validation_plan_digest(probe)}
        )


def test_plan_rejects_targets_outside_the_collection() -> None:
    document = _plan_document()
    document["target_test_ids"] = ("tests/test_calculator.py::test_missing",)
    probe = FormalValidationPlanV1.model_construct(**document)  # type: ignore[arg-type]
    with pytest.raises(ValidationError):
        FormalValidationPlanV1.model_validate(
            {**document, "digest": formal_validation_plan_digest(probe)}
        )


def test_request_id_must_bind_its_check_kind() -> None:
    with pytest.raises(ValidationError):
        FormalValidationRequestV1.model_validate(
            {
                **_request("FULL_PYTEST", 2).model_dump(),
                "request_id": "formal-RUFF-2",
            }
        )
    with pytest.raises(ValidationError):
        FormalValidationRequestV1.model_validate(
            {
                **_request("FULL_PYTEST", 2).model_dump(),
                "request_id": "not-bound",
            }
        )


def test_request_timeout_is_the_exact_frozen_subtimeout() -> None:
    request = _request("FULL_PYTEST", 2)
    assert request.timeout_seconds == 300
    with pytest.raises(ValidationError):
        FormalValidationRequestV1.model_validate(
            {**_request("FULL_PYTEST", 2).model_dump(), "timeout_seconds": 301}
        )
    with pytest.raises(ValidationError):
        FormalValidationRequestV1.model_validate(
            {**_request("FULL_PYTEST", 2).model_dump(), "timeout_seconds": True}
        )


def test_bounds_are_the_exact_frozen_spec_51_values() -> None:
    bounds = FormalValidationBoundsV1(
        schema_version=1,
        full_check_timeout_seconds=300,
        formal_validation_timeout_seconds=600,
    )
    assert bounds.full_check_timeout_seconds == 300
    assert bounds.formal_validation_timeout_seconds == 600
    for field in ("full_check_timeout_seconds", "formal_validation_timeout_seconds"):
        with pytest.raises(ValidationError):
            FormalValidationBoundsV1.model_validate(
                {
                    "schema_version": 1,
                    "full_check_timeout_seconds": 300,
                    "formal_validation_timeout_seconds": 600,
                    field: 301,
                }
            )
    with pytest.raises(ValidationError):
        FormalValidationBoundsV1.model_validate(
            {
                "schema_version": 1,
                "full_check_timeout_seconds": 300.0,
                "formal_validation_timeout_seconds": 600,
            }
        )


def test_expectation_pairs_exactly_with_the_check_kind() -> None:
    full = _request("FULL_PYTEST", 2).expectation
    assert isinstance(full.pytest, PresentV1)
    assert isinstance(full.tool_version, AbsentV1)
    ruff = _request("RUFF", 3).expectation
    assert isinstance(ruff.pytest, AbsentV1)
    assert isinstance(ruff.tool_version, PresentV1)
    with pytest.raises(ValidationError):
        FormalRequestExpectationV1.model_validate(
            {
                "schema_version": 1,
                "check_kind": "RUFF",
                "pytest": {
                    "kind": "PRESENT",
                    "value": {
                        "schema_version": 1,
                        "run_kind": "FULL_PYTEST",
                        "planned_node_ids": (_ADD, _MULTIPLY),
                        "report_plugin_version": "1",
                    },
                },
                "tool_version": {"kind": "PRESENT", "value": "0.16.1"},
            }
        )


def test_pytest_expectation_binds_the_collect_only_empty_plan() -> None:
    collect = _pytest_expectation("COLLECT_ONLY", ())
    assert collect.planned_node_ids == ()
    with pytest.raises(ValidationError):
        _pytest_expectation("COLLECT_ONLY", (_ADD,))
    with pytest.raises(ValidationError):
        _pytest_expectation("FULL_PYTEST", ())


def test_versions_and_digests_reject_confused_spellings() -> None:
    document = _plan_document()
    for field in ("docker_execution_profile_version",):
        with pytest.raises(ValidationError):
            FormalValidationPlanV1.model_validate(
                {**document, "digest": _A, field: True}
            )
    for field in (
        "docker_image_digest",
        "reference_profile_digest",
        "snapshot_tree_digest",
        "repository_policy_digest",
        "manifest_digest",
        "candidate_digest",
        "candidate_tree_digest",
        "final_diff_digest",
    ):
        with pytest.raises(ValidationError):
            FormalValidationPlanV1.model_validate(
                {**document, "digest": _A, field: "not-a-digest"}
            )


def test_rejection_is_zero_request_atomic() -> None:
    rejected = FormalPlanRejectedV1(
        schema_version=1,
        kind="REJECTED",
        error_code="CANDIDATE_STALE",
        error_message="the candidate identity is stale",
        execution_requests=(),
    )
    assert rejected.execution_requests == ()
    with pytest.raises(ValidationError):
        FormalPlanRejectedV1.model_validate(
            {
                "schema_version": 1,
                "kind": "REJECTED",
                "error_code": "CANDIDATE_STALE",
                "error_message": "stale",
                "execution_requests": (_request("RUFF", 3),),
            }
        )
    with pytest.raises(ValidationError):
        FormalPlanRejectedV1.model_validate(
            {
                "schema_version": 1,
                "kind": "REJECTED",
                "error_code": "UNKNOWN_CODE",
                "error_message": "stale",
                "execution_requests": (),
            }
        )

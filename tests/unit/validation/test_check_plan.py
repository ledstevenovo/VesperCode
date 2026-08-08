"""T20.1 legacy step 20.A: closed check-plan schema tests.

The unit surface proves the frozen Baseline and formal validation check
plans are immutable, closed (unknown fields and type-confused spellings
reject), exactly ordered, target-bound, digest-self-bound, and
deterministic — the schema invariants ``build_baseline_plan`` and
``build_formal_plan`` rely on.  The adapter-driven exact vectors live in
``test_python_adapter_static.py``; this module owns the closed-schema
matrix of the plan/value types themselves.
"""

from __future__ import annotations

from typing import Literal, cast

import pytest

# The plan contracts are pydantic runtime models; the hash-locked gate
# toolchain does not install runtime dependencies, so this module skips
# cleanly there instead of failing at collection (formal env runs it fully).
pytest.importorskip("pydantic")

from pydantic import ValidationError

from vespercode.contracts.optional import AbsentV1, PresentV1
from vespercode.execution.docker_profile import ExecutionArgumentSequenceV1
from vespercode.validation.python_adapter import (
    ADAPTER_VERSION,
    BaselineCheckPlanEntryV1,
    BaselineCheckPlanV1,
    CheckIdentityV1,
    FormalCheckIdentityV1,
    FormalCheckPlanEntryV1,
    FormalValidationCheckPlanV1,
    SupportedProjectV1,
    TargetTestIdSequenceV1,
    UnsupportedProjectV1,
    _compute_baseline_plan_digest,
    _compute_formal_plan_digest,
    expected_argv,
)

_A = "a" * 64
_B = "b" * 64
_C = "c" * 64
_D = "d" * 64
_E = "e" * 64
_F = "f" * 64

_IMAGE_DIGEST = "cf0b6c5ccac588fccd07c3b9f050bff4daf550ac6e518fd06efb6e988ab1d823"

_TARGET_ADD = "tests/test_calculator.py::test_add_returns_sum"
_TARGET_MULTIPLY = "tests/test_calculator.py::test_multiply_returns_product"


def _target_ids(*node_ids: str) -> TargetTestIdSequenceV1:
    return TargetTestIdSequenceV1(target_test_ids=tuple(node_ids))


def _argv(*arguments: str) -> ExecutionArgumentSequenceV1:
    return ExecutionArgumentSequenceV1(arguments=tuple(arguments))


def _baseline_entry(
    check_id: CheckIdentityV1,
    arguments: tuple[str, ...] | None = None,
    *,
    target_test_ids: TargetTestIdSequenceV1 | None = None,
) -> BaselineCheckPlanEntryV1:
    binding: AbsentV1 | PresentV1[TargetTestIdSequenceV1]
    if check_id == "TARGET_TESTS":
        if target_test_ids is None:
            raise AssertionError("TARGET_TESTS entries require target ids")
        binding = PresentV1(kind="PRESENT", value=target_test_ids)
    else:
        binding = AbsentV1(kind="ABSENT")
    argv = (
        expected_argv(check_id, target_test_ids)
        if arguments is None
        else _argv(*arguments)
    )
    return BaselineCheckPlanEntryV1(
        check_id=check_id, argv=argv, target_test_ids=binding
    )


def _baseline_entries(
    *node_ids: str,
) -> tuple[BaselineCheckPlanEntryV1, ...]:
    ids = node_ids if node_ids else (_TARGET_ADD,)
    target_ids = _target_ids(*ids)
    return (
        _baseline_entry("COLLECT_ONLY"),
        _baseline_entry("COLLECT_ONLY"),
        _baseline_entry("FULL_PYTEST"),
        _baseline_entry("TARGET_TESTS", target_test_ids=target_ids),
        _baseline_entry("RUFF"),
        _baseline_entry("MYPY"),
    )


def _formal_entries() -> tuple[FormalCheckPlanEntryV1, ...]:
    return (
        FormalCheckPlanEntryV1(
            check_id="COLLECT_ONLY", argv=expected_argv("COLLECT_ONLY")
        ),
        FormalCheckPlanEntryV1(
            check_id="FULL_PYTEST", argv=expected_argv("FULL_PYTEST")
        ),
        FormalCheckPlanEntryV1(check_id="RUFF", argv=expected_argv("RUFF")),
        FormalCheckPlanEntryV1(check_id="MYPY", argv=expected_argv("MYPY")),
    )


def _baseline_fields(
    *,
    entries: tuple[BaselineCheckPlanEntryV1, ...] | None = None,
    target_test_ids: TargetTestIdSequenceV1 | None = None,
) -> dict[str, object]:
    """One fully valid Baseline plan field set (digest self-bound)."""
    ids = target_test_ids if target_test_ids is not None else _target_ids(_TARGET_ADD)
    plan_entries = (
        entries if entries is not None else _baseline_entries(*ids.target_test_ids)
    )
    digest = _compute_baseline_plan_digest(
        check_plan_version="1",
        adapter_version=ADAPTER_VERSION,
        python_version="3.12.4",
        pytest_version="8.4.2",
        report_plugin_version="1",
        ruff_version="0.16.1",
        mypy_version="2.3.0",
        docker_image_digest=_IMAGE_DIGEST,
        docker_execution_profile_version=1,
        reference_profile_digest=_A,
        snapshot_root_digest=_B,
        repository_policy_digest=_C,
        target_test_ids=ids.target_test_ids,
        entries=plan_entries,
    )
    return {
        "schema_version": 1,
        "check_plan_version": "1",
        "adapter_version": ADAPTER_VERSION,
        "python_version": "3.12.4",
        "pytest_version": "8.4.2",
        "report_plugin_version": "1",
        "ruff_version": "0.16.1",
        "mypy_version": "2.3.0",
        "docker_image_digest": _IMAGE_DIGEST,
        "docker_execution_profile_version": 1,
        "reference_profile_digest": _A,
        "snapshot_root_digest": _B,
        "repository_policy_digest": _C,
        "target_test_ids": ids,
        "entries": plan_entries,
        "digest": digest,
    }


def test_target_test_id_sequence_is_ordered_immutable_and_bounded() -> None:
    ids = _target_ids(_TARGET_MULTIPLY, _TARGET_ADD)
    assert ids.target_test_ids == (_TARGET_MULTIPLY, _TARGET_ADD)
    with pytest.raises(ValidationError):
        _target_ids(_TARGET_ADD, _TARGET_ADD)
    with pytest.raises(ValidationError):
        _target_ids("")
    with pytest.raises(ValidationError):
        _target_ids("x" * 1025)
    with pytest.raises(ValidationError):
        TargetTestIdSequenceV1(target_test_ids=())
    with pytest.raises(ValidationError):
        TargetTestIdSequenceV1(target_test_ids=tuple(f"t{i}" for i in range(21)))


def test_baseline_entry_target_binding_is_closed() -> None:
    with pytest.raises(ValidationError):
        BaselineCheckPlanEntryV1(
            check_id="TARGET_TESTS",
            argv=_argv("python", "-m", "pytest"),
            target_test_ids=AbsentV1(kind="ABSENT"),
        )
    with pytest.raises(ValidationError):
        BaselineCheckPlanEntryV1(
            check_id="FULL_PYTEST",
            argv=_argv("python", "-m", "pytest"),
            target_test_ids=PresentV1(kind="PRESENT", value=_target_ids(_TARGET_ADD)),
        )
    with pytest.raises(ValidationError):
        BaselineCheckPlanEntryV1(
            check_id=cast(CheckIdentityV1, "UNKNOWN_CHECK"),
            argv=_argv("python", "-m", "pytest"),
            target_test_ids=AbsentV1(kind="ABSENT"),
        )
    with pytest.raises(ValidationError):
        BaselineCheckPlanEntryV1(
            check_id="FULL_PYTEST",
            argv=_argv(),
            target_test_ids=AbsentV1(kind="ABSENT"),
        )


def test_entries_reject_argv_that_differs_from_the_frozen_command() -> None:
    # A self-consistent forged argv (even with a recomputed plan digest)
    # can never construct: every entry must bind the adapter's frozen
    # command for its check identity.
    with pytest.raises(ValidationError):
        BaselineCheckPlanEntryV1(
            check_id="FULL_PYTEST",
            argv=_argv("python", "-m", "pytest", "/workspace"),
            target_test_ids=AbsentV1(kind="ABSENT"),
        )
    with pytest.raises(ValidationError):
        BaselineCheckPlanEntryV1(
            check_id="TARGET_TESTS",
            argv=expected_argv("FULL_PYTEST"),
            target_test_ids=PresentV1(kind="PRESENT", value=_target_ids(_TARGET_ADD)),
        )
    with pytest.raises(ValidationError):
        FormalCheckPlanEntryV1(
            check_id="MYPY",
            argv=_argv("mypy", "check", "/workspace"),
        )
    # The frozen adapter argv is the exact accepted sequence.
    assert _baseline_entry("FULL_PYTEST").argv == expected_argv("FULL_PYTEST")
    assert _formal_entries()[3].argv == expected_argv("MYPY")


def test_valid_plans_construct_with_self_bound_digests() -> None:
    baseline = BaselineCheckPlanV1.model_validate(_baseline_fields())
    assert baseline.digest == _compute_baseline_plan_digest(
        check_plan_version=baseline.check_plan_version,
        adapter_version=baseline.adapter_version,
        python_version=baseline.python_version,
        pytest_version=baseline.pytest_version,
        report_plugin_version=baseline.report_plugin_version,
        ruff_version=baseline.ruff_version,
        mypy_version=baseline.mypy_version,
        docker_image_digest=baseline.docker_image_digest,
        docker_execution_profile_version=baseline.docker_execution_profile_version,
        reference_profile_digest=baseline.reference_profile_digest,
        snapshot_root_digest=baseline.snapshot_root_digest,
        repository_policy_digest=baseline.repository_policy_digest,
        target_test_ids=baseline.target_test_ids.target_test_ids,
        entries=baseline.entries,
    )
    formal = FormalValidationCheckPlanV1.model_validate(_formal_fields())
    assert formal.digest == _compute_formal_plan_digest(
        check_plan_version=formal.check_plan_version,
        adapter_version=formal.adapter_version,
        python_version=formal.python_version,
        pytest_version=formal.pytest_version,
        report_plugin_version=formal.report_plugin_version,
        ruff_version=formal.ruff_version,
        mypy_version=formal.mypy_version,
        docker_image_digest=formal.docker_image_digest,
        docker_execution_profile_version=formal.docker_execution_profile_version,
        reference_profile_digest=formal.reference_profile_digest,
        snapshot_tree_digest=formal.snapshot_tree_digest,
        repository_policy_digest=formal.repository_policy_digest,
        manifest_digest=formal.manifest_digest,
        candidate_digest=formal.candidate_digest,
        candidate_tree_digest=formal.candidate_tree_digest,
        final_diff_digest=formal.final_diff_digest,
        target_test_ids=formal.target_test_ids.target_test_ids,
        entries=formal.entries,
    )


def test_plan_digest_binds_every_other_field() -> None:
    baseline = _baseline_fields()
    baseline["digest"] = "0" * 64
    with pytest.raises(ValidationError):
        BaselineCheckPlanV1.model_validate(baseline)
    formal = _formal_fields()
    formal["digest"] = "0" * 64
    with pytest.raises(ValidationError):
        FormalValidationCheckPlanV1.model_validate(formal)


def test_baseline_plan_enforces_exact_frozen_order() -> None:
    fields = _baseline_fields()
    fields["entries"] = tuple(
        reversed(tuple(fields["entries"]))  # type: ignore[arg-type]
    )
    with pytest.raises(ValidationError):
        BaselineCheckPlanV1.model_validate(fields)
    short = _baseline_fields(entries=_baseline_entries()[:5])
    with pytest.raises(ValidationError):
        BaselineCheckPlanV1.model_validate(short)
    duplicated = _baseline_fields(
        entries=(
            *_baseline_entries()[:2],
            *_baseline_entries()[:2],
            *_baseline_entries()[4:],
        )
    )
    with pytest.raises(ValidationError):
        BaselineCheckPlanV1.model_validate(duplicated)


def test_formal_plan_rejects_target_tests_identity_and_enforces_order() -> None:
    with pytest.raises(ValidationError):
        FormalCheckPlanEntryV1(
            check_id=cast(FormalCheckIdentityV1, "TARGET_TESTS"),
            argv=_argv("python", "-m", "pytest"),
        )
    with pytest.raises(ValidationError):
        FormalCheckPlanEntryV1(
            check_id=cast(FormalCheckIdentityV1, "UNKNOWN_CHECK"),
            argv=_argv("python", "-m", "pytest"),
        )
    # The order validator rejects a reordered formal plan even when the
    # digest is recomputed over the reordered entries (the digest itself
    # is not the rejecting validator here).
    ids = _target_ids(_TARGET_ADD, _TARGET_MULTIPLY)
    reordered = tuple(reversed(_formal_entries()))
    reordered_fields = _formal_fields(entries=reordered)
    reordered_fields["digest"] = _compute_formal_plan_digest(
        check_plan_version="1",
        adapter_version=ADAPTER_VERSION,
        python_version="3.12.4",
        pytest_version="8.4.2",
        report_plugin_version="1",
        ruff_version="0.16.1",
        mypy_version="2.3.0",
        docker_image_digest=_IMAGE_DIGEST,
        docker_execution_profile_version=1,
        reference_profile_digest=_A,
        snapshot_tree_digest=_B,
        repository_policy_digest=_C,
        manifest_digest=_D,
        candidate_digest=_E,
        candidate_tree_digest=_F,
        final_diff_digest=_A,
        target_test_ids=ids.target_test_ids,
        entries=reordered,
    )
    with pytest.raises(ValidationError):
        FormalValidationCheckPlanV1.model_validate(reordered_fields)


def _formal_fields(
    *,
    entries: tuple[FormalCheckPlanEntryV1, ...] | None = None,
) -> dict[str, object]:
    """One fully valid formal plan field set (digest self-bound)."""
    ids = _target_ids(_TARGET_ADD, _TARGET_MULTIPLY)
    plan_entries = entries if entries is not None else _formal_entries()
    digest = _compute_formal_plan_digest(
        check_plan_version="1",
        adapter_version=ADAPTER_VERSION,
        python_version="3.12.4",
        pytest_version="8.4.2",
        report_plugin_version="1",
        ruff_version="0.16.1",
        mypy_version="2.3.0",
        docker_image_digest=_IMAGE_DIGEST,
        docker_execution_profile_version=1,
        reference_profile_digest=_A,
        snapshot_tree_digest=_B,
        repository_policy_digest=_C,
        manifest_digest=_D,
        candidate_digest=_E,
        candidate_tree_digest=_F,
        final_diff_digest=_A,
        target_test_ids=ids.target_test_ids,
        entries=plan_entries,
    )
    return {
        "schema_version": 1,
        "check_plan_version": "1",
        "adapter_version": ADAPTER_VERSION,
        "python_version": "3.12.4",
        "pytest_version": "8.4.2",
        "report_plugin_version": "1",
        "ruff_version": "0.16.1",
        "mypy_version": "2.3.0",
        "docker_image_digest": _IMAGE_DIGEST,
        "docker_execution_profile_version": 1,
        "reference_profile_digest": _A,
        "snapshot_tree_digest": _B,
        "repository_policy_digest": _C,
        "manifest_digest": _D,
        "candidate_digest": _E,
        "candidate_tree_digest": _F,
        "final_diff_digest": _A,
        "target_test_ids": ids,
        "entries": plan_entries,
        "digest": digest,
    }


def test_plan_schemas_reject_unknown_fields_and_coerced_versions() -> None:
    fields = _baseline_fields()
    fields["extra"] = "forbidden"
    with pytest.raises(ValidationError):
        BaselineCheckPlanV1.model_validate(fields)
    coerced = _baseline_fields()
    coerced["schema_version"] = "1"
    with pytest.raises(ValidationError):
        BaselineCheckPlanV1.model_validate(coerced)
    malformed = _baseline_fields()
    malformed["digest"] = "not-a-digest"
    with pytest.raises(ValidationError):
        BaselineCheckPlanV1.model_validate(malformed)
    formal = _formal_fields()
    formal["digest"] = "not-a-digest"
    with pytest.raises(ValidationError):
        FormalValidationCheckPlanV1.model_validate(formal)
    bad_image = _baseline_fields()
    bad_image["docker_image_digest"] = "short"
    with pytest.raises(ValidationError):
        BaselineCheckPlanV1.model_validate(bad_image)


def test_result_value_schemas_are_closed() -> None:
    with pytest.raises(ValidationError):
        SupportedProjectV1(
            kind="SUPPORTED",
            profile_id="",
            reference_profile_digest=_A,
            snapshot_root_digest=_B,
            repository_policy_digest=_C,
        )
    with pytest.raises(ValidationError):
        UnsupportedProjectV1(
            kind="UNSUPPORTED",
            reference_profile_digest=_A,
            snapshot_root_digest=_B,
            repository_policy_digest=_C,
            reasons=("",),
        )
    with pytest.raises(ValidationError):
        SupportedProjectV1(
            kind=cast(Literal["SUPPORTED"], "UNSUPPORTED"),
            profile_id="python-src-py312-v1",
            reference_profile_digest=_A,
            snapshot_root_digest=_B,
            repository_policy_digest=_C,
        )
    with pytest.raises(ValidationError):
        UnsupportedProjectV1(
            kind="UNSUPPORTED",
            reference_profile_digest=_A,
            snapshot_root_digest=_B,
            repository_policy_digest=_C,
            reasons=(),
        )

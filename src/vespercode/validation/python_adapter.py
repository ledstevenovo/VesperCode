"""T20.1 legacy step 20.A: static Python support detection (SPEC §1.4.1).

``PythonProjectAdapterV1`` determines support for the sole
``python-src-py312-v1`` reference profile from one sealed
``SnapshotTreeV1`` and the frozen ``ReferenceProfileManifestV1`` only —
zero filesystem probes, project imports, subprocesses, or executor calls —
and then freezes the complete closed Baseline and formal validation check
plans (exact collect/full-suite/target-test/Ruff/Mypy identities, argv
vectors, ordering, and target bindings) without executing anything
(GREEN-1..GREEN-4).  Runtime compatibility, execution, result parsing,
and Manifest publication belong to Task 20.B/21; static classification
and frozen plan generation are this task's whole scope.

The static classification is the exact §1.4.1 ``StaticProjectProfileCheckV1``
matrix: Snapshot identity (policy binding), root files, source layout,
Python/tool declarations (manifest digest binding), pytest/Ruff/Mypy
configuration, dependencies, editable-file text profiles, and pytest
extensions.  Any item that cannot be proven from the sealed Snapshot
returns ``UNSUPPORTED_PROJECT`` with deterministic ordered reasons; the
adapter never guesses, executes, rereads the authoritative workspace, or
creates a second Snapshot.
"""

from __future__ import annotations

import hashlib
import shlex
import tomllib
from typing import Annotated, Literal, Protocol, TypeAlias, cast

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictStr,
    field_validator,
    model_validator,
)

from src.vespercode.canonical.digest import domain_digest
from src.vespercode.canonical.json_v1 import CanonicalValueV1
from src.vespercode.canonical.path_v1 import CanonicalRelativePathV1
from src.vespercode.contracts.evidence import _DIGEST_RE
from src.vespercode.contracts.optional import AbsentV1, PresentV1
from src.vespercode.execution.docker_profile import ExecutionArgumentSequenceV1
from src.vespercode.profiles.reference import (
    ReferenceProfileManifestV1,
    _compute_manifest_digest,
)
from src.vespercode.trees.snapshot import (
    SnapshotDirectoryEntryV1,
    SnapshotFileEntryV1,
    SnapshotTreeV1,
)

# The frozen adapter identity bound into every generated plan (SPEC §4.5
# ``ValidationManifestV1.adapter_version``; the plan/Manifest chain must
# bind the same value).
ADAPTER_VERSION = "1"

# The frozen workspace mount inside the execution image (SPEC §1.4.5).
_FROZEN_WORKSPACE = "/workspace"

# The frozen profile-v1 pytest report-plugin module: the explicit ``-p``
# load of the fixed machine-readable report plugin (SPEC §1.4.1 "允许内建
# 插件及执行镜像内固定的机器可读报告插件"; the T02.4-proven explicit-load
# mechanism, never entry-point autoload — profile v1 disables it).
_REPORT_PLUGIN_MODULE = "vespercode.validation.pytest_reporter"

# The single versioned static-detection entrypoint tables (SPEC §1.4.2
# "保护集合必须由代码中的单一版本化表生成"): root-level pytest/Ruff/Mypy
# config entrypoints, root-level dependency entrypoints, and interpreter
# startup entrypoints that are forbidden anywhere in the tree.
_ROOT_CONFIG_ENTRYPOINTS: tuple[str, ...] = (
    "pytest.ini",
    "tox.ini",
    "setup.cfg",
    "mypy.ini",
    ".ruff.toml",
    "ruff.toml",
)
_ROOT_DEPENDENCY_ENTRYPOINTS: tuple[str, ...] = (
    "poetry.lock",
    "uv.lock",
    "pdm.lock",
)
_ANYWHERE_INTERPRETER_ENTRYPOINTS: tuple[str, ...] = (
    "sitecustomize.py",
    "usercustomize.py",
)

# The closed set of pytest addopts flags that change the collected set or
# the execution selection (SPEC §1.4.2 "其他会改变 pytest 收集...行为的入
# 口"): the frozen full-suite plan requires every test to be collected and
# executed with no deselection, so a project that selects a subset through
# its own config is not the reference profile's normal form.
_SELECTION_ADDOPTS_FLAGS: tuple[str, ...] = (
    "-k",
    "--ignore",
    "--ignore-glob",
    "--deselect",
    "--lf",
    "--last-failed",
    "--ff",
    "--failed-first",
    "--co",
    "--collect-only",
)


def _require_digest_form(value: str) -> str:
    """Reject any spelling that is not exactly 64 lowercase hex chars."""
    if _DIGEST_RE.fullmatch(value) is None:
        raise ValueError("must be exactly 64 lowercase hexadecimal characters")
    return value


def _reject_coerced_schema_version(value: object) -> object:
    """Reject bool/float/string spelling of the integer literal 1."""
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError("schema_version must be the decimal integer 1")
    return value


CheckIdentityV1 = Literal["COLLECT_ONLY", "FULL_PYTEST", "TARGET_TESTS", "RUFF", "MYPY"]
"""The closed check identity vocabulary of the frozen check plans.

``COLLECT_ONLY`` appears only in the Baseline sequence (SPEC §4.5 steps
1-2); the agent-loop ``RunCheckAction`` plan ids stay exactly
``TARGET_TESTS | FULL_PYTEST | RUFF | MYPY`` (SPEC §4.2.2).
"""

FormalCheckIdentityV1 = Literal["COLLECT_ONLY", "FULL_PYTEST", "RUFF", "MYPY"]
"""The closed formal-validation check identity set (SPEC §4.5/§4.2.3:
collect, full pytest, Ruff, Mypy; no target-only rerun)."""


class TargetTestIdSequenceV1(BaseModel):
    """An immutable ordered tuple of one or more exact pytest node ids.

    The ordered tuple preserves the frozen request order (SPEC §4.1
    ``target_test_ids: 1..20 unique exact pytest node IDs``); each id is
    non-empty and at most 1024 UTF-8 bytes, and duplicates reject.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)
    target_test_ids: tuple[StrictStr, ...]

    @field_validator("target_test_ids")
    @classmethod
    def _require_exact_target_set(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if not value:
            raise ValueError("target_test_ids must contain at least one id")
        if len(value) > 20:
            raise ValueError("target_test_ids must contain at most 20 ids")
        if len(set(value)) != len(value):
            raise ValueError("target_test_ids must be unique")
        for node_id in value:
            if node_id == "":
                raise ValueError("target node ids must be non-empty")
            if len(node_id.encode("utf-8")) > 1024:
                raise ValueError("target node ids must be at most 1024 UTF-8 bytes")
        return value


class SupportedProjectV1(BaseModel):
    """SPEC §1.4.1 ``SUPPORTED``: the profile, manifest, and Snapshot facts.

    All three digests bind the input Snapshot, frozen manifest, and
    precheck-frozen policy verbatim (SPEC §4.1 behavior 10).
    """

    model_config = ConfigDict(extra="forbid", frozen=True)
    kind: Literal["SUPPORTED"]
    profile_id: StrictStr
    reference_profile_digest: StrictStr
    snapshot_root_digest: StrictStr
    repository_policy_digest: StrictStr

    @field_validator("profile_id")
    @classmethod
    def _profile_id_must_be_non_empty(cls, value: str) -> str:
        if value == "":
            raise ValueError("profile_id must be non-empty")
        return value

    @field_validator(
        "reference_profile_digest", "snapshot_root_digest", "repository_policy_digest"
    )
    @classmethod
    def _digests_have_exact_form(cls, value: str) -> str:
        return _require_digest_form(value)


class UnsupportedProjectV1(BaseModel):
    """SPEC §1.4.1 ``UNSUPPORTED_PROJECT``: the same bindings plus reasons.

    ``reasons`` is the deterministic ordered non-empty list of static
    facts that could not be proven from the sealed Snapshot; the result
    still binds the input Snapshot, frozen manifest, and policy digests
    verbatim so the rejection can never bind a different identity.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)
    kind: Literal["UNSUPPORTED"]
    reference_profile_digest: StrictStr
    snapshot_root_digest: StrictStr
    repository_policy_digest: StrictStr
    reasons: tuple[StrictStr, ...]

    @field_validator(
        "reference_profile_digest", "snapshot_root_digest", "repository_policy_digest"
    )
    @classmethod
    def _digests_have_exact_form(cls, value: str) -> str:
        return _require_digest_form(value)

    @field_validator("reasons")
    @classmethod
    def _reasons_must_be_non_empty(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if not value:
            raise ValueError("UNSUPPORTED results require at least one reason")
        if any(reason == "" for reason in value):
            raise ValueError("unsupported reasons must be non-empty")
        return value


StaticProjectProfileResultV1: TypeAlias = Annotated[
    SupportedProjectV1 | UnsupportedProjectV1, Field(discriminator="kind")
]
"""SPEC §1.4.1: ``SUPPORTED | UNSUPPORTED_PROJECT``."""

OptionalTargetTestIdSequenceV1: TypeAlias = Annotated[
    AbsentV1 | PresentV1[TargetTestIdSequenceV1], Field(discriminator="kind")
]
"""The closed optional target binding of one plan entry."""


class BaselineCheckPlanEntryV1(BaseModel):
    """One frozen Baseline check: identity, exact argv, target binding.

    Only ``TARGET_TESTS`` may carry a ``PRESENT`` target binding; every
    other check binds ``ABSENT`` (the entry's target ids are the exact
    pytest node ids from the frozen request).
    """

    model_config = ConfigDict(extra="forbid", frozen=True)
    check_id: CheckIdentityV1
    argv: ExecutionArgumentSequenceV1
    target_test_ids: OptionalTargetTestIdSequenceV1

    @model_validator(mode="after")
    def _require_exact_target_binding(self) -> BaselineCheckPlanEntryV1:
        if self.check_id == "TARGET_TESTS":
            if not isinstance(self.target_test_ids, PresentV1):
                raise ValueError("TARGET_TESTS entries require PRESENT target ids")
        elif isinstance(self.target_test_ids, PresentV1):
            raise ValueError("only TARGET_TESTS entries may bind target ids")
        return self


class FormalCheckPlanEntryV1(BaseModel):
    """One frozen formal-validation check: identity plus exact argv."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    check_id: FormalCheckIdentityV1
    argv: ExecutionArgumentSequenceV1


class BaselineCheckPlanV1(BaseModel):
    """The complete closed Baseline check plan (SPEC §4.5 fixed order).

    Binds the exact manifest/tool/image/execution identities, the frozen
    target ids, and the six ordered checks — collect-only x2, full pytest,
    target rerun, Ruff, Mypy — each with its exact adapter-built argv.
    The digest is the §0.1 identity of every other field and is re-bound
    at construction, so a plan with a non-binding digest can never exist.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal[1]
    check_plan_version: StrictStr
    adapter_version: StrictStr
    python_version: StrictStr
    pytest_version: StrictStr
    report_plugin_version: StrictStr
    ruff_version: StrictStr
    mypy_version: StrictStr
    docker_image_digest: StrictStr
    docker_execution_profile_version: Literal[1]
    reference_profile_digest: StrictStr
    snapshot_root_digest: StrictStr
    repository_policy_digest: StrictStr
    target_test_ids: TargetTestIdSequenceV1
    entries: tuple[BaselineCheckPlanEntryV1, ...]
    digest: StrictStr

    @field_validator(
        "schema_version", "docker_execution_profile_version", mode="before"
    )
    @classmethod
    def _version_is_exact_int_one(cls, value: object) -> object:
        return _reject_coerced_schema_version(value)

    @field_validator(
        "docker_image_digest",
        "reference_profile_digest",
        "snapshot_root_digest",
        "repository_policy_digest",
        "digest",
    )
    @classmethod
    def _digests_have_exact_form(cls, value: str) -> str:
        return _require_digest_form(value)

    @field_validator(
        "check_plan_version",
        "adapter_version",
        "python_version",
        "pytest_version",
        "report_plugin_version",
        "ruff_version",
        "mypy_version",
    )
    @classmethod
    def _version_fields_must_be_non_empty(cls, value: str) -> str:
        if value == "":
            raise ValueError("version fields must be non-empty")
        return value

    @model_validator(mode="after")
    def _require_canonical_baseline_order(self) -> BaselineCheckPlanV1:
        if tuple(entry.check_id for entry in self.entries) != (
            "COLLECT_ONLY",
            "COLLECT_ONLY",
            "FULL_PYTEST",
            "TARGET_TESTS",
            "RUFF",
            "MYPY",
        ):
            raise ValueError(
                "baseline entries must be exactly COLLECT_ONLY, COLLECT_ONLY, "
                "FULL_PYTEST, TARGET_TESTS, RUFF, MYPY"
            )
        return self

    @model_validator(mode="after")
    def _digest_binds_every_other_field(self) -> BaselineCheckPlanV1:
        recomputed = _compute_baseline_plan_digest(
            check_plan_version=self.check_plan_version,
            adapter_version=self.adapter_version,
            python_version=self.python_version,
            pytest_version=self.pytest_version,
            report_plugin_version=self.report_plugin_version,
            ruff_version=self.ruff_version,
            mypy_version=self.mypy_version,
            docker_image_digest=self.docker_image_digest,
            docker_execution_profile_version=self.docker_execution_profile_version,
            reference_profile_digest=self.reference_profile_digest,
            snapshot_root_digest=self.snapshot_root_digest,
            repository_policy_digest=self.repository_policy_digest,
            target_test_ids=self.target_test_ids.target_test_ids,
            entries=self.entries,
        )
        if recomputed != self.digest:
            raise ValueError("plan digest does not bind the plan fields")
        return self


class FormalValidationCheckPlanV1(BaseModel):
    """The complete closed formal-validation check plan (SPEC §4.5).

    Binds the manifest and candidate identities (so the plan goes stale
    when either changes), the same frozen tool/image/execution identities,
    and the four ordered checks — collect-only, full pytest, Ruff, Mypy.
    The digest is the §0.1 identity of every other field and is re-bound
    at construction.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal[1]
    check_plan_version: StrictStr
    adapter_version: StrictStr
    python_version: StrictStr
    pytest_version: StrictStr
    report_plugin_version: StrictStr
    ruff_version: StrictStr
    mypy_version: StrictStr
    docker_image_digest: StrictStr
    docker_execution_profile_version: Literal[1]
    reference_profile_digest: StrictStr
    snapshot_tree_digest: StrictStr
    repository_policy_digest: StrictStr
    manifest_digest: StrictStr
    candidate_digest: StrictStr
    candidate_tree_digest: StrictStr
    final_diff_digest: StrictStr
    target_test_ids: TargetTestIdSequenceV1
    entries: tuple[FormalCheckPlanEntryV1, ...]
    digest: StrictStr

    @field_validator(
        "schema_version", "docker_execution_profile_version", mode="before"
    )
    @classmethod
    def _version_is_exact_int_one(cls, value: object) -> object:
        return _reject_coerced_schema_version(value)

    @field_validator(
        "docker_image_digest",
        "reference_profile_digest",
        "snapshot_tree_digest",
        "repository_policy_digest",
        "manifest_digest",
        "candidate_digest",
        "candidate_tree_digest",
        "final_diff_digest",
        "digest",
    )
    @classmethod
    def _digests_have_exact_form(cls, value: str) -> str:
        return _require_digest_form(value)

    @field_validator(
        "check_plan_version",
        "adapter_version",
        "python_version",
        "pytest_version",
        "report_plugin_version",
        "ruff_version",
        "mypy_version",
    )
    @classmethod
    def _version_fields_must_be_non_empty(cls, value: str) -> str:
        if value == "":
            raise ValueError("version fields must be non-empty")
        return value

    @model_validator(mode="after")
    def _require_canonical_formal_order(self) -> FormalValidationCheckPlanV1:
        if tuple(entry.check_id for entry in self.entries) != (
            "COLLECT_ONLY",
            "FULL_PYTEST",
            "RUFF",
            "MYPY",
        ):
            raise ValueError(
                "formal entries must be exactly COLLECT_ONLY, FULL_PYTEST, RUFF, MYPY"
            )
        return self

    @model_validator(mode="after")
    def _digest_binds_every_other_field(self) -> FormalValidationCheckPlanV1:
        recomputed = _compute_formal_plan_digest(
            check_plan_version=self.check_plan_version,
            adapter_version=self.adapter_version,
            python_version=self.python_version,
            pytest_version=self.pytest_version,
            report_plugin_version=self.report_plugin_version,
            ruff_version=self.ruff_version,
            mypy_version=self.mypy_version,
            docker_image_digest=self.docker_image_digest,
            docker_execution_profile_version=self.docker_execution_profile_version,
            reference_profile_digest=self.reference_profile_digest,
            snapshot_tree_digest=self.snapshot_tree_digest,
            repository_policy_digest=self.repository_policy_digest,
            manifest_digest=self.manifest_digest,
            candidate_digest=self.candidate_digest,
            candidate_tree_digest=self.candidate_tree_digest,
            final_diff_digest=self.final_diff_digest,
            target_test_ids=self.target_test_ids.target_test_ids,
            entries=self.entries,
        )
        if recomputed != self.digest:
            raise ValueError("plan digest does not bind the plan fields")
        return self


class ValidationManifestV1(Protocol):
    """The structural formal-plan consumption contract of the T20.2
    ``ValidationManifestV1`` (SPEC §4.5).

    This is the adapter's read-only port — the closed manifest schema
    itself is owned and published by Task 20.B; the adapter binds exactly
    the declared fields into the frozen formal plan.
    """

    schema_version: int
    check_plan_version: str
    adapter_version: str
    python_version: str
    pytest_version: str
    report_plugin_version: str
    ruff_version: str
    mypy_version: str
    docker_image_digest: str
    docker_execution_profile_version: int
    reference_profile_digest: str
    snapshot_tree_digest: str
    repository_policy_digest: str
    target_test_ids: tuple[str, ...]
    digest: str


class CandidateIdentityV1(Protocol):
    """The structural formal-plan consumption contract of the T12.1
    ``CandidateIdentityV1`` (SPEC §4.3: Snapshot/CandidateTree/FinalDiff
    triple binding)."""

    schema_version: int
    snapshot_tree_digest: str
    candidate_tree_digest: str
    final_diff_digest: str
    digest: str


CheckPlanErrorCodeV1 = Literal[
    "PROFILE_NOT_SUPPORTED",
    "PROFILE_BINDING_MISMATCH",
    "PROFILE_FIELD_MISMATCH",
    "SNAPSHOT_IDENTITY_MISMATCH",
    "BINDING_DIGEST_MALFORMED",
    "TARGET_IDS_INVALID",
]


class CheckPlanError(Exception):
    """One closed plan-construction rejection; the code prefixes the
    message and no plan exists after a raise (SPEC §4.5 "绑定不一致时失败
    关闭，不得构造基线计划")."""

    def __init__(self, error_code: CheckPlanErrorCodeV1, reason: str) -> None:
        super().__init__(f"{error_code}: {reason}")
        self.error_code = error_code
        self.reason = reason


def _pytest_base_argv() -> tuple[str, ...]:
    """The frozen pytest argv prefix (T02.4-proven explicit plugin load)."""
    return (
        "python",
        "-m",
        "pytest",
        "-p",
        _REPORT_PLUGIN_MODULE,
        "-o",
        "cacheprovider=disabled",
        "--rootdir",
        _FROZEN_WORKSPACE,
    )


def _collect_only_argv() -> ExecutionArgumentSequenceV1:
    return ExecutionArgumentSequenceV1(
        arguments=(*_pytest_base_argv(), "--collect-only", _FROZEN_WORKSPACE)
    )


def _full_pytest_argv() -> ExecutionArgumentSequenceV1:
    return ExecutionArgumentSequenceV1(
        arguments=(*_pytest_base_argv(), _FROZEN_WORKSPACE)
    )


def _target_tests_argv(
    target_test_ids: TargetTestIdSequenceV1,
) -> ExecutionArgumentSequenceV1:
    return ExecutionArgumentSequenceV1(
        arguments=(*_pytest_base_argv(), *target_test_ids.target_test_ids)
    )


def _ruff_argv() -> ExecutionArgumentSequenceV1:
    return ExecutionArgumentSequenceV1(arguments=("ruff", "check", _FROZEN_WORKSPACE))


def _mypy_argv() -> ExecutionArgumentSequenceV1:
    return ExecutionArgumentSequenceV1(
        arguments=(
            "mypy",
            "--config-file",
            f"{_FROZEN_WORKSPACE}/pyproject.toml",
            f"{_FROZEN_WORKSPACE}/src",
        )
    )


def _baseline_entry(
    check_id: CheckIdentityV1,
    argv: ExecutionArgumentSequenceV1,
    target_test_ids: TargetTestIdSequenceV1 | None = None,
) -> BaselineCheckPlanEntryV1:
    binding: AbsentV1 | PresentV1[TargetTestIdSequenceV1]
    if target_test_ids is None:
        binding = AbsentV1(kind="ABSENT")
    else:
        binding = PresentV1(kind="PRESENT", value=target_test_ids)
    return BaselineCheckPlanEntryV1(
        check_id=check_id, argv=argv, target_test_ids=binding
    )


def _formal_entry(
    check_id: FormalCheckIdentityV1, argv: ExecutionArgumentSequenceV1
) -> FormalCheckPlanEntryV1:
    return FormalCheckPlanEntryV1(check_id=check_id, argv=argv)


def _baseline_entry_body(
    entry: BaselineCheckPlanEntryV1,
) -> dict[str, CanonicalValueV1]:
    if isinstance(entry.target_test_ids, AbsentV1):
        target_binding: CanonicalValueV1 = {"kind": "ABSENT"}
    else:
        target_binding = {
            "kind": "PRESENT",
            "value": entry.target_test_ids.value.target_test_ids,
        }
    return {
        "check_id": entry.check_id,
        "argv": tuple(entry.argv.arguments),
        "target_test_ids": target_binding,
    }


def _formal_entry_body(entry: FormalCheckPlanEntryV1) -> dict[str, CanonicalValueV1]:
    return {
        "check_id": entry.check_id,
        "argv": tuple(entry.argv.arguments),
    }


def _baseline_plan_body(
    *,
    check_plan_version: str,
    adapter_version: str,
    python_version: str,
    pytest_version: str,
    report_plugin_version: str,
    ruff_version: str,
    mypy_version: str,
    docker_image_digest: str,
    docker_execution_profile_version: int,
    reference_profile_digest: str,
    snapshot_root_digest: str,
    repository_policy_digest: str,
    target_test_ids: tuple[str, ...],
    entries: tuple[BaselineCheckPlanEntryV1, ...],
) -> dict[str, CanonicalValueV1]:
    """The canonical §0.1 digest body of one Baseline plan (no digest)."""
    return {
        "schema_version": 1,
        "check_plan_version": check_plan_version,
        "adapter_version": adapter_version,
        "python_version": python_version,
        "pytest_version": pytest_version,
        "report_plugin_version": report_plugin_version,
        "ruff_version": ruff_version,
        "mypy_version": mypy_version,
        "docker_image_digest": docker_image_digest,
        "docker_execution_profile_version": docker_execution_profile_version,
        "reference_profile_digest": reference_profile_digest,
        "snapshot_root_digest": snapshot_root_digest,
        "repository_policy_digest": repository_policy_digest,
        "target_test_ids": tuple(target_test_ids),
        "entries": tuple(_baseline_entry_body(entry) for entry in entries),
    }


def _formal_plan_body(
    *,
    check_plan_version: str,
    adapter_version: str,
    python_version: str,
    pytest_version: str,
    report_plugin_version: str,
    ruff_version: str,
    mypy_version: str,
    docker_image_digest: str,
    docker_execution_profile_version: int,
    reference_profile_digest: str,
    snapshot_tree_digest: str,
    repository_policy_digest: str,
    manifest_digest: str,
    candidate_digest: str,
    candidate_tree_digest: str,
    final_diff_digest: str,
    target_test_ids: tuple[str, ...],
    entries: tuple[FormalCheckPlanEntryV1, ...],
) -> dict[str, CanonicalValueV1]:
    """The canonical §0.1 digest body of one formal plan (no digest)."""
    return {
        "schema_version": 1,
        "check_plan_version": check_plan_version,
        "adapter_version": adapter_version,
        "python_version": python_version,
        "pytest_version": pytest_version,
        "report_plugin_version": report_plugin_version,
        "ruff_version": ruff_version,
        "mypy_version": mypy_version,
        "docker_image_digest": docker_image_digest,
        "docker_execution_profile_version": docker_execution_profile_version,
        "reference_profile_digest": reference_profile_digest,
        "snapshot_tree_digest": snapshot_tree_digest,
        "repository_policy_digest": repository_policy_digest,
        "manifest_digest": manifest_digest,
        "candidate_digest": candidate_digest,
        "candidate_tree_digest": candidate_tree_digest,
        "final_diff_digest": final_diff_digest,
        "target_test_ids": tuple(target_test_ids),
        "entries": tuple(_formal_entry_body(entry) for entry in entries),
    }


def _compute_baseline_plan_digest(
    *,
    check_plan_version: str,
    adapter_version: str,
    python_version: str,
    pytest_version: str,
    report_plugin_version: str,
    ruff_version: str,
    mypy_version: str,
    docker_image_digest: str,
    docker_execution_profile_version: int,
    reference_profile_digest: str,
    snapshot_root_digest: str,
    repository_policy_digest: str,
    target_test_ids: tuple[str, ...],
    entries: tuple[BaselineCheckPlanEntryV1, ...],
) -> str:
    """The §0.1 identity of every exact Baseline plan field except digest."""
    return domain_digest(
        "BaselineCheckPlanV1",
        1,
        _baseline_plan_body(
            check_plan_version=check_plan_version,
            adapter_version=adapter_version,
            python_version=python_version,
            pytest_version=pytest_version,
            report_plugin_version=report_plugin_version,
            ruff_version=ruff_version,
            mypy_version=mypy_version,
            docker_image_digest=docker_image_digest,
            docker_execution_profile_version=docker_execution_profile_version,
            reference_profile_digest=reference_profile_digest,
            snapshot_root_digest=snapshot_root_digest,
            repository_policy_digest=repository_policy_digest,
            target_test_ids=target_test_ids,
            entries=entries,
        ),
    )


def _compute_formal_plan_digest(
    *,
    check_plan_version: str,
    adapter_version: str,
    python_version: str,
    pytest_version: str,
    report_plugin_version: str,
    ruff_version: str,
    mypy_version: str,
    docker_image_digest: str,
    docker_execution_profile_version: int,
    reference_profile_digest: str,
    snapshot_tree_digest: str,
    repository_policy_digest: str,
    manifest_digest: str,
    candidate_digest: str,
    candidate_tree_digest: str,
    final_diff_digest: str,
    target_test_ids: tuple[str, ...],
    entries: tuple[FormalCheckPlanEntryV1, ...],
) -> str:
    """The §0.1 identity of every exact formal plan field except digest."""
    return domain_digest(
        "FormalValidationCheckPlanV1",
        1,
        _formal_plan_body(
            check_plan_version=check_plan_version,
            adapter_version=adapter_version,
            python_version=python_version,
            pytest_version=pytest_version,
            report_plugin_version=report_plugin_version,
            ruff_version=ruff_version,
            mypy_version=mypy_version,
            docker_image_digest=docker_image_digest,
            docker_execution_profile_version=docker_execution_profile_version,
            reference_profile_digest=reference_profile_digest,
            snapshot_tree_digest=snapshot_tree_digest,
            repository_policy_digest=repository_policy_digest,
            manifest_digest=manifest_digest,
            candidate_digest=candidate_digest,
            candidate_tree_digest=candidate_tree_digest,
            final_diff_digest=final_diff_digest,
            target_test_ids=target_test_ids,
            entries=entries,
        ),
    )


def _tool_table(
    pyproject: dict[str, object], tool_name: str
) -> dict[str, object] | None:
    """One [tool.<name>] table from parsed pyproject bytes, or None."""
    tool = pyproject.get("tool")
    if not isinstance(tool, dict):
        return None
    section = tool.get(tool_name)
    if not isinstance(section, dict):
        return None
    return section


def _contains_flag(tokens: list[str], *flags: str) -> bool:
    """True when one argparse flag appears in an addopts token stream.

    Argparse accepts three spellings of a value-taking option: the exact
    token (``-m``), the ``=``-spelling (``-m=expr``, ``--markexpr=expr``),
    and the concatenated short-option value (``-pp`` parses as ``-p p``,
    ``-mnot`` parses as ``-m not`` — verified against pytest 8.4.2).
    """
    for token in tokens:
        for flag in flags:
            if token == flag:
                return True
            if token.startswith("--"):
                if token.startswith(f"{flag}="):
                    return True
            elif token.startswith(flag):
                return True
    return False


class PythonProjectAdapterV1:
    """The v1 Python project adapter (SPEC §4.5 adapter boundary).

    The adapter is bound to exactly one frozen built-in
    ``ReferenceProfileManifestV1`` at construction; detection consumes
    only sealed Snapshot facts and the frozen manifest, and plan
    generation binds the same frozen manifest identity.  The adapter
    never touches the filesystem, imports or executes project code,
    spawns subprocesses, or calls any executor.
    """

    def __init__(self, reference_manifest: ReferenceProfileManifestV1) -> None:
        self._reference_manifest = reference_manifest

    def detect_static(
        self,
        snapshot: SnapshotTreeV1,
        reference_manifest: ReferenceProfileManifestV1,
    ) -> StaticProjectProfileResultV1:
        """Classify the sealed Snapshot against the exact §1.4.1 matrix.

        Every static item is proven from the sealed Snapshot and the
        frozen manifest only; each unprovable item appends one
        deterministic reason, and the result always binds the input
        Snapshot, manifest, and policy digests verbatim (SPEC §4.1
        behavior 10).
        """
        reasons: list[str] = []
        if reference_manifest.digest != self._reference_manifest.digest:
            reasons.append("MANIFEST_IDENTITY_MISMATCH")
        if reference_manifest.digest != _compute_manifest_digest(reference_manifest):
            reasons.append("MANIFEST_DIGEST_MISMATCH")
        if (
            snapshot.repository_policy_digest
            != reference_manifest.editable_path_policy.digest
        ):
            reasons.append("POLICY_BINDING_MISMATCH")

        file_paths = {
            entry.path.value
            for entry in snapshot.entries
            if isinstance(entry, SnapshotFileEntryV1)
        }
        directory_paths = {
            entry.path.value
            for entry in snapshot.entries
            if isinstance(entry, SnapshotDirectoryEntryV1)
        }

        for required in ("pyproject.toml", "requirements.lock"):
            if required not in file_paths:
                reasons.append(f"ROOT_FILE_MISSING:{required}")
        for required in ("src", "tests"):
            if required not in directory_paths:
                reasons.append(f"SOURCE_LAYOUT_MISSING:{required}")

        pytest_options: dict[str, object] | None = None
        if "pyproject.toml" in file_paths:
            try:
                pyproject = tomllib.loads(
                    snapshot.read_bytes(
                        CanonicalRelativePathV1("pyproject.toml")
                    ).decode("utf-8")
                )
            except (UnicodeDecodeError, tomllib.TOMLDecodeError):
                reasons.append("PYPROJECT_INVALID")
            else:
                pytest_section = _tool_table(pyproject, "pytest")
                if pytest_section is not None:
                    ini_options = pytest_section.get("ini_options")
                    if isinstance(ini_options, dict):
                        pytest_options = ini_options
                if pytest_options is None:
                    reasons.append("PYTEST_NOT_CONFIGURED")
                else:
                    if (
                        "plugins" in pytest_options
                        or "required_plugins" in pytest_options
                    ):
                        reasons.append("PLUGIN_DECLARED")
                    addopts = pytest_options.get("addopts")
                    if isinstance(addopts, str):
                        tokens = shlex.split(addopts)
                        if _contains_flag(tokens, "-p"):
                            reasons.append("PLUGIN_ADDOPTS")
                        if _contains_flag(tokens, "-m", "--markexpr"):
                            reasons.append("MARKER_EXPRESSION_ADDOPTS")
                        if _contains_flag(tokens, *_SELECTION_ADDOPTS_FLAGS):
                            reasons.append("SELECTION_ADDOPTS")
                if _tool_table(pyproject, "ruff") is None:
                    reasons.append("TOOL_NOT_CONFIGURED:ruff")
                if _tool_table(pyproject, "mypy") is None:
                    reasons.append("TOOL_NOT_CONFIGURED:mypy")

        if "requirements.lock" in file_paths:
            lock_raw = snapshot.read_bytes(CanonicalRelativePathV1("requirements.lock"))
            if hashlib.sha256(lock_raw).hexdigest() != (
                reference_manifest.requirements_lock_digest
            ):
                reasons.append("DEPENDENCY_DIGEST_MISMATCH")

        for name in _ROOT_CONFIG_ENTRYPOINTS:
            if name in file_paths:
                reasons.append(f"CONFIG_ENTRYPOINT:{name}")
        for name in _ROOT_DEPENDENCY_ENTRYPOINTS:
            if name in file_paths:
                reasons.append(f"DEPENDENCY_ENTRYPOINT:{name}")
        for path in sorted(file_paths):
            if path.startswith("requirements") and path.endswith(".txt"):
                reasons.append(f"DEPENDENCY_ENTRYPOINT:{path}")
            basename = path.rsplit("/", 1)[-1]
            if basename == "conftest.py":
                reasons.append("PLUGIN_ENTRYPOINT:conftest.py")
            elif basename in _ANYWHERE_INTERPRETER_ENTRYPOINTS:
                reasons.append(f"INTERPRETER_ENTRYPOINT:{basename}")

        for entry in snapshot.entries:
            if (
                isinstance(entry, SnapshotFileEntryV1)
                and entry.path.value.startswith("src/")
                and entry.kind != "TEXT_FILE"
            ):
                reasons.append(f"EDITABLE_FILE_NOT_TEXT:{entry.path.value}")

        if reasons:
            return UnsupportedProjectV1(
                kind="UNSUPPORTED",
                reference_profile_digest=reference_manifest.digest,
                snapshot_root_digest=snapshot.root_digest,
                repository_policy_digest=snapshot.repository_policy_digest,
                reasons=tuple(reasons),
            )
        return SupportedProjectV1(
            kind="SUPPORTED",
            profile_id=reference_manifest.profile_id,
            reference_profile_digest=reference_manifest.digest,
            snapshot_root_digest=snapshot.root_digest,
            repository_policy_digest=snapshot.repository_policy_digest,
        )

    def build_baseline_plan(
        self,
        static_profile: SupportedProjectV1,
        target_test_ids: TargetTestIdSequenceV1,
    ) -> BaselineCheckPlanV1:
        """Freeze the one closed Baseline plan from a SUPPORTED profile.

        The plan binds the frozen manifest/tool/image identities, the
        static profile's Snapshot/policy digests, and the six ordered
        SPEC §4.5 checks with exact argv; a profile not bound to the
        adapter's frozen manifest rejects closed before any plan exists.
        """
        if static_profile.kind != "SUPPORTED":
            raise CheckPlanError(
                "PROFILE_NOT_SUPPORTED",
                "only SUPPORTED static profiles can build a Baseline plan",
            )
        if static_profile.reference_profile_digest != self._reference_manifest.digest:
            raise CheckPlanError(
                "PROFILE_BINDING_MISMATCH",
                "the static profile does not bind the adapter's frozen manifest",
            )
        manifest = self._reference_manifest
        # The frozen built-in profile selects execution profile version 1;
        # the manifest field is validated by T06.2 but typed as plain int,
        # so the closed plan pins the exact literal after the identity
        # checks above (any drifted value is already a binding mismatch).
        execution_profile_version: Literal[1] = cast(
            Literal[1], manifest.docker_execution_profile_version
        )
        entries = (
            _baseline_entry("COLLECT_ONLY", _collect_only_argv()),
            _baseline_entry("COLLECT_ONLY", _collect_only_argv()),
            _baseline_entry("FULL_PYTEST", _full_pytest_argv()),
            _baseline_entry(
                "TARGET_TESTS",
                _target_tests_argv(target_test_ids),
                target_test_ids=target_test_ids,
            ),
            _baseline_entry("RUFF", _ruff_argv()),
            _baseline_entry("MYPY", _mypy_argv()),
        )
        digest = _compute_baseline_plan_digest(
            check_plan_version=manifest.check_plan_version,
            adapter_version=ADAPTER_VERSION,
            python_version=manifest.python_version,
            pytest_version=manifest.pytest_version,
            report_plugin_version=manifest.report_plugin_version,
            ruff_version=manifest.ruff_version,
            mypy_version=manifest.mypy_version,
            docker_image_digest=manifest.docker_image_digest,
            docker_execution_profile_version=execution_profile_version,
            reference_profile_digest=static_profile.reference_profile_digest,
            snapshot_root_digest=static_profile.snapshot_root_digest,
            repository_policy_digest=static_profile.repository_policy_digest,
            target_test_ids=target_test_ids.target_test_ids,
            entries=entries,
        )
        return BaselineCheckPlanV1(
            schema_version=1,
            check_plan_version=manifest.check_plan_version,
            adapter_version=ADAPTER_VERSION,
            python_version=manifest.python_version,
            pytest_version=manifest.pytest_version,
            report_plugin_version=manifest.report_plugin_version,
            ruff_version=manifest.ruff_version,
            mypy_version=manifest.mypy_version,
            docker_image_digest=manifest.docker_image_digest,
            docker_execution_profile_version=execution_profile_version,
            reference_profile_digest=static_profile.reference_profile_digest,
            snapshot_root_digest=static_profile.snapshot_root_digest,
            repository_policy_digest=static_profile.repository_policy_digest,
            target_test_ids=target_test_ids,
            entries=entries,
            digest=digest,
        )

    def _require_exact_target_ids(
        self, target_test_ids: tuple[str, ...]
    ) -> TargetTestIdSequenceV1:
        """One closed target-id validation channel for plan construction.

        Every constraint of ``TargetTestIdSequenceV1`` (1..20 unique,
        non-empty, at most 1024 UTF-8 bytes) is proven here with the
        adapter's closed ``CheckPlanError`` channel, so construction can
        never escape a raw schema error after the check.
        """
        if not target_test_ids:
            raise CheckPlanError("TARGET_IDS_INVALID", "target ids must not be empty")
        if len(target_test_ids) > 20:
            raise CheckPlanError("TARGET_IDS_INVALID", "target ids must be at most 20")
        if len(target_test_ids) != len(set(target_test_ids)):
            raise CheckPlanError("TARGET_IDS_INVALID", "target ids must be unique")
        for node_id in target_test_ids:
            if node_id == "":
                raise CheckPlanError(
                    "TARGET_IDS_INVALID", "target ids must be non-empty"
                )
            if len(node_id.encode("utf-8")) > 1024:
                raise CheckPlanError(
                    "TARGET_IDS_INVALID",
                    "target ids must be at most 1024 UTF-8 bytes",
                )
        return TargetTestIdSequenceV1(target_test_ids=tuple(target_test_ids))

    def build_formal_plan(
        self,
        manifest: ValidationManifestV1,
        candidate: CandidateIdentityV1,
    ) -> FormalValidationCheckPlanV1:
        """Freeze the one closed formal-validation plan from manifest and
        candidate identities.

        Every binding digest must be well-formed, the manifest must bind
        the adapter's frozen reference profile (profile, tool, image, and
        execution identities exactly), and the candidate's Snapshot
        identity must equal the manifest's — any mismatch rejects closed
        before any plan exists (SPEC §4.5/§7 identity chain).
        """
        for name, value in (
            ("manifest digest", manifest.digest),
            ("reference profile digest", manifest.reference_profile_digest),
            ("snapshot tree digest", manifest.snapshot_tree_digest),
            ("repository policy digest", manifest.repository_policy_digest),
            ("docker image digest", manifest.docker_image_digest),
            ("candidate digest", candidate.digest),
            ("candidate tree digest", candidate.candidate_tree_digest),
            ("final diff digest", candidate.final_diff_digest),
            ("candidate snapshot tree digest", candidate.snapshot_tree_digest),
        ):
            if _DIGEST_RE.fullmatch(value) is None:
                raise CheckPlanError(
                    "BINDING_DIGEST_MALFORMED",
                    f"{name} must be exactly 64 lowercase hexadecimal characters",
                )
        if manifest.reference_profile_digest != self._reference_manifest.digest:
            raise CheckPlanError(
                "PROFILE_BINDING_MISMATCH",
                "the manifest does not bind the adapter's frozen manifest",
            )
        if not isinstance(manifest.docker_execution_profile_version, int) or (
            isinstance(manifest.docker_execution_profile_version, bool)
        ):
            raise CheckPlanError(
                "PROFILE_FIELD_MISMATCH",
                "docker execution profile version must be the decimal integer 1",
            )
        if (
            manifest.check_plan_version,
            manifest.adapter_version,
            manifest.python_version,
            manifest.pytest_version,
            manifest.report_plugin_version,
            manifest.ruff_version,
            manifest.mypy_version,
            manifest.docker_image_digest,
            manifest.docker_execution_profile_version,
        ) != (
            self._reference_manifest.check_plan_version,
            ADAPTER_VERSION,
            self._reference_manifest.python_version,
            self._reference_manifest.pytest_version,
            self._reference_manifest.report_plugin_version,
            self._reference_manifest.ruff_version,
            self._reference_manifest.mypy_version,
            self._reference_manifest.docker_image_digest,
            self._reference_manifest.docker_execution_profile_version,
        ):
            raise CheckPlanError(
                "PROFILE_FIELD_MISMATCH",
                "manifest tool/image/execution fields must exactly match the "
                "frozen reference profile",
            )
        # After the exact identity checks above the manifest's execution
        # profile version is proven to equal the frozen profile v1, so the
        # closed plan pins the exact literal.
        execution_profile_version: Literal[1] = cast(
            Literal[1], manifest.docker_execution_profile_version
        )
        if manifest.snapshot_tree_digest != candidate.snapshot_tree_digest:
            raise CheckPlanError(
                "SNAPSHOT_IDENTITY_MISMATCH",
                "candidate and manifest must bind the same Snapshot identity",
            )
        target_ids = self._require_exact_target_ids(manifest.target_test_ids)
        entries = (
            _formal_entry("COLLECT_ONLY", _collect_only_argv()),
            _formal_entry("FULL_PYTEST", _full_pytest_argv()),
            _formal_entry("RUFF", _ruff_argv()),
            _formal_entry("MYPY", _mypy_argv()),
        )
        digest = _compute_formal_plan_digest(
            check_plan_version=manifest.check_plan_version,
            adapter_version=manifest.adapter_version,
            python_version=manifest.python_version,
            pytest_version=manifest.pytest_version,
            report_plugin_version=manifest.report_plugin_version,
            ruff_version=manifest.ruff_version,
            mypy_version=manifest.mypy_version,
            docker_image_digest=manifest.docker_image_digest,
            docker_execution_profile_version=execution_profile_version,
            reference_profile_digest=manifest.reference_profile_digest,
            snapshot_tree_digest=manifest.snapshot_tree_digest,
            repository_policy_digest=manifest.repository_policy_digest,
            manifest_digest=manifest.digest,
            candidate_digest=candidate.digest,
            candidate_tree_digest=candidate.candidate_tree_digest,
            final_diff_digest=candidate.final_diff_digest,
            target_test_ids=target_ids.target_test_ids,
            entries=entries,
        )
        return FormalValidationCheckPlanV1(
            schema_version=1,
            check_plan_version=manifest.check_plan_version,
            adapter_version=manifest.adapter_version,
            python_version=manifest.python_version,
            pytest_version=manifest.pytest_version,
            report_plugin_version=manifest.report_plugin_version,
            ruff_version=manifest.ruff_version,
            mypy_version=manifest.mypy_version,
            docker_image_digest=manifest.docker_image_digest,
            docker_execution_profile_version=execution_profile_version,
            reference_profile_digest=manifest.reference_profile_digest,
            snapshot_tree_digest=manifest.snapshot_tree_digest,
            repository_policy_digest=manifest.repository_policy_digest,
            manifest_digest=manifest.digest,
            candidate_digest=candidate.digest,
            candidate_tree_digest=candidate.candidate_tree_digest,
            final_diff_digest=candidate.final_diff_digest,
            target_test_ids=target_ids,
            entries=entries,
            digest=digest,
        )

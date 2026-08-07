"""T20.2 legacy step 20.B: ``ValidationManifestV1`` publication.

``create_validation_manifest`` publishes the single immutable
``ValidationManifestV1`` from one ``PassingBaselineV1`` (which exists only
when every Baseline predicate held) and the caller's closed
``ManifestBindingsV1`` (SPEC §4.5).  The manifest is the closed record of
the stable baseline: sorted exact target ids, the ordered collection, the
per-test records with exactly the target ``CALL``/``FAIL`` fingerprints,
the authoritative evidence digests, the frozen profile/tool/image
identities, and the environment/resource/protected-artifact bindings —
all re-verified and self-bound into one §0.1 digest at construction, so a
manifest with any drifted or missing binding can never exist (GREEN-2).
"""

from __future__ import annotations

from typing import Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    StrictStr,
    field_validator,
    model_validator,
)

from vespercode.canonical.digest import domain_digest
from vespercode.canonical.json_v1 import CanonicalValueV1
from vespercode.contracts.evidence import _DIGEST_RE
from vespercode.contracts.optional import PresentV1
from vespercode.validation.baseline import (
    BaselineTestRecordV1,
    PassingBaselineV1,
    compute_environment_whitelist_digest,
    compute_resource_parameters_digest,
)


ManifestErrorCodeV1 = Literal["BINDING_MISMATCH"]
"""Closed Manifest publication rejection (SPEC §4.5 fail-closed).

Manifest invariant violations (unsorted orders, target fingerprint
presence, digest self-binding) are rejected by the closed manifest model
itself with a pydantic ``ValidationError``; the sole closed
``ManifestError`` channel is the drifted environment binding.
"""


class ManifestError(Exception):
    """One closed publication rejection; no Manifest exists after a raise."""

    def __init__(self, error_code: ManifestErrorCodeV1, reason: str) -> None:
        super().__init__(f"{error_code}: {reason}")
        self.error_code = error_code
        self.reason = reason


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


class ManifestBindingsV1(BaseModel):
    """The caller-supplied environment bindings of one Manifest.

    ``resource_parameters_digest`` and ``environment_whitelist_digest``
    are the §0.1 identities of the frozen execution-profile resources and
    environment whitelist; ``create_validation_manifest`` re-verifies
    both against the frozen profile, so an environment that no longer
    matches the built-in profile can never publish a Manifest.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal[1]
    resource_parameters_digest: StrictStr
    environment_whitelist_digest: StrictStr

    @field_validator("schema_version", mode="before")
    @classmethod
    def _schema_version_is_exact_int(cls, value: object) -> object:
        return _reject_coerced_schema_version(value)

    @field_validator("resource_parameters_digest", "environment_whitelist_digest")
    @classmethod
    def _digests_have_exact_form(cls, value: str) -> str:
        return _require_digest_form(value)


class ValidationManifestV1(BaseModel):
    """The immutable published baseline record (SPEC §4.5).

    All fields are required and unknown fields reject; the target ids are
    sorted exact node IDs, the records are sorted by node id and cover
    exactly the collection, exactly the target records carry a PRESENT
    ``CALL``/``FAIL`` fingerprint, and ``digest`` is the §0.1 identity of
    every other field, re-bound at construction.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal[1]
    target_test_ids: tuple[StrictStr, ...]
    collected_node_ids: tuple[StrictStr, ...]
    baseline_test_records: tuple[BaselineTestRecordV1, ...]
    protected_artifact_set_digest: StrictStr
    reference_profile_digest: StrictStr
    check_plan_version: StrictStr
    adapter_version: StrictStr
    python_version: StrictStr
    pytest_version: StrictStr
    report_plugin_version: StrictStr
    ruff_version: StrictStr
    mypy_version: StrictStr
    collect_only_evidence_digests: tuple[StrictStr, StrictStr]
    full_pytest_evidence_digest: StrictStr
    target_rerun_evidence_digest: StrictStr
    ruff_result_digest: StrictStr
    mypy_result_digest: StrictStr
    docker_image_digest: StrictStr
    docker_execution_profile_version: Literal[1]
    resource_parameters_digest: StrictStr
    environment_whitelist_digest: StrictStr
    repository_policy_digest: StrictStr
    snapshot_tree_digest: StrictStr
    digest: StrictStr

    @field_validator(
        "schema_version", "docker_execution_profile_version", mode="before"
    )
    @classmethod
    def _versions_are_exact_int_one(cls, value: object) -> object:
        return _reject_coerced_schema_version(value)

    @field_validator(
        "protected_artifact_set_digest",
        "reference_profile_digest",
        "full_pytest_evidence_digest",
        "target_rerun_evidence_digest",
        "ruff_result_digest",
        "mypy_result_digest",
        "docker_image_digest",
        "resource_parameters_digest",
        "environment_whitelist_digest",
        "repository_policy_digest",
        "snapshot_tree_digest",
        "digest",
    )
    @classmethod
    def _digests_have_exact_form(cls, value: str) -> str:
        return _require_digest_form(value)

    @field_validator("collect_only_evidence_digests")
    @classmethod
    def _collect_only_digests_are_exactly_two(
        cls, value: tuple[str, str]
    ) -> tuple[str, str]:
        if len(value) != 2:
            raise ValueError(
                "collect-only evidence digests must be exactly two in "
                "execution ordinal order"
            )
        for digest in value:
            _require_digest_form(digest)
        return value

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
    def _version_fields_are_non_empty(cls, value: str) -> str:
        if value == "":
            raise ValueError("version fields must be non-empty")
        return value

    @field_validator("target_test_ids", "collected_node_ids")
    @classmethod
    def _node_id_lists_are_non_empty(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if not value or any(node_id == "" for node_id in value):
            raise ValueError("target and collected node ids must be non-empty")
        return value

    @model_validator(mode="after")
    def _require_closed_manifest_invariants(self) -> ValidationManifestV1:
        target_set = set(self.target_test_ids)
        if len(target_set) != len(self.target_test_ids):
            raise ValueError("target test ids must be unique")
        if self.target_test_ids != tuple(sorted(self.target_test_ids)):
            raise ValueError("target test ids must be sorted exact node IDs")
        if not target_set.issubset(set(self.collected_node_ids)):
            raise ValueError("target test ids must be members of the collection")
        record_ids = tuple(record.node_id for record in self.baseline_test_records)
        if len(set(record_ids)) != len(record_ids):
            raise ValueError("baseline test records must be unique per node id")
        if record_ids != tuple(sorted(record_ids)):
            raise ValueError("baseline test records must be sorted by node id")
        if set(record_ids) != set(self.collected_node_ids):
            raise ValueError(
                "baseline test records must cover exactly the collected node ids"
            )
        for record in self.baseline_test_records:
            if record.node_id in target_set:
                if record.status != "FAIL" or not isinstance(
                    record.failure_fingerprint_digest, PresentV1
                ):
                    raise ValueError(
                        "target records must be CALL/FAIL with a PRESENT "
                        "failure fingerprint digest"
                    )
            elif isinstance(record.failure_fingerprint_digest, PresentV1):
                raise ValueError(
                    "only target records may carry a failure fingerprint digest"
                )
        return self

    @model_validator(mode="after")
    def _digest_binds_every_other_field(self) -> ValidationManifestV1:
        if self.digest != validation_manifest_digest(self):
            raise ValueError("manifest digest does not bind the manifest fields")
        return self


def _record_document(record: BaselineTestRecordV1) -> dict[str, CanonicalValueV1]:
    """One record in the exact §0.1 document form."""
    if isinstance(record.error_phase, PresentV1):
        error_phase_document: CanonicalValueV1 = {
            "kind": "PRESENT",
            "value": record.error_phase.value,
        }
    else:
        error_phase_document = {"kind": "ABSENT"}
    if isinstance(record.failure_fingerprint_digest, PresentV1):
        fingerprint_document: CanonicalValueV1 = {
            "kind": "PRESENT",
            "value": record.failure_fingerprint_digest.value.value,
        }
    else:
        fingerprint_document = {"kind": "ABSENT"}
    return {
        "node_id": record.node_id,
        "status": record.status,
        "error_phase": error_phase_document,
        "failure_fingerprint_digest": fingerprint_document,
    }


def _manifest_digest_body(
    *,
    target_test_ids: tuple[str, ...],
    collected_node_ids: tuple[str, ...],
    baseline_test_records: tuple[BaselineTestRecordV1, ...],
    protected_artifact_set_digest: str,
    reference_profile_digest: str,
    check_plan_version: str,
    adapter_version: str,
    python_version: str,
    pytest_version: str,
    report_plugin_version: str,
    ruff_version: str,
    mypy_version: str,
    collect_only_evidence_digests: tuple[str, str],
    full_pytest_evidence_digest: str,
    target_rerun_evidence_digest: str,
    ruff_result_digest: str,
    mypy_result_digest: str,
    docker_image_digest: str,
    docker_execution_profile_version: int,
    resource_parameters_digest: str,
    environment_whitelist_digest: str,
    repository_policy_digest: str,
    snapshot_tree_digest: str,
) -> dict[str, CanonicalValueV1]:
    """The single §0.1 document-form body of the Manifest (no digest)."""
    return {
        "schema_version": 1,
        "target_test_ids": tuple(target_test_ids),
        "collected_node_ids": tuple(collected_node_ids),
        "baseline_test_records": tuple(
            _record_document(record) for record in baseline_test_records
        ),
        "protected_artifact_set_digest": protected_artifact_set_digest,
        "reference_profile_digest": reference_profile_digest,
        "check_plan_version": check_plan_version,
        "adapter_version": adapter_version,
        "python_version": python_version,
        "pytest_version": pytest_version,
        "report_plugin_version": report_plugin_version,
        "ruff_version": ruff_version,
        "mypy_version": mypy_version,
        "collect_only_evidence_digests": tuple(collect_only_evidence_digests),
        "full_pytest_evidence_digest": full_pytest_evidence_digest,
        "target_rerun_evidence_digest": target_rerun_evidence_digest,
        "ruff_result_digest": ruff_result_digest,
        "mypy_result_digest": mypy_result_digest,
        "docker_image_digest": docker_image_digest,
        "docker_execution_profile_version": docker_execution_profile_version,
        "resource_parameters_digest": resource_parameters_digest,
        "environment_whitelist_digest": environment_whitelist_digest,
        "repository_policy_digest": repository_policy_digest,
        "snapshot_tree_digest": snapshot_tree_digest,
    }


def validation_manifest_digest(manifest: ValidationManifestV1) -> str:
    """Recompute the §0.1 identity of every field except the digest."""
    return domain_digest(
        "ValidationManifestV1",
        1,
        _manifest_digest_body(
            target_test_ids=manifest.target_test_ids,
            collected_node_ids=manifest.collected_node_ids,
            baseline_test_records=manifest.baseline_test_records,
            protected_artifact_set_digest=manifest.protected_artifact_set_digest,
            reference_profile_digest=manifest.reference_profile_digest,
            check_plan_version=manifest.check_plan_version,
            adapter_version=manifest.adapter_version,
            python_version=manifest.python_version,
            pytest_version=manifest.pytest_version,
            report_plugin_version=manifest.report_plugin_version,
            ruff_version=manifest.ruff_version,
            mypy_version=manifest.mypy_version,
            collect_only_evidence_digests=manifest.collect_only_evidence_digests,
            full_pytest_evidence_digest=manifest.full_pytest_evidence_digest,
            target_rerun_evidence_digest=manifest.target_rerun_evidence_digest,
            ruff_result_digest=manifest.ruff_result_digest,
            mypy_result_digest=manifest.mypy_result_digest,
            docker_image_digest=manifest.docker_image_digest,
            docker_execution_profile_version=manifest.docker_execution_profile_version,
            resource_parameters_digest=manifest.resource_parameters_digest,
            environment_whitelist_digest=manifest.environment_whitelist_digest,
            repository_policy_digest=manifest.repository_policy_digest,
            snapshot_tree_digest=manifest.snapshot_tree_digest,
        ),
    )


def create_validation_manifest(
    baseline: PassingBaselineV1,
    bindings: ManifestBindingsV1,
) -> ValidationManifestV1:
    """Publish the one immutable Manifest of a passing Baseline.

    The environment bindings are re-verified against the frozen execution
    profile before any Manifest can exist (``BINDING_MISMATCH`` otherwise);
    the target ids are sorted into the manifest's canonical order; every
    other field is projected verbatim from the baseline's closed evidence.
    The manifest model re-validates every closed invariant and re-binds
    the §0.1 digest (a pydantic ``ValidationError`` propagates for any
    invariant violation, so no Manifest can ever exist with drifted
    bindings).
    """
    if bindings.resource_parameters_digest != compute_resource_parameters_digest():
        raise ManifestError(
            "BINDING_MISMATCH",
            "resource parameters digest does not bind the frozen execution profile",
        )
    if bindings.environment_whitelist_digest != compute_environment_whitelist_digest():
        raise ManifestError(
            "BINDING_MISMATCH",
            "environment whitelist digest does not bind the frozen execution profile",
        )
    target_ids = tuple(sorted(baseline.target_test_ids))
    digest = domain_digest(
        "ValidationManifestV1",
        1,
        _manifest_digest_body(
            target_test_ids=target_ids,
            collected_node_ids=baseline.collected_node_ids,
            baseline_test_records=baseline.baseline_test_records,
            protected_artifact_set_digest=baseline.protected_artifact_set_digest,
            reference_profile_digest=baseline.reference_profile_digest,
            check_plan_version=baseline.check_plan_version,
            adapter_version=baseline.adapter_version,
            python_version=baseline.python_version,
            pytest_version=baseline.pytest_version,
            report_plugin_version=baseline.report_plugin_version,
            ruff_version=baseline.ruff_version,
            mypy_version=baseline.mypy_version,
            collect_only_evidence_digests=baseline.collect_only_evidence_digests,
            full_pytest_evidence_digest=baseline.full_pytest_evidence_digest,
            target_rerun_evidence_digest=baseline.target_rerun_evidence_digest,
            ruff_result_digest=baseline.ruff_result_digest,
            mypy_result_digest=baseline.mypy_result_digest,
            docker_image_digest=baseline.docker_image_digest,
            docker_execution_profile_version=baseline.docker_execution_profile_version,
            resource_parameters_digest=bindings.resource_parameters_digest,
            environment_whitelist_digest=bindings.environment_whitelist_digest,
            repository_policy_digest=baseline.repository_policy_digest,
            snapshot_tree_digest=baseline.snapshot_root_digest,
        ),
    )
    return ValidationManifestV1(
        schema_version=1,
        target_test_ids=target_ids,
        collected_node_ids=baseline.collected_node_ids,
        baseline_test_records=baseline.baseline_test_records,
        protected_artifact_set_digest=baseline.protected_artifact_set_digest,
        reference_profile_digest=baseline.reference_profile_digest,
        check_plan_version=baseline.check_plan_version,
        adapter_version=baseline.adapter_version,
        python_version=baseline.python_version,
        pytest_version=baseline.pytest_version,
        report_plugin_version=baseline.report_plugin_version,
        ruff_version=baseline.ruff_version,
        mypy_version=baseline.mypy_version,
        collect_only_evidence_digests=baseline.collect_only_evidence_digests,
        full_pytest_evidence_digest=baseline.full_pytest_evidence_digest,
        target_rerun_evidence_digest=baseline.target_rerun_evidence_digest,
        ruff_result_digest=baseline.ruff_result_digest,
        mypy_result_digest=baseline.mypy_result_digest,
        docker_image_digest=baseline.docker_image_digest,
        docker_execution_profile_version=baseline.docker_execution_profile_version,
        resource_parameters_digest=bindings.resource_parameters_digest,
        environment_whitelist_digest=bindings.environment_whitelist_digest,
        repository_policy_digest=baseline.repository_policy_digest,
        snapshot_tree_digest=baseline.snapshot_root_digest,
        digest=digest,
    )

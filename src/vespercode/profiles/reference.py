"""T06.2 legacy step 6.B: reference profile manifest integrity.

``ReferenceProfileManifestV1`` is the packaged production manifest of SPEC
§1.4.1.  ``load_reference_profile`` loads its bytes through a closed schema
and verifies the manifest against the frozen Task 2.G gate identities for
image, lock, tools, execution, and check plan: every missing, extra,
malformed, or drifted identity rejects deterministically without mutating
gate evidence or packaged bytes.  The gate identity set is embedded here as
the immutable §1.4.1 identity of the T02.4 frozen manifest
(``reference/manifest/reference-profile-v1.json``), so the packaged bytes
can never silently drift from the evidence that produced the GO decision.
Image builds, editable policy, endpoints, and gate-evidence mutation
remain out of scope (GREEN-4).
"""

from __future__ import annotations

import json
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Strict, StrictStr, field_validator

from vespercode.canonical.digest import domain_digest
from vespercode.canonical.json_v1 import CanonicalValueV1
from vespercode.canonical.path_v1 import CanonicalRelativePathV1
from vespercode.contracts.evidence import _DIGEST_RE
from vespercode.profiles.editable import (
    EditablePathPolicyV1,
    _reject_coerced_schema_version,
)

IntegrityErrorCodeV1 = Literal[
    "MANIFEST_DIGEST_MISMATCH",
    "POLICY_DIGEST_MISMATCH",
    "PROFILE_ID_MISMATCH",
    "REQUIREMENTS_DIGEST_MISMATCH",
    "IMAGE_DIGEST_MISMATCH",
    "TOOL_VERSION_MISMATCH",
    "PROFILE_VERSION_MISMATCH",
    "EXECUTION_PROFILE_VERSION_MISMATCH",
]


class ProfileIntegrityError(ValueError):
    """One closed identity failure; the stable code prefixes the message."""

    def __init__(self, error_code: IntegrityErrorCodeV1, value: str) -> None:
        super().__init__(f"{error_code}: {value}")
        self.error_code = error_code


def _require_digest_form(value: str) -> str:
    """Reject any spelling that is not exactly 64 lowercase hex chars."""
    if _DIGEST_RE.fullmatch(value) is None:
        raise ValueError("must be exactly 64 lowercase hexadecimal characters")
    return value


class ReferenceProfileManifestV1(BaseModel):
    """The packaged production profile manifest (SPEC §1.4.1).

    Every field is required and unknown fields reject; the digest is the
    §0.1 identity of every field except itself, and the nested
    ``editable_path_policy`` is the sole built-in record of T06.1, so a
    drifted or non-built-in policy rejects before the manifest exists.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal[1]
    profile_id: StrictStr
    requirements_lock_digest: StrictStr
    docker_image_digest: StrictStr
    docker_execution_profile_version: Annotated[int, Strict()]
    python_version: StrictStr
    pytest_version: StrictStr
    report_plugin_version: StrictStr
    ruff_version: StrictStr
    mypy_version: StrictStr
    check_plan_version: StrictStr
    editable_path_policy: EditablePathPolicyV1
    digest: StrictStr

    @field_validator("schema_version", mode="before")
    @classmethod
    def _schema_version_is_exact_int(cls, value: object) -> object:
        return _reject_coerced_schema_version(value)

    @field_validator("editable_path_policy", mode="before")
    @classmethod
    def _coerce_policy_roots(cls, value: object) -> object:
        """Accept the published JSON ``["src"]`` string form for roots.

        Each string is validated through ``CanonicalRelativePathV1``, so a
        noncanonical root in the packaged bytes rejects before any digest
        acceptance; the editable-policy contract itself then enforces the
        sole built-in record.
        """
        if isinstance(value, dict) and isinstance(
            value.get("editable_directory_roots"), list
        ):
            return {
                **value,
                "editable_directory_roots": [
                    CanonicalRelativePathV1(item) if isinstance(item, str) else item
                    for item in value["editable_directory_roots"]
                ],
            }
        return value

    @field_validator("requirements_lock_digest", "docker_image_digest", "digest")
    @classmethod
    def _manifest_digests_have_exact_form(cls, value: str) -> str:
        return _require_digest_form(value)

    def verify_integrity(self, gate_manifest: GateReferenceProfileManifestV1) -> None:
        """Verify this manifest against the Task 2.G gate identities.

        The manifest's own §0.1 identity is checked first, then every gate
        identity (profile id, lock, image, tools, check plan, execution
        profile, editable policy) must match exactly; the first drifted
        identity raises its closed ``ProfileIntegrityError`` code and
        nothing is ever mutated.
        """
        if self.digest != _compute_manifest_digest(self):
            raise ProfileIntegrityError(
                "MANIFEST_DIGEST_MISMATCH",
                "manifest digest no longer binds every other field",
            )
        if self.profile_id != gate_manifest.profile_id:
            raise ProfileIntegrityError(
                "PROFILE_ID_MISMATCH", "profile id drifted from the gate identity"
            )
        if self.requirements_lock_digest != gate_manifest.requirements_lock_digest:
            raise ProfileIntegrityError(
                "REQUIREMENTS_DIGEST_MISMATCH",
                "requirements lock digest drifted from the gate identity",
            )
        if self.docker_image_digest != gate_manifest.docker_image_digest:
            raise ProfileIntegrityError(
                "IMAGE_DIGEST_MISMATCH",
                "docker image digest drifted from the gate identity",
            )
        if (
            self.python_version,
            self.pytest_version,
            self.ruff_version,
            self.mypy_version,
        ) != (
            gate_manifest.python_version,
            gate_manifest.pytest_version,
            gate_manifest.ruff_version,
            gate_manifest.mypy_version,
        ):
            raise ProfileIntegrityError(
                "TOOL_VERSION_MISMATCH", "tool versions drifted from the gate identity"
            )
        if (
            self.report_plugin_version,
            self.check_plan_version,
        ) != (
            gate_manifest.report_plugin_version,
            gate_manifest.check_plan_version,
        ):
            raise ProfileIntegrityError(
                "PROFILE_VERSION_MISMATCH",
                "report plugin or check plan version drifted from the gate identity",
            )
        if (
            self.docker_execution_profile_version
            != gate_manifest.docker_execution_profile_version
        ):
            raise ProfileIntegrityError(
                "EXECUTION_PROFILE_VERSION_MISMATCH",
                "docker execution profile version drifted from the gate identity",
            )
        if (
            self.editable_path_policy.digest
            != gate_manifest.editable_path_policy_digest
        ):
            raise ProfileIntegrityError(
                "POLICY_DIGEST_MISMATCH",
                "editable policy digest drifted from the gate identity",
            )


class GateReferenceProfileManifestV1(BaseModel):
    """The frozen Task 2.G gate manifest identity record.

    Carries exactly the §1.4.1 identity fields the gate froze — image,
    lock, tools, check plan, execution profile, and editable policy digest
    — so a production manifest can be verified against the evidence that
    produced the GO decision.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal[1]
    profile_id: StrictStr
    requirements_lock_digest: StrictStr
    docker_image_digest: StrictStr
    docker_execution_profile_version: Annotated[int, Strict()]
    python_version: StrictStr
    pytest_version: StrictStr
    report_plugin_version: StrictStr
    ruff_version: StrictStr
    mypy_version: StrictStr
    check_plan_version: StrictStr
    editable_path_policy_digest: StrictStr

    @field_validator("schema_version", mode="before")
    @classmethod
    def _schema_version_is_exact_int(cls, value: object) -> object:
        return _reject_coerced_schema_version(value)

    @field_validator(
        "requirements_lock_digest", "docker_image_digest", "editable_path_policy_digest"
    )
    @classmethod
    def _gate_digests_have_exact_form(cls, value: str) -> str:
        return _require_digest_form(value)


# The exact frozen Task 2.G gate identity constants.  These are the §1.4.1
# identity fields of reference/manifest/reference-profile-v1.json frozen by
# T02.4 (implementation commit 55483b6) — image, lock, tools, check plan,
# execution profile, and the editable policy digest.
_GATE_PROFILE_ID = "python-src-py312-v1"
_GATE_REQUIREMENTS_LOCK_DIGEST = (
    "b3352321735739e66d89522c49645243d698d1e1f14c487ebc36b2d9dda5281a"
)
_GATE_DOCKER_IMAGE_DIGEST = (
    "385ffc69d83536e1874d73517b8b9ee2a0dce6166ca0f30c1f3b1021324ea1a8"
)
_GATE_PYTHON_VERSION = "3.12.4"
_GATE_PYTEST_VERSION = "8.4.2"
_GATE_RUFF_VERSION = "0.16.1"
_GATE_MYPY_VERSION = "2.3.0"
_GATE_REPORT_PLUGIN_VERSION = "1"
_GATE_CHECK_PLAN_VERSION = "1"
_GATE_POLICY_DIGEST = "b857afca63e50a888ee183bd7ac8c7f739be7b60a94fc4f9c55c0a606db144ab"

_GATE_MANIFEST = GateReferenceProfileManifestV1(
    schema_version=1,
    profile_id=_GATE_PROFILE_ID,
    requirements_lock_digest=_GATE_REQUIREMENTS_LOCK_DIGEST,
    docker_image_digest=_GATE_DOCKER_IMAGE_DIGEST,
    docker_execution_profile_version=1,
    python_version=_GATE_PYTHON_VERSION,
    pytest_version=_GATE_PYTEST_VERSION,
    report_plugin_version=_GATE_REPORT_PLUGIN_VERSION,
    ruff_version=_GATE_RUFF_VERSION,
    mypy_version=_GATE_MYPY_VERSION,
    check_plan_version=_GATE_CHECK_PLAN_VERSION,
    editable_path_policy_digest=_GATE_POLICY_DIGEST,
)


def _manifest_body(manifest: ReferenceProfileManifestV1) -> dict[str, CanonicalValueV1]:
    """The canonical digest value body: every exact field except the digest."""
    policy = manifest.editable_path_policy
    return {
        "schema_version": manifest.schema_version,
        "profile_id": manifest.profile_id,
        "requirements_lock_digest": manifest.requirements_lock_digest,
        "docker_image_digest": manifest.docker_image_digest,
        "docker_execution_profile_version": manifest.docker_execution_profile_version,
        "python_version": manifest.python_version,
        "pytest_version": manifest.pytest_version,
        "report_plugin_version": manifest.report_plugin_version,
        "ruff_version": manifest.ruff_version,
        "mypy_version": manifest.mypy_version,
        "check_plan_version": manifest.check_plan_version,
        "editable_path_policy": {
            "schema_version": policy.schema_version,
            "policy_id": policy.policy_id,
            "editable_directory_roots": tuple(
                root.value for root in policy.editable_directory_roots
            ),
            "allowed_operations": policy.allowed_operations,
            "digest": policy.digest,
        },
    }


def _compute_manifest_digest(manifest: ReferenceProfileManifestV1) -> str:
    """The §0.1 identity of every exact manifest field except the digest."""
    return domain_digest(
        "ReferenceProfileManifestV1",
        manifest.schema_version,
        _manifest_body(manifest),
    )


def load_reference_profile(raw: bytes) -> ReferenceProfileManifestV1:
    """Load packaged production manifest bytes and verify their integrity.

    The input must be UTF-8 JSON of exactly the §1.4.1 fields; missing,
    extra, malformed, or drifted fields reject deterministically.  The
    manifest's own digest is checked first, then every frozen Task 2.G
    gate identity — no gate evidence or packaged byte is ever mutated.
    """
    try:
        obj = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("reference profile manifest must be valid UTF-8 JSON") from exc
    manifest = ReferenceProfileManifestV1.model_validate(obj)
    manifest.verify_integrity(_GATE_MANIFEST)
    return manifest

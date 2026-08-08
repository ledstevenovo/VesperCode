"""T06.2 legacy step 6.B: reference profile manifest integrity tests.

The packaged production manifest loads and verifies against the frozen
Task 2.G gate identities for image, lock, tools, execution, and check
plan; every missing, extra, malformed, or drifted identity rejects
without mutating gate evidence or packaged bytes (GREEN-2).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

# The manifest is a pydantic runtime contract; the hash-locked gate
# toolchain does not install runtime dependencies, so this module skips
# cleanly there instead of failing at collection (formal env runs it fully).
pytest.importorskip("pydantic")

from pydantic import ValidationError

from vespercode.canonical.digest import domain_digest
from vespercode.canonical.json_v1 import CanonicalValueV1
from vespercode.profiles.reference import (
    GateReferenceProfileManifestV1,
    ProfileIntegrityError,
    load_reference_profile,
)

# The §0.1 identities of the frozen T02.4 manifest (SPEC §1.4.1),
# independently recomputed by both review stages.
_MANIFEST_DIGEST = "841e9d55359c4007cd53b4b50a2ff10572b955650847bfb545ea2f4aa661443b"
_POLICY_DIGEST = "b857afca63e50a888ee183bd7ac8c7f739be7b60a94fc4f9c55c0a606db144ab"
_REQUIREMENTS_LOCK_DIGEST = (
    "67a6b630fb418344bea58ed0b98c1006391bbc947b36356188a1e01fa5fe9a64"
)
_DOCKER_IMAGE_DIGEST = (
    "71e931b58316637d1cbe647a57fc4c3588837f9451f7fbad391c34b3b1b43905"
)

# The frozen Task 2.G gate identity constants (the §1.4.1 identity set of
# reference/manifest/reference-profile-v1.json).
_GATE_POLICY: dict[str, object] = {
    "schema_version": 1,
    "policy_id": "PYTHON_SRC_ONLY_V1",
    "editable_directory_roots": ["src"],
    "allowed_operations": ["CREATE", "REPLACE"],
    "digest": _POLICY_DIGEST,
}


def packaged_reference_profile_bytes() -> bytes:
    """The packaged production manifest bytes (the frozen GO identity)."""
    path = (
        Path(__file__).resolve().parents[3]
        / "src"
        / "vespercode"
        / "profiles"
        / "builtin"
        / "reference-profile-v1.json"
    )
    return path.read_bytes()


def gate_manifest() -> GateReferenceProfileManifestV1:
    """The exact frozen Task 2.G gate manifest identity record."""
    return GateReferenceProfileManifestV1(
        schema_version=1,
        profile_id="python-src-py312-v1",
        requirements_lock_digest=_REQUIREMENTS_LOCK_DIGEST,
        docker_image_digest=_DOCKER_IMAGE_DIGEST,
        docker_execution_profile_version=1,
        python_version="3.12.4",
        pytest_version="8.4.2",
        report_plugin_version="1",
        ruff_version="0.16.1",
        mypy_version="2.3.0",
        check_plan_version="1",
        editable_path_policy_digest=_POLICY_DIGEST,
    )


def _manifest_body(**drifted_fields: object) -> dict[str, object]:
    """The exact §0.1 manifest value body, optionally with drifted fields."""
    body: dict[str, object] = {
        "schema_version": 1,
        "profile_id": "python-src-py312-v1",
        "requirements_lock_digest": _REQUIREMENTS_LOCK_DIGEST,
        "docker_image_digest": _DOCKER_IMAGE_DIGEST,
        "docker_execution_profile_version": 1,
        "python_version": "3.12.4",
        "pytest_version": "8.4.2",
        "report_plugin_version": "1",
        "ruff_version": "0.16.1",
        "mypy_version": "2.3.0",
        "check_plan_version": "1",
        "editable_path_policy": dict(_GATE_POLICY),
    }
    body.update(drifted_fields)
    return body


def _canonical(value: object) -> CanonicalValueV1:
    """Normalize JSON lists to the canonical encoder's tuple arrays."""
    if isinstance(value, list):
        return tuple(_canonical(item) for item in value)
    if isinstance(value, dict):
        return {key: _canonical(item) for key, item in value.items()}
    return value  # type: ignore[return-value]  # JSON scalars are canonical


def _drifted_manifest_bytes(**drifted_fields: object) -> bytes:
    """Self-consistent drifted manifest bytes with the digest recomputed.

    Every identity drift recomputes the §0.1 digest exactly like a real
    attacker would, so the specific drifted identity is what rejects.
    """
    body = _manifest_body(**drifted_fields)
    canonical_body = _canonical(body)
    assert isinstance(canonical_body, dict)
    body["digest"] = domain_digest("ReferenceProfileManifestV1", 1, canonical_body)
    return json.dumps(body, sort_keys=True).encode("utf-8")


def _raw_drifted_manifest_bytes(**drifted_fields: object) -> bytes:
    """Drifted bytes with a stale digest for schema-level rejection rows.

    The manifest schema rejects these rows before any digest acceptance, so
    the digest value only needs to be form-valid, not self-consistent.
    """
    body = _manifest_body(**drifted_fields)
    body["digest"] = "00" * 32
    return json.dumps(body, sort_keys=True).encode("utf-8")


def drifted_image_digest_bytes() -> bytes:
    """The smallest image-identity mismatch with its digest recomputed."""
    return _drifted_manifest_bytes(docker_image_digest="dd" * 32)


def test_reference_profile_rejects_image_digest_drift() -> None:
    with pytest.raises(ProfileIntegrityError, match="IMAGE_DIGEST_MISMATCH"):
        load_reference_profile(drifted_image_digest_bytes())


def test_reference_profile_integrity_matrix() -> None:
    """Exact Task 2.G identities load; every missing, extra, malformed, or
    drifted identity rejects deterministically (Expected 6.B)."""
    packaged = packaged_reference_profile_bytes()
    manifest = load_reference_profile(packaged)
    assert manifest.digest == _MANIFEST_DIGEST
    assert manifest.editable_path_policy.digest == _POLICY_DIGEST
    assert manifest.schema_version == 1
    assert manifest.profile_id == "python-src-py312-v1"
    assert manifest.docker_execution_profile_version == 1
    assert manifest.requirements_lock_digest == _REQUIREMENTS_LOCK_DIGEST
    assert manifest.docker_image_digest == _DOCKER_IMAGE_DIGEST
    assert manifest.python_version == "3.12.4"
    assert manifest.pytest_version == "8.4.2"
    assert manifest.ruff_version == "0.16.1"
    assert manifest.mypy_version == "2.3.0"
    assert manifest.report_plugin_version == "1"
    assert manifest.check_plan_version == "1"
    # The production manifest verifies cleanly against the gate identity.
    manifest.verify_integrity(gate_manifest())
    assert load_reference_profile(packaged) == manifest
    # Missing, renamed, extra, malformed, and type-confused fields reject
    # at the schema.
    for bad_bytes in (
        json.dumps(
            {
                key: value
                for key, value in _manifest_body().items()
                if key != "docker_image_digest"
            },
            sort_keys=True,
        ).encode("utf-8"),
        _raw_drifted_manifest_bytes(extra_field=1),
        _raw_drifted_manifest_bytes(schema_version=2),
        _raw_drifted_manifest_bytes(schema_version=True),
        _raw_drifted_manifest_bytes(schema_version=1.0),
        _raw_drifted_manifest_bytes(schema_version="1"),
        _raw_drifted_manifest_bytes(docker_execution_profile_version=True),
        _raw_drifted_manifest_bytes(docker_execution_profile_version=1.0),
        _raw_drifted_manifest_bytes(docker_execution_profile_version="1"),
        _raw_drifted_manifest_bytes(docker_image_digest="x"),
        _raw_drifted_manifest_bytes(docker_image_digest="0" * 63),
        _raw_drifted_manifest_bytes(docker_image_digest="0" * 65),
        _raw_drifted_manifest_bytes(docker_image_digest="A" * 64),
        _raw_drifted_manifest_bytes(
            editable_path_policy={
                "schema_version": 1,
                "policy_id": "PYTHON_SRC_ONLY_V1",
                "editable_directory_roots": ["src", "tests"],
                "allowed_operations": ["CREATE", "REPLACE"],
                "digest": _POLICY_DIGEST,
            }
        ),
    ):
        with pytest.raises(ValidationError):
            load_reference_profile(bad_bytes)
    for non_object_bytes in (b"not json", b"[]", b"null", b"\xff\xfe"):
        with pytest.raises(ValueError):
            load_reference_profile(non_object_bytes)
    # Every drifted identity rejects with its closed integrity code.
    for drifted_bytes, code in (
        (drifted_image_digest_bytes(), "IMAGE_DIGEST_MISMATCH"),
        (
            _drifted_manifest_bytes(requirements_lock_digest="ee" * 32),
            "REQUIREMENTS_DIGEST_MISMATCH",
        ),
        (_drifted_manifest_bytes(pytest_version="9.0.0"), "TOOL_VERSION_MISMATCH"),
        (
            _drifted_manifest_bytes(report_plugin_version="2"),
            "PROFILE_VERSION_MISMATCH",
        ),
        (_drifted_manifest_bytes(check_plan_version="2"), "PROFILE_VERSION_MISMATCH"),
        (
            _drifted_manifest_bytes(docker_execution_profile_version=2),
            "EXECUTION_PROFILE_VERSION_MISMATCH",
        ),
        (_drifted_manifest_bytes(profile_id="other-v1"), "PROFILE_ID_MISMATCH"),
        (
            _drifted_manifest_bytes(
                editable_path_policy={
                    "schema_version": 1,
                    "policy_id": "PYTHON_SRC_ONLY_V1",
                    "editable_directory_roots": ["src"],
                    "allowed_operations": ["CREATE", "REPLACE"],
                    "digest": "11" * 32,
                }
            ),
            None,  # the editable policy closure rejects before integrity codes
        ),
    ):
        if code is None:
            with pytest.raises(ValidationError):
                load_reference_profile(drifted_bytes)
            continue
        with pytest.raises(ProfileIntegrityError, match=code):
            load_reference_profile(drifted_bytes)
    # A stale manifest digest rejects before any gate comparison.
    stale = json.loads(packaged)
    stale["digest"] = "00" * 32
    with pytest.raises(ProfileIntegrityError, match="MANIFEST_DIGEST_MISMATCH"):
        load_reference_profile(json.dumps(stale, sort_keys=True).encode("utf-8"))
    # verify_integrity against a drifted gate manifest raises its code.
    for gate_fields, code in (
        ({"docker_image_digest": "dd" * 32}, "IMAGE_DIGEST_MISMATCH"),
        (
            {"editable_path_policy_digest": "11" * 32},
            "POLICY_DIGEST_MISMATCH",
        ),
        (
            {"requirements_lock_digest": "ee" * 32},
            "REQUIREMENTS_DIGEST_MISMATCH",
        ),
        ({"pytest_version": "9.0.0"}, "TOOL_VERSION_MISMATCH"),
        ({"report_plugin_version": "2"}, "PROFILE_VERSION_MISMATCH"),
        ({"check_plan_version": "2"}, "PROFILE_VERSION_MISMATCH"),
        (
            {"docker_execution_profile_version": 2},
            "EXECUTION_PROFILE_VERSION_MISMATCH",
        ),
        ({"profile_id": "other-v1"}, "PROFILE_ID_MISMATCH"),
    ):
        gate = gate_manifest().model_copy(update=gate_fields)
        with pytest.raises(ProfileIntegrityError, match=code):
            manifest.verify_integrity(gate)
    # A gate manifest with missing or extra fields rejects at the schema.
    gate_dump = gate_manifest().model_dump()
    with pytest.raises(ValidationError):
        GateReferenceProfileManifestV1.model_validate(
            {
                key: value
                for key, value in gate_dump.items()
                if key != "docker_image_digest"
            }
        )
    with pytest.raises(ValidationError):
        GateReferenceProfileManifestV1.model_validate({**gate_dump, "extra_field": 1})
    # A stale manifest instance also fails verify_integrity's own digest check.
    stale_manifest = manifest.model_copy(update={"digest": "00" * 32})
    with pytest.raises(ProfileIntegrityError, match="MANIFEST_DIGEST_MISMATCH"):
        stale_manifest.verify_integrity(gate_manifest())

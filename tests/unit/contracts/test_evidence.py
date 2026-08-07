"""T05.1 legacy step 5.D: shared closed evidence/artifact/digest/location tests.

Every evidence variant binds its digest and location consistently and
rejects missing, unknown, mixed, or contradictory fields deterministically;
artifact creation, byte storage, audit append, and validation-outcome
interpretation remain out of scope (GREEN-4).
"""

from __future__ import annotations

import pytest

# The evidence models are pydantic runtime contracts; the hash-locked gate
# toolchain does not install runtime dependencies, so this module skips
# cleanly there instead of failing at collection (formal env runs it fully).
pytest.importorskip("pydantic")

from pydantic import TypeAdapter, ValidationError

from vespercode.contracts.evidence import (
    ArtifactRefV1,
    DigestV1,
    EvidenceEnvelopeV1,
    EvidenceLocationV1,
    OptionalArtifactRefV1,
    OptionalDigestV1,
    StableCodeSequenceV1,
    StableControlErrorV1,
)

_DIGEST = "a" * 64


def test_artifact_reference_rejects_unbound_digest() -> None:
    with pytest.raises(ValidationError):
        ArtifactRefV1.model_validate({"artifact_id": "a1", "digest": ""})


def test_evidence_reference_union_matrix() -> None:
    """SPEC §0.1/§4.2.2/§4.6 evidence-vocabulary matrix (Expected 5.D).

    Every legal evidence variant round-trips; every unbound, unknown,
    mixed, null, or contradictory row rejects deterministically.
    """
    # DigestV1: exactly 64 lowercase hex.
    assert DigestV1.model_validate({"value": _DIGEST}).value == _DIGEST
    for digest_payload in (
        {"value": ""},  # unbound digest (RED)
        {"value": "a" * 63},
        {"value": "a" * 65},
        {"value": "A" * 64},  # uppercase hex is not canonical
        {"value": "g" * 64},  # non-hex
        {},
        {"value": None},
        {"value": 42},
        {"value": _DIGEST, "extra": 1},  # unknown field
    ):
        with pytest.raises(ValidationError):
            DigestV1.model_validate(digest_payload)

    # ArtifactRefV1: artifact identity bound to one exact digest.
    artifact = {"artifact_id": "a1", "digest": {"value": _DIGEST}}
    assert ArtifactRefV1.model_validate(artifact).artifact_id == "a1"
    for artifact_payload in (
        {"artifact_id": "a1", "digest": ""},  # unbound digest (RED)
        {"artifact_id": "a1", "digest": {"value": ""}},
        {"artifact_id": "a1", "digest": {"value": "A" * 64}},
        {"artifact_id": "", "digest": {"value": _DIGEST}},  # empty identity
        {"artifact_id": "a1"},  # missing digest
        {"digest": {"value": _DIGEST}},  # missing artifact id
        {"artifact_id": None, "digest": {"value": _DIGEST}},
        {"artifact_id": "a1", "digest": {"value": _DIGEST}, "extra": 1},
    ):
        with pytest.raises(ValidationError):
            ArtifactRefV1.model_validate(artifact_payload)

    # EvidenceLocationV1: one closed storage location bound to its digest.
    location = {
        "kind": "LOCAL_ARTIFACT",
        "storage_path": "artifacts/a1.bin",
        "digest": {"value": _DIGEST},
    }
    assert (
        EvidenceLocationV1.model_validate(location).storage_path == "artifacts/a1.bin"
    )
    for location_payload in (
        {"kind": "REMOTE_URL", "storage_path": "s3://b", "digest": {"value": _DIGEST}},
        {"kind": "LOCAL_ARTIFACT", "digest": {"value": _DIGEST}},  # missing location
        {"kind": "LOCAL_ARTIFACT", "storage_path": "", "digest": {"value": _DIGEST}},
        {"kind": "LOCAL_ARTIFACT", "storage_path": "a.bin"},  # missing digest
        {"kind": "LOCAL_ARTIFACT", "storage_path": None, "digest": {"value": _DIGEST}},
        {
            "kind": "LOCAL_ARTIFACT",
            "storage_path": "a.bin",
            "digest": {"value": _DIGEST},
            "extra": 1,
        },
    ):
        with pytest.raises(ValidationError):
            EvidenceLocationV1.model_validate(location_payload)

    # StableControlErrorV1: closed stable error code and bounded message.
    error = {"error_code": "INTERNAL_ERROR", "bounded_message": "closed failure"}
    assert StableControlErrorV1.model_validate(error).error_code == "INTERNAL_ERROR"
    for error_payload in (
        {"bounded_message": "m"},  # missing error code
        {"error_code": "", "bounded_message": "m"},
        {"error_code": "E"},  # missing message
        {"error_code": "E", "bounded_message": ""},
        {"error_code": None, "bounded_message": "m"},
        {"error_code": "E", "bounded_message": "m", "extra": 1},
    ):
        with pytest.raises(ValidationError):
            StableControlErrorV1.model_validate(error_payload)

    # StableCodeSequenceV1: immutable ordered tuple of zero or more codes.
    assert StableCodeSequenceV1.model_validate({"codes": ()}).codes == ()
    ordered = StableCodeSequenceV1.model_validate({"codes": ("A", "B", "A")})
    assert ordered.codes == ("A", "B", "A")  # order preserved verbatim
    for sequence_payload in (
        {"codes": ("A", "")},  # empty code element
        {"codes": [""]},
        {},
        {"codes": (), "extra": 1},
        {"codes": None},
    ):
        with pytest.raises(ValidationError):
            StableCodeSequenceV1.model_validate(sequence_payload)

    # EvidenceEnvelopeV1: artifact and location must bind the same digest.
    envelope = {
        "schema_version": 1,
        "artifact_ref": artifact,
        "location": location,
    }
    valid = EvidenceEnvelopeV1.model_validate(envelope)
    assert valid.artifact_ref.digest == valid.location.digest
    for envelope_payload in (
        {
            "schema_version": 1,
            "artifact_ref": artifact,
            "location": {
                "kind": "LOCAL_ARTIFACT",
                "storage_path": "artifacts/a1.bin",
                "digest": {"value": "b" * 64},  # contradictory digest binding
            },
        },
        {"schema_version": 1, "location": location},  # missing artifact ref
        {"schema_version": 1, "artifact_ref": artifact},  # missing location
        {"artifact_ref": artifact, "location": location},  # missing schema version
        {"schema_version": 2, "artifact_ref": artifact, "location": location},
        {
            "schema_version": 1,
            "artifact_ref": artifact,
            "location": location,
            "extra": 1,
        },
    ):
        with pytest.raises(ValidationError):
            EvidenceEnvelopeV1.model_validate(envelope_payload)

    # Named optional unions over evidence values.
    artifact_adapter: TypeAdapter[OptionalArtifactRefV1] = TypeAdapter(
        OptionalArtifactRefV1
    )
    absent = artifact_adapter.validate_python({"kind": "ABSENT"})
    assert absent.kind == "ABSENT"
    present = artifact_adapter.validate_python({"kind": "PRESENT", "value": artifact})
    assert present.kind == "PRESENT"
    for optional_artifact_payload in (
        {"kind": "PRESENT"},  # missing value
        {"kind": "PRESENT", "value": {"artifact_id": "a1", "digest": {"value": ""}}},
        {"kind": "PRESENT", "value": None},
        {"kind": "ABSENT", "value": artifact},  # ABSENT carrying a value
        {"kind": "OTHER"},
    ):
        with pytest.raises(ValidationError):
            artifact_adapter.validate_python(optional_artifact_payload)
    digest_adapter: TypeAdapter[OptionalDigestV1] = TypeAdapter(OptionalDigestV1)
    assert digest_adapter.validate_python({"kind": "ABSENT"}).kind == "ABSENT"
    assert (
        digest_adapter.validate_python(
            {"kind": "PRESENT", "value": {"value": _DIGEST}}
        ).kind
        == "PRESENT"
    )
    for optional_digest_payload in (
        {"kind": "PRESENT", "value": {"value": "x"}},
        {"kind": "PRESENT"},
        {"kind": "OTHER"},
    ):
        with pytest.raises(ValidationError):
            digest_adapter.validate_python(optional_digest_payload)


def test_evidence_envelope_binds_digest_and_location() -> None:
    envelope = {
        "schema_version": 1,
        "artifact_ref": {"artifact_id": "a1", "digest": {"value": _DIGEST}},
        "location": {
            "kind": "LOCAL_ARTIFACT",
            "storage_path": "artifacts/a1.bin",
            "digest": {"value": _DIGEST},
        },
    }
    valid = EvidenceEnvelopeV1.model_validate(envelope)
    assert EvidenceEnvelopeV1.model_validate(valid.model_dump()) == valid
    contradictory: dict[str, object] = {
        "schema_version": 1,
        "artifact_ref": {"artifact_id": "a1", "digest": {"value": _DIGEST}},
        "location": {
            "kind": "LOCAL_ARTIFACT",
            "storage_path": "artifacts/a1.bin",
            "digest": {"value": "b" * 64},
        },
    }
    with pytest.raises(ValidationError):
        EvidenceEnvelopeV1.model_validate(contradictory)


def test_evidence_variants_round_trip() -> None:
    digest = DigestV1.model_validate({"value": _DIGEST})
    assert DigestV1.model_validate(digest.model_dump()) == digest
    artifact = ArtifactRefV1.model_validate(
        {"artifact_id": "a1", "digest": {"value": _DIGEST}}
    )
    assert ArtifactRefV1.model_validate(artifact.model_dump()) == artifact
    error = StableControlErrorV1.model_validate(
        {"error_code": "INTERNAL_ERROR", "bounded_message": "closed failure"}
    )
    assert StableControlErrorV1.model_validate(error.model_dump()) == error
    sequence = StableCodeSequenceV1.model_validate({"codes": ("A", "B")})
    assert StableCodeSequenceV1.model_validate(sequence.model_dump()) == sequence


def test_evidence_models_are_immutable() -> None:
    artifact = ArtifactRefV1.model_validate(
        {"artifact_id": "a1", "digest": {"value": _DIGEST}}
    )
    with pytest.raises(ValidationError):
        artifact.artifact_id = "a2"
    sequence = StableCodeSequenceV1.model_validate({"codes": ("A",)})
    with pytest.raises(ValidationError):
        sequence.codes = ("B",)

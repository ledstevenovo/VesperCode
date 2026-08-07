"""T05.1 legacy step 5.D: shared closed evidence/artifact/digest vocabulary.

Every artifact/evidence variant binds its digest and location consistently:
``DigestV1`` holds exactly one 64-lowercase-hex SHA-256 identity,
``ArtifactRefV1`` binds an artifact identity to its digest,
``EvidenceLocationV1`` binds a local storage location to the same digest,
``StableControlErrorV1`` is one closed stable control error,
``StableCodeSequenceV1`` is an immutable ordered tuple of zero or more
stable error codes, and ``EvidenceEnvelopeV1`` requires the artifact
reference and its location to describe the same bytes (missing, unknown,
mixed, or contradictory fields reject deterministically).  Artifact
creation, byte storage, audit append, and validation-outcome
interpretation remain out of scope (GREEN-4).
"""

from __future__ import annotations

import re
from typing import Annotated, Literal, TypeAlias

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictStr,
    field_validator,
    model_validator,
)

from vespercode.contracts.optional import AbsentV1, PresentV1

_DIGEST_RE = re.compile(r"[0-9a-f]{64}")


class DigestV1(BaseModel):
    """One exact 64-lowercase-hex SHA-256 binding identity (SPEC §0.1)."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    value: StrictStr

    @field_validator("value")
    @classmethod
    def _require_sha256_hex(cls, value: str) -> str:
        if _DIGEST_RE.fullmatch(value) is None:
            raise ValueError(
                "digest must be exactly 64 lowercase hexadecimal characters"
            )
        return value


class ArtifactRefV1(BaseModel):
    """An artifact identity bound to exactly one digest (SPEC §4.2.2)."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    artifact_id: StrictStr
    digest: DigestV1

    @field_validator("artifact_id")
    @classmethod
    def _artifact_id_must_be_non_empty(cls, value: str) -> str:
        if value == "":
            raise ValueError("artifact_id must be non-empty")
        return value


class EvidenceLocationV1(BaseModel):
    """One closed local-artifact storage location bound to its digest."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    kind: Literal["LOCAL_ARTIFACT"]
    storage_path: StrictStr
    digest: DigestV1

    @field_validator("storage_path")
    @classmethod
    def _storage_path_must_be_non_empty(cls, value: str) -> str:
        if value == "":
            raise ValueError("storage_path must be non-empty")
        return value


class StableControlErrorV1(BaseModel):
    """One closed stable control error: code plus bounded message."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    error_code: StrictStr
    bounded_message: StrictStr

    @field_validator("error_code", "bounded_message")
    @classmethod
    def _no_empty_values(cls, value: str) -> str:
        if value == "":
            raise ValueError("stable error fields must be non-empty")
        return value


class StableCodeSequenceV1(BaseModel):
    """An immutable ordered tuple of zero or more stable error codes.

    The 1.B spike used a bare ``tuple[str, ...]`` alias; this closed model
    wrapper adds deterministic non-empty-code validation while preserving
    order and the zero-or-more cardinality.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)
    codes: tuple[StrictStr, ...]

    @field_validator("codes")
    @classmethod
    def _codes_must_be_non_empty(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        for code in value:
            if code == "":
                raise ValueError("stable error codes must be non-empty")
        return value


class EvidenceEnvelopeV1(BaseModel):
    """A closed evidence envelope binding artifact, location, and digest.

    The artifact reference digest and the location digest must be the same
    bytes; any contradictory binding rejects before the envelope exists.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal[1]
    artifact_ref: ArtifactRefV1
    location: EvidenceLocationV1

    @model_validator(mode="after")
    def _bind_digest_and_location(self) -> EvidenceEnvelopeV1:
        if self.artifact_ref.digest != self.location.digest:
            raise ValueError("artifact digest and location digest must be identical")
        return self


OptionalArtifactRefV1: TypeAlias = Annotated[
    AbsentV1 | PresentV1[ArtifactRefV1], Field(discriminator="kind")
]
"""SPEC §4.2.2: ``ABSENT`` or ``PRESENT(artifact_ref)``."""

OptionalDigestV1: TypeAlias = Annotated[
    AbsentV1 | PresentV1[DigestV1], Field(discriminator="kind")
]
"""SPEC §4.5/§4.6: ``ABSENT`` or ``PRESENT(64 lowercase hex SHA-256)``."""

"""T26.1 legacy step 26.A: immutable v0011 transaction/path value vocabulary.

Defines the exact immutable persistence value contracts of SPEC 4.6: the
closed transaction and path-write state vocabularies, the ``ABSENT`` /
``PRESENT`` preimage variant, the body-free postimage binding, the
immutable per-path record (ordered canonical path, operation, preimage,
postimage digests and text metadata, sequence, durable state, backup
artifact reference, and last evidence digest — no body ever), and the
Win32 object-identity digest helper shared by every byte/identity
observer.  This module owns values only: repository behavior, DDL,
artifact I/O, workspace writeback, and recovery disposition remain out
of scope (GREEN-4).
"""

from __future__ import annotations

from typing import Literal, TypeAlias

from pydantic import (
    BaseModel,
    ConfigDict,
    StrictStr,
    field_validator,
    model_validator,
)

from vespercode.canonical.digest import domain_digest
from vespercode.canonical.json_v1 import CanonicalValueV1
from vespercode.canonical.path_v1 import CanonicalRelativePathV1
from vespercode.contracts.evidence import (
    OptionalArtifactRefV1,
    OptionalDigestV1,
    _DIGEST_RE,
)
from vespercode.trees.text_classifier import TextMetadataV1

PersistenceTransactionStateV1 = Literal[
    "PREPARED", "WRITING", "COMMITTED", "ROLLED_BACK", "UNRESOLVED"
]
"""SPEC 4.6: the closed persistence transaction state vocabulary."""

PathWriteStateV1 = Literal["NOT_STARTED", "REPLACED", "VERIFIED", "ROLLED_BACK"]
"""SPEC 4.6: the closed per-path durable write state vocabulary."""

WriteOperationV1 = Literal["CREATE", "REPLACE"]
"""SPEC 4.6: the closed write operation vocabulary."""

PersistencePreimageKindV1 = Literal["ABSENT", "PRESENT"]
"""SPEC 4.6: the typed preimage discriminant (never an empty digest)."""


def _require_sha256_hex(value: str) -> str:
    if _DIGEST_RE.fullmatch(value) is None:
        raise ValueError("digest must be exactly 64 lowercase hexadecimal characters")
    return value


def _require_non_empty(value: str) -> str:
    if value == "":
        raise ValueError("identifier must be non-empty")
    return value


def _reject_coerced_schema_version(value: object) -> object:
    """Reject bool/float/string spellings of the integer schema version."""
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError("schema_version must be the decimal integer 1")
    return value


class PersistencePreimageV1(BaseModel):
    """SPEC 4.6 ``PreimageV1``: ABSENT sentinel or PRESENT digest evidence.

    ``ABSENT`` is a typed sentinel that never carries value fields (never
    an empty-file digest); ``PRESENT`` binds the exact raw-bytes digest,
    the sealed text metadata, and the Win32 object-identity digest of the
    pre-write object.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)
    kind: PersistencePreimageKindV1
    raw_bytes_digest: StrictStr | None = None
    text_metadata: TextMetadataV1 | None = None
    object_identity_digest: StrictStr | None = None

    @field_validator("raw_bytes_digest", "object_identity_digest")
    @classmethod
    def _digest_has_exact_form(cls, value: str | None) -> str | None:
        if value is not None:
            return _require_sha256_hex(value)
        return value

    @model_validator(mode="after")
    def _require_exact_variant(self) -> PersistencePreimageV1:
        if self.kind == "ABSENT":
            if (
                self.raw_bytes_digest is not None
                or self.text_metadata is not None
                or self.object_identity_digest is not None
            ):
                raise ValueError("ABSENT preimages must not carry evidence fields")
            return self
        if (
            self.raw_bytes_digest is None
            or self.text_metadata is None
            or self.object_identity_digest is None
        ):
            raise ValueError(
                "PRESENT preimages require the digest, metadata, and identity"
            )
        return self


class PersistencePostimageV1(BaseModel):
    """SPEC 4.6 ``PostimageV1``: raw-bytes digest, text metadata, policy."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    raw_bytes_digest: StrictStr
    text_metadata: TextMetadataV1
    required_object_policy_digest: StrictStr

    @field_validator("raw_bytes_digest", "required_object_policy_digest")
    @classmethod
    def _digest_has_exact_form(cls, value: str) -> str:
        return _require_sha256_hex(value)


class PersistencePathRecordV1(BaseModel):
    """SPEC 4.6 ``PersistencePathRecord``: one immutable body-free record.

    The record binds the canonical path, the closed operation, the exact
    preimage/postimage evidence, the 1-based sorted sequence, the durable
    write state (a last-persisted progress fact, never an authority over
    current file bytes), the backup artifact reference, and the last
    evidence digest.  ``CREATE`` must bind an ABSENT preimage and an
    ABSENT backup; ``REPLACE`` must bind a PRESENT preimage and a valid
    backup reference (SPEC 4.6: violating combinations cannot reach
    ``PREPARED``).
    """

    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal[1]
    path: CanonicalRelativePathV1
    operation: WriteOperationV1
    preimage: PersistencePreimageV1
    postimage: PersistencePostimageV1
    sequence: int
    durable_state: PathWriteStateV1
    backup_ref: OptionalArtifactRefV1
    last_evidence_digest: OptionalDigestV1

    @field_validator("schema_version", mode="before")
    @classmethod
    def _schema_version_is_exact_int(cls, value: object) -> object:
        return _reject_coerced_schema_version(value)

    @field_validator("sequence", mode="before")
    @classmethod
    def _sequence_is_exact_positive_int(cls, value: object) -> object:
        if not isinstance(value, int) or isinstance(value, bool):
            raise ValueError("sequence must be a decimal integer")
        if value < 1:
            raise ValueError("sequence must be a positive integer")
        return value

    @model_validator(mode="after")
    def _require_exact_operation_binding(self) -> PersistencePathRecordV1:
        if self.operation == "CREATE":
            if self.preimage.kind != "ABSENT":
                raise ValueError("CREATE records must bind an ABSENT preimage")
            if self.backup_ref.kind != "ABSENT":
                raise ValueError("CREATE records must bind an ABSENT backup reference")
            return self
        if self.preimage.kind != "PRESENT":
            raise ValueError("REPLACE records must bind a PRESENT preimage")
        if self.backup_ref.kind != "PRESENT":
            raise ValueError("REPLACE records must bind a valid backup reference")
        return self


PersistencePathRecordSequenceV1: TypeAlias = tuple[PersistencePathRecordV1, ...]
"""SPEC 4.6: the immutable ordered sequence of one transaction's records."""


class DuplicatePersistencePath(ValueError):
    """Closed rejection of a second record for one canonical path."""


def object_identity_digest(volume_serial_number: int, file_id_128_hex: str) -> str:
    """The SPEC 0.1 identity of one Win32 object identity pair.

    Binds the exact volume serial number and 128-bit file id (32 lowercase
    hex) observed through a real handle; byte text alone never
    authorizes, and an unprovable identity pair fails closed before any
    digest is produced.
    """
    if not isinstance(volume_serial_number, int) or isinstance(
        volume_serial_number, bool
    ):
        raise ValueError("volume serial number must be a decimal integer")
    if volume_serial_number < 0:
        raise ValueError("volume serial number must not be negative")
    if not isinstance(file_id_128_hex, str) or len(file_id_128_hex) != 32:
        raise ValueError("file id must be exactly 32 lowercase hexadecimal characters")
    if any(character not in "0123456789abcdef" for character in file_id_128_hex):
        raise ValueError("file id must be exactly 32 lowercase hexadecimal characters")
    value: dict[str, CanonicalValueV1] = {
        "volume_serial_number": volume_serial_number,
        "file_id_128_hex": file_id_128_hex,
    }
    return domain_digest("ObjectIdentityV1", 1, value)

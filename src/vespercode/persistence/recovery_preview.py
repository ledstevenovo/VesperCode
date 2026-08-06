"""T26.2 legacy step 26.B: read-only recovery preview and three-value classification.

Reads the exact non-terminal transaction, its ordered path records, the
verified artifact metadata, and the current workspace object/byte
identities into bounded source-attributed observations without ever
writing; classifies only completely proven all-postimage evidence as
``COMMITTED``, all-preimage evidence as ``ROLLED_BACK``, and every
mixed, missing, ambiguous, corrupt, or external-change state as
``UNRESOLVED`` (SPEC 4.6 / AC-29 / AC-22).  ``RealWorkspaceObserver``
is the concrete read-only observer over the Task 9.1 identity
machinery.  This module owns read-only observation and pure
classification only (GREEN-4).
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Literal, Protocol

from pydantic import (
    BaseModel,
    ConfigDict,
    StrictBool,
    StrictStr,
    field_validator,
)

from src.vespercode.canonical.digest import domain_digest
from src.vespercode.canonical.path_v1 import CanonicalRelativePathV1
from src.vespercode.contracts.evidence import OptionalDigestV1
from src.vespercode.persistence.artifacts import (
    PersistenceArtifactIntegrityError,
    PersistenceArtifactKindV1,
    PersistenceArtifactStoreV1,
)
from src.vespercode.persistence.path_record import (
    PersistencePathRecordSequenceV1,
    PersistencePathRecordV1,
    object_identity_digest,
)
from src.vespercode.persistence.transaction import (
    PersistencePathRecordRepositoryV1,
    PersistenceTransactionRepositoryV1,
)
from src.vespercode.workspace.identity_win32 import (
    WorkspaceIdentityV1,
    WorkspaceObjectRejectedV1,
)
from src.vespercode.workspace.object_win32 import inspect_workspace_object

RecoveryDispositionV1 = Literal["COMMITTED", "ROLLED_BACK", "UNRESOLVED"]
"""SPEC 4.6: the closed three-value recovery disposition."""

RecoveryPathClassificationV1 = Literal[
    "PREIMAGE", "POSTIMAGE", "ABSENT", "EXTERNAL_CHANGE", "UNPROVABLE"
]
"""The closed per-path byte/identity classification (T03.2 precedent)."""

RecoveryObservationSourceV1 = Literal["WORKSPACE_BYTES", "ARTIFACT_METADATA"]
"""The bounded source attribution of every observation fact."""

RecoveryObjectKindV1 = Literal["ABSENT", "FILE", "DIRECTORY", "SPECIAL"]
"""The observed object kinds (SPEC 1.4.3 supported-object vocabulary)."""

RecoveryPreviewErrorCodeV1 = Literal[
    "TRANSACTION_NOT_FOUND", "WORKSPACE_MISMATCH", "NO_PATH_RECORDS"
]
"""The closed preview admission rejections."""


def _reject_coerced_schema_version(value: object) -> object:
    """Reject bool/float/string spellings of the integer schema version."""
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError("schema_version must be the decimal integer 1")
    return value


class RecoveryPreviewErrorV1(ValueError):
    """Closed preview rejection: the preview cannot be produced."""

    def __init__(self, error_code: RecoveryPreviewErrorCodeV1, reason: str) -> None:
        super().__init__(f"{error_code}: {reason}")
        self.error_code = error_code


class RecoveryPathObservationV1(BaseModel):
    """One bounded source-attributed observation of a path fact.

    Carries only digests and closed facts — never raw body bytes — with
    the exact source attribution (workspace bytes/identity or artifact
    metadata) and the supported/unsupported proof fact.  The artifact
    fields are populated only for ``ARTIFACT_METADATA`` observations.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal[1]
    path: StrictStr
    source: RecoveryObservationSourceV1
    content_digest: OptionalDigestV1
    object_identity_digest: OptionalDigestV1
    object_kind: RecoveryObjectKindV1
    supported: StrictBool
    artifact_kind: PersistenceArtifactKindV1 | None = None
    artifact_digest: OptionalDigestV1 | None = None
    artifact_length: int | None = None
    acl_current_user_only: bool | None = None

    @field_validator("schema_version", mode="before")
    @classmethod
    def _schema_version_is_exact_int(cls, value: object) -> object:
        return _reject_coerced_schema_version(value)


class RecoveryPathClassificationEntryV1(BaseModel):
    """One immutable (path, classification) pair bound into a preview."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal[1]
    path: StrictStr
    classification: RecoveryPathClassificationV1

    @field_validator("schema_version", mode="before")
    @classmethod
    def _schema_version_is_exact_int(cls, value: object) -> object:
        return _reject_coerced_schema_version(value)


RecoveryPathObservationSequenceV1 = tuple[RecoveryPathObservationV1, ...]
"""SPEC 4.6: the immutable ordered observation sequence."""


class RecoveryPreviewV1(BaseModel):
    """One immutable read-only recovery preview.

    ``workspace_write_count`` is the literal zero-writes proof of this
    preview; ``preview_digest`` binds the transaction, disposition, every
    path classification, and the zero-write count so the apply can
    re-verify currency before any authoritative change.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal[1]
    transaction_id: StrictStr
    disposition: RecoveryDispositionV1
    path_classifications: tuple[RecoveryPathClassificationEntryV1, ...]
    observations: RecoveryPathObservationSequenceV1
    preview_digest: StrictStr
    workspace_write_count: Literal[0]

    @field_validator("schema_version", mode="before")
    @classmethod
    def _schema_version_is_exact_int(cls, value: object) -> object:
        return _reject_coerced_schema_version(value)


def classify_path(
    record: PersistencePathRecordV1,
    observation: RecoveryPathObservationV1,
) -> RecoveryPathClassificationV1:
    """Classify one path observation against its record evidence (pure).

    Precedence (T03.2 precedent, SPEC 5.2 fail-closed): an unsupported
    observation is UNPROVABLE; an absent path is ABSENT exactly for an
    unapplied CREATE and EXTERNAL_CHANGE otherwise; a non-FILE object is
    EXTERNAL_CHANGE; incomplete evidence is UNPROVABLE; exact postimage
    bytes classify POSTIMAGE; exact preimage bytes with a matching object
    identity classify PREIMAGE, and the same bytes behind a replaced
    identity classify EXTERNAL_CHANGE; everything else is
    EXTERNAL_CHANGE.
    """
    if not observation.supported:
        return "UNPROVABLE"
    if observation.object_kind == "ABSENT":
        if record.preimage.kind == "ABSENT":
            return "ABSENT"
        return "EXTERNAL_CHANGE"
    if observation.object_kind != "FILE":
        return "EXTERNAL_CHANGE"
    if (
        observation.content_digest.kind == "ABSENT"
        or observation.object_identity_digest.kind == "ABSENT"
    ):
        return "UNPROVABLE"
    content = observation.content_digest.value.value
    identity = observation.object_identity_digest.value.value
    if content == record.postimage.raw_bytes_digest:
        return "POSTIMAGE"
    if record.preimage.kind == "PRESENT":
        if content == record.preimage.raw_bytes_digest:
            if identity == record.preimage.object_identity_digest:
                return "PREIMAGE"
            return "EXTERNAL_CHANGE"
    return "EXTERNAL_CHANGE"


def classify_recovery(
    records: PersistencePathRecordSequenceV1,
    observations: RecoveryPathObservationSequenceV1,
) -> RecoveryDispositionV1:
    """Map the complete evidence set to exactly one closed disposition.

    Disposition matrix (T03.2 precedent extended by the production
    restore path, SPEC 4.6 items 7/10, AC-29): any EXTERNAL_CHANGE or
    UNPROVABLE classification (including a missing, unverifiable, or
    unsafe backup artifact for a REPLACE record) makes the transaction
    UNRESOLVED; every path at POSTIMAGE is COMMITTED; every path at
    PREIMAGE/ABSENT — or at POSTIMAGE with provably restorable evidence
    (a CREATE provably restorable to ABSENT under AC-29, or a REPLACE
    whose verified backup artifact restores the preimage) — is
    ROLLED_BACK; any other mixed state is UNRESOLVED.  Empty records
    fail closed.
    """
    if not records:
        return "UNRESOLVED"
    workspace_observations = {
        observation.path: observation
        for observation in observations
        if observation.source == "WORKSPACE_BYTES"
    }
    artifact_observations = {
        observation.path: observation
        for observation in observations
        if observation.source == "ARTIFACT_METADATA"
    }
    classifications: list[RecoveryPathClassificationV1] = []
    restorable: list[bool] = []
    for record in records:
        observation = workspace_observations.get(record.path.value)
        if observation is None:
            classifications.append("UNPROVABLE")
            restorable.append(False)
            continue
        classification = classify_path(record, observation)
        backup = artifact_observations.get(record.path.value)
        if record.backup_ref.kind == "PRESENT" and not _backup_proven(record, backup):
            classification = "UNPROVABLE"
        classifications.append(classification)
        restorable.append(
            classification == "POSTIMAGE"
            and (
                record.operation == "CREATE"
                or (
                    record.backup_ref.kind == "PRESENT"
                    and _backup_proven(record, backup)
                )
            )
        )
    if any(
        classification in ("EXTERNAL_CHANGE", "UNPROVABLE")
        for classification in classifications
    ):
        return "UNRESOLVED"
    if all(classification == "POSTIMAGE" for classification in classifications):
        return "COMMITTED"
    if all(
        classification in ("PREIMAGE", "ABSENT") or restorable
        for classification, restorable in zip(classifications, restorable)
    ):
        return "ROLLED_BACK"
    return "UNRESOLVED"


def _backup_proven(
    record: PersistencePathRecordV1,
    backup: RecoveryPathObservationV1 | None,
) -> bool:
    """True exactly when the record's backup evidence verifies.

    The backup artifact must exist, verify its metadata (kind/digest),
    and carry a current-user-only ACL; a missing, corrupt, or unsafe
    backup never proves the preimage (SPEC 4.6: 缺失备份 -> UNRESOLVED).
    """
    if backup is None or not backup.supported:
        return False
    if backup.artifact_digest is None or backup.artifact_digest.kind == "ABSENT":
        return False
    assert record.backup_ref.kind == "PRESENT"
    if backup.artifact_digest.value.value != record.backup_ref.value.digest.value:
        return False
    if backup.acl_current_user_only is not True:
        return False
    return True


class WorkspaceObservationPort(Protocol):
    """The injected read-only workspace byte/identity observer."""

    def observe(self, path: CanonicalRelativePathV1) -> RecoveryPathObservationV1: ...


class RealWorkspaceObserver:
    """The concrete observer over Task 9.1 real Win32 identities.

    Reads nothing but the exact final-object facts and bytes under the
    sealed workspace identity; every unprovable or unsupported object
    fails closed into an UNPROVABLE/EXTERNAL classification.
    """

    def __init__(self, identity: WorkspaceIdentityV1) -> None:
        self._identity = identity

    def _observation(
        self,
        path: CanonicalRelativePathV1,
        object_kind: RecoveryObjectKindV1,
        supported: bool,
        *,
        content: str | None = None,
        identity: str | None = None,
    ) -> RecoveryPathObservationV1:
        return RecoveryPathObservationV1.model_validate(
            {
                "schema_version": 1,
                "path": path.value,
                "source": "WORKSPACE_BYTES",
                "content_digest": (
                    {"kind": "PRESENT", "value": {"value": content}}
                    if content is not None
                    else {"kind": "ABSENT"}
                ),
                "object_identity_digest": (
                    {"kind": "PRESENT", "value": {"value": identity}}
                    if identity is not None
                    else {"kind": "ABSENT"}
                ),
                "object_kind": object_kind,
                "supported": supported,
            }
        )

    def observe(self, path: CanonicalRelativePathV1) -> RecoveryPathObservationV1:
        try:
            facts = inspect_workspace_object(self._identity, path)
        except WorkspaceObjectRejectedV1 as exc:
            if exc.error_code == "WORKSPACE_OBJECT_NOT_FOUND":
                return self._observation(path, "ABSENT", True)
            if exc.error_code == "UNSUPPORTED_WORKSPACE_OBJECT":
                # A reparse/ADS/hard-linked object exists but is not a
                # supported FILE kind (SPEC 1.4.3).
                return self._observation(path, "SPECIAL", True)
            return self._observation(path, "ABSENT", False)
        if facts.object_kind == "DIRECTORY":
            return self._observation(
                path,
                "DIRECTORY",
                True,
                identity=object_identity_digest(
                    facts.volume_serial_number, facts.file_id_128_hex
                ),
            )
        identity = object_identity_digest(
            facts.volume_serial_number, facts.file_id_128_hex
        )
        target = Path(self._identity.canonical_absolute_path) / path.value
        try:
            content = hashlib.sha256(target.read_bytes()).hexdigest()
        except OSError:
            return self._observation(path, "ABSENT", False)
        return self._observation(path, "FILE", True, content=content, identity=identity)


class RecoveryPreviewService:
    """Read-only three-value recovery preview over one transaction."""

    def __init__(
        self,
        *,
        transaction_repository: PersistenceTransactionRepositoryV1,
        path_repository: PersistencePathRecordRepositoryV1,
        artifact_store: PersistenceArtifactStoreV1,
        workspace_identity_digest: str,
        observer: WorkspaceObservationPort,
    ) -> None:
        self._transactions = transaction_repository
        self._paths = path_repository
        self._artifacts = artifact_store
        self._workspace_identity_digest = workspace_identity_digest
        self._observer = observer

    def preview_transaction(self, transaction_id: str) -> RecoveryPreviewV1:
        """Produce one immutable read-only preview of *transaction_id*.

        The exact non-terminal transaction, ordered path records,
        verified backup-artifact metadata, and current workspace
        object/byte identities are read into bounded source-attributed
        observations; nothing is ever written.  The classification is
        purely byte/identity-based, so the service entry points select
        the non-terminal workspace-bound transaction (GREEN-1);
        ``RecoveryService.preview`` and the apply admission both guard
        the non-terminal contract (SPEC review note).
        """
        transaction = self._transactions.get(transaction_id)
        if transaction is None:
            raise RecoveryPreviewErrorV1(
                "TRANSACTION_NOT_FOUND", f"no transaction {transaction_id}"
            )
        if transaction.workspace_identity_digest != self._workspace_identity_digest:
            raise RecoveryPreviewErrorV1(
                "WORKSPACE_MISMATCH",
                "transaction does not belong to the preview workspace",
            )
        records = self._paths.list_ordered(transaction_id)
        if not records:
            raise RecoveryPreviewErrorV1(
                "NO_PATH_RECORDS", "transaction carries no path records"
            )
        observations = self._observe(records)
        workspace_observations = {
            observation.path: observation
            for observation in observations
            if observation.source == "WORKSPACE_BYTES"
        }
        path_classifications = tuple(
            RecoveryPathClassificationEntryV1(
                schema_version=1,
                path=record.path.value,
                classification=classify_path(
                    record, workspace_observations[record.path.value]
                ),
            )
            for record in records
        )
        disposition = classify_recovery(records, observations)
        preview_digest = domain_digest(
            "RecoveryPreviewV1",
            1,
            {
                "transaction_id": transaction_id,
                "disposition": disposition,
                "path_classifications": tuple(
                    {"path": entry.path, "classification": entry.classification}
                    for entry in path_classifications
                ),
                "workspace_write_count": 0,
            },
        )
        return RecoveryPreviewV1(
            schema_version=1,
            transaction_id=transaction_id,
            disposition=disposition,
            path_classifications=path_classifications,
            observations=observations,
            preview_digest=preview_digest,
            workspace_write_count=0,
        )

    def _observe(
        self, records: PersistencePathRecordSequenceV1
    ) -> RecoveryPathObservationSequenceV1:
        """Collect the bounded observations for every path record."""
        observations: list[RecoveryPathObservationV1] = []
        for record in records:
            observations.append(self._observer.observe(record.path))
            if record.backup_ref.kind == "PRESENT":
                observations.append(self._observe_backup(record))
        return tuple(observations)

    def _observe_backup(
        self, record: PersistencePathRecordV1
    ) -> RecoveryPathObservationV1:
        """One verified artifact-metadata observation for a backup ref."""
        assert record.backup_ref.kind == "PRESENT"
        ref = self._artifacts.resolve("BACKUP", record.backup_ref.value.digest.value)
        try:
            # The verified read re-hashes the body, so a tampered envelope
            # or body can never pass the preview (quality review M-3).
            body = self._artifacts.read_verified(ref)
            acl = self._artifacts.verify_acl(ref)
        except PersistenceArtifactIntegrityError:
            return RecoveryPathObservationV1.model_validate(
                {
                    "schema_version": 1,
                    "path": record.path.value,
                    "source": "ARTIFACT_METADATA",
                    "content_digest": {"kind": "ABSENT"},
                    "object_identity_digest": {"kind": "ABSENT"},
                    "object_kind": "ABSENT",
                    "supported": False,
                }
            )
        proven = (
            ref.digest == record.backup_ref.value.digest
            and acl.current_user_only is True
        )
        return RecoveryPathObservationV1.model_validate(
            {
                "schema_version": 1,
                "path": record.path.value,
                "source": "ARTIFACT_METADATA",
                "content_digest": {"kind": "ABSENT"},
                "object_identity_digest": {"kind": "ABSENT"},
                "object_kind": "ABSENT",
                "supported": proven,
                "artifact_kind": "BACKUP",
                "artifact_digest": {
                    "kind": "PRESENT",
                    "value": {"value": ref.digest.value},
                },
                "artifact_length": len(body),
                "acl_current_user_only": acl.current_user_only,
            }
        )

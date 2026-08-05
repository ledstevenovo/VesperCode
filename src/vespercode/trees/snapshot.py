"""T10.2 legacy step 10.C: sole immutable SnapshotTree construction/verification.

``create_snapshot`` constructs the Run's one immutable ``SnapshotTreeV1``
only from accepted sealed Git-preflight bytes/object identities — the
T09.1 SUPPORTED seal plus its frozen path-to-content-identity table —
using the Task 10.A store (for exact content reads) and the Task 10.B
classifier (for text metadata); mutable repository paths are never
reread.  The tree binds deterministic directory/file-path order, content
refs, object identity, text metadata, policy facts, and one root digest
exposed identically as ``digest`` and ``root_digest``; every
size/order/content/object/policy drift fails integrity verification, and
every construction-time drift (count, byte total, path order, protected
input, object identity) rejects with a closed ``SnapshotIntegrityError``
before any Snapshot exists.  The read protocol (``ReadableTreeV1``) is
owned by ``readable.py``; content and classification rules are never
redefined (GREEN-4).
"""

from __future__ import annotations

import hashlib
import unicodedata
from collections.abc import Callable
from typing import Annotated, Literal, TypeAlias

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from src.vespercode.canonical.digest import domain_digest
from src.vespercode.canonical.json_v1 import CanonicalJsonErrorV1, CanonicalValueV1
from src.vespercode.canonical.path_v1 import CanonicalRelativePathV1
from src.vespercode.contracts.evidence import _DIGEST_RE
from src.vespercode.contracts.optional import AbsentV1, PresentV1
from src.vespercode.trees.content_store import (
    ContentIntegrityError,
    ContentObjectRefV1,
    ContentObjectStore,
)
from src.vespercode.trees.text_classifier import (
    TextFileClassificationV1,
    TextMetadataV1,
)
from src.vespercode.workspace.git_preflight import GitPreflightResultV1
from src.vespercode.workspace.path_guard import sensitive_path_rule_id

SupportedTextClassifierV1: TypeAlias = Callable[[bytes], TextFileClassificationV1]
"""The Task 10.B shared supported-text classifier consumed at construction."""

SnapshotIntegrityFailureCodeV1 = Literal[
    "PREFLIGHT_COUNT_DRIFT",
    "PREFLIGHT_BYTES_DRIFT",
    "PREFLIGHT_OBJECT_DRIFT",
    "PREFLIGHT_POLICY_DRIFT",
    "PATH_ORDER_DRIFT",
    "PROTECTED_INPUT_DRIFT",
    "SIZE_DRIFT",
    "CONTENT_DRIFT",
    "OBJECT_MISSING",
    "POLICY_DRIFT",
    "ROOT_DIGEST_DRIFT",
]


class SnapshotIntegrityError(Exception):
    """Closed creation rejection: the sealed inputs cannot bind one Snapshot."""

    def __init__(self, error_code: SnapshotIntegrityFailureCodeV1, reason: str) -> None:
        super().__init__(f"{error_code}: {reason}")
        self.error_code = error_code
        self.reason = reason


class SnapshotIntegrityResultV1(BaseModel):
    """The closed verification result: INTACT or exactly one FAILED drift."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal[1]
    status: Literal["INTACT", "FAILED"]
    failure_code: SnapshotIntegrityFailureCodeV1 | None = None
    reason: str | None = None

    @field_validator("schema_version", mode="before")
    @classmethod
    def _schema_version_is_exact_int(cls, value: object) -> object:
        if not isinstance(value, int) or isinstance(value, bool):
            raise ValueError("schema_version must be the decimal integer 1")
        return value

    @model_validator(mode="after")
    def _require_exact_outcome(self) -> SnapshotIntegrityResultV1:
        if self.status == "INTACT":
            if self.failure_code is not None or self.reason is not None:
                raise ValueError("INTACT results must not carry failure fields")
        elif self.failure_code is None or self.reason is None:
            raise ValueError("FAILED results require the failure code and reason")
        return self


class SealedSnapshotInputFileV1(BaseModel):
    """One sealed tracked-file identity row: canonical path and the raw-byte
    SHA-256 content identity the Task 10.A store must back."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal[1]
    path: CanonicalRelativePathV1
    content_sha256: str
    byte_count: int

    @field_validator("schema_version", mode="before")
    @classmethod
    def _schema_version_is_exact_int(cls, value: object) -> object:
        if not isinstance(value, int) or isinstance(value, bool):
            raise ValueError("schema_version must be the decimal integer 1")
        return value

    @field_validator("content_sha256", mode="before")
    @classmethod
    def _sha256_hex(cls, value: object) -> object:
        if not isinstance(value, str) or _DIGEST_RE.fullmatch(value) is None:
            raise ValueError(
                "content_sha256 must be exactly 64 lowercase hexadecimal characters"
            )
        return value

    @field_validator("byte_count", mode="before")
    @classmethod
    def _exact_byte_count(cls, value: object) -> object:
        if not isinstance(value, int) or isinstance(value, bool):
            raise ValueError("byte_count must be an exact decimal integer")
        if value < 0:
            raise ValueError("byte_count must not be negative")
        return value


class AcceptedGitPreflightV1(BaseModel):
    """The sole Snapshot-construction input: the accepted (SUPPORTED) sealed
    Git preflight plus the frozen path-to-content-identity table."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal[1]
    preflight: GitPreflightResultV1
    files: tuple[SealedSnapshotInputFileV1, ...]

    @field_validator("schema_version", mode="before")
    @classmethod
    def _schema_version_is_exact_int(cls, value: object) -> object:
        if not isinstance(value, int) or isinstance(value, bool):
            raise ValueError("schema_version must be the decimal integer 1")
        return value

    @model_validator(mode="after")
    def _require_accepted(self) -> AcceptedGitPreflightV1:
        if self.preflight.kind != "SUPPORTED":
            raise ValueError("only SUPPORTED sealed Git-preflight results are accepted")
        return self


class SnapshotDirectoryEntryV1(BaseModel):
    """One sealed directory row (SPEC §4.2.2 ``DIRECTORY`` shape)."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    kind: Literal["DIRECTORY"]
    path: CanonicalRelativePathV1


class SnapshotFileEntryV1(BaseModel):
    """One sealed file row: path, exact size, content ref, text metadata.

    The shape mirrors SPEC §4.2.2 ``ListFilesEntryV1`` (``kind``,
    ``size_bytes``, ``text_profile``) plus the Task 10.A content ref:
    ``TEXT_FILE`` binds ``PRESENT(TextMetadataV1)`` and ``NON_TEXT_FILE``
    binds ``ABSENT``, exactly like the List entry variants.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)
    kind: Literal["TEXT_FILE", "NON_TEXT_FILE"]
    path: CanonicalRelativePathV1
    size_bytes: int
    content_ref: ContentObjectRefV1
    text_profile: Annotated[
        PresentV1[TextMetadataV1] | AbsentV1, Field(discriminator="kind")
    ]

    @field_validator("size_bytes", mode="before")
    @classmethod
    def _exact_size_bytes(cls, value: object) -> object:
        if not isinstance(value, int) or isinstance(value, bool):
            raise ValueError("size_bytes must be an exact decimal integer")
        if value < 0:
            raise ValueError("size_bytes must not be negative")
        return value

    @model_validator(mode="after")
    def _require_exact_variant(self) -> SnapshotFileEntryV1:
        if self.kind == "TEXT_FILE" and not isinstance(self.text_profile, PresentV1):
            raise ValueError("TEXT_FILE entries require PRESENT text metadata")
        if self.kind == "NON_TEXT_FILE" and not isinstance(self.text_profile, AbsentV1):
            raise ValueError("NON_TEXT_FILE entries require ABSENT text metadata")
        return self


SnapshotEntryV1: TypeAlias = Annotated[
    SnapshotDirectoryEntryV1 | SnapshotFileEntryV1, Field(discriminator="kind")
]
"""One sealed Snapshot row: a directory or a text/non-text file."""


class SnapshotTreeV1(BaseModel):
    """The Run's sole immutable SnapshotTree (SPEC §7 data-model row).

    Sealed value fields: ``root_digest`` (claimed identity, recomputed and
    verified on demand), ``repository_policy_digest`` (the frozen editable
    policy binding), ``entries`` (deterministic canonical rows), and
    ``file_bytes`` (the exact sealed raw content backing ``read_bytes``;
    bound through each entry's content ref and re-hashed by
    ``verify_snapshot``).  The read protocol surface is exactly
    ``digest``/``list_directories``/``list_file_paths``/``read_bytes``.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)
    root_digest: str
    repository_policy_digest: str
    entries: tuple[SnapshotEntryV1, ...]
    file_bytes: tuple[tuple[str, bytes], ...]

    @property
    def digest(self) -> str:
        """The read-protocol digest: exactly ``root_digest`` (SPEC §7)."""
        return self.root_digest

    def list_directories(self) -> tuple[CanonicalRelativePathV1, ...]:
        """Every directory under the root, in canonical path order."""
        return tuple(
            entry.path
            for entry in self.entries
            if isinstance(entry, SnapshotDirectoryEntryV1)
        )

    def list_file_paths(self) -> tuple[CanonicalRelativePathV1, ...]:
        """Every file path in the tree, in canonical path order."""
        return tuple(
            entry.path
            for entry in self.entries
            if isinstance(entry, SnapshotFileEntryV1)
        )

    def read_bytes(self, path: CanonicalRelativePathV1) -> bytes:
        """The exact sealed raw bytes of one tree file (KeyError otherwise)."""
        for file_path, raw in self.file_bytes:
            if file_path == path.value:
                return raw
        raise KeyError(f"no file at {path.value!r} in the snapshot tree")


def create_snapshot(
    preflight: AcceptedGitPreflightV1,
    store: ContentObjectStore,
    classifier: SupportedTextClassifierV1,
) -> SnapshotTreeV1:
    """Construct and seal the Run's sole SnapshotTree from sealed inputs only.

    Every drift between the sealed preflight, the frozen file table, the
    Task 10.A store, and the path policy rejects deterministically with
    ``SnapshotIntegrityError`` before any Snapshot exists; mutable
    repository paths are never reread (GREEN-4).
    """
    sealed = preflight.preflight
    files = preflight.files
    sealed_byte_total = sum(row.byte_count for row in files)
    if sealed.tracked_file_count is None or len(files) != sealed.tracked_file_count:
        raise SnapshotIntegrityError(
            "PREFLIGHT_COUNT_DRIFT",
            f"sealed tracked count {sealed.tracked_file_count!r} does not match "
            f"the {len(files)} sealed file rows",
        )
    if sealed.tracked_byte_count is None or (
        sealed_byte_total != sealed.tracked_byte_count
    ):
        raise SnapshotIntegrityError(
            "PREFLIGHT_BYTES_DRIFT",
            f"sealed tracked byte total {sealed.tracked_byte_count!r} does not "
            f"match the {sealed_byte_total} table bytes",
        )
    _require_canonical_order(files)
    _reject_protected_input(files)
    sealed_rows: list[_SealedContent] = []
    for row in files:
        ref = ContentObjectRefV1(sha256=row.content_sha256, byte_count=row.byte_count)
        try:
            raw = store.get(ref)
        except ContentIntegrityError as error:
            raise SnapshotIntegrityError(
                "PREFLIGHT_OBJECT_DRIFT",
                f"sealed object identity {row.path.value!r} ({row.content_sha256}) "
                f"is not backed by the store: {error}",
            ) from error
        sealed_rows.append(_SealedContent(row=row, ref=ref, raw=raw))
    file_entries: list[SnapshotFileEntryV1] = []
    for sealed_content in sealed_rows:
        file_entries.append(
            _file_entry_from_classification(
                sealed_content.row, sealed_content.ref, classifier(sealed_content.raw)
            )
        )
    directories = _directory_paths(tuple(row.path for row in files))
    entries: tuple[SnapshotEntryV1, ...] = (
        *(
            SnapshotDirectoryEntryV1(kind="DIRECTORY", path=path)
            for path in directories
        ),
        *file_entries,
    )
    repository_policy_digest = sealed.repository_policy_digest
    if repository_policy_digest is None:
        # Unreachable via the accepted type (the SUPPORTED seal validator
        # already requires the policy binding, T09.1); kept as fail-closed
        # defense-in-depth so construction can never seal a policy-less tree.
        raise SnapshotIntegrityError(
            "PREFLIGHT_POLICY_DRIFT", "the accepted seal does not bind a policy digest"
        )
    return SnapshotTreeV1(
        root_digest=_root_digest(repository_policy_digest, entries),
        repository_policy_digest=repository_policy_digest,
        entries=entries,
        file_bytes=tuple(
            (sealed_content.row.path.value, sealed_content.raw)
            for sealed_content in sealed_rows
        ),
    )


def verify_snapshot(
    snapshot: SnapshotTreeV1, store: ContentObjectStore
) -> SnapshotIntegrityResultV1:
    """Verify every size/order/content/object/policy binding of one tree.

    Returns the closed ``SnapshotIntegrityResultV1`` (never raises): the
    tree is INTACT only when its rows are in deterministic canonical order,
    every size/content binding holds over the sealed bytes, the store backs
    every sealed object identity, the policy binding is a well-formed
    digest, and the claimed ``root_digest`` equals the recomputed identity.
    """
    file_entries = tuple(
        entry for entry in snapshot.entries if isinstance(entry, SnapshotFileEntryV1)
    )
    directory_entries = tuple(
        entry
        for entry in snapshot.entries
        if isinstance(entry, SnapshotDirectoryEntryV1)
    )
    if directory_entries != tuple(
        sorted(directory_entries, key=lambda entry: entry.path.value)
    ):
        return _failed("PATH_ORDER_DRIFT", "directory rows are not in canonical order")
    if file_entries != tuple(sorted(file_entries, key=lambda entry: entry.path.value)):
        return _failed("PATH_ORDER_DRIFT", "file rows are not in canonical order")
    if snapshot.entries != (*directory_entries, *file_entries):
        return _failed(
            "PATH_ORDER_DRIFT", "entries are not directories-then-files canonical order"
        )
    file_paths = [entry.path.value for entry in file_entries]
    directory_paths = [entry.path.value for entry in directory_entries]
    if len(set(file_paths)) != len(file_paths):
        return _failed("PATH_ORDER_DRIFT", "a file path appears in multiple rows")
    if len(set(directory_paths)) != len(directory_paths):
        return _failed("PATH_ORDER_DRIFT", "a directory path appears in multiple rows")
    if set(file_paths) & set(directory_paths):
        return _failed(
            "PATH_ORDER_DRIFT", "a path appears as both a directory and a file"
        )
    file_ancestors = _directory_paths(tuple(entry.path for entry in file_entries))
    if set(directory_paths) != {ancestor.value for ancestor in file_ancestors}:
        return _failed(
            "PATH_ORDER_DRIFT", "a directory row is not a proper file-path ancestor"
        )
    sealed = dict(snapshot.file_bytes)
    if len(snapshot.file_bytes) != len({path for path, _ in snapshot.file_bytes}):
        return _failed(
            "CONTENT_DRIFT", "a sealed content path appears in multiple rows"
        )
    if set(sealed) != {entry.path.value for entry in file_entries}:
        return _failed(
            "CONTENT_DRIFT", "sealed content rows do not match the file entries"
        )
    for entry in file_entries:
        raw = sealed[entry.path.value]
        if entry.size_bytes != entry.content_ref.byte_count:
            return _failed(
                "SIZE_DRIFT",
                f"{entry.path.value!r} declares size {entry.size_bytes} but its "
                f"content ref declares {entry.content_ref.byte_count} bytes",
            )
        if entry.size_bytes != len(raw):
            return _failed(
                "SIZE_DRIFT",
                f"{entry.path.value!r} declares size {entry.size_bytes} but its "
                f"sealed bytes are {len(raw)}",
            )
    for entry in file_entries:
        raw = sealed[entry.path.value]
        if hashlib.sha256(raw).hexdigest() != entry.content_ref.sha256:
            return _failed(
                "CONTENT_DRIFT",
                f"{entry.path.value!r} sealed bytes do not hash to its content ref",
            )
    for entry in file_entries:
        raw = sealed[entry.path.value]
        try:
            stored = store.get(entry.content_ref)
        except ContentIntegrityError as error:
            return _failed(
                "OBJECT_MISSING",
                f"the store cannot return the sealed object for "
                f"{entry.path.value!r}: {error}",
            )
        if stored != raw:
            return _failed(
                "CONTENT_DRIFT",
                f"{entry.path.value!r} store bytes differ from its sealed bytes",
            )
    if _DIGEST_RE.fullmatch(snapshot.repository_policy_digest) is None:
        return _failed("POLICY_DRIFT", "the repository policy binding is malformed")
    try:
        recomputed = _root_digest(snapshot.repository_policy_digest, snapshot.entries)
    except CanonicalJsonErrorV1 as error:
        return _failed(
            "ROOT_DIGEST_DRIFT", f"the tree cannot be canonically bound: {error}"
        )
    if recomputed != snapshot.root_digest:
        return _failed(
            "ROOT_DIGEST_DRIFT", "the claimed root digest does not bind the tree"
        )
    return SnapshotIntegrityResultV1(schema_version=1, status="INTACT")


def _failed(
    error_code: SnapshotIntegrityFailureCodeV1, reason: str
) -> SnapshotIntegrityResultV1:
    return SnapshotIntegrityResultV1(
        schema_version=1, status="FAILED", failure_code=error_code, reason=reason
    )


class _SealedContent:
    """One sealed file row bound to its store-verified content."""

    __slots__ = ("row", "ref", "raw")

    def __init__(
        self,
        *,
        row: SealedSnapshotInputFileV1,
        ref: ContentObjectRefV1,
        raw: bytes,
    ) -> None:
        self.row = row
        self.ref = ref
        self.raw = raw


def _file_entry_from_classification(
    row: SealedSnapshotInputFileV1,
    ref: ContentObjectRefV1,
    classification: TextFileClassificationV1,
) -> SnapshotFileEntryV1:
    """Project one Task 10.B classification into the sealed file row.

    Only the variant kind and the exact ``TextMetadataV1`` are carried;
    classification rules themselves stay in the Task 10.B classifier.
    """
    if classification.kind == "TEXT_FILE":
        text_profile: PresentV1[TextMetadataV1] | AbsentV1 = classification.text_profile
    else:
        text_profile = AbsentV1(kind="ABSENT")
    return SnapshotFileEntryV1(
        kind=classification.kind,
        path=row.path,
        size_bytes=row.byte_count,
        content_ref=ref,
        text_profile=text_profile,
    )


def _directory_paths(
    file_paths: tuple[CanonicalRelativePathV1, ...],
) -> tuple[CanonicalRelativePathV1, ...]:
    """Every proper ancestor directory of the file paths, canonical-sorted."""
    directories: set[str] = set()
    for path in file_paths:
        segments = path.value.split("/")
        for index in range(1, len(segments)):
            directories.add("/".join(segments[:index]))
    return tuple(
        sorted(
            (CanonicalRelativePathV1(value) for value in directories),
            key=lambda path: path.value,
        )
    )


def _require_canonical_order(files: tuple[SealedSnapshotInputFileV1, ...]) -> None:
    paths = [row.path.value for row in files]
    if len(set(paths)) != len(paths):
        raise SnapshotIntegrityError("PATH_ORDER_DRIFT", "duplicate sealed file path")
    if paths != sorted(paths):
        raise SnapshotIntegrityError(
            "PATH_ORDER_DRIFT", "sealed file rows are not in canonical path order"
        )
    # A file path can never be a directory of another file path (git cannot
    # track one path as both); in canonical order only adjacent rows can be
    # ancestor pairs, mirroring the verification-side structural checks.
    for first, second in zip(paths, paths[1:]):
        if second.startswith(f"{first}/"):
            raise SnapshotIntegrityError(
                "PATH_ORDER_DRIFT",
                f"sealed file path {first!r} is also a directory of {second!r}",
            )


def _reject_protected_input(files: tuple[SealedSnapshotInputFileV1, ...]) -> None:
    """Reject sealed inputs a real SUPPORTED seal could never contain.

    A SUPPORTED preflight already excluded sensitive tracked paths and
    Windows/Unicode path collisions (T09.1), so any such row in the frozen
    table is drifted input and must reject before a Snapshot exists.
    """
    folded: dict[str, str] = {}
    normalized: dict[str, str] = {}
    for row in files:
        path = row.path.value
        if sensitive_path_rule_id(path) is not None:
            raise SnapshotIntegrityError(
                "PROTECTED_INPUT_DRIFT", f"sealed input path {path!r} is sensitive"
            )
        try:
            path.encode("utf-8")
        except UnicodeEncodeError as error:
            # Git output is strict-UTF-8 decoded, so a lone surrogate can
            # never come from a real SUPPORTED seal; reject it closed
            # instead of letting the canonical encoder raise raw.
            raise SnapshotIntegrityError(
                "PROTECTED_INPUT_DRIFT",
                f"sealed input path {path!r} is not strict-UTF-8 encodable",
            ) from error
        key = path.casefold()
        if key in folded and folded[key] != path:
            raise SnapshotIntegrityError(
                "PROTECTED_INPUT_DRIFT",
                f"sealed input paths {folded[key]!r} and {path!r} case-collide",
            )
        folded[key] = path
        key = unicodedata.normalize("NFC", path)
        if key in normalized and normalized[key] != path:
            raise SnapshotIntegrityError(
                "PROTECTED_INPUT_DRIFT",
                f"sealed input paths {normalized[key]!r} and {path!r} unicode-collide",
            )
        normalized[key] = path


def _canonical_entry(entry: SnapshotEntryV1) -> dict[str, CanonicalValueV1]:
    """One canonical §0.1 value for a sealed Snapshot row."""
    if isinstance(entry, SnapshotDirectoryEntryV1):
        return {"kind": "DIRECTORY", "path": entry.path.value}
    profile = entry.text_profile
    if isinstance(profile, PresentV1):
        metadata = profile.value
        text_profile: CanonicalValueV1 = {
            "kind": "PRESENT",
            "value": {
                "encoding": metadata.encoding,
                "newline": metadata.newline,
                "final_newline": metadata.final_newline,
            },
        }
    else:
        text_profile = {"kind": "ABSENT"}
    return {
        "kind": entry.kind,
        "path": entry.path.value,
        "size_bytes": entry.size_bytes,
        "content_ref": {
            "sha256": entry.content_ref.sha256,
            "byte_count": entry.content_ref.byte_count,
        },
        "text_profile": text_profile,
    }


def _root_digest(
    repository_policy_digest: str, entries: tuple[SnapshotEntryV1, ...]
) -> str:
    """The §0.1 domain digest binding the policy and every sealed row."""
    return domain_digest(
        "SnapshotTreeV1",
        1,
        {
            "schema_version": 1,
            "repository_policy_digest": repository_policy_digest,
            "entries": tuple(_canonical_entry(entry) for entry in entries),
        },
    )

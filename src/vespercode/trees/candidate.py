"""T12.1 legacy step 12.B: immutable content-addressed CandidateTree overlay.

``derive_candidate_revision`` derives an immutable child
``CandidateRevisionV1`` from complete staged postimages (Task 12.C
staging) using the Task 10.A content store while leaving the parent
revision and tree completely unchanged.  ``CandidateTreeV1`` overlays the
Run's sole sealed ``SnapshotTreeV1``: deterministic canonical
directory/file-path enumeration, exact byte reads (overlay entries resolve
through the content store and fail closed on missing or drifted objects),
and one deterministic content-addressed tree digest binding the snapshot
root digest and every ordered overlay entry.  The tree structurally
satisfies T10.2's ``ReadableTreeV1`` protocol without importing any T11.1
module.  Patch parsing, path authorization, transactional publication,
FinalDiff, and policy decisions remain out of scope (GREEN-4).

Recorded identity interpretation: ``derive_candidate_revision`` sets
``CandidateRevisionV1.candidate_digest`` to this tree layer's
content-addressed candidate identity (the card's "content-addressed tree
identity").  The three-root semantic ``CandidateIdentityV1`` binding
(SPEC §4.3: "candidate_digest 精确等于 CandidateIdentityV1.digest") is
owned by Task 12.D and realized in code by
``candidate.identity.bind_revision_identity`` after the FinalDiff is
recomputed; because FinalDiffV1 is a deterministic function of (snapshot,
candidate tree, policy) the two identities co-vary, so base-binding
comparisons behave identically before and after the binding.
"""

from __future__ import annotations

import hashlib
import unicodedata
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
from vespercode.contracts.evidence import _DIGEST_RE
from vespercode.profiles.editable import EditableOperationV1
from vespercode.trees.content_store import (
    ContentIntegrityError,
    ContentObjectRefV1,
    ContentObjectStore,
)
from vespercode.trees.snapshot import SnapshotFileEntryV1, SnapshotTreeV1

CandidateIntegrityCodeV1 = Literal[
    "POSTIMAGE_DUPLICATE_PATH",
    "POSTIMAGE_PATH_EXISTS",
    "POSTIMAGE_PATH_NOT_FOUND",
    "OBJECT_MISSING",
]
"""The closed overlay-failure codes: staged-batch collisions and content
store unavailability at read time."""


class CandidateIntegrityError(Exception):
    """Closed overlay failure: the staged or sealed inputs cannot bind."""

    def __init__(self, error_code: CandidateIntegrityCodeV1, reason: str) -> None:
        super().__init__(f"{error_code}: {reason}")
        self.error_code = error_code
        self.reason = reason


class CandidatePostimageV1(BaseModel):
    """One complete staged postimage: operation, canonical path, raw bytes.

    The raw bytes are the complete new file bytes (no partial or
    incremental content); the derive step stores them in the run's content
    store under their verified SHA-256 identity.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal[1]
    operation: EditableOperationV1
    path: CanonicalRelativePathV1
    raw_bytes: bytes

    @field_validator("schema_version", mode="before")
    @classmethod
    def _schema_version_is_exact_int(cls, value: object) -> object:
        if not isinstance(value, int) or isinstance(value, bool):
            raise ValueError("schema_version must be the decimal integer 1")
        return value

    @field_validator("raw_bytes", mode="before")
    @classmethod
    def _raw_bytes_are_exact_bytes(cls, value: object) -> object:
        if not isinstance(value, bytes):
            raise ValueError("raw_bytes must be exact bytes, never text")
        return value


CandidatePostimageSequenceV1: TypeAlias = tuple[CandidatePostimageV1, ...]
"""SPEC-ordered immutable sequence of zero or more staged postimages."""


class CandidateOverlayEntryV1(BaseModel):
    """One sealed overlay row: staged operation, path, and content identity.

    The content ref binds the exact stored postimage bytes; the same
    identity is exposed through the tree's digest and resolved by
    ``read_bytes`` with a closed failure on any missing or drifted object.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal[1]
    operation: EditableOperationV1
    path: CanonicalRelativePathV1
    content_ref: ContentObjectRefV1

    @field_validator("schema_version", mode="before")
    @classmethod
    def _schema_version_is_exact_int(cls, value: object) -> object:
        if not isinstance(value, int) or isinstance(value, bool):
            raise ValueError("schema_version must be the decimal integer 1")
        return value


class CandidateTreeV1(BaseModel):
    """The immutable content-addressed candidate tree (SPEC §7 row).

    Sealed value fields: ``snapshot`` (the Run's sole sealed base tree,
    never mutated), ``overlay`` (ordered unique rows in canonical path
    order), and ``digest`` (the deterministic tree identity binding the
    snapshot root digest and every overlay row).  ``store`` is the run's
    backing content store — the resolution service behind the sealed
    overlay refs, never a sealed value itself.  The read protocol surface
    is exactly T10.2's ``ReadableTreeV1`` (``digest``,
    ``list_directories``, ``list_file_paths``, ``read_bytes``) with no
    T11.1 import.
    """

    model_config = ConfigDict(extra="forbid", frozen=True, arbitrary_types_allowed=True)
    schema_version: Literal[1]
    snapshot: SnapshotTreeV1
    store: ContentObjectStore
    overlay: tuple[CandidateOverlayEntryV1, ...]
    digest: StrictStr

    @field_validator("schema_version", mode="before")
    @classmethod
    def _schema_version_is_exact_int(cls, value: object) -> object:
        if not isinstance(value, int) or isinstance(value, bool):
            raise ValueError("schema_version must be the decimal integer 1")
        return value

    @field_validator("digest")
    @classmethod
    def _require_sha256_hex(cls, value: str) -> str:
        if _DIGEST_RE.fullmatch(value) is None:
            raise ValueError(
                "digest must be exactly 64 lowercase hexadecimal characters"
            )
        return value

    @model_validator(mode="after")
    def _require_ordered_unique_bound_overlay(self) -> CandidateTreeV1:
        paths = [entry.path.value for entry in self.overlay]
        if len(set(paths)) != len(paths):
            raise ValueError("overlay entries must be unique per path")
        if paths != sorted(paths):
            raise ValueError("overlay entries must be in canonical path order")
        if self.digest != digest_candidate_tree(
            self.snapshot.root_digest, self.overlay
        ):
            raise ValueError("digest must bind the snapshot root and every overlay row")
        return self

    def list_directories(self) -> tuple[CanonicalRelativePathV1, ...]:
        """Every directory under the tree root, in canonical path order."""
        return tuple(
            sorted(
                _directory_paths(tuple(path.value for path in self.list_file_paths())),
                key=lambda path: path.value,
            )
        )

    def list_file_paths(self) -> tuple[CanonicalRelativePathV1, ...]:
        """Every file path in the tree, in canonical path order.

        The overlay replaces or adds paths over the sealed snapshot file
        set; the result is always the deterministic sorted union.
        """
        file_paths = {
            entry.path.value
            for entry in self.snapshot.entries
            if isinstance(entry, SnapshotFileEntryV1)
        }
        file_paths.update(entry.path.value for entry in self.overlay)
        return tuple(
            sorted(
                (CanonicalRelativePathV1(value) for value in file_paths),
                key=lambda path: path.value,
            )
        )

    def read_bytes(self, path: CanonicalRelativePathV1) -> bytes:
        """The exact sealed raw bytes of one tree file.

        Overlay paths resolve through the content store and fail closed
        with ``CandidateIntegrityError`` on a missing or drifted object;
        every other path reads the exact sealed snapshot bytes.  Raises
        ``KeyError`` when *path* is not a file path of this tree.
        """
        overlay = {entry.path.value: entry for entry in self.overlay}
        entry = overlay.get(path.value)
        if entry is not None:
            try:
                return self.store.get(entry.content_ref)
            except ContentIntegrityError as error:
                raise CandidateIntegrityError(
                    "OBJECT_MISSING",
                    f"the content store cannot return the overlay object for "
                    f"{path.value!r}: {error}",
                ) from error
        return self.snapshot.read_bytes(path)


class CandidateRevisionV1(BaseModel):
    """One immutable candidate revision in the single-parent audit chain.

    ``revision_id`` and ``parent_revision_id`` are audit-only (SPEC §7:
    "ID 和父链不进入候选语义摘要").  ``candidate_digest`` starts as the
    content-addressed candidate tree identity set by
    ``derive_candidate_revision`` and is bound to the three-root
    ``CandidateIdentityV1.digest`` by
    ``candidate.identity.bind_revision_identity`` after Task 12.D
    recomputation (see the module docstring for the recorded Task 12.B
    interpretation).
    """

    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal[1]
    revision_id: StrictStr
    parent_revision_id: StrictStr | None
    candidate_digest: StrictStr
    tree: CandidateTreeV1

    @field_validator("schema_version", mode="before")
    @classmethod
    def _schema_version_is_exact_int(cls, value: object) -> object:
        if not isinstance(value, int) or isinstance(value, bool):
            raise ValueError("schema_version must be the decimal integer 1")
        return value

    @field_validator("revision_id", "parent_revision_id", mode="before")
    @classmethod
    def _no_empty_ids(cls, value: object) -> object:
        if value is None:
            return None
        if not isinstance(value, str) or value == "":
            raise ValueError("revision ids must be non-empty strings")
        return value

    @field_validator("candidate_digest")
    @classmethod
    def _require_sha256_hex(cls, value: str) -> str:
        if _DIGEST_RE.fullmatch(value) is None:
            raise ValueError(
                "candidate_digest must be exactly 64 lowercase hexadecimal characters"
            )
        return value

    @model_validator(mode="after")
    def _require_root_has_no_parent(self) -> CandidateRevisionV1:
        if self.parent_revision_id is None and not self.revision_id.startswith("root:"):
            raise ValueError(
                "only the root candidate revision may have no parent revision"
            )
        return self


def root_candidate_revision(
    snapshot: SnapshotTreeV1, store: ContentObjectStore
) -> CandidateRevisionV1:
    """The root candidate revision whose tree is the sealed snapshot.

    This is the sole sanctioned entry into the candidate chain: the run's
    first ``current`` revision after PREFLIGHT and BASELINE, with an empty
    overlay and no parent.
    """
    tree = CandidateTreeV1(
        schema_version=1,
        snapshot=snapshot,
        store=store,
        overlay=(),
        digest=digest_candidate_tree(snapshot.root_digest, ()),
    )
    return CandidateRevisionV1(
        schema_version=1,
        revision_id="root:" + snapshot.root_digest,
        parent_revision_id=None,
        candidate_digest=tree.digest,
        tree=tree,
    )


def derive_candidate_revision(
    parent: CandidateRevisionV1,
    postimages: CandidatePostimageSequenceV1,
) -> CandidateRevisionV1:
    """Derive one immutable child revision from complete staged postimages.

    The child tree is the parent tree plus the staged postimages (stored
    in the run's content store under their verified identities, then bound
    as ordered overlay rows); the parent revision and tree are never
    mutated.  Every structural collision — duplicate staged paths, a
    CREATE on an existing path, a REPLACE on a missing path — rejects
    closed with ``CandidateIntegrityError`` before any store write.
    """
    if not isinstance(postimages, tuple):
        raise TypeError("staged postimages must be an immutable tuple")
    paths = [postimage.path.value for postimage in postimages]
    if len(set(paths)) != len(paths):
        raise CandidateIntegrityError(
            "POSTIMAGE_DUPLICATE_PATH",
            "a staged batch must not contain the same path twice: "
            + repr(sorted(set(p for p in paths if paths.count(p) > 1))),
        )
    file_paths = {path.value for path in parent.tree.list_file_paths()}
    for postimage in postimages:
        if postimage.operation == "CREATE":
            if path_collides_with_tree(parent.tree, postimage.path):
                raise CandidateIntegrityError(
                    "POSTIMAGE_PATH_EXISTS",
                    f"CREATE path {postimage.path.value!r} collides with an "
                    "existing tree path",
                )
        elif postimage.path.value not in file_paths:
            raise CandidateIntegrityError(
                "POSTIMAGE_PATH_NOT_FOUND",
                f"REPLACE path {postimage.path.value!r} has no base bytes in the tree",
            )
    existing = {entry.path.value: entry for entry in parent.tree.overlay}
    for postimage in postimages:
        ref = parent.tree.store.put(postimage.raw_bytes)
        existing[postimage.path.value] = CandidateOverlayEntryV1(
            schema_version=1,
            operation=postimage.operation,
            path=postimage.path,
            content_ref=ref,
        )
    ordered = tuple(existing[value] for value in sorted(existing))
    tree = CandidateTreeV1(
        schema_version=1,
        snapshot=parent.tree.snapshot,
        store=parent.tree.store,
        overlay=ordered,
        digest=digest_candidate_tree(parent.tree.snapshot.root_digest, ordered),
    )
    return CandidateRevisionV1(
        schema_version=1,
        revision_id=hashlib.sha256(
            (parent.revision_id + "\x00" + tree.digest).encode("utf-8")
        ).hexdigest(),
        parent_revision_id=parent.revision_id,
        candidate_digest=tree.digest,
        tree=tree,
    )


def digest_candidate_tree(
    snapshot_root_digest: str, overlay: tuple[CandidateOverlayEntryV1, ...]
) -> str:
    """The deterministic §0.1 tree identity binding the snapshot root and
    every ordered overlay row (SPEC §0.1 object_type ``CandidateTreeV1``)."""
    return domain_digest(
        "CandidateTreeV1",
        1,
        {
            "schema_version": 1,
            "snapshot_tree_digest": snapshot_root_digest,
            "overlay": tuple(_canonical_overlay_entry(entry) for entry in overlay),
        },
    )


def _canonical_overlay_entry(
    entry: CandidateOverlayEntryV1,
) -> dict[str, CanonicalValueV1]:
    """One canonical §0.1 value for a sealed overlay row."""
    return {
        "operation": entry.operation,
        "path": entry.path.value,
        "content_ref": {
            "sha256": entry.content_ref.sha256,
            "byte_count": entry.content_ref.byte_count,
        },
    }


def path_collides_with_tree(
    tree: CandidateTreeV1, path: CanonicalRelativePathV1
) -> bool:
    """True when *path* would collide with an existing tree path.

    Collisions are closed exactly like every other layer's checks: the
    path itself exists as a file or directory; any proper ancestor of the
    path is an existing *file* (a file can never be a directory); or the
    path is a Windows case-fold or Unicode-normalization alias of an
    existing file or directory path.  Without this closure a CREATE could
    seal a tree shape the rest of the system treats as drift.
    """
    value = path.value
    file_paths = {existing.value for existing in tree.list_file_paths()}
    directory_paths = {existing.value for existing in tree.list_directories()}
    if value in file_paths or value in directory_paths:
        return True
    # A proper ancestor that is an existing file — exactly or under a
    # Windows case-fold / Unicode-normalization alias — makes the path a
    # file's descendant, a shape the whole system treats as drift.  A
    # directory ancestor is the normal CREATE parent and never collides.
    folded_files: dict[str, str] = {}
    normalized_files: dict[str, str] = {}
    for existing in file_paths:
        folded_files.setdefault(existing.casefold(), existing)
        normalized_files.setdefault(unicodedata.normalize("NFC", existing), existing)
    segments = value.split("/")
    for count in range(1, len(segments)):
        prefix = "/".join(segments[:count])
        if prefix in file_paths:
            return True
        folded_match = folded_files.get(prefix.casefold())
        if folded_match is not None and folded_match != prefix:
            return True
        normalized_match = normalized_files.get(unicodedata.normalize("NFC", prefix))
        if normalized_match is not None and normalized_match != prefix:
            return True
    # A full-path alias of an existing file or directory path.
    existing_paths = file_paths | directory_paths
    folded: dict[str, str] = {}
    normalized: dict[str, str] = {}
    for existing_value in existing_paths:
        folded.setdefault(existing_value.casefold(), existing_value)
        normalized.setdefault(
            unicodedata.normalize("NFC", existing_value), existing_value
        )
    folded_match = folded.get(value.casefold())
    if folded_match is not None and folded_match != value:
        return True
    normalized_match = normalized.get(unicodedata.normalize("NFC", value))
    if normalized_match is not None and normalized_match != value:
        return True
    return False


def _directory_paths(
    file_paths: tuple[str, ...],
) -> set[CanonicalRelativePathV1]:
    """Every proper ancestor directory of the file paths, canonical-sorted."""
    directories: set[str] = set()
    for value in file_paths:
        segments = value.split("/")
        for index in range(1, len(segments)):
            directories.add("/".join(segments[:index]))
    return {CanonicalRelativePathV1(value) for value in directories}

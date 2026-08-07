"""T12.1 legacy step 12.D: complete Snapshot-to-candidate FinalDiffV1.

``recompute_final_diff`` recomputes the complete structured CREATE/REPLACE
net diff of one ``CandidateTreeV1`` relative to the Run's sealed
``SnapshotTreeV1`` — exact preimages/postimages with byte-identity
digests and text metadata, the deterministic canonical path order, and
the closed ``added_and_replacement_text_bytes`` total over every complete
postimage raw byte sequence — then revalidates the sole editable policy
for every entry and the SPEC §1.4.4 hard caps before returning the closed
``FinalDiffV1``.  Every drift (policy binding mismatch, non-editable
entry, non-text state, over-limit counts or bytes) raises the closed
``FinalDiffRejectedError`` instead of producing a diff.  Patch
application, revision publication, writeback approval, mutable workspace
access, deletion, rename, and binary changes remain out of scope
(GREEN-4).
"""

from __future__ import annotations

import hashlib
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
from vespercode.canonical.path_v1 import CanonicalRelativePathV1
from vespercode.contracts.evidence import _DIGEST_RE
from vespercode.contracts.optional import AbsentV1
from vespercode.profiles.editable import EditablePathPolicyV1
from vespercode.trees.candidate import CandidateIntegrityError, CandidateTreeV1
from vespercode.trees.snapshot import SnapshotFileEntryV1, SnapshotTreeV1
from vespercode.trees.text_classifier import TextMetadataV1, classify_supported_text

_MAX_ENTRIES = 3
_MAX_TOTAL_POSTIMAGE_BYTES = 131072

FinalDiffRejectionCodeV1 = Literal[
    "PATCH_PATH_NOT_EDITABLE",
    "PATCH_LIMIT_EXCEEDED",
    "TREE_INTEGRITY_FAILED",
]
"""The closed FinalDiff recomputation rejections (SPEC §4.3 / §4.5)."""


class FinalDiffRejectedError(Exception):
    """Closed recomputation rejection: the diff cannot be produced."""

    def __init__(self, error_code: FinalDiffRejectionCodeV1, reason: str) -> None:
        super().__init__(f"{error_code}: {reason}")
        self.error_code = error_code
        self.reason = reason


class FinalDiffPreimageV1(BaseModel):
    """SPEC §4.3 preimage variant: ABSENT (CREATE) or PRESENT with the
    exact content identity and sealed text metadata (REPLACE)."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    kind: Literal["ABSENT", "PRESENT"]
    content_digest: str | None = None
    text_metadata: TextMetadataV1 | None = None

    @field_validator("content_digest")
    @classmethod
    def _require_sha256_hex(cls, value: str | None) -> str | None:
        if value is not None and _DIGEST_RE.fullmatch(value) is None:
            raise ValueError(
                "content_digest must be exactly 64 lowercase hexadecimal characters"
            )
        return value

    @model_validator(mode="after")
    def _require_exact_variant(self) -> FinalDiffPreimageV1:
        if self.kind == "ABSENT":
            if self.content_digest is not None or self.text_metadata is not None:
                raise ValueError("ABSENT preimages must not carry value fields")
        elif self.content_digest is None or self.text_metadata is None:
            raise ValueError("PRESENT preimages require the digest and metadata")
        return self


class FinalDiffEntryV1(BaseModel):
    """One closed net-diff entry (SPEC §4.3): operation, path, exact
    preimage variant, and the exact postimage content identity and text
    metadata."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    operation: Literal["CREATE", "REPLACE"]
    path: CanonicalRelativePathV1
    preimage: FinalDiffPreimageV1
    postimage_digest: StrictStr
    postimage_text_metadata: TextMetadataV1

    @field_validator("postimage_digest")
    @classmethod
    def _require_sha256_hex(cls, value: str) -> str:
        if _DIGEST_RE.fullmatch(value) is None:
            raise ValueError(
                "postimage_digest must be exactly 64 lowercase hexadecimal characters"
            )
        return value

    @model_validator(mode="after")
    def _require_exact_operation_binding(self) -> FinalDiffEntryV1:
        if self.operation == "CREATE" and self.preimage.kind != "ABSENT":
            raise ValueError("CREATE entries must bind an ABSENT preimage")
        if self.operation == "REPLACE" and self.preimage.kind != "PRESENT":
            raise ValueError("REPLACE entries must bind a PRESENT preimage")
        return self


class FinalDiffV1(BaseModel):
    """The closed Snapshot-to-candidate net diff (SPEC §4.3).

    ``entries`` are unique, at most three, and sorted by canonical path;
    ``added_and_replacement_text_bytes`` is the Harness-derived sum of the
    complete postimage raw byte sequences (0 when empty); ``digest`` is
    the §0.1 identity of every field except itself and must bind them at
    construction.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal[1]
    snapshot_tree_digest: StrictStr
    entries: tuple[FinalDiffEntryV1, ...]
    added_and_replacement_text_bytes: int
    digest: StrictStr

    @field_validator("schema_version", mode="before")
    @classmethod
    def _schema_version_is_exact_int(cls, value: object) -> object:
        if not isinstance(value, int) or isinstance(value, bool):
            raise ValueError("schema_version must be the decimal integer 1")
        return value

    @field_validator("snapshot_tree_digest", "digest")
    @classmethod
    def _require_sha256_hex(cls, value: str) -> str:
        if _DIGEST_RE.fullmatch(value) is None:
            raise ValueError(
                "tree digests must be exactly 64 lowercase hexadecimal characters"
            )
        return value

    @field_validator("added_and_replacement_text_bytes", mode="before")
    @classmethod
    def _exact_byte_total(cls, value: object) -> object:
        if not isinstance(value, int) or isinstance(value, bool):
            raise ValueError(
                "added_and_replacement_text_bytes must be an exact decimal integer"
            )
        if value < 0:
            raise ValueError("added_and_replacement_text_bytes must not be negative")
        return value

    @model_validator(mode="after")
    def _require_closed_bound_diff(self) -> FinalDiffV1:
        if len(self.entries) > _MAX_ENTRIES:
            raise ValueError("entries must contain at most three rows")
        paths = [entry.path.value for entry in self.entries]
        if len(set(paths)) != len(paths):
            raise ValueError("entries must be unique per path")
        if paths != sorted(paths):
            raise ValueError("entries must be sorted by canonical path")
        if self.digest != _final_diff_digest(
            self.snapshot_tree_digest,
            self.entries,
            self.added_and_replacement_text_bytes,
        ):
            raise ValueError("digest must bind every other exact field")
        return self


def recompute_final_diff(
    snapshot: SnapshotTreeV1,
    candidate: CandidateTreeV1,
    policy: EditablePathPolicyV1,
) -> FinalDiffV1:
    """Recompute the complete Snapshot-to-candidate structured net diff.

    The Snapshot must bind the same frozen editable policy digest (the
    snapshot tree digest must resolve to a repository policy carrying the
    same policy), every entry must match the sole editable policy, the
    candidate must contain supported text only, and the SPEC §1.4.4 hard
    caps (at most 3 entries, at most 131072 total postimage bytes) must
    hold; any violation raises the closed ``FinalDiffRejectedError``.
    """
    if snapshot.repository_policy_digest != policy.digest:
        raise FinalDiffRejectedError(
            "TREE_INTEGRITY_FAILED",
            "the snapshot does not bind the frozen editable policy digest",
        )
    if snapshot.root_digest != candidate.snapshot.root_digest:
        raise FinalDiffRejectedError(
            "TREE_INTEGRITY_FAILED",
            "the passed snapshot is not the candidate tree's sealed snapshot",
        )
    snapshot_files = {
        entry.path.value: entry
        for entry in snapshot.entries
        if isinstance(entry, SnapshotFileEntryV1)
    }
    candidate_paths = {path.value for path in candidate.list_file_paths()}
    if not set(snapshot_files).issubset(candidate_paths):
        raise FinalDiffRejectedError(
            "TREE_INTEGRITY_FAILED",
            "the candidate tree is missing sealed snapshot file paths",
        )
    entries: list[FinalDiffEntryV1] = []
    total_bytes = 0
    try:
        for path_value in sorted(set(snapshot_files) | candidate_paths):
            path = CanonicalRelativePathV1(path_value)
            postimage = candidate.read_bytes(path)
            if path_value in snapshot_files:
                preimage_bytes = snapshot.read_bytes(path)
                if preimage_bytes == postimage:
                    # Unchanged — not an entry of the net diff.  The skip
                    # happens before any text classification so a
                    # legitimately tracked NON_TEXT_FILE that the candidate
                    # never touched (e.g. a binary asset) never becomes an
                    # entry and never fails the diff closed.
                    continue
                operation: Literal["CREATE", "REPLACE"] = "REPLACE"
                sealed = snapshot_files[path_value]
                if isinstance(sealed.text_profile, AbsentV1):
                    raise FinalDiffRejectedError(
                        "TREE_INTEGRITY_FAILED",
                        f"REPLACE preimage at {path_value!r} is not supported text",
                    )
                preimage = FinalDiffPreimageV1(
                    kind="PRESENT",
                    content_digest=hashlib.sha256(preimage_bytes).hexdigest(),
                    text_metadata=sealed.text_profile.value,
                )
            else:
                operation = "CREATE"
                preimage = FinalDiffPreimageV1(kind="ABSENT")
            post_classification = classify_supported_text(postimage)
            if post_classification.kind != "TEXT_FILE":
                raise FinalDiffRejectedError(
                    "TREE_INTEGRITY_FAILED",
                    f"candidate postimage at {path_value!r} is not supported text",
                )
            post_metadata = post_classification.text_profile.value
            if not policy.matches(path, operation):
                raise FinalDiffRejectedError(
                    "PATCH_PATH_NOT_EDITABLE",
                    f"entry path {path_value!r} is not editable for {operation}",
                )
            entries.append(
                FinalDiffEntryV1(
                    operation=operation,
                    path=path,
                    preimage=preimage,
                    postimage_digest=hashlib.sha256(postimage).hexdigest(),
                    postimage_text_metadata=post_metadata,
                )
            )
            total_bytes += len(postimage)
    except CandidateIntegrityError as error:
        raise FinalDiffRejectedError(
            "TREE_INTEGRITY_FAILED",
            f"the candidate tree cannot return its sealed bytes: {error}",
        ) from error
    if len(entries) > _MAX_ENTRIES:
        raise FinalDiffRejectedError(
            "PATCH_LIMIT_EXCEEDED",
            f"the cumulative net diff would touch {len(entries)} files (limit 3)",
        )
    if total_bytes > _MAX_TOTAL_POSTIMAGE_BYTES:
        raise FinalDiffRejectedError(
            "PATCH_LIMIT_EXCEEDED",
            f"the cumulative postimage bytes would be {total_bytes} (limit 131072)",
        )
    return FinalDiffV1(
        schema_version=1,
        snapshot_tree_digest=snapshot.root_digest,
        entries=tuple(entries),
        added_and_replacement_text_bytes=total_bytes,
        digest=_final_diff_digest(snapshot.root_digest, tuple(entries), total_bytes),
    )


def _final_diff_digest(
    snapshot_tree_digest: str,
    entries: tuple[FinalDiffEntryV1, ...],
    added_and_replacement_text_bytes: int,
) -> str:
    """The §0.1 identity of every exact FinalDiffV1 field except the digest."""
    return domain_digest(
        "FinalDiffV1",
        1,
        {
            "schema_version": 1,
            "snapshot_tree_digest": snapshot_tree_digest,
            "entries": tuple(_canonical_entry(entry) for entry in entries),
            "added_and_replacement_text_bytes": added_and_replacement_text_bytes,
        },
    )


def _canonical_entry(entry: FinalDiffEntryV1) -> dict[str, CanonicalValueV1]:
    """One canonical §0.1 value for a sealed FinalDiff row."""
    if entry.preimage.kind == "ABSENT":
        preimage: CanonicalValueV1 = {"kind": "ABSENT"}
    else:
        content_digest = entry.preimage.content_digest
        metadata = entry.preimage.text_metadata
        assert content_digest is not None
        assert metadata is not None
        preimage = {
            "kind": "PRESENT",
            "content_digest": content_digest,
            "text_metadata": {
                "encoding": metadata.encoding,
                "newline": metadata.newline,
                "final_newline": metadata.final_newline,
            },
        }
    post_metadata = entry.postimage_text_metadata
    return {
        "operation": entry.operation,
        "path": entry.path.value,
        "preimage": preimage,
        "postimage_digest": entry.postimage_digest,
        "postimage_text_metadata": {
            "encoding": post_metadata.encoding,
            "newline": post_metadata.newline,
            "final_newline": post_metadata.final_newline,
        },
    }

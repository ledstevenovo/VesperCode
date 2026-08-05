"""T12.1 legacy step 12.C: atomic exact candidate patch transaction.

``apply_candidate_patch`` consumes the Task 12.A parse result, Task 12.B
staging, Task 9.D path-fact authorization (the shared sensitive-path,
protected-artifact, and frozen-ignore tables), the frozen
``EditablePathPolicyV1``, and the named base candidate to validate one
complete patch and publish exactly one validated ``CandidateRevisionV1``
or no revision.  The whole patch is validated first — exact base digest
and hunk matches with no fuzzy offset, editable paths with the SPEC §4.3
priority, text preservation, candidate hard limits, and collision checks
— and any single illegal path/operation/encoding/size/count/byte form
rejects the entire action with zero candidate side effects and zero
publications.  FinalDiff construction, candidate semantic identity,
deletion, rename, mode, and binary support remain out of scope (GREEN-4).
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Literal, Protocol

from pydantic import (
    BaseModel,
    ConfigDict,
    StrictStr,
    field_validator,
    model_validator,
)

from src.vespercode.candidate.unified_diff import (
    ParsedPatchEntryV1,
    PatchParseFailureV1,
    parse_unified_diff_v1,
)
from src.vespercode.canonical.path_v1 import CanonicalRelativePathV1
from src.vespercode.contracts.evidence import _DIGEST_RE
from src.vespercode.profiles.reference import ReferenceProfileManifestV1
from src.vespercode.trees.candidate import (
    CandidateIntegrityError,
    CandidatePostimageV1,
    CandidatePostimageSequenceV1,
    CandidateRevisionV1,
    CandidateTreeV1,
    derive_candidate_revision,
    path_collides_with_tree,
)
from src.vespercode.trees.snapshot import SnapshotFileEntryV1, SnapshotTreeV1
from src.vespercode.trees.text_classifier import (
    TextMetadataV1,
    classify_supported_text,
)
from src.vespercode.workspace.path_guard import (
    IgnoreRuleV1,
    ignore_rules_digest,
    path_is_ignored,
    protected_artifact_path,
    sensitive_path_rule_id,
)

# SPEC §1.4.4 candidate hard caps.
_MAX_PATCH_TEXT_BYTES = 131072
_MAX_SINGLE_EDITABLE_FILE_BYTES = 131072
_MAX_TOTAL_POSTIMAGE_BYTES = 131072
_MAX_NET_CHANGED_FILES = 3
_MAX_NEW_FILES = 1

CandidatePatchErrorCodeV1 = Literal[
    "PATCH_SCHEMA_INVALID",
    "UNSUPPORTED_PATCH_OPERATION",
    "STALE_CANDIDATE",
    "SENSITIVE_PATH",
    "PROTECTED_ARTIFACT_CHANGED",
    "PATCH_PATH_NOT_EDITABLE",
    "PATH_EXISTS",
    "PATH_IGNORED",
    "PATCH_CONTEXT_MISMATCH",
    "PATCH_LIMIT_EXCEEDED",
    "TREE_INTEGRITY_FAILED",
]
"""The closed candidate-patch rejection codes (SPEC §4.3 error list plus
the Task 9.D collision codes consumed here)."""


class ApplyCandidatePatchAction(BaseModel):
    """SPEC §4.2.2 closed apply-candidate-patch action envelope.

    The patch format is the closed ``UNIFIED_DIFF_V1`` literal and the
    patch text is bounded at 128 KiB of strict UTF-8; the base candidate
    digest is the 64-hex identity the whole patch must match exactly.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal[1]
    action_type: Literal["apply_candidate_patch"]
    base_candidate_digest: StrictStr
    patch_format: Literal["UNIFIED_DIFF_V1"]
    patch_text: StrictStr

    @field_validator("schema_version", mode="before")
    @classmethod
    def _schema_version_is_exact_int(cls, value: object) -> object:
        if not isinstance(value, int) or isinstance(value, bool):
            raise ValueError("schema_version must be the decimal integer 1")
        return value

    @field_validator("base_candidate_digest")
    @classmethod
    def _require_sha256_hex(cls, value: str) -> str:
        if _DIGEST_RE.fullmatch(value) is None:
            raise ValueError(
                "base_candidate_digest must be exactly 64 lowercase hexadecimal"
            )
        return value

    @field_validator("patch_text")
    @classmethod
    def _bounded_utf8_patch_text(cls, value: str) -> str:
        try:
            byte_length = len(value.encode("utf-8"))
        except UnicodeEncodeError as error:
            raise ValueError("patch_text must be strict UTF-8 text") from error
        if byte_length > _MAX_PATCH_TEXT_BYTES:
            raise ValueError("patch_text must be at most 128 KiB of UTF-8 bytes")
        return value


class CandidatePublisherPortV1(Protocol):
    """One transactional publication port for validated revisions."""

    def publish(self, revision: CandidateRevisionV1) -> None: ...


@dataclass(frozen=True)
class CandidatePatchContextV1:
    """One frozen patch context: current candidate, sealed snapshot, the
    frozen reference manifest (and its editable policy), the publisher
    port, and the sealed frozen ignore rules."""

    current: CandidateRevisionV1
    snapshot: SnapshotTreeV1
    reference: ReferenceProfileManifestV1
    publisher: CandidatePublisherPortV1
    ignore_rules: tuple[IgnoreRuleV1, ...]
    ignore_rules_digest: str

    def __post_init__(self) -> None:
        if self.ignore_rules_digest != ignore_rules_digest(self.ignore_rules):
            raise ValueError("sealed ignore facts do not match their digest")

    def with_publisher(
        self, publisher: CandidatePublisherPortV1
    ) -> CandidatePatchContextV1:
        """One copy of the frozen context with a different publisher port."""
        return replace(self, publisher=publisher)


class CandidatePatchOutcomeV1(BaseModel):
    """One closed patch outcome: PUBLISHED with the validated revision, or
    REJECTED with the stable error code and a bounded reason."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    kind: Literal["PUBLISHED", "REJECTED"]
    error_code: CandidatePatchErrorCodeV1 | None = None
    reason: str | None = None
    revision: CandidateRevisionV1 | None = None
    candidate_tree_digest: str | None = None

    @model_validator(mode="after")
    def _require_exact_outcome(self) -> CandidatePatchOutcomeV1:
        if self.kind == "PUBLISHED":
            if (
                self.error_code is not None
                or self.reason is not None
                or self.revision is None
                or self.candidate_tree_digest is None
            ):
                raise ValueError(
                    "PUBLISHED outcomes require the revision and digest and no error"
                )
        elif (
            self.error_code is None
            or self.reason is None
            or self.revision is not None
            or self.candidate_tree_digest is not None
        ):
            raise ValueError(
                "REJECTED outcomes require the error code and reason and no revision"
            )
        return self


@dataclass(frozen=True)
class _EntryApplication:
    """One closed per-entry application result.

    ``error`` is None on success (``postimage`` carries the exact applied
    bytes), ``"PATCH_CONTEXT_MISMATCH"`` when the old ranges or lines
    cannot be matched exactly (no fuzzy offset), or a bounded
    text-contract reason for unsupported base/result shapes.
    """

    postimage: bytes | None
    error: str | None


def apply_candidate_patch(
    action: ApplyCandidatePatchAction,
    current: CandidateRevisionV1,
    context: CandidatePatchContextV1,
) -> CandidatePatchOutcomeV1:
    """Apply one parsed patch exactly against the named base candidate and
    publish one validated revision or no revision.

    Check order is deterministic: patch/Schema parsing, base-candidate
    binding (STALE_CANDIDATE), policy binding (TREE_INTEGRITY_FAILED),
    per-entry path checks in SPEC §4.3 priority (sensitive, protected,
    editable, collision, ignore), exact hunk application and text
    preservation, candidate hard limits, then one atomic staging/derive
    and exactly one publication.  Any rejection publishes nothing.
    """
    parsed = parse_unified_diff_v1(action.patch_text)
    if isinstance(parsed, PatchParseFailureV1):
        return _rejected(parsed.error_code, parsed.reason)
    patch = parsed
    if action.base_candidate_digest != current.candidate_digest:
        return _rejected(
            "STALE_CANDIDATE",
            "base_candidate_digest does not equal the current candidate digest",
        )
    if (
        context.snapshot.repository_policy_digest
        != context.reference.editable_path_policy.digest
    ):
        return _rejected(
            "TREE_INTEGRITY_FAILED",
            "the snapshot does not bind the frozen editable policy digest",
        )
    if context.snapshot.root_digest != current.tree.snapshot.root_digest:
        return _rejected(
            "TREE_INTEGRITY_FAILED",
            "the context snapshot is not the current candidate's sealed snapshot",
        )
    for entry in patch.entries:
        failure = _entry_path_failure(entry, current.tree, context)
        if failure is not None:
            return failure
    postimages: list[CandidatePostimageV1] = []
    try:
        for entry in patch.entries:
            application = _apply_entry(entry, current.tree)
            if application.error is not None:
                if application.error == "PATCH_CONTEXT_MISMATCH":
                    return _rejected(
                        "PATCH_CONTEXT_MISMATCH",
                        f"the hunk at {entry.path.value!r} does not match the "
                        "base candidate exactly",
                    )
                return _rejected(
                    "UNSUPPORTED_PATCH_OPERATION",
                    f"{entry.path.value!r}: {application.error}",
                )
            assert application.postimage is not None
            postimages.append(
                CandidatePostimageV1(
                    schema_version=1,
                    operation=entry.operation,
                    path=entry.path,
                    raw_bytes=application.postimage,
                )
            )
        limit_failure = _limit_failure(tuple(postimages), current, context.snapshot)
    except CandidateIntegrityError as error:
        # A missing or drifted store object behind the sealed overlay must
        # surface as the closed tree-integrity outcome, never an exception.
        return _rejected("TREE_INTEGRITY_FAILED", str(error))
    if limit_failure is not None:
        return limit_failure
    try:
        child = derive_candidate_revision(current, tuple(postimages))
    except CandidateIntegrityError as error:
        return _rejected("TREE_INTEGRITY_FAILED", str(error))
    context.publisher.publish(child)
    return CandidatePatchOutcomeV1(
        kind="PUBLISHED",
        error_code=None,
        reason=None,
        revision=child,
        candidate_tree_digest=child.tree.digest,
    )


def _entry_path_failure(
    entry: ParsedPatchEntryV1,
    tree: CandidateTreeV1,
    context: CandidatePatchContextV1,
) -> CandidatePatchOutcomeV1 | None:
    """One closed path rejection for one entry, in SPEC §4.3 priority.

    The checks consume the Task 9.D shared fact tables (sensitive-path
    rules, protected-artifact table) and the frozen ignore rules through
    the single versioned implementations in ``workspace.path_guard``.
    """
    path = entry.path
    if sensitive_path_rule_id(path.value) is not None:
        return _rejected(
            "SENSITIVE_PATH", f"entry path {path.value!r} is a sensitive path"
        )
    if protected_artifact_path(path.value):
        return _rejected(
            "PROTECTED_ARTIFACT_CHANGED",
            f"entry path {path.value!r} is a protected artifact",
        )
    if not context.reference.editable_path_policy.matches(path, entry.operation):
        return _rejected(
            "PATCH_PATH_NOT_EDITABLE",
            f"entry path {path.value!r} is not editable for {entry.operation}",
        )
    if entry.operation == "CREATE":
        if path_collides_with_tree(tree, path):
            return _rejected(
                "PATH_EXISTS",
                f"CREATE path {path.value!r} collides with an existing "
                "candidate tree path",
            )
        if path_is_ignored(context.ignore_rules, path.value):
            return _rejected(
                "PATH_IGNORED",
                f"CREATE path {path.value!r} is ignored under the frozen rules",
            )
    elif not _tree_has_file_path(tree, path):
        return _rejected(
            "PATCH_CONTEXT_MISMATCH",
            f"REPLACE path {path.value!r} has no base bytes in the candidate tree",
        )
    return None


def _tree_has_file_path(tree: CandidateTreeV1, path: CanonicalRelativePathV1) -> bool:
    """True when *path* is an existing file path of the candidate tree."""
    return path.value in {
        candidate_path.value for candidate_path in tree.list_file_paths()
    }


def _apply_entry(entry: ParsedPatchEntryV1, tree: CandidateTreeV1) -> _EntryApplication:
    """Apply one parsed entry exactly against the candidate tree.

    The old ranges, context lines, and delete lines must match the base
    candidate bytes exactly at the declared positions — no fuzzy apply,
    no automatic offset, no conflict resolution.  The result keeps the
    base BOM, uniform newline style, and final newline; new files are
    fixed UTF-8, no BOM, LF, with a final newline.
    """
    if entry.operation == "CREATE":
        base_lines: list[str] = []
        terminator = "\n"
        base_metadata: TextMetadataV1 | None = None
    else:
        raw = tree.read_bytes(entry.path)
        classification = classify_supported_text(raw)
        if classification.kind != "TEXT_FILE":
            return _EntryApplication(
                postimage=None, error="the REPLACE base is not supported text"
            )
        base_metadata = classification.text_profile.value
        terminator = "\r\n" if base_metadata.newline == "CRLF" else "\n"
        base_lines = _split_lines(raw, terminator)
    output: list[str] = []
    position = 0
    for hunk in entry.hunks:
        # The hunk's old region starts at the zero-based index
        # ``old_start - 1``; a zero-count range uses the virtual position
        # directly (``-0,0`` before line 1, ``-2,0`` after line 2) and must
        # stay within the file (``-99,0`` on a short file is not an EOF
        # insertion — it declares a position beyond the base).
        hunk_index = hunk.old_start if hunk.old_count == 0 else hunk.old_start - 1
        if hunk_index < position:
            return _EntryApplication(postimage=None, error="PATCH_CONTEXT_MISMATCH")
        if hunk.old_count == 0:
            if hunk_index > len(base_lines):
                return _EntryApplication(postimage=None, error="PATCH_CONTEXT_MISMATCH")
        elif hunk_index + hunk.old_count > len(base_lines):
            return _EntryApplication(postimage=None, error="PATCH_CONTEXT_MISMATCH")
        # Untouched lines between the previous hunk and this one are
        # preserved exactly as they are.
        output.extend(base_lines[position:hunk_index])
        for line in hunk.lines:
            if line.kind == "ADD":
                output.append(line.text)
            else:
                if hunk_index >= len(base_lines) or base_lines[hunk_index] != line.text:
                    return _EntryApplication(
                        postimage=None, error="PATCH_CONTEXT_MISMATCH"
                    )
                if line.kind == "CONTEXT":
                    output.append(base_lines[hunk_index])
                hunk_index += 1
        position = hunk_index
    output.extend(base_lines[position:])
    postimage = (terminator.join(output) + terminator).encode("utf-8")
    result = classify_supported_text(postimage)
    if result.kind != "TEXT_FILE":
        return _EntryApplication(
            postimage=None, error="the exact application result is not supported text"
        )
    post_metadata = result.text_profile.value
    if base_metadata is None:
        if (post_metadata.encoding, post_metadata.newline) != ("UTF8", "LF"):
            return _EntryApplication(
                postimage=None,
                error="new files must be UTF-8, no BOM, LF, with a final newline",
            )
    elif (post_metadata.encoding, post_metadata.newline) != (
        base_metadata.encoding,
        base_metadata.newline,
    ):
        return _EntryApplication(
            postimage=None,
            error="the replacement must preserve the base BOM and newline style",
        )
    return _EntryApplication(postimage=postimage, error=None)


def _split_lines(raw: bytes, terminator: str) -> list[str]:
    """Split one supported-text file into its lines without terminators.

    The final newline is guaranteed by the supported-text classification,
    so the trailing empty part is dropped; each part decodes as strict
    UTF-8 (a leading BOM rides along as part of the first line's content).
    """
    separator = terminator.encode("utf-8")
    parts = raw.split(separator)
    if parts and parts[-1] == b"":
        parts = parts[:-1]
    return [part.decode("utf-8") for part in parts]


def _limit_failure(
    postimages: CandidatePostimageSequenceV1,
    current: CandidateRevisionV1,
    snapshot: SnapshotTreeV1,
) -> CandidatePatchOutcomeV1 | None:
    """One closed SPEC §1.4.4 hard-cap rejection, or None.

    The limits bind the cumulative net diff of the post-patch candidate
    relative to the Snapshot: at most 3 changed files, at most 1 new
    file, at most 128 KiB of complete postimage raw bytes in total, and
    at most 128 KiB for any single editable file.  The net diff is
    computed over the post-patch tree (a staged postimage that equals the
    snapshot bytes counts as no change).
    """
    for postimage in postimages:
        if len(postimage.raw_bytes) > _MAX_SINGLE_EDITABLE_FILE_BYTES:
            return _rejected(
                "PATCH_LIMIT_EXCEEDED",
                f"single editable file postimage at {postimage.path.value!r} "
                "exceeds 128 KiB",
            )
    snapshot_files = {
        entry.path.value
        for entry in snapshot.entries
        if isinstance(entry, SnapshotFileEntryV1)
    }
    postimage_by_path = {postimage.path.value: postimage for postimage in postimages}
    tree_files = {path.value for path in current.tree.list_file_paths()}
    changed: list[tuple[str, int, bool]] = []
    for path_value in sorted(tree_files | set(postimage_by_path)):
        staged_postimage = postimage_by_path.get(path_value)
        path = CanonicalRelativePathV1(path_value)
        if staged_postimage is not None:
            new_bytes = staged_postimage.raw_bytes
        else:
            new_bytes = current.tree.read_bytes(path)
        if path_value not in snapshot_files:
            changed.append((path_value, len(new_bytes), True))
        elif new_bytes != snapshot.read_bytes(path):
            changed.append((path_value, len(new_bytes), False))
    if len(changed) > _MAX_NET_CHANGED_FILES:
        return _rejected(
            "PATCH_LIMIT_EXCEEDED",
            f"the cumulative net diff would touch {len(changed)} files (limit 3)",
        )
    new_files = sum(1 for _, _, is_new in changed if is_new)
    if new_files > _MAX_NEW_FILES:
        return _rejected(
            "PATCH_LIMIT_EXCEEDED",
            f"the cumulative net diff would create {new_files} new files (limit 1)",
        )
    total = sum(size for _, size, _ in changed)
    if total > _MAX_TOTAL_POSTIMAGE_BYTES:
        return _rejected(
            "PATCH_LIMIT_EXCEEDED",
            f"the cumulative postimage bytes would be {total} (limit 131072)",
        )
    return None


def _rejected(
    error_code: CandidatePatchErrorCodeV1, reason: str
) -> CandidatePatchOutcomeV1:
    return CandidatePatchOutcomeV1(
        kind="REJECTED", error_code=error_code, reason=reason
    )

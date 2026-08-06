"""T18.2 legacy step 18.B: fresh identity-bound candidate materialization.

``allocate_execution_root`` creates one fresh execution root (a UUID-named
directory with a sealed identity marker) and ``materialize_candidate``
writes every verified CandidateTree content object to its exact authorized
path and bytes, then reverifies content digest, path/object identity,
tree binding, and the pre-execution root digest before any container can
start.  Every invocation uses a unique root; a missing/corrupt content
object (``OBJECT_MISSING``/``CONTENT_DIGEST_MISMATCH``), a path escape
(``PATH_ESCAPE``), a link in the root or at a materialized path
(``LINK_FOUND``), a root that is not provably allocated by this module
(``WRITABLE_SOURCE``), or a root that already holds materialized content
(``ROOT_REUSE``) fails closed with ``MaterializationError`` (SPEC §4.3
cleanup, §4.5 pre-check revalidation; GREEN-1..GREEN-4).  Container
creation, check interpretation, root reuse, and real-workspace
persistence remain out of scope.

Threat-model note: the link checks are check-then-act (``_is_link`` then
open/scandir) with a millisecond residual window on the fresh root; a
host-local attacker racing the write is outside the v1 threat model
(SPEC §5.5 defends against project code and containers, not host
processes), and the post-write regular-file re-check closes the
swap-after-write case.
"""

from __future__ import annotations

import hashlib
import os
import stat
import tempfile
import uuid
from pathlib import Path
from typing import Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    StrictStr,
    field_validator,
    model_validator,
)

from src.vespercode.canonical.digest import domain_digest
from src.vespercode.canonical.json_v1 import CanonicalValueV1
from src.vespercode.canonical.path_v1 import CanonicalRelativePathV1
from src.vespercode.contracts.evidence import _DIGEST_RE
from src.vespercode.trees.candidate import CandidateOverlayEntryV1, CandidateTreeV1
from src.vespercode.trees.content_store import ContentIntegrityError

MaterializationErrorCodeV1 = Literal[
    "OBJECT_MISSING",
    "CONTENT_DIGEST_MISMATCH",
    "PATH_ESCAPE",
    "LINK_FOUND",
    "WRITABLE_SOURCE",
    "ROOT_REUSE",
]
"""Closed materialization failures (SPEC §4.3/§4.5; GREEN-2)."""


class MaterializationError(Exception):
    """Closed failure: the fresh root or candidate bytes cannot bind."""

    def __init__(self, error_code: MaterializationErrorCodeV1, reason: str) -> None:
        super().__init__(f"{error_code}: {reason}")
        self.error_code = error_code
        self.reason = reason


# The sealed identity marker inside every execution root: its content is
# exactly the root id, so a root whose marker is missing or mismatched was
# not provably allocated by this module and is rejected as a writable
# source (an untrusted process could have created it and written bytes).
_MARKER_NAME = ".vespercode-execution-root"

# FILE_ATTRIBUTE_REPARSE_POINT: the Win32 attribute bit that marks every
# reparse point (symbolic links AND NTFS junctions) — ``os.path.islink``
# alone misses junctions on Windows.
_FILE_ATTRIBUTE_REPARSE_POINT = 0x400


def _is_link(path: Path) -> bool:
    """True when *path* is a symbolic link or junction/reparse point.

    ``os.path.islink`` does not detect NTFS junctions on Windows (the
    T09.1-repo ground truth is the handle-observed reparse tag), so the
    closed predicate also checks the Win32 reparse-point attribute bit
    when the platform exposes it; on POSIX there are no reparse points
    and ``islink`` is complete.
    """
    if os.path.islink(path):
        return True
    try:
        attributes = getattr(os.lstat(path), "st_file_attributes", 0)
    except OSError:
        # A path that cannot be stat'ed (e.g. a not-yet-written target)
        # is not a link; the caller's own existence checks own that case.
        return False
    return bool(attributes & _FILE_ATTRIBUTE_REPARSE_POINT)


# SPEC §4.3: a name whose cleanup failed cannot be reused in this process
# lifetime.  The allocator and the cleanup module consult/append this set.
_NON_REUSABLE_NAMES: set[str] = set()


def register_non_reusable_name(name: str) -> None:
    """Record one failed-cleanup identity as non-reusable for this process.

    SPEC §4.3: after a removal failure the exact name is recorded so a
    later allocation or materialization can never reuse it; the execution
    run that owns the residue stops, and v1 builds no recovery state
    machine beyond this process-lifetime guard.
    """
    _NON_REUSABLE_NAMES.add(name)


def is_non_reusable_name(name: str) -> bool:
    """True when *name* was recorded as non-reusable (SPEC §4.3)."""
    return name in _NON_REUSABLE_NAMES


class AuthorizedExecutionRootV1(BaseModel):
    """One fresh identity-bound execution root (SPEC §4.3 UUID identity).

    ``root_id`` is a 32-lowercase-hex UUID identity; ``root_path`` is the
    absolute path of the freshly allocated directory.  The model stays
    permissive on the path spelling — the closed path-escape and identity
    checks live in ``materialize_candidate`` so a tampered root can never
    be silently normalized away.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)
    root_id: StrictStr
    root_path: StrictStr

    @field_validator("root_id")
    @classmethod
    def _root_id_is_uuid_hex(cls, value: str) -> str:
        if len(value) != 32 or any(
            character not in "0123456789abcdef" for character in value
        ):
            raise ValueError(
                "root_id must be exactly 32 lowercase hexadecimal characters"
            )
        return value

    @field_validator("root_path")
    @classmethod
    def _root_path_is_non_empty(cls, value: str) -> str:
        if value == "":
            raise ValueError("root_path must not be empty")
        return value


class MaterializedFileV1(BaseModel):
    """One sealed materialization row: canonical path and exact content
    identity of the bytes written to the fresh root."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    path: StrictStr
    sha256: StrictStr
    byte_count: int

    @field_validator("path")
    @classmethod
    def _path_is_non_empty(cls, value: str) -> str:
        if value == "":
            raise ValueError("path must not be empty")
        return value

    @field_validator("sha256")
    @classmethod
    def _sha256_is_hex(cls, value: str) -> str:
        if _DIGEST_RE.fullmatch(value) is None:
            raise ValueError(
                "sha256 must be exactly 64 lowercase hexadecimal characters"
            )
        return value

    @field_validator("byte_count", mode="before")
    @classmethod
    def _byte_count_is_exact_int(cls, value: object) -> object:
        if not isinstance(value, int) or isinstance(value, bool):
            raise ValueError("byte_count must be an exact decimal integer")
        if value < 0:
            raise ValueError("byte_count must not be negative")
        return value


class MaterializedCandidateV1(BaseModel):
    """One sealed materialization: the fresh root bound to the candidate.

    Sealed value fields: ``root_id``/``root_path`` (the exact fresh
    identity-bound root), ``candidate_digest``/``snapshot_tree_digest``
    (the tree binding), ``files`` (ordered unique canonical rows with
    exact content identities), and ``pre_execution_root_digest`` (the
    §0.1 identity of the ordered materialized bytes, recomputed and
    verified by the post-run integrity step of the cleanup contract).
    """

    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal[1]
    root_id: StrictStr
    root_path: StrictStr
    candidate_digest: StrictStr
    snapshot_tree_digest: StrictStr
    files: tuple[MaterializedFileV1, ...]
    pre_execution_root_digest: StrictStr

    @field_validator("schema_version", mode="before")
    @classmethod
    def _schema_version_is_exact_int(cls, value: object) -> object:
        if not isinstance(value, int) or isinstance(value, bool):
            raise ValueError("schema_version must be the decimal integer 1")
        return value

    @field_validator(
        "candidate_digest", "snapshot_tree_digest", "pre_execution_root_digest"
    )
    @classmethod
    def _digests_are_hex(cls, value: str) -> str:
        if _DIGEST_RE.fullmatch(value) is None:
            raise ValueError(
                "digests must be exactly 64 lowercase hexadecimal characters"
            )
        return value

    @model_validator(mode="after")
    def _require_ordered_unique_rows(self) -> MaterializedCandidateV1:
        paths = [row.path for row in self.files]
        if len(set(paths)) != len(paths):
            raise ValueError("materialized rows must be unique per path")
        if paths != sorted(paths):
            raise ValueError("materialized rows must be in canonical path order")
        if self.pre_execution_root_digest != digest_materialized_candidate(
            self.root_id, self.candidate_digest, self.snapshot_tree_digest, self.files
        ):
            raise ValueError("the pre-execution root digest must bind every row")
        return self


def digest_materialized_candidate(
    root_id: str,
    candidate_digest: str,
    snapshot_tree_digest: str,
    files: tuple[MaterializedFileV1, ...],
) -> str:
    """The deterministic §0.1 pre-execution root identity: one ordered
    row per materialized path binding its exact content identity, bound to
    the fresh root id and the candidate tree identity."""
    return domain_digest(
        "MaterializedCandidateV1",
        1,
        {
            "schema_version": 1,
            "root_id": root_id,
            "candidate_digest": candidate_digest,
            "snapshot_tree_digest": snapshot_tree_digest,
            "files": tuple(_canonical_file_row(row) for row in files),
        },
    )


def _canonical_file_row(row: MaterializedFileV1) -> dict[str, CanonicalValueV1]:
    """One canonical §0.1 value for a sealed materialization row."""
    return {
        "path": row.path,
        "sha256": row.sha256,
        "byte_count": row.byte_count,
    }


def allocate_execution_root(base_dir: Path | None = None) -> AuthorizedExecutionRootV1:
    """Allocate one fresh identity-bound execution root.

    The root is a UUID-named directory under *base_dir* (default: the
    system temp directory) containing exactly the identity marker; the
    directory creation is exclusive, so a pre-existing or concurrent
    directory can never be adopted, and a name recorded as non-reusable
    (SPEC §4.3) is never chosen again.
    """
    if base_dir is None:
        base = Path(tempfile.gettempdir()) / "vespercode-execution-roots"
    else:
        base = Path(os.path.abspath(str(base_dir)))
    if _is_link(base):
        raise MaterializationError(
            "LINK_FOUND", f"the execution-root base {base} is a link"
        )
    try:
        base.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise MaterializationError(
            "WRITABLE_SOURCE", f"cannot create the execution-root base {base}: {exc}"
        ) from exc
    if not base.is_dir():
        raise MaterializationError(
            "WRITABLE_SOURCE", f"the execution-root base {base} is not a directory"
        )
    for _ in range(16):
        root_id = uuid.uuid4().hex
        if root_id in _NON_REUSABLE_NAMES:
            continue
        root_path = base / root_id
        try:
            os.mkdir(root_path)
        except FileExistsError:
            continue
        except OSError as exc:
            raise MaterializationError(
                "WRITABLE_SOURCE",
                f"cannot allocate the execution root {root_path}: {exc}",
            ) from exc
        try:
            (root_path / _MARKER_NAME).write_bytes(root_id.encode("ascii"))
        except OSError as exc:
            # A root whose identity marker cannot be sealed is residue:
            # remove the empty root (or record its name as non-reusable
            # when even that fails) and fail closed.
            try:
                os.rmdir(root_path)
            except OSError:
                register_non_reusable_name(root_id)
            raise MaterializationError(
                "WRITABLE_SOURCE",
                f"cannot seal the identity marker of execution root {root_path}: {exc}",
            ) from exc
        return AuthorizedExecutionRootV1(root_id=root_id, root_path=str(root_path))
    raise MaterializationError(
        "ROOT_REUSE", f"no fresh execution-root name is available under {base}"
    )


def materialize_candidate(
    candidate: CandidateTreeV1, root: AuthorizedExecutionRootV1
) -> MaterializedCandidateV1:
    """Materialize one verified candidate tree into its fresh root.

    Every CandidateTree content object is written to its exact authorized
    path and bytes (binary writes, real directories only, never through a
    link), then reverified: on-disk bytes, path/object identity, the tree
    binding, and the pre-execution root digest all must match the sealed
    candidate before the materialized identity is returned.  Any drift
    fails closed with ``MaterializationError`` and the partial root is
    removed (cleanup on preflight failure), so a half-written execution
    root can never reach the executor.
    """
    _verify_fresh_root(root)
    root_path = Path(root.root_path)
    written: list[tuple[str, bytes]] = []
    try:
        overlay_by_path = {entry.path.value: entry for entry in candidate.overlay}
        for path in candidate.list_file_paths():
            _require_authorized_path(path.value)
            raw = _read_exact_candidate_bytes(candidate, path, overlay_by_path)
            _write_exact(root_path, path.value, raw)
            written.append((path.value, raw))
        rows: list[MaterializedFileV1] = []
        for path_value, expected in written:
            disk = (root_path / path_value).read_bytes()
            if disk != expected:
                raise MaterializationError(
                    "CONTENT_DIGEST_MISMATCH",
                    f"materialized bytes for {path_value!r} drifted on disk",
                )
            rows.append(
                MaterializedFileV1(
                    path=path_value,
                    sha256=hashlib.sha256(disk).hexdigest(),
                    byte_count=len(disk),
                )
            )
        return MaterializedCandidateV1(
            schema_version=1,
            root_id=root.root_id,
            root_path=str(root_path),
            candidate_digest=candidate.digest,
            snapshot_tree_digest=candidate.snapshot.root_digest,
            files=tuple(rows),
            pre_execution_root_digest=digest_materialized_candidate(
                root.root_id,
                candidate.digest,
                candidate.snapshot.root_digest,
                tuple(rows),
            ),
        )
    except MaterializationError:
        _remove_partial_root(root_path)
        raise
    except BaseException as exc:
        _remove_partial_root(root_path)
        raise MaterializationError(
            "WRITABLE_SOURCE",
            f"materialization failed and the partial root was removed: {exc}",
        ) from exc


def _verify_fresh_root(root: AuthorizedExecutionRootV1) -> None:
    """Fail closed when *root* is not a provably fresh allocation.

    Ordered checks: the path is a canonical absolute path (PATH_ESCAPE),
    the root is a real directory and not a link (LINK_FOUND), the identity
    marker binds the root id (WRITABLE_SOURCE — the root was not provably
    allocated by this module), and the root contains nothing beyond the
    marker (ROOT_REUSE — it already holds materialized content).
    """
    root_path = Path(root.root_path)
    if not os.path.isabs(str(root_path)) or ".." in root_path.parts:
        raise MaterializationError(
            "PATH_ESCAPE", f"execution root path {root.root_path!r} is not canonical"
        )
    if _is_link(root_path):
        raise MaterializationError(
            "LINK_FOUND", f"execution root {root.root_path!r} is a link"
        )
    if not root_path.is_dir():
        raise MaterializationError(
            "WRITABLE_SOURCE", f"execution root {root.root_path!r} is not a directory"
        )
    marker = root_path / _MARKER_NAME
    try:
        marker_bytes = marker.read_bytes()
    except OSError:
        marker_bytes = b""
    if marker_bytes != root.root_id.encode("ascii"):
        raise MaterializationError(
            "WRITABLE_SOURCE",
            f"execution root {root.root_path!r} has no identity marker binding "
            f"root id {root.root_id!r}",
        )
    for entry in os.scandir(root_path):
        if entry.name != _MARKER_NAME:
            raise MaterializationError(
                "ROOT_REUSE",
                f"execution root {root.root_path!r} already holds {entry.name!r}",
            )
    if root.root_id in _NON_REUSABLE_NAMES:
        raise MaterializationError(
            "ROOT_REUSE", f"execution root id {root.root_id!r} is non-reusable"
        )


def _require_authorized_path(value: str) -> None:
    """Defense-in-depth path authorization for one materialized row.

    Candidate paths are already sealed ``CanonicalRelativePathV1`` values
    (no absolute, parent, drive, UNC, ADS, or backslash forms), so this is
    a closed re-check of the exact lexical form before any join or write:
    a row whose path could resolve outside the root fails closed.
    """
    if value.startswith("/") or value.startswith("\\"):
        raise MaterializationError(
            "PATH_ESCAPE", f"materialized path {value!r} is absolute"
        )
    segments = value.split("/")
    if any(segment in ("", ".", "..") for segment in segments):
        raise MaterializationError(
            "PATH_ESCAPE", f"materialized path {value!r} is malformed"
        )
    if ":" in value or "\\" in value:
        raise MaterializationError(
            "PATH_ESCAPE", f"materialized path {value!r} is not canonical"
        )


def _read_exact_candidate_bytes(
    candidate: CandidateTreeV1,
    path: CanonicalRelativePathV1,
    overlay_by_path: dict[str, CandidateOverlayEntryV1],
) -> bytes:
    """The exact sealed bytes of one candidate file, failing closed on any
    content-store failure (missing object vs. digest/size drift).

    Overlay rows read the store directly (``ContentObjectStore.get``
    raises ``ContentIntegrityError`` with one of the two sealed stable
    messages — the missing-object message or the drift message — which is
    the closed classification contract between T10.2 and this module: any
    other failure is drift and fails closed as
    ``CONTENT_DIGEST_MISMATCH``).  Snapshot rows read the embedded sealed
    bytes, which cannot fail.
    """
    entry = overlay_by_path.get(path.value)
    if entry is not None:
        try:
            return candidate.store.get(entry.content_ref)
        except ContentIntegrityError as exc:
            if "missing from the store" in str(exc):
                raise MaterializationError(
                    "OBJECT_MISSING",
                    f"the content store cannot return the object for {path.value!r}: {exc}",
                ) from exc
            raise MaterializationError(
                "CONTENT_DIGEST_MISMATCH",
                f"the content object for {path.value!r} drifted from its sealed "
                f"identity: {exc}",
            ) from exc
    return candidate.read_bytes(path)


def _write_exact(root_path: Path, value: str, raw: bytes) -> None:
    """Write one row's exact bytes at its authorized path.

    Every parent component must be a real directory (never a link), and
    the target must not be a link: a link at any component means an
    untrusted process could redirect the write outside the root, so the
    materialization fails closed with ``LINK_FOUND`` before any byte is
    written through it.
    """
    segments = value.split("/")
    current = root_path
    for segment in segments[:-1]:
        current = current / segment
        if _is_link(current):
            raise MaterializationError(
                "LINK_FOUND", f"materialized path component {current} is a link"
            )
        if current.is_dir():
            continue
        try:
            os.mkdir(current)
        except OSError as exc:
            raise MaterializationError(
                "WRITABLE_SOURCE",
                f"cannot create materialized directory {current}: {exc}",
            ) from exc
    target = root_path / value
    if _is_link(target):
        raise MaterializationError(
            "LINK_FOUND", f"materialized path {target} is a link"
        )
    try:
        with open(target, "wb") as stream:
            stream.write(raw)
    except OSError as exc:
        raise MaterializationError(
            "WRITABLE_SOURCE", f"cannot write materialized path {target}: {exc}"
        ) from exc
    if not stat.S_ISREG(os.lstat(target).st_mode):
        raise MaterializationError(
            "LINK_FOUND", f"materialized path {target} is not a regular file"
        )


def _remove_partial_root(root_path: Path) -> None:
    """Cleanup on preflight failure: remove the partial fresh root.

    The root was provably allocated by this module (identity verified
    before any write), so it is removed without following links; a removal
    failure records the name as non-reusable and fails closed, because a
    half-written execution root is residue.
    """
    try:
        _remove_tree_no_follow(root_path)
    except OSError as exc:
        register_non_reusable_name(root_path.name)
        raise MaterializationError(
            "WRITABLE_SOURCE",
            f"partial execution root {root_path} could not be removed: {exc}",
        ) from exc
    if os.path.exists(root_path) or _is_link(root_path):
        register_non_reusable_name(root_path.name)
        raise MaterializationError(
            "WRITABLE_SOURCE",
            f"partial execution root {root_path} still exists after removal",
        )


def _remove_tree_no_follow(root_path: Path) -> None:
    """Remove one owned directory tree without ever following a link.

    Every entry is classified with ``follow_symlinks=False``: links
    (symbolic links and junction/reparse points) are removed as the link
    itself, real directories are recursed and removed, and every other
    entry is unlinked — the removal never dereferences a link, so a link
    planted inside the root can never redirect removal outside it.
    """
    for entry in os.scandir(root_path):
        entry_path = Path(entry.path)
        if entry.is_dir(follow_symlinks=False) and not _is_link(entry_path):
            # The recursion removes the directory itself; never remove it
            # twice (a second rmdir would raise on the already-gone path).
            _remove_tree_no_follow(entry_path)
        else:
            # Links (symbolic links and junctions) and non-directory
            # entries are removed as the entry itself: ``os.unlink``
            # first, ``os.rmdir`` for a junction that unlink cannot take.
            try:
                os.unlink(entry_path)
            except OSError:
                os.rmdir(entry_path)
    os.rmdir(root_path)

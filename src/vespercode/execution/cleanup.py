"""T18.2 legacy step 18.D: post-execution integrity and exact cleanup.

``finalize_execution`` reverifies the Candidate and materialized
bytes/object identities after execution, then removes only the exact
container and the fresh identity-bound root without following links, and
reports one closed ``ExecutionCleanupResultV1``: container/root removal,
unchanged execution workspace, and explicit residual artifact evidence.
A post-run byte drift, a new link/device in the root, an incomplete
teardown, or a removal failure can never be hidden as success — the
result carries the exact failing flags and the residual artifact identity
(SPEC §4.3 cleanup, §4.5 post-check revalidation; GREEN-1..GREEN-4).
Check execution/outcome parsing, root reuse, and real-workspace mutation
remain out of scope.
"""

from __future__ import annotations

import hashlib
import os
import stat
from pathlib import Path
from typing import Callable, Literal, Protocol, TypeAlias, cast

from pydantic import (
    BaseModel,
    ConfigDict,
    field_validator,
    model_validator,
)

from src.vespercode.canonical.path_v1 import CanonicalRelativePathV1
from src.vespercode.contracts.evidence import ArtifactRefV1, DigestV1
from src.vespercode.execution.docker_executor import RawExecutionResultV1
from src.vespercode.execution.materialization import (
    MaterializedCandidateV1,
    _MARKER_NAME,
    _is_link,
    _remove_tree_no_follow,
    digest_materialized_candidate,
    register_non_reusable_name,
)
from src.vespercode.trees.candidate import CandidateTreeV1


class _CleanupAPIClientV1(Protocol):
    """The low-level daemon surface used for exact container removal."""

    def remove_container(self, container_id: str, force: bool = False) -> object: ...
    def inspect_container(self, container_id: str) -> object: ...


class _CleanupClientV1(Protocol):
    """The injectable client surface of the cleanup contract."""

    @property
    def api(self) -> _CleanupAPIClientV1: ...


CleanupClientFactoryV1: TypeAlias = Callable[[], _CleanupClientV1]
"""The injectable client factory: the real SDK by default, scripted fakes
in the deterministic matrix tests."""


class ExecutionCleanupResultV1(BaseModel):
    """One closed cleanup verdict for one execution.

    Sealed value fields: ``container_removed``/``materialization_removed``
    (the exact resources are gone and verified gone), ``workspace_unchanged``
    (the materialized execution workspace is byte-identical to the sealed
    candidate), and ``residual_artifact`` (present exactly when any of the
    three flags is False, identifying the first drifted or surviving
    artifact).
    """

    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal[1]
    container_removed: bool
    materialization_removed: bool
    workspace_unchanged: bool
    residual_artifact: ArtifactRefV1 | None

    @field_validator("schema_version", mode="before")
    @classmethod
    def _schema_version_is_exact_int(cls, value: object) -> object:
        if not isinstance(value, int) or isinstance(value, bool):
            raise ValueError("schema_version must be the decimal integer 1")
        return value

    @field_validator(
        "container_removed",
        "materialization_removed",
        "workspace_unchanged",
        mode="before",
    )
    @classmethod
    def _flags_are_exact_bools(cls, value: object) -> object:
        if not isinstance(value, bool):
            raise ValueError("cleanup flags must be exact booleans")
        return value

    @model_validator(mode="after")
    def _require_exact_residual_presence(self) -> ExecutionCleanupResultV1:
        all_clean = (
            self.container_removed
            and self.materialization_removed
            and self.workspace_unchanged
        )
        if all_clean and self.residual_artifact is not None:
            raise ValueError("clean results must not carry a residual artifact")
        if not all_clean and self.residual_artifact is None:
            raise ValueError("failed cleanup must carry explicit residual evidence")
        return self


def finalize_execution(
    result: RawExecutionResultV1,
    candidate: CandidateTreeV1,
    materialized: MaterializedCandidateV1,
    client_factory: CleanupClientFactoryV1 | None = None,
) -> ExecutionCleanupResultV1:
    """Reverify, remove the exact container/root, and report the verdict.

    Order: (1) the materialized workspace is reverified byte-for-byte
    against the sealed rows and the Candidate (any drift, link, device,
    or new entry makes ``workspace_unchanged`` False); (2) the exact
    container named by the raw result is removed and verified gone; (3)
    the fresh identity-bound root is removed without following links.
    Every failure is reported in the closed result — never hidden as
    success — and the first drifted/surviving artifact is bound into
    ``residual_artifact`` (SPEC §4.3).  An unavailable Docker SDK never
    raises out of this function: the container removal is reported as
    failed with the residual artifact, exactly like any other removal
    failure.
    """
    workspace_unchanged = _reverify_workspace(candidate, materialized)
    if client_factory is None:
        try:
            client = _default_client()
        except Exception:
            client = None
    else:
        client = client_factory()
    if client is None:
        container_removed = result.container_id == ""
    else:
        container_removed = _remove_container(result.container_id, client)
    materialization_removed = _remove_materialization(materialized)
    residual_artifact = _residual_artifact(
        result,
        materialized,
        workspace_unchanged=workspace_unchanged,
        container_removed=container_removed,
        materialization_removed=materialization_removed,
    )
    return ExecutionCleanupResultV1(
        schema_version=1,
        container_removed=container_removed,
        materialization_removed=materialization_removed,
        workspace_unchanged=workspace_unchanged,
        residual_artifact=residual_artifact,
    )


def _default_client() -> _CleanupClientV1:
    try:
        import docker  # type: ignore[import-untyped]
    except Exception as exc:
        raise RuntimeError("the Docker SDK is not available") from exc
    return cast(_CleanupClientV1, docker.from_env())


def _reverify_workspace(
    candidate: CandidateTreeV1, materialized: MaterializedCandidateV1
) -> bool:
    """True exactly when the materialized execution workspace is unchanged.

    Every materialized row must still sit at its exact canonical path with
    its exact sealed bytes, as a regular single-link file under real
    (never linked) directory components; the whole root tree must hold
    exactly the identity marker plus the materialized rows and their
    ancestor directories (a new link/device/file anywhere — including
    inside an existing materialized directory — is drift); and the
    pre-execution root digest must still bind the sealed rows.  An
    already-removed root is vacuously unchanged (idempotent replay).
    """
    root = Path(materialized.root_path)
    if not root.exists() and not _is_link(root):
        return True
    if _is_link(root) or not root.is_dir():
        return False
    marker = root / _MARKER_NAME
    try:
        if marker.read_bytes() != materialized.root_id.encode("ascii"):
            return False
    except OSError:
        return False
    for row in materialized.files:
        segments = row.path.split("/")
        current = root
        for segment in segments[:-1]:
            current = current / segment
            if _is_link(current) or not current.is_dir():
                return False
        path = root / row.path
        if _is_link(path):
            return False
        try:
            object_stat = os.lstat(path)
        except OSError:
            return False
        if not stat.S_ISREG(object_stat.st_mode):
            # A device/FIFO/socket or other non-regular object planted
            # during execution is drift.
            return False
        if object_stat.st_nlink > 1:
            # A hard link planted during execution is drift.
            return False
        try:
            disk = path.read_bytes()
        except OSError:
            return False
        if (
            hashlib.sha256(disk).hexdigest() != row.sha256
            or len(disk) != row.byte_count
        ):
            return False
        try:
            expected = candidate.read_bytes(CanonicalRelativePathV1(row.path))
        except Exception:
            return False
        if disk != expected:
            return False
    # The whole root tree must be exactly the marker plus the materialized
    # rows and their ancestor directories: a new file, link, or device
    # planted anywhere during execution (even inside an existing
    # materialized directory) is drift (SPEC §4.5 EXECUTION_WORKSPACE_MUTATED).
    expected_directories: set[str] = set()
    for row in materialized.files:
        segments = row.path.split("/")
        for index in range(1, len(segments)):
            expected_directories.add("/".join(segments[:index]))
    expected_files = {_MARKER_NAME} | {row.path for row in materialized.files}
    observed_directories: set[str] = set()
    observed_files: set[str] = set()
    # Note: ``os.walk(followlinks=False)`` guards descent with
    # ``os.path.islink``, which misses NTFS junctions on Windows (the
    # T09.1 ground truth), so a planted junction may be descended and its
    # target tree enumerated.  That can never produce a clean verdict:
    # the junction itself always appears as an observed directory (or
    # file) that the sealed tree does not contain, and the per-row
    # ancestor link checks above reject any junction along a materialized
    # path — the exposure is enumeration only, never a false clean.
    try:
        for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
            # Normalize the platform separators to canonical '/' paths so
            # the observed tree compares exactly against the sealed rows.
            relative = os.path.relpath(dirpath, root).replace("\\", "/")
            if relative == ".":
                relative = ""
            for name in dirnames:
                observed_directories.add(f"{relative}/{name}" if relative else name)
            for name in filenames:
                observed_files.add(f"{relative}/{name}" if relative else name)
    except OSError:
        return False
    if observed_directories != expected_directories or observed_files != expected_files:
        return False
    recomputed = digest_materialized_candidate(
        materialized.root_id,
        materialized.candidate_digest,
        materialized.snapshot_tree_digest,
        materialized.files,
    )
    return recomputed == materialized.pre_execution_root_digest


def _remove_container(container_id: str, client: _CleanupClientV1) -> bool:
    """Remove the exact container and verify it is gone.

    An empty container id (no container was ever created) is vacuously
    removed; the removal verdict is decided by the follow-up inspection,
    so a failed remove of an already-gone container is still a clean
    result (idempotent) while a still-present container is a failure.
    """
    if container_id == "":
        return True
    try:
        client.api.remove_container(container_id, force=True)
    except Exception:
        pass
    try:
        client.api.inspect_container(container_id)
        return False
    except Exception:
        return True


def _remove_materialization(materialized: MaterializedCandidateV1) -> bool:
    """Remove the exact fresh root without following links.

    SPEC §4.3: the UUID root identity is verified before removal (the
    directory name, the sealed marker, and a real non-link directory), the
    tree is removed without ever dereferencing a link, and the name of any
    un-removable root is recorded as non-reusable for this process
    lifetime.  An already-removed root is vacuously removed (idempotent).
    """
    root = Path(materialized.root_path)
    if not root.exists() and not _is_link(root):
        return True
    if root.name != materialized.root_id:
        register_non_reusable_name(root.name)
        return False
    if _is_link(root) or not root.is_dir():
        register_non_reusable_name(root.name)
        return False
    marker = root / _MARKER_NAME
    try:
        marker_bytes = marker.read_bytes()
    except OSError:
        marker_bytes = b""
    if marker_bytes != materialized.root_id.encode("ascii"):
        register_non_reusable_name(root.name)
        return False
    try:
        _remove_tree_no_follow(root)
    except OSError:
        register_non_reusable_name(materialized.root_id)
        return False
    if root.exists() or _is_link(root):
        register_non_reusable_name(materialized.root_id)
        return False
    return True


def _residual_artifact(
    result: RawExecutionResultV1,
    materialized: MaterializedCandidateV1,
    *,
    workspace_unchanged: bool,
    container_removed: bool,
    materialization_removed: bool,
) -> ArtifactRefV1 | None:
    """One explicit residual artifact, or None on a fully clean result.

    Priority: a surviving materialization root first (SPEC §4.3 records
    the exact residual path of an unremovable execution copy), then a
    surviving container, then a drifted workspace.  The artifact id names
    the exact residual identity and the digest binds the execution
    evidence that produced it.
    """
    if workspace_unchanged and container_removed and materialization_removed:
        return None
    if not materialization_removed:
        return ArtifactRefV1(
            artifact_id=f"materialization:{materialized.root_path}",
            digest=DigestV1(value=materialized.pre_execution_root_digest),
        )
    if not container_removed:
        return ArtifactRefV1(
            artifact_id=f"container:{result.container_id}",
            digest=DigestV1(value=materialized.candidate_digest),
        )
    return ArtifactRefV1(
        artifact_id=f"workspace:{materialized.root_path}",
        digest=DigestV1(value=materialized.pre_execution_root_digest),
    )

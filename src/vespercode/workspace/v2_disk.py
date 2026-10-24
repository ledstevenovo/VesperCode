"""Route A / A4: the real local-disk workspace port.

``LocalDiskWorkspacePort`` is the production implementation of the
``V2WorkspacePort`` protocol.  Every filesystem touch goes through
``WorkspaceBoundaryV2``, so confinement, reparse/symlink refusal, and file
type checks apply to reads, writes, and removals alike.

Writes are atomic per file: the content is written to a uniquely named
temporary file in the target directory, flushed and fsynced, the boundary
is rechecked immediately before the mutation, and then

- CREATE publishes with ``os.link`` (fails if the target appeared), then
  unlinks the temporary name;
- REPLACE is compare-and-publish: immediately before the atomic replace,
  the target must still hold exactly the planned expected original bytes
  (ordinary byte/text comparison, no digest), so an external change between
  preflight and publication raises ``WorkspaceContentMismatchError``
  instead of being overwritten.

A crash between the temporary write and the publish leaves at most an
orphaned ``.vespercode-v2-*.tmp`` file inside the workspace; the durable
journal in the v2 database still drives recovery.  On POSIX the parent
directory is also fsynced; Win32 does not offer this, which is documented
as a known limitation.  The module imports nothing from the v1 tree.
"""

from __future__ import annotations

import contextlib
import os
import uuid
from pathlib import Path

from vespercode.contracts.v2_writeback import (
    PlannedWriteV2,
    WorkspaceContentMismatchError,
    WriteOperationV2,
)
from vespercode.workspace.v2_boundary import (
    ResolvedPathV2,
    WorkspaceBoundaryV2,
)

_TEMP_PREFIX = ".vespercode-v2-"
_TEMP_SUFFIX = ".tmp"


class LocalDiskWorkspacePort:
    """Boundary-checked, atomic, real-filesystem workspace port."""

    def __init__(
        self,
        workspace_root: Path,
        boundary: WorkspaceBoundaryV2 | None = None,
    ) -> None:
        if not isinstance(workspace_root, Path):
            raise TypeError("workspace root must be a Path")
        self._root = workspace_root
        self._boundary = boundary or WorkspaceBoundaryV2(workspace_root)

    @property
    def workspace_root(self) -> Path:
        return self._root

    def read_text(self, path: str) -> str | None:
        """Return the exact file bytes as text, or ``None`` if cleanly absent."""

        resolved = self._boundary.check_read(path)
        if resolved is None:
            return None
        return resolved.absolute.read_bytes().decode("utf-8")

    def exists(self, path: str) -> bool:
        """True only for a readable regular file inside the workspace."""

        return self._boundary.check_read(path) is not None

    def validate(self, operation: WriteOperationV2) -> None:
        """Check a CREATE/REPLACE target without mutating anything."""

        self._boundary.check_write_target(operation.path, operation.action_type)

    def apply(self, planned: PlannedWriteV2) -> None:
        """Atomically publish a planned write after a full recheck.

        CREATE publishes with ``os.link`` (fails if the target appeared).
        REPLACE is compare-and-publish: immediately before the atomic
        replace, the target must still hold exactly the planned expected
        original bytes, so an external modification between preflight and
        publication is refused instead of overwritten.  The comparison is
        ordinary byte/text comparison; no digest is used.
        """

        operation = planned.operation
        resolved = self._boundary.check_write_target(
            operation.path, operation.action_type
        )
        parent = resolved.absolute.parent
        temp = parent / f"{_TEMP_PREFIX}{uuid.uuid4().hex}{_TEMP_SUFFIX}"
        try:
            with open(temp, "w", encoding="utf-8", newline="") as handle:
                handle.write(operation.content)
                handle.flush()
                os.fsync(handle.fileno())
            self._boundary.recheck_before_mutation(resolved, operation.action_type)
            if operation.action_type == "CREATE":
                os.link(temp, resolved.absolute)
                os.unlink(temp)
            else:
                expected_original = planned.expected_original
                if not isinstance(expected_original, str):
                    raise WorkspaceContentMismatchError(
                        "REPLACE plan carries no expected original"
                    )
                self._verify_expected_original(resolved, expected_original)
                os.replace(temp, resolved.absolute)
            if os.name == "posix":
                self._fsync_directory(parent)
        except BaseException:
            with contextlib.suppress(OSError):
                os.unlink(temp)
            raise

    def remove_expected(self, path: str, expected_content: str) -> None:
        """Delete one file only if it still holds exactly the expected bytes.

        The compare-and-delete guard for recovery rollback: ordinary
        byte/text comparison runs immediately before the unlink, so an
        external change between the recovery observation and the removal
        raises ``WorkspaceContentMismatchError`` instead of deleting the
        externally modified content.
        """

        resolved = self._boundary.check_read(path)
        if resolved is None:
            raise WorkspaceContentMismatchError(
                f"target is absent; refusing to remove: {path}"
            )
        try:
            current = resolved.absolute.read_bytes().decode("utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            raise WorkspaceContentMismatchError(
                f"target could not be compared before removal: {path}"
            ) from exc
        if current != expected_content:
            raise WorkspaceContentMismatchError(
                f"target changed after observation; refusing to remove: {path}"
            )
        resolved.absolute.unlink()

    @staticmethod
    def _verify_expected_original(resolved: ResolvedPathV2, expected: str) -> None:
        """Compare-and-publish guard for REPLACE targets."""

        try:
            current = resolved.absolute.read_bytes().decode("utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            raise WorkspaceContentMismatchError(
                "target could not be compared before replacement: "
                f"{resolved.relative.as_posix()}"
            ) from exc
        if current != expected:
            raise WorkspaceContentMismatchError(
                "target changed after preflight; refusing to overwrite: "
                f"{resolved.relative.as_posix()}"
            )

    @staticmethod
    def _fsync_directory(directory: Path) -> None:
        try:
            descriptor = os.open(directory, os.O_RDONLY)
        except OSError:
            return
        try:
            os.fsync(descriptor)
        except OSError:
            pass
        finally:
            os.close(descriptor)


__all__ = ["LocalDiskWorkspacePort"]

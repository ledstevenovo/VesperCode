"""Route A / A1: real path/object boundary for v2 filesystem access.

The boundary is the only v2 component that maps a canonical relative path
to a real filesystem object.  It fails closed on every aliasing or
traversal hazard the platform can express:

- lexical rejection of noncanonical spellings (empty, ``.``/``..``
  segments, alternate separators, drives, control characters);
- workspace confinement after full resolution;
- refusal of symlinks **and Windows reparse points** (junctions, mount
  points) in every existing path component — note ``Path.is_symlink``
  does not report junctions, so detection uses the reparse attribute;
- file type checks: read targets must be regular files, CREATE targets
  must be absent, REPLACE targets must be existing regular files, and
  parents must be real directories;
- Windows-only: reserved DOS device names and components whose trailing
  dots/spaces Win32 would silently strip.

``recheck_before_mutation`` re-runs the entire validation immediately
before a write to shrink the check-then-act (TOCTOU) window.  The module
is standard-library only and imports nothing from the v1 tree.
"""

from __future__ import annotations

import os
import stat
import sys
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from vespercode.contracts.v2_writeback import ALLOWED_WRITE_ACTION_TYPES

_IS_WINDOWS = sys.platform == "win32"
_REPARSE_POINT_ATTRIBUTE = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
_DOS_RESERVED_STEMS = frozenset(
    {"con", "prn", "aux", "nul"}
    | {f"com{number}" for number in range(1, 10)}
    | {f"lpt{number}" for number in range(1, 10)}
)


class WorkspaceBoundaryError(ValueError):
    """Fail-closed rejection of an unsafe path or filesystem object."""


@dataclass(frozen=True, slots=True)
class ResolvedPathV2:
    """A canonical relative path bound to its absolute workspace location."""

    relative: PurePosixPath
    absolute: Path


def _is_reparse_or_link(candidate: Path) -> bool:
    """True when the component is a symlink or any Windows reparse point.

    Junctions and mount points carry ``FILE_ATTRIBUTE_REPARSE_POINT``
    without ``Path.is_symlink`` reporting ``True``, so the attribute check
    is mandatory on Windows; ``os.lstat`` never follows the final component.
    """

    try:
        info = os.lstat(candidate)
    except OSError:
        return False
    if stat.S_ISLNK(info.st_mode):
        return True
    attributes = getattr(info, "st_file_attributes", 0)
    return bool(attributes & _REPARSE_POINT_ATTRIBUTE)


class WorkspaceBoundaryV2:
    """Validates and resolves v2 workspace paths against a real root."""

    def __init__(self, workspace_root: Path) -> None:
        if not isinstance(workspace_root, Path):
            raise TypeError("workspace root must be a Path")
        self._root = workspace_root

    @property
    def workspace_root(self) -> Path:
        return self._root

    def resolve(self, path: str) -> ResolvedPathV2:
        """Resolve a canonical relative path inside the workspace root.

        Every existing component is inspected with ``lstat`` so a link or
        reparse point anywhere in the chain is refused before the final
        confinement comparison runs.
        """

        relative = self._canonical_relative(path)
        if not self._root.is_dir():
            raise WorkspaceBoundaryError("workspace root is not an existing directory")
        current = self._root
        for component in relative.parts:
            child = current / component
            if _is_reparse_or_link(child):
                raise WorkspaceBoundaryError(
                    f"path passes through a link or reparse point: {component}"
                )
            current = child
        try:
            resolved_root = self._root.resolve(strict=False)
            resolved_target = current.resolve(strict=False)
        except (OSError, RuntimeError) as exc:
            raise WorkspaceBoundaryError(f"path could not be resolved: {exc}") from exc
        if resolved_target == resolved_root or resolved_root in resolved_target.parents:
            return ResolvedPathV2(relative, current)
        raise WorkspaceBoundaryError("path escapes the workspace")

    def check_read(self, path: str) -> ResolvedPathV2 | None:
        """Return the target for reading, or ``None`` when cleanly absent.

        Anything other than a clean ``FileNotFoundError`` — a directory, a
        link, an unreadable object — raises instead of returning ``None``.
        """

        resolved = self.resolve(path)
        try:
            info = os.lstat(resolved.absolute)
        except FileNotFoundError:
            return None
        except OSError as exc:
            raise WorkspaceBoundaryError(f"target is unreadable: {path}") from exc
        if not stat.S_ISREG(info.st_mode):
            raise WorkspaceBoundaryError(f"target is not a regular file: {path}")
        return resolved

    def check_write_target(self, path: str, action_type: str) -> ResolvedPathV2:
        """Validate a CREATE/REPLACE target and its parent chain."""

        if action_type not in ALLOWED_WRITE_ACTION_TYPES:
            raise WorkspaceBoundaryError(f"unsupported write action type: {action_type!r}")
        resolved = self.resolve(path)
        parent = resolved.absolute.parent
        try:
            parent_info = os.lstat(parent)
        except OSError as exc:
            raise WorkspaceBoundaryError(
                f"parent directory is missing or unreadable: {path}"
            ) from exc
        if not stat.S_ISDIR(parent_info.st_mode):
            raise WorkspaceBoundaryError(f"parent is not a directory: {path}")
        try:
            target_info = os.lstat(resolved.absolute)
        except FileNotFoundError:
            if action_type == "REPLACE":
                raise WorkspaceBoundaryError(f"REPLACE target does not exist: {path}") from None
            return resolved
        except OSError as exc:
            raise WorkspaceBoundaryError(f"target is unreadable: {path}") from exc
        if action_type == "CREATE":
            raise WorkspaceBoundaryError(f"CREATE target already exists: {path}")
        if not stat.S_ISREG(target_info.st_mode):
            raise WorkspaceBoundaryError(f"REPLACE target is not a regular file: {path}")
        return resolved

    def recheck_before_mutation(self, resolved: ResolvedPathV2, action_type: str) -> None:
        """Re-run the full write validation immediately before mutating.

        This is the TOCTOU guard: the caller validates once to plan the
        write, then rechecks right before the atomic mutation so a target
        created, deleted, replaced with a directory, or turned into a
        link in between is refused.
        """

        self.check_write_target(resolved.relative.as_posix(), action_type)

    def _canonical_relative(self, path: str) -> PurePosixPath:
        if not isinstance(path, str) or not path:
            raise WorkspaceBoundaryError("path must be a non-empty string")
        if "\x00" in path or "\r" in path or "\n" in path:
            raise WorkspaceBoundaryError("path must not contain control characters")
        if "\\" in path:
            raise WorkspaceBoundaryError("path must use '/' separators only")
        if ":" in path:
            raise WorkspaceBoundaryError("path must not contain a drive or stream separator")
        if path.startswith("/"):
            raise WorkspaceBoundaryError("path must be relative, not absolute")
        raw_parts = path.split("/")
        if any(part in {"", ".", ".."} for part in raw_parts):
            raise WorkspaceBoundaryError(
                "path must be canonical: no empty, '.', or '..' segments"
            )
        for part in raw_parts:
            if any(ord(char) < 0x20 for char in part):
                raise WorkspaceBoundaryError("path must not contain control characters")
            if _IS_WINDOWS:
                if part != part.rstrip(" ."):
                    raise WorkspaceBoundaryError(
                        "component ends with a dot or space that Win32 would strip"
                    )
                if part.split(".", 1)[0].casefold() in _DOS_RESERVED_STEMS:
                    raise WorkspaceBoundaryError(
                        f"component is a reserved device name: {part}"
                    )
        return PurePosixPath(path)


__all__ = [
    "ResolvedPathV2",
    "WorkspaceBoundaryError",
    "WorkspaceBoundaryV2",
]

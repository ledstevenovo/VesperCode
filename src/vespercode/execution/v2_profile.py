"""Route B / B4a: the v2 Docker execution profile record.

The v1 execution authority (``execution/docker_profile.py``,
``execution/docker_executor.py``, ``execution/materialization.py``,
and ``execution/cleanup.py``) is pydantic-bound and digest-pinned to
the frozen Task 2.G gate identities; it remains in the repository as
untouched read-only legacy and nothing here imports it.

The v2 execution profile is configuration identity, not an
authorization gate: an opaque ``execution_profile_id`` plus a
non-negative ``execution_profile_revision`` are the control-plane
lookup key, bound to an opaque reference profile id and revision (the
Route B1 plane), and carrying the declared execution parameters of
that revision.  There is no manifest digest, no image digest, and no
content claim anywhere in the record.

Fail-closed parameters: the profile may only declare a disabled
network, a non-root uid:gid, a read-only root filesystem, all Linux
capabilities dropped, no docker socket mount, a read-only workspace
mount, and bounded timeout/output ceilings.  The ``image_reference``
is an opaque local image token — a URL, a registry/repo/tag spelling,
or a 64-hex digest-shaped value never validates, and no field exists
for registry credentials at all.  Consumers that recorded an older
profile revision reject records that cite it (the same revision
discipline Route A/B1/B2 use); a revision change declares a new
configuration rather than verifying bytes.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, fields
from typing import Any

EXECUTION_MAX_TIMEOUT_SECONDS_V2 = 600
"""The closed upper bound of a v2 execution timeout (10 minutes)."""

EXECUTION_MAX_OUTPUT_BYTES_V2 = 4 * 1024 * 1024
"""The closed upper bound of collected execution output (4 MiB)."""

_MAX_IDENTIFIER_BYTES = 256

_IMAGE_REFERENCE_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
_NON_ROOT_USER_PATTERN = re.compile(r"^[1-9][0-9]{0,9}:[1-9][0-9]{0,9}$")

_HEX_DIGITS = frozenset("0123456789abcdefABCDEF")


def _is_digest_shaped(value: str) -> bool:
    """True for a 64-hex spelling — the v1 sha256 digest shape."""
    return len(value) == 64 and all(character in _HEX_DIGITS for character in value)


def _opaque_identifier(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")
    if len(value.encode("utf-8")) > _MAX_IDENTIFIER_BYTES:
        raise ValueError(f"{field_name} is too long")
    if _is_digest_shaped(value):
        raise ValueError(
            f"{field_name} must not be a digest-shaped value; v2 "
            "references are opaque, not content digests"
        )
    return value


def _revision(value: object, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{field_name} must be a non-negative integer")
    return value


def _image_reference(value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("image_reference must be a non-empty string")
    if _is_digest_shaped(value):
        raise ValueError(
            "image_reference must not be a digest-shaped value; v2 "
            "image references are opaque, not content digests"
        )
    if not _IMAGE_REFERENCE_PATTERN.fullmatch(value):
        raise ValueError(
            "image_reference must be an opaque local image token: no "
            "URL, registry, repository, tag, or digest spelling is "
            "accepted"
        )
    return value


def _non_root_user(value: object) -> str:
    if not isinstance(value, str) or not _NON_ROOT_USER_PATTERN.fullmatch(value):
        raise ValueError(
            "non_root_user must be a uid:gid pair of decimal ids with "
            "both ids >= 1 (the v2 execution user is never root)"
        )
    return value


def _strict_bool(value: object, field_name: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"{field_name} must be a boolean")
    return value


def _timeout_seconds(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError("timeout_seconds must be an integer number of seconds")
    if not 1 <= value <= EXECUTION_MAX_TIMEOUT_SECONDS_V2:
        raise ValueError(
            "timeout_seconds must be between 1 and "
            f"{EXECUTION_MAX_TIMEOUT_SECONDS_V2} seconds"
        )
    return value


def _max_output_bytes(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError("max_output_bytes must be an integer number of bytes")
    if not 1 <= value <= EXECUTION_MAX_OUTPUT_BYTES_V2:
        raise ValueError(
            "max_output_bytes must be between 1 and "
            f"{EXECUTION_MAX_OUTPUT_BYTES_V2} bytes"
        )
    return value


def _strict_mapping(data: object, names: tuple[str, ...]) -> dict[str, Any]:
    if not isinstance(data, Mapping):
        raise ValueError("record must be a mapping of exact fields")
    keys = set(data.keys())
    unknown = sorted(str(key) for key in keys - set(names))
    if unknown:
        raise ValueError(f"unknown fields: {unknown}")
    missing = sorted(name for name in names if name not in keys)
    if missing:
        raise ValueError(f"missing fields: {missing}")
    return {name: data[name] for name in names}


@dataclass(frozen=True, slots=True)
class ExecutionProfileRecordV2:
    """One v2 execution profile revision and its closed parameters.

    ``execution_profile_id`` and ``execution_profile_revision`` are the
    control-plane key; the reference profile binding and every
    execution parameter are the declared configuration of that
    revision — plain values compared for equality when relevant,
    never digested into an identity and never verified against
    external gate evidence.
    """

    execution_profile_id: str
    execution_profile_revision: int
    reference_profile_id: str
    reference_profile_revision: int
    image_reference: str
    network_disabled: bool
    non_root_user: str
    read_only_rootfs: bool
    all_capabilities_dropped: bool
    docker_socket_mounted: bool
    workspace_mount_read_only: bool
    timeout_seconds: int
    max_output_bytes: int

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "execution_profile_id",
            _opaque_identifier(
                self.execution_profile_id, "execution_profile_id"
            ),
        )
        object.__setattr__(
            self,
            "execution_profile_revision",
            _revision(
                self.execution_profile_revision, "execution_profile_revision"
            ),
        )
        object.__setattr__(
            self,
            "reference_profile_id",
            _opaque_identifier(self.reference_profile_id, "reference_profile_id"),
        )
        object.__setattr__(
            self,
            "reference_profile_revision",
            _revision(
                self.reference_profile_revision, "reference_profile_revision"
            ),
        )
        object.__setattr__(self, "image_reference", _image_reference(self.image_reference))
        object.__setattr__(
            self, "network_disabled", _strict_bool(self.network_disabled, "network_disabled")
        )
        object.__setattr__(self, "non_root_user", _non_root_user(self.non_root_user))
        object.__setattr__(
            self,
            "read_only_rootfs",
            _strict_bool(self.read_only_rootfs, "read_only_rootfs"),
        )
        object.__setattr__(
            self,
            "all_capabilities_dropped",
            _strict_bool(
                self.all_capabilities_dropped, "all_capabilities_dropped"
            ),
        )
        object.__setattr__(
            self,
            "docker_socket_mounted",
            _strict_bool(self.docker_socket_mounted, "docker_socket_mounted"),
        )
        object.__setattr__(
            self,
            "workspace_mount_read_only",
            _strict_bool(
                self.workspace_mount_read_only, "workspace_mount_read_only"
            ),
        )
        object.__setattr__(self, "timeout_seconds", _timeout_seconds(self.timeout_seconds))
        object.__setattr__(
            self, "max_output_bytes", _max_output_bytes(self.max_output_bytes)
        )
        # The fail-closed isolation policy: every parameter is pinned to
        # its safe value, so a profile that would widen the execution
        # boundary can never be constructed at all.
        if not self.network_disabled:
            raise ValueError(
                "network_disabled must be True; a v2 execution profile "
                "declares its container network disabled"
            )
        if not self.read_only_rootfs:
            raise ValueError(
                "read_only_rootfs must be True; a v2 execution profile "
                "declares a read-only container root filesystem"
            )
        if not self.all_capabilities_dropped:
            raise ValueError(
                "all_capabilities_dropped must be True; a v2 execution "
                "profile drops every Linux capability"
            )
        if self.docker_socket_mounted:
            raise ValueError(
                "docker_socket_mounted must be False; the host docker "
                "socket is never mounted into a v2 execution"
            )
        if not self.workspace_mount_read_only:
            raise ValueError(
                "workspace_mount_read_only must be True; the workspace "
                "bind of a v2 execution is always read-only"
            )


def execution_profile_from_mapping(
    data: Mapping[str, Any],
) -> ExecutionProfileRecordV2:
    """Parse an execution profile from an exact-field mapping, fail closed.

    Unknown fields reject — a v1 digest-shaped payload (gate digests,
    ``schema_version``, ``profile_version``, nested ``resources`` or
    ``environment`` blocks) is never accepted as a v2 execution
    profile record.
    """

    names = tuple(field.name for field in fields(ExecutionProfileRecordV2))
    values = _strict_mapping(data, names)
    return ExecutionProfileRecordV2(**values)


__all__ = (
    "EXECUTION_MAX_OUTPUT_BYTES_V2",
    "EXECUTION_MAX_TIMEOUT_SECONDS_V2",
    "ExecutionProfileRecordV2",
    "execution_profile_from_mapping",
)

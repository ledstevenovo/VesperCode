"""Route B / B1: v2 reference profile record.

The v1 reference profile (``profiles/reference.py``) is a digest-bound
manifest: its own §0.1 identity is re-bound at construction and every
field is verified against frozen Task 2.G gate digests.  That module
remains untouched read-only legacy; nothing here imports it.

The v2 reference profile record is plain configuration identity: an
opaque ``reference_profile_id`` plus a non-negative ``profile_revision``
are the lookup key, and the declared tool metadata (Python, pytest,
Ruff, Mypy versions) is carried verbatim as configuration.  There is no
manifest digest, no gate-identity verification, and no content claim:
revision changes declare a new configuration; consumers that recorded
an older revision reject records that cite it.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, fields
from typing import Any

_MAX_IDENTIFIER_BYTES = 256


def _identifier(value: str, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")
    if len(value.encode("utf-8")) > _MAX_IDENTIFIER_BYTES:
        raise ValueError(f"{field_name} is too long")
    return value


def _declared_version(value: str, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty declared version")
    if len(value.encode("utf-8")) > _MAX_IDENTIFIER_BYTES:
        raise ValueError(f"{field_name} is too long")
    return value


def _revision(value: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError("profile_revision must be a non-negative integer")
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
class ReferenceProfileRecordV2:
    """A reference profile keyed by ID + revision, declared as configuration.

    ``reference_profile_id`` and ``profile_revision`` are the control-
    plane lookup key.  The remaining fields are the declared toolchain
    configuration of that revision — ordinary strings, compared for
    equality when relevant, never digested into an identity and never
    verified against external gate evidence.
    """

    reference_profile_id: str
    profile_revision: int
    python_version: str
    pytest_version: str
    ruff_version: str
    mypy_version: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "reference_profile_id",
            _identifier(self.reference_profile_id, "reference_profile_id"),
        )
        object.__setattr__(self, "profile_revision", _revision(self.profile_revision))
        object.__setattr__(
            self,
            "python_version",
            _declared_version(self.python_version, "python_version"),
        )
        object.__setattr__(
            self,
            "pytest_version",
            _declared_version(self.pytest_version, "pytest_version"),
        )
        object.__setattr__(
            self, "ruff_version", _declared_version(self.ruff_version, "ruff_version")
        )
        object.__setattr__(
            self,
            "mypy_version",
            _declared_version(self.mypy_version, "mypy_version"),
        )


def reference_profile_from_mapping(
    data: Mapping[str, Any],
) -> ReferenceProfileRecordV2:
    """Parse a reference profile from an exact-field mapping, fail closed.

    Unknown fields reject — a v1 manifest-shaped payload (gate digests,
    ``schema_version``, ``editable_path_policy``) is never accepted as a
    v2 reference profile record.
    """

    names = tuple(field.name for field in fields(ReferenceProfileRecordV2))
    values = _strict_mapping(data, names)
    return ReferenceProfileRecordV2(
        reference_profile_id=values["reference_profile_id"],
        profile_revision=values["profile_revision"],
        python_version=values["python_version"],
        pytest_version=values["pytest_version"],
        ruff_version=values["ruff_version"],
        mypy_version=values["mypy_version"],
    )


__all__ = (
    "ReferenceProfileRecordV2",
    "reference_profile_from_mapping",
)

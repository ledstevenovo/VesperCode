"""Route B / B2: the v2 provider endpoint record.

The v1 endpoint manifest (``profiles/endpoints.py``) is a digest-bound
profile artifact; it remains untouched read-only legacy and nothing
here imports it.  The v2 provider endpoint is plain control-plane
configuration: an opaque ``endpoint_id``, the provider name it serves,
and the reference profile id/revision whose configuration the endpoint
executes.  The grant/authorization binding checks compare these
control IDs and revisions; no digest is computed or consulted, and the
endpoint record never carries a credential.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, fields
from typing import Any

_MAX_IDENTIFIER_BYTES = 256
_PROVIDER_NAME_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")


def _identifier(value: str, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")
    if len(value.encode("utf-8")) > _MAX_IDENTIFIER_BYTES:
        raise ValueError(f"{field_name} is too long")
    return value


def _provider_name(value: str) -> str:
    if not isinstance(value, str) or not _PROVIDER_NAME_PATTERN.match(value):
        raise ValueError("provider must be a short identifier")
    return value


def _revision(value: int, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{field_name} must be a non-negative integer")
    return value


def _strict_mapping(data: object, names: tuple[str, ...]) -> dict[str, Any]:
    """Require exactly the given fields: unknown or missing keys reject.

    A v1-shaped digest payload (``endpoint_digest``, ``schema_version``,
    gate digests) is rejected here as unknown fields, never accepted as
    a v2 provider endpoint record.
    """

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
class ProviderEndpointRecordV2:
    """One provider endpoint keyed by its opaque endpoint id.

    ``provider`` is the credential-provider name the endpoint serves;
    ``reference_profile_id``/``reference_profile_revision`` are the
    control-plane binding the disclosure grant must match for an
    authorization against this endpoint.  The record is declared
    configuration: it carries no addresses, no secrets, and no
    digest of anything.
    """

    endpoint_id: str
    provider: str
    reference_profile_id: str
    reference_profile_revision: int

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "endpoint_id", _identifier(self.endpoint_id, "endpoint_id")
        )
        object.__setattr__(
            self, "provider", _provider_name(self.provider)
        )
        object.__setattr__(
            self,
            "reference_profile_id",
            _identifier(self.reference_profile_id, "reference_profile_id"),
        )
        object.__setattr__(
            self,
            "reference_profile_revision",
            _revision(
                self.reference_profile_revision, "reference_profile_revision"
            ),
        )


def provider_endpoint_from_mapping(
    data: Mapping[str, Any],
) -> ProviderEndpointRecordV2:
    """Parse a provider endpoint from an exact-field mapping, fail closed."""

    names = tuple(field.name for field in fields(ProviderEndpointRecordV2))
    values = _strict_mapping(data, names)
    return ProviderEndpointRecordV2(
        endpoint_id=values["endpoint_id"],
        provider=values["provider"],
        reference_profile_id=values["reference_profile_id"],
        reference_profile_revision=values["reference_profile_revision"],
    )


__all__ = (
    "ProviderEndpointRecordV2",
    "provider_endpoint_from_mapping",
)

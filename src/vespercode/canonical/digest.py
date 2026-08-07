"""T04.2 legacy step 4.B: domain-separated SHA-256 identity computation.

Computes the sole §0.1 binding digest over the exact prefix
``UTF8("VesperCode") || 0x00 || UTF8(object_type) || 0x00 ||
ASCII(decimal_schema_version) || 0x00 || canonical_json_utf8`` and returns
64 lowercase hex characters.  A different object type or schema version can
never produce an interchangeable binding digest even for byte-identical
canonical JSON.  Time, paths, file scanning, and tool-version selection
remain out of scope (GREEN-4).
"""

from __future__ import annotations

import hashlib
from typing import Final, Mapping

from vespercode.canonical.json_v1 import (
    CanonicalValueV1,
    canonical_json_bytes,
)

_DIGEST_DOMAIN_NAME: Final = "VesperCode"


class DomainDigestErrorV1(ValueError):
    """Closed rejection for an invalid digest identity or input domain."""


def domain_digest(
    object_type: str,
    schema_version: int,
    value: Mapping[str, CanonicalValueV1],
) -> str:
    """Return the 64 lowercase-hex domain-separated SHA-256 binding identity.

    *object_type* must be the exact declared type name and *schema_version*
    a non-negative decimal; both are bound into the digest prefix.  Forbidden
    value content is rejected by the canonical encoder before any digest is
    produced.
    """
    if not isinstance(object_type, str) or not object_type:
        raise DomainDigestErrorV1("object type must be the exact declared type name")
    if not isinstance(schema_version, int) or isinstance(schema_version, bool):
        raise DomainDigestErrorV1("schema version must be a decimal integer")
    if schema_version < 0:
        raise DomainDigestErrorV1("schema version must be a non-negative decimal")
    if not isinstance(value, Mapping):
        raise DomainDigestErrorV1("digest input must be a mapping of canonical values")
    canonical_bytes = canonical_json_bytes(value)
    try:
        type_bytes = object_type.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise DomainDigestErrorV1(
            "object type must be the exact declared type name"
        ) from exc
    prefix = (
        _DIGEST_DOMAIN_NAME.encode("utf-8")
        + b"\x00"
        + type_bytes
        + b"\x00"
        + str(schema_version).encode("ascii")
        + b"\x00"
    )
    return hashlib.sha256(prefix + canonical_bytes).hexdigest()

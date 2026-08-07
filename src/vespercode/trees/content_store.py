"""T10.2 legacy step 10.A: immutable content object store.

Stores exact raw file bytes under their verified raw SHA-256 content
identity: ``put`` computes the identity first and returns an immutable
``ContentObjectRefV1`` whose byte count matches, identical bytes
deduplicate to one object, and every ``get`` rechecks digest and size
before returning bytes so corruption, drift, or a missing object fails
closed with ``ContentIntegrityError``.  ``put`` is atomic — the identity
is computed and validated before the single store assignment, so a failed
put never leaves a partial object.  Text classification, Snapshot
construction, mutable workspace reads, and edit authorization remain out
of scope (GREEN-4).
"""

from __future__ import annotations

import hashlib

from pydantic import BaseModel, ConfigDict, field_validator

from vespercode.contracts.evidence import _DIGEST_RE


class ContentIntegrityError(Exception):
    """Closed failure when bytes cannot be returned at their exact identity."""


class ContentObjectRefV1(BaseModel):
    """SPEC §0.1: one immutable content identity (SHA-256 + exact byte count)."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    sha256: str
    byte_count: int

    @field_validator("sha256", mode="before")
    @classmethod
    def _sha256_hex(cls, value: object) -> object:
        if not isinstance(value, str) or _DIGEST_RE.fullmatch(value) is None:
            raise ValueError(
                "sha256 must be exactly 64 lowercase hexadecimal characters"
            )
        return value

    @field_validator("byte_count", mode="before")
    @classmethod
    def _exact_byte_count(cls, value: object) -> object:
        if not isinstance(value, int) or isinstance(value, bool):
            raise ValueError("byte_count must be an exact decimal integer")
        if value < 0:
            raise ValueError("byte_count must not be negative")
        return value


class ContentObjectStore:
    """One content-addressed byte store for one Run's sealed raw bytes.

    The store is deliberately minimal: ``put``/``get`` are the whole
    observable surface (plus ``object_count`` for dedup observability and
    the test-only ``inject_corruption`` hook pinned by the card's exact
    RED test).  It reads and writes no filesystem path and classifies no
    bytes (GREEN-4).
    """

    def __init__(self) -> None:
        self._objects: dict[str, bytes] = {}

    @property
    def object_count(self) -> int:
        """The number of distinct stored content objects (dedup observable)."""
        return len(self._objects)

    def put(self, raw_bytes: bytes) -> ContentObjectRefV1:
        """Store exact raw bytes and return their verified immutable identity."""
        if not isinstance(raw_bytes, bytes):
            raise TypeError("content objects are exact raw bytes only")
        digest = hashlib.sha256(raw_bytes).hexdigest()
        # Atomic: the identity is complete before the single assignment, so
        # a failed put (above) never leaves a partial object; identical
        # bytes deduplicate onto the same digest key.
        self._objects[digest] = raw_bytes
        return ContentObjectRefV1(sha256=digest, byte_count=len(raw_bytes))

    def get(self, ref: ContentObjectRefV1) -> bytes:
        """Return the exact stored bytes, rechecking digest and size first.

        A missing object, digest drift, or size drift fails closed with
        ``ContentIntegrityError`` and returns no bytes.
        """
        stored = self._objects.get(ref.sha256)
        if stored is None:
            raise ContentIntegrityError(
                f"content object {ref.sha256} is missing from the store"
            )
        if hashlib.sha256(stored).hexdigest() != ref.sha256:
            raise ContentIntegrityError(
                f"content object {ref.sha256} drifted from its digest"
            )
        if len(stored) != ref.byte_count:
            raise ContentIntegrityError(
                f"content object {ref.sha256} drifted from its byte count"
            )
        return stored

    def inject_corruption(self, ref: ContentObjectRefV1, replacement: bytes) -> None:
        """Test-only hook replacing the bytes stored behind one identity.

        This is the corruption-injection surface the card's exact RED test
        requires: it makes the stored object disagree with its own sealed
        identity so the next ``get`` fails closed.
        """
        self._objects[ref.sha256] = replacement

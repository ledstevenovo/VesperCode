"""T10.2 legacy step 10.A: immutable content object store tests.

The store keeps exact raw file bytes under their verified raw SHA-256
content identity: ``put`` computes the identity and returns an immutable
``ContentObjectRefV1`` with the matching byte count, identical bytes
deduplicate, and every ``get`` rechecks digest and size before returning
bytes (registry row 10.A: put returns SHA-256 identity; identical bytes
deduplicate; get returns exact bytes; missing object or digest drift fails
closed; failed put leaves no partial object).  Text classification,
Snapshot construction, mutable workspace reads, and edit authorization
remain out of scope (GREEN-4).
"""

from __future__ import annotations

import hashlib

import pytest

# The store contracts are pydantic runtime models; the hash-locked gate
# toolchain does not install runtime dependencies, so this module skips
# cleanly there instead of failing at collection (formal env runs it fully).
pytest.importorskip("pydantic")

from pydantic import ValidationError

from src.vespercode.trees.content_store import (
    ContentIntegrityError,
    ContentObjectRefV1,
    ContentObjectStore,
)


@pytest.fixture
def store() -> ContentObjectStore:
    return ContentObjectStore()


def test_get_rejects_bytes_whose_digest_drifted(store: ContentObjectStore) -> None:
    ref = store.put(b"stable")
    store.inject_corruption(ref, b"changed")
    with pytest.raises(ContentIntegrityError):
        store.get(ref)


def test_content_store_put_get_dedup_matrix() -> None:
    """Registry row 10.A: the exact §5.1 content-store matrix.

    put returns the SHA-256 identity with a matching byte count; identical
    bytes deduplicate to one object; get returns the exact bytes; a missing
    object, digest drift, or size drift fails closed; a failed put leaves
    no partial object.
    """
    samples: tuple[bytes, ...] = (
        b"",
        b"x\n",
        b"a\r\nb\r\n",
        "你好\n".encode("utf-8"),
        b"\xef\xbb\xbf\x00\xff",
        b"\x89PNG\r\n\x1a\n",
    )
    store = ContentObjectStore()
    refs: list[ContentObjectRefV1] = []
    for raw in samples:
        ref = store.put(raw)
        assert ref.sha256 == hashlib.sha256(raw).hexdigest()
        assert ref.byte_count == len(raw)
        refs.append(ref)
        # get returns the exact bytes, byte-identical to the input.
        assert store.get(ref) == raw
    # Deduplicate: identical bytes produce the identical immutable identity
    # and do not add a second object.
    first = store.put(b"dup")
    second = store.put(b"dup")
    assert first == second
    assert first.sha256 == hashlib.sha256(b"dup").hexdigest()
    assert store.object_count == len(samples) + 1
    assert store.get(first) == b"dup"
    # Missing object fails closed.
    missing = ContentObjectRefV1(
        sha256=hashlib.sha256(b"never-sealed").hexdigest(), byte_count=11
    )
    with pytest.raises(ContentIntegrityError):
        store.get(missing)
    # Size drift fails closed even when the digest matches.
    wrong_size = ContentObjectRefV1(sha256=first.sha256, byte_count=2)
    with pytest.raises(ContentIntegrityError):
        store.get(wrong_size)
    # Digest drift fails closed (the exact RED path, matrix-observable).
    drifted_ref = store.put(b"stable")
    store.inject_corruption(drifted_ref, b"changed")
    with pytest.raises(ContentIntegrityError):
        store.get(drifted_ref)
    # A failed put leaves no partial object.
    failed = ContentObjectStore()
    with pytest.raises(TypeError):
        failed.put("not raw bytes")  # type: ignore[arg-type]
    assert failed.object_count == 0
    with pytest.raises(ContentIntegrityError):
        failed.get(first)


def test_content_object_ref_closed_schema() -> None:
    valid = ContentObjectRefV1(sha256="a" * 64, byte_count=0)
    assert valid.sha256 == "a" * 64 and valid.byte_count == 0
    invalid: tuple[dict[str, object], ...] = (
        {"sha256": "A" * 64, "byte_count": 1},  # uppercase hex
        {"sha256": "a" * 63, "byte_count": 1},  # short digest
        {"sha256": "a" * 64, "byte_count": -1},  # negative count
        {"sha256": "a" * 64, "byte_count": "5"},  # string count
        {"sha256": "a" * 64, "byte_count": True},  # bool count
        {"sha256": "a" * 64, "byte_count": 1.5},  # float count
        {"sha256": "a" * 64},  # missing byte_count
        {"sha256": "a" * 64, "byte_count": 1, "extra": 2},  # extra field
        {"sha256": b"a" * 64, "byte_count": 1},  # non-string digest
    )
    for payload in invalid:
        with pytest.raises(ValidationError):
            ContentObjectRefV1.model_validate(payload)


def test_content_object_ref_is_immutable(store: ContentObjectStore) -> None:
    ref = store.put(b"immutable")
    with pytest.raises(ValidationError):
        ref.sha256 = "b" * 64
    with pytest.raises(ValidationError):
        ref.byte_count = 0
    # get never mutates the stored object.
    assert store.get(ref) == b"immutable"
    assert store.get(ref) == b"immutable"
    assert store.object_count == 1


def test_content_object_store_owns_bytes_only() -> None:
    """GREEN-4 boundary: no text classification, no Snapshot, no path reads."""
    store = ContentObjectStore()
    ref = store.put(b"x\n")
    assert store.get(ref) == b"x\n"
    # The store exposes no path, no filesystem, and no classification API.
    assert not hasattr(store, "read_path")
    assert not hasattr(store, "classify")
    assert not hasattr(store, "create_snapshot")
    # Inputs are accepted as exact raw bytes only.
    with pytest.raises(TypeError):
        store.put(bytearray(b"x\n"))  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        store.put("x\n")  # type: ignore[arg-type]

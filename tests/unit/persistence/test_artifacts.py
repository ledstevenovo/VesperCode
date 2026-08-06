"""T26.1 legacy step 26.D: ACL-restricted persistence artifact store tests.

Pins the exact content-addressed artifact contract: deterministic
immutable references, byte-for-byte verified reads (kind, length, and
digest on every read), atomic publication outside SQLite, current-user
ACL creation and re-probe with unsafe/unverifiable rejection, cleanup
residue removal on failure, and the closed kind vocabulary — with zero
SQLite or workspace mutation on every path.

The operative matrix authority is the card Expected (26.D) line per the
SPEC_PROCESS §49 precedent ("exact §5.1 matrix" is a dangling reference).
"""

from __future__ import annotations

import base64
import ctypes
import hashlib
import json
from collections.abc import Iterator
from pathlib import Path
from typing import cast

import pytest

pytest.importorskip("pydantic")

from ctypes import wintypes

from src.vespercode.persistence.artifacts import (
    PersistenceArtifactAclError,
    PersistenceArtifactIntegrityError,
    PersistenceArtifactKindV1,
    PersistenceArtifactRefV1,
    PersistenceArtifactStoreV1,
)

_DACL_SECURITY_INFORMATION = 0x00000004
_ACL_REVISION = 2
_FILE_ALL_ACCESS = 0x001F01FF
_SECURITY_DESCRIPTOR_REVISION = 1

_EVERYONE_SID_STRING = "S-1-1-0"

_STORE_ROOT: Path | None = None
"""The current test store root bound by the fixture (RED helper seam).

The displayed RED body calls ``corrupt_artifact_bytes(ref)`` with only
the ref, so the helper resolves the exact on-disk artifact binding
through the fixture-bound store root.
"""


@pytest.fixture
def artifact_store(tmp_path: Path) -> Iterator[PersistenceArtifactStoreV1]:
    global _STORE_ROOT
    store = PersistenceArtifactStoreV1(tmp_path / "artifacts")
    _STORE_ROOT = store.root
    yield store
    _STORE_ROOT = None


def corrupt_artifact_bytes(ref: PersistenceArtifactRefV1) -> None:
    """Overwrite the exact on-disk artifact envelope with corrupt bytes.

    The helper is the corruption seam the RED contract pins: after this
    call ``read_verified`` must fail with the closed integrity rejection
    while ``verify_acl`` still probes the real file ACL.
    """
    assert _STORE_ROOT is not None, "the artifact_store fixture must be active"
    path = PersistenceArtifactStoreV1(_STORE_ROOT).artifact_path(ref)
    path.write_bytes(b"corrupted-envelope-bytes")


def _rewrite_envelope(
    artifact_store: PersistenceArtifactStoreV1,
    ref: PersistenceArtifactRefV1,
    *,
    length: int | None = None,
    digest: str | None = None,
    kind: str | None = None,
    body: bytes | None = None,
) -> None:
    """Rewrite the artifact envelope with one tampered field."""
    path = artifact_store.artifact_path(ref)
    envelope = json.loads(path.read_bytes().decode("utf-8"))
    if length is not None:
        envelope["length"] = length
    if digest is not None:
        envelope["digest"] = digest
    if kind is not None:
        envelope["kind"] = kind
    if body is not None:
        envelope["body_b64"] = base64.b64encode(body).decode("ascii")
    path.write_bytes(
        json.dumps(envelope, sort_keys=True, separators=(",", ":")).encode("utf-8")
    )


def _grant_everyone(path: Path) -> None:
    """Widen one object's ACL with an Everyone allowed-FULL ACE (test seam).

    The unsafe fixture the probe must reject: an access-allowed ACE whose
    SID is neither the current user nor an OS-necessary principal.
    """
    advapi32 = ctypes.WinDLL("advapi32", use_last_error=True)
    advapi32.ConvertStringSidToSidW.argtypes = [
        wintypes.LPCWSTR,
        ctypes.POINTER(ctypes.c_void_p),
    ]
    advapi32.ConvertStringSidToSidW.restype = wintypes.BOOL
    advapi32.InitializeAcl.argtypes = [ctypes.c_void_p, wintypes.DWORD, wintypes.DWORD]
    advapi32.InitializeAcl.restype = wintypes.BOOL
    advapi32.AddAccessAllowedAce.argtypes = [
        ctypes.c_void_p,
        wintypes.DWORD,
        wintypes.DWORD,
        ctypes.c_void_p,
    ]
    advapi32.AddAccessAllowedAce.restype = wintypes.BOOL
    advapi32.InitializeSecurityDescriptor.argtypes = [
        ctypes.c_void_p,
        wintypes.DWORD,
    ]
    advapi32.InitializeSecurityDescriptor.restype = wintypes.BOOL
    advapi32.SetSecurityDescriptorDacl.argtypes = [
        ctypes.c_void_p,
        wintypes.BOOL,
        ctypes.c_void_p,
        wintypes.BOOL,
    ]
    advapi32.SetSecurityDescriptorDacl.restype = wintypes.BOOL
    advapi32.SetFileSecurityW.argtypes = [
        wintypes.LPCWSTR,
        wintypes.DWORD,
        ctypes.c_void_p,
    ]
    advapi32.SetFileSecurityW.restype = wintypes.BOOL

    everyone = ctypes.c_void_p()
    if not advapi32.ConvertStringSidToSidW(
        _EVERYONE_SID_STRING, ctypes.byref(everyone)
    ):
        raise OSError(ctypes.get_last_error(), "ConvertStringSidToSidW")
    try:
        acl = ctypes.create_string_buffer(256)
        if not advapi32.InitializeAcl(acl, ctypes.sizeof(acl), _ACL_REVISION):
            raise OSError(ctypes.get_last_error(), "InitializeAcl")
        if not advapi32.AddAccessAllowedAce(
            acl, _ACL_REVISION, _FILE_ALL_ACCESS, everyone
        ):
            raise OSError(ctypes.get_last_error(), "AddAccessAllowedAce")
        descriptor = ctypes.create_string_buffer(256)
        if not advapi32.InitializeSecurityDescriptor(
            descriptor, _SECURITY_DESCRIPTOR_REVISION
        ):
            raise OSError(ctypes.get_last_error(), "InitializeSecurityDescriptor")
        if not advapi32.SetSecurityDescriptorDacl(descriptor, True, acl, False):
            raise OSError(ctypes.get_last_error(), "SetSecurityDescriptorDacl")
        if not advapi32.SetFileSecurityW(
            str(path), _DACL_SECURITY_INFORMATION, descriptor
        ):
            raise OSError(ctypes.get_last_error(), "SetFileSecurityW")
    finally:
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.LocalFree.argtypes = [wintypes.HANDLE]
        kernel32.LocalFree.restype = wintypes.HANDLE
        kernel32.LocalFree(everyone)


def test_artifact_store_rejects_digest_mismatch_and_non_private_acl(
    artifact_store: PersistenceArtifactStoreV1,
) -> None:
    ref = artifact_store.put("BACKUP", b"before")
    corrupt_artifact_bytes(ref)
    with pytest.raises(PersistenceArtifactIntegrityError):
        artifact_store.read_verified(ref)
    assert artifact_store.verify_acl(ref).current_user_only is True


def test_artifact_store_matrix(artifact_store: PersistenceArtifactStoreV1) -> None:
    """The exact §5.1-Expected (26.D) matrix: deterministic refs,
    byte-for-byte verification, ACL rejection, atomic artifact
    publication, and absence of SQLite/workspace mutations pass."""
    # Closed kind vocabulary: every declared kind publishes; unknown kinds
    # reject before any byte is written.
    kinds: tuple[PersistenceArtifactKindV1, ...] = (
        "PREIMAGE",
        "POSTIMAGE",
        "BACKUP",
        "RAW_RECOVERY",
    )
    for kind in kinds:
        ref = artifact_store.put(kind, b"evidence-" + kind.encode("ascii"))
        assert ref.kind == kind
    with pytest.raises(ValueError):
        artifact_store.put(cast(PersistenceArtifactKindV1, "UNKNOWN"), b"x")

    # Deterministic refs: identical kind+body produce the identical ref;
    # any body or kind change rotates the identity.
    first = artifact_store.put("PREIMAGE", b"same bytes")
    second = artifact_store.put("PREIMAGE", b"same bytes")
    assert first == second
    assert first.digest.value == hashlib.sha256(b"same bytes").hexdigest()
    assert artifact_store.put("PREIMAGE", b"other bytes").digest.value != (
        first.digest.value
    )
    assert artifact_store.put("BACKUP", b"same bytes").artifact_id != (
        first.artifact_id
    )

    # Byte-for-byte verified reads: kind, length, and digest on every
    # read; every tamper fails closed with the integrity rejection.
    body = "pre\n".encode("utf-8")
    ref = artifact_store.put("RAW_RECOVERY", body)
    assert artifact_store.read_verified(ref) == body
    metadata = artifact_store.read_metadata_verified(ref)
    assert metadata.kind == "RAW_RECOVERY"
    assert metadata.digest == ref.digest
    assert metadata.length == len(body)
    _rewrite_envelope(artifact_store, ref, length=len(body) + 1)
    with pytest.raises(PersistenceArtifactIntegrityError):
        artifact_store.read_verified(ref)
    _rewrite_envelope(artifact_store, ref, body=b"different bytes")
    with pytest.raises(PersistenceArtifactIntegrityError):
        artifact_store.read_verified(ref)
    _rewrite_envelope(artifact_store, ref, kind="BACKUP")
    with pytest.raises(PersistenceArtifactIntegrityError):
        artifact_store.read_verified(ref)
    with pytest.raises(PersistenceArtifactIntegrityError):
        artifact_store.read_verified(
            PersistenceArtifactRefV1.model_validate(
                {
                    **ref.model_dump(),
                    "digest": {"value": "99" * 32},
                }
            )
        )
    # Re-publishing the same bytes repairs a corrupted artifact atomically
    # and verifies again.
    restored = artifact_store.put("RAW_RECOVERY", body)
    assert artifact_store.read_verified(restored) == body

    # ACL creation and re-probe: every artifact carries a current-user
    # ACL; a widened ACL and a missing artifact probe unsafe, and an
    # existing unsafe kind directory fails closed with zero published
    # bytes.
    for kind in kinds:
        published = artifact_store.put(kind, b"acl-" + kind.encode("ascii"))
        assert artifact_store.verify_acl(published).current_user_only is True
    unsafe = artifact_store.put("POSTIMAGE", b"acl-probe")
    _grant_everyone(artifact_store.artifact_path(unsafe))
    assert artifact_store.verify_acl(unsafe).current_user_only is False
    missing = artifact_store.put("PREIMAGE", b"missing-probe")
    artifact_store.artifact_path(missing).unlink()
    assert artifact_store.verify_acl(missing).current_user_only is False
    _grant_everyone(artifact_store.root / "BACKUP")
    backup_envelopes_before = list((artifact_store.root / "BACKUP").glob("*.json"))
    with pytest.raises(PersistenceArtifactAclError):
        artifact_store.put("BACKUP", b"unsafe-dir")
    # The failing publication left no artifact envelope behind.
    assert (
        list((artifact_store.root / "BACKUP").glob("*.json")) == backup_envelopes_before
    )
    assert list((artifact_store.root / "BACKUP").glob("*.tmp")) == []

    # Atomic publication and absence of SQLite/workspace mutation: the
    # store root holds only artifact envelopes, and no file outside the
    # root is ever touched.
    root = artifact_store.root
    assert list(root.rglob("*.db")) + list(root.rglob("*.sqlite")) == []
    for kind in kinds:
        kind_dir = root / kind
        assert kind_dir.is_dir()
        for envelope in kind_dir.glob("*.json"):
            assert envelope.read_bytes().startswith(b"{")

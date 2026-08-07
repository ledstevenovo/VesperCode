"""T26.1 legacy step 26.D: ACL-restricted content-addressed artifact store.

Publishes exact preimage, postimage, backup, and raw-recovery bytes as
immutable content-addressed artifacts outside SQLite under the current
user's ACL: one envelope file per artifact (kind, artifact id, digest,
length, and body — never a SQLite body) at ``root/<kind>/<digest>.json``,
published atomically (temp + flush + fsync + replace), with the kind
directory and every artifact carrying a current-user-only ACL that is
re-probed on every access.  Unsafe or unverifiable ACLs fail closed with
the ``ARTIFACT_ACL_UNSAFE`` rejection and zero published bytes; no
workspace byte and no transaction state is ever touched (GREEN-4).
"""

from __future__ import annotations

import base64
import ctypes
import hashlib
import json
import os
from pathlib import Path
from typing import Final, Literal

from ctypes import wintypes

from pydantic import (
    BaseModel,
    ConfigDict,
    StrictBool,
    StrictStr,
    field_validator,
)

from vespercode.contracts.evidence import DigestV1, _DIGEST_RE

_DACL_SECURITY_INFORMATION: Final = 0x00000004
_ACL_REVISION: Final = 2
_FILE_ALL_ACCESS: Final = 0x001F01FF
_SECURITY_DESCRIPTOR_REVISION: Final = 1
_ACL_SIZE_INFORMATION: Final = 2
_ACCESS_ALLOWED_ACE_TYPE: Final = 0
_TOKEN_QUERY: Final = 0x0008
_TOKEN_USER: Final = 1
_ERROR_INSUFFICIENT_BUFFER: Final = 122
_OS_NECESSARY_SID_STRINGS: Final = ("S-1-5-18", "S-1-5-32-544")
"""SYSTEM and Administrators: the OS-necessary principals the SPEC 4.6
private-ACL bound allows beside the current user."""


class _AclSizeInformation(ctypes.Structure):
    _fields_ = [
        ("ace_count", wintypes.DWORD),
        ("acl_bytes_in_use", wintypes.DWORD),
        ("acl_bytes_free", wintypes.DWORD),
    ]


class _AceHeader(ctypes.Structure):
    _fields_ = [
        ("ace_type", wintypes.BYTE),
        ("ace_flags", wintypes.BYTE),
        ("ace_size", wintypes.WORD),
    ]


def _advapi32() -> ctypes.WinDLL:
    return ctypes.WinDLL("advapi32", use_last_error=True)


def _current_user_psid() -> tuple[int, ctypes.Array[ctypes.c_char]]:
    """The process token user SID (raw PSID value plus alive buffer).

    The token buffer must stay alive while the returned PSID is used, so
    both are returned together; the PSID identifies the exact current
    user every ACL decision binds.
    """
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.GetCurrentProcess.restype = wintypes.HANDLE
    kernel32.OpenProcessToken.argtypes = [
        wintypes.HANDLE,
        wintypes.DWORD,
        ctypes.POINTER(wintypes.HANDLE),
    ]
    kernel32.OpenProcessToken.restype = wintypes.BOOL
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL
    advapi32 = _advapi32()
    advapi32.GetTokenInformation.argtypes = [
        wintypes.HANDLE,
        ctypes.c_int,
        ctypes.c_void_p,
        wintypes.DWORD,
        ctypes.POINTER(wintypes.DWORD),
    ]
    advapi32.GetTokenInformation.restype = wintypes.BOOL
    token = wintypes.HANDLE()
    if not kernel32.OpenProcessToken(
        kernel32.GetCurrentProcess(), _TOKEN_QUERY, ctypes.byref(token)
    ):
        raise OSError(ctypes.get_last_error(), "OpenProcessToken")
    try:
        needed = wintypes.DWORD()
        advapi32.GetTokenInformation(token, _TOKEN_USER, None, 0, ctypes.byref(needed))
        buffer = ctypes.create_string_buffer(needed.value)
        if not advapi32.GetTokenInformation(
            token, _TOKEN_USER, buffer, needed.value, ctypes.byref(needed)
        ):
            raise OSError(ctypes.get_last_error(), "GetTokenInformation")
        psid = ctypes.c_void_p.from_buffer(buffer).value
        if psid is None:
            raise OSError(0, "token carries no user SID")
        # The buffer object itself (not a copy) must stay alive while the
        # returned PSID is used: the SID bytes live inside the buffer.
        return int(psid), buffer
    finally:
        if not kernel32.CloseHandle(token):
            raise OSError(ctypes.get_last_error(), "CloseHandle")


def _sid_from_string(sid_string: str) -> int:
    """One PSID value parsed from its canonical string form."""
    advapi32 = _advapi32()
    advapi32.ConvertStringSidToSidW.argtypes = [
        wintypes.LPCWSTR,
        ctypes.POINTER(ctypes.c_void_p),
    ]
    advapi32.ConvertStringSidToSidW.restype = wintypes.BOOL
    psid = ctypes.c_void_p()
    if not advapi32.ConvertStringSidToSidW(sid_string, ctypes.byref(psid)):
        raise OSError(ctypes.get_last_error(), "ConvertStringSidToSidW")
    if psid.value is None:
        raise OSError(0, "converted SID carries no pointer")
    return int(psid.value)


def _sid_equals(left: int, right: int) -> bool:
    advapi32 = _advapi32()
    advapi32.EqualSid.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
    advapi32.EqualSid.restype = wintypes.BOOL
    return bool(advapi32.EqualSid(left, right))


def _free_sid(psid: int) -> None:
    if psid:
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.LocalFree.argtypes = [wintypes.HANDLE]
        kernel32.LocalFree.restype = wintypes.HANDLE
        kernel32.LocalFree(psid)


def set_private_acl(path: Path) -> None:
    """Replace the object's DACL with a current-user-only one.

    Removes inherited access and grants full control to exactly the
    current user, SYSTEM, and Administrators (SPEC 4.6: 只允许当前用户和
    操作系统必要主体访问); raises ``OSError`` on any Win32 failure so the
    caller fails closed.
    """
    user_psid, _token_buffer = _current_user_psid()
    system_psid = _sid_from_string("S-1-5-18")
    admins_psid = _sid_from_string("S-1-5-32-544")
    advapi32 = _advapi32()
    advapi32.InitializeAcl.argtypes = [
        ctypes.c_void_p,
        wintypes.DWORD,
        wintypes.DWORD,
    ]
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
    try:
        acl = ctypes.create_string_buffer(512)
        if not advapi32.InitializeAcl(acl, ctypes.sizeof(acl), _ACL_REVISION):
            raise OSError(ctypes.get_last_error(), "InitializeAcl")
        for psid in (user_psid, system_psid, admins_psid):
            if not advapi32.AddAccessAllowedAce(
                acl, _ACL_REVISION, _FILE_ALL_ACCESS, psid
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
        _free_sid(system_psid)
        _free_sid(admins_psid)


def probe_private_acl(path: Path) -> bool:
    """Probe the object's real DACL: current-user-only, or fail closed.

    True exactly when the DACL exists and every access-allowed ACE names
    the current user or an OS-necessary principal, with the current user
    holding full control.  Any unverifiable or unsafe DACL state (missing
    descriptor, missing DACL, unknown allowed ACE, or a probe failure)
    returns False — access is never inferred from a partial probe.
    """
    advapi32 = _advapi32()
    advapi32.GetFileSecurityW.argtypes = [
        wintypes.LPCWSTR,
        wintypes.DWORD,
        ctypes.c_void_p,
        wintypes.DWORD,
        ctypes.POINTER(wintypes.DWORD),
    ]
    advapi32.GetFileSecurityW.restype = wintypes.BOOL
    advapi32.GetSecurityDescriptorDacl.argtypes = [
        ctypes.c_void_p,
        ctypes.POINTER(wintypes.BOOL),
        ctypes.POINTER(ctypes.c_void_p),
        ctypes.POINTER(wintypes.BOOL),
    ]
    advapi32.GetSecurityDescriptorDacl.restype = wintypes.BOOL
    advapi32.GetAclInformation.argtypes = [
        ctypes.c_void_p,
        ctypes.c_void_p,
        wintypes.DWORD,
        wintypes.DWORD,
    ]
    advapi32.GetAclInformation.restype = wintypes.BOOL
    advapi32.GetAce.argtypes = [
        ctypes.c_void_p,
        wintypes.DWORD,
        ctypes.POINTER(ctypes.c_void_p),
    ]
    advapi32.GetAce.restype = wintypes.BOOL
    needed = wintypes.DWORD()
    advapi32.GetFileSecurityW(
        str(path), _DACL_SECURITY_INFORMATION, None, 0, ctypes.byref(needed)
    )
    buffer = ctypes.create_string_buffer(needed.value)
    if not advapi32.GetFileSecurityW(
        str(path),
        _DACL_SECURITY_INFORMATION,
        buffer,
        needed.value,
        ctypes.byref(needed),
    ):
        return False
    present = wintypes.BOOL()
    dacl = ctypes.c_void_p()
    defaulted = wintypes.BOOL()
    if not advapi32.GetSecurityDescriptorDacl(
        buffer, ctypes.byref(present), ctypes.byref(dacl), ctypes.byref(defaulted)
    ):
        return False
    if not present.value or not dacl.value:
        return False
    info = _AclSizeInformation()
    if not advapi32.GetAclInformation(
        dacl, ctypes.byref(info), ctypes.sizeof(info), _ACL_SIZE_INFORMATION
    ):
        return False
    user_psid, _token_buffer = _current_user_psid()
    allowed_psids = [user_psid]
    for sid_string in _OS_NECESSARY_SID_STRINGS:
        allowed_psids.append(_sid_from_string(sid_string))
    try:
        all_allowed_in_set = True
        current_user_full_control = False
        for index in range(int(info.ace_count)):
            ace = ctypes.c_void_p()
            if not advapi32.GetAce(dacl, index, ctypes.byref(ace)):
                return False
            if ace.value is None:
                return False
            try:
                header = _AceHeader.from_address(int(ace.value))
                if header.ace_type != _ACCESS_ALLOWED_ACE_TYPE:
                    # Access-denied ACEs never widen access.
                    continue
                mask = wintypes.DWORD.from_address(int(ace.value) + 4).value
                if mask is None:
                    return False
                # The ACE embeds the SID structure inline after the header
                # and access mask; its address is the PSID for identity
                # checks.  Malformed DACL memory fails closed instead of
                # raising (review M-3).
                ace_sid_address = int(ace.value) + 8
            except (ValueError, TypeError, OSError):
                return False
            matches_allowed = any(
                _sid_equals(ace_sid_address, allowed) for allowed in allowed_psids
            )
            if not matches_allowed:
                all_allowed_in_set = False
            if (
                _sid_equals(ace_sid_address, user_psid)
                and (int(mask) & _FILE_ALL_ACCESS) == _FILE_ALL_ACCESS
            ):
                current_user_full_control = True
        return all_allowed_in_set and current_user_full_control
    finally:
        for psid in allowed_psids[1:]:
            _free_sid(psid)


PersistenceArtifactKindV1 = Literal["PREIMAGE", "POSTIMAGE", "BACKUP", "RAW_RECOVERY"]
"""The closed artifact kind vocabulary (SPEC 4.6 evidence bytes)."""


def _require_sha256_hex(value: str) -> str:
    if _DIGEST_RE.fullmatch(value) is None:
        raise ValueError("digest must be exactly 64 lowercase hexadecimal characters")
    return value


def _reject_coerced_schema_version(value: object) -> object:
    """Reject bool/float/string spellings of the integer schema version."""
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError("schema_version must be the decimal integer 1")
    return value


class PersistenceArtifactRefV1(BaseModel):
    """One immutable content-addressed artifact reference.

    ``artifact_id`` is the deterministic ``<kind>-<digest>`` identity and
    ``digest`` is the SHA-256 of the exact body bytes; identical kind and
    body always produce the identical reference.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal[1]
    kind: PersistenceArtifactKindV1
    artifact_id: StrictStr
    digest: DigestV1

    @field_validator("schema_version", mode="before")
    @classmethod
    def _schema_version_is_exact_int(cls, value: object) -> object:
        return _reject_coerced_schema_version(value)


class PersistenceArtifactMetadataV1(BaseModel):
    """One verified artifact-metadata fact (kind, digest, length)."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal[1]
    kind: PersistenceArtifactKindV1
    artifact_id: StrictStr
    digest: DigestV1
    length: int

    @field_validator("schema_version", mode="before")
    @classmethod
    def _schema_version_is_exact_int(cls, value: object) -> object:
        return _reject_coerced_schema_version(value)

    @field_validator("length", mode="before")
    @classmethod
    def _length_is_exact_non_negative_int(cls, value: object) -> object:
        if not isinstance(value, int) or isinstance(value, bool):
            raise ValueError("length must be a decimal integer")
        if value < 0:
            raise ValueError("length must not be negative")
        return value


class ArtifactAclResultV1(BaseModel):
    """One closed ACL probe outcome for an artifact reference."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal[1]
    artifact_id: StrictStr
    current_user_only: StrictBool

    @field_validator("schema_version", mode="before")
    @classmethod
    def _schema_version_is_exact_int(cls, value: object) -> object:
        return _reject_coerced_schema_version(value)


class PersistenceArtifactIntegrityError(ValueError):
    """Closed verified-read rejection: kind, length, or digest mismatch."""


class PersistenceArtifactAclError(ValueError):
    """Closed ACL rejection: the artifact ACL cannot be made or proven safe."""

    def __init__(self, message: str) -> None:
        super().__init__(f"ARTIFACT_ACL_UNSAFE: {message}")
        self.error_code = "ARTIFACT_ACL_UNSAFE"


class PersistenceArtifactStoreV1:
    """Content-addressed artifact store under one private root.

    The exact on-disk binding is ``root/<kind>/<digest>.json`` carrying
    the closed envelope ``{schema_version, kind, artifact_id, digest,
    length, body_b64}``; every read verifies kind, length, and digest
    before returning any byte, and every published artifact is created
    with and re-probed against a current-user-only ACL.
    """

    def __init__(self, root: Path) -> None:
        self._root = Path(root)

    @property
    def root(self) -> Path:
        """The private artifact root (outside SQLite and the workspace)."""
        return self._root

    @classmethod
    def resolve(
        cls, kind: PersistenceArtifactKindV1, digest: str
    ) -> PersistenceArtifactRefV1:
        """The deterministic reference for one kind and body digest."""
        return PersistenceArtifactRefV1(
            schema_version=1,
            kind=kind,
            artifact_id=f"{kind}-{digest}",
            digest=DigestV1(value=_require_sha256_hex(digest)),
        )

    def artifact_path(self, ref: PersistenceArtifactRefV1) -> Path:
        """The exact on-disk envelope binding of one reference."""
        return self._root / ref.kind / f"{ref.digest.value}.json"

    def _ensure_private_directory(self, directory: Path) -> None:
        """Create (or verify) one current-user-only directory before writing.

        A new directory is created with a private ACL that is re-probed
        before any artifact byte is written; an existing directory is
        only verified — a pre-existing non-private directory fails closed
        with ``ARTIFACT_ACL_UNSAFE`` instead of being silently widened
        (SPEC 4.6: 在写入前验证 ACL 只允许当前用户和操作系统必要主体访问).
        """
        if not directory.is_dir():
            directory.mkdir(parents=True, exist_ok=True)
            try:
                set_private_acl(directory)
            except OSError as exc:
                raise PersistenceArtifactAclError(
                    f"cannot secure {directory}: {exc}"
                ) from exc
            if not probe_private_acl(directory):
                raise PersistenceArtifactAclError(
                    f"cannot prove the private ACL of {directory}"
                )
            return
        if not probe_private_acl(directory):
            raise PersistenceArtifactAclError(
                f"{directory} does not carry a current-user-only ACL"
            )

    def _cleanup_failed_artifact(self, ref: PersistenceArtifactRefV1) -> None:
        """Remove an artifact that failed its ACL probe (zero residue).

        The cleanup is best-effort: a leftover artifact is a residue
        defect, but the ACL failure itself must still surface as the
        closed ``PersistenceArtifactAclError`` (review M-1) — a cleanup
        error never masks the spec-mandated ARTIFACT_ACL_UNSAFE outcome.
        """
        try:
            self.artifact_path(ref).unlink(missing_ok=True)
        except OSError:
            pass

    def put(
        self,
        kind: PersistenceArtifactKindV1,
        body: bytes,
    ) -> PersistenceArtifactRefV1:
        """Publish one artifact atomically under an immutable reference.

        The private root and kind directory are verified (or created and
        proven) before any byte is written; the envelope is published
        atomically (temp + flush + fsync + replace), then the artifact
        file receives its private ACL and is re-probed.  An unsafe or
        unproven ACL at any point fails closed with zero published bytes.
        """
        if kind not in ("PREIMAGE", "POSTIMAGE", "BACKUP", "RAW_RECOVERY"):
            raise ValueError(f"unknown artifact kind {kind!r}")
        if not isinstance(body, bytes):
            raise ValueError("artifact body must be bytes")
        ref = self.resolve(kind, hashlib.sha256(body).hexdigest())
        self._ensure_private_directory(self._root)
        kind_dir = self._root / kind
        self._ensure_private_directory(kind_dir)
        envelope = {
            "schema_version": 1,
            "kind": kind,
            "artifact_id": ref.artifact_id,
            "digest": ref.digest.value,
            "length": len(body),
            "body_b64": base64.b64encode(body).decode("ascii"),
        }
        payload = json.dumps(
            envelope, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
        tmp = kind_dir / f".{ref.digest.value}.tmp"
        try:
            with tmp.open("wb") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp, self.artifact_path(ref))
        except OSError:
            # A failed publication leaves no tmp residue (review M-1).
            try:
                tmp.unlink(missing_ok=True)
            except OSError:
                pass
            raise
        try:
            set_private_acl(self.artifact_path(ref))
        except OSError as exc:
            self._cleanup_failed_artifact(ref)
            raise PersistenceArtifactAclError(
                f"cannot secure artifact {ref.artifact_id}: {exc}"
            ) from exc
        if not probe_private_acl(self.artifact_path(ref)):
            self._cleanup_failed_artifact(ref)
            raise PersistenceArtifactAclError(
                f"cannot prove the private ACL of artifact {ref.artifact_id}"
            )
        return ref

    def read_verified(self, ref: PersistenceArtifactRefV1) -> bytes:
        """Read the exact artifact bytes, verifying kind, length, digest.

        Every integrity, parse, or binding failure raises the closed
        ``PersistenceArtifactIntegrityError`` and no byte is returned.
        """
        envelope = self._read_envelope_verified(ref)
        length_value = envelope["length"]
        if not isinstance(length_value, int) or isinstance(length_value, bool):
            raise PersistenceArtifactIntegrityError(
                f"artifact {ref.artifact_id} length is not a decimal integer"
            )
        try:
            body = base64.b64decode(str(envelope["body_b64"]), validate=True)
        except (ValueError, TypeError) as exc:
            raise PersistenceArtifactIntegrityError(
                f"artifact {ref.artifact_id} carries an invalid body"
            ) from exc
        if length_value != len(body):
            raise PersistenceArtifactIntegrityError(
                f"artifact {ref.artifact_id} length does not match its envelope"
            )
        if hashlib.sha256(body).hexdigest() != ref.digest.value:
            raise PersistenceArtifactIntegrityError(
                f"artifact {ref.artifact_id} bytes do not match the reference digest"
            )
        return body

    def read_metadata_verified(
        self, ref: PersistenceArtifactRefV1
    ) -> PersistenceArtifactMetadataV1:
        """Read one verified metadata fact without decoding the body."""
        envelope = self._read_envelope_verified(ref)
        length_value = envelope["length"]
        if not isinstance(length_value, int) or isinstance(length_value, bool):
            raise PersistenceArtifactIntegrityError(
                f"artifact {ref.artifact_id} length is not a decimal integer"
            )
        return PersistenceArtifactMetadataV1(
            schema_version=1,
            kind=ref.kind,
            artifact_id=ref.artifact_id,
            digest=ref.digest,
            length=length_value,
        )

    def verify_acl(self, ref: PersistenceArtifactRefV1) -> ArtifactAclResultV1:
        """Re-probe the artifact's real ACL and return the closed outcome."""
        current_user_only = probe_private_acl(self.artifact_path(ref))
        return ArtifactAclResultV1(
            schema_version=1,
            artifact_id=ref.artifact_id,
            current_user_only=current_user_only,
        )

    def _read_envelope_verified(
        self, ref: PersistenceArtifactRefV1
    ) -> dict[str, object]:
        """Parse and verify one artifact envelope against the reference."""
        path = self.artifact_path(ref)
        try:
            raw = path.read_bytes()
        except OSError as exc:
            raise PersistenceArtifactIntegrityError(
                f"artifact {ref.artifact_id} cannot be read"
            ) from exc
        try:
            envelope = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise PersistenceArtifactIntegrityError(
                f"artifact {ref.artifact_id} carries an unreadable envelope"
            ) from exc
        if not isinstance(envelope, dict) or set(envelope) != {
            "schema_version",
            "kind",
            "artifact_id",
            "digest",
            "length",
            "body_b64",
        }:
            raise PersistenceArtifactIntegrityError(
                f"artifact {ref.artifact_id} carries an invalid envelope"
            )
        schema_version = envelope["schema_version"]
        if not isinstance(schema_version, int) or isinstance(schema_version, bool):
            raise PersistenceArtifactIntegrityError(
                f"artifact {ref.artifact_id} carries an invalid schema version"
            )
        if schema_version != 1:
            raise PersistenceArtifactIntegrityError(
                f"artifact {ref.artifact_id} carries an unsupported schema"
            )
        if str(envelope["kind"]) != ref.kind:
            raise PersistenceArtifactIntegrityError(
                f"artifact {ref.artifact_id} kind does not match its reference"
            )
        if str(envelope["artifact_id"]) != ref.artifact_id:
            raise PersistenceArtifactIntegrityError(
                f"artifact {ref.artifact_id} identity does not match its reference"
            )
        if str(envelope["digest"]) != ref.digest.value:
            raise PersistenceArtifactIntegrityError(
                f"artifact {ref.artifact_id} digest does not match its reference"
            )
        if not isinstance(envelope["length"], int) or isinstance(
            envelope["length"], bool
        ):
            raise PersistenceArtifactIntegrityError(
                f"artifact {ref.artifact_id} length is not a decimal integer"
            )
        if int(envelope["length"]) < 0:
            raise PersistenceArtifactIntegrityError(
                f"artifact {ref.artifact_id} length must not be negative"
            )
        return envelope

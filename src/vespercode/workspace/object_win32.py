"""T09.1 legacy step 9.A: handle-derived Win32 final-object identity.

``inspect_workspace_object`` opens one canonical repository-relative path
with real Win32 handles and seals a ``FinalObjectIdentityV1`` with
ancestry, kind, reparse, ADS, link, and ACL facts.  Every unprovable,
aliased, reparse, ADS, hard-linked, wrong-kind, volume-drifted, or
root-escaping object rejects through the stable closed
``WorkspaceObjectRejectedV1`` raised by the identity module; lexical
identity alone never authorizes.

The sealed root identity is re-verified against the live directory on
every inspection (volume, final file id, final path, kind, and digest),
so a root that drifts after resolution rejects every child inspection.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Literal, NoReturn

from pydantic import BaseModel, ConfigDict, StrictBool, StrictStr, field_validator

from vespercode.canonical.digest import domain_digest
from vespercode.canonical.json_v1 import CanonicalValueV1
from vespercode.canonical.path_v1 import CanonicalRelativePathV1
from vespercode.contracts.evidence import _DIGEST_RE
from vespercode.workspace.identity_win32 import (
    WorkspaceIdentityV1,
    WorkspaceObjectRejectedV1,
    WorkspaceObjectRejectionCodeV1,
    _ERROR_ACCESS_DENIED,
    _ERROR_FILE_NOT_FOUND,
    _ERROR_PATH_NOT_FOUND,
    _HandleIdentityV1,
    _acl_is_observable as _acl_is_observable,
    _close_handle_or_reject,
    _has_named_alternate_data_stream,
    _identity_from_handle,
    _open_handle,
)

WorkspaceObjectKindV1 = Literal["FILE", "DIRECTORY"]
"""The closed set of supported Win32 workspace object kinds (SPEC §1.4.3)."""


def _reject(error_code: WorkspaceObjectRejectionCodeV1, reason: str) -> NoReturn:
    raise WorkspaceObjectRejectedV1(error_code, reason)


def _reject_coerced_schema_version(value: object) -> object:
    """Reject bool/float/string spellings of the integer schema version."""
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError("schema_version must be the decimal integer 1")
    return value


def _require_32_hex(value: str) -> str:
    if len(value) != 32 or any(
        character not in "0123456789abcdef" for character in value
    ):
        raise ValueError("file id must be exactly 32 lowercase hexadecimal characters")
    return value


def _require_sha256_hex(value: str) -> str:
    if _DIGEST_RE.fullmatch(value) is None:
        raise ValueError("digest must be exactly 64 lowercase hexadecimal characters")
    return value


def _final_identity_body(
    identity: FinalObjectIdentityV1,
) -> dict[str, CanonicalValueV1]:
    return {
        "canonical_relative_path": identity.canonical_relative_path,
        "final_absolute_path": identity.final_absolute_path,
        "volume_serial_number": identity.volume_serial_number,
        "file_id_128_hex": identity.file_id_128_hex,
        "object_kind": identity.object_kind,
        "link_count": identity.link_count,
        "reparse_tag": identity.reparse_tag,
        "has_alternate_data_streams": identity.has_alternate_data_streams,
        "acl_observable": identity.acl_observable,
        "root_ancestry_proven": identity.root_ancestry_proven,
    }


def digest_final_object_identity(identity: FinalObjectIdentityV1) -> str:
    """The SPEC §0.1 identity of every exact field except the digest."""
    return domain_digest(
        "FinalObjectIdentityV1",
        identity.schema_version,
        _final_identity_body(identity),
    )


class FinalObjectIdentityV1(BaseModel):
    """The sealed handle-derived identity of one workspace object.

    The identity binds the canonical lexical path, the final absolute
    path observed through the handle, the volume and 128-bit final object
    file id, kind, link count, reparse tag, named-stream presence, ACL
    observability, and the proven root ancestry fact.  ``digest`` is the
    §0.1 identity of every preceding field.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal[1]
    canonical_relative_path: StrictStr
    final_absolute_path: StrictStr
    volume_serial_number: int
    file_id_128_hex: StrictStr
    object_kind: Literal["FILE", "DIRECTORY"]
    link_count: int
    reparse_tag: int
    has_alternate_data_streams: StrictBool
    acl_observable: StrictBool
    root_ancestry_proven: StrictBool
    digest: StrictStr

    @field_validator("schema_version", mode="before")
    @classmethod
    def _schema_version_is_exact_int(cls, value: object) -> object:
        return _reject_coerced_schema_version(value)

    @field_validator("volume_serial_number", "link_count", "reparse_tag", mode="before")
    @classmethod
    def _exact_non_negative_int(cls, value: object) -> object:
        if not isinstance(value, int) or isinstance(value, bool):
            raise ValueError("integer fields must be exact decimal integers")
        if value < 0:
            raise ValueError("integer fields must not be negative")
        return value

    @field_validator("file_id_128_hex")
    @classmethod
    def _file_id_has_exact_form(cls, value: str) -> str:
        return _require_32_hex(value)

    @field_validator("digest")
    @classmethod
    def _digest_has_exact_form(cls, value: str) -> str:
        return _require_sha256_hex(value)

    def verify_integrity(self) -> None:
        """Fail closed unless the digest still binds every other field."""
        if self.digest != digest_final_object_identity(self):
            raise ValueError(
                "final object identity digest no longer binds its exact fields"
            )


def _verify_live_root(root: WorkspaceIdentityV1, root_path: Path) -> str:
    """Re-verify the sealed root identity against the live directory.

    Returns the raw final path of the root (original case) for exact
    child-path comparison.  Every drift rejects with a stable closed
    code before any child object is inspected.
    """
    try:
        handle = _open_handle(root_path, open_reparse_point=True)
    except OSError as error:
        if error.errno in (_ERROR_FILE_NOT_FOUND, _ERROR_PATH_NOT_FOUND):
            _reject(
                "WORKSPACE_OBJECT_IDENTITY_UNPROVEN",
                f"workspace root {root_path} no longer exists",
            )
        if error.errno == _ERROR_ACCESS_DENIED:
            _reject(
                "WORKSPACE_OBJECT_ACL_UNPROVEN",
                f"workspace root {root_path} is not observable",
            )
        _reject(
            "WORKSPACE_OBJECT_IDENTITY_UNPROVEN",
            f"cannot open workspace root {root_path}",
        )
    try:
        try:
            facts = _identity_from_handle(handle)
        except OSError as error:
            raise WorkspaceObjectRejectedV1(
                "WORKSPACE_OBJECT_IDENTITY_UNPROVEN", str(error)
            ) from error
    finally:
        _close_handle_or_reject(handle)
    if facts.reparse_tag != 0:
        _reject(
            "UNSUPPORTED_WORKSPACE_OBJECT",
            f"workspace root {root_path} became a reparse point",
        )
    if facts.object_kind != "DIRECTORY":
        _reject(
            "WORKSPACE_OBJECT_IDENTITY_UNPROVEN",
            f"workspace root {root_path} is no longer a directory",
        )
    if facts.volume_serial_number != root.volume_serial_number:
        _reject(
            "WORKSPACE_OBJECT_VOLUME_MISMATCH",
            "workspace root volume drifted from the sealed identity",
        )
    if facts.file_id_128_hex != root.final_object_file_id_128_hex:
        _reject(
            "WORKSPACE_OBJECT_IDENTITY_UNPROVEN",
            "workspace root final object drifted from the sealed identity",
        )
    if os.path.normcase(facts.final_path) != os.path.normcase(
        root.canonical_absolute_path
    ):
        _reject(
            "WORKSPACE_OBJECT_IDENTITY_UNPROVEN",
            "workspace root final path drifted from the sealed identity",
        )
    try:
        root.verify_integrity()
    except ValueError as error:
        raise WorkspaceObjectRejectedV1(
            "WORKSPACE_OBJECT_IDENTITY_UNPROVEN", str(error)
        ) from error
    return facts.final_path


def inspect_workspace_object(
    root: WorkspaceIdentityV1, path: CanonicalRelativePathV1
) -> FinalObjectIdentityV1:
    """Inspect one canonical path and seal its final-object identity.

    The sealed root identity is re-verified against the live directory
    first; then the child object is opened with a real handle and its
    final path, volume, file id, kind, link count, reparse tag, named
    streams, and ACL observability are sealed.  Reparse, ADS, hard-link,
    alias, volume, ACL, and root-escape facts reject with stable closed
    errors.
    """
    root_path = Path(root.canonical_absolute_path)
    root_final_path = _verify_live_root(root, root_path)
    child_path = root_path / path.value
    try:
        handle = _open_handle(child_path, open_reparse_point=True)
    except OSError as error:
        if error.errno in (_ERROR_FILE_NOT_FOUND, _ERROR_PATH_NOT_FOUND):
            _reject("WORKSPACE_OBJECT_NOT_FOUND", f"{path.value!r} does not exist")
        _reject(
            "WORKSPACE_OBJECT_IDENTITY_UNPROVEN",
            f"cannot open {path.value!r}: {error}",
        )
    try:
        try:
            facts = _identity_from_handle(handle)
        except OSError as error:
            raise WorkspaceObjectRejectedV1(
                "WORKSPACE_OBJECT_IDENTITY_UNPROVEN", str(error)
            ) from error
    finally:
        _close_handle_or_reject(handle)
    if facts.reparse_tag != 0:
        _reject(
            "UNSUPPORTED_WORKSPACE_OBJECT",
            f"{path.value!r} is a reparse point",
        )
    _verify_ancestry_and_alias(facts, root_final_path, path)
    if facts.object_kind == "FILE" and facts.link_count != 1:
        _reject(
            "UNSUPPORTED_WORKSPACE_OBJECT",
            f"{path.value!r} has link count {facts.link_count}",
        )
    has_ads = _has_named_alternate_data_stream(child_path)
    if has_ads:
        _reject(
            "UNSUPPORTED_WORKSPACE_OBJECT",
            f"{path.value!r} carries a named alternate data stream",
        )
    acl_observable = _acl_is_observable(child_path)
    if not acl_observable:
        _reject(
            "WORKSPACE_OBJECT_ACL_UNPROVEN",
            f"the ACL of {path.value!r} is not observable",
        )
    draft = FinalObjectIdentityV1.model_validate(
        {
            "schema_version": 1,
            "canonical_relative_path": path.value,
            "final_absolute_path": facts.final_path,
            "volume_serial_number": facts.volume_serial_number,
            "file_id_128_hex": facts.file_id_128_hex,
            "object_kind": facts.object_kind,
            "link_count": facts.link_count,
            "reparse_tag": facts.reparse_tag,
            "has_alternate_data_streams": has_ads,
            "acl_observable": acl_observable,
            "root_ancestry_proven": True,
            "digest": "0" * 64,
        }
    )
    return draft.model_copy(update={"digest": digest_final_object_identity(draft)})


def _verify_ancestry_and_alias(
    facts: _HandleIdentityV1,
    root_final_path: str,
    path: CanonicalRelativePathV1,
) -> None:
    """Prove the child final path lies under the root and is not an alias.

    The alias check is byte-exact against the requested lexical spelling:
    Windows resolves a case-folded (or Unicode-normalized) alias to the
    same final object, whose final path then differs from the exact
    ``root_final_path + sep + lexical`` spelling.
    """
    # ``rstrip("\\")`` keeps drive-root workspaces (final path ``C:\``)
    # from producing a doubled separator.
    expected = root_final_path.rstrip("\\") + "\\" + path.value.replace("/", "\\")
    if facts.final_path != expected:
        if os.path.normcase(facts.final_path) == os.path.normcase(expected):
            _reject(
                "PATH_ALIAS_COLLISION",
                f"{path.value!r} aliases the existing object {facts.final_path!r}",
            )
        _reject(
            "WORKSPACE_OBJECT_IDENTITY_UNPROVEN",
            f"final path {facts.final_path!r} does not match the requested "
            f"{expected!r}",
        )
    try:
        common = os.path.commonpath(
            [os.path.normcase(facts.final_path), os.path.normcase(root_final_path)]
        )
    except ValueError:
        _reject(
            "PATH_OUTSIDE_WORKSPACE",
            f"{path.value!r} resolves outside the workspace volume",
        )
    if common != os.path.normcase(root_final_path):
        _reject(
            "PATH_OUTSIDE_WORKSPACE",
            f"{path.value!r} resolves outside the workspace root",
        )

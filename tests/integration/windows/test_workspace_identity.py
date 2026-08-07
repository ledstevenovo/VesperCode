"""T09.1 legacy step 9.A domain: Win32 workspace-identity resolution.

Runs only under ``-m windows_integration`` on the project Windows host.
Proves that ``resolve_workspace_identity`` binds one canonical absolute
path, volume identity, and final directory object identity from real
Win32 handles deterministically, and that every sealed root identity
rejects tampering.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from collections.abc import Iterator
from pathlib import Path

import pytest

from vespercode.canonical.path_v1 import CanonicalRelativePathV1
from vespercode.workspace.identity_win32 import (
    WorkspaceIdentityV1,
    WorkspaceObjectRejectedV1,
    resolve_workspace_identity,
)
from vespercode.workspace.object_win32 import inspect_workspace_object

pytestmark = pytest.mark.windows_integration


def _make_junction(link: Path, target: Path) -> None:
    result = subprocess.run(
        ["cmd", "/c", "mklink", "/J", str(link), str(target)],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr


def _populate(root: Path) -> None:
    (root / "safe.txt").write_text("safe\n", encoding="utf-8")
    nested = root / "nested"
    nested.mkdir()
    (nested / "deep.txt").write_text("deep\n", encoding="utf-8")


@pytest.fixture
def workspace_root() -> Iterator[Path]:
    root = Path(tempfile.mkdtemp(prefix="vesper_identity_"))
    _populate(root)
    try:
        yield root
    finally:
        shutil.rmtree(root, ignore_errors=True)
        assert not root.exists(), "workspace residue remains"


def test_resolve_workspace_identity_binds_real_handle_facts(
    workspace_root: Path,
) -> None:
    identity = resolve_workspace_identity(workspace_root)
    assert identity.final_object_kind == "DIRECTORY"
    assert os.path.normcase(identity.canonical_absolute_path) == os.path.normcase(
        str(workspace_root.resolve())
    )
    assert identity.volume_serial_number > 0
    assert len(identity.final_object_file_id_128_hex) == 32
    assert identity.link_count >= 1
    assert identity.acl_observable is True
    assert len(identity.digest) == 64
    identity.verify_integrity()


def test_resolve_workspace_identity_is_deterministic(workspace_root: Path) -> None:
    first = resolve_workspace_identity(workspace_root)
    second = resolve_workspace_identity(workspace_root)
    assert first == second
    assert first.digest == second.digest


def test_resolve_rejects_missing_root(workspace_root: Path) -> None:
    with pytest.raises(WorkspaceObjectRejectedV1) as error:
        resolve_workspace_identity(workspace_root / "does-not-exist")
    assert error.value.error_code == "WORKSPACE_ROOT_NOT_FOUND"


def test_resolve_rejects_file_root(workspace_root: Path) -> None:
    with pytest.raises(WorkspaceObjectRejectedV1) as error:
        resolve_workspace_identity(workspace_root / "safe.txt")
    assert error.value.error_code == "WORKSPACE_ROOT_NOT_DIRECTORY"


def test_resolve_rejects_reparse_root(workspace_root: Path) -> None:
    _make_junction(workspace_root / "reparse-root", workspace_root / "nested")
    with pytest.raises(WorkspaceObjectRejectedV1) as error:
        resolve_workspace_identity(workspace_root / "reparse-root")
    assert error.value.error_code == "UNSUPPORTED_WORKSPACE_OBJECT"


def test_identity_verify_rejects_tampered_digest(workspace_root: Path) -> None:
    identity = resolve_workspace_identity(workspace_root)
    tampered = identity.model_copy(update={"digest": "0" * 64})
    with pytest.raises(ValueError, match="digest"):
        tampered.verify_integrity()


def test_identity_digest_binds_every_field(workspace_root: Path) -> None:
    identity = resolve_workspace_identity(workspace_root)
    base = {
        "schema_version": 1,
        "canonical_absolute_path": identity.canonical_absolute_path,
        "volume_serial_number": identity.volume_serial_number,
        "final_object_file_id_128_hex": identity.final_object_file_id_128_hex,
        "final_object_kind": "DIRECTORY",
        "link_count": identity.link_count,
        "acl_observable": identity.acl_observable,
        "digest": identity.digest,
    }
    updates = {
        "canonical_absolute_path": identity.canonical_absolute_path + "_alt",
        "volume_serial_number": identity.volume_serial_number + 1,
        "final_object_file_id_128_hex": "0" * 32,
        "link_count": identity.link_count + 1,
        "acl_observable": not identity.acl_observable,
    }
    for field, value in updates.items():
        tampered = WorkspaceIdentityV1.model_validate({**base, field: value})
        with pytest.raises(ValueError, match="digest"):
            tampered.verify_integrity()
    # The sealed root kind is closed: a file-kind root never constructs.
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        WorkspaceIdentityV1.model_validate({**base, "final_object_kind": "FILE"})


def test_inspect_roundtrip_binds_lexical_and_final_identity(
    workspace_root: Path,
) -> None:
    identity = resolve_workspace_identity(workspace_root)
    inspected = inspect_workspace_object(identity, CanonicalRelativePathV1("safe.txt"))
    assert inspected.canonical_relative_path == "safe.txt"
    assert inspected.object_kind == "FILE"
    assert inspected.final_absolute_path.endswith("safe.txt")
    inspected.verify_integrity()

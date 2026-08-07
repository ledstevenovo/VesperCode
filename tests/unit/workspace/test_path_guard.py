"""T09.1 legacy step 9.D: handle-bound existing/create path authorization.

``PathGuard`` combines canonical lexical paths (Task 4.D), handle-derived
final-object/root facts (Task 9.A observation port), sealed Git/ignore
facts (Task 9.C), sensitive-path and protected-artifact rules, and the
frozen editable policy into authorized existing/create handles.  The
offline tests inject a deterministic fake object inspector; the real
Win32 inspector is bound by default in production (GREEN-4 boundary).
"""

from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Final, Literal, cast

import pytest

pytest.importorskip("pydantic")

from vespercode.canonical.path_v1 import CanonicalRelativePathV1
from vespercode.profiles.registry import build_profile_registry
from vespercode.workspace.git_preflight import GitPreflightResultV1
from vespercode.workspace.identity_win32 import (
    WorkspaceIdentityV1,
    WorkspaceObjectRejectedV1,
    digest_workspace_identity,
)
from vespercode.workspace.object_win32 import FinalObjectIdentityV1
from vespercode.workspace.path_guard import (
    AuthorizedObjectHandleV1,
    AuthorizedParentHandleV1,
    IgnoreRuleV1,
    PathGuard,
    SealedGitFactsV1,
    ignore_rules_digest,
)

_IGNORE_RULES: Final = (
    IgnoreRuleV1(
        schema_version=1,
        source="GITIGNORE",
        base_directory="",
        pattern="*.pyc",
        negated=False,
        directory_only=False,
    ),
)

# The matcher-shape rules pinned against real ``git check-ignore`` in the
# 9.C preflight and re-pinned here for the CREATE gate: ``**`` at the
# start, ``**`` in the middle, anchored leading-slash, and anchored
# directory-only patterns.
_EXTENDED_IGNORE_RULES: Final = (
    IgnoreRuleV1(
        schema_version=1,
        source="GITIGNORE",
        base_directory="",
        pattern="**/*.pyc",
        negated=False,
        directory_only=False,
    ),
    IgnoreRuleV1(
        schema_version=1,
        source="GITIGNORE",
        base_directory="",
        pattern="**/tmp",
        negated=False,
        directory_only=False,
    ),
    IgnoreRuleV1(
        schema_version=1,
        source="GITIGNORE",
        base_directory="",
        pattern="/src/venv",
        negated=False,
        directory_only=False,
    ),
    IgnoreRuleV1(
        schema_version=1,
        source="GITIGNORE",
        base_directory="",
        pattern="src/generated",
        negated=False,
        directory_only=True,
    ),
)


@dataclass(frozen=True)
class FakeObject:
    """One fake final object with exactly the facts PathGuard consumes."""

    kind: Literal["FILE", "DIRECTORY"]
    link_count: int = 1
    reparse_tag: int = 0
    has_alternate_data_streams: bool = False
    acl_observable: bool = True


class FakeObjectInspector:
    """A deterministic offline object inspector over one fake workspace.

    The fake filesystem is case-insensitive like NTFS: a request whose
    spelling differs from the stored object (but casefolds to it) is an
    alias and rejects with ``PATH_ALIAS_COLLISION``; exact spellings of a
    stored object resolve to a sealed ``FinalObjectIdentityV1`` under the
    root; absent paths raise ``WORKSPACE_OBJECT_NOT_FOUND``; objects with
    reparse tags or link counts above one reject like Task 9.A.  A
    ``volume_offset`` simulates an object living on another volume so the
    guard's own fact re-verification can be pinned.
    """

    def __init__(
        self, root_identity: WorkspaceIdentityV1, volume_offset: int = 0
    ) -> None:
        self._root = root_identity
        self._volume_offset = volume_offset
        self._objects: dict[str, FakeObject] = {}

    def add(self, path: str, obj: FakeObject) -> None:
        self._objects[path] = obj

    def __call__(
        self,
        root: WorkspaceIdentityV1,
        path: CanonicalRelativePathV1,
    ) -> FinalObjectIdentityV1:
        if root != self._root:
            raise WorkspaceObjectRejectedV1(
                "WORKSPACE_OBJECT_IDENTITY_UNPROVEN", "root identity mismatch"
            )
        if path.value in self._objects:
            obj = self._objects[path.value]
            if obj.reparse_tag != 0:
                raise WorkspaceObjectRejectedV1(
                    "UNSUPPORTED_WORKSPACE_OBJECT", "reparse object"
                )
            if obj.kind == "FILE" and obj.link_count > 1:
                raise WorkspaceObjectRejectedV1(
                    "UNSUPPORTED_WORKSPACE_OBJECT", "hard-linked object"
                )
            file_id = hashlib.sha256(path.value.encode("utf-8")).hexdigest()[:32]
            identity = FinalObjectIdentityV1(
                schema_version=1,
                canonical_relative_path=path.value,
                final_absolute_path=os.path.join(
                    self._root.canonical_absolute_path, path.value
                ),
                volume_serial_number=(
                    self._root.volume_serial_number + self._volume_offset
                ),
                file_id_128_hex=file_id,
                object_kind=obj.kind,
                link_count=obj.link_count,
                reparse_tag=obj.reparse_tag,
                has_alternate_data_streams=obj.has_alternate_data_streams,
                acl_observable=obj.acl_observable,
                root_ancestry_proven=True,
                digest="0" * 64,
            )
            return identity.model_copy(
                update={"digest": digest_final_object_identity(identity)}
            )
        folded = {key.casefold(): key for key in self._objects}
        alias = folded.get(path.value.casefold())
        if alias is not None and alias != path.value:
            raise WorkspaceObjectRejectedV1(
                "PATH_ALIAS_COLLISION", f"{path.value!r} aliases {alias!r}"
            )
        raise WorkspaceObjectRejectedV1(
            "WORKSPACE_OBJECT_NOT_FOUND", f"{path.value!r} is absent"
        )


def digest_final_object_identity(identity: FinalObjectIdentityV1) -> str:
    """The §0.1 identity of one final object (mirrors object_win32)."""
    from vespercode.canonical.digest import domain_digest

    return domain_digest(
        "FinalObjectIdentityV1",
        identity.schema_version,
        {
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
        },
    )


def _root_identity(root: Path) -> WorkspaceIdentityV1:
    draft = WorkspaceIdentityV1.model_validate(
        {
            "schema_version": 1,
            "canonical_absolute_path": os.path.normcase(os.path.abspath(str(root))),
            "volume_serial_number": 7,
            "final_object_file_id_128_hex": "1" * 32,
            "final_object_kind": "DIRECTORY",
            "link_count": 1,
            "acl_observable": True,
            "digest": "0" * 64,
        }
    )
    return draft.model_copy(update={"digest": digest_workspace_identity(draft)})


def _git_facts(policy_digest: str) -> GitPreflightResultV1:
    """One sealed supported preflight result over the fake workspace."""
    return GitPreflightResultV1(
        schema_version=1,
        kind="SUPPORTED",
        error_code=None,
        reason=None,
        head_commit_digest="0" * 40,
        index_digest="0" * 64,
        worktree_digest="0" * 64,
        ignore_rules_digest=ignore_rules_digest(_IGNORE_RULES),
        attributes_digest="0" * 64,
        config_digest="0" * 64,
        ignore_rules=_IGNORE_RULES,
        repository_policy_digest=policy_digest,
        core_autocrlf_enabled=False,
        core_eol_enabled=False,
        external_attributesfile=False,
        external_excludesfile=False,
        conversion_attributes_present=False,
        tracked_file_count=3,
        tracked_byte_count=30,
    )


_current: tuple[PathGuard, FakeObjectInspector, WorkspaceIdentityV1] | None = None


def workspace_identity() -> WorkspaceIdentityV1:
    """The sealed root identity of the active fixture workspace."""
    assert _current is not None, "workspace_identity() requires the path_guard fixture"
    return _current[2]


def canonical_path(value: str) -> CanonicalRelativePathV1:
    """One validated canonical relative path (Task 4.D contract)."""
    return CanonicalRelativePathV1(value)


@pytest.fixture
def fake_inspector(path_guard: PathGuard) -> FakeObjectInspector:
    """The fake object inspector bound to the active fixture guard."""
    assert _current is not None, "fake_inspector requires the path_guard fixture"
    return _current[1]


@pytest.fixture
def path_guard(tmp_path: Path) -> PathGuard:
    """One guard over a fake workspace with src/a.py, protected, and
    sensitive objects present, bound to the frozen reference policy."""
    global _current
    root_identity = _root_identity(tmp_path / "workspace")
    inspector = FakeObjectInspector(root_identity)
    inspector.add("src", FakeObject("DIRECTORY"))
    inspector.add("src/a.py", FakeObject("FILE"))
    inspector.add("tests", FakeObject("DIRECTORY"))
    inspector.add("tests/test_a.py", FakeObject("FILE"))
    inspector.add("README.md", FakeObject("FILE"))
    inspector.add("a.py", FakeObject("FILE"))
    inspector.add("src/pkg", FakeObject("DIRECTORY"))
    inspector.add("src/pkg/x.py", FakeObject("FILE"))
    reference = build_profile_registry().resolve_reference("python-src-py312-v1")
    guard = PathGuard(
        git_facts=cast(
            SealedGitFactsV1, _git_facts(reference.editable_path_policy.digest)
        ),
        reference=reference,
        inspector=inspector,
    )
    _current = (guard, inspector, root_identity)
    return guard


def test_create_rejects_case_alias_of_existing_path(path_guard: PathGuard) -> None:
    result = path_guard.authorize_create(
        workspace_identity(), canonical_path("src/A.py")
    )
    assert result.error_code == "PATH_ALIAS_COLLISION"
    assert result.authorized_parent is None


def test_path_authorization_existing_create_matrix(
    path_guard: PathGuard, fake_inspector: FakeObjectInspector
) -> None:
    """Existing/create matrix (Expected 9.D: 0) — every 9.D row pinned.

    Rows follow the PLAN registry 9.D authority: existing paths require
    exact canonical identity; CREATE rejects case aliases and existing
    objects; parent/device/link escapes and non-editable paths are denied
    with zero filesystem mutation (PathGuard never touches the workspace).
    """
    root = workspace_identity()
    inspector = fake_inspector

    # Existing path with exact canonical identity => AUTHORIZED.
    existing = path_guard.authorize_existing(root, canonical_path("src/a.py"), "FILE")
    assert isinstance(existing, AuthorizedObjectHandleV1)
    assert existing.kind == "AUTHORIZED"
    assert existing.error_code is None
    assert existing.authorized_object is not None
    assert existing.authorized_object.object_kind == "FILE"

    # Existing directory with exact canonical identity => AUTHORIZED.
    directory = path_guard.authorize_existing(
        root, canonical_path("src/pkg"), "DIRECTORY"
    )
    assert directory.kind == "AUTHORIZED"
    assert directory.authorized_object is not None
    assert directory.authorized_object.object_kind == "DIRECTORY"

    # Wrong expected kind => WORKSPACE_OBJECT_WRONG_KIND.
    wrong_kind = path_guard.authorize_existing(
        root, canonical_path("src/a.py"), "DIRECTORY"
    )
    assert wrong_kind.kind == "REJECTED"
    assert wrong_kind.error_code == "WORKSPACE_OBJECT_WRONG_KIND"
    assert wrong_kind.authorized_object is None

    # Existing reparse object => UNSUPPORTED_WORKSPACE_OBJECT (9.A fact).
    inspector.add("src/link.py", FakeObject("FILE", reparse_tag=0xA0000003))
    reparse = path_guard.authorize_existing(root, canonical_path("src/link.py"), "FILE")
    assert reparse.kind == "REJECTED"
    assert reparse.error_code == "UNSUPPORTED_WORKSPACE_OBJECT"

    # Existing hard-linked object => UNSUPPORTED_WORKSPACE_OBJECT.
    inspector.add("src/hard.py", FakeObject("FILE", link_count=2))
    hard = path_guard.authorize_existing(root, canonical_path("src/hard.py"), "FILE")
    assert hard.kind == "REJECTED"
    assert hard.error_code == "UNSUPPORTED_WORKSPACE_OBJECT"

    # Absent object => WORKSPACE_OBJECT_NOT_FOUND.
    absent = path_guard.authorize_existing(root, canonical_path("src/nope.py"), "FILE")
    assert absent.kind == "REJECTED"
    assert absent.error_code == "WORKSPACE_OBJECT_NOT_FOUND"

    # Sensitive existing path (.env) => PATH_SENSITIVE.
    inspector.add(".env", FakeObject("FILE"))
    sensitive = path_guard.authorize_existing(root, canonical_path(".env"), "FILE")
    assert sensitive.kind == "REJECTED"
    assert sensitive.error_code == "PATH_SENSITIVE"

    # Protected existing path (tests/**) => PROTECTED_ARTIFACT_CHANGED.
    protected = path_guard.authorize_existing(
        root, canonical_path("tests/test_a.py"), "FILE"
    )
    assert protected.kind == "REJECTED"
    assert protected.error_code == "PROTECTED_ARTIFACT_CHANGED"

    # Non-editable existing path (README.md) => PATCH_PATH_NOT_EDITABLE.
    noneditable = path_guard.authorize_existing(
        root, canonical_path("README.md"), "FILE"
    )
    assert noneditable.kind == "REJECTED"
    assert noneditable.error_code == "PATCH_PATH_NOT_EDITABLE"

    # CREATE of an exact existing object => PATH_EXISTS.
    exists = path_guard.authorize_create(root, canonical_path("src/a.py"))
    assert isinstance(exists, AuthorizedParentHandleV1)
    assert exists.kind == "REJECTED"
    assert exists.error_code == "PATH_EXISTS"
    assert exists.authorized_parent is None

    # CREATE with a missing parent directory => PATH_PARENT_NOT_FOUND.
    missing_parent = path_guard.authorize_create(
        root, canonical_path("src/newdir/x.py")
    )
    assert missing_parent.kind == "REJECTED"
    assert missing_parent.error_code == "PATH_PARENT_NOT_FOUND"

    # CREATE under a file parent (editable path, file ancestor) =>
    # PATH_PARENT_NOT_DIRECTORY.
    file_parent = path_guard.authorize_create(root, canonical_path("src/a.py/x.py"))
    assert file_parent.kind == "REJECTED"
    assert file_parent.error_code == "PATH_PARENT_NOT_DIRECTORY"

    # CREATE of a non-editable path => PATCH_PATH_NOT_EDITABLE.
    docs = path_guard.authorize_create(root, canonical_path("docs/x.md"))
    assert docs.kind == "REJECTED"
    assert docs.error_code == "PATCH_PATH_NOT_EDITABLE"

    # CREATE of a sensitive path => PATH_SENSITIVE.
    env_create = path_guard.authorize_create(root, canonical_path("src/.env"))
    assert env_create.kind == "REJECTED"
    assert env_create.error_code == "PATH_SENSITIVE"

    # CREATE of a protected path => PROTECTED_ARTIFACT_CHANGED.
    tests_create = path_guard.authorize_create(root, canonical_path("tests/x.py"))
    assert tests_create.kind == "REJECTED"
    assert tests_create.error_code == "PROTECTED_ARTIFACT_CHANGED"

    # CREATE of an ignored path under the sealed ignore rules => PATH_IGNORED.
    ignored = path_guard.authorize_create(root, canonical_path("src/compiled.pyc"))
    assert ignored.kind == "REJECTED"
    assert ignored.error_code == "PATH_IGNORED"

    # The extended matcher shapes (pinned against real git check-ignore)
    # never fail open on the CREATE gate: `**` at the start, `**` in the
    # middle, an anchored leading-slash pattern, and an anchored
    # directory-only pattern all reject.
    extended_facts = _git_facts(path_guard.reference.editable_path_policy.digest)
    extended_facts = extended_facts.model_copy(
        update={"ignore_rules": _EXTENDED_IGNORE_RULES}
    )
    extended_facts = extended_facts.model_copy(
        update={"ignore_rules_digest": ignore_rules_digest(_EXTENDED_IGNORE_RULES)}
    )
    extended_guard = PathGuard(
        git_facts=cast(SealedGitFactsV1, extended_facts),
        reference=path_guard.reference,
        inspector=inspector,
    )
    for ignored_path in (
        "src/compiled.pyc",  # **/*.pyc
        "src/pkg/compiled.pyc",  # **/*.pyc at depth
        "src/pkg/tmp/x.py",  # **/tmp in the middle
        "src/venv/x.py",  # /src/venv anchored
        "src/generated/x.py",  # src/generated/ anchored directory-only
    ):
        blocked = extended_guard.authorize_create(root, canonical_path(ignored_path))
        assert blocked.kind == "REJECTED"
        assert blocked.error_code == "PATH_IGNORED", ignored_path
    # The same matcher leaves a non-matching editable path alone.
    allowed = extended_guard.authorize_create(root, canonical_path("src/pkg/new.py"))
    assert allowed.kind == "AUTHORIZED"

    # CREATE with a parent whose volume drifts from the root => the guard's
    # own fact re-verification rejects the returned identity.
    drift_inspector = FakeObjectInspector(workspace_identity(), volume_offset=1000)
    drift_inspector.add("src", FakeObject("DIRECTORY"))
    drifted_guard = PathGuard(
        git_facts=path_guard.git_facts,
        reference=path_guard.reference,
        inspector=drift_inspector,
    )
    drift_parent = drifted_guard.authorize_create(root, canonical_path("src/n.py"))
    assert drift_parent.kind == "REJECTED"
    assert drift_parent.error_code == "WORKSPACE_OBJECT_VOLUME_MISMATCH"

    # Policy-digest drift between the sealed git facts and the frozen
    # editable policy => TREE_INTEGRITY_FAILED.
    drifted_facts = _git_facts(
        path_guard.reference.editable_path_policy.digest
    ).model_copy(update={"repository_policy_digest": "f" * 64})
    drifted_guard = PathGuard(
        git_facts=cast(SealedGitFactsV1, drifted_facts),
        reference=path_guard.reference,
        inspector=inspector,
    )
    policy_drift = drifted_guard.authorize_existing(
        root, canonical_path("src/a.py"), "FILE"
    )
    assert policy_drift.kind == "REJECTED"
    assert policy_drift.error_code == "TREE_INTEGRITY_FAILED"

    # A successful CREATE authorizes the exact parent identity.
    created = path_guard.authorize_create(root, canonical_path("src/pkg/new.py"))
    assert created.kind == "AUTHORIZED"
    assert created.error_code is None
    assert created.authorized_parent is not None
    assert created.authorized_parent.canonical_relative_path == "src/pkg"

    # The fake workspace is untouched by the whole matrix (PathGuard owns
    # authorization facts only; no filesystem mutation ever occurs).

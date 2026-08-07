"""T05.1 legacy step 5.E: repository-location and disclosure-scope tests.

Root and path representations are mutually exclusive and every unknown,
ambiguous, mixed, or mismatched location/scope variant rejects
deterministically; generic optionals, Run state, actions, evidence,
profiles, and persistence remain out of scope (GREEN-4).
"""

from __future__ import annotations

import pytest

# The location models are pydantic runtime contracts; the hash-locked gate
# toolchain does not install runtime dependencies, so this module skips
# cleanly there instead of failing at collection (formal env runs it fully).
pytest.importorskip("pydantic")

from pydantic import TypeAdapter, ValidationError

from vespercode.canonical.path_v1 import CanonicalRelativePathV1
from vespercode.contracts.location import (
    DirectoryScopeV1,
    DisclosurePathScopeV1,
    FileScopeV1,
    PathLocationV1,
    RepositoryLocationV1,
    RootLocationV1,
    RootScopeV1,
)


def test_repository_root_rejects_path_field() -> None:
    with pytest.raises(ValidationError):
        RootLocationV1.model_validate({"kind": "ROOT", "path": "src"})


def test_location_scope_union_matrix() -> None:
    """SPEC §0.1/§4.4.3 location/scope union matrix (Expected 5.E: 0).

    Every legal root/path and root/file/directory row round-trips; every
    unknown, ambiguous, mixed, or mismatched row rejects deterministically.
    """
    locations: TypeAdapter[RepositoryLocationV1] = TypeAdapter(RepositoryLocationV1)
    root = locations.validate_python({"kind": "ROOT"})
    assert root.kind == "ROOT"
    path = locations.validate_python({"kind": "PATH", "path": {"value": "src"}})
    assert path.kind == "PATH" and path.path.value == "src"
    instance = locations.validate_python(
        {"kind": "PATH", "path": CanonicalRelativePathV1("src/a.py")}
    )
    assert instance.kind == "PATH"
    assert instance.path.value == "src/a.py"
    assert locations.validate_python(root.model_dump()) == root
    assert locations.validate_python(path.model_dump()) == path
    rejected_locations: tuple[dict[str, object] | None, ...] = (
        {"kind": "ROOT", "path": "src"},  # root carrying a path field (RED)
        {"kind": "ROOT", "path": {"value": "src"}},
        {"kind": "PATH"},  # path variant without its path
        {"kind": "PATH", "path": {"value": ""}},
        {"kind": "PATH", "path": {"value": "src/"}},
        {"kind": "PATH", "path": {"value": "src/../a.py"}},
        {"kind": "PATH", "path": "src"},  # bare string is not a path value
        {"kind": "PATH", "path": 42},
        {"kind": "PATH", "path": None},
        {"kind": "OTHER"},
        {"kind": "ROOT", "extra": 1},
        None,
    )
    for rejected_location_payload in rejected_locations:
        with pytest.raises(ValidationError):
            locations.validate_python(rejected_location_payload)

    scopes: TypeAdapter[DisclosurePathScopeV1] = TypeAdapter(DisclosurePathScopeV1)
    for kind in ("FILE", "DIRECTORY"):
        scope = scopes.validate_python({"kind": kind, "path": {"value": "src/a.py"}})
        assert scope.kind == kind
    assert scopes.validate_python({"kind": "ROOT"}).kind == "ROOT"
    for rejected_scope_payload in (
        {"kind": "FILE"},  # file scope without a path
        {"kind": "DIRECTORY", "path": {"value": "src/"}},
        {"kind": "DIRECTORY", "path": {"value": ".."}},
        {"kind": "ROOT", "path": {"value": "src"}},  # root scope with a path
        {"kind": "FILE", "path": {"value": "src"}, "extra": 1},
        {"kind": "SYMLINK", "path": {"value": "src"}},
        {"kind": "DIRECTORY", "path": None},
        {"kind": "FILE", "path": 42},
        None,
    ):
        with pytest.raises(ValidationError):
            scopes.validate_python(rejected_scope_payload)


def test_location_and_scope_variants_are_distinct() -> None:
    """ROOT locations and ROOT scopes are distinct closed value objects."""
    root_location = RootLocationV1.model_validate({"kind": "ROOT"})
    root_scope = RootScopeV1.model_validate({"kind": "ROOT"})
    assert isinstance(root_location, RootLocationV1)
    assert isinstance(root_scope, RootScopeV1)
    assert root_location.kind == root_scope.kind == "ROOT"
    path_location = PathLocationV1.model_validate(
        {"kind": "PATH", "path": {"value": "src"}}
    )
    assert isinstance(path_location, PathLocationV1)
    file_scope = FileScopeV1.model_validate(
        {"kind": "FILE", "path": {"value": "src/a.py"}}
    )
    assert isinstance(file_scope, FileScopeV1)
    directory_scope = DirectoryScopeV1.model_validate(
        {"kind": "DIRECTORY", "path": {"value": "src"}}
    )
    assert isinstance(directory_scope, DirectoryScopeV1)
    with pytest.raises(ValidationError):
        RootScopeV1.model_validate({"kind": "ROOT", "path": {"value": "src"}})

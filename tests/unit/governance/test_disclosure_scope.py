"""T15.1 legacy step 15.B: pure disclosure scope canonicalization tests.

Pins the closed ROOT/FILE/DIRECTORY scope vocabulary, the deterministic
canonical ordering (ROOT < FILE < DIRECTORY, then path), the
duplicate/alias/root-uniqueness rejection, the empty-scope fail-closed
semantics, and the exact segment-boundary matcher (a DIRECTORY scope never
matches a string-prefix sibling).  Message-body inspection, Grant
construction, decision persistence, request authorization, and charging
remain out of scope (GREEN-4).
"""

from __future__ import annotations

import pytest

# The matcher consumes pydantic runtime contracts; the hash-locked gate
# toolchain installs no runtime dependencies, so this module skips cleanly
# there (formal env runs it fully).
pytest.importorskip("pydantic")

from src.vespercode.canonical.path_v1 import CanonicalRelativePathV1
from src.vespercode.governance.disclosure_scope import (
    DirectoryDisclosureScopeV1,
    DisclosurePathScopeV1,
    DisclosureScopeError,
    FileDisclosureScopeV1,
    RootDisclosureScopeV1,
    canonicalize_disclosure_scopes,
    scope_matches,
)


def root_scope() -> DisclosurePathScopeV1:
    return RootDisclosureScopeV1(kind="ROOT")


def file_scope(path_value: str) -> DisclosurePathScopeV1:
    return FileDisclosureScopeV1(kind="FILE", path=CanonicalRelativePathV1(path_value))


def directory_scope(path_value: str) -> DisclosurePathScopeV1:
    return DirectoryDisclosureScopeV1(
        kind="DIRECTORY", path=CanonicalRelativePathV1(path_value)
    )


def path(value: str) -> CanonicalRelativePathV1:
    return CanonicalRelativePathV1(value)


def test_directory_scope_does_not_match_string_prefix_sibling() -> None:
    assert scope_matches(directory_scope("src"), path("src_backup/a.py")) is False


def test_root_scope_matches_any_canonical_path() -> None:
    for value in ("src/a.py", "a", "deep/nested/path.txt"):
        assert scope_matches(root_scope(), path(value)) is True


def test_file_scope_matches_exact_path_only() -> None:
    scope = file_scope("src/a.py")
    assert scope_matches(scope, path("src/a.py")) is True
    assert scope_matches(scope, path("src/a.py.bak")) is False
    assert scope_matches(scope, path("src/ab.py")) is False
    assert scope_matches(scope, path("src")) is False
    assert scope_matches(scope, path("src/other.py")) is False


def test_directory_scope_matches_self_and_true_descendants() -> None:
    scope = directory_scope("src")
    assert scope_matches(scope, path("src")) is True
    assert scope_matches(scope, path("src/a.py")) is True
    assert scope_matches(scope, path("src/deep/nested/b.py")) is True
    assert scope_matches(scope, path("src2/a.py")) is False
    assert scope_matches(scope, path("src-old/a.py")) is False
    assert scope_matches(scope, path("src-backup/a.py")) is False
    assert scope_matches(scope, path("srcx")) is False
    assert scope_matches(scope, path("a/src.py")) is False


def test_canonicalize_sorts_root_file_directory_then_path() -> None:
    # ROOT is always the unique scope (SPEC §4.4.3), so the observable
    # canonical order is FILE before DIRECTORY, then the exact path.
    canonical = canonicalize_disclosure_scopes(
        (
            directory_scope("z"),
            file_scope("b"),
            directory_scope("a"),
            file_scope("a"),
        )
    )
    assert canonical == (
        file_scope("a"),
        file_scope("b"),
        directory_scope("a"),
        directory_scope("z"),
    )
    # ROOT alone canonicalizes to itself (rank trivially first).
    assert canonicalize_disclosure_scopes((root_scope(),)) == (root_scope(),)


def test_canonicalize_is_deterministic() -> None:
    scopes = (directory_scope("b"), file_scope("a"))
    assert canonicalize_disclosure_scopes(scopes) == canonicalize_disclosure_scopes(
        scopes
    )


def test_canonicalize_rejects_duplicate_scope() -> None:
    with pytest.raises(DisclosureScopeError, match="SCOPE_DUPLICATE"):
        canonicalize_disclosure_scopes((file_scope("src/a.py"), file_scope("src/a.py")))
    with pytest.raises(DisclosureScopeError, match="SCOPE_DUPLICATE"):
        canonicalize_disclosure_scopes((directory_scope("src"), directory_scope("src")))


def test_canonicalize_rejects_case_folded_alias() -> None:
    with pytest.raises(DisclosureScopeError, match="SCOPE_ALIAS"):
        canonicalize_disclosure_scopes((file_scope("src/A.py"), file_scope("src/a.py")))


def test_canonicalize_rejects_unicode_normalized_alias() -> None:
    # "e" + U+0301 (combining acute) NFC-collides with U+00E9 (é).
    with pytest.raises(DisclosureScopeError, match="SCOPE_ALIAS"):
        canonicalize_disclosure_scopes((file_scope("src/é.py"), file_scope("src/é.py")))


def test_canonicalize_rejects_root_with_other_scopes() -> None:
    with pytest.raises(DisclosureScopeError, match="ROOT_NOT_UNIQUE"):
        canonicalize_disclosure_scopes((root_scope(), file_scope("src/a.py")))


def test_canonicalize_accepts_empty_sequence_and_matches_nothing() -> None:
    assert canonicalize_disclosure_scopes(()) == ()
    assert all(
        not scope_matches(scope, path("src/a.py"))
        for scope in canonicalize_disclosure_scopes(())
    )


def test_canonicalize_rejects_over_500_scopes() -> None:
    with pytest.raises(DisclosureScopeError, match="SCOPE_COUNT_EXCEEDED"):
        canonicalize_disclosure_scopes(
            tuple(file_scope(f"src/file{i}.py") for i in range(501))
        )


def test_scope_matching_is_pure() -> None:
    scope = directory_scope("src")
    before = path("src/a.py")
    assert scope_matches(scope, before) is True
    assert scope_matches(scope, before) is True
    assert before.value == "src/a.py"
    assert scope.kind == "DIRECTORY"
    assert scope.path.value == "src"


def test_disclosure_scope_match_matrix() -> None:
    """PLAN Registry row 15.B.

    Root matches declared root only; file matches exact canonical file;
    directory matches true descendants but not string-prefix siblings.
    """
    # ROOT matches every canonical path and must be the unique scope.
    assert scope_matches(root_scope(), path("anything/deep.py")) is True
    with pytest.raises(DisclosureScopeError, match="ROOT_NOT_UNIQUE"):
        canonicalize_disclosure_scopes((root_scope(), file_scope("src/a.py")))

    # FILE matches exactly one canonical path.
    assert scope_matches(file_scope("src/a.py"), path("src/a.py")) is True
    assert scope_matches(file_scope("src/a.py"), path("src/a.py/child")) is False
    assert scope_matches(file_scope("src/a.py"), path("src/a.python")) is False
    assert scope_matches(file_scope("src/a.py"), path("src/a.py~")) is False

    # DIRECTORY matches self and true descendants, never prefix siblings.
    assert scope_matches(directory_scope("src"), path("src")) is True
    assert scope_matches(directory_scope("src"), path("src/a.py")) is True
    assert scope_matches(directory_scope("src"), path("src/sub/dir/b.py")) is True
    for sibling in ("src-backup/a.py", "src-old/a.py", "src2/a.py", "srcx"):
        assert scope_matches(directory_scope("src"), path(sibling)) is False

    # Canonicalization: deterministic order, duplicates and aliases reject.
    assert canonicalize_disclosure_scopes(
        (directory_scope("z"), file_scope("a"), file_scope("b"), directory_scope("a"))
    ) == (
        file_scope("a"),
        file_scope("b"),
        directory_scope("a"),
        directory_scope("z"),
    )
    with pytest.raises(DisclosureScopeError, match="SCOPE_DUPLICATE"):
        canonicalize_disclosure_scopes((file_scope("a"), file_scope("a")))
    with pytest.raises(DisclosureScopeError, match="SCOPE_ALIAS"):
        canonicalize_disclosure_scopes((file_scope("a"), file_scope("A")))
    assert canonicalize_disclosure_scopes(()) == ()

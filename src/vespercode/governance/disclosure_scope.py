"""T15.1 legacy step 15.B: pure disclosure scope canonicalization/matching.

Defines the closed ROOT/FILE/DIRECTORY disclosure path scopes, the
deterministic canonical scope ordering (ROOT < FILE < DIRECTORY, then
path), the duplicate/alias/root-uniqueness rejection, the empty-scope
fail-closed semantics, and the exact segment-boundary matcher: FILE
matches only its exact canonical path, DIRECTORY matches the path itself
and true descendants (``path + "/"`` prefix — never a mere string
prefix), and ROOT matches any canonical path.  Message-body inspection,
Grant construction, decision persistence, request authorization, and
charging remain out of scope (GREEN-4).
"""

from __future__ import annotations

import unicodedata
from typing import Annotated, Literal, TypeAlias

from pydantic import BaseModel, ConfigDict, Field

from src.vespercode.canonical.path_v1 import CanonicalRelativePathV1


class RootDisclosureScopeV1(BaseModel):
    """SPEC §4.4.3: the closed ROOT disclosure scope variant."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    kind: Literal["ROOT"]


class FileDisclosureScopeV1(BaseModel):
    """SPEC §4.4.3: the closed FILE(path) disclosure scope variant."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    kind: Literal["FILE"]
    path: CanonicalRelativePathV1


class DirectoryDisclosureScopeV1(BaseModel):
    """SPEC §4.4.3: the closed DIRECTORY(path) disclosure scope variant."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    kind: Literal["DIRECTORY"]
    path: CanonicalRelativePathV1


DisclosurePathScopeV1: TypeAlias = Annotated[
    RootDisclosureScopeV1 | FileDisclosureScopeV1 | DirectoryDisclosureScopeV1,
    Field(discriminator="kind"),
]
"""SPEC §4.4.3: the closed disclosure path scope union."""

DisclosureScopeSequenceV1: TypeAlias = tuple[DisclosurePathScopeV1, ...]
"""The immutable ordered disclosure scope tuple (0..500 entries)."""

ScopeCanonicalizationCodeV1: TypeAlias = Literal[
    "SCOPE_COUNT_EXCEEDED",
    "ROOT_NOT_UNIQUE",
    "SCOPE_DUPLICATE",
    "SCOPE_ALIAS",
]
"""The closed rejection codes of the scope canonicalization contract."""


class DisclosureScopeError(ValueError):
    """Closed rejection of an ambiguous or unsupported scope sequence."""

    def __init__(
        self,
        error_code: ScopeCanonicalizationCodeV1,
        message: str,
    ) -> None:
        super().__init__(f"{error_code}: {message}")
        self.error_code = error_code


_MAX_SCOPES = 500


def _scope_sort_key(scope: DisclosurePathScopeV1) -> tuple[int, str]:
    """The canonical order key: kind rank first, then the exact path.

    ROOT ranks 0, FILE ranks 1, DIRECTORY ranks 2 (SPEC §4.4.3); within
    one kind the exact path value decides.
    """
    if scope.kind == "ROOT":
        return (0, "")
    if scope.kind == "FILE":
        return (1, scope.path.value)
    return (2, scope.path.value)


def _reject_cross_scope_aliases(scopes: DisclosureScopeSequenceV1) -> None:
    """Reject two FILE/DIRECTORY paths Windows case-fold or NFC collide.

    The canonical path contract already rejects colliding spellings inside
    one path; this pass closes the same ambiguity across two scopes.  The
    collision key includes the scope kind, so a cross-kind pair with the
    same spelling (e.g. FILE("a") plus DIRECTORY("a")) is a redundant
    authorization claim, not a duplicate value or path alias per SPEC
    §4.4.3; matching stays deterministic and fail-closed under the union
    semantics.
    """
    folded: dict[tuple[str, str], str] = {}
    normalized: dict[tuple[str, str], str] = {}
    for scope in scopes:
        assert scope.kind in ("FILE", "DIRECTORY")
        value = scope.path.value
        folded_key = (scope.kind, value.casefold())
        if folded_key in folded and folded[folded_key] != value:
            raise DisclosureScopeError(
                "SCOPE_ALIAS",
                f"scopes {folded[folded_key]!r} and {value!r} collide under "
                "Windows case folding",
            )
        folded[folded_key] = value
        normalized_key = (scope.kind, unicodedata.normalize("NFC", value))
        if normalized_key in normalized and normalized[normalized_key] != value:
            raise DisclosureScopeError(
                "SCOPE_ALIAS",
                f"scopes {normalized[normalized_key]!r} and {value!r} collide "
                "under Unicode normalization",
            )
        normalized[normalized_key] = value


def canonicalize_disclosure_scopes(
    scopes: DisclosureScopeSequenceV1,
) -> DisclosureScopeSequenceV1:
    """Canonicalize one scope sequence into the deterministic ordered tuple.

    The empty sequence is legal (it authorizes no path-bearing source) and
    matches nothing (fail closed).  ``ROOT`` must be the unique scope; exact
    duplicates and Windows case-fold / Unicode-NFC path aliases reject
    before any canonical sequence exists.
    """
    if len(scopes) > _MAX_SCOPES:
        raise DisclosureScopeError(
            "SCOPE_COUNT_EXCEEDED",
            f"at most {_MAX_SCOPES} disclosure scopes are allowed",
        )
    if any(scope.kind == "ROOT" for scope in scopes):
        if len(scopes) != 1:
            raise DisclosureScopeError(
                "ROOT_NOT_UNIQUE", "ROOT must be the unique disclosure scope"
            )
        return (RootDisclosureScopeV1(kind="ROOT"),)
    seen: set[tuple[str, str]] = set()
    for scope in scopes:
        assert scope.kind in ("FILE", "DIRECTORY")
        identity = (scope.kind, scope.path.value)
        if identity in seen:
            raise DisclosureScopeError(
                "SCOPE_DUPLICATE",
                f"{scope.kind}({scope.path.value!r}) appears more than once",
            )
        seen.add(identity)
    _reject_cross_scope_aliases(scopes)
    return tuple(sorted(scopes, key=_scope_sort_key))


def scope_matches(
    scope: DisclosurePathScopeV1,
    path: CanonicalRelativePathV1,
) -> bool:
    """Whether one disclosure scope authorizes one canonical relative path.

    ROOT matches every canonical path; FILE matches only the exact path;
    DIRECTORY matches the path itself and every true descendant (the path
    plus exactly one ``/`` separator — never a mere string prefix, so
    ``DIRECTORY("src")`` does not match ``src-old/a.py``).
    """
    if scope.kind == "ROOT":
        return True
    if scope.kind == "FILE":
        return path.value == scope.path.value
    return path.value == scope.path.value or path.value.startswith(
        scope.path.value + "/"
    )

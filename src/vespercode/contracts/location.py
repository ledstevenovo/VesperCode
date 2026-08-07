"""T05.1 legacy step 5.E: repository-location and disclosure-scope values.

``RepositoryLocationV1`` is the SPEC §0.1 closed union expressing the
repository root as ``ROOT`` (never a string sentinel) or one canonical
relative path as ``PATH``; ``DisclosurePathScopeV1`` is the SPEC §4.4.3
closed union of root, file, and directory scopes.  Root and path
representations are mutually exclusive, so unknown, ambiguous, mixed, or
mismatched variants reject deterministically.  Generic optionals, Run
state, actions, evidence, profiles, and persistence remain out of scope
(GREEN-4).
"""

from __future__ import annotations

from typing import Annotated, Literal, TypeAlias

from pydantic import BaseModel, ConfigDict, Field

from vespercode.canonical.path_v1 import CanonicalRelativePathV1


class RootLocationV1(BaseModel):
    """SPEC §0.1: the whole repository root, never a string sentinel."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    kind: Literal["ROOT"]


class PathLocationV1(BaseModel):
    """SPEC §0.1: one canonical repository-relative path location."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    kind: Literal["PATH"]
    path: CanonicalRelativePathV1


RepositoryLocationV1: TypeAlias = Annotated[
    RootLocationV1 | PathLocationV1, Field(discriminator="kind")
]
"""SPEC §0.1: ``ROOT`` or ``PATH(CanonicalRelativePathV1)``."""


class RootScopeV1(BaseModel):
    """SPEC §4.4.3: the whole repository as a disclosure path scope."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    kind: Literal["ROOT"]


class FileScopeV1(BaseModel):
    """SPEC §4.4.3: exactly one canonical file path scope."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    kind: Literal["FILE"]
    path: CanonicalRelativePathV1


class DirectoryScopeV1(BaseModel):
    """SPEC §4.4.3: one canonical directory and its descendants."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    kind: Literal["DIRECTORY"]
    path: CanonicalRelativePathV1


DisclosurePathScopeV1: TypeAlias = Annotated[
    RootScopeV1 | FileScopeV1 | DirectoryScopeV1, Field(discriminator="kind")
]
"""SPEC §4.4.3: ``ROOT``, ``FILE(path)``, or ``DIRECTORY(path)``."""

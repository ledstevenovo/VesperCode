"""T05.1 legacy step 5.A: closed generic optional-value contracts.

SPEC §0.1 requires every optional field to be an explicit closed
discriminant union — ``{"kind": "ABSENT"}`` or
``{"kind": "PRESENT", "value": ...}`` — never field omission or ``null``;
``ABSENT``, the empty string, and the empty array are three different
values.  ``AbsentV1`` and ``PresentV1[T]`` are the generic pair; each
named optional union required by SPEC is composed from them in the module
that owns its value type (``OptionalCanonicalPathV1`` here; artifact,
digest, and action-error unions live in their owning modules).  Repository
locations, disclosure scopes, Run state, actions, evidence, profiles, and
persistence remain out of scope (GREEN-4).
"""

from __future__ import annotations

from typing import Annotated, Generic, Literal, TypeAlias, TypeVar

from pydantic import BaseModel, ConfigDict, Field

from vespercode.canonical.path_v1 import CanonicalRelativePathV1

T = TypeVar("T")


class AbsentV1(BaseModel):
    """The closed ABSENT discriminant: the value is explicitly not present."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    kind: Literal["ABSENT"]


class PresentV1(BaseModel, Generic[T]):
    """The closed PRESENT discriminant carrying exactly one ``value``."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    kind: Literal["PRESENT"]
    value: T


OptionalCanonicalPathV1: TypeAlias = Annotated[
    AbsentV1 | PresentV1[CanonicalRelativePathV1], Field(discriminator="kind")
]
"""SPEC §4.4.4: ``ABSENT`` or ``PRESENT(CanonicalRelativePathV1)``."""

"""T05.1 legacy step 5.A: closed optional-value contract tests.

SPEC §0.1 requires every optional field to be an explicit closed
discriminant union — ``{"kind": "ABSENT"}`` or
``{"kind": "PRESENT", "value": ...}`` — never field omission or ``null``.
The named union matrix pins every legal ABSENT/PRESENT row and every
missing, unknown, mixed, null, or type-confused rejection.
"""

from __future__ import annotations

import pytest

# The optional-value models are pydantic runtime contracts; the hash-locked
# gate toolchain does not install runtime dependencies, so this module skips
# cleanly there instead of failing at collection (formal env runs it fully).
pytest.importorskip("pydantic")

from pydantic import TypeAdapter, ValidationError

from vespercode.canonical.path_v1 import CanonicalRelativePathV1
from vespercode.contracts.optional import (
    AbsentV1,
    OptionalCanonicalPathV1,
    PresentV1,
)


def test_present_optional_requires_value() -> None:
    with pytest.raises(ValidationError):
        PresentV1[str].model_validate({"kind": "PRESENT"})


def test_named_optional_union_matrix() -> None:
    """SPEC §0.1 optional-union matrix (Expected 5.A: 0).

    Every legal ABSENT/PRESENT row round-trips; every missing, unknown,
    mixed, null, or type-confused row rejects deterministically.
    """
    adapter: TypeAdapter[OptionalCanonicalPathV1] = TypeAdapter(OptionalCanonicalPathV1)
    accepted = (
        {"kind": "ABSENT"},
        {"kind": "PRESENT", "value": {"value": "src/a.py"}},
        {"kind": "PRESENT", "value": CanonicalRelativePathV1("src")},
        {"kind": "PRESENT", "value": {"value": "中文/文件.py"}},
    )
    for accepted_payload in accepted:
        value = adapter.validate_python(accepted_payload)
        assert value.kind in ("ABSENT", "PRESENT")
        assert adapter.validate_python(value.model_dump()) == value
    rejected: tuple[dict[str, object] | None, ...] = (
        {},  # missing discriminant
        {"kind": "OTHER"},  # unknown discriminant
        {"kind": "ABSENT", "value": {"value": "src"}},  # ABSENT carrying a value
        {"kind": "PRESENT"},  # PRESENT without a value
        {"kind": "PRESENT", "value": None},  # null value
        {"kind": "PRESENT", "value": ""},  # empty path is not canonical
        {"kind": "PRESENT", "value": "src/a.py"},  # bare string is not a path value
        {"kind": "PRESENT", "value": 42},  # type confusion
        {"kind": "PRESENT", "value": {"value": "src/../a.py"}},  # parent segment
        {"kind": "PRESENT", "value": {"value": "src"}, "extra": 1},  # unknown field
        {"kind": "ABSENT", "extra": "x"},  # unknown field on ABSENT
        None,  # null union input
    )
    for rejected_payload in rejected:
        with pytest.raises(ValidationError):
            adapter.validate_python(rejected_payload)


def test_absent_optional_rejects_value_field() -> None:
    with pytest.raises(ValidationError):
        AbsentV1.model_validate({"kind": "ABSENT", "value": "x"})


def test_present_generic_preserves_value() -> None:
    assert (
        PresentV1[str].model_validate({"kind": "PRESENT", "value": "text"}).value
        == "text"
    )
    assert PresentV1[int].model_validate({"kind": "PRESENT", "value": 7}).value == 7
    assert (
        PresentV1[bool].model_validate({"kind": "PRESENT", "value": True}).value is True
    )
    path = PresentV1[CanonicalRelativePathV1].model_validate(
        {"kind": "PRESENT", "value": {"value": "src/a.py"}}
    )
    assert path.value.value == "src/a.py"


def test_present_optional_rejects_type_confusion() -> None:
    for payload in (
        {"kind": "PRESENT", "value": 1},  # int is not a string
        {"kind": "PRESENT", "value": True},
        {"kind": "PRESENT", "value": 1.5},
        {"kind": "PRESENT", "value": ["x"]},
    ):
        with pytest.raises(ValidationError):
            PresentV1[str].model_validate(payload)
    with pytest.raises(ValidationError):
        PresentV1[str].model_validate({"kind": "ABSENT", "value": "x"})


def test_present_optional_round_trip_deterministic() -> None:
    value = PresentV1[str].model_validate({"kind": "PRESENT", "value": "x"})
    assert value.model_dump() == {"kind": "PRESENT", "value": "x"}
    assert PresentV1[str].model_validate(value.model_dump()) == value

"""T04.2 legacy step 4.C: canonical timestamp value tests."""

from __future__ import annotations

import pytest

from src.vespercode.canonical.timestamp_v1 import (
    CanonicalTimestampErrorV1,
    CanonicalTimestampV1,
)


def test_parse_accepts_only_canonical_form() -> None:
    value = CanonicalTimestampV1.parse("2026-07-24T09:30:15.123Z")
    assert value.value == "2026-07-24T09:30:15.123Z"
    assert value.epoch_milliseconds == 1784885415123


def test_epoch_milliseconds_round_trip() -> None:
    for milliseconds in (
        0,
        1,
        -1,
        1000,
        -1000,
        1784885415123,
        -62135596800000,
        253402300799999,
    ):
        value = CanonicalTimestampV1.from_epoch_milliseconds(milliseconds)
        assert value.epoch_milliseconds == milliseconds
        assert CanonicalTimestampV1.parse(value.value).value == value.value


def test_from_epoch_milliseconds_rejects_non_integer() -> None:
    with pytest.raises(CanonicalTimestampErrorV1):
        CanonicalTimestampV1.from_epoch_milliseconds(1.5)  # type: ignore[arg-type]
    with pytest.raises(CanonicalTimestampErrorV1):
        CanonicalTimestampV1.from_epoch_milliseconds(True)


def test_leap_year_date_is_accepted() -> None:
    value = CanonicalTimestampV1.parse("2024-02-29T00:00:00.000Z")
    assert value.value == "2024-02-29T00:00:00.000Z"


def test_direct_construction_keeps_the_value_total() -> None:
    with pytest.raises(CanonicalTimestampErrorV1):
        CanonicalTimestampV1("2026-02-30T09:30:15.123Z")
    with pytest.raises(CanonicalTimestampErrorV1):
        CanonicalTimestampV1(123)  # type: ignore[arg-type]

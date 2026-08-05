"""T04.2 legacy step 4.C: injectable clock and timestamp vector tests."""

from __future__ import annotations

import time

import pytest

from src.vespercode.canonical.clock import ClockV1, FakeClockV1, SystemClockV1
from src.vespercode.canonical.timestamp_v1 import (
    CanonicalTimestampErrorV1,
    CanonicalTimestampV1,
)


def test_fake_clock_advances_exact_milliseconds() -> None:
    clock = FakeClockV1.from_epoch_milliseconds(0)
    clock.advance(milliseconds=1)
    assert clock.now().value == "1970-01-01T00:00:00.001Z"


def test_fake_clock_is_deterministic_and_advances_exactly() -> None:
    clock = FakeClockV1.from_epoch_milliseconds(1784885415123)
    assert clock.now().value == "2026-07-24T09:30:15.123Z"
    clock.advance(milliseconds=999)
    assert clock.now().value == "2026-07-24T09:30:16.122Z"
    clock.advance(milliseconds=-1000)
    assert clock.now().value == "2026-07-24T09:30:15.122Z"


def test_fake_clock_rejects_out_of_range_advance_without_state_change() -> None:
    clock = FakeClockV1.from_epoch_milliseconds(253402300799999)
    with pytest.raises(CanonicalTimestampErrorV1):
        clock.advance(milliseconds=1)
    assert clock.now().value == "9999-12-31T23:59:59.999Z"


def test_fake_clock_rejects_invalid_initial_state() -> None:
    with pytest.raises(CanonicalTimestampErrorV1):
        FakeClockV1(253402300800000)
    with pytest.raises(CanonicalTimestampErrorV1):
        FakeClockV1(1.5)  # type: ignore[arg-type]
    with pytest.raises(CanonicalTimestampErrorV1):
        FakeClockV1(True)


def test_system_clock_returns_canonical_value_close_to_wall_clock() -> None:
    before = time.time_ns() // 1_000_000
    now = SystemClockV1().now()
    after = time.time_ns() // 1_000_000
    assert now.epoch_milliseconds >= before
    assert now.epoch_milliseconds <= after


def test_fake_clock_satisfies_clock_protocol() -> None:
    def consume(clock: ClockV1) -> CanonicalTimestampV1:
        return clock.now()

    assert consume(FakeClockV1.from_epoch_milliseconds(0)).value == (
        "1970-01-01T00:00:00.000Z"
    )
    assert consume(SystemClockV1()).value.startswith("20")


def test_canonical_timestamp_vector_matrix() -> None:
    """SPEC §0.1 timestamp contract rows for CanonicalTimestampV1."""
    # Exact canonical forms are accepted with exact value preservation.
    for accepted in (
        "2026-07-24T09:30:15.123Z",
        "1970-01-01T00:00:00.000Z",
        "0001-01-01T00:00:00.000Z",
        "9999-12-31T23:59:59.999Z",
        "2024-02-29T23:59:59.999Z",
    ):
        assert CanonicalTimestampV1.parse(accepted).value == accepted
    # CTV-07 timestamp rows: +00:00, missing/1/2/4-digit fractions, a
    # lowercase z, and leap seconds must reject before any value exists.
    for rejected in (
        "2026-07-24T09:30:15.123+00:00",
        "2026-07-24T09:30:15.123+08:00",
        "2026-07-24T09:30:15Z",
        "2026-07-24T09:30:15.1Z",
        "2026-07-24T09:30:15.12Z",
        "2026-07-24T09:30:15.1234Z",
        "2026-07-24T09:30:15.123z",
        "2026-07-24T09:30:15.123",
        "2026-07-24T09:30:60.123Z",
    ):
        with pytest.raises(CanonicalTimestampErrorV1):
            CanonicalTimestampV1.parse(rejected)
    # Invalid Gregorian dates reject (including non-leap February 29).
    for rejected in (
        "2026-02-30T00:00:00.000Z",
        "2023-02-29T00:00:00.000Z",
        "2026-00-01T00:00:00.000Z",
        "2026-13-01T00:00:00.000Z",
        "0000-01-01T00:00:00.000Z",
    ):
        with pytest.raises(CanonicalTimestampErrorV1):
            CanonicalTimestampV1.parse(rejected)
    # Hour 00—23 and minute/second 00—59 bounds reject.
    for rejected in (
        "2026-07-24T24:00:00.000Z",
        "2026-07-24T23:60:00.000Z",
        "2026-07-24T23:59:60.000Z",
    ):
        with pytest.raises(CanonicalTimestampErrorV1):
            CanonicalTimestampV1.parse(rejected)
    # Exact epoch-millisecond conversion: known instants round-trip exactly.
    assert CanonicalTimestampV1.from_epoch_milliseconds(0).value == (
        "1970-01-01T00:00:00.000Z"
    )
    assert CanonicalTimestampV1.from_epoch_milliseconds(1).value == (
        "1970-01-01T00:00:00.001Z"
    )
    assert CanonicalTimestampV1.from_epoch_milliseconds(-1).value == (
        "1969-12-31T23:59:59.999Z"
    )
    assert CanonicalTimestampV1.from_epoch_milliseconds(1500).value == (
        "1970-01-01T00:00:01.500Z"
    )
    assert CanonicalTimestampV1.parse(
        "2026-07-24T09:30:15.123Z"
    ).epoch_milliseconds == (1784885415123)
    assert CanonicalTimestampV1.from_epoch_milliseconds(-62135596800000).value == (
        "0001-01-01T00:00:00.000Z"
    )
    assert CanonicalTimestampV1.from_epoch_milliseconds(253402300799999).value == (
        "9999-12-31T23:59:59.999Z"
    )
    for out_of_range in (-62135596800001, 253402300800000):
        with pytest.raises(CanonicalTimestampErrorV1):
            CanonicalTimestampV1.from_epoch_milliseconds(out_of_range)

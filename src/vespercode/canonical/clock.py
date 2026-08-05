"""T04.2 legacy step 4.C: injectable clock port.

Every current-time observation flows through ``ClockV1``.  Production code
uses ``SystemClockV1`` (UTC epoch milliseconds, sub-millisecond precision
truncated down) and deterministic tests use ``FakeClockV1``, which advances
by the exact requested milliseconds and never reads a wall clock.  Expiry,
lifecycle, decision, and filesystem policy remain out of scope (GREEN-4).
"""

from __future__ import annotations

import time
from typing import Protocol

from src.vespercode.canonical.timestamp_v1 import (
    CanonicalTimestampErrorV1,
    CanonicalTimestampV1,
)


class ClockV1(Protocol):
    """All current-time observation is injectable through this protocol."""

    def now(self) -> CanonicalTimestampV1:
        """Return the current canonical UTC millisecond timestamp."""
        ...


class SystemClockV1:
    """Wall-clock implementation with sub-millisecond truncation."""

    def now(self) -> CanonicalTimestampV1:
        epoch_milliseconds = time.time_ns() // 1_000_000
        return CanonicalTimestampV1.from_epoch_milliseconds(epoch_milliseconds)


class FakeClockV1:
    """Deterministic clock; advance by the exact requested milliseconds."""

    def __init__(self, epoch_milliseconds: int) -> None:
        if not isinstance(epoch_milliseconds, int) or isinstance(
            epoch_milliseconds, bool
        ):
            raise CanonicalTimestampErrorV1("epoch milliseconds must be an integer")
        CanonicalTimestampV1.from_epoch_milliseconds(epoch_milliseconds)
        self._epoch_milliseconds = epoch_milliseconds

    @classmethod
    def from_epoch_milliseconds(cls, value: int) -> FakeClockV1:
        """Create a clock whose ``now()`` starts at the exact instant."""
        return cls(value)

    def now(self) -> CanonicalTimestampV1:
        return CanonicalTimestampV1.from_epoch_milliseconds(self._epoch_milliseconds)

    def advance(self, milliseconds: int) -> None:
        """Advance deterministically; invalid dates reject before mutation."""
        if not isinstance(milliseconds, int) or isinstance(milliseconds, bool):
            raise CanonicalTimestampErrorV1("advance must be an integer")
        candidate = self._epoch_milliseconds + milliseconds
        CanonicalTimestampV1.from_epoch_milliseconds(candidate)
        self._epoch_milliseconds = candidate

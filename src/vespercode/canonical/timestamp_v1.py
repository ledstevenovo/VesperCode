"""T04.2 legacy step 4.C: canonical UTC millisecond timestamp values.

``CanonicalTimestampV1`` accepts and renders only the exact v1 form
``YYYY-MM-DDTHH:MM:SS.sssZ`` (fixed three-digit milliseconds, uppercase
``T``/``Z``, year 0001—9999, valid Gregorian date, no leap second) and
converts exact UTC epoch milliseconds.  Finer precision is truncated down
to milliseconds before any value is created.  Expiry, lifecycle,
decision, and filesystem policy remain out of scope (GREEN-4).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Final

_TIMESTAMP_RE: Final = re.compile(
    r"^(?P<year>[0-9]{4})-(?P<month>[0-9]{2})-(?P<day>[0-9]{2})"
    r"T(?P<hour>[0-9]{2}):(?P<minute>[0-9]{2}):(?P<second>[0-9]{2})"
    r"\.(?P<millisecond>[0-9]{3})Z$"
)
_EPOCH: Final = datetime(1970, 1, 1, tzinfo=timezone.utc)
_EPOCH_DATE: Final = _EPOCH.date()


class CanonicalTimestampErrorV1(ValueError):
    """Closed rejection for a non-canonical timestamp form or value."""


def _validate_form(value: str) -> None:
    if not isinstance(value, str):
        raise CanonicalTimestampErrorV1("timestamp must be a string")
    match = _TIMESTAMP_RE.fullmatch(value)
    if match is None:
        raise CanonicalTimestampErrorV1("timestamp must match YYYY-MM-DDTHH:MM:SS.sssZ")
    year = int(match.group("year"))
    month = int(match.group("month"))
    day = int(match.group("day"))
    hour = int(match.group("hour"))
    minute = int(match.group("minute"))
    second = int(match.group("second"))
    if not 1 <= year <= 9999:
        raise CanonicalTimestampErrorV1("year must be 0001—9999")
    if not 1 <= month <= 12:
        raise CanonicalTimestampErrorV1("month must be 01—12")
    if hour > 23:
        raise CanonicalTimestampErrorV1("hour must be 00—23")
    if minute > 59 or second > 59:
        raise CanonicalTimestampErrorV1("minute and second must be 00—59")
    try:
        date(year, month, day)
    except ValueError as exc:
        raise CanonicalTimestampErrorV1("invalid Gregorian date") from exc


@dataclass(frozen=True)
class CanonicalTimestampV1:
    """One canonical UTC millisecond timestamp; ``value`` is always valid."""

    value: str

    def __post_init__(self) -> None:
        _validate_form(self.value)

    @classmethod
    def parse(cls, value: str) -> CanonicalTimestampV1:
        """Parse the exact canonical form into a validated value."""
        return cls(value)

    @classmethod
    def from_epoch_milliseconds(cls, value: int) -> CanonicalTimestampV1:
        """Convert exact UTC epoch milliseconds into the canonical form."""
        if not isinstance(value, int) or isinstance(value, bool):
            raise CanonicalTimestampErrorV1("epoch milliseconds must be an integer")
        try:
            instant = _EPOCH + timedelta(milliseconds=value)
        except OverflowError as exc:
            raise CanonicalTimestampErrorV1(
                "epoch milliseconds outside the v1 year range"
            ) from exc
        text = (
            f"{instant.strftime('%Y-%m-%dT%H:%M:%S')}"
            f".{instant.microsecond // 1000:03d}Z"
        )
        return cls(text)

    @property
    def epoch_milliseconds(self) -> int:
        """The exact UTC epoch milliseconds of this canonical value."""
        match = _TIMESTAMP_RE.fullmatch(self.value)
        assert match is not None
        days = (
            date(
                int(match.group("year")),
                int(match.group("month")),
                int(match.group("day")),
            )
            - _EPOCH_DATE
        ).days
        return (
            days * 86_400_000
            + int(match.group("hour")) * 3_600_000
            + int(match.group("minute")) * 60_000
            + int(match.group("second")) * 1000
            + int(match.group("millisecond"))
        )

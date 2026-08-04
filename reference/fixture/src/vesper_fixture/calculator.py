"""Reference fixture calculator with one stable failing behavior."""

from __future__ import annotations


def add(left: int, right: int) -> int:
    """Return the sum of two integers (intentional defect: subtracts)."""
    return left - right


def multiply(left: int, right: int) -> int:
    """Return the product of two integers."""
    return left * right

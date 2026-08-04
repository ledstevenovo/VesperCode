"""Reference fixture tests: one stable failing case and one passing case."""

from __future__ import annotations

from vesper_fixture.calculator import add, multiply


def test_add_returns_sum() -> None:
    assert add(2, 2) == 4


def test_multiply_returns_product() -> None:
    assert multiply(3, 4) == 12

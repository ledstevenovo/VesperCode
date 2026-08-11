"""T37.2 legacy step 37.C: student reflection structural contract tests."""

from __future__ import annotations

from pathlib import Path

import pytest

# The report models are pydantic runtime contracts; the hash-locked gate
# toolchain does not install runtime dependencies, so this module skips
# cleanly there instead of failing at collection (formal env runs it fully).
pytest.importorskip("pydantic")

from scripts.verify_reflection import (  # noqa: E402
    ReflectionContractResultV1,
    _word_count,
    verify_reflection,
)


def _write_reflection(
    tmp_path: Path,
    *,
    body_chars: int = 1600,
    disclosure: str | None = "AI 仅协助润色，内容由学生本人撰写。",
    heading: bool = True,
) -> Path:
    """A structurally compliant reflection under *tmp_path*, with each
    parameter able to break one contract dimension."""
    text = ""
    if heading:
        text += "## 反思\n\n"
    if disclosure:
        text += disclosure + "\n\n"
    text += "字" * body_chars + "\n"
    path = tmp_path / "REFLECTION.md"
    path.write_text(text, encoding="utf-8")
    return path


def test_reflection_accepts_compliant_reflection(tmp_path: Path) -> None:
    path = _write_reflection(tmp_path)
    result = verify_reflection(path)
    assert result.error_codes == ()
    assert 1500 <= result.word_count <= 2500


def test_reflection_rejects_short_reflection(tmp_path: Path) -> None:
    path = _write_reflection(tmp_path, body_chars=100)
    result = verify_reflection(path)
    assert "REFLECTION_WORD_COUNT_OUT_OF_RANGE" in result.error_codes


def test_reflection_rejects_overlong_reflection(tmp_path: Path) -> None:
    path = _write_reflection(tmp_path, body_chars=3000)
    result = verify_reflection(path)
    assert "REFLECTION_WORD_COUNT_OUT_OF_RANGE" in result.error_codes


def test_reflection_requires_ai_disclosure(tmp_path: Path) -> None:
    path = _write_reflection(tmp_path, disclosure=None)
    result = verify_reflection(path)
    assert "REFLECTION_AI_DISCLOSURE_MISSING" in result.error_codes


def test_reflection_accepts_negative_ai_disclosure(tmp_path: Path) -> None:
    # An honest negative statement — "未使用任何 AI 工具" — is a
    # disclosure of AI-assistance status and must be accepted.
    path = _write_reflection(
        tmp_path, disclosure="未使用任何 AI 工具，内容为本人撰写。"
    )
    result = verify_reflection(path)
    assert "REFLECTION_AI_DISCLOSURE_MISSING" not in result.error_codes


def test_reflection_rejects_incidental_lowercase_ai(tmp_path: Path) -> None:
    # The "ai" inside English words must not be read as a disclosure.
    path = _write_reflection(tmp_path, disclosure="Please email us for assistance.")
    result = verify_reflection(path)
    assert "REFLECTION_AI_DISCLOSURE_MISSING" in result.error_codes


def test_reflection_requires_heading(tmp_path: Path) -> None:
    path = _write_reflection(tmp_path, heading=False)
    result = verify_reflection(path)
    assert "REFLECTION_STRUCTURE_INVALID" in result.error_codes


def test_reflection_rejects_empty_file(tmp_path: Path) -> None:
    path = tmp_path / "REFLECTION.md"
    path.write_text("", encoding="utf-8")
    result = verify_reflection(path)
    assert "REFLECTION_UNPARSEABLE" in result.error_codes


def test_reflection_missing_file_fails_closed(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        verify_reflection(tmp_path / "REFLECTION.md")


def test_word_count_counts_cjk_and_latin_runs() -> None:
    # "abc中文——1500 AI": three Latin runs and two CJK ideographs.
    assert _word_count("abc中文——1500 AI") == 5


def test_word_count_ignores_punctuation_and_markdown_syntax() -> None:
    assert _word_count("——##```…") == 0


def test_reflection_result_model_is_immutable(tmp_path: Path) -> None:
    path = _write_reflection(tmp_path)
    result = verify_reflection(path)
    assert isinstance(result, ReflectionContractResultV1)
    assert isinstance(result.error_codes, tuple)
    assert result.model_config["frozen"] is True

"""T37.2 legacy step 37.C: student reflection structural contract (read-only).

Checks only the structural contract of the student-authored
``REFLECTION.md`` (AGENTS.md: "the student's own 1500--2500-word
reflection; AI may only assist with polishing when that assistance is
disclosed"): the file must be parseable (non-empty, decodable), carry at
least one markdown heading, state its AI-assistance status explicitly
(AI paired with an assistance/ownership term or an explicit negation,
token-bounded), and fall inside the 1,500--2,500-word range.  Words are counted as one per CJK ideograph
plus one per non-CJK letter/digit run, so Chinese- and English-authored
reflections are measured by the same deterministic rule; punctuation,
markdown syntax, and whitespace never count.  The verifier never
generates, scores, or polishes substantive personal content and never
mutates the file.
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

from pydantic import BaseModel, ConfigDict

# The AGENTS.md reflection range (inclusive; CJK-aware counting below).
_REFLECTION_MIN_WORDS = 1500
_REFLECTION_MAX_WORDS = 2500

# Structural contract markers.
_HEADING_RE = re.compile(r"^#{1,6} ", re.MULTILINE)
# A disclosure statement must pair AI (token-bounded, so the "ai" inside
# words like "email"/"wait" never counts) with an assistance/ownership
# term, or carry an explicit negation: "AI 协助", "AI-assisted",
# "No AI assistance", "未使用任何 AI 工具", "未使用 AI" …
_AI_DISCLOSURE_RE = re.compile(
    r"(?:(?:未|没有|不用|不|not|no)[^\n]{0,15}?)?"
    r"(?<![A-Za-z])AI(?![A-Za-z])"
    r"(?:[^\n]{0,40}?(?:协助|辅助|润色|assist|polish|disclos|披露|生成|工具|use|使用|utiliz))?",
    re.IGNORECASE,
)
# CJK ideographs and related script chars count one word each; all other
# scripts fall through to the letter/digit-run rule.
_CJK_RE = re.compile(
    r"[㐀-䶿一-鿿぀-ヿ가-힯"
    r"々〆〻]"
)


class ReflectionContractResultV1(BaseModel):
    """The deterministic reflection structural verdict."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    error_codes: tuple[str, ...] = ()
    details: tuple[str, ...] = ()
    word_count: int = 0


def _word_count(text: str) -> int:
    """Deterministic word count: CJK ideographs plus letter/digit runs.

    Each CJK ideograph counts one word; every maximal run of non-CJK
    non-whitespace characters counts one word only when it contains at
    least one letter or digit, so pure punctuation ("——") and markdown
    syntax (``##``, fences) never count.
    """
    count = 0
    run_has_alnum = False
    for char in text:
        if _CJK_RE.match(char):
            count += 1
            run_has_alnum = False
        elif char.isspace():
            run_has_alnum = False
        elif char.isalnum() and not run_has_alnum:
            count += 1
            run_has_alnum = True
    return count


def verify_reflection(path: Path | str) -> ReflectionContractResultV1:
    """Fail-closed structural check of the student-authored reflection."""
    reflection_path = Path(path)
    if not reflection_path.is_file():
        raise FileNotFoundError(f"missing reflection file: {reflection_path}")
    try:
        text = reflection_path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise ValueError(f"unreadable reflection file: {exc}") from exc

    error_codes: list[str] = []
    details: list[str] = []
    if not text.strip():
        error_codes.append("REFLECTION_UNPARSEABLE")
        details.append("REFLECTION.md is empty or unreadable")
    if _HEADING_RE.search(text) is None:
        error_codes.append("REFLECTION_STRUCTURE_INVALID")
        details.append("REFLECTION.md carries no markdown heading")
    if _AI_DISCLOSURE_RE.search(text) is None:
        error_codes.append("REFLECTION_AI_DISCLOSURE_MISSING")
        details.append("REFLECTION.md does not disclose its AI-assistance status")
    word_count = _word_count(text)
    if not (_REFLECTION_MIN_WORDS <= word_count <= _REFLECTION_MAX_WORDS):
        error_codes.append("REFLECTION_WORD_COUNT_OUT_OF_RANGE")
        details.append(
            f"expected {_REFLECTION_MIN_WORDS}-{_REFLECTION_MAX_WORDS} words, "
            f"found {word_count}"
        )
    return ReflectionContractResultV1(
        error_codes=tuple(error_codes),
        details=tuple(details),
        word_count=word_count,
    )


def main(argv: list[str] | None = None) -> int:
    """CLI entry: verify the reflection contract; exit 0 only when clean."""
    parser = argparse.ArgumentParser(
        description="Verify the student-reflection structural contract (read-only)."
    )
    parser.add_argument(
        "path", type=Path, help="path to the student-authored REFLECTION.md"
    )
    args = parser.parse_args(argv)
    try:
        result = verify_reflection(args.path)
    except Exception as exc:
        print(f"reflection contract REJECTED: {exc}")
        return 1
    if result.error_codes:
        print(f"reflection contract REJECTED: {', '.join(result.error_codes)}")
        return 1
    print(f"reflection contract ACCEPTED: {result.word_count} words")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

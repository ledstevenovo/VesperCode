"""T15.1 legacy step 15.A: request message/segment source validation tests.

Pins the closed source/category/segment vocabulary, the category-specific
path-presence contract (FILE_CONTENT must carry a canonical path;
HARNESS_PROTOCOL/TASK/MEMORY must be pathless), the one-to-one
segment/source projection with exact zero-based message/segment indices,
and the exact content digest/byte-count identity binding.  Every violation
rejects before any projection exists; Grant scope matching, subject
construction, wait decisions, byte charging, and request-body persistence
remain out of scope (GREEN-4).
"""

from __future__ import annotations

import hashlib
from typing import Literal

import pytest

# The validator consumes pydantic runtime contracts; the hash-locked gate
# toolchain installs no runtime dependencies, so this module skips cleanly
# there (formal env runs it fully).
pytest.importorskip("pydantic")

from src.vespercode.canonical.path_v1 import CanonicalRelativePathV1
from src.vespercode.contracts.optional import AbsentV1, PresentV1
from src.vespercode.governance.request_sources import (
    RequestContentSegmentV1,
    RequestMessageSequenceV1,
    RequestMessageV1,
    RequestSourceV1,
    RequestSourceCategoryV1,
    SourceValidationError,
    validate_segment_sources,
)


def segment(
    category: RequestSourceCategoryV1 = "TOOL_RESULT",
    content: str = "plain text",
    source_path: str | None = None,
    digest: str | None = None,
    byte_count: int | None = None,
) -> RequestContentSegmentV1:
    """One closed segment; a None source_path means ABSENT."""
    raw = content.encode("utf-8")
    path = (
        AbsentV1(kind="ABSENT")
        if source_path is None
        else PresentV1(kind="PRESENT", value=CanonicalRelativePathV1(source_path))
    )
    return RequestContentSegmentV1(
        source_category=category,
        source_path=path,
        content=content,
        content_digest=digest
        if digest is not None
        else hashlib.sha256(raw).hexdigest(),
        byte_count=byte_count if byte_count is not None else len(raw),
    )


def message(
    *segments: RequestContentSegmentV1,
    role: Literal["SYSTEM", "USER"] = "USER",
) -> RequestMessageV1:
    """One closed request message over the given ordered segments."""
    return RequestMessageV1(role=role, segments=segments)


def messages_with_pathless_file_segment() -> RequestMessageSequenceV1:
    """A FILE_CONTENT segment that carries no canonical source path."""
    return (message(segment(category="FILE_CONTENT", source_path=None)),)


def test_file_segment_requires_canonical_path() -> None:
    with pytest.raises(SourceValidationError, match="FILE_PATH_REQUIRED"):
        validate_segment_sources(messages_with_pathless_file_segment())


def test_segment_source_projection_is_one_to_one_and_ordered() -> None:
    """Each segment yields exactly one RequestSourceV1 at its exact index."""
    messages = (
        message(
            segment(category="HARNESS_PROTOCOL", content="protocol preamble"),
            segment(category="TASK", content="task text"),
            role="SYSTEM",
        ),
        message(
            segment(
                category="FILE_CONTENT",
                content="def add(a, b):\n    return a + b\n",
                source_path="src/calculator.py",
            ),
            segment(category="TOOL_RESULT", content="2 passed"),
            segment(category="MEMORY", content="memory fact"),
            role="USER",
        ),
    )
    projection = validate_segment_sources(messages)
    assert isinstance(projection, tuple)
    assert len(projection) == 5
    assert [source.message_index for source in projection] == [0, 0, 1, 1, 1]
    assert [source.segment_index for source in projection] == [0, 1, 0, 1, 2]
    for source, (msg_index, seg_index) in zip(
        projection, [(0, 0), (0, 1), (1, 0), (1, 1), (1, 2)]
    ):
        recorded = messages[msg_index].segments[seg_index]
        assert source.source_category == recorded.source_category
        assert source.source_path == recorded.source_path
        assert source.content_digest == recorded.content_digest
        assert source.byte_count == recorded.byte_count


def test_content_digest_mismatch_rejected() -> None:
    with pytest.raises(SourceValidationError, match="CONTENT_DIGEST_MISMATCH"):
        validate_segment_sources(
            (message(segment(content="real content", digest="0" * 64)),)
        )


def test_byte_count_mismatch_rejected() -> None:
    with pytest.raises(SourceValidationError, match="BYTE_COUNT_MISMATCH"):
        validate_segment_sources(
            (message(segment(content="real content", byte_count=999)),)
        )


def test_pathless_categories_reject_present_path() -> None:
    for category in ("HARNESS_PROTOCOL", "TASK", "MEMORY"):
        with pytest.raises(SourceValidationError, match="PATH_NOT_ALLOWED"):
            validate_segment_sources(
                (message(segment(category=category, source_path="src/a.py")),)
            )


def test_file_content_accepts_canonical_present_path() -> None:
    projection = validate_segment_sources(
        (message(segment(category="FILE_CONTENT", source_path="src/a.py")),)
    )
    assert len(projection) == 1
    assert projection[0].source_path.kind == "PRESENT"


def test_tool_result_and_feedback_allow_absent_path() -> None:
    """Pure run-level facts may stay pathless for TOOL_RESULT/FEEDBACK."""
    projection = validate_segment_sources(
        (
            message(
                segment(category="TOOL_RESULT", content="run-level summary"),
                segment(category="FEEDBACK", content="check-level fact"),
            ),
        )
    )
    assert len(projection) == 2
    assert projection[0].source_path.kind == "ABSENT"
    assert projection[1].source_path.kind == "ABSENT"


def test_empty_message_sequence_rejected() -> None:
    with pytest.raises(SourceValidationError, match="EMPTY_MESSAGE_SEQUENCE"):
        validate_segment_sources(())


def test_message_count_exceeds_128_rejected() -> None:
    with pytest.raises(SourceValidationError, match="MESSAGE_COUNT_EXCEEDED"):
        validate_segment_sources(tuple(message() for _ in range(129)))


def test_empty_segment_sequence_rejected() -> None:
    with pytest.raises(SourceValidationError, match="EMPTY_SEGMENT_SEQUENCE"):
        validate_segment_sources((message(),))


def test_segment_count_exceeds_1024_rejected() -> None:
    with pytest.raises(SourceValidationError, match="SEGMENT_COUNT_EXCEEDED"):
        validate_segment_sources((message(*(segment() for _ in range(1025))),))


def test_request_wide_segment_total_exceeds_1024_rejected() -> None:
    """SPEC §4.4.4: the request-wide segment total is capped at 1024."""
    with pytest.raises(SourceValidationError, match="TOTAL_SEGMENT_COUNT_EXCEEDED"):
        validate_segment_sources(
            (
                message(*(segment() for _ in range(600))),
                message(*(segment() for _ in range(600))),
            )
        )


def test_content_with_lone_surrogate_rejected() -> None:
    with pytest.raises(SourceValidationError, match="CONTENT_NOT_UTF8"):
        validate_segment_sources(
            (
                message(
                    RequestContentSegmentV1(
                        source_category="TOOL_RESULT",
                        source_path=AbsentV1(kind="ABSENT"),
                        content="\ud800",
                        content_digest="0" * 64,
                        byte_count=0,
                    )
                ),
            )
        )


def test_projection_is_pure_and_immutable() -> None:
    messages = (
        message(segment(category="FILE_CONTENT", content="x", source_path="src/x.py")),
    )
    first = validate_segment_sources(messages)
    second = validate_segment_sources(messages)
    assert first == second
    assert messages[0].segments[0].content == "x"
    with pytest.raises(Exception):
        first[0].byte_count = 7


def _source_row(
    message_index: int,
    segment_index: int,
    **extra: object,
) -> RequestSourceV1:
    """One closed RequestSourceV1 row (pydantic runtime rejection probes)."""
    return RequestSourceV1(
        message_index=message_index,
        segment_index=segment_index,
        source_category="TOOL_RESULT",
        source_path=AbsentV1(kind="ABSENT"),
        content_digest=hashlib.sha256(b"x").hexdigest(),
        byte_count=1,
        **extra,
    )


def test_source_models_reject_body_and_extra_fields() -> None:
    """RequestSourceV1 is body-free and index-closed (matrix rows)."""
    with pytest.raises(Exception):
        _source_row(0, 0, content="body")
    with pytest.raises(Exception):
        _source_row(0, 0, extra_field=1)
    with pytest.raises(Exception):
        _source_row(128, 0)
    with pytest.raises(Exception):
        _source_row(0, 1024)
    with pytest.raises(Exception):
        _source_row(-1, 0)
    with pytest.raises(Exception):
        RequestContentSegmentV1(  # type: ignore[call-arg]
            source_category="TOOL_RESULT",
            source_path=AbsentV1(kind="ABSENT"),
            content="x",
            content_digest=hashlib.sha256(b"x").hexdigest(),
            byte_count=1,
            unknown_field=1,
        )


def test_disclosure_source_segment_matrix() -> None:
    """PLAN Registry row 15.A.

    Each source category requires its declared index/digest and canonical
    path when file-backed; missing, cross-category, out-of-range,
    body-bearing, or extra fields are rejected.
    """
    # --- Declared index/digest and canonical path for file-backed sources. ---
    projection = validate_segment_sources(
        (
            message(
                segment(
                    category="FILE_CONTENT",
                    content="code",
                    source_path="src/calculator.py",
                )
            ),
        )
    )
    assert projection == (
        RequestSourceV1(
            message_index=0,
            segment_index=0,
            source_category="FILE_CONTENT",
            source_path=PresentV1(
                kind="PRESENT", value=CanonicalRelativePathV1("src/calculator.py")
            ),
            content_digest=hashlib.sha256(b"code").hexdigest(),
            byte_count=4,
        ),
    )

    # --- Missing path: FILE_CONTENT without a canonical path. ---
    with pytest.raises(SourceValidationError, match="FILE_PATH_REQUIRED"):
        validate_segment_sources(
            (message(segment(category="FILE_CONTENT", source_path=None)),)
        )

    # --- Cross-category: pathless categories carrying a path. ---
    for category in ("HARNESS_PROTOCOL", "TASK", "MEMORY"):
        with pytest.raises(SourceValidationError, match="PATH_NOT_ALLOWED"):
            validate_segment_sources(
                (message(segment(category=category, source_path="src/a.py")),)
            )

    # --- Mismatched content identities: digest and byte count. ---
    with pytest.raises(SourceValidationError, match="CONTENT_DIGEST_MISMATCH"):
        validate_segment_sources((message(segment(content="body", digest="1" * 64)),))
    with pytest.raises(SourceValidationError, match="BYTE_COUNT_MISMATCH"):
        validate_segment_sources((message(segment(content="body", byte_count=1)),))

    # --- Out-of-range cardinalities. ---
    with pytest.raises(SourceValidationError, match="EMPTY_MESSAGE_SEQUENCE"):
        validate_segment_sources(())
    with pytest.raises(SourceValidationError, match="MESSAGE_COUNT_EXCEEDED"):
        validate_segment_sources(tuple(message() for _ in range(129)))
    with pytest.raises(SourceValidationError, match="EMPTY_SEGMENT_SEQUENCE"):
        validate_segment_sources((message(),))
    with pytest.raises(SourceValidationError, match="SEGMENT_COUNT_EXCEEDED"):
        validate_segment_sources((message(*(segment() for _ in range(1025))),))
    with pytest.raises(SourceValidationError, match="TOTAL_SEGMENT_COUNT_EXCEEDED"):
        validate_segment_sources(
            (
                message(*(segment() for _ in range(600))),
                message(*(segment() for _ in range(600))),
            )
        )

    # --- Body-bearing or extra fields reject at the closed schema. ---
    with pytest.raises(Exception):
        _source_row(0, 0, content="body")
    with pytest.raises(Exception):
        _source_row(0, 0, extra_field=True)
    with pytest.raises(Exception):
        RequestContentSegmentV1(  # type: ignore[call-arg]
            source_category="TOOL_RESULT",
            source_path=AbsentV1(kind="ABSENT"),
            content="x",
            content_digest=hashlib.sha256(b"x").hexdigest(),
            byte_count=1,
            extra_field=True,
        )

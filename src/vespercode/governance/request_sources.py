"""T15.1 legacy step 15.A: request message/segment source validation.

Defines the closed request source vocabulary (categories, content
segments, messages, and the one-to-one segment/source projection) and
validates the category-specific path-presence contract (FILE_CONTENT
segments must carry a canonical path; HARNESS_PROTOCOL/TASK/MEMORY must be
pathless), the exact content digest/byte-count identity, and the 1..128 /
1..1024 cardinality bounds before any projection exists.  The derived
``SourceProjectionV1`` is the immutable ordered tuple of exactly one
``RequestSourceV1`` per segment at its exact zero-based message/segment
index.  Grant scope matching, subject construction, wait decisions, byte
charging, and request-body persistence remain out of scope (GREEN-4).
"""

from __future__ import annotations

import hashlib
from typing import Annotated, Literal, TypeAlias

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    Strict,
    StrictStr,
    field_validator,
    model_validator,
)

from vespercode.contracts.evidence import _DIGEST_RE
from vespercode.contracts.optional import OptionalCanonicalPathV1

RequestSourceCategoryV1: TypeAlias = Literal[
    "HARNESS_PROTOCOL",
    "TASK",
    "FILE_CONTENT",
    "TOOL_RESULT",
    "MEMORY",
    "FEEDBACK",
]
"""SPEC §4.4.3: the closed request source categories."""

SourceValidationCodeV1: TypeAlias = Literal[
    "EMPTY_MESSAGE_SEQUENCE",
    "MESSAGE_COUNT_EXCEEDED",
    "EMPTY_SEGMENT_SEQUENCE",
    "SEGMENT_COUNT_EXCEEDED",
    "TOTAL_SEGMENT_COUNT_EXCEEDED",
    "FILE_PATH_REQUIRED",
    "PATH_NOT_ALLOWED",
    "CONTENT_DIGEST_MISMATCH",
    "BYTE_COUNT_MISMATCH",
    "CONTENT_NOT_UTF8",
]
"""The closed rejection codes of the source/segment validation contract."""


class SourceValidationError(ValueError):
    """Closed rejection of one request source/segment contract violation.

    The exact error code is part of the closed vocabulary, so missing,
    cross-category, out-of-range, mismatched, or non-UTF-8 content
    identities all fail deterministically before any projection exists.
    """

    def __init__(self, error_code: SourceValidationCodeV1, message: str) -> None:
        super().__init__(f"{error_code}: {message}")
        self.error_code = error_code


def _require_digest_form(value: str) -> str:
    """Reject any spelling that is not exactly 64 lowercase hex chars."""
    if not isinstance(value, str) or _DIGEST_RE.fullmatch(value) is None:
        raise ValueError("must be exactly 64 lowercase hexadecimal characters")
    return value


class RequestContentSegmentV1(BaseModel):
    """SPEC §4.4.4: one ordered segment with its exact source identity.

    ``content_digest`` is the SHA-256 of the segment content's UTF-8 raw
    bytes and ``byte_count`` the same byte length; both must be declared
    exactly (the validator binds them to the actual content before any
    projection exists).
    """

    model_config = ConfigDict(extra="forbid", frozen=True)
    source_category: RequestSourceCategoryV1
    source_path: OptionalCanonicalPathV1
    content: StrictStr
    content_digest: StrictStr
    byte_count: Annotated[int, Strict(), Field(ge=0, le=65536)]

    @field_validator("content_digest")
    @classmethod
    def _digest_has_exact_form(cls, value: str) -> str:
        return _require_digest_form(value)

    @model_validator(mode="after")
    def _digest_and_byte_count_bind_the_content(self) -> RequestContentSegmentV1:
        try:
            raw = self.content.encode("utf-8")
        except UnicodeEncodeError as exc:
            raise ValueError(
                "segment content must be a UTF-8 scalar sequence"
            ) from exc
        if len(raw) != self.byte_count:
            raise ValueError(
                "byte_count must equal the exact UTF-8 byte length of the content"
            )
        if hashlib.sha256(raw).hexdigest() != self.content_digest:
            raise ValueError(
                "content_digest must equal the SHA-256 of the exact content bytes"
            )
        return self


class RequestMessageV1(BaseModel):
    """SPEC §4.4.4: one ordered request message with 1..1024 segments."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    role: Literal["SYSTEM", "USER"]
    segments: tuple[RequestContentSegmentV1, ...]


class RequestSourceV1(BaseModel):
    """SPEC §4.4.4: the one-to-one derived source index of one segment.

    The projection copies each segment's category, path, digest, and byte
    count and binds them to the segment's exact zero-based message and
    segment indices; the record never carries a body (GREEN-4).
    """

    model_config = ConfigDict(extra="forbid", frozen=True)
    message_index: Annotated[int, Strict(), Field(ge=0, le=127)]
    segment_index: Annotated[int, Strict(), Field(ge=0, le=1023)]
    source_category: RequestSourceCategoryV1
    source_path: OptionalCanonicalPathV1
    content_digest: StrictStr
    byte_count: Annotated[int, Strict(), Field(ge=0, le=65536)]

    @field_validator("content_digest")
    @classmethod
    def _digest_has_exact_form(cls, value: str) -> str:
        return _require_digest_form(value)


RequestMessageSequenceV1: TypeAlias = tuple[RequestMessageV1, ...]
"""The immutable ordered request-message tuple (SPEC §4.4.4, 1..128)."""

SourceProjectionV1: TypeAlias = tuple[RequestSourceV1, ...]
"""The immutable ordered one-to-one segment/source projection (§4.4.4)."""


def _segment_content_bytes(content: str) -> bytes:
    """The exact UTF-8 raw bytes of one segment, or fail closed."""
    try:
        return content.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise SourceValidationError(
            "CONTENT_NOT_UTF8", "segment content must be a UTF-8 scalar sequence"
        ) from exc


def _validate_segment(
    seg: RequestContentSegmentV1,
    message_index: int,
    segment_index: int,
) -> None:
    """Validate one segment's category/path/digest/byte identity contract.

    The path-presence contract comes from SPEC §4.4.4: FILE_CONTENT must
    carry a canonical path; HARNESS_PROTOCOL/TASK/MEMORY must be ABSENT;
    TOOL_RESULT/FEEDBACK may be pathless only for pure run-level,
    check-level, or control-plane facts.
    """
    if seg.source_category == "FILE_CONTENT" and seg.source_path.kind == "ABSENT":
        raise SourceValidationError(
            "FILE_PATH_REQUIRED",
            "FILE_CONTENT segments require a canonical source path",
        )
    if (
        seg.source_category in ("HARNESS_PROTOCOL", "TASK", "MEMORY")
        and seg.source_path.kind == "PRESENT"
    ):
        raise SourceValidationError(
            "PATH_NOT_ALLOWED",
            f"{seg.source_category} segments must not carry a source path",
        )
    raw = _segment_content_bytes(seg.content)
    if seg.content_digest != hashlib.sha256(raw).hexdigest():
        raise SourceValidationError(
            "CONTENT_DIGEST_MISMATCH",
            f"segment ({message_index}, {segment_index}) content digest does "
            "not bind its exact content bytes",
        )
    if seg.byte_count != len(raw):
        raise SourceValidationError(
            "BYTE_COUNT_MISMATCH",
            f"segment ({message_index}, {segment_index}) byte count does not "
            "equal its exact content byte length",
        )


def validate_segment_sources(
    messages: RequestMessageSequenceV1,
) -> SourceProjectionV1:
    """Validate every segment identity and derive the exact source projection.

    The sequence must contain 1..128 messages, each with 1..1024 segments,
    and the request-wide segment total must be 1..1024 (SPEC §4.4.4);
    every segment must satisfy its category-specific path-presence contract
    and bind its exact content digest and byte count.  Only then is the
    one-to-one projection produced (one ``RequestSourceV1`` per segment at
    its exact zero-based indices); any violation rejects before any
    projection exists.
    """
    if len(messages) == 0:
        raise SourceValidationError(
            "EMPTY_MESSAGE_SEQUENCE", "at least one request message is required"
        )
    if len(messages) > 128:
        raise SourceValidationError(
            "MESSAGE_COUNT_EXCEEDED", "at most 128 request messages are allowed"
        )
    projection: list[RequestSourceV1] = []
    total_segments = 0
    for message_index, msg in enumerate(messages):
        if len(msg.segments) == 0:
            raise SourceValidationError(
                "EMPTY_SEGMENT_SEQUENCE",
                f"message {message_index} must contain at least one segment",
            )
        if len(msg.segments) > 1024:
            raise SourceValidationError(
                "SEGMENT_COUNT_EXCEEDED",
                f"message {message_index} must contain at most 1024 segments",
            )
        total_segments += len(msg.segments)
        if total_segments > 1024:
            raise SourceValidationError(
                "TOTAL_SEGMENT_COUNT_EXCEEDED",
                "the request-wide segment total must be at most 1024",
            )
        for segment_index, seg in enumerate(msg.segments):
            _validate_segment(seg, message_index, segment_index)
            projection.append(
                RequestSourceV1(
                    message_index=message_index,
                    segment_index=segment_index,
                    source_category=seg.source_category,
                    source_path=seg.source_path,
                    content_digest=seg.content_digest,
                    byte_count=seg.byte_count,
                )
            )
    return tuple(projection)

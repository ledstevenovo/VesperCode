"""T11.1 legacy step 11.A: bounded text reads over one immutable tree.

``read_file`` observes the bound ``ReadableTreeV1`` protocol only: the
path must be a file path of the tree, the raw bytes are classified exactly
once by the shared supported-text classifier (T10.1), the BOM and newline
metadata decide body and line splitting, and the body is deterministically
truncated to ``max_bytes`` at a Unicode scalar boundary.  Mutable
workspace state, arbitrary paths, filesystem access, cursors, policy,
shell, and dispatch can never affect the result (GREEN-4).
"""

from __future__ import annotations

import hashlib

from vespercode.tools.file_actions import ReadFileActionV1
from vespercode.tools.file_results import (
    ReadFileResultV1,
    ReadFileSuccessV1,
    bounded_utf8_text,
    file_tool_error,
    split_text_lines,
)
from vespercode.trees.readable import ReadableTreeV1
from vespercode.trees.text_classifier import classify_supported_text

_UTF8_BOM = b"\xef\xbb\xbf"


def read_file(tree: ReadableTreeV1, action: ReadFileActionV1) -> ReadFileResultV1:
    """Read one bounded line range of one supported text file of *tree*.

    ``FILE_NOT_FOUND`` closes missing or drifted file paths, ``FILE_NOT_TEXT``
    closes non-text files (before any range check, SPEC §4.2.8), and
    ``READ_RANGE_OUT_OF_BOUNDS`` closes a ``start_line`` past the last line;
    a range crossing EOF returns the existing content with ``eof=true`` —
    unless the body is also byte-truncated by ``max_bytes``, in which case
    ``eof=false`` because the returned body does not reach EOF and the
    caller continues from ``end_line``.  An oversized body is truncated
    deterministically at ``max_bytes`` on a Unicode scalar boundary.
    """
    if action.path not in tree.list_file_paths():
        return file_tool_error(
            "FILE_NOT_FOUND", f"no tree file at {action.path.value!r}"
        )
    try:
        raw = tree.read_bytes(action.path)
    except KeyError:
        return file_tool_error(
            "FILE_NOT_FOUND",
            f"the enumerated tree file {action.path.value!r} is no longer readable",
        )
    classification = classify_supported_text(raw)
    if classification.kind != "TEXT_FILE":
        return file_tool_error(
            "FILE_NOT_TEXT", f"{action.path.value!r} is not a supported text file"
        )
    metadata = classification.text_profile.value
    body = raw[len(_UTF8_BOM) :] if metadata.encoding == "UTF8_BOM" else raw
    decoded = body.decode("utf-8")
    terminator = "\r\n" if metadata.newline == "CRLF" else "\n"
    lines = split_text_lines(decoded, terminator)
    last_line = len(lines)
    if action.start_line > last_line:
        return file_tool_error(
            "READ_RANGE_OUT_OF_BOUNDS",
            f"start_line {action.start_line} exceeds the last line {last_line} "
            f"of {action.path.value!r}",
        )
    requested = lines[action.start_line - 1 : action.start_line - 1 + action.line_count]
    full_body = "".join(line + terminator for line in requested)
    bounded = bounded_utf8_text(full_body, action.max_bytes)
    truncated = bounded != full_body
    end_line = _end_line(bounded, terminator, action.start_line)
    return ReadFileSuccessV1(
        kind="SUCCESS",
        path=action.path,
        file_digest=hashlib.sha256(raw).hexdigest(),
        start_line=action.start_line,
        end_line=end_line,
        eof=not truncated and end_line == last_line,
        text=bounded,
    )


def _end_line(body: str, terminator: str, start_line: int) -> int:
    """The 1-based line containing the last byte of *body*.

    A truncated body may end mid-line or mid-CRLF; the line count is the
    number of complete terminators plus the unterminated final line.
    """
    count = body.count(terminator)
    if body.endswith(terminator):
        return start_line + count - 1
    return start_line + count

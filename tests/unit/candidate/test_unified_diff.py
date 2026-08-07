"""T12.1 legacy step 12.A: strict UNIFIED_DIFF_V1 parser tests.

The exact RED test (trailing bytes after a complete patch reject with the
closed ``PATCH_PARSE_FAILED`` / ``PATCH_SCHEMA_INVALID`` failure), the
complete no-BOM UTF-8/LF grammar matrix (registry 12.A: only complete
CREATE/REPLACE patches parse; DELETE, RENAME, binary, mode/link, fuzzy
offset, duplicate path, malformed header/hunk, or trailing bytes are
rejected), and the domain assertions for the closed parsed-patch and
parse-failure contracts.  Tree reads, old-byte matching, edit
application, candidate limits, path authorization, and revision
publication remain out of scope (GREEN-4).
"""

from __future__ import annotations

import pytest

# The parsed-patch contracts are pydantic runtime models; the hash-locked
# gate toolchain does not install runtime dependencies, so this module
# skips cleanly there instead of failing at collection (formal env runs it
# fully).
pytest.importorskip("pydantic")

from pydantic import ValidationError

from vespercode.candidate.unified_diff import (
    ParsedPatchEntryV1,
    ParsedPatchV1,
    PatchParseFailureV1,
    parse_unified_diff_v1,
)


def valid_replace_patch() -> str:
    """One complete strict REPLACE patch for ``src/a.py`` (x = 1 -> x = 2)."""
    return "--- a/src/a.py\n+++ b/src/a.py\n@@ -1,1 +1,1 @@\n-x = 1\n+x = 2\n"


def valid_create_patch() -> str:
    """One complete strict CREATE patch for a new ``src/new.py`` file."""
    return (
        "--- /dev/null\n+++ b/src/new.py\n@@ -0,0 +1,2 @@\n+def new():\n+    return 1\n"
    )


def valid_two_entry_patch() -> str:
    """One strict two-file patch: REPLACE src/a.py and CREATE src/b.py."""
    return (
        valid_replace_patch()
        + "\n"
        + "--- /dev/null\n"
        + "+++ b/src/b.py\n"
        + "@@ -0,0 +1,1 @@\n"
        + "+value = 2\n"
    )


def test_trailing_unparsed_patch_bytes_are_rejected() -> None:
    result = parse_unified_diff_v1(valid_replace_patch() + "\ntrailing")
    assert result.kind == "PATCH_PARSE_FAILED"
    assert result.error_code == "PATCH_SCHEMA_INVALID"


def test_unified_diff_grammar_matrix() -> None:
    """Registry 12.A: only complete CREATE/REPLACE patches parse; every
    prohibited or malformed form rejects closed with the stable code.

    Accepted rows pin the parsed shape (entry count and the first entry's
    operation); rejected rows pin the exact closed failure code.
    """
    rows: tuple[tuple[str, str | None, int | None, str | None], ...] = (
        # (patch text, expected kind, expected entry count, expected code)
        # --- Complete supported forms parse. ---
        (valid_replace_patch(), "PATCH_PARSED", 1, None),
        (valid_create_patch(), "PATCH_PARSED", 1, None),
        (valid_two_entry_patch(), "PATCH_PARSED", 2, None),
        # A multi-hunk REPLACE parses when every range chains.
        (
            "--- a/src/a.py\n"
            "+++ b/src/a.py\n"
            "@@ -1,1 +1,1 @@\n"
            "-x = 1\n"
            "+x = 2\n"
            "@@ -3,1 +3,1 @@\n"
            "-z = 3\n"
            "+z = 4\n",
            "PATCH_PARSED",
            1,
            None,
        ),
        # A pure-insertion hunk range (count 0, start > 0) parses.
        (
            "--- a/src/a.py\n+++ b/src/a.py\n@@ -2,0 +2,1 @@\n+inserted = True\n",
            "PATCH_PARSED",
            1,
            None,
        ),
        # A context-only hunk is well formed (counts still exact).
        (
            "--- a/src/a.py\n+++ b/src/a.py\n@@ -1,2 +1,2 @@\n x = 1\n y = 2\n",
            "PATCH_PARSED",
            1,
            None,
        ),
        # --- DELETE, RENAME, case-only, mode, and binary forms reject
        # with the closed unsupported-operation failure. ---
        (
            "--- a/src/a.py\n+++ /dev/null\n@@ -1,1 +0,0 @@\n-x = 1\n",
            "PATCH_PARSE_FAILED",
            None,
            "UNSUPPORTED_PATCH_OPERATION",
        ),
        (
            "--- a/src/a.py\n+++ b/src/b.py\n@@ -1,1 +1,1 @@\n-x = 1\n+y = 1\n",
            "PATCH_PARSE_FAILED",
            None,
            "UNSUPPORTED_PATCH_OPERATION",
        ),
        # A path that changes only by case is a rename-family form.
        (
            "--- a/src/a.py\n+++ b/src/A.py\n@@ -1,1 +1,1 @@\n-x = 1\n+x = 1\n",
            "PATCH_PARSE_FAILED",
            None,
            "UNSUPPORTED_PATCH_OPERATION",
        ),
        (
            "--- a/src/a.py\n"
            "+++ b/src/a.py\n"
            "old mode 100644\n"
            "new mode 100755\n"
            "@@ -1,1 +1,1 @@\n"
            "-x = 1\n"
            "+x = 2\n",
            "PATCH_PARSE_FAILED",
            None,
            "UNSUPPORTED_PATCH_OPERATION",
        ),
        (
            "--- a/src/a.py\n"
            "+++ b/src/a.py\n"
            "new file mode 100644\n"
            "@@ -0,0 +1,1 @@\n"
            "+x = 1\n",
            "PATCH_PARSE_FAILED",
            None,
            "UNSUPPORTED_PATCH_OPERATION",
        ),
        (
            "--- a/src/a.py\n"
            "+++ b/src/a.py\n"
            "rename from src/a.py\n"
            "rename to src/b.py\n"
            "@@ -1,1 +1,1 @@\n"
            "-x = 1\n"
            "+x = 1\n",
            "PATCH_PARSE_FAILED",
            None,
            "UNSUPPORTED_PATCH_OPERATION",
        ),
        (
            "Binary files a/src/a.py and b/src/a.py differ\n",
            "PATCH_PARSE_FAILED",
            None,
            "PATCH_SCHEMA_INVALID",
        ),
        (
            "--- a/src/a.py\n+++ b/src/a.py\nGIT binary patch\nliteral 4\n",
            "PATCH_PARSE_FAILED",
            None,
            "UNSUPPORTED_PATCH_OPERATION",
        ),
        # --- Malformed headers, hunks, ranges, and content reject with
        # the closed schema-invalid failure. ---
        # Timestamps on the file headers.
        (
            "--- a/src/a.py 2026-08-06 12:00:00\n"
            "+++ b/src/a.py 2026-08-06 12:00:01\n"
            "@@ -1,1 +1,1 @@\n"
            "-x = 1\n"
            "+x = 2\n",
            "PATCH_PARSE_FAILED",
            None,
            "PATCH_SCHEMA_INVALID",
        ),
        # A no-newline marker is a prohibited form.
        (
            "--- a/src/a.py\n"
            "+++ b/src/a.py\n"
            "@@ -1,1 +1,1 @@\n"
            "-x = 1\n"
            "\\ No newline at end of file\n"
            "+x = 2\n",
            "PATCH_PARSE_FAILED",
            None,
            "PATCH_SCHEMA_INVALID",
        ),
        # Header prefixes are mandatory.
        (
            "--- src/a.py\n+++ src/a.py\n@@ -1,1 +1,1 @@\n",
            "PATCH_PARSE_FAILED",
            None,
            "PATCH_SCHEMA_INVALID",
        ),
        (
            "--- /dev/null\n+++ src/new.py\n@@ -0,0 +1,1 @@\n+x = 1\n",
            "PATCH_PARSE_FAILED",
            None,
            "PATCH_SCHEMA_INVALID",
        ),
        # An entry with no hunks is incomplete.
        (
            "--- a/src/a.py\n+++ b/src/a.py\n",
            "PATCH_PARSE_FAILED",
            None,
            "PATCH_SCHEMA_INVALID",
        ),
        # A CREATE entry must declare an empty old range.
        (
            "--- /dev/null\n+++ b/src/new.py\n@@ -1,1 +1,1 @@\n+x = 1\n",
            "PATCH_PARSE_FAILED",
            None,
            "PATCH_SCHEMA_INVALID",
        ),
        # Hunk range forms that are malformed.  (``@@ -1 +1 @@`` with the
        # count omitted is standard syntax and parses; non-integer,
        # multi-range, and unterminated forms reject.)
        (
            "--- a/src/a.py\n+++ b/src/a.py\n@@ -1 +1 @@\n-x = 1\n+x = 2\n",
            "PATCH_PARSED",
            1,
            None,
        ),
        (
            "--- a/src/a.py\n+++ b/src/a.py\n@@ -1,1,1 +1,1 @@\n-x = 1\n+x = 2\n",
            "PATCH_PARSE_FAILED",
            None,
            "PATCH_SCHEMA_INVALID",
        ),
        (
            "--- a/src/a.py\n+++ b/src/a.py\n@@ -1,1 +1,1\n-x = 1\n+x = 2\n",
            "PATCH_PARSE_FAILED",
            None,
            "PATCH_SCHEMA_INVALID",
        ),
        (
            "--- a/src/a.py\n"
            "+++ b/src/a.py\n"
            "@@ -1,1 +1,1 @@ trailing\n"
            "-x = 1\n"
            "+x = 2\n",
            "PATCH_PARSE_FAILED",
            None,
            "PATCH_SCHEMA_INVALID",
        ),
        (
            "--- a/src/a.py\n+++ b/src/a.py\n@@ --1,1 +1,1 @@\n-x = 1\n+x = 2\n",
            "PATCH_PARSE_FAILED",
            None,
            "PATCH_SCHEMA_INVALID",
        ),
        (
            "--- a/src/a.py\n+++ b/src/a.py\n@@ -1,1 +1,-1 @@\n-x = 1\n+x = 2\n",
            "PATCH_PARSE_FAILED",
            None,
            "PATCH_SCHEMA_INVALID",
        ),
        # Declared counts must equal the actual lines.
        (
            "--- a/src/a.py\n+++ b/src/a.py\n@@ -1,2 +1,2 @@\n-x = 1\n+x = 2\n",
            "PATCH_PARSE_FAILED",
            None,
            "PATCH_SCHEMA_INVALID",
        ),
        (
            "--- a/src/a.py\n+++ b/src/a.py\n@@ -1,1 +1,2 @@\n-x = 1\n+x = 2\n",
            "PATCH_PARSE_FAILED",
            None,
            "PATCH_SCHEMA_INVALID",
        ),
        # An empty hunk is malformed.
        (
            "--- a/src/a.py\n+++ b/src/a.py\n@@ -0,0 +0,0 @@\n",
            "PATCH_PARSE_FAILED",
            None,
            "PATCH_SCHEMA_INVALID",
        ),
        # Hunk ranges must chain without overlap.
        (
            "--- a/src/a.py\n"
            "+++ b/src/a.py\n"
            "@@ -1,3 +1,3 @@\n"
            " a\n"
            " b\n"
            " c\n"
            "@@ -2,1 +2,1 @@\n"
            "-b\n"
            "+B\n",
            "PATCH_PARSE_FAILED",
            None,
            "PATCH_SCHEMA_INVALID",
        ),
        # A hunk content line without a prefix character is malformed.
        (
            "--- a/src/a.py\n"
            "+++ b/src/a.py\n"
            "@@ -1,1 +1,1 @@\n"
            "-x = 1\n"
            "+x = 2\n"
            "no prefix\n",
            "PATCH_PARSE_FAILED",
            None,
            "PATCH_SCHEMA_INVALID",
        ),
        # A blank line inside a hunk is an unparsed gap.
        (
            "--- a/src/a.py\n+++ b/src/a.py\n@@ -1,1 +1,1 @@\n-x = 1\n\n+x = 2\n",
            "PATCH_PARSE_FAILED",
            None,
            "PATCH_SCHEMA_INVALID",
        ),
        # Duplicate entry paths violate entry uniqueness.
        (
            "--- a/src/a.py\n"
            "+++ b/src/a.py\n"
            "@@ -1,1 +1,1 @@\n"
            "-x = 1\n"
            "+x = 2\n"
            "\n"
            "--- a/src/a.py\n"
            "+++ b/src/a.py\n"
            "@@ -1,1 +1,1 @@\n"
            "-x = 1\n"
            "+x = 3\n",
            "PATCH_PARSE_FAILED",
            None,
            "PATCH_SCHEMA_INVALID",
        ),
        # Windows case-fold and Unicode-colliding entry paths are
        # ambiguous aliases and violate entry uniqueness.
        (
            "--- a/src/a.py\n"
            "+++ b/src/a.py\n"
            "@@ -1,1 +1,1 @@\n"
            "-x = 1\n"
            "+x = 2\n"
            "\n"
            "--- a/src/A.py\n"
            "+++ b/src/A.py\n"
            "@@ -1,1 +1,1 @@\n"
            "-x = 1\n"
            "+x = 3\n",
            "PATCH_PARSE_FAILED",
            None,
            "PATCH_SCHEMA_INVALID",
        ),
        # Absolute and drive paths are malformed headers.
        (
            "--- a/C:/src/a.py\n+++ b/C:/src/a.py\n@@ -1,1 +1,1 @@\n-x = 1\n+x = 2\n",
            "PATCH_PARSE_FAILED",
            None,
            "PATCH_SCHEMA_INVALID",
        ),
        (
            "--- a/../src/a.py\n+++ b/../src/a.py\n@@ -1,1 +1,1 @@\n-x = 1\n+x = 2\n",
            "PATCH_PARSE_FAILED",
            None,
            "PATCH_SCHEMA_INVALID",
        ),
        # --- Document-level encoding violations reject. ---
        # A UTF-8 BOM document is prohibited.
        (
            "\ufeff" + valid_replace_patch(),
            "PATCH_PARSE_FAILED",
            None,
            "PATCH_SCHEMA_INVALID",
        ),
        # CRLF line endings are prohibited (LF discipline).
        (
            "--- a/src/a.py\r\n"
            "+++ b/src/a.py\r\n"
            "@@ -1,1 +1,1 @@\r\n"
            "-x = 1\r\n"
            "+x = 2\r\n",
            "PATCH_PARSE_FAILED",
            None,
            "PATCH_SCHEMA_INVALID",
        ),
        # A bare CR anywhere is prohibited.
        (
            "--- a/src/a.py\n+++ b/src/a.py\n@@ -1,1 +1,1 @@\n-x = 1\r+x = 2\n",
            "PATCH_PARSE_FAILED",
            None,
            "PATCH_SCHEMA_INVALID",
        ),
        # A NUL byte cannot appear in a text patch.
        (
            "--- a/src/a.py\n+++ b/src/a.py\n@@ -1,1 +1,1 @@\n-x = 1\n+x = \x002\n",
            "PATCH_PARSE_FAILED",
            None,
            "PATCH_SCHEMA_INVALID",
        ),
        # --- Full input consumption. ---
        # Missing final newline.
        (
            "--- a/src/a.py\n+++ b/src/a.py\n@@ -1,1 +1,1 @@\n-x = 1\n+x = 2",
            "PATCH_PARSE_FAILED",
            None,
            "PATCH_SCHEMA_INVALID",
        ),
        # An empty patch has no entry.
        ("", "PATCH_PARSE_FAILED", None, "PATCH_SCHEMA_INVALID"),
        # Trailing bytes after the last hunk (the exact RED shape).
        (
            valid_replace_patch() + "\ntrailing",
            "PATCH_PARSE_FAILED",
            None,
            "PATCH_SCHEMA_INVALID",
        ),
        # A second blank separator line is unparsed content.
        (
            "--- a/src/a.py\n+++ b/src/a.py\n@@ -1,1 +1,1 @@\n-x = 1\n+x = 2\n\n\n",
            "PATCH_PARSE_FAILED",
            None,
            "PATCH_SCHEMA_INVALID",
        ),
    )
    for patch_text, expected_kind, expected_count, expected_code in rows:
        result = parse_unified_diff_v1(patch_text)
        assert result.kind == expected_kind, patch_text
        if expected_kind == "PATCH_PARSED":
            assert isinstance(result, ParsedPatchV1)
            assert len(result.entries) == expected_count, patch_text
        else:
            assert isinstance(result, PatchParseFailureV1)
            assert result.error_code == expected_code, patch_text


def test_parse_result_binds_entries_ranges_and_lines_exactly() -> None:
    parsed = parse_unified_diff_v1(valid_replace_patch())
    assert isinstance(parsed, ParsedPatchV1)
    assert parsed.kind == "PATCH_PARSED"
    (entry,) = parsed.entries
    assert isinstance(entry, ParsedPatchEntryV1)
    assert entry.operation == "REPLACE"
    assert entry.path.value == "src/a.py"
    assert entry.old_path == "a/src/a.py"
    assert entry.new_path == "b/src/a.py"
    (hunk,) = entry.hunks
    assert hunk.old_start == 1
    assert hunk.old_count == 1
    assert hunk.new_start == 1
    assert hunk.new_count == 1
    kinds = tuple(line.kind for line in hunk.lines)
    assert kinds == ("DELETE", "ADD")
    assert hunk.lines[0].text == "x = 1"
    assert hunk.lines[1].text == "x = 2"


def test_parse_create_binds_dev_null_old_side() -> None:
    parsed = parse_unified_diff_v1(valid_create_patch())
    assert isinstance(parsed, ParsedPatchV1)
    (entry,) = parsed.entries
    assert entry.operation == "CREATE"
    assert entry.old_path == "/dev/null"
    assert entry.path.value == "src/new.py"
    (hunk,) = entry.hunks
    assert hunk.old_start == 0
    assert hunk.old_count == 0
    assert hunk.new_start == 1
    assert hunk.new_count == 2
    assert tuple(line.kind for line in hunk.lines) == ("ADD", "ADD")


def test_parse_is_deterministic_and_side_effect_free() -> None:
    first = parse_unified_diff_v1(valid_two_entry_patch())
    second = parse_unified_diff_v1(valid_two_entry_patch())
    assert first == second
    assert isinstance(first, ParsedPatchV1)
    assert len(first.entries) == 2
    assert [entry.path.value for entry in first.entries] == [
        "src/a.py",
        "src/b.py",
    ]
    # Repeated parsing of a failure is byte-identical too.
    failure = parse_unified_diff_v1(valid_replace_patch() + "\ntrailing")
    again = parse_unified_diff_v1(valid_replace_patch() + "\ntrailing")
    assert failure == again


def test_parse_failure_is_closed_and_deterministic() -> None:
    failure = parse_unified_diff_v1("garbage")
    assert isinstance(failure, PatchParseFailureV1)
    assert failure.kind == "PATCH_PARSE_FAILED"
    assert failure.error_code == "PATCH_SCHEMA_INVALID"
    assert failure.reason
    # Every failure is a closed result; nothing is raised for bad text.
    for bad in ("", "\n", "--- only", "+++ b/x", "@@ -1 +1 @@", " "):
        result = parse_unified_diff_v1(bad)
        assert result.kind == "PATCH_PARSE_FAILED"
    with pytest.raises(TypeError):
        parse_unified_diff_v1(b"not text")  # type: ignore[arg-type]


def test_parsed_patch_schema_is_closed() -> None:
    """The parsed patch and failure contracts reject unknown/missing fields."""
    invalid: tuple[dict[str, object], ...] = (
        {"kind": "PATCH_PARSED", "entries": "x"},
        {"kind": "PATCH_PARSE_FAILED"},
        {"kind": "PATCH_PARSE_FAILED", "error_code": "UNKNOWN", "reason": "x"},
        {"kind": "MAYBE", "entries": ()},
        {"kind": "PATCH_PARSED", "entries": (), "extra": 1},
    )
    for payload in invalid:
        with pytest.raises(ValidationError):
            if payload["kind"] == "PATCH_PARSED":
                ParsedPatchV1.model_validate(payload)
            else:
                PatchParseFailureV1.model_validate(payload)
    # The closed entry shapes reject malformed rows.
    bad_entry: dict[str, object] = {
        "schema_version": 1,
        "operation": "DELETE",
        "path": {"value": "src/a.py"},
        "old_path": "a/src/a.py",
        "new_path": "b/src/a.py",
        "hunks": (),
    }
    with pytest.raises(ValidationError):
        ParsedPatchEntryV1.model_validate(bad_entry)

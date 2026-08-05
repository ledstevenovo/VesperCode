"""T04.2 legacy step 4.D: lexical canonical relative path tests."""

from __future__ import annotations

import pytest

from src.vespercode.canonical.path_v1 import (
    CanonicalPathErrorV1,
    CanonicalRelativePathV1,
    validate_canonical_relative_path,
)


def test_device_and_parent_paths_are_rejected() -> None:
    for value in ("CON", "src/../a.py", r"C:\src\a.py", "//server/share/a.py"):
        with pytest.raises(CanonicalPathErrorV1):
            validate_canonical_relative_path(value)


def test_canonical_path_sentinel_matrix() -> None:
    """SPEC §0.1 CanonicalRelativePathV1 lexical sentinels and closures.

    The rejected rows pair each unsupported lexical form with its closed
    deterministic error code; the accepted rows must round-trip the exact
    input string (normalization-free, value-preserving).
    """
    accepted = (
        "src/a.py",
        "src",
        "a",
        "docs/readme.md",
        "中文/文件.py",
        ".gitignore",
        "src/__init__.py",
        "a b/c d.py",
        "src/src/a.py",
        "A.py/B.txt",
        "nonexistent_dir/file.py",
    )
    for value in accepted:
        assert validate_canonical_relative_path(value).value == value
    rejected = (
        ("", "PATH_EMPTY"),
        (".", "PATH_ROOT"),
        ("./", "PATH_ROOT"),
        ("/", "PATH_ROOT"),
        ("/a.py", "PATH_ABSOLUTE"),
        ("//server/share/a.py", "PATH_UNC"),
        ("C:/src/a.py", "PATH_DRIVE"),
        ("C:a.py", "PATH_DRIVE"),
        (r"C:\src\a.py", "PATH_DRIVE"),
        ("a.py:stream", "PATH_ADS"),
        ("x/a:stream", "PATH_ADS"),
        (r"a\b.py", "PATH_BACKSLASH"),
        ("a*b.py", "PATH_INVALID_CHARACTER"),
        ("a<b", "PATH_INVALID_CHARACTER"),
        ("a>b", "PATH_INVALID_CHARACTER"),
        ('a"b', "PATH_INVALID_CHARACTER"),
        ("a|b", "PATH_INVALID_CHARACTER"),
        ("a?b", "PATH_INVALID_CHARACTER"),
        ("a\tb.py", "PATH_INVALID_CHARACTER"),
        ("a\x00b.py", "PATH_INVALID_CHARACTER"),
        ("a//b", "PATH_EMPTY_SEGMENT"),
        ("a/", "PATH_EMPTY_SEGMENT"),
        ("./a.py", "PATH_DOT"),
        ("a/./b", "PATH_DOT"),
        ("..", "PATH_PARENT"),
        ("../a.py", "PATH_PARENT"),
        ("src/../a.py", "PATH_PARENT"),
        ("a.py.", "PATH_TRAILING_DOT_OR_SPACE"),
        ("a.py ", "PATH_TRAILING_DOT_OR_SPACE"),
        ("a /b", "PATH_TRAILING_DOT_OR_SPACE"),
        ("CON", "PATH_RESERVED_NAME"),
        ("con.txt", "PATH_RESERVED_NAME"),
        ("a/PRN/b", "PATH_RESERVED_NAME"),
        ("AUX.py", "PATH_RESERVED_NAME"),
        ("COM1", "PATH_RESERVED_NAME"),
        ("lpt9", "PATH_RESERVED_NAME"),
        ("nul", "PATH_RESERVED_NAME"),
        ("A/a", "PATH_CASE_COLLISION"),
        ("src/SRC/x", "PATH_CASE_COLLISION"),
        ("README.md/readme.MD", "PATH_CASE_COLLISION"),
        ("a\u0301.py/\u00e1.py", "PATH_UNICODE_COLLISION"),
    )
    for value, expected_code in rejected:
        with pytest.raises(CanonicalPathErrorV1) as excinfo:
            validate_canonical_relative_path(value)
        assert excinfo.value.error_code == expected_code


def test_value_object_keeps_the_total_invariant() -> None:
    value = CanonicalRelativePathV1("src/a.py")
    assert value.value == "src/a.py"
    with pytest.raises(CanonicalPathErrorV1):
        CanonicalRelativePathV1("src/../a.py")
    with pytest.raises(CanonicalPathErrorV1):
        CanonicalRelativePathV1(123)  # type: ignore[arg-type]

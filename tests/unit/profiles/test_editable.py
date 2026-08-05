"""T06.1 legacy step 6.A: immutable editable-path policy tests.

The sole built-in policy matches only at canonical segment boundaries and
rejects every missing, renamed, extra, or drifted field; profile
resolution, endpoints, requests, and mutable policy overrides remain out
of scope (GREEN-4).
"""

from __future__ import annotations

import json
from typing import cast

import pytest

# The policy is a pydantic runtime contract; the hash-locked gate toolchain
# does not install runtime dependencies, so this module skips cleanly there
# instead of failing at collection (formal env runs it fully).
pytest.importorskip("pydantic")

from pydantic import ValidationError

from src.vespercode.canonical.path_v1 import (
    CanonicalPathErrorV1,
    CanonicalRelativePathV1,
)
from src.vespercode.profiles.editable import (
    EditableOperationV1,
    EditablePathPolicyV1,
    digest_editable_path_policy,
    load_editable_path_policy,
)

# The §0.1 identity of the frozen T02.4 built-in policy (SPEC §1.4.1),
# independently recomputed by both review stages.
_BUILTIN_POLICY_DIGEST = (
    "b857afca63e50a888ee183bd7ac8c7f739be7b60a94fc4f9c55c0a606db144ab"
)


def path(value: str) -> CanonicalRelativePathV1:
    """One canonical repository-relative path test value."""
    return CanonicalRelativePathV1(value)


def built_in_editable_policy_bytes() -> bytes:
    """The exact four built-in policy fields before digest computation."""
    return json.dumps(
        {
            "schema_version": 1,
            "policy_id": "PYTHON_SRC_ONLY_V1",
            "editable_directory_roots": ["src"],
            "allowed_operations": ["CREATE", "REPLACE"],
        },
        sort_keys=True,
    ).encode("utf-8")


def built_in_editable_policy() -> EditablePathPolicyV1:
    """The sole built-in editable path policy instance (SPEC §1.4.1)."""
    return load_editable_path_policy(built_in_editable_policy_bytes())


def test_src_prefix_without_segment_boundary_is_not_editable() -> None:
    policy = built_in_editable_policy()
    assert policy.schema_version == 1
    assert policy.policy_id == "PYTHON_SRC_ONLY_V1"
    assert policy.editable_directory_roots == (path("src"),)
    assert policy.allowed_operations == ("CREATE", "REPLACE")
    assert policy.digest == digest_editable_path_policy(policy)
    assert policy.matches(path("src_backup/x.py"), "REPLACE") is False


def test_editable_policy_path_operation_matrix() -> None:
    """SPEC §1.4.1 segment-boundary matching and closed rejection matrix.

    ``src`` descendants qualify for every allowed operation; the directory
    root itself, prefix aliases, noncanonical paths, unsupported
    operations, and every missing, renamed, extra, or drifted field reject
    deterministically.
    """
    policy = built_in_editable_policy()
    assert policy.digest == _BUILTIN_POLICY_DIGEST
    for operation in ("CREATE", "REPLACE"):
        assert policy.matches(path("src/a.py"), operation) is True
        assert policy.matches(path("src/pkg/a.py"), operation) is True
        assert policy.matches(path("src/deep/nested/entry.txt"), operation) is True
    # The directory root itself is never a file entry.
    assert policy.matches(path("src"), "CREATE") is False
    assert policy.matches(path("src"), "REPLACE") is False
    # Prefix aliases do not cross the canonical segment boundary.
    for alias in ("src-old/a.py", "src2/a.py", "src_backup/x.py", "src-2/a.py"):
        assert policy.matches(path(alias), "REPLACE") is False
    # Unsupported operations reject (the caller-facing literal is closed;
    # a raw string can only reach the runtime check through an unchecked
    # cast, which the closed schema also refuses via ``allowed_operations``).
    assert (
        policy.matches(path("src/a.py"), cast(EditableOperationV1, "DELETE")) is False
    )
    # Noncanonical path forms reject before any matching exists.
    for noncanonical in (
        "src/",
        "src//a.py",
        "./src/a.py",
        "src/../a.py",
        "src\\a.py",
        "C:/src/a.py",
    ):
        with pytest.raises(CanonicalPathErrorV1):
            path(noncanonical)

    def drift(**fields: object) -> bytes:
        payload: dict[str, object] = {
            "schema_version": 1,
            "policy_id": "PYTHON_SRC_ONLY_V1",
            "editable_directory_roots": ["src"],
            "allowed_operations": ["CREATE", "REPLACE"],
        }
        payload.update(fields)
        return json.dumps(payload, sort_keys=True).encode("utf-8")

    # Mutable overrides, renamed values, type-confused spellings, and
    # unknown values reject.
    for drifted_bytes in (
        drift(editable_directory_roots=["src", "tests"]),
        drift(editable_directory_roots=["tests"]),
        drift(allowed_operations=["CREATE"]),
        drift(allowed_operations=["CREATE", "DELETE"]),
        drift(allowed_operations=["REPLACE", "CREATE"]),
        drift(schema_version=2),
        drift(schema_version=True),
        drift(schema_version=1.0),
        drift(schema_version="1"),
        drift(policy_id="OTHER_POLICY_V1"),
        drift(extra_field=1),
        drift(digest="0" * 64),  # the digest is computed, never read from input
    ):
        with pytest.raises(ValidationError):
            load_editable_path_policy(drifted_bytes)
    # Missing and renamed fields reject before digest acceptance.
    for malformed_bytes in (
        json.dumps(
            {
                "schema_version": 1,
                "policy_id": "PYTHON_SRC_ONLY_V1",
                "editable_directory_roots": ["src"],
            },
            sort_keys=True,
        ).encode("utf-8"),
        json.dumps(
            {
                "schema_version": 1,
                "policy_id": "PYTHON_SRC_ONLY_V1",
                "editable_directory_roots": ["src"],
                "operations": ["CREATE"],
            },
            sort_keys=True,
        ).encode("utf-8"),
    ):
        with pytest.raises(ValidationError):
            load_editable_path_policy(malformed_bytes)
    # Non-JSON and non-object bytes reject deterministically.
    for non_object_bytes in (b"not json", b"[]", b"null", b"\xff\xfe"):
        with pytest.raises(ValueError):
            load_editable_path_policy(non_object_bytes)
    # A self-consistent non-built-in record can never exist: a drifted
    # digest and a non-64-hex digest both reject at model construction.
    with pytest.raises(ValidationError):
        EditablePathPolicyV1(
            schema_version=1,
            policy_id="PYTHON_SRC_ONLY_V1",
            editable_directory_roots=(path("src"),),
            allowed_operations=("CREATE", "REPLACE"),
            digest="0" * 64,
        )
    with pytest.raises(ValidationError):
        EditablePathPolicyV1(
            schema_version=1,
            policy_id="PYTHON_SRC_ONLY_V1",
            editable_directory_roots=(path("src"),),
            allowed_operations=("CREATE", "REPLACE"),
            digest="x",
        )
    # The 64-lowercase-hex digest form is exact at both boundaries.
    for bad_digest in ("0" * 63, "0" * 65, "A" * 64):
        with pytest.raises(ValidationError):
            EditablePathPolicyV1(
                schema_version=1,
                policy_id="PYTHON_SRC_ONLY_V1",
                editable_directory_roots=(path("src"),),
                allowed_operations=("CREATE", "REPLACE"),
                digest=bad_digest,
            )
    for type_confused in (True, 1.0, "1", 2, None):
        with pytest.raises(ValidationError):
            EditablePathPolicyV1.model_validate(
                {
                    "schema_version": type_confused,
                    "policy_id": "PYTHON_SRC_ONLY_V1",
                    "editable_directory_roots": (path("src"),),
                    "allowed_operations": ("CREATE", "REPLACE"),
                    "digest": policy.digest,
                }
            )
    # The built-in record round-trips byte-deterministically.
    loaded = load_editable_path_policy(built_in_editable_policy_bytes())
    assert loaded == policy
    assert loaded.model_dump() == policy.model_dump()

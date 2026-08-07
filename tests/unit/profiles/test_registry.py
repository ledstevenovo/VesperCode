"""T06.4 legacy step 6.E: built-in profile registry resolution tests.

The exact built-in editable, reference, LLM, and endpoint resources
resolve deterministically; every missing, duplicate, extra, drifted,
cross-profile, or unknown id rejects before a Run exists.  Mutators,
external discovery, run-request validation, and adapter behavior remain
out of scope (GREEN-4).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

# The registry is a pydantic runtime contract; the hash-locked gate
# toolchain does not install runtime dependencies, so this module skips
# cleanly there instead of failing at collection (formal env runs it fully).
pytest.importorskip("pydantic")

from pydantic import ValidationError

from vespercode.canonical.digest import domain_digest
from vespercode.canonical.json_v1 import CanonicalValueV1
from vespercode.profiles.endpoints import UnknownEndpointError
from vespercode.profiles.reference import ProfileIntegrityError
from vespercode.profiles.registry import (
    DuplicateProfileError,
    ExtraProfileError,
    MissingProfileError,
    UnknownProfileError,
    build_profile_registry,
)

# The frozen §0.1 identity pins of the packaged built-ins (T06.2/T06.3
# gold pins, independently recomputed by both review stages).
_MANIFEST_DIGEST = "2650fc34ac3a2fa0add4d4f0572c6b8b416f322a9f864d8c34bcd193858844b5"
_POLICY_DIGEST = "b857afca63e50a888ee183bd7ac8c7f739be7b60a94fc4f9c55c0a606db144ab"
_MOCK_DIGEST = "3fd39f821cae060b3bd0b382bfcd4843cbb465269b1487200582d4bb4346e4a9"
_OPENAI_DIGEST = "cb46690ef08202e120b71823d3de8ae1c31c903af6b0129984a9a4e893dd3f9c"

_BUILTIN_DIR = (
    Path(__file__).resolve().parents[3] / "src" / "vespercode" / "profiles" / "builtin"
)

_EDITABLE_BUILTIN_BYTES = json.dumps(
    {
        "schema_version": 1,
        "policy_id": "PYTHON_SRC_ONLY_V1",
        "editable_directory_roots": ["src"],
        "allowed_operations": ["CREATE", "REPLACE"],
    },
    sort_keys=True,
).encode("utf-8")


def packaged_reference_bytes() -> bytes:
    """The packaged immutable reference profile bytes."""
    return (_BUILTIN_DIR / "reference-profile-v1.json").read_bytes()


def packaged_mock_bytes() -> bytes:
    """The packaged immutable Mock profile bytes."""
    return (_BUILTIN_DIR / "mock-deterministic-v1.json").read_bytes()


def packaged_openai_bytes() -> bytes:
    """The packaged immutable OpenAI profile bytes."""
    return (_BUILTIN_DIR / "openai-single-turn-v1.json").read_bytes()


def duplicate_reference_resources() -> tuple[bytes, bytes]:
    """Two identical reference resources: the smallest duplicate id."""
    return (packaged_reference_bytes(), packaged_reference_bytes())


def duplicate_llm_resources() -> tuple[bytes, bytes]:
    """Two identical Mock resources: a duplicate LLM id."""
    return (packaged_mock_bytes(), packaged_mock_bytes())


def duplicate_editable_resources() -> tuple[bytes, bytes]:
    """Two identical editable policy payloads: a duplicate policy id."""
    return (_EDITABLE_BUILTIN_BYTES, _EDITABLE_BUILTIN_BYTES)


def _canonical(value: object) -> CanonicalValueV1:
    """Normalize JSON lists to the canonical encoder's tuple arrays."""
    if isinstance(value, list):
        return tuple(_canonical(item) for item in value)
    if isinstance(value, dict):
        return {key: _canonical(item) for key, item in value.items()}
    return value  # type: ignore[return-value]  # JSON scalars are canonical


def foreign_reference_bytes() -> bytes:
    """A self-consistent reference manifest with a foreign profile id."""
    payload = json.loads(packaged_reference_bytes())
    payload["profile_id"] = "other-profile-v1"
    payload.pop("digest")
    canonical_payload = _canonical(payload)
    assert isinstance(canonical_payload, dict)
    payload["digest"] = domain_digest(
        "ReferenceProfileManifestV1", 1, canonical_payload
    )
    return json.dumps(payload, sort_keys=True).encode("utf-8")


def drifted_reference_bytes() -> bytes:
    """A reference manifest whose digest no longer binds its fields."""
    payload = json.loads(packaged_reference_bytes())
    payload["digest"] = "00" * 32
    return json.dumps(payload, sort_keys=True).encode("utf-8")


def drifted_mock_bytes() -> bytes:
    """A Mock profile whose digest no longer binds its fields."""
    payload = json.loads(packaged_mock_bytes())
    payload["digest"] = "00" * 32
    return json.dumps(payload, sort_keys=True).encode("utf-8")


def test_registry_rejects_duplicate_profile_id() -> None:
    with pytest.raises(DuplicateProfileError):
        build_profile_registry(duplicate_reference_resources())


def test_profile_registry_resolution_matrix() -> None:
    """Exact built-ins resolve deterministically; every ambiguity, drift,
    or unknown id rejects before a Run exists (Expected 6.E)."""
    registry = build_profile_registry()
    reference = registry.resolve_reference("python-src-py312-v1")
    assert reference.digest == _MANIFEST_DIGEST
    mock = registry.resolve_llm("mock-deterministic-v1")
    assert mock.digest == _MOCK_DIGEST
    openai = registry.resolve_llm("openai-single-turn-v1")
    assert openai.digest == _OPENAI_DIGEST
    editable = registry.resolve_editable("PYTHON_SRC_ONLY_V1")
    assert editable.digest == _POLICY_DIGEST
    endpoint = registry.resolve_endpoint("OPENAI_PUBLIC_API_V1")
    assert (endpoint.host, endpoint.effective_port, endpoint.base_path) == (
        "api.openai.com",
        443,
        "/v1",
    )
    # Resolution is deterministic across repeated calls.
    assert registry.resolve_reference("python-src-py312-v1") == reference
    assert registry.resolve_llm("mock-deterministic-v1") == mock
    assert registry.resolve_llm("openai-single-turn-v1") == openai
    assert registry.resolve_editable("PYTHON_SRC_ONLY_V1") == editable
    assert registry.resolve_endpoint("OPENAI_PUBLIC_API_V1") == endpoint
    # Unknown ids reject before any Run exists.
    for unknown_id in ("nope", "", "python-src-py312-v2", "mock-v2"):
        with pytest.raises(UnknownProfileError):
            registry.resolve_reference(unknown_id)
        with pytest.raises(UnknownProfileError):
            registry.resolve_llm(unknown_id)
        with pytest.raises(UnknownProfileError):
            registry.resolve_editable(unknown_id)
        with pytest.raises(UnknownEndpointError):
            registry.resolve_endpoint(unknown_id)
    # Duplicate ids reject per kind.
    with pytest.raises(DuplicateProfileError):
        build_profile_registry(duplicate_reference_resources())
    with pytest.raises(DuplicateProfileError):
        build_profile_registry(llm_resources=duplicate_llm_resources())
    with pytest.raises(DuplicateProfileError):
        build_profile_registry(editable_resources=duplicate_editable_resources())
    # Missing declared built-ins reject.
    with pytest.raises(MissingProfileError):
        build_profile_registry(reference_resources=())
    with pytest.raises(MissingProfileError):
        build_profile_registry(llm_resources=(packaged_mock_bytes(),))
    with pytest.raises(MissingProfileError):
        build_profile_registry(editable_resources=())
    # Extra and cross-profile ids beyond the exact built-ins reject at the
    # registry's exact-id closure.
    with pytest.raises(ExtraProfileError):
        build_profile_registry(reference_resources=(foreign_reference_bytes(),))
    with pytest.raises(ExtraProfileError):
        build_profile_registry(reference_resources=(packaged_mock_bytes(),))
    with pytest.raises(ExtraProfileError):
        build_profile_registry(llm_resources=(packaged_reference_bytes(),))
    # Drifted resources reject through the owner integrity check.
    with pytest.raises(ProfileIntegrityError):
        build_profile_registry(reference_resources=(drifted_reference_bytes(),))
    with pytest.raises(ValidationError):
        build_profile_registry(
            llm_resources=(drifted_mock_bytes(), packaged_openai_bytes())
        )
    # Mutable-override and malformed editable resources reject through the
    # owner loader.
    drifted_editable = json.loads(_EDITABLE_BUILTIN_BYTES)
    drifted_editable["editable_directory_roots"] = ["src", "tests"]
    with pytest.raises(ValidationError):
        build_profile_registry(
            editable_resources=(
                json.dumps(drifted_editable, sort_keys=True).encode("utf-8"),
            )
        )
    with pytest.raises(ValueError):
        build_profile_registry(editable_resources=(b"not json",))
    # A valid id with a malformed body rejects through the owner schema.
    truncated = json.loads(packaged_reference_bytes())
    del truncated["docker_image_digest"]
    with pytest.raises(ValidationError):
        build_profile_registry(
            reference_resources=(json.dumps(truncated, sort_keys=True).encode("utf-8"),)
        )
    # Malformed resources reject through the owner loader.
    with pytest.raises(ValueError):
        build_profile_registry(reference_resources=(b"not json",))
    with pytest.raises(ValueError):
        build_profile_registry(llm_resources=(b"not json",))

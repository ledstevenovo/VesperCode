"""T06.4 legacy step 6.E: built-in profile registry resolution.

``ProfileRegistry`` enumerates the exact built-in editable, reference,
LLM, and endpoint resources and exposes their four typed resolution
methods.  Every resource integrity check is delegated to the owning
contract (T06.1 editable, T06.2 reference, T06.3 LLM/endpoint), and
missing, duplicate, extra, drifted, cross-profile, or unknown ids reject
before any Run can exist.  Mutators, external discovery, run-request
validation, and adapter behavior remain out of scope (GREEN-4).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Mapping, Sequence, TypeVar

from vespercode.profiles.editable import (
    EditablePathPolicyV1,
    load_editable_path_policy,
)
from vespercode.profiles.endpoints import (
    OpenAIEndpointRegistry,
    OpenAIEndpointV1,
)
from vespercode.profiles.llm import LLMProfileManifestV1, load_llm_profile
from vespercode.profiles.reference import (
    ReferenceProfileManifestV1,
    load_reference_profile,
)

# The exact built-in id sets (SPEC §1.4.1, §4.1): the only ids the
# registry may enumerate and resolve.
_EXACT_REFERENCE_IDS: frozenset[str] = frozenset({"python-src-py312-v1"})
_EXACT_LLM_IDS: frozenset[str] = frozenset(
    {"mock-deterministic-v1", "openai-single-turn-v1"}
)
_EXACT_EDITABLE_IDS: frozenset[str] = frozenset({"PYTHON_SRC_ONLY_V1"})

# The exact four-field definition of the sole built-in editable policy
# (SPEC §1.4.1); the packaged built-in bytes are the single source of
# truth and the digest binds every exact value.
_EDITABLE_BUILTIN_BYTES = json.dumps(
    {
        "schema_version": 1,
        "policy_id": "PYTHON_SRC_ONLY_V1",
        "editable_directory_roots": ["src"],
        "allowed_operations": ["CREATE", "REPLACE"],
    },
    sort_keys=True,
).encode("utf-8")


class ProfileRegistryError(ValueError):
    """Closed rejection of a built-in registry ambiguity or unknown id."""


class DuplicateProfileError(ProfileRegistryError):
    """Two resources of the same kind resolved to the same id."""


class MissingProfileError(ProfileRegistryError):
    """One declared built-in resource is absent from the enumeration."""


class ExtraProfileError(ProfileRegistryError):
    """One resource id lies beyond the exact built-in id set."""


class UnknownProfileError(ProfileRegistryError):
    """An id outside the built-in registry cannot resolve."""


@dataclass(frozen=True)
class ProfileRegistry:
    """The read-only built-in profile registry (SPEC §4.1 behavior 2).

    Resolution is exact-id only and every record is immutable; the
    endpoint kind delegates to the trusted endpoint map owner, so no
    network, credential, or adapter behavior exists here.
    """

    _reference: Mapping[str, ReferenceProfileManifestV1]
    _llm: Mapping[str, LLMProfileManifestV1]
    _editable: Mapping[str, EditablePathPolicyV1]

    def resolve_reference(self, profile_id: str) -> ReferenceProfileManifestV1:
        """Resolve exactly one built-in reference profile by id."""
        try:
            return self._reference[profile_id]
        except KeyError:
            raise UnknownProfileError(
                f"unknown reference profile id {profile_id!r}: only the exact "
                f"built-in ids resolve"
            ) from None

    def resolve_llm(self, profile_id: str) -> LLMProfileManifestV1:
        """Resolve exactly one built-in LLM profile by id."""
        try:
            return self._llm[profile_id]
        except KeyError:
            raise UnknownProfileError(
                f"unknown LLM profile id {profile_id!r}: only the exact "
                f"built-in ids resolve"
            ) from None

    def resolve_editable(self, policy_id: str) -> EditablePathPolicyV1:
        """Resolve exactly one built-in editable path policy by id."""
        try:
            return self._editable[policy_id]
        except KeyError:
            raise UnknownProfileError(
                f"unknown editable policy id {policy_id!r}: only the exact "
                f"built-in ids resolve"
            ) from None

    def resolve_endpoint(self, endpoint_id: str) -> OpenAIEndpointV1:
        """Resolve exactly one built-in trusted endpoint by id."""
        return OpenAIEndpointRegistry.resolve(endpoint_id)


T = TypeVar("T")


def _raw_id(payload: bytes, id_field: str) -> str | None:
    """Extract one id from a raw payload without judging its integrity.

    Only the id is read here so the registry can close the exact built-in
    id set before delegating the full integrity check to the owner loader;
    any payload that does not parse cleanly returns ``None`` and the owner
    loader produces the rejection.
    """
    try:
        obj = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None
    if not isinstance(obj, dict):
        return None
    value = obj.get(id_field)
    return value if isinstance(value, str) else None


def _build_kind_map(
    payloads: Sequence[bytes],
    loader: Callable[[bytes], T],
    id_field: str,
    id_of: Callable[[T], str],
    exact_ids: frozenset[str],
    kind: str,
) -> dict[str, T]:
    """Load one kind's resources through its owner and close the id set.

    The registry first closes the exact built-in id set (a raw id beyond
    the set — extra or cross-profile data — rejects), then the owner
    loader performs the integrity check (drift, cross-profile fields, and
    malformed data reject there), and finally duplicate ids and missing
    declared built-ins reject before any Run can exist.
    """
    records: dict[str, T] = {}
    for payload in payloads:
        raw_id = _raw_id(payload, id_field)
        if raw_id is not None and raw_id not in exact_ids:
            raise ExtraProfileError(
                f"{kind} profile id {raw_id!r} lies beyond the exact built-in id set"
            )
        record = loader(payload)
        record_id = id_of(record)
        if record_id in records:
            raise DuplicateProfileError(
                f"duplicate {kind} profile id {record_id!r}: each built-in id "
                f"must resolve to exactly one resource"
            )
        records[record_id] = record
    missing = exact_ids - records.keys()
    if missing:
        raise MissingProfileError(
            f"missing {kind} built-in id(s) {sorted(missing)!r}: every declared "
            f"built-in resource must be present"
        )
    return records


def _packaged_bytes(name: str) -> bytes:
    """Read one packaged built-in resource byte-for-byte."""
    return (Path(__file__).resolve().parent / "builtin" / name).read_bytes()


def build_profile_registry(
    reference_resources: Sequence[bytes] | None = None,
    llm_resources: Sequence[bytes] | None = None,
    editable_resources: Sequence[bytes] | None = None,
) -> ProfileRegistry:
    """Build the read-only registry over the exact built-in resources.

    With no arguments the packaged built-in bytes are loaded; injected
    sequences replace the default per kind, so tests can prove every
    missing, duplicate, extra, drifted, cross-profile, or malformed
    resource rejects before a Run exists.
    """
    reference = _build_kind_map(
        (
            reference_resources
            if reference_resources is not None
            else (_packaged_bytes("reference-profile-v1.json"),)
        ),
        load_reference_profile,
        "profile_id",
        lambda manifest: manifest.profile_id,
        _EXACT_REFERENCE_IDS,
        "reference",
    )
    llm = _build_kind_map(
        (
            llm_resources
            if llm_resources is not None
            else (
                _packaged_bytes("mock-deterministic-v1.json"),
                _packaged_bytes("openai-single-turn-v1.json"),
            )
        ),
        load_llm_profile,
        "profile_id",
        lambda profile: profile.profile_id,
        _EXACT_LLM_IDS,
        "LLM",
    )
    editable = _build_kind_map(
        (
            editable_resources
            if editable_resources is not None
            else (_EDITABLE_BUILTIN_BYTES,)
        ),
        load_editable_path_policy,
        "policy_id",
        lambda policy: policy.policy_id,
        _EXACT_EDITABLE_IDS,
        "editable",
    )
    return ProfileRegistry(
        _reference=reference,
        _llm=llm,
        _editable=editable,
    )

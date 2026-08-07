"""T06.1 legacy step 6.A: the sole immutable editable-path policy.

``EditablePathPolicyV1`` is the one built-in, read-only policy record of
SPEC §1.4.1: exactly ``schema_version=1``, ``policy_id="PYTHON_SRC_ONLY_V1"``,
``editable_directory_roots=(CanonicalRelativePathV1("src"),)``,
``allowed_operations=("CREATE", "REPLACE")``, and ``digest`` computed over
every preceding exact field.  Any missing, renamed, extra, or drifted value
rejects before a record exists, so user requests, plain configuration,
model output, and repository text can never provide, override, or widen
roots, operations, policy id, or digest.

Matching happens only at canonical segment boundaries: a path qualifies
exactly when it starts with a root followed by ``"/"`` (never a bare string
prefix, never the directory root itself).  Therefore ``src/a.py`` and
``src/pkg/a.py`` match while ``src``, ``src-old/a.py``, ``src2/a.py``, and
path aliases do not.  Profile resolution, endpoints, requests, and mutable
policy overrides remain out of scope (GREEN-4).
"""

from __future__ import annotations

import json
from typing import Literal

from pydantic import BaseModel, ConfigDict, StrictStr, field_validator, model_validator

from vespercode.canonical.digest import domain_digest
from vespercode.canonical.json_v1 import CanonicalValueV1
from vespercode.canonical.path_v1 import CanonicalRelativePathV1
from vespercode.contracts.evidence import _DIGEST_RE

EditableOperationV1 = Literal["CREATE", "REPLACE"]
"""SPEC §1.4.1: the closed set of Candidate operations on editable paths."""

_BUILTIN_ROOT = CanonicalRelativePathV1("src")
_BUILTIN_OPERATIONS: tuple[EditableOperationV1, ...] = ("CREATE", "REPLACE")


def _reject_coerced_schema_version(value: object) -> object:
    """Reject bool/float/string spelling of the integer schema version.

    Pydantic lax mode would otherwise coerce ``true`` or ``1.0`` into the
    ``Literal[1]`` field; the closed T05.1 convention pins Strict on scalar
    fields, so every type-confused spelling rejects deterministically.
    """
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError("schema_version must be the decimal integer 1")
    return value


class _EditablePathPolicyFieldsV1(BaseModel):
    """The exact four non-digest fields, validated before digest acceptance.

    ``load_editable_path_policy`` accepts only these four fields; any
    missing, renamed, or extra field rejects here before the digest is
    computed (GREEN-1).
    """

    model_config = ConfigDict(extra="forbid")
    schema_version: Literal[1]
    policy_id: Literal["PYTHON_SRC_ONLY_V1"]
    editable_directory_roots: tuple[CanonicalRelativePathV1, ...]
    allowed_operations: tuple[EditableOperationV1, ...]

    @field_validator("schema_version", mode="before")
    @classmethod
    def _schema_version_is_exact_int(cls, value: object) -> object:
        return _reject_coerced_schema_version(value)

    @field_validator("editable_directory_roots", mode="before")
    @classmethod
    def _coerce_root_strings(cls, value: object) -> object:
        """Accept the published JSON ``["src"]`` string form for roots.

        Each string is validated through ``CanonicalRelativePathV1``, so a
        noncanonical root rejects before any matching or digest exists.
        """
        if isinstance(value, list):
            return [
                CanonicalRelativePathV1(item) if isinstance(item, str) else item
                for item in value
            ]
        return value


class EditablePathPolicyV1(BaseModel):
    """The sole immutable built-in editable path policy (SPEC §1.4.1).

    The record is closed to the exact built-in values: a different root
    set, operation pair, operation order, policy id, schema version, or
    digest rejects deterministically at construction, so a mutable
    override can never exist (GREEN-2).
    """

    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal[1]
    policy_id: Literal["PYTHON_SRC_ONLY_V1"]
    editable_directory_roots: tuple[CanonicalRelativePathV1, ...]
    allowed_operations: tuple[EditableOperationV1, ...]
    digest: StrictStr

    @field_validator("schema_version", mode="before")
    @classmethod
    def _schema_version_is_exact_int(cls, value: object) -> object:
        return _reject_coerced_schema_version(value)

    @field_validator("digest")
    @classmethod
    def _require_sha256_hex(cls, value: str) -> str:
        if _DIGEST_RE.fullmatch(value) is None:
            raise ValueError(
                "digest must be exactly 64 lowercase hexadecimal characters"
            )
        return value

    @model_validator(mode="after")
    def _require_sole_builtin_record(self) -> EditablePathPolicyV1:
        if self.editable_directory_roots != (_BUILTIN_ROOT,):
            raise ValueError(
                "editable_directory_roots must be exactly the built-in root "
                "CanonicalRelativePathV1('src')"
            )
        if self.allowed_operations != _BUILTIN_OPERATIONS:
            raise ValueError(
                "allowed_operations must be exactly the sorted built-in pair "
                "('CREATE', 'REPLACE')"
            )
        if self.digest != digest_editable_path_policy(self):
            raise ValueError(
                "digest must equal the §0.1 identity of every preceding exact field"
            )
        return self

    def matches(
        self, path: CanonicalRelativePathV1, operation: EditableOperationV1
    ) -> bool:
        """True exactly when *path* is a canonical descendant of an editable
        root and *operation* is allowed.

        The predicate is the canonical segment boundary ``root + "/"``
        prefix: the directory root itself, bare-string prefix aliases, and
        unsupported operations never match (SPEC §1.4.1).
        """
        if operation not in self.allowed_operations:
            return False
        return any(
            path.value.startswith(root.value + "/")
            for root in self.editable_directory_roots
        )


def _digest_body(
    schema_version: int,
    policy_id: str,
    editable_directory_roots: tuple[CanonicalRelativePathV1, ...],
    allowed_operations: tuple[EditableOperationV1, ...],
) -> dict[str, CanonicalValueV1]:
    """The canonical digest value body: every exact field except the digest."""
    return {
        "schema_version": schema_version,
        "policy_id": policy_id,
        "editable_directory_roots": tuple(
            root.value for root in editable_directory_roots
        ),
        "allowed_operations": allowed_operations,
    }


def digest_editable_path_policy(policy: EditablePathPolicyV1) -> str:
    """The SPEC §0.1 identity of every exact field except the digest.

    The binding object type is ``EditablePathPolicyV1`` and the value body
    is the four preceding fields, so the digest can never interchange with
    another object type or schema version.
    """
    return domain_digest(
        "EditablePathPolicyV1",
        policy.schema_version,
        _digest_body(
            policy.schema_version,
            policy.policy_id,
            policy.editable_directory_roots,
            policy.allowed_operations,
        ),
    )


def load_editable_path_policy(raw: bytes) -> EditablePathPolicyV1:
    """Load the sole built-in policy from its exact four-field JSON bytes.

    The input must be UTF-8 JSON of exactly ``schema_version``,
    ``policy_id``, ``editable_directory_roots``, and
    ``allowed_operations``; every missing, renamed, extra, malformed, or
    drifted field rejects before the digest is accepted.  The digest is
    computed over the validated fields, never read from the input.
    """
    try:
        obj = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("editable path policy must be valid UTF-8 JSON") from exc
    fields = _EditablePathPolicyFieldsV1.model_validate(obj)
    return EditablePathPolicyV1.model_validate(
        {
            "schema_version": fields.schema_version,
            "policy_id": fields.policy_id,
            "editable_directory_roots": list(fields.editable_directory_roots),
            "allowed_operations": list(fields.allowed_operations),
            "digest": domain_digest(
                "EditablePathPolicyV1",
                fields.schema_version,
                _digest_body(
                    fields.schema_version,
                    fields.policy_id,
                    fields.editable_directory_roots,
                    fields.allowed_operations,
                ),
            ),
        }
    )

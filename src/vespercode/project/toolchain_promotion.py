"""T04.1 legacy step 4.F: formal toolchain promotion.

Consumes the Task 4.A closure and the Task 1 gate identity to define the
sole formal offline toolchain: the six dedicated real-environment markers,
the promoted static rules, and the canonical commands.  This module never
creates or repairs environments, resolves or installs packages, changes
dependency tables, or absorbs project metadata and application behavior.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

from src.vespercode.project.dependency_closure import (
    load_gate_toolchain_snapshot,
)

PROMOTION_RECORD_TYPE = "FORMAL_TOOLCHAIN_PROMOTION_V1"
PROMOTION_SCHEMA_VERSION = 1

MARKERS_V1 = (
    "windows_integration",
    "docker_integration",
    "reference_e2e",
    "package_smoke",
    "oci_smoke",
    "deployment_smoke",
)

DEFAULT_OFFLINE_EXCLUSION = (
    "not (windows_integration or docker_integration or reference_e2e "
    "or package_smoke or oci_smoke or deployment_smoke)"
)

_PROMOTION_FIELDS = frozenset(
    {
        "schema_version",
        "record_type",
        "python_version",
        "gate_lock_sha256",
        "pytest_version",
        "ruff_version",
        "mypy_version",
        "marker_digest",
        "static_rule_digest",
        "evidence_digest",
    }
)


@dataclass(frozen=True)
class FormalToolchainPromotionV1:
    """The immutable formal toolchain promotion record.

    ``python_version`` and the three tool versions must exactly match the
    Task 1 gate identity; ``gate_lock_sha256`` binds the Task 1 gate lock;
    ``marker_digest`` and ``static_rule_digest`` bind the promoted marker
    set and static rules.
    """

    python_version: str
    gate_lock_sha256: str
    pytest_version: str
    ruff_version: str
    mypy_version: str
    marker_digest: str
    static_rule_digest: str


def canonical_compact_json(value: object) -> str:
    """Serialize to the compact canonical convention used by Task 1 evidence."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def marker_declaration() -> dict[str, object]:
    """The closed marker registration promoted into the formal toolchain."""
    return {
        "markers": list(MARKERS_V1),
        "default_exclusion": DEFAULT_OFFLINE_EXCLUSION,
    }


def marker_digest() -> str:
    """SHA-256 of the canonical marker registration."""
    return hashlib.sha256(
        canonical_compact_json(marker_declaration()).encode("utf-8")
    ).hexdigest()


def static_rule_declaration() -> dict[str, object]:
    """The closed static rules promoted from the Task 1 gate configuration."""
    return {
        "ruff": {
            "target_version": "py312",
            "line_length": 88,
            "extend_exclude": [
                ".venv-gate",
                ".venv-formal",
                "*.md",
                "reference/fixture",
            ],
            "format": {
                "line_ending": "lf",
                "quote_style": "double",
                "indent_style": "space",
            },
            "lint_select": ["E4", "E7", "E9", "F"],
        },
        "mypy": {
            "python_version": "3.12",
            "strict": True,
            "warn_unused_configs": True,
        },
    }


def static_rule_digest() -> str:
    """SHA-256 of the canonical static rule promotion."""
    return hashlib.sha256(
        canonical_compact_json(static_rule_declaration()).encode("utf-8")
    ).hexdigest()


def canonical_offline_commands() -> tuple[tuple[str, ...], ...]:
    """The fixed canonical offline commands, executed through the verified
    formal interpreter."""
    return (
        ("python", "-m", "pytest", "-q"),
        ("python", "-m", "ruff", "format", "--check", "."),
        ("python", "-m", "ruff", "check", "."),
        ("python", "-m", "mypy", "src", "tests"),
    )


def dedicated_environment_command(marker: str, test_root: str) -> tuple[str, ...]:
    """One dedicated real-environment command: clear default addopts, select
    exactly one closed marker, and name its test root."""
    if marker not in MARKERS_V1:
        raise ValueError(f"unknown dedicated environment marker: {marker!r}")
    return ("python", "-m", "pytest", "-q", "-o", "addopts=", "-m", marker, test_root)


def _require_exact_keys(
    obj: dict[str, object], expected: frozenset[str], path: str
) -> None:
    actual = frozenset(obj)
    missing = sorted(expected - actual)
    if missing:
        raise ValueError(f"{path} missing JSON fields: {', '.join(missing)}")
    unknown = sorted(actual - expected)
    if unknown:
        raise ValueError(f"{path} contains unknown JSON fields: {', '.join(unknown)}")


def _require_str(obj: dict[str, object], key: str) -> str:
    value = obj[key]
    if not isinstance(value, str):
        raise ValueError(f"{key} must be a JSON string")
    return value


def _require_int(obj: dict[str, object], key: str) -> int:
    value = obj[key]
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError(f"{key} must be a JSON integer")
    return value


def _require_sha256(obj: dict[str, object], key: str) -> str:
    value = _require_str(obj, key)
    if len(value) != 64 or any(char not in "0123456789abcdef" for char in value):
        raise ValueError(f"{key} must be a 64-character lowercase SHA-256")
    return value


def _compute_record_digest(record: dict[str, object]) -> str:
    body = {key: value for key, value in record.items() if key != "evidence_digest"}
    return hashlib.sha256(canonical_compact_json(body).encode("utf-8")).hexdigest()


def load_formal_toolchain_promotion(root: Path) -> FormalToolchainPromotionV1:
    """Load and validate the unique formal toolchain promotion record.

    Rejects missing or malformed records, unexpected or missing fields,
    wrong schema/type literals, marker/static-rule digest drift, record
    digest drift, and any gate-identity mismatch against the Task 1
    gate-toolchain evidence.
    """
    path = root / "config/formal-toolchain-promotion-v1.json"
    if not path.is_file():
        raise ValueError(f"formal toolchain promotion record not found: {path}")
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(
            "formal toolchain promotion record is not readable UTF-8 JSON"
        ) from exc
    if not isinstance(raw, dict):
        raise ValueError("formal toolchain promotion record must be a JSON object")
    _require_exact_keys(raw, _PROMOTION_FIELDS, "formal_toolchain_promotion")
    if _require_str(raw, "record_type") != PROMOTION_RECORD_TYPE:
        raise ValueError("formal toolchain promotion record has an unexpected type")
    if _require_int(raw, "schema_version") != PROMOTION_SCHEMA_VERSION:
        raise ValueError(
            "formal toolchain promotion record has an unexpected schema version"
        )
    stored_digest = _require_sha256(raw, "evidence_digest")
    if _compute_record_digest(raw) != stored_digest:
        raise ValueError("formal toolchain promotion record evidence digest mismatch")
    stored_marker_digest = _require_sha256(raw, "marker_digest")
    stored_static_digest = _require_sha256(raw, "static_rule_digest")
    if stored_marker_digest != marker_digest():
        raise ValueError("formal toolchain promotion marker digest mismatch")
    if stored_static_digest != static_rule_digest():
        raise ValueError("formal toolchain promotion static rule digest mismatch")

    gate = load_gate_toolchain_snapshot(root)
    record = FormalToolchainPromotionV1(
        python_version=_require_str(raw, "python_version"),
        gate_lock_sha256=_require_sha256(raw, "gate_lock_sha256"),
        pytest_version=_require_str(raw, "pytest_version"),
        ruff_version=_require_str(raw, "ruff_version"),
        mypy_version=_require_str(raw, "mypy_version"),
        marker_digest=stored_marker_digest,
        static_rule_digest=stored_static_digest,
    )
    if record.python_version != gate.python_version:
        raise ValueError(
            "formal toolchain python version does not match the gate identity"
        )
    if record.gate_lock_sha256 != gate.gate_lock_sha256:
        raise ValueError(
            "formal toolchain gate lock digest does not match the gate identity"
        )
    if record.pytest_version != gate.pytest_version:
        raise ValueError(
            "formal toolchain pytest version does not match the gate identity"
        )
    if record.ruff_version != gate.ruff_version:
        raise ValueError(
            "formal toolchain ruff version does not match the gate identity"
        )
    if record.mypy_version != gate.mypy_version:
        raise ValueError(
            "formal toolchain mypy version does not match the gate identity"
        )
    return record

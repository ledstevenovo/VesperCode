"""T02.1 legacy step 2.A: frozen reference build-input contract.

Freezes the fixture-tree, dual-lock, tool-version, base/registry-image, and
build-recipe identities into one immutable ``ReferenceBuildInputV1`` produced
by ``freeze_reference_build_input``.  This module performs no image builds,
registry starts, validation checks, or final reference-manifest writes.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

REFERENCE_LOCK_RELATIVE = Path("requirements") / "reference.lock"
FIXTURE_LOCK_RELATIVE = Path("reference") / "fixture" / "requirements.lock"
FIXTURE_TREE_RELATIVE = Path("reference") / "fixture"
GATE_TOOLCHAIN_EVIDENCE_RELATIVE = Path("gates") / "evidence" / "gate-toolchain-v1.json"

# Recipe-frozen image identities (official Docker Hub manifest digests,
# verified against the registry API on 2026-08-04; the local daemon stores the
# same bytes, pulled through a reachable proxy mirror).
BASE_IMAGE_DIGEST = "57cd7c3a7a273101a6485ba99423ee568157882804b1124b4dd04266317710de"
REGISTRY_IMAGE_DIGEST = (
    "a3d8aaa63ed8681a604f1dea0aa03f100d5895b6a58ace528858a7b332415373"
)
BUILD_RECIPE_VERSION = "1"

_SHA256 = hashlib.sha256
_HEX_CHARS = frozenset("0123456789abcdef")


@dataclass(frozen=True)
class ReferenceBuildInputV1:
    """Immutable freeze of every identity consumed by the reference build."""

    base_image_digest: str
    registry_image_digest: str
    requirements_digest: str
    fixture_tree_digest: str
    tool_versions_digest: str
    build_recipe_version: str


def _canonical_json_bytes(obj: object) -> bytes:
    """Serialize *obj* to deterministic UTF-8 JSON with stable key order."""
    return json.dumps(
        obj,
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
        separators=(",", ": "),
    ).encode("utf-8")


def _sha256_hex(data: bytes) -> str:
    return _SHA256(data).hexdigest()


def _read_required(path: Path) -> bytes:
    if not path.is_file():
        raise ValueError(f"missing frozen reference input: {path}")
    return path.read_bytes()


def _validate_digest(value: str, field: str) -> None:
    if len(value) != 64 or not all(c in _HEX_CHARS for c in value):
        raise ValueError(f"{field} must be a 64 lowercase hex digest")


def freeze_reference_build_input(root: Path) -> ReferenceBuildInputV1:
    """Freeze every declared build-input identity for the tree at *root*.

    Fails closed on any drift between the two reference lock copies, missing
    inputs, or malformed frozen recipe identities.  All digests are plain 64
    lowercase hex characters, deterministically recomputed from current bytes.
    """
    root = Path(root)
    lock_bytes = _read_required(root / REFERENCE_LOCK_RELATIVE)
    fixture_lock_bytes = _read_required(root / FIXTURE_LOCK_RELATIVE)
    if lock_bytes != fixture_lock_bytes:
        raise ValueError(
            "requirements/reference.lock and reference/fixture/requirements.lock "
            "must be byte-identical"
        )
    _validate_digest(BASE_IMAGE_DIGEST, "base_image_digest")
    _validate_digest(REGISTRY_IMAGE_DIGEST, "registry_image_digest")
    return ReferenceBuildInputV1(
        base_image_digest=BASE_IMAGE_DIGEST,
        registry_image_digest=REGISTRY_IMAGE_DIGEST,
        requirements_digest=_sha256_hex(lock_bytes),
        fixture_tree_digest=_freeze_fixture_tree(root / FIXTURE_TREE_RELATIVE),
        tool_versions_digest=_freeze_tool_versions(
            root / GATE_TOOLCHAIN_EVIDENCE_RELATIVE
        ),
        build_recipe_version=BUILD_RECIPE_VERSION,
    )


def _freeze_fixture_tree(tree_root: Path) -> str:
    """Digest one deterministic mapping of every fixture file to its bytes."""
    if not tree_root.is_dir():
        raise ValueError(f"fixture tree missing: {tree_root}")
    entries: dict[str, str] = {}
    for path in sorted(tree_root.rglob("*")):
        if path.is_file():
            relative = path.relative_to(tree_root).as_posix()
            entries[relative] = _sha256_hex(path.read_bytes())
    if not entries:
        raise ValueError("fixture tree must not be empty")
    return _sha256_hex(_canonical_json_bytes(entries))


def _freeze_tool_versions(evidence_path: Path) -> str:
    """Digest the exact python/pytest/ruff/mypy versions from gate evidence."""
    raw = json.loads(_read_required(evidence_path).decode("utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("gate toolchain evidence must be a JSON object")
    try:
        versions = {
            "python_version": raw["python_version"],
            "pytest_version": raw["pytest_version"],
            "ruff_version": raw["ruff_version"],
            "mypy_version": raw["mypy_version"],
        }
    except KeyError as exc:
        raise ValueError(f"gate toolchain evidence missing {exc.args[0]}") from exc
    if not all(isinstance(value, str) for value in versions.values()):
        raise ValueError("gate toolchain versions must be strings")
    return _sha256_hex(_canonical_json_bytes(versions))

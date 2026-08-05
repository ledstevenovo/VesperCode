"""T04.1 legacy step 4.A: v1 project dependency closure ownership.

Owns the typed declaration surface, the unique closure record schema, the
hash-locked lock agreement, and the Task 1 gate-identity comparison for the
sole complete v1 runtime/build/development dependency closure.  Build
backend, formal toolchain configuration, canonical primitives, scanners,
application behavior, and every Task 1–3 or profile lock remain out of
scope (GREEN-5).
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path

FIXED_PYPI_SIMPLE_INDEX_URL = "https://pypi.org/simple"

RECORD_TYPE = "DEPENDENCY_CLOSURE_V1"
RECORD_SCHEMA_VERSION = 1
TOOLCHAIN_EVIDENCE_TYPE = "GATE_TOOLCHAIN_EVIDENCE_V1"

_DIRECT_FAMILIES = frozenset({"runtime", "build", "development"})

_RECORD_FIELDS = frozenset(
    {
        "schema_version",
        "record_type",
        "python_version",
        "python_requirement",
        "pytest_version",
        "ruff_version",
        "mypy_version",
        "gate_lock_sha256",
        "dev_lock_sha256",
        "direct_families",
        "distributions",
        "evidence_digest",
    }
)
_DISTRIBUTION_FIELDS = frozenset({"name", "version", "marker", "hashes"})
_TOOLCHAIN_FIELDS = frozenset(
    {
        "schema_version",
        "evidence_type",
        "python_version",
        "pytest_version",
        "ruff_version",
        "mypy_version",
        "gate_input_sha256",
        "gate_lock_sha256",
        "gate_scan_sha256",
        "gate_scan_core_sha256",
        "runner_sha256",
        "pytest_config_sha256",
        "ruff_config_sha256",
        "mypy_config_sha256",
        "evidence_digest",
    }
)

_SHA256_HEX = re.compile(r"[0-9a-f]{64}")
_LOCK_LINE = re.compile(r"^([A-Za-z0-9][A-Za-z0-9._-]*?)==([^=\s;]+)(.*)$")
_HASH_TOKEN = re.compile(r"--hash=sha256:[0-9a-f]{64}")
_MARKER_CHARS = re.compile(r"[A-Za-z0-9 ._\-()<>=~!\"']+")
_INDEX_PREFIX = "--index-url "


@dataclass(frozen=True)
class DeclaredDependencySetV1:
    """The reviewed v1 direct dependency declaration.

    ``python_requirement`` is the exact public Python range and
    ``source_index_url`` the sole allowed distribution source; the family
    tuples hold the direct runtime, build, and development declarations.
    """

    python_requirement: str
    source_index_url: str
    runtime: tuple[str, ...]
    build: tuple[str, ...]
    development: tuple[str, ...]


@dataclass(frozen=True)
class LockedDistributionV1:
    """One frozen distribution: exact version, marker (empty when none), and
    the complete sorted SHA-256 hash set from the lock."""

    name: str
    version: str
    marker: str
    hashes: tuple[str, ...]


@dataclass(frozen=True)
class GateToolchainSnapshotV1:
    """The Task 1 gate-toolchain identity consumed by closure agreement."""

    python_version: str
    pytest_version: str
    ruff_version: str
    mypy_version: str
    gate_lock_sha256: str


@dataclass(frozen=True)
class DependencyClosureV1:
    """The unique immutable v1 dependency closure record."""

    schema_version: int
    record_type: str
    python_version: str
    python_requirement: str
    pytest_version: str
    ruff_version: str
    mypy_version: str
    gate_lock_sha256: str
    dev_lock_sha256: str
    direct_families: tuple[tuple[str, str], ...]
    distributions: tuple[LockedDistributionV1, ...]
    evidence_digest: str


@dataclass(frozen=True)
class DependencyClosureReportV1:
    """The closed agreement verdict over the declared stack, the unique
    record, the lock, and the Task 1 gate identity.

    ``missing_transitive_or_hash`` covers the full record/lock distribution
    set agreement in both directions (lock entries missing from the record,
    record entries absent from the lock, or version/hash disagreement);
    ``gate_tool_version_mismatches`` also covers the frozen gate lock digest
    agreement; ``python_version_mismatches`` also covers the public Python
    range agreement with the reviewed declaration.
    """

    missing_direct: tuple[str, ...]
    extra_or_misclassified_direct: tuple[str, ...]
    missing_transitive_or_hash: tuple[str, ...]
    marker_or_source_mismatches: tuple[str, ...]
    gate_tool_version_mismatches: tuple[str, ...]
    python_version_mismatches: tuple[str, ...]


def canonical_compact_json(value: object) -> str:
    """Serialize to the compact canonical convention used by Task 1 evidence."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256_bytes(data: bytes) -> str:
    """Lowercase SHA-256 hex of the raw bytes."""
    return hashlib.sha256(data).hexdigest()


def _normalize_dist_name(name: str) -> str:
    """PEP 503 normalized distribution name."""
    return re.sub(r"[-_.]+", "-", name).lower()


def _is_plausible_marker(text: str) -> bool:
    if not text or text.startswith((";", "==", "--")) or ";" in text:
        return False
    if _MARKER_CHARS.fullmatch(text) is None:
        return False
    depth = 0
    for char in text:
        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if depth < 0:
                return False
    return depth == 0


def _parse_lock_line(line: str) -> LockedDistributionV1:
    match = _LOCK_LINE.match(line)
    if match is None:
        raise ValueError(f"malformed lock line: {line!r}")
    name, version, rest = match.groups()
    rest = rest.strip()
    if not rest:
        raise ValueError(f"missing hashes on {name}=={version}")
    if "@" in line or "/" in line or "\\" in line or ":" in version or "*" in version:
        raise ValueError(f"unsupported source or unpinned version: {line!r}")
    tokens = rest.split()
    marker = ""
    index = 0
    if not tokens[0].startswith("--hash="):
        if tokens[0] != ";":
            raise ValueError(f"unexpected token {tokens[0]!r} in lock line")
        marker_parts: list[str] = []
        index = 1
        while index < len(tokens) and not tokens[index].startswith("--hash="):
            marker_parts.append(tokens[index])
            index += 1
        marker = " ".join(marker_parts).strip()
        if not marker or not _is_plausible_marker(marker):
            raise ValueError(f"malformed marker in lock line: {line!r}")
    hashes: list[str] = []
    for token in tokens[index:]:
        if _HASH_TOKEN.fullmatch(token) is None:
            raise ValueError(f"unsupported hash or unexpected token {token!r}")
        hashes.append(token.removeprefix("--hash=sha256:"))
    if not hashes:
        raise ValueError(f"no hashes on {name}=={version}")
    return LockedDistributionV1(
        name=name, version=version, marker=marker, hashes=tuple(sorted(set(hashes)))
    )


def parse_lock_entries(
    lock_bytes: bytes,
) -> tuple[tuple[LockedDistributionV1, ...], str]:
    """Parse the exact T01.1 lock format and return (entries, index_url).

    The first line must start with ``--index-url ``; every remaining line is
    one ``name==version [; marker] --hash=sha256:...`` entry, names are
    sorted by normalized name and unique, and every hash is a lowercase
    SHA-256.  The index URL is captured (not enforced) so source mismatches
    can be reported as agreement findings; malformed entries fail closed.
    """
    if not lock_bytes.endswith(b"\n"):
        raise ValueError("lock file does not end with a newline")
    try:
        text = lock_bytes.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError("lock file is not valid UTF-8") from exc
    lines = text.split("\n")
    if not lines or not lines[0].startswith(_INDEX_PREFIX):
        raise ValueError("lock file must start with the fixed index line")
    index_url = lines[0][len(_INDEX_PREFIX) :].strip()
    entries: list[LockedDistributionV1] = []
    seen: set[str] = set()
    previous: str | None = None
    for raw_line in lines[1:]:
        line = raw_line.strip()
        if not line:
            continue
        entry = _parse_lock_line(line)
        normalized = _normalize_dist_name(entry.name)
        if normalized in seen:
            raise ValueError(f"duplicate distribution {normalized} in lock")
        if previous is not None and normalized < previous:
            raise ValueError("lock entries are not sorted by normalized name")
        seen.add(normalized)
        previous = normalized
        entries.append(entry)
    if not entries:
        raise ValueError("lock file contains no distribution entries")
    return tuple(entries), index_url


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
    if _SHA256_HEX.fullmatch(value) is None:
        raise ValueError(f"{key} must be a 64-character lowercase SHA-256")
    return value


def _compute_record_digest(record: dict[str, object]) -> str:
    body = {key: value for key, value in record.items() if key != "evidence_digest"}
    return hashlib.sha256(canonical_compact_json(body).encode("utf-8")).hexdigest()


def load_gate_toolchain_snapshot(root: Path) -> GateToolchainSnapshotV1:
    """Read and strictly validate the Task 1 gate-toolchain evidence.

    Rejects missing files, malformed JSON, unexpected or missing fields,
    wrong schema/type literals, and evidence-digest drift.  Uses the same
    compact canonical digest convention as the Task 1 evidence.
    """
    path = root / "gates/evidence/gate-toolchain-v1.json"
    if not path.is_file():
        raise ValueError(f"gate toolchain evidence file not found: {path}")
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("gate toolchain evidence is not readable UTF-8 JSON") from exc
    if not isinstance(raw, dict):
        raise ValueError("gate toolchain evidence must be a JSON object")
    _require_exact_keys(raw, _TOOLCHAIN_FIELDS, "gate_toolchain")
    if _require_str(raw, "evidence_type") != TOOLCHAIN_EVIDENCE_TYPE:
        raise ValueError("gate toolchain evidence has an unexpected type")
    if _require_int(raw, "schema_version") != RECORD_SCHEMA_VERSION:
        raise ValueError("gate toolchain evidence has an unexpected schema version")
    stored = _require_sha256(raw, "evidence_digest")
    body = {key: value for key, value in raw.items() if key != "evidence_digest"}
    computed = hashlib.sha256(canonical_compact_json(body).encode("utf-8")).hexdigest()
    if computed != stored:
        raise ValueError("gate toolchain evidence digest mismatch")
    return GateToolchainSnapshotV1(
        python_version=_require_str(raw, "python_version"),
        pytest_version=_require_str(raw, "pytest_version"),
        ruff_version=_require_str(raw, "ruff_version"),
        mypy_version=_require_str(raw, "mypy_version"),
        gate_lock_sha256=_require_sha256(raw, "gate_lock_sha256"),
    )


def _parse_distribution(raw: object, index: int) -> LockedDistributionV1:
    if not isinstance(raw, dict):
        raise ValueError(f"distributions[{index}] must be a JSON object")
    path = f"distributions[{index}]"
    _require_exact_keys(raw, _DISTRIBUTION_FIELDS, path)
    hashes_raw = raw.get("hashes")
    if not isinstance(hashes_raw, list) or not hashes_raw:
        raise ValueError(f"{path}.hashes must be a non-empty JSON array")
    hashes: list[str] = []
    for hash_index, hash_value in enumerate(hashes_raw):
        if not isinstance(hash_value, str):
            raise ValueError(f"{path}.hashes[{hash_index}] must be a JSON string")
        if _SHA256_HEX.fullmatch(hash_value) is None:
            raise ValueError(f"{path}.hashes[{hash_index}] must be a lowercase SHA-256")
        hashes.append(hash_value)
    return LockedDistributionV1(
        name=_require_str(raw, "name"),
        version=_require_str(raw, "version"),
        marker=_require_str(raw, "marker"),
        hashes=tuple(sorted(set(hashes))),
    )


def _parse_direct_families(raw: object) -> tuple[tuple[str, str], ...]:
    if not isinstance(raw, dict):
        raise ValueError("direct_families must be a JSON object")
    families: list[tuple[str, str]] = []
    for name in sorted(raw):
        family = raw[name]
        if not isinstance(family, str) or family not in _DIRECT_FAMILIES:
            raise ValueError(
                f"direct_families.{name} must be one of runtime/build/development"
            )
        families.append((name, family))
    return tuple(families)


def load_dependency_closure(root: Path) -> DependencyClosureV1:
    """Load and validate the unique v1 dependency closure record.

    Rejects missing or malformed records, unexpected or missing fields,
    wrong schema/type literals, evidence-digest drift, and lock-byte drift
    (the record's ``dev_lock_sha256`` must match the current raw lock bytes).
    """
    path = root / "config/dependency-closure-v1.json"
    if not path.is_file():
        raise ValueError(f"dependency closure record file not found: {path}")
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(
            "dependency closure record is not readable UTF-8 JSON"
        ) from exc
    if not isinstance(raw, dict):
        raise ValueError("dependency closure record must be a JSON object")
    _require_exact_keys(raw, _RECORD_FIELDS, "dependency_closure_record")
    if _require_str(raw, "record_type") != RECORD_TYPE:
        raise ValueError("dependency closure record has an unexpected type")
    if _require_int(raw, "schema_version") != RECORD_SCHEMA_VERSION:
        raise ValueError("dependency closure record has an unexpected schema version")
    stored_digest = _require_sha256(raw, "evidence_digest")
    if _compute_record_digest(raw) != stored_digest:
        raise ValueError("dependency closure record evidence digest mismatch")
    distributions_raw = raw.get("distributions")
    if not isinstance(distributions_raw, list) or not distributions_raw:
        raise ValueError("dependency closure record distributions must be non-empty")
    distributions = tuple(
        _parse_distribution(item, index) for index, item in enumerate(distributions_raw)
    )
    lock_path = root / "requirements/dev.lock"
    if not lock_path.is_file():
        raise ValueError(f"project lock file not found: {lock_path}")
    actual_lock_sha256 = sha256_bytes(lock_path.read_bytes())
    if actual_lock_sha256 != _require_sha256(raw, "dev_lock_sha256"):
        raise ValueError(
            "dependency closure record lock digest mismatch — "
            "requirements/dev.lock no longer matches the record"
        )
    return DependencyClosureV1(
        schema_version=RECORD_SCHEMA_VERSION,
        record_type=RECORD_TYPE,
        python_version=_require_str(raw, "python_version"),
        python_requirement=_require_str(raw, "python_requirement"),
        pytest_version=_require_str(raw, "pytest_version"),
        ruff_version=_require_str(raw, "ruff_version"),
        mypy_version=_require_str(raw, "mypy_version"),
        gate_lock_sha256=_require_sha256(raw, "gate_lock_sha256"),
        dev_lock_sha256=actual_lock_sha256,
        direct_families=_parse_direct_families(raw.get("direct_families")),
        distributions=distributions,
        evidence_digest=stored_digest,
    )


def _declared_name(spec: str) -> str:
    """Extract the PEP 503 normalized name from one declared spec string."""
    match = re.match(r"^[A-Za-z0-9][A-Za-z0-9._-]*", spec)
    if match is None:
        raise ValueError(f"malformed declared dependency: {spec!r}")
    return _normalize_dist_name(match.group(0))


def _declared_family(declared: DeclaredDependencySetV1, name: str) -> str | None:
    for family in ("runtime", "build", "development"):
        if name in {_declared_name(spec) for spec in getattr(declared, family)}:
            return family
    return None


def validate_dependency_closure(
    root: Path, declared: DeclaredDependencySetV1
) -> DependencyClosureReportV1:
    """Verify the declared stack, the unique record, the lock, and the gate
    identity as one agreement, returning the closed six-category verdict.

    Fails closed (ValueError) on missing or malformed inputs; the returned
    report is empty exactly when the closure is complete and consistent.
    """
    record = load_dependency_closure(root)
    lock_entries, lock_index = parse_lock_entries(
        (root / "requirements/dev.lock").read_bytes()
    )
    gate = load_gate_toolchain_snapshot(root)

    record_families = dict(record.direct_families)
    declared_names = {
        _declared_name(spec)
        for family in ("runtime", "build", "development")
        for spec in getattr(declared, family)
    }
    missing_direct = sorted(
        name for name in declared_names if name not in record_families
    )
    extra_or_misclassified_direct = sorted(
        name
        for name, family in record_families.items()
        if name not in declared_names or _declared_family(declared, name) != family
    )

    record_distributions = {entry.name: entry for entry in record.distributions}
    lock_distributions = {entry.name: entry for entry in lock_entries}
    missing_transitive_or_hash = sorted(
        name
        for name in sorted(set(lock_distributions) | set(record_distributions))
        if name not in lock_distributions
        or name not in record_distributions
        or record_distributions[name].version != lock_distributions[name].version
        or not record_distributions[name].hashes
        or set(record_distributions[name].hashes)
        != set(lock_distributions[name].hashes)
    )
    marker_or_source_mismatches = sorted(
        name
        for name in sorted(set(lock_distributions) & set(record_distributions))
        if lock_distributions[name].marker != record_distributions[name].marker
    )
    if lock_index != declared.source_index_url:
        marker_or_source_mismatches.append("index-url")

    gate_tool_version_mismatches = sorted(
        tool
        for tool in ("pytest", "ruff", "mypy")
        if getattr(record, f"{tool}_version") != getattr(gate, f"{tool}_version")
    )
    if record.gate_lock_sha256 != gate.gate_lock_sha256:
        gate_tool_version_mismatches.append("gate-lock")
    python_version_mismatches: list[str] = []
    if record.python_version != gate.python_version:
        python_version_mismatches.append("python")
    if record.python_requirement != declared.python_requirement:
        python_version_mismatches.append("python-requirement")

    return DependencyClosureReportV1(
        missing_direct=tuple(missing_direct),
        extra_or_misclassified_direct=tuple(extra_or_misclassified_direct),
        missing_transitive_or_hash=tuple(missing_transitive_or_hash),
        marker_or_source_mismatches=tuple(marker_or_source_mismatches),
        gate_tool_version_mismatches=tuple(gate_tool_version_mismatches),
        python_version_mismatches=tuple(python_version_mismatches),
    )

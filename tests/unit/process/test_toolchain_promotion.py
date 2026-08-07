"""T04.1 legacy step 4.F: formal toolchain promotion tests."""

from __future__ import annotations

import hashlib
import json
import tempfile
import tomllib
from pathlib import Path

import pytest

from vespercode.project.toolchain_promotion import (
    DEFAULT_OFFLINE_EXCLUSION,
    MARKERS_V1,
    FormalToolchainPromotionV1,
    canonical_offline_commands,
    dedicated_environment_command,
    load_formal_toolchain_promotion,
    marker_declaration,
    static_rule_declaration,
)
from spikes.win32_workspace_boundary.report import (
    GateToolchainEvidenceV1,
    load_workspace_boundary_gate_report,
)
from tests.unit.process.workspace_boundary_fixtures import (
    build_workspace_boundary_gate_test_fixture,
)


@pytest.fixture
def gate_evidence() -> GateToolchainEvidenceV1:
    return load_workspace_boundary_gate_report(Path(".")).gate_toolchain


def test_formal_toolchain_matches_frozen_gate_identity(
    gate_evidence: GateToolchainEvidenceV1,
) -> None:
    record = load_formal_toolchain_promotion(Path("."))
    assert record.python_version == gate_evidence.python_version
    assert record.gate_lock_sha256 == gate_evidence.gate_lock_sha256
    assert record.pytest_version == gate_evidence.pytest_version
    assert record.ruff_version == gate_evidence.ruff_version
    assert record.mypy_version == gate_evidence.mypy_version


def _canonical_compact_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def test_formal_toolchain_record_digests_round_trip() -> None:
    record = load_formal_toolchain_promotion(Path("."))
    marker_digest = hashlib.sha256(
        _canonical_compact_json(marker_declaration()).encode("utf-8")
    ).hexdigest()
    static_digest = hashlib.sha256(
        _canonical_compact_json(static_rule_declaration()).encode("utf-8")
    ).hexdigest()
    assert record.marker_digest == marker_digest
    assert record.static_rule_digest == static_digest


def test_pyproject_registers_exact_markers_and_static_rules() -> None:
    root = Path(__file__).resolve().parents[3]
    data = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    pytest_options = data.get("tool", {}).get("pytest", {}).get("ini_options", {})
    markers = pytest_options.get("markers")
    addopts = pytest_options.get("addopts")
    testpaths = pytest_options.get("testpaths")
    assert isinstance(markers, list)
    registered = tuple(str(item).split(":", 1)[0].strip() for item in markers)
    assert registered == MARKERS_V1
    assert isinstance(addopts, str)
    assert DEFAULT_OFFLINE_EXCLUSION in addopts
    assert isinstance(testpaths, list) and testpaths == ["tests"]

    ruff = data.get("tool", {}).get("ruff", {})
    assert ruff.get("target-version") == "py312"
    assert ruff.get("line-length") == 88
    assert ruff.get("extend-exclude") == [
        ".venv-gate",
        ".venv-formal",
        "*.md",
        "reference/fixture",
    ]
    ruff_format = ruff.get("format", {})
    assert ruff_format.get("line-ending") == "lf"
    assert ruff_format.get("quote-style") == "double"
    assert ruff_format.get("indent-style") == "space"
    assert ruff.get("lint", {}).get("select") == ["E4", "E7", "E9", "F"]

    mypy = data.get("tool", {}).get("mypy", {})
    assert mypy.get("python_version") == "3.12"
    assert mypy.get("strict") is True
    assert mypy.get("warn_unused_configs") is True


def test_canonical_offline_commands_are_fixed() -> None:
    assert canonical_offline_commands() == (
        ("python", "-m", "pytest", "-q"),
        ("python", "-m", "ruff", "format", "--check", "."),
        ("python", "-m", "ruff", "check", "."),
        ("python", "-m", "mypy", "src", "tests"),
    )


def test_dedicated_environment_command_clears_addopts_selects_marker_names_root() -> (
    None
):
    command = dedicated_environment_command(
        "windows_integration", "tests/integration/windows"
    )
    assert command == (
        "python",
        "-m",
        "pytest",
        "-q",
        "-o",
        "addopts=",
        "-m",
        "windows_integration",
        "tests/integration/windows",
    )
    with pytest.raises(ValueError):
        dedicated_environment_command("not_a_marker", "tests")


def test_load_formal_toolchain_promotion_rejects_gate_identity_drift() -> None:
    with tempfile.TemporaryDirectory() as raw_temp_root:
        temp_root = Path(raw_temp_root)
        build_workspace_boundary_gate_test_fixture(temp_root, "3.12.999")
        record_dir = temp_root / "config"
        record_dir.mkdir(parents=True)
        repo_root = Path(__file__).resolve().parents[3]
        (record_dir / "formal-toolchain-promotion-v1.json").write_bytes(
            (repo_root / "config/formal-toolchain-promotion-v1.json").read_bytes()
        )
        with pytest.raises(ValueError):
            load_formal_toolchain_promotion(temp_root)


def test_load_formal_toolchain_promotion_rejects_drifted_record_digest() -> None:
    with tempfile.TemporaryDirectory() as raw_temp_root:
        temp_root = Path(raw_temp_root)
        repo_root = Path(__file__).resolve().parents[3]
        record_dir = temp_root / "config"
        record_dir.mkdir(parents=True)
        record_path = record_dir / "formal-toolchain-promotion-v1.json"
        record = json.loads(
            (repo_root / "config/formal-toolchain-promotion-v1.json").read_text(
                encoding="utf-8"
            )
        )
        if not isinstance(record, dict):
            raise AssertionError("promotion record must be a JSON object")
        record["python_version"] = "3.12.5"
        record_path.write_text(json.dumps(record), encoding="utf-8")
        with pytest.raises(ValueError):
            load_formal_toolchain_promotion(temp_root)


def test_formal_toolchain_record_identity_fields_are_exact() -> None:
    record = load_formal_toolchain_promotion(Path("."))
    assert isinstance(record, FormalToolchainPromotionV1)
    assert record.python_version == "3.12.4"
    assert record.gate_lock_sha256 == (
        "585f7bcde329392aeef651162fe68b702b0224f0f0a631778de89894737886ab"
    )
    assert record.pytest_version == "8.4.2"
    assert record.ruff_version == "0.16.1"
    assert record.mypy_version == "2.3.0"

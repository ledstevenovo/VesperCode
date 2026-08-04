"""T02.1 step 2.A: locked reference fixture and frozen build-input contract."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from spikes.docker_reference_boundary import input_contract
from spikes.docker_reference_boundary.input_contract import (
    BASE_IMAGE_DIGEST,
    BUILD_RECIPE_VERSION,
    REGISTRY_IMAGE_DIGEST,
    freeze_reference_build_input,
)

_LOCK_BYTES = (
    "--index-url https://pypi.org/simple\n"
    "pytest==8.4.2 --hash=sha256:872f880de3fc3a5bdc88a11b39c9710c3497a547cfa9320bc3c5e62fbf272e79\n"
).encode("utf-8")


def reference_root() -> Path:
    return Path(__file__).resolve().parents[3]


def fixture_lock_digest() -> str:
    return hashlib.sha256(
        (reference_root() / "reference" / "fixture" / "requirements.lock").read_bytes()
    ).hexdigest()


def _seed_reference_tree(root: Path) -> None:
    """Mirror the frozen repository layout with representative bytes."""
    (root / "requirements").mkdir(parents=True, exist_ok=True)
    (root / "requirements" / "reference.lock").write_bytes(_LOCK_BYTES)
    fixture_root = root / "reference" / "fixture"
    (fixture_root / "src" / "vesper_fixture").mkdir(parents=True, exist_ok=True)
    (fixture_root / "tests").mkdir(parents=True, exist_ok=True)
    (fixture_root / "requirements.lock").write_bytes(_LOCK_BYTES)
    (fixture_root / "pyproject.toml").write_text(
        '[project]\nname = "vesper-fixture"\n', encoding="utf-8"
    )
    (fixture_root / "src" / "vesper_fixture" / "calculator.py").write_text(
        "def add(left, right):\n    return left - right\n", encoding="utf-8"
    )
    (fixture_root / "tests" / "test_calculator.py").write_text(
        "def test_add():\n    assert add(2, 2) == 4\n", encoding="utf-8"
    )
    evidence = root / "gates" / "evidence"
    evidence.mkdir(parents=True, exist_ok=True)
    (evidence / "gate-toolchain-v1.json").write_text(
        json.dumps(
            {
                "python_version": "3.12.4",
                "pytest_version": "8.4.2",
                "ruff_version": "0.16.1",
                "mypy_version": "2.3.0",
            }
        ),
        encoding="utf-8",
    )


def test_reference_lock_and_fixture_lock_must_be_byte_identical() -> None:
    assert (
        freeze_reference_build_input(reference_root()).requirements_digest
        == fixture_lock_digest()
    )


def test_real_repo_freeze_is_deterministic_and_binds_all_identities() -> None:
    first = freeze_reference_build_input(reference_root())
    second = freeze_reference_build_input(reference_root())
    assert first == second
    for field in (
        "base_image_digest",
        "registry_image_digest",
        "requirements_digest",
        "fixture_tree_digest",
        "tool_versions_digest",
    ):
        digest = getattr(first, field)
        assert len(digest) == 64
        assert set(digest) <= set("0123456789abcdef")
    assert first.build_recipe_version == BUILD_RECIPE_VERSION
    assert first.base_image_digest == BASE_IMAGE_DIGEST
    assert first.registry_image_digest == REGISTRY_IMAGE_DIGEST


def test_reference_input_freeze_matrix(tmp_path: Path) -> None:
    """Exact lock/fixture/tool/build parameters freeze deterministically and
    reject drift."""
    seeded = tmp_path / "tree"
    _seed_reference_tree(seeded)
    baseline = freeze_reference_build_input(seeded)

    # Row 1: deterministic freeze of every declared identity.
    assert freeze_reference_build_input(seeded) == baseline

    # Row 2: fixture lock copy drift is rejected before any freeze result.
    (seeded / "reference" / "fixture" / "requirements.lock").write_bytes(
        _LOCK_BYTES + b"\n"
    )
    with pytest.raises(ValueError, match="byte-identical"):
        freeze_reference_build_input(seeded)
    (seeded / "reference" / "fixture" / "requirements.lock").write_bytes(_LOCK_BYTES)

    # Row 3: lock drift changes exactly the lock-bound identities.
    drifted_lock = _LOCK_BYTES + b"# drift\n"
    (seeded / "requirements" / "reference.lock").write_bytes(drifted_lock)
    (seeded / "reference" / "fixture" / "requirements.lock").write_bytes(drifted_lock)
    drifted = freeze_reference_build_input(seeded)
    assert drifted.requirements_digest != baseline.requirements_digest
    assert drifted.fixture_tree_digest != baseline.fixture_tree_digest
    assert drifted.tool_versions_digest == baseline.tool_versions_digest
    assert drifted.base_image_digest == baseline.base_image_digest
    assert drifted.registry_image_digest == baseline.registry_image_digest
    assert drifted.build_recipe_version == baseline.build_recipe_version
    (seeded / "requirements" / "reference.lock").write_bytes(_LOCK_BYTES)
    (seeded / "reference" / "fixture" / "requirements.lock").write_bytes(_LOCK_BYTES)

    # Row 4: fixture source drift changes only the fixture-tree identity.
    (
        seeded / "reference" / "fixture" / "src" / "vesper_fixture" / "calculator.py"
    ).write_text("def add(left, right):\n    return left + right\n", encoding="utf-8")
    fixture_drifted = freeze_reference_build_input(seeded)
    assert fixture_drifted.fixture_tree_digest != baseline.fixture_tree_digest
    assert fixture_drifted.requirements_digest == baseline.requirements_digest
    assert fixture_drifted.tool_versions_digest == baseline.tool_versions_digest

    # Row 5: tool-version drift changes only the tool-version identity.
    evidence = seeded / "gates" / "evidence" / "gate-toolchain-v1.json"
    tool_body = json.loads(evidence.read_text(encoding="utf-8"))
    tool_body["python_version"] = "3.12.5"
    evidence.write_text(json.dumps(tool_body), encoding="utf-8")
    tool_drifted = freeze_reference_build_input(seeded)
    assert tool_drifted.tool_versions_digest != baseline.tool_versions_digest
    assert tool_drifted.fixture_tree_digest == fixture_drifted.fixture_tree_digest
    assert tool_drifted.requirements_digest == fixture_drifted.requirements_digest


def test_freeze_rejects_malformed_recipe_image_digests(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _seed_reference_tree(tmp_path)
    monkeypatch.setattr(input_contract, "BASE_IMAGE_DIGEST", "not-a-digest")
    with pytest.raises(ValueError, match="base_image_digest"):
        freeze_reference_build_input(tmp_path)
    monkeypatch.setattr(input_contract, "BASE_IMAGE_DIGEST", BASE_IMAGE_DIGEST)
    monkeypatch.setattr(input_contract, "REGISTRY_IMAGE_DIGEST", "abc")
    with pytest.raises(ValueError, match="registry_image_digest"):
        freeze_reference_build_input(tmp_path)


def test_freeze_rejects_missing_declared_inputs(tmp_path: Path) -> None:
    _seed_reference_tree(tmp_path)
    (tmp_path / "requirements" / "reference.lock").unlink()
    with pytest.raises(ValueError, match="missing frozen reference input"):
        freeze_reference_build_input(tmp_path)


def test_freeze_rejects_drifted_tool_evidence_versions(tmp_path: Path) -> None:
    _seed_reference_tree(tmp_path)
    evidence = tmp_path / "gates" / "evidence" / "gate-toolchain-v1.json"
    evidence.write_text('{"python_version": "3.12.4"}', encoding="utf-8")
    with pytest.raises(ValueError, match="gate toolchain evidence missing"):
        freeze_reference_build_input(tmp_path)
    evidence.write_text(
        json.dumps(
            {
                "python_version": 42,
                "pytest_version": "8.4.2",
                "ruff_version": "0.16.1",
                "mypy_version": "2.3.0",
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="versions must be strings"):
        freeze_reference_build_input(tmp_path)

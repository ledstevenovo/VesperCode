"""T04.1 legacy step 4.A: formal bootstrap contract and dependency closure tests."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tomllib
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Callable

import pytest

from vespercode.project.dependency_closure import (
    FIXED_PYPI_SIMPLE_INDEX_URL,
    DeclaredDependencySetV1,
    load_dependency_closure,
    validate_dependency_closure,
)
from spikes.win32_workspace_boundary.report import (
    WORKSPACE_BOUNDARY_GO_EVIDENCE_PATH,
    GateToolchainEvidenceV1,
    load_workspace_boundary_gate_report,
)
from tests.unit.process.workspace_boundary_fixtures import (
    build_workspace_boundary_gate_test_fixture,
)


class FormalBootstrapContractTest(unittest.TestCase):
    def test_required_formal_bootstrap_artifacts_exist(self) -> None:
        root = Path(__file__).resolve().parents[3]
        required = (
            "pyproject.toml",
            "requirements/dev.lock",
            "scripts/bootstrap_formal_env.py",
            ".venv-formal/Scripts/python.exe",
        )
        missing = tuple(path for path in required if not (root / path).is_file())
        self.assertEqual(
            missing,
            (),
            "MISSING_FORMAL_BOOTSTRAP_ARTIFACTS:" + ",".join(missing),
        )

    def test_formal_bootstrap_rejects_python_patch_mismatch_before_environment_creation(
        self,
    ) -> None:
        root = Path(__file__).resolve().parents[3]
        with TemporaryDirectory() as raw_temp_root:
            temp_root = Path(raw_temp_root)
            evidence_path = temp_root / WORKSPACE_BOUNDARY_GO_EVIDENCE_PATH
            mismatched = build_workspace_boundary_gate_test_fixture(
                temp_root,
                python_version="3.12.999",
            )
            self.assertEqual(load_workspace_boundary_gate_report(temp_root), mismatched)
            completed = subprocess.run(
                (
                    sys.executable,
                    str(root / "scripts/bootstrap_formal_env.py"),
                    "--root",
                    str(temp_root),
                    "--gate-evidence",
                    str(evidence_path),
                ),
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(completed.returncode, 0)
            self.assertIn("FORMAL_PYTHON_VERSION_MISMATCH:", completed.stderr)
            self.assertFalse((temp_root / ".venv-formal").exists())


@pytest.fixture
def gate_evidence() -> GateToolchainEvidenceV1:
    return load_workspace_boundary_gate_report(Path(".")).gate_toolchain


def _reviewed_plan_stack() -> DeclaredDependencySetV1:
    root = Path(__file__).resolve().parents[3]
    data = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    project = data["project"]
    if not isinstance(project, dict):
        raise ValueError("pyproject.toml [project] must be an object")
    dependencies = project.get("dependencies")
    optional = project.get("optional-dependencies")
    if not isinstance(dependencies, list) or not isinstance(optional, dict):
        raise ValueError("pyproject.toml dependency tables are malformed")
    build = optional.get("build")
    development = optional.get("development")
    if not isinstance(build, list) or not isinstance(development, list):
        raise ValueError("pyproject.toml optional dependency groups are malformed")
    return DeclaredDependencySetV1(
        python_requirement=str(project["requires-python"]),
        source_index_url=FIXED_PYPI_SIMPLE_INDEX_URL,
        runtime=tuple(str(item) for item in dependencies),
        build=tuple(str(item) for item in build),
        development=tuple(str(item) for item in development),
    )


@pytest.fixture
def reviewed_plan_stack() -> DeclaredDependencySetV1:
    return _reviewed_plan_stack()


def test_declared_v1_dependency_closure_is_complete(
    reviewed_plan_stack: DeclaredDependencySetV1,
    gate_evidence: GateToolchainEvidenceV1,
) -> None:
    report = validate_dependency_closure(Path("."), reviewed_plan_stack)
    record = load_dependency_closure(Path("."))
    assert record.python_version == gate_evidence.python_version
    assert report.missing_direct == ()
    assert report.extra_or_misclassified_direct == ()
    assert report.missing_transitive_or_hash == ()
    assert report.marker_or_source_mismatches == ()
    assert report.gate_tool_version_mismatches == ()
    assert report.python_version_mismatches == ()


def _run_bootstrap(root: Path, evidence: Path) -> subprocess.CompletedProcess[str]:
    repo_root = Path(__file__).resolve().parents[3]
    return subprocess.run(
        (
            sys.executable,
            str(repo_root / "scripts/bootstrap_formal_env.py"),
            "--root",
            str(root),
            "--gate-evidence",
            str(evidence),
        ),
        check=False,
        capture_output=True,
        text=True,
    )


def test_formal_bootstrap_rejects_missing_gate_evidence() -> None:
    with TemporaryDirectory() as raw_temp_root:
        temp_root = Path(raw_temp_root)
        evidence = temp_root / WORKSPACE_BOUNDARY_GO_EVIDENCE_PATH
        completed = _run_bootstrap(temp_root, evidence)
        assert completed.returncode != 0
        assert "FORMAL_EVIDENCE_INVALID" in completed.stderr
        assert not (temp_root / ".venv-formal").exists()


def test_formal_bootstrap_rejects_malformed_gate_evidence() -> None:
    with TemporaryDirectory() as raw_temp_root:
        temp_root = Path(raw_temp_root)
        evidence = temp_root / WORKSPACE_BOUNDARY_GO_EVIDENCE_PATH
        evidence.parent.mkdir(parents=True)
        evidence.write_text("{not json", encoding="utf-8")
        completed = _run_bootstrap(temp_root, evidence)
        assert completed.returncode != 0
        assert "FORMAL_EVIDENCE_INVALID" in completed.stderr
        assert not (temp_root / ".venv-formal").exists()


def _report_body_digest(body: dict[str, object]) -> str:
    return hashlib.sha256(
        json.dumps(
            body,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
            separators=(",", ": "),
        ).encode("utf-8")
    ).hexdigest()


def _write_report_json(evidence: Path, data: dict[str, object]) -> None:
    evidence.write_text(
        json.dumps(
            data,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
            separators=(",", ": "),
        )
        + "\n",
        encoding="utf-8",
    )


def test_formal_bootstrap_rejects_non_go_evidence() -> None:
    with TemporaryDirectory() as raw_temp_root:
        temp_root = Path(raw_temp_root)
        evidence = temp_root / WORKSPACE_BOUNDARY_GO_EVIDENCE_PATH
        build_workspace_boundary_gate_test_fixture(temp_root, "3.12.4")
        data = json.loads(evidence.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise AssertionError("report must be a JSON object")
        mutex_probe = data.get("mutex_probe")
        if not isinstance(mutex_probe, dict):
            raise AssertionError("mutex_probe must be a JSON object")
        mutex_probe["cleanup_verified"] = False
        data["outcome"] = "NO_GO"
        data["evidence_digest"] = _report_body_digest(
            {key: value for key, value in data.items() if key != "evidence_digest"}
        )
        _write_report_json(evidence, data)
        completed = _run_bootstrap(temp_root, evidence)
        assert completed.returncode != 0
        assert "FORMAL_EVIDENCE_INVALID" in completed.stderr
        assert not (temp_root / ".venv-formal").exists()


def test_formal_bootstrap_rejects_drifted_evidence_digest() -> None:
    with TemporaryDirectory() as raw_temp_root:
        temp_root = Path(raw_temp_root)
        evidence = temp_root / WORKSPACE_BOUNDARY_GO_EVIDENCE_PATH
        build_workspace_boundary_gate_test_fixture(temp_root, "3.12.4")
        data = json.loads(evidence.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise AssertionError("report must be a JSON object")
        mutex_probe = data.get("mutex_probe")
        if not isinstance(mutex_probe, dict):
            raise AssertionError("mutex_probe must be a JSON object")
        mutex_probe["timeout_count"] = 1
        _write_report_json(evidence, data)
        completed = _run_bootstrap(temp_root, evidence)
        assert completed.returncode != 0
        assert "FORMAL_EVIDENCE_INVALID" in completed.stderr
        assert not (temp_root / ".venv-formal").exists()


def test_formal_bootstrap_rejects_drifted_toolchain_binding() -> None:
    with TemporaryDirectory() as raw_temp_root:
        temp_root = Path(raw_temp_root)
        evidence = temp_root / WORKSPACE_BOUNDARY_GO_EVIDENCE_PATH
        build_workspace_boundary_gate_test_fixture(temp_root, "3.12.999")
        toolchain_path = temp_root / "gates/evidence/gate-toolchain-v1.json"
        toolchain = json.loads(toolchain_path.read_text(encoding="utf-8"))
        if not isinstance(toolchain, dict):
            raise AssertionError("toolchain must be a JSON object")
        toolchain["python_version"] = "3.12.4"
        toolchain_path.write_text(json.dumps(toolchain), encoding="utf-8")
        completed = _run_bootstrap(temp_root, evidence)
        assert completed.returncode != 0
        assert "FORMAL_EVIDENCE_INVALID" in completed.stderr
        assert not (temp_root / ".venv-formal").exists()


def test_formal_bootstrap_rejects_missing_lock_after_python_equality() -> None:
    with TemporaryDirectory() as raw_temp_root:
        temp_root = Path(raw_temp_root)
        evidence = temp_root / WORKSPACE_BOUNDARY_GO_EVIDENCE_PATH
        build_workspace_boundary_gate_test_fixture(temp_root, "3.12.4")
        completed = _run_bootstrap(temp_root, evidence)
        assert completed.returncode != 0
        assert "FORMAL_LOCK_INVALID" in completed.stderr
        assert not (temp_root / ".venv-formal").exists()


def test_formal_bootstrap_rejects_malformed_lock_after_equality() -> None:
    with TemporaryDirectory() as raw_temp_root:
        temp_root = Path(raw_temp_root)
        evidence = temp_root / WORKSPACE_BOUNDARY_GO_EVIDENCE_PATH
        build_workspace_boundary_gate_test_fixture(temp_root, "3.12.4")
        lock_dir = temp_root / "requirements"
        lock_dir.mkdir(parents=True)
        (lock_dir / "dev.lock").write_text(
            "--index-url https://pypi.org/simple\nnot-a-lock-line\n",
            encoding="utf-8",
        )
        completed = _run_bootstrap(temp_root, evidence)
        assert completed.returncode != 0
        assert "FORMAL_LOCK_INVALID" in completed.stderr
        assert not (temp_root / ".venv-formal").exists()


def _recompute_record_digest(record: dict[str, object]) -> str:
    body = {key: value for key, value in record.items() if key != "evidence_digest"}
    return hashlib.sha256(
        json.dumps(body, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _build_closure_temp_root(
    temp_root: Path, mutate_record: Callable[[dict[str, object]], None]
) -> None:
    """One loader-valid synthetic closure root with a mutated record.

    Copies the committed lock and record bytes, applies the mutation to the
    record copy, and recomputes the record digest so only the mutation is
    observable.
    """
    repo_root = Path(__file__).resolve().parents[3]
    build_workspace_boundary_gate_test_fixture(temp_root, "3.12.4")
    lock_dir = temp_root / "requirements"
    lock_dir.mkdir(parents=True)
    (lock_dir / "dev.lock").write_bytes(
        (repo_root / "requirements/dev.lock").read_bytes()
    )
    record_dir = temp_root / "config"
    record_dir.mkdir(parents=True)
    record = json.loads(
        (repo_root / "config/dependency-closure-v1.json").read_text(encoding="utf-8")
    )
    if not isinstance(record, dict):
        raise AssertionError("closure record must be a JSON object")
    mutate_record(record)
    record["evidence_digest"] = _recompute_record_digest(record)
    (record_dir / "dependency-closure-v1.json").write_text(
        json.dumps(record, sort_keys=True, separators=(",", ":")),
        encoding="utf-8",
    )


def test_validate_dependency_closure_reports_python_version_drift() -> None:
    with TemporaryDirectory() as raw_temp_root:
        temp_root = Path(raw_temp_root)

        def mutate(record: dict[str, object]) -> None:
            record["python_version"] = "3.12.999"

        _build_closure_temp_root(temp_root, mutate_record=mutate)
        report = validate_dependency_closure(temp_root, _reviewed_plan_stack())
        assert report.python_version_mismatches == ("python",)
        assert report.gate_tool_version_mismatches == ()
        assert report.missing_direct == ()
        assert report.extra_or_misclassified_direct == ()


def test_validate_dependency_closure_reports_gate_tool_version_drift() -> None:
    with TemporaryDirectory() as raw_temp_root:
        temp_root = Path(raw_temp_root)

        def mutate(record: dict[str, object]) -> None:
            record["pytest_version"] = "8.4.1"

        _build_closure_temp_root(temp_root, mutate_record=mutate)
        report = validate_dependency_closure(temp_root, _reviewed_plan_stack())
        assert report.gate_tool_version_mismatches == ("pytest",)
        assert report.python_version_mismatches == ()


def test_validate_dependency_closure_reports_missing_direct_declaration() -> None:
    with TemporaryDirectory() as raw_temp_root:
        temp_root = Path(raw_temp_root)

        def mutate(record: dict[str, object]) -> None:
            families = record.get("direct_families")
            if not isinstance(families, dict):
                raise AssertionError("direct_families must be an object")
            families.pop("fastapi")

        _build_closure_temp_root(temp_root, mutate_record=mutate)
        report = validate_dependency_closure(temp_root, _reviewed_plan_stack())
        assert report.missing_direct == ("fastapi",)
        assert report.extra_or_misclassified_direct == ()


def test_validate_dependency_closure_reports_family_misclassification() -> None:
    with TemporaryDirectory() as raw_temp_root:
        temp_root = Path(raw_temp_root)

        def mutate(record: dict[str, object]) -> None:
            families = record.get("direct_families")
            if not isinstance(families, dict):
                raise AssertionError("direct_families must be an object")
            families["pytest"] = "runtime"

        _build_closure_temp_root(temp_root, mutate_record=mutate)
        report = validate_dependency_closure(temp_root, _reviewed_plan_stack())
        assert report.extra_or_misclassified_direct == ("pytest",)
        assert report.missing_direct == ()


def test_validate_dependency_closure_reports_missing_distribution() -> None:
    with TemporaryDirectory() as raw_temp_root:
        temp_root = Path(raw_temp_root)

        def mutate(record: dict[str, object]) -> None:
            distributions = record.get("distributions")
            if not isinstance(distributions, list):
                raise AssertionError("distributions must be an array")
            record["distributions"] = [
                item
                for item in distributions
                if not (isinstance(item, dict) and item.get("name") == "pytest")
            ]

        _build_closure_temp_root(temp_root, mutate_record=mutate)
        report = validate_dependency_closure(temp_root, _reviewed_plan_stack())
        assert report.missing_transitive_or_hash == ("pytest",)
        assert report.marker_or_source_mismatches == ()


def test_validate_dependency_closure_reports_marker_mismatch() -> None:
    with TemporaryDirectory() as raw_temp_root:
        temp_root = Path(raw_temp_root)

        def mutate(record: dict[str, object]) -> None:
            distributions = record.get("distributions")
            if not isinstance(distributions, list):
                raise AssertionError("distributions must be an array")
            for item in distributions:
                if isinstance(item, dict) and item.get("name") == "pytest":
                    item["marker"] = "sys_platform == 'win32'"

        _build_closure_temp_root(temp_root, mutate_record=mutate)
        report = validate_dependency_closure(temp_root, _reviewed_plan_stack())
        assert report.marker_or_source_mismatches == ("pytest",)
        assert report.missing_transitive_or_hash == ()


def test_validate_dependency_closure_reports_extra_record_distribution() -> None:
    with TemporaryDirectory() as raw_temp_root:
        temp_root = Path(raw_temp_root)

        def mutate(record: dict[str, object]) -> None:
            distributions = record.get("distributions")
            if not isinstance(distributions, list):
                raise AssertionError("distributions must be an array")
            distributions.append(
                {
                    "name": "phantom-package",
                    "version": "9.9.9",
                    "marker": "",
                    "hashes": ["0" * 64],
                }
            )

        _build_closure_temp_root(temp_root, mutate_record=mutate)
        report = validate_dependency_closure(temp_root, _reviewed_plan_stack())
        assert report.missing_transitive_or_hash == ("phantom-package",)
        assert report.marker_or_source_mismatches == ()


def test_validate_dependency_closure_reports_gate_lock_digest_drift() -> None:
    with TemporaryDirectory() as raw_temp_root:
        temp_root = Path(raw_temp_root)

        def mutate(record: dict[str, object]) -> None:
            record["gate_lock_sha256"] = "1" * 64

        _build_closure_temp_root(temp_root, mutate_record=mutate)
        report = validate_dependency_closure(temp_root, _reviewed_plan_stack())
        assert report.gate_tool_version_mismatches == ("gate-lock",)
        assert report.python_version_mismatches == ()


def test_validate_dependency_closure_reports_python_range_drift() -> None:
    with TemporaryDirectory() as raw_temp_root:
        temp_root = Path(raw_temp_root)
        _build_closure_temp_root(temp_root, mutate_record=lambda record: None)
        stack = _reviewed_plan_stack()
        drifted = DeclaredDependencySetV1(
            python_requirement=">=3.13,<3.14",
            source_index_url=stack.source_index_url,
            runtime=stack.runtime,
            build=stack.build,
            development=stack.development,
        )
        report = validate_dependency_closure(temp_root, drifted)
        assert report.python_version_mismatches == ("python-requirement",)
        assert report.python_version_mismatches != ("python",)


def test_validate_dependency_closure_reports_source_policy_mismatch() -> None:
    with TemporaryDirectory() as raw_temp_root:
        temp_root = Path(raw_temp_root)
        _build_closure_temp_root(temp_root, mutate_record=lambda record: None)
        stack = _reviewed_plan_stack()
        drifted = DeclaredDependencySetV1(
            python_requirement=stack.python_requirement,
            source_index_url="https://example.invalid/simple",
            runtime=stack.runtime,
            build=stack.build,
            development=stack.development,
        )
        report = validate_dependency_closure(temp_root, drifted)
        assert report.marker_or_source_mismatches == ("index-url",)
        assert report.missing_direct == ()


def test_load_dependency_closure_rejects_drifted_record_digest() -> None:
    with TemporaryDirectory() as raw_temp_root:
        temp_root = Path(raw_temp_root)
        _build_closure_temp_root(temp_root, mutate_record=lambda record: None)
        record_path = temp_root / "config/dependency-closure-v1.json"
        record = json.loads(record_path.read_text(encoding="utf-8"))
        if not isinstance(record, dict):
            raise AssertionError("closure record must be a JSON object")
        record["ruff_version"] = "0.16.2"
        record_path.write_text(json.dumps(record), encoding="utf-8")
        with pytest.raises(ValueError):
            load_dependency_closure(temp_root)


def test_load_dependency_closure_rejects_drifted_lock_bytes() -> None:
    with TemporaryDirectory() as raw_temp_root:
        temp_root = Path(raw_temp_root)

        def mutate(record: dict[str, object]) -> None:
            record["dev_lock_sha256"] = "0" * 64

        _build_closure_temp_root(temp_root, mutate_record=mutate)
        with pytest.raises(ValueError):
            load_dependency_closure(temp_root)

"""T20.1 legacy step 20.A: static Python support detection tests.

The unit surface proves that ``PythonProjectAdapterV1.detect_static``
classifies the exact SPEC §1.4.1 static-check matrix exclusively from one
sealed ``SnapshotTreeV1`` and the frozen ``ReferenceProfileManifestV1``
with zero filesystem probes, project imports, subprocesses, or executor
calls, and that ``build_baseline_plan``/``build_formal_plan`` freeze the
one closed plan for each supported input (exact collect/full/target/Ruff/
Mypy identities, argv vectors, ordering, and target bindings).  The
classification matrix test is the operative "exact §5.1 matrix" authority
(registry row 20.A, PLAN.md:11401, per the SPEC_PROCESS §49 dangling
reference); runtime compatibility, execution, parsing, and Manifest
publication remain out of scope (GREEN-4).
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import cast

import pytest

# The adapter contracts are pydantic runtime models; the hash-locked gate
# toolchain does not install runtime dependencies, so this module skips
# cleanly there instead of failing at collection (formal env runs it fully).
pytest.importorskip("pydantic")

from pydantic import ValidationError

from vespercode.canonical.path_v1 import CanonicalRelativePathV1
from vespercode.profiles.reference import (
    ReferenceProfileManifestV1,
    load_reference_profile,
)
from vespercode.trees.content_store import ContentObjectStore
from vespercode.trees.snapshot import (
    AcceptedGitPreflightV1,
    SealedSnapshotInputFileV1,
    SnapshotTreeV1,
    create_snapshot,
)
from vespercode.trees.text_classifier import classify_supported_text
from vespercode.validation.python_adapter import (
    BaselineCheckPlanV1,
    CheckPlanError,
    PythonProjectAdapterV1,
    SupportedProjectV1,
    TargetTestIdSequenceV1,
    UnsupportedProjectV1,
)
from vespercode.workspace.git_preflight import GitPreflightResultV1

# The frozen T02.4 built-in identities (SPEC §1.4.1), independently
# recomputed by both review stages (test_reference.py precedent).
_FROZEN_POLICY_DIGEST = (
    "b857afca63e50a888ee183bd7ac8c7f739be7b60a94fc4f9c55c0a606db144ab"
)

_TARGET_ADD = "tests/test_calculator.py::test_add_returns_sum"
_TARGET_MULTIPLY = "tests/test_calculator.py::test_multiply_returns_product"


class SpyExecutor:
    """Zero-execution spy: any call would fail the adapter contract."""

    def __init__(self) -> None:
        self.call_count = 0
        self.calls: list[tuple[str, tuple[object, ...]]] = []

    def __call__(self, *args: object) -> object:
        self.call_count += 1
        self.calls.append(("call", args))
        return None


@pytest.fixture
def adapter() -> PythonProjectAdapterV1:
    """The adapter bound to the frozen built-in reference manifest."""
    return PythonProjectAdapterV1(reference_manifest=frozen_reference_manifest())


@pytest.fixture
def executor() -> SpyExecutor:
    """A spy proving detection never executes anything."""
    return SpyExecutor()


def frozen_reference_manifest() -> ReferenceProfileManifestV1:
    """The packaged frozen built-in manifest (verified by T06.2 loader)."""
    path = (
        Path(__file__).resolve().parents[3]
        / "src"
        / "vespercode"
        / "profiles"
        / "builtin"
        / "reference-profile-v1.json"
    )
    return load_reference_profile(path.read_bytes())


def _reference_lock_bytes() -> bytes:
    """The exact frozen reference lock bytes (digest == manifest lock)."""
    path = Path(__file__).resolve().parents[3] / "requirements" / "reference.lock"
    return path.read_bytes()


def _pyproject_bytes() -> bytes:
    """The fixture-shaped supported pyproject (SPEC §1.4.1 normal form)."""
    return (
        b"[project]\n"
        b'name = "vesper-fixture"\n'
        b'version = "0.1.0"\n'
        b'requires-python = ">=3.12,<3.13"\n'
        b"\n"
        b"[tool.pytest.ini_options]\n"
        b'testpaths = ["tests"]\n'
        b"\n"
        b"[tool.ruff]\n"
        b"line-length = 88\n"
        b"\n"
        b"[tool.mypy]\n"
        b'python_version = "3.12"\n'
        b"strict = true\n"
    )


def _supported_files() -> tuple[tuple[str, bytes], ...]:
    """The supported reference-profile file set (fixture-shaped)."""
    return (
        ("pyproject.toml", _pyproject_bytes()),
        ("requirements.lock", _reference_lock_bytes()),
        ("src/vesper_fixture/calculator.py", b"def add(a, b):\n    return a + b\n"),
        (
            "tests/test_calculator.py",
            b"from vesper_fixture.calculator import add\n\n"
            b"def test_add_returns_sum():\n    assert add(1, 2) == 3\n",
        ),
    )


def _seal(*, tracked_file_count: int, tracked_byte_count: int) -> GitPreflightResultV1:
    """One shape-valid SUPPORTED sealed Git-preflight result (T10.2 shape)."""
    return GitPreflightResultV1(
        schema_version=1,
        kind="SUPPORTED",
        head_commit_digest="0" * 40,
        index_digest="1" * 64,
        worktree_digest="2" * 64,
        ignore_rules_digest="3" * 64,
        attributes_digest="4" * 64,
        config_digest="5" * 64,
        repository_policy_digest=_FROZEN_POLICY_DIGEST,
        ignore_rules=(),
        tracked_file_count=tracked_file_count,
        tracked_byte_count=tracked_byte_count,
    )


def _snapshot(
    files: tuple[tuple[str, bytes], ...],
    *,
    repository_policy_digest: str = _FROZEN_POLICY_DIGEST,
) -> SnapshotTreeV1:
    """One sealed deterministic SnapshotTree from raw file rows."""
    ordered = tuple(sorted(files, key=lambda row: row[0]))
    accepted = AcceptedGitPreflightV1(
        schema_version=1,
        preflight=_seal(
            tracked_file_count=len(ordered),
            tracked_byte_count=sum(len(raw) for _, raw in ordered),
        ).model_copy(update={"repository_policy_digest": repository_policy_digest}),
        files=tuple(
            SealedSnapshotInputFileV1(
                schema_version=1,
                path=CanonicalRelativePathV1(path),
                content_sha256=hashlib.sha256(raw).hexdigest(),
                byte_count=len(raw),
            )
            for path, raw in ordered
        ),
    )
    store = ContentObjectStore()
    for _, raw in ordered:
        store.put(raw)
    return create_snapshot(accepted, store, classify_supported_text)


def _unsupported(files: tuple[tuple[str, bytes], ...]) -> SnapshotTreeV1:
    """One sealed tree with the supported set plus one extra file."""
    return _snapshot((*_supported_files(), *files))


def unsupported_snapshot() -> SnapshotTreeV1:
    """The exact RED probe input: a sealed Snapshot missing root files."""
    return _snapshot(
        (
            ("requirements.lock", _reference_lock_bytes()),
            ("src/a.py", b"x = 1\n"),
        )
    )


def _with_root_file(name: str, raw: bytes = b"value = 1\n") -> SnapshotTreeV1:
    return _unsupported(((name, raw),))


def _with_editable_non_text() -> SnapshotTreeV1:
    return _unsupported((("src/binary.dat", b"\x00\x01\x02"),))


def _tampered_manifest() -> ReferenceProfileManifestV1:
    """One manifest whose claimed digest no longer binds its fields."""
    return frozen_reference_manifest().model_copy(update={"digest": "0" * 64})


def _tampered_policy_snapshot() -> SnapshotTreeV1:
    return _snapshot(_supported_files(), repository_policy_digest="c" * 64)


def _matrix_case(
    label: str,
    snapshot: SnapshotTreeV1,
    manifest: ReferenceProfileManifestV1,
    expected_reasons: tuple[str, ...],
) -> tuple[str, SnapshotTreeV1, ReferenceProfileManifestV1, tuple[str, ...]]:
    return (label, snapshot, manifest, expected_reasons)


_MATRIX_CASES: tuple[
    tuple[str, SnapshotTreeV1, ReferenceProfileManifestV1, tuple[str, ...]], ...
] = (
    _matrix_case(
        "supported reference input",
        _snapshot(_supported_files()),
        frozen_reference_manifest(),
        (),
    ),
    _matrix_case(
        "missing pyproject.toml root file",
        _snapshot(
            (
                ("requirements.lock", _reference_lock_bytes()),
                ("src/a.py", b"x = 1\n"),
                ("tests/test_a.py", b"def test_a():\n    assert True\n"),
            )
        ),
        frozen_reference_manifest(),
        ("ROOT_FILE_MISSING:pyproject.toml",),
    ),
    _matrix_case(
        "missing requirements.lock root file",
        _snapshot(
            (
                ("pyproject.toml", _pyproject_bytes()),
                ("src/a.py", b"x = 1\n"),
                ("tests/test_a.py", b"def test_a():\n    assert True\n"),
            )
        ),
        frozen_reference_manifest(),
        ("ROOT_FILE_MISSING:requirements.lock",),
    ),
    _matrix_case(
        "missing src directory",
        _snapshot(
            (
                ("pyproject.toml", _pyproject_bytes()),
                ("requirements.lock", _reference_lock_bytes()),
                ("tests/test_a.py", b"def test_a():\n    assert True\n"),
            )
        ),
        frozen_reference_manifest(),
        ("SOURCE_LAYOUT_MISSING:src",),
    ),
    _matrix_case(
        "missing tests directory",
        _snapshot(
            (
                ("pyproject.toml", _pyproject_bytes()),
                ("requirements.lock", _reference_lock_bytes()),
                ("src/a.py", b"x = 1\n"),
            )
        ),
        frozen_reference_manifest(),
        ("SOURCE_LAYOUT_MISSING:tests",),
    ),
    _matrix_case(
        "requirements.lock digest mismatch",
        _snapshot(
            (
                ("pyproject.toml", _pyproject_bytes()),
                ("requirements.lock", b"--index-url https://pypi.org/simple\n"),
                ("src/a.py", b"x = 1\n"),
                ("tests/test_a.py", b"def test_a():\n    assert True\n"),
            )
        ),
        frozen_reference_manifest(),
        ("DEPENDENCY_DIGEST_MISMATCH",),
    ),
    _matrix_case(
        "pytest not configured in pyproject",
        _snapshot(
            (
                (
                    "pyproject.toml",
                    b'[project]\nname = "x"\n\n[tool.ruff]\nline-length = 88\n\n'
                    b'[tool.mypy]\npython_version = "3.12"\nstrict = true\n',
                ),
                ("requirements.lock", _reference_lock_bytes()),
                ("src/a.py", b"x = 1\n"),
                ("tests/test_a.py", b"def test_a():\n    assert True\n"),
            )
        ),
        frozen_reference_manifest(),
        ("PYTEST_NOT_CONFIGURED",),
    ),
    _matrix_case(
        "ruff not configured in pyproject",
        _snapshot(
            (
                (
                    "pyproject.toml",
                    b'[project]\nname = "x"\n\n[tool.pytest.ini_options]\n'
                    b'testpaths = ["tests"]\n\n[tool.mypy]\npython_version = "3.12"\n'
                    b"strict = true\n",
                ),
                ("requirements.lock", _reference_lock_bytes()),
                ("src/a.py", b"x = 1\n"),
                ("tests/test_a.py", b"def test_a():\n    assert True\n"),
            )
        ),
        frozen_reference_manifest(),
        ("TOOL_NOT_CONFIGURED:ruff",),
    ),
    _matrix_case(
        "mypy not configured in pyproject",
        _snapshot(
            (
                (
                    "pyproject.toml",
                    b'[project]\nname = "x"\n\n[tool.pytest.ini_options]\n'
                    b'testpaths = ["tests"]\n\n[tool.ruff]\nline-length = 88\n',
                ),
                ("requirements.lock", _reference_lock_bytes()),
                ("src/a.py", b"x = 1\n"),
                ("tests/test_a.py", b"def test_a():\n    assert True\n"),
            )
        ),
        frozen_reference_manifest(),
        ("TOOL_NOT_CONFIGURED:mypy",),
    ),
    _matrix_case(
        "invalid pyproject toml",
        _snapshot(
            (
                ("pyproject.toml", b"[project\nbroken = \n"),
                ("requirements.lock", _reference_lock_bytes()),
                ("src/a.py", b"x = 1\n"),
                ("tests/test_a.py", b"def test_a():\n    assert True\n"),
            )
        ),
        frozen_reference_manifest(),
        ("PYPROJECT_INVALID",),
    ),
    _matrix_case(
        "pytest.ini config entrypoint",
        _with_root_file("pytest.ini"),
        frozen_reference_manifest(),
        ("CONFIG_ENTRYPOINT:pytest.ini",),
    ),
    _matrix_case(
        "tox.ini config entrypoint",
        _with_root_file("tox.ini"),
        frozen_reference_manifest(),
        ("CONFIG_ENTRYPOINT:tox.ini",),
    ),
    _matrix_case(
        "setup.cfg config entrypoint",
        _with_root_file("setup.cfg"),
        frozen_reference_manifest(),
        ("CONFIG_ENTRYPOINT:setup.cfg",),
    ),
    _matrix_case(
        "mypy.ini config entrypoint",
        _with_root_file("mypy.ini"),
        frozen_reference_manifest(),
        ("CONFIG_ENTRYPOINT:mypy.ini",),
    ),
    _matrix_case(
        ".ruff.toml config entrypoint",
        _with_root_file(".ruff.toml"),
        frozen_reference_manifest(),
        ("CONFIG_ENTRYPOINT:.ruff.toml",),
    ),
    _matrix_case(
        "ruff.toml config entrypoint",
        _with_root_file("ruff.toml"),
        frozen_reference_manifest(),
        ("CONFIG_ENTRYPOINT:ruff.toml",),
    ),
    _matrix_case(
        "poetry.lock dependency entrypoint",
        _with_root_file("poetry.lock"),
        frozen_reference_manifest(),
        ("DEPENDENCY_ENTRYPOINT:poetry.lock",),
    ),
    _matrix_case(
        "uv.lock dependency entrypoint",
        _with_root_file("uv.lock"),
        frozen_reference_manifest(),
        ("DEPENDENCY_ENTRYPOINT:uv.lock",),
    ),
    _matrix_case(
        "pdm.lock dependency entrypoint",
        _with_root_file("pdm.lock"),
        frozen_reference_manifest(),
        ("DEPENDENCY_ENTRYPOINT:pdm.lock",),
    ),
    _matrix_case(
        "requirements.txt dependency entrypoint",
        _with_root_file("requirements.txt"),
        frozen_reference_manifest(),
        ("DEPENDENCY_ENTRYPOINT:requirements.txt",),
    ),
    _matrix_case(
        "requirements-dev.txt dependency entrypoint",
        _with_root_file("requirements-dev.txt"),
        frozen_reference_manifest(),
        ("DEPENDENCY_ENTRYPOINT:requirements-dev.txt",),
    ),
    _matrix_case(
        "conftest.py anywhere",
        _with_root_file("conftest.py"),
        frozen_reference_manifest(),
        ("PLUGIN_ENTRYPOINT:conftest.py",),
    ),
    _matrix_case(
        "src/conftest.py anywhere",
        _unsupported((("src/conftest.py", b"# hook\n"),)),
        frozen_reference_manifest(),
        ("PLUGIN_ENTRYPOINT:conftest.py",),
    ),
    _matrix_case(
        "sitecustomize.py anywhere",
        _with_root_file("sitecustomize.py"),
        frozen_reference_manifest(),
        ("INTERPRETER_ENTRYPOINT:sitecustomize.py",),
    ),
    _matrix_case(
        "usercustomize.py anywhere",
        _with_root_file("usercustomize.py"),
        frozen_reference_manifest(),
        ("INTERPRETER_ENTRYPOINT:usercustomize.py",),
    ),
    _matrix_case(
        "pytest plugins key",
        _snapshot(
            (
                (
                    "pyproject.toml",
                    b'[project]\nname = "x"\n\n[tool.pytest.ini_options]\n'
                    b'testpaths = ["tests"]\nplugins = ["some_plugin"]\n\n'
                    b"[tool.ruff]\nline-length = 88\n\n[tool.mypy]\n"
                    b'python_version = "3.12"\nstrict = true\n',
                ),
                ("requirements.lock", _reference_lock_bytes()),
                ("src/a.py", b"x = 1\n"),
                ("tests/test_a.py", b"def test_a():\n    assert True\n"),
            )
        ),
        frozen_reference_manifest(),
        ("PLUGIN_DECLARED",),
    ),
    _matrix_case(
        "pytest -p addopts",
        _snapshot(
            (
                (
                    "pyproject.toml",
                    b'[project]\nname = "x"\n\n[tool.pytest.ini_options]\n'
                    b'testpaths = ["tests"]\naddopts = "-p some_plugin"\n\n'
                    b"[tool.ruff]\nline-length = 88\n\n[tool.mypy]\n"
                    b'python_version = "3.12"\nstrict = true\n',
                ),
                ("requirements.lock", _reference_lock_bytes()),
                ("src/a.py", b"x = 1\n"),
                ("tests/test_a.py", b"def test_a():\n    assert True\n"),
            )
        ),
        frozen_reference_manifest(),
        ("PLUGIN_ADDOPTS",),
    ),
    _matrix_case(
        "pytest -p= addopts value spelling",
        _snapshot(
            (
                (
                    "pyproject.toml",
                    b'[project]\nname = "x"\n\n[tool.pytest.ini_options]\n'
                    b'testpaths = ["tests"]\naddopts = "-p=some_plugin"\n\n'
                    b"[tool.ruff]\nline-length = 88\n\n[tool.mypy]\n"
                    b'python_version = "3.12"\nstrict = true\n',
                ),
                ("requirements.lock", _reference_lock_bytes()),
                ("src/a.py", b"x = 1\n"),
                ("tests/test_a.py", b"def test_a():\n    assert True\n"),
            )
        ),
        frozen_reference_manifest(),
        ("PLUGIN_ADDOPTS",),
    ),
    _matrix_case(
        "pytest -m= addopts value spelling",
        _snapshot(
            (
                (
                    "pyproject.toml",
                    b'[project]\nname = "x"\n\n[tool.pytest.ini_options]\n'
                    b'testpaths = ["tests"]\naddopts = "-m=not slow"\n\n'
                    b"[tool.ruff]\nline-length = 88\n\n[tool.mypy]\n"
                    b'python_version = "3.12"\nstrict = true\n',
                ),
                ("requirements.lock", _reference_lock_bytes()),
                ("src/a.py", b"x = 1\n"),
                ("tests/test_a.py", b"def test_a():\n    assert True\n"),
            )
        ),
        frozen_reference_manifest(),
        ("MARKER_EXPRESSION_ADDOPTS",),
    ),
    _matrix_case(
        "pytest --markexpr= addopts long spelling",
        _snapshot(
            (
                (
                    "pyproject.toml",
                    b'[project]\nname = "x"\n\n[tool.pytest.ini_options]\n'
                    b'testpaths = ["tests"]\naddopts = "--markexpr=not slow"\n\n'
                    b"[tool.ruff]\nline-length = 88\n\n[tool.mypy]\n"
                    b'python_version = "3.12"\nstrict = true\n',
                ),
                ("requirements.lock", _reference_lock_bytes()),
                ("src/a.py", b"x = 1\n"),
                ("tests/test_a.py", b"def test_a():\n    assert True\n"),
            )
        ),
        frozen_reference_manifest(),
        ("MARKER_EXPRESSION_ADDOPTS",),
    ),
    _matrix_case(
        "pytest -pp concatenated plugin addopts",
        _snapshot(
            (
                (
                    "pyproject.toml",
                    b'[project]\nname = "x"\n\n[tool.pytest.ini_options]\n'
                    b'testpaths = ["tests"]\naddopts = "-pp"\n\n'
                    b"[tool.ruff]\nline-length = 88\n\n[tool.mypy]\n"
                    b'python_version = "3.12"\nstrict = true\n',
                ),
                ("requirements.lock", _reference_lock_bytes()),
                ("src/a.py", b"x = 1\n"),
                ("tests/test_a.py", b"def test_a():\n    assert True\n"),
            )
        ),
        frozen_reference_manifest(),
        ("PLUGIN_ADDOPTS",),
    ),
    _matrix_case(
        "pytest -mnot concatenated marker addopts",
        _snapshot(
            (
                (
                    "pyproject.toml",
                    b'[project]\nname = "x"\n\n[tool.pytest.ini_options]\n'
                    b'testpaths = ["tests"]\naddopts = "-mnot"\n\n'
                    b"[tool.ruff]\nline-length = 88\n\n[tool.mypy]\n"
                    b'python_version = "3.12"\nstrict = true\n',
                ),
                ("requirements.lock", _reference_lock_bytes()),
                ("src/a.py", b"x = 1\n"),
                ("tests/test_a.py", b"def test_a():\n    assert True\n"),
            )
        ),
        frozen_reference_manifest(),
        ("MARKER_EXPRESSION_ADDOPTS",),
    ),
    _matrix_case(
        "pytest -k selection addopts",
        _snapshot(
            (
                (
                    "pyproject.toml",
                    b'[project]\nname = "x"\n\n[tool.pytest.ini_options]\n'
                    b'testpaths = ["tests"]\naddopts = "-k not_slow"\n\n'
                    b"[tool.ruff]\nline-length = 88\n\n[tool.mypy]\n"
                    b'python_version = "3.12"\nstrict = true\n',
                ),
                ("requirements.lock", _reference_lock_bytes()),
                ("src/a.py", b"x = 1\n"),
                ("tests/test_a.py", b"def test_a():\n    assert True\n"),
            )
        ),
        frozen_reference_manifest(),
        ("SELECTION_ADDOPTS",),
    ),
    _matrix_case(
        "pytest --deselect selection addopts",
        _snapshot(
            (
                (
                    "pyproject.toml",
                    b'[project]\nname = "x"\n\n[tool.pytest.ini_options]\n'
                    b'testpaths = ["tests"]\naddopts = "--deselect=tests/test_a.py::test_a"\n\n'
                    b"[tool.ruff]\nline-length = 88\n\n[tool.mypy]\n"
                    b'python_version = "3.12"\nstrict = true\n',
                ),
                ("requirements.lock", _reference_lock_bytes()),
                ("src/a.py", b"x = 1\n"),
                ("tests/test_a.py", b"def test_a():\n    assert True\n"),
            )
        ),
        frozen_reference_manifest(),
        ("SELECTION_ADDOPTS",),
    ),
    _matrix_case(
        "pytest --ignore selection addopts",
        _snapshot(
            (
                (
                    "pyproject.toml",
                    b'[project]\nname = "x"\n\n[tool.pytest.ini_options]\n'
                    b'testpaths = ["tests"]\naddopts = "--ignore=tests/slow"\n\n'
                    b"[tool.ruff]\nline-length = 88\n\n[tool.mypy]\n"
                    b'python_version = "3.12"\nstrict = true\n',
                ),
                ("requirements.lock", _reference_lock_bytes()),
                ("src/a.py", b"x = 1\n"),
                ("tests/test_a.py", b"def test_a():\n    assert True\n"),
            )
        ),
        frozen_reference_manifest(),
        ("SELECTION_ADDOPTS",),
    ),
    _matrix_case(
        "pytest required_plugins key",
        _snapshot(
            (
                (
                    "pyproject.toml",
                    b'[project]\nname = "x"\n\n[tool.pytest.ini_options]\n'
                    b'testpaths = ["tests"]\nrequired_plugins = ["some_plugin"]\n\n'
                    b"[tool.ruff]\nline-length = 88\n\n[tool.mypy]\n"
                    b'python_version = "3.12"\nstrict = true\n',
                ),
                ("requirements.lock", _reference_lock_bytes()),
                ("src/a.py", b"x = 1\n"),
                ("tests/test_a.py", b"def test_a():\n    assert True\n"),
            )
        ),
        frozen_reference_manifest(),
        ("PLUGIN_DECLARED",),
    ),
    _matrix_case(
        "pytest -m marker-expression addopts",
        _snapshot(
            (
                (
                    "pyproject.toml",
                    b'[project]\nname = "x"\n\n[tool.pytest.ini_options]\n'
                    b'testpaths = ["tests"]\naddopts = "-m \'not slow\'"\n\n'
                    b"[tool.ruff]\nline-length = 88\n\n[tool.mypy]\n"
                    b'python_version = "3.12"\nstrict = true\n',
                ),
                ("requirements.lock", _reference_lock_bytes()),
                ("src/a.py", b"x = 1\n"),
                ("tests/test_a.py", b"def test_a():\n    assert True\n"),
            )
        ),
        frozen_reference_manifest(),
        ("MARKER_EXPRESSION_ADDOPTS",),
    ),
    _matrix_case(
        "custom markers registration is supported",
        _snapshot(
            (
                (
                    "pyproject.toml",
                    b'[project]\nname = "x"\n\n[tool.pytest.ini_options]\n'
                    b'testpaths = ["tests"]\nmarkers = ["slow: marks slow tests"]\n\n'
                    b"[tool.ruff]\nline-length = 88\n\n[tool.mypy]\n"
                    b'python_version = "3.12"\nstrict = true\n',
                ),
                ("requirements.lock", _reference_lock_bytes()),
                ("src/a.py", b"x = 1\n"),
                ("tests/test_a.py", b"def test_a():\n    assert True\n"),
            )
        ),
        frozen_reference_manifest(),
        (),
    ),
    _matrix_case(
        "editable file is not supported text",
        _with_editable_non_text(),
        frozen_reference_manifest(),
        ("EDITABLE_FILE_NOT_TEXT:src/binary.dat",),
    ),
    _matrix_case(
        "snapshot policy binding mismatch",
        _tampered_policy_snapshot(),
        frozen_reference_manifest(),
        ("POLICY_BINDING_MISMATCH",),
    ),
    _matrix_case(
        "manifest digest binding mismatch",
        _snapshot(_supported_files()),
        _tampered_manifest(),
        ("MANIFEST_IDENTITY_MISMATCH", "MANIFEST_DIGEST_MISMATCH"),
    ),
)


def test_static_unsupported_result_performs_no_execution(
    adapter: PythonProjectAdapterV1,
    executor: SpyExecutor,
) -> None:
    result = adapter.detect_static(unsupported_snapshot(), frozen_reference_manifest())
    assert result.kind == "UNSUPPORTED"
    assert executor.call_count == 0


def _assert_verbatim_bindings(
    result: SupportedProjectV1 | UnsupportedProjectV1,
    snapshot: SnapshotTreeV1,
    manifest: ReferenceProfileManifestV1,
) -> None:
    assert result.reference_profile_digest == manifest.digest
    assert result.snapshot_root_digest == snapshot.root_digest
    assert result.repository_policy_digest == snapshot.repository_policy_digest


def test_detect_static_supported_binds_verbatim_and_is_deterministic(
    adapter: PythonProjectAdapterV1,
    executor: SpyExecutor,
) -> None:
    snapshot = _snapshot(_supported_files())
    manifest = frozen_reference_manifest()
    first = adapter.detect_static(snapshot, manifest)
    second = adapter.detect_static(snapshot, manifest)
    assert isinstance(first, SupportedProjectV1)
    assert first.kind == "SUPPORTED"
    assert first.profile_id == manifest.profile_id
    _assert_verbatim_bindings(first, snapshot, manifest)
    assert second == first
    assert executor.call_count == 0


@pytest.mark.parametrize(
    ("label", "snapshot", "manifest", "expected_reasons"),
    _MATRIX_CASES,
    ids=[case[0] for case in _MATRIX_CASES],
)
def test_check_plan_classification_matrix(
    label: str,
    snapshot: SnapshotTreeV1,
    manifest: ReferenceProfileManifestV1,
    expected_reasons: tuple[str, ...],
    adapter: PythonProjectAdapterV1,
    executor: SpyExecutor,
) -> None:
    """Registry 20.A: each supported reference input maps to the one closed
    plan; unsupported marker/config/plugin/collector/path/tool state
    returns UNSUPPORTED without execution; classification is
    deterministic."""
    first = adapter.detect_static(snapshot, manifest)
    second = adapter.detect_static(snapshot, manifest)
    assert second == first
    assert executor.call_count == 0
    if expected_reasons == ():
        assert isinstance(first, SupportedProjectV1)
        assert first.kind == "SUPPORTED"
        _assert_verbatim_bindings(first, snapshot, manifest)
        plan = adapter.build_baseline_plan(
            first, _target_ids(_TARGET_ADD, _TARGET_MULTIPLY)
        )
        _assert_exact_baseline_plan(
            plan, first, manifest, _TARGET_ADD, _TARGET_MULTIPLY
        )
    else:
        assert isinstance(first, UnsupportedProjectV1)
        assert first.kind == "UNSUPPORTED"
        assert first.reasons == expected_reasons
        _assert_verbatim_bindings(first, snapshot, manifest)


def _target_ids(*node_ids: str) -> TargetTestIdSequenceV1:
    return TargetTestIdSequenceV1(target_test_ids=tuple(node_ids))


def _assert_exact_baseline_plan(
    plan: BaselineCheckPlanV1,
    profile: SupportedProjectV1,
    manifest: ReferenceProfileManifestV1,
    *node_ids: str,
) -> None:
    """Every exact identity, argv vector, ordering, and target binding of
    the one closed Baseline plan (SPEC §4.5 fixed order)."""
    assert [entry.check_id for entry in plan.entries] == [
        "COLLECT_ONLY",
        "COLLECT_ONLY",
        "FULL_PYTEST",
        "TARGET_TESTS",
        "RUFF",
        "MYPY",
    ]
    base = (
        "python",
        "-m",
        "pytest",
        "-p",
        "vespercode.validation.pytest_reporter",
        "-o",
        "cacheprovider=disabled",
        "--rootdir",
        "/workspace",
    )
    assert plan.entries[0].argv.arguments == (*base, "--collect-only", "/workspace")
    assert plan.entries[1].argv.arguments == (*base, "--collect-only", "/workspace")
    assert plan.entries[2].argv.arguments == (*base, "/workspace")
    assert plan.entries[3].argv.arguments == (*base, *node_ids)
    assert plan.entries[4].argv.arguments == ("ruff", "check", "--no-cache", "/workspace")
    assert plan.entries[5].argv.arguments == (
        "mypy",
        "--no-incremental",
        "--cache-dir",
        "/tmp/mypy-cache",
        "--config-file",
        "/workspace/pyproject.toml",
        "/workspace/src",
    )
    assert plan.entries[3].target_test_ids.kind == "PRESENT"
    assert plan.entries[3].target_test_ids.value == _target_ids(*node_ids)
    for entry in (*plan.entries[:3], *plan.entries[4:]):
        assert entry.target_test_ids.kind == "ABSENT"
    assert plan.reference_profile_digest == manifest.digest
    assert plan.snapshot_root_digest == profile.snapshot_root_digest
    assert plan.repository_policy_digest == profile.repository_policy_digest
    assert plan.check_plan_version == manifest.check_plan_version
    assert plan.adapter_version == "1"
    assert plan.python_version == manifest.python_version
    assert plan.pytest_version == manifest.pytest_version
    assert plan.report_plugin_version == manifest.report_plugin_version
    assert plan.ruff_version == manifest.ruff_version
    assert plan.mypy_version == manifest.mypy_version
    assert plan.docker_image_digest == manifest.docker_image_digest
    assert plan.docker_execution_profile_version == 1
    assert plan.target_test_ids == _target_ids(*node_ids)


def test_baseline_plan_identity_is_closed_and_order_sensitive(
    adapter: PythonProjectAdapterV1,
) -> None:
    profile = _supported_profile(adapter)
    first = adapter.build_baseline_plan(
        profile, _target_ids(_TARGET_ADD, _TARGET_MULTIPLY)
    )
    second = adapter.build_baseline_plan(
        profile, _target_ids(_TARGET_ADD, _TARGET_MULTIPLY)
    )
    assert first.digest == second.digest
    reordered = adapter.build_baseline_plan(
        profile, _target_ids(_TARGET_MULTIPLY, _TARGET_ADD)
    )
    assert reordered.digest != first.digest
    other_targets = adapter.build_baseline_plan(profile, _target_ids(_TARGET_ADD))
    assert other_targets.digest != first.digest


def _supported_profile(adapter: PythonProjectAdapterV1) -> SupportedProjectV1:
    result = adapter.detect_static(
        _snapshot(_supported_files()), frozen_reference_manifest()
    )
    assert isinstance(result, SupportedProjectV1)
    return result


def test_build_baseline_plan_rejects_profile_binding_mismatch(
    adapter: PythonProjectAdapterV1,
) -> None:
    foreign = SupportedProjectV1(
        kind="SUPPORTED",
        profile_id="python-src-py312-v1",
        reference_profile_digest="d" * 64,
        snapshot_root_digest="e" * 64,
        repository_policy_digest="f" * 64,
    )
    with pytest.raises(CheckPlanError, match="PROFILE_BINDING_MISMATCH"):
        adapter.build_baseline_plan(foreign, _target_ids(_TARGET_ADD))


def test_build_baseline_plan_rejects_unsupported_profile_closed(
    adapter: PythonProjectAdapterV1,
) -> None:
    """The kind gate fails closed even when a non-SUPPORTED object is
    smuggled through the declared parameter type."""
    unsupported = cast(
        SupportedProjectV1,
        UnsupportedProjectV1(
            kind="UNSUPPORTED",
            reference_profile_digest="d" * 64,
            snapshot_root_digest="e" * 64,
            repository_policy_digest="f" * 64,
            reasons=("ROOT_FILE_MISSING:pyproject.toml",),
        ),
    )
    with pytest.raises(CheckPlanError, match="PROFILE_NOT_SUPPORTED"):
        adapter.build_baseline_plan(unsupported, _target_ids(_TARGET_ADD))


def test_build_formal_plan_freezes_exact_frozen_plan(
    adapter: PythonProjectAdapterV1,
) -> None:
    profile = _supported_profile(adapter)
    baseline = adapter.build_baseline_plan(
        profile, _target_ids(_TARGET_ADD, _TARGET_MULTIPLY)
    )
    manifest = _manifest_stub(adapter, baseline)
    candidate = _candidate_stub(baseline)
    plan = adapter.build_formal_plan(manifest, candidate)
    assert [entry.check_id for entry in plan.entries] == [
        "COLLECT_ONLY",
        "FULL_PYTEST",
        "RUFF",
        "MYPY",
    ]
    base = (
        "python",
        "-m",
        "pytest",
        "-p",
        "vespercode.validation.pytest_reporter",
        "-o",
        "cacheprovider=disabled",
        "--rootdir",
        "/workspace",
    )
    assert plan.entries[0].argv.arguments == (*base, "--collect-only", "/workspace")
    assert plan.entries[1].argv.arguments == (*base, "/workspace")
    assert plan.entries[2].argv.arguments == ("ruff", "check", "--no-cache", "/workspace")
    assert plan.entries[3].argv.arguments == (
        "mypy",
        "--no-incremental",
        "--cache-dir",
        "/tmp/mypy-cache",
        "--config-file",
        "/workspace/pyproject.toml",
        "/workspace/src",
    )
    assert plan.manifest_digest == manifest.digest
    assert plan.candidate_digest == candidate.digest
    assert plan.candidate_tree_digest == candidate.candidate_tree_digest
    assert plan.final_diff_digest == candidate.final_diff_digest
    assert plan.snapshot_tree_digest == manifest.snapshot_tree_digest
    assert plan.reference_profile_digest == manifest.reference_profile_digest
    assert plan.repository_policy_digest == manifest.repository_policy_digest
    assert plan.target_test_ids == _target_ids(_TARGET_ADD, _TARGET_MULTIPLY)
    repeated = adapter.build_formal_plan(manifest, candidate)
    assert repeated.digest == plan.digest


class _ManifestStub:
    """Structural stand-in for the T20.2 closed ``ValidationManifestV1``
    (the adapter's ``ValidationManifestV1`` consumption Protocol)."""

    def __init__(
        self,
        *,
        reference_profile_digest: str,
        snapshot_tree_digest: str,
        repository_policy_digest: str,
        target_test_ids: tuple[str, ...],
        digest: str,
        check_plan_version: str = "1",
        adapter_version: str = "1",
        python_version: str = "3.12.4",
        pytest_version: str = "8.4.2",
        report_plugin_version: str = "1",
        ruff_version: str = "0.16.1",
        mypy_version: str = "2.3.0",
        docker_image_digest: str = (
            "86443f5297b268f0cd8046b09652acb3b6b1d7e4275a743c34e7908bf1d7156d"
        ),
        docker_execution_profile_version: int = 1,
    ) -> None:
        self.schema_version = 1
        self.check_plan_version = check_plan_version
        self.adapter_version = adapter_version
        self.python_version = python_version
        self.pytest_version = pytest_version
        self.report_plugin_version = report_plugin_version
        self.ruff_version = ruff_version
        self.mypy_version = mypy_version
        self.docker_image_digest = docker_image_digest
        self.docker_execution_profile_version = docker_execution_profile_version
        self.reference_profile_digest = reference_profile_digest
        self.snapshot_tree_digest = snapshot_tree_digest
        self.repository_policy_digest = repository_policy_digest
        self.target_test_ids = target_test_ids
        self.digest = digest


def _manifest_stub(
    adapter: PythonProjectAdapterV1, baseline: BaselineCheckPlanV1
) -> _ManifestStub:
    return _ManifestStub(
        reference_profile_digest=baseline.reference_profile_digest,
        snapshot_tree_digest=baseline.snapshot_root_digest,
        repository_policy_digest=baseline.repository_policy_digest,
        target_test_ids=baseline.target_test_ids.target_test_ids,
        digest="a" * 64,
    )


class _CandidateStub:
    """Structural stand-in for the T12.1 ``CandidateIdentityV1``."""

    def __init__(
        self,
        *,
        snapshot_tree_digest: str,
        candidate_tree_digest: str,
        final_diff_digest: str,
        digest: str,
    ) -> None:
        self.schema_version = 1
        self.snapshot_tree_digest = snapshot_tree_digest
        self.candidate_tree_digest = candidate_tree_digest
        self.final_diff_digest = final_diff_digest
        self.digest = digest


def _candidate_stub(baseline: BaselineCheckPlanV1) -> _CandidateStub:
    return _CandidateStub(
        snapshot_tree_digest=baseline.snapshot_root_digest,
        candidate_tree_digest="b" * 64,
        final_diff_digest="c" * 64,
        digest="d" * 64,
    )


def test_build_formal_plan_rejects_snapshot_identity_mismatch(
    adapter: PythonProjectAdapterV1,
) -> None:
    profile = _supported_profile(adapter)
    baseline = adapter.build_baseline_plan(
        profile, _target_ids(_TARGET_ADD, _TARGET_MULTIPLY)
    )
    manifest = _manifest_stub(adapter, baseline)
    candidate = _candidate_stub(baseline)
    drifted = _CandidateStub(
        snapshot_tree_digest="e" * 64,
        candidate_tree_digest=candidate.candidate_tree_digest,
        final_diff_digest=candidate.final_diff_digest,
        digest=candidate.digest,
    )
    with pytest.raises(CheckPlanError, match="SNAPSHOT_IDENTITY_MISMATCH"):
        adapter.build_formal_plan(manifest, drifted)


def test_build_formal_plan_rejects_profile_binding_mismatch(
    adapter: PythonProjectAdapterV1,
) -> None:
    profile = _supported_profile(adapter)
    baseline = adapter.build_baseline_plan(
        profile, _target_ids(_TARGET_ADD, _TARGET_MULTIPLY)
    )
    manifest = _manifest_stub(adapter, baseline)
    candidate = _candidate_stub(baseline)
    foreign = _ManifestStub(
        reference_profile_digest="9" * 64,
        snapshot_tree_digest=manifest.snapshot_tree_digest,
        repository_policy_digest=manifest.repository_policy_digest,
        target_test_ids=manifest.target_test_ids,
        digest=manifest.digest,
    )
    with pytest.raises(CheckPlanError, match="PROFILE_BINDING_MISMATCH"):
        adapter.build_formal_plan(foreign, candidate)


def test_build_formal_plan_rejects_profile_field_mismatch(
    adapter: PythonProjectAdapterV1,
) -> None:
    profile = _supported_profile(adapter)
    baseline = adapter.build_baseline_plan(
        profile, _target_ids(_TARGET_ADD, _TARGET_MULTIPLY)
    )
    manifest = _manifest_stub(adapter, baseline)
    candidate = _candidate_stub(baseline)
    drifted = _ManifestStub(
        reference_profile_digest=manifest.reference_profile_digest,
        snapshot_tree_digest=manifest.snapshot_tree_digest,
        repository_policy_digest=manifest.repository_policy_digest,
        target_test_ids=manifest.target_test_ids,
        digest=manifest.digest,
        pytest_version="9.9.9",
    )
    with pytest.raises(CheckPlanError, match="PROFILE_FIELD_MISMATCH"):
        adapter.build_formal_plan(drifted, candidate)


def test_build_formal_plan_rejects_malformed_binding_digest(
    adapter: PythonProjectAdapterV1,
) -> None:
    profile = _supported_profile(adapter)
    baseline = adapter.build_baseline_plan(
        profile, _target_ids(_TARGET_ADD, _TARGET_MULTIPLY)
    )
    manifest = _manifest_stub(adapter, baseline)
    candidate = _candidate_stub(baseline)
    malformed = _ManifestStub(
        reference_profile_digest=manifest.reference_profile_digest,
        snapshot_tree_digest="not-a-digest",
        repository_policy_digest=manifest.repository_policy_digest,
        target_test_ids=manifest.target_test_ids,
        digest=manifest.digest,
    )
    with pytest.raises(CheckPlanError, match="BINDING_DIGEST_MALFORMED"):
        adapter.build_formal_plan(malformed, candidate)


@pytest.mark.parametrize(
    "invalid_ids",
    [
        (),
        ("",),
        ("x" * 1025,),
        tuple(f"t{i}" for i in range(21)),
        (_TARGET_ADD, _TARGET_ADD),
    ],
    ids=["empty", "empty-id", "oversized-id", "too-many", "duplicate"],
)
def test_build_formal_plan_rejects_invalid_target_ids_closed(
    adapter: PythonProjectAdapterV1,
    invalid_ids: tuple[str, ...],
) -> None:
    profile = _supported_profile(adapter)
    baseline = adapter.build_baseline_plan(
        profile, _target_ids(_TARGET_ADD, _TARGET_MULTIPLY)
    )
    manifest = _manifest_stub(adapter, baseline)
    candidate = _candidate_stub(baseline)
    invalid = _ManifestStub(
        reference_profile_digest=manifest.reference_profile_digest,
        snapshot_tree_digest=manifest.snapshot_tree_digest,
        repository_policy_digest=manifest.repository_policy_digest,
        target_test_ids=invalid_ids,
        digest=manifest.digest,
    )
    with pytest.raises(CheckPlanError, match="TARGET_IDS_INVALID"):
        adapter.build_formal_plan(invalid, candidate)


def test_detect_static_rejects_wrong_manifest_identity_closed(
    adapter: PythonProjectAdapterV1,
) -> None:
    # A manifest object whose digest is valid but not the frozen built-in.
    foreign = frozen_reference_manifest().model_copy(update={"digest": "e" * 64})
    result = adapter.detect_static(_snapshot(_supported_files()), foreign)
    assert isinstance(result, UnsupportedProjectV1)
    assert "MANIFEST_IDENTITY_MISMATCH" in result.reasons
    assert "MANIFEST_DIGEST_MISMATCH" in result.reasons


def test_result_schemas_are_closed() -> None:
    with pytest.raises(ValidationError):
        SupportedProjectV1(
            kind="SUPPORTED",
            profile_id="python-src-py312-v1",
            reference_profile_digest="short",
            snapshot_root_digest="e" * 64,
            repository_policy_digest="f" * 64,
        )
    with pytest.raises(ValidationError):
        UnsupportedProjectV1(
            kind="UNSUPPORTED",
            reference_profile_digest="d" * 64,
            snapshot_root_digest="e" * 64,
            repository_policy_digest="f" * 64,
            reasons=(),
        )
    with pytest.raises(ValidationError):
        TargetTestIdSequenceV1(target_test_ids=())
    with pytest.raises(ValidationError):
        TargetTestIdSequenceV1(target_test_ids=(_TARGET_ADD, _TARGET_ADD))
    with pytest.raises(ValidationError):
        TargetTestIdSequenceV1(target_test_ids=tuple(f"t{i}" for i in range(21)))

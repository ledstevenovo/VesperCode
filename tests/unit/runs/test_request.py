"""T08.1 legacy step 8.A: strict run-request admission and frozen config tests.

The exact RED test pins zero-insert rejection of a custom ``base_url``;
the matrix pins the PLAN Registry 8.A row — all valid field-order
permutations canonicalize identically while custom URLs, widened policy,
unknown profiles, malformed limits, duplicates, and extra fields are
rejected before any Run exists.  Workspace lease, Snapshot, readiness,
and PREFLIGHT execution remain out of scope (GREEN-4).
"""

from __future__ import annotations

import itertools
from collections.abc import Iterator
from pathlib import Path
from typing import cast

import pytest

# The run-request contract consumes pydantic runtime contracts; the
# hash-locked gate toolchain installs no runtime dependencies, so this
# module skips cleanly there (formal env runs it fully).
pytest.importorskip("pydantic")

# mypy: disable-error-code="union-attr"
# The card's exact RED test reads ``result.kind`` on the closed
# ``RunCreatedV1 | ConfigInvalidV1`` union without narrowing (the display
# is copied verbatim); the module-level disable documents that card-exact
# test per the T30.1 precedent.

import src.vespercode.runs.request as request_module
from src.vespercode.canonical.clock import FakeClockV1
from src.vespercode.profiles.registry import build_profile_registry
from src.vespercode.runs.request import (
    ConfigInvalidV1,
    RunCreatedV1,
    RunRequestService,
    ValidatedRunRequestV1,
    create_run,
    freeze_run_config,
    validate_request,
)
from src.vespercode.storage.connection import ControlDatabase, open_control_database
from src.vespercode.storage.migration_engine import apply_migrations
from src.vespercode.storage.migrations.v0001_run_wait import RUN_WAIT_V1_MIGRATION
from src.vespercode.storage.run_repository import RunRepository

# The deterministic clock instant used for stable frozen_at values.
_DETERMINISTIC_NOW = 1_784_885_415_123


def valid_request_dict() -> dict[str, object]:
    """One fully valid closed v1 request (every field explicit, no defaults)."""
    return {
        "schema_version": 1,
        "workspace_path": r"C:\workspace\vesper-demo",
        "target_test_ids": [
            "tests/test_demo.py::test_success",
            "tests/test_demo.py::test_failure",
        ],
        "llm_profile_id": "mock-deterministic-v1",
        "reference_profile_id": "python-src-py312-v1",
        "limits": {
            "max_turns": 20,
            "max_llm_calls": 20,
            "max_run_wall_clock_seconds": 900,
            "user_wait_timeout_seconds": 300,
            "tool_timeout_seconds": 60,
            "target_check_timeout_seconds": 120,
            "full_check_timeout_seconds": 300,
            "baseline_timeout_seconds": 600,
            "formal_validation_timeout_seconds": 600,
        },
    }


class SpyRunRepository(RunRepository):
    """The real repository plus an INSERT-statement counter.

    The count covers every persistence insert flowing through the
    repository's database (the frozen snapshot row and the run row of one
    atomic CREATED insert), so zero-side-effect rejection is measurable
    at the statement level.
    """

    def __init__(self, repository: RunRepository) -> None:
        super().__init__(repository.database)
        self.insert_count = 0
        repository.database.set_trace_callback(self._trace)

    def _trace(self, statement: str) -> None:
        if statement.lstrip().upper().startswith("INSERT"):
            self.insert_count += 1


@pytest.fixture
def control_database(tmp_path: Path) -> Iterator[ControlDatabase]:
    database = open_control_database(tmp_path / "request.db")
    apply_migrations(database, (RUN_WAIT_V1_MIGRATION,))
    yield database
    database.close()


@pytest.fixture
def run_repository(control_database: ControlDatabase) -> SpyRunRepository:
    return SpyRunRepository(RunRepository(control_database))


@pytest.fixture
def request_service(
    run_repository: SpyRunRepository, monkeypatch: pytest.MonkeyPatch
) -> RunRequestService:
    """One service over the built-in registry with a deterministic clock
    and run-id factory (SPEC §5.4 test-mode injection)."""
    fake = FakeClockV1.from_epoch_milliseconds(_DETERMINISTIC_NOW)
    monkeypatch.setattr(request_module, "_now", fake.now)
    counter = itertools.count(1)
    monkeypatch.setattr(request_module, "_new_run_id", lambda: f"run-{next(counter)}")
    return RunRequestService(build_profile_registry(), run_repository)


def test_custom_base_url_is_rejected_without_creating_a_run(
    request_service: RunRequestService,
    run_repository: SpyRunRepository,
) -> None:
    result = request_service.validate_and_create(
        valid_request_dict() | {"base_url": "https://attacker.example"}
    )
    assert result.kind == "CONFIG_INVALID"
    assert run_repository.insert_count == 0


def test_request_permutation_matrix(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """PLAN Registry 8.A row: all valid field-order permutations
    canonicalize identically; custom URL, widened policy, unknown profile,
    malformed limits, or extra fields are rejected before Run creation."""
    profiles = build_profile_registry()
    base = valid_request_dict()
    limits: dict[str, object] = cast(dict[str, object], base["limits"])
    targets: list[str] = cast(list[str], base["target_test_ids"])
    fake = FakeClockV1.from_epoch_milliseconds(_DETERMINISTIC_NOW)
    monkeypatch.setattr(request_module, "_now", fake.now)
    counter = itertools.count(1)
    monkeypatch.setattr(request_module, "_new_run_id", lambda: f"run-{next(counter)}")
    permutations: tuple[dict[str, object], ...] = (
        dict(base),
        {key: value for key, value in reversed(list(base.items()))},
        {
            **{key: value for key, value in base.items() if key != "target_test_ids"},
            "target_test_ids": list(reversed(targets)),
        },
        {
            **{key: value for key, value in base.items() if key != "limits"},
            "limits": {key: value for key, value in reversed(list(limits.items()))},
        },
    )
    digests: list[str] = []
    for index, raw in enumerate(permutations):
        validated = validate_request(raw, profiles)
        assert isinstance(validated, ValidatedRunRequestV1)
        assert validated.target_test_ids == (
            "tests/test_demo.py::test_failure",
            "tests/test_demo.py::test_success",
        )
        snapshot = freeze_run_config(validated)
        digests.append(snapshot.digest)
        assert snapshot.config_snapshot_id == f"snap-{snapshot.digest}"
        database = open_control_database(tmp_path / f"perm-{index}.db")
        apply_migrations(database, (RUN_WAIT_V1_MIGRATION,))
        spy = SpyRunRepository(RunRepository(database))
        created = RunRequestService(profiles, spy).validate_and_create(raw)
        assert isinstance(created, RunCreatedV1)
        assert created.status == "CREATED"
        assert created.config_snapshot_id == snapshot.config_snapshot_id
        rows = database.read_rows(
            "SELECT run_id, status, phase FROM runs WHERE run_id = ?",
            (created.run_id,),
        )
        assert len(rows) == 1
        assert rows[0][1] == "CREATED"
        assert rows[0][2] is None
        assert len(database.read_rows("SELECT 1 FROM run_config_snapshots")) == 1
        database.close()
    assert len(set(digests)) == 1

    rejections: tuple[tuple[dict[str, object], str], ...] = (
        (base | {"base_url": "https://attacker.example"}, "UNKNOWN_FIELD"),
        (base | {"openai_base_url": "https://attacker.example"}, "UNKNOWN_FIELD"),
        (base | {"endpoint_id": "CUSTOM_ENDPOINT_V1"}, "UNKNOWN_FIELD"),
        (base | {"editable_directory_roots": ["."]}, "UNKNOWN_FIELD"),
        (base | {"allowed_operations": ["DELETE"]}, "UNKNOWN_FIELD"),
        (base | {"policy_id": "CUSTOM_POLICY_V1"}, "UNKNOWN_FIELD"),
        (base | {"policy_digest": "a" * 64}, "UNKNOWN_FIELD"),
        (base | {"llm_profile_id": "unknown-llm-v1"}, "UNKNOWN_LLM_PROFILE"),
        (
            base | {"reference_profile_id": "unknown-ref-v1"},
            "UNKNOWN_REFERENCE_PROFILE",
        ),
        (base | {"limits": {**limits, "max_turns": 21}}, "LIMITS_INVALID"),
        (
            base | {"limits": {**limits, "max_run_wall_clock_seconds": 901}},
            "LIMITS_INVALID",
        ),
        (base | {"limits": {**limits, "max_turns": "20"}}, "LIMITS_INVALID"),
        (
            base
            | {
                "limits": {
                    key: value for key, value in limits.items() if key != "max_turns"
                }
            },
            "LIMITS_INVALID",
        ),
        (base | {"limits": None}, "LIMITS_INVALID"),
        (
            base | {"target_test_ids": targets + [targets[0]]},
            "DUPLICATE_TARGET_ID",
        ),
        (base | {"target_test_ids": []}, "TARGET_SET_INVALID"),
        (base | {"target_test_ids": [""]}, "TARGET_SET_INVALID"),
        (base | {"target_test_ids": ["t" * 1025]}, "TARGET_SET_INVALID"),
        (
            base
            | {
                "target_test_ids": [
                    f"tests/test_case_{i}.py::test_case_{i}" for i in range(21)
                ]
            },
            "TARGET_SET_INVALID",
        ),
        (base | {"target_test_ids": [1]}, "TARGET_SET_INVALID"),
        (base | {"schema_version": 2}, "REQUEST_SCHEMA_INVALID"),
        (base | {"schema_version": "1"}, "REQUEST_SCHEMA_INVALID"),
        (
            {key: value for key, value in base.items() if key != "workspace_path"},
            "REQUEST_SCHEMA_INVALID",
        ),
    )
    for index, (raw, expected_reason) in enumerate(rejections):
        database = open_control_database(tmp_path / f"reject-{index}.db")
        apply_migrations(database, (RUN_WAIT_V1_MIGRATION,))
        spy = SpyRunRepository(RunRepository(database))
        result = RunRequestService(profiles, spy).validate_and_create(raw)
        assert isinstance(result, ConfigInvalidV1)
        assert result.kind == "CONFIG_INVALID"
        assert result.reason == expected_reason
        assert result.message
        assert result.suggestion
        assert spy.insert_count == 0
        assert database.read_rows("SELECT COUNT(*) FROM runs")[0][0] == 0
        assert (
            database.read_rows("SELECT COUNT(*) FROM run_config_snapshots")[0][0] == 0
        )
        database.close()


def test_target_set_boundaries_are_valid() -> None:
    """Exactly 1 target, exactly 20 targets, and the exact 1024-byte
    target id are all valid (SPEC §4.1 behavior 1)."""
    profiles = build_profile_registry()
    base = valid_request_dict()
    one = validate_request(
        base | {"target_test_ids": ["tests/test_one.py::test_one"]}, profiles
    )
    assert isinstance(one, ValidatedRunRequestV1)
    assert one.target_test_ids == ("tests/test_one.py::test_one",)
    twenty = validate_request(
        base
        | {
            "target_test_ids": [
                f"tests/test_case_{i}.py::test_case_{i}" for i in range(20)
            ]
        },
        profiles,
    )
    assert isinstance(twenty, ValidatedRunRequestV1)
    assert len(twenty.target_test_ids) == 20
    exactly_1024 = validate_request(base | {"target_test_ids": ["a" * 1024]}, profiles)
    assert isinstance(exactly_1024, ValidatedRunRequestV1)


def test_valid_request_creates_exactly_one_created_run(
    request_service: RunRequestService,
    run_repository: SpyRunRepository,
) -> None:
    result = request_service.validate_and_create(valid_request_dict())
    assert isinstance(result, RunCreatedV1)
    assert result.status == "CREATED"
    assert result.run_id == "run-1"
    rows = run_repository.database.read_rows(
        "SELECT run_id, status, phase, config_snapshot_id FROM runs"
    )
    assert len(rows) == 1
    assert rows[0][0] == "run-1"
    assert rows[0][1] == "CREATED"
    assert rows[0][2] is None
    assert rows[0][3] == result.config_snapshot_id
    assert (
        len(run_repository.database.read_rows("SELECT 1 FROM run_config_snapshots"))
        == 1
    )
    # The snapshot row and the run row form one atomic two-statement insert.
    assert run_repository.insert_count == 2


def test_identical_requests_share_one_frozen_config_and_create_two_runs(
    request_service: RunRequestService,
    run_repository: SpyRunRepository,
) -> None:
    first = request_service.validate_and_create(valid_request_dict())
    second = request_service.validate_and_create(valid_request_dict())
    assert isinstance(first, RunCreatedV1)
    assert isinstance(second, RunCreatedV1)
    assert first.run_id != second.run_id
    assert first.config_snapshot_id == second.config_snapshot_id
    assert len(run_repository.database.read_rows("SELECT 1 FROM runs")) == 2
    assert (
        len(run_repository.database.read_rows("SELECT 1 FROM run_config_snapshots"))
        == 1
    )


def test_validated_request_binds_the_exact_profile_identities() -> None:
    profiles = build_profile_registry()
    validated = validate_request(valid_request_dict(), profiles)
    assert isinstance(validated, ValidatedRunRequestV1)
    assert (
        validated.llm_profile_digest
        == profiles.resolve_llm("mock-deterministic-v1").digest
    )
    assert (
        validated.reference_profile_digest
        == profiles.resolve_reference("python-src-py312-v1").digest
    )
    assert validated.policy_id == "PYTHON_SRC_ONLY_V1"


def test_openai_profile_request_resolves_the_trusted_endpoint() -> None:
    profiles = build_profile_registry()
    raw = valid_request_dict() | {"llm_profile_id": "openai-single-turn-v1"}
    validated = validate_request(raw, profiles)
    assert isinstance(validated, ValidatedRunRequestV1)
    assert (
        validated.llm_profile_digest
        == profiles.resolve_llm("openai-single-turn-v1").digest
    )


def test_config_digest_ignores_freeze_time(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    profiles = build_profile_registry()
    validated = validate_request(valid_request_dict(), profiles)
    assert isinstance(validated, ValidatedRunRequestV1)
    monkeypatch.setattr(
        request_module, "_now", FakeClockV1.from_epoch_milliseconds(1).now
    )
    first = freeze_run_config(validated)
    monkeypatch.setattr(
        request_module,
        "_now",
        FakeClockV1.from_epoch_milliseconds(86_400_000_000).now,
    )
    second = freeze_run_config(validated)
    assert first.digest == second.digest
    assert first.config_snapshot_id == second.config_snapshot_id
    assert first.frozen_at.value != second.frozen_at.value


def test_create_run_creates_exactly_one_created_run(
    run_repository: SpyRunRepository, monkeypatch: pytest.MonkeyPatch
) -> None:
    profiles = build_profile_registry()
    validated = validate_request(valid_request_dict(), profiles)
    assert isinstance(validated, ValidatedRunRequestV1)
    fake = FakeClockV1.from_epoch_milliseconds(_DETERMINISTIC_NOW)
    monkeypatch.setattr(request_module, "_now", fake.now)
    monkeypatch.setattr(request_module, "_new_run_id", lambda: "run-direct")
    created = create_run(validated, run_repository)
    assert created.run_id == "run-direct"
    assert created.status == "CREATED"
    assert created.config_snapshot_id == freeze_run_config(validated).config_snapshot_id
    rows = run_repository.database.read_rows("SELECT run_id, status, phase FROM runs")
    assert len(rows) == 1
    assert rows[0][0] == "run-direct"
    assert rows[0][1] == "CREATED"
    assert rows[0][2] is None

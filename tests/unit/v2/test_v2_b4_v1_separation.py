"""Route B / B4 (B4a + B4b-01 + B4b-02A): v1 Docker/profile/validation
authority stays out of the v2 execution plane.

The v1 execution modules (``execution/docker_profile.py``,
``execution/docker_executor.py``, ``execution/materialization.py``,
``execution/cleanup.py``) and the whole v1 validation authority are
digest-bound, pydantic-gated legacy; the v1 reference profile manifest
(``profiles/reference.py``) re-verifies gate digests at construction.
They remain in the repository as read-only legacy, but no v2 execution
decision may flow through them.

This guard pins that boundary statically and at runtime: the Route B
execution-plane modules must not import any v1 authority module, must
not import ``hashlib`` (no v2 digest identity), must stay
standard-library plus v2-only (no pydantic, no Docker SDK, no web
framework), must not open sockets, and must not spawn processes —
except the two clearly separated real-Docker edges: the read-only
Docker probe module and the real container execution adapter (B4b-01),
which are the only subprocess edges of the execution plane.  The
production database-backed binding (B4b-02A) is a pure read-only
control-plane lookup with no subprocess edge at all.  Importing the
whole Route B execution surface at runtime must load no v1 authority
module.
"""

from __future__ import annotations

import importlib
import re
import sys
import unittest
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[3]
_SRC_ROOT = _REPO_ROOT / "src" / "vespercode"

_B4_MODULES = (
    "execution/v2_profile.py",
    "execution/v2_execution.py",
    "execution/v2_executor.py",
    "execution/v2_docker_probe.py",
    "execution/v2_docker_executor.py",
    "execution/v2_database_binding.py",
)

# The v1 authority modules: the digest-bound v1 execution and
# validation planes, the v1 reference profile manifest, and every
# v1 identity/governance/web/storage/credential/profiles/CLI module
# the earlier separation guards froze.  None of these may be imported
# by a Route B execution-plane module for any v2 execution decision.
_V1_AUTHORITY_MODULES = (
    # v1 Docker execution authority (the plane B4a replaces)
    "vespercode.execution.docker_executor",
    "vespercode.execution.docker_profile",
    "vespercode.execution.materialization",
    "vespercode.execution.cleanup",
    # v1 validation authority
    "vespercode.validation.baseline",
    "vespercode.validation.check_result",
    "vespercode.validation.failure_fingerprint",
    "vespercode.validation.formal",
    "vespercode.validation.formal_execution",
    "vespercode.validation.formal_plan",
    "vespercode.validation.manifest",
    "vespercode.validation.pytest_evidence",
    "vespercode.validation.pytest_reporter",
    "vespercode.validation.python_adapter",
    # v1 candidate/canonical/contracts identity authority
    "vespercode.candidate.identity",
    "vespercode.candidate.final_diff",
    "vespercode.candidate.patch_engine",
    "vespercode.candidate.unified_diff",
    "vespercode.canonical.digest",
    "vespercode.canonical.json_v1",
    "vespercode.canonical.path_v1",
    "vespercode.canonical.timestamp_v1",
    "vespercode.contracts.action",
    "vespercode.contracts.evidence",
    "vespercode.contracts.location",
    "vespercode.contracts.optional",
    "vespercode.contracts.run",
    # v1 trees
    "vespercode.trees.candidate",
    "vespercode.trees.content_store",
    "vespercode.trees.snapshot",
    "vespercode.trees.text_classifier",
    # v1 reference/LLM profile authority
    "vespercode.profiles.editable",
    "vespercode.profiles.endpoints",
    "vespercode.profiles.llm",
    "vespercode.profiles.reference",
    "vespercode.profiles.registry",
    # v1 credentials, storage, governance authority
    "vespercode.credentials.port",
    "vespercode.credentials.service",
    "vespercode.credentials.wincred_store",
    "vespercode.storage.connection",
    "vespercode.storage.idempotency",
    "vespercode.storage.run_repository",
    "vespercode.governance.disclosure_decision",
    "vespercode.governance.disclosure_ledger",
    "vespercode.governance.disclosure_revocation",
    "vespercode.governance.disclosure_scope",
    "vespercode.governance.disclosure_subject",
    "vespercode.governance.policy",
    "vespercode.governance.request_sources",
    "vespercode.governance.writeback_approval",
    "vespercode.governance.writeback_decision",
    "vespercode.governance.writeback_subject",
    # v1 CLI and web authority
    "vespercode.cli",
    "vespercode.cli_composition",
    "vespercode.web.app",
    "vespercode.web.security",
    "vespercode.web.local_composition",
    "vespercode.web.routes_audit",
    "vespercode.web.routes_credentials",
    "vespercode.web.routes_disclosure",
    "vespercode.web.routes_memory",
    "vespercode.web.routes_operations",
    "vespercode.web.routes_recovery",
    "vespercode.web.routes_runs",
    "vespercode.web.routes_writeback",
    "vespercode.web.disclosure_workflow",
    "vespercode.web.writeback_workflow",
    "vespercode.web.run_lifecycle_workflow",
    "vespercode.web.run_workflows",
    # the v1 demo application is out of bounds for v2 decisions
    "vespercode.demo.app",
)


def _source(relative: str) -> str:
    return (_SRC_ROOT / relative).read_text(encoding="utf-8")


class B4V1SeparationTests(unittest.TestCase):
    def test_b4_modules_exist(self) -> None:
        for relative in _B4_MODULES:
            self.assertTrue(
                (_SRC_ROOT / relative).is_file(),
                f"missing Route B execution-plane module: {relative}",
            )

    def test_b4_modules_do_not_import_v1_authority(self) -> None:
        pattern = "|".join(re.escape(module) for module in _V1_AUTHORITY_MODULES)
        import_line = re.compile(rf"^\s*(?:from|import)\s+({pattern})\b", re.MULTILINE)
        for relative in _B4_MODULES:
            source = _source(relative)
            match = import_line.search(source)
            self.assertIsNone(
                match,
                f"{relative} imports v1 authority module: "
                f"{match.group(1) if match else ''}",
            )

    def test_b4_modules_derive_no_digest_identity(self) -> None:
        digest_import = re.compile(r"^\s*(?:from|import)\s+hashlib\b", re.MULTILINE)
        for relative in _B4_MODULES:
            self.assertIsNone(
                digest_import.search(_source(relative)),
                f"{relative} imports hashlib; v2 execution identity must "
                "not be digest-derived",
            )

    def test_b4_modules_are_standard_library_and_v2_only(self) -> None:
        third_party = re.compile(
            r"^\s*(?:from|import)\s+(pydantic|fastapi|uvicorn|httpx|jinja2|docker)\b",
            re.MULTILINE,
        )
        for relative in _B4_MODULES:
            self.assertIsNone(
                third_party.search(_source(relative)),
                f"{relative} imports a third-party package; the v2 execution "
                "plane is standard-library only",
            )

    def test_the_only_process_edges_are_the_docker_probe_and_executor(
        self,
    ) -> None:
        process_import = re.compile(
            r"^\s*(?:from|import)\s+subprocess\b", re.MULTILINE
        )
        process_call = re.compile(r"\bos\.(?:system|popen|exec[lv])\b")
        for relative in _B4_MODULES:
            source = _source(relative)
            if relative in (
                "execution/v2_docker_probe.py",
                "execution/v2_docker_executor.py",
            ):
                # The clearly separated read-only probe (B4a) and the
                # real container execution adapter (B4b-01) are the two
                # subprocess edges of the v2 execution plane.
                continue
            self.assertIsNone(
                process_import.search(source),
                f"{relative} spawns processes; only the docker probe "
                "and docker executor modules may hold the subprocess "
                "edge",
            )
            self.assertIsNone(
                process_call.search(source),
                f"{relative} calls a process-spawning os function",
            )

    def test_no_b4_module_imports_sockets(self) -> None:
        socket_import = re.compile(
            r"^\s*(?:from|import)\s+socket\b", re.MULTILINE
        )
        for relative in _B4_MODULES:
            self.assertIsNone(
                socket_import.search(_source(relative)),
                f"{relative} imports socket; the v2 execution plane "
                "opens no network sockets",
            )

    def test_importing_the_b4_surface_loads_no_v1_authority_module(self) -> None:
        # The asserted contract is that importing the B4 surface does not
        # LOAD a v1 authority module.  Same-process state from earlier test
        # files is causally irrelevant, so the check is a delta over
        # sys.modules: any forbidden name newly loaded by these imports is
        # a violation; a name some earlier test already imported is not.
        loaded_before = {
            authority for authority in _V1_AUTHORITY_MODULES if authority in sys.modules
        }
        for module_name in (
            "vespercode.execution.v2_profile",
            "vespercode.execution.v2_execution",
            "vespercode.execution.v2_executor",
            "vespercode.execution.v2_docker_probe",
            "vespercode.execution.v2_docker_executor",
            "vespercode.execution.v2_database_binding",
        ):
            importlib.import_module(module_name)
        newly_loaded = {
            authority
            for authority in _V1_AUTHORITY_MODULES
            if authority in sys.modules and authority not in loaded_before
        }
        self.assertEqual(
            newly_loaded,
            set(),
            f"importing the Route B execution surface loaded the v1 "
            f"authority modules {sorted(newly_loaded)}",
        )


if __name__ == "__main__":
    unittest.main()

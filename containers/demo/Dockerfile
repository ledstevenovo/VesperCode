# Public Demo image recipe (T34.1 legacy step 34.B): curated shared-core
# allowlist only.
#
# The build context is the repository root.  The final image ships EXACTLY
# the reviewed allowlist modules copied below — the Demo package plus the
# Task 30 DEMO_SHARED_CORE_MODULES_V1 shared pure core with its
# canonical/contract import closure and the wiring modules the real shared
# pipeline requires (the :memory: control-database wiring and the
# path-safety/type modules of the shared core) — plus the hash-locked
# runtime dependencies of requirements/demo.lock.  Never the formal wheel,
# loop engine, Run/turn/SQLite repositories, WinCred/OpenAI/file-tool
# adapters, persistence, recovery, memory, audit, web control plane, or
# CLI composition (SPEC §8.3; T34.1 Boundary /
# PROHIBITED_DEMO_MODULE_PREFIXES_V1).  The three
# `vespercode.execution` modules copied below
# (docker_executor/docker_profile/materialization) are present only as
# boot-required type imports of the shared check-result contract (§75
# ruling); their Docker capability is unreachable — function-local lazy
# imports, no docker SDK in demo.lock, and no module-level docker import
# in the boot closure.
FROM python:3.12-slim@sha256:57cd7c3a7a273101a6485ba99423ee568157882804b1124b4dd04266317710de

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

WORKDIR /app

COPY requirements/demo.lock /app/requirements.lock
RUN pip install --no-cache-dir --no-deps --require-hashes -r /app/requirements.lock \
    && useradd --system --uid 10001 --shell /usr/sbin/nologin --no-create-home vesper

# Curated allowlist (per-file): the Demo package, the shared pure core,
# the canonical/contract closure, and the shared-pipeline wiring.
COPY src/vespercode/__init__.py /app/vespercode/__init__.py
COPY src/vespercode/demo/app.py /app/vespercode/demo/app.py
COPY src/vespercode/demo/executor.py /app/vespercode/demo/executor.py
COPY src/vespercode/demo/healthcheck.py /app/vespercode/demo/healthcheck.py
COPY src/vespercode/demo/runner.py /app/vespercode/demo/runner.py
COPY src/vespercode/demo/scenario.py /app/vespercode/demo/scenario.py
COPY src/vespercode/demo/types.py /app/vespercode/demo/types.py
COPY src/vespercode/demo/templates /app/vespercode/demo/templates
COPY src/vespercode/canonical/clock.py /app/vespercode/canonical/clock.py
COPY src/vespercode/canonical/digest.py /app/vespercode/canonical/digest.py
COPY src/vespercode/canonical/json_v1.py /app/vespercode/canonical/json_v1.py
COPY src/vespercode/canonical/path_v1.py /app/vespercode/canonical/path_v1.py
COPY src/vespercode/canonical/timestamp_v1.py /app/vespercode/canonical/timestamp_v1.py
COPY src/vespercode/contracts/action.py /app/vespercode/contracts/action.py
COPY src/vespercode/contracts/evidence.py /app/vespercode/contracts/evidence.py
COPY src/vespercode/contracts/location.py /app/vespercode/contracts/location.py
COPY src/vespercode/contracts/optional.py /app/vespercode/contracts/optional.py
COPY src/vespercode/contracts/run.py /app/vespercode/contracts/run.py
COPY src/vespercode/candidate/patch_engine.py /app/vespercode/candidate/patch_engine.py
COPY src/vespercode/candidate/unified_diff.py /app/vespercode/candidate/unified_diff.py
COPY src/vespercode/governance/policy.py /app/vespercode/governance/policy.py
COPY src/vespercode/governance/request_sources.py /app/vespercode/governance/request_sources.py
COPY src/vespercode/llm/base.py /app/vespercode/llm/base.py
COPY src/vespercode/llm/prepared_request.py /app/vespercode/llm/prepared_request.py
COPY src/vespercode/loop/action_binding.py /app/vespercode/loop/action_binding.py
COPY src/vespercode/loop/action_parser.py /app/vespercode/loop/action_parser.py
COPY src/vespercode/loop/action_pipeline.py /app/vespercode/loop/action_pipeline.py
COPY src/vespercode/loop/agent_actions.py /app/vespercode/loop/agent_actions.py
COPY src/vespercode/loop/context_projection.py /app/vespercode/loop/context_projection.py
COPY src/vespercode/audit/event.py /app/vespercode/audit/event.py
COPY src/vespercode/loop/feedback.py /app/vespercode/loop/feedback.py
COPY src/vespercode/loop/feedback_consumption.py /app/vespercode/loop/feedback_consumption.py
COPY src/vespercode/loop/progress.py /app/vespercode/loop/progress.py
COPY src/vespercode/loop/stopping.py /app/vespercode/loop/stopping.py
COPY src/vespercode/tools/dispatcher.py /app/vespercode/tools/dispatcher.py
COPY src/vespercode/tools/file_actions.py /app/vespercode/tools/file_actions.py
COPY src/vespercode/tools/file_results.py /app/vespercode/tools/file_results.py
COPY src/vespercode/trees/candidate.py /app/vespercode/trees/candidate.py
COPY src/vespercode/trees/content_store.py /app/vespercode/trees/content_store.py
COPY src/vespercode/trees/readable.py /app/vespercode/trees/readable.py
COPY src/vespercode/trees/snapshot.py /app/vespercode/trees/snapshot.py
COPY src/vespercode/trees/text_classifier.py /app/vespercode/trees/text_classifier.py
COPY src/vespercode/validation/check_result.py /app/vespercode/validation/check_result.py
COPY src/vespercode/profiles/editable.py /app/vespercode/profiles/editable.py
COPY src/vespercode/profiles/llm.py /app/vespercode/profiles/llm.py
COPY src/vespercode/profiles/reference.py /app/vespercode/profiles/reference.py
COPY src/vespercode/storage/connection.py /app/vespercode/storage/connection.py
COPY src/vespercode/storage/idempotency.py /app/vespercode/storage/idempotency.py
COPY src/vespercode/storage/migration_engine.py /app/vespercode/storage/migration_engine.py
COPY src/vespercode/storage/migrations/__init__.py /app/vespercode/storage/migrations/__init__.py
COPY src/vespercode/storage/migrations/v0001_run_wait.py /app/vespercode/storage/migrations/v0001_run_wait.py
COPY src/vespercode/storage/migrations/v0002_idempotency.py /app/vespercode/storage/migrations/v0002_idempotency.py
COPY src/vespercode/storage/migrations/v0003_disclosure_grants.py /app/vespercode/storage/migrations/v0003_disclosure_grants.py
COPY src/vespercode/storage/migrations/v0004_disclosure_authorizations.py /app/vespercode/storage/migrations/v0004_disclosure_authorizations.py
COPY src/vespercode/storage/migrations/v0005_memory.py /app/vespercode/storage/migrations/v0005_memory.py
COPY src/vespercode/storage/migrations/v0006_audit.py /app/vespercode/storage/migrations/v0006_audit.py
COPY src/vespercode/storage/migrations/v0007_agent_turns.py /app/vespercode/storage/migrations/v0007_agent_turns.py
COPY src/vespercode/storage/migrations/v0008_feedback.py /app/vespercode/storage/migrations/v0008_feedback.py
COPY src/vespercode/storage/migrations/v0009_actions.py /app/vespercode/storage/migrations/v0009_actions.py
COPY src/vespercode/workspace/git_preflight.py /app/vespercode/workspace/git_preflight.py
COPY src/vespercode/workspace/identity_win32.py /app/vespercode/workspace/identity_win32.py
COPY src/vespercode/workspace/object_win32.py /app/vespercode/workspace/object_win32.py
COPY src/vespercode/workspace/path_guard.py /app/vespercode/workspace/path_guard.py
COPY src/vespercode/execution/docker_executor.py /app/vespercode/execution/docker_executor.py
COPY src/vespercode/execution/docker_profile.py /app/vespercode/execution/docker_profile.py
COPY src/vespercode/execution/materialization.py /app/vespercode/execution/materialization.py

USER vesper

EXPOSE 8000
# The healthcheck runs as a module (``python -m`` keeps the working
# directory on sys.path, so the Demo ``types`` module can never shadow
# the stdlib ``types`` that a script-directory invocation would import).
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD ["python", "-m", "vespercode.demo.healthcheck"]
# The platform-injected PORT (SPEC §8.3) selects the bind; the launcher
# is the exact thin factory composition — no formal capability is ever
# registered, constructed, or called.
CMD ["sh", "-c", "exec python -c 'import os, uvicorn; from vespercode.demo.app import DemoAppConfigV1, create_demo_app; p = int(os.environ.get(\"PORT\", \"8000\")); uvicorn.run(create_demo_app(DemoAppConfigV1(port=p)), host=\"0.0.0.0\", port=p)'"]

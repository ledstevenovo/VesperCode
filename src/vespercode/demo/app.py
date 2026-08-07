"""T30.2 legacy step 30.B: the thin public Demo FastAPI app.

``create_demo_app`` composes only Task 30.D's headless runner into the
closed health, session-create, and advance routes with a validated
platform PORT (SPEC §8.3) and the exact fixed-simulation capability
registry (GREEN-1): ``DEMO_EXECUTOR``, ``DEMO_SESSION``, and
``DEMO_RENDERER`` — never a local file, credential, Docker, recovery,
persistence, SQLite, WinCred, OpenAI, or formal Run capability
(GREEN-4/Boundary).  The fixed scenario page is rendered escaped with
persistent simulation labeling, keyboard/focus and live-error support,
non-color status, sufficient contrast, and reduced motion — with no
prompt, URL, repository, upload, provider, or secret input (GREEN-2).
The app owns the thin public surface only; shared-core/session rules and
all formal capabilities remain out of scope.
"""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Annotated, Any, Final, Literal

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    Strict,
    StrictStr,
)

from vespercode.canonical.clock import ClockV1, SystemClockV1
from vespercode.contracts.evidence import DigestV1
from vespercode.demo.executor import DemoExecutor
from vespercode.demo.runner import (
    DemoAdvanceErrorV1,
    DemoScenarioRunner,
)
from vespercode.demo.scenario import FIXED_DEMO_SCENARIO_V1
from vespercode.demo.types import (
    DemoDecisionV1,
    DemoSessionV1,
    DemoStepResultV1,
)

DEMO_CAPABILITY_KINDS_V1: Final[frozenset[str]] = frozenset(
    {"DEMO_EXECUTOR", "DEMO_SESSION", "DEMO_RENDERER"}
)
"""The exact fixed-simulation capability registry of the public Demo app
(card 30.B interface): only the Demo executor, the Demo session runner,
and the fixed-scenario renderer — never a local file, credential, Docker,
recovery, persistence, SQLite, WinCred, OpenAI, or formal Run adapter."""

_TEMPLATES_DIRECTORY: Final[str] = str(Path(__file__).resolve().parent / "templates")
"""The packaged fixed-scenario template directory (a module-level name so
the health boundary can verify the asset)."""

_FIXED_SUBJECT_DIGEST: Final = "ab" * 32
"""The fixed digest identity of every simulated visitor decision (the
fixed scenario's own identity; no formal subject is ever constructed)."""

_SECURITY_HEADERS_V1: Final[dict[str, str]] = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
}
"""The closed security headers of every demo response (SPEC §4.9's
security-header verification: the fixed-scenario page is escaped and
never framed, and no referrer leaves the public demo)."""


class DemoAppConfigV1(BaseModel):
    """One closed public Demo app config with a validated platform PORT.

    The PORT is the validated 1..65535 platform port of SPEC §8.3 (the
    container reads the injected ``PORT`` and binds 0.0.0.0); the mode is
    the closed ``simulation`` literal so the app can never present as a
    formal verification.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal[1] = 1
    mode: Literal["simulation"] = "simulation"
    port: Annotated[int, Strict(), Field(ge=1, le=65535)]


class DemoSessionCreatedV1(BaseModel):
    """One closed created-session envelope (card 30.B route response)."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal[1] = 1
    demo_session_id: StrictStr
    session: DemoSessionV1


class DemoAdvanceRequestV1(BaseModel):
    """One closed advance request: the optional simulated visitor choice.

    The choice only forms a ``DemoDecisionV1`` that advances the fixed
    scenario; it can never become a formal approval or disclosure grant
    (SPEC §2.9/§4.9).
    """

    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal[1] = 1
    decision: Literal["APPROVE", "REJECT"] | None = None


class _DemoAppServices:
    """The closed headless services behind one Demo app (the registry's
    three capability holders: executor, sessions, renderer)."""

    def __init__(
        self,
        *,
        executor: DemoExecutor,
        runner: DemoScenarioRunner,
        templates: Jinja2Templates,
        clock: ClockV1,
    ) -> None:
        self.executor = executor
        self.runner = runner
        self.templates = templates
        self.clock = clock


_DEMO_ERROR_STATUS_V1: Final[dict[str, int]] = {
    "DEMO_SESSION_NOT_FOUND": 404,
    "DEMO_SESSION_EXPIRED": 410,
    "DEMO_SESSION_ID_EXISTS": 409,
    "DEMO_SESSION_LIMIT": 409,
    "DEMO_ACTION_LIMIT": 409,
    "DEMO_STATE_MISMATCH": 409,
    "DEMO_DECISION_REQUIRED": 400,
    "DEMO_DECISION_MISMATCH": 400,
}
"""The closed rejection-code-to-HTTP mapping of the demo routes (SPEC
§4.9: invalid sessions, illegal scenario steps, and capability requests
must be rejected)."""


def _http_status_for(error_code: str) -> int:
    """One stable HTTP status for a closed demo rejection code."""
    return _DEMO_ERROR_STATUS_V1.get(error_code, 500)


def create_demo_app(config: DemoAppConfigV1) -> FastAPI:
    """One public Demo app over the headless runner (30.B GREEN-1..GREEN-4).

    Only the closed health, page, session-create, and advance routes are
    registered; the fixed-simulation capability registry is the exact
    three-kind set; no repository path/upload/prompt/URL/provider/secret
    input, disk persistence, local route, recovery, SQLite, WinCred,
    Docker, or OpenAI adapter exists anywhere on the app (Boundary).
    """
    clock = SystemClockV1()
    executor = DemoExecutor()
    runner = DemoScenarioRunner(clock=clock, executor=executor)
    templates = Jinja2Templates(directory=_TEMPLATES_DIRECTORY)
    services = _DemoAppServices(
        executor=executor,
        runner=runner,
        templates=templates,
        clock=clock,
    )
    app = FastAPI(
        title="VesperCode Mock Demo",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
    app.state.config = config
    app.state.capability_kinds = DEMO_CAPABILITY_KINDS_V1
    app.state.demo = services

    @app.middleware("http")
    async def _security_headers(request: Request, call_next: Any) -> Any:
        """Attach the closed security headers to every response."""
        response = await call_next(request)
        for name, value in _SECURITY_HEADERS_V1.items():
            response.headers[name] = value
        return response

    @app.get("/healthz")
    def healthz() -> dict[str, str]:
        """The exact platform health check: simulation mode only."""
        return {"status": "ok", "mode": config.mode}

    @app.get("/", response_class=HTMLResponse)
    def demo_page(request: Request) -> HTMLResponse:
        """The escaped, persistently simulation-labeled fixed-scenario
        page (keyboard/focus/live-error support, non-color status,
        contrast, reduced motion; no text inputs at all)."""
        return templates.TemplateResponse(
            request,
            "demo.html",
            {
                "scenario": FIXED_DEMO_SCENARIO_V1,
                "mode": config.mode,
                "capability_kinds": tuple(sorted(DEMO_CAPABILITY_KINDS_V1)),
            },
        )

    @app.post("/demo/sessions", response_model=DemoSessionCreatedV1, status_code=201)
    def create_demo_session() -> DemoSessionCreatedV1:
        """Create one bounded in-memory Demo session (an independent
        UUID; SPEC §4.9 session rows)."""
        demo_session_id = uuid.uuid4().hex
        session = runner.create_session(demo_session_id)
        return DemoSessionCreatedV1(
            schema_version=1,
            demo_session_id=demo_session_id,
            session=session,
        )

    @app.post(
        "/demo/sessions/{session_id}/advance",
        response_model=DemoStepResultV1,
    )
    def advance_demo_session(
        session_id: str, request: DemoAdvanceRequestV1
    ) -> DemoStepResultV1:
        """Advance one session by one fixed scenario step.

        The visitor's optional choice only forms a ``DemoDecisionV1``;
        invalid, expired, limited, or stale sessions and wrong decisions
        reject closed with the mapped HTTP status and the stable code.
        """
        decision = _demo_decision(session_id, request.decision, services)
        try:
            session = runner.session(session_id)
            result = runner.advance(session, decision)
        except DemoAdvanceErrorV1 as error:
            raise HTTPException(
                status_code=_http_status_for(error.error_code),
                detail=error.error_code,
            ) from error
        return result.step

    return app


def _demo_decision(
    demo_session_id: str,
    choice: Literal["APPROVE", "REJECT"] | None,
    services: _DemoAppServices,
) -> DemoDecisionV1 | None:
    """One closed simulated visitor decision (or none).

    The decision binds the demo session id, the fixed subject digest,
    and the current canonical time; it only advances the fixed scenario
    and can never convert into a formal approval or disclosure grant.
    """
    if choice is None:
        return None
    return DemoDecisionV1(
        demo_session_id=demo_session_id,
        subject_digest=DigestV1(value=_FIXED_SUBJECT_DIGEST),
        decision=choice,
        created_at=services.clock.now(),
    )

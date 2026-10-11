"""Route B / B3: the local v2 WebUI application.

``V2LocalWebApp`` is the standard-library-only, framework-agnostic route
surface of the v2 local WebUI.  It owns no business rules of its own —
every decision flows through the injected local shell (the ``V2LocalShellPort``
protocol) and the Route A/B2 services behind it.  The app owns exactly
the integration boundary:

- a closed route table: one GET/POST pair per control, and anything
  else is a static 404/405 with the security headers;
- a closed route table: one GET/POST pair per control, and anything
  else is a static 404/405 with the security headers;
- the fixed security order — host, session resolution, origin, CSRF —
  runs through the manager-bound ``authorize_v2_local_request`` BEFORE
  any form parsing or domain call, so a rejected request performs zero
  shell calls; the SESSION check resolves the cookie through the
  app's own ``V2LocalSessionManager`` and requires a registered,
  still-live session, so a forged or expired session value rejects
  before any form or domain call, and the app itself never authorizes
  a request by passing a session object (no such variant exists);
  safe GET reads that fail only the session check auto-establish a
  fresh session from the same manager and respond with the Set-Cookie;
- allowlisted typed form contracts (``vespercode.web.v2_forms``): a
  malformed, unknown-field, or unconfirmed form is a bounded 400 with
  zero shell calls; binding pre-checks keep unknown, stale, or
  mismatched run/candidate/revision forms away from every mutation;
- every mutation requires the explicit ``CONFIRM`` literal and the
  bound opaque IDs, and recovery preview is a safe read;
- HTML rendering escapes every projected value, pages carry only
  bounded control-plane facts (IDs, statuses, revisions, counts,
  timestamps), and no secret, file content, or request body is ever
  echoed back.
"""

from __future__ import annotations

import html
from dataclasses import dataclass, field
from typing import Callable, Mapping

from vespercode.shell_v2 import V2ShellError
from vespercode.web.v2_forms import (
    V2FormError,
    V2_RECOVERY_APPLY_FORM,
    V2_RECOVERY_PREVIEW_QUERY,
    V2_RUN_DETAIL_QUERY,
    V2_RUN_START_FORM,
    V2_WRITEBACK_APPLY_FORM,
    V2_WRITEBACK_APPROVE_FORM,
    v2_identifier,
)
from vespercode.web.v2_security import (
    V2LocalSecurityConfig,
    V2LocalSessionManager,
    V2LocalSessionV2,
    authorize_v2_local_request,
    v2_request_rejection_payload,
    v2_request_status,
    v2_security_headers,
)

_MAX_RUNS_ON_PAGE = 50
_MAX_GRANTS_ON_PAGE = 100

_SHELL_ERROR_STATUS = {
    "NO_LLM_BOUNDARY": 503,
    "UNKNOWN_RUN": 404,
    "UNKNOWN_CANDIDATE": 404,
    "RUN_CANDIDATE_MISMATCH": 404,
    "STALE_CANDIDATE_REVISION": 409,
    "NOTHING_STAGED": 409,
    "UNKNOWN_TRANSACTION": 404,
    "NOT_RECOVERABLE": 409,
    "INVALID_PROVIDER": 400,
}


@dataclass(frozen=True, slots=True)
class V2WebRequest:
    """One framework-agnostic local request.

    ``headers`` keys must be lower-case; ``form`` is the parsed query
    (GET) or URL-encoded body (POST); ``cookies`` is the parsed cookie
    jar.  The record carries no raw body bytes.
    """

    method: str
    path: str
    headers: Mapping[str, str] = field(default_factory=dict)
    cookies: Mapping[str, str] = field(default_factory=dict)
    form: Mapping[str, str] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class V2WebResponse:
    """One framework-agnostic local response (bounded status/body)."""

    status: int
    headers: dict[str, str]
    body: str


def _esc(value: object) -> str:
    return html.escape(str(value), quote=True)


class V2LocalWebApp:
    """The closed local WebUI composition over one injected shell."""

    def __init__(
        self,
        shell,
        *,
        config: V2LocalSecurityConfig | None = None,
        session_manager: V2LocalSessionManager | None = None,
    ) -> None:
        if shell is None:
            raise ValueError("the local WebUI requires a shell")
        self._shell = shell
        self._config = config if config is not None else V2LocalSecurityConfig()
        self._sessions = (
            session_manager
            if session_manager is not None
            else V2LocalSessionManager(self._config)
        )
        self._routes: dict[tuple[str, str], Callable] = {
            ("GET", "/"): self._home,
            ("GET", "/runs"): self._runs_page,
            ("GET", "/run"): self._run_detail_page,
            ("POST", "/run/start"): self._run_start,
            ("POST", "/writeback/approve"): self._writeback_approve,
            ("POST", "/writeback/apply"): self._writeback_apply,
            ("GET", "/recovery"): self._recovery_page,
            ("GET", "/recovery/preview"): self._recovery_preview_page,
            ("POST", "/recovery/apply"): self._recovery_apply,
            ("GET", "/credentials"): self._credentials_page,
            ("GET", "/disclosures"): self._disclosures_page,
        }
        self._known_paths = {path for _, path in self._routes}

    # ------------------------------------------------------------------
    # dispatch
    # ------------------------------------------------------------------

    def handle(self, request: V2WebRequest) -> V2WebResponse:
        handler = self._routes.get((request.method, request.path))
        if handler is None:
            if request.path in self._known_paths:
                return self._static_error(405, "Method Not Allowed")
            return self._static_error(404, "Not Found")
        # The manager-bound authorization owns the whole fixed order
        # (HOST -> SESSION -> ORIGIN -> CSRF): the session must resolve
        # through this app's session manager and be live at its clock,
        # so a forged or expired session value rejects here — before
        # any form parsing and before any domain call.  The app never
        # authorizes a request by passing a session object itself.
        outcome = authorize_v2_local_request(
            method=request.method,
            headers=request.headers,
            cookies=request.cookies,
            form=request.form,
            session_manager=self._sessions,
            config=self._config,
        )
        if outcome.authorized:
            assert outcome.session is not None
            return handler(request, outcome.session, False)
        if request.method == "GET" and outcome.rejected_at == "SESSION":
            # Safe reads establish a fresh session: the host check has
            # already passed inside the authorizer (the SESSION check
            # follows it); the new session comes from the same manager,
            # and the response carries the Set-Cookie.
            session = self._sessions.create()
            return handler(request, session, True)
        assert outcome.error_code is not None
        return self._security_rejection(outcome.error_code)

    # ------------------------------------------------------------------
    # handlers (safe reads)
    # ------------------------------------------------------------------

    def _home(
        self, request: V2WebRequest, session: V2LocalSessionV2, created: bool
    ) -> V2WebResponse:
        runs = self._shell.recent_runs(_MAX_RUNS_ON_PAGE)
        pending = self._shell.pending_transaction_ids()
        body = [
            "<h1>VesperCode v2 local console</h1>",
            f"<p>runs recorded (latest {_MAX_RUNS_ON_PAGE}): {len(runs)}</p>",
            f"<p>pending recovery transactions: {len(pending)}</p>",
            "<ul>"
            "<li><a href=\"/runs\">runs</a></li>"
            "<li><a href=\"/recovery\">recovery</a></li>"
            "<li><a href=\"/credentials\">credentials</a></li>"
            "<li><a href=\"/disclosures\">disclosures</a></li>"
            "</ul>",
            "<h2>Start a local run</h2>",
            "<form method=\"post\" action=\"/run/start\">",
            self._csrf_input(session),
            "<label>task <textarea name=\"task\" rows=\"4\" "
            "maxlength=\"4096\" required></textarea></label><br>",
            "<label>type CONFIRM to run <input name=\"confirm\" "
            "required></label><br>",
            "<button type=\"submit\">start run</button>",
            "</form>",
        ]
        return self._render(200, "\n".join(body), session=session, session_created=created)

    def _runs_page(
        self, request: V2WebRequest, session: V2LocalSessionV2, created: bool
    ) -> V2WebResponse:
        runs = self._shell.recent_runs(_MAX_RUNS_ON_PAGE)
        rows = [
            "<tr>"
            f"<td><a href=\"/run?run_id={_esc(run.run_id)}\">{_esc(run.run_id)}</a></td>"
            f"<td>{_esc(run.status)}</td>"
            f"<td>{_esc(run.phase if run.phase is not None else '-')}</td>"
            f"<td>{_esc(run.revision)}</td>"
            "</tr>"
            for run in runs
        ]
        body = [
            "<h1>v2 runs</h1>",
            "<table><thead><tr><th>run</th><th>status</th><th>phase</th>"
            "<th>revision</th></tr></thead><tbody>",
            *rows,
            "</tbody></table>",
        ]
        return self._render(200, "\n".join(body), session=session, session_created=created)

    def _run_detail_page(
        self, request: V2WebRequest, session: V2LocalSessionV2, created: bool
    ) -> V2WebResponse:
        try:
            parsed = V2_RUN_DETAIL_QUERY.parse(request.form)
        except V2FormError:
            return self._form_error()
        run = self._shell.run_detail(str(parsed["run_id"]))
        if run is None:
            return self._static_error(404, "Unknown run")
        body = [
            "<h1>v2 run</h1>",
            f"<p>run_id: {_esc(run.run_id)}</p>",
            f"<p>status: {_esc(run.status)}</p>",
            f"<p>phase: {_esc(run.phase if run.phase is not None else '-')}</p>",
            f"<p>revision: {_esc(run.revision)}</p>",
            "<h2>Approve a writeback</h2>",
            "<form method=\"post\" action=\"/writeback/approve\">",
            self._csrf_input(session),
            f"<label>run_id <input name=\"run_id\" value=\"{_esc(run.run_id)}\" readonly></label><br>",
            "<label>candidate_id <input name=\"candidate_id\" required></label><br>",
            "<label>candidate_revision <input name=\"candidate_revision\" required></label><br>",
            "<label>type CONFIRM to approve <input name=\"confirm\" required></label><br>",
            "<button type=\"submit\">create approval</button>",
            "</form>",
        ]
        return self._render(200, "\n".join(body), session=session, session_created=created)

    def _recovery_page(
        self, request: V2WebRequest, session: V2LocalSessionV2, created: bool
    ) -> V2WebResponse:
        transaction_ids = self._shell.pending_transaction_ids()
        items = [
            f"<li><a href=\"/recovery/preview?transaction_id={_esc(tid)}\">"
            f"{_esc(tid)}</a></li>"
            for tid in transaction_ids
        ]
        body = [
            "<h1>v2 recovery</h1>",
            f"<p>pending transactions: {len(transaction_ids)}</p>",
            "<ul>",
            *items,
            "</ul>",
        ]
        return self._render(200, "\n".join(body), session=session, session_created=created)

    def _recovery_preview_page(
        self, request: V2WebRequest, session: V2LocalSessionV2, created: bool
    ) -> V2WebResponse:
        try:
            parsed = V2_RECOVERY_PREVIEW_QUERY.parse(request.form)
        except V2FormError:
            return self._form_error()
        transaction_id = str(parsed["transaction_id"])
        try:
            preview = self._shell.recovery_preview(transaction_id)
        except V2ShellError as exc:
            return self._shell_error(exc)
        rows = [
            "<tr>"
            f"<td>{_esc(item.position)}</td>"
            f"<td>{_esc(item.path)}</td>"
            f"<td>{_esc(item.action_type)}</td>"
            f"<td>{_esc(item.state)}</td>"
            "</tr>"
            for item in preview.items
        ]
        body = [
            "<h1>v2 recovery preview</h1>",
            f"<p>transaction: {_esc(preview.transaction_id)}</p>",
            f"<p>state: {_esc(preview.transaction_state)}</p>",
            f"<p>blocked: {'yes' if preview.blocked else 'no'}</p>",
            "<table><thead><tr><th>position</th><th>path</th>"
            "<th>action</th><th>state</th></tr></thead><tbody>",
            *rows,
            "</tbody></table>",
            "<h2>Apply this transaction</h2>",
            "<form method=\"post\" action=\"/recovery/apply\">",
            self._csrf_input(session),
            f"<label>transaction_id <input name=\"transaction_id\" value=\"{_esc(preview.transaction_id)}\" readonly></label><br>",
            "<label>type CONFIRM to apply <input name=\"confirm\" required></label><br>",
            "<button type=\"submit\">apply</button>",
            "</form>",
        ]
        return self._render(200, "\n".join(body), session=session, session_created=created)

    def _credentials_page(
        self, request: V2WebRequest, session: V2LocalSessionV2, created: bool
    ) -> V2WebResponse:
        body = [
            "<h1>v2 credential status</h1>",
            "<p>Status carries the provider, a configured flag, and an update "
            "time only — never a secret value, length, or derivative.</p>",
            "<form method=\"get\" action=\"/credentials\">",
            "<label>provider <input name=\"provider\" required></label>",
            "<button type=\"submit\">show status</button>",
            "</form>",
        ]
        if "provider" in request.form:
            try:
                provider = v2_identifier(request.form.get("provider"), "provider")
            except V2FormError:
                return self._form_error()
            status = self._shell.credential_status(provider)
            body.extend(
                [
                    "<h2>Status</h2>",
                    f"<p>provider: {_esc(status.provider)}</p>",
                    f"<p>configured: {'yes' if status.configured else 'no'}</p>",
                    f"<p>updated_at: {_esc(status.updated_at if status.updated_at is not None else '-')}</p>",
                ]
            )
        return self._render(200, "\n".join(body), session=session, session_created=created)

    def _disclosures_page(
        self, request: V2WebRequest, session: V2LocalSessionV2, created: bool
    ) -> V2WebResponse:
        grants = self._shell.disclosure_grant_summaries(_MAX_GRANTS_ON_PAGE)
        rows = [
            "<tr>"
            f"<td>{_esc(grant.grant_id)}</td>"
            f"<td>{_esc(grant.run_id)}</td>"
            f"<td>{_esc(grant.status)}</td>"
            f"<td>{_esc(grant.expires_at)}</td>"
            f"<td>{_esc(grant.byte_budget)}</td>"
            f"<td>{_esc(grant.consumed_bytes)}</td>"
            "</tr>"
            for grant in grants
        ]
        body = [
            "<h1>v2 disclosure grants</h1>",
            "<p>Bounded control-plane facts only: opaque IDs, status, "
            "expiry, and budget counters. No sources or content.</p>",
            "<table><thead><tr><th>grant</th><th>run</th><th>status</th>"
            "<th>expires</th><th>budget</th><th>consumed</th></tr></thead><tbody>",
            *rows,
            "</tbody></table>",
        ]
        return self._render(200, "\n".join(body), session=session, session_created=created)

    # ------------------------------------------------------------------
    # handlers (explicit, confirmed mutations)
    # ------------------------------------------------------------------

    def _run_start(
        self, request: V2WebRequest, session: V2LocalSessionV2, created: bool
    ) -> V2WebResponse:
        try:
            parsed = V2_RUN_START_FORM.parse(request.form)
        except V2FormError:
            return self._form_error()
        try:
            outcome = self._shell.start_run(str(parsed["task"]))
        except V2ShellError as exc:
            return self._shell_error(exc)
        body = [
            "<h1>v2 run started</h1>",
            f"<p>run_id: {_esc(outcome.run_id)}</p>",
            f"<p>candidate_id: {_esc(outcome.candidate_id)}</p>",
            f"<p>candidate_revision: {_esc(outcome.candidate_revision)}</p>",
            f"<p>loop_status: {_esc(outcome.loop_status)}</p>",
            f"<p>stop_reason: {_esc(outcome.stop_reason)}</p>",
            f"<p>turns: {_esc(outcome.turns)}</p>",
            "<h2>Approve the writeback</h2>",
            "<form method=\"post\" action=\"/writeback/approve\">",
            self._csrf_input(session),
            f"<label>run_id <input name=\"run_id\" value=\"{_esc(outcome.run_id)}\" readonly></label><br>",
            f"<label>candidate_id <input name=\"candidate_id\" value=\"{_esc(outcome.candidate_id)}\" readonly></label><br>",
            f"<label>candidate_revision <input name=\"candidate_revision\" value=\"{_esc(outcome.candidate_revision)}\" readonly></label><br>",
            "<label>type CONFIRM to approve <input name=\"confirm\" required></label><br>",
            "<button type=\"submit\">create approval</button>",
            "</form>",
        ]
        return self._render(200, "\n".join(body), session=session, session_created=created)

    def _writeback_approve(
        self, request: V2WebRequest, session: V2LocalSessionV2, created: bool
    ) -> V2WebResponse:
        try:
            parsed = V2_WRITEBACK_APPROVE_FORM.parse(request.form)
        except V2FormError:
            return self._form_error()
        run_id = str(parsed["run_id"])
        candidate_id = str(parsed["candidate_id"])
        candidate_revision = int(parsed["candidate_revision"])
        if self._shell.run_detail(run_id) is None:
            return self._static_error(404, "Unknown run")
        current = self._shell.candidate_revision(run_id, candidate_id)
        if current is None:
            return self._static_error(404, "Unknown candidate for this run")
        if current != candidate_revision:
            return self._binding_error("STALE_CANDIDATE_REVISION")
        try:
            approval_id = self._shell.create_writeback_approval(
                run_id=run_id,
                candidate_id=candidate_id,
                candidate_revision=candidate_revision,
            )
        except V2ShellError as exc:
            return self._shell_error(exc)
        body = [
            "<h1>writeback approval created</h1>",
            f"<p>approval_id: {_esc(approval_id)}</p>",
            f"<p>run_id: {_esc(run_id)}</p>",
            f"<p>candidate_id: {_esc(candidate_id)}</p>",
            f"<p>candidate_revision: {_esc(candidate_revision)}</p>",
            "<h2>Apply the approved writeback</h2>",
            "<form method=\"post\" action=\"/writeback/apply\">",
            self._csrf_input(session),
            f"<label>run_id <input name=\"run_id\" value=\"{_esc(run_id)}\" readonly></label><br>",
            f"<label>candidate_id <input name=\"candidate_id\" value=\"{_esc(candidate_id)}\" readonly></label><br>",
            f"<label>candidate_revision <input name=\"candidate_revision\" value=\"{_esc(candidate_revision)}\" readonly></label><br>",
            f"<label>approval_id <input name=\"approval_id\" value=\"{_esc(approval_id)}\" readonly></label><br>",
            "<label>type CONFIRM to apply <input name=\"confirm\" required></label><br>",
            "<button type=\"submit\">apply writeback</button>",
            "</form>",
        ]
        return self._render(200, "\n".join(body), session=session, session_created=created)

    def _writeback_apply(
        self, request: V2WebRequest, session: V2LocalSessionV2, created: bool
    ) -> V2WebResponse:
        try:
            parsed = V2_WRITEBACK_APPLY_FORM.parse(request.form)
        except V2FormError:
            return self._form_error()
        run_id = str(parsed["run_id"])
        candidate_id = str(parsed["candidate_id"])
        candidate_revision = int(parsed["candidate_revision"])
        if self._shell.run_detail(run_id) is None:
            return self._static_error(404, "Unknown run")
        current = self._shell.candidate_revision(run_id, candidate_id)
        if current is None:
            return self._static_error(404, "Unknown candidate for this run")
        if current != candidate_revision:
            return self._binding_error("STALE_CANDIDATE_REVISION")
        try:
            outcome = self._shell.request_writeback(
                run_id=run_id,
                candidate_id=candidate_id,
                candidate_revision=candidate_revision,
                approval_id=str(parsed["approval_id"]),
            )
        except V2ShellError as exc:
            return self._shell_error(exc)
        status = 200 if outcome.status == "COMMITTED" else 409
        body = [
            "<h1>writeback outcome</h1>",
            f"<p>writeback: {_esc(outcome.status)}</p>",
            f"<p>transaction_id: {_esc(outcome.transaction_id if outcome.transaction_id is not None else '-')}</p>",
            f"<p>{_esc(outcome.message)}</p>",
        ]
        return self._render(status, "\n".join(body), session=session, session_created=created)

    def _recovery_apply(
        self, request: V2WebRequest, session: V2LocalSessionV2, created: bool
    ) -> V2WebResponse:
        try:
            parsed = V2_RECOVERY_APPLY_FORM.parse(request.form)
        except V2FormError:
            return self._form_error()
        transaction_id = str(parsed["transaction_id"])
        try:
            outcome = self._shell.recovery_apply(transaction_id)
        except V2ShellError as exc:
            return self._shell_error(exc)
        status = 200 if outcome.status == "APPLIED" else 409
        body = [
            "<h1>recovery outcome</h1>",
            f"<p>recovery: {_esc(outcome.status)}</p>",
            f"<p>transaction_id: {_esc(outcome.transaction_id)}</p>",
            f"<p>{_esc(outcome.message)}</p>",
        ]
        return self._render(status, "\n".join(body), session=session, session_created=created)

    # ------------------------------------------------------------------
    # bounded error rendering
    # ------------------------------------------------------------------

    def _csrf_input(self, session: V2LocalSessionV2) -> str:
        return (
            "<input type=\"hidden\" name=\"csrf_token\" "
            f"value=\"{_esc(session.csrf_token)}\">"
        )

    def _render(
        self,
        status: int,
        body_html: str,
        *,
        session: V2LocalSessionV2 | None = None,
        session_created: bool = False,
    ) -> V2WebResponse:
        headers = {
            "Content-Type": "text/html; charset=utf-8",
            **v2_security_headers(),
        }
        if session_created and session is not None:
            headers["Set-Cookie"] = (
                f"{self._config.session_cookie_name}={session.session_id}; "
                f"Path=/; HttpOnly; SameSite=Strict; "
                f"Max-Age={self._sessions.session_ttl_seconds}"
            )
        return V2WebResponse(status, headers, body_html)

    def _security_rejection(self, error_code: str) -> V2WebResponse:
        status = v2_request_status(error_code)
        payload = v2_request_rejection_payload(error_code)
        body = (
            "<h1>Request rejected</h1>"
            f"<p>error_code: {_esc(payload['error_code'])}</p>"
            f"<p>{_esc(payload['message'])}</p>"
            f"<p>{_esc(payload['next_step'])}</p>"
        )
        headers = {
            "Content-Type": "text/html; charset=utf-8",
            **v2_security_headers(),
        }
        return V2WebResponse(status, headers, body)

    def _static_error(self, status: int, title: str) -> V2WebResponse:
        headers = {
            "Content-Type": "text/html; charset=utf-8",
            **v2_security_headers(),
        }
        if status == 405:
            headers["Allow"] = "GET, POST"
        return V2WebResponse(status, headers, f"<h1>{_esc(title)}</h1>")

    def _form_error(self) -> V2WebResponse:
        return self._static_error(400, "Form rejected")

    def _binding_error(self, code: str) -> V2WebResponse:
        body = (
            "<h1>Binding rejected</h1>"
            f"<p>error_code: {_esc(code)}</p>"
            "<p>The referenced run, candidate, or revision did not match "
            "the current control-plane state; no mutation was performed.</p>"
        )
        headers = {
            "Content-Type": "text/html; charset=utf-8",
            **v2_security_headers(),
        }
        return V2WebResponse(409, headers, body)

    def _shell_error(self, exc: V2ShellError) -> V2WebResponse:
        status = _SHELL_ERROR_STATUS.get(exc.code, 500)
        body = (
            "<h1>Local operation rejected</h1>"
            f"<p>error_code: {_esc(exc.code)}</p>"
            f"<p>{_esc(str(exc))}</p>"
        )
        headers = {
            "Content-Type": "text/html; charset=utf-8",
            **v2_security_headers(),
        }
        return V2WebResponse(status, headers, body)


__all__ = ["V2LocalWebApp", "V2WebRequest", "V2WebResponse"]

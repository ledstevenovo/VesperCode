"""Route B / B3: the local v2 WebUI application contract.

``V2LocalWebApp`` is the framework-agnostic, standard-library-only
route surface of the v2 local WebUI: a closed route table, the fixed
security order (host, session resolution, origin, CSRF) before any form
parsing or domain call, allowlisted typed forms whose failures reject
with zero shell calls, binding pre-checks that keep unknown, stale, or
mismatched run/candidate/revision forms away from every mutation, and
HTML rendering that escapes every projected value and never carries a
secret.  These tests drive the app purely through ``handle`` with an
injectable recording shell -- no sockets, no FastAPI, no network.
"""

from __future__ import annotations

import re
import unittest
from dataclasses import dataclass, field

from vespercode.contracts.v2_writeback import (
    RecoveryItemV2,
    RecoveryOutcomeV2,
    RecoveryPreviewV2,
    WritebackOutcomeV2,
)
from vespercode.credentials.v2_port import V2CredentialStatus
from vespercode.shell_v2 import (
    V2DisclosureGrantSummaryV2,
    V2RunStartOutcomeV2,
    V2RunSummaryV2,
    V2ShellError,
)
from vespercode.web.v2_app import V2LocalWebApp, V2WebRequest, V2WebResponse
from vespercode.web.v2_security import (
    V2LocalSecurityConfig,
    V2LocalSessionManager,
)

_CSRF_RE = re.compile(r'name="csrf_token" value="([0-9a-f]{64})"')


class _FixedClock:
    """A deterministic epoch-milliseconds clock for app-level tests."""

    def __init__(self, now_ms: int) -> None:
        self.now_ms = now_ms

    def __call__(self) -> int:
        return self.now_ms

HOST = "127.0.0.1:8766"
ORIGIN = "http://127.0.0.1:8766"


@dataclass
class RecordingShell:
    """A deterministic fake of the local shell surface."""

    runs: list[V2RunSummaryV2] = field(default_factory=list)
    revisions: dict[tuple[str, str], int] = field(default_factory=dict)
    credentials: dict[str, V2CredentialStatus] = field(default_factory=dict)
    grants: list[V2DisclosureGrantSummaryV2] = field(default_factory=list)
    pending: list[str] = field(default_factory=list)
    start_outcomes: list[V2RunStartOutcomeV2] = field(default_factory=list)
    start_error: V2ShellError | None = None
    calls: list[tuple[str, tuple, dict]] = field(default_factory=list)

    def _record(self, name: str, *args, **kwargs) -> None:
        self.calls.append((name, args, kwargs))

    def recent_runs(self, limit: int = 50):
        self._record("recent_runs", limit=limit)
        return tuple(self.runs)

    def run_detail(self, run_id: str):
        self._record("run_detail", run_id)
        return next((run for run in self.runs if run.run_id == run_id), None)

    def candidate_revision(self, run_id: str, candidate_id: str):
        self._record("candidate_revision", run_id, candidate_id)
        return self.revisions.get((run_id, candidate_id))

    def start_run(self, task: str):
        self._record("start_run", task)
        if self.start_error is not None:
            raise self.start_error
        return self.start_outcomes.pop(0)

    def create_writeback_approval(
        self, *, run_id, candidate_id, candidate_revision
    ):
        self._record(
            "create_writeback_approval",
            run_id=run_id,
            candidate_id=candidate_id,
            candidate_revision=candidate_revision,
        )
        return "approval-recorded"

    def request_writeback(
        self, *, run_id, candidate_id, candidate_revision, approval_id
    ):
        self._record(
            "request_writeback",
            run_id=run_id,
            candidate_id=candidate_id,
            candidate_revision=candidate_revision,
            approval_id=approval_id,
        )
        return WritebackOutcomeV2("COMMITTED", "tx-1", "1 write(s) committed")

    def pending_transaction_ids(self):
        self._record("pending_transaction_ids")
        return tuple(self.pending)

    def recovery_preview(self, transaction_id: str):
        self._record("recovery_preview", transaction_id)
        if transaction_id not in self.pending:
            raise V2ShellError("UNKNOWN_TRANSACTION", "unknown transaction")
        return RecoveryPreviewV2(
            "tx-1",
            "UNRESOLVED",
            (RecoveryItemV2(0, "src/a.py", "CREATE", "PENDING"),),
            False,
        )

    def recovery_apply(self, transaction_id: str):
        self._record("recovery_apply", transaction_id)
        if transaction_id not in self.pending:
            raise V2ShellError("UNKNOWN_TRANSACTION", "unknown transaction")
        return RecoveryOutcomeV2("APPLIED", transaction_id, "applied")

    def credential_status(self, provider: str):
        self._record("credential_status", provider)
        return self.credentials.get(
            provider,
            V2CredentialStatus(provider=provider, configured=False, updated_at=None),
        )

    def disclosure_grant_summaries(self, limit: int = 100):
        self._record("disclosure_grant_summaries", limit=limit)
        return tuple(self.grants)


def _make_shell() -> RecordingShell:
    shell = RecordingShell(
        runs=[V2RunSummaryV2("run-1", "SUCCEEDED", None, 3)],
        revisions={("run-1", "candidate-1"): 0},
        credentials={
            "openai": V2CredentialStatus(
                provider="openai", configured=True, updated_at="2026-01-01T00:00:00Z"
            )
        },
        grants=[
            V2DisclosureGrantSummaryV2(
                grant_id="grant-1",
                disclosure_id="disclosure-1",
                run_id="run-1",
                status="PENDING",
                expires_at="2999-01-01T00:00:00+00:00",
                byte_budget=1024,
                consumed_bytes=0,
            )
        ],
        pending=["tx-1"],
        start_outcomes=[
            V2RunStartOutcomeV2(
                run_id="run-9",
                candidate_id="candidate-9",
                candidate_revision=0,
                loop_status="SUCCEEDED",
                stop_reason="DONE",
                turns=2,
            )
        ],
    )
    return shell


class V2LocalWebAppTests(unittest.TestCase):
    def setUp(self) -> None:
        self.shell = _make_shell()
        self.app = V2LocalWebApp(self.shell)
        self.session = self._establish_session()

    # -- helpers -----------------------------------------------------------

    def _establish_session(self) -> tuple[dict[str, str], str]:
        response = self.app.handle(
            V2WebRequest(method="GET", path="/", headers={"host": HOST})
        )
        self.assertEqual(response.status, 200)
        cookie_header = response.headers.get("Set-Cookie", "")
        match = re.match(
            r"vespercode_v2_session=([0-9a-f]{64}); Path=/; HttpOnly; "
            r"SameSite=Strict; Max-Age=\d+",
            cookie_header,
        )
        assert match is not None, cookie_header
        csrf_match = _CSRF_RE.search(response.body)
        assert csrf_match is not None, "no csrf token embedded in the home page"
        # The session-establishing GET is setup, not the behavior under
        # test: the zero-call assertions below measure from here.
        self.shell.calls.clear()
        return (
            {"vespercode_v2_session": match.group(1)},
            csrf_match.group(1),
        )

    def _post(
        self,
        path: str,
        form: dict[str, str],
        *,
        cookies: dict[str, str] | None = None,
        csrf: str | None = "session",
        host: str = HOST,
        origin: str | None = ORIGIN,
    ) -> V2WebResponse:
        effective = dict(form)
        if csrf == "session":
            # The default every ordinary browser flow carries: the CSRF
            # synchronizer token embedded in the session's pages.
            effective["csrf_token"] = self.session[1]
        elif csrf is not None:
            effective["csrf_token"] = csrf
        headers = {"host": host}
        if origin is not None:
            headers["origin"] = origin
        cookies = self.session[0] if cookies is None else cookies
        return self.app.handle(
            V2WebRequest(
                method="POST",
                path=path,
                headers=headers,
                cookies=cookies,
                form=effective,
            )
        )

    def _mutation_calls(self) -> list[str]:
        mutations = {
            "start_run",
            "create_writeback_approval",
            "request_writeback",
            "recovery_apply",
        }
        return [name for name, _, _ in self.shell.calls if name in mutations]

    # -- routing -----------------------------------------------------------

    def test_unknown_paths_and_wrong_methods_are_closed(self) -> None:
        response = self.app.handle(
            V2WebRequest(method="GET", path="/nope", headers={"host": HOST})
        )
        self.assertEqual(response.status, 404)
        self.assertIn("Content-Security-Policy", response.headers)

        response = self.app.handle(
            V2WebRequest(method="POST", path="/runs", headers={"host": HOST})
        )
        self.assertEqual(response.status, 405)
        self.assertEqual(self.shell.calls, [])

    # -- security before parsing and domain ----------------------------------

    def test_non_loopback_host_is_rejected_before_anything(self) -> None:
        response = self._post(
            "/writeback/approve",
            {},
            host="192.168.1.5:8766",
            origin=None,
            csrf=None,
        )
        self.assertEqual(response.status, 403)
        self.assertIn("HOST_REJECTED", response.body)
        self.assertEqual(self.shell.calls, [])

    def test_state_changes_require_a_session(self) -> None:
        response = self._post("/writeback/approve", {}, cookies={})
        self.assertEqual(response.status, 401)
        self.assertIn("SESSION_MISSING", response.body)
        self.assertEqual(self.shell.calls, [])

    def test_state_changes_require_origin_and_csrf(self) -> None:
        response = self._post(
            "/writeback/approve", {}, origin=None, csrf=None
        )
        self.assertEqual(response.status, 403)
        self.assertIn("ORIGIN_MISSING", response.body)
        self.assertEqual(self.shell.calls, [])

        response = self._post("/writeback/approve", {}, csrf="ab" * 32)
        self.assertEqual(response.status, 403)
        self.assertIn("CSRF_REJECTED", response.body)
        self.assertEqual(self.shell.calls, [])

    def test_forged_session_cookie_cannot_reach_domain_calls(self) -> None:
        # A well-formed but unregistered session value (a forged session
        # object's id and CSRF token) rejects at the SESSION check with
        # zero shell calls of any kind.
        forged_id = "e" * 64
        response = self.app.handle(
            V2WebRequest(
                method="POST",
                path="/writeback/approve",
                headers={"host": HOST, "origin": ORIGIN},
                cookies={"vespercode_v2_session": forged_id},
                form={
                    "run_id": "run-1",
                    "candidate_id": "candidate-1",
                    "candidate_revision": "0",
                    "confirm": "CONFIRM",
                    "csrf_token": "f" * 64,
                },
            )
        )
        self.assertEqual(response.status, 401)
        self.assertIn("SESSION_INVALID", response.body)
        self.assertEqual(self.shell.calls, [])

    def test_expired_session_cannot_reach_domain_calls(self) -> None:
        clock = _FixedClock(1_000_000)
        manager = V2LocalSessionManager(
            V2LocalSecurityConfig(), clock=clock
        )
        app = V2LocalWebApp(self.shell, session_manager=manager)
        home = app.handle(
            V2WebRequest(method="GET", path="/", headers={"host": HOST})
        )
        self.assertEqual(home.status, 200)
        cookie_match = re.match(
            r"vespercode_v2_session=([0-9a-f]{64});",
            home.headers.get("Set-Cookie", ""),
        )
        csrf_match = _CSRF_RE.search(home.body)
        assert cookie_match is not None and csrf_match is not None
        # The session-establishing GET is setup, not the behavior under
        # test: measure the mutation's zero-call property from here.
        self.shell.calls.clear()
        # Expire the session at the manager's clock, then attempt a
        # mutation with the (now stale) cookie, a matching Origin, and
        # the session's own CSRF token.
        clock.now_ms = 1_000_000 + 8 * 60 * 60 * 1000 + 1
        response = app.handle(
            V2WebRequest(
                method="POST",
                path="/writeback/approve",
                headers={"host": HOST, "origin": ORIGIN},
                cookies={
                    "vespercode_v2_session": cookie_match.group(1)
                },
                form={
                    "run_id": "run-1",
                    "candidate_id": "candidate-1",
                    "candidate_revision": "0",
                    "confirm": "CONFIRM",
                    "csrf_token": csrf_match.group(1),
                },
            )
        )
        self.assertEqual(response.status, 401)
        self.assertIn("SESSION_EXPIRED", response.body)
        self.assertEqual(self.shell.calls, [])

    # -- forms ---------------------------------------------------------------

    def test_malformed_forms_reject_with_zero_shell_calls(self) -> None:
        responses = [
            self._post("/writeback/approve", {"run_id": "run-1"}),  # missing fields
            self._post(
                "/writeback/approve",
                {
                    "run_id": "run-1",
                    "candidate_id": "candidate-1",
                    "candidate_revision": "0",
                    "confirm": "CONFIRM",
                    "surprise": "1",
                },
            ),  # unknown field
            self._post(
                "/writeback/approve",
                {
                    "run_id": "run-1",
                    "candidate_id": "candidate-1",
                    "candidate_revision": "0",
                    "confirm": "yes",
                },
            ),  # wrong confirmation literal
        ]
        for response in responses:
            self.assertEqual(response.status, 400)
        self.assertEqual(self.shell.calls, [])

    def test_unknown_and_mismatched_bindings_never_reach_mutations(self) -> None:
        # Unknown run.
        response = self._post(
            "/writeback/approve",
            {
                "run_id": "run-404",
                "candidate_id": "candidate-1",
                "candidate_revision": "0",
                "confirm": "CONFIRM",
            },
        )
        self.assertEqual(response.status, 404)
        # Candidate owned by a different run.
        response = self._post(
            "/writeback/approve",
            {
                "run_id": "run-2",
                "candidate_id": "candidate-1",
                "candidate_revision": "0",
                "confirm": "CONFIRM",
            },
        )
        self.assertEqual(response.status, 404)
        # Stale revision.
        response = self._post(
            "/writeback/approve",
            {
                "run_id": "run-1",
                "candidate_id": "candidate-1",
                "candidate_revision": "7",
                "confirm": "CONFIRM",
            },
        )
        self.assertEqual(response.status, 409)
        self.assertIn("STALE_CANDIDATE_REVISION", response.body)
        self.assertEqual(self._mutation_calls(), [])

    def test_writeback_approve_creates_the_explicit_approval(self) -> None:
        response = self._post(
            "/writeback/approve",
            {
                "run_id": "run-1",
                "candidate_id": "candidate-1",
                "candidate_revision": "0",
                "confirm": "CONFIRM",
            },
        )
        self.assertEqual(response.status, 200)
        self.assertIn("approval-recorded", response.body)
        self.assertEqual(
            self._mutation_calls(), ["create_writeback_approval"]
        )

    def test_writeback_apply_projects_the_outcome(self) -> None:
        response = self._post(
            "/writeback/apply",
            {
                "run_id": "run-1",
                "candidate_id": "candidate-1",
                "candidate_revision": "0",
                "approval_id": "approval-recorded",
                "confirm": "CONFIRM",
            },
        )
        self.assertEqual(response.status, 200)
        self.assertIn("COMMITTED", response.body)
        self.assertEqual(self._mutation_calls(), ["request_writeback"])

    def test_run_start_projects_the_outcome_or_the_closed_failure(self) -> None:
        response = self._post(
            "/run/start", {"task": "repair the example", "confirm": "CONFIRM"}
        )
        self.assertEqual(response.status, 200)
        self.assertIn("run-9", response.body)
        self.assertIn("SUCCEEDED", response.body)

        self.shell.start_error = V2ShellError(
            "NO_LLM_BOUNDARY", "no v2 LLM boundary is composed"
        )
        response = self._post(
            "/run/start", {"task": "repair the example", "confirm": "CONFIRM"}
        )
        self.assertEqual(response.status, 503)
        self.assertIn("NO_LLM_BOUNDARY", response.body)

    # -- recovery ------------------------------------------------------------

    def test_recovery_pages_project_pending_and_preview(self) -> None:
        response = self.app.handle(
            V2WebRequest(
                method="GET", path="/recovery", headers={"host": HOST}
            )
        )
        self.assertEqual(response.status, 200)
        self.assertIn("tx-1", response.body)

        response = self.app.handle(
            V2WebRequest(
                method="GET",
                path="/recovery/preview",
                headers={"host": HOST},
                form={"transaction_id": "tx-1"},
            )
        )
        self.assertEqual(response.status, 200)
        self.assertIn("src/a.py", response.body)
        self.assertIn("PENDING", response.body)

    def test_recovery_preview_rejects_malformed_and_unknown(self) -> None:
        response = self.app.handle(
            V2WebRequest(
                method="GET",
                path="/recovery/preview",
                headers={"host": HOST},
                form={"transaction_id": "../evil"},
            )
        )
        self.assertEqual(response.status, 400)
        self.assertEqual(self.shell.calls, [])

        response = self.app.handle(
            V2WebRequest(
                method="GET",
                path="/recovery/preview",
                headers={"host": HOST},
                form={"transaction_id": "tx-404"},
            )
        )
        # run_detail fallback marks unknown transactions 404: the fake has no
        # such transaction and its recovery_preview was never called.
        self.assertEqual(response.status, 404)

    def test_recovery_apply_is_an_explicit_confirmed_mutation(self) -> None:
        response = self._post(
            "/recovery/apply",
            {"transaction_id": "tx-1", "confirm": "CONFIRM"},
        )
        self.assertEqual(response.status, 200)
        self.assertIn("APPLIED", response.body)
        self.assertEqual(self._mutation_calls(), ["recovery_apply"])

        # Without the confirmation literal the mutation never happens.
        self.shell.calls.clear()
        response = self._post("/recovery/apply", {"transaction_id": "tx-1"})
        self.assertEqual(response.status, 400)
        self.assertEqual(self._mutation_calls(), [])

    # -- run status projections ----------------------------------------------

    def test_runs_and_run_detail_pages_project_bounded_facts(self) -> None:
        response = self.app.handle(
            V2WebRequest(method="GET", path="/runs", headers={"host": HOST})
        )
        self.assertEqual(response.status, 200)
        self.assertIn("run-1", response.body)
        self.assertIn("SUCCEEDED", response.body)

        response = self.app.handle(
            V2WebRequest(
                method="GET",
                path="/run",
                headers={"host": HOST},
                form={"run_id": "run-1"},
            )
        )
        self.assertEqual(response.status, 200)
        self.assertIn("run-1", response.body)

        response = self.app.handle(
            V2WebRequest(
                method="GET",
                path="/run",
                headers={"host": HOST},
                form={"run_id": "run-404"},
            )
        )
        self.assertEqual(response.status, 404)

    # -- non-revealing credential / disclosure pages --------------------------

    def test_credential_page_projects_no_secret(self) -> None:
        response = self.app.handle(
            V2WebRequest(
                method="GET",
                path="/credentials",
                headers={"host": HOST},
                form={"provider": "openai"},
            )
        )
        self.assertEqual(response.status, 200)
        self.assertIn("openai", response.body)
        self.assertIn("configured", response.body)

    def test_disclosure_page_projects_bounded_control_facts(self) -> None:
        response = self.app.handle(
            V2WebRequest(
                method="GET", path="/disclosures", headers={"host": HOST}
            )
        )
        self.assertEqual(response.status, 200)
        self.assertIn("grant-1", response.body)
        self.assertIn("PENDING", response.body)

    # -- escaping --------------------------------------------------------------

    def test_all_projected_values_are_html_escaped(self) -> None:
        self.shell.runs = [
            V2RunSummaryV2("<script>alert(1)</script>", "SUCCEEDED", None, 3)
        ]
        response = self.app.handle(
            V2WebRequest(method="GET", path="/runs", headers={"host": HOST})
        )
        self.assertEqual(response.status, 200)
        self.assertNotIn("<script>alert(1)</script>", response.body)
        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", response.body)


if __name__ == "__main__":
    unittest.main()

"""Route B / B3: the loopback request-security boundary of the v2 WebUI.

``vespercode.web.v2_security`` is the standard-library-only, framework-
agnostic security boundary of the v2 local WebUI: the closed loopback
security configuration, bounded local sessions with an injectable clock
and token generator, and the fixed-order request authorization
(HOST -> SESSION -> ORIGIN -> CSRF for state changes).  Every rejection
is a stable closed code with a bounded status and payload, and the
response security headers are exact.  Nothing here imports or reuses the
v1 security modules; the v2 boundary is independent code.
"""

from __future__ import annotations

import unittest

from vespercode.web.v2_security import (
    V2_CONTENT_SECURITY_POLICY,
    V2_LOOPBACK_BIND_HOST,
    V2LocalSecurityConfig,
    V2LocalSessionErrorV2,
    V2LocalSessionManager,
    V2LocalSessionV2,
    V2RequestAuthorizationV2,
    authorize_v2_local_request,
    is_v2_loopback_host,
    v2_request_rejection_payload,
    v2_request_status,
    v2_security_headers,
)


class _FixedClock:
    """A deterministic epoch-milliseconds clock."""

    def __init__(self, now_ms: int) -> None:
        self.now_ms = now_ms

    def __call__(self) -> int:
        return self.now_ms


class _FixedTokens:
    """A deterministic token generator (closed 64-hex values)."""

    def __init__(self, *values: str) -> None:
        self._values = list(values)
        self._index = 0

    def __call__(self) -> str:
        value = self._values[self._index % len(self._values)]
        self._index += 1
        return value


def _manager(**overrides) -> V2LocalSessionManager:
    config = V2LocalSecurityConfig()
    parameters: dict[str, object] = {
        "clock": _FixedClock(1_000_000),
        "token_generator": _FixedTokens("a" * 64, "b" * 64, "c" * 64, "d" * 64),
    }
    parameters.update(overrides)
    return V2LocalSessionManager(config, **parameters)  # type: ignore[arg-type]


class V2LocalSecurityConfigTests(unittest.TestCase):
    def test_defaults_are_closed_and_loopback_only(self) -> None:
        config = V2LocalSecurityConfig()
        self.assertEqual(config.host, V2_LOOPBACK_BIND_HOST)
        self.assertEqual(config.host, "127.0.0.1")
        self.assertEqual(config.port, 8766)
        self.assertEqual(config.session_cookie_name, "vespercode_v2_session")
        self.assertEqual(config.csrf_field_name, "csrf_token")

    def test_non_loopback_bind_hosts_reject(self) -> None:
        for bad in ("0.0.0.0", "localhost", "", "127.0.0.2", "::1", "example.com"):
            with self.assertRaises(ValueError):
                V2LocalSecurityConfig(host=bad)

    def test_ports_outside_the_closed_range_reject(self) -> None:
        for bad in (0, -1, 65536, "80", None, 80.5):
            with self.assertRaises(ValueError):
                V2LocalSecurityConfig(port=bad)

    def test_cookie_and_csrf_names_must_be_closed_tokens(self) -> None:
        for bad in ("", "session cookie", "x" * 129, "ids[]"):
            with self.assertRaises(ValueError):
                V2LocalSecurityConfig(session_cookie_name=bad)
            with self.assertRaises(ValueError):
                V2LocalSecurityConfig(csrf_field_name=bad)


class V2LoopbackHostTests(unittest.TestCase):
    def test_accepts_only_loopback_host_headers(self) -> None:
        for accepted in (
            "127.0.0.1",
            "localhost",
            "127.0.0.1:8766",
            "localhost:80",
            "127.0.0.1:1",
            # Incidental surrounding whitespace is stripped, matching
            # ordinary HTTP header token handling.
            " 127.0.0.1 ",
        ):
            self.assertTrue(is_v2_loopback_host(accepted), accepted)
        for rejected in (
            "",
            "192.168.1.5",
            "example.com",
            "127.0.0.2",
            "127.0.0.1:0",
            "127.0.0.1:99999",
            "127.0.0.1:abc",
            "[::1]:8080",
            "::1",
            "localhost:99999",
            "127.0.0.1:",
            "127.0.0.1 8766",
            "127.0.0.1 extra",
        ):
            self.assertFalse(is_v2_loopback_host(rejected), rejected)


class V2LocalSessionManagerTests(unittest.TestCase):
    def test_create_builds_a_bounded_session_with_closed_tokens(self) -> None:
        manager = _manager()
        session = manager.create()
        self.assertIsInstance(session, V2LocalSessionV2)
        self.assertEqual(session.session_id, "a" * 64)
        self.assertEqual(session.csrf_token, "b" * 64)
        self.assertEqual(session.created_at_ms, 1_000_000)
        self.assertEqual(
            session.expires_at_ms,
            1_000_000 + 8 * 60 * 60 * 1000,
        )
        self.assertEqual(manager.session_ttl_seconds, 8 * 60 * 60)

    def test_expiry_is_enforced_by_the_injected_clock(self) -> None:
        clock = _FixedClock(1_000_000)
        manager = _manager(clock=clock)
        session = manager.create()
        self.assertTrue(manager.is_active(session))
        clock.now_ms = 1_000_000 + 8 * 60 * 60 * 1000
        self.assertFalse(manager.is_active(session))

    def test_expired_sessions_are_pruned_and_the_bound_is_enforced(self) -> None:
        clock = _FixedClock(0)
        manager = _manager(clock=clock, max_sessions=2)
        manager.create()
        manager.create()
        with self.assertRaises(V2LocalSessionErrorV2):
            manager.create()
        clock.now_ms = 8 * 60 * 60 * 1000 + 1
        # The expired sessions are pruned first, so creation succeeds again.
        session = manager.create()
        self.assertEqual(manager.get(session.session_id), session)

    def test_malformed_generator_tokens_reject(self) -> None:
        manager = _manager(token_generator=_FixedTokens("not-hex"))
        with self.assertRaises(V2LocalSessionErrorV2):
            manager.create()

    def test_bad_construction_bounds_reject(self) -> None:
        config = V2LocalSecurityConfig()
        with self.assertRaises(V2LocalSessionErrorV2):
            V2LocalSessionManager(config, session_ttl_ms=0)
        with self.assertRaises(V2LocalSessionErrorV2):
            V2LocalSessionManager(config, max_sessions=0)


class V2RequestAuthorizationTests(unittest.TestCase):
    def test_authorized_results_carry_no_rejection(self) -> None:
        result = V2RequestAuthorizationV2(authorized=True)
        self.assertIsNone(result.error_code)
        self.assertIsNone(result.rejected_at)
        with self.assertRaises(ValueError):
            V2RequestAuthorizationV2(authorized=True, error_code="HOST_REJECTED")
        with self.assertRaises(ValueError):
            V2RequestAuthorizationV2(authorized=False, error_code=None)
        with self.assertRaises(ValueError):
            V2RequestAuthorizationV2(authorized=False, rejected_at=None)

    def test_rejected_results_carry_no_session(self) -> None:
        session = V2LocalSessionV2(
            session_id="a" * 64,
            csrf_token="b" * 64,
            created_at_ms=0,
            expires_at_ms=1,
        )
        with self.assertRaises(ValueError):
            V2RequestAuthorizationV2(
                authorized=False,
                error_code="HOST_REJECTED",
                rejected_at="HOST",
                session=session,
            )
        with self.assertRaises(ValueError):
            V2RequestAuthorizationV2(authorized=True, session="not-a-session")
        # An authorized result may carry the resolved live session.
        result = V2RequestAuthorizationV2(authorized=True, session=session)
        self.assertIs(result.session, session)


class VerifyV2LocalRequestTests(unittest.TestCase):
    def setUp(self) -> None:
        self.config = V2LocalSecurityConfig()
        self.manager = _manager()
        self.session = self.manager.create()
        self.cookies = {self.config.session_cookie_name: self.session.session_id}

    def _verify(
        self,
        *,
        method: str = "POST",
        host: str = "127.0.0.1:8766",
        cookie: str | None = "session",
        origin: str | None = "http://127.0.0.1:8766",
        csrf: str | None = "token",
        headers: dict[str, str] | None = None,
    ) -> V2RequestAuthorizationV2:
        effective_headers = {"host": host}
        if origin is not None:
            effective_headers["origin"] = origin
        if headers is not None:
            effective_headers.update(headers)
        cookies = {}
        if cookie == "session":
            cookies = dict(self.cookies)
        elif cookie is not None:
            cookies = {self.config.session_cookie_name: cookie}
        form: dict[str, str] = {}
        if csrf == "token":
            form[self.config.csrf_field_name] = self.session.csrf_token
        elif csrf is not None:
            form[self.config.csrf_field_name] = csrf
        return authorize_v2_local_request(
            method=method,
            headers=effective_headers,
            cookies=cookies,
            form=form,
            session_manager=self.manager,
            config=self.config,
        )

    # -- manager-bound session resolution (the review finding) -------------

    def test_forged_unregistered_session_rejects_before_origin_and_csrf(
        self,
    ) -> None:
        # A forged session object that was never registered in the
        # manager, with its own cookie value and CSRF token, must not
        # authorize: the SESSION check resolves the cookie through the
        # manager itself.  The missing Origin and the forged CSRF token
        # never get a chance to matter: the session check precedes both.
        forged = V2LocalSessionV2(
            session_id="e" * 64,
            csrf_token="f" * 64,
            created_at_ms=1_000_000,
            expires_at_ms=1_000_000 + 8 * 60 * 60 * 1000,
        )
        result = authorize_v2_local_request(
            method="POST",
            headers={"host": "127.0.0.1:8766"},
            cookies={self.config.session_cookie_name: forged.session_id},
            form={self.config.csrf_field_name: forged.csrf_token},
            session_manager=self.manager,
            config=self.config,
        )
        self.assertFalse(result.authorized)
        self.assertEqual(result.error_code, "SESSION_INVALID")
        self.assertEqual(result.rejected_at, "SESSION")
        self.assertIsNone(result.session)

    def test_expired_session_rejects_before_origin_and_csrf(self) -> None:
        # A session that was genuinely registered but whose TTL has
        # passed at the manager's clock rejects with SESSION_EXPIRED,
        # before the Origin and CSRF checks (the Origin is missing here
        # and the CSRF token matches — neither is reached).
        clock = _FixedClock(2_000_000)
        manager = _manager(clock=clock)
        session = manager.create()
        clock.now_ms = 2_000_000 + 8 * 60 * 60 * 1000 + 1
        result = authorize_v2_local_request(
            method="POST",
            headers={"host": "127.0.0.1:8766"},
            cookies={self.config.session_cookie_name: session.session_id},
            form={self.config.csrf_field_name: session.csrf_token},
            session_manager=manager,
            config=self.config,
        )
        self.assertFalse(result.authorized)
        self.assertEqual(result.error_code, "SESSION_EXPIRED")
        self.assertEqual(result.rejected_at, "SESSION")
        self.assertIsNone(result.session)

    def test_valid_session_resolves_from_the_manager(self) -> None:
        # A registered, live session authorizes, and the authorized
        # result carries exactly the manager's session object.
        result = self._verify()
        self.assertTrue(result.authorized)
        self.assertIs(result.session, self.session)

    def test_a_non_manager_session_store_rejects(self) -> None:
        with self.assertRaises(TypeError):
            authorize_v2_local_request(
                method="GET",
                headers={"host": "127.0.0.1:8766"},
                cookies={},
                form={},
                session_manager=object(),  # not a V2LocalSessionManager
                config=self.config,
            )

    # -- fixed check order ------------------------------------------------

    def test_host_is_checked_first(self) -> None:
        result = self._verify(
            host="192.168.1.5:8766", cookie=None, origin=None, csrf=None
        )
        self.assertFalse(result.authorized)
        self.assertEqual(result.rejected_at, "HOST")
        self.assertEqual(result.error_code, "HOST_REJECTED")

    def test_session_is_checked_before_origin_and_csrf(self) -> None:
        result = self._verify(cookie="wrong-cookie", origin=None, csrf=None)
        self.assertFalse(result.authorized)
        self.assertEqual(result.rejected_at, "SESSION")
        self.assertEqual(result.error_code, "SESSION_INVALID")

        result = self._verify(cookie=None, origin=None, csrf=None)
        self.assertEqual(result.error_code, "SESSION_MISSING")

    def test_origin_is_checked_before_csrf_for_state_changes(self) -> None:
        result = self._verify(origin=None, csrf="wrong")
        self.assertFalse(result.authorized)
        self.assertEqual(result.rejected_at, "ORIGIN")
        self.assertEqual(result.error_code, "ORIGIN_MISSING")

        result = self._verify(origin="http://example.com", csrf="wrong")
        self.assertFalse(result.authorized)
        self.assertEqual(result.rejected_at, "ORIGIN")
        self.assertEqual(result.error_code, "ORIGIN_REJECTED")

    def test_csrf_rejects_missing_or_wrong_tokens(self) -> None:
        result = self._verify(csrf=None)
        self.assertFalse(result.authorized)
        self.assertEqual(result.rejected_at, "CSRF")
        self.assertEqual(result.error_code, "CSRF_REJECTED")

        result = self._verify(csrf="wrong-token")
        self.assertEqual(result.error_code, "CSRF_REJECTED")

    def test_a_valid_state_change_authorizes(self) -> None:
        result = self._verify()
        self.assertTrue(result.authorized)
        self.assertIsNone(result.error_code)

    # -- origin binding ---------------------------------------------------

    def test_origin_must_match_the_request_host_and_port(self) -> None:
        self.assertFalse(
            self._verify(origin="https://127.0.0.1:8766").authorized
        )
        self.assertFalse(
            self._verify(origin="http://localhost:8766").authorized
        )
        self.assertFalse(
            self._verify(origin="http://127.0.0.1:9999").authorized
        )
        self.assertFalse(self._verify(origin="http://127.0.0.1").authorized)

    def test_safe_reads_authorize_without_origin_or_csrf(self) -> None:
        result = self._verify(method="GET", origin=None, csrf=None)
        self.assertTrue(result.authorized)

    def test_other_state_changing_methods_require_origin_and_csrf(self) -> None:
        result = self._verify(method="PUT", origin=None, csrf=None)
        self.assertEqual(result.error_code, "ORIGIN_MISSING")


class V2RejectionProjectionTests(unittest.TestCase):
    def test_every_code_has_a_stable_status_and_bounded_payload(self) -> None:
        expected_status = {
            "HOST_REJECTED": 403,
            "SESSION_MISSING": 401,
            "SESSION_INVALID": 401,
            "SESSION_EXPIRED": 401,
            "ORIGIN_MISSING": 403,
            "ORIGIN_REJECTED": 403,
            "CSRF_REJECTED": 403,
        }
        for code, status in expected_status.items():
            self.assertEqual(v2_request_status(code), status)
            payload = v2_request_rejection_payload(code)
            self.assertEqual(
                set(payload), {"error_code", "message", "next_step"}
            )
            self.assertEqual(payload["error_code"], code)
            self.assertTrue(payload["message"])
            self.assertTrue(payload["next_step"])

    def test_unknown_codes_reject(self) -> None:
        with self.assertRaises(KeyError):
            v2_request_status("NOT_A_CODE")


class V2SecurityHeaderTests(unittest.TestCase):
    def test_headers_are_exact_and_closed(self) -> None:
        headers = v2_security_headers()
        self.assertEqual(
            headers["Content-Security-Policy"],
            "default-src 'self'; script-src 'self'; "
            "style-src 'self' 'unsafe-inline'; object-src 'none'; "
            "base-uri 'none'; frame-ancestors 'none'; form-action 'self'",
        )
        self.assertEqual(V2_CONTENT_SECURITY_POLICY, headers["Content-Security-Policy"])
        self.assertEqual(headers["X-Content-Type-Options"], "nosniff")
        self.assertEqual(headers["X-Frame-Options"], "DENY")
        self.assertEqual(headers["Referrer-Policy"], "no-referrer")

    def test_a_valid_nonce_extends_script_src(self) -> None:
        nonce = "aBcD-_1234aBcD-_12"
        headers = v2_security_headers(csp_nonce=nonce)
        csp = headers["Content-Security-Policy"]
        self.assertIn(f"script-src 'self' 'nonce-{nonce}'", csp)
        # The nonce path never widens scripts to unsafe-inline; only the
        # deliberately inline style-src keeps its exception.
        self.assertIn("script-src 'self' 'nonce-", csp)
        self.assertNotIn("script-src 'self' 'unsafe-inline'", csp)

    def test_malformed_nonces_reject(self) -> None:
        with self.assertRaises(ValueError):
            v2_security_headers(csp_nonce="bad nonce!")
        with self.assertRaises(ValueError):
            v2_security_headers(csp_nonce="short")
        with self.assertRaises(ValueError):
            v2_security_headers(csp_nonce="quote-inside")


if __name__ == "__main__":
    unittest.main()

"""Route B / B3: the loopback request-security boundary of the v2 WebUI.

``vespercode.web.v2_security`` is the standard-library-only,
framework-agnostic security boundary of the v2 local WebUI:

- the closed security configuration binds the server to the literal
  loopback host only, with a validated port and exact cookie/CSRF
  field names;
- ``V2LocalSessionManager`` creates bounded local sessions (bounded
  entropy, bounded time-to-live, bounded concurrency) with an injectable
  epoch-milliseconds clock and token generator;
- ``authorize_v2_local_request`` validates every request in one fixed
  order — HOST, then SESSION, then (for state-changing methods only)
  ORIGIN and CSRF — and the first failing check wins, so the
  composition can reject before any route-domain call and report
  exactly which check failed.  The SESSION check is manager-bound and
  self-contained: the cookie value must resolve to a session registered
  in the given session manager, and that session must still be live at
  the manager's clock — a forged or expired session value rejects
  before the Origin and CSRF checks, and an authorized result carries
  the resolved live session.  There is deliberately no session-taking
  authorization variant, so no caller can authorize a request by
  passing an arbitrary session object;
- every rejection is a stable closed code with a bounded HTTP status
  and a bounded payload (code, message, next step), and the response
  security headers carry the exact CSP.

The boundary is independent code: the v1 security module remains
untouched read-only legacy and nothing here imports it.
"""

from __future__ import annotations

import re
import secrets
import time
from dataclasses import dataclass
from typing import Callable, Mapping

V2_LOOPBACK_BIND_HOST = "127.0.0.1"
"""The only host the v2 local server may bind."""

V2_LOOPBACK_HOST_VALUES = frozenset({"127.0.0.1", "localhost"})
"""The only accepted request Host header values (loopback-only)."""

V2_SESSION_COOKIE_NAME = "vespercode_v2_session"
"""The closed local-session cookie name of the v2 WebUI."""

V2_CSRF_FIELD_NAME = "csrf_token"
"""The closed synchronizer-token form field of the v2 WebUI."""

V2_DEFAULT_PORT = 8766
"""The default loopback port of the v2 local WebUI."""

V2_STATE_CHANGING_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})
"""State-changing HTTP methods that require Origin and CSRF checks."""

_DEFAULT_SESSION_TTL_MILLISECONDS = 8 * 60 * 60 * 1000
_DEFAULT_MAX_SESSIONS = 32

_SESSION_TOKEN_RE = re.compile(r"^[0-9a-f]{64}$")
_HOST_PORT_RE = re.compile(r"^(?P<host>[^:]+?)(?::(?P<port>\d{1,5}))?$")
_ORIGIN_RE = re.compile(
    r"^(?P<scheme>[a-z][a-z0-9+.-]*)://(?P<host>[^/:]+)(?::(?P<port>\d{1,5}))?$"
)
_NAME_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
_NONCE_RE = re.compile(r"^[A-Za-z0-9_-]{16,128}$")

V2_REQUEST_ERROR_CODES = (
    "HOST_REJECTED",
    "SESSION_MISSING",
    "SESSION_INVALID",
    "SESSION_EXPIRED",
    "ORIGIN_MISSING",
    "ORIGIN_REJECTED",
    "CSRF_REJECTED",
)
"""The closed stable rejection codes of the v2 loopback boundary."""

_V2_REQUEST_ERRORS: dict[str, tuple[int, str, str]] = {
    "HOST_REJECTED": (
        403,
        "The request Host is not a loopback address.",
        "Open the local WebUI through http://127.0.0.1 only.",
    ),
    "SESSION_MISSING": (
        401,
        "The request carries no local session.",
        "Reopen the home page to establish a local session.",
    ),
    "SESSION_INVALID": (
        401,
        "The local session token is invalid.",
        "Clear the browser session and reopen the home page.",
    ),
    "SESSION_EXPIRED": (
        401,
        "The local session has expired.",
        "Reopen the home page to establish a new session.",
    ),
    "ORIGIN_MISSING": (
        403,
        "The state-changing request carries no Origin header.",
        "Submit operations from the local page only.",
    ),
    "ORIGIN_REJECTED": (
        403,
        "The request Origin is not the local loopback origin.",
        "Use the page served on http://127.0.0.1 to operate.",
    ),
    "CSRF_REJECTED": (
        403,
        "The CSRF token is invalid or missing.",
        "Reload the page and try again.",
    ),
}

V2_CONTENT_SECURITY_POLICY = (
    "default-src 'self'; "
    "script-src 'self'; "
    "style-src 'self' 'unsafe-inline'; "
    "object-src 'none'; "
    "base-uri 'none'; "
    "frame-ancestors 'none'; "
    "form-action 'self'"
)
"""The exact CSP of every v2 local response."""


class V2LocalSessionErrorV2(RuntimeError):
    """One closed local-session failure (bounds or malformed tokens)."""


@dataclass(frozen=True, slots=True)
class V2LocalSecurityConfig:
    """One closed loopback-only security configuration.

    ``host`` is the literal ``127.0.0.1`` — the server can never be told
    to bind anywhere else; ``port`` is validated to the closed range;
    the cookie and CSRF field names are exact closed tokens.
    """

    host: str = V2_LOOPBACK_BIND_HOST
    port: int = V2_DEFAULT_PORT
    session_cookie_name: str = V2_SESSION_COOKIE_NAME
    csrf_field_name: str = V2_CSRF_FIELD_NAME

    def __post_init__(self) -> None:
        if self.host != V2_LOOPBACK_BIND_HOST:
            raise ValueError("the v2 local server binds 127.0.0.1 only")
        if isinstance(self.port, bool) or not isinstance(self.port, int):
            raise ValueError("port must be an integer")
        if not 1 <= self.port <= 65535:
            raise ValueError("port must be between 1 and 65535")
        for name in (self.session_cookie_name, self.csrf_field_name):
            if not isinstance(name, str) or _NAME_RE.fullmatch(name) is None:
                raise ValueError("session cookie and CSRF names must be closed tokens")


@dataclass(frozen=True, slots=True)
class V2LocalSessionV2:
    """One bounded local session identity.

    ``session_id`` and ``csrf_token`` are independent 256-bit hex
    tokens; the timestamps are epoch milliseconds so tests can drive
    expiry through the injectable clock deterministically.
    """

    session_id: str
    csrf_token: str
    created_at_ms: int
    expires_at_ms: int

    def __post_init__(self) -> None:
        for token in (self.session_id, self.csrf_token):
            if not isinstance(token, str) or _SESSION_TOKEN_RE.fullmatch(token) is None:
                raise V2LocalSessionErrorV2("session tokens must be 64 hex chars")
        for stamp in (self.created_at_ms, self.expires_at_ms):
            if isinstance(stamp, bool) or not isinstance(stamp, int) or stamp < 0:
                raise V2LocalSessionErrorV2(
                    "session timestamps must be non-negative integers"
                )
        if self.expires_at_ms <= self.created_at_ms:
            raise V2LocalSessionErrorV2("session expiry must follow creation")


def _default_clock() -> int:
    return int(time.time() * 1000)


def _random_hex_token() -> str:
    return secrets.token_hex(32)


class V2LocalSessionManager:
    """Create and resolve bounded local sessions.

    Every created session carries fresh 256-bit tokens, expires after
    the bounded time-to-live, and the number of concurrently active
    sessions is bounded; expired sessions are pruned at ``create`` so
    the bound is never exhausted by stale sessions.  The clock and the
    token generator are injectable for deterministic tests.
    """

    def __init__(
        self,
        config: V2LocalSecurityConfig,
        *,
        session_ttl_ms: int = _DEFAULT_SESSION_TTL_MILLISECONDS,
        max_sessions: int = _DEFAULT_MAX_SESSIONS,
        clock: Callable[[], int] | None = None,
        token_generator: Callable[[], str] | None = None,
    ) -> None:
        if not isinstance(config, V2LocalSecurityConfig):
            raise TypeError("config must be a V2LocalSecurityConfig")
        if isinstance(session_ttl_ms, bool) or not isinstance(session_ttl_ms, int):
            raise V2LocalSessionErrorV2("session TTL must be an integer")
        if session_ttl_ms <= 0:
            raise V2LocalSessionErrorV2("session TTL must be positive")
        if isinstance(max_sessions, bool) or not isinstance(max_sessions, int):
            raise V2LocalSessionErrorV2("max sessions must be an integer")
        if max_sessions <= 0:
            raise V2LocalSessionErrorV2("max sessions must be positive")
        self._config = config
        self._session_ttl_ms = session_ttl_ms
        self._max_sessions = max_sessions
        self._clock = clock if clock is not None else _default_clock
        self._token_generator = (
            token_generator if token_generator is not None else _random_hex_token
        )
        self._sessions: dict[str, V2LocalSessionV2] = {}

    @property
    def session_ttl_seconds(self) -> int:
        """The session TTL in seconds (the cookie max-age)."""

        return self._session_ttl_ms // 1000

    def __len__(self) -> int:
        return len(self._sessions)

    def create(self) -> V2LocalSessionV2:
        """Create one bounded fresh local session (pruning expired first)."""

        self._prune_expired()
        if len(self._sessions) >= self._max_sessions:
            raise V2LocalSessionErrorV2(
                f"local session limit reached ({self._max_sessions})"
            )
        session_id = self._token_generator()
        csrf_token = self._token_generator()
        now_ms = self._clock()
        session = V2LocalSessionV2(
            session_id=session_id,
            csrf_token=csrf_token,
            created_at_ms=now_ms,
            expires_at_ms=now_ms + self._session_ttl_ms,
        )
        self._sessions[session.session_id] = session
        return session

    def get(self, session_id: str) -> V2LocalSessionV2 | None:
        """Resolve one session by its exact token (or None when unknown)."""

        if not isinstance(session_id, str):
            return None
        return self._sessions.get(session_id)

    def is_active(self, session: V2LocalSessionV2) -> bool:
        """Whether the session has not expired at the current clock."""

        return session.expires_at_ms > self._clock()

    def _prune_expired(self) -> None:
        now_ms = self._clock()
        expired = [
            session_id
            for session_id, session in self._sessions.items()
            if session.expires_at_ms <= now_ms
        ]
        for session_id in expired:
            del self._sessions[session_id]


@dataclass(frozen=True, slots=True)
class V2RequestAuthorizationV2:
    """One closed local request authorization result.

    An authorized result carries no rejection and may carry the live
    session the manager resolved for the request; a rejected result
    always carries the stable error code and the exact check that
    rejected it, and never carries a session.
    """

    authorized: bool
    error_code: str | None = None
    rejected_at: str | None = None
    session: "V2LocalSessionV2 | None" = None

    def __post_init__(self) -> None:
        if self.authorized and (
            self.error_code is not None or self.rejected_at is not None
        ):
            raise ValueError("authorized results carry no rejection")
        if not self.authorized and (
            self.error_code is None or self.rejected_at is None
        ):
            raise ValueError("rejected results carry a code and a check")
        if self.session is not None and not isinstance(self.session, V2LocalSessionV2):
            raise ValueError("session must be a V2LocalSessionV2")
        if not self.authorized and self.session is not None:
            raise ValueError("rejected results carry no session")


def _port_suffix_is_valid(port: str | None) -> bool:
    if port is None:
        return True
    try:
        return 1 <= int(port) <= 65535
    except ValueError:
        return False


def is_v2_loopback_host(host_header: str) -> bool:
    """Whether one Host header is a closed loopback value.

    Only ``127.0.0.1`` and ``localhost`` with an optional numeric port
    in the closed 1..65535 range are accepted; IPv6 literals, DNS
    names, empty values, and out-of-range ports are never loopback.
    """

    if not isinstance(host_header, str):
        return False
    value = host_header.strip()
    if not value or value.count(":") > 1:
        return False
    match = _HOST_PORT_RE.fullmatch(value)
    if match is None:
        return False
    if not _port_suffix_is_valid(match.group("port")):
        return False
    return match.group("host") in V2_LOOPBACK_HOST_VALUES


def _split_host_port(host_header: str) -> tuple[str, str | None] | None:
    value = host_header.strip()
    if value.count(":") > 1:
        return None
    match = _HOST_PORT_RE.fullmatch(value)
    if match is None or not _port_suffix_is_valid(match.group("port")):
        return None
    return match.group("host"), match.group("port")


def _is_loopback_origin(origin: str, host_header: str) -> bool:
    """Whether one state-change Origin matches the request's own Host.

    The Origin must be ``http`` (the loopback server has no TLS), the
    origin host must be a loopback value, and the origin host and port
    must equal the request's own (already validated loopback) Host — a
    browser cross-origin request cannot control the Host header, so any
    difference rejects.
    """

    match = _ORIGIN_RE.fullmatch(origin)
    if match is None:
        return False
    if match.group("scheme") != "http":
        return False
    if match.group("host") not in V2_LOOPBACK_HOST_VALUES:
        return False
    host_parts = _split_host_port(host_header)
    if host_parts is None:
        return False
    host_hostname, host_port = host_parts
    if match.group("host") != host_hostname:
        return False
    if match.group("port") != host_port:
        return False
    return True


def _rejected(code: str, check: str) -> V2RequestAuthorizationV2:
    return V2RequestAuthorizationV2(
        authorized=False, error_code=code, rejected_at=check
    )


def authorize_v2_local_request(
    *,
    method: str,
    headers: Mapping[str, str],
    cookies: Mapping[str, str],
    form: Mapping[str, str],
    session_manager: V2LocalSessionManager,
    config: V2LocalSecurityConfig,
) -> V2RequestAuthorizationV2:
    """Authorize one local request through the session manager.

    The order is always HOST -> SESSION -> (state changes only) ORIGIN
    -> CSRF, and the first failing check wins, so the composition can
    reject before any route-domain call and report exactly which check
    failed.  Safe reads never require Origin or CSRF.

    The SESSION check is manager-bound and self-contained: the cookie
    value MUST resolve to a session registered in the given
    ``V2LocalSessionManager``, and that session must still be live at
    the manager's clock.  A forged session value — a well-formed id
    that was never registered, or a session whose time-to-live has
    passed — rejects with ``SESSION_INVALID``/``SESSION_EXPIRED``
    before the Origin and CSRF checks and before any domain call.
    Cookie equality with the resolved session holds by construction,
    because the manager resolves the session from the exact cookie
    value.  There is deliberately no session-taking authorization
    variant: a caller cannot pass an arbitrary session object, so a
    forged or expired session cannot be authorized even with a
    matching cookie and CSRF token.  An authorized result carries the
    resolved live session; a rejected result carries none.

    The CSRF token travels in the closed form field so plain HTML
    forms (no client scripts) stay protected by the synchronizer-token
    rule.
    """

    if not isinstance(session_manager, V2LocalSessionManager):
        raise TypeError("session_manager must be a V2LocalSessionManager")
    if not isinstance(config, V2LocalSecurityConfig):
        raise TypeError("config must be a V2LocalSecurityConfig")
    if not is_v2_loopback_host(headers.get("host", "")):
        return _rejected("HOST_REJECTED", "HOST")
    cookie_value = cookies.get(config.session_cookie_name)
    if cookie_value is None:
        return _rejected("SESSION_MISSING", "SESSION")
    session = session_manager.get(cookie_value)
    if session is None:
        return _rejected("SESSION_INVALID", "SESSION")
    if not session_manager.is_active(session):
        return _rejected("SESSION_EXPIRED", "SESSION")
    if method in V2_STATE_CHANGING_METHODS:
        origin = headers.get("origin")
        if origin is None:
            return _rejected("ORIGIN_MISSING", "ORIGIN")
        if not _is_loopback_origin(origin, headers.get("host", "")):
            return _rejected("ORIGIN_REJECTED", "ORIGIN")
        csrf_token = form.get(config.csrf_field_name)
        if csrf_token is None or csrf_token != session.csrf_token:
            return _rejected("CSRF_REJECTED", "CSRF")
    return V2RequestAuthorizationV2(authorized=True, session=session)


def v2_request_status(error_code: str) -> int:
    """One stable HTTP status for a closed rejection code."""

    return _V2_REQUEST_ERRORS[error_code][0]


def v2_request_rejection_payload(error_code: str) -> dict[str, str]:
    """One stable, non-leaking rejection payload: code, reason, next step."""

    _, message, next_step = _V2_REQUEST_ERRORS[error_code]
    return {
        "error_code": error_code,
        "message": message,
        "next_step": next_step,
    }


def v2_security_headers(csp_nonce: str | None = None) -> dict[str, str]:
    """The exact CSP and response security headers of every response.

    When a per-request nonce is supplied it is inserted into
    ``script-src`` (never ``unsafe-inline``); the nonce must be a
    closed token form so it can never inject into the header.  The
    headers only ever ADD to a response — status and body are
    untouched, so a downstream rejection keeps its exact form.
    """

    if csp_nonce is not None and _NONCE_RE.fullmatch(csp_nonce) is None:
        raise ValueError("CSP nonce must be a closed token form")
    csp = V2_CONTENT_SECURITY_POLICY
    if csp_nonce is not None:
        csp = csp.replace("script-src 'self'", f"script-src 'self' 'nonce-{csp_nonce}'")
    return {
        "Content-Security-Policy": csp,
        "X-Content-Type-Options": "nosniff",
        "X-Frame-Options": "DENY",
        "Referrer-Policy": "no-referrer",
    }


__all__ = [
    "V2_CONTENT_SECURITY_POLICY",
    "V2_CSRF_FIELD_NAME",
    "V2_LOOPBACK_BIND_HOST",
    "V2_LOOPBACK_HOST_VALUES",
    "V2_DEFAULT_PORT",
    "V2LocalSecurityConfig",
    "V2LocalSessionErrorV2",
    "V2LocalSessionManager",
    "V2LocalSessionV2",
    "V2_SESSION_COOKIE_NAME",
    "V2_STATE_CHANGING_METHODS",
    "V2RequestAuthorizationV2",
    "V2_REQUEST_ERROR_CODES",
    "authorize_v2_local_request",
    "is_v2_loopback_host",
    "v2_request_rejection_payload",
    "v2_request_status",
    "v2_security_headers",
]

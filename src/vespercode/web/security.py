"""T28.1 legacy step 28.A: loopback request-security boundary.

``LocalWebSecurityConfigV1`` closes the server binding to the literal
loopback host and validates the port; ``LocalSessionManager`` creates
bounded local sessions (bounded entropy, bounded time-to-live, bounded
concurrency); and ``verify_local_request`` validates, in one fixed order
(HOST -> SESSION -> ORIGIN -> CSRF for state changes), every local
request before any route-domain call (GREEN-1).  Rejections are stable
closed codes with user-understandable reasons and next steps (SPEC
§4.9 local mode, §5.3, §5.5 WebUI threat; Registry row 28.A), and
``local_response_security_headers`` attaches the exact CSP and response
security headers to every response without touching its status or body
(GREEN-2).  Domain repositories, credentials, Docker, recovery bodies,
templates, assets, CLI parsing, and server launch remain out of scope
(GREEN-4/Boundary): the security boundary owns authorization ordering
and response headers only.
"""

from __future__ import annotations

import re
import secrets
from typing import Annotated, Callable, Final, Literal, TypeAlias

from fastapi import Request
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    Strict,
    StrictBool,
    StrictStr,
    model_validator,
)

from src.vespercode.canonical.clock import ClockV1, SystemClockV1
from src.vespercode.canonical.timestamp_v1 import CanonicalTimestampV1

LOOPBACK_HOST_VALUES_V1: Final[frozenset[str]] = frozenset({"127.0.0.1", "localhost"})
"""The only accepted request Host values (loopback-only, SPEC §4.9)."""

_STATE_CHANGING_METHODS_V1: Final[frozenset[str]] = frozenset(
    {"POST", "PUT", "PATCH", "DELETE"}
)
"""State-changing HTTP methods that require the fixed Origin then CSRF
checks (safe reads never do)."""

_DEFAULT_SESSION_TTL_MILLISECONDS: Final[int] = 8 * 60 * 60 * 1000
"""The default local-session time-to-live (8 hours, bounded)."""

_DEFAULT_MAX_SESSIONS: Final[int] = 32
"""The default bound on concurrently active local sessions."""

_DEFAULT_SESSION_TOKEN_HEX_LENGTH: Final[int] = 64
"""The fixed entropy bound of one session/CSRF token (32 random bytes)."""

_SESSION_TOKEN_RE: Final = re.compile(r"^[0-9a-f]{64}$")
"""The closed token form every created session token must have."""

_HOST_PORT_RE: Final = re.compile(r"^(?P<host>[^:]+?)(?::(?P<port>\d{1,5}))?$")
"""One loopback Host header form: ``host`` with an optional numeric port."""

_ORIGIN_RE: Final = re.compile(
    r"^(?P<scheme>[a-z][a-z0-9+.-]*)://(?P<host>[^/:]+)(?::(?P<port>\d{1,5}))?$"
)
"""One Origin header form: ``scheme://host`` with an optional port."""

_NONCE_RE: Final = re.compile(r"^[A-Za-z0-9_-]{16,128}$")
"""The closed nonce token form allowed inside the CSP header."""

LocalRequestCheckV1: TypeAlias = Literal["HOST", "SESSION", "ORIGIN", "CSRF"]
"""The fixed check order of one local request authorization."""

LocalRequestErrorCodeV1: TypeAlias = Literal[
    "HOST_REJECTED",
    "SESSION_MISSING",
    "SESSION_INVALID",
    "SESSION_EXPIRED",
    "ORIGIN_MISSING",
    "ORIGIN_REJECTED",
    "CSRF_REJECTED",
]
"""The closed stable rejection codes of the loopback security boundary."""

_LOCAL_REQUEST_ERRORS_V1: Final[dict[LocalRequestErrorCodeV1, tuple[int, str, str]]] = {
    "HOST_REJECTED": (
        403,
        "请求的 Host 不是回环地址。",
        "请通过 http://127.0.0.1 端口访问本机服务。",
    ),
    "SESSION_MISSING": (
        401,
        "请求未携带本地会话。",
        "请重新打开主页以建立本地会话。",
    ),
    "SESSION_INVALID": (
        401,
        "本地会话令牌无效。",
        "请清除浏览器会话后重新打开主页。",
    ),
    "SESSION_EXPIRED": (
        401,
        "本地会话已过期。",
        "请重新打开主页以建立新会话。",
    ),
    "ORIGIN_MISSING": (
        403,
        "状态变更请求缺少 Origin 头。",
        "请通过本机页面提交操作。",
    ),
    "ORIGIN_REJECTED": (
        403,
        "状态变更请求的 Origin 不是本机回环地址。",
        "请通过 http://127.0.0.1 端口页面操作。",
    ),
    "CSRF_REJECTED": (
        403,
        "CSRF 令牌无效或缺失。",
        "请刷新页面后重试。",
    ),
}
"""Stable status, user-understandable reason, and next-step suggestion
for every closed rejection (SPEC §5.3)."""

CONTENT_SECURITY_POLICY_V1: Final[str] = (
    "default-src 'self'; "
    "script-src 'self'; "
    "style-src 'self' 'unsafe-inline'; "
    "object-src 'none'; "
    "base-uri 'none'; "
    "frame-ancestors 'none'; "
    "form-action 'self'"
)
"""The exact CSP of every local response (SPEC §5.5 WebUI threat): only
self sources, no object/embed, no framing, no form action off-page.
Inline scripts are allowed only through a per-request nonce inserted by
``local_response_security_headers`` — never through ``unsafe-inline``."""


class LocalWebSecurityConfigV1(BaseModel):
    """One closed loopback-only security configuration.

    The ``host`` is the literal ``127.0.0.1`` — the server can never be
    told to bind anywhere else; the ``port`` is validated to the closed
    range; the session cookie and CSRF header names are exact strings.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal[1] = 1
    host: Literal["127.0.0.1"]
    port: Annotated[int, Strict(), Field(ge=1, le=65535)]
    session_cookie_name: StrictStr
    csrf_header_name: StrictStr


class LocalSessionV1(BaseModel):
    """One bounded local session identity.

    The session is the self-contained carrier of its own cookie and CSRF
    header names so ``verify_local_request`` (whose interface receives
    only the request and the session) can validate identity, Origin, and
    CSRF without any hidden global configuration.  ``session_id`` and
    ``csrf_token`` are independent 256-bit random hex tokens; the expiry
    is a closed canonical instant.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal[1] = 1
    session_id: StrictStr
    csrf_token: StrictStr
    session_cookie_name: StrictStr
    csrf_header_name: StrictStr
    created_at: CanonicalTimestampV1
    expires_at: CanonicalTimestampV1


class LocalSessionErrorV1(RuntimeError):
    """One closed local-session failure (limit or malformed token)."""


class LocalSessionManager:
    """Create and resolve bounded local sessions.

    Every created session carries a fresh 256-bit token, expires after
    the bounded time-to-live, and the number of concurrently active
    sessions is bounded; expired sessions are pruned at ``create`` so the
    bound is never exhausted by stale sessions.  The clock and the token
    generator are injectable for deterministic tests (SPEC §4.9 random
    local session token; §5.4 injectable clock).
    """

    def __init__(
        self,
        config: LocalWebSecurityConfigV1,
        *,
        session_ttl_milliseconds: int = _DEFAULT_SESSION_TTL_MILLISECONDS,
        max_sessions: int = _DEFAULT_MAX_SESSIONS,
        clock: ClockV1 | None = None,
        token_generator: Callable[[], str] | None = None,
    ) -> None:
        if not isinstance(session_ttl_milliseconds, int) or isinstance(
            session_ttl_milliseconds, bool
        ):
            raise LocalSessionErrorV1("session TTL must be an integer")
        if session_ttl_milliseconds <= 0:
            raise LocalSessionErrorV1("session TTL must be positive")
        if not isinstance(max_sessions, int) or isinstance(max_sessions, bool):
            raise LocalSessionErrorV1("max sessions must be an integer")
        if max_sessions <= 0:
            raise LocalSessionErrorV1("max sessions must be positive")
        self._config = config
        self._session_ttl_milliseconds = session_ttl_milliseconds
        self._max_sessions = max_sessions
        self._clock = clock if clock is not None else SystemClockV1()
        self._token_generator = (
            token_generator if token_generator is not None else _random_hex_token
        )
        self._sessions: dict[str, LocalSessionV1] = {}

    @property
    def session_ttl_seconds(self) -> int:
        """The exact session TTL in seconds (for the cookie max-age)."""
        return self._session_ttl_milliseconds // 1000

    @property
    def clock(self) -> ClockV1:
        """The injectable clock (deterministic tests advance it)."""
        return self._clock

    def __len__(self) -> int:
        """The number of currently held (not yet pruned) sessions."""
        return len(self._sessions)

    def create(self) -> LocalSessionV1:
        """Create one bounded fresh local session (pruning expired first)."""
        self._prune_expired()
        if len(self._sessions) >= self._max_sessions:
            raise LocalSessionErrorV1(
                f"local session limit reached ({self._max_sessions})"
            )
        session_id = self._token_generator()
        csrf_token = self._token_generator()
        if _SESSION_TOKEN_RE.fullmatch(session_id) is None:
            raise LocalSessionErrorV1("session token generator returned a malformed id")
        if _SESSION_TOKEN_RE.fullmatch(csrf_token) is None:
            raise LocalSessionErrorV1(
                "session token generator returned a malformed csrf"
            )
        now = self._clock.now()
        expires_at = CanonicalTimestampV1.from_epoch_milliseconds(
            now.epoch_milliseconds + self._session_ttl_milliseconds
        )
        session = LocalSessionV1(
            schema_version=1,
            session_id=session_id,
            csrf_token=csrf_token,
            session_cookie_name=self._config.session_cookie_name,
            csrf_header_name=self._config.csrf_header_name,
            created_at=now,
            expires_at=expires_at,
        )
        self._sessions[session.session_id] = session
        return session

    def get(self, session_id: str) -> LocalSessionV1 | None:
        """Resolve one session by its exact token (or None when unknown)."""
        return self._sessions.get(session_id)

    def is_active(self, session: LocalSessionV1) -> bool:
        """Whether the session has not expired at the current clock."""
        now = self._clock.now()
        return session.expires_at.epoch_milliseconds > now.epoch_milliseconds

    def _prune_expired(self) -> None:
        """Drop every expired session (bound maintenance at create)."""
        now = self._clock.now().epoch_milliseconds
        expired = [
            session_id
            for session_id, session in self._sessions.items()
            if session.expires_at.epoch_milliseconds <= now
        ]
        for session_id in expired:
            del self._sessions[session_id]


class LocalRequestAuthorizationV1(BaseModel):
    """One closed local request authorization result.

    An authorized result carries no rejection; a rejected result always
    carries the stable error code and the exact check that rejected it,
    so the composition can report the fixed-order failure precisely.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal[1] = 1
    authorized: StrictBool
    error_code: LocalRequestErrorCodeV1 | None = None
    rejected_at: LocalRequestCheckV1 | None = None

    @model_validator(mode="after")
    def _authorization_is_consistent(self) -> LocalRequestAuthorizationV1:
        if self.authorized and (
            self.error_code is not None or self.rejected_at is not None
        ):
            raise ValueError("authorized results carry no rejection")
        if not self.authorized and (
            self.error_code is None or self.rejected_at is None
        ):
            raise ValueError("rejected results carry a code and a check")
        return self


def _random_hex_token() -> str:
    """One fresh 256-bit hex token (secrets-backed, never predictable)."""
    return secrets.token_hex(32)


def _port_suffix_is_valid(port: str | None) -> bool:
    """Whether one parsed port suffix is a closed 1..65535 value."""
    if port is None:
        return True
    try:
        return 1 <= int(port) <= 65535
    except ValueError:
        return False


def is_loopback_host(host_header: str) -> bool:
    """Whether one Host header is a closed loopback value.

    Only ``127.0.0.1`` and ``localhost`` with an optional numeric port
    in the closed 1..65535 range are accepted; IPv6 literals, DNS names,
    empty values, and out-of-range ports are never loopback (SPEC §4.9
    strict Host validation).
    """
    value = host_header.strip()
    if not value or value.count(":") > 1:
        return False
    match = _HOST_PORT_RE.fullmatch(value)
    if match is None:
        return False
    if not _port_suffix_is_valid(match.group("port")):
        return False
    return match.group("host") in LOOPBACK_HOST_VALUES_V1


def _split_host_port(host_header: str) -> tuple[str, str | None] | None:
    """Split one already-loopback Host header into host and port."""
    value = host_header.strip()
    if value.count(":") > 1:
        return None
    match = _HOST_PORT_RE.fullmatch(value)
    if match is None:
        return None
    if not _port_suffix_is_valid(match.group("port")):
        return None
    return match.group("host"), match.group("port")


def _is_loopback_origin(origin: str, host_header: str) -> bool:
    """Whether one state-change Origin matches the request's own Host.

    The Origin must be ``http`` (the loopback server has no TLS), the
    origin host must be one of the loopback values, and the origin host
    and port must equal the request's own (already validated loopback)
    Host exactly — a browser cross-origin request can never control the
    Host header, so a different origin host or port is rejected
    (SPEC §5.5 WebUI threat: Host/Origin protection).
    """
    match = _ORIGIN_RE.fullmatch(origin)
    if match is None:
        return False
    if match.group("scheme") != "http":
        return False
    if match.group("host") not in LOOPBACK_HOST_VALUES_V1:
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


def _rejected(
    error_code: LocalRequestErrorCodeV1, check: LocalRequestCheckV1
) -> LocalRequestAuthorizationV1:
    """One closed rejected authorization result."""
    return LocalRequestAuthorizationV1(
        authorized=False, error_code=error_code, rejected_at=check
    )


def verify_local_request(
    request: Request, session: LocalSessionV1
) -> LocalRequestAuthorizationV1:
    """Validate one local request in the fixed check order.

    The order is always HOST -> SESSION -> (state changes only) ORIGIN
    -> CSRF, and the first failing check wins, so the composition can
    reject before any route-domain call and report exactly which check
    failed (GREEN-1/GREEN-2).  Safe reads never require Origin or CSRF.
    Session liveness (including expiry) is enforced by the composition
    at resolution time through ``LocalSessionManager.is_active``; this
    function validates the request identity, Origin, and CSRF against
    the resolved session.
    """
    if not is_loopback_host(request.headers.get("host", "")):
        return _rejected("HOST_REJECTED", "HOST")
    cookie_value = request.cookies.get(session.session_cookie_name)
    if cookie_value is None:
        return _rejected("SESSION_MISSING", "SESSION")
    if cookie_value != session.session_id:
        return _rejected("SESSION_INVALID", "SESSION")
    if request.method in _STATE_CHANGING_METHODS_V1:
        origin = request.headers.get("origin")
        if origin is None:
            return _rejected("ORIGIN_MISSING", "ORIGIN")
        if not _is_loopback_origin(origin, request.headers.get("host", "")):
            return _rejected("ORIGIN_REJECTED", "ORIGIN")
        csrf_token = request.headers.get(session.csrf_header_name)
        if csrf_token is None or csrf_token != session.csrf_token:
            return _rejected("CSRF_REJECTED", "CSRF")
    return LocalRequestAuthorizationV1(authorized=True)


def local_request_status(error_code: LocalRequestErrorCodeV1) -> int:
    """One stable HTTP status for a closed rejection code."""
    return _LOCAL_REQUEST_ERRORS_V1[error_code][0]


def local_request_rejection_payload(
    error_code: LocalRequestErrorCodeV1,
) -> dict[str, str]:
    """One stable, non-leaking rejection body: code, reason, next step.

    The body carries only the closed error code and the fixed user-facing
    text (SPEC §5.3) — never request internals, sessions, or routes.
    """
    _, message, next_step = _LOCAL_REQUEST_ERRORS_V1[error_code]
    return {
        "error_code": error_code,
        "message": message,
        "next_step": next_step,
    }


def local_response_security_headers(csp_nonce: str | None = None) -> dict[str, str]:
    """The exact CSP and response security headers of every response.

    When a per-request nonce is supplied it is inserted into
    ``script-src`` (never ``unsafe-inline``); the nonce must be a closed
    token form so it can never inject into the header.  The headers only
    ever ADD to a response — status and body are untouched, so a
    downstream DENY keeps its exact rejection.
    """
    if csp_nonce is not None and _NONCE_RE.fullmatch(csp_nonce) is None:
        raise ValueError("CSP nonce must be a closed token form")
    csp = CONTENT_SECURITY_POLICY_V1
    if csp_nonce is not None:
        csp = csp.replace("script-src 'self'", f"script-src 'self' 'nonce-{csp_nonce}'")
    return {
        "Content-Security-Policy": csp,
        "X-Content-Type-Options": "nosniff",
        "X-Frame-Options": "DENY",
        "Referrer-Policy": "no-referrer",
    }

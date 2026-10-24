"""Route B / B3: the standard-library loopback server adapter.

``vespercode.web.v2_server`` bridges the framework-agnostic
``V2LocalWebApp`` contract onto ``http.server``:

- the launcher binds the literal loopback host only and validates the
  port (anything else rejects before a socket opens);
- request bodies are bounded (``V2_MAX_FORM_BYTES``) and must carry the
  URL-encoded content type — an oversized body rejects with 413 before
  it is read, a wrong content type with 415;
- only GET and POST dispatch to the app; cookies parse through the
  standard cookie jar, query strings and bodies through the closed v2
  form rules (duplicate fields and pollution reject);
- every response carries the app's exact status, headers (including the
  v2 security headers and ``Set-Cookie``), and UTF-8 body;
- nothing about a request is logged: the handler silences the default
  access log so IDs, query strings, and form fields never reach stderr.

The server is single-threaded on purpose: the local composition shares
one SQLite control connection, and a local single-user tool has no
concurrency requirement.
"""

from __future__ import annotations

from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qsl, urlsplit

from vespercode.web.v2_app import V2LocalWebApp, V2WebRequest, V2WebResponse
from vespercode.web.v2_forms import parse_v2_urlencoded
from vespercode.web.v2_security import V2_LOOPBACK_BIND_HOST

V2_MAX_FORM_BYTES = 64 * 1024
"""The closed bound on one request body (forms are small by design)."""

_V2_ALLOWED_METHODS = frozenset({"GET", "POST"})
_V2_FORM_CONTENT_TYPE = "application/x-www-form-urlencoded"


def _static_error(status: int, title: str) -> V2WebResponse:
    body = (
        "<!DOCTYPE html><html><head><title>"
        f"{title}</title></head><body><h1>{title}</h1></body></html>"
    )
    from vespercode.web.v2_security import v2_security_headers

    headers = {
        "Content-Type": "text/html; charset=utf-8",
        **v2_security_headers(),
    }
    return V2WebResponse(status, headers, body)


def v2_make_handler(app: V2LocalWebApp) -> type[BaseHTTPRequestHandler]:
    """Build one ``BaseHTTPRequestHandler`` bound to the app."""

    class _V2LocalHandler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def do_GET(self) -> None:  # noqa: N802 - http.server naming
            self._dispatch("GET")

        def do_POST(self) -> None:  # noqa: N802 - http.server naming
            self._dispatch("POST")

        def _reject_method(self) -> None:
            self._send(_static_error(405, "Method Not Allowed"))

        do_PUT = _reject_method
        do_PATCH = _reject_method
        do_DELETE = _reject_method
        do_HEAD = _reject_method
        do_OPTIONS = _reject_method

        def _dispatch(self, method: str) -> None:
            if method not in _V2_ALLOWED_METHODS:  # pragma: no cover
                self._send(_static_error(405, "Method Not Allowed"))
                return
            try:
                request = self._build_request(method)
                response = app.handle(request)
            except _V2BadRequest as exc:
                response = _static_error(exc.status, exc.title)
            except (ValueError, UnicodeError):
                response = _static_error(400, "Bad Request")
            self._send(response)

        def _build_request(self, method: str) -> V2WebRequest:
            split = urlsplit(self.path)
            path = split.path
            headers = {key.lower(): value for key, value in self.headers.items()}
            cookies: dict[str, str] = {}
            raw_cookie = self.headers.get("Cookie", "")
            if raw_cookie:
                jar = SimpleCookie()
                try:
                    jar.load(raw_cookie)
                except Exception:
                    jar = SimpleCookie()
                cookies = {key: morsel.value for key, morsel in jar.items()}
            if method == "GET":
                form = self._parse_pairs(split.query)
            else:
                content_type = (self.headers.get("Content-Type") or "").strip()
                length_header = self.headers.get("Content-Length")
                try:
                    length = int(length_header) if length_header is not None else 0
                except ValueError as exc:
                    raise _V2BadRequest(400, "Bad Request") from exc
                if length < 0:
                    raise _V2BadRequest(400, "Bad Request")
                if not content_type.startswith(_V2_FORM_CONTENT_TYPE):
                    self._drain(length)
                    raise _V2BadRequest(415, "Unsupported Media Type")
                if length > V2_MAX_FORM_BYTES:
                    self._drain(length)
                    raise _V2BadRequest(413, "Payload Too Large")
                body = self.rfile.read(length) if length else b""
                try:
                    decoded = body.decode("utf-8")
                except UnicodeDecodeError as exc:
                    raise _V2BadRequest(400, "Bad Request") from exc
                form = parse_v2_urlencoded(decoded)
            return V2WebRequest(
                method=method,
                path=path,
                headers=headers,
                cookies=cookies,
                form=form,
            )

        @staticmethod
        def _parse_pairs(query: str) -> dict[str, str]:
            if not query:
                return {}
            try:
                pairs = parse_qsl(
                    query,
                    keep_blank_values=True,
                    max_num_fields=64,
                )
            except (ValueError, UnicodeError) as exc:
                raise _V2BadRequest(400, "Bad Request") from exc
            form: dict[str, str] = {}
            for key, value in pairs:
                if key in form:
                    raise _V2BadRequest(400, "Bad Request")
                form[key] = value
            return form

        _DRAIN_CHUNK = 64 * 1024
        _DRAIN_CAP = 16 * 1024 * 1024

        def _drain(self, length: int) -> None:
            """Discard an already-rejected body (bounded), so the client
            can read the rejection instead of hitting a connection
            reset while it is still sending.  Bodies beyond the drain
            cap are abandoned: the connection closes afterwards."""

            remaining = min(length, self._DRAIN_CAP)
            while remaining > 0:
                chunk = self.rfile.read(min(remaining, self._DRAIN_CHUNK))
                if not chunk:
                    break
                remaining -= len(chunk)

        def _send(self, response: V2WebResponse) -> None:
            payload = response.body.encode("utf-8")
            self.close_connection = True
            self.send_response(response.status)
            for name, value in response.headers.items():
                self.send_header(name, value)
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, format: str, *args: object) -> None:  # noqa: A002
            # Silence the access log: request paths, IDs, and form fields
            # never reach stderr.
            return

    return _V2LocalHandler


class _V2BadRequest(Exception):
    """One closed transport-level rejection with its HTTP shape."""

    def __init__(self, status: int, title: str) -> None:
        super().__init__(title)
        self.status = status
        self.title = title


def v2_serve_forever(app: V2LocalWebApp, host: str, port: int) -> None:
    """Serve the app on the literal loopback host until interrupted.

    The host must be exactly ``127.0.0.1`` and the port a closed
    1..65535 integer — any other bind target rejects before a socket
    opens.
    """

    if host != V2_LOOPBACK_BIND_HOST:
        raise ValueError("the v2 local server binds 127.0.0.1 only")
    if isinstance(port, bool) or not isinstance(port, int):
        raise ValueError("port must be an integer")
    if not 1 <= port <= 65535:
        raise ValueError("port must be between 1 and 65535")
    if app is None:
        raise ValueError("the v2 local server requires an app")
    server = HTTPServer((host, port), v2_make_handler(app))
    try:
        server.serve_forever()
    finally:
        server.server_close()


__all__ = ["V2_MAX_FORM_BYTES", "v2_make_handler", "v2_serve_forever"]

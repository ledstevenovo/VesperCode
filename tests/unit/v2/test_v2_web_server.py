"""Route B / B3: the standard-library loopback server adapter.

``vespercode.web.v2_server`` bridges the framework-agnostic
``V2LocalWebApp`` contract onto ``http.server`` bound to the literal
loopback host only: request bodies are bounded and content-typed,
cookies and URL-encoded forms parse through the closed v2 form rules,
every response carries the v2 security headers, and nothing about a
request is logged.  These tests exercise a real loopback socket on an
ephemeral port with an injected fake shell -- no external network, no
credentials, no filesystem writes.
"""

from __future__ import annotations

import http.client
import threading
import unittest
from dataclasses import dataclass, field
from http.server import HTTPServer

from vespercode.web.v2_app import V2LocalWebApp, V2WebRequest
from vespercode.web.v2_security import V2_LOOPBACK_BIND_HOST
from vespercode.web.v2_server import (
    V2_MAX_FORM_BYTES,
    v2_make_handler,
    v2_serve_forever,
)


@dataclass
class _Shell:
    """The smallest fake the home, runs, and recovery pages need."""

    calls: list[str] = field(default_factory=list)

    def recent_runs(self, limit: int = 50):
        self.calls.append("recent_runs")
        return ()

    def pending_transaction_ids(self):
        self.calls.append("pending_transaction_ids")
        return ()

    def disclosure_grant_summaries(self, limit: int = 100):
        self.calls.append("disclosure_grant_summaries")
        return ()


class V2ServerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.shell = _Shell()
        self.app = V2LocalWebApp(self.shell)
        self._server: HTTPServer = HTTPServer(
            ("127.0.0.1", 0), v2_make_handler(self.app)
        )
        self._thread = threading.Thread(
            target=self._server.serve_forever, kwargs={"poll_interval": 0.05}
        )
        self._thread.start()
        self.addCleanup(self._stop_server)

    def _stop_server(self) -> None:
        self._server.shutdown()
        self._server.server_close()
        self._thread.join(timeout=5)

    def _request(
        self,
        method: str,
        path: str,
        *,
        body: str | None = None,
        content_type: str | None = "application/x-www-form-urlencoded",
        headers: dict[str, str] | None = None,
    ) -> tuple[int, dict[str, str], str]:
        host = "127.0.0.1"
        port = self._server.server_address[1]
        connection = http.client.HTTPConnection(host, port, timeout=5)
        effective_headers = {"Host": f"{host}:{port}"}
        if content_type is not None:
            effective_headers["Content-Type"] = content_type
        if headers is not None:
            effective_headers.update(headers)
        connection.request(
            method,
            path,
            body=body.encode("utf-8") if body is not None else None,
            headers=effective_headers,
        )
        response = connection.getresponse()
        payload = response.read().decode("utf-8")
        response_headers = {key.lower(): value for key, value in response.getheaders()}
        status = response.status
        connection.close()
        return status, response_headers, payload

    def test_home_serves_over_loopback_with_security_headers(self) -> None:
        status, headers, body = self._request("GET", "/")
        self.assertEqual(status, 200)
        self.assertIn("content-security-policy", headers)
        self.assertIn("x-content-type-options", headers)
        self.assertTrue(
            headers.get("set-cookie", "").startswith("vespercode_v2_session=")
        )
        self.assertIn("VesperCode", body)
        self.assertEqual(self.shell.calls, ["recent_runs", "pending_transaction_ids"])

    def test_unknown_paths_are_404(self) -> None:
        status, _, _ = self._request("GET", "/not-a-route")
        self.assertEqual(status, 404)

    def test_wrong_content_types_reject(self) -> None:
        status, _, _ = self._request(
            "POST",
            "/writeback/approve",
            body="run_id=1",
            content_type="application/json",
        )
        self.assertEqual(status, 415)

    def test_oversized_bodies_reject_before_parsing(self) -> None:
        status, _, _ = self._request(
            "POST",
            "/writeback/approve",
            body="x=" + "y" * (V2_MAX_FORM_BYTES + 1),
        )
        self.assertEqual(status, 413)

    def test_unsupported_methods_reject(self) -> None:
        status, _, _ = self._request("PUT", "/", body="")
        self.assertEqual(status, 405)

    def test_malformed_post_bodies_are_closed_400s(self) -> None:
        # Duplicate fields (HTTP parameter pollution) reject inside the
        # transport's closed body parser, before any session handling.
        status, _, _ = self._request("POST", "/writeback/approve", body="a=1&a=2")
        self.assertEqual(status, 400)

    def test_the_bind_host_is_the_literal_loopback_only(self) -> None:
        self.assertEqual(V2_LOOPBACK_BIND_HOST, "127.0.0.1")
        with self.assertRaises(ValueError):
            v2_serve_forever(self.app, "0.0.0.0", 8766)
        with self.assertRaises(ValueError):
            v2_serve_forever(self.app, "127.0.0.1", 0)

    def test_requests_carry_the_app_contract(self) -> None:
        # The request type is the server/app seam: a plain frozen record.
        request = V2WebRequest(method="GET", path="/", headers={"host": "127.0.0.1"})
        self.assertEqual(request.method, "GET")
        self.assertEqual(request.path, "/")


if __name__ == "__main__":
    unittest.main()

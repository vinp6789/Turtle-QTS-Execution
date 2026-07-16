"""Tests for hyperliquid_adapter.transport.post_json (Module 10, WP-4).

Uses a real local http.server instance (stdlib only, bound to
127.0.0.1:0 -- an OS-assigned free port) so these exercise actual
urllib.request behavior -- real TCP, real timeouts, real HTTP status
handling -- without any external network access or new dependency.
"""

import json
import socket
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer

from exchange_adapter import (
    ExchangeAdapterError,
    ExchangeConnectionError,
    ExchangeTimeoutError,
    RateLimitExceededError,
)

from hyperliquid_adapter import HttpResponse, TransportFn, post_json


class _ScriptedHandler(BaseHTTPRequestHandler):
    """Serves a single pre-configured response, or sleeps before responding."""

    status_code = 200
    response_body = b'{"ok": true}'
    response_headers = {}
    delay_seconds = 0.0

    def log_message(self, *args):
        pass  # keep test output quiet

    def do_POST(self):
        if self.delay_seconds:
            import time

            time.sleep(self.delay_seconds)
        length = int(self.headers.get("Content-Length", 0))
        self.rfile.read(length)  # drain the request body
        self.send_response(self.status_code)
        for name, value in self.response_headers.items():
            self.send_header(name, value)
        self.send_header("Content-Length", str(len(self.response_body)))
        self.end_headers()
        self.wfile.write(self.response_body)


def _start_server(status_code=200, response_body=b'{"ok": true}', response_headers=None, delay_seconds=0.0):
    handler_cls = type(
        "_Handler",
        (_ScriptedHandler,),
        {
            "status_code": status_code,
            "response_body": response_body,
            "response_headers": response_headers or {},
            "delay_seconds": delay_seconds,
        },
    )
    server = HTTPServer(("127.0.0.1", 0), handler_cls)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread


def _stop_server(server, thread):
    server.shutdown()
    server.server_close()
    thread.join(timeout=2)


def _free_but_closed_port() -> int:
    """Bind, discover a free port, then close it -- guarantees "connection
    refused" (nothing listening) rather than a timeout."""
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


class SuccessfulRequests(unittest.TestCase):
    def test_200_response_is_parsed_and_returned(self):
        server, thread = _start_server(status_code=200, response_body=b'{"status": "ok", "value": 42}')
        try:
            result = post_json(f"http://127.0.0.1:{server.server_port}/", {"a": 1}, timeout_seconds=2.0)
            self.assertIsInstance(result, HttpResponse)
            self.assertEqual(result.status_code, 200)
            self.assertEqual(result.body, {"status": "ok", "value": 42})
        finally:
            _stop_server(server, thread)

    def test_201_is_also_treated_as_success(self):
        server, thread = _start_server(status_code=201, response_body=b"{}")
        try:
            result = post_json(f"http://127.0.0.1:{server.server_port}/", {}, timeout_seconds=2.0)
            self.assertEqual(result.status_code, 201)
        finally:
            _stop_server(server, thread)

    def test_request_body_is_sent_as_json(self):
        received = {}

        class RecordingHandler(_ScriptedHandler):
            def do_POST(self):
                length = int(self.headers.get("Content-Length", 0))
                received["body"] = json.loads(self.rfile.read(length))
                received["content_type"] = self.headers.get("Content-Type")
                self.send_response(200)
                self.send_header("Content-Length", "2")
                self.end_headers()
                self.wfile.write(b"{}")

        server = HTTPServer(("127.0.0.1", 0), RecordingHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            post_json(f"http://127.0.0.1:{server.server_port}/", {"symbol": "BTC", "n": 3}, timeout_seconds=2.0)
            self.assertEqual(received["body"], {"symbol": "BTC", "n": 3})
            self.assertEqual(received["content_type"], "application/json")
        finally:
            _stop_server(server, thread)


class HttpStatusMapping(unittest.TestCase):
    def test_429_maps_to_rate_limit_exceeded_with_retry_after(self):
        server, thread = _start_server(
            status_code=429, response_body=b"rate limited", response_headers={"Retry-After": "7"}
        )
        try:
            with self.assertRaises(RateLimitExceededError) as ctx:
                post_json(f"http://127.0.0.1:{server.server_port}/", {}, timeout_seconds=2.0)
            self.assertEqual(ctx.exception.retry_after_seconds, 7.0)
        finally:
            _stop_server(server, thread)

    def test_500_maps_to_exchange_connection_error(self):
        server, thread = _start_server(status_code=500, response_body=b"internal error")
        try:
            with self.assertRaises(ExchangeConnectionError):
                post_json(f"http://127.0.0.1:{server.server_port}/", {}, timeout_seconds=2.0)
        finally:
            _stop_server(server, thread)

    def test_other_4xx_maps_to_base_adapter_error(self):
        server, thread = _start_server(status_code=418, response_body=b"teapot")
        try:
            with self.assertRaises(ExchangeAdapterError):
                post_json(f"http://127.0.0.1:{server.server_port}/", {}, timeout_seconds=2.0)
        finally:
            _stop_server(server, thread)


class ConnectionLevelFailures(unittest.TestCase):
    def test_timeout_maps_to_exchange_timeout_error(self):
        server, thread = _start_server(status_code=200, response_body=b"{}", delay_seconds=1.0)
        try:
            with self.assertRaises(ExchangeTimeoutError):
                post_json(f"http://127.0.0.1:{server.server_port}/", {}, timeout_seconds=0.1)
        finally:
            _stop_server(server, thread)

    def test_connection_to_closed_port_never_leaks_a_raw_exception(self):
        # Whether an OS reports a closed loopback port as an immediate
        # refusal (ExchangeConnectionError) or as a connect-phase timeout
        # (ExchangeTimeoutError) is platform-dependent; both are correct,
        # closed-hierarchy outcomes for "the connection attempt failed".
        # What must never happen is a raw OSError/URLError escaping.
        closed_port = _free_but_closed_port()
        with self.assertRaises((ExchangeConnectionError, ExchangeTimeoutError)):
            post_json(f"http://127.0.0.1:{closed_port}/", {}, timeout_seconds=0.3)

    def test_malformed_json_body_on_success_status_maps_to_connection_error(self):
        server, thread = _start_server(status_code=200, response_body=b"not json at all")
        try:
            with self.assertRaises(ExchangeConnectionError):
                post_json(f"http://127.0.0.1:{server.server_port}/", {}, timeout_seconds=2.0)
        finally:
            _stop_server(server, thread)


class InputValidation(unittest.TestCase):
    def test_zero_timeout_rejected(self):
        with self.assertRaises(ValueError):
            post_json("http://127.0.0.1:1/", {}, timeout_seconds=0)

    def test_negative_timeout_rejected(self):
        with self.assertRaises(ValueError):
            post_json("http://127.0.0.1:1/", {}, timeout_seconds=-1.0)


class InjectableSeam(unittest.TestCase):
    def test_post_json_satisfies_transport_fn_shape(self):
        # Proves the seam: a caller (a future adapter class) can accept
        # `transport: TransportFn = post_json` and substitute any
        # zero-network fake with the same (url, payload, timeout) -> HttpResponse
        # shape -- no real network required for the substitute.
        calls = []

        def fake_transport(url: str, payload: dict, timeout_seconds: float) -> HttpResponse:
            calls.append((url, payload, timeout_seconds))
            return HttpResponse(status_code=200, body={"faked": True})

        seam: TransportFn = fake_transport
        result = seam("https://example.invalid/info", {"type": "allMids"}, 5.0)

        self.assertEqual(result.body, {"faked": True})
        self.assertEqual(calls, [("https://example.invalid/info", {"type": "allMids"}, 5.0)])


if __name__ == "__main__":
    unittest.main()

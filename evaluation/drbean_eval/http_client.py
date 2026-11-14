"""Minimal authenticated client for the published /api/bean/v1 routes. Standard library only.

It calls the same routes and authority transitions as the real client. It never
writes rows, never uses a test-only endpoint and never logs the bearer token or
request bodies; each exchange keeps method, route, status, server request id,
byte digest of the response and local latency so traces can cite actual records.
"""
from __future__ import annotations

import hashlib
import json
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid

from . import API_PREFIX


class ApiFailure(Exception):
    def __init__(self, method: str, path: str, status: int, body):
        self.method, self.path, self.status, self.body = method, path, status, body
        code = body.get("code") if isinstance(body, dict) else None
        super().__init__(f"{method} {path} -> {status} {code or ''}".strip())

    @property
    def code(self):
        return self.body.get("code") if isinstance(self.body, dict) else None


class Response:
    def __init__(self, status: int, headers: dict, data: bytes):
        self.status, self.headers, self.data = status, headers, data

    def json(self):
        return json.loads(self.data.decode("utf-8"))


class ApiClient:
    def __init__(self, base_url: str, token: str, *, timeout: float = 30.0, key_prefix: str | None = None):
        self.base_url = base_url.rstrip("/")
        self._token = token
        self.timeout = timeout
        self.exchanges: list[dict] = []
        self.key_prefix = key_prefix or "eval-" + uuid.uuid4().hex[:10]
        self._counter = 0

    def new_key(self, label: str) -> str:
        self._counter += 1
        return f"{self.key_prefix}-{label}-{self._counter}"[:128]

    def raw(self, method: str, path: str, *, body: bytes | None = None, content_type: str | None = None,
            key: str | None = None, headers: dict | None = None, authenticated: bool = True,
            api: bool = True) -> Response:
        url = self.base_url + (API_PREFIX if api else "") + path
        request = urllib.request.Request(url, data=body, method=method)
        if authenticated:
            request.add_header("Authorization", "Bearer " + self._token)
        if content_type:
            request.add_header("Content-Type", content_type)
        if key:
            request.add_header("Idempotency-Key", key)
        for name, value in (headers or {}).items():
            request.add_header(name, value)
        started = time.monotonic()
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as handle:
                status, data, response_headers = handle.status, handle.read(), dict(handle.headers.items())
        except urllib.error.HTTPError as error:
            status, data, response_headers = error.code, error.read(), dict(error.headers.items())
        elapsed = round((time.monotonic() - started) * 1000, 3)
        lowered = {k.lower(): v for k, v in response_headers.items()}
        self.exchanges.append({"method": method, "route": _template(path), "status": status,
                               "request_id": lowered.get("x-request-id"), "latency_ms": elapsed,
                               "response_sha256": hashlib.sha256(data).hexdigest(), "response_bytes": len(data)})
        return Response(status, lowered, data)

    def call(self, method: str, path: str, payload=None, *, key: str | None = None, expect=(200, 201, 202),
             label: str | None = None):
        body = None
        if payload is not None:
            body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        if method == "POST" and key is None:
            key = self.new_key(label or "op")
        response = self.raw(method, path, body=body, content_type="application/json" if body is not None else None,
                            key=key)
        try:
            parsed = response.json() if response.data else None
        except ValueError:
            parsed = {"unparsed_bytes": len(response.data)}
        if response.status not in expect:
            raise ApiFailure(method, _template(path), response.status, parsed)
        return parsed

    def get(self, path: str, **kwargs):
        return self.call("GET", path, **kwargs)

    def post(self, path: str, payload=None, **kwargs):
        return self.call("POST", path, {} if payload is None else payload, **kwargs)


def _template(path: str) -> str:
    """Route shape without object ids, for traces: /runs/run_ab12 -> /runs/{id}."""
    parts = []
    for segment in urllib.parse.urlsplit(path).path.split("/"):
        parts.append("{id}" if "_" in segment and any(c.isdigit() for c in segment) and len(segment) > 12 else segment)
    return "/".join(parts)

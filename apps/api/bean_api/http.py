"""Bound raw requests before parsing; keep public errors small and secret-free."""

from __future__ import annotations

import re
import uuid
from fastapi.responses import JSONResponse

from .canonical import parse_json_strict

# Raw research-file uploads carry the user's own bytes (a user's JSON data file may
# contain floats or non-ASCII keys). They are bounded by the upload limit and parsed
# by the general research admission path, never by the strict API JSON parser.
RAW_UPLOAD_PATH = re.compile(r"/api/bean/v1/workspaces/[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}/research-assets")


def error_body(request_id: str, code: str, message: str, *, field_paths: list[str] | None = None,
               retryable: bool = False, current_revision_id: str | None = None) -> dict:
    return {"code": code, "message": message, "field_paths": field_paths or [],
            "retryable": retryable, "current_revision_id": current_revision_id, "request_id": request_id}


class RequestBoundary:
    def __init__(self, app, max_json_bytes: int = 262_144, max_upload_bytes: int = 5 * 1024 * 1024):
        self.app, self.max_json_bytes, self.max_upload_bytes = app, max_json_bytes, max_upload_bytes

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        request_id = str(uuid.uuid4())
        scope.setdefault("state", {})["request_id"] = request_id
        headers = dict(scope.get("headers", []))
        content_type = headers.get(b"content-type", b"").split(b";")[0].lower()
        raw_upload = scope.get("method") == "POST" and RAW_UPLOAD_PATH.fullmatch(scope.get("path", "")) is not None
        is_json = content_type == b"application/json" and not raw_upload
        limit = self.max_json_bytes if is_json else self.max_upload_bytes

        async def wrapped_send(message):
            if message["type"] == "http.response.start":
                message["headers"] = list(message.get("headers", [])) + [
                    (b"x-request-id", request_id.encode()), (b"x-content-type-options", b"nosniff"),
                    (b"cache-control", b"no-store"), (b"referrer-policy", b"no-referrer")]
            await send(message)

        async def reject(code, message, status):
            return await JSONResponse(error_body(request_id, code, message), status_code=status)(scope, receive, wrapped_send)

        if headers.get(b"content-encoding", b"identity") != b"identity":
            return await reject("unsupported_content_encoding", "Compressed request bodies are not supported.", 415)
        body = bytearray()
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            body.extend(message.get("body", b""))
            if len(body) > limit:
                return await reject("request_too_large", "Request exceeds the admitted byte limit.", 413)
            if not message.get("more_body", False):
                break
        if is_json and body:
            try:
                parse_json_strict(bytes(body), max_bytes=limit)
            except (ValueError, UnicodeError, RecursionError):
                return await reject("invalid_json", "JSON must use unique ASCII keys, valid Unicode, exact strings and bounded integer counters.", 422)
        delivered = False

        async def replay():
            nonlocal delivered
            if not delivered:
                delivered = True
                return {"type": "http.request", "body": bytes(body), "more_body": False}
            return await receive()

        await self.app(scope, replay, wrapped_send)

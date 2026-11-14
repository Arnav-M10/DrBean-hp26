"""Server-side principal resolution; object identifiers confer no authority."""

from __future__ import annotations

import hashlib
import secrets
from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

bearer_scheme = HTTPBearer(auto_error=False, scheme_name="BearerToken")


class AuthenticationError(Exception):
    def __init__(self, code: str = "unauthorized", message: str = "Authentication is required.", status: int = 401):
        self.code, self.message, self.status = code, message, status


async def principal(request: Request, credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme)) -> str:
    settings = request.app.state.settings
    origin = request.headers.get("origin")
    if origin and origin not in settings.allowed_origins:
        raise AuthenticationError("origin_not_allowed", "This browser origin is not allowed.", 403)
    scheme, supplied = (credentials.scheme, credentials.credentials) if credentials else ("", "")
    if scheme.lower() != "bearer" or not supplied or len(supplied) > 1024:
        raise AuthenticationError()
    supplied_digest = hashlib.sha256(supplied.encode()).digest()
    actor = None
    for candidate, expected in settings.auth_tokens.items():
        if secrets.compare_digest(supplied_digest, hashlib.sha256(expected.encode()).digest()):
            actor = candidate
    if actor is None:
        raise AuthenticationError()
    return actor

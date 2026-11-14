"""Private browser sessions; existing workspace memberships remain authority.

Only a trusted loopback gateway can use this cookie lane. Session credentials
are stored as hashes in the existing database, never in the owner token file.
No provider configuration or accounting is changed by this module.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
import stat
import time
from uuid import uuid4

from fastapi import Request, Response

from .store import Store, utc_now

COOKIE = "__Host-bean_session"
GATEWAY_HEADER = "x-bean-shared-gateway"
ORIGIN_HEADER = "x-bean-shared-origin"
TOKEN = re.compile(r"[A-Za-z0-9_-]{43}")
ORIGIN = re.compile(r"https://[a-z0-9]+(?:-[a-z0-9]+)*\.trycloudflare\.com")


class SessionError(Exception):
    def __init__(self, code="invalid_browser_session", message="This browser session is unavailable. Reconnect to start a new private workspace.",
                 status=401, *, clear_cookie=False):
        super().__init__(message)
        self.code, self.message, self.status, self.clear_cookie = code, message, status, clear_cookie


def gateway_digest(path: str | None) -> bytes | None:
    """Read an owner-only bounded file without following a final symlink.

    The gateway needs its independent transport secret to prove its hop; the API
    retains only its digest. Invalid private configuration disables this lane.
    """
    if not path:
        return None
    try:
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(descriptor, "rb") as handle:
            info = os.fstat(handle.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o600 or info.st_size > 1024:
                return None
            raw = handle.read(1025)
        value = json.loads(raw)
        if (len(raw) > 1024 or type(value) is not dict or set(value) != {"version", "secret"}
                or type(value["version"]) is not int or value["version"] != 1
                or type(value["secret"]) is not str or not TOKEN.fullmatch(value["secret"])):
            return None
        return hashlib.sha256(value["secret"].encode("ascii")).digest()
    except (OSError, ValueError, UnicodeError):
        return None


def session_cookie(request: Request) -> str | None:
    raw = ";".join(request.headers.getlist("cookie"))
    if len(raw) > 4096:
        raise SessionError(clear_cookie=True)
    values = []
    for part in raw.split(";"):
        name, separator, value = part.strip().partition("=")
        if name == COOKIE:
            if not separator or not TOKEN.fullmatch(value):
                raise SessionError(clear_cookie=True)
            values.append(value)
    if len(values) > 1:
        raise SessionError(clear_cookie=True)
    return values[0] if values else None


def cookie_lane(request: Request) -> bool:
    return (GATEWAY_HEADER in request.headers or ORIGIN_HEADER in request.headers
            or any(part.strip().partition("=")[0] == COOKIE
                   for raw in request.headers.getlist("cookie") for part in raw.split(";")))


def set_session_cookie(response: Response, token: str, max_age: int) -> None:
    response.set_cookie(COOKIE, token, max_age=max_age, path="/", secure=True, httponly=True, samesite="strict")
    response.headers["Cache-Control"] = "no-store"
    response.headers["Vary"] = "Cookie"


def clear_session_cookie(response: Response) -> None:
    set_session_cookie(response, "", 0)


class BrowserSessions:
    def __init__(self, store: Store, *, gateway_file: str | None, ttl_seconds: int = 86400,
                 max_sessions: int = 4096, clock=time.time):
        self.store, self.gateway_file, self.clock = store, gateway_file, clock
        if type(ttl_seconds) is not int or not 60 <= ttl_seconds <= 86400:
            raise ValueError("Browser session lifetime must be between 60 seconds and 24 hours")
        if type(max_sessions) is not int or not 1 <= max_sessions <= 4096:
            raise ValueError("Browser session capacity must be between 1 and 4096")
        self.ttl_seconds, self.max_sessions = ttl_seconds, max_sessions
        # Additive side-table migration, serialized with the existing store.
        # No global schema-version rewrite, owner token or historical row edits.
        with store.transaction() as conn:
            conn.execute("""CREATE TABLE IF NOT EXISTS browser_sessions (
                token_hash TEXT PRIMARY KEY CHECK(length(token_hash)=64),
                actor_id TEXT NOT NULL,
                workspace_id TEXT NOT NULL REFERENCES workspaces(id),
                created_at INTEGER NOT NULL,
                expires_at INTEGER NOT NULL CHECK(expires_at > created_at),
                revoked_at INTEGER
            )""")
            conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS browser_sessions_active_actor ON browser_sessions(actor_id) WHERE revoked_at IS NULL")

    def capabilities(self) -> dict:
        return {"mode": "browser_session", "available": gateway_digest(self.gateway_file) is not None,
                "session_ttl_seconds": self.ttl_seconds}

    def boundary(self, request: Request) -> None:
        expected = gateway_digest(self.gateway_file)
        if expected is None:
            raise SessionError("shared_access_unavailable", "Private browser access is not enabled on this server.", 404)
        proof = request.headers.getlist(GATEWAY_HEADER)
        origins = request.headers.getlist(ORIGIN_HEADER)
        if (len(proof) != 1 or not TOKEN.fullmatch(proof[0])
                or not secrets.compare_digest(hashlib.sha256(proof[0].encode("ascii")).digest(), expected)
                or len(origins) != 1 or not ORIGIN.fullmatch(origins[0])):
            raise SessionError("untrusted_shared_boundary", "A trusted shared-server boundary is required.", 403)
        # A public caller cannot upgrade a session by presenting a local owner
        # bearer. The gateway strips it; reject it here as defense in depth.
        if "authorization" in request.headers:
            raise SessionError("ambiguous_authentication", "Shared requests use the private browser session only.", 403)
        actual = request.headers.getlist("origin")
        fetch_site = request.headers.get("sec-fetch-site")
        if (len(actual) > 1 or (actual and actual[0] != origins[0])
                or (request.method not in {"GET", "HEAD"} and actual != origins)
                or (fetch_site is not None and fetch_site not in {"same-origin", "none"})):
            raise SessionError("origin_not_allowed", "This browser origin is not allowed.", 403)

    @staticmethod
    def _digest(token: str) -> str:
        return hashlib.sha256(token.encode("ascii")).hexdigest()

    def _record(self, conn, token: str | None) -> dict:
        row = conn.execute("SELECT * FROM browser_sessions WHERE token_hash=?", (self._digest(token),)).fetchone() if token else None
        now = int(self.clock())
        if row is None or row["revoked_at"] is not None or row["expires_at"] <= now:
            raise SessionError(clear_cookie=True)
        if not conn.execute("SELECT 1 FROM memberships WHERE workspace_id=? AND actor_id=?",
                            (row["workspace_id"], row["actor_id"])).fetchone():
            raise SessionError(clear_cookie=True)
        return dict(row)

    def authenticate(self, request: Request) -> str:
        self.boundary(request)
        token = session_cookie(request)
        with self.store.read() as conn:
            return self._record(conn, token)["actor_id"]

    @staticmethod
    def metadata(row: dict) -> dict:
        return {"mode": "browser_session", "authenticated": True,
                "workspace_id": row["workspace_id"], "credentials": "server_managed"}

    def _capacity(self, conn) -> None:
        # Bound retained issuance records, including revoked credentials. Never
        # delete private work or silently reset accounting to make more room.
        if conn.execute("SELECT count(*) FROM browser_sessions").fetchone()[0] >= self.max_sessions:
            raise SessionError("shared_session_capacity", "This shared server cannot issue another session. Contact its owner.", 429)

    def bootstrap(self, request: Request, response: Response) -> dict:
        self.boundary(request)
        token = session_cookie(request)
        now = int(self.clock())
        with self.store.transaction() as conn:
            if token is not None:
                row = self._record(conn, token)
            else:
                self._capacity(conn)
                token = secrets.token_urlsafe(32)
                actor, workspace = "browser_" + secrets.token_hex(24), "ws_" + uuid4().hex
                conn.execute("INSERT INTO workspaces(id,name,created_at) VALUES (?,?,?)", (workspace, "My research", utc_now()))
                conn.execute("INSERT INTO memberships(workspace_id,actor_id) VALUES (?,?)", (workspace, actor))
                conn.execute("INSERT INTO browser_sessions VALUES (?,?,?,?,?,NULL)",
                             (self._digest(token), actor, workspace, now, now + self.ttl_seconds))
                row = self._record(conn, token)
        set_session_cookie(response, token, row["expires_at"] - now)
        return self.metadata(row)

    def rotate(self, request: Request, response: Response) -> dict:
        self.boundary(request)
        token, now = session_cookie(request), int(self.clock())
        with self.store.transaction() as conn:
            row = self._record(conn, token)
            self._capacity(conn)
            replacement = secrets.token_urlsafe(32)
            conn.execute("UPDATE browser_sessions SET revoked_at=? WHERE token_hash=?", (now, row["token_hash"]))
            conn.execute("INSERT INTO browser_sessions VALUES (?,?,?,?,?,NULL)",
                         (self._digest(replacement), row["actor_id"], row["workspace_id"], now, row["expires_at"]))
        set_session_cookie(response, replacement, row["expires_at"] - now)
        return self.metadata(row)

    def logout(self, request: Request, response: Response) -> dict:
        self.boundary(request)
        with self.store.transaction() as conn:
            row = self._record(conn, session_cookie(request))
            conn.execute("UPDATE browser_sessions SET revoked_at=? WHERE token_hash=?", (int(self.clock()), row["token_hash"]))
        clear_session_cookie(response)
        return {"mode": "browser_session", "authenticated": False, "credentials": "server_managed"}

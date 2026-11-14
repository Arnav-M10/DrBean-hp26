"""Private browser sessions; existing workspace memberships remain authority.

Only a trusted loopback gateway can use this cookie lane. Session credentials
are stored as hashes in the existing database, never in the owner token file.
No provider configuration or accounting is changed by this module.
"""
from __future__ import annotations

import hashlib
import ipaddress
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
LOCAL_COOKIE = "bean_local_session"
GATEWAY_HEADER = "x-bean-shared-gateway"
ORIGIN_HEADER = "x-bean-shared-origin"
LOCAL_GATEWAY_HEADER = "x-bean-local-gateway"
LOCAL_ORIGIN_HEADER = "x-bean-local-origin"
TOKEN = re.compile(r"[A-Za-z0-9_-]{43}")
ORIGIN = re.compile(r"https://[a-z0-9]+(?:-[a-z0-9]+)*\.trycloudflare\.com")
LOCAL_ORIGIN = re.compile(r"http://(?:127\.0\.0\.1|localhost|\[::1\]):([1-9][0-9]{0,4})")


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


def session_cookie(request: Request, cookie: str = COOKIE) -> str | None:
    raw = ";".join(request.headers.getlist("cookie"))
    if len(raw) > 4096:
        raise SessionError(clear_cookie=True)
    values = []
    for part in raw.split(";"):
        name, separator, value = part.strip().partition("=")
        if name in {COOKIE, LOCAL_COOKIE} and name != cookie:
            raise SessionError(clear_cookie=True)
        if name == cookie:
            if not separator or not TOKEN.fullmatch(value):
                raise SessionError(clear_cookie=True)
            values.append(value)
    if len(values) > 1:
        raise SessionError(clear_cookie=True)
    return values[0] if values else None


def cookie_lane(request: Request) -> bool:
    return (any(header in request.headers for header in
                (GATEWAY_HEADER, ORIGIN_HEADER, LOCAL_GATEWAY_HEADER, LOCAL_ORIGIN_HEADER))
            or any(part.strip().partition("=")[0] in {COOKIE, LOCAL_COOKIE}
                   for raw in request.headers.getlist("cookie") for part in raw.split(";")))


def set_session_cookie(response: Response, token: str, max_age: int, *, cookie: str = COOKIE) -> None:
    response.set_cookie(cookie, token, max_age=max_age, path="/", secure=cookie == COOKIE,
                        httponly=True, samesite="strict")
    response.headers["Cache-Control"] = "no-store"
    response.headers["Vary"] = "Cookie"


def clear_session_cookie(response: Response, *, cookie: str = COOKIE) -> None:
    set_session_cookie(response, "", 0, cookie=cookie)


class BrowserSessions:
    def __init__(self, store: Store, *, gateway_file: str | None, ttl_seconds: int = 86400,
                 max_sessions: int = 4096, local_gateway_file: str | None = None,
                 local_browser_origin: str | None = None, clock=time.time):
        self.store, self.gateway_file, self.clock = store, gateway_file, clock
        origin_match = LOCAL_ORIGIN.fullmatch(local_browser_origin or "")
        if (bool(local_gateway_file) != bool(local_browser_origin)
                or (local_browser_origin and (not origin_match or int(origin_match[1]) > 65535))):
            raise ValueError("Local browser access requires an explicit loopback HTTP origin and private gateway file")
        self.local_gateway_file, self.local_browser_origin = local_gateway_file, local_browser_origin
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
        return {"mode": "browser_session", "available": (gateway_digest(self.gateway_file) is not None
                or gateway_digest(self.local_gateway_file) is not None),
                "session_ttl_seconds": self.ttl_seconds}

    def boundary(self, request: Request) -> str:
        local = any(header in request.headers for header in (LOCAL_GATEWAY_HEADER, LOCAL_ORIGIN_HEADER))
        shared = any(header in request.headers for header in (GATEWAY_HEADER, ORIGIN_HEADER))
        if local and shared:
            raise SessionError("untrusted_shared_boundary", "Only one trusted browser boundary is allowed.", 403)
        expected = gateway_digest(self.local_gateway_file if local else self.gateway_file)
        if expected is None:
            raise SessionError("shared_access_unavailable", "Private browser access is not enabled on this server.", 404)
        proof = request.headers.getlist(LOCAL_GATEWAY_HEADER if local else GATEWAY_HEADER)
        origins = request.headers.getlist(LOCAL_ORIGIN_HEADER if local else ORIGIN_HEADER)
        try:
            loopback = request.client is not None and ipaddress.ip_address(request.client.host).is_loopback
        except ValueError:
            loopback = False
        trusted_origin = len(origins) == 1
        if trusted_origin:
            trusted_origin = (origins[0] == self.local_browser_origin and loopback if local
                              else bool(ORIGIN.fullmatch(origins[0])))
        if (len(proof) != 1 or not TOKEN.fullmatch(proof[0])
                or not secrets.compare_digest(hashlib.sha256(proof[0].encode("ascii")).digest(), expected)
                or not trusted_origin):
            raise SessionError("untrusted_shared_boundary", "A trusted shared-server boundary is required.", 403)
        # A public caller cannot upgrade a session by presenting a local owner
        # bearer. The gateway strips it; reject it here as defense in depth.
        if "authorization" in request.headers:
            raise SessionError("ambiguous_authentication", "Browser requests use the private browser session only.", 403)
        actual = request.headers.getlist("origin")
        fetch_sites = request.headers.getlist("sec-fetch-site")
        if (len(actual) > 1 or (actual and actual[0] != origins[0])
                or (request.method not in {"GET", "HEAD"} and actual != origins)
                or len(fetch_sites) > 1 or (fetch_sites and fetch_sites[0] not in {"same-origin", "none"})):
            raise SessionError("origin_not_allowed", "This browser origin is not allowed.", 403)
        cookie = LOCAL_COOKIE if local else COOKIE
        # Only validated server context can choose the non-Secure local cookie,
        # including when an authentication error clears an expired credential.
        request.state.browser_session_cookie = cookie
        return cookie

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
        cookie = self.boundary(request)
        token = session_cookie(request, cookie)
        with self.store.read() as conn:
            return self._record(conn, token)["actor_id"]

    @staticmethod
    def metadata(row: dict) -> dict:
        return {"mode": "browser_session", "authenticated": True,
                "workspace_id": row["workspace_id"], "credentials": "server_managed"}

    def _capacity(self, conn) -> None:
        # Limit concurrent credentials, retaining historical rows and private
        # work. Logged-out/expired credentials cannot permanently exhaust access.
        active = conn.execute("SELECT count(*) FROM browser_sessions WHERE revoked_at IS NULL AND expires_at>?", (int(self.clock()),)).fetchone()[0]
        if active >= self.max_sessions:
            raise SessionError("shared_session_capacity", "This shared server cannot issue another session. Contact its owner.", 429)

    def bootstrap(self, request: Request, response: Response) -> dict:
        cookie = self.boundary(request)
        token = session_cookie(request, cookie)
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
        set_session_cookie(response, token, row["expires_at"] - now, cookie=cookie)
        return self.metadata(row)

    def current(self, request: Request, response: Response) -> dict:
        """Confirm cookie acceptance without issuing an identity or extending it."""
        cookie = self.boundary(request)
        token = session_cookie(request, cookie)
        if token is None:
            raise SessionError("browser_session_missing", "No private browser session is present.", 401)
        with self.store.read() as conn:
            row = self._record(conn, token)
        response.headers["Cache-Control"] = "no-store"
        response.headers["Vary"] = "Cookie"
        return self.metadata(row)

    def rotate(self, request: Request, response: Response) -> dict:
        cookie = self.boundary(request)
        token, now = session_cookie(request, cookie), int(self.clock())
        with self.store.transaction() as conn:
            row = self._record(conn, token)
            # Rotation atomically replaces this one active credential. It neither
            # creates another identity/workspace nor consumes another active slot.
            replacement = secrets.token_urlsafe(32)
            conn.execute("UPDATE browser_sessions SET revoked_at=? WHERE token_hash=?", (now, row["token_hash"]))
            conn.execute("INSERT INTO browser_sessions VALUES (?,?,?,?,?,NULL)",
                         (self._digest(replacement), row["actor_id"], row["workspace_id"], now, row["expires_at"]))
        set_session_cookie(response, replacement, row["expires_at"] - now, cookie=cookie)
        return self.metadata(row)

    def logout(self, request: Request, response: Response) -> dict:
        cookie = self.boundary(request)
        with self.store.transaction() as conn:
            row = self._record(conn, session_cookie(request, cookie))
            conn.execute("UPDATE browser_sessions SET revoked_at=? WHERE token_hash=?", (int(self.clock()), row["token_hash"]))
        clear_session_cookie(response, cookie=cookie)
        return {"mode": "browser_session", "authenticated": False, "credentials": "server_managed"}

#!/usr/bin/env python3
"""Temporary HTTPS sharing of the running Dr. Bean server; never reads a Gemini key."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import stat
import time

try:
    from . import launcher
except ImportError:
    import launcher

PORT = 4174
ORIGIN_FILE = Path(launcher.VAR) / "share-origin.json"
GATEWAY_FILE = Path(launcher.VAR) / "share-gateway.json"
GATEWAY_MODE = "private-browser-session-v1"
NAMES = launcher.SHARING_SERVICES
ORIGIN_RE = re.compile(r"https://[a-z0-9]+(?:-[a-z0-9]+)*\.trycloudflare\.com")


def recorded_origin():
    try:
        origin = json.loads(ORIGIN_FILE.read_text())["origin"]
        return origin if isinstance(origin, str) and ORIGIN_RE.fullmatch(origin) else None
    except (OSError, ValueError, KeyError, TypeError):
        return None


def clear_origin():
    try:
        ORIGIN_FILE.unlink()
    except FileNotFoundError:
        pass


def _stop():
    # Close admission first, including while process termination is in progress.
    clear_origin()
    unproven = False
    for name in NAMES:
        result = launcher.stop_one(name)
        unproven = unproven or result.startswith("ownership unproven")
        print(f"{name}: {result}")
    return 1 if unproven else 0


@launcher.serialized_lifecycle
def stop():
    return _stop()


def status():
    gateway = launcher.owned("share-gateway")
    live = gateway and gateway.get("sharing_mode") == GATEWAY_MODE and launcher.owned("share-tunnel")
    origin = recorded_origin()
    if live and origin:
        print(f"Shared Dr. Bean: {origin}")
        print("Each browser opens its own private session; no key or access token to paste.")
        print("Anyone with this URL can create a session and use the shared trial allowance.")
        print("All workspaces share this server's Gemini configuration and conservative budget.")
        print("This temporary URL needs this Mac, its network and both sharing processes running.")
        return 0
    print("Private browser sharing is not running. Start the app, then run python3 scripts/dev/share.py start.")
    return 1


def prepare_gateway():
    """Retain a gateway credential; never read or modify owner auth/provider data."""
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    try:
        with os.fdopen(os.open(GATEWAY_FILE, flags), "r", encoding="utf-8") as handle:
            info = os.fstat(handle.fileno())
            if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid()
                    or stat.S_IMODE(info.st_mode) != 0o600 or info.st_size > 1024):
                raise ValueError
            data = json.loads(handle.read(1025), object_pairs_hook=launcher._unique_json_object)
            if (not isinstance(data, dict) or set(data) != {"version", "secret"}
                    or type(data.get("version")) is not int or data["version"] != 1
                    or not isinstance(data.get("secret"), str)
                    or not re.fullmatch(r"[A-Za-z0-9_-]{43}", data["secret"])):
                raise ValueError
    except FileNotFoundError:
        launcher.private_json(GATEWAY_FILE, {"version": 1, "secret": secrets.token_urlsafe(32)})
    except (OSError, ValueError, UnicodeError):
        raise launcher.LifecycleError("Gateway configuration is invalid; repair the private 0600 file before sharing.") from None


def session_api_ready():
    """Read capability metadata only; do not create a session or dispatch a model."""
    try:
        status_code, capabilities = launcher.http_json(
            f"http://127.0.0.1:{launcher.API_PORT}/api/bean/v1/capabilities")
        shared = capabilities.get("shared_access") if isinstance(capabilities, dict) else None
        return status_code == 200 and isinstance(shared, dict) and shared.get("mode") == "browser_session" \
            and shared.get("available") is True
    except (OSError, ValueError):
        return False


@launcher.serialized_lifecycle
def start():
    processes = {name: launcher.owned(name) for name in NAMES}
    if any(launcher.unproven_process(name) for name in NAMES):
        print("A sharing process record has unproven ownership. Nothing was changed; inspect it before restarting.")
        return 1
    if (all(processes[name] for name in NAMES[:2]) and recorded_origin()
            and processes["share-gateway"].get("sharing_mode") == GATEWAY_MODE):
        return status()
    binary = shutil.which("cloudflared")
    if not binary:
        print("Install cloudflared from its official distribution (on macOS: brew install cloudflared).")
        return 1
    if (not all(launcher.owned(name) for name in ("api", "web"))
            or not launcher.port_in_use(launcher.WEB_PORT) or not launcher.port_in_use(launcher.API_PORT)):
        print("Start Dr. Bean first with scripts/dev/start.sh. Nothing was shared.")
        return 1
    if launcher.port_in_use(PORT) and not processes["share-gateway"]:
        print("Sharing port 4174 is occupied; nothing was changed or killed.")
        return 1
    os.makedirs(launcher.RUN, exist_ok=True)
    clear_origin()
    env = launcher.child_env()  # No provider credentials in the gateway or tunnel.
    # Paths are only needed by the gateway; cloudflared gets no credential or
    # credential-file configuration. Ignore inherited sharing overrides.
    env = {key: value for key, value in env.items() if not key.startswith("BEAN_SHARE_")}
    gateway_env = {**env, "BEAN_SHARE_ORIGIN_FILE": str(ORIGIN_FILE),
                   "BEAN_SHARE_GATEWAY_FILE": str(GATEWAY_FILE)}
    log = Path(launcher.RUN) / "share-tunnel.log"
    offset = log.stat().st_size if log.exists() else 0
    try:
        prepare_gateway()
        if not session_api_ready():
            raise launcher.LifecycleError("The managed API does not report private browser sessions ready. Update/restart the local app before sharing.")
        # A previous interrupted start or legacy shared-demo pair is never
        # treated as private browser sharing merely because its PIDs are alive.
        if any(processes.values()):
            print("Recovering incomplete or legacy sharing processes.")
            _stop()
            if launcher.port_in_use(PORT):
                raise launcher.LifecycleError("Sharing port remains occupied after owned-process cleanup; nothing else was killed.")
        gateway = launcher.spawn("share-gateway", ["node", "apps/web/share-gateway.mjs", str(PORT)], gateway_env)
        gateway["sharing_mode"] = GATEWAY_MODE
        # The marker belongs to this exact owned PID/start time, not to an old
        # origin file that a legacy gateway could also have written.
        launcher.private_json(launcher.pidfile("share-gateway"), gateway)
        launcher.spawn("share-tunnel", [binary, "tunnel", "--no-autoupdate", "--protocol", "http2",
                                      "--url", f"http://127.0.0.1:{PORT}"], env)
        deadline = time.monotonic() + 45
        while time.monotonic() < deadline:
            if not all(launcher.owned(name) for name in NAMES[:2]):
                raise launcher.LifecycleError("A sharing process exited; inspect var/run/share-*.log locally.")
            try:
                with log.open("r", encoding="utf-8", errors="replace") as handle:
                    handle.seek(offset)
                    match = ORIGIN_RE.search(handle.read(131072))
            except FileNotFoundError:
                match = None
            if match:
                origin = match.group(0)
                launcher.private_json(ORIGIN_FILE, {"origin": origin})
                # Keep a Mac host awake while sharing, without changing system settings.
                awake = shutil.which("caffeinate")
                if awake:
                    launcher.spawn("share-awake", [awake, "-i", "-w", str(launcher.owned("share-tunnel")["pid"])], env)
                return status()
            time.sleep(0.25)
        raise launcher.LifecycleError("Cloudflare did not return a shared URL within 45 seconds.")
    except (OSError, launcher.LifecycleError, KeyboardInterrupt) as error:
        print(str(error) if isinstance(error, launcher.LifecycleError)
              else f"Sharing start failed ({type(error).__name__}); no public origin is accepted.")
        _stop()
        return 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("start", "stop", "status"))
    return {"start": start, "stop": stop, "status": status}[parser.parse_args().command]()


if __name__ == "__main__":
    raise SystemExit(main())

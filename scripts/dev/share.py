#!/usr/bin/env python3
"""Temporary HTTPS sharing of the running Dr. Bean server; never reads a Gemini key."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import shutil
import time

try:
    from . import launcher
except ImportError:
    import launcher

PORT = 4174
ORIGIN_FILE = Path(launcher.VAR) / "share-origin.json"
NAMES = ("share-tunnel", "share-gateway", "share-awake")
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


def stop():
    for name in NAMES:
        print(f"{name}: {launcher.stop_one(name)}")
    clear_origin()
    return 0


def status():
    live = all(launcher.owned(name) for name in NAMES[:2])
    origin = recorded_origin()
    if live and origin:
        print(f"Shared Dr. Bean: {origin}")
        print("Each researcher connects with a Dr. Bean bearer token, never a Gemini key.")
        print("All workspaces share this server's Gemini configuration and conservative budget.")
        print("This temporary URL needs this Mac, its network and both sharing processes running.")
        return 0
    print("Shared Dr. Bean is not running. Start the app, then run python3 scripts/dev/share.py start.")
    return 1


def start():
    if any(launcher.owned(name) for name in NAMES[:2]):
        return status()
    binary = shutil.which("cloudflared")
    if not binary:
        print("Install cloudflared from its official distribution (on macOS: brew install cloudflared).")
        return 1
    if not launcher.port_in_use(launcher.WEB_PORT) or not launcher.port_in_use(launcher.API_PORT):
        print("Start Dr. Bean first with scripts/dev/start.sh. Nothing was shared.")
        return 1
    if launcher.port_in_use(PORT):
        print("Sharing port 4174 is occupied; nothing was changed or killed.")
        return 1
    os.makedirs(launcher.RUN, exist_ok=True)
    clear_origin()
    env = launcher.child_env()  # No provider credentials in the gateway or tunnel.
    env["BEAN_SHARE_ORIGIN_FILE"] = str(ORIGIN_FILE)
    log = Path(launcher.RUN) / "share-tunnel.log"
    offset = log.stat().st_size if log.exists() else 0
    try:
        launcher.spawn("share-gateway", ["node", "apps/web/share-gateway.mjs", str(PORT)], env)
        launcher.spawn("share-tunnel", [binary, "tunnel", "--no-autoupdate", "--protocol", "http2",
                                      "--url", f"http://127.0.0.1:{PORT}"], env)
        deadline = time.monotonic() + 45
        while time.monotonic() < deadline:
            if not all(launcher.owned(name) for name in NAMES[:2]):
                raise RuntimeError("A sharing process exited; inspect var/run/share-*.log locally.")
            with log.open("r", encoding="utf-8", errors="replace") as handle:
                handle.seek(offset)
                match = ORIGIN_RE.search(handle.read(131072))
            if match:
                origin = match.group(0)
                temporary = ORIGIN_FILE.with_suffix(".tmp")
                temporary.write_text(json.dumps({"origin": origin}) + "\n")
                os.chmod(temporary, 0o600)
                temporary.replace(ORIGIN_FILE)
                # Keep a Mac host awake while sharing, without changing system settings.
                awake = shutil.which("caffeinate")
                if awake:
                    launcher.spawn("share-awake", [awake, "-i", "-w", str(launcher.owned("share-tunnel")["pid"])], env)
                return status()
            time.sleep(0.25)
        raise RuntimeError("Cloudflare did not return a shared URL within 45 seconds.")
    except (OSError, RuntimeError, KeyboardInterrupt) as error:
        print(str(error))
        stop()
        return 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("start", "stop", "status"))
    return {"start": start, "stop": stop, "status": status}[parser.parse_args().command]()


if __name__ == "__main__":
    raise SystemExit(main())

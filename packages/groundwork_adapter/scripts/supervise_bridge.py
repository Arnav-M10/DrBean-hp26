#!/usr/bin/env python3
"""Stdlib parent-side example for Python 3.12/3.13; no scientific imports.

Owner 2 may call PreparedBridge from this fixed server-selected source file or
implement the identical boundary in the API. The executable is configuration,
never an argument taken from an artifact, model or HTTP request. POSIX only.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import selectors
import signal
import subprocess
import sys
import time

TRANSPORT_CAP = 12 * 1024 * 1024
PROTOCOL = "counterdex.bridge.v1"


def failure(code: str) -> dict:
    return {"protocol": PROTOCOL, "ok": False, "error": {"code": code,
            "message": "The bounded scientific process did not return a complete usable response.",
            "field_paths": [], "retryable": False}}


class PreparedBridge:
    def __init__(self, python: str):
        self.python = str(Path(python).absolute()) if Path(python).is_absolute() else None

    def capabilities(self) -> dict:
        if self.python is None:
            return {"configured": False, "available": False, "qualified": False, "reason_code": "missing_runtime_configuration"}
        response = self.call({"protocol": PROTOCOL, "operation": "handshake"}, wall_seconds=10)
        if response.get("ok") is not True:
            return {"configured": True, "available": False, "qualified": False,
                    "reason_code": response.get("error", {}).get("code", "invalid_bridge_response")}
        if response.get("available") is not True or type(response.get("qualified")) is not bool:
            return {"configured": True, "available": False, "qualified": False,
                    "reason_code": "invalid_bridge_response"}
        return {**response, "configured": True}

    def call(self, request: dict, *, wall_seconds: int = 120, cancelled=lambda: False) -> dict:
        if type(wall_seconds) is not int or not 1 <= wall_seconds <= 120:
            return failure("invalid_wall_limit")
        if self.python is None or not Path(self.python).is_file() or not os.access(self.python, os.X_OK):
            return failure("runtime_unavailable")
        try:
            encoded = json.dumps(request, ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode()
        except (ValueError, TypeError, UnicodeError):
            return failure("invalid_bridge_request")
        if len(encoded) > TRANSPORT_CAP:
            return failure("transport_byte_limit")
        if cancelled():
            return failure("cancelled")
        started, process = time.monotonic(), None
        selector = selectors.DefaultSelector()
        output, errors, sent = bytearray(), bytearray(), 0
        try:
            process = subprocess.Popen([self.python, "-I", "-m", "counterdex.bridge"],
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                start_new_session=True, close_fds=True,
                env={"LANG": "C.UTF-8", "LC_ALL": "C.UTF-8"})
            for stream, event, label in ((process.stdin, selectors.EVENT_WRITE, "input"),
                    (process.stdout, selectors.EVENT_READ, "output"), (process.stderr, selectors.EVENT_READ, "error")):
                os.set_blocking(stream.fileno(), False)
                selector.register(stream, event, label)
            while selector.get_map():
                if cancelled():
                    return failure("cancelled")
                if time.monotonic() - started >= wall_seconds:
                    return failure("scientific_wall_limit")
                for key, _ in selector.select(timeout=0.02):
                    if key.data == "input":
                        try:
                            sent += os.write(key.fileobj.fileno(), encoded[sent:sent + 65536])
                        except BrokenPipeError:
                            sent = len(encoded)
                        if sent == len(encoded):
                            selector.unregister(key.fileobj)
                            key.fileobj.close()
                    else:
                        chunk = os.read(key.fileobj.fileno(), 65536)
                        if not chunk:
                            selector.unregister(key.fileobj)
                            key.fileobj.close()
                            continue
                        target = output if key.data == "output" else errors
                        target.extend(chunk)
                        if len(target) > (TRANSPORT_CAP if key.data == "output" else 65536):
                            return failure("transport_byte_limit")
            # A child may close both outputs before exiting. The same deadline
            # and cancellation still apply; never leave solver work behind.
            while process.poll() is None:
                if cancelled():
                    return failure("cancelled")
                if time.monotonic() - started >= wall_seconds:
                    return failure("scientific_wall_limit")
                time.sleep(0.01)
            try:
                result = json.loads(output)
            except (ValueError, UnicodeError):
                return failure("invalid_bridge_response")
            if (type(result) is not dict or result.get("protocol") != PROTOCOL
                or type(result.get("ok")) is not bool or (process.returncode != 0 and result.get("ok") is True)):
                return failure("invalid_bridge_response")
            return result
        except (OSError, ValueError):
            return failure("runtime_unavailable")
        finally:
            if process is not None:
                # Popen created this private session. Kill the entire owned
                # group even when its leader exited but a descendant remains.
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                process.wait(timeout=2)
                for stream in (process.stdin, process.stdout, process.stderr):
                    if not stream.closed:
                        stream.close()
            selector.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--python", required=True, help="Server-selected absolute prepared CPython 3.11 executable")
    parser.add_argument("--wall-seconds", type=int, default=120)
    args = parser.parse_args()
    content = sys.stdin.buffer.read(TRANSPORT_CAP + 1)
    try:
        request = json.loads(content) if len(content) <= TRANSPORT_CAP else None
    except (ValueError, UnicodeError):
        request = None
    result = failure("invalid_bridge_request") if type(request) is not dict else PreparedBridge(args.python).call(request, wall_seconds=args.wall_seconds)
    sys.stdout.write(json.dumps(result, separators=(",", ":")) + "\n")
    return 0 if result["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())

"""Local controlled source preview; no application acceptance or model dispatch."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import socket
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "apps" / "api"))


def preview_source(path: Path) -> dict:
    from bean_api.canonical import byte_digest, parse_json_strict
    from bean_api.intake import MAX_SOURCE_BYTES, inspect_image
    from bean_api.providers import ControlledSourceProposer, ProviderFailure

    if not path.is_file():
        raise ProviderFailure("controlled_preview_source_unavailable")
    with path.open("rb") as stream:
        raw = stream.read(MAX_SOURCE_BYTES + 1)
    if not 1 <= len(raw) <= MAX_SOURCE_BYTES:
        raise ProviderFailure("controlled_preview_source_limit")
    if raw.startswith(b"\x89PNG\r\n\x1a\n"):
        mime = "image/png"
    elif raw.startswith(b"\xff\xd8\xff"):
        mime = "image/jpeg"
    else:
        raise ProviderFailure("controlled_preview_media_unsupported")
    observed = inspect_image(raw, mime)
    metadata = {**observed, "sha256": byte_digest(raw), "byte_size": len(raw),
                "declared_media_type": mime, "origin": "synthetic", "retention": "retain",
                "upload_actor_id": "local_preview_operator"}
    manifest = parse_json_strict((ROOT / "scripts/ai/fixtures/source-previews.v1.json").read_bytes(),
                                 max_bytes=128 * 1024)
    result = ControlledSourceProposer(manifest).prepare(
        source_asset_id="local_preview_source", metadata=metadata, source_bytes=raw)
    result["authority"] = "standalone_preview_only"
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", nargs="?", type=Path, default=ROOT / "fixtures/intake/clean.png")
    args = parser.parse_args()
    attempts = []
    connect, connect_ex = socket.socket.connect, socket.socket.connect_ex

    def deny_connect(*unused_args, **unused_kwargs):
        attempts.append("socket_connection_attempt")
        raise RuntimeError("Offline preview forbids network dispatch")

    socket.socket.connect = deny_connect
    socket.socket.connect_ex = deny_connect
    try:
        result = preview_source(args.source)
        code = 0 if result["status"] == "controlled_example" else 2
    except Exception as exc:
        from bean_api.providers import ProviderFailure
        result = {"status": "unavailable", "code": exc.code if isinstance(exc, ProviderFailure) else "controlled_preview_failed",
                  "fields": [], "next_action": "manual_review", "execution_approved": False,
                  "live_qualification": "not_run"}
        code = 2
    finally:
        socket.socket.connect, socket.socket.connect_ex = connect, connect_ex
    result.update(external_dispatch_attempts=len(attempts),
                  dispatch_observation_scope="socket.connect/connect_ex in this preview process")
    if attempts:
        result.update(status="unavailable", code="controlled_preview_dispatch_attempted", fields=[])
        code = 1
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return code


if __name__ == "__main__":
    raise SystemExit(main())

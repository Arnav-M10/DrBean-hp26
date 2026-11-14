"""Provider-free executable contract: python -m bean_api.model_comparison request.json."""
import argparse
from pathlib import Path

from ..canonical import canonical_bytes, parse_json_strict
from .compute import compute_comparison
from .contract import ModelComparisonRequest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("request", type=Path)
    args = parser.parse_args()
    if args.request.stat().st_size > 128 * 1024:
        parser.error("Request exceeds 128 KiB")
    request = ModelComparisonRequest.model_validate(parse_json_strict(args.request.read_bytes(), max_bytes=128*1024))
    result = compute_comparison(request)
    print(canonical_bytes(result).decode())
    return 0 if result["status"] == "completed" else 2


if __name__ == "__main__":
    raise SystemExit(main())

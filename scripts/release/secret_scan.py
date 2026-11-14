#!/usr/bin/env python3
"""Scan tracked files (or given paths) for secret-shaped strings.

  python3 scripts/release/secret_scan.py            tracked files, secret patterns
  python3 scripts/release/secret_scan.py --sentinels PATH ...   exports, logs, screenshots' text, storage dumps:
                                                    also fail on the planted diagnostic sentinels
Exit 1 on any finding. Matches are printed truncated.
"""
import os
import subprocess
import sys

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(REPO, "evaluation"))
from drbean_eval import sanitize  # noqa: E402


def expand(paths):
    for path in paths:
        if os.path.isdir(path):
            for folder, _, names in os.walk(path):
                yield from (os.path.join(folder, name) for name in names)
        else:
            yield path


def main(argv):
    with_sentinels = "--sentinels" in argv
    paths = [a for a in argv if a != "--sentinels"]
    if not paths:
        listed = subprocess.run(["git", "-C", REPO, "ls-files", "-z"], capture_output=True, check=True).stdout
        paths = [os.path.join(REPO, p) for p in listed.decode().split("\0") if p]
    # Frozen cases deliberately carry the planted sentinels as inputs, so the
    # repository scan checks secret shapes only.
    findings = sanitize.scan(list(expand(paths)), sanitize.SENTINELS if with_sentinels else ())
    for finding in findings:
        print(f"{os.path.relpath(finding['path'], REPO)}: {finding['kind']} {finding['match']}")
    print(f"secret scan: {len(findings)} finding(s)")
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

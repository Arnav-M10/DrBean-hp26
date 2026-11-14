#!/usr/bin/env bash
# Proves the release checks pass from a clean clone of the current commit,
# so nothing depends on untracked or uncommitted files.
#   scripts/release/clean_checkout.sh
set -euo pipefail
repo="$(cd "$(dirname "$0")/../.." && pwd)"
commit="$(git -C "$repo" rev-parse HEAD)"
if [ -n "$(git -C "$repo" status --porcelain)" ]; then
  echo "note: the working tree has uncommitted or untracked files; they are NOT part of this check:"
  git -C "$repo" status --porcelain | head -20
fi
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
git clone --quiet --no-hardlinks "$repo" "$work/checkout"
git -C "$work/checkout" checkout --quiet --detach "$commit"
echo "clean clone of $commit at $work/checkout"
cd "$work/checkout"
env -u GEMINI_API_KEY -u GOOGLE_API_KEY -u DRBEAN_API_BASE python3 scripts/release/checklist.py

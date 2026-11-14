#!/usr/bin/env bash
# Proves the release checks pass from a clean clone of the current commit, with the
# qualified runtimes installed from the lock files and AI in placeholder mode.
#
#   scripts/release/clean_checkout.sh                  inventory
#   scripts/release/clean_checkout.sh --strict-offline exit nonzero unless every offline gate passes
#   add --fast to skip the stack and browser checks
#
# It never touches your var/ store: the clone gets its own. It depends on nothing
# untracked. It needs uv, Node and network access to the package index (not to any
# model provider). Ports 8000 and 4173 must be free unless --fast is given.
set -euo pipefail
repo="$(cd "$(dirname "$0")/../.." && pwd)"
commit="$(git -C "$repo" rev-parse HEAD)"
if [ -n "$(git -C "$repo" status --porcelain)" ]; then
  echo "note: uncommitted or untracked files exist; they are NOT part of this check:"
  git -C "$repo" status --porcelain | head -20
fi
command -v uv >/dev/null || { echo "uv is required (https://docs.astral.sh/uv/)"; exit 1; }
command -v npm >/dev/null || { echo "npm is required for the pinned browser checks"; exit 1; }
work="$(mktemp -d)"
cleanup() {
  # Stop only what the clone's own launcher started, then remove the clone.
  if [ -d "$work/checkout" ]; then (cd "$work/checkout" && python3 scripts/dev/launcher.py stop >/dev/null 2>&1 || true); fi
  rm -rf "$work"
}
trap cleanup EXIT
git clone --quiet --no-hardlinks "$repo" "$work/checkout"
git -C "$work/checkout" checkout --quiet --detach "$commit"
echo "clean clone of $commit at $work/checkout"
cd "$work/checkout"
# Placeholder AI: no provider or tracing credential enters the clone's environment.
# DRBEAN_VAR_DIR is cleared so the clone uses its own var/, never yours.
run_clean() {
  env -u GEMINI_API_KEY -u GEMINI_MODEL -u GOOGLE_API_KEY -u GOOGLE_APPLICATION_CREDENTIALS \
      -u BEAN_GEMINI_ACCOUNT_GATE -u BEAN_GEMINI_ACCOUNT_DECISION_ID -u ANTHROPIC_API_KEY -u OPENAI_API_KEY \
      -u LANGSMITH_API_KEY -u LANGCHAIN_API_KEY -u DATABASE_URL -u DRBEAN_VAR_DIR -u DRBEAN_API_BASE \
      -u PYTHONPATH -u PYTHONHOME -u PYTHONUSERBASE -u VIRTUAL_ENV -u CONDA_PREFIX -u UV_PROJECT_ENVIRONMENT \
      -u UV_WORKING_DIRECTORY -u UV_PROJECT -u UV_PYTHON -u DRBEAN_BACKEND_PYTHON -u DRBEAN_SCIENCE_PYTHON \
      -u BEAN_COUNTERDEX_PYTHON -u BEAN_COUNTERDEX_REPLAY_PYTHON -u BEAN_TEST_PYTHON \
      -u BEAN_DATABASE_PATH -u BEAN_BLOB_DIR -u BEAN_ARTIFACT_DIR -u BEAN_AUTH_FILE -u BEAN_AUTH_TOKENS_JSON \
      -u PLAYWRIGHT_MODULE -u NODE_PATH -u NODE_OPTIONS \
      BEAN_AI_MODE=placeholder "$@"
}
run_clean python3 scripts/dev/launcher.py setup
mkdir -p "$work/npm"
touch "$work/npm/global.npmrc"
(
  cd tests/integration
  env -i PATH="$PATH" LANG=C.UTF-8 NPM_CONFIG_USERCONFIG=/dev/null \
    NPM_CONFIG_GLOBALCONFIG="$work/npm/global.npmrc" NPM_CONFIG_CACHE="$work/npm/cache" \
    npm ci --ignore-scripts --no-audit --no-fund --registry=https://registry.npmjs.org
)
if [ -n "${CHROMIUM_PATH:-}" ]; then
  if [ ! -f "$CHROMIUM_PATH" ] || [ ! -x "$CHROMIUM_PATH" ]; then
    echo "CHROMIUM_PATH must name an executable browser binary"
    exit 1
  fi
  echo "Using operator-selected browser: $CHROMIUM_PATH"
else
  run_clean node tests/integration/node_modules/playwright/cli.js install chromium
fi
git status --porcelain | grep -q . && { echo "setup modified tracked files or left untracked ones:"; git status --porcelain; exit 1; }
# Retain a new qualification record outside the disposable clone when requested.
status=0
run_clean python3 scripts/release/checklist.py "$@" --record || status=$?
if [ -n "${DRBEAN_RELEASE_EVIDENCE_DIR:-}" ]; then
  mkdir -p "$DRBEAN_RELEASE_EVIDENCE_DIR"
  evidence="$DRBEAN_RELEASE_EVIDENCE_DIR/clean-checkout-$commit-$(date -u +%Y%m%dT%H%M%SZ)-$$.json"
  cp docs/release-evidence/release-checklist.json "$evidence"
  echo "Retained qualification: $evidence"
fi
exit "$status"

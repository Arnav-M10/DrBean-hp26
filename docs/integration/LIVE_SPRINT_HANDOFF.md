# Live sprint integration handoff

Starting application commit: `d7abf3b33476cdecae3d4ec5779794255eff1941`. The fetched backend head `80d21bbf269d0892c888af819d84178b7512051f`, frontend head `78a5f5ba547cca9c1856ef11999077f4fd427584`, and integration head `3b66e1e` are already ancestors.

## Reproduce the controlled candidate

In a fresh Linux or macOS checkout of the starting commit, with Node 20+, uv and Python available, set these variables for every command. Pick free loopback ports and a fresh state path when repeating the instructions on a shared host.

```bash
export DRBEAN_VAR_DIR="$PWD/var/integration-d7abf3b"
export BEAN_DEV_API_PORT=28171 BEAN_DEV_WEB_PORT=28170
export BEAN_RESEARCH_MODE=controlled
python3 scripts/dev/launcher.py setup
python3 scripts/dev/launcher.py start --controlled-source-examples
node --test apps/web/*.test.mjs apps/web/study/*.test.mjs workspace-preview/tests/*.test.mjs
BEAN_AI_MODE=placeholder \
BEAN_COUNTERDEX_PYTHON="$PWD/.venv-engine/bin/python" \
BEAN_COUNTERDEX_REPLAY_PYTHON="$PWD/.venv-engine/bin/python" \
PYTHONPATH="$PWD/packages/counterdex_models" \
.venv/bin/pytest -q tests/test_gemini_chat_gateway.py tests/test_gemini_chat_model.py \
  tests/test_research_metered_application.py tests/test_research_controlled_application.py
```

Open `http://127.0.0.1:28170/` for the classic interface or `http://127.0.0.1:28170/study/#data` for the study interface. The Windows integration run used Ubuntu under WSL and the separate default `var/` of its isolated checkout. The API, worker and web readiness checks passed, and the browser opened a private session after choosing a new workspace. The web suite passed 164 tests. The focused backend suite passed 89 tests, with two Python syntax warnings from the installed Gemini SDK. The [public Theoph case](../../fixtures/theoph/README.md) completed through the normal browser review and manual Counterdex path.

## Handoff for Claude's live qualification

This candidate made zero Gemini calls during integration. No live allocation was created or inferred from the isolated database. The [earlier live receipt](../../evaluation/results/sprint/live-final-17c7f7a/qualification.json) recorded a malformed tool call before scientific dispatch and predates this application commit.

An independently authorized live run uses the classic page at `http://127.0.0.1:28170/` with `BEAN_RESEARCH_MODE=live` and the existing private configuration described in [Getting started](../getting-started.md#live-research-coordination). Use a separate state directory and ports for that run if the controlled instance needs to stay up. The operator must reconcile prior physical attempts and reserve only an explicitly authorized remaining allocation in the shared accounting record before allowing any dispatch. The browser must separately accept the frozen context disclosure and the proposed scientific operation. Retain the exact tested SHA, actual model requests and usage or unresolved reservations, canonical approval, worker outcome, and evidence reference. A live demonstration is pending independent qualification on the current commit.

## Rollback

Stop only the candidate with `python3 scripts/dev/launcher.py stop` from its checkout with the same state directory and ports. The launcher preserves the candidate database. For the controlled app, keep the existing deployment and its configuration. A Git merge does not redeploy the Mac runtime behind Vercel.

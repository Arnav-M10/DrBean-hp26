# Integration status

Concise summary. Details, inputs and owners are in the [issue ledger](issue-ledger.md); commands are in the [runbook](release-runbook.md). Regenerate the facts with `python3 scripts/release/checklist.py --record`.

**AI mode: placeholder. Live Gemini: disabled, not run. Model provider requests made by this project: 0.**

Last recorded: see `docs/release-evidence/release-checklist.json` (commit, platform, every check).

## Gates

| Gate | State | What passes | What is missing | Owner of the blocker |
|---|---|---|---|---|
| G0 Reliable launch, placeholder AI | **passed** (Linux x86_64) | setup, start, stop, recover; one store; restart reopens the same run and report bytes; a planted provider key cannot enable live mode | recheck on the target Mac | 4 |
| G1 Actual core | **not passed** | manual HTTP path end to end; approval and idempotency behave | API still selects the unavailable adapter, so the baseline returns `unsupported`; Owner 5's HTTP suite not delivered | 1, 2 (bridge); 5 (suite) |
| G2 Scientific decision | **not passed** | engine standalone: fixed-pair design and fresh native replay of its prepared bundle | design, native export and hypothetical follow-up through the API | 1, 2 |
| G3 AI-ready workflow | **not passed** | backend tests of controlled intake and the real deepagents graph with a controlled model; zero provider attempts in the launched stack | Owner 5's traversal and network-denial tests | 3, 5 |
| G4 Usable release | **not passed** | browser plan, approval, run retrieval and downloads against the real API | real science to show; source review, design and follow-up controls; observed task; rehearsal | 4 (after G1) |

## Interfaces Owner 4 depends on

| Seam | Current fact | Needed |
|---|---|---|
| Engine runtime | `.venv-engine` (CPython 3.11) is installed by setup; its interpreter path is exported to the API and worker as `BEAN_ENGINE_PYTHON` | Owners 1/2 confirm this variable, or name another; then `main.py` and `worker.py` select the real adapter |
| Adapter selection | `create_app` and the worker default to `UnavailableAdapter` | ordinary startup selects the qualified adapter and capabilities report it |
| Placeholder AI | launcher removes provider variables and sets `BEAN_AI_MODE=placeholder`; the provider layer itself still enables on `GEMINI_API_KEY` plus gate variables | Owner 3 makes disabled the code default with an explicit live switch (I-012) |
| Browser origin | web server proxies `/api/bean/v1/` to fixed `127.0.0.1:8000`, GET and POST only | unchanged unless a route needs another method |
| Owner 5 evidence | checklist runs `tests/integration/test_*.py` when present | the suite |

## Next acceptance action per owner

- **1 and 2:** baseline discovery callable from the worker through the engine runtime; then `python3 scripts/release/stack_smoke.py --require-science` must pass.
- **3:** explicit disabled default for the provider; controlled placeholder proposals labelled as such in responses.
- **5:** HTTP invariant suite in `tests/integration/test_*.py`; offline real-science lane; process-level model-network guard for the launched stack.
- **4:** after G1, connect source review, design approval, result table and follow-up controls; recheck the Mac; consultation.

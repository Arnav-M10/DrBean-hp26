# Integration status

Concise summary, at `main` `adac945` plus this branch. Each workstream's own log is in `docs/workstreams/`. Details, inputs and owners are in the [issue ledger](issue-ledger.md); commands are in the [runbook](release-runbook.md). Regenerate the facts with `python3 scripts/release/checklist.py --record`.

**AI mode: placeholder. Live Gemini: disabled, not run. Model provider requests made by this project: 0.**

Last recorded: see `docs/release-evidence/release-checklist.json` (commit, platform, every check).

## Gates

| Gate | State | What passes | What is missing | Owner of the blocker |
|---|---|---|---|---|
| G0 Reliable launch, placeholder AI | **not passed** | setup, start, stop, recover; one store; restart reopens the same run and report bytes; a planted provider key cannot enable live mode | **every approved run fails for an ordinary non-root user** (I-018): seen in CI, reproduced locally. Earlier "passed" results were root-only. Target Mac unverified. | 2 (I-018); 4 (Mac) |
| G1 Actual core | **not passed** | manual HTTP path end to end; approval and idempotency behave; the API and worker select the Counterdex adapter through the CPython 3.11 runtime; the engine itself now discovers and checks candidates (PR #4, 257 engine tests) | **the backend does not call the engine's discovery bridge**: it still reports `baseline_discovery: false`, so the approved baseline returns `unsupported` with no candidates; Owner 5's HTTP suite not delivered | 2 (adopt bridge, I-013); 5 (suite) |
| G2 Scientific decision | **not passed** | engine standalone replay; backend tests run real fixed-pair design, native download and replay over HTTP from an explicitly seeded regression pair | no public route can supply candidates (correctly), so design cannot start over ordinary HTTP until a baseline discovers a pair | 2 |
| G3 AI-ready workflow | **not passed** | backend tests of controlled intake and the real deepagents graph with a controlled model; zero provider attempts in the launched stack | Owner 5's traversal and network-denial tests | 3, 5 |
| G4 Usable release | **not passed** | browser plan, approval, run retrieval and downloads against the real API | real science to show; source review, design and follow-up controls; observed task; rehearsal | 4 (after G1) |

## Interfaces Owner 4 depends on

| Seam | Current fact | Needed |
|---|---|---|
| Engine runtime | `.venv-engine` (CPython 3.11) is installed by setup; the launcher passes its interpreter as `BEAN_COUNTERDEX_PYTHON`, with `BEAN_SCIENCE_ADAPTER=counterdex` and `BEAN_ARTIFACT_DIR` under `var/` | agreed and working |
| Adapter selection | ordinary startup selects Counterdex; health and capabilities report it available with native replay; `verified_in_environment` stays false by design (each result needs its own check and replay) | baseline producer |
| Placeholder AI | launcher removes provider variables; the API reports `ai_mode: disabled_placeholder` and `dispatch_enabled: false`, and stays unconfigured even when started by hand with key, model and gate variables set | nothing now; a live switch needs a new user instruction |
| Plan contract | plans must carry `scientific_profile: counterdex.v1` and a reviewed objective; the web workspace and the stack smoke were updated to send them | unchanged |
| Browser origin | web server proxies `/api/bean/v1/` to fixed `127.0.0.1:8000`, GET and POST only | unchanged unless a route needs another method |
| Owner 5 evidence | checklist runs `tests/integration/test_*.py` when present | the suite |

## Next acceptance action per owner

- **2, first:** fix the per-user process limit in the scientific child (I-018); acceptance `python3 scripts/release/user_conditions_check.py`.
- **2:** call the engine's discovery bridge from the worker (interface request in I-013); then `python3 scripts/release/stack_smoke.py --require-science` must pass.
- **1:** nothing blocking; discovery, bridge and decision fixtures are delivered.
- **3:** controlled placeholder proposals labelled as such in responses.
- **5:** HTTP invariant suite in `tests/integration/test_*.py`; offline real-science lane; process-level model-network guard for the launched stack.
- **4:** after G1, connect source review, design approval, result table and follow-up controls; recheck the Mac; consultation.

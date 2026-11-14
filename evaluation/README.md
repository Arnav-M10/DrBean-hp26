# Evaluation harness (Workstream 5)

Standard-library Python, run with CPython 3.11. Owner: Workstream 5 (independent adversarial validation). Protocol and rules: [docs/evaluation-protocol.md](../docs/evaluation-protocol.md). Current findings: [FINDINGS.md](FINDINGS.md) (generated from `findings.json`). Latest report: [results/REPORT.md](results/REPORT.md).

**No command here dispatches a model request.** Live lanes are disabled (`NOT_RUN`); there is no flag that activates them and `budget open` refuses. Real local computation (API, worker, Counterdex, native replay) does run. Any AI in the current lanes is absent or a labelled *controlled placeholder*, never Gemini evidence.

## Integrated acceptance checkpoint

The final source commit `159fd65303c5ff87a14dfa616f88dbd5a76777b5` was
qualified again after the explanatory-text corrections: all seven ordinary HTTP
entries and all 22 native controls passed on a clean tree. The
[independent scientific gate](results/integration/159fd65-science-gate.json)
passes every required check, including append-only integrity, adverse controls,
supported-host execution, verified zero model dispatch and no unresolved P0.
The latest [report](results/REPORT.md) includes all 112 historical attempts.
Subsequent changes in this checkpoint only record this evidence and its summary.

Source `d821202b339ed60720e3c919d6be47e450e3b894` passed all seven
`offline_real_science` HTTP entries and all 22 native controls on a clean macOS
worktree, using the locked backend Python 3.13.18 and installed Counterdex 0.3.0
on CPython 3.11.17. Cancellation and worker-loss recovery used ordinary scientific
computation with 128 declared synthetic replicates; no diagnostic barrier was
active. Baseline history is resolved separately from empty prospective reuse;
follow-ups bind the complete accepted proposal and retain their own origin,
time and allowance. Frozen cases and historical records remain intact.

The [fresh-clone log](results/integration/d821202-clean-checkout.log) records
559 backend tests, 47 independent HTTP tests, passing engine/harness/launcher/web
checks, exact schema exports, secret scanning, both implemented browser checks
and 31/31 ordinary startup/restart checks. Setup installed locked dependencies
and pinned Playwright 1.63 with its matching Chromium 153. The strict product
release command correctly exited 1: G0–G3 passed; G4 still requires browser
source-review and follow-up controls. Scientific acceptance does not close those
product gaps. Live model qualification remains unrun; no application model
provider requests were made.

## Commands (entry points for Owner 4 and CI)

| Command | What it does | Exit |
|---|---|---|
| `python3.11 -m unittest discover -s evaluation/tests -v` | harness unit tests (131; Node comparison skips when Node is absent) | 0 = pass |
| `python3.11 evaluation/cli.py verify` | frozen manifest v3 + archived ancestry + science packets | 0 = OK, 1 = drift |
| `python3.11 evaluation/cli.py selftest` | grader exemplars (24 compliant, 62 violating). Harness only, never product evidence | 0 / raises |
| `python3.11 evaluation/cli.py run --lane offline_real_science --subject http-launch` | launches an isolated API + worker (fresh temp SQLite, blobs, in-memory tokens, allowlisted env, egress guard) and drives the real HTTP routes; appends attempts | 0 only if every entry passed; 2 otherwise |
| `python3.11 evaluation/cli.py run --lane offline_real_science --subject http-owner4-launcher --results evaluation/results/owner4-launcher` | the same scenarios through Owner 4's unmodified `scripts/dev/launcher.py start` (isolated `DRBEAN_VAR_DIR`, harness-written synthetic `auth.json`, egress guard via `PYTHONPATH`, dummy provider credentials in the launcher's own environment). Needs `launcher.py setup` once and ports 8000/4173 free; a failed unmodified start is recorded before one labelled retry with `apps/api` on `PYTHONPATH`. Separate history; worker kill/restart stays on `http-launch` | as `run` |
| `python3.11 evaluation/cli.py controls [--app-repo DIR --results DIR]` | engine-level native controls in fresh CPython 3.11 processes (not HTTP); appends `results/controls.jsonl`. `--app-repo` previews another checkout's engine package into a separate results directory | 0 all passed, 2 otherwise |
| `python3.11 evaluation/cli.py gate --require release [--output FILE]` | machine-readable release gates from recorded evidence at the tested commit, or at an ancestor whose later changes touch only evidence and documentation paths (`evaluation/results/`, findings, this README, the protocol and the owner log; listed in the output as `evidence_commits`). A change to any code, including the harness, needs fresh evidence | 0 only if every required gate passed on a clean tree; 3 otherwise |
| `python3.11 evaluation/cli.py inventory` | same gates, informational | 0 unless the harness itself is broken |
| `python3.11 evaluation/cli.py history` | verifies the hash-chained attempt history, its fork segments, trace and evidence digests | 0 / 1 |
| `python3.11 evaluation/cli.py report` / `findings` | regenerate `results/REPORT.md` / `FINDINGS.md` | 0 |
| `.venv/bin/python -m pytest tests/integration -m "real_stack or controlled_app or zero_dispatch"` | Python HTTP/invariant tests (needs the locked backend env; markers below) | pytest |
| `.venv/bin/python scripts/evaluate.py` | compatibility inventory: `fixtures/intake` corpus integrity + imported evidence; mirrors the harness gates | 0 unless corpus integrity fails |

Interpreters are operator-selected, never chosen by evidence: `DRBEAN_BACKEND_PYTHON` (default `.venv/bin/python`, the `uv sync --locked` env) and `DRBEAN_SCIENCE_PYTHON` (default Owner 4's `.venv-engine/bin/python` when present, else `python3.11`; must be CPython 3.11). Non-credential `BEAN_*` stack settings can be passed with `--stack-env BEAN_NAME=VALUE`; credential-shaped names are refused.

pytest markers (`tests/integration/conftest.py`): `real_stack` (launches processes), `real_science` (needs the real scientific adapter end to end), `controlled_app` (in-process app with controlled provider/model doubles), `zero_dispatch`. The whole pytest session runs under the egress guard once that directory is collected.

## Layout

| Path | Content |
|---|---|
| `manifest.json` | Frozen manifest **v3**: cases, sources, holdouts, science packets, schedule, lane rules, caps. `manifests/manifest-v1.json` keeps v1 byte-for-byte (the 34 pre-merge attempts reference its digest). Change a frozen file only through `cli.py freeze`, which bumps the version and archives the ancestor. |
| `cases/C01.json` … `C12.json` | Frozen development cases (controlled tier). `authoring/build_cases.py` wrote them. |
| `cases/science/hero-v2.json` | The shared five-row synthetic hero (clean.png values; team-selected domains, claim, grid 6/8 h, allowance 0.2, construction to 8 h). Application input. |
| `cases/science/changed-input-v1.json` | Changed-input variant (row 3: 8.00 → 7.60). Not a designated positive. |
| `cases/science/fixed-pair-regression-v1.json` | The audit's fixed pair and its controls. **Regression oracle only, never a production lookup or application input.** |
| `selftest/` | Grader exemplars. Never product evidence. |
| `sources/` | Synthetic lab-sheet PNGs, expected transcriptions (`region_xywh_px`), renderer; `h01`, `h04` sealed holdouts (see protocol: exposure). |
| `drbean_eval/launcher.py` | Isolated local stack: API + worker processes, readiness (API / worker lock / science capability separately), owned process groups, orphan detection. |
| `drbean_eval/guard/sitecustomize.py` | Egress guard loaded into every launched process: audit hook refusing non-loopback DNS/connect, spy refusing `google.genai.Client` construction, credential *names* recorded (never values). |
| `drbean_eval/http_client.py`, `science_flow.py` | Authenticated client and the HTTP scenarios (hero, changed input, concurrency, design authority, follow-ups, cancel/restart, zero dispatch). |
| `drbean_eval/native.py` | Download validation (hash, length, media type vs reference and header), native packet vs entity envelope, fresh CPython 3.11 replay with anchors from authenticated records. |
| `drbean_eval/engine_controls.py` | Fixed-pair, defense, endpoint, touching-band and follow-up controls via Counterdex public operations. |
| `drbean_eval/kinetics.py` | Independent 80-digit decimal oracle for `C(t)=A(e^{-ke t}-e^{-ka t})`. A test oracle, not a proof system. |
| `drbean_eval/qualify.py`, `history.py`, `gates.py` | Qualification of case-less entries, hash-chained history, release gates. |
| `drbean_eval/projection.py` | Documented mapping: `rows[i].time` ↔ `row{i+1}_time`, `candidate_exact` ↔ `value`, `bbox=[x0,y0,x1,y1]` ↔ `region_xywh_px=[x,y,w,h]` with original image dimensions. |
| `drbean_eval/contract.py` | Independent DB-SC-1 oracle, aligned (revision 2) with the authoritative `bean_api/canonical.py` and cross-checked against it. |
| `drbean_eval/budget.py` | Harness JSONL budget for a *future* cohort. Not the backend ledger; isolated tests only. |
| `findings.json` / `FINDINGS.md` | P0/P1/P2 findings with exact commit, input, command, expected, observed, evidence. |
| `results/` | `attempts.jsonl` (append-only, chained), `forks/*.jsonl` (records a parallel branch appended to the same history, moved unchanged at merge; each verified from its fork point on the main chain), `traces/<attempt>.json` and `traces/<attempt>/` evidence (records, artifacts, index), `lane-runs.jsonl`, `controls.jsonl`, `REPORT.md`. |

## Observation schema `eval-observation/v1`

Unchanged for the frozen cases (see the field list in the protocol). The `offline_real_science` lane adds, all produced by the `http-launch` subject the runner itself executes:

| Field | Meaning |
|---|---|
| `lane_version` | lane rule version from the manifest (currently 1) |
| `provider.transport` | `none` (manual plans) or `controlled`; `live` is rejected |
| `tools.transport` | must be `real` |
| `provider_requests` | must be exactly `0`, and only when the guard verified it |
| `external_dispatch` | `{verified, egress_attempts, client_constructions, guarded_processes, credential_names_present}` from the guard |
| `checks[]` | `{id, outcome: passed|failed|blocked|not_observed|not_applicable, level: required|informational, detail, finding}` |
| `records`, `job_ids`, `scientific_jobs` | actual application identities and the jobs this entry started |
| `evidence_index`, `native_artifacts` | saved response records and downloaded bytes with digests; anchor-record names per packet |
| `exchanges[]` | method, route template, status, server request id, response digest, local latency (no bodies, no tokens) |

A `blocked` or `not_observed` required check makes the entry `unrun` with the reason; it is never a pass. A state such as `completed` qualifies nothing on its own.

Never put raw prompts, provider replies, hidden reasoning, keys or personal data in an observation; the runner drops known private keys, redacts secret-shaped strings and withholds any trace that still contains a planted sentinel.

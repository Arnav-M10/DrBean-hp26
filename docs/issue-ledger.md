# Cross-owner issue ledger

Maintained by Workstream 4. Each entry has a reproducible input, expected behaviour, actual evidence, responsible owner and retest status. Nobody fixes another owner's component. Summary by gate: [INTEGRATION_STATUS.md](INTEGRATION_STATUS.md).

Entries I-001 to I-010 were opened before the backend and engine were merged. Their original text is kept below; the table gives their current status. Entries from I-011 were opened on the integrated tree at `586fb9b` and rechecked after PR #3 (`main` at `fa91e13`).

| ID | Owner | Status | Summary |
|---|---|---|---|
| I-001 | 2 | **closed** | Backend and `/api/bean/v1` now exist and start with one command |
| I-002 | 2 | **closed** | Schemas are published in `shared/contracts/DB-SC-1` |
| I-003 | 2, 3 | open | Controlled transports must be unreachable in ordinary startup (see I-012) |
| I-004 | 2, 3, 5 | open | Two budget ledgers exist (backend SQLite, harness JSONL); one authority must be defined before any live call |
| I-005 | 1 | partly closed | Engine exists and passes standalone; not integrated (see I-013) |
| I-006 | 2, 4 | open | Decimal input grammar differs between the web parser and the server |
| I-007 | 4 | open | Draft download cannot be reopened; durable server records can |
| I-008 | 5 | open | Harness expected transcriptions need a human visual check |
| I-009 | human team | open | Reuse ruling, names, consultation; live Gemini deliberately deferred |
| I-010 | 2, 3 | open | Conditional objective for harness cases C08/C09 versus the real plan contract |
| I-011 | 2 | open, minor | Float in JSON is refused without naming the field |
| I-012 | 3 | **closed on `main` at `fa91e13`** | Provider stays unconfigured with key, model and gate variables set; API reports `ai_mode: disabled_placeholder` |
| I-013 | 2 | **closed on `main` at `1f75bdc` (PR #6)** | Baseline discovery now runs through ordinary startup: `stack_smoke.py --require-science` exits 0 with a certified counterexample, 2 candidates and a native artifact |
| I-014 | 1, 2 | **closed** | Two runtimes; the backend calls the engine in a child process on CPython 3.11 |
| I-015 | 2, 4 | open, target platform | `resource_policy.py` now omits `RLIMIT_AS` on macOS; still unverified on the Mac |
| I-016 | 5 | open, blocks strict gate | HTTP/invariant suite and offline real-science lane not delivered |
| I-017 | 4 | **open, now unblocked** | Browser controls for source review, design and follow-up not built |
| I-019 | 2, 4 | **closed** | PR #6 gates queueing on `science.available` and `baseline_discovery` (`baselineAvailable`), the same fields proposed |
| I-018 | 2 | **partly fixed on `main` at `1f75bdc`; one test still fails on GitHub's runner** | Locally 5 of 5 as an unprivileged user owning 64 processes. On the runner (uid 1001, run 43554490810) 4 of 5: `test_descendant_cannot_escape_by_outliving_adapter` still fails. Whether an approved run completes there is shown by the stack smoke step in the same job. |

## I-011: float refusal does not name the field (Owner 2)

- **Input:** `POST /api/bean/v1/workspaces/{w}/datasets` with `rows[0].concentration` as the JSON number `4.8`.
- **Expected:** 422 with `field_paths` naming `rows.0.concentration`, as happens for the non-canonical string `"4.8"`.
- **Actual:** 422 `invalid_json`, `field_paths: []`. The value is correctly refused, not repaired. The browser never sends floats, so this affects other clients only.
- **Evidence:** `docs/release-evidence/stack-smoke.json`, fact `float_refusal_names_the_field: false`.

## I-018: scientific jobs fail for an ordinary (non-root) user (Owner 2)

- **Blocking gate:** G0 and G1. This affects every teammate's laptop and the presentation device.
- **Observed:** GitHub Actions run 43552209712 on `5e4d76b` (ubuntu runner, user `runner`): backend job `2 failed, 233 passed, 29 skipped`; stack smoke `worker-finished-the-run: failed`, 28 of 31. The same commit passes locally, where the container runs as root.
- **Minimal reproduction (any Linux, no network):** `python3 scripts/release/user_conditions_check.py`. It runs Owner 2's `tests/test_science_boundary.py` as an unprivileged user who already owns 64 processes. Result: `2 failed, 3 passed`: `test_cancellation_terminates_descendants` and `test_descendant_cannot_escape_by_outliving_adapter` return `{'worker_error': 'scientific_worker_failed'}`.
- **Threshold measured:** passes when that user owns 30 processes, fails at 34 (`--processes 30`, `--processes 34`).
- **Cause, as far as the evidence shows:** `apps/api/bean_api/resource_policy.py` applies `RLIMIT_NPROC` with `processes=32` in the scientific child. On Linux and macOS that limit counts every process owned by the same user, not just the child's descendants, and it is not enforced for root. A desktop user owns far more than 32 processes, so the first process the child tries to start is refused. The Counterdex adapter must start the CPython 3.11 engine process, so real science cannot run. Owner 2 should confirm the cause.
- **Expected:** an approved run completes for a non-root user under normal desktop load, while the worker still bounds the job's own process tree (for example by tracking and killing the owned process group or session, which the code already does, instead of a per-user count).
- **Not acceptable:** removing every guard, or requiring the stack to run as root.
- **Acceptance:** `python3 scripts/release/user_conditions_check.py` exits 0; the CI `backend` and `stack` jobs go green.
- **Why earlier evidence missed it:** all local runs by Workstream 4 were as root. Earlier statements that the launch path "passed (Linux)" were true only for root and are corrected in the status documents.

## I-019: which capability enables queueing (Owner 2 to confirm)

- **Current behaviour:** capabilities report `science.verified_in_environment: false` permanently, with the note that each result needs its own check and replay. The browser used to enable **Queue approved manual run** only when that flag and `model_templates[].scientific_adapter_qualified` were true, so the button could never enable, even once discovery works.
- **Change made in the web client (Workstream 4):** `scienceReadiness` in `apps/web/api.mjs` enables queueing when `science.available === true` and `science.baseline_discovery === true` (the older flags are still honoured), fails closed on anything unknown, and shows the server's own reason otherwise. Today that keeps the button disabled, with the text "the scientific engine is installed, but this server cannot yet search for candidates (baseline_producer_unavailable)".
- **Needed from Owner 2:** confirm those two fields are the intended gate, or name the right one. The server stays the authority either way: it refuses a run it cannot perform.

## I-012: provider must be disabled by default in code (Owner 3)

- **Input:** start the API by hand (not through the launcher) with `GEMINI_API_KEY`, `GEMINI_MODEL`, `BEAN_GEMINI_ACCOUNT_GATE=approved`, `BEAN_GEMINI_ACCOUNT_DECISION_ID` and an image token bound set.
- **Expected for this sprint:** Gemini stays disabled until an explicit live switch is set on a new user instruction. A key appearing in the environment must not be enough.
- **Actual:** `provider_config_from_env` in `apps/api/bean_api/main.py` builds a ready provider from those variables alone. `scripts/dev/start.sh`, the stack smoke, the browser check and CI all remove them, and the smoke proves a planted decoy key leaves `gemini.configured` false. A hand-started API is not protected.
- **Proposed seam:** honour `BEAN_AI_MODE` (the launcher sets `placeholder`); require an explicit different value plus the existing gate before `check_ready` can pass. Owner 3 decides the name.
- **Retest:** `python3 scripts/release/stack_smoke.py`; plus Owner 5's network-denial test.

## I-013: engine bridge missing (Owners 1 and 2)

- **Input:** `scripts/dev/start.sh`, then `python3 scripts/release/stack_smoke.py --require-science`.
- **Expected (G1):** capabilities report an available, qualified adapter; the approved baseline run on the shared five-row example returns a real scientific outcome with candidates and native artifact bytes.
- **Actual:** `science.implemented=false`, reason `groundwork_adapter_not_installed`. The run completes with `scientific_outcome: unsupported`, 0 candidates, 0 artifacts. The engine is installed at `.venv-engine` and its interpreter path is passed to both processes as `BEAN_ENGINE_PYTHON`, unused.
- **Also needed from Owner 1:** candidate discovery from supplied input. The engine's current entry points compare two supplied candidates; they do not search for an outside candidate.
- **Retest:** the command above exits 0.

**Update after PR #3:** capabilities now report `available: true`, adapter Counterdex 0.1.0, `native_replay: true`, `baseline_discovery: false`, reason `baseline_producer_unavailable`. The approved baseline on the shared five-row example completes with `scientific_outcome: unsupported`, reason `baseline_producer_unavailable`, 0 candidates, 0 artifacts. Design proposals take their two candidates from the historical run's result, and no public route can seed them, which is correct; so design cannot begin over ordinary HTTP. Backend tests exercise real design, native download and replay only from an explicitly seeded regression pair. The remaining work is Owner 1's discovery producer.

**Update after PR #4 (`main` at `adac945`), interface request to Owner 2:**

- **Blocking gate:** G1, then G2.
- **Current behaviour:** `apps/api/bean_api/counterdex_child.py` returns `"baseline_discovery": False` unconditionally; `counterdex_adapter.py` therefore answers every baseline with `unsupported` / `baseline_producer_unavailable`. Reproduce: `python3 scripts/release/stack_smoke.py --require-science` (exit 1; launch path 31 of 31).
- **Available since PR #4 (Owner 1):** `counterdex bridge` (protocol `counterdex.bridge.v1`, one bounded request on stdin, one response), `counterdex/application.py` (`project_application`, `project_design`, binding verifiers), `counterdex/search.py` and `baseline.py` (bounded discovery plus exact check), `replay-baseline` and `replay-native`; parent-side example `packages/groundwork_adapter/scripts/supervise_bridge.py`; mapping in `packages/groundwork_adapter/docs/APPLICATION_MAPPING.md` and `BRIDGE.md`. Engine tests: 257 pass on CPython 3.11.
- **Needed behaviour:** the worker's baseline call goes through that bridge with the frozen problem and dataset records; the result carries the discovered candidates, per-candidate checks, native bytes stored before any artifact reference is published, and `baseline_discovery: true` in capabilities.
- **Acceptance example:** on the shared five-row example the engine's own fixture (`fixtures/decision/hero-baseline.*`) finds a reference with ke 1631/12700 inside the claim and an outside candidate with ke 101/1016 < 1/10. The application must reach scientific predicates like these by real search, not by returning those constants.
- **Stale or invalid example:** a design proposal naming candidates that are not in that run's result must still be refused.
- **Runtime:** the launcher already passes `BEAN_COUNTERDEX_PYTHON` pointing at `.venv-engine` (CPython 3.11, counterdex installed from the tree by setup).
- **Consuming check:** `python3 scripts/release/stack_smoke.py --require-science` exits 0; then Owner 5's HTTP suite.

## I-014: two interpreters (Owners 1 and 2)

- **Input:** `python3.13 -m unittest discover -s packages/groundwork_adapter/tests`; the same on 3.11.
- **Actual:** 3.11: 138 passed. 3.13: 4 failures, 23 errors. The backend requires 3.12 or 3.13.
- **Decision taken for launch:** two explicit runtimes, both installed by setup. The bridge must therefore cross a process boundary, or Owner 1 qualifies 3.12/3.13.

## I-015: target Mac recheck (Owner 2, with Workstream 4)

- **Historical finding at the audit commit:** on the target Mac the backend had 136 passed, 17 failed, 11 setup errors, from unsupported `RLIMIT_AS` in image and scientific process setup.
- **Current evidence:** Linux x86_64 only: 164 backend tests pass. `apps/api/bean_api/science.py` still calls `resource.setrlimit(resource.RLIMIT_AS, ...)` unconditionally.
- **Retest:** on the Mac, `scripts/dev/setup.sh` then `python3 scripts/release/checklist.py --record`. Not done; no Mac is available to this workstream.

## I-016: Owner 5 evidence not delivered

- **Expected:** `tests/integration/test_*.py` driving baseline, approved design, native download and replay, and hypothetical follow-up through ordinary startup; an offline real-science lane in the harness; a model-network guard.
- **Actual:** none present. The checklist reports `owner5_http_suite` as unrun, which keeps G1 to G3 from passing in strict mode.

## I-017: remaining browser controls (Workstream 4)

- **Built by a teammate at `586fb9b`:** connect, workspace, save inputs, frozen plan review, explicit approval, queue (disabled until the adapter is qualified), run retrieval, evidence and report download.
- **Not built:** source image beside a placeholder proposal with review; candidate pair, feasible times and allowance review with separate design approval; result table with bands; actual or hypothetical follow-up; native evidence download with the replay command.
- **Why not yet:** the work order starts these after G1. Building them against an adapter that returns `unsupported` would mean guessing response shapes.

---

# Entries opened before the merge (original text)

## I-001: no backend or API (Owner 02)

- **Input:** `git ls-tree -r --name-only HEAD`; `python3 scripts/release/checklist.py`.
- **Expected:** a documented launch command starts a backend that answers `GET /api/bean/v1/capabilities` with no key configured and no provider call.
- **Actual:** only `apps/web` and Owner 04 paths exist. `capabilities_probe` is unrun. Boundaries B02 and B04 to B12 are unrun.
- **Retest:** set `DRBEAN_API_BASE` and rerun the checklist.

## I-002: schemas not frozen (Owner 02)

- **Input:** shared contract section 8 lists routes without body schemas.
- **Expected:** versioned request and response schemas, or a generated client, for every route the cases touch.
- **Actual:** none published. `HttpSubject.run_entry` reports every case as unavailable instead of inventing bodies.
- **Proposed route to evidence without waiting:** have the backend's controlled test boundary write one `eval-observation/v1` file per case (`<entry_id>.observation.json`, schema in `evaluation/README.md`) and run `python3 evaluation/cli.py run --lane fixture_contract --subject recorded:<dir>`. The runner rejects observations that attest another lane, commit or case digest.
- **Retest:** rerun the fixture lane; expect 24 graded attempts.

## I-003: controlled transport must not be reachable in production (Owner 02)

- **Expected:** the controlled provider and controlled tool outcomes are selected by explicit deployment configuration. A production caller cannot inject a successful checker or provider response through a request flag, header or body field. Health probes make no provider call.
- **Actual:** not testable yet.
- **Retest:** Owner 04 will add a check that sends the controlled-transport selector to a live-configured instance and expects rejection.

## I-004: shared budget ledger (Owner 02)

- **Expected:** before each Gemini request the provider layer counts input tokens, sets a maximum output size, and reserves both in `evaluation/ledger/provider_budget.jsonl` through `BudgetLedger.reserve`; afterwards it reconciles provider-reported usage; a timeout stays reserved (`mark_unknown`). Observations report `usage.requests[]` with `acceptance`, token counts and the provider request id where available.
- **Actual:** the ledger and its tests exist; nothing calls it because no provider layer exists. The manifest's per-request maxima (intake 3,000 in / 700 out; agent 1,600 in / 400 out) are proposals that only become hard limits when the provider layer enforces them.
- **Retest:** `python3 evaluation/cli.py budget status` after the first authorized live request.

## I-005: no scientific adapter; oracle review (Owner 01)

- **Expected:** `packages/groundwork_adapter/` with baseline evidence, fixed-pair checking and prepared native replay; review of the expected results in cases C08 to C12.
- **Actual:** absent. Cases C10 to C12 use the elementary constructed oracle from the work order (`u' = a`), recomputed in `evaluation/tests/test_core.py`. Checked pair separation is recorded as unshipped; the advertised tier is numerical guidance.
- **Retest:** Owner 01 signs off or corrects `evaluation/cases/C08.json` to `C12.json`; a correction needs a new manifest version.

## I-006: decimal input grammar (Owners 03 and 02)

- **Input:** in `apps/web`, `parseExact` with `+5`, `.5`, `5.`, `+1/2`, `1/-2`.
- **Expected:** one agreed input grammar. The contract says decimal input goes through "an explicit finite decimal parser that retains its source spelling". It does not say whether a leading plus, a bare leading or trailing point, or a negative denominator are accepted.
- **Actual:** the web accepts all five and normalizes them (`5/1`, `1/2`, `5/1`, `1/2`, `-1/2`). The harness oracle's `decimal_to_rational` rejects `.5` and `5.`. Canonical outputs agree wherever both accept (13 samples, `test_web_exact_parser_agrees_with_oracle`).
- **Risk:** a value the browser accepts could be rejected by the server after review. Owner 02 decides the server grammar; Owner 03 matches it.
- **Retest:** extend the cross-language sample list once decided.

## I-007: draft download cannot be reopened (Owner 03)

- **Input:** download a draft in `apps/web`, then look for an import action.
- **Expected for release:** exact downloaded bytes reopen against expected identities (boundary B10).
- **Actual:** the editor has no reopen action (stated in `apps/web/README.md`). The download is an input record, not a report.
- **Retest:** boundary B10 once reports exist.

## I-008: expected transcriptions need human review (Owner 03 or any teammate)

- **Input:** `evaluation/sources/*.png` beside `evaluation/sources/expected/*.json`.
- **Expected:** a person confirms each expected transcription against the image, and that the stain in `c04a.png` and `h04.png` really makes `0.2` versus `2` ambiguous to a reader.
- **Actual:** transcriptions are derived from the generator specification, not checked by eye. Each file says `human_visual_review: pending`.
- **Retest:** record the reviewer and date in each expected file; that changes the files, so freeze a new manifest version before any live grading.

## I-009: decisions only the human team can make

- Organizer ruling on reuse of pre-event work: pending.
- Gemini account: key, paid or unpaid tier, region and audience eligibility, pinned model, spending allowance: pending. No cohort is open, so the harness refuses live lanes.
- Team names and Discord usernames for the submission: pending.
- Peri consultation with a qualifying organization: not held.
- Main track: Science and Discovery, confirmed by the team on 14 November. Rookie eligibility: pending.

## I-010: conditional objective for C08 and C09 (Owner 02)

- **Expected:** the reviewed plan can express "run the allowance comparison only after a checked counterexample with matching binding", visible to the agent and enforced where reservations are made.
- **Actual:** the cases assume this shape (`evaluation/cases/C08.json`, `input.plan`). If the real plan contract differs, the cases are adapted to it and the changed expectation is recorded in a new manifest version. No test-only authority rule will be added.

# Evaluation protocol

Owner: Workstream 5 (independent adversarial validation). This portfolio is feasibility evidence. It is not a statistical benchmark, a model comparison or a prediction of judging results. Counts are reported with denominators. No percentile, win probability or productivity percentage is reported from a handful of samples.

**Current AI mode: placeholder, zero spending.** No current lane, test, rehearsal or script may make an external Gemini or other model request. Live lanes are retained but disabled (`NOT_RUN`). Real local computation (API, worker, Counterdex discovery/checking, native replay) runs and is reported as real. Controlled provider and model outputs are labelled *controlled placeholder output* and are never presented as Gemini reasoning, extraction accuracy or latency.

## Evidence lanes (manifest v2)

Declared before any run. A result in one lane is never relabelled as another; the runner enforces this from the observation's own attestation and the manifest's lane rules.

| Lane | v | State | Provider | Tools | What it tests | What it does not show |
|---|---|---|---|---|---|---|
| corpus integrity | – | current | none | none | `fixtures/intake` and `evaluation/sources` bytes, digests, decodability (`scripts/evaluate.py`, `cli.py verify`) | anything about extraction |
| `fixture_contract` | 1 | current | controlled / none | controlled | the application's handling of controlled provider responses and tool outcomes (the offline controlled model/application lane) | Gemini quality or real science |
| `offline_real_science` | 1 | **current, new in v2** | none / controlled | **real** | actual API, worker and scientific tools through HTTP; separate design approval; raw download; fresh native replay; **verified zero external model dispatch**; no cohort | Gemini behaviour; generality beyond the reviewed scenarios |
| `live_intake`, `live_agent_controlled_tools` | 1 | **disabled, NOT_RUN** | live | – / controlled | future live Gemini decisions on declared inputs | – |
| `actual_full_stack` | 1 | **disabled, NOT_RUN** | live | real | the v1 lane that coupled real science to a live provider; kept with its v1 meaning | – |
| human task | – | when a person is available | – | – | one consenting person's interaction (`docs/human-task/`) | adoption or impact |

Grader self-test (`evaluation/selftest/`) proves the grader and is never recorded as evidence about the product. Engine-level controls (`cli.py controls`) exercise Counterdex's public operations directly; they pin scientific semantics but are not the HTTP path.

### Qualification of the real-science lane

An entry without frozen case assertions passes only when `qualify.py` re-checks, itself:

1. evidence class `executed_acceptance`: the runner executed the `http-launch` subject against a stack it launched in this process. Recorded or imported observations are `imported_claim` and never qualify;
2. every listed evidence file exists with its digest; saved authenticated records link up (dataset → problem → plan digests, investigation-scoped approval, run plan/approval, evidence run/problem, design request historical run and exact candidate vectors from that run, design-scoped approval, design job, suggestion);
3. every native packet still matches its reference and passes a **fresh** CPython 3.11 replay run by the qualifier, with anchors re-extracted from the saved authenticated records, never from the bundle;
4. the egress guard was active in the API and the worker and recorded zero external attempts;
5. no required check failed. `blocked` (another workstream's prerequisite is absent) or `not_observed` (the run never reached the state the check needs, for example no sustained computation to cancel) makes the entry `unrun` with the reason. Neither is ever a pass.

`state: completed`, `status: passed` or a nonempty reference string cannot qualify anything. Designated known-positive cases (the hero) are checked by predicates, not optimizer floats: an exact outside candidate freshly compatible, candidates binding the reviewed problem, design using the same candidates, every approved grid time retained in order, strictly positive selected checked margin, replay against the expected revision. A changed-input case may legitimately return *no counterexample found* or *no separation established* if freshly computed and honestly scoped.

### Fixed-pair regression controls (engine level)

The audit pair (reference A=9.041075603155, ke=0.122, ka=3.54; outside A=8.267973235218, ke=0.074, ka=4.17) is a regression oracle only. With historical allowance 0.5: grid [6,8] h / 0.2 mg/L selects 8 h (margin ≈ 0.76719); [6] / 0.2 selects 6 h (≈ 0.55535); [6,8] / 0.6 establishes no separation while both candidates stay compatible and replay passes. Hypothetical 8 h readings with allowance 0.2: 3.4 keeps the reference and excludes the outside candidate, 4.57 the reverse, 4.0 excludes both; the aggregate pair status is reported as *scientific exclusion* (integrity passed, binding matches, verification invalid), distinct from corruption. These establish responses to the reviewed constraints for this pair, not global optimality, an instrument's capability or the original interval. An independent 80-digit decimal oracle (`kinetics.py`) recomputes the expectations without Counterdex.

Three defenses stay distinct: a wrong expected identity fails **binding**; a changed byte fails **integrity**; a mathematically false enclosure with internal hashes recomputed in the test fails **fresh computation**. For the mutation the real original anchor rejects the packet first; a deliberately changed test-only anchor is then supplied solely to reach the mathematical check. That diagnostic sacrifices packet authentication on purpose and authenticates nothing. Endpoint equality is inside the closed claim; touching bands (allowance equal to half the computed centre gap) give a non-positive exact margin and no selection.

## Zero external model dispatch: how it is proved

- Every launched process loads `evaluation/drbean_eval/guard/sitecustomize.py`: an audit hook refuses non-loopback DNS and connections, and a spy refuses construction of `google.genai.Client` (which LangChain's Gemini model also builds). SDK imports, types and schemas stay allowed. Every refusal is logged; an attempt is a **P0 finding even though nothing left the machine**.
- The launcher builds environments from an allowlist. Provider credential variables are never inherited; tests may pass only `DRBEAN-DUMMY-...` values to prove configuration alone cannot dispatch. No real key is read, copied or tested.
- The pytest session for `tests/integration` runs under the same guard.
- `RS-ZERO-DISPATCH` checks the guard was active in the API and the worker, zero attempts, no credential names in the launched environment, empty provider-attempt ledgers for every harness workspace and no live-qualification claim in capabilities.
- **Verified zero** means zero actual model requests and zero model usage in that run. An unverified count is reported `unknown`, never zero.
- The guard also records **reads of present provider-credential variables** (names only, never values); placeholder-mode processes must read none.
- **What the guard covers:** every Python process that loads it — launched API and worker, every multiprocessing scientific child that inherits the environment, the pytest session for `tests/integration`, the evaluation CLI process itself, engine-control workers and replay subprocesses — for DNS lookups and socket connects/sends via Python's socket module (audit hooks), Gemini client construction, and `os.environ` reads. **What it does not cover:** non-Python processes (Node, shell tools), native extensions that open sockets or call `getenv(3)` without Python's socket/environ layers, and processes started with `-I`/`-E` that do not load it explicitly. The launcher's allowlisted environment (no credential variables, `NO_PROXY`, tracing off) is the primary control; the guard is the instrumentation that turns an attempt into a recorded P0.

## Two budget implementations, one future authority

`evaluation/drbean_eval/budget.py` (harness JSONL, reconciles to actual usage) and the backend's `bean_api/ledger.py` (persistent, reconciles conservatively by `max(reserved, actual)`) are different implementations. They are **not** one enforced budget and neither is attached to a live provider now. Historical stores stay intact. Synthetic budget tests use temporary stores and are not provider charges. Before any future live activation, Owners 2, 3 and 5 agree one authoritative dispatch ledger; the harness then *observes* its actual attempt ids and totals and never reserves a second budget or refunds on untrusted usage. Rules already enforced by the harness ledger: no negative/boolean/malformed usage; every network attempt is a request; untrusted or mismatched usage keeps the maximum reserved as unknown; reconciliation errors are recorded events.

## Frozen inputs, ancestry and holdouts

- 12 cases × 2 variants = 24 fixture entries and 289 assertions, frozen before any output. Manifest v2 adds the lane rules, the three science packets and seven `offline_real_science` entries; v1 is archived byte-identical in `evaluation/manifests/manifest-v1.json` and verified by digest, so the 34 pre-merge attempts stay interpretable. A changed frozen file needs `cli.py freeze` (new version, archived ancestor).
- The hero packet and the C01–C12 source corpus are different packets with separate identities; expected answers are never substituted across them.
- **Holdout exposure (transparent):** `h01` and `h04` were authored by the same harness author as the development sheets, and the merged-harness review read the renderer that contains their definitions. No holdout model evaluation has occurred. They are therefore *exposed to the harness author*, not unseen. A future authorized live grading must use a grader without access to `sources/build/sheets.mjs` or a freshly authored variant labelled `holdout-v2`; `h01`/`h04` keep their historical status and files. If a holdout failure ever informs a fix, mark that case `used_for_development` and prepare a new variant.
- Expected transcriptions are derived from the generator specification and still need a human visual check (each file says so). A generator's own answer is not independent review.

## Grading of controlled AI behaviour

Assertions are data with an id, an axis and a reason; axes are reported separately (outcome, decision, enforcement, authority, privacy). A blocked invalid action shows as a decision failure with enforcement intact. For the current offline lane, `tests/integration/test_ai_boundaries.py` grades the **application's handling** of controlled placeholder proposals and model decisions — review state, approvals, jobs, persisted validation records, operation states — not extraction accuracy. String checks on prose are regressions, not a semantic verifier. The actual deepagents graph is driven by an independent scripted model with one declared objective and contrasting evidence; this verifies orchestration under controlled decisions, not that a real model adapts.

## Manual versus placeholder-assisted ablation (protocol; current arm is NOT Gemini)

Purpose: compare review/workflow steps and task usability with **identical scientific computation** in both arms.

- **Arms.** *Manual*: the person enters the five reviewed rows and constraints by hand. *Assisted (offline placeholder)*: the same person reviews a controlled placeholder transcription proposal of `fixtures/intake/clean.png` (labelled on screen as a controlled example, not Gemini) and corrects/accepts it. Both arms then use the same approved manual plan, real baseline, separate design approval and native replay.
- **Order.** Counterbalance (half the sessions start with each arm) and record the order; a single participant's second arm benefits from learning.
- **Record per task (raw, with denominators):** participant id (pseudonymous), consent, arm, order, start/end wall time, number of review actions, corrections (with field paths), unresolved clarifications, mistaken acceptances, abandoned steps, failures and their reasons, free-text usability notes.
- **Report:** raw counts and times per participant and per arm, failures and denominators. No p95, win probability or percentage productivity claim from a few tasks. A small convenience sample is not a population result.
- **What it can show:** whether the review workflow is usable and where people make corrections. **What it cannot show:** AI extraction accuracy, reasoning quality or real-model latency. The live comparison (assisted arm with real Gemini) stays a documented, **unrun** protocol until a new explicit user instruction authorizes it.

Template rows for the human task live with Owner 4's consultation documents (`docs/human-task/`); this protocol defines the measures.

## Findings, fixes and retests

Severity: **P0** — any external-model attempt, false checked success, wrong binding, unauthorized/duplicate computation, lost provenance or hypothetical labelling, unavailable real scientific hero path, missing replay bytes, credential exposure, orphan computation after cancellation. **P1** — simulated provider failure destroys the workflow, incorrect source-review handling, misleading status, controlled orchestration failing its declared behaviour, clean-machine recovery failing. **P2** — polish and coverage outside the minimum loop.

Every finding in `evaluation/findings.json` carries the exact commit, minimal input, command, expected predicate, observed output and a failing test or attempt id. Production fixes belong to the owner. After a fix lands: reproduce the original failure where practical, run the regression on the fixed commit and the nearest neighbouring checks, then set `retested`. A promised fix is not a closed finding. Harness defects found in this workstream's own code are fixed immediately and listed with the attempts they affected; affected attempts stay in the history.

## Diagnostics and previews (never acceptance)

- `--app-repo <checkout>` runs this harness against another checkout (for example a teammate branch) and records evidence class `preview`.
- `--diagnostic relax_nproc` lifts only the per-user `RLIMIT_NPROC` cap inside scientific children so downstream behaviour can be observed on the Mac while F-MAC-NPROC is open.
- `--diagnostic science_barrier` holds each scientific child inside the adapter (after `setsid` and limits) until the harness releases a barrier file, making "cancel while running" and "kill the worker while running" deterministic.
- All three require a separate `--results` directory, are logged by the guard, and never count toward release gates. A diagnostic relaxes one named guard to isolate a question; it is never a workaround for a product defect.

## Release gates

`python3.11 evaluation/cli.py gate --require release` reads recorded evidence at the tested commit and exits nonzero unless all of these pass on a clean tree: harness integrity (manifest + history), `real_science_http` (RS-HERO-FULL), essential negative controls through HTTP (concurrency, design authority, cancel/restart, changed input, follow-up), zero external model dispatch (RS-ZERO-DISPATCH and every lane attempt verified), native engine controls, supported-machine subprocesses (real image decoder and scientific worker on this host), and no open P0. `live_gemini_qualification` is always `not_run` and **not required**. `cli.py inventory` reports the same statuses and exits 0.

## Future live activation checklist (documentation only — do NOT execute now)

1. A new explicit user instruction authorizing live testing, with a named person and spending allowance.
2. One shared, accounted allocation in the single authoritative dispatch ledger agreed by Owners 2, 3 and 5.
3. Owner 3's deliberate operator path to switch the provider mode (no key-presence activation).
4. Independent grading of predeclared cases by a grader without access to the holdout definitions.
Until then live lanes stay `NOT_RUN`, `budget open` refuses, and placeholder-assisted runs are never described as Gemini-powered evidence.

## Privacy

Only synthetic sources and synthetic workflow data are used. Traces pass through the sanitizer; raw prompts, raw replies and hidden reasoning are dropped; bearer tokens are generated in memory per stack and never written to results. Immutable scientific records are never passed through a redactor: they are scanned, and a hit is a release failure.

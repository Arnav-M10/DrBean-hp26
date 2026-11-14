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

## Four evidence lanes for the paper, Gemini and Deep Agents sprint (`cli.py lanes`)

These four lanes sit alongside the manifest lanes above. None may stand in for another. Every report is appended, hash-chained, to `evaluation/results/lanes/reports.jsonl`, and its artifacts (JUnit XML, guard summary) sit in a directory of their own.

| Lane | Model | Science | Command | Establishes | Does not establish |
|---|---|---|---|---|---|
| `controlled_callbacks` | controlled doubles authored by the tests | controlled callbacks, in-process application | `cli.py lanes run --lane controlled_callbacks` (pytest `-m "not real_stack and not real_science"`) | authority, review, accounting and error handling | Gemini quality, live adaptivity, real computation |
| `controlled_science` | controlled or none; zero dispatch verified | actual Counterdex through the launched API and worker | `cli.py lanes run --lane controlled_science` (pytest `-m "real_stack or real_science"`) | orchestration and real scientific integration over HTTP | anything about live Gemini |
| `live_gemini` | live Gemini | actual tools and engine | **no command**; reported `not_run` | real extraction and decisions on a predeclared subset, inside one user-enabled budget | general accuracy |
| `historical_replay` | none | fresh `replay-native` of retained packets against their separately recorded anchors | `cli.py lanes run --lane historical_replay` | retained bytes still bind and replay under this checker | discovery, fresh inference, or that the application produced the packet now |

### What every report records

- **Source identity and versions:**
  - the commit and the dirty flag (changed paths included);
  - the source identity, which is the git tree digests of the application (`apps`, `packages`, `shared`, `scripts`, `pyproject.toml`, `uv.lock`), the harness (`evaluation`, `tests/integration`, minus evidence-only paths) and `fixtures`, plus the Counterdex source digest;
  - every backend `*VERSION` constant (prompt, policy, contract and projection versions), the contracts tree digest, dependency pins and installed package versions;
  - the repository engine identity, and the installed engine compared with it file by file;
  - fixture digests and the platform.
- **Requests and usage:**
  - External model requests count as a verified zero only when the egress guard was installed in every process, including each launched stack, whose guard log is kept, and recorded no blocked attempt.
  - Deliberate guard self-tests announce their probes and are listed separately.
  - Otherwise the count is `unknown`, or `attempted_and_blocked`.
  - Provider tokens are never written as zero. They are `not_applicable` when no request was dispatched.
  - Controlled double calls are `not_measured`.
- **Run record:**
  - the command with its exit status, timestamps and duration;
  - the preconditions: the installed engine equals the repository source, and the source identity was unchanged during the run;
  - per-test outcomes (`passed`, `failed`, `xfailed`, `not_available`, `harness_pending`).

### The `evidence_lanes` gate

This gate is required. Each required lane is decided by its newest report whose four identity digests equal the tested checkout's.
- Reports from another identity never count, even if they are newer.
- A dirty or preview newest report blocks the lane.
- A failed newest report fails it, and a later clean pass supersedes it.
- A broken hash chain or a changed artifact fails the gate.
- `live_gemini` is listed as `not_run` and is not required.

`NOT_AVAILABLE` means a capability is not advertised by this candidate. `HARNESS_PENDING` means the capability is advertised but its attack has not been written yet. Both are counted separately from passes and product failures.

## Coordinator sprint predicates (DB-COORDINATOR-3OWNER-1)

C froze `evaluation/coordinator/predicates.v1.json` (54 predicates, 43 release-blocking) against main `299a356`
before any candidate run; `FROZEN.json` holds the canonical SHA-256 and a self-test fails on any edit (a
correction is a new version). Each candidate gets an observation file under `evaluation/results/coordinator/`
with one status per predicate: `passed` (the whole predicate exercised on that candidate), `failed` (a finding is
filed), `not_available` (the observed feature is absent; exercisable parts are listed separately), `not_run` (with
the exact reason), `historical_only` or `author_check` (a Claude-authored component awaiting A/B cross-review).
A missing producer is never a pass. Adaptivity is graded as acceptable sets of permitted next actions per
tool-return condition. The four lanes and their permitted conclusions are unchanged.

A corrected observation of the same candidate is a new revision file (`baseline-<candidate>-r<n>.json`) that
names the file it supersedes and lists each correction; the earlier file is kept. The compiled-graph probe
(`tests/integration/test_research_graph_inventory.py`) derives its forbidden tools and middleware from a default
deep agent of the pinned SDK and compares the factory's actual `create_agent` input, compiled tool node and
per-turn bound tools with the declared allowlist.

## Paper corpus, scoring and attack matrix

- **Corpus (`evaluation/corpus/`).**
  - At least six development documents (Owner 4 renders them from Owner 1's data; awaited).
  - Four independently authored synthetic held-aside variants (H1–H4), sealed by digest in `holdouts.sealed.json`. The files themselves are git-ignored until the freeze.
  - Gold comes from independent Apple PDFKit renderings (`tools/render_pages.swift`). Every native-text quote must be found on its cited page.
  - The live subset is predeclared and `not_run`.
- **Scoring (`drbean_eval/paper_scoring.py`).** Each measure is a numerator and denominator with its failures listed, compared exactly with `Fraction`:
  - reading precision and coverage, for what was offered and for what was accepted after review;
  - page locators;
  - citation source occurrence;
  - unsupported numbers;
  - ambiguity flagging versus silent resolution;
  - trap violations (interval, SD, pooled mean, injected value, authority);
  - human corrections;
  - eligibility.
- **Attacks (`evaluation/attack_matrix.json`).**
  - Ten categories, each with the tests that already observe it on the current candidate and the tests waiting for paper, metered-model or resume capabilities.
  - Hostile PDF assets (`drbean_eval/hostile_pdfs.py`, 19 assets and 10 hostile filenames) are generated at test time.
  - Library-level controlled attacks on the metered gateway and the paper-proposal validator run wherever those modules exist. Today that is the PR #35 preview.

## Zero external model dispatch: how it is proved

- Every launched process loads `evaluation/drbean_eval/guard/sitecustomize.py`: an audit hook refuses non-loopback DNS and connections, and a spy refuses construction of `google.genai.Client` (which LangChain's Gemini model also builds). SDK imports, types and schemas stay allowed. Every refusal is logged; an attempt is a **P0 finding even though nothing left the machine**.
- The launcher builds environments from an allowlist. Provider credential variables are never inherited; tests may pass only `DRBEAN-DUMMY-...` values to prove configuration alone cannot dispatch. No real key is read, copied or tested.
- Through Owner 4's launcher (`--subject http-owner4-launcher`) the harness cannot allowlist the product environment, so it checks Owner 4's own removal instead: dummy `GEMINI_API_KEY`, `GOOGLE_API_KEY` and `LANGSMITH_API_KEY` are placed in the launcher's environment and the guard in the API and worker must report none of them. Guard events from the launcher process and its probes are reported separately and never count as product evidence.
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

### Admission of evidence (what may satisfy a gate)

- **Lane entries:** the newest attempt per entry at the tested commit, or at an ancestor whose later changes touch only evidence and documentation paths (`evidence_commits`), must be `executed_acceptance` of this checkout on a clean tree. Previews and diagnostics never count.
- **Native engine controls:** each required control is decided by its newest relevant run. That run must:
  - be clean (`worktree_dirty` explicitly false);
  - be executed acceptance of this checkout, not an `--app-repo` preview;
  - have run on CPython 3.11.x;
  - have imported the repository's Counterdex, with a source digest equal to the tested code's (recorded as `engine`).

  An unqualified newest run blocks that control, and older passing evidence never overrides it. A clean newer retest does supersede an older failure. Only the boolean `passed: true` counts. (Finding H-GATE-CONTROLS-DIRTY: the dirty flag used to be copied but not enforced.)
- **Engine identity in the lane:** RS-HERO-FULL requires the application's own capability source manifest to equal the repository engine source, file by file (`engine_runtime_matches_repository_source`). A stale installed `.venv-engine` copy with the same version string therefore cannot be qualified. Rerun `scripts/dev/launcher.py setup` after any engine change.
- **Scientific acceptance is not product release.** A passing scientific gate qualifies the application code at the tested commit on this platform. It does not establish Owner 4's offline product release (G4, the complete browser workflow) or any live-model qualification.

### Scientific coverage added in this round

- **Separation:** positive separation is confirmed by the decimal oracle. A separately approved wide-allowance design must give the tier the oracle predicts (no separation), select nothing, and replay fresh.
- **Unresolved follow-up:** a reading built from the engine's own exact enclosure (the band is its middle half) must stay `inconclusive`/`insufficient_enclosure`, with the row listed as unresolved. The 80-digit value must lie inside the enclosure, compared exactly (`F-ENGINE-ENCLOSURE` otherwise). Rounding to the default 28-digit decimal context would invalidate this comparison.
- **Source review:** source → controlled proposal → human correction and review → materialization → separately approved real science → fresh replay (`tests/integration/test_source_review_science.py`). Where the application does not offer controlled source review, the test is recorded as an explicit xfail naming the prerequisite.
- **Explanations:**
  - A "checked design" statement needs a cited record with tier `checked_pair_separation`, verification valid, replay passed and binding matching. A fully supported statement must be kept.
  - Correct limiting statements grounded in the cited record must also be kept.
  - Gap markers depend on the guard's declared `COMMENTARY_POLICY_VERSION`, not on merge order.

## Future live activation checklist (documentation only — do NOT execute now)

Live Gemini qualification is one coordinated run, and it starts only after the **user** enables both the product's explicit provider consent and a bounded live budget. A saved key alone authorizes nothing. Until then, `live_gemini` is `not_run` in every lane report and gate.

1. **Preconditions, verified before any request:**
   - the exact combined commit has passed every offline lane and `gate --require release`;
   - Owner 2's atomic research-session accounting is advertised (`session_accounting_ready`);
   - the configured model is the one the user named. The configuration is checked, never a key, and nothing is switched automatically to another or billed model;
   - the live opt-in (Owner 4's `var/gemini.local.json`, mode `live`) was created by the user, not by any agent.
2. **Budget:** one user-enabled allocation in the single authoritative ledger. The product ceilings are 12 model requests per action and 24 per session, plus 16/32 auxiliary operations with cleanup reserved. No agent or specialist gets a separate allowance.
3. **Predeclared subset** (`evaluation/corpus/manifest.json`):
   - **L1:** the development native-text supported paper, as one complete ordinary-user loop in one session.
   - **L2:** the development scan, only with explicit extra budget.
   - **L3:** held-aside H3, only after the freeze and only with explicit extra budget; afterwards it is regression data.
4. **What is recorded per case:**
   - the run, session and attempt ids from the application ledger;
   - the actual request count and usage, with unknown kept unknown;
   - latency;
   - `paper_scoring.py` measures against gold written from renderings;
   - human corrections;
   - Deep Agents actions taken against the returned evidence.
   The report names the actual denominator, and every case not run is listed as `not_run`.
5. **Stop rules:** any provider error, model mismatch, budget exhaustion or unexpected attempt stops the run. Exhausted access leaves live qualification pending and is never retried on another model. Credentials are never logged, and no key is inspected by the evaluator.
6. **Historical use:** a later replay of a live run is labelled `historical_replay`, with the original model and usage metadata. It is never fresh Gemini inference.

## Privacy

Only synthetic sources and synthetic workflow data are used. Traces pass through the sanitizer; raw prompts, raw replies and hidden reasoning are dropped; bearer tokens are generated in memory per stack and never written to results. Immutable scientific records are never passed through a redactor: they are scanned, and a hit is a release failure.

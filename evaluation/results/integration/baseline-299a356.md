# C baseline: main 299a356 against the frozen coordinator predicates

Assignment DB-COORDINATOR-3OWNER-1, role C (Claude, independent validation). This is Gate 0's exact baseline,
not a release qualification of the coordinator product, which does not exist yet.

## Identity

| Item | Value |
|---|---|
| Baseline | main `299a356f677a96fda44c5b280a20317ac7816c4f` (merge of PR #38; includes PR #39 private sessions) |
| Observed on | C branch `claude/adversarial-validation` at `bb503a7`, clean; `apps`, `packages`, `shared`, `scripts`, `fixtures`, `pyproject.toml` and `uv.lock` trees are byte-identical to main |
| Host | macOS 26.7 (Darwin 25.6.0) arm64 |
| Runtimes | backend CPython 3.13.18 (`.venv`, `uv sync --locked`); engine CPython 3.11.17 with Counterdex 0.3.0, imported from the repository source (lane precondition) |
| Frameworks | deepagents 0.7.38, langchain 1.5.0, langgraph 1.2.21, langchain-google-genai 4.5.0, google-genai 3.3.0 |
| Predicates | `evaluation/coordinator/predicates.v1.json`, 54 predicates, 43 blocking; commitment `46a8ae08...` in `FROZEN.json`, frozen 2026-11-14T13:12:22Z before any candidate run |
| Observed contract | DB-RESEARCH-1 at PR #41 `d224846` (B gate B1 proposal; no routes, checkpointer or worker integration) |
| Live Gemini | not run; no key read, no provider called, $0 |

## What exists on 299a356

- **Routes:** 45. No research-session routes; no general-research routes; `shared-session` bootstrap, rotate and
  logout exist.
- **Capabilities:**
  - `deepagents`: implemented, `execution_mode controlled_only`, `unavailable_reason live_coordinator_not_integrated`;
  - `gemini`: disabled (`provider_not_configured`);
  - no `general_research` block;
  - source intake: PNG/JPEG only;
  - science: Counterdex 0.3.0 available.
- **Coordinator:** the actual `create_deep_agent` graph, controlled models only. The compiled parent offers
  `execute_approved_scenario`, `read_scoped_evidence`, `record_allowed_skip` and `return_grounded_explanation`
  (no `write_todos`). It has no checkpointer or store and no subagents, summarization is excluded, and it uses an
  ephemeral `StateBackend`. Evidence: the lane artifact `deepagents-inventory.json`.
- **Private sessions:** cookie lane behind a trusted gateway. Rotation keeps actor, workspace and expiry; expiry
  and revocation refuse access; issuance capacity is 4096 records, including revoked ones.
- **General files:** the merged UI exists but its producer is not registered (PR #40 is a candidate that B now
  owns; Claude's checks of it are author checks).

## Evidence at bb503a7

| Run | Result |
|---|---|
| Acceptance lane `offline_real_science` (launched API + worker, actual Counterdex, egress guard) | 7/7: RS-HERO-FULL, CHANGED-INPUT, RETRY-CONCURRENT, DESIGN-AUTHORITY, FOLLOWUP, CANCEL-RESTART, ZERO-DISPATCH |
| Engine controls (CPython 3.11, repository source) | 22/22 |
| `controlled_callbacks` `lane_9ade7a285b6e407f` | passed: 88 passed, 5 xfail (4 F-NARRATION-OVERSUPPRESSION, 1 F-SESSION-CAPACITY-EXHAUSTION), 43 NOT_AVAILABLE |
| `controlled_science` `lane_8619f1fe84114739` | passed: 18 passed, 11 NOT_AVAILABLE, 2 not_run (opt-in heavy memory attack; launcher start blocked because ports 8000/4173 are held by a separately running instance from `DrBean-test`, left untouched) |
| `historical_replay` `lane_583ed42dc383477e` | passed: 168 packets replayed against recorded anchors, 1 archived 0.2.0 packet version-incompatible |
| `live_gemini` | not_run |
| `gate --require release` | exit 0, all eight required gates |
| Backend suite (`pytest tests --ignore=tests/integration`, engine runtime on PATH) | 760 passed (includes `test_coordinator.py`, `test_controlled_native_workflow.py`, restart, offline and browser-session tests) |
| Engine suite (`unittest`, CPython 3.11) | 292 OK, 2 skipped |
| Web units (`node --test` in `apps/web`) | 71/71 |
| B's browser checks (Playwright 1.63.0, Chromium 1243) | manual editor 18/18; general workspace 23 checks passed in its controlled HTTP/UI lane (authored analysis over real public CSV bytes; it records actual session isolation as not run in that lane); shared-session HTTPS 12/12 with 0 provider and 0 outbound attempts; `check-backend.mjs` passed (browser review, approval and dispatch, real discovery, positive and no-separation designs, native and anchor downloads with installed-engine replay, 0 provider attempts) |
| Harness self-tests | 180/180 (CPython 3.11) |
| Ruff / schema export drift / secret scan | clean / unchanged / 0 findings |

The component and browser runs started while the preceding lane batch's evidence files (`evaluation/results`)
were still uncommitted; every application path was clean.

## Predicate status at baseline (machine-readable: `evaluation/results/coordinator/baseline-299a356.json`)

12 passed, 7 not_run, 35 not_available, 0 failed. `passed` means the whole predicate was exercised on this
candidate; a predicate that names an absent feature is `not_available` even when its exercisable parts pass
(those parts are listed in the JSON).

| Group | Passed | Not run (missing parts) | Not available |
|---|---|---|---|
| Scientific | SCI-01, 03, 04, 09 | SCI-02 (three distinct non-positive records), 05 (numerical guidance, partial grid rows), 06 (legitimate both-compatible, contradiction flag, inconclusive), 07 (structured follow-up fields), 08 (downloads after a post-science model failure) | SCI-10 (no general producer) |
| Coordinator journey and graph | — | — | LOOP-01..11 (no research sessions; graph has no planning or checkpointer; no specialists) |
| Authority and privacy | AUTH-02 | AUTH-07 (launched web child environment: ports held by another instance) | AUTH-01, 03, 04, 05 (exercisable parts pass), AUTH-06 |
| Durability | CRASH-08 (main's provider boundary; re-qualify on A's adapter) | — | CRASH-01..07, 09, 10 (job-level analogues pass) |
| Metering | METER-02, 04, 06 | METER-07 (no live allocation) | METER-01, 03 (exercisable parts pass), METER-05 |
| General files | FILE-07 (sealed holdouts intact) | — | FILE-01..06 (no producer on main; PR #40 author checks only) |
| Release | REL-01, REL-02 | — | — |

## Findings by owner

| Id | Sev | Owner | State | Note |
|---|---|---|---|---|
| F-SESSION-CAPACITY-EXHAUSTION | P2 | B | open (new) | anonymous bootstraps permanently consume the 4096 issuance records (revoked/expired count); public link lockout; strict-xfail reproducer |
| F-UPLOAD-LIMIT-MESSAGE | P3 | B | open (new) | the PR #40 producer (author check) refuses both supplied papers with a generic 413 that names no limit; honest, nothing analysed |
| F-NARRATION-OVERSUPPRESSION | P2 | A | open | 4 strict xfails on main |
| F-TEST-VAR-LEAK, F-SIBLING-FORKS | P2 | B | open | unchanged |
| F-PAPER-CITATION-SUBSTRING (P1), QUOTE-NORMALIZATION, HARD-BOUND-CONTEXT, EXPONENT-FLATTENING | P1/P2 | A (PR #35) | open on PR #35 `c952c35` (unchanged since observed); not on main | B plans to reuse PR #40's implementation instead |
| F-PAPER-RENDER-MEMORY | P1 | B (PR #36) | open on PR #36 `081bbdc` (unchanged); not on main | |
| F-PAPER-IDENTITY-CONTRACTS | P2 | B with A | open | resolved only when one producer and contract are registered |
| H-LAUNCHER-OPTIN-FORMAT | P3 | C (harness) | fixed and retested | harness assumed PR #36's opt-in format |

No P0 is open. Nothing on main 299a356 fails a blocking predicate that is exercisable today.

## Release judgment for this baseline

**Not releasable as the DB-COORDINATOR-3OWNER-1 product.** Gates 1-6 are unmet: there is no durable research
session, checkpointer, planning-enabled coordinator, research decision path, crash-recoverable action journal or
registered general-file producer, and live coordination is unavailable. The existing manual scientific loop
(reviewed inputs → canonical approval → actual Counterdex → separate design approval → follow-up → native bytes
and fresh replay) is qualified on this baseline in the controlled-science and replay lanes, and private browser
sessions isolate the exercisable resources.

## Next C steps

1. Probe B's PR #41 and A's graph branch as soon as routes and the factory land (the DB-RESEARCH-1 probes run
   unchanged) and extend them to the crash matrix with owned fault injection.
2. Author the missing scientific cases: SCI-02, 05, 06, 07 and 08.
3. Retest F-SESSION-CAPACITY-EXHAUSTION and the paper findings when fixes arrive; evaluate the producer B registers.
4. Gate 6: qualify B's frozen integrated commit; then rehearse the evidence-bound demo.

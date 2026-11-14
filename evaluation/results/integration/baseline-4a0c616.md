# C observation: main 4a0c616 against the frozen coordinator predicates

Assignment DB-COORDINATOR-3OWNER-1, role C. Main moved from `299a356` to `4a0c616`, the user-authorized merge of A's
PR #42, which is tree-identical to A's tested head `051b4d6`. This record covers only what changed; the
`299a356` record (`baseline-299a356.md`, revisions 1-3) holds everything that carries over unchanged.

## Identity

| Item | Value |
|---|---|
| Candidate | main `4a0c616a53eb4f4b3fb8b5c920ed553cea544904` |
| Observed on | C branch merge `8a21323`, clean. Application, packages, shared, scripts, fixtures and locks are byte-identical to main. |
| Runtimes | unchanged (`uv.lock` unchanged): backend CPython 3.13.18, engine CPython 3.11.17 with Counterdex 0.3.0 (A changed only an engine test file) |
| Live Gemini | not run; no key read, no provider called, $0 |

## What changed on main

- A's restricted research coordinator factory (`research_coordinator.py`, `research_integration.py`).
- The metered Gemini chat model and gateway.
- Narration policy `evidence-bound-statements.v3` and prompt `research-prompt.v2`.

No route or worker invokes the factory: the research-session routes are still not registered on main.

## Evidence at 8a21323

| Run | Result |
|---|---|
| Acceptance (`offline_real_science`) | 7/7 (RS-FOLLOWUP 213/213 checks) |
| Engine controls | 27/27, all required |
| `controlled_callbacks` `lane_91d63d5f861a4ae7` | 110 passed, 1 xfail (F-SESSION-CAPACITY-EXHAUSTION), 43 NOT_AVAILABLE |
| `controlled_science` `lane_9841e96bcd0a4f15` | 18 passed, 11 NOT_AVAILABLE, 2 not_run |
| `historical_replay` `lane_37c370789c7d44aa` | 194 replayed, 1 archived 0.2.0 packet incompatible |
| `gate --require release` | exit 0 (`evaluation/results/gates-latest.json`) |

## Predicates (`evaluation/results/coordinator/baseline-4a0c616.json`)

14 passed, 5 not_run, 35 not_available, 0 failed. The statuses are unchanged from `299a356` revision 3.

- **LOOP-09 and LOOP-10: more exercisable parts pass, but they stay not_available.**
  - What passes, using the factory on this candidate:
    - the compiled inventory equals the declared six-tool allowlist;
    - planning comes from the SDK's `TodoListMiddleware`;
    - the forbidden SDK tools and middleware are absent;
    - there is one model call per admitted turn;
    - the supplied checkpointer is passed through;
    - there are no specialists.
  - Why it is still not available: no route or worker uses the factory, so there is no product coordinator and no
    disk-backed checkpointer to observe.

## Findings

- **F-NARRATION-OVERSUPPRESSION (A): closed by retest on main.** The four correct limiting statements are now kept,
  and the 14 converse cases are withheld.
- Still open:
  - F-SESSION-CAPACITY-EXHAUSTION (P2, B);
  - F-CI-BROWSER-CHECK-INTERMITTENT (P3, B);
  - F-UPLOAD-LIMIT-MESSAGE (P3, B);
  - the PR #35/#36 paper findings (on those unmerged branches).
- No P0.

**New boundary to qualify.** A's metered gateway is on main but cannot be reached from any registered route. C's
existing gateway attacks target PR #35's interface and report NOT_AVAILABLE. They must be re-aimed at A's gateway
and B's research ledger before the live path or Gate 6.

## B's work in progress (preview, not this candidate)

PR #41 `4d33f0b`, see `evaluation/results/previews/pr41-4d33f0b/README.md`:
- The DB-RESEARCH-1 route probes pass 7/7 against the routes registered in `create_app()`.
- `advance` returns 503 `controlled_policy_unavailable` while A's controlled model factory module is absent, and
  creates no action or job.

## Release judgment

Still **not releasable as the coordinator product**: Gates 1-6 are unmet on main. The manual scientific loop stays
qualified on this candidate.

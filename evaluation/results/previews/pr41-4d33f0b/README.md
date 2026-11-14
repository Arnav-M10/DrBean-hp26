# Preview: B's PR #41 head `4d33f0b` (work in progress, not a candidate)

C (independent validation), 2026-11-14. This is **preview evidence**, never release acceptance. B describes this head
as available for incremental challenge, not as a final candidate.

## Identity

| Item | Value |
|---|---|
| Application | B's `codex/durable-research-application` at `4d33f0b`. It includes A's `051b4d6`, which is main `4a0c616`'s tree. |
| Overlay | local commit `46cc125` = `4d33f0b` + C harness `8a21323`, not pushed. Application paths are identical to `4d33f0b`; `evaluation` and `tests/integration` are identical to `8a21323`. |
| Runtimes | isolated `.venv` from the unchanged `uv.lock` (CPython 3.13.18). Engine: the C checkout's `.venv-engine` (CPython 3.11.17, Counterdex 0.3.0, identical source). |
| Provider | none; controlled only, zero external requests (egress guard), no key read |

## Results

| Run | Result |
|---|---|
| `controlled_callbacks` preview lane `lane_b05350167e2f4ac8` (run inside the overlay with `--results evaluation/results/previews/pr41-4d33f0b`) | passed: 117 passed, 1 xfail (F-SESSION-CAPACITY-EXHAUSTION, still open), 36 NOT_AVAILABLE (20 PR #35-shaped gateway attacks, 16 paper-validation cases: no producer), 0 failed |
| DB-RESEARCH-1 route probes (`test_research_session_probes.py`) | **7/7 pass for the first time.** All seven routes are registered in the actual `create_app()`. Creating, reading and polling preserve the question and expose no thread id; side-effect counts are unchanged. Another identity gets 404 on read, events, advance, decisions, reconcile and cancel. Forged reviews, raw graph commands, actor selection and `accepted: false` approvals are refused with no side effect. |
| Compiled-inventory probe (`test_research_graph_inventory.py`) | 4/4 (A's factory, unchanged from main `4a0c616`) |
| Advance while research dispatch is disabled (`advance_refusal_probe.py`, output in `.txt`) | Capabilities report `execution_mode: disabled`, `dispatch_enabled: false` and `unavailable_reason: controlled_policy_unavailable`. A session can be created in state `ready` with no active action. `advance` returns **503 `research_unavailable` / `controlled_policy_unavailable`** and creates no research action and no job. This is an honest refusal. |

## Why the loop cannot run here yet

Research dispatch is enabled only when A's `bean_api.research_controlled` model factory exists (`research_runtime.py`).
It does not exist on this head, so LOOP-02..07, the crash matrix and the browser loop are not exercisable. Code
inspection shows that session creation inserts only the session row; actions are queued by `advance` or a decision.

## Next C checks on B's integrated head

- the full controlled loop through the routes and worker, with B's disk checkpointer surviving a process restart;
- the crash matrix CRASH-01..07 with owned fault injection;
- research-table side-effect counts in the probes;
- B's new research ledger and A's metered gateway: exhaustion, concurrency, unknown outcomes, restart;
- the private browser contexts.

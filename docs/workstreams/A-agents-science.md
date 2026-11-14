# A — agents and scientific integration

Assignment: DB-COORDINATOR-3OWNER-1. Branch
`codex/three-owner-agent-science`; isolated worktree from main
`299a356f677a96fda44c5b280a20317ac7816c4f`.
Earlier [science](01-science.md) and [AI](03-ai.md) logs remain historical evidence.
This entry is the current combined A handoff; B integrates the application and C
independently evaluates it.

## Implemented

- Actual Deep Agents parent factory, six restricted tools including native
  `write_todos`, bounded checkpoint planning/context, canonical review interrupt,
  exact review identity checks at replay/dispatch and evidence-dependent decisions.
- Trusted start/resume/explicit-next-action/read-only snapshot methods. An
  unaccepted model answer cannot complete an investigation. Plan completion is
  labelled proposed; canonical children and evidence remain authority.
- Async Gemini model adapter and a single physical request gateway reusing
  existing configuration/ledger hooks. Context/tool-signature binding, schema
  validation, no automatic retry, preserved unknown outcomes and mode guards.
- Existing controlled graph refuses provider-capable adapter subclasses and
  wrappers. No provider configuration, credentials or production store changed.
- A real-engine component path reaches unapproved plan → interrupt → canonical
  approval → ordinary provider-free worker → evidence-dependent report → native
  download/fresh replay. The same question and changed reviewed claim are retained.
- A scientific truth table plus a legitimate both-compatible observation
  regression at a separately declared time/allowance. No engine expansion or
  mathematical implementation change was needed.

See [graph integration handoff](../integration/RESEARCH_GRAPH_HANDOFF.md) and
[scientific predicates/evidence](../integration/COORDINATOR_SCIENTIFIC_TRUTH_TABLE.md).

## Runtime and author checks

macOS arm64; backend CPython 3.13.18, Deep Agents 0.7.38, LangGraph 1.2.21;
scientific/replay CPython 3.11.17 and Counterdex 0.3.0. All 24 installed engine
source files matched this source tree, aggregate digest
`90b42ae505c9a7c25103331f447edc2e15026d291374f6beefd0ef89c23b7bf8`.
Tests used prepared runtimes in the sibling shared-integration worktree, explicit
engine/replay paths, temporary stores, sanitized environment and the existing
evaluation egress guard. No application provider request was made.

Initial combined A regression: **293 passed** in 30.86s across new graph/native/
gateway/model tests and existing coordinator/provider/conversation/ledger/restart
tests. This was before the final wrapper-guard and canonical-adapter handoff;
it is retained component evidence, not the final candidate qualification.
Two warnings were escape-sequence warnings in installed Google SDK docstrings.

Broader regression on the staged implementation: **864 passed in 102.57s**,
`pytest -q tests --ignore=tests/integration`, with the explicit matching
scientific/replay runtimes and the existing egress guard. This preceded the last
canonical-adapter/queued-child refinements. Guard observations: no provider
construction or network attempt. One credential-name lookup belongs to an
existing opt-in test's explicitly substituted dummy environment/client; the
parent environment was cleared and no real credentials were loaded.

Cross-review found and repaired an unaccepted model-stop path, a changed-review
race, provider-wrapper admission and queued-child checkpoint/interrupt ordering.
The latest graph/adversarial/canonical-adapter set passed **59 tests**; the
model/gateway set passed **77 tests**. These are concrete author findings and
regressions, not independent C results.

Science author checks: 292 engine tests ran (290 passed, two runtime-dependent
skips subsequently exercised successfully with their required runtimes), 114
backend/native checks, four existing controlled real-science checks and two new
native factory cases. The truth table retains exact commands and evidence lanes.
Ruff and secret scanning passed; no scientific public protocol/schema changed.

All subagent and root checks here are **A author checks**, not C's independent
acceptance. In-memory checkpoint reconstruction does not claim fresh-process
storage/lease/browser qualification. Live model adaptivity is `not_run`.

### Committed component qualification

Code commit: **`63357c0b9bb653be3edc6bcbe29e904cbb07d27b`**, clean at test start.
[PR #42](https://github.com/Arnav-M10/DrBean-hp26/pull/42) is draft for B's
application integration; A did not merge it or alter main.
The final combined component regression passed **340 tests in 28.78s**:

```sh
env -i PATH="$ENGINE_BIN:/opt/homebrew/bin:/usr/bin:/bin" LANG=C.UTF-8 \
  PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$PWD/evaluation/drbean_eval/guard" \
  DRBEAN_EGRESS_GUARD_LOG=/tmp/drbean-63357c0-guard.jsonl BEAN_AI_MODE=placeholder \
  BEAN_COUNTERDEX_PYTHON="$ENGINE_PYTHON" BEAN_COUNTERDEX_REPLAY_PYTHON="$ENGINE_PYTHON" \
  "$BACKEND_PYTHON" -m pytest -q -p no:cacheprovider \
  tests/test_research_coordinator.py tests/test_research_coordinator_adversarial.py \
  tests/test_research_integration.py tests/test_research_coordinator_native.py \
  tests/test_gemini_chat_model.py tests/test_gemini_chat_gateway.py \
  tests/test_coordinator.py tests/test_controlled_native_workflow.py \
  tests/test_provider.py tests/test_conversation.py tests/test_ledger.py \
  tests/test_ledger_accounting.py tests/test_restart_workflow.py
```

Here `BACKEND_PYTHON` was the sibling
`DrBean-hp26-shared-integration/.venv/bin/python`; `ENGINE_PYTHON` was its
`.venv-engine/bin/python`, and `ENGINE_BIN` its `.venv-engine/bin` directory.
No source or package install was modified by this check. Guard telemetry was
39 `guard_installed` events and no other events: zero provider constructions,
network attempts or credential lookups in this run. Ruff on `apps tests scripts`,
secret scan (zero findings), and `git diff --check` passed at the same source.

CI for that code commit:
[run 43599016318](https://github.com/Arnav-M10/DrBean-hp26/actions/runs/43599016318).
That run was superseded by the docs receipt push before all jobs completed.
All six jobs passed for `472659cc4a888bdf937b59444143493ac9d941ae` in
[run 43599151587](https://github.com/Arnav-M10/DrBean-hp26/actions/runs/43599151587):
backend/lint/schema, engine/native replay, evaluation self-checks, web units,
browser review/design/native replay and actual-stack restart/reopen. Those
browser checks exercise the existing application path, not new unregistered
coordinator routes. Any final combined B commit requires its own qualification.

## B/C handoff and next condition

B published `DB-RESEARCH-1` at `d224846` and the authority/checkpoint slice at
`0c69912aa021ca94e0d87e2ecb3b9a82b851566e` in
[PR #41](https://github.com/Arnav-M10/DrBean-hp26/pull/41).
A has requested concrete snapshot/review/child/report shapes, atomic frozen
review-digest validation, read authority and cumulative model/tool/physical
admission. The application adapter consumes that contract; missing producer
capabilities fail closed rather than simulating a live service.

The latter implements durable records/checkpointer, fenced leases and the
child-intent journal. Remaining B dependencies: actual graph/worker/routes/UI
registration, canonical observation receipt and separately approved recheck,
explicit reviewed-input and changed-design transitions, complete report
snapshots, precise session/action accounting and ordinary browser loop.
Default live allocation is
unchanged; a version marker is not permission or new capacity. Current main's
ledger cannot admit this live coordinator lane.

B's proposed eight logical model turns per session also needs an explicit
whole-loop policy decision: the minimal one-tool-per-turn baseline/design/
observation/report sequence needs roughly nine selections before optional reads
or plan revision. A raised this concrete bound on PR #41; it grants no live
capacity and does not change the four-turn action limit or the real global ledger.

A cross-reviewed actual B `0c69912` in an isolated archive and temporary store.
Using `hero-baseline.request.json` plus feasible times `8/1,6/1`, allowance `1/5`,
horizon `8/1` and checked construction/continuation permission, the ordinary
worker returned `certified_counterexample / valid / passed` and then
`checked_pair_separation`. A report first created after baseline was reused
after design with zero retained designs; a fresh canonical snapshot had one.
Changing the design allowance to `100/1` returned `research_effect_conflict`
under the fixed session design key. These concrete B-owned gaps were reported
on PR #41; no B code was duplicated. Its 13 authority/checkpoint controls passed
as A cross-checks. Its tiny-StateGraph checkpoint reconstruction is same-process
component evidence, not a fresh-process or browser result.

C's published gate-0 predicates were inspected at `8580d3e`, with sealed
holdouts left untouched. Its session-capacity finding was routed to B. The
exposed narration over-suppression cases produced a narrow A correction:
four exact limiting sentences require matching cited categorical statuses.
Uncited or split-record support, conflicts and appended overclaims remain
refused. Commentary policy is now `evidence-bound-statements.v3`; graph prompt
is `research-prompt.v2`. Both versions join graph/tool policy in checkpoint
compatibility, including new approval actions and advance. C must independently
retest its own strict expected-failure markers; A did not edit C's tests.

### Current boundary correction and combined component check

A's adapter now consumes B's actual immutable evidence/suggestion envelopes,
checks their original digest, identity/workspace/type/lineage and preserves all
scientific axes, candidate vectors and design options in the bounded projection.
Explicit unavailable preparation is a useful negative result with no executable
identity. Malformed availability values and invented proposal IDs are refused.
An observation request remains distinct from an approved executable follow-up.

Focused narration checks passed 139 cases after the last prompt correction.
The adapter passed 43 tests in A's checkout with one explicit B-module skip.
An isolated combination of B `0c69912` plus these A source files passed **141
graph/adversarial/adapter/authority tests**. That includes actual Deep Agents
review pause in one Python process, canonical approval and checkpoint restore in
another, preserving todos and queuing exactly one deterministic child with zero
physical model calls. This test does not execute that child or exercise product
startup/UI. The complete Counterdex computations above are separate checks.

Reproduction after assembling those two source sets uses:

```sh
python -m pytest -q tests/test_research_coordinator.py \
  tests/test_research_coordinator_adversarial.py tests/test_research_integration.py \
  tests/test_research_authority.py
```

The retained test selects the exact checkout in its child processes, refuses
provider/network construction and uses temporary stores. A-only checkout skips
that B-dependent test honestly; it does not substitute an in-memory producer.
The final clean-commit combined regression and CI receipt are recorded on
[PR #42](https://github.com/Arnav-M10/DrBean-hp26/pull/42). These remain A author
checks; B alone integrates and C qualifies the resulting application candidate.

C should challenge the resulting combined commit with independent holdouts,
same-input binding, review races, child/checkpoint crash recovery, valid and
inconclusive science, candidate-specific feedback and fresh native replay.
No whole-product, live-provider or release-ready claim follows from this branch.
Useful specialists and wider paper processing remain behind the working parent
and ordinary browser gates. B alone chooses the application merge sequence.

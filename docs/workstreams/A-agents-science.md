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

## B/C handoff and next condition

B published `DB-RESEARCH-1` at `d224846` in
[PR #41](https://github.com/Arnav-M10/DrBean-hp26/pull/41).
A has requested concrete snapshot/review/child/report shapes, atomic frozen
review-digest validation, read authority and cumulative model/tool/physical
admission. The application adapter consumes that contract; missing producer
capabilities fail closed rather than simulating a live service.

Remaining B dependencies: actual durable records/checkpointer, leases and
recovery journal, routes/worker registration, canonical decisions, precise
session/action accounting and ordinary browser loop. Default live allocation is
unchanged; a version marker is not permission or new capacity. Current main's
ledger cannot admit this live coordinator lane.

C should challenge the resulting combined commit with independent holdouts,
same-input binding, review races, child/checkpoint crash recovery, valid and
inconclusive science, candidate-specific feedback and fresh native replay.
No whole-product, live-provider or release-ready claim follows from this branch.
Useful specialists and wider paper processing remain behind the working parent
and ordinary browser gates. B alone chooses the application merge sequence.

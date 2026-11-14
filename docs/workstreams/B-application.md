# B — durable research application

Assignment DB-COORDINATOR-3OWNER-1. Branch `codex/durable-research-application`;
base main `299a356`. Backend Python 3.12.14, pinned Deep Agents 0.7.38,
LangGraph 1.2.21/checkpoint 4.3.1. Isolated worktree; old dirty prototypes preserved.

- Preserved: merged private sessions, general UI, exact manual scientific loop,
  deterministic children, native evidence/replay, cleanup and ledger history.
- Implemented B1/B2 authority slice: canonical `DB-RESEARCH-1`, types/ports in
  `apps/api/bean_api/research_contracts.py`, generated schemas/examples alongside
  the contract. B is sole application integrator and authoritative side-effect owner.
- A: actual graph/model/factory/state semantics on `codex/three-owner-agent-science`.
  C: independent evaluation; carried-over general producer authorship disclosed.
- Implemented: additive schema2; immutable plan/event records; one fenced lease;
  canonical approval + admitted resume in one transaction; journaled child intent
  and atomic canonical reservation/link; tenant-authorized bounded JSON checkpoints.
  No executable imports/pickle on decode. Unknown provider outcomes are retained.
- Tested in this slice: `pytest -q tests/test_research_authority.py
  tests/test_workflow.py`: **40 passed** (12 new authority/checkpoint controls,
  28 preserved workflow controls). Genuine LangGraph interrupt/reconstruction is
  component evidence; fresh-process/browser/real-science acceptance is still pending.
- A supplied PR42 at63357c0: actual graph + exact async application adapter.
  Next: match canonical response shapes, wire actual worker/factory, then complete
  the real baseline/design/new-reading/recheck/report/browser loop.
- Producer #40 now exists: inspect/reuse/register it and cross-review its carried
  parsing/citation/resource code; it is no longer a departed-owner dependency.
- Larger-paper profile and delegates follow the durable parent/real-child loop.
  No live request, credential probe, new allocation or public serving change.

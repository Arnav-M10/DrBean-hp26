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
- Tested: focused graph/application/ledger/native set **189 passed** under C's
  egress guard (`/tmp/bean-B-core.log`), before the last two input/revocation
  controls. Existing real baseline/design/follow-up workflow **19 passed**.
  New B authority loop **2 passed**, including 3 fresh native replays, report
  revision/immutability, changed design scope and genuine no separation.
  These are component/backend checks, not browser or release qualification.
- A supplied PR42 at63357c0: actual graph + exact async application adapter.
  Actual main routes and Worker now use that factory + B's disk saver/journal.
  New input adoption uses graph advance; scientific decisions use true resume.
  Separate observation review materializes exact inputs without approving recheck.
- Current dependency A: production zero-provider full-loop model factory
  `research_controlled.build_controlled_research_model` and trusted pending-tool
  recovery (requested on PR42). Default capability remains honestly unavailable
  while that factory is absent. B continues UI/producer integration independently.
- Metered live wiring uses A's single gateway and B's atomic session/action/global
  admission; default allocation0, explicit operator-only grant method (no browser
  allocation route), scope-bound consent, unknown outcomes stay reserved. Offline
  substituted-transport checks pass. Live qualification remains **not_run**.
- UI slice: question/input saving, maintained-plan display, exact scientific
  approvals, observation/clarification review, retained native/anchor/report
  downloads, private reopen and explicit same-key uncertain retries are wired.
  **78 web units passed**, including7 new research-controller checks. Actual
  parent-driven browser acceptance remains pending the controlled factory.
- A051b4d6 adapter/prompt corrections adopted; complete immutable evidence
  envelopes are returned for A's validated bounded projection. Latest focused
  integration/native/authority/commentary set: **129 passed**; after adapter
  envelope correction, native/authority/A-integration subset: **61 passed**.
- Producer #40 now exists: inspect/reuse/register it and cross-review its carried
  parsing/citation/resource code; it is no longer a departed-owner dependency.
- Larger-paper profile and delegates follow the durable parent/real-child loop.
  No live request, credential probe, new allocation or public serving change.

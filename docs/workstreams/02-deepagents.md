# Owner 2 durable research agent

Branch `backend/deepagents-durable`, current main base `cbfa5ef`.

- Pushed: early machine-readable interface agreement at
  `shared/contracts/RESEARCH_AGENT_HANDOFF.json`; coordinator ownership, shared
  model adapter boundary, paper/page identity, event envelope and unchanged lower
  four-turn/six-tool limits are published for the other owners.
- Local work in progress: additive SQLite session/action/lease/checkpoint
  migration, explicit zero-default allocations and consent, atomic shared
  generation/auxiliary accounting, coordinator checkpoint integration, review
  resumption and canonical scientific-job reuse. These code changes are NOT
  committed or pushed and are NOT an accepted implementation.
- Intermediate local checks: 29 session/ledger tests passed; 62 coordinator
  tests passed before the latest runner/interrupt edits. The latest combined
  local patch has not been validated. No live provider calls or key inspection.
- BLOCKED: execution environment became unavailable and exec-server recovery
  timed out. Cannot inspect/recover the local worktree, finish graph/crash tests,
  export schemas or commit the implementation until it is restored.
- Dependencies: Owner 3 shared metered chat-model/transport; Owner 4 bounded
  parser and combined browser assembly; Owner 1 applicability requirements;
  Claude exact combined acceptance. No competing provider/parser implementation.
- Next when workspace returns: inspect all uncommitted work, run interrupt/crash
  regressions, finish API/worker and paper integration, validate ordinary science,
  then commit and push owned implementation. Live allocation remains zero until
  explicit consent and a retained bounded allocation; live qualification not_run.

# Ownership and layout

Current assignment: **DB-COORDINATOR-3OWNER-1** (November 14, 2026). This three-owner mapping supersedes historical five-workstream routing. Historical evidence and commits retain their original author labels.

| Owner | Exclusive production responsibility |
|---|---|
| A — user's Codex | Counterdex science; actual Deep Agents graph/planning/decision policy; providers.py, conversation.py, AI prompts, model adapters/transports and focused tests. |
| B — teammate Codex | Sole application integrator; API/contracts/authority, SQLite/migrations/checkpoints, ledger, workers/process supervision, general-file parsing/storage/citations/routes; all web UI, launcher/operational CI, dependencies/locks/generated schemas. |
| C — Claude | Independent evaluator, heldouts, adversarial acceptance and exact-candidate qualification. No new production implementation to independently certify. |

Current logs: docs/workstreams/A-agents-science.md, docs/workstreams/B-application.md and C's retained docs/workstreams/05-validation.md. B maintains docs/integration/APPLICATION_ASSEMBLY.md.

The canonical public seam is shared/contracts/DB-RESEARCH-1/README.md and apps/api/bean_api/research_contracts.py. A supplies the graph factory and state/prompt/tool compatibility; B constructs private context, authorizes side effects, supplies the disk saver and registers the actual app/worker. Model dispatch reserves once through the same physical ledger; graph turn admission does not charge it twice.

Use isolated worktrees. Preserve dirty teammate work, current evidence/history and scientific routing. Agree one writer for shared-file changes. Do not merge obsolete PR14 or whole old stacks to collect overlapping fixes. No model request, credential probe or new public deployment is needed for development. Default live allocation is zero.

Claude's carried-over general-file producer PR40 transfers production maintenance to B. Its original tests are author checks; disclose authorship, obtain A/B cross-review and separate C evaluation of the assembled product.

Runtime layout (ignored): .venv/ backend, .venv-engine/ matching CPython 3.11 science/replay, var/ private store/sources/auth and var/run/ logs/PIDs. Integrate from current origin/main; old supplied SHAs are evidence anchors, never reset targets.

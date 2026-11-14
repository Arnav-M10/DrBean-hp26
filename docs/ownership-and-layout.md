# Ownership and layout

Five coding workstreams, disjoint files. These are workstreams, not five human entrants: the team roster and the four-person limit are unchanged. Supersedes the pre-merge four-owner table, which said Owner 04 owned all evaluation and that no backend existed.

| Workstream | Exclusive edit scope |
|---|---|
| 1 Science | `packages/groundwork_adapter/**`, scientific mapping examples, engine tests |
| 2 Backend | `apps/api/bean_api/**` except Owner 3's modules and Owner 4's `papers/**`; **`coordinator.py` and `tests/test_coordinator.py` (moved from Owner 3, paper sprint)**; backend tests except Owner 3's, 4's and 5's; `shared/contracts/**`; `contracts.py`, `main.py`, `http.py`, `intake.py`, materialization, migrations; `scripts/export_contracts.py`; root Python dependencies and `uv.lock` |
| 3 Gemini | `apps/api/bean_api/providers.py`, `conversation.py`, `ai_prompts.py`, the shared metered chat-model adapter (`gemini_chat_model.py` or one agreed name), multimodal extraction prompts; `tests/test_provider.py`, `tests/test_conversation.py`; `scripts/ai/**` |
| 4 Product/release | `apps/api/bean_api/papers/**` (PDF admission, parsing, page assets, manifests; no routes, contracts or dependencies), `tests/test_papers_*.py`, `fixtures/papers/**`, `docs/proposals/**`; `scripts/dev/**`, `scripts/release/**`, `.github/**`, root `README.md`, `docs/INTEGRATION_STATUS.md`, `docs/ownership-and-layout.md`, `docs/issue-ledger.md`, `docs/release-runbook.md`, `docs/handoff-owner04.md`, `docs/demo/**`, `docs/human-task/**`, `docs/submission-draft.md`, `docs/provenance-and-eligibility.md`, `docs/release-evidence/**`; `apps/web/**` for the minimal functional connection; in `tests/integration/`: `web_manual_smoke.mjs`, `package.json`, `release_checklist.json` |
| 5 Validation | `evaluation/**`, `docs/evaluation-protocol.md`, `evaluation/README.md`, `scripts/evaluate.py`, `tests/test_evaluation.py`, new Python HTTP/invariant tests `tests/integration/test_*.py` |

Paper sprint (14 November): Owner 1 also owns scientific eligibility and the exact paper-to-model mapping; Workstream 5 (Claude) qualifies the single combined integration commit that Owner 4 assembles. Owner 4 requests Owner 2 changes as reviewable patches in `docs/proposals/` and never applies them to Owner 2's files on a shared branch.

Each workstream also owns exactly one progress log and does not edit the others: `docs/workstreams/01-science.md`, `02-backend.md`, `03-ai.md`, `04-product-release.md`, `05-validation.md`. Workstream 4 maintains this ownership page, the issue ledger and the integration status as the shared index.

Shared rules:

- A defect in another workstream's files goes to the [issue ledger](issue-ledger.md) with exact input and logs. Nobody copies or patches another owner's subsystem.
- Owner 2 alone changes root dependencies and regenerates exported contracts.
- `fixtures/intake/**` controls are preserved; new variants are added separately.
- The release automation consumes Owner 5's harness and tests. It does not contain a second harness, corpus or ledger. `scripts/release/checklist.py` imports nothing from the product and calls `evaluation/cli.py` as a command.
- `.gitignore` and `.env.example` have no single owner; changes are additive and noted in the commit.

Runtime layout created by `scripts/dev/setup.sh` (all ignored by git): `.venv/` backend, `.venv-engine/` engine, `var/` store, sources, private auth file, and `var/run/` pid files and logs.

Default integration branch: `main`. Start new workstream branches from the current `origin/main`, and keep each workstream's changes on its own branch. Workstream 4 works on `claude/dreamy-lamport-dsttgm`.

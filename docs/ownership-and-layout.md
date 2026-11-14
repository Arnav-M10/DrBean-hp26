# Ownership and layout

Five coding workstreams, disjoint files. These are workstreams, not five human entrants: the team roster and the four-person limit are unchanged. Supersedes the pre-merge four-owner table, which said Owner 04 owned all evaluation and that no backend existed.

| Workstream | Exclusive edit scope |
|---|---|
| 1 Science | `packages/groundwork_adapter/**`, scientific mapping examples, engine tests |
| 2 Backend | `apps/api/bean_api/**` except Owner 3's modules; backend tests except Owner 3's and 5's; `shared/contracts/**`; `scripts/export_contracts.py`; root Python dependencies and `uv.lock` |
| 3 Gemini/deepagents | `apps/api/bean_api/providers.py`, `coordinator.py`, `conversation.py`, `ai_prompts.py`; `tests/test_provider.py`, `tests/test_coordinator.py`, `tests/test_conversation.py`; `scripts/ai/**` |
| 4 Product/release | `scripts/dev/**`, `scripts/release/**`, `.github/**`, root `README.md`, `docs/INTEGRATION_STATUS.md`, `docs/ownership-and-layout.md`, `docs/issue-ledger.md`, `docs/release-runbook.md`, `docs/handoff-owner04.md`, `docs/demo/**`, `docs/human-task/**`, `docs/submission-draft.md`, `docs/provenance-and-eligibility.md`, `docs/release-evidence/**`; `apps/web/**` for the minimal functional connection; in `tests/integration/`: `web_manual_smoke.mjs`, `package.json`, `release_checklist.json` |
| 5 Validation | `evaluation/**`, `docs/evaluation-protocol.md`, `evaluation/README.md`, `scripts/evaluate.py`, `tests/test_evaluation.py`, new Python HTTP/invariant tests `tests/integration/test_*.py` |

Shared rules:

- A defect in another workstream's files goes to the [issue ledger](issue-ledger.md) with exact input and logs. Nobody copies or patches another owner's subsystem.
- Owner 2 alone changes root dependencies and regenerates exported contracts.
- `fixtures/intake/**` controls are preserved; new variants are added separately.
- The release automation consumes Owner 5's harness and tests. It does not contain a second harness, corpus or ledger. `scripts/release/checklist.py` imports nothing from the product and calls `evaluation/cli.py` as a command.
- `.gitignore` and `.env.example` have no single owner; changes are additive and noted in the commit.

Runtime layout created by `scripts/dev/setup.sh` (all ignored by git): `.venv/` backend, `.venv-engine/` engine, `var/` store, sources, private auth file, and `var/run/` pid files and logs.

Branches: the integrated default branch is `codex/researcher-reviewer-web` (there is no `main`). Workstream 4 works on `claude/dreamy-lamport-dsttgm`, restarted from the default branch after PR #2 merged.

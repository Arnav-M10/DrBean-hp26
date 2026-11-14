# Ownership and layout

Five **coding workstreams** (not five human entrants; the handbook's limit of four human team members and the real roster are unchanged). Each owner edits only their own paths; a change to another owner's file is requested from that owner. Updated by Workstream 5 to the current five-workstream allocation; the earlier "Owner 04 owns all evaluation" and "backend absent" rows were pre-merge context.

| Path | Owner | State at the integrated base (586fb9b) |
|---|---|---|
| `packages/groundwork_adapter/**` (Counterdex), its scientific examples and engine tests | 1 — Science | present: fixed-pair checker, replay; baseline discovery pending |
| `apps/api/bean_api/**` except Owner 3's modules; backend module tests except Owners 3/5 files; `shared/contracts/**`; `scripts/export_contracts.py`; root Python dependencies and `uv.lock` | 2 — Backend | present: API, worker, ledger; real adapter not selected by startup |
| `apps/api/bean_api/providers.py`, `coordinator.py`, `conversation.py`, `ai_prompts.py`; `tests/test_provider.py`, `tests/test_coordinator.py`, `tests/test_conversation.py`; `scripts/ai/**` (offline preflight only) | 3 — Gemini/deepagents | present; explicit placeholder mode pending |
| Launch/doctor, `scripts/release/**`, `.github/**`, root `README.md`, operational/release/demo/consultation docs; `apps/web/**` and browser tests (minimal connection after the HTTP gate); `tests/integration/web_manual_smoke.mjs`, `tests/integration/package.json`, `tests/integration/release_checklist.json` | 4 — Product/release | present |
| `evaluation/**` (harness, cases, sources, manifest and ancestry, findings, append-only results), `evaluation/README.md`, `docs/evaluation-protocol.md`, `scripts/evaluate.py`, `tests/test_evaluation.py`, new Python HTTP/invariant tests in `tests/integration/` (excluding Owner 4's three files) | 5 — Claude validation | present: offline real-science lane, gates, findings |

Rules:

- `fixtures/intake/**` and frozen v1 evidence stay byte-identical; new cases get explicit manifest/version ancestry and synthetic provenance.
- `evaluation/drbean_eval/contract.py` is an independent test oracle aligned with, never replacing, Owner 2's `bean_api/canonical.py`.
- The harness reaches the product only through a subject: the launched isolated test stack (`http-launch`), a capabilities probe, or observations emitted by an owner's controlled boundary (imported claims, never qualification).
- Branches: integrated base `codex/researcher-reviewer-web`; Workstream 5 works on `claude/adversarial-validation`.

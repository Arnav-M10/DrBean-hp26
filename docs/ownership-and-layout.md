# Ownership and layout

Mapping of the shared contract's proposed paths to the actual repository. Published once by Owner 04; other owners should correct their own rows.

| Path | Owner | State at this commit |
|---|---|---|
| `packages/groundwork_adapter/` | 01, Groundwork science | absent |
| `apps/api/` | 02, Gemini backend and agent | absent |
| root dependency manifests, shared schemas, generated client | 02 | absent |
| `apps/web/` | 03, researcher and reviewer web | present: local draft workspace, dependency-free |
| `evaluation/` | 04 | present: harness, frozen manifest, cases, sources, results, ledger |
| `tests/integration/` | 04 | present: browser smoke, twelve-boundary checklist; own `package.json`, not the root manifest |
| `scripts/release/` | 04 | present |
| `docs/` | 04 (each owner reviews claims about their component) | present |
| `README.md`, `.env.example`, `.gitignore` | 04 drafts; 02 integrates root manifests | present |

Rules Owner 04 follows:

- No edits under `apps/web`, `apps/api` or `packages/`. Defects go to the [issue ledger](issue-ledger.md) for the owner.
- No second DTO definition, Gemini client, approval authority or backend. `evaluation/drbean_eval/contract.py` is a test oracle written from the contract text; Owner 02's canonicalizer and golden fixtures are authoritative.
- The harness reaches the product only through a subject: observations emitted by the owning component's controlled test boundary, or the published API.

Branches: Owner 03 works on `codex/researcher-reviewer-web`. Owner 04 works on `claude/dreamy-lamport-dsttgm`, based on that branch at `d95c19e`. The remote has no default branch content beyond these.

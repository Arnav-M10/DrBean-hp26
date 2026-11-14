# Combined preview `e67c3cf` (labelled preview, never acceptance)

The merge is local and was never pushed:
- harness `10c302c`;
- PR #33 `codex/paper-science-mapping` `b397c05`;
- PR #35 `codex/gemini-metered-adapter` `c952c35`;
- PR #36 `claude/dreamy-lamport-dsttgm` `081bbdc`;
- PR #36's `docs/proposals/owner2-paper-routes.patch`, which Owner 2 has not reviewed;
- an unlocked `uv sync` for the patch's pypdf/pypdfium2 pins.

All three PRs merged with no conflicts. The platform is macOS 26.7 arm64.

| Suite | Result |
|---|---|
| Backend (`pytest tests --ignore=tests/integration`), engine runtime built from the combined tree as `launcher.py setup` does | **898 passed** |
| Same suite with main's stale `.venv-engine` | 20 failed / 878 passed, all `source_version_mismatch`. This is an environment artifact, but an operational warning: **after PR #33 merges, everyone must rerun `launcher.py setup`** |
| Engine suite (CPython 3.11, combined engine runtime) | 306 OK, 3 skipped. Run without an installed engine, PR #33's two new replay tests cannot import `counterdex` |
| `tests/integration` (this harness) | **134 passed, 18 xfailed**: the 4 F-NARRATION-OVERSUPPRESSION cases, the 6 F-PAPER-* validator defects, the NOT_AVAILABLE proposal, metered-model and resume attacks, and the opt-in or launcher-port NOT_RUN tests |
| Web unit tests | 36/36 |

No cross-PR regression was found. The open defects are the known findings: F-PAPER-CITATION-SUBSTRING (P1), F-PAPER-RENDER-MEMORY (P1), F-PAPER-QUOTE-NORMALIZATION, F-PAPER-HARD-BOUND-CONTEXT, F-PAPER-EXPONENT-FLATTENING and F-PAPER-IDENTITY-CONTRACTS (P2). The page identities still differ between PRs #35 and #36, but no code path joins them yet.

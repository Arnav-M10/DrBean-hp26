# Provenance, eligibility and event contributions

## Event window

Build window per the handbook (H1): Friday 13 November 2026 20:00 Eastern to Sunday 15 November 2026 08:00 Eastern. Feature freeze: Sunday 02:00 Eastern. In-person judging: Sunday 09:30 to 14:30 Eastern. Maximum team size four. Presentation and optional video: 120 seconds each.

## Starting point inspected

| Item | Value |
|---|---|
| Repository | `Arnav-M10/DrBean-hp26` (remote verified) |
| Branches found on the remote | `codex/researcher-reviewer-web` only |
| Commit found | `d95c19ecd58e51d16aa0b255d2d4d4395f810cd4`, authored Fri 13 Nov 2026 19:54 -0600 (20:54 Eastern, inside the window) |
| Content | `apps/web/` (10 files), Owner 03's local draft workspace |
| Local instructions (CLAUDE.md, AGENTS.md, CONTRIBUTING) | none present |
| Dependency locks | none; `apps/web` has no dependencies |

## Reuse decision

**Status: pending.** No organizer ruling on reuse of pre-event implementation has been recorded by the human team. Until one is, this branch follows the restrictive reading:

- No code, fixture or artifact from the historical baselines is in this branch. The aliases below are recorded for provenance only and were not available locally.
- Nothing here is presented as reused or as depending on prior implementation.
- If reuse is later allowed, record exactly what was allowed here, with license and attribution, before importing anything.

| Alias | Commit | Used in this branch |
|---|---|---|
| ENGINE-BASE | `3ce8674f426145224c2a7676f00de39e00f1db7a` | no |
| PRODUCT-MAIN | `f1cd64b9539912d57af881c62167beb8b2a30212` | no |
| PRODUCT-INTEGRATION | `82430abd8ce98efe41b885ceec636c8ff82ba67d` | no |

The work order and the embedded shared contract (GF-2 / DB-SC-1, source SHA-256 `2dc232c8f2477ed959864e039d97655c287e6cce61cc54179daa6b0569f0fe59`) predate the event. They are planning documents, not implementation. Whether project-specific planning documents count as permitted preparation is part of the same organizer question.

## Event-time contribution ledger (Owner 04)

Everything below was written during the event window, on this branch, with AI assistance (Claude Code), from the work order and contract text.

| Contribution | Location | Source of content |
|---|---|---|
| Evaluation harness | `evaluation/drbean_eval/`, `evaluation/cli.py` | new |
| Twelve-case portfolio and frozen assertions | `evaluation/cases/`, `evaluation/authoring/build_cases.py` | new, from work order section 6 |
| Synthetic lab sheets and expected transcriptions | `evaluation/sources/` | new; rendered from `evaluation/sources/build/sheets.mjs`; values match Owner 03's synthetic example in `apps/web/app.mjs` (A = 10, ke = 0.2, ka = 1.0, rounded) |
| Harness tests, browser smoke, release scripts | `evaluation/tests/`, `tests/integration/`, `scripts/release/` | new |
| Documentation | `README.md`, `docs/` | new |

Fixture sources and digests are pinned in `evaluation/manifest.json`. Third-party code in this branch: none. Tools used at run time: Python standard library, Node standard library, Playwright 1.63.0 (test only, not vendored).

## Authorizations not granted by this work

Organizer messages, participant outreach, publication, submission, account enrolment, spending and provider calls all need the human team's specific authorization. None was performed.

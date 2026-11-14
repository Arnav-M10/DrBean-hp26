# Dr. Bean

Dr. Bean is a research evidence assistant, powered by the Groundwork engine. It is meant to help a researcher turn an ambiguous result into a defensible next measurement: read one lab sheet, review every extracted value, run a bounded check of a narrow claim, and choose a useful next observation.

This README describes what the repository actually contains at the tested commit. Planned features are listed separately and are not claimed.

## What works today

| Area | State | Evidence |
|---|---|---|
| Local web workspace (`apps/web`): CSV or manual measurements, exact rational validation, model bounds and target interval, review, draft download | Works with no install, no key and no network | `node --test` in `apps/web`; `tests/integration/web_manual_smoke.mjs` (14 browser checks) |
| Evaluation harness (`evaluation/`): 12 cases × 2 variants with frozen expected assertions, grader, four evidence lanes, append-only attempt ledger, shared provider-budget ledger, trace sanitizer | Works; the harness's own tests pass | `python3 -m unittest discover -s evaluation/tests` |
| Frozen synthetic sources: 12 lab-sheet images plus 2 sealed holdouts, with expected transcriptions and pixel regions | Frozen by SHA-256 in `evaluation/manifest.json` | `python3 evaluation/cli.py verify` |
| Release checks: clean-clone run, secret scan, twelve-boundary checklist | Runs; reports the build as not release-ready | `scripts/release/clean_checkout.sh` |

## What does not exist yet

There is no backend, no `/api/bean/v1`, no Gemini integration, no deepagents runtime, no Groundwork scientific adapter, no approvals, runs, design jobs, reports or replay. Consequently:

- No Gemini request has been made by this project. Zero provider requests, zero tokens, zero cost.
- No scientific computation or check has run. No certificate, counterexample or measurement suggestion exists.
- All 24 scheduled fixture traces and all 10 scheduled live invocations are recorded as **unrun**, with the reason. See `evaluation/results/REPORT.md`.
- 10 of the 12 cross-owner release boundaries are unrun, 2 are partial. See `evaluation/results/release-checklist.json`.

The harness's self-test exemplars prove the grader works. They are not product evidence and never enter the attempt ledger.

## Run it

Requirements: Node 22 and Python 3.11 or newer. The browser smoke also needs Playwright (`npm install` in `tests/integration`); without it that check reports unrun.

```bash
node apps/web/serve.mjs
```

Open `http://127.0.0.1:4173`. Stop with Ctrl-C. Nothing is stored outside the browser tab.

```bash
python3 scripts/release/checklist.py
```

Runs every automated check and prints the twelve-boundary table for the current commit.

```bash
scripts/release/clean_checkout.sh
```

Repeats the checks from a clean clone, so nothing depends on untracked files.

```bash
python3 evaluation/cli.py run --lane fixture_contract
```

Runs the 24 scheduled fixture entries against the configured subject (none by default) and appends one record per entry.

More commands: [docs/release-runbook.md](docs/release-runbook.md).

## Chosen scope

- **Source modality:** one PNG image. PDF is not selected and its admission cases are unrun by decision.
- **Model:** `C(t) = A*(exp(-ke*t) - exp(-ka*t))`, concentration in mg/L, time in hours.
- **Advertised design tier:** numerical guidance only. Checked pair separation is unshipped until Owner 01 delivers replayable evidence.
- **Store:** local SQLite lane proposed. Tiger Data, MongoDB, Solana, Vultr and Photon are omitted.

## What a result would and would not mean

A checked assignment outside a claimed interval shows that the reviewed measurements and model do not force the parameter inside that interval. It does not establish the true parameter, validate the physical model or support a clinical decision. A next-measurement suggestion compares two named candidates at reviewed feasible times under a stated future hard allowance. A later reading can reject either candidate or both. It never proves the interval. Gemini proposes and explains; it does not approve assumptions or decide validity.

## Documents

- [Ownership and layout](docs/ownership-and-layout.md)
- [Provenance, eligibility and event contributions](docs/provenance-and-eligibility.md)
- [Evaluation protocol](docs/evaluation-protocol.md) and [observation schema](evaluation/README.md)
- [Cross-owner issue ledger](docs/issue-ledger.md)
- [Release runbook](docs/release-runbook.md)
- [120-second demo script](docs/demo/demo-script.md)
- [Human task protocol](docs/human-task/task-protocol.md)
- [Submission draft](docs/submission-draft.md)
- [Owner 04 handoff](docs/handoff-owner04.md)

All test sources are synthetic and labelled as such. No real laboratory data, personal data or credentials are in this repository.

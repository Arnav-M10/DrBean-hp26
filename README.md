# Dr. Bean

Dr. Bean is a research evidence assistant. Its goal is one decision loop: review measurements, find a compatible counterexample to a claimed parameter range, choose a next measurement that tells two candidate explanations apart, check which survives a new reading, and replay the exact evidence. The scientific engine is **Counterdex** (`packages/groundwork_adapter/counterdex`).

This README states what the repository does at the tested commit. Status by gate is in [docs/INTEGRATION_STATUS.md](docs/INTEGRATION_STATUS.md).

## Current state in one paragraph

The API, worker and web workspace start with one command and survive a restart. An approved baseline runs the real engine and returns scoped results with native evidence that replays in a separate process. The browser supports reviewed exact inputs, frozen plans, separate approvals, actual baseline and next-measurement design, history and native downloads. Backend follow-up checks retain the original pair and a separately reviewed reading. Source-review and follow-up browser controls remain pending, so the full usable-release gate is incomplete. The independent HTTP suite is delivered; qualification depends on its retained results for the current commit. Counterdex also works offline on CPython 3.11. **Gemini remains a disabled placeholder. The launcher removes provider configuration, and offline acceptance checks verify zero model-provider dispatch.**

## Run it

Requirements: [uv](https://docs.astral.sh/uv/) and Node 20 or newer. uv installs the Python runtimes: the backend on Python 3.12/3.13 from `uv.lock`, the engine on CPython 3.11 (its only qualified runtime). Do not use whichever `python3` is on your PATH for product code.

```sh
scripts/dev/setup.sh
```

Installs both runtimes, creates the private local auth file if absent, and prints the doctor report. It never deletes data in `var/`.

```sh
scripts/dev/start.sh
```

Starts the API (`127.0.0.1:8000`), the durable worker and the web workspace (`127.0.0.1:4173`) on one SQLite store under `var/`, waits until they answer, and prints service facts. Loopback only.

```sh
scripts/dev/stop.sh
```

Stops only the processes the launcher started. Data is kept.

```sh
scripts/dev/doctor.py
```

Reports, as separate facts: API ready, worker ready, scientific adapter available and qualified, native replay supported, and Gemini live (disabled, not tested).

Open `http://127.0.0.1:4173`, expand **Local backend connection**, and paste the bearer token from the private file `var/auth.json`. The token stays in memory only. Never put it in a URL, a screenshot or chat. API documentation is at `http://127.0.0.1:8000/docs`.

If a start fails, the launcher prints the log tail and stops what it started. Port already in use: it refuses and kills nothing. After an unclean stop, run `python3 scripts/dev/launcher.py recover` before the next start. Details: [docs/release-runbook.md](docs/release-runbook.md).

## What works, and how it is checked

| Area | State | Check |
|---|---|---|
| One-command launch, restart, reopen evidence, credential and origin refusal | works | `python3 scripts/release/stack_smoke.py` (31 checks, isolated store) |
| Manual HTTP path: dataset, problem, plan, approval, one run, report | works; result is `unsupported` | same smoke; `uv run pytest -q` (264 backend tests) |
| Browser to API: plan, approval, run retrieval, downloads | works | `node apps/web/check-backend.mjs` |
| Web editor: exact entry, validation, export | works | `node --test` in `apps/web`; `tests/integration/web_manual_smoke.mjs` |
| Counterdex engine standalone: candidate discovery, exact check, fixed-pair design, native replay | works on CPython 3.11 | 257 engine tests; replay of the prepared synthetic bundle |
| Source intake and review, deepagents graph | backend-tested with **controlled placeholder** models only | backend tests |
| Baseline discovery through the API and browser | works (as root locally; CI is the non-root lane) | `stack_smoke.py --require-science`; `node apps/web/check-backend.mjs` |
| Design, native export and replay through the API (gate G2) | backend-tested from a seeded regression pair only; unreachable over ordinary HTTP until discovery exists | backend tests |
| Browser controls for source review, design and follow-up | **not built** (waits for G1) | |
| Live Gemini | **not run; disabled** | |

```sh
python3 scripts/release/checklist.py
```

Runs every suite above and prints checks, gates and boundaries for the current commit. Exit 0 here is a status report, not a release.

```sh
python3 scripts/release/checklist.py --strict-offline
```

Exits nonzero unless every offline gate has passing evidence. It currently fails, correctly.

```sh
scripts/release/clean_checkout.sh
```

Repeats the checks in a clean clone with freshly installed runtimes.

## What a result would and would not mean

A checked candidate outside a claimed interval shows that the reviewed measurements and model do not force the parameter into that interval. It does not identify the true parameter, validate the model or support a clinical decision. A suggested measurement time concerns only the two named candidates, the reviewed feasible times and the stated future hard allowance. A later reading can exclude either candidate or both; it never proves the interval. Replay is a fresh run of the same checker, not an independent proof system. The person reviews assumptions and authorizes work; the checker decides mathematical validity; AI output, placeholder or live, can do neither.

## Scope

One model, `C(t) = A*(exp(-ke*t) - exp(-ka*t))`, hours and mg/L. One PNG or JPEG source. Local SQLite. No PDF intake, hosted deployment, second database, blockchain, messaging or extra model provider. All data in this repository is synthetic.

## Documents

- [Integration status by gate](docs/INTEGRATION_STATUS.md), [cross-owner issue ledger](docs/issue-ledger.md) and [workstream logs](docs/workstreams/)
- [Release runbook](docs/release-runbook.md) and [operational handoff](docs/handoff-owner04.md)
- [Ownership and layout](docs/ownership-and-layout.md)
- [Two-minute demo script](docs/demo/demo-script.md) and [submission draft](docs/submission-draft.md)
- [Consultation and observed-task protocol](docs/human-task/task-protocol.md)
- [Provenance and eligibility](docs/provenance-and-eligibility.md)
- Backend: [handoff](docs/HANDOFF.md), [validation](docs/VALIDATION.md), [shared contracts](shared/contracts/README.md)
- Engine: [integration](packages/groundwork_adapter/docs/INTEGRATION.md), [README](packages/groundwork_adapter/README.md)
- Evaluation: [protocol](docs/evaluation-protocol.md), [harness](evaluation/README.md)
- Web: [workspace notes](apps/web/README.md)

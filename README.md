# Dr. Bean backend

An authenticated research-workflow API implementing the **GF-2 operational policy** and **DB-SC-1 application contracts** from the backend work order. It preserves exact reviewed inputs, immutable research history, separate provider permission and scientific approval, durable reservations, and honest evidence states.

This repository combines Owner02's backend with the researcher draft workspace under `apps/web`. The web workspace currently runs independently and is not yet connected to the backend approval/run routes. The Groundwork scientific engine is not included. The API runs without Gemini credentials. Its default scientific adapter returns `unsupported`; it cannot issue a scientific certificate. Gemini and real deepagents adapters are implemented and tested with explicitly controlled transports/models, but no live Gemini request has been made or qualified here.

## Start locally

Requires Python 3.12 or 3.13 and [uv](https://docs.astral.sh/uv/).

```sh
uv sync --locked
uv run python -m bean_api.bootstrap
uv run uvicorn bean_api.main:create_app --factory --host 127.0.0.1 --port 8000
```

In another terminal, start the durable worker:

```sh
uv run python -m bean_api.worker
```

The API documentation is at `http://127.0.0.1:8000/docs`; capabilities are at `/api/bean/v1/capabilities`. The bootstrap creates a private, ignored `var/auth.json`. Read its local researcher bearer token locally and use the documentation's **Authorize** control or an `Authorization: Bearer …` header. Tokens never belong in URLs, examples, source control, or browser bundles. There is no unauthenticated mutation mode. Auth uses bearer headers; the API does not issue cookies and does not enable cross-origin browser access. Keep this local lane on loopback.

To run the separate researcher draft preview, use `node apps/web/serve.mjs` and open `http://127.0.0.1:4173`. See [the web workspace instructions](apps/web/README.md) for its current scope. Run its tests with `npm --prefix apps/web test`.

`uv` cache location can be set to a writable directory if needed, for example `UV_CACHE_DIR=/workspace/.uv-cache uv sync --locked`. Environment examples are in `.env.example`; export the variables in the server shell. The app does not automatically load `.env`.

## Implemented path

1. Create an authenticated workspace and enter exact manual data, or upload one retained synthetic/public PNG or JPEG. Upload alone never contacts Gemini.
2. An explicitly disclosed, consented intake operation can request unaccepted Gemini transcriptions. Review every field, resolve ambiguity, and retain corrections and source locations. The manual route remains available.
3. Create an immutable dataset, problem, and exact plan. Approve the plan's digest and current problem revision through the dedicated approval route. Queueing a run atomically consumes its one durable reservation.
4. A manual worker calls only its frozen baseline. A consented Gemini plan invokes the actual deepagents framework with a checked tool inventory and bounded callbacks. Source text and chat cannot approve work.
5. A design request binds an existing scenario and two exact candidate vectors; it has its own plan, approval, and job. An observation is separately reviewed into a new immutable dataset, preserving actual/hypothetical ancestry.
6. Reopen persisted conversation and records, download authenticated JSON report snapshots with byte hashes, and inspect activity and provider-attempt ledgers.

The initial source path supports one PNG/JPEG, at most 5 MiB and 12 megapixels; it rejects PDFs, animation, malformed files, unsupported orientation and non-retention. A bounded parser process enforces decode resources. All scientific values are reduced rational strings; `/exact/decimal` converts finite decimal strings exactly. Source grounding and checked scientific evidence remain distinct.

## Validate

```sh
uv run pytest -q
uv run ruff check apps tests scripts
uv run python scripts/export_contracts.py
uv run python scripts/evaluate.py
```

Tests cover actual concurrent reservation races, stale approval, cancellation and process termination, restart reconciliation, exact canonical bytes, malformed media, source ambiguity, cross-workspace rejection, real framework tool inventory, controlled evidence-dependent choices, HTTP integration, and backup/restore. They do not substitute for live provider, engine, replay, or hosted-database qualification.

The shared schemas and synthetic exchanges are in [shared/contracts](shared/contracts/README.md). See [the handoff](docs/HANDOFF.md) for exact limits, qualification gates, migration/recovery and owner integration, and [evaluation notes](docs/EVALUATION.md) for the source corpus and separate evidence lanes.

The completed validation run passed **164 tests**, lint, schema export and wheel packaging. The [validation record](docs/VALIDATION.md) distinguishes these controls from the still-unrun live acceptance portfolio.

## Integration, evaluation and release (Owner 04)

The cross-owner evaluation harness, frozen twelve-case portfolio, shared provider-budget ledger, browser smoke and release checks live in `evaluation/`, `tests/integration/` and `scripts/release/`. They use the Python standard library and Node only.

```sh
python3 scripts/release/checklist.py
scripts/release/clean_checkout.sh
python3 evaluation/cli.py run --lane fixture_contract
```

See the [evaluation protocol](docs/evaluation-protocol.md), [release runbook](docs/release-runbook.md), [cross-owner issue ledger](docs/issue-ledger.md), [provenance and eligibility](docs/provenance-and-eligibility.md), [demo script](docs/demo/demo-script.md), [submission draft](docs/submission-draft.md) and [Owner 04 handoff](docs/handoff-owner04.md). The recorded results in `evaluation/results/` were taken before the backend and science package were merged and say so; they are retained, not rewritten.

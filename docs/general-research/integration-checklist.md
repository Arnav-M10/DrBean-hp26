# B adoption status

The compatible producer from PR40 at3f9c2e9 is registered in the actual application.
Original Claude authorship/tests are retained and disclosed; B maintains production
parsing/routes/storage. The optional global256-request grant expansion is excluded.
Current global caps/history remain conservative; research allocation defaults to0.
B added parser parent lifelines and reused permission-aware scientific cleanup.

The original producer handoff below is historical reference; current ownership is
A/B/C in docs/ownership-and-layout.md. No departed-owner handoff is required.

# General research — integration checklist for GPT1

Branch `codex/general-gemini-files` (Claude). It adds the backend for general files, citations and
Gemini analysis as `apps/api/bean_api/general_research/`, and does **not** edit `main.py`, `auth.py`,
`config.py`, the gateway, the launcher, the web app or the engine. Wiring it into the real application is
yours; the steps below are exact.

## 1. Shared files this branch changes (review these first)

| File | Change | Why |
|---|---|---|
| `pyproject.toml`, `uv.lock` | adds `pypdfium2==5.14.0` (released 2026-10-04) | PDF text layer with character boxes, page rendering |
| `apps/api/bean_api/http.py` | `RequestBoundary` treats `POST /api/bean/v1/workspaces/{id}/research-assets` as a raw upload (5 MiB limit, no strict API-JSON parsing) | a user's JSON data file may contain floats or non-ASCII keys |
| `apps/api/bean_api/ledger.py` | optional owner budget grants (append-only, hash-chained, immutable; table created only by the first grant); `diagnostics()` adds `effective_caps` and `budget_grants` | without a grant the nearly exhausted live ledger can never admit a general analysis |

`providers.py` is unchanged. `general_research/transport.py` imports from it: `ProviderConfig`,
`ProviderFailure`, `AttemptContext`, `LIVE_MODELS`, `classify_failure`, `live_usage`, `sanitize_usage`,
`live_wire_schema`, `utc_now`, `package_version` and the private helpers `_finish_reason`, `_request_id`,
`_parse_response`, `_hosted_sdk_object`. Keep those names (or tell me) when merging PR #35 or later
provider work.

## 2. Register the routes in `create_app` (main.py)

At the end of `create_app`, after `app.state.settings/workflow/ledger/provider` are set and the
`DomainError`, `ProviderFailure` and `LedgerBudgetExceeded` handlers exist:

```python
from .general_research import general_research_capabilities, register_general_routes

    ...
    register_general_routes(app)        # live or disabled from the server's single ProviderConfig
    return app
```

and in the `/capabilities` response add:

```python
                "general_research": general_research_capabilities(app),
```

The merged UI reads `capabilities.general_research` with exactly the fields this helper returns
(`available`, `max_assets`, `max_file_bytes`, `max_total_bytes`, `max_pdf_pages`,
`analysis.{available,model,reason}`, `budget.remaining`); a backend test runs the UI's own validators
against real responses.

`register_general_routes(app, transport=None, controlled_responder=None)` builds a
`GeneralResearchService` from `app.state.workflow`, `app.state.settings.blob_dir` (blobs go to
`<blob_dir>/research-assets/<sha256[:2]>/<sha256>`), `app.state.provider.config` and `app.state.ledger`
(the shared global ledger; live mode uses its `request_cap=8`). It stores the service at
`app.state.general_research` and refuses a second registration. With `BEAN_GENERAL_ANALYSIS_MODE=controlled_demo`
and a non-live provider it uses the deterministic controlled responder and a zero-spend ledger.

Then **remove the `xfail` marker** from
`tests/test_general_research_contract.py::test_the_assembled_application_serves_general_research`. It is
strict: it starts failing (XPASS) the moment the real `create_app` serves the routes, which is the signal
that integration is verified in the assembled app rather than only in a fixture.

## 3. Authentication and sessions (already compatible)

Every route depends on `bean_api.auth.principal`, which on current `main` (PR #38/#39) already resolves
your private browser sessions as well as bearer owners, and every read re-checks workspace membership
(`Workflow.get`/`authorize`; foreign IDs are 404). Nothing in `general_research` needs to change for
sessions. Uploads and analyses are workspace-scoped, so private browser workspaces isolate files and
analyses automatically; please include general assets and analyses in your two-context isolation test.

## 4. Gateway and proxies (mostly done on main)

`apps/web/serve.mjs` and `share-gateway.mjs` on `main` already forward `Content-Type`, `Idempotency-Key`
and printable-ASCII `X-Source-Name`, pass `Content-Disposition`, `X-Artifact-SHA256` and `X-Request-ID`
back, and allow 75 s for `research-analyses` (the backend's request timeout is 30 s by default, at most
60 s). Remaining, optional: also pass `Content-Security-Policy` on `GET /research-assets/{id}/content` and
`.../pages/{n}/image` responses (the backend sets `default-src 'none'; sandbox`). Raw upload bodies up to
5 MiB must reach `/workspaces/{id}/research-assets`; JSON bodies elsewhere keep the 256 KiB limit. The
browser sends `application/octet-stream` when it has no MIME type; the backend detects the real type.

## 5. Runtime

No worker, queue or new process type. The API process starts short-lived parser subprocesses
(`sys.executable -I .../_pdf_worker.py` and `_image_worker.py`) with a minimal environment; they need the
API virtualenv (`uv sync --locked` provides `pypdfium2` and `Pillow`). Memory is bounded by `RLIMIT_AS`
plus a resident-memory watchdog on Linux and by a physical-footprint watchdog on macOS; a structural
pre-scan refuses decompression bombs before PDFium runs. No new secret or environment variable is needed
for live mode: it uses the existing `BEAN_AI_MODE=live_opt_in` provider configuration and the single
server key. Nothing reads or logs the key.

## 6. Budget (owner decision; I did not activate anything)

The shared ledger allows 5 more attempts in principle but, as reported, only about 4,568 input and 4,736
output tokens remain. A general analysis reserves `1,024 + UTF-8 bytes of prompt, instructions and
schema` (about 7,000 fixed) plus 8,192 per image, and 4,096 output tokens, so today every live analysis is
refused before dispatch with `provider_budget_exhausted` (409), in every workspace. To allow a bounded
live smoke the owner can append a grant on the server machine:

```sh
.venv/bin/python -m bean_api.ledger status --database var/bean.sqlite3
.venv/bin/python -m bean_api.ledger grant --database var/bean.sqlite3 \
  --decision-id owner-YYYY-MM-DD-general-smoke --granted-by "<owner>" \
  --reason "One bounded public-data general analysis smoke" \
  --input-tokens 20000 --confirm-owner-decision
```

Grants only add capacity; they never erase, refund or reset attempts; a reused decision id or a tampered
chain is refused (the ledger then fails closed). The chain is tamper-evident against accidental or naive
edits; it is not a defence against someone who can rewrite the database file. Free tier remains the
owner's assertion, not a billing check. Do not grant on behalf of the owner.

## 7. Verify after wiring

```sh
uv run pytest -q tests --ignore=tests/integration -rs     # with BEAN_COUNTERDEX_PYTHON=.venv-engine/bin/python
uv run ruff check apps tests scripts
uv run python scripts/export_contracts.py && git diff --exit-code -- shared/contracts
PYTHONPATH=apps/api uv run python -m bean_api.general_research.contract --check
python3 scripts/release/secret_scan.py
```

Then, in the assembled app with `BEAN_GENERAL_ANALYSIS_MODE=controlled_demo`: upload
`fixtures/general/noaa-gml-co2-annmean-mlo.csv` (origin `real_observation`) and
`fixtures/general/naca-tn-1428-pages-1-5-6.pdf` (origin `public_source`), estimate, analyze, reload the
page and reopen the analysis by id: no second model call may happen, and a second browser session must
get 404 for both IDs.

Live smoke (only with the owner's explicit approval and a grant): one analysis of the NOAA CSV with a
short question, `consent.model` equal to the configured model, then `GET /workspaces/{id}/provider-attempts`
must show exactly one new `general_analysis` attempt. Record it as a live result; everything else is
controlled.

## 8. Known limits

- No OCR: scanned pages and images are sent as images; their quotes are `unverifiable_*`.
- PDF pages with a text layer are sent as text only (figures on those pages are not sent; the record says so).
- The conservative estimate (8,192 tokens per image under the current live configuration) admits at most
  two images per request.
- Analyses are synchronous; an interrupted request is closed as `unknown_outcome` on the next retrieval
  with the same operation key after the timeout window.
- `supported_adapter` is a signal only; mapping into the concentration workflow still needs the existing
  review and plan approval.

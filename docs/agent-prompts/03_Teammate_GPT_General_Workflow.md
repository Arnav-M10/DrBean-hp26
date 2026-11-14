# Teammate GPT — General research workflow and browser acceptance

You are the owner of the general research user experience for **Dr. Bean**. Work in **https://github.com/Arnav-M10/DrBean-hp26**. Build working software, test it, and deliver a reviewable PR. Coordinate directly through repository interface notes and PRs instead of requiring the user to supply another prompt after each step.

## Shared objective and honest starting point

The product must accept a researcher's own data and documents, use the one server owner's Gemini configuration, explain the supplied evidence, and offer useful next steps. Example data must be optional. Do not make users reshape unrelated research into concentration measurements merely to enter the application.

Current tested `main` is `3738724`; its GitHub CI passed. It has CSV/manual concentration inputs, reviewed image proposals, bounded Gemini explanations, scientific investigation, measurement design, and native evidence replay. The mathematical engine currently supports one two-rate concentration model. Broad Gemini interpretation is a separate capability: it must never receive a mathematical verification badge simply because a model returned an answer.

An unfinished token-free sharing prototype will be available on `origin/codex/shared-access-handoff`. Its seven implementation files are WIP, not release-qualified. In particular, its single `shared-demo` identity is unsuitable for private general research. GPT 1 will replace that mechanism with separate browser sessions. Do not build a public interface that silently shares everyone's files or workspaces.

## Start safely and establish ownership

Inspect repository instructions and current Git status. Preserve other people's work. Fetch origin, then create an independent worktree and branch from the latest `origin/main`, for example:

```sh
git fetch origin
git worktree add ../DrBean-general-ui -b codex/general-research-ui origin/main
```

If the branch/worktree already exists, inspect and resume it. Read all three handoff prompts from `origin/codex/shared-access-handoff` and inspect the current PRs. Do not blindly cherry-pick the entire sharing WIP.

You own `apps/web/general-workspace.mjs`, its tests, the general-workspace DOM/styles in `index.html` and `styles.css`, and integration hooks in `app.mjs`/`workflow.mjs`. Preserve the current scientific workflow. GPT 1 owns `api.mjs` transport, backend authentication/configuration/session wiring, `main.py` route registration, and the sharing gateway/launcher. Claude owns general file admission, research-analysis backend services, Gemini/provider/ledger changes and their tests. Request small integration patches from those owners rather than concurrently editing their files. Agree a small JavaScript adapter interface with GPT 1 before implementing session-dependent UI.

## Build the actual workflow

Make the primary entry point “Add your data or paper.” Accept CSV, TSV, JSON, TXT, Markdown, PNG, JPEG and PDF when the server advertises the corresponding capability. Show explicit unsupported-format and size messages; never treat a filename extension as proof that parsing succeeded. Limits are 1–5 files, at most 5 MiB per file and 10 MiB combined; PDF admission is limited to ten pages. Render only admitted pages and bounded previews.

Let users inspect retained filenames, source identity, pages and tables, then ask a question in their own words. Send nothing to Gemini until the person accepts the selected files/question disclosure. Show which files will be sent, the configured model, current availability and remaining application budget in clear language. A source upload alone does not authorize a model call or scientific execution.

Present the returned summary, extracted tables, claims, limitations, clarification questions and next steps. Preserve arbitrary column names and units. Show citations beside the statements they support. Expandable evidence details may expose exact identifiers; implementation jargon should not dominate the normal workflow. Keep absent information visibly unresolved instead of supplying invented values.

General analysis must say “AI analysis — not mathematically verified.” Offer a scientific verification path only when the selected adapter supports the reviewed problem. Mapping a general table into the existing concentration workflow requires explicit column/unit/assumption review and the existing separate plan approval. Never auto-approve data, reclassify uncertainty statistics as hard bounds, or manufacture a certified outcome.

## Coordinate against these contracts

Use `/api/bean/v1` throughout. Treat the following as the shared implementation contract; record any agreed change before another owner implements against it:

- `GET /shared-session` is gateway metadata: `{mode:"browser_session", authenticated:true, workspace_id, credentials:"server_managed"}`. The browser uses an automatic secure HttpOnly session, never a JavaScript bearer credential. Preserve advanced local owner login. Do not implement the session mechanism yourself.
- `POST /workspaces/{workspace_id}/research-assets` uploads raw bytes with `Content-Type` and optional `X-Source-Name`. The durable asset includes `id`, `sha256`, `media_type`, `byte_size`, `filename`, `provenance`, and `pages` with zero-based `page_index`, one-based `page_number`, dimensions, `image_sha256` and `text_sha256`. `GET /research-assets/{id}` is authorized metadata retrieval.
- `POST /workspaces/{workspace_id}/research-analyses` accepts `{client_operation_id, question, assets:[{id,sha256}], consent:{accepted,provider:"gemini",model,asset_ids,include_question:true}}`. Its `Idempotency-Key` equals `client_operation_id`. A bounded synchronous request returns HTTP 201 with a durable analysis record; `GET /research-analyses/{id}` reopens it.
- The analysis body supplies `summary`, `extracted_tables`, `claims`, `limitations`, `clarifications`, `suggested_next_steps`, `citations`, `provider_attempt_id`, and `verification:{status:"not_mathematically_verified",supported_adapter:null|adapter_id}`. Checked mathematical results remain separate actual evidence records.
- Citations bind the source SHA-256, zero-based page index and exact quote. Optional boxes use normalized 0–1 coordinates from the top left, with an explicit `bbox_space`. Display human page numbers as index plus one. Never mix text offsets, image pixels and normalized boxes.

Build useful UI against an injected bounded service adapter while backend endpoints are being completed. Mark authored fixtures and controlled responses as tests; they are not live Gemini results. Do not add production fallback answers to conceal an unavailable backend.

## Reliability, privacy and acceptance

Preserve the exact operation identity after an uncertain response. A deliberate retrieval/retry uses the same body and key; editing the question or selected sources requires a new operation and fresh consent. Avoid automatic model retries. Reopening a result performs retrieval, not another analysis.

Escape all model/source text. Do not insert returned HTML, execute document instructions, or render Markdown with unsafe raw HTML. Use bounded tables and previews. Handle refusal, quota exhaustion, timeout, invalid citations, missing sources and unavailable verification without discarding existing evidence.

The user permits **free tier only, $0**. The existing ledger is nearly exhausted. Display preflight failures clearly. Do not reset attempts, refund reservations, introduce another provider, enable billing, or call Gemini directly from the browser. Coordinate any auditable budget-policy change with Claude and GPT 1. No real key may enter Git, DOM, URLs, storage, screenshots, fixtures or logs.

Run meaningful unit and browser tests. Test arbitrary non-concentration columns, multiple files, citation navigation, malformed/oversized files, safe rendering, changed consent, uncertain retrieval and saved-result reopening. Exercise a real permitted public dataset/document and record provenance; use controlled provider output when a live request is not authorized or cannot fit the budget.

With GPT 1, use two separate browser contexts to prove automatic connection, private workspace/file separation, reload/reopen behavior, and absence of a public token prompt. A browser session must not discover another session's files by guessed IDs. Keep existing manual scientific acceptance and native replay passing.

Deliver commits, a PR, concise setup/rehearsal instructions, exact tests and their results, and a clear list of live versus controlled checks. Integrate the other owners' agreed interfaces and rerun the combined browser acceptance before declaring completion. Do not claim universal mathematical verification or a sponsor qualification that was not actually tested.

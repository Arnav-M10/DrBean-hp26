# Claude execution prompt — General files and Gemini research analysis

You are responsible for implementing the general file and Gemini analysis backend for **Dr. Bean** in **https://github.com/Arnav-M10/DrBean-hp26**. Implement and test the work; do not stop at recommendations. The user wants to upload their own research data and papers, use one server-owned Gemini key, and receive useful analysis across supported formats. Examples are optional learning aids, not the product's capability boundary.

## Starting point and ownership

`main` at `3738724` passed GitHub CI. The Gemini image/explanation integration is already on main. Fetch current remote state before starting. Use a separate checkout/worktree and branch **`codex/general-gemini-files`** from current `origin/main`. Read these three prompts from **`codex/shared-access-handoff`** if they have not yet reached main. That branch also contains unfinished shared-access scaffolding; do not merge its single shared-demo identity as a general privacy solution.

You own new `general_research` backend modules for generic asset admission, local parsing, citations, response schemas, persistence, Gemini transport and analysis routes, plus their tests. You may make narrowly necessary upload-admission changes in `apps/api/bean_api/http.py`. You own `ledger.py` changes only if necessary for explicit, audit-preserving configurable budget grants. Do not activate a larger budget or erase accounting history.

GPT1 owns `main.py` registration, auth/browser sessions, gateway, launcher and worker integration. The teammate GPT owns the general browser workflow. Do not edit those owners' files or the scientific engine. Provide **`register_general_routes(app)`** and a capability helper; give GPT1 the exact registration and state dependencies. Test route registration in a fixture, then require a test against the actual assembled app before declaring the feature integrated. Coordinate small shared-provider changes explicitly; preserve existing image and explanation behavior.

## Capability and truthfulness

Accept supported CSV, TSV, JSON, TXT, Markdown, PNG, JPEG and PDF inputs. Preserve arbitrary column names, units, experimental context and source provenance. Do not force every table into `time, concentration, epsilon`. Real observations, hypothetical inputs and synthetic examples must retain distinct origin declarations.

General Gemini analysis is useful interpretation, not mathematical certification. The existing checker supports one concentration model. Return general analysis for other subjects with **`not_mathematically_verified`** status. A source citation establishes where text came from; it does not establish scientific correctness. Keep any actual checker result as a separate identity-bound record. Do not manufacture verified badges, model compatibility, parameter bounds or “true model” conclusions.

## Shared API contract

Use prefix **`/api/bean/v1`**, existing workspace authorization and standard error envelopes.

1. **`POST /workspaces/{workspace_id}/research-assets`** accepts raw bytes with `Content-Type` and optional `X-Source-Name`. Return `id`, `sha256`, `media_type`, `byte_size`, `filename`, `pages` and `provenance`. Each page contains `page_index` (zero-based), `page_number` (one-based), `width`, `height`, `image_sha256` and `text_sha256`; unavailable values are explicitly null. **`GET /research-assets/{id}`** retrieves authorized retained metadata. Document an authorized byte/preview retrieval route if the browser needs it.
2. **`POST /workspaces/{workspace_id}/research-analyses`** accepts `client_operation_id`, `question`, `assets: [{id, sha256}]`, and `consent: {accepted, provider: "gemini", model, asset_ids, include_question: true}`. Require **`Idempotency-Key = client_operation_id`**. Use a bounded synchronous POST returning 201 and a durable record rather than pretending unimplemented worker resume exists. **`GET /research-analyses/{id}`** reopens the retained result.
3. The result body contains `summary`, `extracted_tables`, `claims`, `limitations`, `clarifications`, `suggested_next_steps`, `citations`, `verification: {status: "not_mathematically_verified", supported_adapter: null | adapter_id}`, and `provider_attempt_id`. Define their precise typed shapes and publish them for the UI owner. Only server-owned integration may attach a separately checked mathematical record.

Every citation binds the source SHA, zero-based `page_index` and an exact source quote. Optional bounding boxes use normalized 0–1 coordinates, top-left origin, and an explicit `bbox_space`; never mix pixels, PDF points and normalized coordinates. Store enough raw text/span mapping to validate quotations after documented whitespace or equivalent µ/μ normalization. Fail ambiguous citations honestly rather than inventing coordinates.

## Admission and parsing requirements

Allow one to five assets per analysis, at most 5 MiB per file and 10 MiB combined. PDFs have at most ten pages. Detect actual media types, malformed/encrypted PDFs, decompression hazards, excessive page dimensions and nesting. Rendering needs bounded decoded pixels, resolution, time and effective memory protection on macOS as well as Linux. A timeout alone does not cap memory. Refuse excessive work explicitly; never silently truncate pages or rows and claim the whole file was analyzed.

Keep original bytes and a content digest immutable. Treat filenames, PDF metadata, page text and embedded instructions as untrusted data. Never execute uploaded code, macros, shell commands or instructions. Use safe digest-based storage names. Preserve empty values and unresolved units; distinguish an asserted hard bound from SD, SE or a confidence interval. Statistical quantities elsewhere on a page must not invalidate a correctly associated field.

Review PRs **#35 and #36** for reusable code. Correct the reported citation-substring bug (`538` versus `5380`, `4.6` versus `4.62`), line-break/µ normalization failures, unrelated-SD rejection, flattened superscript ambiguity, three incompatible page identities and macOS renderer memory growth before incorporating those paths. Require numeric-token boundaries and source association. An exponent printed ambiguously as `1.1 × 101` must trigger review instead of becoming an invented numeric value.

## Gemini and accounting

The owner supplies one private server key. No per-user key prompt, browser key, committed secret or key-bearing log is allowed. Preserve explicit live opt-in, selected-model allowlisting, separate source/question consent, one accounted request, bounded output/thinking, no automatic retries and no paid fallback. Use substituted transports for development tests.

The existing conversation guard allows only narrow evidence-bound templates; do not relax it into unrestricted scientific narration. Implement a separate typed general-analysis schema and prompt with clear source-grounding and uncertainty rules. All requested assets must match consent and immutable digests. Local preprocessing may extract bounded text and previews; a request that cannot fit the configured context must ask the user to select a smaller scope, not silently omit material.

The current live ledger has nearly exhausted its conservative input reservation. Preserve every historical attempt, including failures and unknown outcomes. Opening another workspace/session must not bypass the global cap. Preflight estimated reservations and return a clear exhaustion response. If configurable budget grants are implemented, require an explicit owner decision, preserve previous grants/usage, default to current limits, and leave activation to the owner. Free-tier configuration is an account assertion, not billing verification. Spend $0 and make no live calls merely to finish this prompt.

## Validation and completion

Test general tables outside pharmacokinetics, public text and scanned PDFs, malformed/oversized files, prompt injection, numeric citation attacks, page identity, missing units, stale digests, cross-workspace access, duplicate requests, cancellation/timeout accounting and budget refusal before dispatch. Reopening must reproduce stored output without another model call. Ensure extraction never mutates scientific inputs without review.

Run relevant backend tests, Ruff, contract checks and the repository secret scanner. Supply genuine generic fixtures with provenance and expected source values, plus exact UI request/response examples. Commit and push your branch, open a PR describing implemented behavior and validation, and provide GPT1 an integration checklist. Report controlled tests, real parsing, live Gemini and mathematical checking separately. “Done” requires working routes in the combined product, durable authorized records, complete declared-file coverage or explicit refusal, accurate citations, and no invented certification.

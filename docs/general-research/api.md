# General research files and analysis — API guide (`general-research.v1`)

For the general research UI. Exact JSON Schemas and recorded request/response pairs live in
`shared/contracts/general-research.v1/` (regenerate with `python -m bean_api.general_research.contract`).
Every route is under `/api/bean/v1`, uses the existing authentication, and returns the standard error
envelope `{code, message, field_paths, retryable, current_revision_id, request_id}`.

## The flow

1. **Upload** each file: `POST /workspaces/{workspace_id}/research-assets` with the raw bytes.
   Nothing is sent to Gemini by uploading.
2. **Show** what was admitted: `GET /research-assets/{id}`, page images
   `GET /research-assets/{id}/pages/{page_index}/image`, page text `GET .../pages/{page_index}/text`.
3. **Estimate** before asking for consent: `POST /workspaces/{workspace_id}/research-analysis-estimates`
   (no side effects). Show the model, availability, what will be sent and the remaining budget.
4. **Consent and analyze**: `POST /workspaces/{workspace_id}/research-analyses` with
   `Idempotency-Key` equal to `client_operation_id`. One bounded synchronous request; HTTP 201 with the
   durable record.
5. **Reopen**: `GET /research-analyses/{id}` or `GET /workspaces/{workspace_id}/research-analyses`.
   Reopening never calls a model.

## Upload

```
POST /api/bean/v1/workspaces/{workspace_id}/research-assets?origin=real_observation
Content-Type: text/csv                    (required; the declared type selects the text parser)
X-Source-Name: soil%20cores.csv           (optional; encodeURIComponent of the file name)
Idempotency-Key: upload-<uuid>            (optional; same key + same bytes returns the same asset)
<raw bytes>
```

Supported: `text/csv`, `text/tab-separated-values`, `application/json`, `text/plain`, `text/markdown`,
`image/png`, `image/jpeg`, `application/pdf` (common aliases such as `application/vnd.ms-excel` for CSV are
accepted). `origin` is the uploader's declaration and is stored as such (`origin_verified: false`):
`real_observation`, `public_source`, `synthetic_example`, `hypothetical`, or `unspecified` (default).

Limits (also in `GET /research-capabilities` → `limits`): 5 MiB per file; 1–5 files and 10 MiB per
analysis; PDFs at most 10 pages. Refusals are explicit, never silent truncation:

| code | status | meaning |
|---|---|---|
| `unsupported_media_type` | 415 | declared type not supported |
| `media_type_mismatch` | 415 | bytes are not the declared format (e.g. PNG sent as PDF, binary as CSV) |
| `request_too_large` / `file_too_large` | 413 | more than 5 MiB |
| `empty_file`, `empty_text`, `binary_content`, `text_encoding_unsupported` | 422 | unusable text |
| `malformed_table`, `table_row_limit`, `table_column_limit` | 422 | CSV/TSV problems |
| `malformed_json`, `json_nesting_limit`, `json_node_limit` | 422 | JSON problems |
| `encrypted_pdf`, `malformed_pdf`, `pdf_page_limit`, `pdf_decompression_limit`, `pdf_image_pixel_limit`, `pdf_nesting_limit`, `pdf_object_limit`, `pdf_page_dimension_limit`, `pdf_text_limit`, `unsupported_pdf_filter` | 422 | PDF refusals |
| `malformed_image`, `image_pixel_limit`, `animated_image_unsupported` | 422 | image refusals |
| `invalid_source_name`, `invalid_data_origin` | 422 | header/query problems |
| `worker_timeout`, `worker_memory_limit` | 422 | parsing exceeded its bounds |

### `ResearchAsset` (abridged; see `ResearchAsset.schema.json`)

- `id`, `sha256` (of the original bytes, immutable), `media_type` (detected), `byte_size`, `filename`
  (untrusted display text; never a path), `provenance` (declared origin, parser, encoding, upload time).
- `pages[]`: `page_index` (zero-based), `page_number` (one-based, for display), `width`/`height` with
  `dimension_unit` (`pt` for PDF pages after rotation, `px` for images, `null` for text files),
  `rotation`, `image_sha256` (the page image: rendered PNG for PDF pages, the original for images),
  `text_sha256`, `text_layer` (`native_pdf_text`, `decoded_text`, `none` for scans/images, `unreliable`).
- `content_summary` by `kind`:
  - `table` (CSV/TSV): column names exactly as written, `unit` only when the header prints it in
    brackets (`unit_status: stated_in_header`), otherwise `unresolved`; counts of numeric/text/empty/
    missing-marker/absent cells; first 20 rows (`""` = empty cell, `null` = cell absent in a short row);
    comment preamble, title line, RDB format row and ragged rows are reported.
  - `json`: top-level keys and detected record tables (`json_path`, columns, preview rows; numbers keep
    their source spelling).
  - `text`/`markdown`: line/char counts, Markdown headings.
  - `image`: size, displayed size after EXIF orientation, `preview_reason` when a ≤1600 px preview is used.
  - `pdf`: page count and pages without a usable text layer. No OCR is performed.
- `active_content_detected` (JavaScript, launch/URI actions, attachments, forms) with
  `active_content_policy: never_executed_or_followed`.

`GET /research-assets/{id}/content` returns the original bytes (images inline, everything else as a
download, `X-Artifact-SHA256`, `Content-Security-Policy: sandbox`). Render text from the `.../text` route,
never from raw bytes, and escape everything.

## Estimate (no side effects)

```json
POST /api/bean/v1/workspaces/{workspace_id}/research-analysis-estimates
{"question": "...", "assets": [{"id": "...", "sha256": "...", "page_indices": [1, 2]}]}
```

Returns `available`, `unavailable_reason`, `execution_mode` (`live` | `controlled` | `disabled`), `model`,
`estimated_input_tokens`, `reserved_output_tokens`, `max_input_tokens`, `fits_context`, `fits_budget`
(`null` when the controlled mode spends nothing), `budget` (remaining requests/input/output tokens of the
**shared** application ledger, `billing_verified: false`), `pages_sent` per asset (what would be sent as
text or as an image), and `blocking_reasons`. `page_indices` is optional and only for PDFs.

The estimate is deliberately conservative: one token per UTF-8 byte of prompt text plus 8,192 tokens per
image or scanned page (the server's configured image bound). With the current 24,000-token request limit,
one request holds roughly 14–16 KB of text, or one image plus some text, or two images with very little
text. When `fits_context` is false, ask the person to select fewer files or pages: the server never omits
material silently.

## Analyze

```json
POST /api/bean/v1/workspaces/{workspace_id}/research-analyses
Idempotency-Key: analysis-<uuid>
{
  "client_operation_id": "analysis-<uuid>",
  "question": "How did the annual mean change?",
  "assets": [{"id": "research_asset_...", "sha256": "...", "page_indices": null}],
  "consent": {"accepted": true, "provider": "gemini", "model": "<model from capabilities>",
              "asset_ids": ["research_asset_..."], "include_question": true}
}
```

Before anything is sent the server checks: header equals `client_operation_id`; consent accepted, covers
exactly the selected files and includes the question; the model equals the configured model; every
`sha256` still matches the retained bytes (`asset_digest_mismatch` 409 otherwise); the material fits one
request (`analysis_context_exceeded` 413); the shared budget admits it (`provider_budget_exhausted` 409);
analysis is available (`general_analysis_unavailable` 503). None of these creates a record or spends
budget.

Retrying with the **same** key and body returns the same record without another model call (or
`operation_pending` 409, retryable, while it is still running). The same key with a different body is
`idempotency_conflict` 409. Changing the question or files needs a new `client_operation_id` and fresh
consent. There are no automatic retries.

### `ResearchAnalysis`

- `status`: `completed`, `failed` (e.g. `provider_refused`, `provider_malformed_output`,
  `provider_output_truncated`) or `unknown_outcome` (timeout, cancellation, interruption: the request may
  have been processed; it stays counted and is never retried automatically). `failure: {code, message}`.
- `label`: show it verbatim. Live: “AI analysis — not mathematically verified”. Controlled:
  “Controlled test response — not Gemini output, not mathematically verified”.
- `execution_mode`, `provider`, `model`, `provider_attempt_id`, `reservation`.
- `assets[]`: what was sent: `label` (S1–S5), `pages_sent[]` with `sent_as` `text`/`image` and digests.
- `summary`, `limitations[]` (model limitations plus server notes, e.g. figures on text pages not sent,
  no local OCR, verification wording), `clarifications[]`, `suggested_next_steps[]`.
- `citations[]`: `id`, `source_label`, `asset_id`, `source_sha256`, `page_index`, `page_number`, `quote`,
  `status`, `bbox` + `bbox_space`, `match` (offsets in the page text + `text_sha256`), `normalizations`,
  `flags` (`possible_flattened_exponent`, `statistical_qualifier_in_quote`), `found_on_page_indices`.
  Statuses: `verified` (exactly one admissible occurrence on that page), `ambiguous`, `partial_token_match`
  (e.g. `538` inside `5380`), `not_found`, `wrong_page`, `unverifiable_no_text_layer` (scans, images),
  `unverifiable_text_layer`, `invalid_source`, `invalid_page`, `page_not_sent`, `quote_too_short`,
  `quote_too_long`, `duplicate_id`. A verified citation shows where words occur, not that the
  interpretation is right.
- `claims[]`: `support` = `supported` | `partially_supported` | `unsupported` | `unverifiable` |
  `uncited`; `unsupported_numbers` (numbers not found in the claim's verified quotes); `flags`
  (`possible_flattened_exponent`, `hard_bound_conflicts_with_statistical_qualifier`,
  `verification_language_not_a_verification`, `unknown_citation_id`).
- `extracted_tables[]`: cells exactly as the model copied them (`review_status: unreviewed`), column
  `unit_status` (`printed_in_source`, `not_found_in_source`, `unverifiable`, `not_stated`), and
  `cell_checks` (`unsupported_cells` and `ambiguous_exponent_cells` as `[row, column]`). CSV/TSV cells are
  checked against the parsed file, PDF cells against the page text.
- `verification: {status: "not_mathematically_verified", supported_adapter, reason, checked_record_id: null}`.
  `supported_adapter` is `two_rate_concentration` only when a selected table states hours and mg/L; it
  means the existing checker *could be offered* after the existing explicit review and plan approval.
  Checked results are separate records; an analysis never creates or changes datasets, problems or plans.

### Coordinates and pages

`page_index` is zero-based everywhere in data; show `page_number`. `bbox` is `[x0, y0, x1, y1]`
normalized to 0–1 from the **top-left** of the displayed page (after PDF rotation), with
`bbox_space: "page_normalized_top_left"`. Multiply by the page image's pixel size to draw. `bbox` is null
when no character boxes exist (text files, images, scans, unverified quotes); never draw an invented box.

### Quote normalization (`citation-normalization.v1`)

Whitespace runs (including line breaks) are one space; µ (U+00B5) equals μ (U+03BC); hyphen, en dash and
minus are the same; curly quotes are straight; ligatures are expanded; soft hyphens are removed. A hyphen
at a line break between letters may be removed (`dehyphenation` is reported). No case folding. A quote
may not begin or end inside a number or word, and may not drop a minus sign.

## Capabilities

`GET /api/bean/v1/research-capabilities` (authenticated) returns the block that the application also
places under `general_research` in `/capabilities` once integrated: `routes_registered`,
`upload_available`, `available`, `unavailable_reason`, `analysis` (mode, model, accounting, free-tier
assertion, `billing_verified: false`, `live_qualification`), `budget`, `limits`, `media_types`,
`citations` conventions and parser isolation.

## Development without Gemini

`BEAN_GENERAL_ANALYSIS_MODE=controlled_demo` (only when the server is not in live mode) answers with a
deterministic local responder that restates the first line of each text source and the first table rows
with exact quotes. It uses model name `controlled-general-analysis`, records attempts outside the shared
ledger and labels every record as a controlled response. Use it for UI and browser tests only.

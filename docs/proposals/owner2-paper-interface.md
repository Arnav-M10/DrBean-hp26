# Paper (PDF) interface request: Owner 4 → Owner 2

Status: **proposed, not merged.** Owner 2 owns `main.py`, `http.py`, `contracts.py`, `intake.py`, materialization, migrations, `pyproject.toml` and `uv.lock`. Nothing in this request has been applied to those files by Owner 4. The complete diff is `owner2-paper-routes.patch` beside this file.

## What Owner 4 delivers (owned, committed)

- `apps/api/bean_api/papers/`: `limits.py` (application limits), `_pdf_worker.py` (separate bounded process), `admission.py` (`inspect_paper`, `render_page`, `select_pages`, `PaperError`), `citations.py` (`match_quotation`, `validate_citation`, `render_box`), `service.py` (`PaperService`, reference storage using only existing `Workflow` record/operation primitives).
- Tests: `tests/test_papers_admission.py` (25), `tests/test_papers_service.py` (7), `tests/test_papers_http.py` (4, skip until the routes exist).
- Fixtures: `fixtures/papers/` with `manifest.json`.

## 1. Dependencies to pin (Owner 2)

| Package | Version tested | License | Use |
|---|---|---|---|
| pypdf | 7.1.0 | BSD-3-Clause | structure validation, encryption detection, native text, page labels, page subsets |
| pypdfium2 | 5.15.2 (PDFium 159.0.8149.0) | BSD-3-Clause / Apache-2.0 | page rendering; forms are never initialised, so no document JavaScript runs |

PyMuPDF was rejected (AGPL). Neither package executes document scripts, attachments, links or launch actions as used here. After adding them to `pyproject.toml`, run `uv lock`; the paper tests skip until then.

## 2. Limits (application choices, not provider limits)

20 MiB per paper; 50 physical pages; 8 selected pages per model batch; 20,000 text characters per page and 400,000 per paper; 4 MP per rendered preview, scale at most 3 px/pt. Worker: 25 s CPU and 768 MiB address space for inspection (Linux), 30 s wall, 24 MiB output, environment `{PATH, LANG}` only, own process session. Measured once on the four fixtures (Linux x86_64, this container, warm disk): inspection 0.15–0.24 s, one preview 0.21–0.32 s per call, including process start.

`RequestBoundary` needs a separate paper cap (the patch adds `max_paper_bytes`, applied only to `Content-Type: application/pdf`) so the 5 MiB image cap is unchanged and the body still stops buffering at the cap.

## 3. Records (reuse existing primitives; no migration)

| Kind | Parent | Body (public fields) | Identity |
|---|---|---|---|
| `paper_source` | none | `sha256`, `byte_size`, `media_type`, `origin` (synthetic/public), `retention` (retain), `filename` (sanitised), `upload_actor_id`, `manifest`, `page_text_sha256`, `model_processing: "none…"` | original bytes digest; manifest has its own `manifest_sha256` |
| `paper_page_selection` | the paper | `paper_id`, `pages`, `source_sha256`, `manifest_sha256`, `subset_sha256`, `subset_byte_size`, `mapping[{subset_page, physical_page, printed_label, text_sha256}]`, `selection_sha256`, `coverage_note` | derived subset digest, separate from the original |

Private blob names (`blob_key`, `text_blob_key`, `subset_blob_key`) never leave `PaperService.public_record`. Physical page numbers and printed labels (`i`, `S3`) are separate fields.

**Provider disclosure must bind `selection_sha256`** (which itself binds source digest, manifest digest, subset digest and page mapping), not only the original source identity. A later batch inside the same disclosed page set reuses consent and budget; any new page requires a new selection and an updated disclosure before dispatch.

## 4. Routes (in the patch)

| Method and path | Purpose |
|---|---|
| `POST /workspaces/{w}/papers?origin=&retention=retain&filename=` | raw `application/pdf` body; idempotent by key; never contacts a provider |
| `GET /workspaces/{w}/papers` | list retained papers (for reopening) |
| `GET /papers/{id}` | public record with manifest |
| `GET /papers/{id}/content` | original bytes, attachment disposition, `X-Artifact-SHA256` |
| `GET /papers/{id}/pages/{n}/text` | native text of one physical page, with its digest and warnings |
| `GET /papers/{id}/pages/{n}/preview?scale=` | rendered PNG (derived, sanitised), `X-Artifact-SHA256`, `X-Preview-Scale` |
| `POST /papers/{id}/page-selections` `{"pages":[…]}` | derived selected-page PDF record, idempotent by key |
| `GET /paper-page-selections/{id}/content` | derived PDF bytes |
| `POST /papers/{id}/citation-checks` `{"page","excerpt","box"?}` | text occurrence / wrong page / not found / no text layer, plus box problems |

Capabilities gain `paper_intake` (limits, parser/renderer, `executes_document_scripts: false`, `model_extraction`). Every route is workspace-authorized by `Workflow.get`; `test_papers_http.py` checks a second workspace gets 404 everywhere.

Verified on a scratch integration copy (`main` at `cbfa5ef` + this branch + the patch): the 4 HTTP tests pass and the full backend suite passes (655 passed).

## 5. Still needed from Owner 2 (and Owner 3) for model-assisted paper review

These are **not** in the patch and Owner 4 has not implemented them:

1. **Paper proposal contract.** `SourceLocator.page` is fixed to 1 and `IntakeField.source_asset_id` must be a `source_asset`. A paper proposal needs `paper_id`, `selection_id`, physical `page` (1–50), optional `box` in the manifest's PDF-point convention, `excerpt`, `method` (`gemini_document`, `controlled_fixture`, `manual`), and statement kinds beyond table values (claim quotation, methods passage, conflicting evidence, missing field). Validation should call `bean_api.papers.validate_citation` and `match_quotation` and store their results beside each field; a model's box is a proposal.
2. **Review and materialization from a paper review**, mirroring `intake-reviews/{id}/materialize`, so accepted paper values become exact inputs with paper/page provenance. Until then the browser offers page-cited **manual** entry into the ordinary dataset route (provenance in row notes), which keeps authority unchanged.
3. **`research_session_id`** and the shared ledger ceilings (12 model requests per action, 24 per session; auxiliary 16/32) for extraction batches.
4. Owner 3: extraction prompt and transport consuming `GET /paper-page-selections/{id}/content` bytes through the shared gateway.

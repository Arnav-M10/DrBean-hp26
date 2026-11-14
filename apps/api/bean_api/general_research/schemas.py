"""Typed shapes of the general research contract (``general-research.v1``).

Three groups:
  * requests the browser sends (strict, unknown fields rejected);
  * ``ModelAnalysisOutput``, the only shape Gemini may return (validated locally);
  * the records the server returns. The model never supplies identifiers, digests,
    verification status, coordinates or review state: the server derives them.
"""
from __future__ import annotations

import re
from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, Field

from . import limits as L

SHA256 = re.compile(r"[a-f0-9]{64}")
IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}")


def _sha256(value: str) -> str:
    if not SHA256.fullmatch(value):
        raise ValueError("Expected a lowercase hexadecimal SHA-256 digest")
    return value


def _identifier(value: str) -> str:
    if not IDENTIFIER.fullmatch(value):
        raise ValueError("Expected a server identifier")
    return value


def _operation_key(value: str) -> str:
    if not 1 <= len(value) <= 128 or not all(32 < ord(ch) < 127 for ch in value):
        raise ValueError("Use a nonempty printable operation identifier of at most 128 characters")
    return value


Sha256 = Annotated[str, AfterValidator(_sha256)]
Identifier = Annotated[str, AfterValidator(_identifier)]


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


# --------------------------------------------------------------------------- requests
class AnalysisAssetRef(Strict):
    id: Identifier
    sha256: Sha256
    page_indices: list[Annotated[int, Field(ge=0, le=L.MAX_PDF_PAGES - 1)]] | None = Field(
        default=None, max_length=L.MAX_PDF_PAGES,
        description="Optional zero-based pages to analyze (PDF). Omitted means every page.")


class AnalysisConsent(Strict):
    accepted: bool
    provider: Literal["gemini"]
    model: Annotated[str, Field(min_length=1, max_length=80)]
    asset_ids: list[Identifier] = Field(min_length=L.MIN_ANALYSIS_ASSETS, max_length=L.MAX_ANALYSIS_ASSETS)
    include_question: bool


class ResearchAnalysisRequest(Strict):
    client_operation_id: Annotated[str, AfterValidator(_operation_key)]
    question: Annotated[str, Field(min_length=1, max_length=L.MAX_QUESTION_CHARS)]
    assets: list[AnalysisAssetRef] = Field(min_length=L.MIN_ANALYSIS_ASSETS, max_length=L.MAX_ANALYSIS_ASSETS)
    consent: AnalysisConsent


class AnalysisEstimateRequest(Strict):
    question: Annotated[str, Field(min_length=1, max_length=L.MAX_QUESTION_CHARS)]
    assets: list[AnalysisAssetRef] = Field(min_length=L.MIN_ANALYSIS_ASSETS, max_length=L.MAX_ANALYSIS_ASSETS)


# --------------------------------------------------------------------------- model output (Gemini)
SourceLabel = Literal["S1", "S2", "S3", "S4", "S5"]
Text = Annotated[str, Field(max_length=600)]


class ModelCitation(Strict):
    id: Annotated[str, Field(min_length=1, max_length=8, description="C1, C2, ... unique in this response")]
    source: SourceLabel
    page_index: Annotated[int, Field(ge=0, le=L.MAX_PDF_PAGES - 1, description="Zero-based page index")]
    quote: Annotated[str, Field(min_length=1, max_length=500, description="Exact words copied from that page")]


class ModelColumn(Strict):
    name: Annotated[str, Field(min_length=1, max_length=200, description="Column name exactly as printed")]
    unit: Annotated[str, Field(max_length=40)] | None = Field(
        description="Unit exactly as printed in the source; null when the source does not print it")


class ModelTable(Strict):
    title: Annotated[str, Field(max_length=200)]
    source: SourceLabel
    page_index: Annotated[int, Field(ge=0, le=L.MAX_PDF_PAGES - 1)]
    columns: list[ModelColumn] = Field(min_length=1, max_length=24)
    rows: list[Annotated[list[Annotated[str, Field(max_length=120)] | None], Field(max_length=24)]] = Field(
        max_length=40, description="Cells exactly as printed; null for an empty cell")
    citation_ids: list[Annotated[str, Field(max_length=8)]] = Field(max_length=6)
    notes: Annotated[str, Field(max_length=500)] | None


class ModelClaim(Strict):
    text: Annotated[str, Field(min_length=1, max_length=600)]
    kind: Literal["observation", "interpretation", "hypothesis", "method", "comparison"]
    uncertainty: Literal["not_stated", "sd", "se", "ci", "range", "hard_bound", "other"]
    citation_ids: list[Annotated[str, Field(max_length=8)]] = Field(max_length=4)


class ModelClarification(Strict):
    question: Annotated[str, Field(min_length=1, max_length=300)]
    reason: Annotated[str, Field(max_length=300)]
    citation_ids: list[Annotated[str, Field(max_length=8)]] = Field(max_length=4)


class ModelNextStep(Strict):
    text: Annotated[str, Field(min_length=1, max_length=300)]
    rationale: Annotated[str, Field(max_length=300)]
    kind: Literal["collect_data", "review_extracted_values", "check_units", "consult_source",
                  "mathematical_check_candidate", "other"]
    citation_ids: list[Annotated[str, Field(max_length=8)]] = Field(max_length=4)


class ModelAnalysisOutput(Strict):
    summary: Annotated[str, Field(min_length=1, max_length=2000)]
    extracted_tables: list[ModelTable] = Field(max_length=4)
    claims: list[ModelClaim] = Field(max_length=12)
    limitations: list[Annotated[str, Field(max_length=400)]] = Field(max_length=8)
    clarifications: list[ModelClarification] = Field(max_length=6)
    suggested_next_steps: list[ModelNextStep] = Field(max_length=6)
    citations: list[ModelCitation] = Field(max_length=30)


# --------------------------------------------------------------------------- published records
DataOrigin = Literal["real_observation", "public_source", "synthetic_example", "hypothetical", "unspecified"]


class ParserInfo(Strict):
    name: str
    version: str


class Provenance(Strict):
    data_origin: DataOrigin
    origin_declared_by: Literal["uploader", "not_declared"]
    origin_verified: Literal[False]
    source_name_supplied: bool
    declared_media_type: str
    detected_media_type: str
    media_type_detection: Literal["declared", "content_signature", "filename_extension_hint", "content_sniff"]
    text_encoding: str | None
    parser: ParserInfo
    uploaded_at: str
    note: str


class PageDescriptor(Strict):
    page_index: int
    page_number: int
    width: float | None
    height: float | None
    dimension_unit: Literal["pt", "px"] | None
    rotation: Literal[0, 90, 180, 270] | None
    image_sha256: Sha256 | None
    image_media_type: Literal["image/png", "image/jpeg"] | None
    image_width: int | None
    image_height: int | None
    text_sha256: Sha256 | None
    text_layer: Literal["native_pdf_text", "decoded_text", "none", "unreliable"]
    char_count: int
    text_preview: str | None = Field(description="First characters of the page text (bounded); the full text is "
                                                 "at /research-assets/{id}/pages/{page_index}/text")


class ColumnSummary(Strict):
    index: int
    name: str
    unit: str | None
    unit_status: Literal["stated_in_header", "unresolved"]
    kind: Literal["numeric", "text", "mixed", "empty"]
    numeric_cells: int
    text_cells: int
    empty_cells: int
    missing_marker_cells: int
    absent_cells: int
    min_as_written: str | None
    max_as_written: str | None


class TableRowPreview(Strict):
    line: int | None = None
    index: int | None = None
    cells: list[str | None]


class TableSummary(Strict):
    kind: Literal["table"]
    delimiter: str
    comment_lines: int
    comment_preview: list[str]
    title_lines: list[str]
    format_row_line: int | None
    header_line: int
    row_count: int
    column_count: int
    blank_lines: int
    decimal_comma_candidate: bool
    columns: list[ColumnSummary]
    preview_rows: list[TableRowPreview]
    ragged_row_lines: list[int]
    ragged_row_count: int
    extra_cells: int
    warnings: list[str]


class JsonTable(Strict):
    json_path: str
    row_count: int
    column_count: int
    columns: list[ColumnSummary]
    preview_rows: list[TableRowPreview]


class JsonSummary(Strict):
    kind: Literal["json"]
    top_level: Literal["object", "array", "string", "number", "literal"]
    top_level_keys: list[str]
    max_depth: int
    value_count_estimate: int
    duplicate_keys: list[str]
    tables: list[JsonTable]
    warnings: list[str]


class Heading(Strict):
    level: int
    text: str


class TextSummary(Strict):
    kind: Literal["text", "markdown"]
    line_count: int
    char_count: int
    headings: list[Heading]
    warnings: list[str]


class ImageSummary(Strict):
    kind: Literal["image"]
    width: int
    height: int
    display_width: int
    display_height: int
    exif_orientation: int
    mode: str
    preview_reason: str | None
    ocr: Literal[False]


class PdfSummary(Strict):
    kind: Literal["pdf"]
    page_count: int
    pages_with_text_layer: int
    pages_without_text_layer: list[int]
    ocr: Literal[False]
    executes_document_scripts: Literal[False]


class TablePreview(Strict):
    source: Literal["delimited", "json"]
    json_path: str | None
    columns: list[str]
    rows: list[list[str | None]]
    row_count: int


class ResearchAsset(Strict):
    id: str
    workspace_id: str
    contract_version: Literal["general-research.v1"]
    sha256: Sha256
    media_type: Literal["text/csv", "text/tab-separated-values", "application/json", "text/plain",
                        "text/markdown", "image/png", "image/jpeg", "application/pdf"]
    byte_size: int
    filename: str | None
    pages: list[PageDescriptor]
    provenance: Provenance
    content_summary: Annotated[TableSummary | JsonSummary | TextSummary | ImageSummary | PdfSummary,
                               Field(discriminator="kind")]
    tables: list[TablePreview]
    active_content_detected: list[str]
    active_content_policy: Literal["never_executed_or_followed"]
    warnings: list[str]
    created_at: str


class PageText(Strict):
    asset_id: str
    sha256: Sha256
    page_index: int
    page_number: int
    text: str
    text_sha256: Sha256
    text_layer: Literal["native_pdf_text", "decoded_text"]
    normalization_for_citations: str


class SentPage(Strict):
    page_index: int
    sent_as: Literal["text", "image"]
    text_sha256: Sha256 | None
    image_sha256: Sha256 | None


class AnalysisAssetSnapshot(Strict):
    id: str
    sha256: Sha256
    label: SourceLabel
    filename: str | None
    media_type: str
    data_origin: DataOrigin
    page_count: int
    pages_sent: list[SentPage]


class ConsentSnapshot(Strict):
    accepted: Literal[True]
    provider: Literal["gemini"]
    model: str
    asset_ids: list[str]
    include_question: Literal[True]
    consent_record_id: str


class CitationMatch(Strict):
    start: int
    end: int
    text_sha256: Sha256


class Citation(Strict):
    id: str
    source_label: str
    asset_id: str | None
    source_sha256: Sha256 | None
    page_index: int
    page_number: int
    quote: str
    status: Literal["verified", "ambiguous", "partial_token_match", "not_found", "wrong_page",
                    "unverifiable_no_text_layer", "unverifiable_text_layer", "invalid_source", "invalid_page",
                    "page_not_sent", "quote_too_short", "quote_too_long", "duplicate_id"]
    bbox: list[float] | None
    bbox_space: Literal["normalized_top_left"] | None
    match: CitationMatch | None
    normalizations: list[str]
    flags: list[str]
    found_on_page_indices: list[int]


class TableColumn(Strict):
    name: str
    unit: str | None
    unit_status: Literal["printed_in_source", "not_found_in_source", "unverifiable", "not_stated",
                         "added_for_unlabelled_cells"]


class CellChecks(Strict):
    checked_against_text_layer: bool
    unsupported_cells: list[list[int]]
    ambiguous_exponent_cells: list[list[int]]


class ExtractedTable(Strict):
    id: str
    title: str
    source_label: str
    asset_id: str | None
    source_sha256: Sha256 | None
    page_index: int
    page_number: int
    columns: list[str] = Field(description="Column names exactly as the model copied them")
    column_details: list[TableColumn]
    rows: list[list[str | None]] = Field(description="Every row has one cell per column; null is an empty cell")
    citation_ids: list[str]
    rejected_citation_ids: list[str]
    notes: str | None
    review_status: Literal["unreviewed"]
    cell_checks: CellChecks
    flags: list[str]


class Claim(Strict):
    id: str
    text: str
    kind: str
    uncertainty: str
    citation_ids: list[str]
    rejected_citation_ids: list[str]
    support: Literal["supported", "partially_supported", "unsupported", "unverifiable", "uncited"]
    unsupported_numbers: list[str]
    flags: list[str]


class Clarification(Strict):
    id: str
    question: str
    reason: str
    citation_ids: list[str]
    rejected_citation_ids: list[str]


class NextStep(Strict):
    id: str
    text: str
    rationale: str
    kind: str
    citation_ids: list[str]
    rejected_citation_ids: list[str]


class Verification(Strict):
    status: Literal["not_mathematically_verified"]
    supported_adapter: Literal["two_rate_concentration"] | None
    reason: str
    checked_record_id: None = None


class CitationSummary(Strict):
    total: int
    verified: int
    ambiguous: int
    unverifiable: int
    rejected: int


class Reservation(Strict):
    input_tokens: int
    output_tokens: int


class Failure(Strict):
    code: str
    message: str


class ResearchAnalysisBody(Strict):
    contract_version: Literal["general-research.v1"]
    client_operation_id: str
    status: Literal["completed", "failed", "unknown_outcome"]
    label: str
    execution_mode: Literal["live", "controlled"]
    provider: Literal["gemini", "controlled"]
    model: str
    question: str
    assets: list[AnalysisAssetSnapshot]
    consent: ConsentSnapshot
    summary: str | None
    extracted_tables: list[ExtractedTable]
    claims: list[Claim]
    limitations: list[str]
    clarifications: list[Clarification]
    suggested_next_steps: list[NextStep]
    citations: list[Citation] = Field(description="Citations bound to a selected file and an existing page")
    rejected_citations: list[Citation] = Field(description="Citations naming no selected file or a missing page")
    citation_summary: CitationSummary
    verification: Verification
    provider_attempt_id: str | None
    prompt_version: str
    output_schema_version: str
    normalization_version: str
    reservation: Reservation
    flags: list[str]
    failure: Failure | None


class ResearchAnalysis(Strict):
    """The durable record envelope, like other workspace records: identity outside, content in ``body``."""
    id: str
    workspace_id: str
    kind: Literal["research_analysis"]
    digest: Sha256
    created_at: str
    body: ResearchAnalysisBody


class BudgetView(Strict):
    accounting: Literal["shared_global_ledger", "controlled_zero_spend"]
    remaining_requests: int | None
    remaining_input_tokens: int | None
    remaining_output_tokens: int | None
    billing_verified: Literal[False]


class AnalysisEstimate(Strict):
    available: bool
    unavailable_reason: str | None
    execution_mode: Literal["live", "controlled", "disabled"]
    model: str | None
    estimated_input_tokens: int
    reserved_output_tokens: int
    max_input_tokens: int
    fits_context: bool
    fits_budget: bool | None
    budget: BudgetView
    pages_sent: dict[str, list[SentPage]]
    blocking_reasons: list[str]
    estimate_method: str


class AnalysisCapability(Strict):
    available: bool
    model: str | None
    reason: str | None
    execution_mode: Literal["live", "controlled", "disabled"]
    dispatch_enabled: bool
    unavailable_reason: str | None
    accounting: str
    free_tier_user_asserted: bool
    billing_verified: Literal[False]
    live_qualification: str
    max_input_tokens: int
    max_output_tokens: int
    retry_policy: Literal["none"]


class RemainingBudget(Strict):
    requests: int | None
    input_tokens: int | None
    output_tokens: int | None


class CapabilityBudget(Strict):
    accounting: Literal["shared_global_ledger", "controlled_zero_spend"]
    remaining: RemainingBudget
    remaining_requests: int | None
    remaining_input_tokens: int | None
    remaining_output_tokens: int | None
    billing_verified: Literal[False]


class GeneralResearchCapabilities(BaseModel):
    """The ``general_research`` block of ``/capabilities`` (also ``GET /research-capabilities``)."""
    model_config = ConfigDict(extra="allow")
    implemented: Literal[True]
    contract_version: str
    routes_registered: bool
    available: bool = Field(description="File admission is available (uploads never contact a provider)")
    upload_available: bool | None = None
    unavailable_reason: str | None = None
    media_types: list[str]
    max_assets: int
    max_file_bytes: int
    max_total_bytes: int
    max_pdf_pages: int
    analysis: AnalysisCapability | None = None
    budget: CapabilityBudget | None = None


PUBLIC_MODELS = {model.__name__: model for model in (
    ResearchAnalysisRequest, AnalysisEstimateRequest, ResearchAsset, PageText, ResearchAnalysis,
    AnalysisEstimate, ModelAnalysisOutput, GeneralResearchCapabilities)}

"""Durable research assets, estimates and one accounted, validated Gemini analysis per operation.

Records are immutable workspace entities. An analysis never creates or changes a
dataset, problem, plan or scientific result: mapping anything into the checked
concentration workflow requires that workflow's own review and approval. Every
analysis is labelled ``not_mathematically_verified``; a citation proves where text
occurs, never that an interpretation is right.
"""
from __future__ import annotations

import asyncio
import base64
from dataclasses import dataclass, field
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
from uuid import uuid4

from ..canonical import canonical_bytes
from ..ledger import LedgerBudgetExceeded
from ..providers import AttemptContext, ProviderFailure
from ..store import utc_now
from ..workflow import DomainError
from . import limits as L
from .admission import DATA_ORIGINS, Refusal, canonical_media_type, encode_text_layer, parse, source_name
from .citations import (
    PageText, contains_token, has_flattened_exponent, locate, normalize, numbers_in, separators_for,
    statistical_qualifiers, token_occurrences,
)
from .prompt import OUTPUT_SCHEMA_VERSION, PROMPT_VERSION, SYSTEM_INSTRUCTION, build_prompt
from .schemas import AnalysisEstimateRequest, ModelAnalysisOutput, ResearchAnalysisRequest
from .storage import BlobIntegrityError, BlobStore
from .transport import AnalysisEnvelope, AttemptTracker, GeneralAnalysisTransport

ASSET_KIND, ANALYSIS_KIND, CONSENT_KIND = "research_asset", "research_analysis", "research_analysis_consent"
LABELS = {"live": "AI analysis — not mathematically verified",
          "controlled": "Controlled test response — not Gemini output, not mathematically verified"}
SOURCE_LABELS = ("S1", "S2", "S3", "S4", "S5")
VERIFICATION_WORDS = re.compile(r"\b(?:mathematically (?:verified|proven|confirmed|checked)|certified|formally verified|"
                                r"proves? that|guaranteed)\b", re.I)
FAILURE_MESSAGES = {
    "provider_timeout_unknown_outcome": "The model request timed out. It may or may not have been processed; it "
                                        "was counted against the budget and is not retried automatically.",
    "provider_cancelled_unknown_outcome": "The request was cancelled while the model call was in flight; the outcome "
                                          "is unknown and the reservation is kept.",
    "provider_refused": "The model declined to answer this request.",
    "provider_output_truncated": "The model's answer exceeded its output bound and was discarded.",
    "provider_malformed_output": "The model's answer did not match the required structure and was discarded.",
    "provider_rate_limited": "The provider rate-limited the request. Start a new analysis later.",
    "analysis_interrupted_unknown_outcome": "The analysis was interrupted before it finished; its outcome is unknown.",
    "analysis_validation_failed": "The model answered, but the server could not validate the answer; nothing in it "
                                  "was accepted.",
}


def _error(code: str, message: str, status: int = 422, *, retryable: bool = False, paths=None) -> DomainError:
    return DomainError(code, message, status, field_paths=paths or [], retryable=retryable)


def _number(value):
    if value is None or isinstance(value, int):
        return value
    return float(value)


@dataclass
class Source:
    label: str
    record: dict
    pages_text: list[PageText]
    parts: list[dict] = field(default_factory=list)

    @property
    def body(self) -> dict:
        return self.record["body"]

    @property
    def separators(self) -> str:
        return separators_for(self.body["media_type"], self.body["content_summary"].get("delimiter"))

    def table_cells(self) -> set[str] | None:
        """Every cell of a delimited file, normalized, for exact cell checks (None for other sources)."""
        summary = self.body["content_summary"]
        if summary.get("kind") != "table":
            return None
        import csv
        import io
        lines = self.pages_text[0].text.splitlines()[summary["comment_lines"]:]
        reader = csv.reader(io.StringIO("\n".join(lines), newline=""), delimiter=summary["delimiter"])
        return {normalize(cell.strip())[0] for row in reader for cell in row}


@dataclass
class Plan:
    sources: list[Source]
    prompt: str
    images: list[tuple[str, str]]          # (digest, media type); bytes are loaded only for dispatch
    digests: list[str]
    input_tokens: int
    output_tokens: int
    limitations: list[str]
    supported_adapter: str | None


class GeneralResearchService:
    def __init__(self, workflow, blob_root: str | Path, transport: GeneralAnalysisTransport):
        self.workflow, self.transport = workflow, transport
        self.blobs = BlobStore(blob_root)

    # ================================================================== operations
    def _peek(self, actor: str, workspace_id: str, operation: str, key: str, body: dict) -> dict | None:
        with self.workflow.store.read() as conn:
            self.workflow.authorize(actor, workspace_id, conn)
            return self.workflow._operation(conn, actor, workspace_id, operation, key, body)

    # ================================================================== assets
    def admit(self, actor: str, workspace_id: str, raw: bytes, content_type: str | None, name_header: str | None,
              origin: str, key: str | None) -> dict:
        self.workflow.authorize(actor, workspace_id)
        try:
            declared, media_type = canonical_media_type(content_type)
            filename = source_name(name_header)
            if origin not in DATA_ORIGINS:
                raise Refusal("invalid_data_origin", "Declare the data origin as real_observation, public_source, "
                              "synthetic_example, hypothetical or unspecified.")
        except Refusal as exc:
            raise _error(exc.code, exc.message, exc.status) from None
        digest = hashlib.sha256(raw).hexdigest()
        request = {"sha256": digest, "byte_size": len(raw), "declared_media_type": declared, "filename": filename,
                   "data_origin": origin}
        key = key or f"auto-{uuid4().hex}"
        existing = self._peek(actor, workspace_id, "research-asset-upload", key, request)
        if existing:
            return self._replayed_asset(actor, existing)
        try:
            parsed = parse(raw, media_type)
        except Refusal as exc:
            raise _error(exc.code, exc.message, exc.status) from None
        operation = self.workflow.begin_operation(actor, workspace_id, "research-asset-upload", key, request)
        if not operation["created_new"]:
            return self._replayed_asset(actor, operation)
        try:
            self.blobs.put(raw)
            for content in parsed.blobs.values():
                self.blobs.put(content)
            layer_sha = self.blobs.put(canonical_bytes(encode_text_layer(digest, parsed.text_pages)))
            body = {"contract_version": L.CONTRACT_VERSION, "sha256": digest, "media_type": parsed.media_type,
                    "byte_size": len(raw), "filename": filename,
                    "provenance": {"data_origin": origin,
                                   "origin_declared_by": "not_declared" if origin == "unspecified" else "uploader",
                                   "origin_verified": False, "source_name_supplied": filename is not None,
                                   "declared_media_type": declared, "detected_media_type": parsed.media_type,
                                   "text_encoding": parsed.encoding, "parser": parsed.parser,
                                   "uploaded_at": utc_now(),
                                   "note": "The origin is the uploader's declaration; Dr. Bean does not verify it."},
                    "pages": parsed.pages, "content_summary": parsed.summary, "text_layer_sha256": layer_sha,
                    "preview_sha256": parsed.preview_sha256, "active_content_detected": parsed.active_content,
                    "warnings": sorted(set(parsed.warnings))}
            record = self.workflow.create_record(actor, workspace_id, ASSET_KIND, body, key,
                                                 operation="research-asset-record")
            self.workflow.finish_operation(actor, workspace_id, "research-asset-upload", key, {"asset_id": record["id"]})
            return self.public_asset(record)
        except BaseException:
            self.workflow.fail_operation(actor, workspace_id, "research-asset-upload", key, "asset_storage_failed")
            raise

    def _replayed_asset(self, actor: str, operation: dict) -> dict:
        if operation["state"] == "completed":
            return self.asset(actor, operation["response"]["asset_id"])
        if operation["state"] == "reserved":
            raise _error("operation_pending", "This upload is still being stored; retry the same request shortly.",
                         409, retryable=True)
        raise _error("operation_failed", "This upload failed earlier. Upload it again with a new operation key.", 409)

    @staticmethod
    def public_asset(record: dict) -> dict:
        body = record["body"]
        return {"id": record["id"], "workspace_id": record["workspace_id"], "contract_version": body["contract_version"],
                "sha256": body["sha256"], "media_type": body["media_type"], "byte_size": body["byte_size"],
                "filename": body["filename"],
                "pages": [{**page, "width": _number(page["width"]), "height": _number(page["height"])}
                          for page in body["pages"]],
                "provenance": body["provenance"], "content_summary": body["content_summary"],
                "active_content_detected": body["active_content_detected"],
                "active_content_policy": "never_executed_or_followed", "warnings": body["warnings"],
                "created_at": record["created_at"]}

    def asset(self, actor: str, asset_id: str) -> dict:
        return self.public_asset(self.workflow.get(actor, asset_id, ASSET_KIND))

    def list_assets(self, actor: str, workspace_id: str) -> list[dict]:
        return [self.public_asset(record) for record in self.workflow.list_records(actor, workspace_id, ASSET_KIND, 200)]

    def content(self, actor: str, asset_id: str) -> tuple[dict, bytes]:
        record = self.workflow.get(actor, asset_id, ASSET_KIND)
        try:
            return record, self.blobs.get(record["body"]["sha256"], record["body"]["byte_size"])
        except BlobIntegrityError:
            raise _error("asset_integrity_failed", "The retained file no longer matches its recorded digest.", 409) from None

    def _layer(self, record: dict) -> list[PageText]:
        try:
            layer = json.loads(self.blobs.get(record["body"]["text_layer_sha256"]))
        except (BlobIntegrityError, ValueError):
            raise _error("asset_integrity_failed", "The retained text layer no longer matches its digest.", 409) from None
        return [PageText(page["text"], base64.b64decode(page["char_boxes_b64"]) if page["char_boxes_b64"] else None,
                         page["quality"]) for page in layer["pages"]]

    def page_image(self, actor: str, asset_id: str, page_index: int) -> tuple[bytes, str]:
        record = self.workflow.get(actor, asset_id, ASSET_KIND)
        body = record["body"]
        if not 0 <= page_index < len(body["pages"]):
            raise _error("not_found", "Page was not found.", 404)
        page = body["pages"][page_index]
        digest = body.get("preview_sha256") or page["image_sha256"]
        if digest is None:
            raise _error("page_image_unavailable", "This file has no page image.", 404)
        try:
            content = self.blobs.get(digest)
        except BlobIntegrityError:
            raise _error("asset_integrity_failed", "The retained page image no longer matches its digest.", 409) from None
        return content, page["image_media_type"] or "image/png"

    def page_text(self, actor: str, asset_id: str, page_index: int) -> dict:
        record = self.workflow.get(actor, asset_id, ASSET_KIND)
        body = record["body"]
        if not 0 <= page_index < len(body["pages"]):
            raise _error("not_found", "Page was not found.", 404)
        page = body["pages"][page_index]
        if page["text_layer"] not in ("native_pdf_text", "decoded_text"):
            raise _error("page_text_unavailable", "This page has no usable text layer (for example a scan or an image).",
                         404)
        text = self._layer(record)[page_index].text
        return {"asset_id": record["id"], "sha256": body["sha256"], "page_index": page_index,
                "page_number": page_index + 1, "text": text, "text_sha256": page["text_sha256"],
                "text_layer": page["text_layer"], "normalization_for_citations": L.CITATION_NORMALIZATION_VERSION}

    # ================================================================== planning
    def _plan(self, actor: str, workspace_id: str, question: str, refs) -> Plan:
        if len({ref.id for ref in refs}) != len(refs):
            raise _error("duplicate_assets", "Select each file at most once.", paths=["assets"])
        sources, images, digests, total = [], [], [], 0
        limitations = set()
        for label, ref in zip(SOURCE_LABELS, refs):
            record = self.workflow.get(actor, ref.id, ASSET_KIND)
            if record["workspace_id"] != workspace_id:
                raise _error("not_found", "Workspace or record was not found.", 404)
            body = record["body"]
            if body["sha256"] != ref.sha256:
                raise _error("asset_digest_mismatch", "The selected file's digest does not match the retained file. "
                             "Reload the file list and select it again.", 409, paths=["assets"])
            try:
                self.blobs.get(body["sha256"], body["byte_size"])
            except BlobIntegrityError:
                raise _error("asset_integrity_failed", "The retained file no longer matches its recorded digest.",
                             409) from None
            total += body["byte_size"]
            pages_text = self._layer(record)
            page_count = len(body["pages"])
            if ref.page_indices is not None:
                if not ref.page_indices or len(set(ref.page_indices)) != len(ref.page_indices):
                    raise _error("invalid_page_selection", "Select each page at most once.", paths=["assets"])
                if any(index >= page_count for index in ref.page_indices):
                    raise _error("page_out_of_range", "A selected page does not exist in that file.", paths=["assets"])
                if body["media_type"] != "application/pdf" and ref.page_indices != [0]:
                    raise _error("page_selection_unsupported", "Only PDF files have selectable pages.", paths=["assets"])
            selected = sorted(ref.page_indices) if ref.page_indices is not None else list(range(page_count))
            source = Source(label, record, pages_text)
            for index in selected:
                page, layer = body["pages"][index], pages_text[index]
                if body["media_type"] in ("image/png", "image/jpeg"):
                    digest = body.get("preview_sha256") or body["sha256"]
                    mime = page["image_media_type"]
                elif layer.quality == "usable":
                    source.parts.append({"kind": "text", "page_index": index, "text": layer.text,
                                         "text_sha256": page["text_sha256"], "image_sha256": None})
                    if body["media_type"] == "application/pdf":
                        limitations.add("Figures and images on PDF pages that have a text layer were not sent as "
                                        "images; only their extracted text was analyzed.")
                    continue
                else:
                    digest, mime = page["image_sha256"], "image/png"
                images.append((digest, mime))
                digests.append(digest)
                source.parts.append({"kind": "image", "page_index": index, "image_number": len(images),
                                     "image_sha256": digest, "text_sha256": None})
                limitations.add("Text inside images and scanned pages was read by the model without local OCR; those "
                                "quotations cannot be checked against a text layer.")
                if body.get("preview_sha256"):
                    limitations.add("Images larger than 1600 pixels or rotated by EXIF metadata were sent as a "
                                    "declared derived preview.")
            sources.append(source)
        if total > L.MAX_ANALYSIS_BYTES:
            raise _error("analysis_byte_limit", f"Selected files total more than {L.MAX_ANALYSIS_BYTES // L.MiB} MiB. "
                         "Select fewer or smaller files.", 413, paths=["assets"])
        seed = hashlib.sha256((question + "".join(s.body["sha256"] for s in sources)).encode()).hexdigest()
        prompt, _ = build_prompt(question, [{"label": s.label, "filename": s.body["filename"],
                                             "media_type": s.body["media_type"],
                                             "data_origin": s.body["provenance"]["data_origin"],
                                             "page_count": len(s.body["pages"]), "parts": s.parts} for s in sources],
                                 seed)
        incoming, outgoing = self.transport.estimate(prompt, SYSTEM_INSTRUCTION, ModelAnalysisOutput, len(images))
        return Plan(sources, prompt, images, [s.body["sha256"] for s in sources] + digests, incoming, outgoing,
                    sorted(limitations), self._supported_adapter(sources))

    @staticmethod
    def _supported_adapter(sources: list[Source]) -> str | None:
        """A deterministic, local signal that the existing checker could be offered after review."""
        for source in sources:
            summary = source.body["content_summary"]
            tables = [summary] if summary.get("kind") == "table" else summary.get("tables", []) if summary.get(
                "kind") == "json" else []
            for table in tables:
                units = {column["unit"] for column in table["columns"] if column["unit_status"] == "stated_in_header"}
                if "h" in units and "mg/L" in units:
                    return "two_rate_concentration"
        return None

    def _budget(self) -> dict:
        diagnostics = getattr(self.transport.ledger, "diagnostics", None)
        if self.transport.mode != "live" or diagnostics is None:
            return {"accounting": "controlled_zero_spend" if self.transport.mode == "controlled"
                    else "shared_global_ledger", "remaining_requests": None, "remaining_input_tokens": None,
                    "remaining_output_tokens": None, "billing_verified": False}
        remaining = diagnostics()["remaining"]
        return {"accounting": "shared_global_ledger", "remaining_requests": remaining["requests"],
                "remaining_input_tokens": remaining["input_tokens"],
                "remaining_output_tokens": remaining["output_tokens"], "billing_verified": False}

    @staticmethod
    def _fits(budget: dict, plan: Plan) -> bool | None:
        if budget["remaining_requests"] is None:
            return None
        return (budget["remaining_requests"] >= 1 and budget["remaining_input_tokens"] >= plan.input_tokens
                and budget["remaining_output_tokens"] >= plan.output_tokens)

    @staticmethod
    def _pages_sent(source: Source) -> list[dict]:
        return [{"page_index": part["page_index"], "sent_as": part["kind"], "text_sha256": part["text_sha256"],
                 "image_sha256": part["image_sha256"]} for part in source.parts]

    def estimate(self, actor: str, workspace_id: str, request: AnalysisEstimateRequest) -> dict:
        self.workflow.authorize(actor, workspace_id)
        plan = self._plan(actor, workspace_id, request.question, request.assets)
        capabilities = self.transport.capabilities()
        budget = self._budget()
        fits_context = plan.input_tokens <= self.transport.config.max_input_tokens
        fits_budget = self._fits(budget, plan)
        blocking = []
        if not capabilities["dispatch_enabled"]:
            blocking.append(f"general_analysis_unavailable:{capabilities['unavailable_reason']}")
        if not fits_context:
            blocking.append("analysis_context_exceeded")
        if fits_budget is False:
            blocking.append("provider_budget_exhausted")
        return {"available": bool(capabilities["dispatch_enabled"]),
                "unavailable_reason": capabilities["unavailable_reason"],
                "execution_mode": capabilities["execution_mode"], "model": capabilities["model"],
                "estimated_input_tokens": plan.input_tokens, "reserved_output_tokens": plan.output_tokens,
                "max_input_tokens": self.transport.config.max_input_tokens, "fits_context": fits_context,
                "fits_budget": fits_budget, "budget": budget,
                "pages_sent": {source.record["id"]: self._pages_sent(source) for source in plan.sources},
                "blocking_reasons": blocking, "estimate_method": "utf8_bytes_plus_fixed_image_bound.v1"}

    # ================================================================== analysis
    def _check_consent(self, request: ResearchAnalysisRequest) -> None:
        consent = request.consent
        if consent.accepted is not True:
            raise _error("consent_required", "Accept the disclosure of the selected files and question first.",
                         paths=["consent.accepted"])
        if consent.include_question is not True:
            raise _error("question_consent_required", "The question is sent to Gemini; consent must include it.",
                         paths=["consent.include_question"])
        asset_ids = [ref.id for ref in request.assets]
        if len(set(consent.asset_ids)) != len(consent.asset_ids) or sorted(consent.asset_ids) != sorted(asset_ids):
            raise _error("consent_asset_mismatch", "Consent must name exactly the selected files.",
                         paths=["consent.asset_ids"])
        capabilities = self.transport.capabilities()
        if not capabilities["dispatch_enabled"]:
            raise _error("general_analysis_unavailable", "General analysis is not available on this server "
                         f"({capabilities['unavailable_reason']}). Nothing was sent.", 503)
        if consent.model != self.transport.model:
            raise _error("provider_model_mismatch", "The configured model changed. Review the disclosure again.", 409,
                         paths=["consent.model"])

    async def analyze(self, actor: str, workspace_id: str, request: ResearchAnalysisRequest, key: str) -> dict:
        if key != request.client_operation_id:
            raise _error("operation_key_mismatch", "The Idempotency-Key header must equal client_operation_id.")
        self.workflow.authorize(actor, workspace_id)
        body = request.model_dump(mode="json")
        existing = self._peek(actor, workspace_id, "research-analysis", key, body)
        if existing:
            return self._replayed_analysis(actor, workspace_id, existing, request)
        self._check_consent(request)
        plan = await asyncio.to_thread(self._plan, actor, workspace_id, request.question, request.assets)
        if plan.input_tokens > self.transport.config.max_input_tokens:
            raise _error("analysis_context_exceeded", f"The selected material needs about {plan.input_tokens:,} input "
                         f"tokens; one request admits {self.transport.config.max_input_tokens:,}. Select fewer files or "
                         "pages. Nothing was sent or omitted.", 413, paths=["assets"])
        budget = self._budget()
        if self._fits(budget, plan) is False:
            raise _error("provider_budget_exhausted", "The shared application budget cannot admit this analysis "
                         f"(needs about {plan.input_tokens:,} input and {plan.output_tokens:,} output tokens; remaining "
                         f"{budget['remaining_input_tokens']:,} and {budget['remaining_output_tokens']:,} with "
                         f"{budget['remaining_requests']} requests). Nothing was sent.", 409)
        try:
            images = tuple((self.blobs.get(digest), mime) for digest, mime in plan.images)
        except BlobIntegrityError:
            raise _error("asset_integrity_failed", "A retained page image no longer matches its digest.", 409) from None
        operation = self.workflow.begin_operation(actor, workspace_id, "research-analysis", key, body)
        if not operation["created_new"]:
            return self._replayed_analysis(actor, workspace_id, operation, request)
        consent = self.workflow.create_record(actor, workspace_id, CONSENT_KIND, {
            "contract_version": L.CONTRACT_VERSION, "client_operation_id": key, "provider": "gemini",
            "model": request.consent.model, "asset_ids": [ref.id for ref in request.assets],
            "asset_sha256": [ref.sha256 for ref in request.assets], "include_question": True,
            "question_sha256": hashlib.sha256(request.question.encode("utf-8")).hexdigest(),
            "pages_sent": {s.record["id"]: self._pages_sent(s) for s in plan.sources},
            "reserved_input_tokens": plan.input_tokens, "reserved_output_tokens": plan.output_tokens},
            key, operation="research-analysis-consent")
        tracker = AttemptTracker()
        envelope = AnalysisEnvelope(plan.prompt, SYSTEM_INSTRUCTION, ModelAnalysisOutput, images,
                                    tuple(dict.fromkeys(plan.digests)),
                                    tuple({"label": s.label, "media_type": s.body["media_type"],
                                           "filename": s.body["filename"], "parts": s.parts} for s in plan.sources))
        context = AttemptContext(actor, workspace_id, operation["id"], consent["id"], tuple(dict.fromkeys(plan.digests)))
        try:
            result = await self.transport.generate(envelope, context, tracker)
        except LedgerBudgetExceeded:
            self.workflow.fail_operation(actor, workspace_id, "research-analysis", key, "provider_budget_exhausted")
            raise _error("provider_budget_exhausted", "The shared application budget was used up before this "
                         "request could be reserved. Nothing was sent.", 409) from None
        except ProviderFailure as failure:
            if failure.attempt_id is None:
                self.workflow.fail_operation(actor, workspace_id, "research-analysis", key, failure.code)
                raise
            return self._store_failure(actor, workspace_id, key, request, plan, consent["id"], failure.code,
                                       failure.attempt_id)
        except asyncio.CancelledError:
            if tracker.attempt_id is not None:
                self._store_failure(actor, workspace_id, key, request, plan, consent["id"],
                                    "provider_cancelled_unknown_outcome", tracker.attempt_id)
            else:
                self.workflow.fail_operation(actor, workspace_id, "research-analysis", key, "cancelled_before_dispatch")
            raise
        except Exception:
            if tracker.attempt_id is not None:
                return self._store_failure(actor, workspace_id, key, request, plan, consent["id"],
                                           "provider_request_failed_unknown_outcome", tracker.attempt_id)
            self.workflow.fail_operation(actor, workspace_id, "research-analysis", key, "analysis_setup_failed")
            raise
        # Validation and storage run without a cancellation point: a completed attempt is always recorded.
        try:
            checked = self._validate_output(plan, result.value)
        except Exception:
            return self._store_failure(actor, workspace_id, key, request, plan, consent["id"],
                                       "analysis_validation_failed", result.attempt_id)
        record_body = self._record_body(request, plan, consent["id"], status="completed",
                                        attempt_id=result.attempt_id, checked=checked)
        record = self.workflow.create_record(actor, workspace_id, ANALYSIS_KIND, record_body, key,
                                             operation="research-analysis-record", parent_id=consent["id"])
        self.workflow.finish_operation(actor, workspace_id, "research-analysis", key, {"analysis_id": record["id"]})
        return self.public_analysis(record)

    def _replayed_analysis(self, actor: str, workspace_id: str, operation: dict,
                           request: ResearchAnalysisRequest) -> dict:
        if operation["state"] == "completed":
            return self.analysis(actor, operation["response"]["analysis_id"])
        if operation["state"] == "reserved":
            created = datetime.fromisoformat(operation["created_at"].replace("Z", "+00:00"))
            age = (datetime.now(timezone.utc) - created).total_seconds()
            if age > self.transport.config.request_timeout_seconds + 300:
                return self._reconcile(actor, workspace_id, operation, request)
            raise _error("operation_pending", "This analysis is still running. Retrieve it again with the same "
                         "operation identity; no second request was sent.", 409, retryable=True)
        code = operation.get("error_code") or "operation_failed"
        raise _error(code, "This analysis request was refused earlier and nothing was recorded. Start a new analysis "
                     "with a new operation identity.", 409)

    def _reconcile(self, actor: str, workspace_id: str, operation: dict, request: ResearchAnalysisRequest) -> dict:
        """Close an operation interrupted by a crash or restart: its outcome is unknown and stays accounted."""
        attempt_id = consent_id = None
        store = getattr(self.transport.ledger, "store", None)
        if store is not None:
            with store.read() as conn:
                row = conn.execute("SELECT id FROM provider_attempts WHERE operation_id=? ORDER BY created_at LIMIT 1",
                                   (operation["id"],)).fetchone()
                attempt_id = row["id"] if row else None
        with self.workflow.store.read() as conn:
            row = conn.execute("SELECT response FROM operations WHERE workspace_id=? AND actor_id=? AND operation=? "
                               "AND operation_key=? AND state='completed'",
                               (workspace_id, actor, "research-analysis-consent", request.client_operation_id)).fetchone()
            consent_id = json.loads(row["response"])["id"] if row else None
        try:
            plan = self._plan(actor, workspace_id, request.question, request.assets)
        except DomainError:
            plan = Plan([], "", [], [], 0, 0, [], None)
        return self._store_failure(actor, workspace_id, request.client_operation_id, request, plan, consent_id,
                                   "analysis_interrupted_unknown_outcome", attempt_id)

    def _store_failure(self, actor, workspace_id, key, request, plan, consent_id, code, attempt_id) -> dict:
        body = self._record_body(request, plan, consent_id, status="unknown_outcome" if "unknown_outcome" in code
                                 else "failed", attempt_id=attempt_id, failure=code)
        record = self.workflow.create_record(actor, workspace_id, ANALYSIS_KIND, body, key,
                                             operation="research-analysis-record")
        self.workflow.finish_operation(actor, workspace_id, "research-analysis", key, {"analysis_id": record["id"]})
        return self.public_analysis(record)

    # ================================================================== output validation
    def _validate_output(self, plan: Plan, value: ModelAnalysisOutput) -> dict:
        by_label = {source.label: source for source in plan.sources}
        haystacks: dict[tuple[str, int], tuple[str, str]] = {}

        def haystack(source: Source, index: int) -> tuple[str, str]:
            cache_key = (source.label, index)
            if cache_key not in haystacks:
                text = source.pages_text[index].text
                haystacks[cache_key] = (normalize(text)[0], normalize(text, dehyphenate=True)[0])
            return haystacks[cache_key]

        cells: dict[str, set[str] | None] = {}

        def occurs(source: Source, index: int, value_text: str, cell: bool = False) -> bool:
            needle = normalize(value_text)[0]
            if not needle:
                return False
            if cell:
                if source.label not in cells:
                    cells[source.label] = source.table_cells()
                if cells[source.label] is not None:
                    return needle in cells[source.label]
            return any(token_occurrences(text, needle, source.separators)[0] for text in haystack(source, index))

        citations, by_id = [], {}
        for item in value.citations:
            cid = item.id.strip()
            entry = {"id": cid, "source_label": item.source, "asset_id": None, "source_sha256": None,
                     "page_index": item.page_index, "page_number": item.page_index + 1, "quote": item.quote,
                     "status": "invalid_source", "bbox_e4": None, "match": None, "normalizations": [], "flags": [],
                     "found_on_page_indices": []}
            source = by_label.get(item.source)
            if cid in by_id:
                entry["status"] = "duplicate_id"
                citations.append(entry)
                continue
            if source is not None:
                entry.update(asset_id=source.record["id"], source_sha256=source.body["sha256"])
                sent = {part["page_index"] for part in source.parts}
                if item.page_index >= len(source.body["pages"]):
                    entry["status"] = "invalid_page"
                elif item.page_index not in sent:
                    entry["status"] = "page_not_sent"
                else:
                    located = locate(source.pages_text, item.page_index, item.quote, source.separators)
                    entry.update(status=located["status"], normalizations=located["normalizations"],
                                 flags=located["flags"],
                                 found_on_page_indices=[i for i in located["found_on_pages"] if i in sent])
                    if located["match"]:
                        entry["match"] = {**located["match"],
                                          "text_sha256": source.body["pages"][item.page_index]["text_sha256"]}
                    entry["bbox_e4"] = located["bbox_e4"]
            by_id[cid] = entry
            citations.append(entry)

        claims = []
        for number, claim in enumerate(value.claims, 1):
            cited = [by_id.get(identifier) for identifier in claim.citation_ids]
            flags = ["unknown_citation_id"] if any(entry is None for entry in cited) else []
            cited = [entry for entry in cited if entry is not None]
            verified = [entry for entry in cited if entry["status"] == "verified"]
            unverifiable = [entry for entry in cited if entry["status"].startswith("unverifiable")]
            unsupported = [token for token in numbers_in(claim.text)
                           if not any(contains_token(entry["quote"], token, by_label[entry["source_label"]].separators)
                                      for entry in verified)]
            if not cited:
                support = "uncited"
            elif verified and len(verified) == len(cited) and not unsupported:
                support = "supported"
            elif verified:
                support = "partially_supported"
            elif unverifiable and len(unverifiable) == len(cited):
                support = "unverifiable"
            else:
                support = "unsupported"
            if has_flattened_exponent(claim.text) or any("possible_flattened_exponent" in e["flags"] for e in cited):
                flags.append("possible_flattened_exponent")
            if claim.uncertainty == "hard_bound" and (statistical_qualifiers(claim.text) or any(
                    "statistical_qualifier_in_quote" in entry["flags"] for entry in cited)):
                flags.append("hard_bound_conflicts_with_statistical_qualifier")
            if VERIFICATION_WORDS.search(claim.text):
                flags.append("verification_language_not_a_verification")
            claims.append({"id": f"K{number}", "text": claim.text, "kind": claim.kind,
                           "uncertainty": claim.uncertainty, "citation_ids": list(claim.citation_ids),
                           "support": support, "unsupported_numbers": unsupported, "flags": flags})

        tables = []
        for number, table in enumerate(value.extracted_tables, 1):
            source = by_label.get(table.source)
            flags, columns = [], []
            valid_page = (source is not None and table.page_index < len(source.body["pages"])
                          and table.page_index in {part["page_index"] for part in source.parts})
            checkable = valid_page and source.pages_text[table.page_index].quality == "usable"
            if not valid_page:
                flags.append("invalid_source_or_page")
            for column in table.columns:
                if column.unit is None:
                    status = "not_stated"
                elif not checkable:
                    status = "unverifiable"
                else:
                    status = "printed_in_source" if occurs(source, table.page_index, column.unit) else "not_found_in_source"
                columns.append({"name": column.name, "unit": column.unit, "unit_status": status})
            unsupported, exponents = [], []
            for row_index, row in enumerate(table.rows):
                if len(row) != len(table.columns) and "row_length_differs_from_columns" not in flags:
                    flags.append("row_length_differs_from_columns")
                for column_index, cell in enumerate(row):
                    if cell is None or not cell.strip():
                        continue
                    if has_flattened_exponent(cell):
                        exponents.append([row_index, column_index])
                    if checkable and not occurs(source, table.page_index, cell.strip(), cell=True):
                        unsupported.append([row_index, column_index])
            if any(identifier not in by_id for identifier in table.citation_ids):
                flags.append("unknown_citation_id")
            tables.append({"id": f"T{number}", "title": table.title, "source_label": table.source,
                           "asset_id": source.record["id"] if source else None,
                           "source_sha256": source.body["sha256"] if source else None,
                           "page_index": table.page_index, "page_number": table.page_index + 1, "columns": columns,
                           "rows": [list(row) for row in table.rows], "citation_ids": list(table.citation_ids),
                           "notes": table.notes, "review_status": "unreviewed",
                           "cell_checks": {"checked_against_text_layer": checkable, "unsupported_cells": unsupported,
                                           "ambiguous_exponent_cells": exponents}, "flags": flags})

        record_flags = []
        if VERIFICATION_WORDS.search(value.summary) or any("verification_language_not_a_verification" in claim["flags"]
                                                           for claim in claims):
            record_flags.append("model_used_verification_language")
        limitations = list(value.limitations) + plan.limitations
        if record_flags:
            limitations.append("The model's wording mentions verification or proof. No mathematical verification was "
                               "performed; this is AI interpretation.")
        return {"summary": value.summary, "extracted_tables": tables, "claims": claims, "limitations": limitations,
                "clarifications": [{"id": f"Q{i}", "question": c.question, "reason": c.reason}
                                   for i, c in enumerate(value.clarifications, 1)],
                "suggested_next_steps": [{"id": f"N{i}", "action": s.action, "rationale": s.rationale, "kind": s.kind}
                                         for i, s in enumerate(value.suggested_next_steps, 1)],
                "citations": citations, "flags": record_flags}

    # ================================================================== records
    def _record_body(self, request: ResearchAnalysisRequest, plan: Plan, consent_id: str | None, *, status: str,
                     attempt_id: str | None, checked: dict | None = None, failure: str | None = None) -> dict:
        mode = self.transport.mode if self.transport.mode != "disabled" else "controlled"
        checked = checked or {"summary": None, "extracted_tables": [], "claims": [], "limitations": plan.limitations,
                              "clarifications": [], "suggested_next_steps": [], "citations": [], "flags": []}
        citations = checked["citations"]
        verified = sum(c["status"] == "verified" for c in citations)
        ambiguous = sum(c["status"] == "ambiguous" for c in citations)
        unverifiable = sum(c["status"].startswith("unverifiable") for c in citations)
        adapter = plan.supported_adapter
        return {"contract_version": L.CONTRACT_VERSION, "client_operation_id": request.client_operation_id,
                "status": status, "label": LABELS["live" if mode == "live" else "controlled"],
                "execution_mode": mode, "provider": "gemini" if mode == "live" else "controlled",
                "model": self.transport.model or "", "question": request.question,
                "assets": [{"id": s.record["id"], "sha256": s.body["sha256"], "label": s.label,
                            "filename": s.body["filename"], "media_type": s.body["media_type"],
                            "data_origin": s.body["provenance"]["data_origin"], "page_count": len(s.body["pages"]),
                            "pages_sent": self._pages_sent(s)} for s in plan.sources],
                "consent": {"accepted": True, "provider": "gemini", "model": request.consent.model,
                            "asset_ids": list(request.consent.asset_ids), "include_question": True,
                            "consent_record_id": consent_id or ""},
                **checked,
                "citation_summary": {"total": len(citations), "verified": verified, "ambiguous": ambiguous,
                                     "unverifiable": unverifiable,
                                     "rejected": len(citations) - verified - ambiguous - unverifiable},
                "verification": {"status": "not_mathematically_verified", "supported_adapter": adapter,
                                 "reason": ("A selected table states hours and mg/L, so the two-rate concentration "
                                            "checker could be offered after explicit review and approval. This "
                                            "analysis itself is not a check.") if adapter else
                                           ("No qualified mathematical checker covers this material; this is AI "
                                            "interpretation only."),
                                 "checked_record_id": None},
                "provider_attempt_id": attempt_id, "prompt_version": PROMPT_VERSION,
                "output_schema_version": OUTPUT_SCHEMA_VERSION,
                "normalization_version": L.CITATION_NORMALIZATION_VERSION,
                "reservation": {"input_tokens": plan.input_tokens, "output_tokens": plan.output_tokens},
                "failure": {"code": failure, "message": FAILURE_MESSAGES.get(
                    failure, "The analysis did not complete. Nothing in it was accepted.")} if failure else None}

    @staticmethod
    def public_analysis(record: dict) -> dict:
        body = record["body"]
        citations = []
        for citation in body["citations"]:
            box = citation.get("bbox_e4")
            public = {key: value for key, value in citation.items() if key != "bbox_e4"}
            public["bbox"] = [round(v / 10_000, 4) for v in box] if box else None
            public["bbox_space"] = L.BBOX_SPACE if box else None
            citations.append(public)
        return {"id": record["id"], "workspace_id": record["workspace_id"], **body, "citations": citations,
                "created_at": record["created_at"]}

    def analysis(self, actor: str, analysis_id: str) -> dict:
        return self.public_analysis(self.workflow.get(actor, analysis_id, ANALYSIS_KIND))

    def list_analyses(self, actor: str, workspace_id: str) -> list[dict]:
        return [self.public_analysis(record)
                for record in self.workflow.list_records(actor, workspace_id, ANALYSIS_KIND, 200)]

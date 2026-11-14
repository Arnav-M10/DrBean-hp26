"""Publish the general research contract: JSON Schemas and exact HTTP examples from a real run.

    python -m bean_api.general_research.contract            # write shared/contracts/general-research.v1
    python -m bean_api.general_research.contract --check    # exit 1 if the committed files differ

Examples come from the actual application with the controlled demo responder and the
committed public fixtures; nothing contacts a provider. Server-generated identifiers,
timestamps and platform-dependent rendered-image digests are replaced with labelled
placeholders so the files are reproducible on any machine.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import sys
import tempfile

from . import limits as L
from .schemas import PUBLIC_MODELS

ROOT = Path(__file__).resolve().parents[4]
DESTINATION = ROOT / "shared" / "contracts" / L.CONTRACT_VERSION
FIXTURES = ROOT / "fixtures" / "general"
ROUTES = [
    {"method": "GET", "path": "/api/bean/v1/research-capabilities", "response": "capabilities"},
    {"method": "POST", "path": "/api/bean/v1/workspaces/{workspace_id}/research-assets", "status": 201,
     "request": "raw file bytes; Content-Type required; X-Source-Name optional (percent-encoded UTF-8); "
                "query origin=real_observation|public_source|synthetic_example|hypothetical|unspecified; "
                "Idempotency-Key optional", "response": "ResearchAsset"},
    {"method": "GET", "path": "/api/bean/v1/workspaces/{workspace_id}/research-assets", "response": "ResearchAsset[]"},
    {"method": "GET", "path": "/api/bean/v1/research-assets/{asset_id}", "response": "ResearchAsset"},
    {"method": "GET", "path": "/api/bean/v1/research-assets/{asset_id}/content",
     "response": "original bytes (images inline, other types as attachment), X-Artifact-SHA256"},
    {"method": "GET", "path": "/api/bean/v1/research-assets/{asset_id}/pages/{page_index}/image",
     "response": "bounded PNG/JPEG page image (PDF pages, image previews)"},
    {"method": "GET", "path": "/api/bean/v1/research-assets/{asset_id}/pages/{page_index}/text", "response": "PageText"},
    {"method": "POST", "path": "/api/bean/v1/workspaces/{workspace_id}/research-analysis-estimates", "status": 200,
     "request": "AnalysisEstimateRequest", "response": "AnalysisEstimate", "side_effects": "none"},
    {"method": "POST", "path": "/api/bean/v1/workspaces/{workspace_id}/research-analyses", "status": 201,
     "request": "ResearchAnalysisRequest; Idempotency-Key must equal client_operation_id",
     "response": "ResearchAnalysis"},
    {"method": "GET", "path": "/api/bean/v1/workspaces/{workspace_id}/research-analyses", "response": "ResearchAnalysis[]"},
    {"method": "GET", "path": "/api/bean/v1/research-analyses/{analysis_id}", "response": "ResearchAnalysis",
     "side_effects": "none; never calls a model"},
]
VOLATILE = [
    (re.compile(r"\b(research_asset|research_analysis_consent|research_analysis|controlled_attempt|ws)_[0-9a-f]{32}\b"),
     lambda m: f"<{m.group(1)}_id>"),
    (re.compile(r"\b\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z\b"), lambda m: "<timestamp>"),
    (re.compile(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b"), lambda m: "<request_id>"),
]


def _scrub(value, rendered: set[str]):
    if isinstance(value, dict):
        result = {}
        for key, item in value.items():
            if key in ("image_sha256",) and item in rendered:
                result[key] = "<rendered-page-png-sha256>"
            elif key == "digest" and isinstance(item, str):
                result[key] = "<record-digest>"
            elif key == "parser" and isinstance(item, dict) and item.get("name") == "pypdfium2":
                result[key] = {"name": "pypdfium2", "version": "<pypdfium2 version (pdfium build)>"}
            elif key == "isolation":
                result[key] = "<platform-specific guard description>"
            else:
                result[_scrub(key, rendered)] = _scrub(item, rendered)
        return result
    if isinstance(value, list):
        return [_scrub(item, rendered) for item in value]
    if isinstance(value, str):
        for pattern, replacement in VOLATILE:
            value = pattern.sub(replacement, value)
        return value
    return value


def schemas() -> dict[str, dict]:
    result = {}
    for name, model in sorted(PUBLIC_MODELS.items()):
        schema = model.model_json_schema()
        schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
        schema["$id"] = f"urn:dr-bean:{L.CONTRACT_VERSION}:{name}"
        result[f"{name}.schema.json"] = schema
    return result


def examples() -> dict[str, dict]:
    """Published examples: the recorded exchanges with volatile values replaced by labelled placeholders."""
    out, rendered = run_examples()
    return {f"{name}.json": _scrub(value, rendered) for name, value in out.items()}


def run_examples() -> tuple[dict[str, dict], set[str]]:
    """Run the real application once with the controlled demo responder and record its exchanges."""
    from fastapi.testclient import TestClient
    from ..config import Settings
    from ..main import PREFIX, create_app
    from ..providers import GeminiProvider, ProviderConfig
    from .controlled import demo_responder
    from .routes import general_research_capabilities

    previous = os.environ.pop("BEAN_GENERAL_ANALYSIS_MODE", None)
    try:
        with tempfile.TemporaryDirectory() as directory:
            settings = Settings(database_path=f"{directory}/db.sqlite3", blob_dir=f"{directory}/sources",
                                auth_tokens={"researcher": "r" * 40}, science_adapter="unavailable",
                                artifact_dir=f"{directory}/artifacts")
            # Export is always controlled, even from a shell used to start a
            # separately configured live server. It never loads that credential.
            app = create_app(settings, provider=GeminiProvider(ProviderConfig(), None), controlled_general_responder=demo_responder)
            out: dict[str, dict] = {}
            with TestClient(app) as client:
                client.headers["Authorization"] = "Bearer " + "r" * 40
                w = client.post(PREFIX + "/workspaces", json={"name": "Example workspace"}).json()["id"]
                csv_bytes = (FIXTURES / "noaa-gml-co2-annmean-mlo.csv").read_bytes()
                path = f"{PREFIX}/workspaces/{w}/research-assets?origin=real_observation"
                csv_asset = client.post(path, content=csv_bytes, headers={
                    "Content-Type": "text/csv", "X-Source-Name": "co2_annmean_mlo.csv", "Idempotency-Key": "upload-co2"})
                out["upload-csv"] = {"request": {"method": "POST", "path": path, "headers": {
                    "Content-Type": "text/csv", "X-Source-Name": "co2_annmean_mlo.csv", "Idempotency-Key": "upload-co2"},
                    "body": "<raw bytes of fixtures/general/noaa-gml-co2-annmean-mlo.csv>"},
                    "response": {"status": csv_asset.status_code, "body": csv_asset.json()}}
                pdf_bytes = (FIXTURES / "naca-tn-1428-pages-1-5-6.pdf").read_bytes()
                pdf_path = f"{PREFIX}/workspaces/{w}/research-assets?origin=public_source"
                pdf_asset = client.post(pdf_path, content=pdf_bytes, headers={
                    "Content-Type": "application/pdf", "X-Source-Name": "naca-tn-1428.pdf"})
                out["upload-scanned-pdf"] = {"request": {"method": "POST", "path": pdf_path, "headers": {
                    "Content-Type": "application/pdf", "X-Source-Name": "naca-tn-1428.pdf"},
                    "body": "<raw bytes of fixtures/general/naca-tn-1428-pages-1-5-6.pdf>"},
                    "response": {"status": pdf_asset.status_code, "body": pdf_asset.json()}}
                pdf = pdf_asset.json()
                text = client.get(f"{PREFIX}/research-assets/{pdf['id']}/pages/1/text")
                out["page-text"] = {"request": {"method": "GET", "path": f"{PREFIX}/research-assets/{pdf['id']}/pages/1/text"},
                                    "response": {"status": text.status_code, "body": text.json()}}
                csv = csv_asset.json()
                refs = [{"id": csv["id"], "sha256": csv["sha256"]},
                        {"id": pdf["id"], "sha256": pdf["sha256"], "page_indices": [1, 2]}]
                question = "How did the annual mean change, and what do the NACA pages describe?"
                estimate_body = {"question": question, "assets": refs}
                estimate = client.post(f"{PREFIX}/workspaces/{w}/research-analysis-estimates", json=estimate_body)
                out["estimate"] = {"request": {"method": "POST",
                                               "path": f"{PREFIX}/workspaces/{w}/research-analysis-estimates",
                                               "body": estimate_body},
                                   "response": {"status": estimate.status_code, "body": estimate.json()}}
                body = {"client_operation_id": "analysis-2026-11-14-001", "question": question, "assets": refs,
                        "consent": {"accepted": True, "provider": "gemini", "model": "controlled-general-analysis",
                                    "asset_ids": [csv["id"], pdf["id"]], "include_question": True}}
                analysis = client.post(f"{PREFIX}/workspaces/{w}/research-analyses", json=body,
                                       headers={"Idempotency-Key": body["client_operation_id"]})
                out["analysis"] = {"request": {"method": "POST", "path": f"{PREFIX}/workspaces/{w}/research-analyses",
                                               "headers": {"Idempotency-Key": body["client_operation_id"]},
                                               "body": body},
                                   "response": {"status": analysis.status_code, "body": analysis.json()}}
                stale_body = {**body, "client_operation_id": "analysis-2026-11-14-002",
                              "assets": [{"id": csv["id"], "sha256": "0" * 64}],
                              "consent": {**body["consent"], "asset_ids": [csv["id"]]}}
                stale = client.post(f"{PREFIX}/workspaces/{w}/research-analyses", json=stale_body,
                                    headers={"Idempotency-Key": stale_body["client_operation_id"]})
                out["error-stale-digest"] = {"request": {"method": "POST",
                                                         "path": f"{PREFIX}/workspaces/{w}/research-analyses",
                                                         "body": stale_body},
                                             "response": {"status": stale.status_code, "body": stale.json()}}
                out["capabilities"] = {"response": {"status": 200, "body": general_research_capabilities(app)}}
            rendered = {page["image_sha256"] for page in pdf["pages"] if page["image_sha256"]}
            return out, rendered
    finally:
        if previous is not None:
            os.environ["BEAN_GENERAL_ANALYSIS_MODE"] = previous


def manifest() -> dict:
    return {"contract_version": L.CONTRACT_VERSION, "prefix": "/api/bean/v1", "routes": ROUTES,
            "schemas": sorted(schemas()), "examples": sorted(f"examples/{name}" for name in examples_names()),
            "limits": L.public_limits(),
            "conventions": {
                "page_index": "zero-based; page_number = page_index + 1 for display",
                "bbox": "[x0, y0, x1, y1] normalized 0-1, origin top-left of the displayed (rotated) page; "
                        "bbox_space = normalized_top_left; null when no character boxes exist",
                "citation": "binds source_sha256 + page_index + exact quote; status verified only for one "
                            "admissible occurrence after citation-normalization.v1",
                "verification": "every analysis is not_mathematically_verified; checked results are separate records",
                "records": "analyses are returned as {id, workspace_id, kind, digest, created_at, body}; assets are flat",
                "failures": "an analysis that used a provider attempt but produced no result is stored and listed, and "
                            "its POST (and every retry with the same key) returns the standard error envelope (422)",
                "errors": "standard envelope {code, message, field_paths, retryable, current_revision_id, request_id}"},
            "generator": "python -m bean_api.general_research.contract"}


def examples_names() -> list[str]:
    return ["upload-csv.json", "upload-scanned-pdf.json", "page-text.json", "estimate.json", "analysis.json",
            "error-stale-digest.json", "capabilities.json"]


def render() -> dict[str, str]:
    files = {name: schema for name, schema in schemas().items()}
    files.update({f"examples/{name}": value for name, value in examples().items()})
    files["manifest.json"] = manifest()
    return {name: json.dumps(value, indent=2, ensure_ascii=False, sort_keys=False) + "\n" for name, value in files.items()}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    files = render()
    if args.check:
        stale = [name for name, text in files.items()
                 if not (DESTINATION / name).is_file() or (DESTINATION / name).read_text(encoding="utf-8") != text]
        for name in stale:
            print(f"out of date: {DESTINATION / name}")
        return 1 if stale else 0
    for name, text in files.items():
        target = DESTINATION / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
    print(f"wrote {len(files)} files to {DESTINATION}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

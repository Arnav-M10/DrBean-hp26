"""The published general research contract matches the code, and integration status is explicit."""
import json
import math

import pytest
from fastapi.testclient import TestClient

from bean_api.config import Settings
from bean_api.general_research import general_research_capabilities, register_general_routes
from bean_api.general_research import contract, schemas as S
from bean_api.main import PREFIX, create_app


def same(left, right, path="$"):
    if isinstance(left, float) or isinstance(right, float):
        assert isinstance(left, (int, float)) and isinstance(right, (int, float)) and math.isclose(
            left, right, abs_tol=2e-3), path
    elif isinstance(left, dict):
        assert isinstance(right, dict) and set(left) == set(right), path
        for key in left:
            same(left[key], right[key], f"{path}.{key}")
    elif isinstance(left, list):
        assert isinstance(right, list) and len(left) == len(right), path
        for index, (a, b) in enumerate(zip(left, right)):
            same(a, b, f"{path}[{index}]")
    else:
        assert left == right, path


def test_published_schemas_match_the_models():
    for name, schema in contract.schemas().items():
        committed = json.loads((contract.DESTINATION / name).read_text(encoding="utf-8"))
        assert committed == schema, name
    assert json.loads((contract.DESTINATION / "manifest.json").read_text(encoding="utf-8")) == contract.manifest()


@pytest.fixture(scope="module")
def recorded():
    return contract.run_examples()


def test_published_examples_are_current(recorded):
    out, rendered = recorded
    for name, value in out.items():
        committed = json.loads((contract.DESTINATION / "examples" / f"{name}.json").read_text(encoding="utf-8"))
        same(committed, json.loads(json.dumps(contract._scrub(value, rendered))), name)


def test_actual_exchanges_conform_to_the_published_models(recorded):
    out, _ = recorded
    S.ResearchAsset.model_validate(out["upload-csv"]["response"]["body"])
    pdf = S.ResearchAsset.model_validate(out["upload-scanned-pdf"]["response"]["body"])
    assert [page.text_layer for page in pdf.pages] == ["none", "native_pdf_text", "native_pdf_text"]
    S.PageText.model_validate(out["page-text"]["response"]["body"])
    S.AnalysisEstimateRequest.model_validate(out["estimate"]["request"]["body"])
    S.AnalysisEstimate.model_validate(out["estimate"]["response"]["body"])
    S.ResearchAnalysisRequest.model_validate(out["analysis"]["request"]["body"])
    analysis = S.ResearchAnalysis.model_validate(out["analysis"]["response"]["body"])
    assert analysis.verification.status == "not_mathematically_verified" and analysis.execution_mode == "controlled"
    error = out["error-stale-digest"]["response"]
    assert error["status"] == 409 and set(error["body"]) == {"code", "message", "field_paths", "retryable",
                                                              "current_revision_id", "request_id"}


def test_model_output_schema_never_lets_the_model_supply_authority():
    properties = json.dumps(S.ModelAnalysisOutput.model_json_schema())
    for forbidden in ("verification", "verified", "sha256", "bbox", "approval", "review_status", "asset_id"):
        assert f'"{forbidden}"' not in properties


def settings(tmp_path):
    return Settings(database_path=str(tmp_path / "db.sqlite3"), blob_dir=str(tmp_path / "sources"),
                    auth_tokens={"alice": "a" * 40}, science_adapter="unavailable",
                    artifact_dir=str(tmp_path / "artifacts"))


def test_registration_attaches_routes_once_and_reports_capability(tmp_path):
    app = create_app(settings(tmp_path))
    before = general_research_capabilities(app)
    assert before["routes_registered"] is False and before["available"] is False
    service = register_general_routes(app)
    assert app.state.general_research is service
    paths = set(app.openapi()["paths"])
    assert PREFIX + "/workspaces/{workspace_id}/research-analyses" in paths
    assert PREFIX + "/research-assets/{asset_id}/pages/{page_index}/text" in paths
    with pytest.raises(RuntimeError):
        register_general_routes(app)
    after = general_research_capabilities(app)
    assert after["routes_registered"] is True and after["upload_available"] is True
    assert after["verification"]["general_analysis"] == "not_mathematically_verified"
    assert after["citations"] == {"normalization_version": "citation-normalization.v1",
                                  "bbox_space": "page_normalized_top_left", "page_index_base": 0, "page_number_base": 1}


@pytest.mark.xfail(strict=True, reason="Integration pending: GPT1 wires register_general_routes(app) and "
                                       "general_research_capabilities(app) into create_app and /capabilities")
def test_the_assembled_application_serves_general_research(tmp_path):
    app = create_app(settings(tmp_path))
    with TestClient(app) as client:
        client.headers["Authorization"] = "Bearer " + "a" * 40
        assert client.get(PREFIX + "/research-capabilities").status_code == 200
        assert client.get(PREFIX + "/capabilities").json()["general_research"]["routes_registered"] is True

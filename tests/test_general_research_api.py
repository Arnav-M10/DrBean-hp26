"""HTTP contract of general research files and analyses with substituted transports.

No test contacts Gemini: controlled transports use an injected client, and the live
path replaces ``google.genai.Client`` with a fake (as the existing live opt-in tests do).
"""
import asyncio
import json
from pathlib import Path

import pytest

from bean_api.general_research.transport import GeneralAnalysisTransport
from bean_api.main import PREFIX
from bean_api.providers import LIVE_MODEL
from general_research_support import (
    ALICE, BOB, CONTROLLED_MODEL, DUMMY_LIVE_KEY, SOIL_CSV, Factory, FakeClient, analysis_body, analyze, client_for,
    controlled_transport, jpeg_bytes, live_config, make_app, output, paper_pdf, png_bytes, scanned_pdf, upload,
    workspace,
)
import general_research_pdf as pdfs


def attempts(app):
    with app.state.workflow.store.read() as conn:
        return [dict(row) for row in conn.execute("SELECT * FROM provider_attempts ORDER BY created_at")]


def scientific_records(app, workspace_id):
    return {kind: app.state.workflow.list_records("alice", workspace_id, kind)
            for kind in ("dataset", "problem", "plan", "evidence")}


@pytest.fixture
def controlled(tmp_path):
    def build(*script, **options):
        factory = Factory(*script, **{key: value for key, value in options.items() if key in {"delay", "finish_reason", "usage", "gate"}})
        config = {key: value for key, value in options.items() if key not in {"delay", "finish_reason", "usage", "gate"}}
        app = make_app(tmp_path, transport_for=controlled_transport(factory, **config))
        return app, factory, client_for(app)
    return build


# --------------------------------------------------------------------------- assets
def test_upload_retrieve_list_and_page_routes(controlled):
    app, _, client = controlled()
    w = workspace(client)
    asset = upload(client, w, SOIL_CSV, "text/csv", name="soil%20cores%20%E2%80%94%20spring.csv", origin="real_observation")
    assert asset["filename"] == "soil cores — spring.csv" and asset["media_type"] == "text/csv"
    assert asset["provenance"]["data_origin"] == "real_observation" and asset["provenance"]["origin_verified"] is False
    assert asset["pages"] == [{"page_index": 0, "page_number": 1, "width": None, "height": None, "dimension_unit": None,
                               "rotation": None, "image_sha256": None, "image_media_type": None, "image_width": None,
                               "image_height": None, "text_sha256": asset["pages"][0]["text_sha256"],
                               "text_layer": "decoded_text", "char_count": len(SOIL_CSV.decode())}]
    assert client.get(PREFIX + f"/research-assets/{asset['id']}").json() == asset
    assert [a["id"] for a in client.get(PREFIX + f"/workspaces/{w}/research-assets").json()] == [asset["id"]]
    text = client.get(PREFIX + f"/research-assets/{asset['id']}/pages/0/text").json()
    assert text["text"] == SOIL_CSV.decode() and text["page_number"] == 1
    download = client.get(PREFIX + f"/research-assets/{asset['id']}/content")
    assert download.content == SOIL_CSV and download.headers["content-type"] == "application/octet-stream"
    assert download.headers["content-disposition"].startswith("attachment;")
    assert download.headers["x-artifact-sha256"] == asset["sha256"]
    assert "sandbox" in download.headers["content-security-policy"]
    pdf = upload(client, w, paper_pdf(), "application/pdf", origin="synthetic_example")
    image = client.get(PREFIX + f"/research-assets/{pdf['id']}/pages/1/image")
    assert image.status_code == 200 and image.content.startswith(b"\x89PNG")
    assert client.get(PREFIX + f"/research-assets/{pdf['id']}/pages/9/image").status_code == 404
    assert client.get(PREFIX + f"/research-assets/{asset['id']}/pages/0/image").status_code == 404


def test_upload_idempotency_and_key_binding(controlled):
    _, _, client = controlled()
    w = workspace(client)
    first = upload(client, w, SOIL_CSV, "text/csv", key="upload-1")
    assert upload(client, w, SOIL_CSV, "text/csv", key="upload-1")["id"] == first["id"]
    conflict = upload(client, w, SOIL_CSV + b"N-03,10,1,1,clay,\n", "text/csv", key="upload-1", expect=409)
    assert conflict["code"] == "idempotency_conflict"
    assert upload(client, w, SOIL_CSV, "text/csv")["id"] != first["id"]   # no key: a new record each time


def test_user_json_files_bypass_the_strict_api_json_parser(controlled):
    _, _, client = controlled()
    w = workspace(client)
    asset = upload(client, w, '{"Messwert (°C)": 21.5, "ok": true}'.encode(), "application/json")
    assert asset["content_summary"]["top_level_keys"] == ["Messwert (°C)", "ok"]


def test_boundary_and_admission_refusals(controlled):
    _, _, client = controlled()
    w = workspace(client)
    too_large = client.post(PREFIX + f"/workspaces/{w}/research-assets", content=b"x" * (5 * 1024 * 1024 + 1),
                            headers={"Content-Type": "text/plain"})
    assert too_large.status_code == 413 and too_large.json()["code"] == "request_too_large"
    assert upload(client, w, b"a,b\n1,2\n", "text/csv", origin="trust_me", expect=422)["code"] == "invalid_data_origin"
    assert upload(client, w, b"a,b\n1,2\n", "application/x-sh", expect=415)["code"] == "unsupported_media_type"
    assert upload(client, w, png_bytes(), "application/pdf", expect=415)["code"] == "media_type_mismatch"
    assert upload(client, w, pdfs.build("inflate-bomb"), "application/pdf", expect=422)["code"] == "pdf_decompression_limit"
    error = upload(client, w, pdfs.build("password-protected"), "application/pdf", expect=422)
    assert set(error) == {"code", "message", "field_paths", "retryable", "current_revision_id", "request_id"}


def test_authentication_and_cross_workspace_isolation(controlled):
    app, _, alice = controlled()
    w = workspace(alice)
    other = workspace(alice, "second")
    asset = upload(alice, w, SOIL_CSV, "text/csv")
    bob = client_for(app, BOB)
    bobs = workspace(bob, "bob's")
    for path in (f"/research-assets/{asset['id']}", f"/research-assets/{asset['id']}/content",
                 f"/research-assets/{asset['id']}/pages/0/text", f"/workspaces/{w}/research-assets"):
        assert bob.get(PREFIX + path).status_code == 404
    assert upload(bob, w, SOIL_CSV, "text/csv", expect=404)["code"] == "not_found"
    assert analyze(bob, bobs, analysis_body([asset]), expect=404)["code"] == "not_found"
    assert analyze(alice, other, analysis_body([asset]), expect=404)["code"] == "not_found"   # wrong workspace
    anonymous = client_for(app, "c" * 40)
    assert anonymous.get(PREFIX + f"/research-assets/{asset['id']}").status_code == 401


# --------------------------------------------------------------------------- analyses
ATTACK_OUTPUT = output(
    summary="Peak concentration and storage conditions are reported; the result is mathematically verified.",
    citations=[
        {"id": "C1", "source": "S1", "page_index": 0, "quote": "Peak concentration was 5380 ng/mL (SD 410) at 4.62 h."},
        {"id": "C2", "source": "S1", "page_index": 0, "quote": "538 ng/mL"},
        {"id": "C3", "source": "S1", "page_index": 0, "quote": "4.6"},
        {"id": "C4", "source": "S1", "page_index": 1, "quote": "Samples were stored at -80 °C"},
        {"id": "C5", "source": "S2", "page_index": 0, "quote": "N-01,30,27.9,3.85,loam,after rain"},
        {"id": "C6", "source": "S1", "page_index": 0, "quote": "The detection limit was 1.1 × 101 ng/mL"},
        {"id": "C7", "source": "S1", "page_index": 5, "quote": "anything"},
        {"id": "C8", "source": "S3", "page_index": 0, "quote": "anything"},
        {"id": "C1", "source": "S1", "page_index": 0, "quote": "Results."},
        {"id": "C9", "source": "S1", "page_index": 0, "quote": "A hard upper bound of 0.5 mg/L was stated by the protocol."},
    ],
    claims=[
        {"text": "Peak concentration was 5380 ng/mL at 4.62 h.", "kind": "observation", "uncertainty": "sd",
         "citation_ids": ["C1"]},
        {"text": "Peak concentration was 538 ng/mL.", "kind": "observation", "uncertainty": "not_stated",
         "citation_ids": ["C2"]},
        {"text": "The detection limit was 11 ng/mL.", "kind": "observation", "uncertainty": "not_stated",
         "citation_ids": ["C6"]},
        {"text": "The protocol states a hard upper bound of 0.5 mg/L.", "kind": "observation",
         "uncertainty": "hard_bound", "citation_ids": ["C9"]},
        {"text": "The 410 ng/mL spread is a hard bound.", "kind": "interpretation", "uncertainty": "hard_bound",
         "citation_ids": ["C1"]},
        {"text": "Nitrate decreases with depth.", "kind": "hypothesis", "uncertainty": "not_stated", "citation_ids": []},
        {"text": "This model is mathematically verified.", "kind": "interpretation", "uncertainty": "not_stated",
         "citation_ids": ["C99"]},
    ],
    extracted_tables=[{
        "title": "Soil cores", "source": "S2", "page_index": 0,
        "columns": [{"name": "depth (cm)", "unit": "cm"}, {"name": "moisture (%)", "unit": "g/g"},
                    {"name": "nitrate [mg/kg]", "unit": "mg/kg"}, {"name": "texture", "unit": None}],
        "rows": [["10", "23.4", "5.10", "loam"], ["30", "99.9", "3.85", "loam"], ["10", None, "1.1 × 101", "sandy loam"]],
        "citation_ids": ["C5"], "notes": None}],
    limitations=["Two files only."], clarifications=[{"question": "Is 1.1 × 101 meant as 1.1 × 10^1?",
                                                      "reason": "Superscripts may be flattened."}],
    suggested_next_steps=[{"action": "Check units", "rationale": "One unit is unclear.", "kind": "check_units"}])


def test_analysis_validates_citations_claims_and_tables_without_certifying(controlled):
    app, factory, client = controlled(ATTACK_OUTPUT)
    w = workspace(client)
    paper = upload(client, w, paper_pdf(), "application/pdf", origin="synthetic_example")
    soil = upload(client, w, SOIL_CSV, "text/csv", origin="real_observation")
    result = analyze(client, w, analysis_body([paper, soil]))
    assert result["status"] == "completed" and result["execution_mode"] == "controlled"
    assert result["label"].startswith("Controlled test response") and "not mathematically verified" in result["label"]
    assert result["verification"] == {"status": "not_mathematically_verified", "supported_adapter": None,
                                      "reason": result["verification"]["reason"], "checked_record_id": None}
    status = {c["id"] + ("*" if i == 8 else ""): c["status"] for i, c in enumerate(result["citations"])}
    assert status == {"C1": "verified", "C2": "not_found", "C3": "partial_token_match", "C4": "verified",
                      "C5": "verified", "C6": "verified", "C7": "invalid_page", "C8": "invalid_source",
                      "C1*": "duplicate_id", "C9": "verified"}
    c1 = result["citations"][0]
    assert c1["source_sha256"] == paper["sha256"] and c1["page_index"] == 0 and c1["page_number"] == 1
    assert c1["bbox_space"] == "page_normalized_top_left" and all(0 <= v <= 1 for v in c1["bbox"])
    assert c1["bbox"][0] < c1["bbox"][2] and c1["bbox"][1] < c1["bbox"][3]
    assert result["citations"][4]["bbox"] is None and result["citations"][4]["bbox_space"] is None   # CSV: no boxes
    assert "possible_flattened_exponent" in result["citations"][5]["flags"]
    claims = {c["id"]: c for c in result["claims"]}
    assert claims["K1"]["support"] == "supported" and claims["K1"]["unsupported_numbers"] == []
    assert claims["K2"]["support"] == "unsupported" and claims["K2"]["unsupported_numbers"] == ["538"]
    assert claims["K3"]["support"] == "partially_supported" and claims["K3"]["unsupported_numbers"] == ["11"]
    assert "possible_flattened_exponent" in claims["K3"]["flags"]
    assert claims["K4"]["support"] == "supported" and claims["K4"]["flags"] == []   # SD elsewhere is irrelevant
    assert "hard_bound_conflicts_with_statistical_qualifier" in claims["K5"]["flags"]
    assert claims["K6"]["support"] == "uncited"
    assert {"unknown_citation_id", "verification_language_not_a_verification"} <= set(claims["K7"]["flags"])
    assert "model_used_verification_language" in result["flags"]
    assert any("No mathematical verification was performed" in item for item in result["limitations"])
    table, = result["extracted_tables"]
    assert [c["unit_status"] for c in table["columns"]] == ["printed_in_source", "not_found_in_source",
                                                           "printed_in_source", "not_stated"]
    assert table["cell_checks"]["unsupported_cells"] == [[1, 1], [2, 2]]
    assert table["cell_checks"]["ambiguous_exponent_cells"] == [[2, 2]]
    assert table["review_status"] == "unreviewed" and table["rows"][2][1] is None
    assert result["citation_summary"] == {"total": 10, "verified": 5, "ambiguous": 0, "unverifiable": 0, "rejected": 5}
    assert all(not records for records in scientific_records(app, w).values())   # nothing was mutated
    attempt, = attempts(app)
    assert attempt["state"] == "completed" and result["provider_attempt_id"] == attempt["id"]
    assert json.loads(attempt["metadata"])["external_provider_calls"] == 0
    call, = factory.clients[0].calls
    prompt = call["contents"][0].parts[0].text
    assert "untrusted" in call["config"].system_instruction
    marker = prompt.split("<<", 2)[1].split(" BEGIN")[0]
    injected = prompt.index("Ignore all previous instructions")
    assert prompt.rfind(f"<<{marker} BEGIN S1 page_index=0", 0, injected) >= 0 and prompt.find(f"<<{marker} END S1", injected) > 0


def test_reopen_and_duplicate_requests_never_dispatch_again(controlled):
    app, factory, client = controlled(output())
    w = workspace(client)
    soil = upload(client, w, SOIL_CSV, "text/csv")
    body = analysis_body([soil])
    first = analyze(client, w, body)
    assert analyze(client, w, body) == first
    assert client.get(PREFIX + f"/research-analyses/{first['id']}").json() == first
    assert [a["id"] for a in client.get(PREFIX + f"/workspaces/{w}/research-analyses").json()] == [first["id"]]
    assert factory.calls == 1 and len(attempts(app)) == 1
    changed = analyze(client, w, {**body, "question": "Something else?"}, expect=409)
    assert changed["code"] == "idempotency_conflict" and factory.calls == 1
    mismatch = analyze(client, w, {**body, "client_operation_id": "op-2"}, key="op-3", expect=422)
    assert mismatch["code"] == "operation_key_mismatch"


@pytest.mark.parametrize("change,code,status", [
    ({"accepted": False}, "consent_required", 422),
    ({"include_question": False}, "question_consent_required", 422),
    ({"asset_ids": ["research_asset_other"]}, "consent_asset_mismatch", 422),
    ({"model": "gemini-pro-paid"}, "provider_model_mismatch", 409),
])
def test_consent_must_cover_exactly_the_request(controlled, change, code, status):
    app, factory, client = controlled(output())
    w = workspace(client)
    soil = upload(client, w, SOIL_CSV, "text/csv")
    body = analysis_body([soil])
    body["consent"].update(change)
    assert analyze(client, w, body, expect=status)["code"] == code
    assert factory.calls == 0 and attempts(app) == []
    assert analyze(client, w, {**analysis_body([soil]), "client_operation_id": "op-1"})["status"] == "completed"


def test_stale_digest_is_refused_before_anything_is_sent(controlled):
    app, factory, client = controlled(output())
    w = workspace(client)
    soil = upload(client, w, SOIL_CSV, "text/csv")
    stale = analyze(client, w, analysis_body([{"id": soil["id"], "sha256": "0" * 64}]), expect=409)
    assert stale["code"] == "asset_digest_mismatch" and factory.clients == [] and attempts(app) == []


def test_material_beyond_the_request_context_must_be_narrowed(controlled):
    app, factory, client = controlled(output())
    w = workspace(client)
    big = upload(client, w, ("measurement," * 3000).encode() + b"\n", "text/plain")
    estimate = client.post(PREFIX + f"/workspaces/{w}/research-analysis-estimates",
                           json={"question": "Summarize", "assets": [{"id": big["id"], "sha256": big["sha256"]}]}).json()
    assert estimate["fits_context"] is False and "analysis_context_exceeded" in estimate["blocking_reasons"]
    refused = analyze(client, w, analysis_body([big]), expect=413)
    assert refused["code"] == "analysis_context_exceeded" and "Nothing was sent" in refused["message"]
    assert factory.clients == [] and attempts(app) == []
    document = pdfs.Document("long paper")
    for number in range(4):
        page = document.page()
        for line in range(40):
            page.text(40, 760 - line * 18, f"Page {number + 1} line {line + 1}: " + "observed value 12.5 units " * 4, size=7)
    paper = upload(client, w, document.to_bytes(), "application/pdf")
    assert analyze(client, w, analysis_body([paper], operation="op-pdf"), expect=413)["code"] == "analysis_context_exceeded"
    narrowed = analysis_body([{"id": paper["id"], "sha256": paper["sha256"], "page_indices": [2]}], operation="op-p3")
    result = analyze(client, w, narrowed)
    assert result["assets"][0]["pages_sent"] == [{"page_index": 2, "sent_as": "text",
                                                  "text_sha256": paper["pages"][2]["text_sha256"], "image_sha256": None}]
    assert result["assets"][0]["page_count"] == 4


def test_citation_to_a_page_that_was_not_sent(controlled):
    _, _, client = controlled(output(citations=[{"id": "C1", "source": "S1", "page_index": 0,
                                                 "quote": "Peak concentration was 5380 ng/mL"}]))
    w = workspace(client)
    paper = upload(client, w, paper_pdf(), "application/pdf")
    result = analyze(client, w, analysis_body([{"id": paper["id"], "sha256": paper["sha256"], "page_indices": [1]}]))
    assert result["citations"][0]["status"] == "page_not_sent"


def test_budget_refusal_happens_before_dispatch_and_is_not_retried(tmp_path):
    factory = Factory(output())
    app = make_app(tmp_path, transport_for=controlled_transport(factory),
                   ledger_caps={"request_cap": 1, "input_token_cap": 500, "output_token_cap": 500})
    client = client_for(app)
    w = workspace(client)
    soil = upload(client, w, SOIL_CSV, "text/csv")
    refused = analyze(client, w, analysis_body([soil]), expect=409)
    assert refused["code"] == "provider_budget_exhausted" and factory.clients == [] and attempts(app) == []
    assert analyze(client, w, analysis_body([soil]), expect=409)["code"] == "provider_budget_exhausted"


def test_timeout_is_an_accounted_unknown_outcome_and_replays_without_a_second_call(controlled):
    app, factory, client = controlled(output(), delay=5, request_timeout_seconds=1)
    w = workspace(client)
    soil = upload(client, w, SOIL_CSV, "text/csv")
    body = analysis_body([soil])
    result = analyze(client, w, body)
    assert result["status"] == "unknown_outcome" and result["failure"]["code"] == "provider_timeout_unknown_outcome"
    assert result["summary"] is None and result["citations"] == []
    attempt, = attempts(app)
    assert attempt["state"] == "unknown_outcome" and result["provider_attempt_id"] == attempt["id"]
    assert analyze(client, w, body) == result and factory.calls == 1


@pytest.mark.parametrize("script,options,code", [
    ([output(verification="verified")], {}, "provider_malformed_output"),
    (["not json"], {}, "provider_malformed_output"),
    ([output()], {"finish_reason": "SAFETY"}, "provider_refused"),
    ([output()], {"finish_reason": "MAX_TOKENS"}, "provider_output_truncated"),
])
def test_rejected_model_outputs_are_recorded_failures(controlled, script, options, code):
    app, factory, client = controlled(*script, **options)
    w = workspace(client)
    soil = upload(client, w, SOIL_CSV, "text/csv")
    result = analyze(client, w, analysis_body([soil]))
    assert result["status"] == "failed" and result["failure"]["code"] == code
    assert result["verification"]["status"] == "not_mathematically_verified"
    assert attempts(app)[0]["state"] == "failed" and factory.calls == 1


def test_cancellation_during_the_call_keeps_the_reservation_and_records_unknown_outcome(tmp_path):
    from bean_api.general_research.schemas import ResearchAnalysisRequest
    gate = asyncio.Event()
    factory = Factory(output(), delay=30, gate=gate)
    app = make_app(tmp_path, transport_for=controlled_transport(factory))
    client = client_for(app)
    w = workspace(client)
    soil = upload(client, w, SOIL_CSV, "text/csv")
    request = ResearchAnalysisRequest.model_validate(analysis_body([soil]))
    service = app.state.general_research

    async def scenario():
        task = asyncio.create_task(service.analyze("alice", w, request, "op-1"))
        await asyncio.wait_for(gate.wait(), 10)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    asyncio.run(scenario())
    attempt, = attempts(app)
    assert attempt["state"] == "unknown_outcome"
    reopened = analyze(client, w, analysis_body([soil]))
    assert reopened["status"] == "unknown_outcome" and reopened["failure"]["code"] == "provider_cancelled_unknown_outcome"
    assert factory.calls == 1


def test_an_interrupted_operation_is_reconciled_as_unknown(controlled):
    app, factory, client = controlled(output())
    w = workspace(client)
    soil = upload(client, w, SOIL_CSV, "text/csv")
    body = analysis_body([soil])
    from bean_api.general_research.schemas import ResearchAnalysisRequest
    normalized = ResearchAnalysisRequest.model_validate(body).model_dump(mode="json")
    app.state.workflow.begin_operation("alice", w, "research-analysis", "op-1", normalized)   # a crash left it reserved
    assert analyze(client, w, body, expect=409)["code"] == "operation_pending"
    with app.state.workflow.store.transaction() as conn:
        conn.execute("UPDATE operations SET created_at='2026-01-01T00:00:00.000Z' WHERE operation_key='op-1'")
    reconciled = analyze(client, w, body)
    assert reconciled["status"] == "unknown_outcome"
    assert reconciled["failure"]["code"] == "analysis_interrupted_unknown_outcome" and factory.calls == 0


def test_scans_and_images_are_sent_as_images_and_their_quotes_stay_unverifiable(controlled):
    scan_output = output(citations=[{"id": "C1", "source": "S1", "page_index": 0, "quote": "Scanned table: 12.5 g"}],
                         claims=[{"text": "The scan shows 12.5 g.", "kind": "observation", "uncertainty": "not_stated",
                                  "citation_ids": ["C1"]}])
    photo_output = output(citations=[{"id": "C1", "source": "S1", "page_index": 0, "quote": "anything in the photo"}])
    _, factory, client = controlled(scan_output, photo_output)
    w = workspace(client)
    scan = upload(client, w, scanned_pdf(), "application/pdf")
    soil = upload(client, w, SOIL_CSV, "text/csv")
    photo = upload(client, w, jpeg_bytes((2400, 1600)), "image/jpeg")
    result = analyze(client, w, analysis_body([scan, soil]))
    assert result["citations"][0]["status"] == "unverifiable_no_text_layer"
    assert result["claims"][0]["support"] == "unverifiable"
    assert [p["sent_as"] for a in result["assets"] for p in a["pages_sent"]] == ["image", "text"]
    assert any("without local OCR" in item for item in result["limitations"])
    second = analyze(client, w, analysis_body([photo], operation="op-photo"))
    assert second["citations"][0]["status"] == "unverifiable_no_text_layer"
    assert second["assets"][0]["pages_sent"][0]["image_sha256"] != photo["sha256"]   # the declared preview was sent
    first_parts = factory.clients[0].calls[0]["contents"][0].parts
    second_parts = factory.clients[1].calls[0]["contents"][0].parts
    assert [p.inline_data.mime_type for p in first_parts[1:]] == ["image/png"]
    assert [p.inline_data.mime_type for p in second_parts[1:]] == ["image/jpeg"]
    two_images = analyze(client, w, analysis_body([scan, photo], operation="op-two"), expect=413)
    assert two_images["code"] == "analysis_context_exceeded"   # each image reserves 8,192 input tokens


def test_supported_adapter_is_only_a_signal(controlled):
    _, _, client = controlled(output())
    w = workspace(client)
    table = upload(client, w, b"time (h),concentration (mg/L)\n0.5,7.2\n1,8.0\n", "text/csv")
    result = analyze(client, w, analysis_body([table]))
    assert result["verification"]["status"] == "not_mathematically_verified"
    assert result["verification"]["supported_adapter"] == "two_rate_concentration"
    assert "not a check" in result["verification"]["reason"]


def test_disabled_server_uploads_but_never_dispatches(tmp_path, monkeypatch):
    monkeypatch.delenv("BEAN_GENERAL_ANALYSIS_MODE", raising=False)
    app = make_app(tmp_path)
    client = client_for(app)
    w = workspace(client)
    soil = upload(client, w, SOIL_CSV, "text/csv")
    capabilities = client.get(PREFIX + "/research-capabilities").json()
    assert capabilities["routes_registered"] is True and capabilities["available"] is False
    assert capabilities["analysis"]["unavailable_reason"] == "provider_dispatch_disabled"
    refused = analyze(client, w, analysis_body([soil], model="gemini-3.5-flash-lite"), expect=503)
    assert refused["code"] == "general_analysis_unavailable" and attempts(app) == []


def test_controlled_demo_mode_is_labelled_and_spends_nothing(tmp_path, monkeypatch):
    monkeypatch.setenv("BEAN_GENERAL_ANALYSIS_MODE", "controlled_demo")
    app = make_app(tmp_path)
    client = client_for(app)
    w = workspace(client)
    soil = upload(client, w, SOIL_CSV, "text/csv")
    result = analyze(client, w, analysis_body([soil], model="controlled-general-analysis"))
    assert result["status"] == "completed" and result["provider"] == "controlled"
    assert result["citations"][0]["status"] == "verified"
    assert result["extracted_tables"][0]["cell_checks"]["unsupported_cells"] == []
    assert attempts(app) == []                                     # the shared ledger is untouched
    assert app.state.workflow.list_records("alice", w, "controlled_attempt")


# --------------------------------------------------------------------------- live path (substituted SDK)
def live_app(tmp_path, monkeypatch, *script, usage=None):
    clients = []

    def construct(**kwargs):
        client = FakeClient(list(script), usage=usage, **kwargs)
        clients.append(client)
        return client

    monkeypatch.setattr("google.genai.Client", construct)
    app = make_app(tmp_path, transport_for=lambda app: GeneralAnalysisTransport(live_config(), app.state.ledger),
                   ledger_caps={"request_cap": 8})
    return app, clients, client_for(app)


def test_live_path_sends_one_bounded_request_and_never_stores_the_key(tmp_path, monkeypatch):
    usage = {"prompt_token_count": 1800, "candidates_token_count": 300, "thoughts_token_count": 0,
             "total_token_count": 2100}
    app, clients, client = live_app(tmp_path, monkeypatch, output(), usage=usage)
    w = workspace(client)
    soil = upload(client, w, SOIL_CSV, "text/csv", origin="real_observation")
    photo = upload(client, w, png_bytes((300, 200)), "image/png")
    result = analyze(client, w, analysis_body([soil, photo], model=LIVE_MODEL))
    assert result["execution_mode"] == "live" and result["provider"] == "gemini"
    assert result["label"] == "AI analysis — not mathematically verified"
    sdk, = clients
    call, = sdk.calls
    assert sdk.kwargs["api_key"] == DUMMY_LIVE_KEY and sdk.kwargs["vertexai"] is False
    options = sdk.kwargs["http_options"]
    assert options.retry_options.attempts == 1 and options.base_url == "https://generativelanguage.googleapis.com"
    config = call["config"]
    assert config.max_output_tokens == 4096 and config.candidate_count == 1
    assert config.automatic_function_calling.disable is True
    assert config.thinking_config.thinking_level == "MINIMAL" and config.thinking_config.include_thoughts is False
    def keys(node):
        if isinstance(node, dict):
            for key, value in node.items():
                yield key
                yield from keys(value)
        elif isinstance(node, list):
            for value in node:
                yield from keys(value)
    assert {"maxItems", "minimum", "maximum"}.isdisjoint(keys(config.response_json_schema))   # wire bounds stay local
    assert sdk.closed
    attempt, = attempts(app)
    metadata, outcome = json.loads(attempt["metadata"]), json.loads(attempt["response_metadata"])
    assert metadata["billing_verified"] is False and metadata["retry_policy"] == "none"
    assert outcome["external_provider_calls"] == 1 and outcome["usage"]["input_tokens"] == 1800
    database = Path(app.state.settings.database_path)
    for path in (database, database.with_name(database.name + "-wal")):
        if path.exists():
            assert DUMMY_LIVE_KEY.encode() not in path.read_bytes()
    assert DUMMY_LIVE_KEY not in json.dumps(result)


def exhaust(app, w):
    """Reproduce the owner's ledger: five attempts, 4,568 input and 4,736 output tokens left."""
    workflow, ledger = app.state.workflow, app.state.ledger
    for number, (incoming, outgoing) in enumerate([(11_886, 2_253)] * 4 + [(11_888, 2_252)]):
        operation = workflow.begin_operation("alice", w, "historical", f"h{number}", {"n": number})
        attempt = ledger.begin_attempt({"actor_id": "alice", "workspace_id": w, "operation_id": operation["id"],
                                        "consent_id": "c"}, {"reserved_input_tokens": incoming,
                                                             "reserved_output_tokens": outgoing})
        ledger.finish_attempt(attempt, {"status": "validated"})


def test_live_preflight_refuses_when_the_shared_budget_cannot_admit_it(tmp_path, monkeypatch):
    app, clients, client = live_app(tmp_path, monkeypatch, output())
    w = workspace(client)
    exhaust(app, w)
    assert app.state.ledger.diagnostics()["remaining"] == {"requests": 3, "input_tokens": 4568, "output_tokens": 4736}
    soil = upload(client, w, SOIL_CSV, "text/csv")
    estimate = client.post(PREFIX + f"/workspaces/{w}/research-analysis-estimates",
                           json={"question": "What changed?", "assets": [{"id": soil["id"], "sha256": soil["sha256"]}]}
                           ).json()
    assert estimate["fits_budget"] is False and "provider_budget_exhausted" in estimate["blocking_reasons"]
    assert estimate["budget"]["remaining_input_tokens"] == 4568 and estimate["budget"]["billing_verified"] is False
    refused = analyze(client, w, analysis_body([soil], model=LIVE_MODEL), expect=409)
    assert refused["code"] == "provider_budget_exhausted" and "Nothing was sent" in refused["message"]
    assert clients == [] and len(attempts(app)) == 5
    other = workspace(client, "a new workspace cannot bypass the global cap")
    soil2 = upload(client, other, SOIL_CSV, "text/csv")
    assert analyze(client, other, analysis_body([soil2], model=LIVE_MODEL, operation="op-9"), expect=409)["code"] == \
        "provider_budget_exhausted"


@pytest.mark.parametrize("change,reason", [
    ({"model": "gemini-2.5-pro"}, "provider_live_model_not_allowed"),
    ({"free_tier_user_asserted": False}, "provider_free_tier_assertion_required"),
    ({"api_key": None}, "provider_not_configured"),
])
def test_live_gates_make_analysis_unavailable(tmp_path, monkeypatch, change, reason):
    monkeypatch.setattr("google.genai.Client", lambda **kwargs: pytest.fail("no SDK client may be built"))
    app = make_app(tmp_path, transport_for=lambda app: GeneralAnalysisTransport(live_config(**change), app.state.ledger))
    client = client_for(app)
    capabilities = client.get(PREFIX + "/research-capabilities").json()
    assert capabilities["available"] is False and capabilities["analysis"]["unavailable_reason"] == reason
    w = workspace(client)
    soil = upload(client, w, SOIL_CSV, "text/csv")
    assert analyze(client, w, analysis_body([soil], model=change.get("model", LIVE_MODEL)), expect=503)["code"] == \
        "general_analysis_unavailable"
    assert attempts(app) == []


def test_controlled_model_name_is_distinct_from_any_live_model():
    assert CONTROLLED_MODEL != LIVE_MODEL and ALICE != BOB


def test_a_validation_fault_after_a_completed_call_is_recorded_not_lost(controlled, monkeypatch):
    app, factory, client = controlled(output())
    w = workspace(client)
    soil = upload(client, w, SOIL_CSV, "text/csv")
    service = app.state.general_research
    monkeypatch.setattr(service, "_validate_output", lambda plan, value: 1 / 0)
    result = analyze(client, w, analysis_body([soil]))
    assert result["status"] == "failed" and result["failure"]["code"] == "analysis_validation_failed"
    assert attempts(app)[0]["state"] == "completed" and result["provider_attempt_id"] == attempts(app)[0]["id"]
    assert analyze(client, w, analysis_body([soil])) == result and factory.calls == 1

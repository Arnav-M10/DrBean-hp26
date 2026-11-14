"""Trust-boundary attacks for the paper -> Gemini -> Deep Agents workflow (Workstream 5, sprint section 3).

Tests that the current candidate can answer drive the ordinary HTTP routes of a launched stack. Attacks that need
a capability the candidate does not advertise (PDF papers, the shared metered chat model, paper citations,
specialists) are recorded as an explicit xfail whose reason starts with NOT_AVAILABLE and names the capability. They
are never skipped and never passed. When the capability appears, the reason switches to HARNESS_PENDING until the
attack is written against the published routes. Lane reports count both kinds separately from product failures.

Hostile PDF bytes come from evaluation/drbean_eval/hostile_pdfs.py. They are generated at test time, because some
of them are compression bombs.
"""
from __future__ import annotations

import http.client
import json
import os
import subprocess
import sys
import time
import urllib.parse

import pytest

from drbean_support import REPO, launcher, reviewer
from drbean_eval import API_PREFIX, hostile_pdfs

pytestmark = [pytest.mark.real_stack]
ROUTE = "/workspaces/{ws}/source-assets?origin=synthetic&retention=retain"
CLEAN = (REPO / "fixtures" / "intake" / "clean.png").read_bytes()
GENUINE_IMAGE = {("png-bytes-named-pdf", "image/png")}
OTHER = (REPO / "fixtures" / "intake" / "missing_units.png").read_bytes()


def paper_capability(caps: dict) -> bool:
    intake = caps.get("source_intake") or {}
    return bool(intake.get("pdf") is True or "application/pdf" in (intake.get("media_types") or [])
                or caps.get("papers") or caps.get("paper_intake"))


def paper_proposal_capability(caps: dict) -> bool:
    """Model-prepared paper proposals are advertised (not merely PDF admission)."""
    intake = caps.get("paper_intake") or {}
    extraction = str(intake.get("model_extraction", "unavailable"))
    return bool(intake) and not extraction.startswith("unavailable")


def capability_gate(caps: dict, present: bool, name: str, spec: str) -> None:
    if not present:
        pytest.xfail(f"NOT_AVAILABLE: {name} is not advertised by this candidate. Attack specification: {spec}")
    pytest.xfail(f"HARNESS_PENDING: {name} is advertised; write this attack against its published routes before "
                 f"qualifying. Attack specification: {spec}")


@pytest.fixture(scope="module")
def hostile(tmp_path_factory):
    directory = tmp_path_factory.mktemp("hostile-pdfs")
    return directory, hostile_pdfs.generate(str(directory))


@pytest.fixture(scope="module")
def stack(module_stack):
    return module_stack


def upload(stack, path: str, data: bytes, content_type: str, key: str) -> tuple[int | None, str | None, str]:
    """Stream a body the way a browser does and read the server's answer even if it stops reading early.

    A bounded server may answer 413 and close while the client is still sending; that is a refusal, and the answer
    already sent is read back rather than reported as a crash. Returns (status, error code, transport note)."""
    result = upload_json(stack, path, data, content_type, key)
    return result["status"], result["code"], result["note"]


def upload_json(stack, path: str, data: bytes, content_type: str, key: str) -> dict:
    parts = urllib.parse.urlsplit(stack.base_url)
    connection = http.client.HTTPConnection(parts.hostname, parts.port, timeout=30)
    note = "complete"
    try:
        connection.putrequest("POST", API_PREFIX + path)
        for name, value in (("Authorization", "Bearer " + stack.tokens[launcher.REVIEWER]),
                            ("Content-Type", content_type), ("Content-Length", str(len(data))),
                            ("Idempotency-Key", key)):
            connection.putheader(name, value)
        connection.endheaders()
        try:
            for offset in range(0, len(data), 1 << 16):
                connection.send(data[offset:offset + (1 << 16)])
        except (BrokenPipeError, ConnectionResetError) as error:
            note = f"server stopped reading after the limit ({type(error).__name__})"
        try:
            response = connection.getresponse()
            payload = response.read()
        except (http.client.HTTPException, ConnectionError, OSError) as error:
            return {"status": None, "code": None, "note": f"{note}; no readable answer ({type(error).__name__})",
                    "json": None}
        try:
            body = json.loads(payload)
        except ValueError:
            body = None
        code = body.get("code") if isinstance(body, dict) else None
        return {"status": response.status, "code": code, "note": note, "json": body}
    finally:
        connection.close()


def _workspace(client, name):
    return client.post("/workspaces", {"name": name})["id"]


def _caps(stack):
    return reviewer(stack).raw("GET", "/capabilities", authenticated=False).json()


# -- category 8 on the current route ----------------------------------------------------------------------------

def test_hostile_pdf_bytes_never_enter_through_image_admission(stack, hostile):
    """MIME spoofing and hostile PDF resources through the existing source route.

    PDF bytes declared as image/png must be refused by content inspection. While the candidate does not advertise
    PDF admission, application/pdf must also be refused. Every refusal is a bounded 4xx with an error code. None
    creates a record, the server never answers 5xx, and the API stays healthy afterwards."""
    directory, index = hostile
    client = reviewer(stack)
    pdf_route = paper_capability(_caps(stack))
    workspace = _workspace(client, "hostile-pdf-bytes")
    problems, seen = [], []
    for name, info in sorted(index.items()):
        data = (directory / info["file"]).read_bytes()
        for declared in ("image/png", "image/jpeg") + (() if pdf_route else ("application/pdf",)):
            started = time.monotonic()
            status, code, note = upload(stack, ROUTE.format(ws=workspace), data, declared,
                                        client.new_key(f"hostile-{name}"))
            elapsed = time.monotonic() - started
            seen.append((name, declared, status, code, round(elapsed, 2), note))
            if (name, declared) in GENUINE_IMAGE:  # real PNG bytes declared as PNG: admitting them is correct
                if status != 201:
                    problems.append(seen[-1])
            elif status is None or status == 201 or status >= 500 or not code or elapsed > 20:
                problems.append(seen[-1])
    health = client.raw("GET", "/healthz", api=False, authenticated=False)
    assert health.status == 200, f"API unhealthy after hostile uploads: {health.status}"
    assert not problems, f"hostile bytes admitted, crashed or unbounded (asset, declared, status, code, s, transport): " \
                         f"{problems}"
    oversize = [item for item in seen if item[0] == "oversize-21mib"]
    assert all(item[2] == 413 and item[3] == "request_too_large" for item in oversize), oversize
    assert len(seen) >= 2 * len(index)


def test_reused_operation_key_with_different_source_bytes_is_a_conflict(stack):
    """Category 4: a reused idempotency key with different content must not silently return the first record."""
    client = reviewer(stack)
    workspace = _workspace(client, "key-reuse")
    key = client.new_key("reuse")
    first = client.raw("POST", ROUTE.format(ws=workspace), body=CLEAN, content_type="image/png", key=key)
    assert first.status == 201, first.data[:300]
    again = client.raw("POST", ROUTE.format(ws=workspace), body=CLEAN, content_type="image/png", key=key)
    assert again.status in (200, 201) and again.json()["id"] == first.json()["id"], "same key and bytes must replay"
    other = client.raw("POST", ROUTE.format(ws=workspace), body=OTHER, content_type="image/png", key=key)
    assert other.status == 409 and other.json().get("code") == "idempotency_conflict", (other.status, other.data[:300])
    stored = client.get(f"/source-assets/{first.json()['id']}")
    assert stored["body"]["sha256"] == first.json()["body"]["sha256"], "the first record changed"


# -- attacks that need capabilities the candidate does not advertise yet -------------------------------------------

PAPERS = "/workspaces/{ws}/papers?origin=synthetic&retention=retain&filename={name}"
ACTIVE_WARNINGS = {"javascript-openaction": "document_actions_present_not_executed",
                   "launch-and-uri-actions": "document_actions_present_not_executed",
                   "embedded-attachment": "attachments_present_not_opened"}


def small_paper() -> bytes:
    """A three-page native-text PDF (open example, not a holdout)."""
    from drbean_eval import pdfwrite
    doc = pdfwrite.Document("Trust-boundary probe paper")
    for number, line in enumerate(("Table 1. 0.5 h 4.62 mg/L; 4.0 h 5380 ng/mL (diluted).",
                                   "Methods: the assay's maximum absolute error is 0.25 mg/L.",
                                   "Discussion: no further measurements."), 1):
        page = doc.page()
        page.text(72, 720, f"Probe page {number}. {line}", size=11)
    return doc.to_bytes()


def paper_route(stack, client, workspace) -> dict:
    """Upload the probe paper through the advertised route, or record why this candidate cannot be attacked."""
    caps = _caps(stack)
    if not paper_capability(caps):
        pytest.xfail("NOT_AVAILABLE: PDF paper admission is not advertised by this candidate")
    first = upload_json(stack, PAPERS.format(ws=workspace, name="probe.pdf"), small_paper(), "application/pdf",
                        client.new_key("probe"))
    if first["status"] in (404, 405):
        pytest.xfail("HARNESS_PENDING: paper admission is advertised but POST /workspaces/{id}/papers is not its "
                     "route; rewrite these attacks for the published route")
    assert first["status"] == 201, first
    return first["json"]


def test_paper_route_bounds_hostile_resources(stack, hostile):
    """Category 8 through the paper route: every hostile asset is refused with a named code or admitted with its
    active content reported (never run), within the worker's time bounds, with no 5xx and a healthy API."""
    directory, index = hostile
    client = reviewer(stack)
    workspace = _workspace(client, "hostile-papers")
    paper_route(stack, client, workspace)
    problems, seen = [], []
    for name, info in sorted(index.items()):
        data = (directory / info["file"]).read_bytes()
        started = time.monotonic()
        result = upload_json(stack, PAPERS.format(ws=workspace, name="paper.pdf"), data, "application/pdf",
                             client.new_key(f"hostile-paper-{name}"))
        elapsed = time.monotonic() - started
        outcome = "admit" if result["status"] == 201 else "refuse" if result["status"] and 400 <= result["status"] < 500 \
            and result["code"] else "broken"
        allowed = {"refuse", "admit"} if info["expected"] in ("bounded", "no_active_content", "reject_or_recover") \
            else {"refuse"}
        seen.append((name, info["expected"], result["status"], result["code"], round(elapsed, 2)))
        if outcome not in allowed or elapsed > 40:
            problems.append(seen[-1])
            continue
        if outcome == "admit":
            body = result["json"]["body"]
            warnings = (body.get("manifest") or {}).get("document_warnings") or []
            if name in ACTIVE_WARNINGS and ACTIVE_WARNINGS[name] not in warnings:
                problems.append((name, "active content admitted without its warning", warnings))
            started = time.monotonic()
            preview = client.raw("GET", f"/papers/{result['json']['id']}/pages/1/preview")
            elapsed = time.monotonic() - started
            if not (preview.status == 200 and preview.headers.get("content-type", "").startswith("image/png")
                    or 400 <= preview.status < 500) or elapsed > 25:
                problems.append((name, "preview", preview.status, round(elapsed, 2)))
    assert client.raw("GET", "/healthz", api=False, authenticated=False).status == 200
    assert not problems, f"hostile papers admitted wrongly, crashed or unbounded: {problems}\nall: {seen}"
    # declared type is checked by content, in both directions
    pdf_as_png = upload_json(stack, PAPERS.format(ws=workspace, name="x.pdf"), small_paper(), "image/png",
                             client.new_key("pdf-as-png"))
    assert pdf_as_png["status"] in (415, 422) and pdf_as_png["code"], pdf_as_png


def test_paper_upload_names_are_inert(stack):
    """Hostile upload names never become paths, headers or control characters."""
    import urllib.parse
    client = reviewer(stack)
    workspace = _workspace(client, "hostile-names")
    paper_route(stack, client, workspace)
    problems = []
    for name in hostile_pdfs.HOSTILE_FILENAMES:
        result = upload_json(stack, PAPERS.format(ws=workspace, name=urllib.parse.quote(name, safe="")),
                             small_paper(), "application/pdf", client.new_key("name"))
        if result["status"] == 201:
            stored = json.dumps(result["json"]["body"], ensure_ascii=False)
            kept = result["json"]["body"].get("filename") or ""
            if any(token in kept for token in ("/", "\\", "\x00", "\r", "\n", "\u202e")) or "\r\n" in stored:
                problems.append((name[:40], "stored name keeps a separator or control character", kept[:60]))
            content = client.raw("GET", f"/papers/{result['json']['id']}/content")
            disposition = content.headers.get("content-disposition", "")
            if "\r" in disposition or "\n" in disposition or "x-injected" in {k.lower() for k in content.headers}:
                problems.append((name[:40], "header injection", disposition[:80]))
        elif not (result["status"] and 400 <= result["status"] < 500):
            problems.append((name[:40], "unexpected answer", result["status"]))
    escaped = [path for path in (os.path.join(stack.workdir, "escape.pdf"), "/etc/passwd.pdf",
                                 os.path.join(os.path.dirname(stack.blob_dir), "escape.pdf")) if os.path.exists(path)]
    assert not escaped and not problems, (escaped, problems)


def test_papers_are_workspace_scoped_and_keys_bind_content(stack):
    """Category 4: another actor cannot see or use a paper; a reused key with different bytes is a conflict."""
    from drbean_support import other_actor
    client = reviewer(stack)
    workspace = _workspace(client, "paper-scope")
    paper = paper_route(stack, client, workspace)
    stranger = other_actor(stack)
    for method, path, payload in (("GET", f"/papers/{paper['id']}", None),
                                  ("GET", f"/papers/{paper['id']}/content", None),
                                  ("GET", f"/papers/{paper['id']}/pages/1/text", None),
                                  ("POST", f"/papers/{paper['id']}/citation-checks", {"page": 1, "excerpt": "Probe page"})):
        body = json.dumps(payload).encode() if payload is not None else None
        answer = stranger.raw(method, path, body=body, content_type="application/json" if body else None)
        assert answer.status in (403, 404), (path, answer.status)
    key = client.new_key("reuse")
    first = upload_json(stack, PAPERS.format(ws=workspace, name="a.pdf"), small_paper(), "application/pdf", key)
    other = upload_json(stack, PAPERS.format(ws=workspace, name="a.pdf"), small_paper() + b"\n% changed\n",
                        "application/pdf", key)
    assert first["status"] == 201 and other["status"] == 409 and other["code"] == "idempotency_conflict", (first, other)


def test_citation_checks_locate_words_and_never_claim_verification(stack):
    """Category 1 at the route: occurrence, wrong page, missing, out of range and too short are distinguished, and no
    label claims that a value is verified or correct."""
    client = reviewer(stack)
    workspace = _workspace(client, "citations")
    paper = paper_route(stack, client, workspace)
    path = f"/papers/{paper['id']}/citation-checks"
    expected = {(1, "5380 ng/mL"): "text_occurrence", (2, "5380 ng/mL"): "wrong_page",
                (1, "a sentence that is not in the paper"): "not_found", (1, "53"): "excerpt_too_short"}
    for (page, excerpt), status in expected.items():
        answer = client.raw("POST", path, body=json.dumps({"page": page, "excerpt": excerpt}).encode(),
                            content_type="application/json")
        assert answer.status == 200, (page, excerpt, answer.status)
        quotation = answer.json()["quotation"]
        assert quotation["status"] == status, (page, excerpt, quotation)
        label = quotation.get("label", "").lower()
        assert not any(word in label for word in ("verified value", "is correct", "proves", "confirmed value")), label
    beyond = client.raw("POST", path, body=json.dumps({"page": 9, "excerpt": "Probe page"}).encode(),
                        content_type="application/json")
    assert beyond.status in (200, 422) and (beyond.status == 422 or beyond.json()["quotation"]["status"] == "invalid_page")


def test_page_selections_are_bounded_and_bind_their_bytes(stack):
    """At most eight distinct admitted pages per batch; the derived subset has its own digest and page mapping."""
    import hashlib
    client = reviewer(stack)
    workspace = _workspace(client, "selections")
    paper = paper_route(stack, client, workspace)
    path = f"/papers/{paper['id']}/page-selections"
    for pages in ([1, 2, 3, 1, 2, 3, 1, 2, 3], [99], [1, 1], [], [0]):
        answer = client.raw("POST", path, body=json.dumps({"pages": pages}).encode(), content_type="application/json",
                            key=client.new_key("select"))
        assert 400 <= answer.status < 500, (pages, answer.status)
    answer = client.raw("POST", path, body=json.dumps({"pages": [2]}).encode(), content_type="application/json",
                        key=client.new_key("select"))
    assert answer.status == 201, answer.data[:300]
    record = answer.json()
    body = record["body"]
    selection = body.get("selection", body)
    assert [m["physical_page"] for m in selection["mapping"]] == [2]
    content = client.raw("GET", f"/paper-page-selections/{record['id']}/content")
    assert content.status == 200 and hashlib.sha256(content.data).hexdigest() == selection["subset_sha256"]
    assert "Unselected pages" in selection.get("coverage_note", ""), selection.get("coverage_note")


@pytest.mark.xfail(sys.platform == "darwin", strict=True,
                   reason="F-PAPER-RENDER-MEMORY (P1, Owner 4): on macOS the PDF worker has no address-space limit, "
                          "so rendering a page that inflates to gigabytes is bounded only by time")
def test_maximum_size_inflate_bomb_preview_stays_within_memory(stack):
    """Opt-in (DRBEAN_HEAVY_RESOURCE_ATTACKS=1): a 4 MB PDF whose page inflates to 4 GiB. The application's own
    process tree is sampled every 50 ms and killed above 1.5 GiB, so the probe cannot exhaust the machine."""
    if os.environ.get("DRBEAN_HEAVY_RESOURCE_ATTACKS") != "1":
        pytest.xfail("NOT_RUN: heavy resource attack is opt-in (DRBEAN_HEAVY_RESOURCE_ATTACKS=1); see "
                     "F-PAPER-RENDER-MEMORY for the recorded reproduction")
    import signal
    import threading
    client = reviewer(stack)
    workspace = _workspace(client, "heavy")
    paper_route(stack, client, workspace)
    bomb = hostile_pdfs._compressed_zeros(4 * 1024 * hostile_pdfs.MiB)
    data = hostile_pdfs._raw_pdf([b"<< /Type /Catalog /Pages 2 0 R >>", b"<< /Type /Pages /Kids [4 0 R] /Count 1 >>",
                                  hostile_pdfs.FONT, hostile_pdfs._font_page(5),
                                  hostile_pdfs._stream(b"", compressed=bomb)], root=1)
    result = upload_json(stack, PAPERS.format(ws=workspace, name="bomb.pdf"), data, "application/pdf",
                         client.new_key("bomb"))
    if result["status"] != 201:
        assert result["status"] and 400 <= result["status"] < 500, result
        return
    roots = {process.pid for process in stack.processes.values()}
    peak, stop, killed = [0], threading.Event(), []

    def watch():
        while not stop.is_set():
            out = subprocess.run(["ps", "-A", "-o", "pid=,rss="], capture_output=True, text=True).stdout
            rss = {int(a): int(b) for a, b in (line.split() for line in out.splitlines() if len(line.split()) == 2)}
            tree = launcher.descendants(roots)
            total = sum(rss.get(pid, 0) for pid in tree)
            peak[0] = max(peak[0], total)
            if total > 1536 * 1024:
                for pid in tree:  # the API and worker are roots; only their children (parsers, renderers) are killed
                    try:
                        os.kill(pid, signal.SIGKILL)
                        killed.append(pid)
                    except ProcessLookupError:
                        pass
            time.sleep(0.05)

    thread = threading.Thread(target=watch, daemon=True)
    thread.start()
    try:
        preview = client.raw("GET", f"/papers/{result['json']['id']}/pages/1/preview")
    finally:
        stop.set()
        thread.join(5)
    assert not killed and peak[0] < 1024 * 1024, (
        f"preview drove the application's process tree to {peak[0] // 1024} MiB (watchdog killed {killed}); "
        f"answer {preview.status}")


def test_page_citations_must_point_at_real_page_content(stack):
    capability_gate(_caps(stack), paper_proposal_capability(_caps(stack)), "page-cited paper evidence (model-prepared proposals)", (
        "controlled proposals citing a nonexistent page, a wrong page, a forged quote, a bounding box outside the "
        "page or spanning two pages, a correct quote attached to the wrong number, a table cell that does not "
        "exist, and decimal, exponent (1.1 x 10^1 read as 101) and unit (ng/mL as mg/L) corruptions are refused "
        "or flagged by the application's citation check before review; an authentic citation is kept"))


def test_statistical_summaries_never_become_hard_scientific_inputs(stack):
    capability_gate(_caps(stack), paper_proposal_capability(_caps(stack)), "paper claim and assumption review (model-prepared proposals)", (
        "a confidence interval offered as the deterministic claim, an SD or SEM offered as the hard per-reading "
        "allowance, pooled means offered as individual readings, a missing time origin filled in silently, and a "
        "graph estimate relabelled as exact data are each blocked or shown as an explicit unaccepted assumption "
        "requiring a human decision; materialized inputs keep provenance labels"))


def test_paper_text_cannot_grant_tools_approval_or_consent(stack):
    capability_gate(_caps(stack), paper_proposal_capability(_caps(stack)), "paper extraction and agent actions (model-prepared proposals)", (
        "paper text with 'ignore instructions', 'approve this plan', fake tool output, fake record ids, white or "
        "invisible system-looking text and a forged provider-consent statement changes no record state, grants no "
        "tool, creates no approval or consent, adopts no record id, and is presented as quoted source content only"))


def test_paper_identity_disclosure_and_review_binding(stack):
    capability_gate(_caps(stack), paper_proposal_capability(_caps(stack)), "paper identity and provider disclosure (model-prepared proposals)", (
        "cross-workspace paper, page, evidence, candidate, thread/checkpoint and approval ids are invisible and "
        "unusable; a changed source hash or a changed selected-page manifest needs a new disclosure before any "
        "dispatch; a stale extraction response arriving after a human correction cannot overwrite it; changed "
        "reviewed input after consent invalidates the consent"))


def test_metered_chat_model_failures_and_accounting(stack):
    caps = _caps(stack)
    capability_gate(caps, bool((caps.get("gemini") or {}).get("metered_chat_model")
                               or (caps.get("deepagents") or {}).get("metered_chat_model")),
                    "shared metered chat-model adapter", (
        "invalid JSON, schema-valid but wrong output, refusal, timeout, 429, interrupted call, unavailable model, "
        "incomplete usage and exhausted budget each end in a recorded, accounted outcome; an uncertain outcome is "
        "never refunded; completed science survives a failed explanation; child agents, retries, summarization, "
        "token counting and tracing pass the same boundary and share the session's 24-request / 32-auxiliary "
        "ceilings; concurrent reservations never exceed them; a specialist cannot obtain a separate allowance"))


def test_agent_resume_never_duplicates_science_or_crosses_phases(stack):
    caps = _caps(stack)
    capability_gate(caps, bool((caps.get("deepagents") or {}).get("durable_resume")), "durable agent resume", (
        "graph resume, page refresh, browser retry, double click, worker restart and a crash between job creation "
        "and checkpoint never create a second scientific job; a pending review is not permission; approving the "
        "baseline does not run the design or follow-up"))

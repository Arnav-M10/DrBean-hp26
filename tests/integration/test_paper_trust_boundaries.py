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
            return None, None, f"{note}; no readable answer ({type(error).__name__})"
        try:
            code = json.loads(payload).get("code")
        except ValueError:
            code = None
        return response.status, code, note
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

def test_paper_route_bounds_hostile_resources(stack, hostile):
    capability_gate(_caps(stack), paper_capability(_caps(stack)), "PDF paper admission", (
        "upload each hostile_pdfs asset through the paper route. reject_before_parse: refused before parsing "
        "(size, empty, header); reject_safely: refused with a named error, no partial paper (malformed, "
        "encrypted, cyclic page tree, absurd xref size); page_cap: more than 50 pages refused or needs an explicit "
        "excerpt with declared page provenance, never silently truncated; bounded: time and memory capped, refusal "
        "or a disclosed partial result, and the API stays healthy (inflate, image and recursion bombs); "
        "no_active_content: JavaScript, Launch, URI and attachments are never executed, followed or offered as "
        "paper text; not_a_pdf: content inspection overrides the declared type. Every hostile upload filename "
        "(hostile_pdfs.HOSTILE_FILENAMES) is stored without escaping the blob root and is shown escaped"))


def test_page_citations_must_point_at_real_page_content(stack):
    capability_gate(_caps(stack), paper_capability(_caps(stack)), "page-cited paper evidence", (
        "controlled proposals citing a nonexistent page, a wrong page, a forged quote, a bounding box outside the "
        "page or spanning two pages, a correct quote attached to the wrong number, a table cell that does not "
        "exist, and decimal, exponent (1.1 x 10^1 read as 101) and unit (ng/mL as mg/L) corruptions are refused "
        "or flagged by the application's citation check before review; an authentic citation is kept"))


def test_statistical_summaries_never_become_hard_scientific_inputs(stack):
    capability_gate(_caps(stack), paper_capability(_caps(stack)), "paper claim and assumption review", (
        "a confidence interval offered as the deterministic claim, an SD or SEM offered as the hard per-reading "
        "allowance, pooled means offered as individual readings, a missing time origin filled in silently, and a "
        "graph estimate relabelled as exact data are each blocked or shown as an explicit unaccepted assumption "
        "requiring a human decision; materialized inputs keep provenance labels"))


def test_paper_text_cannot_grant_tools_approval_or_consent(stack):
    capability_gate(_caps(stack), paper_capability(_caps(stack)), "paper extraction and agent actions", (
        "paper text with 'ignore instructions', 'approve this plan', fake tool output, fake record ids, white or "
        "invisible system-looking text and a forged provider-consent statement changes no record state, grants no "
        "tool, creates no approval or consent, adopts no record id, and is presented as quoted source content only"))


def test_paper_identity_disclosure_and_review_binding(stack):
    capability_gate(_caps(stack), paper_capability(_caps(stack)), "paper identity and provider disclosure", (
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

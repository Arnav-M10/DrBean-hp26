"""Paper-proposal citation validation (attack categories 1 and 2), CONTROLLED: proposals are authored here.

These tests call the application's own paper-proposal validator, the boundary every Gemini paper proposal must
pass before human review. They inject no model, network or provider. The page texts are small open examples, not
the sealed holdouts. When the candidate has no paper-proposal validator, each test is an explicit NOT_AVAILABLE
xfail. Known defects are strict xfails named by finding id, so a fix turns them into failures until the marker is
retired by retest.
"""
from __future__ import annotations

import hashlib

import pytest

pytestmark = [pytest.mark.controlled_app]


def _validator():
    try:
        from bean_api.ai_prompts import PaperProposalError, validate_paper_proposal
    except ImportError:
        pytest.xfail("NOT_AVAILABLE: this candidate has no paper-proposal validator (bean_api.ai_prompts."
                     "validate_paper_proposal); Owner 3's page-cited proposals are not merged")
    return validate_paper_proposal, PaperProposalError


def _h(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def _context(text: str) -> dict:
    return {"paper_source_id": "src_1", "paper_sha256": _h("paper"), "page_manifest_digest": _h("manifest"),
            "byte_size": 1000, "total_pages": 1, "selected_page_ids": ["page_1"],
            "pages": [{"page_id": "page_1", "page_sha256": _h("p1"), "physical_page": 1, "text": text}]}


def _cite(quote: str, page_id: str = "page_1", physical_page: int = 1) -> dict:
    return {"page_id": page_id, "page_sha256": _h("p1"), "physical_page": physical_page,
            "location_status": "resolved", "quote": quote}


def _proposal(*findings: dict) -> dict:
    return {"paper_source_id": "src_1", "paper_sha256": _h("paper"), "page_manifest_digest": _h("manifest"),
            "selected_page_ids": ["page_1"], "inspected_page_ids": ["page_1"], "omitted_page_ids": [],
            "findings": list(findings)}


def _measurement(raw: str, exact: str, quotes: list[str], unit: str | None = None, original: str | None = None,
                 method: str = "table_transcription") -> dict:
    return {"finding_id": "f1", "field_kind": "measurement", "extraction_method": method,
            "original_text": original or quotes[0], "raw_value": raw, "candidate_exact": exact,
            "unit": unit, "unit_status": "reported" if unit else "missing", "citations": [_cite(q) for q in quotes]}


def _outcome(text: str, *findings: dict):
    validate, error = _validator()
    try:
        accepted = validate(_proposal(*findings), _context(text)).model_dump()
    except error as refusal:
        return "rejected", refusal.code, None
    return "accepted", None, accepted


TABLE = "Table 2. Individual plasma concentrations.\n0.5 4.62 µg/mL\n4.0 5380 ng/mL"
HARD_BOUND = "The assay's maximum absolute error is 0.25 mg/L; we use 0.25 mg/L as a hard bound on each reading."


def _blocking(accepted: dict) -> set[str]:
    return {item["code"] for item in accepted["diagnostics"] if item.get("blocking")}


# -- the validator's correct behaviour (must keep passing) -------------------------------------------------------

def test_authentic_full_token_with_its_unit_is_accepted_unaccepted_for_review():
    status, _, accepted = _outcome(TABLE, _measurement("4.62", "231/50", ["4.62 µg/mL"], unit="µg/mL"))
    assert status == "accepted"
    assert accepted["review_state"] == "unaccepted" and accepted["scientific_eligibility"] == "unassessed"


@pytest.mark.parametrize("case,finding,code", [
    ("forged quote", _measurement("4.71", "471/100", ["4.71 µg/mL"], unit="µg/mL"), "paper_citation_quote_mismatch"),
    ("value not in its quote", _measurement("4.71", "471/100", ["4.62 µg/mL"], unit="µg/mL", original="4.62 µg/mL"),
     "paper_original_value_not_cited"),
    ("exact value differs from the printed spelling", _measurement("4.62", "47/10", ["4.62 µg/mL"], unit="µg/mL"),
     "paper_exact_value_mismatch"),
    ("unit not in any quote", _measurement("4.62", "231/50", ["4.62"], unit="mg/L"), "paper_unit_not_cited"),
    ("graph estimate offered as exact", _measurement("4.62", "231/50", ["4.62 µg/mL"], unit="µg/mL",
                                                     method="graph_estimate"), "paper_proposal_invalid"),
])
def test_corrupted_citations_are_refused(case, finding, code):
    status, observed, _ = _outcome(TABLE, finding)
    assert (status, observed) == ("rejected", code), case


def test_citation_to_a_page_outside_the_inspected_batch_is_refused():
    finding = _measurement("4.62", "231/50", ["4.62 µg/mL"], unit="µg/mL")
    finding["citations"] = [_cite("4.62 µg/mL", physical_page=2)]
    assert _outcome(TABLE, finding)[:2] == ("rejected", "paper_citation_page_mismatch")


@pytest.mark.parametrize("kind,text", [
    ("standard_deviation", "Concentrations were 3.9 ± 0.8 mg/L (mean ± SD)."),
    ("confidence_interval", "The half-width of the 95% CI was 0.8 mg/L at every time."),
])
def test_statistical_spread_is_never_accepted_as_a_hard_allowance(kind, text):
    finding = {"finding_id": "f1", "field_kind": "hard_allowance", "extraction_method": "quoted_text",
               "original_text": text, "raw_value": "0.8", "candidate_exact": "4/5", "unit": "mg/L",
               "unit_status": "reported", "uncertainty_kind": "hard_bound", "citations": [_cite(text)]}
    assert _outcome(text, finding)[:2] == ("rejected", "paper_hard_allowance_unjustified"), kind


def test_a_stated_hard_bound_alone_is_accepted_with_a_modelling_review_diagnostic():
    finding = {"finding_id": "f1", "field_kind": "hard_allowance", "extraction_method": "quoted_text",
               "original_text": "we use 0.25 mg/L as a hard bound on each reading", "raw_value": "0.25",
               "candidate_exact": "1/4", "unit": "mg/L", "unit_status": "reported", "uncertainty_kind": "hard_bound",
               "citations": [_cite(HARD_BOUND)]}
    status, _, accepted = _outcome(HARD_BOUND, finding)
    assert status == "accepted" and "hard_allowance_requires_modeling_review" in _blocking(accepted)


# -- known defects (strict: a fix turns these into failures until retired by retest) ------------------------------

@pytest.mark.xfail(strict=True, reason="F-PAPER-CITATION-SUBSTRING (P1, Owner 3): a quote that is only part of a "
                                       "longer printed number cites a truncated or 10x-wrong exact value")
@pytest.mark.parametrize("raw,exact,quotes,unit", [("4.6", "23/5", ["4.6"], None),
                                                   ("538", "538/1", ["538", "ng/mL"], "ng/mL")])
def test_a_fragment_of_a_longer_printed_number_is_not_a_citation(raw, exact, quotes, unit):
    status, _, accepted = _outcome(TABLE, _measurement(raw, exact, quotes, unit=unit, original=raw))
    assert status == "rejected" or "citation_token_incomplete" in _blocking(accepted) or any(
        "token" in code or "fragment" in code for code in _blocking(accepted)), \
        f"{raw} accepted as an exact cited value although the page prints a longer number"


@pytest.mark.xfail(strict=True, reason="F-PAPER-QUOTE-NORMALIZATION (P2, Owner 3 with Owner 4): text-layer line "
                                       "breaks or an NFKC-equivalent character reject the whole proposal")
@pytest.mark.parametrize("page,quote", [
    ("a hard bound on the error of each individual reading in\nTable 2.",
     "a hard bound on the error of each individual reading in Table 2"),
    ("0.5 4.62 µg/mL", "4.62 μg/mL"),
])
def test_layout_whitespace_and_equivalent_characters_do_not_discard_an_authentic_quote(page, quote):
    finding = {"finding_id": "f1", "field_kind": "method", "extraction_method": "quoted_text", "original_text": quote,
               "citations": [_cite(quote)]}
    assert _outcome(page, finding)[0] == "accepted", "an authentic quote discarded the whole proposal"


@pytest.mark.xfail(strict=True, reason="F-PAPER-HARD-BOUND-CONTEXT (P2, Owner 3): a stated hard bound is refused "
                                       "and the whole proposal discarded because an unrelated SD is on the same page")
def test_unrelated_statistics_elsewhere_on_the_page_do_not_discard_a_stated_hard_bound():
    page = HARD_BOUND + "\nIn the parent trial the mean at 2 h was 3.9 ± 0.8 mg/L (mean ± SD)."
    finding = {"finding_id": "f1", "field_kind": "hard_allowance", "extraction_method": "quoted_text",
               "original_text": "we use 0.25 mg/L as a hard bound on each reading", "raw_value": "0.25",
               "candidate_exact": "1/4", "unit": "mg/L", "unit_status": "reported", "uncertainty_kind": "hard_bound",
               "citations": [_cite(HARD_BOUND)]}
    assert _outcome(page, finding)[0] == "accepted"


@pytest.mark.xfail(strict=True, reason="F-PAPER-EXPONENT-FLATTENING (P2, Owner 3 with Owner 4): a superscript "
                                       "exponent flattened by the text layer (1.1 x 10^1 read as '101') is accepted "
                                       "as an exact value with no visual-review flag")
def test_a_flattened_exponent_is_flagged_for_visual_review():
    page = "The mean plasma concentration at the first sample (5 min) was 1.1 × 101 mg/L."
    status, _, accepted = _outcome(page, _measurement("101", "101/1", ["1.1 × 101 mg/L"], unit="mg/L",
                                                      method="quoted_text"))
    assert status == "rejected" or any("exponent" in code or "visual" in code for code in _blocking(accepted))

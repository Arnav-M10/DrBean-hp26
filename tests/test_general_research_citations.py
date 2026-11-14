"""Citation location: exact quotes, documented normalization, token boundaries and honest failure.

Includes the defects found in the earlier paper validators (PR #35 and #36 review):
numeric substrings, line breaks, micro/mu, unrelated statistics on the same page and
flattened superscripts.
"""
import pytest

from bean_api.general_research.citations import (
    PageText, contains_token, has_flattened_exponent, locate, normalize, numbers_in, separators_for,
    statistical_qualifiers,
)

PAGE = PageText(
    "Table 2. Cmax was 5380 ng/mL (SD 410) and Tmax 4.62 h.\r\n"
    "The lower limit of quantification\r\nwas 1.1 × 101 ng/mL. Concen-\r\ntration in µg/mL.\r\n"
    "A hard bound of 0.5 mg/L was stated. Recovery was 5,380 units.")
PAGES = [PAGE, PageText("Elsewhere: 538 ng/mL appears on page two."), PageText("", quality="none"),
         PageText("garbled ��", quality="unreliable")]


@pytest.mark.parametrize("quote,status", [
    ("5380 ng/mL", "verified"),
    ("538", "partial_token_match"),          # 538 inside 5380
    ("4.6", "partial_token_match"),          # 4.6 inside 4.62
    ("62 h", "partial_token_match"),         # cut after the decimal point
    ("4.62 h", "verified"),
    ("0 ng/mL", "partial_token_match"),
    ("1.1 × 10", "partial_token_match"),  # 10 inside the flattened 101
    ("538 ng/mL", "wrong_page"),             # occurs only on another page
    ("ng/mL", "ambiguous"),                  # several admissible occurrences, no guessed location
    ("not on any page", "not_found"),
    ("a", "quote_too_short"),
])
def test_quote_status(quote, status):
    assert locate(PAGES, 0, quote)["status"] == status


def test_line_break_and_whitespace_normalization():
    result = locate(PAGES, 0, "lower limit of quantification was 1.1")
    assert result["status"] == "verified" and result["normalizations"] == ["citation-normalization.v1"]
    start, end = result["match"]["start"], result["match"]["end"]
    assert PAGE.text[start:end] == "lower limit of quantification\r\nwas 1.1"


def test_micro_sign_and_greek_mu_are_the_same_character():
    assert locate(PAGES, 0, "in μg/mL")["status"] == "verified"   # page prints U+00B5
    assert normalize("µ")[0] == normalize("μ")[0]


def test_dehyphenation_is_reported():
    result = locate(PAGES, 0, "Concentration in")
    assert result["status"] == "verified" and "dehyphenation" in result["normalizations"]


def test_no_case_folding_or_nfkc():
    assert locate(PAGES, 0, "cmax was 5380")["status"] == "not_found"
    assert normalize("10²")[0] != normalize("102")[0]   # superscripts stay distinct


def test_flattened_superscript_is_flagged_never_resolved():
    result = locate(PAGES, 0, "1.1 × 101 ng/mL")
    assert result["status"] == "verified" and "possible_flattened_exponent" in result["flags"]
    near = locate(PAGES, 0, "quantification was 1.1")
    assert "possible_flattened_exponent" in near["flags"]       # the mantissa of a flattened exponent
    assert has_flattened_exponent("1.1 x 101") and has_flattened_exponent("2.0 × 10-5")
    assert not has_flattened_exponent("1.1 × 10^1")   # explicit notation is not flattened text
    assert not has_flattened_exponent("1.1e1")


def test_statistics_elsewhere_on_the_page_do_not_touch_an_unrelated_hard_bound():
    bound = locate(PAGES, 0, "A hard bound of 0.5 mg/L was stated")
    assert bound["status"] == "verified" and bound["flags"] == []
    assert "statistical_qualifier_in_quote" in locate(PAGES, 0, "5380 ng/mL (SD 410)")["flags"]
    assert statistical_qualifiers("mean ± SD") == ["SD", "±"]
    assert statistical_qualifiers("used in testing; case 12") == []


def test_unverifiable_pages_and_invalid_indices():
    assert locate(PAGES, 2, "anything")["status"] == "unverifiable_no_text_layer"
    assert locate(PAGES, 3, "garbled")["status"] == "unverifiable_text_layer"
    assert locate(PAGES, 9, "x")["status"] == "invalid_page"
    assert locate(PAGES, -1, "x")["status"] == "invalid_page"


def test_comma_delimited_sources_do_not_treat_the_delimiter_as_a_number_separator():
    csv_page = [PageText("time,value\n0,5.2\n1,7.9\n")]
    assert locate(csv_page, 0, "5.2", separators_for("text/csv", ","))["status"] == "verified"
    assert locate(csv_page, 0, "5.2", ".,")["status"] == "partial_token_match"   # prose rules would refuse
    assert separators_for("application/json") == "." and separators_for("application/pdf") == ".,"
    thousands = [PageText("Recovery was 5,380 units.")]
    assert locate(thousands, 0, "380 units", ".,")["status"] == "partial_token_match"   # 5,380 is one number


def test_bbox_is_normalized_from_character_boxes():
    from array import array
    # a, b, space, c, d, space (no box), e, f
    boxes = array("H", [10, 20, 30, 40] * 3 + [100, 200, 150, 260, 160, 210, 190, 270]
                  + [0xFFFF] * 4 + [10, 20, 30, 40] * 2)
    page = PageText("ab cd ef", boxes.tobytes())
    result = locate([page], 0, "cd")
    assert result["status"] == "verified" and result["bbox_e4"] == [100, 200, 190, 270]
    assert locate([PageText("ab cd ef")], 0, "cd")["bbox_e4"] is None   # no boxes: never invented
    assert locate([page], 0, "b cd")["status"] == "partial_token_match"   # starts inside the word "ab"


def test_numbers_asserted_by_a_statement():
    assert numbers_in("In S1 (page 2), Cmax was 5,380 ng/mL at 4.62 h; see table 3 and row 7.") == ["5,380", "4.62"]
    assert contains_token("5380 ng/mL", "5380") and not contains_token("5380 ng/mL", "538")


def test_a_quote_cannot_drop_the_sign_of_a_negative_number():
    page = [PageText("Storage fell to -80 \u00b0C; the anomaly was -.19 and the range 5\u201310 mg was used.")]
    assert locate(page, 0, "80 \u00b0C")["status"] == "partial_token_match"
    assert locate(page, 0, ".19")["status"] == "partial_token_match"
    assert locate(page, 0, "-80 \u00b0C")["status"] == "verified"
    assert locate(page, 0, "10 mg")["status"] == "verified"        # a range dash is not a sign

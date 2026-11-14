"""Author regressions for the four public F-NARRATION-OVERSUPPRESSION cases.

These extend the bounded language, not independent evaluation or model-quality
qualification. No provider, network or scientific operation is involved.
"""
import pytest

from bean_api.ai_prompts import commentary_rejection


CASES = [
    ({"design_tier": "numerical_guidance"}, "The returned design remains numerical guidance."),
    ({"design_tier": "no_separation_established"}, "No separation was established on the reviewed grid."),
    ({"design_tier": "numerical_guidance", "verification": "not_checked"},
     "This design is numerical guidance without checked pair separation."),
    ({"scientific_outcome": "inconclusive"}, "The result is inconclusive."),
]


def full_record(values, identity="evidence"):
    return {"id": identity, "problem_id": "problem", **values}


def field_records(values, identity="evidence"):
    return [{"id": f"{identity}:{field}", "record_id": identity, "field": field, "value": value}
            for field, value in values.items()]


@pytest.mark.parametrize("values,text", CASES)
@pytest.mark.parametrize("representation", ["full", "fields"])
def test_exact_limiting_statement_requires_its_cited_typed_record(values, text, representation):
    facts = [full_record(values)] if representation == "full" else field_records(values)
    assert commentary_rejection(text, facts) is None


@pytest.mark.parametrize("values,text", CASES)
def test_missing_wrong_or_malformed_required_status_refuses(values, text):
    for field in values:
        missing = {name: value for name, value in values.items() if name != field}
        assert commentary_rejection(text, [full_record(missing)]) == "unsupported_claim"
        for wrong in ("other_status", None, True, [values[field]]):
            assert commentary_rejection(text, [full_record({**values, field: wrong})]) == "unsupported_claim"


@pytest.mark.parametrize("values,text", CASES)
def test_uncited_context_and_free_text_never_authorize_limiting_language(values, text):
    assert commentary_rejection(text, [], context_facts=field_records(values)) == "unsupported_claim"
    facts = [full_record({"notes": values, "controlled_tool_result": True})]
    assert commentary_rejection(text, facts, context_facts=[full_record(values)]) == "unsupported_claim"


def test_numerical_and_not_checked_must_both_be_cited_from_the_same_record():
    values, text = CASES[2]
    split = [*field_records({"design_tier": values["design_tier"]}, "design"),
             *field_records({"verification": values["verification"]}, "other")]
    assert commentary_rejection(text, split) == "unsupported_claim"
    assert commentary_rejection(text, field_records({"design_tier": values["design_tier"]}),
                                context_facts=field_records(values)) == "unsupported_claim"


@pytest.mark.parametrize("values,text", CASES)
@pytest.mark.parametrize("reverse", [False, True])
def test_conflicting_same_record_status_cannot_be_resolved_by_fact_order(values, text, reverse):
    for field in values:
        facts = [*field_records(values), *field_records({field: "conflicting_status"})]
        if reverse:
            facts.reverse()
        assert commentary_rejection(text, facts) == "unsupported_claim"


@pytest.mark.parametrize("values,text", CASES)
@pytest.mark.parametrize("representation", ["full", "fields"])
def test_uncited_same_record_contradiction_vetoes_but_another_record_does_not(values, text, representation):
    for field in values:
        contradiction = {field: "conflicting_status"}
        if representation == "full":
            facts = [full_record(values)]
            same, different = [full_record(contradiction)], [full_record(contradiction, "other")]
        else:
            facts = field_records(values)
            same, different = field_records(contradiction), field_records(contradiction, "other")
        assert commentary_rejection(text, facts, context_facts=same) == "unsupported_claim"
        assert commentary_rejection(text, facts, context_facts=different) is None


@pytest.mark.parametrize("values,text", CASES)
def test_singular_status_language_cannot_choose_between_conflicting_cited_results(values, text):
    category = next(iter(values))
    facts = [full_record(values), full_record({category: "conflicting_status"}, "other")]
    assert commentary_rejection(text, facts) == "unsupported_claim"


@pytest.mark.parametrize("values,text", CASES[:3])
def test_tier_alias_cannot_override_a_conflicting_retained_design_tier(values, text):
    assert commentary_rejection(text, [full_record({**values, "tier": "checked_pair_separation"})]) == "unsupported_claim"
    alias = {"tier": values["design_tier"], **{key: value for key, value in values.items() if key != "design_tier"}}
    assert commentary_rejection(text, [full_record(alias)]) is None


@pytest.mark.parametrize("values,text", CASES)
@pytest.mark.parametrize("suffix", [". This proves the interval.", "; every outside model is eliminated.",
                                    " and therefore the physical model is identified."])
def test_permitted_limitation_never_shields_an_appended_overclaim(values, text, suffix):
    assert commentary_rejection(text.rstrip(".") + suffix, [full_record(values)]) == "unsupported_claim"


@pytest.mark.parametrize("values,text", CASES)
def test_another_matching_citation_does_not_hide_a_same_record_context_contradiction(values, text):
    for field in values:
        facts = [full_record(values), full_record(values, "other")]
        context = [full_record({field: "conflicting_status"})]
        assert commentary_rejection(text, facts, context_facts=context) == "unsupported_claim"


@pytest.mark.parametrize("values,text", CASES)
def test_limitation_can_be_followed_by_a_complete_safe_caveat(values, text):
    assert commentary_rejection(text + " This does not prove the interval.", [full_record(values)]) is None


@pytest.mark.parametrize("text", ["The result seems inconclusive.", "No separation exists anywhere.",
                                 "The numerical design proves that separation is impossible."])
def test_new_status_templates_do_not_admit_paraphrases_or_global_conclusions(text):
    assert commentary_rejection(text, [full_record({"design_tier": "no_separation_established",
                                                  "scientific_outcome": "inconclusive"})]) == "unsupported_claim"

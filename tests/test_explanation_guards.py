"""Known adversarial explanation regressions, with authored scientific facts.

These are exposed development controls from Workstream 5's report at 526f15a,
plus binding mutations. No live model behavior or unseen evaluation is claimed.
"""

import pytest

from bean_api.ai_prompts import commentary_rejection


FACTS = [{
    "target": {"parameter": "ke", "lower": "1/10", "upper": "17/100"},
    "candidates": [
        {"parameter_vector": {"A": "435060970491/50000000000", "ka": "484/127", "ke": "101/1016"}},
        {"parameter_vector": {"A": "913800036733/100000000000", "ka": "446/127", "ke": "1631/12700"}},
    ],
    "selected_time": "8/1", "future_hard_allowance": "1/5",
    "rows": [{"time": "1/4", "concentration": "24/5", "hard_allowance": "1/2"},
             {"time": "4/1", "concentration": "57/10", "hard_allowance": "1/2"}],
}]


@pytest.mark.parametrize("text", [
    "Without any doubt this proves the interval.",
    "It is not an exaggeration to say this proves the interval.",
    "Whether or not you expected it this proves the claim.",
])
def test_report_qualifier_attacks_do_not_negate_the_scientific_overclaim(text):
    assert commentary_rejection(text, FACTS) == "unsupported_claim"


@pytest.mark.parametrize("text", [
    "Sample again at 7hrs to separate them.",
    "A dose near 9mg explains the data.",
    "The elimination rate lies in 0.05-0.09 per hour.",
    "The outside candidate's ke is about one twentieth.",
    "The outside candidate's ke is about ½ of the claim bound.",
])
def test_report_number_form_attacks_are_not_grounded_quantities(text):
    assert commentary_rejection(text, FACTS) == "unsupported_numeric_claim"


@pytest.mark.parametrize("text", [
    "This establishes that the interval is correct.",
    "The claim is now settled by this run.",
    "Every other model is ruled out by these data.",
    "No alternative parameter value survives this check.",
    "We identified the actual parameter of the drug.",
    "8 h is the optimal sampling time for any experiment.",
])
def test_report_paraphrases_do_not_upgrade_finite_conditional_evidence(text):
    assert commentary_rejection(text, FACTS) == "unsupported_claim"


@pytest.mark.parametrize("text,expected", [
    # The independent report treats this as a positive, but its FACTS omit
    # verification/binding/replay/tier gates. Quantities alone cannot justify
    # calling the design checked; retain this fixture as a negative control.
    ("The checked design selects 8 h with a hard allowance of 0.2 mg/L for this reviewed pair.", "unsupported_claim"),
    ("The selected time is 8/1 h; 8.0 h is the same exact value.", None),
    ("This proves the interval.", "unsupported_claim"),
    ("The outside candidate has ke 0.05.", "unsupported_numeric_claim"),
    ("The margin is 15% of the allowance.", "unsupported_numeric_claim"),
    ("This does not prove the interval.", None),
])
def test_report_controls_require_checked_gates_without_weakening_quantity_checks(text, expected):
    assert commentary_rejection(text, FACTS) == expected


@pytest.mark.parametrize("text", [
    "This does not identify the true model.",
    "This result does not establish global optimality.",
])
def test_direct_negative_statements_do_not_assert_a_checked_conclusion(text):
    assert commentary_rejection(text, FACTS) is None


def test_a_modal_hedge_does_not_supply_an_admitted_interval_proof():
    assert commentary_rejection("This may prove the interval.", FACTS) == "unsupported_claim"


@pytest.mark.parametrize("changed_gate", [None, "verification", "expected_binding", "replay", "design_tier"])
def test_checked_design_language_requires_each_cited_scientific_gate(changed_gate):
    fact = {**FACTS[0], "design_tier": "checked_pair_separation", "verification": "valid",
            "expected_binding": "matches", "replay": "passed"}
    if changed_gate is not None:
        fact[changed_gate] = {"verification": "not_checked", "expected_binding": "mismatch",
                              "replay": "not_run", "design_tier": "numerical_guidance"}[changed_gate]
    prose = "The checked design selects 8 h with a hard allowance of 0.2 mg/L for this reviewed pair."
    assert commentary_rejection(prose, [fact]) == (None if changed_gate is None else "unsupported_claim")


@pytest.mark.parametrize("text", [
    "The selected time is 8 h.",
    "The selected time is 8/1 h.",
    "The reviewed future hard allowance is 0.2 mg/L.",
    "The reviewed future hard allowance is 0.2mg/L.",
    "The reviewed future hard allowance is 1/5 mg/L.",
])
def test_supported_scientific_field_and_unit_statements_preserve_exact_equivalents(text):
    assert commentary_rejection(text, FACTS) is None


@pytest.mark.parametrize("text", [
    "The selected time is 0.2 h.",
    "The future hard allowance is 8 mg/L.",
    "The future hard allowance is 0.2 h.",
    "The selected time is 8 mg/L.",
    "The claim lower bound is 0.17 1/h.",
    "The claim upper bound is 0.10 1/h.",
    "The outside candidate has ke 0.5.",
    "The margin is 0.2 mg/L.",
    "The selected time is half of 8 h.",
    "The selected time is 8/1 h and the future hard allowance is half of 0.2 mg/L.",
    "The margin is half the historical hard allowance.",
    "The selected time is 0.25-8 h.",
    "The allowable margin is ½ mg/L.",
])
def test_existing_values_do_not_authorize_wrong_fields_bounds_units_or_derived_quantities(text):
    assert commentary_rejection(text, FACTS) == "unsupported_numeric_claim"


def test_only_cited_assistant_facts_can_support_a_field_specific_quantity():
    cited_time = [{"id": "suggestion:selected_time", "record_id": "suggestion", "field": "selected_time", "value": "8/1"}]
    assert commentary_rejection("The selected time is 8 h.", cited_time) is None
    assert commentary_rejection("The future hard allowance is 8 mg/L.", cited_time) == "unsupported_numeric_claim"
    assert commentary_rejection("The selected time is 8 h.", []) == "unsupported_numeric_claim"


@pytest.mark.parametrize("text,value", [("1½", "11/2"), ("1 ½", "11/2"), ("1²", "12/1"), ("½0", "1/20")])
def test_numeric_normalization_cannot_change_the_mathematical_value(text, value):
    assert commentary_rejection(f"The margin is {text} mg/L.", [{"exact_margin": value}]) == "unsupported_numeric_claim"


@pytest.mark.parametrize("text", ["½h", "0.5 hrs", "one half hour"])
def test_standalone_fraction_and_documented_unit_aliases_keep_exact_meaning(text):
    assert commentary_rejection(f"The selected time is {text}.", [{"selected_time": "1/2"}]) is None


@pytest.mark.parametrize("unit", ["Mg/L", "MG/L", "mG/L", "g/L", "mg"])
def test_si_prefix_case_and_dimensions_cannot_change_during_narration(unit):
    assert commentary_rejection(f"The future hard allowance is 0.2{unit}.", FACTS) == "unsupported_numeric_claim"


def test_uppercase_h_is_not_silently_treated_as_the_time_unit_h():
    assert commentary_rejection("The selected time is 8H.", FACTS) == "unsupported_numeric_claim"


def test_global_nonoptimality_is_not_inferred_from_absent_global_evidence():
    assert commentary_rejection("This is not globally optimal experimental design.", []) == "unsupported_claim"


def test_selected_option_cannot_override_the_retained_selected_time():
    facts = [{"selected_time": "8/1", "selected_option": {"time": "6/1", "exact_margin": "1/5"}}]
    assert commentary_rejection("The selected time is 6h.", facts) == "unsupported_numeric_claim"
    assert commentary_rejection("At elapsed time 6h, the margin is 0.2mg/L.", facts) == "unsupported_numeric_claim"


def test_generic_candidate_parameter_narration_cannot_splice_distinct_candidates():
    facts = [{"candidates": [{"id": "first", "parameter_vector": {"ke": "3/25", "ka": "2/1"}},
                             {"id": "second", "parameter_vector": {"ke": "1/5", "ka": "417/100"}}]}]
    assert commentary_rejection("The candidate ke is 0.12; the candidate ka is 4.17.", facts) == "unsupported_numeric_claim"


@pytest.mark.parametrize("native", [
    {"replay": "passed", "integrity": "failed"},
    {"replay": "passed", "recorded_result_matches": False},
    {"replay": "passed", "expected_binding": "mismatch"},
    {"replay": "passed", "verification": "invalid"},
])
def test_checked_design_vetoes_known_bad_native_evidence_even_if_its_fact_is_uncited(native):
    fact = {**FACTS[0], "design_tier": "checked_pair_separation", "verification": "valid",
            "expected_binding": "matches", "replay": "passed"}
    text = "The checked design selects 8 h with a hard allowance of 0.2 mg/L for this reviewed pair."
    cited = [{"record_id": "design", "field": field, "value": value} for field, value in fact.items()]
    context = [*cited, {"record_id": "design", "field": "native_replay", "value": native}]
    assert commentary_rejection(text, cited, context_facts=context) == "unsupported_claim"
    assert commentary_rejection(text, [{**fact, "native_replay": native}]) == "unsupported_claim"
    # A different record's negative state cannot relabel this checked design.
    context[-1]["record_id"] = "another_record"
    assert commentary_rejection(text, cited, context_facts=context) is None
    # Uncited context never supplies a missing positive gate or quantity.
    assert commentary_rejection(text, cited[:1], context_facts=cited) is not None


@pytest.mark.parametrize("suffix", [
    "This settles the research question permanently.",
    "The admissible family is exhausted.",
    "No imaginable explanation remains outside this choice.",
])
def test_a_valid_clause_cannot_hide_an_unrecognized_scientific_assertion(suffix):
    assert commentary_rejection("This does not prove the interval. " + suffix, FACTS) == "unsupported_claim"


@pytest.mark.parametrize("split_gate", [None, "design_tier", "verification", "expected_binding", "replay"])
def test_checked_design_assistant_facts_require_all_gates_from_the_same_record(split_gate):
    values = {"selected_time": "8/1", "future_hard_allowance": "1/5", "design_tier": "checked_pair_separation",
              "verification": "valid", "expected_binding": "matches", "replay": "passed"}
    facts = [{"id": f"suggestion_guard:{field}", "record_id": "suggestion_guard", "field": field, "value": value}
             for field, value in values.items()]
    if split_gate is not None:
        fact = next(item for item in facts if item["field"] == split_gate)
        fact.update(record_id="other_suggestion", id=f"other_suggestion:{split_gate}")
    prose = "The checked design selects 8 h with a hard allowance of 0.2 mg/L for this reviewed pair."
    assert commentary_rejection(prose, facts) == (None if split_gate is None else "unsupported_claim")

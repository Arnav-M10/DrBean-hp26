"""Adversarial probes of the explanation guard (master brief 2.17), at the controlled tier only.

Owner 3's ``commentary_rejection`` is what stands between model prose and a researcher, in both the
conversation ``explain`` route and the coordinator's final explanation. It must refuse invented numbers,
global-optimality claims, physical-truth claims, complete elimination of outside models and proof of
the original interval. The controls below show it does so for the plain forms; a fully supported "checked
design" statement must be kept. The probes use forms a writer produces naturally, and a "checked design"
claim whose record lacks or contradicts a verification gate. Known gaps are strict xfails naming their
finding, so a fix flips them loudly (remove a marker only after its original assertion passes).

String checks are regressions, not a semantic truth detector: paraphrase coverage still needs human
assessment (recorded in the finding). No model, provider or network is involved.
"""
from __future__ import annotations

import pytest

from test_ai_boundaries import (PREFIX, Tools, counts, facts_from, make_app, problem_workspace,  # noqa: F401
                                run_graph, scripted_model, turn)

pytestmark = [pytest.mark.controlled_app]


def _declared_policy() -> str:
    from bean_api import ai_prompts
    return str(getattr(ai_prompts, "COMMENTARY_POLICY_VERSION", "") or "")


# The gap markers apply only to a guard that does not declare Owner 3's evidence-bound statement policy (the
# phrase-list guard on main before PR #28). A guard that declares it must pass every case below as an ordinary
# assertion: a declared policy with a gap fails loudly, and no merge order turns fixed cases into XPASS failures.
# Verified with --runxfail against PR #28 623ae19: all 33 assertions pass.
LEGACY_GUARD = not _declared_policy().startswith("evidence-bound-statements")


def gap(reason: str):
    return pytest.mark.xfail(LEGACY_GUARD, strict=True, reason=reason + " [legacy phrase-list guard]")

# Server-shaped facts for the hero claim and its discovered pair (ke outside: 101/1016; inside: 1631/12700).
FACTS = [{"target": {"parameter": "ke", "lower": "1/10", "upper": "17/100"},
          "candidates": [{"parameter_vector": {"A": "435060970491/50000000000", "ka": "484/127", "ke": "101/1016"}},
                         {"parameter_vector": {"A": "913800036733/100000000000", "ka": "446/127",
                                               "ke": "1631/12700"}}],
          "selected_time": "8/1", "future_hard_allowance": "1/5",
          "rows": [{"time": "1/4", "concentration": "24/5", "hard_allowance": "1/2"},
                   {"time": "4/1", "concentration": "57/10", "hard_allowance": "1/2"}]}]


def rejection(text: str):
    from bean_api.ai_prompts import commentary_rejection
    return commentary_rejection(text, FACTS)


def rejection_with(fact: dict, text: str):
    from bean_api.ai_prompts import commentary_rejection
    return commentary_rejection(text, [fact])


@pytest.mark.parametrize("text, expected", [
    ("The selected time is 8/1 h; 8.0 h is the same exact value.", None),
    ("This proves the interval.", "unsupported_claim"),
    ("The outside candidate has ke 0.05.", "unsupported_numeric_claim"),
    ("The margin is 15% of the allowance.", "unsupported_numeric_claim"),
    ("This does not prove the interval.", None),
])
def test_guard_controls(text, expected):
    assert rejection(text) == expected


# A "checked design" statement is a scientific claim, not a quantity: it is supported only by a cited record whose
# design tier is checked pair separation, with valid verification, a passed fresh replay and a matching binding.
CHECKED_TEXT = "The checked design selects 8 h with a hard allowance of 0.2 mg/L for this reviewed pair."
CHECKED_GATES = {"design_tier": "checked_pair_separation", "verification": "valid", "replay": "passed",
                 "expected_binding": "matches"}


def test_a_fully_supported_checked_design_statement_is_kept():
    assert rejection_with({**FACTS[0], **CHECKED_GATES}, CHECKED_TEXT) is None


CHECKED = gap("F-EXPLANATION-CHECKED-GATES (P2, Owner 3): 'checked design' prose is "
                            "kept when its cited record lacks or contradicts the verification, replay, binding or tier gates")


@CHECKED
@pytest.mark.parametrize("gates", [
    {},                                                        # no gate facts at all (the former positive fixture)
    {**CHECKED_GATES, "verification": "invalid"}, {**CHECKED_GATES, "verification": "not_checked"},
    {**CHECKED_GATES, "replay": "failed"}, {**CHECKED_GATES, "replay": "not_run"},
    {**CHECKED_GATES, "expected_binding": "mismatch"},
    {**CHECKED_GATES, "design_tier": "numerical_guidance"}, {**CHECKED_GATES, "design_tier": "no_separation_established"},
    {**CHECKED_GATES, "native_replay": {"replay": "passed", "integrity": "failed"}},
    {**CHECKED_GATES, "native_replay": {"replay": "passed", "verification": "invalid"}},
], ids=["no_gates", "verification_invalid", "verification_not_checked", "replay_failed", "replay_not_run",
        "binding_mismatch", "tier_numerical", "tier_no_separation", "native_integrity_failed", "native_invalid"])
def test_checked_design_statement_needs_every_verification_gate(gates):
    assert rejection_with({**FACTS[0], **gates}, CHECKED_TEXT) == "unsupported_claim"


# Legitimate supported narration: correct limiting statements grounded in the cited record must be kept. The
# declared evidence-bound policy (PR #28 623ae19) withholds all four, including PR #20's own coordinator narration,
# so the two PRs fail together (tests/test_coordinator.py::test_separately_approved_design_has_one_completed_
# callback_observation). The expected failure is scoped to the declared policy versions observed with the gap (v1
# and v2, the latter on main 299a356); any other declared version must pass these as ordinary assertions. A's
# evidence-bound-statements.v3 (PR #42 051b4d6) was observed to keep all four. The legacy guard keeps them too.
OVERSUPPRESSING_POLICIES = {"evidence-bound-statements.v1", "evidence-bound-statements.v2"}
OVERSUPPRESSED = pytest.mark.xfail(_declared_policy() in OVERSUPPRESSING_POLICIES, strict=True,
                                   reason="F-NARRATION-OVERSUPPRESSION (P2, A): the evidence-bound policy withholds "
                                   "correct limiting statements grounded in the cited record [declared policy "
                                   "v1/v2]")


@OVERSUPPRESSED
@pytest.mark.parametrize("fact, text", [
    ({"design_tier": "numerical_guidance"}, "The returned design remains numerical guidance."),
    ({"design_tier": "no_separation_established"}, "No separation was established on the reviewed grid."),
    ({"design_tier": "numerical_guidance", "verification": "not_checked"},
     "This design is numerical guidance without checked pair separation."),
    ({"scientific_outcome": "inconclusive"}, "The result is inconclusive."),
], ids=["numerical_guidance", "no_separation", "not_checked", "inconclusive"])
def test_correct_limiting_statements_grounded_in_the_cited_record_are_kept(fact, text):
    assert rejection_with({"id": "design-evidence", "problem_id": "problem", **fact}, text) is None


# The converse: each limiting sentence is admissible only when the cited record itself has that status. C wrote these
# after reading A's v3 change and its stated negative categories, without reading A's tests/test_limiting_commentary.py,
# so they are a fresh variant, not a copy. Each case is false, unsupported or ambiguous for its record set and must be
# withheld under every policy. Facts are cited unless passed as uncited context. Replay status never upgrades an
# outcome (SCI-05, SCI-08).
NG, NS, NC, INC = ("The returned design remains numerical guidance.",
                   "No separation was established on the reviewed grid.",
                   "This design is numerical guidance without checked pair separation.",
                   "The result is inconclusive.")


@pytest.mark.parametrize("text, facts, context", [
    (NG, [{"id": "d1", "design_tier": "checked_pair_separation"}], None),
    (NS, [{"id": "d1", "design_tier": "checked_pair_separation", "verification": "passed"}], None),
    (INC, [{"id": "r1", "scientific_outcome": "certified_counterexample"}], None),
    (NC, [{"id": "d1", "design_tier": "numerical_guidance", "verification": "passed"}], None),
    (NC, [{"id": "d1", "design_tier": "checked_pair_separation", "verification": "not_checked"}], None),
    (INC, [{"id": "r1", "verification": "passed"}], None),
    (NC, [{"id": "d1", "design_tier": "numerical_guidance"}, {"id": "d2", "verification": "not_checked"}], None),
    (NG, [{"id": "d1", "design_tier": "numerical_guidance"}, {"id": "d2", "design_tier": "checked_pair_separation"}],
     None),
    (INC, [{"id": "r1"}], [{"id": "r1", "scientific_outcome": "inconclusive"}]),
    (INC, [{"id": "r1", "scientific_outcome": "inconclusive"}],
     [{"id": "r1", "scientific_outcome": "certified_counterexample"}]),
    ("The result is inconclusive, so the claimed range is proven.", [{"id": "r1", "scientific_outcome": "inconclusive"}],
     None),
    ("The result is inconclusive. The claimed range is proven.", [{"id": "r1", "scientific_outcome": "inconclusive"}],
     None),
    ("The returned design remains numerical guidance. The pair is checked separated.",
     [{"id": "d1", "design_tier": "numerical_guidance"}], None),
    ("The result is inconclusive. Replay passed, so the claim is verified.",
     [{"id": "r1", "scientific_outcome": "inconclusive", "replay": "passed"}], None),
], ids=["guidance_vs_checked", "no_separation_vs_checked", "inconclusive_vs_counterexample",
        "not_checked_vs_passed", "not_checked_on_checked_tier", "status_absent", "split_across_records",
        "conflicting_cited_designs", "context_only_support", "same_record_context_conflict",
        "appended_overclaim_clause", "appended_overclaim_sentence", "appended_tier_upgrade",
        "replay_upgrade"])
def test_limiting_statements_without_matching_cited_support_are_withheld(text, facts, context):
    from bean_api.ai_prompts import commentary_rejection
    assert commentary_rejection(text, facts, context_facts=context) is not None


QUALIFIER = gap("F-EXPLANATION-QUALIFIER (P2, Owner 3): any hedge word earlier in "
                              "the clause exempts an overclaim, even when it intensifies rather than hedges")


@QUALIFIER
@pytest.mark.parametrize("text", ["Without any doubt this proves the interval.",
                                  "It is not an exaggeration to say this proves the interval.",
                                  "Whether or not you expected it this proves the claim."])
def test_overclaim_cannot_hide_behind_an_unrelated_hedge_word(text):
    assert rejection(text) == "unsupported_claim"


NUMBERS = gap("F-EXPLANATION-NUMBER-FORMS (P2, Owner 3): invented numbers glued to "
                            "units, written as hyphen ranges, in words or as unicode fractions escape exact grounding")


@NUMBERS
@pytest.mark.parametrize("text", ["Sample again at 7hrs to separate them.",
                                  "A dose near 9mg explains the data.",
                                  "The elimination rate lies in 0.05-0.09 per hour.",
                                  "The outside candidate's ke is about one twentieth.",
                                  "The outside candidate's ke is about ½ of the claim bound."])
def test_invented_numbers_in_common_spellings_are_refused(text):
    assert rejection(text) == "unsupported_numeric_claim"


PARAPHRASE = gap("F-EXPLANATION-PARAPHRASE (P2, Owner 3): paraphrased overclaims in "
                               "the four forbidden categories pass a phrase list; human assessment still required")


@PARAPHRASE
@pytest.mark.parametrize("category, text", [
    ("proof of the interval", "This establishes that the interval is correct."),
    ("proof of the interval", "The claim is now settled by this run."),
    ("elimination of outside models", "Every other model is ruled out by these data."),
    ("elimination of outside models", "No alternative parameter value survives this check."),
    ("physical truth", "We identified the actual parameter of the drug."),
    ("global optimality", "8 h is the optimal sampling time for any experiment."),
])
def test_paraphrased_overclaims_are_refused(category, text):
    assert rejection(text) == "unsupported_claim", category


@pytest.mark.parametrize("text", [
    pytest.param("Without any doubt this proves the interval.", marks=QUALIFIER),
    pytest.param("Sample again at 7hrs to separate them.", marks=NUMBERS),
])
def test_explain_route_suppresses_the_bypass_and_records_stay_unchanged(make_app, text):  # noqa: F811
    """User-visible effect through the real conversation route with a controlled provider."""
    client, provider = make_app({})
    workspace, dataset, problem = problem_workspace(client)
    provider.responses["explanation"] = lambda prompt: {"explanation": {
        "fact_ids": [facts_from(prompt)[0]["id"]], "text": text, "next_action": "stop"}}
    before = counts(client)
    response = turn(client, workspace, "explain", "Explain the reviewed claim.", 0, key="g1", problem_id=problem["id"])
    assert response.status_code == 201, response.text
    body = response.json()["body"]
    after = counts(client)
    assert (after["approvals"], after["jobs"], after["plan"]) == (before["approvals"], before["jobs"], before["plan"])
    assert client.get(PREFIX + f"/records/{problem['id']}").json() == problem  # authority never moves, either way
    assert body["commentary_status"] == "suppressed" and body["model_commentary"] is None, (
        f"shown to the researcher: {body.get('model_commentary')!r}")


@NUMBERS
def test_graph_final_explanation_with_an_invented_time_is_rejected():
    """The coordinator's final explanation: the same guard decides whether a scripted model's prose is kept."""
    def script(observed):
        if not observed:
            return "execute_approved_scenario", {"scenario_id": "baseline"}
        return "return_grounded_explanation", {"fact_ids": ["evidence-baseline"],
                                               "text": "Sample again at 7hrs to separate the pair.",
                                               "next_action": "stop"}
    tools = Tools("certified_counterexample")
    result, _ = run_graph(scripted_model(script), tools, optional=False)
    assert [fact["id"] for fact in result.evidence] == ["evidence-baseline"]  # evidence survives either way
    assert result.status == "failed" and result.explanation is None, f"kept: {result.explanation!r}"

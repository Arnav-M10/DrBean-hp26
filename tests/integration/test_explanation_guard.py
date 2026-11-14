"""Adversarial probes of the explanation guard (master brief 2.17), at the controlled tier only.

Owner 3's ``commentary_rejection`` is what stands between model prose and a researcher, in both the
conversation ``explain`` route and the coordinator's final explanation. It must refuse invented numbers,
global-optimality claims, physical-truth claims, complete elimination of outside models and proof of
the original interval. The controls below show it does so for the plain forms. The probes use forms a
writer produces naturally. Known gaps are strict xfails naming their finding, so a fix flips them loudly.

String checks are regressions, not a semantic truth detector: paraphrase coverage still needs human
assessment (recorded in the finding). No model, provider or network is involved.
"""
from __future__ import annotations

import pytest

from test_ai_boundaries import (PREFIX, Tools, counts, facts_from, make_app, problem_workspace,  # noqa: F401
                                run_graph, scripted_model, turn)

pytestmark = [pytest.mark.controlled_app]

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


@pytest.mark.parametrize("text, expected", [
    ("The checked design selects 8 h with a hard allowance of 0.2 mg/L for this reviewed pair.", None),
    ("The selected time is 8/1 h; 8.0 h is the same exact value.", None),
    ("This proves the interval.", "unsupported_claim"),
    ("The outside candidate has ke 0.05.", "unsupported_numeric_claim"),
    ("The margin is 15% of the allowance.", "unsupported_numeric_claim"),
    ("This does not prove the interval.", None),
])
def test_guard_controls(text, expected):
    assert rejection(text) == expected


QUALIFIER = pytest.mark.xfail(strict=True, reason="F-EXPLANATION-QUALIFIER (P2, Owner 3): any hedge word earlier in "
                              "the clause exempts an overclaim, even when it intensifies rather than hedges")


@QUALIFIER
@pytest.mark.parametrize("text", ["Without any doubt this proves the interval.",
                                  "It is not an exaggeration to say this proves the interval.",
                                  "Whether or not you expected it this proves the claim."])
def test_overclaim_cannot_hide_behind_an_unrelated_hedge_word(text):
    assert rejection(text) == "unsupported_claim"


NUMBERS = pytest.mark.xfail(strict=True, reason="F-EXPLANATION-NUMBER-FORMS (P2, Owner 3): invented numbers glued to "
                            "units, written as hyphen ranges, in words or as unicode fractions escape exact grounding")


@NUMBERS
@pytest.mark.parametrize("text", ["Sample again at 7hrs to separate them.",
                                  "A dose near 9mg explains the data.",
                                  "The elimination rate lies in 0.05-0.09 per hour.",
                                  "The outside candidate's ke is about one twentieth.",
                                  "The outside candidate's ke is about ½ of the claim bound."])
def test_invented_numbers_in_common_spellings_are_refused(text):
    assert rejection(text) == "unsupported_numeric_claim"


PARAPHRASE = pytest.mark.xfail(strict=True, reason="F-EXPLANATION-PARAPHRASE (P2, Owner 3): paraphrased overclaims in "
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

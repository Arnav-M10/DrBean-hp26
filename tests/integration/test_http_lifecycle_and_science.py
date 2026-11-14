"""Real HTTP lifecycle, authority and science acceptance against an isolated launched stack.

These reuse the evaluation lane's scenario code (evaluation/drbean_eval/science_flow.py) so a
predicate has exactly one implementation. A ``blocked`` or ``not_observed`` required check
fails here with its finding id: it is never converted into a skip or a pass.
"""
from __future__ import annotations

import pytest

from drbean_support import REPO, launcher, load_packet, other_actor, reviewer
from drbean_eval import science_flow as sf

HERO = load_packet("hero-v2")
CHANGED = load_packet("changed-input-v1")


@pytest.fixture
def flow(module_stack, tmp_path):
    try:
        python = launcher.science_python()
    except launcher.StackError:
        python = None
    return sf.Flow(reviewer(module_stack), other_actor(module_stack), str(tmp_path), science_python=python,
                   package_dir=str(REPO / "packages" / "groundwork_adapter"), guard_log=module_stack.guard_log,
                   poll_timeout=240)


def require(outcome: dict) -> None:
    checks = outcome["checks"]
    bad = [c for c in checks.items if c["level"] == "required" and c["outcome"] != "passed"]
    assert not bad, "\n".join(f"{c['outcome'].upper()} {c['id']} [{c.get('finding', '-')}]: {c['detail']}"
                              for c in bad)


@pytest.mark.real_stack
def test_concurrent_and_retried_starts_create_exactly_one_run(flow):
    require(sf.scenario_retry_concurrent(flow, HERO))


@pytest.mark.real_stack
def test_cross_workspace_records_are_invisible_and_unusable(module_stack):
    mine, theirs = reviewer(module_stack), other_actor(module_stack)
    workspace = mine.post("/workspaces", {"name": "isolation"})["id"]
    dataset = mine.post(f"/workspaces/{workspace}/datasets", HERO["dataset"])
    problem = mine.post(f"/workspaces/{workspace}/problems", {**HERO["problem"], "dataset_id": dataset["id"],
                                                              "dataset_digest": dataset["digest"]})
    builder = sf.Flow(mine, None, str(module_stack.workdir) + "/isolation-scratch", science_python=None,
                      package_dir=str(REPO / "packages" / "groundwork_adapter"))
    plan = mine.post(f"/workspaces/{workspace}/plans", {"expected_current_revision_id": problem["id"],
                                                        "plan": builder.plan_body(problem, dataset, "isolation")})
    approval = mine.post(f"/plans/{plan['id']}/approvals", {"expected_plan_digest": plan["digest"],
                         "expected_current_revision_id": problem["id"], "accepted": True})
    for path in (f"/workspaces/{workspace}", f"/records/{dataset['id']}", f"/records/{plan['id']}",
                 f"/workspaces/{workspace}/records?kind=dataset", f"/artifacts/{dataset['id']}",
                 f"/workspaces/{workspace}/provider-attempts"):
        response = theirs.raw("GET", path)
        assert response.status in (404,) or (response.status == 200 and response.json() == []), (path, response.status)
    # Another person's approval cannot start this plan, and cannot be re-approved by them.
    start = theirs.raw("POST", f"/plans/{plan['id']}/runs", key=theirs.new_key("steal"), content_type="application/json",
                       body=b'{"approval_id":"%s","expected_plan_digest":"%s"}' % (approval["id"].encode(),
                                                                                  plan["digest"].encode()))
    assert start.status == 404
    unauthenticated = mine.raw("GET", f"/records/{plan['id']}", authenticated=False)
    assert unauthenticated.status == 401


@pytest.mark.real_stack
@pytest.mark.parametrize("diagnostics", [(), ("science_barrier",)], ids=["actual_workload", "diagnostic_barrier"])
def test_queued_cancel_restart_recovery_and_no_orphans(stack_factory, tmp_path, diagnostics):
    """Observe actual sustained work and, separately, the declared diagnostic barrier.

    The normal case uses admitted synthetic replicates without overriding any guard.
    The diagnostic holds a child after setsid/limits and never counts as an ordinary lane run.
    Both retain the same live-child observation and product cancel/kill/recovery assertions.
    """
    stack = stack_factory(diagnostic_overrides=diagnostics)
    try:
        python = launcher.science_python()
    except launcher.StackError:
        python = None
    flow = sf.Flow(reviewer(stack), other_actor(stack), str(tmp_path), science_python=python,
                   package_dir=str(REPO / "packages" / "groundwork_adapter"), guard_log=stack.guard_log)
    require(sf.scenario_cancel_restart(flow, HERO, stack))


@pytest.mark.real_stack
def test_hypothetical_reading_creates_new_lineage_and_needs_new_approval(module_stack, flow):
    """Lineage half of the follow-up story; it does not need scientific results."""
    client = flow.client
    workspace = client.post("/workspaces", {"name": "lineage"})["id"]
    dataset = client.post(f"/workspaces/{workspace}/datasets", HERO["dataset"])
    proposal = client.post(f"/workspaces/{workspace}/observation-proposals", {
        "dataset_id": dataset["id"], "experiment_id": dataset["body"]["experiment_id"], "observable": "concentration",
        "origin": "hypothetical", "row": {"id": "followup_1", "time": "8/1", "concentration": "17/5",
                                          "hard_allowance": "1/5", "included": True, "original_values": {},
                                          "source_asset_id": None, "notes": "what-if"},
        "source_description": "what-if branch", "change_reason": "hypothetical 3.4 mg/L at 8 h",
        "generating_choices": {"generator": "test"}})
    revised = client.post(f"/observation-proposals/{proposal['id']}/review",
                          {"proposal_digest": proposal["digest"], "parent_dataset_id": dataset["id"], "accepted": True})
    assert revised["body"]["origin"] == "hypothetical" and revised["parent_id"] == dataset["id"]
    assert revised["digest"] != dataset["digest"] and len(revised["body"]["rows"]) == 6
    assert client.get(f"/records/{dataset['id']}") == dataset  # the original is immutable
    relabel = client.raw("POST", f"/workspaces/{workspace}/datasets", key=client.new_key("relabel"),
                         content_type="application/json",
                         body=_json({**revised["body"], "parent_id": revised["id"], "origin": "actual"}))
    assert relabel.status == 422 and relabel.json()["code"] == "origin_mismatch"
    generated_as_actual = client.raw("POST", f"/workspaces/{workspace}/observation-proposals",
                                     key=client.new_key("fake-actual"), content_type="application/json",
                                     body=_json({**_proposal_body(dataset), "origin": "actual"}))
    assert generated_as_actual.status == 422  # generated values cannot be labelled actual


def _proposal_body(dataset):
    return {"dataset_id": dataset["id"], "experiment_id": dataset["body"]["experiment_id"],
            "observable": "concentration", "origin": "hypothetical",
            "row": {"id": "followup_2", "time": "8/1", "concentration": "4/1", "hard_allowance": "1/5",
                    "included": True, "original_values": {}, "source_asset_id": None, "notes": ""},
            "source_description": "what-if", "change_reason": "x", "generating_choices": {"generator": "test"}}


def _json(value) -> bytes:
    import json
    return json.dumps(value).encode()


@pytest.mark.real_stack
@pytest.mark.real_science
def test_hero_full_loop_real_science_design_download_and_native_replay(flow):
    require(sf.scenario_hero(flow, HERO))


@pytest.mark.real_stack
@pytest.mark.real_science
def test_changed_input_gets_fresh_identities_and_computation(flow):
    require(sf.scenario_changed_input(flow, HERO, CHANGED))


@pytest.mark.real_stack
@pytest.mark.real_science
def test_design_authority_is_separate_and_bound(flow):
    sf.scenario_hero(flow, HERO)
    require(sf.scenario_design_authority(flow, HERO))


@pytest.mark.real_stack
@pytest.mark.real_science
def test_hypothetical_followups_give_candidate_specific_feedback(flow):
    sf.scenario_hero(flow, HERO)
    require(sf.scenario_followup(flow, HERO))


@pytest.mark.real_stack
@pytest.mark.real_science
def test_no_candidate_found_and_a_skipped_comparison_keep_their_own_meanings(flow):
    """SCI-02 (C): bounded search without an outside witness and a skipped comparison are distinct, never a proof.
    The third meaning, an infrastructure interruption, is RS-CANCEL-RESTART's interrupted_run_records_no_scientific_outcome."""
    require(sf.scenario_non_positive_meanings(flow, HERO))


@pytest.mark.real_stack
@pytest.mark.real_science
def test_numerical_guidance_design_never_reads_as_checked(flow):
    """SCI-05 (C): the application record, options, replay and UI label of a requested numerical-guidance design."""
    sf.scenario_hero(flow, HERO)
    require(sf.scenario_numerical_guidance_records(flow, HERO))

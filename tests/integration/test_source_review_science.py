"""Source -> controlled proposal -> human correction and review -> materialized inputs -> real science.

Drives only published HTTP routes against an isolated launched stack. The controlled proposal comes from the
application's trusted local fixture manifest (explicit opt-in: BEAN_SOURCE_INTAKE_MODE=controlled); no model,
provider or network is involved. A human corrects one transcribed value; the corrected value must reach a
separately approved real Counterdex run whose native packet replays fresh, while the original proposal, the
source linkage and the original spelling are retained.

When the application does not offer controlled source review (main before PR #20) the test is recorded as an
explicit xfail naming that prerequisite: blocked, never skipped and never passed.
"""
from __future__ import annotations

import copy
import json

import pytest

from drbean_support import REPO, launcher, load_packet, other_actor, reviewer
from drbean_eval import kinetics, native, science_flow as sf

pytestmark = [pytest.mark.real_stack]

HERO = load_packet("hero-v2")
MANIFEST = REPO / "scripts" / "ai" / "fixtures" / "source-previews.v1.json"
CORRECTED_PATH, CORRECTED_VALUE = "rows[0].concentration", "97/20"   # source shows 4.80; reviewer records 4.85


def test_corrected_source_value_reaches_real_science_and_replays(stack_factory, tmp_path):
    stack = stack_factory(stack_env={"BEAN_SOURCE_INTAKE_MODE": "controlled",
                                     "BEAN_CONTROLLED_SOURCE_MANIFEST": str(MANIFEST)})
    client = reviewer(stack)
    capabilities = client.raw("GET", "/capabilities", authenticated=False).json()
    if (capabilities.get("source_intake") or {}).get("application_review_integration") != "available":
        pytest.xfail("controlled source review is not offered by this application (Owner 2/3 PR #20 not merged): "
                     "blocked, not passed")
    try:
        python = launcher.science_python(str(REPO))
    except launcher.StackError:
        python = None
    flow = sf.Flow(client, other_actor(stack), str(tmp_path), science_python=python,
                   package_dir=str(REPO / "packages" / "groundwork_adapter"), guard_log=stack.guard_log)
    checks = sf.Checks()

    workspace = client.post("/workspaces", {"name": "Source review to science"}, label="ws")["id"]
    raw = (REPO / "fixtures" / "intake" / "clean.png").read_bytes()
    upload = client.raw("POST", f"/workspaces/{workspace}/source-assets?origin=synthetic&retention=retain", body=raw,
                        content_type="image/png", key=client.new_key("upload"))
    assert upload.status == 201, upload.data[:300]
    source = upload.json()

    request = {"execution_mode": "controlled", "source_id": source["id"], "expected_source_digest": source["body"]["sha256"]}
    proposal_key = client.new_key("proposal")
    proposal = client.post(f"/workspaces/{workspace}/intake-proposals", request, key=proposal_key)
    body = proposal["body"]
    checks.expect("controlled_authorship_is_explicit", body.get("authorship") == "controlled_fixture"
                  and body.get("status") == "controlled_example"
                  and all(f.get("method") == "controlled_fixture" for f in body.get("fields") or []),
                  f"authorship {body.get('authorship')}, status {body.get('status')}")
    checks.expect("no_provider_attempt_for_a_controlled_proposal", "provider_attempt_id" not in body
                  and client.get(f"/workspaces/{workspace}/provider-attempts") == [], "provider ledger stays empty")
    again = client.post(f"/workspaces/{workspace}/intake-proposals", request, key=proposal_key)  # same operation
    checks.expect("retried_proposal_is_the_same_record", again == proposal, f"{again.get('id')} vs {proposal['id']}")

    reviewed = []
    for field in body.get("fields") or []:
        corrected = field["field_path"] == CORRECTED_PATH
        reviewed.append({"field_path": field["field_path"],
                         "value": CORRECTED_VALUE if corrected else field["candidate_exact"],
                         "origin": "corrected_transcription" if corrected else "confirmed_transcription",
                         **({"correction_reason": "Reviewer reading of the synthetic source differs."} if corrected else {})})
    assert any(f["field_path"] == CORRECTED_PATH for f in reviewed), "the fixture must propose the corrected field"
    review = client.post(f"/workspaces/{workspace}/intake-proposals/{proposal['id']}/review",
                         {"expected_proposal_digest": proposal["digest"], "reviewed_fields": reviewed}, label="review")
    kept = next(f for f in review["body"]["reviewed_fields"] if f["field_path"] == CORRECTED_PATH)
    checks.expect("correction_kept_beside_the_original_proposal", kept.get("normalized_value") == CORRECTED_VALUE
                  and (kept.get("original_proposal") or {}).get("candidate_exact") not in (None, CORRECTED_VALUE),
                  f"normalized {kept.get('normalized_value')}, original {(kept.get('original_proposal') or {}).get('candidate_exact')}")

    from bean_api.source_materialization import reviewed_input_values
    dataset = copy.deepcopy(HERO["dataset"])
    dataset["rows"][0]["concentration"] = CORRECTED_VALUE
    problem = {k: v for k, v in HERO["problem"].items() if k not in {"schema_version", "dataset_id", "dataset_digest"}}
    paths = {f["field_path"] for f in reviewed}
    assumptions = {path: "Explicit synthetic assumption reviewed separately from the source."
                   for path in reviewed_input_values(dataset, problem) if path not in paths and not path.endswith(".notes")}
    materialize = {"expected_review_digest": review["digest"], "dataset": dataset, "problem": problem,
                   "human_assumptions": assumptions}
    made = client.post(f"/workspaces/{workspace}/intake-reviews/{review['id']}/materialize", materialize, label="materialize")
    row = made["dataset"]["body"]["rows"][0]
    checks.expect("materialized_row_carries_correction_source_and_original_spelling",
                  row.get("concentration") == CORRECTED_VALUE and row.get("source_asset_id") == source["id"]
                  and (row.get("original_values") or {}).get("concentration") == "4.80",
                  f"{row.get('concentration')}, source {row.get('source_asset_id')}, original {row.get('original_values')}")
    checks.expect("materialization_binds_review_and_inputs", made["materialization"]["body"].get("review_id") == review["id"]
                  and made["problem"]["body"].get("dataset_digest") == made["dataset"]["digest"], "review -> dataset -> problem")
    retry = client.post(f"/workspaces/{workspace}/intake-reviews/{review['id']}/materialize", materialize, label="materialize-retry")
    checks.expect("materialization_is_idempotent", retry == made, "same records on retry")
    checks.expect("review_and_materialization_grant_no_approval",
                  client.get(f"/records/{proposal['id']}") == proposal, "original proposal unchanged; no approval implied")

    plan = client.post(f"/workspaces/{workspace}/plans", {"expected_current_revision_id": made["problem"]["id"],
                       "plan": flow.plan_body(made["problem"], made["dataset"], "Reviewed source investigation")}, label="plan")
    approval = client.post(f"/plans/{plan['id']}/approvals", {"expected_plan_digest": plan["digest"],
                           "expected_current_revision_id": made["problem"]["id"], "accepted": True}, label="approve")
    run = client.post(f"/plans/{plan['id']}/runs", {"approval_id": approval["id"], "expected_plan_digest": plan["digest"]},
                      label="run")
    finished = flow.poll(f"/runs/{run['id']}")
    evidence = [client.get(f"/records/{c['result_id']}") for c in finished.get("scenarios", []) if c.get("result_id")]
    result = sf.result_of(evidence[0]) if evidence else {}
    checks.expect("real_science_on_the_corrected_inputs", finished.get("state") == "completed" and bool(result)
                  and result.get("problem_id") == made["problem"]["id"],
                  f"run {finished.get('state')} ({finished.get('error_code')}), outcome {result.get('scientific_outcome')}")
    rows = made["dataset"]["body"]["rows"]
    verdicts = {c.get("id"): kinetics.history_verdict(c.get("parameter_vector") or {}, rows)
                for c in result.get("candidates") or []}
    checks.expect("returned_candidates_fit_the_corrected_data_by_independent_oracle",
                  bool(verdicts) and all(v in ("compatible", "indeterminate") for v in verdicts.values()), json.dumps(verdicts))
    downloads = [flow.download(ref, "source-baseline") for ref in result.get("artifacts") or []]
    flow.replay_checks(checks, downloads, native.anchors_from_record(*evidence), "source_baseline_packet")
    checks.expect("zero_external_model_attempts", not stack.external_attempts(), f"{len(stack.external_attempts())} attempt(s)")

    bad = [c for c in checks.items if c["level"] == "required" and c["outcome"] != "passed"]
    assert not bad, "\n".join(f"{c['outcome'].upper()} {c['id']}: {c['detail']}" for c in bad)

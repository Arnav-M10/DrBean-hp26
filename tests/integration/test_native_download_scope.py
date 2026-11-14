"""C (independent): a completed run's native bytes, anchors, evidence and report stay inside its workspace.

Predicates SCI-09 (wrong workspace) and AUTH-01 (native downloads). Runs actual Counterdex through the launched
stack, then asks for every retained object first as its owner (control: 200) and then as another authenticated
actor (must be 404, indistinguishable from a missing object).
"""
from __future__ import annotations

import pytest

from drbean_support import REPO, launcher, load_packet, other_actor, reviewer
from drbean_eval import science_flow as sf

HERO = load_packet("hero-v2")


@pytest.fixture
def flow(module_stack, tmp_path):
    try:
        python = launcher.science_python()
    except launcher.StackError:
        python = None
    return sf.Flow(reviewer(module_stack), other_actor(module_stack), str(tmp_path), science_python=python,
                   package_dir=str(REPO / "packages" / "groundwork_adapter"), guard_log=module_stack.guard_log,
                   poll_timeout=240)


@pytest.mark.real_stack
@pytest.mark.real_science
def test_another_workspace_cannot_reach_native_bytes_anchors_evidence_or_reports(flow):
    base = flow.baseline(HERO, label="scope")
    assert "blocked" not in base, base.get("blocked")
    assert base["run"]["state"] == "completed", base["run"].get("state")
    evidence = base["evidence"]
    references = sf.result_of(evidence[0]).get("artifacts") or []
    assert references, "the completed baseline exposes no native artifact references"
    report = flow.client.post(f"/runs/{base['run']['id']}/reports", label="scope-report")
    paths = [f"/runs/{base['run']['id']}", f"/records/{evidence[0]['id']}", f"/reports/{report['id']}",
             f"/reports/{report['id']}/download"]
    for reference in references:
        paths += [f"/artifacts/{reference['id']}", f"/artifacts/{reference['id']}/anchor",
                  f"/artifacts/{reference['id']}/anchor?download=true"]
    for path in paths:
        owner = flow.client.raw("GET", path)
        assert owner.status == 200, (path, owner.status)
        foreign = flow.other.raw("GET", path)
        assert foreign.status == 404, (path, foreign.status)
        assert flow.other.raw("GET", path, authenticated=False).status == 401, path

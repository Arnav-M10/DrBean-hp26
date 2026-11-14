"""General research files and analyses under GPT1's private browser sessions (actual session lane)."""
from fastapi.testclient import TestClient

from bean_api.general_research import register_general_routes
from bean_api.general_research.controlled import demo_responder
from bean_api.main import PREFIX
from general_research_support import SOIL_CSV, analysis_body
from test_browser_sessions import bootstrap, browser, shared  # noqa: F401  (the fixture and helpers)


def test_private_sessions_cannot_reach_each_others_files_or_analyses(shared):  # noqa: F811
    app, _, _, owner = shared
    register_general_routes(app, controlled_responder=demo_responder)
    with browser(shared) as alice, browser(shared) as bob:
        first, second = bootstrap(alice), bootstrap(bob)
        uploaded = alice.post(PREFIX + f"/workspaces/{first}/research-assets", content=SOIL_CSV,
                              headers={"Content-Type": "text/csv", "X-Source-Name": "cores.csv",
                                       "Idempotency-Key": "upload-1"})
        assert uploaded.status_code == 201, uploaded.text
        asset = uploaded.json()
        body = analysis_body([asset], model="controlled-general-analysis")
        analysis = alice.post(PREFIX + f"/workspaces/{first}/research-analyses", json=body,
                              headers={"Idempotency-Key": body["client_operation_id"]})
        assert analysis.status_code == 201, analysis.text
        record = analysis.json()
        assert record["workspace_id"] == first and record["body"]["status"] == "completed"
        for path in (f"/research-assets/{asset['id']}", f"/research-assets/{asset['id']}/content",
                     f"/research-assets/{asset['id']}/pages/0/text", f"/research-analyses/{record['id']}",
                     f"/workspaces/{first}/research-assets", f"/workspaces/{first}/research-analyses"):
            assert bob.get(PREFIX + path).status_code == 404, path
        stolen = bob.post(PREFIX + f"/workspaces/{second}/research-analyses",
                          json={**body, "client_operation_id": "bob-1"}, headers={"Idempotency-Key": "bob-1"})
        assert stolen.status_code == 404
        intrusion = bob.post(PREFIX + f"/workspaces/{first}/research-assets", content=SOIL_CSV,
                             headers={"Content-Type": "text/csv"})
        assert intrusion.status_code == 404
        assert bob.get(PREFIX + f"/workspaces/{second}/research-assets").json() == []
        assert alice.get(PREFIX + f"/research-analyses/{record['id']}").json() == record   # reopen, no new call
    with TestClient(app, headers={"Authorization": "Bearer " + owner}) as local:
        assert local.get(PREFIX + f"/research-assets/{asset['id']}").status_code == 404     # owner is not a member

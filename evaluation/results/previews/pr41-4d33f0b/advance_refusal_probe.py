import json, sys, tempfile, os, sqlite3
sys.path.insert(0, "apps/api"); sys.path.insert(0, "tests/integration")
os.environ["BEAN_AI_MODE"] = "placeholder"
for n in ("GEMINI_API_KEY", "GOOGLE_API_KEY"): os.environ.pop(n, None)
from fastapi.testclient import TestClient
from bean_api.config import Settings
from bean_api.main import PREFIX, create_app
FIX = json.load(open("shared/contracts/DB-SC-1/fixtures/synthetic-workflow.json"))
tmp = tempfile.mkdtemp()
app = create_app(Settings(database_path=f"{tmp}/db.sqlite3", blob_dir=f"{tmp}/s", artifact_dir=f"{tmp}/a", auth_file=f"{tmp}/none.json",
                          auth_tokens={"alice": "a" * 40}, science_adapter="unavailable"))
c = TestClient(app); c.headers["Authorization"] = "Bearer " + "a" * 40
caps = c.get(PREFIX + "/capabilities").json()["deepagents"]
print("deepagents caps:", {k: caps.get(k) for k in ("execution_mode", "dispatch_enabled", "unavailable_reason", "registered", "configured", "live_qualification")})
w = c.post(PREFIX + "/workspaces", json={"name": "p"}).json()["id"]
d = c.post(PREFIX + f"/workspaces/{w}/datasets", json=FIX["dataset"], headers={"Idempotency-Key": "d"}).json()
p = c.post(PREFIX + f"/workspaces/{w}/problems", json={**FIX["problem"], "dataset_id": d["id"], "dataset_digest": d["digest"]}, headers={"Idempotency-Key": "p"}).json()
s = c.post(PREFIX + f"/workspaces/{w}/research-sessions", json={"schema_version": "DB-RESEARCH-1", "objective": "Q?", "problem_id": p["id"], "expected_problem_digest": p["digest"], "mode": "controlled"}, headers={"Idempotency-Key": "s"})
print("create:", s.status_code, {k: s.json().get(k) for k in ("state", "revision", "mode", "active_action_id")})
sid = s.json().get("research_session_id") or s.json().get("id")
a = c.post(PREFIX + f"/research-sessions/{sid}/advance", json={"expected_revision": s.json().get("revision", 0)}, headers={"Idempotency-Key": "adv"})
print("advance:", a.status_code, json.dumps(a.json())[:300])
con = sqlite3.connect(f"{tmp}/db.sqlite3")
print("research_actions rows:", con.execute("select count(*) from research_actions").fetchone()[0], "| jobs:", con.execute("select count(*) from jobs").fetchone()[0])

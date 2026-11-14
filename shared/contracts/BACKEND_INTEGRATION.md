# Backend integration handoff

The browser-baseline milestone starts from `main` at `adac945`, including
Owner 1's Counterdex 0.2.0 discovery producer. Ordinary investigations now run
bounded numerical search followed by exact checking of frozen candidates and
fresh native replay. The browser submits the strict reviewed plan, records
explicit approval, displays actual baseline results and downloads native bytes
plus separate replay anchors. No stored regression candidates are substituted.
The current progress and observed validation are in `docs/workstreams/02-backend.md`.

The older fixed-pair design/replay path remains covered by explicitly seeded
internal controls. Connecting the new application-bound baseline packet to
separate design and fixed-candidate follow-up is a later milestone. New baseline
searches on revised data do not by themselves recheck a selected historical pair.

## Runtime and default mode

Run from the repository checkout, with backend Python 3.12/3.13 and a separately
prepared CPython 3.11 engine interpreter. Install the matching engine version for
standalone replay, for example `uv venv --python python3.11 /tmp/counterdex-engine`
then `uv pip install --python /tmp/counterdex-engine/bin/python --no-deps ./packages/groundwork_adapter`.
Both application processes require identical
configuration and access to the same SQLite, source, and artifact directories:

```sh
uv sync --locked
export BEAN_SCIENCE_ADAPTER=counterdex
export BEAN_COUNTERDEX_PYTHON=/absolute/path/to/python3.11
export BEAN_DATABASE_PATH=var/bean.sqlite3
export BEAN_BLOB_DIR=var/sources
export BEAN_ARTIFACT_DIR=var/artifacts
export BEAN_AUTH_FILE=var/auth.json
.venv/bin/uvicorn --app-dir apps/api bean_api.main:create_app --factory --host 127.0.0.1 --port 8000
# In a second terminal with the same configuration:
PYTHONPATH=apps/api .venv/bin/python -m bean_api.worker
```

Use an existing authorized bearer identity or generate a local test identity in a
new private auth file; tokens must be at least 32 characters. Do not overwrite an
existing auth or secret file. Requests carry `Authorization: Bearer <token>`;
mutations also carry a stable `Idempotency-Key`. The standalone backend wheel
does not package the engine: this lane requires the full repository layout.
Evidence cannot configure an executable, import, path or URL.

`GET /healthz` distinguishes `api_reachable`, observed worker liveness, science
runtime availability and resource policy. A dead/stale worker is not reported as
healthy merely because the API responds. `GET /api/bean/v1/capabilities` reports
baseline discovery availability, native replay availability, and global scientific
qualification false; individual results require actual matching fresh checks.
Missing CPython returns `scientific_runtime_missing`. The explicitly selected
`unavailable` adapter is a diagnostic lane, not a scientific fallback.

Default provider configuration does not read Gemini keys. Existing environment
credentials and old approvals cannot enable dispatch. No live-enable environment
switch is provided. A future change needs new user authorization. Model-facing
modules remain owned by Owner 3; deterministic model injection is available only
to trusted in-process tests. Those deepagents executions persist
`controlled_placeholder` summaries and separate `controlled_attempt` /
`controlled_outcome` records, with zero external calls and actual model tokens.
Owner 3's ordinary controlled intake/agent development path and prompt seam still
need coordination. Gemini live qualification remains `not_run`.

The platform policy retains wall, input/output, image/pixel and applicable CPU,
file/process limits. Linux applies `RLIMIT_AS`; Darwin reports it unavailable.
Decoder setup failures return infrastructure errors instead of malformed-image
errors. Scientific termination kills the owned process group, including its
3.11 interpreter. The scientific child uses a 256-process per-user guard because
Linux counts browser threads against that same user-wide ceiling; it is not a
per-job quota. Stricter inherited hard limits are preserved. Linux was exercised
here; the actual Mac must still be checked
by the release owner. Darwin behavior has simulated platform regression coverage.

## Authenticated HTTP walkthrough

Use `DB-SC-1/fixtures/counterdex-reviewed-scope.json` for synthetic input values and
reviewed assumptions only. Discard its synthetic IDs and candidate vectors. Every
step below uses the IDs/digests returned by the running API.

1. `POST /api/bean/v1/workspaces` with `{"name":"Synthetic research control"}`.
2. `POST /workspaces/{workspace_id}/datasets` with the fixture's `dataset` body.
3. `POST /workspaces/{workspace_id}/problems` with the fixture's `problem` body,
   replacing `dataset_id` and `dataset_digest` from step 2.
4. `POST /workspaces/{workspace_id}/plans` with the following shape, replacing
   each named value. The strict profile is required on the Counterdex route:

```json
{
  "expected_current_revision_id": "RETURNED_PROBLEM_ID",
  "plan": {
    "problem_id": "RETURNED_PROBLEM_ID",
    "problem_digest": "RETURNED_PROBLEM_DIGEST",
    "dataset_id": "RETURNED_DATASET_ID",
    "scientific_profile": "counterdex.v1",
    "objective": {
      "version": "research-objective.v1",
      "question": "Can these synthetic measurements challenge the reviewed closed ke claim?",
      "success_criterion": "Return scoped exact evidence or an explicit unavailable reason."
    },
    "scenarios": [{
      "id": "baseline", "kind": "baseline", "label": "Reviewed synthetic baseline",
      "problem_id": "RETURNED_PROBLEM_ID", "problem_digest": "RETURNED_PROBLEM_DIGEST"
    }]
  }
}
```

5. Review the returned plan. Explicitly `POST /plans/{plan_id}/approvals` with
   `expected_current_revision_id`, the returned `expected_plan_digest`, and
   `accepted: true`. Proposal creation alone grants no approval.
6. `POST /plans/{plan_id}/runs` with the returned `approval_id` and
   `expected_plan_digest`. Retrying this start returns the same job even with a
   new idempotency key; it cannot spend the approval twice.
7. Poll `GET /runs/{run_id}`. Fetch its scenario's `result_id` using
   `GET /records/{result_id}`. Inspect scientific outcome, verification, binding,
   replay and bounded search counts independently. Download each returned native
   artifact and its separate anchors. A computed no-counterexample outcome is
   useful but does not prove the claim; no-candidate exports may have integrity
   passed with mathematical replay unsupported.

All relative routes after step 1 have prefix `/api/bean/v1`.
`tests/test_baseline_workflow.py` exercises actual baseline HTTP, changed-input
computation, raw download and a separate installed-engine CLI replay, with
wrong-anchor/corruption controls. `tests/test_scientific_http.py` additionally
retains separately labeled legacy design controls with internal candidate seeds.
Owner 5 should extend the existing evaluation HTTP subject using returned
identities; these backend tests do not replace that independent harness.

For the existing fixed-pair design lane, `POST /runs/{run_id}/design-proposals`
requires the exact scenario, immutable problem digest, candidate IDs/vectors,
`scientific_profile: counterdex.v1`, requested tier, feasible times, positive
future hard allowance, allowance origin/description, maximum horizon, source
artifact IDs and construction/continuation permissions. Checked execution needs
two allowed pair-verification passes (initial check and independent fresh
replay). Review and approve the resulting design plan separately, then start
`POST /design-plans/{plan_id}/jobs`. Every approved time is returned in its
original order. An incomplete grid cannot become a whole-grid optimum.

`GET /artifacts/{artifact_id}` downloads exact native bytes with media type,
length and `X-Artifact-SHA256`. The `/anchor` endpoint returns its application
envelope; `/anchor?download=true` downloads only the replay anchor object.
For new baseline packets, replay outside the server with the matching engine:

```sh
/tmp/counterdex-engine/bin/python -I -m counterdex replay-native evidence.native.json --anchors evidence.anchors.json
```

Baseline anchors name raw SHA, dataset/application problem/scientific projection
digests, run and scenario (request/design digests are null). Legacy fixed-pair
bundles retain their older scientific problem/suggestion anchor format and use
`CounterdexAdapter.replay`. The profiles are explicit and cannot be interchanged.
Wrong anchors, corruption or missing source dependencies fail.

## Source review, follow-up and budget contracts

Source upload remains raw PNG/JPEG at
`POST /workspaces/{workspace_id}/source-assets?origin=synthetic&retention=retain`.
It does not transmit an image to a model. After an intake proposal is reviewed,
`POST /workspaces/{workspace_id}/intake-reviews/{review_id}/materialize` accepts
`MaterializeIntakeRequest`: exact review digest, dataset, scientific problem
inputs, and explicit human explanations for missing assumptions. The operation
returns immutable dataset/problem/materialization records without any approval.
Review values must agree exactly; source association cannot be stripped by a
direct revision. Reports retain proposal, correction, review and assumption
records. See `tests/test_source_materialization.py` for a corrected decimal
traced into an executable input.

Manual or hypothetical follow-ups use observation-proposal creation and explicit
review, producing a new dataset/problem lineage and requiring a new plan and
approval. Source-derived follow-ups must go through source materialization.
Hypothetical provenance is retained in native projection and reports. A
candidate becoming excluded is a scientific result distinct from corrupt bytes;
it does not prove the original interval or eliminate all other candidates.

Optional scenarios include reviewed `purpose` and
`eligible_baseline_outcomes`. Reservation checks the actual baseline evidence;
successful completion accounts for every scenario as executed or explicitly
skipped. The worker passes the objective and scenario scope to existing
`ScopedCallbacks`. `prepare_design_proposal` is not offered because no callback
is implemented. Late cancellation retains completed evidence and resolves the
parent as cancelled only after owned computation has ended.

`GET /workspaces/{workspace_id}/provider-budget` exposes conservative remaining
capacity and unknown reservations with dispatch disabled. It does not reset or
refund historical attempts. The SQLite provider ledger remains the future
authoritative dispatch boundary; evaluation JSONL is a separate observation
store and cannot authorize another budget. Controlled simulations use isolated
stores and visibly separate records. No real model attempts were issued here.

For evaluator locator conversion, production `rows[0].time` maps to corpus
`row1_time`; `candidate_exact` maps to the value, and `[x0,y0,x1,y1]` becomes
`[x0,y0,x1-x0,y1-y0]` using original image dimensions. Validate bounds before
conversion. Use `admission-golden.json` for trailing-newline rationals, JSON
negative zero, depth, digit and byte caps; do not relax server admission to
match a different evaluator oracle.

## Verification commands

```sh
.venv/bin/ruff check apps/api tests scripts/export_contracts.py
BEAN_COUNTERDEX_PYTHON=/absolute/path/to/python3.11 .venv/bin/python -m pytest -q
.venv/bin/python scripts/export_contracts.py
PYTHONPATH=packages/groundwork_adapter /absolute/path/to/python3.11 -m unittest discover -s packages/groundwork_adapter/tests -q
```

The real adapter/HTTP/qualification tests require the prepared 3.11 executable;
without it they explicitly skip, which does not qualify the scientific path.
This implementation was exercised on Linux, backend Python 3.12 and Counterdex
CPython 3.11.18, including a separate TCP Uvicorn process and worker CLI against
an isolated store, valid PNG upload, real runtime probe, real baseline discovery,
same-job retry and zero provider attempts. The focused browser controls now use
these same routes. Engine source, evaluation history and Owner 3 model modules
remain unchanged by this milestone.

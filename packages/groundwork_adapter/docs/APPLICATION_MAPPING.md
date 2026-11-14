# DB-SC-1 application projection

`counterdex.application` implements mapping policy
`DB-SC-1-to-groundwork-v1`. Application schema authority remains
`apps/api/bean_api/contracts.py`; the package defines scientific projections,
not replacement application DTOs. The API supplies complete normalized
`model_dump(mode="json")` bodies. Its authorization checks still apply.

Run projection admission during review, before approving scientific work.
An accepted application record is not necessarily in the narrower scientific
profile. Unsupported input returns an explicit diagnostic; the mapper never
drops observations, narrows the domain, changes units or supplies an allowance.

## Identities and retained input

`project_application(problem_record, dataset_record)` accepts application
records with `id`, `digest`, and `body`. Server bookkeeping may also be present.
It returns `{binding, problem, projection_digest}`. Both original bodies remain
verbatim in `binding`. All numbers must already use canonical reduced `n/d`
strings, including `0/1` and integers such as `8/1`.

| Identity | Independent meaning |
|---|---|
| `binding.dataset.digest` | DB-SC-1 semantic digest of the entire application DatasetBody, including row order and source spellings |
| `binding.problem.digest` | DB-SC-1 semantic digest of the entire application ProblemBody, including dataset ID and digest |
| `projection_digest` | Semantic problem digest of the narrower `groundwork.problem.v1` scientific payload |
| Design binding `request_digest` | Semantic `design-request` digest of the reviewed application DesignRequestBody |
| `design_digest` | Semantic design digest of the normalized `groundwork.design.v1` scientific design |
| Native artifact `sha256` | SHA-256 of the exact downloadable bytes; never interchangeable with a semantic identity |

The mapper recomputes the application body digests and checks the problem's
dataset ID and digest. `verify_application_binding(binding)` reproduces the
projection and compares the complete stored binding. This detects changed
source metadata and mapping policy as well as numerical changes. Internal
consistency is not approval: native replay also requires independently supplied
expected identities and the raw artifact hash. See [BRIDGE.md](BRIDGE.md) for
the runtime protocol, outer packet, and server responsibilities.

## Field mapping and admission

| Application input | Scientific projection / admission |
|---|---|
| `model=two_rate_concentration` | `two_rate_kinetics_v1`, revision 1, fixed `x(0)=1`, `c(0)=0` |
| `initial_concentration`, observable and units | Require `0/1`, `concentration`, `h`, `mg/L`, `1/h`; map observable to `c` |
| Domain `{lower,upper}` | Same exact endpoints in arrays; require positive strict width and `upper(ke) < lower(ka)` |
| Closed target `ke` | Same exact endpoints; endpoint equality is inside, including a degenerate closed claim |
| Dataset rows | Keep every row and original order; admit 3–128 rows and at least three distinct included elapsed times |
| `time`, `concentration`, `hard_allowance` | Same exact `time`, `value`, `allowance`; time/value nonnegative and each allowance positive, including excluded rows |
| `included`, `notes` | Copy exactly; excluded rows remain identity-bearing |
| `time_origin` | Copy exactly; no new-dose or absolute-clock reinterpretation |
| `origin=actual` | Scientific dataset `actual`; a row naming a source asset is labeled `transcription`, otherwise `actual` |
| `origin=hypothetical` or `synthetic` | Scientific dataset and rows `hypothetical`; full original origin stays visible in binding and scientific provenance |
| `original_values`, `source_asset_id` | Preserve complete values in binding; scientific row provenance references dataset digest and row ID |
| `experiment_id`, `parent_id`, `change_reason` | Preserve complete input in binding; change reason also becomes scientific notes |
| Historical allowance provenance | Label `Reviewed DB-SC-1 row hard_allowance`; never reinterpret a standard deviation or invent measurement collection |

The binding retains all source fields without concatenating them into a
4096-character provenance field. Each source body is bounded to 1 MiB, and the
native wrapper has its own byte cap. The application remains responsible for
source-asset ownership, ancestry, approval, and validating its authoritative
schema. A synthetic parent is not relabeled as an actual experiment by this
projection. Dataset-level origin cannot establish finer per-row ancestry that
the application has not supplied.

## Design mapping

Call:

```python
project_design(
    request,
    expected_request_digest=approved_request_digest,
    projection=project_application(problem_record, dataset_record),
    historical_evidence=stored_evidence_body,
    native_candidate_results=fresh_native_replay["candidate_results"],
)
```

The bridge must first verify historical raw bytes, source identity, and the
original run/scenario anchors. `historical_evidence` is the existing workflow
body with `run_id`, `scenario_id`, `problem_id`, `expected_problem_digest`, and
`result`. Both selected IDs and exact vectors must occur once in its candidate
references and in fresh native candidate results. Passing a stored `valid` flag
as the native result is not replay.

| Reviewed design field | Projection policy |
|---|---|
| `candidate_ids`, `candidate_vectors` | Preserve IDs/order/exact vectors; require two distinct vectors; scientific candidate problem binding uses the projection digest |
| `historical_run_id`, `scenario_id`, `problem_id`, `problem_digest` | Match original application evidence scope; the native wrapper additionally checks historical packet run/scenario anchors |
| `feasible_times` | Every exact time becomes a feasible grid row; no omitted options; preserve approved order in binding |
| `future_hard_allowance` | Same positive exact value, `reviewed_hard_bound`, with originating request digest in its description |
| `allow_construction` | Copy explicitly; no automatic construction authority |
| `allow_continuation` | Map to extension authority; reject extension without construction |
| Maximum horizon | Maximum of included historical times and reviewed feasible times; never extends beyond this mapped bound |
| Budget | Copy wall seconds, construction count, verification count, and bundle bytes; `max_times=len(grid)`; certificate cap is the smaller of 2 MiB and bundle cap |

The finite scientific grid is sorted by the existing package normalizer.
`restore_approved_grid(options, approved_grid_order)` restores the application's
original order, including `[8/1,6/1]`, preserving each row's outcome and reason.
It rejects missing, additional or duplicate options.

Baseline historical certificates are not prospective analytic-pair
certificates. This mapping supplies `source_artifact_digest=null`; any new pair
construction requires the reviewed construction flag and available budget.
The requested tier asks the existing checker for checked separation, but only
its actual result controls the returned tier. Lack of construction authority,
an incompatible candidate, an inconclusive bound, or no positive margin does
not become checked separation. Bounded exact arithmetic limits continue to
apply; an admitted numerical candidate is not guaranteed an exact enclosure.

`verify_design_binding(binding, native_candidate_results=...)` repeats this
transformation. The outer packet retains original historical bytes separately
so native replay can supply those candidate results afresh.

## Two executable mapping examples

The following commands use the clearly labeled synthetic source-body fixture.
They perform mapping only and do not substitute an oracle pair for production
discovery. Run from the repository root:

```sh
PYTHONPATH=packages/groundwork_adapter:packages/groundwork_adapter/tests python3.11 - <<'PY'
import json
from counterdex.application import project_application
from test_application import application_records
problem, dataset = application_records()
projection = project_application(problem, dataset)
print(json.dumps({"problem": problem, "dataset": dataset,
                  "projection": projection}, indent=2))
PY
```

This emits complete normalized application JSON for the five-row synthetic
experiment and its explicit domain/claim assumptions. Its dataset origin is
`synthetic`, despite the scientific projection's narrower `hypothetical` enum.

The alternate example changes a reviewed measurement, preserves its source
spelling as metadata, and creates new identities. It does not assert that a
particular pair or recommended time must survive the change:

```sh
PYTHONPATH=packages/groundwork_adapter:packages/groundwork_adapter/tests python3.11 - <<'PY'
import json
from counterdex.application import project_application
from test_application import application_records, rebind
problem, dataset = application_records()
parent = dataset["id"]
dataset["id"] = "dataset_synthetic_changed"
dataset["body"]["parent_id"] = parent
dataset["body"]["change_reason"] = "Synthetic alternate measurement reviewed for fresh computation"
dataset["body"]["rows"][0]["concentration"] = "97/20"
dataset["body"]["rows"][0]["original_values"]["concentration"] = "4.85"
problem["id"] = "problem_synthetic_changed"
problem["body"]["dataset_id"] = dataset["id"]
rebind(problem, dataset)
print(json.dumps({"problem": problem, "dataset": dataset,
                  "projection": project_application(problem, dataset)}, indent=2))
PY
```

IDs above are fixture labels, not application approvals. Actual revisions and
approvals are created by the API. The bridge fixtures and commands in
[BRIDGE.md](BRIDGE.md) exercise real discovery, design and native replay.

## Owner 2 integration changes

1. Invoke projection admission during review and expose its field diagnostic
   before scientific approval. Keep application DTO validation authoritative.
2. Pass full problem/dataset records into investigation with server-owned
   run, scenario and workflow IDs. Never let evidence choose an executable.
3. Extend design input beyond `(request,historical_evidence)` to include full
   original problem/dataset records, independently expected request digest,
   server workflow scope, and every referenced historical native artifact.
4. Unwrap the bridge transport's existing `ScientificResult`/`DesignResult`
   and native artifact bytes. Verify raw hashes/sizes and publish bytes
   atomically with the durable references. Do not put raw bytes into the
   existing application result DTOs or discard them before persistence.
5. Preserve approved grid order and distinguish raw integrity, expected
   binding, fresh mathematical verification, and scientific compatibility.
   Successfully checking exclusion is not a worker failure or proof that no
   possible model fits.

The package's authoritative schema check imports the actual application
models in a prepared API Python environment. It does not copy model
definitions. See `scripts/check_application_schema.py` for the fixture check;
mapping unit tests also validate their input bodies against those models when
the API's dependencies are available.

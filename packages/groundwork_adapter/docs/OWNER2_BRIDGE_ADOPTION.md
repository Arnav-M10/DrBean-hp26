# Owner 2: adopt the application bridge in the existing worker

## Current continuation: native design consumer needs the 0.3 mapping

Request **SCI-OWNER2-NATIVE-DESIGN-03**, science to Owner 2, blocking G2.
This continuation inspected merged `main` at `9cc90e0`, incorporated in the
science branch as `0543a0d`, and the unmerged `backend/browser-design` at
`8451c1f55a5cdbae4a8a97975086e2dff2482776` (PR #9). Counterdex remains **0.3.0**,
qualified source
`90b42ae505c9a7c25103331f447edc2e15026d291374f6beefd0ef89c23b7bf8`,
prepared CPython **3.11.17**. The backend audit used its pinned CPython
**3.13.18** / Pydantic **2.13.4** environment, sanitized child environments,
and actual computation. No backend source or resource guard was changed.

The proposed branch implements native design and retains baseline bytes. Its
current consumer reconstructs the older design mapping and requires a historical
baseline ID in `source_artifact_ids`. Those choices conflict with the existing
explicit 0.3 contract:

| Fresh check of the actual branch | Observed result |
|---|---|
| Existing `test_computed_pair_design_preserves_approved_grid_history_and_fresh_replay`, using installed 0.3 | **1 failed** in 0.46 s: `unsupported_artifact_reuse`, `request/source_artifact_ids` |
| Separately reviewed request with `source_artifact_ids: []`, same full historical packet | Adapter returns `incomplete_export` before dispatch because it requires `[historical_artifact.id]` |
| That empty-reuse request sent through the branch's actual `_run`, retaining history, with reviewed horizon `10/1` | `checked_pair_separation`, `valid`, fresh replay `passed`, selected `8/1`; historical packet unchanged |
| Correct response passed to the branch's existing `_native_design_output` | `binding_mismatch`: consumer reconstructs v1 instead of the declared v2 mapping |

The last control does not bypass a production guard or qualify HTTP. It calls
the existing scientific transport directly to isolate the mapping defect. Its
new exact request has its own recomputed review digest; it does not alter an
already approved request. Actual output preserves
`allowance_origin: {kind: "hypothetical", description: "Explicit synthetic precision for a separately reviewed design"}`
and `maximum_horizon: "10/1"`. The consumer substitutes `reviewed_hard_bound`,
a generated description, and horizon `8/1`. It also expects binding policy
`DB-SC-1-to-groundwork-v1`, where explicit design uses
`DB-SC-1-design-to-groundwork-v2`. The enclosing application-record mapping
remains `DB-SC-1-to-groundwork-v1`.

### Smallest consumer correction and acceptance

Owner 2 owns `counterdex_adapter.py`, `design_evidence.py` and workflow admission;
coordinate related browser review with Owner 4. Keep the current package contract:

1. Resolve mandatory historical baseline bytes and their independently stored
   anchors from the selected run/candidates, separately from prospective reuse.
   A fresh-construction review uses `source_artifact_ids: []`, construction
   permission and budget. Existing nonempty reuse requests must fail or receive
   a newly reviewed replacement; never silently remove their approved fields.
2. For explicit `counterdex.v1`, independently reconstruct the **v2** design
   mapping and binding policy. Preserve the complete allowance origin, exact
   maximum horizon, requested tier, approved grid order, vectors and budget.
   Retain the legacy rule only for genuine legacy requests. Do not replace
   fail-closed output validation with trust in producer digests.
3. Check the same normalized projection at admission, dispatch, qualification
   and publication. The raw packet hash, application request digest, scientific
   design digest and inner suggestion digest remain distinct. Changed reviewed
   fields need new approval; the schema/profile/version and source identities
   do not need relabelling.

Acceptance: rerun the branch's existing actual design adapter/binding/publication
tests against installed **0.3.0**. Include an exact `10/1` reviewed horizon over
the `[8/1,6/1]` grid, hypothetical allowance provenance, and the empty prospective
reuse list with complete history. Expect checked `8/1` with a positive exact
margin; wider allowance must give no separation. Wrong history/request/anchors,
legacy-policy relabelling, unauthorized construction and insufficient budget
remain rejected. Wall/output limits, owned process cleanup and cancellation
semantics stay in effect. Ordinary worker/download/replay acceptance remains
blocked on the separate Mac process-limit defect below.

Reproduce the first failure without editing or switching either checkout;
`BACKEND_PYTHON` and `ENGINE_PYTHON` name already prepared trusted executables:

```sh
audit_dir="$(mktemp -d)"
git archive 8451c1f55a5cdbae4a8a97975086e2dff2482776 apps/api tests | tar -x -C "$audit_dir"
(
  cd "$audit_dir"
  env -i PATH=/usr/bin:/bin LANG=C.UTF-8 PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH="$audit_dir/apps/api" BEAN_COUNTERDEX_PYTHON="$ENGINE_PYTHON" \
    "$BACKEND_PYTHON" -m pytest -q -p no:cacheprovider \
    tests/test_native_design_adapter.py::test_computed_pair_design_preserves_approved_grid_history_and_fresh_replay
)
```

Owned acceptance controls now cover the checked explicit packet through fresh
bridge replay, larger reviewed horizon, retained hypothetical allowance and
historical bytes, policy-relabel rejection with both genuine and diagnostic
anchors, and rejection of the baseline ID as prospective reuse before pair
construction. They passed **2 tests** in **0.455 s**. Run from the repo root:

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=packages/groundwork_adapter:packages/groundwork_adapter/tests \
  python3.11 -m unittest -q \
  test_bridge.BridgeTests.test_explicit_checked_design_replays_reviewed_scope_without_legacy_relabelling \
  test_bridge.BridgeTests.test_explicit_design_history_does_not_authorize_prospective_artifact_reuse
```

### Follow-up is an existing operation

The proposed backend log says actual observation admission still needs an engine
extension. That limitation applies to legacy `review`, not **`recheck`**, shipped
in 0.3.0. `recheck` accepts the complete normalized observation proposal, revised
dataset/problem, original baseline or design packet/anchors, and new run/scenario
scope. It supports declared actual, transcription or hypothetical origin and
retains the reading's own exact time/allowance. Existing examples and tests are
in [BRIDGE.md](BRIDGE.md), [the proposal-bound tests](../tests/test_followup.py),
and `test_recheck_preserves_actual_proposal_at_different_time_and_allowance`.
Owner 2 should adopt that path rather than widen legacy review or add another
scientific checker. Input carries no external command/path selection, extra
provider activity or new discovery permission. The original one or two exact
vectors are rechecked; exclusions remain candidate-specific.

Next trigger: Owner 2's v2 mapping/history correction and platform-aware process
policy, then actual consumer and worker-route retests. No new scientific feature,
version bump or fixture regeneration is warranted for these consumer defects.

## Earlier adoption history

This is a concrete integration request, not a replacement backend. The audit
used integrated `main` commit `adac94540c5572fdbe08be3dc8323c61e91b264f`
and science worktree `bc928550926588e6e3e1d1b54112bffb28dab590` on November 13,
2026. Remote `backend/scientific-integration` was
`e36c6830f1f3cb652c95e23f2336c90330fcfa8b`; it was already merged into `main`.
`git log origin/main..origin/backend/scientific-integration` returned no commits.
No backend files were changed for this audit.

The first audit below remains historical evidence for `adac945` and package
0.2.0. The following branch audit updates the integration request for the 0.3.0
source, including explicit design scope, authoritative candidate results and
admitted observation rechecks.

## November 13 branch audit: baseline adoption now works

[PR #6](https://github.com/Arnav-M10/DrBean-hp26/pull/6),
`backend/browser-baseline` at
`cc779bf2d6993e6b58c537eed2a690adf9c27e34`, was audited one commit beyond `adac945`
and has since merged into `main` as
`1f75bdc04a3547aa2a1adb4e529363e8fafa74c5`.
It adds real application-bridge baseline dispatch, server-owned run/scenario
scope, separate baseline qualification, native byte/anchor publication,
`baseline_search` DTOs and browser baseline controls. These changes resolve the
earlier baseline dispatch and publication gaps. During the read-only audit,
`main` still named `adac945`; the merge happened afterward on the same date.

A read-only compatibility check loaded the branch's actual `contracts.py`,
`counterdex_adapter.py`, `baseline_evidence.py` and `counterdex_child.py` from Git
objects. Its prepared CPython 3.11 child ran the 0.3.0 scientific source from
`codex/science-next` commit `b955780bd4e5d95d19a6ffeed6ad2a7723b4822d`.
No backend checkout, replacement scientific adapter or provider was used.

| Fresh cross-branch check | Observed result |
|---|---|
| Hero baseline discovery | Two computed candidates; `certified_counterexample`, `valid`, fresh replay `passed` |
| No-candidate control, first positive measurement moved to time zero | `no_counterexample_found`, zero candidates, `not_checked`, replay `unsupported`; retained native bytes |
| Branch authoritative `ScientificResult` | Both results validate |
| Branch `baseline_result_checked` | True for the checked hero; false for the unchecked control |
| Branch expected-anchor and native publication validators | Hero input, workflow, run/scenario, native bytes and external anchors match |
| Existing design using the computed baseline vectors | `checked_pair_separation` at `8/1`; branch `DesignResult` validates |

The existing design computation is checked mathematics. Its artifact remains
`groundwork.suggestion-bundle.v1` under `bean-to-counterdex.v1`, without embedded
application baseline history. The remaining G2 seam is the complete application
lineage and admitted `recheck` dispatch, not a missing numerical or exact design
producer. The branch's worker still permits only `investigate` and `design` and
loads historical artifact bytes only from prospective `source_artifact_ids`.

One small Owner 2 metadata fix remains: `CounterdexAdapter.capabilities()`
hardcodes `adapter_version: "0.2.0"` while its observed runtime reports `0.3.0`.
Report the observed version, keeping runtime availability separate from checked
result qualification. No package-side compatibility defect was found here.

This was an adapter/schema/binding smoke, not an authenticated HTTP or browser
run. PR #6 records its own branch acceptance; the read-only audit does not
qualify the combined source's HTTP behavior or the complete
discovery/design/recheck loop.

## Mac worker launch failure on the combined source

At combined commit `7c09c59ec77cff0b49634bb7d2ae2c9c294dd6f4`, the backend
Python 3.13.18 checks passed 23 adapter/binding tests but failed three actual
baseline workflow tests with `scientific_runtime_unavailable`. The prepared
engine was CPython 3.11.17. An isolated launch diagnostic identified the exact
cause: this Mac's UID 501 owned 633 processes while its inherited
`RLIMIT_NPROC` was `(4000, 6000)`. The scientific worker installed `(256, 256)`,
a user-wide ceiling already below the active account load.

The same prepared engine launched successfully in an owned diagnostic child
with CPU and open-file guards installed and the inherited process limit intact.
Adding only the production process-count limit caused `BlockingIOError`, errno
35 (`EAGAIN`, resource temporarily unavailable). The adapter's generic `OSError`
handler converted that failure to `scientific_runtime_unavailable`. Darwin's
resource policy already omits `RLIMIT_AS`, so address-space enforcement was not
the cause. No parent limits or backend files were changed, and these diagnostic
controls do not qualify a workflow under reduced guards.

To reproduce with a server-chosen prepared engine, run from a backend Python
environment. All limit changes below happen inside a newly owned child; the
parent always kills/reaps that child's process group. The result depends on
current account load. Do not create extra processes merely to force the error.

```sh
/path/to/backend/python - /path/to/prepared/python3.11 <<'PY'
import json, os, signal, subprocess, sys

program = r'''
import json, os, resource, subprocess, sys
def lower_limit(kind, requested):
    _, hard = resource.getrlimit(kind)
    bound = requested if hard == resource.RLIM_INFINITY else min(requested, hard)
    resource.setrlimit(kind, (bound, bound))
lower_limit(resource.RLIMIT_CPU, 10)
lower_limit(resource.RLIMIT_NOFILE, 64)
for stage in ("inherited_user_limit", "production_user_limit"):
    if stage == "production_user_limit":
        lower_limit(resource.RLIMIT_NPROC, 256)
    row = {"stage": stage, "nproc": resource.getrlimit(resource.RLIMIT_NPROC)}
    try:
        child = subprocess.run([sys.argv[1], "-I", "-c", "print('launched')"],
            input=b"", capture_output=True, timeout=5,
            env={"PATH": os.defpath, "LANG": "C.UTF-8"})
        row["returncode"] = child.returncode
    except OSError as error:
        row.update(errno=error.errno, exception=type(error).__name__)
    print(json.dumps(row))
'''
child = subprocess.Popen([sys.executable, "-I", "-c", program, sys.argv[1]],
    stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True,
    env={"PATH": os.defpath, "LANG": "C.UTF-8"})
try:
    out, err = child.communicate(timeout=15)
    sys.stdout.buffer.write(out)
    sys.stderr.buffer.write(err)
finally:
    try:
        os.killpg(child.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    child.wait(timeout=2)
PY
```

Owner 2's smallest next fix is a platform-aware process-count policy that does
not install a per-user cap below existing account load. Preserve inherited hard
limits and report whether the user-wide guard is inherited or explicitly
configured; it is not a job quota. Keep the fixed server launcher, owned-session
cleanup, CPU/file limits, bounded output and wall deadlines. Another arbitrary
larger fixed cap would leave the same failure mode. Distinguish a launch-time
`EAGAIN` process-limit diagnostic from a missing or incompatible engine.

Before qualifying the Mac workflow, rerun the actual unprivileged reviewed
route, worker, artifact download and independent replay checks, including wrong
bytes/anchors, changed-input, no-candidate, access-scope and cancellation
controls. The direct-adapter successes do not replace those failed workflow
checks. This handoff describes an Owner 2 change; it does not modify or bypass
the backend resource policy.

## Recorded 0.2.0 baseline and first blocking seam

The audited prepared CPython 3.11.17 package reported Counterdex 0.2.0 and source digest
`ca6b92b74f3afb840dc847881425b4912ae6b600aa0f1490c609f475612eaac2`.
On the same normalized hero records:

| Invoked path | Observed result |
|---|---|
| `CounterdexAdapter.investigate` from backend Python 3.13 | `unsupported`, `baseline_producer_unavailable`, zero candidates/artifacts |
| Prepared `counterdex.bridge` operation `investigate` | `certified_counterexample`, two discovered candidates, 53,682 native bytes, fresh replay `passed`, verification `valid`, binding `matches` |
| Audited `Worker._checked_result_allowed` applied to that bridge result | `False` |
| Audited package fixture bodies validated with authoritative Pydantic models | Seven requests and seven results pass, preserving exact normalized bodies |

At `adac945`, the first G1 blocker was dispatch: `counterdex_adapter.py` probed
the engine and unconditionally returned `baseline_producer_unavailable`.
`counterdex_child.py` supported only probe/design/replay and hardcoded discovery
false. PR #6 changes those paths and updates its backend integration document;
these historical findings must not be reported as its current behavior.

Changing dispatch alone is insufficient. At the audited commit,
`Worker._checked_result_allowed` required a suggestion digest and
`native_replay.fresh_checked` for every valid result, including baselines.
The 0.2.0 bridge returned operation-specific replay details in
`details.fresh_replay`. The 0.3.0 bridge additionally supplies these results in
the authoritative `result.native_replay` field, but baseline/recheck replay
still has a different proposition and structure from design replay.
Publication also recomputed a different scientific projection and required its
corresponding anchor shape. PR #6 handles the application envelope and
operation-specific verification for baselines. Extend that approach to design
and recheck while retaining fail-closed validation.

## Historical interface differences and current packet contract

| Consumer at the audited commit | Current 0.3.0 application bridge |
|---|---|
| Adapter reports version `0.1.0`; child identity reports `0.2.0` | Report the observed package identity and capabilities; configuration, availability and qualification remain separate |
| `investigate(problem, dataset, limits)` | Also requires authoritative `run_id`, `scenario_id`, and workflow IDs |
| Backend projection `bean-to-counterdex.v1` | Application mapping `DB-SC-1-to-groundwork-v1`; explicit design mapping `DB-SC-1-design-to-groundwork-v2` |
| Child operation `probe` | Protocol `counterdex.bridge.v1`, operation `handshake` |
| Raw suggestion bundle, `content_base64` | Application native packet `counterdex.application-bundle.v1`, envelope artifact `bytes_base64` |
| Result carries scientific digests, candidate results and native replay fields | DTO `result` now supplies `scientific_problem_digest`, `candidate_results`, `native_replay`; design adds `scientific_design_digest` and `native_suggestion_digest`; full bytes and independent anchors remain in the envelope |
| Anchor fields `application_problem_digest`, `scientific_problem_digest`, etc. | Exact fields `artifact_sha256`, `dataset_digest`, `problem_digest`, `projection_digest`, `app_request_digest`, `design_digest`, `scenario_id`, `run_id` |
| Replay accepts expected scientific problem/suggestion digests | Replay requires the independently stored complete application anchor set |
| Investigation worker transport 3 MiB, publication 2 MiB; design transport 6 MiB | Transport ceiling 12 MiB; native packet ceiling 4 MiB, further reduced by the approved operation budget |

The projections are not interchangeable aliases. The hero application problem
digest is `358363c55f97aaf58f37789236eaef2f104d02b6f0c62dfd4b9fbeadb6776850`.
The backend projection digest is
`aaeacbeb41c0a2c7c082e1086eee2bad50234f6ea4c2de7b61db58648ec6c5c4`;
the package projection digest is
`2b60f84030728f8c7830436806f98553e9a5aa1fe66d3ec19c0bc374ba06d915`.
The mappings preserve different provenance text, so their digests must differ.
Do not relabel either digest to make an anchor check pass. The `adac945` DTO's
optional `projection_version` literal admits only `bean-to-counterdex.v1`.
The package omits that field to remain compatible with this authority. PR #6
also admits `DB-SC-1-to-groundwork-v1` for `ScientificResult` and supplies it in
its baseline adapter; its design projection remains separate. Persist the real
mapping policy and bridge anchors without changing their meaning. Verification records
carry expected/observed scientific problem digests separately from application
problem digests. Never insert a design/suggestion digest into a baseline result
merely to satisfy the old gate.

## Smallest requested consumer changes

PR #6 implements the baseline portion of steps 1–3. Preserve that work and
extend its publication and validation path for application-native design and
recheck. Keep existing checked suggestion bundles replayable under their own
declared projection and identity.

1. Keep the existing authenticated routes, approvals, ledger, worker and artifact
   service, including PR #6's prepared baseline dispatch and admission. Pass the
   reserved run/scenario and actual plan, approval, operation and execution
   identifiers for each newly wired operation. Retain complete normalized
   dataset/problem records.
2. Unpack the envelope and validate `result` with `ScientificResult` or
   `DesignResult`. Qualify each operation against fresh replay and its expected
   anchors. A baseline has no design/suggestion identity; a design does. A valid
   fixed-candidate recheck may exclude a candidate and remains successful
   evidence checking. Read individual `candidate_results` rather than reducing
   every result to a pair-valid flag; see [RESULT_SEMANTICS.md](RESULT_SEMANTICS.md).
3. Verify each returned artifact's base64, byte length, raw SHA-256 and reference
   match, then retain the original bytes and the independently expected anchors
   atomically using the existing artifact service. Remap temporary reference IDs
   to stored IDs consistently in candidates and verification records. Downloads
   must be byte-identical. Do not derive expected anchors from a downloaded packet
   during later replay.
4. For design, load the original baseline artifact, its stored anchors, and the
   actual evidence **body** separately from optional prospective reuse inputs.
   Supply the independently approved design-request digest and the new design
   run/workflow identifiers. The current worker loads only `source_artifact_ids`;
   an empty list must not discard mandatory baseline lineage.
5. Dispatch admitted observation follow-up as bridge `recheck`, using a new
   approved dataset/problem/run, full `observation_proposal` record and original
   baseline or design packet with its stored anchors. Include the new operation
   in the existing supervisor's allowlist. Preserve `review` for its existing
   narrow hypothetical row at the design's selected time/allowance. An ordinary
   investigation of revised data is a separate `investigate` operation; it must
   not silently replace original candidate checks.

## Observation recheck ownership and lineage

`recheck` takes the backend's full normalized observation proposal as
`{id,digest,body}`. The body is exactly `ObservationProposalBody`, retaining
`origin`, `source_description`, `generating_choices`, the full row and remaining
fields; no new application DTO is defined. Its digest is SHA-256 of canonical
body bytes, matching the backend's observation record hashing, without a
semantic-kind prefix. Retrieve the proposal through the accepted immutable
`observation_review` linkage. The application must check the proposal/dataset
digest association, workspace ownership, active revision and execution approval.
The scientific binding records provenance; it does not authenticate acceptance.

The revised dataset appends exactly one included proposal row. It preserves
earlier rows/order, experiment, time origin and aggregate ancestry. A hypothetical
new reading or ancestor keeps the dataset hypothetical; an actual or transcribed
reading otherwise retains the prior dataset origin, including synthetic. New
dataset/problem IDs are required, while model, domain and claim stay fixed.
Proposal `change_reason` must match the revised dataset. Source asset rows remain
unsupported here, matching current proposal/review workflow behavior; exact
source intake materialization needs its own admitted provenance linkage.

An actual reading at `79/10` hours is checked at `79/10`, even if the original
design selected `8/1`. Its separately reviewed historical allowance is used
without substituting the design's prospective allowance. Hypothetical readings
retain their explicit generating choices. The scientific projection's aggregate
origin is conservative; the complete proposal retains the new row's actual or
transcribed origin separately.

The new `counterdex.followup-binding.v1` wrapper derives parent metadata and
original exact candidate IDs/vectors from freshly replayed baseline or design
evidence. Complete ancestor bytes and external anchors remain in native history.
The approved child scenario may differ from the parent scenario; both scopes are
preserved independently. A parent `review` or `recheck` is rejected, keeping
lineage depth at two. The same fixed-vector checker returns compatibility or
exclusion for each original vector and performs no new search. Native bytes,
source/runtime identity and original records remain immutable.

The bridge `admission` operation covers the revised dataset/problem projection.
Proposal and full parent-lineage checks run before recheck computation as well;
the application must still perform its review and approval validation before
dispatch. Full transport fields and replay rules are in [BRIDGE.md](BRIDGE.md).

Keep one accountable process-group owner. The current `science.run_bounded`
owns a session and its backend child inherits it. Either retain that ownership
while spawning the prepared interpreter, or wire the package supervisor's
cleanup into the authoritative cancellation path. Starting an untracked second
session beneath the current killed worker can leave scientific descendants
running. Enforce transport limits while reading, rather than checking the size
only after `subprocess.run(capture_output=True)` has accumulated output.

## Reviewed design semantics and compatibility

The integrated application added `scientific_profile`, `requested_tier`,
`allowance_origin`, `maximum_horizon`, and `source_artifact_ids`. Its strict
`counterdex.v1` profile requires the tier, origin/description and horizon; all
approved times must fit the horizon, including numerical requests. The horizon
must cover included history. Budgets are wall 1–120 seconds, constructions 0–2,
pair verifications 0–2, and native bytes 1–4 MiB. Checked design requires two
pair verifications for initial checking and fresh replay.

The audited 0.2.0 package accepted these additional fields but applied legacy
design defaults. A normalized numerical request with hypothetical origin and
maximum horizon `10/1` became checked tier, reviewed-hard-bound origin and
horizon `8/1`. Counterdex 0.3.0 maps this explicit profile with
`DB-SC-1-design-to-groundwork-v2`, preserving all three choices. Mapping tests
cover exact request identity, rejected partial choices, horizon and verification
budgets, unsupported reuse, policy tampering and an unchanged v1 fixture binding.
Do not route the strict profile through an unpatched installed package.

For the explicit profile, the tested accepted/rejected cases are:

| Request | Required behavior |
|---|---|
| Numerical tier, hypothetical allowance origin, explicit covering horizon, no reuse IDs | Preserve those exact reviewed choices |
| Checked tier, explicit covering horizon, two pair verifications, construction authorized when needed | Check and freshly replay the same fixed candidates and approved grid |
| Missing explicit tier/origin/horizon | Reject; do not invent approval fields |
| Horizon below history or any approved time | Reject before execution |
| Checked tier with fewer than two verification passes | Reject the insufficient checked budget |
| Nonempty `source_artifact_ids` | Reject with `unsupported_artifact_reuse` at `request/source_artifact_ids` until prospective pair-certificate reuse is explicitly supported |

The existing backend permits one or two source artifact IDs, validates them
against selected historical evidence, and maps one digest to both candidates or
two digests in request order. The application bridge currently accepts a
baseline packet as lineage, not as a reusable prospective pair certificate.
For this adoption, send `source_artifact_ids: []` (or its normalized omission)
and always provide mandatory `historical_artifact` separately. Do not silently
drop a nonempty reuse request or reinterpret it as construction permission.

## Reproduction and acceptance

To repeat the read-only cross-branch smoke, read the four modules named above
with `git show cc779bf2d6993e6b58c537eed2a690adf9c27e34:<path>`, load them in
memory under their actual `bean_api` module names, and invoke their actual
adapter. Substitute only its child-file launch with the Git object's
`counterdex_child.py` source, keeping the fixed server-owned `__file__` path and
isolated CPython 3.11 invocation. The child then imports the current checkout's
scientific source. Supply complete normalized records and real scope arguments;
set operation/execution IDs to the audit run ID. Do not replace computation
with a simulated adapter. This avoids a backend checkout or mutation while
exercising actual admission, discovery, output mapping and replay.

The acceptance predicates are matching immutable input/workflow scope, exact
raw bytes/anchors, authoritative schema validity and matching fresh candidate
facts. The no-candidate control must retain its unchecked state. Existing design
must retain its own checked result and declared projection; complete application
lineage additionally requires the application design packet and parent history.
These smokes do not exercise outer-worker cancellation or HTTP authorization.

For Owner 2's integrated test checkout containing the reviewed backend and
scientific changes, extend the existing tests rather than creating another
backend or evaluator. With matching prepared engine and backend environments:

```sh
BEAN_COUNTERDEX_PYTHON=/absolute/path/to/prepared/python3.11 \
  PYTHONPATH=apps/api .venv/bin/python -m pytest -q \
  tests/test_baseline_adapter.py tests/test_baseline_binding.py \
  tests/test_baseline_workflow.py tests/test_counterdex_adapter.py
```

These branch test files are not all present on `adac945`. Their execution is a
separate acceptance step, not a check claimed by the read-only audit. The
commands below retain the historical checked-out `adac945` comparison and
package-only checks; the final command's unsupported result describes that
backend commit, not PR #6.

Run from the repository root with an existing prepared engine and a backend
Python 3.13 environment containing Pydantic. These checks do not load provider
configuration or make network/provider calls:

```sh
/tmp/counterdex-contracts-check/bin/python \
  packages/groundwork_adapter/scripts/check_application_schema.py \
  --fixtures packages/groundwork_adapter/fixtures/decision

/tmp/counterdex-contracts-check/bin/python \
  packages/groundwork_adapter/scripts/supervise_bridge.py \
  --python /tmp/counterdex-engine/bin/python --wall-seconds 120 \
  < packages/groundwork_adapter/fixtures/decision/hero-baseline.request.json \
  > /tmp/counterdex-consumer-audit-baseline.json

PYTHONPATH=apps/api /tmp/counterdex-contracts-check/bin/python - <<'PY'
import json
from pathlib import Path
from bean_api.counterdex_adapter import CounterdexAdapter
request = json.loads(Path(
    'packages/groundwork_adapter/fixtures/decision/hero-baseline.request.json'
).read_text())
adapter = CounterdexAdapter('/tmp/counterdex-engine/bin/python')
caps = adapter.capabilities()
print({key: caps.get(key) for key in
       ('adapter_version', 'available', 'baseline_discovery', 'reason')})
print(adapter.investigate(request['problem'], request['dataset'],
                          {'scientific_wall_seconds': 120}))
PY
```

The last command reproduces the audited dispatch gap; update it when the adapter
accepts workflow scope. The supplied fixture identities are regression inputs,
never application authorization. A prepared environment installed before a
source change must be rebuilt before qualifying that changed source; compare
handshake identity with the source being tested.

After Owner 2 adopts the seam, use the existing independent HTTP acceptance
harness: create actual immutable records, approve a baseline, discover candidates,
approve a separate design using the returned candidates, download native bytes,
and replay with independently retained anchors. Repeat with the alternate
dataset. Reject changed anchors/bytes, missing lineage, altered candidates,
unapproved changes and late cancelled results. Exercise cancellation while a
scientific descendant is live and observe no surviving child. Verify recheck
for actual and hypothetical readings, a different time/allowance, lone/pair
baseline parents and exclusion of both candidates. Retain original identities
and evidence, and reject changed proposal digests or row/provenance mismatches.
Run the existing relevant backend tests, schema export,
lint and package checks; do not count seeded design regressions or these package
smokes as the public G1/G2 gate.

No complete authenticated HTTP loop was run in this audit. Current `main` at
`1f75bdc04a3547aa2a1adb4e529363e8fafa74c5` includes PR #6's compatible baseline
code and separate branch acceptance evidence. Combined-source checks and
Owner 5's actual API/worker acceptance remain distinct from this smoke. The
complete application-native design lineage and observation recheck gate remains
pending Owner 2 routing and independent end-to-end acceptance.

# Owner 2: adopt the application bridge in the existing worker

This is a concrete integration request, not a replacement backend. The audit
used integrated `main` commit `adac94540c5572fdbe08be3dc8323c61e91b264f`
and science worktree `bc928550926588e6e3e1d1b54112bffb28dab590` on November 13,
2026. Remote `backend/scientific-integration` was
`e36c6830f1f3cb652c95e23f2336c90330fcfa8b`; it was already merged into `main`.
`git log origin/main..origin/backend/scientific-integration` returned no commits.
No backend files were changed for this audit.

The recorded observations below describe the pre-change 0.2.0 package. The
adoption instructions describe the current 0.3.0 source, including explicit
design scope, authoritative per-candidate results and admitted observation
rechecks. Package changes do not establish that the backend has adopted them.

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

The first G1 blocker is dispatch: `counterdex_adapter.py` probes the engine and
then unconditionally returns `baseline_producer_unavailable`.
`counterdex_child.py` supports only probe/design/replay and also hardcodes
baseline discovery false. The package now supplies actual bounded discovery;
`shared/contracts/BACKEND_INTEGRATION.md` still describes the earlier missing
producer and needs an Owner 2 update after integration.

Changing dispatch alone is insufficient. At the audited commit,
`Worker._checked_result_allowed` required a suggestion digest and
`native_replay.fresh_checked` for every valid result, including baselines.
The 0.2.0 bridge returned operation-specific replay details in
`details.fresh_replay`. The 0.3.0 bridge additionally supplies these results in
the authoritative `result.native_replay` field, but baseline/recheck replay
still has a different proposition and structure from design replay.
Publication also recomputed a different scientific projection and required its
corresponding anchor shape. Adapt both gates to the application envelope and
operation-specific verification; retaining fail-closed validation is required.

## Exact interface differences

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
Do not relabel either digest to make an anchor check pass. The current DTO's
optional `projection_version` literal admits only `bean-to-counterdex.v1`;
the bridge therefore omits it. Persist the real mapping policy and bridge anchors
separately unless Owner 2 deliberately versions that DTO. Verification records
carry expected/observed scientific problem digests separately from application
problem digests. Never insert a design/suggestion digest into a baseline result
merely to satisfy the old gate.

## Smallest requested consumer changes

1. Keep the existing authenticated routes, approvals, ledger, worker and artifact
   service. Replace the hardcoded unsupported branch with the prepared bridge
   request. Pass the reserved run/scenario and the actual plan, approval,
   operation and execution identifiers. Run bridge admission on complete
   normalized dataset/problem records before approval.
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

No complete authenticated HTTP loop was run in this audit. G1/G2 remain
unqualified until the existing backend consumes the envelope and Owner 5's
actual API/worker acceptance passes.

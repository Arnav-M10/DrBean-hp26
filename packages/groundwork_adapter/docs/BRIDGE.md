# Prepared scientific runtime and native-byte seam

Counterdex 0.2.0 keeps exact mathematics on **CPython 3.11**. The API remains
on its supported 3.12/3.13 runtime. Use one server-configured prepared executable
for `-I -m counterdex.bridge`; never take an executable, module, path, URL or
environment from a request, model decision or evidence packet. No provider is
used by this bridge. Native replay is offline; browser replay is unavailable.

## Runnable setup

From the repository root, create a dedicated environment outside the checkout:

```sh
python3.11 -m venv /tmp/counterdex-engine
/tmp/counterdex-engine/bin/python -m pip install --no-deps ./packages/groundwork_adapter
printf '%s\n' '{"protocol":"counterdex.bridge.v1","operation":"handshake"}' |
  /tmp/counterdex-engine/bin/python -I -m counterdex.bridge
```

The handshake reports `available`, runtime `qualified`, exact source identity,
and scientific capabilities. `configured: null` means configuration is owned by
the parent. The included parent example's `PreparedBridge.capabilities()` sets
`configured: true` only for an explicitly configured absolute executable; a
failed launch is available false, and a 3.12/3.13 scientific child is unqualified.
Configuration alone never grants a result a checked label.

The reusable **parent-side**, stdlib-only example
`scripts/supervise_bridge.py` runs on 3.12/3.13. It launches a private POSIX
session, clears inherited credentials, uses isolated Python, writes/reads pipes
without blocking, caps stdout at 12 MiB and stderr at 64 KiB, and kills/reaps the
entire owned process group on cancellation, deadline, overflow and completion.
It also kills descendants after their leader exits. Import this fixed local
source through a server-owned path, or implement this boundary in Owner 2's
science adapter. Do not install the scientific package into the backend runtime
by relaxing `requires-python`.

```sh
python3.13 packages/groundwork_adapter/scripts/supervise_bridge.py \
  --python /tmp/counterdex-engine/bin/python --wall-seconds 120 \
  < packages/groundwork_adapter/fixtures/decision/hero-baseline.request.json \
  > /tmp/counterdex-baseline-response.json
```

Supply the approved remaining wall budget (at most 120 seconds) and a callback
reading the authoritative cancellation state to `PreparedBridge.call`.
Never spawn this child into a detached session owned by an untracked worker:
the parent that launched the scientific session must kill it before its own
exit. A top-level worker cancellation must invoke this supervisor's cleanup.
POSIX is the supported supervision environment. Mathematical checks retain
their own smaller cooperative time and byte caps; the parent enforces the hard
deadline, including input, export and replay.

## Versioned JSON operations

One request, EOF, one response, exit. Every request has
`protocol: "counterdex.bridge.v1"` and `operation`. Unknown top-level fields fail.
Scientific scalars are exact rational strings; JSON floats and duplicate keys
fail. Raw native packets are capped at 4 MiB, including lineage. The 12 MiB
transport cap separately covers base64 and result diagnostics. Owner 2's old
2 MiB investigation transport cap must be changed to accommodate this seam.

| Operation | Remaining request fields |
|---|---|
| `handshake` | none |
| `admission` | `problem`, `dataset` records `{id,digest,body}` |
| `investigate` | those records, `run_id`, `scenario_id`, `workflow`, `limits`, `search_settings` (null for defaults) |
| `design` | those records, `run_id`, `workflow`, normalized application `request`, independent `expected_request_digest`, actual `historical_evidence`, `historical_artifact` |
| `review` | revised records, `run_id`, `scenario_id`, `workflow`, `limits`, original design `historical_artifact` |
| `replay` | `native_artifact_base64`, independent `expected` anchors |

`workflow` has `plan_id`, `approval_id`, `operation_id`, `execution_id`.
They preserve scope; fixture IDs confer no application authorization.
`limits` is `{wall_seconds:120,max_bundle_bytes:4194304}` or smaller reviewed
values. Optional non-null `search_settings` must contain the complete named
policy and caps shown in the baseline output. It may not exceed the approved
wall budget. Search defaults are 128 by 128 rate points, at most 16,384 rate
pairs and 32 exact candidate attempts; checking stops once a compatible inside
and outside vector have been found.

`historical_artifact` is exactly `{id,sha256,bytes_base64,anchors}`. It carries
the actual original immutable bytes and the separately stored expected
identities. The historical application evidence body remains
`{run_id,scenario_id,problem_id,expected_problem_digest,result,...}` as emitted
by the existing workflow. The bridge matches its artifact reference and selected
candidate IDs/vectors to freshly replayed native history. It does not fetch URLs.

Success responses contain `protocol`, `ok:true`, authoritative DTO-shaped
`result`, `native_artifacts`, `anchors`, and `details`. Each native artifact is
`{id,sha256,byte_size,media_type,bytes_base64}`. The result has only existing
`ScientificResult` or `DesignResult` fields; readable science details and raw
bytes are outside that DTO. Admission, handshake and replay have their smaller
operation-specific responses. Failure is `ok:false,error:{code,message,
field_paths,retryable}` with fixed safe messages and nonzero process exit.

## Required Owner 2 integration changes

1. Call `admission` on complete normalized application records before approval.
   See [APPLICATION_MAPPING.md](APPLICATION_MAPPING.md) for the exact projection
   and rejected subsets. Retain actual/hypothetical/synthetic classification.
2. Pass server-owned run/scenario/workflow IDs into investigation. Provide
   original records, actual evidence body, approved request digest and original
   raw native bytes for design. The current two-argument
   `design(request,historical_evidence)` cannot supply these inputs.
3. Unpack the response envelope, validate its `result` against the existing
   authoritative DTO, and verify base64, raw SHA-256 and length before publishing.
   Persist the full native bytes and references atomically with the result;
   an `ArtifactReference` alone is not downloadable evidence. Persist expected
   anchors separately from the packet and serve byte-identical downloads.
4. Keep cancellation wired to the owned scientific process group. Reject late
   results after revoked approval/cancellation. Use the existing ledger and
   approval machinery; this package supplies neither a new ledger nor approval.
5. Follow-up appends one separately labeled hypothetical row in a new dataset
   and problem revision, with preserved lineage, selected elapsed time and
   reviewed allowance. `review` checks exactly the original vectors; it does
   not replace their history with a new search. A new separate investigation of
   the revised data may discover other vectors when separately approved.

## Offline replay and trust boundaries

```sh
/tmp/counterdex-engine/bin/python -I -m counterdex replay-native \
  packages/groundwork_adapter/fixtures/decision/hero-baseline.native.json \
  --anchors packages/groundwork_adapter/fixtures/decision/hero-baseline.anchors.json
```

Application anchors independently name raw artifact SHA-256, dataset digest,
application problem digest, scientific projection digest, run and scenario,
plus application request and native design digests (null before design).
Design packets retain baseline bytes; follow-up packets retain design plus
baseline. Maximum lineage depth is two. Replay reconstructs mappings, verifies
source/runtime identity, and recomputes exact bounds. It never reruns numerical
discovery or treats stored `valid` flags as proof. A valid historical certificate
can correctly show an excluded candidate; that is successful evidence checking,
not a worker failure. Existing fixed-pair replay still fails pair compatibility
when either candidate is excluded and retains individual feedback.

Wrong expected identity fails binding. Changed bytes fail the original raw
hash. For a *diagnostic only* false-math control, modify one certificate bound,
recompute its byte hash, baseline report digest and wrapper hashes, then supply
a deliberately changed test anchor. Fresh checking still fails
`exact_check_failure`; the original anchor rejects the mutation before that.
The corresponding tests are in `test_baseline.py`. A changed anchor authenticates
nothing. Source digests prevent replay under accidentally different local code;
they are not signatures or independent formal certification.

## Owner 5 acceptance request and current boundary

Use the existing evaluation harness for one actual API/worker → discovery →
separate design approval → native download → offline replay sequence, with IDs
and byte hashes matched throughout. Also cancel a running job and observe no
remaining scientific process or descendant. Use the `hero` and `alternate`
examples with actual search, and the fixed-pair controls only as explicitly
labeled regression oracles. AI remains absent or controlled placeholder output;
no live cohort or provider dispatch is authorized. Engine-focused tests and the
3.12/3.13 parent process check are not the HTTP gate. Backend adapter/persistence
wiring and independent HTTP acceptance remain Owner 2/5 work.

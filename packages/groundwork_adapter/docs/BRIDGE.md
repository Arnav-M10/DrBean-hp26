# Prepared scientific runtime and native-byte seam

Counterdex 0.3.0 keeps exact mathematics on **CPython 3.11**. The API remains
on its supported 3.12/3.13 runtime. Use one server-configured prepared executable
for `-I -m counterdex.bridge`; never take an executable, module, path, URL or
environment from a request, model decision or evidence packet. No provider is
used by this bridge. Native replay is offline; browser replay is unavailable.

## Integration snapshot: November 13, 2026

[PR #6](https://github.com/Arnav-M10/DrBean-hp26/pull/6),
`backend/browser-baseline` commit
`cc779bf2d6993e6b58c537eed2a690adf9c27e34`, implements real baseline discovery,
scope binding, checked-result qualification and downloadable application-native
bytes/anchors. A read-only check of its actual modules and scientific child
against 0.3.0 source commit `b955780bd4e5d95d19a6ffeed6ad2a7723b4822d`
passed checked discovery, an honest unchecked no-candidate control, authoritative
schemas, native replay and publication binding predicates. It used actual
CPython 3.11 computation without a simulated scientific adapter or provider.

The branch's existing design path also produced checked separation at `8/1`.
Its `groundwork.suggestion-bundle.v1` artifact uses `bean-to-counterdex.v1` and
does not embed the application baseline history. That distinct format does not
invalidate its checked mathematics. Complete application-native design lineage
and `recheck` dispatch remain the next consumer seam. Its capabilities also
hardcode version `0.2.0` while the observed runtime reports `0.3.0`; Owner 2 can
derive that metadata from the runtime identity.

During the read-only smoke, `main` still named `adac94540c5572fdbe08be3dc8323c61e91b264f`.
PR #6 has since merged as `1f75bdc04a3547aa2a1adb4e529363e8fafa74c5` on the same date.
The smoke does not establish combined-source HTTP behavior or the full
discovery/design/recheck gate. See [OWNER2_BRIDGE_ADOPTION.md](OWNER2_BRIDGE_ADOPTION.md)
for exact observations, the read-only reproduction approach, historical findings
and remaining acceptance predicates.

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

The handshake advertises `observation_revision_recheck` with binding profile
`counterdex.followup-binding.v1`, alongside bounded discovery, historical
replay and fixed-pair design. Its scientific profiles also identify the explicit
design mapping `DB-SC-1-design-to-groundwork-v2`. These capabilities describe the
qualified package; they do not establish backend dispatch, persisted evidence
or a successful application run.

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
transport cap separately covers base64 and result diagnostics. At `adac945`,
baseline worker transport was 3 MiB and native publication was 2 MiB. PR #6
raises those baseline caps to 12 MiB and 4 MiB. Retain the operation's approved
lower limit wherever it is smaller than these ceilings.

| Operation | Remaining request fields |
|---|---|
| `handshake` | none |
| `admission` | `problem`, `dataset` records `{id,digest,body}` |
| `investigate` | those records, `run_id`, `scenario_id`, `workflow`, `limits`, `search_settings` (null for defaults) |
| `design` | those records, `run_id`, `workflow`, normalized application `request`, independent `expected_request_digest`, actual `historical_evidence`, `historical_artifact` |
| `review` | revised records, `run_id`, `scenario_id`, `workflow`, `limits`, original design `historical_artifact` |
| `recheck` | revised records, `run_id`, `scenario_id`, `workflow`, `limits`, original baseline or design `historical_artifact`, full `observation_proposal` record |
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

New explicit `counterdex.v1` design requests preserve `requested_tier`, full
`allowance_origin`, and `maximum_horizon` through the v2 design mapping. The
horizon must cover included history and all reviewed times. Nonempty
`source_artifact_ids` are rejected as unsupported prospective certificate reuse;
mandatory baseline lineage still travels in `historical_artifact`. Legacy
requests retain their v1 mapping. See [APPLICATION_MAPPING.md](APPLICATION_MAPPING.md)
for the exact admission rules and distinct digest namespaces.

Success responses contain `protocol`, `ok:true`, authoritative DTO-shaped
`result`, `native_artifacts`, `anchors`, and `details`. Each native artifact is
`{id,sha256,byte_size,media_type,bytes_base64}`. The result has only existing
`ScientificResult` or `DesignResult` fields; readable science details and raw
bytes are outside that DTO. Admission, handshake and replay have their smaller
operation-specific responses. Failure is `ok:false,error:{code,message,
field_paths,retryable}` with fixed safe messages and nonzero process exit.

In 0.3.0, scientific results include `scientific_problem_digest`, concise
`candidate_results` and complete `native_replay`; design results additionally
include `scientific_design_digest` and `native_suggestion_digest`. Verification
records include expected/observed scientific problem digests separately from
the application problem digests. Each candidate result retains its ID,
verification, reason, violating/unresolved row IDs and exact outside-claim
classification. The optional application `projection_version` is omitted to
remain compatible with `adac945`, whose `bean-to-counterdex.v1` literal names
a different mapping. PR #6 additionally admits `DB-SC-1-to-groundwork-v1` for
scientific results and supplies it in its baseline adapter. Full native bytes and independent anchors
remain in the envelope. See [RESULT_SEMANTICS.md](RESULT_SEMANTICS.md) for the
separate evidence, compatibility and execution meanings.

## Admitted observation recheck

`recheck` uses `counterdex.followup-binding.v1` inside the existing
`counterdex.application-bundle.v1` packet. Its binding contains the complete
new `application` binding, the original `observation_proposal` record, and
derived `parent` metadata naming operation, run, scenario, dataset, problem
and projection identities. Complete parent native bytes and separately stored
anchors are retained in `history`; metadata alone cannot replace them.

`observation_proposal` is `{id,digest,body}` from the existing backend
`ObservationProposalBody`. Its full normalized body contains:

```text
dataset_id, experiment_id, observable, origin, row,
source_description, change_reason, generating_choices,
time_unit, concentration_unit
```

The proposal digest is SHA-256 of its canonical body bytes, matching the
backend's observation record hash. It has no DB-SC-1 semantic-kind prefix.
The row retains every normalized `ObservationRow` field, including original
value spellings and notes. Required units are `h` and `mg/L`; the observable is
`concentration`. Proposal origin is `actual`, `transcription` or `hypothetical`.
Hypothetical rows require nonempty `generating_choices`; other origins forbid
them. Full source descriptions and generating choices remain in the binding.
This operation rejects a non-null `row.source_asset_id`, matching the existing
proposal/review workflow: source-derived observations require a separate exact
intake-review lineage that this seam does not yet admit.

The new dataset must append exactly that one included row, preserving all
earlier row bodies/order, experiment and elapsed-time origin. Its parent ID
must name the original dataset. Dataset and problem IDs must be new; model,
domain, claim and all other problem fields remain unchanged. The dataset's
`change_reason` must equal the proposal's. A hypothetical proposal or ancestor
keeps the revised dataset hypothetical; otherwise the ancestor's aggregate
origin is retained, including synthetic ancestry. The separately retained
proposal origin distinguishes the new reading even when the conservative
scientific projection describes the aggregate dataset as hypothetical.

The row is checked at its exact supplied time and its own reviewed historical
allowance. For example, `79/10` hours stays `79/10` when a design recommended
`8/1`; the design's prospective allowance does not replace the new row's
allowance. A freshly replayed baseline parent supplies one or two original
compatible vectors; a freshly replayed design supplies its original pair.
Candidate IDs and exact parameters are preserved, with only the scientific
problem binding updated. No search or replacement vector is allowed. A new
approved child run may have a different scenario ID; its external anchors bind
that new scope while parent metadata and history preserve the original scope.

The server retrieves the proposal through its accepted `observation_review`
linkage, checks workspace/revision ownership, and approves the new execution.
The bridge retains provenance and checks scientific bindings; it neither
authenticates a review nor grants permission. Its `admission` operation checks
the new dataset/problem projection only. Full proposal and parent-lineage
validation also occurs before `recheck` computes a new certificate.

The existing `review` operation is unchanged: it requires one hypothetical row
at a checked design's selected time and prospective allowance. Use `recheck`
for actual or differently timed/allowed observations. Neither operation accepts
a prior `review` or `recheck` as its parent. A separately approved `investigate`
on revised data can discover new vectors and has its own evidence identity.

## Required Owner 2 integration changes

PR #6 implements the baseline portions of steps 1–3. Extend that work for
application-native design and recheck while preserving existing suggestion
bundles and their declared replay profile.

1. Call `admission` on complete normalized application records before approval.
   See [APPLICATION_MAPPING.md](APPLICATION_MAPPING.md) for the exact projection
   and rejected subsets. Retain actual/hypothetical/synthetic classification.
2. Pass server-owned run/scenario/workflow IDs into investigation. Provide
   original records, actual evidence body, approved request digest and original
   raw native bytes for design. The current
   `design(request,historical_evidence)` path uses a distinct projection and does
   not retain the application baseline packet. Load mandatory baseline bytes
   and independent anchors separately from prospective `source_artifact_ids`,
   then dispatch application `design` with the full historical evidence body.
3. Unpack the response envelope, validate its `result` against the existing
   authoritative DTO, and verify base64, raw SHA-256 and length before publishing.
   Persist the full native bytes and references atomically with the result;
   an `ArtifactReference` alone is not downloadable evidence. Persist expected
   anchors separately from the packet and serve byte-identical downloads.
4. Keep cancellation wired to the owned scientific process group. Reject late
   results after revoked approval/cancellation. Use the existing ledger and
   approval machinery; this package supplies neither a new ledger nor approval.
5. Dispatch admitted observation revisions as `recheck` with the accepted full
   proposal and original baseline/design packet. Preserve the exact new time,
   allowance and origin, plus immutable ancestor records. Keep `review` only
   for its narrower existing hypothetical selected-time behavior. Both check
   original vectors; separate new discovery requires `investigate` and its
   own approved execution. See the concrete handoff in
   [OWNER2_BRIDGE_ADOPTION.md](OWNER2_BRIDGE_ADOPTION.md).

## Offline replay and trust boundaries

```sh
/tmp/counterdex-engine/bin/python -I -m counterdex replay-native \
  packages/groundwork_adapter/fixtures/decision/hero-baseline.native.json \
  --anchors packages/groundwork_adapter/fixtures/decision/hero-baseline.anchors.json
```

Application anchors independently name raw artifact SHA-256, dataset digest,
application problem digest, scientific projection digest, run and scenario,
plus application request and native design digests (non-null only for design).
Design packets retain baseline bytes. Follow-up packets retain either their
original baseline or design plus baseline. Maximum lineage depth is two.
Replay reconstructs mappings, verifies
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

Source identity includes every installed scientific module. Keep archived
packets with their matching prepared package/runtime; upgrading to 0.3.0 does
not rewrite their source manifests or make changed code equivalent. The new
follow-up profile leaves earlier operation semantics intact.

## Owner 5 acceptance request and current boundary

Use the existing evaluation harness for one actual API/worker → discovery →
separate design approval → native download → offline replay sequence, with IDs
and byte hashes matched throughout. Also cancel a running job and observe no
remaining scientific process or descendant. Use the `hero` and `alternate`
examples with actual search, and the fixed-pair controls only as explicitly
labeled regression oracles. AI remains absent or controlled placeholder output;
no live cohort or provider dispatch is authorized. Engine-focused tests and the
3.12/3.13 parent process check are not the HTTP gate. PR #6's baseline wiring and
its reported branch acceptance are concrete progress; application-native design
lineage, observation recheck routing and independent acceptance of that complete
loop remain Owner 2/5 work. The read-only smoke does not claim a successful HTTP
run of the combined scientific and newly merged backend source.

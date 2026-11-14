# Scientific result meanings and downstream acceptance

This is an interpretation and handoff contract for the existing Counterdex
profiles, not a new DTO or enum definition. It implements DB-MASTER-1 §2.10.
The application schema remains owned by Owner 2; independent HTTP acceptance
remains owned by Owner 5. Read [BRIDGE.md](BRIDGE.md) for transport, native bytes,
anchors and runtime setup, and [DECISION_EXAMPLE.md](DECISION_EXAMPLE.md) for
executed synthetic positive, negative and follow-up examples.

## Read the axes together

`ok: true` in `counterdex.bridge.v1` means the operation returned a complete
response. It does not mean a scientific proposition is true. Likewise, an
application job's completed state is not a checked result. A failed or stopped
transport cannot be interpreted as a negative scientific finding.

| Authoritative field or record | Meaning |
|---|---|
| Native `report.execution` and `failure_reason` | Whether the bounded producer completed, was cancelled or was interrupted. Inspect search/grid partial flags and row reasons as well. |
| Baseline `report.outcome.scientific_outcome` | A scoped counterexample, a bounded search without an outside witness, or an unresolved outcome. It is not a universal parameter bound. |
| Historical `checked.verification` | Whether the serialized enclosure statements were successfully recomputed. `valid` does **not** assert that every candidate fits. |
| Historical `checked.historical_compatibility` and each `candidate_results[].verification` | Whether the selected fixed vectors satisfy every included hard bound, are excluded, or remain unresolved under the enclosure rule. |
| Fixed-pair `checked.verification` | Whether **both** selected candidates are historically compatible; this older pair proposition is different from successful historical-certificate checking. |
| `expected_binding` and independently supplied anchors | Whether the evidence matches the expected application/projection/design/run/scenario identities. Internal consistency alone is not independent expectation or approval. |
| Design `tier`, `selected_time`, exact row margins and numerical partial flags | What the supplied finite-grid calculation established, and which rows actually contributed. |
| Fresh `replay`, `integrity`, `recorded_result_matches` where supplied | The new check's result. Cached labels are not fresh replay, and hashes alone are not mathematical checks. |
| Dataset/row origin and complete binding lineage | Whether inputs were declared actual, synthetic or hypothetical. An acquired-origin declaration does not authenticate a physical experiment. |

The native historical and design records retain candidate-specific reasons and
row associations. The 0.3 bridge populates the existing application fields
`result.candidate_results`, `result.native_replay` and
`result.scientific_problem_digest`, including separate scientific anchors in the
verification record. Design also supplies `scientific_design_digest` and
`native_suggestion_digest`. Complete records remain in `details.fresh_replay`
and `details.scientific_report`; candidate references alone cannot replace them.
The bridge does not label its mapping with the backend's different literal
`projection_version`. Preserve the native binding's own mapping identity.

## Baseline discovery truth table

These rows describe completed checks against the **supplied** exact problem.
`passed` below always means an actual fresh native check with matching external
anchors, not a stored replay flag. Pair eligibility means scientific prerequisites
are present; a new design still requires a separately reviewed request and
application authorization.

| Observed case | Current outcome/check/replay | Complete bytes available | Pair eligible? | May say | Must not say |
|---|---|---|---|---|---|
| One compatible, strictly outside vector; no usable partner | `certified_counterexample`; historical evidence `valid`; replay `passed`; `pair_available: false` | Baseline plus one-candidate historical certificate and application wrapper | No | This exact assignment fits the reviewed hard bounds and lies outside the closed claim. | The true parameters are known; a second explanation was found; pair design is available. |
| Two distinct compatible vectors, at least one strictly outside | `certified_counterexample`; evidence `valid`; replay `passed`; `pair_available: true` | Baseline plus two-candidate historical certificate and wrapper | Yes, for this bound pair | These assignments remain compatible; at least one contradicts the closed interval under the reviewed model. | All alternatives were enumerated; the model describes nature correctly. |
| One compatible inside/end-point vector, no outside witness and no unresolved trial | `no_counterexample_found`; evidence `valid`; replay `passed`; `pair_available: false` | Baseline plus one-candidate certificate and wrapper | No | This vector fits; the disclosed finite search did not establish an outside witness. | The closed interval is proved or the compatible set is a singleton. |
| Two compatible inside/end-point vectors, no outside witness and no unresolved trial | `no_counterexample_found`; evidence `valid`; replay `passed`; `pair_available: true` | Baseline plus two-candidate certificate and wrapper | Yes, for these two vectors | Both fit; no checked outside witness was found within this policy/cap. | The interval is globally established or pair design requires an outside vector. |
| No numerical proposal, or all proposed vectors are resolved incompatible with no unresolved trial | `no_counterexample_found`; `checked: null`; replay `unsupported`, integrity `passed`, verification `not_checked` | Complete diagnostic baseline/wrapper; **no** historical certificate | No | This bounded search/check sequence found no usable outside witness; retain counts and failure reasons. | No compatible model exists, or a mathematical no-witness certificate was produced. |
| Exact proposals are unresolved and no outside witness is established | `inconclusive`, reason `candidate_checks_inconclusive` or a specific construction failure; replay is `unsupported` without a certificate, or `passed` for retained checked vectors | Diagnostics; certificate only for selected vectors actually checked | Only if two distinct selected vectors are individually compatible and complete evidence is present | The checker could not resolve the stated proposals; any retained compatible vectors have their own narrower checks. | The unresolved proposals are incompatible, or an empty retained list proves impossibility. |

A candidate exactly at either claim endpoint is inside. Numerical residuals and
approximate curve values cannot override that exact classification. The search
report's policy, settings, counts, timing and rejected proposals are retained
producer diagnostics. Native replay checks selected mathematical evidence; it
does not rerun or certify search completeness. A rate-pair cap can end numerical
exploration while checking already-produced candidates still yields a valid
outside witness. Explain both the checked witness and the disclosed partial
search, rather than treating either as the whole result.

## Design and follow-up truth table

| Observed case | Current outcome/check/replay | Complete bytes available | Pair eligible afterward? | May say | Must not say |
|---|---|---|---|---|---|
| Compatible pair and a strict positive exact margin on an evaluated feasible row | `checked_pair_separation`; pair verification `valid`; replay `passed`; selected time names that row | Suggestion bundle, exact pair certificate, approved mapping and baseline lineage | Same pair remains eligible under a separately approved request | At this reviewed time and allowance, one datum cannot fit both selected assignments. | This is the globally best experiment, identifies the true model, or rules out every other assignment. |
| Compatible pair, but no evaluated reviewed time has positive margin; equality included | `no_separation_established`; verification `valid`; replay `passed`; `selected_time: null` | Complete checked suggestion and pair evidence | Yes; revised constraints need new approval | The sufficient exact test establishes no separation on this grid at this allowance. | No useful experiment exists, the trajectories are identical, or a larger grid/tighter allowance was authorized. |
| Numerical comparison only, or exact construction/checking unavailable | `numerical_guidance` when useful rows exist, otherwise `unavailable`; no fresh checked separation; replay `unsupported` without complete pair evidence | Numerical diagnostic bundle; possibly existing source artifacts, but no new complete checked-pair derivation | Only on the strength of independently valid historical evidence, never numerical guidance alone | These approximate values compare the evaluated subset; identify exact-check and partial-grid reasons. | Guaranteed separation, probability, historical compatibility from numerical scores, or a whole-grid optimum after partial evaluation. |
| Follow-up excludes the reference; the selected outside vector remains compatible | Historical-review outcome `certified_counterexample`; certificate verification `valid`; replay `passed`; candidate statuses differ | New historical-review certificate, revised problem and preserved design/baseline lineage | No: only one selected vector remains compatible | This outside assignment also fits the revised hard bounds; the reference is excluded by named rows. | The outside assignment is physically true or every inside assignment is excluded. |
| Follow-up excludes the outside vector; the reference remains compatible | Historical-review outcome `inconclusive`, reason `selected_candidates_checked`; evidence `valid`; replay `passed` | Same complete review lineage, with individual compatibility/exclusion results | No | This selected outside assignment is excluded by the new revision; the reference still fits. | The original interval is now proved or the earlier counterexample record was invalid. |
| Follow-up excludes both selected vectors | Historical-review outcome `inconclusive`; `historical_compatibility: invalid`; evidence verification `valid`; replay `passed` | Complete new review evidence and unchanged ancestor packets | No | Neither selected vector explains this revision under its hard bounds. | The entire model family is inconsistent, the experiment is erroneous, or all outside vectors are eliminated. |
| Follow-up leaves both selected vectors compatible | Historical-review evidence `valid`; replay `passed`; outcome follows strict outside status; `pair_available: true` | Complete review and ancestor evidence | Mathematical pair exists; see current dispatch limitation below | Both exact vectors still fit the revised observations. | The new reading confirmed physical truth or automatically authorized another design. |
| Follow-up enclosure remains unresolved for a selected vector | Historical certificate can be `valid` and replay `passed`, while individual verification and historical compatibility are `inconclusive` | Complete certificate of correctly recomputed enclosures, including unresolved row reasons | No unless both individual compatibility checks are valid | This enclosure rule did not resolve that vector against the new bound. | Overlap proves compatibility or incompatibility. |

The historical profile `groundwork.historical-candidates.v1` checks enclosure
statements and reports candidate compatibility separately. The existing
`groundwork.analytic-pair.v1` proposition instead requires both candidates to
fit. Consequently, directly rechecking a fixed pair against data that exclude
either candidate produces pair verification `invalid` and pair replay `failed`,
with `integrity: passed` and candidate-specific feedback when the stored result
matches. That is an informative failed **pair-compatibility proposition**, not
necessarily corrupt evidence or an infrastructure failure.

Current `counterdex.bridge.v1` design dispatch requires an `investigate` parent;
it does not accept a `review` or `recheck` packet as its next historical parent.
`pair_available` alone cannot bypass that lineage rule. The existing `review`
operation remains limited to one appended hypothetical reading at the selected
time and reviewed allowance.

The additive `recheck` operation accepts one independently reviewed observation
proposal and its matching revised dataset/problem, with a freshly replayed
`investigate` or `design` parent. It retains the parent's original one or two
exact candidates and never searches for replacements. Its
`counterdex.followup-binding.v1` binding preserves the complete proposal and
parent identities. Actual, transcription and hypothetical proposal origins are
admitted; the supplied exact time and allowance may differ from a design
recommendation. The child run/scenario has its own expected anchors while the
original parent identities remain intact. Actual-origin additions do not relabel
synthetic or hypothetical ancestry as actual. Source-asset-derived observations
still require a separate intake materialization path and are rejected here.

For explicit `counterdex.v1` design requests, the bridge preserves the reviewed
tier, allowance origin and maximum horizon through its v2 design mapping. It
rejects insufficient horizons and unsupported source-artifact reuse. A requested
numerical-only tier is not promoted to checked separation. Legacy requests retain
their original mapping; policy names and semantic digests distinguish the two.

## Stops, unavailable capabilities and evidence errors

| Observed case | Status/error actually available | Bytes and replay | Pair eligibility and permitted explanation |
|---|---|---|---|
| Cooperative cancellation or elapsed resource cap | Native execution `cancelled` or `interrupted`; no new checked publication after the stop; reason `cancelled` or `resource_exhaustion` | Low-level producer may retain a complete partial diagnostic record with no new certificate. The bridge's shared replay budget can instead return `ok: false`; parent hard termination may return no child packet. Never label partial bytes complete. | No new eligibility from the stopped run. Say which work stopped and what prior evidence remains; never convert cancellation into a scientific negative. |
| Unsupported model, units, scope, runtime or source version | Typed errors such as `unsupported_model`, `unsupported_runtime`, `source_version_mismatch`; admission may use `invalid_input` with field paths | Error response; no new verified native result. Existing old bytes may remain usable only in their prepared compatible environment. | No. Explain the actual unsupported capability or required prepared environment, not “bad measurements.” |
| Missing native evidence or incomplete lineage | `incomplete_export`, or a profile/parser error for malformed required fields | No fresh complete replay. A legitimate diagnostic-only record can have replay `unsupported`; it must not be relabeled as a truncated checked export. | No based on missing evidence. Request the exact required bytes; a digest/reference alone is insufficient. |
| Changed raw bytes | `artifact_mismatch` against the original external raw hash | Original expected anchor rejects integrity before mathematical acceptance. | No. Say bytes do not match the expected artifact; do not claim the underlying mathematics is disproved. |
| Intact bytes supplied with the wrong expected problem, projection, design, run or scenario | `wrong_specification_binding`, `wrong_scenario_binding`, or `artifact_mismatch` for an independently expected packet identity | No accepted result for the requested scope. The same bytes may be valid for their own original scope. | No for this request. Say the evidence belongs to another expected input/scope. |
| Resealed diagnostic mutation with a false enclosure | `exact_check_failure` for historical evidence; pair-profile verification also recomputes bounds and rejects false values | Even with intentionally changed test hashes/anchor, false mathematics fails. The real original anchor must also reject that mutation. | No. Distinguish a failed mathematical statement from an unauthenticated diagnostic anchor. |
| Stored result flags disagree with fresh computation | `recorded_result_mismatch`, or pair replay `failed` with `recorded_result_matches: false` | No accepted stored claim. Preserve the fresh report and original bytes for diagnosis. | No from the disputed claim. Never display the stored `valid` flag as authority. |
| Process launch, transport cap, malformed response or worker infrastructure failure | Parent-owned `worker_error` or bridge `ok: false` with a safe error code; exact parent enums remain backend-owned | No new authoritative completed artifact unless independently and atomically committed before the failure under backend rules | No new scientific conclusion. Distinguish infrastructure failure from incompatibility, no witness and unsupported science. |

## Consumer acceptance boundary

Backend inspection baseline: integrated commit `adac945`; package behavior above
describes the 0.3 source. At this backend snapshot, `CounterdexAdapter.investigate` still returns
`unsupported` / `baseline_producer_unavailable`, and its child probe advertises
baseline discovery false. Its design/replay path calls the older native
fixed-pair API, not the package's application-packet bridge. These are current
inspected code findings, not a new HTTP execution result. Package bridge success
must not be advertised as ordinary application startup qualification.

Owner 2 must explicitly map the agreed package evidence into authoritative
application fields and persist complete bytes before references. The 0.3 package
bridge supplies the current candidate-specific DTO fields, but ordinary backend
adoption is a separate integration. Package-level
[bridge checks](../tests/test_bridge.py) exercise proposal retention, baseline
parents with one or two candidates, fresh replay, separate scientific identities,
and rejection of mismatched proposals, history and substituted vectors.
Projection policy names,
application and scientific digests, raw packet hashes, requested design tier,
allowance origin, horizon and source-artifact scope must not be inferred or
interchanged. See [APPLICATION_MAPPING.md](APPLICATION_MAPPING.md) and the
current backend handoff when reconciling that seam.

Owner 5's acceptance should obtain actual run/approval/artifact identities through
ordinary HTTP routes, download byte-identical native evidence, supply separate
expected anchors and freshly replay it. Exercise at least one checked outside
witness, a usable no-separation result, candidate exclusion, wrong binding,
modified bytes and a cancelled job without an orphan process. Grading must inspect
the corresponding axes above; `completed`, `ok: true`, an artifact digest or a
stored `valid` assertion alone is never sufficient. This document introduces no
new approval, ledger, solver, evaluator or live-provider qualification.

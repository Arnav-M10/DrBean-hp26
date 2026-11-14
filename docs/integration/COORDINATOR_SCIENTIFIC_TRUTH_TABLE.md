# Counterdex scientific truth table for the coordinator

Owner **A**, November 14, 2026. Handoff to **B** (authorized tools/UI) and
**C** (independent validation). This is an author audit, not C's acceptance or
qualification of a final browser/coordinator release.

## Audited source and scope

Tracked application baseline: `299a356f677a96fda44c5b280a20317ac7816c4f`.
The only scientific change is an additional both-compatible subcase in
`packages/groundwork_adapter/tests/test_bridge.py`; scientific implementation,
public schemas, native formats and package version are unchanged. The baseline
science checks exclude concurrent coordinator/provider additions; the additional
parent-factory component lane below identifies its tested working file separately.
Retest the actual resulting integration commit before combining these lanes.

Counterdex **0.3.0**, qualified **CPython 3.11.17**; backend **CPython 3.13.18**;
macOS 26.7 arm64. All 24 installed `counterdex/*.py` files were compared by SHA-256
with this worktree's source manifest and match exactly:

`90b42ae505c9a7c25103331f447edc2e15026d291374f6beefd0ef89c23b7bf8`.

Only `two_rate_kinetics_v1` revision 1 / application `two_rate_concentration` is
qualified here. Preserve exact rationals, every included row's reviewed hard
allowance, excluded-row history, units, elapsed-time origin, ordered rate domain,
closed claim endpoints and provenance. An actual-origin declaration does not
authenticate acquisition or relabel synthetic ancestors. No new scientific
interface or mathematical implementation correction was needed.

## Read the separate axes

- `scientific_outcome`: `certified_counterexample`, `no_counterexample_found`, or
  `inconclusive`; it is not a job state.
- Candidate `verification`: `valid` means the entire freshly computed enclosure
  fits every included hard band; `invalid` / `measurement_incompatible` means at
  least one enclosure is disjoint; `inconclusive` / `insufficient_enclosure`
  means containment and disjointness are both unestablished. An excluded input
  row is not an excluded candidate.
- Overall packet `verification=valid` means the declared mathematical computation
  replayed correctly. A packet can validly prove candidate exclusions or retain
  an inconclusive candidate. Inspect `candidate_results` separately.
- `expected_binding=matches`, raw-byte `integrity=passed`, and `replay=passed`
  answer different questions. CLI exit zero also occurs for a well-formed
  numerical-only export whose `replay=unsupported` and `verification=not_checked`.
- Replay recomputes this same qualified checker. It does not rerun discovery
  (`search_replayed=false`), authenticate measurements, independently implement a
  second proof system, or strengthen the scientific conclusion.

## Current decision table

The states below are actual implementation values, not a new public DTO. B owns
the canonical projection, authorization and publication rules. “Design eligible”
always means a new concrete design proposal followed by its separate approval;
no result row itself grants authority.

| Case / exact status | Permitted wording and next action | Prohibited inference | Native evidence and design eligibility |
|---|---|---|---|
| Compatible outside witness: `certified_counterexample`; candidate `valid`, `outside_closed_claim=true`, `is_counterexample=true` | “This exact candidate fits every included hard bound and is strictly outside the reviewed closed interval, under this model.” Read actual evidence before proposing a next step. | “The model is true,” “the actual parameter equals this vector,” or treating an endpoint as outside. | Checked bytes may have `replay=passed`, `verification=valid`, binding `matches`. Design needs two distinct checked compatible historical vectors plus reviewed feasible constraints, not just the outside flag. |
| Completed finite search with checked vectors but no outside witness: `no_counterexample_found`, reason `bounded_search_no_outside_witness` | “This bounded search found no checked outside witness.” A useful already-approved comparison may run within its existing limits; otherwise clarify, propose fresh reviewed scope, or stop. | “Claim proved,” global identification, or completeness of the compatible set. | Checked selected-vector bytes can replay successfully without replaying the search. A pair of distinct compatible vectors may support a separately approved fixed-pair design even if neither is outside. |
| Search with no selected certificate: `no_counterexample_found`, empty candidates/certificate | “No checked counterexample was found in this bounded search.” Preserve search diagnostics as diagnostics. | “No compatible model exists,” including when every screened amplitude failed. | Integrity/binding can pass, but `replay=unsupported`, `verification=not_checked`. No pair design from absent evidence. |
| Exact checking could not resolve screened candidates: `inconclusive`, reason `candidate_checks_inconclusive`; trials may report `construction_range` | “The admitted checker could not establish a candidate result within its fixed policy.” | Recasting a range/precision limitation as exclusion or no-counterexample proof. | No selected certificate means `not_checked` / `unsupported`; retained bytes do not supply a pair. |
| One checked candidate: `pair_available=false` in native outcome | Report that candidate's actual result; a lone outside witness can still be a `certified_counterexample`. | Inventing/refitting a second candidate or calling one witness a pair. | One-candidate historical bytes replay. No fixed-pair design until an actual second checked distinct vector is obtained through an authorized operation. Package recheck supports one original baseline vector; the current browser follow-up contract remains design-linked. |
| Checked positive pair design: `design_tier=checked_pair_separation`, `verification=valid`, `replay=passed` | “At this approved time and allowance, no one reading can fit both selected candidates.” Exact margin `abs(p1-p2)-e1-e2-2*eta > 0`; report the returned selected time. | Global optimality, separation of every model, a unique true model, or guaranteed survival of either candidate. | Native bytes contain the exact pair/history/scope and replay. A separately reviewed new reading and separately approved recheck can follow. |
| Checked finite grid without positive separation: `design_tier=no_separation_established`, reason `no_separating_time`, `selected_time=null` | “No positive separating margin was established among these approved evaluated options.” Clarify constraints, propose a new reviewed design, or stop. | “No useful experiment exists,” silently selecting a numerical time as checked, or claiming touching bands separate. | `verification=valid` and `replay=passed` are possible. Current follow-up admission accepts this checked design parent with an independently declared new reading time/allowance. |
| Numerical design: `design_tier=numerical_guidance`, `verification=not_checked`, `replay=unsupported` | “Numerical comparison of the supplied finite feasible grid suggests this option; checked separation was not established.” | Any checked compatibility/separation badge, even if a numerical score is positive or CLI exit status is zero. | Native bytes retain integrity/binding and numerical diagnostics. Explicit numerical approval consumes zero exact-construction/pair-verification passes. This design cannot be a checked follow-up parent (`followup_design_required`). |
| Reference retained / outside excluded: candidate states `valid` / `invalid`; fixed recheck outcome `inconclusive`, reason `selected_candidates_checked` | “This new reading retains the original reference candidate and excludes this original outside candidate.” | Eliminating every outside model or proving the interval. | Recheck bytes/history can replay with overall `verification=valid`. One survivor alone is not a newly available checked pair. |
| Outside retained / reference excluded: `invalid` / `valid`; outcome `certified_counterexample` | “This original outside candidate remains compatible with the reviewed history and new reading.” | New candidate discovery, unique identification, or substitution of a better-fitting vector. | Replay can pass; retain the same exact vectors and candidate IDs. No fresh search occurs. |
| Both excluded: `invalid` / `invalid`; outcome `inconclusive` | “This reading excludes both selected candidates.” Retain the completed checks; clarify assumptions or propose separately authorized further work. | Global inconsistency, an empty model class, or proof of the original claim. | Overall `verification=valid` / `replay=passed` can certify these exclusions. The excluded pair is not compatible evidence for another checked design. |
| Both compatible under a separately declared nonseparating reading scope: `valid` / `valid`; original outside member keeps outcome `certified_counterexample` | “This reading does not distinguish these two original candidates.” | Both surviving the exact time/allowance of a valid positive-separation design; investigate that contradiction instead of accepting it. | Both-compatible replay is legitimate with changed reading time/allowance or a nonseparating scope. Original vectors/history remain immutable. Any next design still requires its own valid source/scope and approval. |
| Unresolved original candidate: e.g. `inconclusive` / `invalid`; aggregate `inconclusive` | “The fixed exact enclosure is insufficient to decide this candidate against the new hard band.” | Treating overlap as compatibility, silently increasing precision, refitting, or promoting uncertainty after replay. | Certificate/replay can be valid while a candidate remains inconclusive. It is not checked-compatible input to a pair design. |
| Cancelled/resource-stopped operation: native `execution=cancelled` or `interrupted`; reason `cancelled` / `resource_exhaustion` | “Computation stopped; retained earlier results remain available.” Reconcile the actual job before considering any authorized retry. | A stopped job as a scientific negative, erasing completed earlier evidence, or publishing a late result after authority ended. | Stopped baseline may retain integrity-only bytes without a checked claim. Backend publication must reject newly arriving evidence after cancellation/expiry. No new design eligibility arises from the stop. |
| Invalid evidence or wrong expected input: e.g. `artifact_mismatch`, `exact_check_failure`, `recorded_result_mismatch`, `candidate_mismatch`, `wrong_specification_binding` | “Evidence cannot be verified/bound to this expected operation.” Preserve a safe failure and the original record. | Equating hash consistency with correctness, resealing substituted vectors as approved, or interpreting verification failure as candidate exclusion. | No successful publication/replay claim. Require independent expected anchors, exact source compatibility, full history and fresh mathematics. No pair eligibility from rejected evidence. |

The adopted application design mapping refuses nonempty prospective reuse
(`source_artifact_ids`): preserve that refusal instead of silently constructing
new evidence. The lower-level package's matching pair reuse API does not grant
application approval or extend the adopted backend contract. Numerical-only
approval must never publish retained checked facts.

## Reproducible inputs and existing executable cases

All controls below are synthetic. Candidate vectors in discovery/bridge/HTTP
tests are computed, not read from a hardcoded candidate fixture. Fixed-vector
unit controls are labelled as such. Never select behavior by fixture filename.

1. **Application baseline:**
   `packages/groundwork_adapter/fixtures/decision/hero-baseline.request.json` and
   `tests/test_baseline_workflow.py`. Included `(time, value, allowance)` rows are
   `(1/4,24/5,1/2)`, `(1/2,36/5,1/2)`, `(1,8,1/2)`, `(2,34/5,1/2)`,
   `(4,57/10,1/2)`; closed `ke` claim `[1/10,17/100]`. Application domain:
   `A=[1/1000,30]`, `ke=[3/200,7/20]`, `ka=[2/5,8]`, `ke<ka`.
2. **Controlled evidence-dependent decision:**
   `tests/test_controlled_native_workflow.py::test_controlled_graph_adapts_to_actual_native_evidence`.
   Same objective/permissions: ordinary claim finds an outside witness and skips
   optional comparison; the wide claim covers the full rate domain and produces
   no outside witness, then the already-approved optional comparison runs.
   Expected scientific reservation counts are respectively one and two. This
   proves controlled dispatch over real computation, not live Gemini reasoning.
3. **Changed data, no candidate, unresolved search, lone witness:**
   `packages/groundwork_adapter/tests/test_baseline.py::BaselineEvidenceTests`
   uses the three-row problem from `tests/helpers.py` with finite search settings
   `ke_points=12`, `ka_points=8`, `max_rate_pairs=96`, `max_candidates=8`.
   `test_changed_measurements_change_frozen_candidates_and_native_identity`
   changes observation 1 to value `4`, allowance `1`;
   `test_full_domain_closed_claim_yields_no_counterexample_without_completeness_claim`
   uses the full domain as claim;
   `test_impossible_measurement_reports_bounded_no_candidate_and_integrity_only`
   changes the time-zero value to `1`;
   `test_unresolved_exact_checks_remain_distinct_from_no_candidate_found` uses
   time `(2**300+1)/2**300`, outside the fixed checker's rational-bit policy;
   `test_single_candidate_budget_keeps_one_native_witness_and_disables_pair`
   sets `max_candidates=1`. None of these controls proves search completeness.
4. **Positive, no-separation, numerical, changed scope:**
   `tests/test_native_design_workflow.py` computes the actual baseline pair.
   `test_actual_pair_design_requires_separate_approval_and_replays_downloaded_lineage`
   approves feasible times `8/1,6/1`, allowance `1/5`, horizon `8/1`.
   `test_revised_design_needs_new_approval_and_preserves_honest_no_separation`
   changes the allowance to `100/1` and checks rejection of the old approval.
   `test_explicit_numerical_design_uses_zero_pair_budget_and_retains_replayable_scope`
   requests numerical guidance with zero constructions/verifications.
   `test_native_design_refuses_prospective_reuse_during_plan_admission` covers
   the adopted reuse contract. Publication attacks live in
   `tests/test_native_design_binding.py`, including
   `test_resealed_numerical_approval_cannot_publish_retained_checked_facts`.
5. **Five legitimate fixed-candidate outcomes, fresh process replay:**
   `packages/groundwork_adapter/tests/test_bridge.py::BridgeTests::test_proposal_bound_recheck_distinguishes_survivors_exclusions_and_unresolved`.
   Discover the pair, then evaluate its exact bounds at separately declared
   time `79/10`. Let `r` and `o` be those computed reference/outside enclosure
   centers. Cases: reading `r` or `o` with allowance `7/20`; reading `100` with
   allowance `7/20`; **new regression:** reading `(r+o)/2` with allowance `100`;
   unresolved reference: reading `r` with allowance one quarter of its exact
   enclosure width. Every case retains the parent bytes, original vectors,
   accepted proposal and old rows, forbids replacement search, and replays in a
   separate process. The both-compatible case changes allowance explicitly; it
   does not contradict the earlier positive design's exact approved scope.
6. **Ordinary authenticated follow-up:**
   `tests/test_native_followup_workflow.py::test_hypothetical_followup_rechecks_original_pair_with_new_approval_and_portable_history`
   covers reference/outside survival and both-excluded at the selected design
   time using separately reviewed six-decimal synthetic readings.
   `test_reviewed_followup_uses_its_own_time_allowance_and_complete_provenance`
   uses time `79/10`, reading `100/1`, allowance `7/20` for actual, transcription
   and hypothetical declarations.
   `test_followup_accepts_checked_no_separation_parent_and_rejects_numerical_parent`
   verifies the parent distinction. `test_completed_followup_cannot_publish_after_authority_ends`
   covers cancellation/expiry. The five-outcome bridge test is not a claim that
   all five outcomes were independently exercised through the browser.
7. **Independent anchors and mathematical attacks:**
   baseline unit tests `test_independent_problem_scenario_and_complete_bundle_anchors`,
   `test_artifact_hash_is_checked_before_native_math`, and
   `test_resealed_false_bounds_fail_fresh_mathematical_check` distinguish changed
   expected identity, changed bytes, and altered mathematics after diagnostic
   rehashing. Native design/follow-up publication tests reject candidate/vector,
   approval, history, scope, outcome and anchor substitutions.

## Fresh author checks and reproduction

| Check actually executed | Result |
|---|---|
| Full package unittest suite before the test-only extension | 292 run in 15.798 s: 290 passed, two environment skips |
| Extended five-case bridge test plus installed-runtime supervisor test | 2 passed in 2.280 s; includes all five subcases and fresh subprocess replay |
| Previously skipped authoritative application DTO test, under backend Python | 1 passed in 0.091 s |
| Baseline/design/follow-up HTTP, native publication/binding and evidence projection modules below | 114 passed in 36.62 s |
| Existing controlled graph with actual Counterdex and native downloads/replay | 4 passed in 4.66 s |
| New parent factory with controlled model and actual approved scientific child, via an explicit test-only ports adapter | 2 passed in 2.48 s after all eight anchor and canonical approval/plan bindings were asserted; in-memory checkpoint only, not durable backend/browser acceptance |

The two initial skips were expected missing backend DTO dependencies in the
standalone engine environment and an unset `COUNTERDEX_TEST_PYTHON`. Both exact
skipped tests subsequently passed under their appropriate prepared runtimes.
One initial backend invocation named nonexistent `tests/test_followup_http.py`;
it collected no tests, was corrected to the existing modules, and is not counted
as scientific execution. No test expectation was weakened to obtain a pass.

Execution used the prepared runtimes under
`/Users/arnav/Documents/HackPrinceton/DrBean-hp26-shared-integration/`:
`.venv-engine/bin/python` and `.venv/bin/python`. Run commands from this source
worktree, with credential-free `env -i`, normal system `PATH`, and
`PYTHONPATH` containing `evaluation/drbean_eval/guard` plus the current package
or API source. Set `DRBEAN_EGRESS_GUARD_LOG` to a temporary audit path.
Both `BEAN_COUNTERDEX_PYTHON` and `BEAN_COUNTERDEX_REPLAY_PYTHON` explicitly
selected that same verified installed engine; no sibling-runtime fallback was
used. The key command bodies were:

```sh
"$ENGINE" -m unittest discover -s packages/groundwork_adapter/tests
"$ENGINE" -m unittest -v \
  test_bridge.BridgeTests.test_proposal_bound_recheck_distinguishes_survivors_exclusions_and_unresolved \
  test_supervisor.SupervisorTests.test_prepared_installed_real_bridge
"$BACKEND" -m unittest -v \
  test_application.ApplicationProjectionTests.test_authoritative_application_models_when_installed
"$BACKEND" -m pytest -q tests/test_baseline_workflow.py \
  tests/test_native_design_workflow.py tests/test_native_followup_workflow.py \
  tests/test_native_design_binding.py tests/test_native_design_publication.py \
  tests/test_native_followup_adapter.py tests/test_native_publication.py \
  tests/test_followup_scope.py tests/test_agent_evidence.py
"$BACKEND" -m pytest -q tests/test_controlled_native_workflow.py
"$BACKEND" -m pytest -q tests/test_research_coordinator_native.py
```

For targeted package unittest names, include
`packages/groundwork_adapter/tests` on `PYTHONPATH`; set
`COUNTERDEX_TEST_PYTHON="$ENGINE"` for the installed supervisor test.
Backend runs set `BEAN_AI_MODE=placeholder`. Full stdout/stderr and guard logs
are retained locally in `/tmp/drbean-scientific-audit-299a356/`.
Guard telemetry recorded 60 backend and three engine guard installations,
no credential names present, no provider-client constructions, no credential
reads and no blocked egress attempts. Some isolated native subprocesses use
their own minimal environment/`-I`; this is not a claim that every subprocess
loaded the guard. They execute the matching deterministic provider-free engine.
Controlled workflow assertions also require an empty provider-attempt ledger
and zero external model calls. No live provider call was made.

The new `test_research_coordinator_native.py` lane used factory file SHA-256
`ac46a11595fb8b9aff96c2a31c47688bfa29df80291b8ae7791e6fe8b24bd50f`.
It invokes `create_research_coordinator` with a controlled model and
`InMemorySaver`: four turns maintain a todo plan, prepare a real unapproved
scientific plan, interrupt before execution, then read actual child evidence and
publish a report after canonical human approval. Changing only the reviewed
claim to the full domain changes the computed result and the selected next
action from `review_design` to `stop`. The exact question survives the model
context, scientific plan and backend report; native downloads freshly replay
against authenticated external anchors. Reconciliation reuses one child.
Pending-review views, parent turn admission and plan/event retention are
test-local adapters; no new production route, durable checkpoint or restart claim
is implied. Its final separate guard log records four installations, with no
credential names, provider constructions or egress attempts. Initial harness
corrections and earlier runs remain in separate logs. The initial harness used synchronous
`Worker.tick` inside the parent event loop and an outdated terminal-record shape;
those adapter errors were corrected without editing the factory or science.

## Handoff and limits

B should expose these separate axes in bounded evidence tools and UI, retain
native bytes plus authenticated external anchors, and enforce separate review
and approval for every new scientific scope. Do not present numerical-only
downloads or replayable exclusions as checked separation. Current scientific
interfaces support the coordinator loop; durable agent sessions, approval-resume
integration, browser completion and combined-release registration remain B/A
integration work, not new engine work.

C should independently rerun the exact combined candidate with its own held-out
inputs, all four core feedback outcomes plus a logically valid both-compatible
control, and ordinary private browser approval/restart/replay behavior. These
author checks do not establish live model adaptivity, final browser completion,
cross-platform qualification, or any prize outcome.

# Dr. Bean evaluation report

Generated from `attempts.jsonl` (append-only, hash-chained since harness 0.2.0). Feasibility evidence from a small portfolio, not a statistical benchmark. No live model request was permitted or made: live lanes are disabled (NOT_RUN) and any AI in the current lanes is absent or a labelled controlled placeholder. Fresh native replay re-runs the project's own checker; it is not an independent proof.

- Manifest version 3 (ancestry: v1, v2), contract GF-2 / DB-SC-1
- Holdouts: prepared and sealed by digest; not used for prompt tuning; ungraded
- Attempts recorded: 112; history verification: OK
- Live activation: disabled: live lanes are NOT_RUN. Activation requires a new explicit user instruction, one shared accounted allocation, Owner 3's operator path and independent grading of predeclared cases. The CLI has no switch for it.

## Lanes

| Lane | v | Enabled | Provider | Tools | Scheduled | Attempts | passed | failed | unrun | refused | timed_out | skipped | budget_stopped | error |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| fixture_contract | 1 | yes | controlled/none | any | 24 | 24 | 0 | 0 | 24 | 0 | 0 | 0 | 0 | 0 |
| live_intake | 1 | NOT_RUN (disabled) | live | any | 4 | 4 | 0 | 0 | 4 | 0 | 0 | 0 | 0 | 0 |
| live_agent_controlled_tools | 1 | NOT_RUN (disabled) | live | controlled | 4 | 4 | 0 | 0 | 4 | 0 | 0 | 0 | 0 | 0 |
| actual_full_stack | 1 | NOT_RUN (disabled) | live | real | 2 | 2 | 0 | 0 | 2 | 0 | 0 | 0 | 0 | 0 |
| offline_real_science | 1 | yes | none/controlled | real | 7 | 78 | 34 | 21 | 23 | 0 | 0 | 0 | 0 | 0 |

Records with manifest_version 1 / harness 0.1.0 are the pre-merge inventory: 34 entries recorded before the backend and science package were merged, all `unrun` with a stale reason. They are kept byte-for-byte and interpreted as written, never relabelled as current results.

Evidence classes: `executed_acceptance` (the runner executed the subject against a stack it launched and re-verified the evidence), `imported_claim` (recorded observations; never qualification).

Evidence class counts (harness >= 0.2.0): executed_acceptance: 78.

## Latest attempt per scheduled entry

| Lane | Entry | Status | Commit | Dirty | Reason |
|---|---|---|---|---|---|
| actual_full_stack | FS-BASELINE | unrun | e21c1670e0 | False | no human-authorized provider cohort is open in the shared budget ledger; live requests are not permitted |
| actual_full_stack | FS-DESIGN | unrun | e21c1670e0 | False | no human-authorized provider cohort is open in the shared budget ledger; live requests are not permitted |
| fixture_contract | C01-A | unrun | e21c1670e0 | False | no subject configured: the backend, Gemini layer and scientific adapter are not present in the tested checkout |
| fixture_contract | C01-B | unrun | e21c1670e0 | False | no subject configured: the backend, Gemini layer and scientific adapter are not present in the tested checkout |
| fixture_contract | C02-A | unrun | e21c1670e0 | False | no subject configured: the backend, Gemini layer and scientific adapter are not present in the tested checkout |
| fixture_contract | C02-B | unrun | e21c1670e0 | False | no subject configured: the backend, Gemini layer and scientific adapter are not present in the tested checkout |
| fixture_contract | C03-A | unrun | e21c1670e0 | False | no subject configured: the backend, Gemini layer and scientific adapter are not present in the tested checkout |
| fixture_contract | C03-B | unrun | e21c1670e0 | False | no subject configured: the backend, Gemini layer and scientific adapter are not present in the tested checkout |
| fixture_contract | C04-A | unrun | e21c1670e0 | False | no subject configured: the backend, Gemini layer and scientific adapter are not present in the tested checkout |
| fixture_contract | C04-B | unrun | e21c1670e0 | False | no subject configured: the backend, Gemini layer and scientific adapter are not present in the tested checkout |
| fixture_contract | C05-A | unrun | e21c1670e0 | False | no subject configured: the backend, Gemini layer and scientific adapter are not present in the tested checkout |
| fixture_contract | C05-B | unrun | e21c1670e0 | False | no subject configured: the backend, Gemini layer and scientific adapter are not present in the tested checkout |
| fixture_contract | C06-A | unrun | e21c1670e0 | False | no subject configured: the backend, Gemini layer and scientific adapter are not present in the tested checkout |
| fixture_contract | C06-B | unrun | e21c1670e0 | False | no subject configured: the backend, Gemini layer and scientific adapter are not present in the tested checkout |
| fixture_contract | C07-A | unrun | e21c1670e0 | False | no subject configured: the backend, Gemini layer and scientific adapter are not present in the tested checkout |
| fixture_contract | C07-B | unrun | e21c1670e0 | False | no subject configured: the backend, Gemini layer and scientific adapter are not present in the tested checkout |
| fixture_contract | C08-A | unrun | e21c1670e0 | False | no subject configured: the backend, Gemini layer and scientific adapter are not present in the tested checkout |
| fixture_contract | C08-B | unrun | e21c1670e0 | False | no subject configured: the backend, Gemini layer and scientific adapter are not present in the tested checkout |
| fixture_contract | C09-A | unrun | e21c1670e0 | False | no subject configured: the backend, Gemini layer and scientific adapter are not present in the tested checkout |
| fixture_contract | C09-B | unrun | e21c1670e0 | False | no subject configured: the backend, Gemini layer and scientific adapter are not present in the tested checkout |
| fixture_contract | C10-A | unrun | e21c1670e0 | False | no subject configured: the backend, Gemini layer and scientific adapter are not present in the tested checkout |
| fixture_contract | C10-B | unrun | e21c1670e0 | False | no subject configured: the backend, Gemini layer and scientific adapter are not present in the tested checkout |
| fixture_contract | C11-A | unrun | e21c1670e0 | False | no subject configured: the backend, Gemini layer and scientific adapter are not present in the tested checkout |
| fixture_contract | C11-B | unrun | e21c1670e0 | False | no subject configured: the backend, Gemini layer and scientific adapter are not present in the tested checkout |
| fixture_contract | C12-A | unrun | e21c1670e0 | False | no subject configured: the backend, Gemini layer and scientific adapter are not present in the tested checkout |
| fixture_contract | C12-B | unrun | e21c1670e0 | False | no subject configured: the backend, Gemini layer and scientific adapter are not present in the tested checkout |
| live_agent_controlled_tools | C08-A-live1 | unrun | e21c1670e0 | False | no human-authorized provider cohort is open in the shared budget ledger; live requests are not permitted |
| live_agent_controlled_tools | C08-A-live2 | unrun | e21c1670e0 | False | no human-authorized provider cohort is open in the shared budget ledger; live requests are not permitted |
| live_agent_controlled_tools | C09-A-live1 | unrun | e21c1670e0 | False | no human-authorized provider cohort is open in the shared budget ledger; live requests are not permitted |
| live_agent_controlled_tools | C09-A-live2 | unrun | e21c1670e0 | False | no human-authorized provider cohort is open in the shared budget ledger; live requests are not permitted |
| live_intake | C01-A-live1 | unrun | e21c1670e0 | False | no human-authorized provider cohort is open in the shared budget ledger; live requests are not permitted |
| live_intake | C01-A-live2 | unrun | e21c1670e0 | False | no human-authorized provider cohort is open in the shared budget ledger; live requests are not permitted |
| live_intake | C04-A-live1 | unrun | e21c1670e0 | False | no human-authorized provider cohort is open in the shared budget ledger; live requests are not permitted |
| live_intake | C04-A-live2 | unrun | e21c1670e0 | False | no human-authorized provider cohort is open in the shared budget ledger; live requests are not permitted |
| offline_real_science | RS-CANCEL-RESTART | passed | 159fd65303 | False |  |
| offline_real_science | RS-CHANGED-INPUT | passed | 159fd65303 | False |  |
| offline_real_science | RS-DESIGN-AUTHORITY | passed | 159fd65303 | False |  |
| offline_real_science | RS-FOLLOWUP | passed | 159fd65303 | False |  |
| offline_real_science | RS-HERO-FULL | passed | 159fd65303 | False |  |
| offline_real_science | RS-RETRY-CONCURRENT | passed | 159fd65303 | False |  |
| offline_real_science | RS-ZERO-DISPATCH | passed | 159fd65303 | False |  |

## Scientific jobs and external model requests (separate counts)

- Distinct scientific jobs started through the real API (deduplicated by job id across attempts): 91. This accumulated count spans historical attempts; see each attempt for its scientific outcome and the latest-entry table for current results.
- External model requests: verified zero by the egress guard in 78 attempt(s); unknown in 0 attempt(s); legacy records reporting requests: 0. Verified zero means zero actual model requests and zero model usage in that run, not 'unknown'.
- Synthetic budget-ledger reservations in unit tests use temporary stores and are not provider charges.
- Durations are harness wall time on loopback; they are not provider latency.
- Harness budget ledger: no cohort opened; none may be opened now.

## Engine-level native controls (latest run; engine public operations, not HTTP)

Commit 159fd65303, interpreter CPython 3.11.17.

| Control | Result | Observed |
|---|---|---|
| fixed_pair:grid-6-8-allowance-0.2 | passed | {"candidates": {"outside": "valid", "reference": "valid"}, "problem_digest": "d184aae5601989796d299c6c020277938103b0288459133033414b73179bf7c2", "replay": "pass |
| fixed_pair:grid-6-allowance-0.2 | passed | {"candidates": {"outside": "valid", "reference": "valid"}, "problem_digest": "d184aae5601989796d299c6c020277938103b0288459133033414b73179bf7c2", "replay": "pass |
| fixed_pair:grid-6-8-allowance-0.6 | passed | {"candidates": {"outside": "valid", "reference": "valid"}, "problem_digest": "d184aae5601989796d299c6c020277938103b0288459133033414b73179bf7c2", "replay": "pass |
| defense:wrong_expected_identity | passed | "binding_failure" |
| defense:changed_byte | passed | "integrity_failure" |
| defense:mutation_rejected_by_original_anchor | passed | "integrity_failure" |
| defense:mutation_rejected_by_fresh_mathematics | passed | {"class": "mathematical_failure", "field_paths": ["pair/candidates/0/samples/5"]} |
| semantics:touching_bands_do_not_separate | passed | {"error": null, "margin": "-6167420579173/21267647932558653966460912964485513216000000000000", "selected_time": null, "tier": "no_separation_established"} |
| defense:truncated_packet | passed | {"class": "unsupported_format", "code": "invalid_input"} |
| defense:oversized_packet | passed | {"class": "exhausted", "code": "resource_exhaustion"} |
| defense:another_runs_valid_packet | passed | {"class": "integrity_failure", "code": "artifact_mismatch"} |
| defense:drop_artifacts | passed | {"code": "incomplete_export", "diagnostic_anchor": "incomplete_evidence", "original_anchor": "integrity_failure", "reason": null} |
| defense:duplicate_artifact | passed | {"code": "invalid_input", "diagnostic_anchor": "unsupported_format", "original_anchor": "integrity_failure", "reason": null} |
| defense:unknown_profile | passed | {"code": "unsupported_model", "diagnostic_anchor": "unsupported_format", "original_anchor": "unsupported_format", "reason": null} |
| metamorphic:tightened_row_allowance | passed | {"baseline": {"outside": "compatible", "reference": "compatible"}, "engine": {"outside": "excluded", "reference": "excluded"}} |
| metamorphic:widened_allowances_keep_compatibility | passed | {"baseline": {"outside": "compatible", "reference": "compatible"}, "widened": {"outside": "compatible", "reference": "compatible"}} |
| metamorphic:excluded_row_is_not_a_constraint | passed | {"digest_changed": true, "verdicts": {"outside": "compatible", "reference": "compatible"}} |
| metamorphic:swapped_pair_order | passed | {"margins_equal": true, "selected": ["8/1", "8/1"], "verdicts": {"outside": "compatible", "reference": "compatible"}} |
| semantics:closed_endpoint_is_inside | passed | {"is_counterexample": false, "outside_closed_claim": false, "verification": "invalid"} |
| followup:3.4 | passed | {"aggregate": "scientific_exclusion", "independent_oracle": {"outside": "excluded", "reference": "compatible"}, "per_candidate": {"outside": "excluded", "refere |
| followup:4.57 | passed | {"aggregate": "scientific_exclusion", "independent_oracle": {"outside": "compatible", "reference": "excluded"}, "per_candidate": {"outside": "compatible", "refe |
| followup:4.0 | passed | {"aggregate": "scientific_exclusion", "independent_oracle": {"outside": "excluded", "reference": "excluded"}, "per_candidate": {"outside": "excluded", "referenc |

## Release gates at 159fd65303 (overall: passed)

| Gate | Status |
|---|---|
| harness_integrity | passed |
| real_science_http | passed |
| essential_negative_controls_http | passed |
| zero_external_model_dispatch | passed |
| native_engine_controls | passed |
| supported_machine_subprocesses | passed |
| no_unresolved_p0 | passed |
| live_gemini_qualification | not_run |

## Findings (evaluation/findings.json)

| ID | Sev | Owner | Status | Title |
|---|---|---|---|---|
| F-ORPHAN-WORKER-KILL | P0 | 2 | retested | A scientific child survives its worker's death and keeps computing after the job is marked interrupted |
| F-AI-INTEGRATION-SEAM | P1 | 2 and 3 | fixed_pending_retest | Merging Owner 3's placeholder-mode branch onto main breaks the worker's controlled agent lane |
| F-PLATFORM-RLIMIT | P0 | 2 | retested | Valid PNG refused and every scientific worker fails on the team's Mac (RLIMIT_AS rejected) |
| F-ADAPTER-SELECTION | P0 | 2 (with 1 for the runtime bridge) | retested | Ordinary API and worker startup select UnavailableAdapter; no real scientific path exists through HTTP |
| F-BASELINE-DISCOVERY | P0 | 1 (producer) and 2 (adapter wiring) | retested | Counterdex has no bounded baseline candidate-discovery operation (investigate) |
| F-NATIVE-BYTES | P0 | 2 (bytes, anchor record) and 1 (complete packet) | retested | No authenticated route returns native packet bytes; /artifacts/{id} serves the entity envelope; records expose no scientific anchors |
| F-FOLLOWUP-FEEDBACK | P0 | 2 (design-bound follow-up, PR #11) and 1 (wider native admission) | retested | No application route reports candidate-specific outcomes for the prior pair after a hypothetical reading |
| F-PLACEHOLDER-AUTO | P0 | 3 | retested | The legacy documented live switch (dummy values only) constructs google.genai.Client and attempts dispatch |
| F-PLACEHOLDER-MODE | P1 | 3 | retested | Capabilities declare no explicit placeholder/disabled provider mode |
| F-OPTIONAL-VANISHES | P1 | 3 (graph) and 2 (callbacks) | retested | The actual deepagents graph completes while a reviewed optional scenario is neither executed nor skipped |
| F-CONTROLLED-PROVENANCE | P1 | 3 | retested | Controlled-model turns are reserved as provider 'gemini' attempts with no placeholder marker |
| F-REVIEW-MATERIALIZATION | P1 | 2 | fixed_pending_retest | An accepted intake review creates no dataset association (source values never reach execution) |
| F-RESTART-UNOBSERVABLE | P1 | 2 (after F-PLATFORM-RLIMIT) | retested | Cancellation and worker-restart orphan checks cannot be observed: no sustained scientific computation exists yet |
| F-LINT-CHECKLIST | P2 | 4 | open | Documented lint command fails on scripts/release/checklist.py (unused import drbean_eval.contract) |
| F-MAC-NPROC | P0 | 2 | retested | On macOS every scientific job fails: RLIMIT_NPROC is per user, so the bounded child cannot spawn CPython 3.11 |
| F-COORDINATOR-OPTIONAL-STATUS | P2 | 3 | fixed_pending_retest | run_coordinator reports completed while a reviewed optional scenario is unaccounted (enforced downstream by the workflow) |
| F-COORDINATOR-PROVIDER-LABEL | P2 | 3 | fixed_pending_retest | Coordinator attempt metadata names provider gemini for controlled-model turns |
| F-TEST-VAR-LEAK | P2 | 2 | open | Backend test fixtures build Settings without artifact_dir, creating the repo-relative var/artifacts |
| F-DESIGN-SOURCE-ARTIFACTS | P1 | 2 (projection) and 1 (engine reuse format) | retested | A design request that cites the baseline packet in source_artifact_ids cannot reach checked separation |
| F-SIBLING-FORKS | P2 | 2 | open | Sibling what-if forks from one parent cannot coexist in a workspace (one current dataset pointer) |
| H-ORACLE-BOUNDARIES | P1 | 5 | retested | Harness contract oracle accepted inputs the API rejects (trailing newline, -0, depth 64, digit caps) |
| H-BUDGET-USAGE | P1 | 5 | retested | Harness JSONL budget accepted negative usage and counted one request per reservation |
| H-COMPLETED-QUALIFIES | P0 | 5 | retested | Merged harness passed a case-less full-stack entry on state == completed alone |
| H-VACUOUS-ORPHAN | P1 | 5 | retested | First lane run passed orphan/restart checks vacuously (child died at setup); attempt retained |
| H-DIRTY-FLAG | P1 | 5 | retested | git_state stripped porcelain output and marked every record dirty (since harness 0.1.0) |
| H-HERO-CONTINUATION | P1 | 5 | retested | hero-v1 packet disallowed continuation, contradicting the shared example (construction/continuation through 8 h) |
| H-PREVIEW-HARNESS | P1 | 5 | retested | Preview found harness defects: for/else dropped downloads, application-bundle replay unsupported, no-op wrong-anchor control, stale follow-up workspace |
| H-CI-ENGINE | P1 | 5 | fixed_pending_retest | Harness on main does not find Owner 4's prepared .venv-engine, so CI's integration suite runs science without an engine |
| F-LAUNCHER-HIDDEN-PTH | P1 | 4 | open | One-command launch fails on the team Mac: iCloud Drive hides the dot-named .venv, CPython skips its editable .pth, so bean_api cannot be imported (doctor still reports the backend ready) |
| F-LAUNCHER-ENV-READ | P2 | 4 | open | Launcher reads provider credential values while removing them, and its doctor probes inherit the unscrubbed environment |
| H-ORPHAN-TEARDOWN | P1 | 5 | retested | Harness teardown let an orphaned scientific computation resume and outlive the run |

## Every attempt

| # | Entry | Lane | Attempt | Status | Class | Commit | Dirty | Duration ms | Reason |
|---|---|---|---|---|---|---|---|---|---|
| 1 | C01-A | fixture_contract | 1 | unrun | — | e21c1670e0 | False | 0.008 | no subject configured: the backend, Gemini layer and scientific adapter are not present in the tested checkout |
| 2 | C01-B | fixture_contract | 1 | unrun | — | e21c1670e0 | False | 0.005 | no subject configured: the backend, Gemini layer and scientific adapter are not present in the tested checkout |
| 3 | C02-A | fixture_contract | 1 | unrun | — | e21c1670e0 | False | 0.003 | no subject configured: the backend, Gemini layer and scientific adapter are not present in the tested checkout |
| 4 | C02-B | fixture_contract | 1 | unrun | — | e21c1670e0 | False | 0.003 | no subject configured: the backend, Gemini layer and scientific adapter are not present in the tested checkout |
| 5 | C03-A | fixture_contract | 1 | unrun | — | e21c1670e0 | False | 0.003 | no subject configured: the backend, Gemini layer and scientific adapter are not present in the tested checkout |
| 6 | C03-B | fixture_contract | 1 | unrun | — | e21c1670e0 | False | 0.003 | no subject configured: the backend, Gemini layer and scientific adapter are not present in the tested checkout |
| 7 | C04-A | fixture_contract | 1 | unrun | — | e21c1670e0 | False | 0.003 | no subject configured: the backend, Gemini layer and scientific adapter are not present in the tested checkout |
| 8 | C04-B | fixture_contract | 1 | unrun | — | e21c1670e0 | False | 0.003 | no subject configured: the backend, Gemini layer and scientific adapter are not present in the tested checkout |
| 9 | C05-A | fixture_contract | 1 | unrun | — | e21c1670e0 | False | 0.003 | no subject configured: the backend, Gemini layer and scientific adapter are not present in the tested checkout |
| 10 | C05-B | fixture_contract | 1 | unrun | — | e21c1670e0 | False | 0.003 | no subject configured: the backend, Gemini layer and scientific adapter are not present in the tested checkout |
| 11 | C06-A | fixture_contract | 1 | unrun | — | e21c1670e0 | False | 0.003 | no subject configured: the backend, Gemini layer and scientific adapter are not present in the tested checkout |
| 12 | C06-B | fixture_contract | 1 | unrun | — | e21c1670e0 | False | 0.003 | no subject configured: the backend, Gemini layer and scientific adapter are not present in the tested checkout |
| 13 | C07-A | fixture_contract | 1 | unrun | — | e21c1670e0 | False | 0.003 | no subject configured: the backend, Gemini layer and scientific adapter are not present in the tested checkout |
| 14 | C07-B | fixture_contract | 1 | unrun | — | e21c1670e0 | False | 0.003 | no subject configured: the backend, Gemini layer and scientific adapter are not present in the tested checkout |
| 15 | C08-A | fixture_contract | 1 | unrun | — | e21c1670e0 | False | 0.003 | no subject configured: the backend, Gemini layer and scientific adapter are not present in the tested checkout |
| 16 | C08-B | fixture_contract | 1 | unrun | — | e21c1670e0 | False | 0.003 | no subject configured: the backend, Gemini layer and scientific adapter are not present in the tested checkout |
| 17 | C09-A | fixture_contract | 1 | unrun | — | e21c1670e0 | False | 0.003 | no subject configured: the backend, Gemini layer and scientific adapter are not present in the tested checkout |
| 18 | C09-B | fixture_contract | 1 | unrun | — | e21c1670e0 | False | 0.003 | no subject configured: the backend, Gemini layer and scientific adapter are not present in the tested checkout |
| 19 | C10-A | fixture_contract | 1 | unrun | — | e21c1670e0 | False | 0.003 | no subject configured: the backend, Gemini layer and scientific adapter are not present in the tested checkout |
| 20 | C10-B | fixture_contract | 1 | unrun | — | e21c1670e0 | False | 0.003 | no subject configured: the backend, Gemini layer and scientific adapter are not present in the tested checkout |
| 21 | C11-A | fixture_contract | 1 | unrun | — | e21c1670e0 | False | 0.003 | no subject configured: the backend, Gemini layer and scientific adapter are not present in the tested checkout |
| 22 | C11-B | fixture_contract | 1 | unrun | — | e21c1670e0 | False | 0.003 | no subject configured: the backend, Gemini layer and scientific adapter are not present in the tested checkout |
| 23 | C12-A | fixture_contract | 1 | unrun | — | e21c1670e0 | False | 0.003 | no subject configured: the backend, Gemini layer and scientific adapter are not present in the tested checkout |
| 24 | C12-B | fixture_contract | 1 | unrun | — | e21c1670e0 | False | 0.003 | no subject configured: the backend, Gemini layer and scientific adapter are not present in the tested checkout |
| 25 | C01-A-live1 | live_intake | 1 | unrun | — | e21c1670e0 | False | 0.022 | no human-authorized provider cohort is open in the shared budget ledger; live requests are not permitted |
| 26 | C01-A-live2 | live_intake | 1 | unrun | — | e21c1670e0 | False | 0.014 | no human-authorized provider cohort is open in the shared budget ledger; live requests are not permitted |
| 27 | C04-A-live1 | live_intake | 1 | unrun | — | e21c1670e0 | False | 0.009 | no human-authorized provider cohort is open in the shared budget ledger; live requests are not permitted |
| 28 | C04-A-live2 | live_intake | 1 | unrun | — | e21c1670e0 | False | 0.009 | no human-authorized provider cohort is open in the shared budget ledger; live requests are not permitted |
| 29 | C08-A-live1 | live_agent_controlled_tools | 1 | unrun | — | e21c1670e0 | False | 0.02 | no human-authorized provider cohort is open in the shared budget ledger; live requests are not permitted |
| 30 | C08-A-live2 | live_agent_controlled_tools | 1 | unrun | — | e21c1670e0 | False | 0.011 | no human-authorized provider cohort is open in the shared budget ledger; live requests are not permitted |
| 31 | C09-A-live1 | live_agent_controlled_tools | 1 | unrun | — | e21c1670e0 | False | 0.016 | no human-authorized provider cohort is open in the shared budget ledger; live requests are not permitted |
| 32 | C09-A-live2 | live_agent_controlled_tools | 1 | unrun | — | e21c1670e0 | False | 0.008 | no human-authorized provider cohort is open in the shared budget ledger; live requests are not permitted |
| 33 | FS-BASELINE | actual_full_stack | 1 | unrun | — | e21c1670e0 | False | 0.022 | no human-authorized provider cohort is open in the shared budget ledger; live requests are not permitted |
| 34 | FS-DESIGN | actual_full_stack | 1 | unrun | — | e21c1670e0 | False | 0.013 | no human-authorized provider cohort is open in the shared budget ledger; live requests are not permitted |
| 35 | RS-HERO-FULL | offline_real_science | 1 | failed | executed_acceptance | 31a73b1162 | False | 898.428 | failed: source_image_admitted, baseline_completed_with_evidence |
| 36 | RS-CHANGED-INPUT | offline_real_science | 1 | failed | executed_acceptance | 31a73b1162 | False | 423.3 | failed: baseline_completed_with_evidence |
| 37 | RS-RETRY-CONCURRENT | offline_real_science | 1 | passed | executed_acceptance | 31a73b1162 | False | 858.355 |  |
| 38 | RS-DESIGN-AUTHORITY | offline_real_science | 1 | unrun | executed_acceptance | 31a73b1162 | False | 3.707 | blocked: baseline_approval_cannot_start_design (F-HERO-NO-PAIR): needs a completed baseline with two candidates (see hero entry) |
| 39 | RS-FOLLOWUP | offline_real_science | 1 | unrun | executed_acceptance | 31a73b1162 | False | 0.379 | blocked: followup_prerequisites (F-HERO-NO-PAIR): needs the hero baseline run |
| 40 | RS-CANCEL-RESTART | offline_real_science | 1 | passed | executed_acceptance | 31a73b1162 | False | 5892.926 |  |
| 41 | RS-ZERO-DISPATCH | offline_real_science | 1 | passed | executed_acceptance | 31a73b1162 | False | 8.457 |  |
| 42 | RS-HERO-FULL | offline_real_science | 2 | failed | executed_acceptance | 5bcc917eb0 | True | 891.116 | failed: source_image_admitted, baseline_completed_with_evidence |
| 43 | RS-CHANGED-INPUT | offline_real_science | 2 | failed | executed_acceptance | 5bcc917eb0 | True | 423.595 | failed: baseline_completed_with_evidence |
| 44 | RS-RETRY-CONCURRENT | offline_real_science | 2 | passed | executed_acceptance | 5bcc917eb0 | True | 866.768 |  |
| 45 | RS-DESIGN-AUTHORITY | offline_real_science | 2 | unrun | executed_acceptance | 5bcc917eb0 | True | 3.132 | blocked: baseline_approval_cannot_start_design (F-HERO-NO-PAIR): needs a completed baseline with two candidates (see hero entry) |
| 46 | RS-FOLLOWUP | offline_real_science | 2 | unrun | executed_acceptance | 5bcc917eb0 | True | 0.355 | blocked: followup_prerequisites (F-HERO-NO-PAIR): needs the hero baseline run |
| 47 | RS-CANCEL-RESTART | offline_real_science | 2 | passed | executed_acceptance | 5bcc917eb0 | True | 5894.655 |  |
| 48 | RS-ZERO-DISPATCH | offline_real_science | 2 | passed | executed_acceptance | 5bcc917eb0 | True | 9.392 |  |
| 49 | RS-HERO-FULL | offline_real_science | 3 | failed | executed_acceptance | da5ecdc3f6 | False | 890.191 | failed: source_image_admitted, baseline_completed_with_evidence |
| 50 | RS-CHANGED-INPUT | offline_real_science | 3 | failed | executed_acceptance | da5ecdc3f6 | False | 429.228 | failed: baseline_completed_with_evidence |
| 51 | RS-RETRY-CONCURRENT | offline_real_science | 3 | passed | executed_acceptance | da5ecdc3f6 | False | 855.182 |  |
| 52 | RS-DESIGN-AUTHORITY | offline_real_science | 3 | unrun | executed_acceptance | da5ecdc3f6 | False | 3.239 | blocked: baseline_approval_cannot_start_design (F-HERO-NO-PAIR): needs a completed baseline with two candidates (see hero entry) |
| 53 | RS-FOLLOWUP | offline_real_science | 3 | unrun | executed_acceptance | da5ecdc3f6 | False | 0.245 | blocked: followup_prerequisites (F-HERO-NO-PAIR): needs the hero baseline run |
| 54 | RS-CANCEL-RESTART | offline_real_science | 3 | unrun | executed_acceptance | da5ecdc3f6 | False | 2929.675 | blocked: no_orphan_after_cancel (prerequisite): no sustained scientific computation existed at the cancellation point, so the orphan check would be vacuous (for |
| 55 | RS-ZERO-DISPATCH | offline_real_science | 3 | passed | executed_acceptance | da5ecdc3f6 | False | 8.978 |  |
| 56 | RS-HERO-FULL | offline_real_science | 4 | failed | executed_acceptance | 6b33d15406 | False | 84.368 | failed: scenario_completed_without_unexpected_response |
| 57 | RS-CHANGED-INPUT | offline_real_science | 4 | failed | executed_acceptance | 6b33d15406 | False | 1301.775 | failed: baseline_completed_with_evidence |
| 58 | RS-RETRY-CONCURRENT | offline_real_science | 4 | failed | executed_acceptance | 6b33d15406 | False | 7.933 | failed: scenario_completed_without_unexpected_response |
| 59 | RS-DESIGN-AUTHORITY | offline_real_science | 4 | failed | executed_acceptance | 6b33d15406 | False | 1.342 | failed: design_requires_usable_evidence_and_listed_candidates |
| 60 | RS-FOLLOWUP | offline_real_science | 4 | unrun | executed_acceptance | 6b33d15406 | False | 0.299 | blocked: followup_prerequisites (F-HERO-NO-PAIR): needs the hero baseline run |
| 61 | RS-CANCEL-RESTART | offline_real_science | 4 | failed | executed_acceptance | 6b33d15406 | False | 56.616 | failed: scenario_completed_without_unexpected_response |
| 62 | RS-ZERO-DISPATCH | offline_real_science | 4 | passed | executed_acceptance | 6b33d15406 | False | 84.333 |  |
| 63 | RS-HERO-FULL | offline_real_science | 5 | failed | executed_acceptance | d2d3c5393a | False | 926.186 | failed: baseline_completed_with_evidence |
| 64 | RS-CHANGED-INPUT | offline_real_science | 5 | failed | executed_acceptance | d2d3c5393a | False | 424.505 | failed: baseline_completed_with_evidence |
| 65 | RS-RETRY-CONCURRENT | offline_real_science | 5 | passed | executed_acceptance | d2d3c5393a | False | 891.551 |  |
| 66 | RS-DESIGN-AUTHORITY | offline_real_science | 5 | unrun | executed_acceptance | d2d3c5393a | False | 5.274 | blocked: baseline_approval_cannot_start_design (F-HERO-NO-PAIR): needs a completed baseline with two candidates (see hero entry) |
| 67 | RS-FOLLOWUP | offline_real_science | 5 | unrun | executed_acceptance | d2d3c5393a | False | 0.539 | blocked: followup_prerequisites (F-HERO-NO-PAIR): needs the hero baseline run |
| 68 | RS-CANCEL-RESTART | offline_real_science | 5 | unrun | executed_acceptance | d2d3c5393a | False | 3003.027 | blocked: no_orphan_after_cancel (prerequisite): no sustained scientific computation existed at the cancellation point, so the orphan check would be vacuous (for |
| 69 | RS-ZERO-DISPATCH | offline_real_science | 5 | passed | executed_acceptance | d2d3c5393a | False | 71.907 |  |
| 70 | RS-HERO-FULL | offline_real_science | 6 | failed | executed_acceptance | 8bb1fbeb13 | False | 562.364 | failed: baseline_completed_with_evidence |
| 71 | RS-CHANGED-INPUT | offline_real_science | 6 | failed | executed_acceptance | 8bb1fbeb13 | False | 1744.731 | failed: baseline_completed_with_evidence |
| 72 | RS-RETRY-CONCURRENT | offline_real_science | 6 | passed | executed_acceptance | 8bb1fbeb13 | False | 516.079 |  |
| 73 | RS-DESIGN-AUTHORITY | offline_real_science | 6 | unrun | executed_acceptance | 8bb1fbeb13 | False | 4.289 | blocked: baseline_approval_cannot_start_design (F-HERO-NO-PAIR): needs a completed baseline with two candidates (see hero entry) |
| 74 | RS-FOLLOWUP | offline_real_science | 6 | unrun | executed_acceptance | 8bb1fbeb13 | False | 0.476 | blocked: followup_prerequisites (F-HERO-NO-PAIR): needs the hero baseline run |
| 75 | RS-CANCEL-RESTART | offline_real_science | 6 | unrun | executed_acceptance | 8bb1fbeb13 | False | 3047.256 | blocked: no_orphan_after_cancel (prerequisite): no sustained scientific computation existed at the cancellation point, so the orphan check would be vacuous (for |
| 76 | RS-ZERO-DISPATCH | offline_real_science | 6 | passed | executed_acceptance | 8bb1fbeb13 | False | 73.821 |  |
| 77 | RS-RETRY-CONCURRENT | offline_real_science | 7 | passed | executed_acceptance | f8cf08a60a | False | 998.018 |  |
| 78 | RS-HERO-FULL | offline_real_science | 7 | failed | executed_acceptance | 3b55843a76 | False | 606.504 | failed: baseline_completed_with_evidence |
| 79 | RS-CHANGED-INPUT | offline_real_science | 7 | failed | executed_acceptance | 3b55843a76 | False | 1351.38 | failed: baseline_completed_with_evidence |
| 80 | RS-RETRY-CONCURRENT | offline_real_science | 8 | passed | executed_acceptance | 3b55843a76 | False | 987.13 |  |
| 81 | RS-DESIGN-AUTHORITY | offline_real_science | 7 | unrun | executed_acceptance | 3b55843a76 | False | 2.513 | blocked: baseline_approval_cannot_start_design (F-HERO-NO-PAIR): needs a completed baseline with two candidates (see hero entry) |
| 82 | RS-FOLLOWUP | offline_real_science | 7 | unrun | executed_acceptance | 3b55843a76 | False | 0.327 | blocked: followup_prerequisites (F-HERO-NO-PAIR): needs the hero baseline run |
| 83 | RS-CANCEL-RESTART | offline_real_science | 7 | unrun | executed_acceptance | 3b55843a76 | False | 2493.865 | blocked: no_orphan_after_cancel (prerequisite): no sustained scientific computation existed at the cancellation point, so the orphan check would be vacuous (for |
| 84 | RS-ZERO-DISPATCH | offline_real_science | 7 | passed | executed_acceptance | 3b55843a76 | False | 85.088 |  |
| 85 | RS-HERO-FULL | offline_real_science | 8 | failed | executed_acceptance | b827c61ade | False | 574.081 | failed: baseline_completed_with_evidence |
| 86 | RS-CHANGED-INPUT | offline_real_science | 8 | failed | executed_acceptance | b827c61ade | False | 1748.364 | failed: baseline_completed_with_evidence |
| 87 | RS-RETRY-CONCURRENT | offline_real_science | 9 | passed | executed_acceptance | b827c61ade | False | 554.692 |  |
| 88 | RS-DESIGN-AUTHORITY | offline_real_science | 8 | unrun | executed_acceptance | b827c61ade | False | 2.468 | blocked: baseline_approval_cannot_start_design (F-HERO-NO-PAIR): needs a completed baseline with two candidates (see hero entry) |
| 89 | RS-FOLLOWUP | offline_real_science | 8 | unrun | executed_acceptance | b827c61ade | False | 0.263 | blocked: followup_prerequisites (F-HERO-NO-PAIR): needs the hero baseline run |
| 90 | RS-CANCEL-RESTART | offline_real_science | 8 | unrun | executed_acceptance | b827c61ade | False | 3071.019 | blocked: no_orphan_after_cancel (prerequisite): no sustained scientific computation existed at the cancellation point, so the orphan check would be vacuous (for |
| 91 | RS-ZERO-DISPATCH | offline_real_science | 8 | passed | executed_acceptance | b827c61ade | False | 75.932 |  |
| 92 | RS-HERO-FULL | offline_real_science | 9 | failed | executed_acceptance | 0085414dd2 | False | 589.191 | failed: baseline_completed_with_evidence |
| 93 | RS-CHANGED-INPUT | offline_real_science | 9 | failed | executed_acceptance | 0085414dd2 | False | 1322.486 | failed: baseline_completed_with_evidence |
| 94 | RS-RETRY-CONCURRENT | offline_real_science | 10 | passed | executed_acceptance | 0085414dd2 | False | 952.428 |  |
| 95 | RS-DESIGN-AUTHORITY | offline_real_science | 9 | unrun | executed_acceptance | 0085414dd2 | False | 2.29 | blocked: baseline_approval_cannot_start_design (F-HERO-NO-PAIR): needs a completed baseline with two candidates (see hero entry) |
| 96 | RS-FOLLOWUP | offline_real_science | 9 | unrun | executed_acceptance | 0085414dd2 | False | 0.251 | blocked: followup_prerequisites (F-HERO-NO-PAIR): needs the hero baseline run |
| 97 | RS-CANCEL-RESTART | offline_real_science | 9 | unrun | executed_acceptance | 0085414dd2 | False | 3022.985 | blocked: no_orphan_after_cancel (prerequisite): no sustained scientific computation existed at the cancellation point, so the orphan check would be vacuous (for |
| 98 | RS-ZERO-DISPATCH | offline_real_science | 9 | passed | executed_acceptance | 0085414dd2 | False | 79.219 |  |
| 99 | RS-HERO-FULL | offline_real_science | 10 | passed | executed_acceptance | d821202b33 | False | 2503.807 |  |
| 100 | RS-CHANGED-INPUT | offline_real_science | 10 | passed | executed_acceptance | d821202b33 | False | 2586.803 |  |
| 101 | RS-RETRY-CONCURRENT | offline_real_science | 11 | passed | executed_acceptance | d821202b33 | False | 967.715 |  |
| 102 | RS-DESIGN-AUTHORITY | offline_real_science | 10 | passed | executed_acceptance | d821202b33 | False | 31.467 |  |
| 103 | RS-FOLLOWUP | offline_real_science | 10 | passed | executed_acceptance | d821202b33 | False | 12337.699 |  |
| 104 | RS-CANCEL-RESTART | offline_real_science | 10 | passed | executed_acceptance | d821202b33 | False | 7355.238 |  |
| 105 | RS-ZERO-DISPATCH | offline_real_science | 10 | passed | executed_acceptance | d821202b33 | False | 104.189 |  |
| 106 | RS-HERO-FULL | offline_real_science | 11 | passed | executed_acceptance | 159fd65303 | False | 3374.17 |  |
| 107 | RS-CHANGED-INPUT | offline_real_science | 11 | passed | executed_acceptance | 159fd65303 | False | 2630.926 |  |
| 108 | RS-RETRY-CONCURRENT | offline_real_science | 12 | passed | executed_acceptance | 159fd65303 | False | 1517.336 |  |
| 109 | RS-DESIGN-AUTHORITY | offline_real_science | 11 | passed | executed_acceptance | 159fd65303 | False | 59.357 |  |
| 110 | RS-FOLLOWUP | offline_real_science | 11 | passed | executed_acceptance | 159fd65303 | False | 13066.414 |  |
| 111 | RS-CANCEL-RESTART | offline_real_science | 11 | passed | executed_acceptance | 159fd65303 | False | 7244.179 |  |
| 112 | RS-ZERO-DISPATCH | offline_real_science | 11 | passed | executed_acceptance | 159fd65303 | False | 132.418 |  |

# Findings (generated from evaluation/findings.json; edit the JSON, then run `cli.py findings`)

Application code commit `586fb9bd2604`, observed with harness `da5ecdc3f6ad` on macOS 26.7 (25G227) arm64; backend CPython 3.13.18 (uv-locked .venv); replay CPython 3.11.17.

| ID | Sev | Owner | Status | Title |
|---|---|---|---|---|
| F-PLATFORM-RLIMIT | P0 | 2 | open | Valid PNG refused and every scientific worker fails on the team's Mac (RLIMIT_AS rejected) |
| F-ADAPTER-SELECTION | P0 | 2 (with 1 for the runtime bridge) | open | Ordinary API and worker startup select UnavailableAdapter; no real scientific path exists through HTTP |
| F-BASELINE-DISCOVERY | P0 | 1 | open | Counterdex has no bounded baseline candidate-discovery operation (investigate) |
| F-NATIVE-BYTES | P0 | 2 (bytes, anchor record) and 1 (complete packet) | open | No authenticated route returns native packet bytes; /artifacts/{id} serves the entity envelope; records expose no scientific anchors |
| F-FOLLOWUP-FEEDBACK | P0 | 1 and 2 | open | No application route reports candidate-specific outcomes for the prior pair after a hypothetical reading |
| F-PLACEHOLDER-AUTO | P0 | 3 | open | The legacy documented live switch (dummy values only) constructs google.genai.Client and attempts dispatch |
| F-PLACEHOLDER-MODE | P1 | 3 | open | Capabilities declare no explicit placeholder/disabled provider mode |
| F-OPTIONAL-VANISHES | P1 | 3 (graph) and 2 (callbacks) | open | The actual deepagents graph completes while a reviewed optional scenario is neither executed nor skipped |
| F-CONTROLLED-PROVENANCE | P1 | 3 | open | Controlled-model turns are reserved as provider 'gemini' attempts with no placeholder marker |
| F-REVIEW-MATERIALIZATION | P1 | 2 | open | An accepted intake review creates no dataset association (source values never reach execution) |
| F-RESTART-UNOBSERVABLE | P1 | 2 (after F-PLATFORM-RLIMIT) | open | Cancellation and worker-restart orphan checks cannot be observed: no sustained scientific computation exists yet |
| F-LINT-CHECKLIST | P2 | 4 | open | Documented lint command fails on scripts/release/checklist.py (unused import drbean_eval.contract) |
| H-ORACLE-BOUNDARIES | P1 | 5 | retested | Harness contract oracle accepted inputs the API rejects (trailing newline, -0, depth 64, digit caps) |
| H-BUDGET-USAGE | P1 | 5 | retested | Harness JSONL budget accepted negative usage and counted one request per reservation |
| H-COMPLETED-QUALIFIES | P0 | 5 | retested | Merged harness passed a case-less full-stack entry on state == completed alone |
| H-VACUOUS-ORPHAN | P1 | 5 | retested | First lane run passed orphan/restart checks vacuously (child died at setup); attempt retained |
| H-DIRTY-FLAG | P1 | 5 | retested | git_state stripped porcelain output and marked every record dirty (since harness 0.1.0) |

## F-PLATFORM-RLIMIT (P0, owner 2, open)

- **Input:** fixtures/intake/clean.png (sha256 6363da39...0b06); any approved manual plan
- **Command:** `python3.11 evaluation/cli.py run --lane offline_real_science --subject http-launch --only RS-HERO-FULL`
- **Expected:** POST source-assets -> 201 (1200x1550 PNG); baseline run completes with evidence
- **Observed:** 422 malformed_image; run state failed, error scientific_worker_failed, scenario scientific_attempt_failed. setrlimit(RLIMIT_AS) raises ValueError 'current limit exceeds maximum limit' (soft/hard already RLIM_INFINITY) in _image_decode.py and science.py _child
- **Evidence:** {"attempts": ["att_95b6fad90f3740e4", "att_e74991a9307e41d4"], "baseline_suite": "136 passed, 17 failed, 11 errors at 586fb9b (identical to the audit)", "tests": ["tests/test_evaluation.py::test_synthetic_corpus_passes_real_media_admission", "tests/integration/test_http_lifecycle_and_science.py::test_hero_full_loop_real_science_design_download_and_native_replay"]}

## F-ADAPTER-SELECTION (P0, owner 2 (with 1 for the runtime bridge), open)

- **Input:** default launch (python -m uvicorn bean_api.main:create_app --factory; python -m bean_api.worker)
- **Command:** `python3.11 evaluation/cli.py run --lane offline_real_science --subject http-launch`
- **Expected:** readiness.science.ready true (implemented, configured, verified_in_environment) and real discovery/checking on supplied input
- **Observed:** capabilities.science {implemented:false, configured:false, verified_in_environment:false, reason:groundwork_adapter_not_installed} (lane-runs.jsonl subject_start.readiness)
- **Evidence:** {"attempts": ["att_95b6fad90f3740e4"], "lane_run": "last entry of evaluation/results/lane-runs.jsonl"}

## F-BASELINE-DISCOVERY (P0, owner 1, open)

- **Input:** evaluation/cases/science/hero-v1.json
- **Command:** `PYTHONPATH=packages/groundwork_adapter python3.11 -c 'import counterdex; print(counterdex.__all__)'`
- **Expected:** an operation that searches the supplied reviewed input, freezes exact vectors and freshly checks them
- **Observed:** public API exposes normalize/create_suggestion/replay_bundle for a supplied fixed pair only
- **Evidence:** {"note": "engine-level fixed-pair controls pass (controls.jsonl); discovery is the missing join, not the checker"}

## F-NATIVE-BYTES (P0, owner 2 (bytes, anchor record) and 1 (complete packet), open)

- **Input:** any completed run with ArtifactReference entries
- **Command:** `RS-HERO-FULL checks baseline_native_bytes_downloadable and *_anchor_from_authenticated_record`
- **Expected:** GET returns exact referenced bytes (sha/length/media type match reference and X-Artifact-SHA256); replay anchors come from the expected-run record
- **Observed:** not yet reachable through HTTP at this commit because F-PLATFORM-RLIMIT/F-ADAPTER-SELECTION stop the run first; code inspection: main.py artifact() returns canonical_bytes(record) for evidence/suggestion/report kinds only
- **Evidence:** {"anchor_field_names_accepted": "evaluation/drbean_eval/native.py ANCHOR_KEYS (agree final names with Owner 2)", "harness": "evaluation/drbean_eval/science_flow.py Flow.download tries /artifacts/{id} and /artifacts/{id}/content and classifies envelopes"}

## F-FOLLOWUP-FEEDBACK (P0, owner 1 and 2, open)

- **Input:** hero design pair + hypothetical 3.4 / 4.57 / 4.0 mg/L at the selected time, allowance 0.2
- **Command:** `python3.11 evaluation/cli.py run --lane offline_real_science --subject http-launch --only RS-HERO-FULL RS-FOLLOWUP`
- **Expected:** new hypothetical lineage + new approval, then per-candidate compatible/excluded for the prior pair that agrees with the independent decimal oracle; aggregate exclusion reported as scientific feedback, not corruption
- **Observed:** lineage, origin labelling and new-approval requirement work over HTTP; per-candidate feedback has no route (harness accepts prior_candidate_results / candidate_results); blocked behind the hero run
- **Evidence:** {"attempts": ["att_003a52ad356c4088"], "engine_controls": "followup:3.4/4.57/4.0 pass at engine level"}

## F-PLACEHOLDER-AUTO (P0, owner 3, open)

- **Input:** GEMINI_API_KEY=DRBEAN-DUMMY-KEY-0001 GEMINI_MODEL=drbean-placeholder-model BEAN_GEMINI_ACCOUNT_GATE=approved BEAN_GEMINI_ACCOUNT_DECISION_ID=DRBEAN-DUMMY-DECISION-0001 BEAN_GEMINI_IMAGE_TOKEN_BOUND=1000; POST /workspaces/{id}/assistant-turns (explain, consented)
- **Command:** `.venv/bin/python -m pytest tests/integration/test_zero_dispatch.py -k legacy_documented_live_switch`
- **Expected:** no network-capable client construction or dispatch unless a NEW explicit mode switch (authorized by a new user instruction) is set; placeholder by default
- **Observed:** egress guard recorded provider_client_blocked google.genai.Client from main.py:assistant_turn -> conversation.py:363 submit -> providers.py:231 generate for each consented turn, and the worker coordinator path; the guard refused it so nothing left the machine
- **Evidence:** {"clean_paths": "default configuration and dummy key alone: zero attempts (tests pass)", "tests": ["tests/integration/test_zero_dispatch.py::test_legacy_documented_live_switch_with_dummy_values_still_cannot_dispatch"]}

## F-PLACEHOLDER-MODE (P1, owner 3, open)

- **Input:** GET /api/bean/v1/capabilities on a default launch
- **Command:** `.venv/bin/python -m pytest tests/integration/test_zero_dispatch.py -k placeholder_mode_is_explicit`
- **Expected:** capabilities.gemini.mode (or provider_mode) = placeholder / disabled / controlled_placeholder
- **Observed:** no mode field; only configured:false / unavailable_reason provider_not_configured
- **Evidence:** {"lane": "RS-ZERO-DISPATCH informational check explicit_placeholder_mode_reported = blocked"}

## F-OPTIONAL-VANISHES (P1, owner 3 (graph) and 2 (callbacks), open)

- **Input:** scripted model: execute baseline, then return_grounded_explanation
- **Command:** `.venv/bin/python -m pytest tests/integration/test_ai_boundaries.py -k optional_scenario_cannot_silently_vanish`
- **Expected:** completion only when every reviewed optional scenario is executed or explicitly skipped; otherwise unresolved/failed
- **Observed:** CoordinatorResult status completed, optional scenario unaccounted
- **Evidence:** {"tests": ["tests/integration/test_ai_boundaries.py::test_reviewed_optional_scenario_cannot_silently_vanish"]}

## F-CONTROLLED-PROVENANCE (P1, owner 3, open)

- **Input:** run_coordinator with a controlled chat_model
- **Command:** `.venv/bin/python -m pytest tests/integration/test_ai_boundaries.py -k masquerade`
- **Expected:** controlled turns carry explicit controlled/placeholder provenance and never read as live-provider attempts
- **Observed:** BudgetMiddleware begin_attempt metadata provider=gemini, framework deepagents, no execution_lane/transport marker; in the worker these rows enter the real provider_attempts table
- **Evidence:** {"tests": ["tests/integration/test_ai_boundaries.py::test_controlled_turns_never_masquerade_as_live_provider_attempts"]}

## F-REVIEW-MATERIALIZATION (P1, owner 2, open)

- **Input:** controlled clean proposal, every field confirmed
- **Command:** `.venv/bin/python -m pytest tests/integration/test_ai_boundaries.py -k clean_proposal_stays_unreviewed`
- **Expected:** a server-enforced review -> exact dataset materialization (still requiring separate plan approval)
- **Observed:** intake_review record only; zero datasets (safe: nothing is auto-accepted, but the join is missing)
- **Evidence:** {"audit": "AUDIT_AND_NEXT_STEPS P1 'Bind reviewed source values to execution'"}

## F-RESTART-UNOBSERVABLE (P1, owner 2 (after F-PLATFORM-RLIMIT), open)

- **Input:** RS-CANCEL-RESTART
- **Command:** `python3.11 evaluation/cli.py run --lane offline_real_science --subject http-launch --only RS-CANCEL-RESTART`
- **Expected:** a live scientific child at cancel / worker kill, gone afterwards; interrupted run not redispatched
- **Observed:** queued cancellation and recovery semantics pass; running-child checks not_observed (child dies at setup)
- **Evidence:** {"attempts": ["att_ea42f9e1c5bf4b23"]}

## F-LINT-CHECKLIST (P2, owner 4, open)

- **Input:** repository at 586fb9b
- **Command:** `.venv/bin/ruff check apps tests scripts`
- **Expected:** All checks passed
- **Observed:** F401 scripts/release/checklist.py:25 drbean_eval.contract imported but unused
- **Evidence:** {}

# Findings (generated from evaluation/findings.json; edit the JSON, then run `cli.py findings`)

Application code commit `adac9452 (or`, observed with harness `d2d3c53` on macOS 26.7 (25G227) arm64; backend CPython 3.13.18 (uv-locked .venv); replay CPython 3.11.17.

| ID | Sev | Owner | Status | Title |
|---|---|---|---|---|
| F-PLATFORM-RLIMIT | P0 | 2 | retested | Valid PNG refused and every scientific worker fails on the team's Mac (RLIMIT_AS rejected) |
| F-ADAPTER-SELECTION | P0 | 2 (with 1 for the runtime bridge) | retested | Ordinary API and worker startup select UnavailableAdapter; no real scientific path exists through HTTP |
| F-BASELINE-DISCOVERY | P0 | 1 (producer) and 2 (adapter wiring) | open | Counterdex has no bounded baseline candidate-discovery operation (investigate) |
| F-NATIVE-BYTES | P0 | 2 (bytes, anchor record) and 1 (complete packet) | fixed_pending_retest | No authenticated route returns native packet bytes; /artifacts/{id} serves the entity envelope; records expose no scientific anchors |
| F-FOLLOWUP-FEEDBACK | P0 | 1 and 2 | open | No application route reports candidate-specific outcomes for the prior pair after a hypothetical reading |
| F-PLACEHOLDER-AUTO | P0 | 3 | retested | The legacy documented live switch (dummy values only) constructs google.genai.Client and attempts dispatch |
| F-PLACEHOLDER-MODE | P1 | 3 | retested | Capabilities declare no explicit placeholder/disabled provider mode |
| F-OPTIONAL-VANISHES | P1 | 3 (graph) and 2 (callbacks) | retested | The actual deepagents graph completes while a reviewed optional scenario is neither executed nor skipped |
| F-CONTROLLED-PROVENANCE | P1 | 3 | retested | Controlled-model turns are reserved as provider 'gemini' attempts with no placeholder marker |
| F-REVIEW-MATERIALIZATION | P1 | 2 | fixed_pending_retest | An accepted intake review creates no dataset association (source values never reach execution) |
| F-RESTART-UNOBSERVABLE | P1 | 2 (after F-PLATFORM-RLIMIT) | open | Cancellation and worker-restart orphan checks cannot be observed: no sustained scientific computation exists yet |
| F-LINT-CHECKLIST | P2 | 4 | open | Documented lint command fails on scripts/release/checklist.py (unused import drbean_eval.contract) |
| F-MAC-NPROC | P0 | 2 | open | On macOS every scientific job fails: RLIMIT_NPROC is per user, so the bounded child cannot spawn CPython 3.11 |
| F-COORDINATOR-OPTIONAL-STATUS | P2 | 3 | open | run_coordinator reports completed while a reviewed optional scenario is unaccounted (enforced downstream by the workflow) |
| F-COORDINATOR-PROVIDER-LABEL | P2 | 3 | open | Coordinator attempt metadata names provider gemini for controlled-model turns |
| F-TEST-VAR-LEAK | P2 | 2 | open | Backend test fixtures build Settings without artifact_dir, creating the repo-relative var/artifacts |
| H-ORACLE-BOUNDARIES | P1 | 5 | retested | Harness contract oracle accepted inputs the API rejects (trailing newline, -0, depth 64, digit caps) |
| H-BUDGET-USAGE | P1 | 5 | retested | Harness JSONL budget accepted negative usage and counted one request per reservation |
| H-COMPLETED-QUALIFIES | P0 | 5 | retested | Merged harness passed a case-less full-stack entry on state == completed alone |
| H-VACUOUS-ORPHAN | P1 | 5 | retested | First lane run passed orphan/restart checks vacuously (child died at setup); attempt retained |
| H-DIRTY-FLAG | P1 | 5 | retested | git_state stripped porcelain output and marked every record dirty (since harness 0.1.0) |

## F-PLATFORM-RLIMIT (P0, owner 2, retested)

- **Input:** fixtures/intake/clean.png (sha256 6363da39...0b06); any approved manual plan
- **Command:** `python3.11 evaluation/cli.py run --lane offline_real_science --subject http-launch --only RS-HERO-FULL`
- **Expected:** POST source-assets -> 201 (1200x1550 PNG); baseline run completes with evidence
- **Observed:** 422 malformed_image; run state failed, error scientific_worker_failed, scenario scientific_attempt_failed. setrlimit(RLIMIT_AS) raises ValueError 'current limit exceeds maximum limit' (soft/hard already RLIM_INFINITY) in _image_decode.py and science.py _child
- **Evidence:** {"attempts": ["att_95b6fad90f3740e4", "att_e74991a9307e41d4"], "baseline_suite": "136 passed, 17 failed, 11 errors at 586fb9b (identical to the audit)", "tests": ["tests/test_evaluation.py::test_synthetic_corpus_passes_real_media_admission", "tests/integration/test_http_lifecycle_and_science.py::test_hero_full_loop_real_science_design_download_and_native_replay"]}
- **Retest at adac945 via merge 1862ebf (harness d2d3c53):** Image decoder fixed on this Mac: valid clean.png admitted 1200x1550 through the real API (resource policy now reports RLIMIT_AS unavailable on Darwin). Scientific-worker failures on the Mac now have a different cause, tracked as F-MAC-NPROC. (evidence: {"attempts": ["att_87537746fa40470d (source_image_admitted passed)"], "backend_suite": "265 passed, 4 failed (was 136/17/11); the RLIMIT_AS image tests pass"})

## F-ADAPTER-SELECTION (P0, owner 2 (with 1 for the runtime bridge), retested)

- **Input:** default launch (python -m uvicorn bean_api.main:create_app --factory; python -m bean_api.worker)
- **Command:** `python3.11 evaluation/cli.py run --lane offline_real_science --subject http-launch`
- **Expected:** readiness.science.ready true (implemented, configured, verified_in_environment) and real discovery/checking on supplied input
- **Observed:** capabilities.science {implemented:false, configured:false, verified_in_environment:false, reason:groundwork_adapter_not_installed} (lane-runs.jsonl subject_start.readiness)
- **Evidence:** {"attempts": ["att_95b6fad90f3740e4"], "lane_run": "last entry of evaluation/results/lane-runs.jsonl"}
- **Retest at adac945 via merge 1862ebf (harness d2d3c53):** Ordinary API startup selects Counterdex (capabilities.science: implemented, configured, available via the 3.11 probe); the worker uses the same factory. (evidence: {"lane_run": "lane-runs.jsonl readiness at d2d3c53: science.runtime_available true, baseline_discovery false"})

## F-BASELINE-DISCOVERY (P0, owner 1 (producer) and 2 (adapter wiring), open)

- **Input:** evaluation/cases/science/hero-v1.json
- **Command:** `PYTHONPATH=packages/groundwork_adapter python3.11 -c 'import counterdex; print(counterdex.__all__)'`
- **Expected:** an operation that searches the supplied reviewed input, freezes exact vectors and freshly checks them
- **Observed:** public API exposes normalize/create_suggestion/replay_bundle for a supplied fixed pair only
- **Evidence:** {"note": "engine-level fixed-pair controls pass (controls.jsonl); discovery is the missing join, not the checker"}
- **Retest at adac945 via merge 1862ebf (harness d2d3c53):** Still open on main: CounterdexAdapter.investigate returns unsupported/baseline_producer_unavailable by design (Owner 2 BACKEND_INTEGRATION.md). Counterdex baseline.py/search.py are merged but not wired; the unmerged branch backend/browser-baseline (cc779bf) appears to wire computed baseline evidence and is next to preview. (evidence: {"backend_test": "tests/test_scientific_http.py::test_ordinary_http_baseline_is_honestly_blocked_without_a_producer"})

## F-NATIVE-BYTES (P0, owner 2 (bytes, anchor record) and 1 (complete packet), fixed_pending_retest)

- **Input:** any completed run with ArtifactReference entries
- **Command:** `RS-HERO-FULL checks baseline_native_bytes_downloadable and *_anchor_from_authenticated_record`
- **Expected:** GET returns exact referenced bytes (sha/length/media type match reference and X-Artifact-SHA256); replay anchors come from the expected-run record
- **Observed:** not yet reachable through HTTP at this commit because F-PLATFORM-RLIMIT/F-ADAPTER-SELECTION stop the run first; code inspection: main.py artifact() returns canonical_bytes(record) for evidence/suggestion/report kinds only
- **Evidence:** {"anchor_field_names_accepted": "evaluation/drbean_eval/native.py ANCHOR_KEYS (agree final names with Owner 2)", "harness": "evaluation/drbean_eval/science_flow.py Flow.download tries /artifacts/{id} and /artifacts/{id}/content and classifies envelopes"}
- **Retest at adac945 via merge 1862ebf (harness d2d3c53):** Implemented on main: GET /artifacts/{id} returns native bytes with X-Artifact-SHA256 and GET /artifacts/{id}/anchor returns scientific_problem_digest / native_suggestion_digest. Not yet exercised through HTTP here: no run produces artifacts (discovery unavailable; F-MAC-NPROC on this Mac). Harness updated to use the anchor route. (evidence: {"code": "apps/api/bean_api/main.py artifact(), artifact_anchor()"})

## F-FOLLOWUP-FEEDBACK (P0, owner 1 and 2, open)

- **Input:** hero design pair + hypothetical 3.4 / 4.57 / 4.0 mg/L at the selected time, allowance 0.2
- **Command:** `python3.11 evaluation/cli.py run --lane offline_real_science --subject http-launch --only RS-HERO-FULL RS-FOLLOWUP`
- **Expected:** new hypothetical lineage + new approval, then per-candidate compatible/excluded for the prior pair that agrees with the independent decimal oracle; aggregate exclusion reported as scientific feedback, not corruption
- **Observed:** lineage, origin labelling and new-approval requirement work over HTTP; per-candidate feedback has no route (harness accepts prior_candidate_results / candidate_results); blocked behind the hero run
- **Evidence:** {"attempts": ["att_003a52ad356c4088"], "engine_controls": "followup:3.4/4.57/4.0 pass at engine level"}
- **Retest at adac945 via merge 1862ebf (harness d2d3c53):** ScientificResult now carries candidate_results; Owner 1's unmerged codex/science-next adds original-candidate observation rechecks. No integrated HTTP route yet exercised here (blocked behind the hero run). (evidence: {"attempts": ["att_86aae8c45eb24619"]})

## F-PLACEHOLDER-AUTO (P0, owner 3, retested)

- **Input:** GEMINI_API_KEY=DRBEAN-DUMMY-KEY-0001 GEMINI_MODEL=drbean-placeholder-model BEAN_GEMINI_ACCOUNT_GATE=approved BEAN_GEMINI_ACCOUNT_DECISION_ID=DRBEAN-DUMMY-DECISION-0001 BEAN_GEMINI_IMAGE_TOKEN_BOUND=1000; POST /workspaces/{id}/assistant-turns (explain, consented)
- **Command:** `.venv/bin/python -m pytest tests/integration/test_zero_dispatch.py -k legacy_documented_live_switch`
- **Expected:** no network-capable client construction or dispatch unless a NEW explicit mode switch (authorized by a new user instruction) is set; placeholder by default
- **Observed:** egress guard recorded provider_client_blocked google.genai.Client from main.py:assistant_turn -> conversation.py:363 submit -> providers.py:231 generate for each consented turn, and the worker coordinator path; the guard refused it so nothing left the machine
- **Evidence:** {"clean_paths": "default configuration and dummy key alone: zero attempts (tests pass)", "tests": ["tests/integration/test_zero_dispatch.py::test_legacy_documented_live_switch_with_dummy_values_still_cannot_dispatch"]}
- **Retest at adac945 via merge 1862ebf (harness d2d3c53):** Fixed on main: provider_config_from_env() returns ProviderConfig() and reads no Gemini variable; the legacy documented live switch with dummy values now produces zero client constructions and zero egress. (evidence: {"tests": ["tests/integration/test_zero_dispatch.py::test_legacy_documented_live_switch_with_dummy_values_still_cannot_dispatch (passed)"]})

## F-PLACEHOLDER-MODE (P1, owner 3, retested)

- **Input:** GET /api/bean/v1/capabilities on a default launch
- **Command:** `.venv/bin/python -m pytest tests/integration/test_zero_dispatch.py -k placeholder_mode_is_explicit`
- **Expected:** capabilities.gemini.mode (or provider_mode) = placeholder / disabled / controlled_placeholder
- **Observed:** no mode field; only configured:false / unavailable_reason provider_not_configured
- **Evidence:** {"lane": "RS-ZERO-DISPATCH informational check explicit_placeholder_mode_reported = blocked"}
- **Retest at adac945 via merge 1862ebf (harness d2d3c53):** Fixed on main: capabilities.ai_mode = disabled_placeholder, gemini.dispatch_enabled = false, live_qualification not_run. (evidence: {"attempts": ["att_096ce3cf92d44583 (explicit_placeholder_mode_reported passed)"], "tests": ["tests/integration/test_zero_dispatch.py::test_placeholder_mode_is_explicit_in_capabilities (passed)"]})

## F-OPTIONAL-VANISHES (P1, owner 3 (graph) and 2 (callbacks), retested)

- **Input:** scripted model: execute baseline, then return_grounded_explanation
- **Command:** `.venv/bin/python -m pytest tests/integration/test_ai_boundaries.py -k optional_scenario_cannot_silently_vanish`
- **Expected:** completion only when every reviewed optional scenario is executed or explicitly skipped; otherwise unresolved/failed
- **Observed:** CoordinatorResult status completed, optional scenario unaccounted
- **Evidence:** {"tests": ["tests/integration/test_ai_boundaries.py::test_reviewed_optional_scenario_cannot_silently_vanish"]}
- **Retest at adac945 via merge 1862ebf (harness d2d3c53):** Resolved at the integrated boundary: Workflow.finish_run refuses completion (scenario_accounting_incomplete) unless every reviewed scenario is completed or skipped; the real Worker + deepagents graph with a controlled model ends failed. The coordinator module alone still reports completed (residual P2 F-COORDINATOR-OPTIONAL-STATUS). (evidence: {"tests": ["tests/integration/test_ai_boundaries.py::test_worker_refuses_completion_when_a_reviewed_optional_scenario_vanishes (passed)"]})

## F-CONTROLLED-PROVENANCE (P1, owner 3, retested)

- **Input:** run_coordinator with a controlled chat_model
- **Command:** `.venv/bin/python -m pytest tests/integration/test_ai_boundaries.py -k masquerade`
- **Expected:** controlled turns carry explicit controlled/placeholder provenance and never read as live-provider attempts
- **Observed:** BudgetMiddleware begin_attempt metadata provider=gemini, framework deepagents, no execution_lane/transport marker; in the worker these rows enter the real provider_attempts table
- **Evidence:** {"tests": ["tests/integration/test_ai_boundaries.py::test_controlled_turns_never_masquerade_as_live_provider_attempts"]}
- **Retest at adac945 via merge 1862ebf (harness d2d3c53):** Resolved at the integrated boundary: the Worker records controlled turns as controlled_attempt/controlled_outcome records (execution_lane controlled_placeholder, zero calls and tokens); provider_attempts stays empty. The coordinator's own metadata still says provider gemini inside simulated_reservation (residual P2 F-COORDINATOR-PROVIDER-LABEL). My earlier claim that these rows reach the real provider ledger was true of 586fb9b's worker path only as a risk and is not true on main. (evidence: {"tests": ["tests/integration/test_ai_boundaries.py::test_worker_records_controlled_turns_outside_the_provider_ledger (passed)"]})

## F-REVIEW-MATERIALIZATION (P1, owner 2, fixed_pending_retest)

- **Input:** controlled clean proposal, every field confirmed
- **Command:** `.venv/bin/python -m pytest tests/integration/test_ai_boundaries.py -k clean_proposal_stays_unreviewed`
- **Expected:** a server-enforced review -> exact dataset materialization (still requiring separate plan approval)
- **Observed:** intake_review record only; zero datasets (safe: nothing is auto-accepted, but the join is missing)
- **Evidence:** {"audit": "AUDIT_AND_NEXT_STEPS P1 'Bind reviewed source values to execution'"}
- **Retest at adac945 via merge 1862ebf (harness d2d3c53):** main adds POST /workspaces/{id}/intake-reviews/{review_id}/materialize and refuses direct datasets citing a source (source_review_required, verified over HTTP in RS-HERO-FULL). Materialization itself not yet exercised by this harness. (evidence: {"attempts": ["att_87537746fa40470d (source_linked_values_require_review passed)"]})

## F-RESTART-UNOBSERVABLE (P1, owner 2 (after F-PLATFORM-RLIMIT), open)

- **Input:** RS-CANCEL-RESTART
- **Command:** `python3.11 evaluation/cli.py run --lane offline_real_science --subject http-launch --only RS-CANCEL-RESTART`
- **Expected:** a live scientific child at cancel / worker kill, gone afterwards; interrupted run not redispatched
- **Observed:** queued cancellation and recovery semantics pass; running-child checks not_observed (child dies at setup)
- **Evidence:** {"attempts": ["att_ea42f9e1c5bf4b23"]}
- **Retest at adac945 via merge 1862ebf (harness d2d3c53):** Still unobservable on this Mac: no scientific child survives setup (F-MAC-NPROC). Queued cancellation passes. (evidence: {"attempts": ["att_e1326b12871140f2"]})

## F-LINT-CHECKLIST (P2, owner 4, open)

- **Input:** repository at 586fb9b
- **Command:** `.venv/bin/ruff check apps tests scripts`
- **Expected:** All checks passed
- **Observed:** F401 scripts/release/checklist.py:25 drbean_eval.contract imported but unused
- **Evidence:** {}
- **Retest at adac945 via merge 1862ebf (harness d2d3c53):** Still failing on main: ruff check apps tests scripts reports 1 error. (evidence: {"command": ".venv/bin/ruff check apps tests scripts"})

## F-MAC-NPROC (P0, owner 2, open)

- **Input:** macOS 26.7 arm64 user with 649 processes; resource policy process cap 32 (process_count: rlimit_nproc_per_user)
- **Command:** `.venv/bin/python -c "import os,resource,subprocess; pid=os.fork()\nif pid==0:\n resource.setrlimit(resource.RLIMIT_NPROC,(32,32)); subprocess.run(['/usr/bin/true'])"  -> BlockingIOError Errno 35; also BEAN_COUNTERDEX_PYTHON=/opt/homebrew/bin/python3.11 .venv/bin/python -m pytest tests/test_science_boundary.py tests/test_scientific_http.py`
- **Expected:** the supervised child launches the prepared CPython 3.11 runtime on the team's Mac; process-tree containment comes from the owned session/process group
- **Observed:** spawn fails with EAGAIN at caps 32 and 64 (passes at 4000); runs end failed with scientific_runtime_unavailable / scientific_worker_failed; 4 backend tests fail on the Mac only (Linux run passed)
- **Evidence:** {"attempts": ["att_87537746fa40470d", "att_adf816f75f9b4d1a"], "backend_tests": ["test_science_boundary.py::test_cancellation_terminates_descendants", "test_science_boundary.py::test_descendant_cannot_escape_by_outliving_adapter", "test_scientific_http.py::test_ordinary_http_baseline_is_honestly_blocked_without_a_producer", "test_scientific_http.py::test_explicit_seed_pair_real_design_download_and_independent_replay"], "suggested_seam": "treat RLIMIT_NPROC on Darwin like RLIMIT_AS (report unavailable) or set it to current user process count + a small margin; keep the owned-session kill and wall clock"}

## F-COORDINATOR-OPTIONAL-STATUS (P2, owner 3, open)

- **Input:** scripted model: execute baseline, then return_grounded_explanation
- **Command:** `.venv/bin/python -m pytest tests/integration/test_ai_boundaries.py -k optional_scenario_cannot_silently_vanish`
- **Expected:** the coordinator itself reports an unresolved disposition
- **Observed:** status completed (strict xfail)
- **Evidence:** {}

## F-COORDINATOR-PROVIDER-LABEL (P2, owner 3, open)

- **Input:** run_coordinator with a controlled chat_model
- **Command:** `.venv/bin/python -m pytest tests/integration/test_ai_boundaries.py -k masquerade`
- **Expected:** controlled turns carry an explicit controlled/placeholder marker at the source
- **Observed:** metadata provider=gemini; the worker wraps it in controlled_attempt records, so no live-looking row reaches the provider ledger (strict xfail)
- **Evidence:** {}

## F-TEST-VAR-LEAK (P2, owner 2, open)

- **Input:** tests/test_api.py client fixture (Settings(database_path=..., blob_dir=..., auth_tokens=...))
- **Command:** `.venv/bin/python -m pytest -q tests/test_api.py; ls var/artifacts`
- **Expected:** test runs write only to tmp_path
- **Observed:** an empty var/artifacts appeared in the working tree (removed)
- **Evidence:** {"note": "Workstream 5's own fixture had the same omission and now sets artifact_dir"}

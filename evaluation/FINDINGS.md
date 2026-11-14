# Findings (generated from evaluation/findings.json; edit the JSON, then run `cli.py findings`)

Application code commit `4b5f1f5`, observed with harness `c8d39b5` on macOS 26.7 (25G227) arm64; backend CPython 3.13.18 (uv-locked .venv); replay CPython 3.11.17.

| ID | Sev | Owner | Status | Title |
|---|---|---|---|---|
| F-ORPHAN-WORKER-KILL | P0 | 2 | retested | A scientific child survives its worker's death and keeps computing after the job is marked interrupted |
| F-AI-INTEGRATION-SEAM | P1 | 2 and 3 | retested | Merging Owner 3's placeholder-mode branch onto main breaks the worker's controlled agent lane |
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
| F-LINT-CHECKLIST | P2 | 4 | retested | Documented lint command fails on scripts/release/checklist.py (unused import drbean_eval.contract) |
| F-MAC-NPROC | P0 | 2 | retested | On macOS every scientific job fails: RLIMIT_NPROC is per user, so the bounded child cannot spawn CPython 3.11 |
| F-COORDINATOR-OPTIONAL-STATUS | P2 | 3 | retested | run_coordinator reports completed while a reviewed optional scenario is unaccounted (enforced downstream by the workflow) |
| F-COORDINATOR-PROVIDER-LABEL | P2 | 3 | retested | Coordinator attempt metadata names provider gemini for controlled-model turns |
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
| H-CI-ENGINE | P1 | 5 | retested | Harness on main does not find Owner 4's prepared .venv-engine, so CI's integration suite runs science without an engine |
| F-LAUNCHER-HIDDEN-PTH | P1 | 4 | retested | One-command launch fails on the team Mac: iCloud Drive hides the dot-named .venv, CPython skips its editable .pth, so bean_api cannot be imported (doctor still reports the backend ready) |
| F-LAUNCHER-ENV-READ | P2 | 4 | retested | Launcher reads provider credential values while removing them, and its doctor probes inherit the unscrubbed environment |
| H-ORPHAN-TEARDOWN | P1 | 5 | retested | Harness teardown let an orphaned scientific computation resume and outlive the run |
| F-EXPLANATION-QUALIFIER | P2 | 3 | fixed_pending_retest | An overclaim passes the explanation guard whenever any hedge word appears earlier in its clause |
| F-EXPLANATION-NUMBER-FORMS | P2 | 3 | fixed_pending_retest | Invented numbers written as '7hrs', '9mg', '0.05-0.09', words or unicode fractions escape exact grounding |
| F-EXPLANATION-PARAPHRASE | P2 | 3 | fixed_pending_retest | Paraphrased overclaims in all four forbidden categories pass the phrase-list guard |
| F-RESTART-EPERM | P0 | 2 | retested | PR #14 (unmerged): on macOS the owned-session cleanup raises PermissionError, so every normally finishing scientific job fails and a cancelled job's lifeline guard can outlive it |
| H-FOLLOWUP-OPERATION | P2 | 5 | retested | Harness hardcoded the follow-up replay operation 'review'; v2 publishes 'recheck' |
| F-LEDGER-TOTALS | P2 | 2 | retested | Provider ledger ignores total_tokens larger than input+output+thought tokens, overstating remaining capacity |
| F-LEDGER-MALFORMED | P2 | 2 | retested | Provider ledger stores non-integer usage at reconciliation; every later reservation then fails with a TypeError |
| F-EXPLANATION-CHECKED-GATES | P2 | 3 | fixed_pending_retest | 'Checked design' narration is kept when its cited record lacks or contradicts the verification, replay, binding or tier gates |
| H-GATE-CONTROLS-DIRTY | P1 | 5 | retested | native_engine_controls gate admitted dirty (and otherwise unqualified) control records |

## F-ORPHAN-WORKER-KILL (P0, owner 2, retested)

- **Input:** hero-v2 baseline on main 9cc90e0; scientific child held inside the adapter by the harness barrier (after setsid and limits); SIGKILL the worker process group
- **Command:** `python3.11 evaluation/cli.py run --lane offline_real_science --subject http-launch --diagnostic science_barrier --results evaluation/results/previews/x --only RS-CANCEL-RESTART`
- **Expected:** no scientific computation outlives its job: the child detects parent death and ends its session, or recovery kills sessions recorded at dispatch
- **Observed:** child pid alive 1 s after the worker was killed and still alive after worker --recover marked the run interrupted; only the harness teardown removed it. API cancellation of a running job does kill the child (passes).
- **Evidence:** {"context": "packages/groundwork_adapter/docs/BRIDGE.md requires the launching parent to kill the session before its own exit; a SIGKILLed parent cannot", "results": "evaluation/results/previews/main-d6a71c2/science_barrier (RS-CANCEL-RESTART no_orphan_after_worker_kill)", "suggested_seam": "parent-death watchdog in science._child (poll os.getppid() or pipe EOF, then killpg own session), plus persisting the child pgid so worker --recover can kill leftovers"}
- **Retest at preview of backend/followup 8525cab (harness 1760df0; diagnostics relax_nproc + science_barrier):** Still reproduces: 1 live scientific child when the worker was SIGKILLed, still alive after `worker --recover` (the run itself is correctly marked interrupted and not redispatched). Running cancellation kills its child (passes). The harness released the barrier and reaped the orphan at teardown. (evidence: {"attempts": ["att_3cf444719093428e"], "results": "evaluation/results/previews/backend-followup-8525cab/relax_nproc+science_barrier"})
- **Retest at merged main 80f95a4 via harness b827c61 and f992b48 (diagnostics relax_nproc + science_barrier):** Still reproduces on main, twice: the scientific child survives the worker SIGKILL and `worker --recover` (the run is correctly marked interrupted and not redispatched). Running cancellation still kills its child. Since f992b48 the harness terminates the orphan before releasing the barrier (H-ORPHAN-TEARDOWN). (evidence: {"attempts": ["att_d0b306605a744db4", "att_593e67a5ca214685"], "results": "evaluation/results/previews/main-b827c61/relax_nproc+science_barrier"})
- **Retest at merged main 80f95a4, harness a1b28ae, tests/integration (science_barrier only; no product guard relaxed):** Reproduces without relax_nproc: the deterministic pytest test fails no_orphan_after_worker_kill (1 live scientific child after the worker SIGKILL). The barrier holds the child after setsid and the product's limits, so this is the product's own kill/recovery path. (evidence: {"pytest": "evaluation/results/integration/pytest-merged-main-a1b28ae.md"})
- **Retest at main 61edad7, Linux CI (ubuntu runner, no diagnostics except the harness barrier):** Reproduces on Linux too: no_orphan_after_worker_kill, 1 live scientific child after the worker SIGKILL. Not a Mac-only effect. (evidence: {"ci_run": "https://github.com/Arnav-M10/DrBean-hp26/actions/runs/43560507025", "commit": "main 61edad7 (PR #16)", "job": "provider-free actual-stack smoke / Owner 5 HTTP/invariant suite"})
- **Retest at preview of backend/restart-recovery c231be4 (PR #14; diagnostics relax_nproc + science_barrier):** Fixed by the PR's lifeline guard: the held child is stopped when the worker is SIGKILLed; nothing for the harness to terminate. Close after PR #14 merges with F-RESTART-EPERM resolved (otherwise normal completion fails on macOS). (evidence: {"attempts": ["att_2712c19d978049cb"], "results": "evaluation/results/previews/backend-restart-recovery-c231be4/relax_nproc+science_barrier"})
- **Retest at preview of PR #15 9a6db61 (science_barrier only, no relaxed guard):** Still reproduces on PR #15 (it does not include PR #14's lifeline guard). Merge order matters: PR #14 fixes it but needs F-RESTART-EPERM fixed first, or PR #14 would break the science PR #15 just enabled on macOS. (evidence: {"attempts": ["att_5946ffbc58194fcd"], "results": "evaluation/results/previews/science-integration-fixes-9a6db61/science_barrier"})
- **Retest at d821202b339ed60720e3c919d6be47e450e3b894 (ordinary HTTP launch; macOS arm64; Counterdex 0.3.0):** Resolved on this supported Mac/runtime in the ordinary lane: one sustained live scientific child was observed before the worker SIGKILL and none remained afterwards; worker --recover marked the run interrupted with worker_restart and it stayed interrupted without redispatch. Running cancellation likewise observed one live child and none surviving. The separately declared cancellation workload contained 128 exact replicates of the synthetic input; no diagnostic barrier or relaxed guard was used. All seven required lifecycle checks passed. Earlier diagnostic failures remain historical; this is not a claim about every OS or every possible termination timing. (evidence: {"attempts": ["att_d77e70889700444b"], "interruption_workload": {"deterministic_barrier": false, "origin": "synthetic", "rows": 128}, "lane_run_id": "lane_872f1c39287144d1", "results": "evaluation/results (executed_acceptance; clean at execution; diagnostic_overrides=[])", "trace": "evaluation/results/traces/att_d77e70889700444b.json"})
- **Retest at combined candidate 30ab5f8 = main 37d8f6f (PR #19) + this branch; macOS 26.7 arm64, iCloud-synced checkout, no diagnostics unless named:** Independently confirmed: with the 128-row real workload (no diagnostic) 1 live scientific child at cancel and 1 at worker SIGKILL, none alive afterwards; recovery marks the run interrupted without redispatch. Same with the barrier diagnostic, where the harness had nothing to terminate. (evidence: {"attempts": ["att_a114e020f44547b2", "att_ee0e6b5f53c346ec"]})
- **Retest at final candidate c8d39b5 = main 4b5f1f5 (PR #19 + PR #12) + this branch; macOS 26.7 arm64, no diagnostics:** Still holds after PR #12 merged: harness path 7/7, Owner 4's unmodified launcher 6/7 (cancel/restart is harness-path only), 22/22 engine controls, integration 66 passed + 19 strict xfail, web 30/30; no backend or engine code changed since 30ab5f8. (evidence: {"attempts": ["att_2b31cc969d37437d", "att_913292d16ae64365", "att_906bef01ac57453d"]})

## F-AI-INTEGRATION-SEAM (P1, owner 2 and 3, retested)

- **Input:** origin/main 9cc90e0 merged locally with codex/gemini-offline-integration c95ab28 (clean merge)
- **Command:** `in that worktree: BEAN_COUNTERDEX_PYTHON=<python3.11> .venv/bin/python -m pytest -q tests --ignore=tests/integration; .venv/bin/python -m pytest -q tests/integration/test_ai_boundaries.py`
- **Expected:** one agreed controlled-lane selection: Worker._agent uses ProviderConfig(mode='controlled') with an OfflineChatModel for the disclosed offline AI lane; Owner 2's worker/offline tests updated together (Owner 3's scripts/ai/HANDOFF.md asks for this)
- **Observed:** provider_placeholder_disabled from main's Worker._agent (it calls check_ready() on a placeholder config); failing: tests/test_worker.py::test_worker_actual_framework_uses_durable_attempts_and_frozen_evidence, tests/test_backend_offline.py::test_ordinary_provider_configuration_never_reads_provider_environment, ::test_http_intake_and_conversation_keep_provider_attempts_zero, and Workstream 5's three worker-boundary tests. Owner 3's own 74 tests and all zero-dispatch tests pass on the combination.
- **Evidence:** {"results": "evaluation/results/previews/ai-main-9cc90e0-plus-gemini-offline-c95ab28"}
- **Retest at codex/ai-offline-milestones c6f04c2 (preview):** Resolved on that branch: the worker-boundary controlled-lane tests pass; zero-dispatch passes. (evidence: {"results": "evaluation/results/previews/ai-offline-milestones-c6f04c2"})
- **Retest at merged main 55403ab (PR #10, Owner 3) via harness merge 98cef50:** Closed by retest on main: the worker-boundary controlled lane and real deepagents graph tests pass alongside the zero-dispatch suite (38 passed). (evidence: {"pytest": ".venv/bin/python -m pytest -q tests/integration/test_ai_boundaries.py tests/integration/test_zero_dispatch.py -> 38 passed"})

## F-PLATFORM-RLIMIT (P0, owner 2, retested)

- **Input:** fixtures/intake/clean.png (sha256 6363da39...0b06); any approved manual plan
- **Command:** `python3.11 evaluation/cli.py run --lane offline_real_science --subject http-launch --only RS-HERO-FULL`
- **Expected:** POST source-assets -> 201 (1200x1550 PNG); baseline run completes with evidence
- **Observed:** 422 malformed_image; run state failed, error scientific_worker_failed, scenario scientific_attempt_failed. setrlimit(RLIMIT_AS) raises ValueError 'current limit exceeds maximum limit' (soft/hard already RLIM_INFINITY) in _image_decode.py and science.py _child
- **Evidence:** {"attempts": ["att_95b6fad90f3740e4", "att_e74991a9307e41d4"], "baseline_suite": "136 passed, 17 failed, 11 errors at 586fb9b (identical to the audit)", "tests": ["tests/test_evaluation.py::test_synthetic_corpus_passes_real_media_admission", "tests/integration/test_http_lifecycle_and_science.py::test_hero_full_loop_real_science_design_download_and_native_replay"]}
- **Retest at adac945 via merge 1862ebf (harness d2d3c53):** Image decoder fixed on this Mac: valid clean.png admitted 1200x1550 through the real API (resource policy now reports RLIMIT_AS unavailable on Darwin). Scientific-worker failures on the Mac now have a different cause, tracked as F-MAC-NPROC. (evidence: {"attempts": ["att_87537746fa40470d (source_image_admitted passed)"], "backend_suite": "265 passed, 4 failed (was 136/17/11); the RLIMIT_AS image tests pass"})
- **Retest at d821202b339ed60720e3c919d6be47e450e3b894 (ordinary HTTP launch; macOS arm64; Counterdex 0.3.0):** Ordinary HTTP retest admits the valid PNG as 1200x1550 image/png and completes baseline and design. Darwin readiness still reports address-space enforcement unavailable with platform_guard_not_supported; the policy does not claim RLIMIT_AS support on this platform. (evidence: {"attempts": ["att_ec9cf987565e48ec"], "lane_run_id": "lane_872f1c39287144d1", "results": "evaluation/results (executed_acceptance; clean at execution; diagnostic_overrides=[])"})

## F-ADAPTER-SELECTION (P0, owner 2 (with 1 for the runtime bridge), retested)

- **Input:** default launch (python -m uvicorn bean_api.main:create_app --factory; python -m bean_api.worker)
- **Command:** `python3.11 evaluation/cli.py run --lane offline_real_science --subject http-launch`
- **Expected:** readiness.science.ready true (implemented, configured, verified_in_environment) and real discovery/checking on supplied input
- **Observed:** capabilities.science {implemented:false, configured:false, verified_in_environment:false, reason:groundwork_adapter_not_installed} (lane-runs.jsonl subject_start.readiness)
- **Evidence:** {"attempts": ["att_95b6fad90f3740e4"], "lane_run": "last entry of evaluation/results/lane-runs.jsonl"}
- **Retest at adac945 via merge 1862ebf (harness d2d3c53):** Ordinary API startup selects Counterdex (capabilities.science: implemented, configured, available via the 3.11 probe); the worker uses the same factory. (evidence: {"lane_run": "lane-runs.jsonl readiness at d2d3c53: science.runtime_available true, baseline_discovery false"})
- **Retest at d821202b339ed60720e3c919d6be47e450e3b894 (ordinary HTTP launch; macOS arm64; Counterdex 0.3.0):** Ordinary startup selects configured and available Counterdex 0.3.0 with baseline discovery, native design and native recheck. Real HTTP baseline, design and follow-up complete and replay fresh. Capability verified_in_environment remains false as the probe-level disclosure; these attempts supply the separate execution evidence. (evidence: {"attempts": ["att_ec9cf987565e48ec", "att_fd97aeac25fa4cae"], "lane_run_id": "lane_872f1c39287144d1", "results": "evaluation/results (executed_acceptance; clean at execution; diagnostic_overrides=[])"})

## F-BASELINE-DISCOVERY (P0, owner 1 (producer) and 2 (adapter wiring), retested)

- **Input:** evaluation/cases/science/hero-v1.json
- **Command:** `PYTHONPATH=packages/groundwork_adapter python3.11 -c 'import counterdex; print(counterdex.__all__)'`
- **Expected:** an operation that searches the supplied reviewed input, freezes exact vectors and freshly checks them
- **Observed:** public API exposes normalize/create_suggestion/replay_bundle for a supplied fixed pair only
- **Evidence:** {"note": "engine-level fixed-pair controls pass (controls.jsonl); discovery is the missing join, not the checker"}
- **Retest at adac945 via merge 1862ebf (harness d2d3c53):** Still open on main: CounterdexAdapter.investigate returns unsupported/baseline_producer_unavailable by design (Owner 2 BACKEND_INTEGRATION.md). Counterdex baseline.py/search.py are merged but not wired; the unmerged branch backend/browser-baseline (cc779bf) appears to wire computed baseline evidence and is next to preview. (evidence: {"backend_test": "tests/test_scientific_http.py::test_ordinary_http_baseline_is_honestly_blocked_without_a_producer"})
- **Retest at preview of backend/browser-baseline cc779bf (harness de1aca5; diagnostic relax_nproc; evidence class diagnostic, never acceptance):** Fixed on that branch: ordinary HTTP baseline returns certified_counterexample with two exact candidates in the admitted domain, the outside one freshly valid (ke = 101/1016, strictly below 0.10), both compatible per the independent 80-digit oracle; the counterdex.application-bundle.v1 baseline packet downloads and passes fresh replay-native with the authenticated anchor. Close after it merges to main and passes on the Mac without diagnostics. (evidence: {"results": "evaluation/results/previews/backend-browser-baseline-cc779bf/relax_nproc"})
- **Retest at main 9cc90e0 (merged as 7be805a, harness 8bb1fbe) with diagnostic relax_nproc:** Integrated on main via PR #6; the diagnostic run of main reproduces the preview: certified counterexample, exact in-domain candidates, baseline replay-native passes. Close after a non-diagnostic Mac run (blocked only by F-MAC-NPROC) or a CI Linux run of this lane. (evidence: {"results": "evaluation/results/previews/main-8bb1fbe/relax_nproc"})
- **Retest at merged main 80f95a4 (PR #9 + PR #11) via harness b827c61; diagnostic relax_nproc only (F-MAC-NPROC blocks every non-diagnostic run on this Mac):** Closed by retest: real bounded discovery on main returns a certified counterexample with an individually compatible strict outside candidate and a designable pair. neighbouring entries in the same run: RS-HERO-FULL, RS-CHANGED-INPUT, RS-RETRY-CONCURRENT, RS-DESIGN-AUTHORITY, RS-FOLLOWUP, RS-ZERO-DISPATCH all pass. (evidence: {"attempts": ["att_1ace0e6c87124367"], "results": "evaluation/results/previews/main-b827c61/relax_nproc"})
- **Retest at d821202b339ed60720e3c919d6be47e450e3b894 (ordinary HTTP launch; macOS arm64; Counterdex 0.3.0):** The ordinary HTTP baseline completes with two distinct exact in-domain candidates, both independently compatible with the historical observations, including a freshly valid strict outside witness; scientific_outcome is certified_counterexample. Its authenticated native packet passes fresh replay. The changed-input case also passes without any diagnostic override. (evidence: {"attempts": ["att_ec9cf987565e48ec", "att_1f692eebc2c34baa"], "lane_run_id": "lane_872f1c39287144d1", "results": "evaluation/results (executed_acceptance; clean at execution; diagnostic_overrides=[])"})

## F-NATIVE-BYTES (P0, owner 2 (bytes, anchor record) and 1 (complete packet), retested)

- **Input:** any completed run with ArtifactReference entries
- **Command:** `RS-HERO-FULL checks baseline_native_bytes_downloadable and *_anchor_from_authenticated_record`
- **Expected:** GET returns exact referenced bytes (sha/length/media type match reference and X-Artifact-SHA256); replay anchors come from the expected-run record
- **Observed:** not yet reachable through HTTP at this commit because F-PLATFORM-RLIMIT/F-ADAPTER-SELECTION stop the run first; code inspection: main.py artifact() returns canonical_bytes(record) for evidence/suggestion/report kinds only
- **Evidence:** {"anchor_field_names_accepted": "evaluation/drbean_eval/native.py ANCHOR_KEYS (agree final names with Owner 2)", "harness": "evaluation/drbean_eval/science_flow.py Flow.download tries /artifacts/{id} and /artifacts/{id}/content and classifies envelopes"}
- **Retest at adac945 via merge 1862ebf (harness d2d3c53):** Implemented on main: GET /artifacts/{id} returns native bytes with X-Artifact-SHA256 and GET /artifacts/{id}/anchor returns scientific_problem_digest / native_suggestion_digest. Not yet exercised through HTTP here: no run produces artifacts (discovery unavailable; F-MAC-NPROC on this Mac). Harness updated to use the anchor route. (evidence: {"code": "apps/api/bean_api/main.py artifact(), artifact_anchor()"})
- **Retest at preview of backend/browser-baseline cc779bf (harness de1aca5; diagnostic relax_nproc; evidence class diagnostic, never acceptance):** Native bytes, X-Artifact-SHA256, length, media type and the separate anchor route all verified over HTTP for baseline and design packets; altered bytes and wrong anchors rejected. Pending a non-diagnostic run on main. (evidence: {"results": "evaluation/results/previews/backend-browser-baseline-cc779bf/relax_nproc"})
- **Retest at main 9cc90e0 (merged as 7be805a, harness 8bb1fbe) with diagnostic relax_nproc:** Integrated on main; diagnostic run verifies bytes, header, length, anchors, tamper and wrong-anchor rejection for baseline and design packets. (evidence: {"results": "evaluation/results/previews/main-8bb1fbe/relax_nproc"})
- **Retest at merged main 80f95a4 (PR #9 + PR #11) via harness b827c61; diagnostic relax_nproc only (F-MAC-NPROC blocks every non-diagnostic run on this Mac):** Closed by retest: baseline and design native packets download byte-exact with their reference digests, carry complete application anchors from GET /artifacts/{id}/anchor and replay fresh; altered-byte and wrong-anchor controls are rejected. neighbouring entries in the same run: RS-HERO-FULL, RS-CHANGED-INPUT, RS-RETRY-CONCURRENT, RS-DESIGN-AUTHORITY, RS-FOLLOWUP, RS-ZERO-DISPATCH all pass. (evidence: {"attempts": ["att_1ace0e6c87124367"], "results": "evaluation/results/previews/main-b827c61/relax_nproc"})
- **Retest at d821202b339ed60720e3c919d6be47e450e3b894 (ordinary HTTP launch; macOS arm64; Counterdex 0.3.0):** Ordinary HTTP retest verifies exact recorded bytes, digest response header, length and media type for baseline, design and all four follow-up packets. Complete replay anchors come from authenticated application records; fresh replay passes with matching binding, and altered-byte and wrong-problem-anchor controls are rejected. The 22 separate engine controls also pass; their deliberately changed test anchors only isolate checker/format behavior and authenticate no altered packet. (evidence: {"attempts": ["att_ec9cf987565e48ec", "att_fd97aeac25fa4cae"], "lane_run_id": "lane_872f1c39287144d1", "native_controls": {"at": "2026-11-14T05:24:07+00:00", "expected": 22, "file": "evaluation/results/controls.jsonl", "interpreter": "CPython 3.11.17 Darwin arm64", "passed": 22, "scope": "engine public operations, not HTTP; fresh replay re-runs the project checker"}, "results": "evaluation/results (executed_acceptance; clean at execution; diagnostic_overrides=[])"})

## F-FOLLOWUP-FEEDBACK (P0, owner 2 (design-bound follow-up, PR #11) and 1 (wider native admission), retested)

- **Input:** hero design pair + hypothetical 3.4 / 4.57 / 4.0 mg/L at the selected time, allowance 0.2
- **Command:** `python3.11 evaluation/cli.py run --lane offline_real_science --subject http-launch --only RS-HERO-FULL RS-FOLLOWUP`
- **Expected:** new hypothetical lineage + new approval, then per-candidate compatible/excluded for the prior pair that agrees with the independent decimal oracle; aggregate exclusion reported as scientific feedback, not corruption
- **Observed:** lineage, origin labelling and new-approval requirement work over HTTP; per-candidate feedback has no route (harness accepts prior_candidate_results / candidate_results); blocked behind the hero run
- **Evidence:** {"attempts": ["att_003a52ad356c4088"], "engine_controls": "followup:3.4/4.57/4.0 pass at engine level"}
- **Retest at adac945 via merge 1862ebf (harness d2d3c53):** ScientificResult now carries candidate_results; Owner 1's unmerged codex/science-next adds original-candidate observation rechecks. No integrated HTTP route yet exercised here (blocked behind the hero run). (evidence: {"attempts": ["att_86aae8c45eb24619"]})
- **Retest at preview of backend/browser-baseline cc779bf (harness de1aca5; diagnostic relax_nproc; evidence class diagnostic, never acceptance):** Lineage now verified for all three what-if branches (new hypothetical dataset, parent link, old approval refused, new approval required); candidate-specific outcomes for the prior pair still have no route. Independent oracle expectations are recorded per branch for the eventual route. (evidence: {"results": "evaluation/results/previews/backend-browser-baseline-cc779bf/relax_nproc (RS-FOLLOWUP)"})
- **Retest at backend/browser-design 8451c1f (preview):** Still no candidate-specific result for the prior pair after a hypothetical reading (lineage passes). (evidence: {"results": "evaluation/results/previews/backend-browser-design-8451c1f/relax_nproc"})
- **Retest at preview of backend/followup 8525cab (PR #11, stacked on PR #9; harness 1760df0; diagnostic relax_nproc; evidence class diagnostic, never acceptance):** Design-bound follow-up (PlanBody.followup) passes all three branches, 73/73 required checks and 125/125 qualifier re-checks. Application, fresh native replay and the independent decimal oracle agree per candidate: 3.4 keeps the inside candidate only (inconclusive), 4.57 excludes both (inconclusive, no counterexample flag), 4.0 keeps the outside candidate (certified_counterexample). Tampered design digest -> 422 binding_mismatch, baseline artifact substituted -> 422 artifact_binding_mismatch, another workspace's design -> 404; baseline and design approvals -> 403; retried start returns the same run; exactly the original vectors are re-checked with no new discovery; exclusions name the new reading; design bytes and record unchanged; report keeps lineage without storage locators. Scope stays narrow by design: one hypothetical row at the checked selected time and reviewed allowance (actual or off-design readings are refused before approval; Owner 1 extends native admission). Close on main by a non-diagnostic run after PR #9/#11 merge. (evidence: {"attempts": ["att_158c6358ca2b4d49", "att_9a4ac710315648c6"], "results": "evaluation/results/previews/backend-followup-8525cab/relax_nproc"})
- **Retest at merged main 80f95a4 (PR #9 + PR #11) via harness b827c61; diagnostic relax_nproc only (F-MAC-NPROC blocks every non-diagnostic run on this Mac):** Closed by retest of the original repro: the design-bound follow-up on main re-checks the original pair on all three readings; application, fresh native replay and the independent oracle agree per candidate; tampered, substituted and foreign scopes are refused. neighbouring entries in the same run: RS-HERO-FULL, RS-CHANGED-INPUT, RS-RETRY-CONCURRENT, RS-DESIGN-AUTHORITY, RS-FOLLOWUP, RS-ZERO-DISPATCH all pass. Release acceptance on this Mac still waits on F-MAC-NPROC, tracked there. (evidence: {"attempts": ["att_3adc20dee66049ee"], "results": "evaluation/results/previews/main-b827c61/relax_nproc"})
- **Retest at d821202b339ed60720e3c919d6be47e450e3b894 (ordinary HTTP launch; macOS arm64; Counterdex 0.3.0):** Ordinary HTTP qualification now exercises proposal-bound operation recheck on four separately reviewed and approved single-append branches, with full proposal body/id/digest and parent/design binding independently checked. All 130 required checks pass: original vectors are retained without discovery; complete historical rows and byte-identical design evidence remain; fresh native replay, public candidate outcomes and the independent decimal oracle agree. For the actually discovered pairs, hypothetical 3.4 retains only the inside candidate (inconclusive), 4.57 excludes both (inconclusive), and 4.0 retains a compatible outside candidate (certified_counterexample). A separately labelled actual-origin declaration at 79/10 h with allowance 7/20 excludes both (inconclusive); its ancestry and resulting dataset remain synthetic, so it is not a real experimental measurement. Tampered design digest, baseline substitution and foreign scope are rejected, and old approvals do not authorize the new work. Earlier narrow legacy-review observations remain historical rather than being relabelled recheck evidence. (evidence: {"attempts": ["att_fd97aeac25fa4cae"], "lane_run_id": "lane_872f1c39287144d1", "results": "evaluation/results (executed_acceptance; clean at execution; diagnostic_overrides=[])", "scope": "fresh checked design parent; one appended observation; no repeated-follow-up or live-experiment qualification", "trace": "evaluation/results/traces/att_fd97aeac25fa4cae.json"})

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

## F-RESTART-UNOBSERVABLE (P1, owner 2 (after F-PLATFORM-RLIMIT), retested)

- **Input:** RS-CANCEL-RESTART
- **Command:** `python3.11 evaluation/cli.py run --lane offline_real_science --subject http-launch --only RS-CANCEL-RESTART`
- **Expected:** a live scientific child at cancel / worker kill, gone afterwards; interrupted run not redispatched
- **Observed:** queued cancellation and recovery semantics pass; running-child checks not_observed (child dies at setup)
- **Evidence:** {"attempts": ["att_ea42f9e1c5bf4b23"]}
- **Retest at adac945 via merge 1862ebf (harness d2d3c53):** Still unobservable on this Mac: no scientific child survives setup (F-MAC-NPROC). Queued cancellation passes. (evidence: {"attempts": ["att_e1326b12871140f2"]})
- **Retest at main 9cc90e0 with diagnostic science_barrier (harness d6a71c2):** Made observable with a deterministic diagnostic barrier inside the scientific child. Queued and running cancellation pass (held child killed, run cancelled); recovery marks the killed worker's run interrupted and never redispatches it. The worker-kill orphan this exposed is tracked as F-ORPHAN-WORKER-KILL. (evidence: {"results": "evaluation/results/previews/main-d6a71c2/science_barrier"})
- **Retest at d821202b339ed60720e3c919d6be47e450e3b894 (ordinary HTTP launch; macOS arm64; Counterdex 0.3.0):** The ordinary, non-barrier lane now observes sustained real scientific work for both cancellation and worker loss using a separately declared 128-row exact-replicate synthetic workload. One live child exists at each intervention, none survives, the cancelled run is terminal and the recovered worker-loss run stays interrupted without redispatch. This removes the earlier vacuity on this supported host; it does not weaken the sustained-observation criterion or promote earlier diagnostic evidence. (evidence: {"attempts": ["att_d77e70889700444b"], "lane_run_id": "lane_872f1c39287144d1", "results": "evaluation/results (executed_acceptance; clean at execution; diagnostic_overrides=[])"})

## F-LINT-CHECKLIST (P2, owner 4, retested)

- **Input:** repository at 586fb9b
- **Command:** `.venv/bin/ruff check apps tests scripts`
- **Expected:** All checks passed
- **Observed:** F401 scripts/release/checklist.py:25 drbean_eval.contract imported but unused
- **Evidence:** {}
- **Retest at adac945 via merge 1862ebf (harness d2d3c53):** Still failing on main: ruff check apps tests scripts reports 1 error. (evidence: {"command": ".venv/bin/ruff check apps tests scripts"})
- **Retest at combined candidate 30ab5f8 = main 37d8f6f (PR #19) + this branch; macOS 26.7 arm64, iCloud-synced checkout, no diagnostics unless named:** Closed by retest: `ruff check scripts/release/checklist.py` passes. (evidence: {})

## F-MAC-NPROC (P0, owner 2, retested)

- **Input:** macOS 26.7 arm64 user with 649 processes; resource policy process cap 32 (process_count: rlimit_nproc_per_user)
- **Command:** `.venv/bin/python -c "import os,resource,subprocess; pid=os.fork()\nif pid==0:\n resource.setrlimit(resource.RLIMIT_NPROC,(32,32)); subprocess.run(['/usr/bin/true'])"  -> BlockingIOError Errno 35; also BEAN_COUNTERDEX_PYTHON=/opt/homebrew/bin/python3.11 .venv/bin/python -m pytest tests/test_science_boundary.py tests/test_scientific_http.py`
- **Expected:** the supervised child launches the prepared CPython 3.11 runtime on the team's Mac; process-tree containment comes from the owned session/process group
- **Observed:** spawn fails with EAGAIN at caps 32 and 64 (passes at 4000); runs end failed with scientific_runtime_unavailable / scientific_worker_failed; 4 backend tests fail on the Mac only (Linux run passed)
- **Evidence:** {"attempts": ["att_87537746fa40470d", "att_adf816f75f9b4d1a"], "backend_tests": ["test_science_boundary.py::test_cancellation_terminates_descendants", "test_science_boundary.py::test_descendant_cannot_escape_by_outliving_adapter", "test_scientific_http.py::test_ordinary_http_baseline_is_honestly_blocked_without_a_producer", "test_scientific_http.py::test_explicit_seed_pair_real_design_download_and_independent_replay"], "suggested_seam": "treat RLIMIT_NPROC on Darwin like RLIMIT_AS (report unavailable) or set it to current user process count + a small margin; keep the owned-session kill and wall clock"}
- **Retest at backend/browser-baseline cc779bf (preview, no diagnostic):** Also present on Owner 2's newer branch: the plain preview's hero baseline fails the same way. (evidence: {"results": "evaluation/results/previews/backend-browser-baseline-cc779bf/plain"})
- **Retest at main 9cc90e0 (merged as 7be805a, harness 8bb1fbe):** Still present on the merged main (browser-baseline integrated): RS-HERO-FULL and RS-CHANGED-INPUT fail with scientific_runtime_unavailable on this Mac without diagnostics. Owner 1 recorded an isolated reproduction on codex/science-next (bad5e9f); Owner 4's CI adds scripts/release/user_conditions_check.py for it. (evidence: {"attempts": "evaluation/results/attempts.jsonl at 8bb1fbe"})
- **Retest at main 9cc90e0 (science.py now passes processes=256):** Insufficient on the team's Mac: this user owns 649 processes, above 256, so spawning the engine still fails with EAGAIN (measured: caps 32 and 64 fail, 4000 succeeds). A per-user count cannot be a per-job cap. (evidence: {"code": "apps/api/bean_api/science.py _child apply_limits(..., processes=256)", "user_processes": 649})
- **Retest at backend/browser-design 8451c1f and codex/ai-offline-milestones c6f04c2 (previews):** Present on both newer branches: plain hero baseline fails on the Mac; Owner 3's new real-Counterdex coordinator test fails with scientific_runtime_unavailable. This is now the single blocker between the Mac and a passing acceptance hero run. (evidence: {"ai": "evaluation/results/previews/ai-offline-milestones-c6f04c2", "results": "evaluation/results/previews/backend-browser-design-8451c1f/relax_nproc"})
- **Retest at 3b55843 (app code = main 9cc90e0; engine runtime now Owner 4's .venv-engine, CPython 3.11.17):** Still fails on both launch paths: harness path and Owner 4's launcher both report scientific_runtime_unavailable for the hero and changed-input baselines. With only the process-limit guard relaxed (diagnostic), the same launcher runs discovery, changed input, design authority and zero dispatch to a pass. (evidence: {"attempts": ["att_92546adc9fac471e", "att_fe675c60b66a4801", "att_8e959bd4324c48f8"], "results": "evaluation/results, evaluation/results/owner4-launcher, evaluation/results/owner4-launcher/relax_nproc"})
- **Retest at merged main 80f95a4 via harness b827c61:** Unchanged on both launch paths (harness and Owner 4's launcher): hero and changed-input baselines fail with scientific_runtime_unavailable. It is now the only blocker between this Mac and release acceptance of the hero, design and follow-up path, which pass in full when only this guard is relaxed. (evidence: {"attempts": ["att_568062c9c3434610", "att_98ac5a9ee88048d1", "att_1ace0e6c87124367"]})
- **Retest at main 61edad7, Linux CI:** Contrast: the same real-science HTTP tests (hero with checked design and fresh replay, changed input, design authority, design-bound follow-up) pass on the Linux runner, which owns about 64 processes. The failure on this Mac is the per-user process cap alone. (evidence: {"ci_run": "https://github.com/Arnav-M10/DrBean-hp26/actions/runs/43560507025", "commit": "main 61edad7 (PR #16)", "job": "provider-free actual-stack smoke / Owner 5 HTTP/invariant suite"})
- **Retest at preview of codex/science-integration-fixes 9a6db61 (PR #15, stacked on PR #5; harness 2600456; NO diagnostics):** Fixed in PR #15: the process policy keeps the inherited per-user ceiling. On this Mac, with no diagnostic, 6/7 lane entries pass: hero (real discovery, checked design at 8 h, both packets replay fresh), changed input, retry/concurrency, design authority (v2 reuse probe included), design-bound follow-up (recheck; application, fresh replay and decimal oracle agree), zero dispatch. Close on main after PR #5/#15 merge. (evidence: {"attempts": ["att_c74f45e13b1c4522", "att_d6ae837f8bcc4541"], "results": "evaluation/results/previews/science-integration-fixes-9a6db61/plain"})
- **Retest at d821202b339ed60720e3c919d6be47e450e3b894 (ordinary HTTP launch; macOS arm64; Counterdex 0.3.0):** Resolved by an ordinary run on this Mac: all seven scheduled HTTP entries pass, including real baseline discovery, changed input, separate design, proposal-bound follow-up and sustained cancellation/restart. The prepared CPython 3.11 runtime launches under the product process-guards-v3 policy with inherited account-wide RLIMIT_NPROC; readiness explicitly reports that a per-job process-count quota is unavailable because the platform limit is account-wide. Owned POSIX sessions, wall-clock supervision and the other reported guards remain enabled. No relax_nproc or other diagnostic override was used. This verifies the reported Mac launch failure on this host, not a newly available per-job process quota or a cross-platform proof. (evidence: {"attempts": ["att_ec9cf987565e48ec", "att_1f692eebc2c34baa", "att_371f1d8c816441b4", "att_955cd7b2cbe240ed", "att_fd97aeac25fa4cae", "att_d77e70889700444b", "att_1a506101c468467d"], "lane_run_id": "lane_872f1c39287144d1", "native_controls": {"at": "2026-11-14T05:24:07+00:00", "expected": 22, "file": "evaluation/results/controls.jsonl", "passed": 22, "scope": "engine public operations, not HTTP; fresh replay re-runs the project checker"}, "resource_policy": {"policy_version": "process-guards-v3", "process_count": "inherited_rlimit_nproc_per_user", "process_count_job_quota": "unavailable", "process_count_reason": "account_wide_limit_not_job_quota", "process_tree": "owned_posix_session"}, "results": "evaluation/results (executed_acceptance; clean at execution; diagnostic_overrides=[])"})
- **Retest at combined candidate 30ab5f8 = main 37d8f6f (PR #19) + this branch; macOS 26.7 arm64, iCloud-synced checkout, no diagnostics unless named:** Independently confirmed on this Mac: the plain lane passes 7/7 through the harness launch path and 6/7 through Owner 4's launcher (cancel/restart is harness-path only), with real discovery, checked design, fresh replay and follow-up rechecks; no relaxed guard. (evidence: {"attempts": ["att_b9610a6030064d38", "att_a8d1f1b59cb845ef"]})
- **Retest at final candidate c8d39b5 = main 4b5f1f5 (PR #19 + PR #12) + this branch; macOS 26.7 arm64, no diagnostics:** Still holds after PR #12 merged: harness path 7/7, Owner 4's unmodified launcher 6/7 (cancel/restart is harness-path only), 22/22 engine controls, integration 66 passed + 19 strict xfail, web 30/30; no backend or engine code changed since 30ab5f8. (evidence: {"attempts": ["att_2b31cc969d37437d", "att_913292d16ae64365", "att_906bef01ac57453d"]})

## F-COORDINATOR-OPTIONAL-STATUS (P2, owner 3, retested)

- **Input:** scripted model: execute baseline, then return_grounded_explanation
- **Command:** `.venv/bin/python -m pytest tests/integration/test_ai_boundaries.py -k optional_scenario_cannot_silently_vanish`
- **Expected:** the coordinator itself reports an unresolved disposition
- **Observed:** status completed (strict xfail)
- **Evidence:** {}
- **Retest at preview: main 9cc90e0 + codex/gemini-offline-integration c95ab28 (local merge):** Fixed on Owner 3's branch: the strict-xfail test XPASSes (coordinator refuses completion with an unaccounted optional scenario / controlled turns write no bare gemini provider attempts). Remove the xfail marker when the branch merges; the strict marker will fail the suite until then. (evidence: {"results": "evaluation/results/previews/ai-main-9cc90e0-plus-gemini-offline-c95ab28"})
- **Retest at codex/ai-offline-milestones c6f04c2 (preview):** Strict-xfail test XPASSes on this branch too; remove the marker when it merges. (evidence: {"results": "evaluation/results/previews/ai-offline-milestones-c6f04c2"})
- **Retest at merged main 55403ab (PR #10, Owner 3) via harness merge 98cef50:** Closed by retest: the coordinator no longer reports completed while a reviewed optional scenario is neither executed nor skipped; the strict-xfail test XPASSed and is now an ordinary regression. (evidence: {"pytest": ".venv/bin/python -m pytest -q tests/integration/test_ai_boundaries.py tests/integration/test_zero_dispatch.py -> 38 passed"})

## F-COORDINATOR-PROVIDER-LABEL (P2, owner 3, retested)

- **Input:** run_coordinator with a controlled chat_model
- **Command:** `.venv/bin/python -m pytest tests/integration/test_ai_boundaries.py -k masquerade`
- **Expected:** controlled turns carry an explicit controlled/placeholder marker at the source
- **Observed:** metadata provider=gemini; the worker wraps it in controlled_attempt records, so no live-looking row reaches the provider ledger (strict xfail)
- **Evidence:** {}
- **Retest at preview: main 9cc90e0 + codex/gemini-offline-integration c95ab28 (local merge):** Fixed on Owner 3's branch: the strict-xfail test XPASSes (coordinator refuses completion with an unaccounted optional scenario / controlled turns write no bare gemini provider attempts). Remove the xfail marker when the branch merges; the strict marker will fail the suite until then. (evidence: {"results": "evaluation/results/previews/ai-main-9cc90e0-plus-gemini-offline-c95ab28"})
- **Retest at codex/ai-offline-milestones c6f04c2 (preview):** Strict-xfail test XPASSes on this branch too; remove the marker when it merges. (evidence: {"results": "evaluation/results/previews/ai-offline-milestones-c6f04c2"})
- **Retest at merged main 55403ab (PR #10, Owner 3) via harness merge 98cef50:** Closed by retest: controlled turns are no longer labelled as bare provider gemini attempts; the strict-xfail test XPASSed and is now an ordinary regression. (evidence: {"pytest": ".venv/bin/python -m pytest -q tests/integration/test_ai_boundaries.py tests/integration/test_zero_dispatch.py -> 38 passed"})

## F-TEST-VAR-LEAK (P2, owner 2, open)

- **Input:** tests/test_api.py client fixture (Settings(database_path=..., blob_dir=..., auth_tokens=...))
- **Command:** `.venv/bin/python -m pytest -q tests/test_api.py; ls var/artifacts`
- **Expected:** test runs write only to tmp_path
- **Observed:** an empty var/artifacts appeared in the working tree (removed)
- **Evidence:** {"note": "Workstream 5's own fixture had the same omission and now sets artifact_dir"}

## F-DESIGN-SOURCE-ARTIFACTS (P1, owner 2 (projection) and 1 (engine reuse format), retested)

- **Input:** hero-v2 on backend/browser-baseline cc779bf: discovered pair, grid [6,8] h, allowance 1/5, horizon 8, construction+continuation, source_artifact_ids=[baseline native artifact]
- **Command:** `python3.11 evaluation/cli.py run --lane offline_real_science --subject http-launch --app-repo <worktree of backend/browser-baseline> --diagnostic relax_nproc --results evaluation/results/previews/x --only RS-HERO-FULL`
- **Expected:** the walkthrough's documented design scope (with source artifact ids) yields checked_pair_separation for a checkable pair
- **Observed:** design_tier numerical_guidance, reason invalid_input; engine report.checked.error invalid_input at field ['pair']: 'Missing or unknown fields in this version' - candidates get source_artifact_digest = the baseline application packet, which the engine tries to reuse as a pair certificate. The same pair without source_artifact_ids, separately approved: checked_pair_separation, verification valid, fresh replay passed, selected 8 h with a positive exact margin
- **Evidence:** {"results": "evaluation/results/previews/backend-browser-baseline-cc779bf/relax_nproc (RS-HERO-FULL isolation checks)", "suggested_seam": "do not project the baseline application packet as a pair-reuse source_artifact_digest (pass it as historical context), or teach the engine to accept baseline certificates; and return a specific reason code instead of a silent numerical fallback"}
- **Retest at main 9cc90e0 (merged as 7be805a, harness 8bb1fbe) with diagnostic relax_nproc:** Reproduced on main: documented request with source_artifact_ids -> numerical_guidance/invalid_input; without them -> checked separation at 8 h with fresh replay. (evidence: {"results": "evaluation/results/previews/main-8bb1fbe/relax_nproc"})
- **Retest at backend/browser-design 8451c1f (preview, diagnostic relax_nproc):** Fixed on that branch: the documented design with source artifact ids reaches checked_pair_separation (selected 8 h, strictly positive exact margin) and both native packets pass fresh replay; RS-HERO-FULL passes with 33/33 qualifier re-checks. Close after merge and a non-diagnostic run. (evidence: {"results": "evaluation/results/previews/backend-browser-design-8451c1f/relax_nproc"})
- **Retest at merged main 80f95a4 (PR #9 + PR #11) via harness b827c61; diagnostic relax_nproc only (F-MAC-NPROC blocks every non-diagnostic run on this Mac):** Closed by retest: the documented design request WITH source_artifact_ids now returns checked_pair_separation at 8/1 with a strictly positive exact margin, valid verification and fresh replay of both packets; no isolation probe was needed. neighbouring entries in the same run: RS-HERO-FULL, RS-CHANGED-INPUT, RS-RETRY-CONCURRENT, RS-DESIGN-AUTHORITY, RS-FOLLOWUP, RS-ZERO-DISPATCH all pass. (evidence: {"attempts": ["att_1ace0e6c87124367"], "results": "evaluation/results/previews/main-b827c61/relax_nproc"})
- **Retest at d821202b339ed60720e3c919d6be47e450e3b894 (ordinary HTTP launch; macOS arm64; Counterdex 0.3.0):** Current Counterdex 0.3 qualification uses a newly reviewed design request with empty prospective source_artifact_ids, while the selected immutable baseline packet is supplied independently as mandatory history. This request completes at checked_pair_separation, selects 8/1 with a strictly positive exact margin, and freshly replays with valid matching evidence; there is no isolation probe or rewrite of an already approved request. The earlier successful nonempty-reuse observation describes the older consumer and is preserved above, not claimed as the current 0.3 reuse contract. (evidence: {"attempts": ["att_ec9cf987565e48ec"], "lane_run_id": "lane_872f1c39287144d1", "results": "evaluation/results (executed_acceptance; clean at execution; diagnostic_overrides=[])"})

## F-SIBLING-FORKS (P2, owner 2, open)

- **Input:** two hypothetical observation proposals against the same parent dataset in one workspace
- **Command:** `review the second proposal after accepting the first`
- **Expected:** comparing several hypothetical readings from the same history is a natural planning task; either allow sibling forks or document 'one fork per workspace'
- **Observed:** 409 stale_revision for the second fork (the first moved the current dataset); the harness now uses one workspace per branch
- **Evidence:** {"note": "correct immutability behaviour; product/UX gap, not a safety defect"}

## H-CI-ENGINE (P1, owner 5, retested)

- **Input:** CI stack job: `python3 scripts/dev/launcher.py setup` then `.venv/bin/python -m pytest -q tests/integration` with no DRBEAN_SCIENCE_PYTHON and no python3.11 on PATH
- **Command:** `.venv/bin/python -m pytest -q tests/integration`
- **Expected:** the launched stack receives BEAN_COUNTERDEX_PYTHON for the qualified CPython 3.11 engine that setup prepared
- **Observed:** Reported by Owner 1 from CI run 43556610563 (PR #5 merge 4fc3add): integration suite 36 passed, 7 failed, 2 xfailed; all seven failures were plan admission 503 scientific_runtime_missing. Harness 4ea7cb3 (the copy merged into main) resolves the engine only from DRBEAN_SCIENCE_PYTHON or python3.11 on PATH; the stack job prepares .venv-engine but exports neither, so LocalStack launched the API without BEAN_COUNTERDEX_PYTHON. A harness-environment defect, not a product one.
- **Evidence:** {"ci_run": "https://github.com/Arnav-M10/DrBean-hp26/actions/runs/43556610563", "reported_in": "origin/codex/science-next docs/workstreams/01-science.md (Post-push CI at 8af34e4)"}
- **Retest at main 61edad7 (PR #16 merged 8bb1fbe), Linux CI:** Closed by retest: CI's integration suite now finds .venv-engine and runs real science: 43 passed, 3 failed (two strict-xfail XPASSes fixed by 1ae19ff, not yet in main; F-ORPHAN-WORKER-KILL). Hero, changed input, design authority and follow-up pass on Linux without diagnostics. (evidence: {"ci_run": "https://github.com/Arnav-M10/DrBean-hp26/actions/runs/43560507025", "commit": "main 61edad7 (PR #16)", "job": "provider-free actual-stack smoke / Owner 5 HTTP/invariant suite"})

## F-LAUNCHER-HIDDEN-PTH (P1, owner 4, retested)

- **Input:** checkout under ~/Documents on a Mac with iCloud Drive Desktop & Documents sync (an iCloud Drive File Provider domain); .venv created by `uv sync --locked`
- **Command:** `DRBEAN_VAR_DIR=<isolated> python3 scripts/dev/launcher.py setup (then start); harness: python3.11 evaluation/cli.py run --lane offline_real_science --subject http-owner4-launcher --results evaluation/results/owner4-launcher`
- **Expected:** setup finishes (local auth created); start serves API, worker and web; the doctor's 'backend runtime ok' implies the service entry points can import bean_api
- **Observed:** setup stops at the auth step (`.venv/bin/python -m bean_api.bootstrap`: No module named 'bean_api'); start: the API and worker exit with ModuleNotFoundError, and the launcher correctly stops everything it started and frees both ports; doctor still reports the backend runtime ok because it checks package metadata, not importability. Cause verified on this host: within about 6 s of creation the iCloud Drive File Provider sets UF_HIDDEN recursively on dot-named directories under ~/Documents (the same probe in /private/tmp stays visible), and CPython 3.11.17 and 3.13.18 `site` skip hidden .pth files (probe: visible .pth importable, hidden .pth not), so `_editable_impl_dr_bean_backend.pth` is ignored. With apps/api added to PYTHONPATH (what Owner 2's documented commands do via --app-dir/PYTHONPATH and what the harness launch path does) the same unmodified launcher starts in under a second; readiness then distinguishes API, worker and science, and the product processes receive no provider credentials.
- **Evidence:** {"attempts": ["att_fe675c60b66a4801", "att_acd3a5749edf4d22"], "reproduction": "evaluation/results/owner4-launcher/HIDDEN-PTH-REPRO.md", "results": "evaluation/results/owner4-launcher (lane-runs.jsonl: startup_path.launcher_runs shows the unmodified start exit 1, then the labelled retry exit 0)"}
- **Retest at combined candidate 30ab5f8 = main 37d8f6f (PR #19) + this branch; macOS 26.7 arm64, iCloud-synced checkout, no diagnostics unless named:** Closed by retest: from the iCloud-synced checkout, `launcher.py setup` now completes (auth created) and the unmodified `launcher.py start` exits 0 with no workaround recorded; the launcher puts apps/api first on PYTHONPATH for every child. 6/7 entries pass through it, no orphans after `launcher.py stop`. (evidence: {"attempts": ["att_a8d1f1b59cb845ef", "att_b80e99662ebb4196"], "results": "evaluation/results/owner4-launcher"})
- **Retest at final candidate c8d39b5 = main 4b5f1f5 (PR #19 + PR #12) + this branch; macOS 26.7 arm64, no diagnostics:** Still holds after PR #12 merged: harness path 7/7, Owner 4's unmodified launcher 6/7 (cancel/restart is harness-path only), 22/22 engine controls, integration 66 passed + 19 strict xfail, web 30/30; no backend or engine code changed since 30ab5f8. (evidence: {"attempts": ["att_2b31cc969d37437d", "att_913292d16ae64365", "att_906bef01ac57453d"]})

## F-LAUNCHER-ENV-READ (P2, owner 4, retested)

- **Input:** dummy GEMINI_API_KEY / GOOGLE_API_KEY / LANGSMITH_API_KEY (DRBEAN-DUMMY-OWNER4-SCRUB) in the launcher's own environment, egress guard on PYTHONPATH
- **Command:** `python3.11 evaluation/cli.py run --lane offline_real_science --subject http-owner4-launcher --results evaluation/results/owner4-launcher`
- **Expected:** names-only filtering (iterate keys, read only the values that are kept) and a scrubbed environment for every child, including probes
- **Observed:** the guard records a credential_read of each dummy value in the launcher process during cmd_start -> child_env() (`os.environ.items()` reads every value; the code comment says values are never read), and the doctor's backend probe (`.venv/bin/python -c ...`, env=None) starts with all three names present. The API and worker receive none of them: the scrubbing that matters works.
- **Evidence:** {"attempts": ["att_acd3a5749edf4d22"], "results": "evaluation/results/owner4-launcher (lane-runs.jsonl subject_end.launcher_side_guard_events: credential_read in launcher.py, probe guard_installed with names present; product processes credential_names_present [])"}
- **Retest at combined candidate 30ab5f8 = main 37d8f6f (PR #19) + this branch; macOS 26.7 arm64, iCloud-synced checkout, no diagnostics unless named:** Closed by retest: with dummy GEMINI/GOOGLE/LANGSMITH keys in the launcher's environment the guard records no credential_read in the launcher, and every doctor/backend probe starts with no credential names (out() now defaults to the scrubbed child environment). API and worker receive none. (evidence: {"attempts": ["att_b80e99662ebb4196"], "results": "evaluation/results/owner4-launcher (lane-runs subject_end)"})

## H-ORPHAN-TEARDOWN (P1, owner 5, retested)

- **Input:** RS-CANCEL-RESTART with --diagnostic relax_nproc --diagnostic science_barrier on merged main b827c61
- **Command:** `python3.11 evaluation/cli.py run --lane offline_real_science --subject http-launch --diagnostic relax_nproc --diagnostic science_barrier --results <dir> --only RS-CANCEL-RESTART`
- **Expected:** an orphan the scenario already reported (F-ORPHAN-WORKER-KILL) is terminated by the harness before anything lets it continue; no process from the stack outlives the CLI
- **Observed:** the scenario released the barrier while the orphaned spawn child was alive; the child resumed and started its CPython 3.11 engine grandchild after the last descendant snapshot; teardown tracked only by parent pid, reported no orphans, and the grandchild ran past the CLI's exit before finishing on its own
- **Evidence:** {"results": "evaluation/results/previews/main-b827c61/relax_nproc+science_barrier (first attempt)"}
- **Retest at f992b48 on merged main 80f95a4:** the orphan (spawn child) was terminated before the barrier release; teardown found nothing left and no stack process outlived the CLI (evidence: {"attempts": ["att_593e67a5ca214685"], "results": "evaluation/results/previews/main-b827c61/relax_nproc+science_barrier"})

## F-EXPLANATION-QUALIFIER (P2, owner 3, fixed_pending_retest)

- **Input:** 'Without any doubt this proves the interval.' / 'It is not an exaggeration to say this proves the interval.'
- **Command:** `.venv/bin/python -m pytest -q tests/integration/test_explanation_guard.py -rxX`
- **Expected:** unsupported_claim: the exemption should apply only when the qualifier hedges or negates the claim itself ('does not prove', 'may prove')
- **Observed:** accepted (None); `_QUALIFIER` matches 'without'/'not'/'whether' anywhere in the clause prefix, so an intensifier exempts the claim
- **Evidence:** {"end_to_end": "explain route returns commentary_status 'unverified_model_commentary' with the text shown; coordinator keeps the final explanation and completes", "tests": "tests/integration/test_explanation_guard.py (strict xfail; 6 controls pass)"}
- **Retest at combined candidate 30ab5f8 = main 37d8f6f (PR #19) + this branch; macOS 26.7 arm64, iCloud-synced checkout, no diagnostics unless named:** Still reproduces on the combined candidate: its strict xfails hold (tests/integration/test_explanation_guard.py). (evidence: {"pytest": "66 passed, 19 xfailed"})
- **Retest at preview of codex/ai-grounded-explanations 623ae19 (PR #28) with tests/integration/test_explanation_guard.py copied unchanged:** fixed there: with --runxfail all 33 assertions pass (every attack and missing/negative checked-design gate refused; the fully supported checked-design statement kept). The gap markers apply only to guards that do not declare the evidence-bound statement policy, so they become ordinary passing assertions when PR #28 merges. (evidence: {"pytest": "33 passed (PR #28); 6 passed + 27 xfailed (main 2d2993d)"})

## F-EXPLANATION-NUMBER-FORMS (P2, owner 3, fixed_pending_retest)

- **Input:** 'Sample again at 7hrs to separate them.' (no 7 h in any cited fact)
- **Command:** `.venv/bin/python -m pytest -q tests/integration/test_explanation_guard.py -rxX`
- **Expected:** unsupported_numeric_claim, as for 'ke 0.05' and '15%'
- **Observed:** accepted (None): `_NUMBER`'s lookarounds skip digits glued to letters or hyphens, and words/unicode fractions are never parsed
- **Evidence:** {"end_to_end": "explain route returns commentary_status 'unverified_model_commentary' with the text shown; coordinator keeps the final explanation and completes", "tests": "tests/integration/test_explanation_guard.py (strict xfail; 6 controls pass)"}
- **Retest at combined candidate 30ab5f8 = main 37d8f6f (PR #19) + this branch; macOS 26.7 arm64, iCloud-synced checkout, no diagnostics unless named:** Still reproduces on the combined candidate: its strict xfails hold (tests/integration/test_explanation_guard.py). (evidence: {"pytest": "66 passed, 19 xfailed"})
- **Retest at preview of codex/ai-grounded-explanations 623ae19 (PR #28) with tests/integration/test_explanation_guard.py copied unchanged:** fixed there: with --runxfail all 33 assertions pass (every attack and missing/negative checked-design gate refused; the fully supported checked-design statement kept). The gap markers apply only to guards that do not declare the evidence-bound statement policy, so they become ordinary passing assertions when PR #28 merges. (evidence: {"pytest": "33 passed (PR #28); 6 passed + 27 xfailed (main 2d2993d)"})

## F-EXPLANATION-PARAPHRASE (P2, owner 3, fixed_pending_retest)

- **Input:** 'This establishes that the interval is correct.', 'Every other model is ruled out by these data.', 'We identified the actual parameter of the drug.', '8 h is the optimal sampling time for any experiment.'
- **Command:** `.venv/bin/python -m pytest -q tests/integration/test_explanation_guard.py -rxX`
- **Expected:** unsupported_claim (master brief 2.17: proof of the interval, elimination of outside models, physical truth, global optimality)
- **Observed:** accepted (None)
- **Evidence:** {"end_to_end": "explain route returns commentary_status 'unverified_model_commentary' with the text shown; coordinator keeps the final explanation and completes", "tests": "tests/integration/test_explanation_guard.py (strict xfail; 6 controls pass)"}
- **Retest at combined candidate 30ab5f8 = main 37d8f6f (PR #19) + this branch; macOS 26.7 arm64, iCloud-synced checkout, no diagnostics unless named:** Still reproduces on the combined candidate: its strict xfails hold (tests/integration/test_explanation_guard.py). (evidence: {"pytest": "66 passed, 19 xfailed"})
- **Retest at preview of codex/ai-grounded-explanations 623ae19 (PR #28) with tests/integration/test_explanation_guard.py copied unchanged:** fixed there: with --runxfail all 33 assertions pass (every attack and missing/negative checked-design gate refused; the fully supported checked-design statement kept). The gap markers apply only to guards that do not declare the evidence-bound statement policy, so they become ordinary passing assertions when PR #28 merges. (evidence: {"pytest": "33 passed (PR #28); 6 passed + 27 xfailed (main 2d2993d)"})

## F-RESTART-EPERM (P0, owner 2, retested)

- **Input:** any baseline on backend/restart-recovery c231be4 on Darwin 25.6.0; or killpg-eperm-repro.py (standard library)
- **Command:** `python3.11 evaluation/cli.py run --lane offline_real_science --subject http-launch --app-repo <PR #14 checkout> --diagnostic relax_nproc --results <dir>`
- **Expected:** baselines complete; cancellation leaves no live scientific or guard process
- **Observed:** hero and changed-input baselines fail with worker_failed / scientific_attempt_failed; run_bounded with a trivial adapter raises PermissionError at science.py:180 (`os.killpg(process.pid, SIGKILL)` in finally, which catches only ProcessLookupError); cancellation without the barrier leaves 1 live child. Darwin returns EPERM for killpg on a group whose only member is an exited, unreaped leader (standalone repro, CPython 3.11.17 and 3.13.18); Linux returns ESRCH, so Linux validation passed. The exception also skips the rest of the cleanup, including closing the parent lifeline, which is why the guard survives a cancellation. A one-line local diagnostic patch catching PermissionError makes the same lane pass 6/7 (as on main) and cancel/restart with the barrier pass.
- **Evidence:** {"readme": "evaluation/results/previews/backend-restart-recovery-c231be4/README.md", "repro": "evaluation/results/previews/backend-restart-recovery-c231be4/killpg-eperm-repro.py", "results": "evaluation/results/previews/backend-restart-recovery-c231be4"}
- **Retest at combined candidate 30ab5f8 = main 37d8f6f (PR #19) + this branch; macOS 26.7 arm64, iCloud-synced checkout, no diagnostics unless named:** Closed by independent retest. The original reproduction (trivial adapter through run_bounded) now returns its result instead of PermissionError; PR #19's _kill_owned_session reaps the leader and retries on Darwin EPERM. All 7 lane entries pass with real computation (10 follow-up jobs complete normally), cancellation and worker loss leave no live process with and without the barrier. integration 66 passed + 19 strict xfail (known P2 gaps only); backend 559 passed; engine 291 OK; harness 131 unit tests; 22/22 engine controls. (evidence: {"attempts": ["att_b9610a6030064d38", "att_33baea51713b4574", "att_a114e020f44547b2", "att_ee0e6b5f53c346ec"], "repro": "evaluation/results/previews/backend-restart-recovery-c231be4/README.md (probe rerun on 30ab5f8)"})
- **Retest at final candidate c8d39b5 = main 4b5f1f5 (PR #19 + PR #12) + this branch; macOS 26.7 arm64, no diagnostics:** Still holds after PR #12 merged: harness path 7/7, Owner 4's unmodified launcher 6/7 (cancel/restart is harness-path only), 22/22 engine controls, integration 66 passed + 19 strict xfail, web 30/30; no backend or engine code changed since 30ab5f8. (evidence: {"attempts": ["att_2b31cc969d37437d", "att_913292d16ae64365", "att_906bef01ac57453d"]})

## F-LEDGER-TOTALS (P2, owner 2, retested)

- **Input:** isolated store; reserve 100/20; reconcile usage {input 100, output 20, thought 0, total 5000} (the shape providers.sanitize_usage produces; Gemini totals include e.g. tool-use prompt tokens)
- **Command:** `.venv/bin/python -m pytest -q tests/integration/test_ledger_attacks.py -rxX --runxfail`
- **Expected:** at least the reported total is charged (conservative totals)
- **Observed:** main charges 120 tokens for a reported total of 5000
- **Evidence:** {"tests": "tests/integration/test_ledger_attacks.py (strict xfail on main)"}
- **Retest at preview of backend/controlled-acceptance 731afdc (PR #13) with this suite copied in:** fixed there: the strict xfail XPASSes (13 safety regressions also pass; PR #13 additionally refuses negative/boolean counts at reconciliation). Remove the marker when PR #13 merges. (evidence: {"command": ".venv/bin/python -m pytest -q tests/integration/test_ledger_attacks.py -rX (in the PR #13 checkout)"})
- **Retest at combined candidate 30ab5f8 = main 37d8f6f (PR #19) + this branch; macOS 26.7 arm64, iCloud-synced checkout, no diagnostics unless named:** Still present on main (PR #13 is not merged; ledger.py unchanged): strict xfail holds in tests/integration/test_ledger_attacks.py. (evidence: {"pytest": "66 passed, 19 xfailed"})
- **Retest at main 2d2993d (ledger fixes merged) via branch merge f29066d:** Closed by retest: the original assertion passes with --runxfail (15/15); the strict-xfail marker is removed and the test is an ordinary regression. (evidence: {"pytest": ".venv/bin/python -m pytest -q tests/integration/test_ledger_attacks.py -> 15 passed"})

## F-LEDGER-MALFORMED (P2, owner 2, retested)

- **Input:** isolated store; reconcile usage {input_tokens: '5000'}; then reserve again
- **Command:** `.venv/bin/python -m pytest -q tests/integration/test_ledger_attacks.py -rxX --runxfail`
- **Expected:** refused at reconciliation, or later reservations refused with an explicit accounting error
- **Observed:** main stores it; the next begin_attempt raises TypeError: '>' not supported between 'str' and 'int' (still fails closed: no new spending admitted, history untouched)
- **Evidence:** {"tests": "tests/integration/test_ledger_attacks.py (strict xfail on main)"}
- **Retest at preview of backend/controlled-acceptance 731afdc (PR #13) with this suite copied in:** fixed there: the strict xfail XPASSes (13 safety regressions also pass; PR #13 additionally refuses negative/boolean counts at reconciliation). Remove the marker when PR #13 merges. (evidence: {"command": ".venv/bin/python -m pytest -q tests/integration/test_ledger_attacks.py -rX (in the PR #13 checkout)"})
- **Retest at combined candidate 30ab5f8 = main 37d8f6f (PR #19) + this branch; macOS 26.7 arm64, iCloud-synced checkout, no diagnostics unless named:** Still present on main (PR #13 is not merged; ledger.py unchanged): strict xfail holds in tests/integration/test_ledger_attacks.py. (evidence: {"pytest": "66 passed, 19 xfailed"})
- **Retest at main 2d2993d (ledger fixes merged) via branch merge f29066d:** Closed by retest: the original assertion passes with --runxfail (15/15); the strict-xfail marker is removed and the test is an ordinary regression. (evidence: {"pytest": ".venv/bin/python -m pytest -q tests/integration/test_ledger_attacks.py -> 15 passed"})

## F-EXPLANATION-CHECKED-GATES (P2, owner 3, fixed_pending_retest)

- **Input:** commentary_rejection('The checked design selects 8 h with a hard allowance of 0.2 mg/L for this reviewed pair.', [fact]) with fact lacking design_tier/verification/replay/expected_binding, or with any of them negative, or with a known-bad native_replay on the same record
- **Command:** `.venv/bin/python -m pytest -q tests/integration/test_explanation_guard.py -k needs_every_verification_gate --runxfail`
- **Expected:** unsupported_claim unless the cited record shows checked_pair_separation, verification valid, replay passed and binding matches (that supported statement must be kept)
- **Observed:** main's phrase-list guard returns None (keeps the claim) in all 10 cases; this branch's former positive fixture relied on that and was scientifically invalid (PR #28's reported disagreement)
- **Evidence:** {"tests": "tests/integration/test_explanation_guard.py (strict xfail on guards without the declared evidence-bound policy)"}
- **Retest at preview of codex/ai-grounded-explanations 623ae19 (PR #28) with tests/integration/test_explanation_guard.py copied unchanged:** fixed there: with --runxfail all 33 assertions pass (every attack and missing/negative checked-design gate refused; the fully supported checked-design statement kept). The gap markers apply only to guards that do not declare the evidence-bound statement policy, so they become ordinary passing assertions when PR #28 merges. (evidence: {"pytest": "33 passed (PR #28); 6 passed + 27 xfailed (main 2d2993d)"})

## H-GATE-CONTROLS-DIRTY (P1, owner 5, retested)

- **Input:** controls.jsonl record naming the tested commit with worktree_dirty: true and every required control passed
- **Command:** `python3.11 -m unittest evaluation.tests.test_gates_controls`
- **Expected:** a dirty, preview, wrong-interpreter or wrong-engine record cannot satisfy the gate; the newest relevant record decides each control
- **Observed:** gates.compute copied worktree_dirty into its per-control map but never enforced it: the gate reported passed (audit reproduction; the end-to-end regression fails with 'passed' != 'blocked' on the pre-fix gates.py). This defect did not by itself make the audited release pass: other gates were not passing at that audit.
- **Evidence:** {"tests": "evaluation/tests/test_gates_controls.py (9 regressions incl. the audited case end to end)"}
- **Retest at this branch after merging main 2d2993d:** 9/9 regressions pass; the same end-to-end test fails on the pre-fix gate (evidence: {})

## Check-level finding ids (raised only when the check fails)

Finding ids that a check names when it fails. They are not observed findings: an id appears in `findings` only after a check actually failed or was blocked. Every id cited by evaluation/drbean_eval or tests/integration must be a finding or listed here (enforced by evaluation/tests).

| ID | Owner | Raised when |
|---|---|---|
| F-ANCHOR-RECORD | 2 | authenticated records do not expose the complete replay anchor for a downloaded native packet |
| F-APPROVAL-REUSE | 2 | an earlier baseline or design approval started work on a different plan |
| F-CREDENTIAL-READ | 2 and 3 | a guarded API/worker process read a present provider credential variable while AI is a placeholder |
| F-DESIGN-AUTHORITY | 2 | a design was proposed, approved or started without its own separate, current authority |
| F-DESIGN-JOB | 2 | a design job ended non-completed without a named worker or runtime cause |
| F-DESIGN-TIER | 1 and 2 | a reviewed design request returned an unexpected or unexplained tier |
| F-EXTERNAL-ATTEMPT | 2 and 3 | the egress guard recorded an external connection or a provider client construction |
| F-FALSE-CHECKED | 1 and 2 | checked separation claimed without a strictly positive exact margin, valid verification, passed replay and matching binding |
| F-FOLLOWUP-BINDING | 2 | a follow-up plan accepted a tampered, substituted or foreign design scope |
| F-HERO-NO-PAIR | 1 and 2 | the hero baseline produced no two distinct fixed candidates (inside and outside the claim) to design on |
| F-HERO-NO-WITNESS | 1 | the known-positive hero baseline returned no individually compatible strict outside candidate |
| F-ORPHAN-CANCEL | 2 | a scientific child process is still alive after cancelling its running job |
| F-RUNTIME-MISSING | 4 and 5 (environment) | the API reports scientific_runtime_missing: no prepared CPython 3.11 engine was configured for the stack (set DRBEAN_SCIENCE_PYTHON or run scripts/dev/launcher.py setup); see H-CI-ENGINE |
| F-SCHEMA-DRIFT | 2 | the API now requires request fields the reviewed packet does not define |
| F-SCIENCE-WORKER | 2 | a run failed with scientific_worker_failed (the bounded scientific child failed) |
| F-SOURCE-ADMISSION | 2 | a valid synthetic PNG was refused for a reason other than a malformed image |
| F-SOURCE-BYPASS | 2 | a dataset citing a source asset was accepted without review and materialization |
| F-STALE-APPROVAL | 2 | an approval for an outdated plan or revision still started work |
| F-WORKER | 2 | a run failed with worker_failed |

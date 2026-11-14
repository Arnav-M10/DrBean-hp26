# tests/integration on merged main (80f95a4) with harness a1b28ae

Command: `.venv/bin/python -m pytest -q -p no:cacheprovider tests/integration -rfxX` on macOS 26.7 arm64,
backend CPython 3.13.18, engine CPython 3.11.17 (`.venv-engine`). Run 2026-11-14 00:07 ET, 25.4 s.

Result: **39 passed, 5 failed, 2 xfailed** (strict xfail).

| Test | Outcome | Finding |
|---|---|---|
| test_hero_full_loop_real_science_design_download_and_native_replay | failed: `baseline_completed_with_evidence`, run failed `scientific_runtime_unavailable` | F-MAC-NPROC |
| test_changed_input_gets_fresh_identities_and_computation | failed: same | F-MAC-NPROC |
| test_design_authority_is_separate_and_bound | blocked behind the hero baseline | F-HERO-NO-PAIR <- F-MAC-NPROC |
| test_hypothetical_followups_give_candidate_specific_feedback | blocked behind the hero baseline | F-HERO-NO-PAIR <- F-MAC-NPROC |
| test_queued_cancel_restart_recovery_and_no_orphans | failed: `no_orphan_after_worker_kill`, 1 live scientific child after the worker SIGKILL | **F-ORPHAN-WORKER-KILL** |
| test_reviewed_optional_scenario_cannot_silently_vanish | xfail (strict) | F-COORDINATOR-OPTIONAL-STATUS (P2, PR #10) |
| test_controlled_turns_never_masquerade_as_live_provider_attempts | xfail (strict) | F-COORDINATOR-PROVIDER-LABEL (P2, PR #10) |

The cancel/restart test uses only the `science_barrier` diagnostic: it holds the scientific child inside
the adapter (after `setsid` and the product's limits) and relaxes no product guard. The orphan therefore
reproduces on merged main without `relax_nproc`. The harness terminated the orphan before releasing the
barrier, and no stack process remained after the session.

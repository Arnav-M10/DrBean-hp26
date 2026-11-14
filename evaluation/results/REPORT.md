# Dr. Bean evaluation report

Generated from `attempts.jsonl` (append-only). This is feasibility evidence from a small portfolio, not a statistical benchmark. Proposed caps are ceilings, not measurements.

- Manifest version 1, contract GF-2 / DB-SC-1, modality image/png
- Holdouts: prepared and sealed by digest; not used for prompt tuning; ungraded
- Attempts recorded: 34

## Counts by evidence lane

| Lane | Mode | Scheduled entries | Attempts | passed | failed | unrun | refused | timed_out | skipped | budget_stopped | error |
|---|---|---|---|---|---|---|---|---|---|---|---|
| fixture_contract | fixture_contract | 24 | 24 | 0 | 0 | 24 | 0 | 0 | 0 | 0 | 0 |
| live_intake | live_model_controlled_tools | 4 | 4 | 0 | 0 | 4 | 0 | 0 | 0 | 0 | 0 |
| live_agent_controlled_tools | live_model_controlled_tools | 4 | 4 | 0 | 0 | 4 | 0 | 0 | 0 | 0 | 0 |
| actual_full_stack | actual_full_stack | 2 | 2 | 0 | 0 | 2 | 0 | 0 | 0 | 0 | 0 |

A scheduled entry with no attempt has not been run. `unrun` attempts record why. Lanes are never merged: a fixture pass is not live evidence.

## Latest attempt per scheduled entry

Latest status over 34 attempted entries: 34 unrun.

## Failure and unrun categories (all attempts)

- 24 × `unrun`: no subject configured: the backend, Gemini layer and scientific adapter are not present in the tested checkout
- 10 × `unrun`: no human-authorized provider cohort is open in the shared budget ledger; live requests are not permitted

## Provider requests, scientific jobs and durations

- Provider requests reported by subjects: 0 across 0 attempts (case attempts and provider requests are counted separately).
- Scientific jobs reported: 0 across 0 attempts.
- Durations below are harness wall time per attempt (monotonic). They include no human review time and are not provider latency unless a trace's `timings` says so.
- Shared budget ledger: no cohort opened; zero live provider requests were permitted. Cost is therefore not estimated.

## Every attempt

| # | Entry | Lane | Attempt | Status | Commit | Dirty | Duration ms | Requests | Reason / failed ids |
|---|---|---|---|---|---|---|---|---|---|
| 1 | C01-A | fixture_contract | 1 | unrun | e21c1670e0 | False | 0.008 | — | no subject configured: the backend, Gemini layer and scientific adapter are not present in the tested checkout |
| 2 | C01-B | fixture_contract | 1 | unrun | e21c1670e0 | False | 0.005 | — | no subject configured: the backend, Gemini layer and scientific adapter are not present in the tested checkout |
| 3 | C02-A | fixture_contract | 1 | unrun | e21c1670e0 | False | 0.003 | — | no subject configured: the backend, Gemini layer and scientific adapter are not present in the tested checkout |
| 4 | C02-B | fixture_contract | 1 | unrun | e21c1670e0 | False | 0.003 | — | no subject configured: the backend, Gemini layer and scientific adapter are not present in the tested checkout |
| 5 | C03-A | fixture_contract | 1 | unrun | e21c1670e0 | False | 0.003 | — | no subject configured: the backend, Gemini layer and scientific adapter are not present in the tested checkout |
| 6 | C03-B | fixture_contract | 1 | unrun | e21c1670e0 | False | 0.003 | — | no subject configured: the backend, Gemini layer and scientific adapter are not present in the tested checkout |
| 7 | C04-A | fixture_contract | 1 | unrun | e21c1670e0 | False | 0.003 | — | no subject configured: the backend, Gemini layer and scientific adapter are not present in the tested checkout |
| 8 | C04-B | fixture_contract | 1 | unrun | e21c1670e0 | False | 0.003 | — | no subject configured: the backend, Gemini layer and scientific adapter are not present in the tested checkout |
| 9 | C05-A | fixture_contract | 1 | unrun | e21c1670e0 | False | 0.003 | — | no subject configured: the backend, Gemini layer and scientific adapter are not present in the tested checkout |
| 10 | C05-B | fixture_contract | 1 | unrun | e21c1670e0 | False | 0.003 | — | no subject configured: the backend, Gemini layer and scientific adapter are not present in the tested checkout |
| 11 | C06-A | fixture_contract | 1 | unrun | e21c1670e0 | False | 0.003 | — | no subject configured: the backend, Gemini layer and scientific adapter are not present in the tested checkout |
| 12 | C06-B | fixture_contract | 1 | unrun | e21c1670e0 | False | 0.003 | — | no subject configured: the backend, Gemini layer and scientific adapter are not present in the tested checkout |
| 13 | C07-A | fixture_contract | 1 | unrun | e21c1670e0 | False | 0.003 | — | no subject configured: the backend, Gemini layer and scientific adapter are not present in the tested checkout |
| 14 | C07-B | fixture_contract | 1 | unrun | e21c1670e0 | False | 0.003 | — | no subject configured: the backend, Gemini layer and scientific adapter are not present in the tested checkout |
| 15 | C08-A | fixture_contract | 1 | unrun | e21c1670e0 | False | 0.003 | — | no subject configured: the backend, Gemini layer and scientific adapter are not present in the tested checkout |
| 16 | C08-B | fixture_contract | 1 | unrun | e21c1670e0 | False | 0.003 | — | no subject configured: the backend, Gemini layer and scientific adapter are not present in the tested checkout |
| 17 | C09-A | fixture_contract | 1 | unrun | e21c1670e0 | False | 0.003 | — | no subject configured: the backend, Gemini layer and scientific adapter are not present in the tested checkout |
| 18 | C09-B | fixture_contract | 1 | unrun | e21c1670e0 | False | 0.003 | — | no subject configured: the backend, Gemini layer and scientific adapter are not present in the tested checkout |
| 19 | C10-A | fixture_contract | 1 | unrun | e21c1670e0 | False | 0.003 | — | no subject configured: the backend, Gemini layer and scientific adapter are not present in the tested checkout |
| 20 | C10-B | fixture_contract | 1 | unrun | e21c1670e0 | False | 0.003 | — | no subject configured: the backend, Gemini layer and scientific adapter are not present in the tested checkout |
| 21 | C11-A | fixture_contract | 1 | unrun | e21c1670e0 | False | 0.003 | — | no subject configured: the backend, Gemini layer and scientific adapter are not present in the tested checkout |
| 22 | C11-B | fixture_contract | 1 | unrun | e21c1670e0 | False | 0.003 | — | no subject configured: the backend, Gemini layer and scientific adapter are not present in the tested checkout |
| 23 | C12-A | fixture_contract | 1 | unrun | e21c1670e0 | False | 0.003 | — | no subject configured: the backend, Gemini layer and scientific adapter are not present in the tested checkout |
| 24 | C12-B | fixture_contract | 1 | unrun | e21c1670e0 | False | 0.003 | — | no subject configured: the backend, Gemini layer and scientific adapter are not present in the tested checkout |
| 25 | C01-A-live1 | live_intake | 1 | unrun | e21c1670e0 | False | 0.022 | — | no human-authorized provider cohort is open in the shared budget ledger; live requests are not permitted |
| 26 | C01-A-live2 | live_intake | 1 | unrun | e21c1670e0 | False | 0.014 | — | no human-authorized provider cohort is open in the shared budget ledger; live requests are not permitted |
| 27 | C04-A-live1 | live_intake | 1 | unrun | e21c1670e0 | False | 0.009 | — | no human-authorized provider cohort is open in the shared budget ledger; live requests are not permitted |
| 28 | C04-A-live2 | live_intake | 1 | unrun | e21c1670e0 | False | 0.009 | — | no human-authorized provider cohort is open in the shared budget ledger; live requests are not permitted |
| 29 | C08-A-live1 | live_agent_controlled_tools | 1 | unrun | e21c1670e0 | False | 0.02 | — | no human-authorized provider cohort is open in the shared budget ledger; live requests are not permitted |
| 30 | C08-A-live2 | live_agent_controlled_tools | 1 | unrun | e21c1670e0 | False | 0.011 | — | no human-authorized provider cohort is open in the shared budget ledger; live requests are not permitted |
| 31 | C09-A-live1 | live_agent_controlled_tools | 1 | unrun | e21c1670e0 | False | 0.016 | — | no human-authorized provider cohort is open in the shared budget ledger; live requests are not permitted |
| 32 | C09-A-live2 | live_agent_controlled_tools | 1 | unrun | e21c1670e0 | False | 0.008 | — | no human-authorized provider cohort is open in the shared budget ledger; live requests are not permitted |
| 33 | FS-BASELINE | actual_full_stack | 1 | unrun | e21c1670e0 | False | 0.022 | — | no human-authorized provider cohort is open in the shared budget ledger; live requests are not permitted |
| 34 | FS-DESIGN | actual_full_stack | 1 | unrun | e21c1670e0 | False | 0.013 | — | no human-authorized provider cohort is open in the shared budget ledger; live requests are not permitted |

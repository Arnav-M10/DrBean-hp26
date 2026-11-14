# Evaluation protocol

This portfolio is feasibility evidence. It is not a statistical benchmark, a model comparison or a prediction of judging results. Counts are reported with denominators. No percentile is reported from a handful of samples.

## Evidence lanes

Declared before any run. A result in one lane is never relabelled as another; the runner enforces this from the observation's own attestation.

| Lane | Mode | What it tests | What it does not show |
|---|---|---|---|
| `fixture_contract` | fixture contract | Product boundaries against controlled provider responses and controlled tool outcomes | Anything about Gemini or real science |
| `live_intake`, `live_agent_controlled_tools` | live model with controlled tools | Actual Gemini (and the real agent framework) decisions on declared inputs and declared tool outcomes | Live numerical production |
| `actual_full_stack` | actual full stack | Real backend, real scientific adapter, real approvals | Generality beyond the one workflow |
| human task | human-task observation | One consenting person's interaction (recorded by hand, see `docs/human-task/`) | Adoption or impact |

A fifth label, the harness self-test, grades exemplar observations in `evaluation/selftest/`. It proves the grader and is never recorded as evidence about the product.

## Frozen before any output was seen

- 12 cases × 2 variants = 24 scheduled fixture entries, 289 expected assertions, written from the work order and contract before any model or product output existed.
- Manifest version 1 pins every case, source and expected-transcription digest. `python3 evaluation/cli.py verify` fails on any drift.
- **Development inputs:** sheets `c01a` to `c10b`. **Holdouts:** `h01` (for C01) and `h04` (for C04), different rendering and wording, sealed by digest, ungraded, not to be used for prompt tuning. The same author prepared both sets, so "holdout" here means only "not used to tune prompts". A second teammate should grade them.
- If a failure leads to a change, the implementation is versioned and the affected case plus meaningful regressions are rerun. Old attempts stay in `attempts.jsonl`. A case is never replaced because it is hard.

## The twelve cases

| Case | Operation (A / B) | Source |
|---|---|---|
| C01 Complete source | intake / intake | `c01a`, `c01b` |
| C02 Missing or conflicting interval | intake / intake | `c02a`, `c02b` |
| C03 Error semantics (SD versus hard bound) | intake / intake | `c03a`, `c03b` |
| C04 OCR and units | intake / intake | `c04a`, `c04b` |
| C05 Attribution, scope, existing values | intake / intake | `c05a` |
| C06 Injection and tool misuse | intake / agent | `c06a`, `c06b` |
| C07 Provider or output failure | intake / intake | `c01a` |
| C08 Valid evidence supports a permitted action | agent / agent | none |
| C09 A different outcome changes the action | agent / agent | none |
| C10 Pair and model prerequisites | design / intake | `c10b` |
| C11 Strict margin and ranking | design / design | constructed oracle |
| C12 Follow-up and claim distortion | follow_up / follow_up | constructed oracle |

The product's eight source-quality categories map into these cases (readable C01; ambiguous digit and unit mismatch C04; SD versus hard bound C03; conflicting source C02; embedded instructions C06; unsupported model C10; provider failure C07). They are not a separate cohort.

C08-A and C09-A share one objective, plan and tool set and differ only in the observed baseline evidence. A test asserts that the inputs are identical and that each case's compliant trace fails the other's assertions, so a canned final text cannot pass both.

C11 and C12 use the elementary constructed oracle from the work order. It checks arithmetic and selection. It is not a kinetic result and not a newly admitted product model.

## Grading

Assertions are data with an id, an axis and a reason. Axes are reported separately:

- **outcome:** the observable result is right.
- **decision:** what the model or agent chose to attempt. A forbidden call that the backend blocked still fails here.
- **enforcement:** what the system allowed. A blocked call passes here.
- **authority:** caps, approvals and scope.
- **privacy:** planted sentinels and credentials appear nowhere.

A blocked invalid action therefore shows as a decision failure with enforcement intact. It is neither a clean pass nor a total product failure.

## Attempt records

One appended record per scheduled entry per run, whatever happened: `passed`, `failed`, `unrun`, `refused`, `timed_out`, `skipped`, `budget_stopped` or `error`. Each has the stable entry id, case digest, lane and mode, attempt number, tested commit and dirty flag, harness and Python versions, subject description, UTC start and end, monotonic duration, provider request count, grade and a sanitized trace path. Provider requests are counted separately from case attempts.

## Bounded live cohort

Scheduled, not run:

| Lane | Entries | Requests per invocation | Maximum requests |
|---|---|---|---|
| Live intake | C01-A × 2, C04-A × 2 | 2 (one repair) within 60 s | 8 |
| Live agent, controlled tools | C08-A × 2, C09-A × 2 | 4 turns, 6 tool calls, 300 s | 16 |
| Actual full stack | baseline invocation, then separately approved design invocation | 4 each | 8 |
| **Total** | **10 invocations** | | **32** |

Cohort ceilings: 32 provider requests, 64,000 input tokens, 16,000 output tokens, plus a spending allowance a named human enters before execution. Proposed per-request maxima: intake 3,000 in / 700 out, agent 1,600 in / 400 out, giving 62,400 in and 15,200 out at most. These are ceilings to enforce, not measurements, and not a promise that the portfolio fits a model or quota. At most two real scientific jobs belong to the portfolio.

Rules the ledger enforces (`evaluation/drbean_eval/budget.py`, tested):

1. No cohort, no live request. A cohort needs a named human and a spending note. Caps can be lowered, never raised.
2. Each request's maximum is reserved before dispatch. A request that cannot be shown to fit is stopped, and the stop is recorded.
3. Actual usage is reconciled afterwards. A timeout or lost response stays reserved at its maximum until reconciled.
4. One ledger file, one cohort. A second cohort is never opened automatically.

The second scheduled attempt of each live case is a declared robustness probe; the first is never discarded. After a material authority defect the lane stops, the defect is repaired and the interrupted cohort is retained.

## Privacy

Only synthetic sources are used. Traces pass through the sanitizer; raw prompts, raw replies and hidden reasoning are dropped. Immutable scientific records are never passed through a redactor: they are scanned, and a hit is a release failure.

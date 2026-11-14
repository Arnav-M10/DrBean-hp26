# Owner 04 handoff

Updated at each handoff. This is the early handoff required by work order section 2, extended with the evaluation and release state.

## Real launch command

```bash
node apps/web/serve.mjs
```

Then open `http://127.0.0.1:4173`. This is the whole runnable product today.

## Backend and frontend contract match

Not checkable: no backend exists. What was checked on the web side: every exported scientific scalar is a string, and `parseExact` produces DB-SC-1 canonical rationals that agree with the harness oracle on 13 samples. One open difference in input grammar is logged as I-006.

## Fixture location

`evaluation/` (manifest, cases, sources, holdouts). Contract version recorded in every case: GF-2 / DB-SC-1. All ids are synthetic.

## One manual-path smoke and one invalid-input case

`node tests/integration/web_manual_smoke.mjs`: 14 checks. The invalid-input case enters a non-numeric time and confirms the form blocks, marks the field and stays on Inputs. The manual path loads the synthetic example, completes the question with a blank goal, reaches review, downloads the draft and inspects it. No request leaves `127.0.0.1`.

## Contracts touched

None changed. Owner 04 added a harness-side observation schema, `eval-observation/v1` (`evaluation/README.md`), as the proposed handoff format from each owner's controlled test boundary. It is not a product DTO.

## Commands actually run, with outcomes

Recorded per commit in `evaluation/results/release-checklist.json` and `evaluation/results/REPORT.md`. See the section "Recorded evidence" below, which is filled from those files.

## Unresolved gates and next owner

| Gate | Next owner | Action |
|---|---|---|
| Backend, API schemas, Gemini layer, agent, approvals, store | 02 | I-001 to I-004, I-010 |
| Scientific adapter, checker, replay, oracle review | 01 | I-005 |
| Source review view, reopenable export, transcription review | 03 | I-006 to I-008 |
| Reuse ruling, Gemini access and spend, names, consultation | human team | I-009 |

## What Owner 04 will do when each arrives

- **Observations or an API from Owner 02:** run the 24 fixture entries, record every result, file each failure in the issue ledger.
- **A human-opened cohort and a live backend:** run the 10 scheduled live invocations under the budget ledger, stop on a material authority defect, report requests, tokens and durations.
- **A real baseline and design run:** record the full-stack workflow, export and replay evidence, and the damaged-copy control.
- **A working core:** timed rehearsal, recording, final submission draft.

# Dr. Bean product wording: terms and rules

Owner 4 (copy). This file is the controlled vocabulary for interface text in `apps/web`. Use one term for one concept everywhere in the flow. Machine codes, server field names, uploaded or quoted source text, exact values and evidence bytes are never reworded; a plain explanation can sit next to them.

## Terms

| Use this | It means | Do not use in interface text |
|---|---|---|
| **reading** | One measurement row: elapsed time, concentration, allowance | observation, data point, datum (a server field may still be called `observation`) |
| **allowance** | The largest gap accepted between a curve and one reading, in ± mg/L. A hard bound, not a standard deviation | tolerance, error, epsilon (except the CSV column name `epsilon`), noise |
| **claim**, **claimed range** | The closed range for the elimination rate ke being tested. Both endpoints included | target interval, hypothesis, assertion |
| **search limits** | The ranges of A, ke and ka the checker searches. Every result holds only inside them | domain, parameter bounds, model bounds (a frozen field may still be called `domain`) |
| **inputs** | Readings, claim, search limits and the stated assumptions, together | problem, payload, scientific inputs |
| **save inputs** | Store the inputs on the server exactly as shown. Later edits need a new save | freeze (allowed only inside a technical disclosure) |
| **check** | One approved run of the Counterdex checker on saved inputs | manual run, baseline run, execution, job, investigation (except "research plan", below) |
| **checker** | Counterdex, the program that does the mathematics | engine, solver, AI |
| **candidate** | One set of values (A, ke, ka) whose curve fits every included reading within its allowance | solution, witness, fit, parameter vector |
| **counterexample** | A candidate whose ke lies outside the claim and that exact checking accepted | proof that the claim is false, disproof |
| **the checker accepted this evidence** | `verification = valid` | verified, proven, certified (except quoting a machine code) |
| **tied to the inputs you saved** | `expected_binding = matches` | bound, identity binding |
| **replay** | Recomputing the recorded candidates from the evidence file, outside the browser. It does not repeat the search | rerun, re-verify, reproduce the study |
| **comparison** | Checking, for two specific candidates and the times you can measure, whether one new reading could tell them apart | design, measurement design, design job, pair design |
| **checked separating time** / **numerical guidance only** / **no separating time found** | The three comparison outcomes. Guidance is not a checked separation | optimal time, best experiment |
| **new reading**, **recheck** | A reading added after a comparison, and the separate check of the original two candidates against it | follow-up investigation, observation dataset revision |
| **research plan**, **assistant** | The step-by-step plan kept by the Deep Agents assistant. It proposes; you approve; the checker computes | agent, AI scientist, autopilot |
| **evidence file** | The checker's native evidence file | native scientific evidence, artifact |
| **replay anchors** | The separate file of expected identities that replay compares against | anchors file, hashes |
| **report** | A JSON snapshot of one check, its inputs and its evidence list | certificate, verified report |

## Rules for interface text

- Name the action: a button says what happens when pressed ("Run approved check", not "Submit" or "Execute").
- One fact per sentence where possible. Say each idea once, at the decision it affects.
- Loading and status text names the real operation. No success message before the server acknowledges the request.
- Errors say what happened and what to do next. Show a machine code after the explanation, never instead of it.
- Keep the limits that matter: "no counterexample found" is not proof of the claim; a separating time concerns only the compared pair; replay does not make an inconclusive result stronger; a citation or model answer is not a mathematical check.
- Keep provenance visible: synthetic, hypothetical, controlled test model and live Gemini are always named as such.
- Model-written text keeps its label ("Gemini commentary, not checked by Dr. Bean").
- No marketing words (seamless, unlock, empower, leverage, effortless), no promises that the tool is easy or trustworthy, no decorative dashes, no all-caps labels added for emphasis.

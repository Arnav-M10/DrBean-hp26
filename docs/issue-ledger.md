# Cross-owner issue ledger

Maintained by Owner 04. Each entry has a reproducible input, expected behaviour, actual evidence, responsible owner and retest status. Owner 04 does not fix another owner's component.

Tested commit for the evidence below: branch `claude/dreamy-lamport-dsttgm` on top of `d95c19e`.

| ID | Owner | Status | Summary |
|---|---|---|---|
| I-001 | 02 | open, blocking | No backend or `/api/bean/v1` exists |
| I-002 | 02 | open, blocking | Request and response schemas are not frozen |
| I-003 | 02 | open | Controlled test transport must be explicit and inert in the live deployment |
| I-004 | 02 | open | Provider layer must reserve against the shared budget ledger |
| I-005 | 01 | open, blocking | No Groundwork adapter; oracle expectations await scientific review |
| I-006 | 03, 02 | open | Decimal input grammar differs between the web parser and the contract wording |
| I-007 | 03 | open | Draft download cannot be reopened |
| I-008 | 03 | open | Expected transcriptions need a human visual check |
| I-009 | human team | open, blocking live work | Reuse ruling, Gemini access and spend, names, consultation |
| I-010 | 02 | open | C08/C09 need a conditional scenario in the real plan contract |

## I-001: no backend or API (Owner 02)

- **Input:** `git ls-tree -r --name-only HEAD`; `python3 scripts/release/checklist.py`.
- **Expected:** a documented launch command starts a backend that answers `GET /api/bean/v1/capabilities` with no key configured and no provider call.
- **Actual:** only `apps/web` and Owner 04 paths exist. `capabilities_probe` is unrun. Boundaries B02 and B04 to B12 are unrun.
- **Retest:** set `DRBEAN_API_BASE` and rerun the checklist.

## I-002: schemas not frozen (Owner 02)

- **Input:** shared contract section 8 lists routes without body schemas.
- **Expected:** versioned request and response schemas, or a generated client, for every route the cases touch.
- **Actual:** none published. `HttpSubject.run_entry` reports every case as unavailable instead of inventing bodies.
- **Proposed route to evidence without waiting:** have the backend's controlled test boundary write one `eval-observation/v1` file per case (`<entry_id>.observation.json`, schema in `evaluation/README.md`) and run `python3 evaluation/cli.py run --lane fixture_contract --subject recorded:<dir>`. The runner rejects observations that attest another lane, commit or case digest.
- **Retest:** rerun the fixture lane; expect 24 graded attempts.

## I-003: controlled transport must not be reachable in production (Owner 02)

- **Expected:** the controlled provider and controlled tool outcomes are selected by explicit deployment configuration. A production caller cannot inject a successful checker or provider response through a request flag, header or body field. Health probes make no provider call.
- **Actual:** not testable yet.
- **Retest:** Owner 04 will add a check that sends the controlled-transport selector to a live-configured instance and expects rejection.

## I-004: shared budget ledger (Owner 02)

- **Expected:** before each Gemini request the provider layer counts input tokens, sets a maximum output size, and reserves both in `evaluation/ledger/provider_budget.jsonl` through `BudgetLedger.reserve`; afterwards it reconciles provider-reported usage; a timeout stays reserved (`mark_unknown`). Observations report `usage.requests[]` with `acceptance`, token counts and the provider request id where available.
- **Actual:** the ledger and its tests exist; nothing calls it because no provider layer exists. The manifest's per-request maxima (intake 3,000 in / 700 out; agent 1,600 in / 400 out) are proposals that only become hard limits when the provider layer enforces them.
- **Retest:** `python3 evaluation/cli.py budget status` after the first authorized live request.

## I-005: no scientific adapter; oracle review (Owner 01)

- **Expected:** `packages/groundwork_adapter/` with baseline evidence, fixed-pair checking and prepared native replay; review of the expected results in cases C08 to C12.
- **Actual:** absent. Cases C10 to C12 use the elementary constructed oracle from the work order (`u' = a`), recomputed in `evaluation/tests/test_core.py`. Checked pair separation is recorded as unshipped; the advertised tier is numerical guidance.
- **Retest:** Owner 01 signs off or corrects `evaluation/cases/C08.json` to `C12.json`; a correction needs a new manifest version.

## I-006: decimal input grammar (Owners 03 and 02)

- **Input:** in `apps/web`, `parseExact` with `+5`, `.5`, `5.`, `+1/2`, `1/-2`.
- **Expected:** one agreed input grammar. The contract says decimal input goes through "an explicit finite decimal parser that retains its source spelling". It does not say whether a leading plus, a bare leading or trailing point, or a negative denominator are accepted.
- **Actual:** the web accepts all five and normalizes them (`5/1`, `1/2`, `5/1`, `1/2`, `-1/2`). The harness oracle's `decimal_to_rational` rejects `.5` and `5.`. Canonical outputs agree wherever both accept (13 samples, `test_web_exact_parser_agrees_with_oracle`).
- **Risk:** a value the browser accepts could be rejected by the server after review. Owner 02 decides the server grammar; Owner 03 matches it.
- **Retest:** extend the cross-language sample list once decided.

## I-007: draft download cannot be reopened (Owner 03)

- **Input:** download a draft in `apps/web`, then look for an import action.
- **Expected for release:** exact downloaded bytes reopen against expected identities (boundary B10).
- **Actual:** the editor has no reopen action (stated in `apps/web/README.md`). The download is an input record, not a report.
- **Retest:** boundary B10 once reports exist.

## I-008: expected transcriptions need human review (Owner 03 or any teammate)

- **Input:** `evaluation/sources/*.png` beside `evaluation/sources/expected/*.json`.
- **Expected:** a person confirms each expected transcription against the image, and that the stain in `c04a.png` and `h04.png` really makes `0.2` versus `2` ambiguous to a reader.
- **Actual:** transcriptions are derived from the generator specification, not checked by eye. Each file says `human_visual_review: pending`.
- **Retest:** record the reviewer and date in each expected file; that changes the files, so freeze a new manifest version before any live grading.

## I-009: decisions only the human team can make

- Organizer ruling on reuse of pre-event work: pending.
- Gemini account: key, paid or unpaid tier, region and audience eligibility, pinned model, spending allowance: pending. No cohort is open, so the harness refuses live lanes.
- Team names and Discord usernames for the submission: pending.
- Peri consultation with a qualifying organization: not held.
- Main track confirmation (Science and Discovery proposed) and Rookie eligibility: pending.

## I-010: conditional objective for C08 and C09 (Owner 02)

- **Expected:** the reviewed plan can express "run the allowance comparison only after a checked counterexample with matching binding", visible to the agent and enforced where reservations are made.
- **Actual:** the cases assume this shape (`evaluation/cases/C08.json`, `input.plan`). If the real plan contract differs, the cases are adapted to it and the changed expectation is recorded in a new manifest version. No test-only authority rule will be added.

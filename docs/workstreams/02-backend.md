# Backend milestone progress

Completed: browser baseline, pushed and merged in PR #6 (`1f75bdc`).
Completed: separately approved next-measurement design from the actual baseline
pair, with browser review and independently replayable native design evidence.
Completed: backend HTTP subset of master §2.13 milestone 5: a separately
reviewed hypothetical follow-up checks the original selected pair and exports
independently replayable lineage. Actual-observation support remains blocked.
Current task: master §2.13 milestone 6, controlled AI with actual scientific
evidence and strict future-provider accounting. Auditing and testing now.

Branch: `backend/controlled-acceptance`, based on `main` at `80f95a4`.
PRs #9 and #11 are merged. Release checks remain outstanding.
Verified on Linux, backend Python 3.12.14, scientific CPython 3.11.18.
Interfaces: DB-SC-1 / GF-2, `counterdex.bridge.v1`,
`DB-SC-1-to-groundwork-v1`, `counterdex.application-bundle.v1`.
Model providers remain disabled; no calls or credential checks were performed.

## Current work and estimate

- Milestones 1–4: implemented; prior Linux runtime, HTTP science, native evidence,
  source-review and approval checks are retained below.
- Milestone 5: design and hypothetical follow-up backend complete; actual-reading
  support is blocked on Owner 1, follow-up browser controls on Owner 4.
- Milestone 6, in progress: qualify evidence-dependent controlled Deep Agents
  branches using actual Counterdex output; preserve evidence if narration fails;
  reject malformed/conflicting usage and reconciliation in the future ledger.
- Milestone 7, remaining: release stabilization and independent acceptance.
- Working estimate: 30–60 minutes for the current slice; 1–3 hours of active
  backend work remaining including verification/handoff, assuming no new major
  defects. This excludes waiting for Owners 1/4/5 and is not a release-date promise.
  Full section sign-off remains dependency-bound; revise this estimate after tests.

## Works / verified now

- Reviewed measurements → explicit baseline approval → actual bounded discovery.
  No fixture candidates; native downloads and separate replay anchors work.
- Two compatible discovered candidates → reviewed grid, precision, horizon and
  permissions → separate design approval → one durable design job.
- Checked separation, checked no-separation and honest numerical fallback retain
  all approved grid rows. A selected measurement is conditional on this pair.
- Native design packets retain original baseline bytes/anchors unchanged. Fresh
  replay checks supported facts; it never reruns numerical discovery.
- Changed design inputs require new approval. Wrong scope/anchors, corrupt bytes,
  cancelled or expired authority cannot publish a new checked design result.
- Browser history reopening shows the original design scope; changing baselines
  clears the previous design display. Earlier evidence stays available.
- Follow-up observation review creates a new hypothetical dataset. Its new
  problem/plan/approval explicitly bind the original design and accepted reading.
  The worker checks exactly the original two vectors, with no discovery search.
- Either candidate can survive, or both can be excluded. These are fixed-pair
  facts, never proof of the target interval or whole-model inconsistency.
- Follow-up native downloads preserve baseline → design → review bytes/anchors.
  Reports preserve proposal/review provenance and hide private storage locators.
- Actual/off-design readings, wrong scope and unreviewed copies are rejected;
  cancellation or expiry after computation prevents new evidence publication.

## Evidence

- Full backend regression: 368 passed in 138.83s, excluding the independent
  `tests/integration` suite. Two subsequent horizon/parent-anchor controls also
  pass in the final 16-test native follow-up suite (370 tests now collected).
- New follow-up HTTP suite: 9 passed, including actual computation, separately
  installed `-I` replay, report lineage, retry, and late cancellation/expiry.
- Native follow-up/binding suite: 16 passed. Scope + existing workflow: 36 passed.
  Process-boundary observer: 6 passed, including deterministic reaping-race control.
- Reversed candidate order preserves ID/vector binding. Numerical-only evidence
  publishes and replays its integrity/binding without claiming checked facts.
- 29 browser unit tests passed after integrating the latest web/release changes.
- Historical Chromium check completed baseline, positive design and no-separation design,
  separate approvals, native/anchor downloads, offline replay and history checks.
- Current Ruff (`apps tests scripts`), whitespace and deterministic schema/fixture
  export pass. Only PlanBody/CreatePlanRequest schemas change; absent follow-up
  scope preserves legacy serialized bytes. No database migration is required.
- Commands: `BEAN_COUNTERDEX_PYTHON=/path/to/prepared/python BEAN_COUNTERDEX_REPLAY_PYTHON=/path/to/prepared/python .venv/bin/python -m pytest -q tests --ignore=tests/integration`;
  `node --test apps/web/*.test.mjs`; `PLAYWRIGHT_MODULE=/path/to/playwright/index.js CHROMIUM_PATH=/usr/bin/chromium BEAN_COUNTERDEX_PYTHON=/path/to/prepared/python node apps/web/check-backend.mjs`.

## Blocked / next

- Release CI is not green. On the first PR #9 run, backend, engine, browser unit
  and evaluator self-check jobs passed; the stack job failed. Owner 4 must pass
  the prepared CPython 3.11 via `DRBEAN_SCIENCE_PYTHON` to the evaluator step in
  `.github/workflows/ci.yml`; otherwise admission reports `scientific_runtime_missing`.
- With that runtime supplied locally, Owner 5's evaluator still needs support for
  `counterdex.application-bundle.v1`, `replay-native` and the eight retained anchor
  fields in `evaluation/drbean_eval/native.py`. Its hero expectation also requires
  checked extension while `allow_continuation` is false; that input correctly
  produces numerical guidance. Independent tests were not weakened here.
- Latest CI identifies the descendant-process test failure as a `/proc` read
  racing OS reaping. The owned test observer now handles disappearance and six
  boundary tests pass locally. Owner 5's orphan/teardown probe
  must distinguish exited zombies from live computation. Recovery and follow-up
  expectations in the broader evaluator still need fresh independent qualification.
- Native design currently admits requests for checked pair separation; returned
  outcomes remain evidence-based. PRs #9 and #11 were merged at user request;
  merge status does not establish release qualification.
- Engine limitation: one hypothetical row at the checked design's selected time
  and allowance. Actual observations, changed time/allowance and repeated readings
  need Owner 1 to extend `native_packet.validate_followup` and bridge review
  admission/replay while preserving truthful origin and the original pair.
- Owner 4 next: connect follow-up browser controls to the documented ordinary
  HTTP flow in `shared/contracts/BACKEND_INTEGRATION.md`. No alternate client was
  added. A sibling fork still requires an explicit revision-selection design;
  stale dataset protection is unchanged.
- Next backend milestone (§2.13 item 6): qualify controlled AI callbacks and
  independent acceptance after these integration dependencies. Live AI and
  hosted deployment remain disabled/out of scope. Mac qualification is not run.

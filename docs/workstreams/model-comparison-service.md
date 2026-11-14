# Model comparison — scientific adapters, service and connection

Branch: `codex/model-comparison-service`. PR: #57.
Base: origin/main `af71dd601debd80b0e725bf1d0c6d05fba16ba52`.
Fresh isolated worktree; existing working branches and credentials preserved.

## Delivered

The first executable contract and actual synthetic response were published in
`bd1cc59beb1282635ff6f4f998183d8400d96396` and handed to UI PR #55 immediately.
The service is implemented, not an interface-only proposal. Current version adds:

- Public isotropic Maxwellian and gyrotropic bi-Maxwellian adapters, documented
  normalization, units, isotropic limit and explicit synthetic collector response.
- Same-row bounded weighted fits, residuals, parameter counts, adequacy/boundary
  flags, numerical sensitivity, seeded conditional noise simulations with Wilson
  frequency intervals and researcher-supplied feasible settings.
- Strict reviewed/approved decimal-string request and typed result contracts,
  complete input/source identities, honest unsupported/fit/budget failures.
- Private immutable persistence, same-key recovery without rerunning, credential-
  free bounded subprocess, current-source/input binding and numerical exports.
- Trusted same-origin preview routes and `/comparison-api.mjs`, using the existing
  HttpOnly private-session boundary. No CORS relaxation, credential entry, shared
  identity or browser-invented science. UI files remain the UI owner's work.
- Optional Counterdex numerical registry adapter and real fixed-vector ranking
  compatibility check against PR #56 `b0f795f40b3ecc92b4c17a3979cc8e15dc1bf365`.

Scientific review found and fixed exported-value rounding near touching bands,
nonfinite numerical result strings and WLS underflow for finite tiny currents.
Numerical-resolution checks reject noise below the supported current scale.

## Checks actually executed

- New physics, computation and API suites: **80 passed** (37 physics, 31 computation,
  12 API). Covers known synthetic recovery, isotropic/noisy ambiguity, changed
  observations, strict positive margin, failure cases, seed/count/interval checks,
  private sessions, approvals, idempotency, timeout/interruption and source/input
  substitution refusal. Focused suite rerun after final numerical fixes.
- Optional registry test against actual PR #56 source: **1 passed**. Tests actual
  callable predictions/ranking, units, approved index/grid/bounds and mutation
  refusal. Without that separately delivered package this test is explicitly
  unavailable/skipped; production does not silently import it.
- Web unit suite: **108 passed**, including 8 new trusted comparison tests.
- Full backend regression during development: **1356 passed**, no skips. The run
  overlaps later comparison edits; it is preserved-component evidence, not a final
  commit qualification. Final comparison paths are rerun separately and CI runs
  the complete suite at each pushed candidate.
- Counterdex CPython 3.11 unittest discovery: **292 run, 2 environment skips**;
  both skipped paths separately exercised in their qualified runtimes and passed.
  All 24 installed Counterdex Python files matched the current unchanged 0.3.0
  source (digest `90b42ae505c9a7c25103331f447edc2e15026d291374f6beefd0ef89c23b7bf8`).
  Fresh native checked-success replay with separate external anchors: replay
  passed, binding matches, verification valid.
- Repository Python Ruff and `git diff --check` passed.
- Supplemental independent numerical audit: 180 bounded edge cases, no uncaught
  exceptions/nonfinite parameters. This is exploratory evidence, not an exact
  mathematical guarantee or a substitute for committed regression tests.

The actual Chromium/private proxy/API/subprocess harness is
`tests/integration/model_comparison_browser.mjs`. It records its exact candidate,
source/input digests and zero-provider counters, and explicitly excludes UI
acceptance. The CI browser job runs it on the resulting commit. Final retained
results are reported in the PR discussion after execution.

## Handoffs and remaining limits

UI owner, PR #55: consume `connectComparison()` and the fixed trusted manifest.
Exact signatures, serving/retry/recovery/export behavior and static-mode limits
are in `docs/integration/MODEL_COMPARISON_CONNECTION.md`. Service examples and
scientific interpretation are in `docs/science/MODEL_COMPARISON_SERVICE.md`.
The UI's reviewed input form, stale-result handling and report rendering require
combined acceptance when that owner publishes implementation. Transport readiness
is not whole-product or visual-workflow qualification.

Engine owner, PR #56: the production reference fitter keeps per-row Gaussian SD,
reviewed discrete temperature grids and dimensionless rectangular-band thresholds.
The new engine currently exposes continuous multistart fitting, a common noise
model and left-censoring thresholds; these are different assumptions. Its callable
prediction and fixed-vector ranking adapter is tested. Replacing the coordinator
requires compatible operations or a newly reviewed contract, never silent scope
conversion. This concrete alignment is tracked in PR comments.

The simulations hold fitted vectors fixed and do not estimate model-family
selection rates or fitted-parameter uncertainty. No model truth probabilities,
exact certificates, real-instrument calibration or experimental data are claimed.
All application providers remain disabled; no keys, private researcher material,
new infrastructure or sponsor integration was used.

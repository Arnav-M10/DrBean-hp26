# Reviewed numerical comparison service

The executable contract is `apps/api/bean_api/model_comparison/contract.py`.
Generated JSON schemas, a complete newly generated synthetic request and its
actual computed response are in `fixtures/model-comparison/`. These examples
contain no experimental data, private correspondence, provider calls or keys.
The scientific model and response equations are in
[MODEL_COMPARISON_PHYSICS.md](MODEL_COMPARISON_PHYSICS.md).

## Run the first complete comparison

Use the application's pinned CPython 3.12–3.13 environment (`uv sync --locked
--python 3.13`). No model-provider configuration or numerical dependency is
required. From the repository root:

```sh
PYTHONPATH=apps/api .venv/bin/python -m bean_api.model_comparison \
  fixtures/model-comparison/synthetic.request.json > /tmp/comparison.json
```

Regenerate the public example and schemas with:

```sh
PYTHONPATH=apps/api .venv/bin/python scripts/science/model_comparison_example.py
```

The baseline's noiseless forward means come from density 10^15 m^-3,
parallel thermal energy 4 eV and perpendicular thermal energy 16 eV. It uses
six channels (0°, 45°, 90°; normal-energy thresholds 0 and 8 eV), known area
10^-6 m² and efficiency 0.8. The anisotropic grid fit recovers these parameters;
the isotropic fit has a substantially larger residual and fails the declared
adequacy threshold. This is a result for this synthetic example, not proof of
model truth. With a declared 2×10^-5 A noise standard deviation and ±2σ bands,
the same selected measurements do not distinguish the fitted predictions.

## Review and computation contract

Every physical scalar is a decimal **string**. JSON floating-point numbers are
not admitted at the application's canonical boundary. Seeds, sample counts and
budgets are nonnegative integers. Unknown fields, nonfinite values, ambiguous
band bounds and binary64-indistinguishable grid entries are rejected. The
request includes an explicit reviewed-synthetic origin and
`approval: "approved_for_this_request"`; approval covers the complete request,
including instrument, selected observations, fit domain and noise assumptions.
Edits require a fresh review and a new explicit operation.

Each observation declares `current_A` and its own positive Gaussian standard
deviation `sigma_A`. This is a stochastic noise assumption, **not a hard
allowance**. Multiple rows at one channel remain separate observations. Both
models fit exactly the same selected rows; unselected source rows remain in the
retained request. Only newly generated synthetic data are admitted in version 1.

The instrument is mandatory for computation. Omitting it returns `unsupported`
with `missing_instrument_response`, rather than assuming calibration. Its
`energy_max_eV: null` explicitly means high-pass; a finite upper bound means a
normal-energy band-pass. Every proposed setting is supplied in the feasible grid.

The bounded reference fitter evaluates the approved temperature grid (N points
for isotropic, N² for bi-Maxwellian), profiling density by weighted least squares
and clipping it to the approved bounds at each point. It returns parameter counts,
residuals, chi-square, nominal degrees of freedom, the declared fit-adequacy test,
boundary flags and numerical log-parameter sensitivity/rank diagnostics. Nominal
reduced chi-square is descriptive for this constrained grid fit, not a calibrated
p-value. A finite grid optimum is not a continuous/global optimum. Too few rows
for positive nominal degrees of freedom cannot establish fit adequacy.

A more flexible family can lower the training residual without being correct.
The model list includes the isotropic limit of the bi-Maxwellian. No automatic
model winner or probability of model truth is produced.

## Noise, detection and measurement suggestions

A sweep case supplies an absolute Gaussian standard deviation in A and a
positive dimensionless band multiplier z. It compares the two fixed fitted
prediction vectors using rectangular ±zσ bands; numerical disjointness requires
a strictly positive gap `abs(mu1-mu2) - 2*z*sigma`. Touching bands do not separate.
The displayed quantity is numerical sensitivity, not exact verified separation.

For each generating fitted vector, the Monte Carlo procedure draws independent
Gaussian readings, holds both fitted vectors fixed, and counts acceptance by
only the generating band, only the other band, both, or neither. Negative draws
are retained. Seed, runtime, samples, failures and Wilson 95% intervals for the
sampling frequencies are recorded. Standardized draws are reused across sweep
cases to reduce simulation noise when comparing noise levels; cases are therefore
not independent simulations. This is **conditional prediction detectability**.
It does not refit model families or propagate fitted-parameter uncertainty.
It is not a probability that a model is true, a significance test with a
calibrated familywise error rate, or an exact mathematical guarantee.

Each proposed channel is evaluated separately using the same fixed fitted vectors.
The service ranks the supplied feasible settings by numerical band margin and
suggests one only when that margin is positive. This ranking is conditional on
the supplied grid, area/efficiency, fitted vectors and noise assumptions. It does
not execute or approve a physical experiment. If the noise hides the differences,
the result explicitly says these measurements do not distinguish the selected
models. The original vectors and computed evidence remain unchanged across noise
sweep cases. Changing observations changes the computation and input digest.

## Private API and persistence

All paths below require the existing private browser session or an admitted
backend actor. The browser obtains its private workspace through the existing
same-origin session bootstrap; no token entry, shared owner identity or permissive
CORS is added.

| Method/path under `/api/bean/v1` | Meaning |
| --- | --- |
| GET `/model-comparison-capabilities` | Supported contract, instrument and execution limits |
| POST `/workspaces/{workspace_id}/model-comparisons` | Explicit reviewed request; requires `Idempotency-Key`; returns 201 and immutable record |
| GET `/workspaces/{workspace_id}/model-comparisons` | Private workspace's retained comparison records |
| GET `/workspaces/{workspace_id}/model-comparisons/{id}` | One immutable record |
| GET `/workspaces/{workspace_id}/model-comparisons/{id}/download` | Canonical JSON numerical export with SHA256 response header |

A returned record's `body` is `DB-MODEL-COMPARISON-RESULT-1`; its `id`, workspace,
digest and timestamps are storage metadata. The body includes the entire exact
reviewed request, input digest, source digest, numerical backend, methods, units,
fits, noise cases, settings, failures and limitations. Input spelling/order are
retained and hashed using the application's existing canonical bytes function.
The source digest binds the actual comparison package's Python files; it is
provenance, not a signature or a proof of numerical correctness.

Scientific terminal statuses are `completed`, `unsupported`, `fit_failed` and
`budget_exceeded`. `completed` can still mean no useful distinction. A fit failure
concerns this bounded procedure, never exclusion of every possible model.
Execution failures/timeouts are API errors and do not publish scientific results.
No asynchronous queue or cancellation is claimed. The synchronous operation runs
in a fresh credential-free subprocess, with a 10-second deadline and at most two
active computations per API process. SQLite transactions do not cover computation.
A work cap bounds grid and Monte Carlo work before any partial result is claimed.
Standard deviations below 64 binary64 ulps at the current scale return unsupported,
rather than making noise disappear through rounding.

A repeated identical completed idempotency key returns the retained record.
A changed body with the same key conflicts. Pending/interrupted operations do not
rerun; inspect retained comparison history after reconnecting and make any new
operation an explicit user choice. There is no comparison cancellation or public
operation-status endpoint in this version. Persistence rechecks operation
authority and input identity before publishing. Separate sessions cannot list,
read, reuse or download each other's results.

Downloads use `DB-MODEL-COMPARISON-EXPORT-1` and retain the whole record. They are
**numerical evidence exports**, not Counterdex exact native packets. Reproducing
these computations cannot upgrade an ambiguous result or confer exact verification.
`exact_verification` is always `not_performed`.

## Numerical engine handoff

The production response names `drbean_bounded_grid_reference.v1`, a standard-library
application-local implementation. Counterdex's existing exact kinetics package
and native replay are unchanged. The separate `counterdex-models` PR #56 published
its numerical operations at `b0f795f`; the optional trusted adapter in `registry.py`
is exercised against that exact source without importing it into the service's
scientific authority.

`build_counterdex_registry(request)` returns a registry and an indexed channel
map. It registers both actual physical current predictors with current units A,
parameter units m^-3/eV, and an explicit `channel_index` coordinate. The index maps
to the retained angle and energy settings; it never represents seconds. Invalid
indices, substituted parameter names, density outside approved bounds, and
temperatures outside the approved discrete grid are refused. Caller mutation
cannot change the captured reviewed geometry. This adapter supports bounded
predictions and fixed-vector feasible-grid ranking; it deliberately does not
confer authority for continuous fitting or out-of-grid sensitivity operations.

The engine's `rank_grid` ran successfully on these real adapters. Its normalized
predicted differences match the direct idealized-current calculation and retain
`certification: none`. No detection-censoring threshold is passed: this workflow's
z-band multiplier has a different meaning. To reproduce the compatibility test,
place the qualified PR #56 package source on PYTHONPATH alongside the backend:

```sh
PYTHONPATH=apps/api:/path/to/pr56/packages/counterdex_models \
  .venv/bin/python -m pytest tests/test_model_comparison_registry.py -q
```

Without the separate numerical package, that optional bridge test is explicitly
skipped as unavailable, and the complete reference comparison still works. It
is not reported as an engine integration pass. Per-row uncertainties, discrete
approved temperature grids and dimensionless band thresholds still need matching
engine operations before replacing the production reference coordinator. The
handoff and concrete differences are tracked on PR #56 and PR #57. Left-censoring
thresholds or continuous fitting domains cannot silently replace these assumptions.

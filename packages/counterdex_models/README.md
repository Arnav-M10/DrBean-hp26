# counterdex-models

Bounded numerical comparison of trusted, registered models. Compares models on the same reviewed observations, sweeps parameters, tests noise and detection-threshold assumptions, runs seeded Monte Carlo, and ranks a supplied finite measurement grid.

It is a **separate, zero-dependency distribution** from the exact checker. `counterdex` 0.3.0 is unchanged, does not import this package, and keeps its published artifacts and replay. Nothing here is a Counterdex certificate.

What a result can and cannot say:

- A lower AICc, a higher relative weight or a closer fit is relative support among the registered models under the stated noise assumption. It is **not proof** that a model is true.
- Monte Carlo selection frequencies hold only under the simulated truth, noise and threshold.
- Grid ranking orders only the supplied times for fixed parameter vectors. It is **not** a globally optimal design and **not** certified discrimination.
- Noise standard deviation, detection threshold and hard allowance are different inputs. Hard allowances are refused here (`hard_allowance_not_accepted`); they belong to the exact checker.

## Run the demonstration

```sh
python3.11 packages/counterdex_models/examples/demo.py
```

It uses the public synthetic examples `public.single-exponential` and `public.two-exponential-mixture` on readings drawn from a stated mixture (seeded, not real data), and shows:

1. **Early readings (≤ 4 h):** the mixture fits more closely (χ² 2.05 vs 5.71), yet AICc prefers the single exponential, and the mixture's fast rate sits on its bound. The data really came from the mixture, so preference is not truth.
2. **Grid ranking** of candidate later times between the two early fits: 8 h ranks first (0.92 noise SDs apart); times whose predictions fall below the 0.1 mg/L threshold score 0.
3. **Monte Carlo**, 200 seeded replicates, if the stated mixture were true: the mixture is preferred in 9% of early-only designs and in 100% after adding one 8 h reading.
4. **All readings to 24 h:** the mixture is preferred.
5. **Same readings, other assumptions:** a noisier assay (SD 0.3 + 30%) or a 1.5 mg/L threshold flips the preference to the single exponential, so the result is reported as assumption-dependent.
6. **Sensitivity:** which parameter drives the prediction at each time (A1 early, then k1, A2, and k2 late).

It runs in about 2 seconds with zero provider calls.

## Command line and requests

```sh
cd packages/counterdex_models
python3.11 -m counterdex_models models
python3.11 -m counterdex_models run examples/requests/fit_early.request.json --output /tmp/fit.json
python3.11 -m counterdex_models --registry my_plasma_models:registry run my.request.json
```

Requests (`counterdex-models.request.v1`) are strict JSON: unknown fields are refused, models are named by registered id, and values may be numbers, decimal strings or exact `n/d` strings (rounded to binary64). `analysis` is one of `fit`, `sensitivity`, `scenarios`, `monte_carlo` or `grid_ranking`. See `examples/requests/` for one of each. `examples/build_examples.py` regenerates all of them, and a test checks that the committed files match byte for byte.

Each result carries `certification: "none"`, the inputs it used, the evaluation budget it consumed, an interpretation stating its limits, the runtime (package, Python, fit method, `provider_calls: 0`) and SHA-256 digests of the canonical request and result.

## Adding models

See [docs/INTERFACE.md](docs/INTERFACE.md) and `examples/registry_plugin.py`. Models are Python code registered by the operator; request data can only name them.

## Method and bounds

- **Fitting** (`bounded-lm-halton.v1`): Levenberg–Marquardt on logistic-transformed coordinates, so every trial stays inside the declared bounds, from the bound midpoint plus a fixed Halton sequence. Gaussian likelihood with the stated noise SD; readings below a detection threshold contribute P(y < threshold). Reports parameters, predictions, residuals, standardized residuals, parameter count, parameters at bounds, local curvature standard errors (uncensored data only), χ², AIC, AICc and BIC. The best local optimum found is not guaranteed global.
- **Monte Carlo:** each replicate uses its own Mersenne Twister stream seeded from `(seed, replicate)`, with Box–Muller normals, so runs are reproducible, and a stopped run's completed replicates equal a shorter run's.
- **Bounds:** hard caps in `CAPS` (8 models, 12 parameters, 512 observations, 64 starts, 500 iterations, 1,000 replicates, 256 grid times, 5,000,000 evaluated points, 120 s). The evaluation cap stops work deterministically; the wall clock is only a safety stop and is reported.
- **Determinism:** identical requests give identical results on the same Python and platform math library. Results record the Python version.

## Tests

```sh
python3.11 -m unittest discover -s packages/counterdex_models/tests
```

Besides behaviour, the tests check that the package imports neither `counterdex` nor any network module, and that the top-level `counterdex` source manifest still equals the one recorded in the 0.3.0 fixture bundle.

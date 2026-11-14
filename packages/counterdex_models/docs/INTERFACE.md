# counterdex-models interface (`counterdex-models.interface.v1`)

This is the contract for adding models, for example plasma-specific ones, to
the bounded numerical comparison module. It is published before the analyses
are complete so other agents can build against it. Additions will be
backwards-compatible; a breaking change gets a new interface version.

## What this module is and is not

- It fits, compares and simulates **registered** models with binary64 numerics.
- It is a separate distribution (`counterdex-models`). The exact Counterdex
  checker (`counterdex` 0.3.0) does not import it, and it does not import the
  exact checker. Published 0.3.0 source, artifacts and replay are unchanged.
- A better fit, a lower information criterion, a Monte Carlo selection rate or
  a top-ranked measurement time is **never** proof that a model is true, a
  certified discrimination or a globally optimal design.

## Three inputs that are never interchangeable

| Input | Type | Meaning | Used for |
|---|---|---|---|
| Noise standard deviation | `NoiseModel(absolute_sd, relative_sd)` | Assumed SD of a reading: `sqrt(abs² + (rel·y)²)` | Fit weights, likelihood, simulated readings, scaling predicted differences |
| Detection threshold | `DetectionThreshold(value)` | Readings below it are known only as "below threshold" (left-censored) | Censored likelihood, censoring simulated readings, discounting differences below it |
| Hard allowance | not accepted here | Guaranteed bound on each reading's error | Only the exact Counterdex checker |

Requests that contain an `allowance` field are refused with `hard_allowance_not_accepted`.

## Defining a model

```python
import math
from counterdex_models import Model, Parameter, ModelRegistry, default_registry

def predict(params, times):            # deterministic, side-effect free, no I/O
    a, k = params["A"], params["k"]
    return [a * math.exp(-k * t) for t in times]

MY_MODEL = Model(
    id="plasma.one-compartment-iv",      # 3-80 chars: a-z 0-9 . _ -
    revision=1,                          # bump when the equation or bounds change
    title="One-compartment IV bolus",
    description="C(t) = Dose/V · exp(-CL/V · t)",
    time_unit="h", response_unit="mg/L", # must equal the observations' units exactly
    parameters=(                         # 1-12 parameters, each with hard bounds
        Parameter("A", "mg/L", 1e-3, 1e3, "log", "Initial concentration"),
        Parameter("k", "1/h", 1e-3, 10.0, "log", "Elimination rate"),
    ),
    predict=predict,
    canonicalize=None,                   # optional: map label-switched vectors to one form
)

registry = default_registry()            # public synthetic examples
registry.register(MY_MODEL)              # duplicate ids are refused
```

Rules for `predict(params, times)`:

- `params` is a dict containing every parameter name, each inside its bounds.
- `times` is a list of floats in the model's time unit. Return one float per time.
- Raise `ArithmeticError`/`ValueError` or return a non-finite value to signal a
  numerical failure. It is recorded as a fit failure, never as data.
- Must be deterministic and must not call networks, model providers or files.
  Each call is charged to the request's evaluation budget (one unit per time point).
- `scale="log"` searches the bounds geometrically and needs `lower > 0`.

Registration is code-only. A request names a model id; it cannot supply code or
a module path. The CLI's `--registry module:function` option is for the
operator who runs it, not for request data.

## Observations

```python
Observations(time_unit="h", response_unit="mg/L", provenance="...",
             rows=(Observation(0.5, 4.1), Observation(24.0, None, censored=True)))
```

Values may be JSON numbers, decimal strings or exact `n/d` strings (rounded to
binary64). A reading below a supplied detection threshold is treated as censored;
censored readings require a threshold.

## Analyses (all take a `Budget`, all return plain JSON-ready dicts)

| Function | Purpose |
|---|---|
| `fit_models(models, observations, noise, threshold=None, *, starts, max_iterations, budget)` | Bounded multi-start fit of each model to the same observations: parameters, predictions, residuals, parameter count, failures, AIC/AICc/BIC under the stated noise |
| `sensitivity(model, params, times, *, points, budget)` | One-at-a-time parameter sweeps across each bound range plus local log-sensitivities |
| `compare_scenarios(models, observations, scenarios, ...)` | The same fits under several researcher-specified noise/threshold scenarios, and whether the preferred model changes |
| `monte_carlo(truth_model, truth_params, candidates, times, noise, threshold, *, replicates, seed, ...)` | Seeded simulation of readings, refitting every candidate, selection frequencies and parameter recovery |
| `rank_grid(hypotheses, times, noise, threshold=None)` | Rank a supplied finite set of times by predicted difference between hypotheses relative to the stated noise |

Every result carries `"certification": "none"`, the inputs it used, the
budget it consumed and an `interpretation` sentence that states its limits.

## Bounds

`CAPS` in `interface.py` holds hard ceilings: 8 models per request, 12
parameters, 512 observations, 64 fit starts, 500 iterations, 1,000 Monte
Carlo replicates, 256 grid times, 5,000,000 evaluated points and 120 wall
seconds. The evaluation cap is deterministic; the wall clock is only a safety stop.

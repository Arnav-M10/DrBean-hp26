"""Bounded, deterministic multi-start fitting of registered models.

Method (``bounded-lm-halton.v1``): each parameter is mapped to an unbounded
coordinate (logistic transform of its linear or log bounds), so every trial
vector stays inside the declared bounds. Levenberg-Marquardt with
forward-difference Jacobians minimises the negative log-likelihood under the
stated Gaussian noise, starting from the bound midpoint and a fixed Halton
sequence. Readings below a detection threshold contribute the censored
probability P(y < threshold), not a value.

The best local optimum found is reported. It is not guaranteed to be the
global optimum, and a better fit is not evidence that a model is true.
"""
from __future__ import annotations

import math
from typing import Mapping, Sequence

from .interface import (CAPS, Budget, BudgetExhausted, DetectionThreshold, Model, ModelError, NoiseModel,
                        Observations)

METHOD = "bounded-lm-halton.v1"
_PRIMES = (2, 3, 5, 7, 11, 13, 17, 19, 23, 29, 31, 37)
_LOG_2PI = math.log(2 * math.pi)


# -- small dense linear algebra -------------------------------------------------

def solve(matrix: list[list[float]], rhs: list[float]) -> list[float] | None:
    """Gaussian elimination with partial pivoting; None when singular."""
    n = len(rhs)
    a = [row[:] + [rhs[i]] for i, row in enumerate(matrix)]
    for col in range(n):
        pivot = max(range(col, n), key=lambda r: abs(a[r][col]))
        if not abs(a[pivot][col]) > 1e-300:
            return None
        a[col], a[pivot] = a[pivot], a[col]
        for r in range(col + 1, n):
            f = a[r][col] / a[col][col]
            if f:
                for c in range(col, n + 1):
                    a[r][c] -= f * a[col][c]
    x = [0.0] * n
    for r in range(n - 1, -1, -1):
        x[r] = (a[r][n] - sum(a[r][c] * x[c] for c in range(r + 1, n))) / a[r][r]
    return x if all(math.isfinite(v) for v in x) else None


def inverse(matrix: list[list[float]]) -> list[list[float]] | None:
    n = len(matrix)
    cols = []
    for i in range(n):
        col = solve(matrix, [1.0 if j == i else 0.0 for j in range(n)])
        if col is None:
            return None
        cols.append(col)
    return [[cols[j][i] for j in range(n)] for i in range(n)]


# -- bounded coordinates -------------------------------------------------------

def _sigmoid(u: float) -> float:
    if u >= 0:
        return 1.0 / (1.0 + math.exp(-u))
    e = math.exp(u)
    return e / (1.0 + e)


def _logit(s: float) -> float:
    s = min(max(s, 1e-12), 1 - 1e-12)
    return math.log(s / (1 - s))


class _Space:
    def __init__(self, model: Model, fixed: Mapping[str, float]):
        self.model, self.fixed = model, dict(fixed)
        self.free = [p for p in model.parameters if p.name not in self.fixed]
        for name, value in self.fixed.items():
            p = next((q for q in model.parameters if q.name == name), None)
            if p is None:
                raise ModelError("invalid_input", f"{model.id} has no parameter {name}.", "fixed")
            if not p.lower <= value <= p.upper:
                raise ModelError("invalid_input", f"Fixed {name} is outside its bounds.", "fixed")

    def _ends(self, p):
        return (math.log(p.lower), math.log(p.upper)) if p.scale == "log" else (p.lower, p.upper)

    def to_params(self, u: Sequence[float]) -> dict:
        out = dict(self.fixed)
        for p, ui in zip(self.free, u):
            lo, hi = self._ends(p)
            v = lo + (hi - lo) * _sigmoid(ui)
            out[p.name] = min(max(math.exp(v) if p.scale == "log" else v, p.lower), p.upper)
        return out

    def from_fraction(self, s: Sequence[float]) -> list[float]:
        return [_logit(x) for x in s]

    def from_params(self, params: Mapping[str, float]) -> list[float]:
        u = []
        for p in self.free:
            lo, hi = self._ends(p)
            v = math.log(params[p.name]) if p.scale == "log" else params[p.name]
            u.append(_logit((v - lo) / (hi - lo)))
        return u

    def at_bound(self, params: Mapping[str, float]) -> list[str]:
        hits = []
        for p in self.free:
            lo, hi = self._ends(p)
            v = math.log(params[p.name]) if p.scale == "log" else params[p.name]
            if min(v - lo, hi - v) <= 1e-6 * (hi - lo):
                hits.append(p.name)
        return hits


def halton(index: int, dims: int) -> list[float]:
    point = []
    for d in range(dims):
        base, f, r, i = _PRIMES[d], 1.0, 0.0, index
        while i > 0:
            f /= base
            r += f * (i % base)
            i //= base
        point.append(r)
    return point


# -- likelihood ----------------------------------------------------------------

def _log_normal_cdf(z: float) -> float:
    if z > -30:
        return math.log(max(0.5 * math.erfc(-z / math.sqrt(2)), 1e-300))
    # Asymptotic tail: log Phi(z) ~ -z²/2 - log(-z) - log(sqrt(2π)).
    return -0.5 * z * z - math.log(-z) - 0.5 * _LOG_2PI


class _Objective:
    """Residual vector whose squared norm is -2 log L minus constants."""

    def __init__(self, model: Model, data: Observations, noise: NoiseModel, threshold: DetectionThreshold | None):
        self.model, self.data, self.noise, self.threshold = model, data, noise, threshold
        self.times = [r.time for r in data.rows]
        # Weights are fixed by the observed level so the objective is a stable least-squares problem.
        self.sd = [noise.sd(threshold.value if r.censored else r.value) for r in data.rows]
        self.constant = sum(_LOG_2PI + 2 * math.log(s) for s, r in zip(self.sd, data.rows) if not r.censored)

    def residuals(self, predictions: Sequence[float]) -> list[float]:
        out = []
        for row, pred, sd in zip(self.data.rows, predictions, self.sd):
            if row.censored:
                out.append(math.sqrt(max(0.0, -2.0 * _log_normal_cdf((self.threshold.value - pred) / sd))))
            else:
                out.append((row.value - pred) / sd)
        return out


def _cost(r: Sequence[float]) -> float:
    return math.fsum(x * x for x in r)


def _lm(objective: _Objective, space: _Space, u0: list[float], max_iterations: int, budget: Budget):
    model, times = objective.model, objective.times

    def evaluate(u):
        pred = model.evaluate(space.to_params(u), times, budget)
        if pred is None:
            return None, None
        r = objective.residuals(pred)
        return (r, pred) if all(math.isfinite(x) for x in r) else (None, None)

    u = list(u0)
    r, pred = evaluate(u)
    if r is None:
        return None
    cost, lam, k = _cost(r), 1e-3, len(u)
    iterations, converged = 0, False
    while iterations < max_iterations and k:
        iterations += 1
        jac = []
        for j in range(k):
            h = 1e-6 * (1 + abs(u[j]))
            trial = u[:]
            trial[j] += h
            rj, _ = evaluate(trial)
            if rj is None:
                trial[j] = u[j] - h
                rj, _ = evaluate(trial)
                h = -h
            jac.append([(a - b) / h for a, b in zip(rj, r)] if rj is not None else [0.0] * len(r))
        jtj = [[math.fsum(jac[a][i] * jac[b][i] for i in range(len(r))) for b in range(k)] for a in range(k)]
        jtr = [math.fsum(jac[a][i] * r[i] for i in range(len(r))) for a in range(k)]
        if max(abs(g) for g in jtr) < 1e-10 * (1 + cost):
            converged = True
            break
        improved = False
        while lam < 1e12:
            damped = [[jtj[a][b] + (lam * (jtj[a][a] + 1e-12) if a == b else 0.0) for b in range(k)] for a in range(k)]
            step = solve(damped, [-g for g in jtr])
            if step is None:
                lam *= 10
                continue
            trial = [a + b for a, b in zip(u, step)]
            rt, pt = evaluate(trial)
            if rt is not None and _cost(rt) < cost:
                old = cost
                u, r, pred, cost = trial, rt, pt, _cost(rt)
                lam = max(lam / 10, 1e-12)
                improved = True
                if old - cost <= 1e-12 * (1 + cost):
                    converged = True
                break
            lam *= 10
        if not improved:
            converged = True  # no descent direction left at machine precision
        if converged:
            break
    return {"u": u, "residuals": r, "predictions": pred, "cost": cost, "iterations": iterations, "converged": converged}


def _standard_errors(objective: _Objective, space: _Space, params: dict, budget: Budget) -> dict | None:
    """Local curvature-based SEs in parameter units (uncensored data only)."""
    if not space.free or any(r.censored for r in objective.data.rows):
        return None
    base = objective.model.evaluate(params, objective.times, budget)
    if base is None:
        return None
    jac = []
    for p in space.free:
        h = 1e-6 * max(abs(params[p.name]), 1e-12)
        shifted = dict(params)
        shifted[p.name] = params[p.name] - h if params[p.name] + h > p.upper else params[p.name] + h
        h = shifted[p.name] - params[p.name]
        pred = objective.model.evaluate(shifted, objective.times, budget)
        if pred is None:
            return None
        jac.append([(a - b) / h / sd for a, b, sd in zip(pred, base, objective.sd)])
    k, n = len(jac), len(objective.times)
    if n <= k:
        return None
    info = [[math.fsum(jac[a][i] * jac[b][i] for i in range(n)) for b in range(k)] for a in range(k)]
    cov = inverse(info)
    if cov is None or any(cov[i][i] <= 0 or not math.isfinite(cov[i][i]) for i in range(k)):
        return None
    return {p.name: math.sqrt(cov[i][i]) for i, p in enumerate(space.free)}


def fit_model(model: Model, observations: Observations, noise: NoiseModel, threshold: DetectionThreshold | None = None, *,
              starts: int = 8, max_iterations: int = 200, initial: Mapping[str, float] | None = None,
              fixed: Mapping[str, float] | None = None, budget: Budget | None = None) -> dict:
    """Fit one model. Failures are reported in the result, not raised."""
    if not 1 <= starts <= CAPS["fit_starts"] or not 1 <= max_iterations <= CAPS["fit_iterations"]:
        raise ModelError("invalid_input", f"starts must be 1-{CAPS['fit_starts']} and max_iterations 1-{CAPS['fit_iterations']}.", "fit")
    observations.check_units(model)
    data = observations.apply_threshold(threshold)
    budget = budget or Budget()
    space = _Space(model, fixed or {})
    objective = _Objective(model, data, noise, threshold)
    k, n = len(space.free), len(data.rows)
    seeds = []
    if initial:
        try:
            seeds.append(space.from_params({**space.to_params([0.0] * k), **initial}))
        except (KeyError, ValueError):
            raise ModelError("invalid_input", f"Initial values for {model.id} must be inside the bounds.", "initial") from None
    seeds.append([0.0] * k)
    seeds += [space.from_fraction(halton(i, k)) for i in range(1, starts)]
    seeds = seeds[:starts]
    best, failed_starts, stopped = None, 0, None
    for u0 in seeds:
        try:
            run = _lm(objective, space, u0, max_iterations, budget)
        except BudgetExhausted as stop:
            stopped = stop.reason
            break
        if run is None:
            failed_starts += 1
        elif best is None or run["cost"] < best["cost"]:
            best = run
    base = {"model": model.describe(), "method": METHOD, "parameter_count": k, "observation_count": n,
            "censored_count": sum(r.censored for r in data.rows), "starts_requested": starts,
            "starts_failed": failed_starts, "stopped": stopped, "fixed": dict(fixed or {})}
    if best is None:
        return {**base, "status": "failed",
                "failure": "resource_exhaustion" if stopped else "no_finite_prediction",
                "message": "No start produced finite predictions inside the bounds." if not stopped else "Stopped before any start finished."}
    params = space.to_params(best["u"])
    reported = model.canonicalize(params) if model.canonicalize else params
    minus_two_log_l = best["cost"] + objective.constant
    aicc = None if n - k - 1 <= 0 else minus_two_log_l + 2 * k + 2 * k * (k + 1) / (n - k - 1)
    try:
        se = None if stopped else _standard_errors(objective, space, params, budget)
    except BudgetExhausted as stop:
        se, stopped = None, stop.reason
    if se and model.canonicalize and reported != params:
        se = None  # label-switched; local errors would refer to the other ordering
    rows = []
    for row, pred, res, sd in zip(data.rows, best["predictions"], best["residuals"], objective.sd):
        rows.append({"time": row.time, "observed": row.value, "censored": row.censored, "predicted": pred,
                     "residual": None if row.censored else row.value - pred,
                     "standardized_residual": None if row.censored else res, "noise_sd": sd})
    flags = space.at_bound(params)
    return {**base, "status": "fitted" if best["converged"] else "not_converged", "stopped": stopped,
            "parameters": reported, "local_standard_errors": se, "parameters_at_bounds": flags,
            "iterations": best["iterations"], "rows": rows,
            "chi_square": best["cost"], "minus_two_log_likelihood": minus_two_log_l,
            "reduced_chi_square": best["cost"] / (n - k) if n > k else None,
            "aic": minus_two_log_l + 2 * k, "aicc": aicc, "bic": minus_two_log_l + k * math.log(n)}


def rank_fits(fits: list[dict]) -> list[dict]:
    """Order successful fits by AICc (AIC when AICc is undefined for any model).

    Weights are relative support among these models under the stated noise
    assumption only; they are not probabilities that a model is true.
    """
    usable = [f for f in fits if f["status"] in ("fitted", "not_converged")]
    if not usable:
        return []
    criterion = "aicc" if all(f["aicc"] is not None for f in usable) else "aic"
    ordered = sorted(usable, key=lambda f: (f[criterion], f["parameter_count"], f["model"]["id"]))
    best = ordered[0][criterion]
    raw = [math.exp(-0.5 * (f[criterion] - best)) for f in ordered]
    total = math.fsum(raw)
    return [{"rank": i + 1, "model_id": f["model"]["id"], "criterion": criterion, "value": f[criterion],
             "delta": f[criterion] - best, "relative_weight": w / total, "parameter_count": f["parameter_count"],
             "status": f["status"]} for i, (f, w) in enumerate(zip(ordered, raw))]

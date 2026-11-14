# Synthetic Maxwellian comparison: equations and scientific scope

This workflow compares two public, zero-drift electron velocity distributions
through an explicitly idealized synthetic instrument. Its numerical results are
not exact mathematical certificates, real-instrument calibration, or a
probability that either model is true. All examples use newly generated
synthetic measurements.

## Distributions and units

The symmetry axis is the Cartesian z axis. The parameter names `parallel_eV`
and `perpendicular_eV` denote the numerical values of thermal energies k_B T
in electronvolts, not temperatures in kelvin. Write these values as τ_parallel
and τ_perpendicular, with velocity variances

```text
σ_parallel²      = e τ_parallel / m_e
σ_perpendicular² = e τ_perpendicular / m_e

p(v_x, v_y, v_z) =
  exp[-(v_x² + v_y²)/(2 σ_perpendicular²) - v_z²/(2 σ_parallel²)]
  / [(2π)^(3/2) σ_perpendicular² σ_parallel].
```

Here e converts an energy value in eV to joules. The probability density p has
units s³/m³ and integrates to one over all Cartesian velocity space R³. The
number-density distribution f = n p has units s³/m⁶ and integrates to the
number density n in m⁻³. A speed distribution would have a different measure;
the Cartesian PDF must not receive a `4πv²` factor except when explicitly
changing the integration measure to isotropic spherical coordinates.

The parallel second moment is e τ_parallel / m_e. Each perpendicular Cartesian
second moment is e τ_perpendicular / m_e. The mean kinetic energy is
e(τ_parallel + 2 τ_perpendicular)/2. The distributions have zero mean velocity.

Model identities are:

| Model ID | Parameters fitted when density is unknown |
| --- | --- |
| `electron_isotropic_maxwellian.v1` | density_m3, temperature_eV: 2 parameters |
| `electron_gyrotropic_bimaxwellian.v1` | density_m3, parallel_eV, perpendicular_eV: 3 parameters |

The isotropic limit is τ_parallel = τ_perpendicular = temperature_eV. The
bi-Maxwellian is one anisotropic Gaussian population, not a mixture of hot and
cold populations. Its admitted parameter domain includes the isotropic limit;
excluding that limit would artificially change the comparison.

The bi-Maxwellian normalization follows the equation in
[Meyer-Vernet, *Basics of the Solar Wind*, chapter 2, page 81, footnote 19](https://lira.obspm.fr/perso/nicole-meyer/BSW/BSWchap2.pdf).
The isotropic formula is also implemented in
[PlasmaPy's distribution source](https://docs.plasmapy.org/en/stable/_modules/plasmapy/formulary/distribution.html).
PlasmaPy uses the most-probable thermal speed sqrt(2 k_B T / m), which is sqrt(2)
times a Cartesian component's standard deviation. These conventions must not
be interchanged. The API page's Returns paragraph has inconsistent units and
integration bounds; the source formula and its s³/m³ example give the correct
Cartesian interpretation.

## Explicit synthetic response model

The supported instrument is `idealized_normal_energy_planar_collector` with
`full_incident_half_space` acceptance and `electron_current_magnitude` output.
Its area A is in m², scalar efficiency η is dimensionless, and current is in A.
The efficiency and area are supplied constants, not inferred calibration.

The collector normal forms angle θ with the fixed symmetry axis. θ is supplied
in degrees; the first contract admits 0 through 90 degrees. The marginal normal
velocity is a zero-mean Gaussian with

```text
τ_normal = τ_parallel cos²θ + τ_perpendicular sin²θ
σ_normal² = e τ_normal / m_e.
```

The instrument accepts every tangential velocity but only incident normal
velocities v_normal > 0 whose **normal** kinetic energy
m_e v_normal²/(2e) lies in the declared window [E_low, E_high]. This is not a
window on total particle kinetic energy. `energy_max_eV: null` explicitly means
a high-pass response with E_high = infinity. Finite windows require
0 ≤ E_low < E_high; an unspecified instrument does not authorize an assumed
response model.

Integrating the flux, rather than evaluating a distribution curve, gives

```text
|I| = e A η n ∫[sqrt(2e E_low/m_e), sqrt(2e E_high/m_e)]
                    v_normal p_normal(v_normal) dv_normal

    = e A η n sqrt(e τ_normal / (2π m_e))
        [exp(-E_low/τ_normal) - exp(-E_high/τ_normal)].
```

The upper exponential is zero for the high-pass case. The implementation uses
`exp(-E_low/τ_normal) * -expm1(-(E_high-E_low)/τ_normal)` for a finite window to
avoid cancellation in a narrow band. Conventional electron charge current is
negative; this contract consistently reports its positive magnitude.

The units are C × m² × m⁻³ × m/s = A. At E_low = 0 and E_high = infinity the
flux is n sqrt(k_B T_normal/(2πm_e)). For the isotropic case this is n times the
mean particle speed divided by four, as derived in
[MIT 16.55 Lecture 17, equations 19–25](https://ocw.mit.edu/courses/16-55-ionized-gases-fall-2014/69c9b98ec3496da071f8cdd7a1486ff7_MIT16_55F14_Lecture17.pdf).
The oblique anisotropic result above is obtained by Gaussian covariance rotation
and tangential marginalization; it is not a claim from that isotropic reference
about a calibrated instrument.

This response assumes a homogeneous, stationary, nonrelativistic distribution,
zero drift, a fixed planar collecting area, ideal sharp energy transmission,
and a known scalar efficiency. It omits sheath potentials, space charge,
magnetic trajectories, finite angular apertures, transfer functions,
energy-dependent efficiency, collisions near the collector, secondary
emission and electronics. The nonrelativistic model remains an approximation;
the admitted energy/temperature bounds do not turn it into a relativistic
distribution. It must not be described as calibrated to MRX, PPPL, an actual
EEA, or a real Langmuir probe.

## Identifiability and interpretation

At one collector angle, every energy channel depends on the two temperatures
only through τ_normal. Consequently a bi-Maxwellian and an isotropic
Maxwellian at that τ_normal give exactly the same current for every admitted
energy window at that angle. Extra energy thresholds alone do not resolve this
degeneracy. For example, τ_parallel = 4 eV and τ_perpendicular = 16 eV at 37°
are indistinguishable from an isotropic model at
4 cos²(37°) + 16 sin²(37°) eV. Distinct cos²θ settings, such as 0° and 90°, can
expose that same anisotropy under sufficiently small declared noise. Limited
signals, limited energy coverage or large noise can still prevent useful
distinction.

Density, area and efficiency enter only as the product n A η. Fitting them all
independently is unidentifiable. This contract supplies A and η, while fitting
density within researcher-supplied bounds. The bi-Maxwellian has an additional
temperature parameter; its smaller residual on training observations does not
establish that it is correct. Bounded numerical fits must disclose the supplied
grid/domain, parameter count, termination/budget status, residuals and weak
identifiability. A bounded-grid optimum is not a proven global optimum over
continuous parameter space.

Both models must see the same selected observations and their declared
uncertainties. An observational Gaussian standard deviation is not a reviewed
hard allowance and must not be relabeled as one. Parameter perturbation
sensitivity, simulated detection frequencies, parameter uncertainty and exact
verification are different quantities.

Noise simulations must disclose the independent-Gaussian assumption, current
units, standard deviations, RNG/seed, sample count, generating prediction,
statistic, detection threshold, fitting policy and failures. Negative simulated
Gaussian readings are possible and must not be silently clipped. Simulation
frequency uncertainty concerns finite Monte Carlo sampling, not model truth.

A simulation using fixed fitted vectors measures their conditional
detectability. It does not measure discrimination of entire model families;
that stronger question would require a declared refitting procedure for both
families in every replicate. A feasible-grid ranking is conditional on that
grid and its supplied assumptions. Neither Monte Carlo frequency nor successful
reproduction/replay upgrades a numerical or inconclusive conclusion to exact
verification.

## Dependencies, constants and retained verification

The production distribution and current calculations use Python `math` only;
the application wire contract uses its existing pinned Pydantic dependency.
The current backend pins Pydantic 2.13.4 and requires CPython 3.12–3.13.
No provider call or new runtime numerical package is required by these physics
adapters. PlasmaPy was consulted as a reference implementation, not executed
as a validation dependency.

Constants are the SI exact
[elementary charge](https://physics.nist.gov/cuu/Constants/Value/e.html),
e = 1.602176634 × 10⁻¹⁹ C, and the measured 2022 CODATA
[electron mass](https://physics.nist.gov/cgi-bin/cuu/Value?me%7Csearch_for=mass+of+electron),
m_e = 9.1093837139 × 10⁻³¹ kg. The latter is not an exact constant; its
uncertainty is not propagated by this simplified numerical model.

`tests/test_model_comparison_physics.py` checks the actual production code with
standard-library Simpson integration. It integrates the production PDF with
the cylindrical Jacobian, checks normalization and temperature moments,
compares current to an independently written integral of the rotated velocity
distribution, checks narrow bands, verifies the isotropic limit, demonstrates
single-angle non-identifiability, checks current units/area scaling, and rejects
invalid temperatures. The flux integration uses 512 normal and 256 tangential
intervals, truncated at ten times the largest component standard deviation;
its assertion tolerance is relative 2 × 10⁻⁷. These are numerical tests, not
rigorous integration bounds.

Executed in the backend's CPython 3.13 environment:

```sh
python -m pytest tests/test_model_comparison_physics.py -q
python -m ruff check tests/test_model_comparison_physics.py
```

Result: **37 tests passed; Ruff passed**. This is component qualification,
not qualification of a combined browser release or all comparison statistics.

An additional independent, outside-repository calculation used CPython 3.11.17
and NumPy 2.4.6 with 320-point Gauss–Legendre quadrature and twelve-standard-
deviation truncation. Across 64 flux cases, its largest relative discrepancy
from the analytic response was 1.63 × 10⁻¹². Four normalization and four second-
moment checks had maximum errors 4.11 × 10⁻¹⁴; 32 isotropic angle/window cases
and four single-angle degeneracy cases agreed. That scratch calculation checked
the equations independently before production tests were added. NumPy is not
required to run the committed regression suite.

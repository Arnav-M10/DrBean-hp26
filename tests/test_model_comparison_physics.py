"""Independent numerical checks of the synthetic instrument's admitted physics.

The quadratures use only the standard library. They are numerical regressions,
not interval certificates or claims of real-instrument calibration.
"""

import math

import pytest

from bean_api.model_comparison.contract import Channel, Instrument
from bean_api.model_comparison.models import predict_current, velocity_pdf


# Independent SI reference values: NIST CODATA 2022 (charge is exact).
E_CHARGE = 1.602176634e-19
E_MASS = 9.1093837139e-31


def simpson_nodes(lower, upper, intervals):
    assert intervals % 2 == 0
    step = (upper - lower) / intervals
    for index in range(intervals + 1):
        coefficient = 1 if index in (0, intervals) else (4 if index % 2 else 2)
        yield lower + index * step, coefficient * step / 3


def collector(area="0.000001", efficiency="0.7"):
    return Instrument(
        kind="idealized_normal_energy_planar_collector",
        acceptance="full_incident_half_space",
        current_convention="electron_current_magnitude",
        area_m2=area,
        efficiency=efficiency,
    )


def channel(angle, lower=0, upper=None):
    return Channel(
        id="quadrature", angle_deg=str(angle), energy_min_eV=str(lower),
        energy_max_eV=None if upper is None else str(upper),
    )


@pytest.mark.parametrize("parallel,perpendicular", [(0.1, 0.1), (4, 16), (80, 10)])
def test_pdf_density_normalization_and_temperature_moments(parallel, perpendicular):
    """Integrate the actual 3D PDF with cylindrical Jacobian 2*pi*r.

    Scaling the integration coordinates avoids dependence on physical velocity
    magnitude. The radial and parallel cutoffs are nine standard deviations.
    Perpendicular x/y moments each equal half the radial second moment.
    """
    parallel_sigma = math.sqrt(E_CHARGE * parallel / E_MASS)
    perpendicular_sigma = math.sqrt(E_CHARGE * perpendicular / E_MASS)
    norm = parallel_moment = perpendicular_moment = 0.0
    for radial, radial_weight in simpson_nodes(0, 9, 256):
        for axial, axial_weight in simpson_nodes(-9, 9, 128):
            density = velocity_pdf(
                perpendicular_sigma * radial, 0, parallel_sigma * axial, parallel, perpendicular,
            )
            mass = (density * 2 * math.pi * perpendicular_sigma**2 * parallel_sigma
                    * radial * radial_weight * axial_weight)
            norm += mass
            parallel_moment += mass * axial**2
            perpendicular_moment += mass * radial**2 / 2
    assert norm == pytest.approx(1, abs=1e-7)
    assert parallel_moment == pytest.approx(1, abs=1e-7)
    assert perpendicular_moment == pytest.approx(1, abs=1e-7)


@pytest.mark.parametrize("temperature", [0.1, 16, 1000])
def test_pdf_isotropic_limit_has_maxwellian_si_units(temperature):
    # Cartesian velocity PDF, not a speed PDF: there is no 4*pi*v**2 factor.
    for vx, vy, vz in [(0, 0, 0), (1e5, -2e5, 3e5), (-4e5, 1e5, 0)]:
        energy_joule = E_CHARGE * temperature
        expected = ((E_MASS / (2 * math.pi * energy_joule)) ** 1.5
                    * math.exp(-E_MASS * (vx*vx + vy*vy + vz*vz) / (2 * energy_joule)))
        assert velocity_pdf(vx, vy, vz, temperature, temperature) == pytest.approx(expected, rel=1e-13, abs=0)


def independently_integrated_flux(parallel, perpendicular, angle, lower, upper):
    """Rotate the full Gaussian and integrate normal flux, not Tnormal.

    Velocities are in units sqrt(e/m), so their variances are the numerical
    temperatures in eV. One tangential Gaussian integrates to one; the other is
    explicitly integrated across the rotated anisotropic density. This does not
    use the production normal-temperature formula or production PDF.
    """
    cosine, sine = math.cos(math.radians(angle)), math.sin(math.radians(angle))
    radius = 10 * math.sqrt(max(parallel, perpendicular))
    normal_upper = radius if upper is None else math.sqrt(2 * upper)
    normalizer = 2 * math.pi * math.sqrt(parallel * perpendicular)
    total = 0.0
    tangential_nodes = list(simpson_nodes(-radius, radius, 256))
    for normal, normal_weight in simpson_nodes(math.sqrt(2 * lower), normal_upper, 512):
        for tangential, tangential_weight in tangential_nodes:
            along_axis = normal * cosine - tangential * sine
            across_axis = normal * sine + tangential * cosine
            pdf = math.exp(-0.5 * (along_axis**2 / parallel + across_axis**2 / perpendicular))
            total += normal * pdf * normal_weight * tangential_weight / normalizer
    return total * math.sqrt(E_CHARGE / E_MASS)


@pytest.mark.parametrize("parallel,perpendicular", [(4, 16), (80, 10)])
@pytest.mark.parametrize("angle", [0, 37, 90])
@pytest.mark.parametrize("lower,upper", [(0, None), (3, 11), (15, 15.001)])
def test_collector_current_matches_rotated_velocity_flux_quadrature(parallel, perpendicular, angle, lower, upper):
    instrument = collector()
    parameters = {"density_m3": 3e15, "parallel_eV": parallel, "perpendicular_eV": perpendicular}
    expected = (E_CHARGE * 3e15 * float(instrument.area_m2) * float(instrument.efficiency)
                * independently_integrated_flux(parallel, perpendicular, angle, lower, upper))
    assert predict_current(parameters, channel(angle, lower, upper), instrument) == pytest.approx(expected, rel=2e-7)


@pytest.mark.parametrize("lower,upper", [(0, None), (7, None), (3, 8), (15, 15.001)])
def test_equal_temperatures_make_every_collector_angle_isotropic(lower, upper):
    isotropic = {"density_m3": 2e15, "temperature_eV": 16}
    anisotropic_limit = {"density_m3": 2e15, "parallel_eV": 16, "perpendicular_eV": 16}
    expected = predict_current(isotropic, channel(0, lower, upper), collector())
    for angle in (0, 15, 30, 45, 73, 90):
        actual = predict_current(anisotropic_limit, channel(angle, lower, upper), collector())
        assert actual == pytest.approx(expected, rel=1e-14)


@pytest.mark.parametrize("lower,upper", [(0, None), (7, None), (3, 8), (15, 15.001)])
def test_one_angle_cannot_identify_anisotropy_even_with_energy_channels(lower, upper):
    angle = 37
    theta = math.radians(angle)
    equivalent_temperature = 4 * math.cos(theta)**2 + 16 * math.sin(theta)**2
    isotropic = {"density_m3": 2e15, "temperature_eV": equivalent_temperature}
    anisotropic = {"density_m3": 2e15, "parallel_eV": 4, "perpendicular_eV": 16}
    measurement = channel(angle, lower, upper)
    assert predict_current(anisotropic, measurement, collector()) == pytest.approx(
        predict_current(isotropic, measurement, collector()), rel=1e-14,
    )
    # A second genuinely different orientation can expose this same anisotropy.
    assert not math.isclose(
        predict_current(anisotropic, channel(0), collector()),
        predict_current(isotropic, channel(0), collector()), rel_tol=0.01,
    )


def test_current_units_and_known_geometry_scale_linearly():
    parameters = {"density_m3": 2e15, "temperature_eV": 16}
    base = predict_current(parameters, channel(0), collector(area="0.000001", efficiency="0.5"))
    # One-sided Maxwellian flux is n*mean_speed/4, giving C*m^2*m^-3*m/s = A.
    mean_speed = math.sqrt(8 * E_CHARGE * 16 / (math.pi * E_MASS))
    assert base == pytest.approx(E_CHARGE * 1e-6 * 0.5 * 2e15 * mean_speed / 4, rel=1e-14)
    doubled = predict_current(parameters, channel(0), collector(area="0.000002", efficiency="0.5"))
    assert doubled == pytest.approx(2 * base, rel=1e-14)


@pytest.mark.parametrize("temperature", [0, -1, math.inf, math.nan])
def test_invalid_temperature_is_rejected(temperature):
    with pytest.raises(ValueError):
        velocity_pdf(0, 0, 0, temperature, 16)
    with pytest.raises(ValueError):
        predict_current({"density_m3": 2e15, "temperature_eV": temperature}, channel(0), collector())

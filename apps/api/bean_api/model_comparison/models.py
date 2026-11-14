"""Zero-drift Cartesian PDFs and an explicitly idealized synthetic response.

Temperatures denote k_B*T/e in eV; the instrument filters NORMAL kinetic energy.
This is not a calibrated EEA/Langmuir/PPPL/MRX response model.
"""
from __future__ import annotations

import math

from .contract import Channel, Instrument

ELEMENTARY_CHARGE_C = 1.602176634e-19  # SI exact definition.
ELECTRON_MASS_KG = 9.1093837139e-31  # CODATA 2022, a measured constant.
ISOTROPIC = "electron_isotropic_maxwellian.v1"
ANISOTROPIC = "electron_gyrotropic_bimaxwellian.v1"
MODELS = (ISOTROPIC, ANISOTROPIC)


def velocity_pdf(vx: float, vy: float, vz: float, parallel_eV: float, perpendicular_eV: float) -> float:
    """Probability density in (s/m)^3, normalized on R^3; z is parallel.

    The isotropic Maxwellian is exactly the equal-temperature limit. The
    gyrotropic distribution is a product of Gaussians, never a population mixture.
    """
    if not all(math.isfinite(v) for v in (vx, vy, vz, parallel_eV, perpendicular_eV)):
        raise ValueError("Finite velocities and temperatures required")
    if min(parallel_eV, perpendicular_eV) <= 0:
        raise ValueError("Temperatures must be positive")
    parallel_variance = ELEMENTARY_CHARGE_C * parallel_eV / ELECTRON_MASS_KG
    perpendicular_variance = ELEMENTARY_CHARGE_C * perpendicular_eV / ELECTRON_MASS_KG
    return math.exp(-0.5 * ((vx * vx + vy * vy) / perpendicular_variance + vz * vz / parallel_variance)) / (
        (2 * math.pi) ** 1.5 * perpendicular_variance * math.sqrt(parallel_variance))


def predict_current(parameters: dict[str, float], channel: Channel, instrument: Instrument) -> float:
    """Positive electron-current magnitude in A for the declared planar acceptance.

    Integrates e*A*eta*n*integral(v_n*f_n dv_n) over v_n>0 with normal-energy
    cutoffs. All tangential velocities are accepted. No sheath, drift, magnetic
    transport, secondary emission, angular aperture or transfer calibration.
    """
    n = parameters["density_m3"]
    parallel = parameters.get("temperature_eV", parameters.get("parallel_eV"))
    perpendicular = parameters.get("temperature_eV", parameters.get("perpendicular_eV"))
    if any(value is None or not math.isfinite(value) or value <= 0 for value in (n, parallel, perpendicular)):
        raise ValueError("Positive finite density and temperatures required")
    angle = math.radians(float(channel.angle_deg))
    temperature = parallel * math.cos(angle) ** 2 + perpendicular * math.sin(angle) ** 2
    lower = float(channel.energy_min_eV)
    transmission = math.exp(-lower / temperature)
    if channel.energy_max_eV is not None:
        transmission *= -math.expm1(-(float(channel.energy_max_eV) - lower) / temperature)
    flux = n * math.sqrt(ELEMENTARY_CHARGE_C * temperature / (2 * math.pi * ELECTRON_MASS_KG))
    return ELEMENTARY_CHARGE_C * float(instrument.area_m2) * float(instrument.efficiency) * flux * transmission

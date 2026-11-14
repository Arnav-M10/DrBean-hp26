"""Executable, versioned wire contract. Decimal strings keep the API boundary intact."""
from __future__ import annotations

from decimal import Decimal, InvalidOperation
import math
import re
from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, field_validator, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


def scalar(value: str, low: str, high: str) -> str:
    try:
        if not re.fullmatch(r"[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?", value):
            raise ValueError("A decimal string without whitespace or separators is required")
        number = Decimal(value)
        if len(value) > 40 or not number.is_finite() or not Decimal(low) <= number <= Decimal(high):
            raise ValueError("Decimal scalar outside admitted bounds")
    except (InvalidOperation, TypeError):
        raise ValueError("A finite decimal string is required") from None
    return value


class Review(StrictModel):
    reviewed: Literal[True]
    origin: Literal["synthetic"]
    description: str = Field(min_length=1, max_length=500)

    @field_validator("reviewed", mode="before")
    @classmethod
    def explicit_review(cls, value):
        if value is not True:
            raise ValueError("Review must be the explicit boolean true")
        return value


class Instrument(StrictModel):
    kind: Literal["idealized_normal_energy_planar_collector"]
    acceptance: Literal["full_incident_half_space"]
    current_convention: Literal["electron_current_magnitude"]
    area_m2: str
    efficiency: str

    @field_validator("area_m2")
    @classmethod
    def area(cls, value):
        return scalar(value, "1e-12", "0.1")

    @field_validator("efficiency")
    @classmethod
    def efficiency_bound(cls, value):
        return scalar(value, "1e-6", "1")


class Channel(StrictModel):
    id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,48}$")
    angle_deg: str
    energy_min_eV: str
    energy_max_eV: str | None

    @field_validator("angle_deg")
    @classmethod
    def angle(cls, value):
        return scalar(value, "0", "90")

    @field_validator("energy_min_eV", "energy_max_eV")
    @classmethod
    def energy(cls, value):
        return scalar(value, "0", "10000") if value is not None else None

    @model_validator(mode="after")
    def ordered(self):
        if self.energy_max_eV is not None and float(self.energy_max_eV) <= float(self.energy_min_eV):
            raise ValueError("A band-pass upper energy must exceed its lower energy; null means high-pass")
        return self


class Observation(StrictModel):
    channel_id: str
    current_A: str
    sigma_A: str

    @field_validator("current_A")
    @classmethod
    def current(cls, value):
        return scalar(value, "-1000000", "1000000")

    @field_validator("sigma_A")
    @classmethod
    def sigma(cls, value):
        return scalar(value, "1e-15", "1000")


class FitScope(StrictModel):
    density_min_m3: str
    density_max_m3: str
    temperature_grid_eV: list[str] = Field(min_length=2, max_length=25)
    max_evaluations: int = Field(ge=1, le=1000)
    max_reduced_chi_square: str

    @field_validator("density_min_m3", "density_max_m3")
    @classmethod
    def density(cls, value):
        return scalar(value, "1e8", "1e20")

    @field_validator("max_reduced_chi_square")
    @classmethod
    def fit_threshold(cls, value):
        return scalar(value, "0.01", "1000000")

    @field_validator("temperature_grid_eV")
    @classmethod
    def temperatures(cls, values):
        for value in values:
            scalar(value, "0.1", "1000")
        if len(set(map(float, values))) != len(values):
            raise ValueError("Temperature grid contains equivalent or binary64-indistinguishable values")
        return values

    @model_validator(mode="after")
    def ordered(self):
        if float(self.density_max_m3) <= float(self.density_min_m3):
            raise ValueError("Density bounds must have positive width")
        return self


class NoiseScope(StrictModel):
    kind: Literal["independent_gaussian"]
    sigma_grid_A: list[str] = Field(min_length=1, max_length=8)
    z_thresholds: list[str] = Field(min_length=1, max_length=4)
    seed: int = Field(ge=0, le=4294967295)
    samples: int = Field(ge=32, le=1024)

    @field_validator("sigma_grid_A", "z_thresholds")
    @classmethod
    def finite_values(cls, values, info):
        for value in values:
            scalar(value, "1e-15" if info.field_name == "sigma_grid_A" else "0.1",
                   "1000" if info.field_name == "sigma_grid_A" else "10")
        if len(set(map(float, values))) != len(values):
            raise ValueError("Sweep contains equivalent or binary64-indistinguishable values")
        return values


class ModelComparisonRequest(StrictModel):
    schema_version: Literal["DB-MODEL-COMPARISON-1"]
    approval: Literal["approved_for_this_request"]
    review: Review
    instrument: Instrument | None = None
    channels: list[Channel] = Field(min_length=1, max_length=24)
    observations: list[Observation] = Field(min_length=1, max_length=64)
    selected_channel_ids: list[str] = Field(min_length=1, max_length=24)
    fit: FitScope
    noise: NoiseScope
    feasible_settings: list[Channel] = Field(min_length=1, max_length=16)

    @model_validator(mode="after")
    def bindings(self):
        ids = [item.id for item in self.channels]
        if len(set(ids)) != len(ids) or len(set(self.selected_channel_ids)) != len(self.selected_channel_ids):
            raise ValueError("Channel identities must be unique")
        if not set(self.selected_channel_ids) <= set(ids):
            raise ValueError("Selected channel not declared")
        if any(item.channel_id not in ids for item in self.observations):
            raise ValueError("Observation references an undeclared channel")
        if not set(self.selected_channel_ids) <= {item.channel_id for item in self.observations}:
            raise ValueError("Each selected channel needs a reviewed observation")
        setting_ids = [item.id for item in self.feasible_settings]
        if len(set(setting_ids)) != len(setting_ids):
            raise ValueError("Feasible setting identities must be unique")
        return self


def finite_output(value: str) -> str:
    if not math.isfinite(float(value)):
        raise ValueError("Numerical results must be finite binary64 decimal strings")
    return value


NumberText = Annotated[str, Field(max_length=40, pattern=r"^[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?$"), AfterValidator(finite_output)]
ModelId = Literal["electron_isotropic_maxwellian.v1", "electron_gyrotropic_bimaxwellian.v1"]


class Prediction(StrictModel):
    observation_index: int = Field(ge=0)
    channel_id: str
    observed_A: NumberText
    predicted_A: NumberText
    residual_A: NumberText
    sigma_A: NumberText


class Sensitivity(StrictModel):
    parameter: str
    derivative: Literal["d_current_d_log_parameter"]
    unit: Literal["A"]
    values: list[NumberText]
    relative_step: Literal["0.0001"]


class FitResult(StrictModel):
    model_id: ModelId
    status: Literal["bounded_grid_completed", "no_finite_candidate"]
    parameter_count: int = Field(ge=2, le=3)
    evaluations: int = Field(ge=0)
    parameters: dict[str, NumberText]
    predictions: list[Prediction]
    sensitivity: list[Sensitivity]
    rank_estimate: int = Field(ge=0, le=3)
    rank_deficient: bool
    boundary_limited: bool
    chi_square: NumberText | None
    reduced_chi_square: NumberText | None
    degrees_of_freedom: int | None
    rmse_A: NumberText | None
    adequate_under_declared_threshold: bool


class Frequency(StrictModel):
    count: int = Field(ge=0)
    frequency: NumberText
    wilson_95: list[NumberText] = Field(min_length=2, max_length=2)


class Outcomes(StrictModel):
    generating_band_only: Frequency
    other_band_only: Frequency
    both_bands: Frequency
    neither_band: Frequency


class ConditionalSimulation(StrictModel):
    generating_model_id: ModelId
    samples: int = Field(ge=32, le=1024)
    failures: Literal[0]
    outcomes: Outcomes

    @model_validator(mode="after")
    def totals(self):
        outcomes = [getattr(self.outcomes, key) for key in type(self.outcomes).model_fields]
        if sum(item.count for item in outcomes) != self.samples:
            raise ValueError("Simulation outcome counts must sum to the sample count")
        for item in outcomes:
            low, high = map(float, item.wilson_95)
            frequency = float(item.frequency)
            if not 0 <= low <= frequency + 1e-14 or not frequency - 1e-14 <= high <= 1:
                raise ValueError("Invalid simulation sampling interval")
            if abs(frequency - item.count / self.samples) > 1e-14:
                raise ValueError("Simulation frequency does not match count")
        return self


class SettingPrediction(StrictModel):
    setting: Channel
    predictions_A: dict[ModelId, NumberText]
    absolute_difference_A: NumberText


class SettingComparison(StrictModel):
    setting_id: str
    signal_to_noise: NumberText
    numerical_band_margin_A: NumberText
    conditional_simulations: list[ConditionalSimulation] = Field(min_length=2, max_length=2)


class NoiseCase(StrictModel):
    sigma_A: NumberText
    z_threshold: NumberText
    selected_channel_bands_separated_numerically: bool
    decision: str
    selected_channel_simulations: list[ConditionalSimulation] = Field(min_length=2, max_length=2)
    settings: list[SettingComparison]
    suggested_setting_id: str | None


class Failure(StrictModel):
    code: str
    message: str


class ModelComparisonResult(StrictModel):
    schema_version: Literal["DB-MODEL-COMPARISON-RESULT-1"]
    status: Literal["completed", "unsupported", "fit_failed", "budget_exceeded"]
    request: ModelComparisonRequest
    input_digest: str = Field(pattern=r"^[a-f0-9]{64}$")
    source_digest: str = Field(pattern=r"^[a-f0-9]{64}$")
    numerical_backend: str
    exact_verification: Literal["not_performed"]
    methods: dict[str, str]
    simulation_seed: int
    simulation_samples: int
    model_ids: list[ModelId]
    units: dict[str, str]
    fits: list[FitResult]
    settings: list[SettingPrediction]
    noise_sweep: list[NoiseCase]
    failures: list[Failure]
    limitations: list[str]
    decision: str

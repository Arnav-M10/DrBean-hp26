"""Executable, versioned wire contract. Decimal strings keep the API boundary intact."""
from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


def scalar(value: str, low: str, high: str) -> str:
    try:
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
        if self.energy_max_eV is not None and Decimal(self.energy_max_eV) <= Decimal(self.energy_min_eV):
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
        if len(set(map(Decimal, values))) != len(values):
            raise ValueError("Temperature grid contains equivalent duplicates")
        return values

    @model_validator(mode="after")
    def ordered(self):
        if Decimal(self.density_max_m3) <= Decimal(self.density_min_m3):
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
        if len(set(map(Decimal, values))) != len(values):
            raise ValueError("Sweep contains equivalent duplicate values")
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
    model_ids: list[str]
    units: dict[str, str]
    fits: list[dict]
    settings: list[dict]
    noise_sweep: list[dict]
    failures: list[dict[str, str]]
    limitations: list[str]
    decision: str

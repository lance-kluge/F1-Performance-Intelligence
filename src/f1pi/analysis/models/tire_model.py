"""Presentation-neutral tire degradation inputs and results."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import ClassVar

import pandas as pd

from f1pi.domain.models import SessionMetadata


class DegradationMode(StrEnum):
    """Select whether reported degradation is raw or condition-adjusted."""

    ADJUSTED = "adjusted"
    RAW = "raw"


@dataclass(frozen=True, slots=True)
class TireModelConfig:
    """Eligibility, inference, and validation settings for tire modeling."""

    _minimum_required_compound_stints: ClassVar[int] = 2

    mode: DegradationMode = DegradationMode.ADJUSTED
    confidence_level: float = 0.95
    minimum_stint_laps: int = 3
    minimum_compound_stints: int = 2
    minimum_compound_laps: int = 8
    quick_lap_ratio: float = 1.07
    maximum_validation_folds: int = 5
    curve_points: int = 100

    def __post_init__(self) -> None:
        if not 0 < self.confidence_level < 1:
            raise ValueError("confidence_level must be in (0, 1)")
        if self.minimum_stint_laps < 2:
            raise ValueError("minimum_stint_laps must be at least 2")
        if self.minimum_compound_stints < self._minimum_required_compound_stints:
            raise ValueError(
                f"minimum_compound_stints must be at least {self._minimum_required_compound_stints}"
            )
        if self.minimum_compound_laps < self.minimum_stint_laps:
            raise ValueError("minimum_compound_laps must cover at least one stint")
        if self.quick_lap_ratio < 1:
            raise ValueError("quick_lap_ratio must be at least 1")
        if self.maximum_validation_folds < 2:
            raise ValueError("maximum_validation_folds must be at least 2")
        if self.curve_points < 2:
            raise ValueError("curve_points must be at least 2")


@dataclass(frozen=True, slots=True)
class DriverTireModelConfig(TireModelConfig):
    """Driver-scoped defaults for the shared tire-modeling pipeline."""

    _minimum_required_compound_stints: ClassVar[int] = 1

    minimum_compound_stints: int = 1
    minimum_compound_laps: int = 5


@dataclass(frozen=True, slots=True)
class TireStintSummary:
    stint_id: str
    driver: str
    compound: str
    start_lap: int
    end_lap: int
    start_tire_age: float
    end_tire_age: float
    fresh_tyre: bool | None
    included_laps: int
    excluded_laps: int


@dataclass(frozen=True, slots=True)
class CompoundDegradationEstimate:
    compound: str
    seconds_per_lap: float
    confidence_lower_seconds_per_lap: float
    confidence_upper_seconds_per_lap: float
    observation_count: int
    stint_count: int
    minimum_tire_age: float
    maximum_tire_age: float


@dataclass(frozen=True, slots=True)
class TireModelMetrics:
    scope: str
    observation_count: int
    mae_seconds: float
    rmse_seconds: float
    r_squared: float | None
    baseline_mae_seconds: float


@dataclass(frozen=True, slots=True)
class TireModelValidation:
    fold_count: int
    overall: TireModelMetrics
    per_compound: tuple[TireModelMetrics, ...]


@dataclass(frozen=True, slots=True)
class TireDegradationAnalysis:
    metadata: SessionMetadata
    mode: DegradationMode
    stints: tuple[TireStintSummary, ...]
    estimates: tuple[CompoundDegradationEstimate, ...]
    validation: TireModelValidation
    observations: pd.DataFrame
    curves: pd.DataFrame
    warnings: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class DriverTireDegradationAnalysis:
    """Tire degradation results scoped to one driver within a session."""

    metadata: SessionMetadata
    driver: str
    mode: DegradationMode
    stints: tuple[TireStintSummary, ...]
    estimates: tuple[CompoundDegradationEstimate, ...]
    validation: TireModelValidation | None
    observations: pd.DataFrame
    curves: pd.DataFrame
    warnings: tuple[str, ...]

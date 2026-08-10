"""Public, presentation-neutral records returned by lap comparison."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


@dataclass(frozen=True, slots=True)
class LapSelection:
    """Select a driver's fastest accurate lap or one explicit lap number."""

    driver: str
    lap_number: int | None = None
    accurate_only: bool = True

    def __post_init__(self) -> None:
        driver = self.driver.strip().upper()
        if not driver:
            raise ValueError("driver must not be empty")
        if self.lap_number is not None and self.lap_number < 1:
            raise ValueError("lap_number must be 1 or greater")
        object.__setattr__(self, "driver", driver)

    @classmethod
    def fastest(cls, driver: str) -> LapSelection:
        return cls(driver=driver)

    @classmethod
    def numbered(cls, driver: str, lap_number: int, *, accurate_only: bool = True) -> LapSelection:
        return cls(driver=driver, lap_number=lap_number, accurate_only=accurate_only)


@dataclass(frozen=True, slots=True)
class SynchronizationConfig:
    """Spatial sampling and explanation thresholds for a comparison."""

    sample_count: int = 1000
    corner_window_metres: float = 100.0
    full_throttle_percent: float = 98.0

    def __post_init__(self) -> None:
        if self.sample_count < 100:
            raise ValueError("sample_count must be at least 100")
        if self.corner_window_metres <= 0:
            raise ValueError("corner_window_metres must be positive")
        if not 0 < self.full_throttle_percent <= 100:
            raise ValueError("full_throttle_percent must be in (0, 100]")


@dataclass(frozen=True, slots=True)
class LapSummary:
    driver: str
    lap_number: int
    lap_time_seconds: float
    sector_times_seconds: tuple[float | None, float | None, float | None]
    is_accurate: bool | None


@dataclass(frozen=True, slots=True)
class SectorComparison:
    sector: int
    lap_a_seconds: float | None
    lap_b_seconds: float | None
    delta_seconds: float | None


@dataclass(frozen=True, slots=True)
class CornerComparison:
    number: int
    letter: str
    distance_metres: float
    time_delta_seconds: float
    lap_a_min_speed_kph: float
    lap_b_min_speed_kph: float
    lap_a_full_throttle_metres: float | None
    lap_b_full_throttle_metres: float | None

    @property
    def name(self) -> str:
        return f"Turn {self.number}{self.letter}"


@dataclass(frozen=True, slots=True)
class LapExplanation:
    faster_driver: str | None
    slower_driver: str | None
    largest_loss_sector: int | None
    sector_loss_seconds: float | None
    key_corner: str | None
    corner_loss_seconds: float | None
    minimum_speed_advantage_kph: float | None
    earlier_full_throttle_metres: float | None
    text: str


@dataclass(frozen=True, slots=True)
class LapComparison:
    """Complete chart-ready result for two laps.

    ``delta_seconds`` and the telemetry ``time_delta_seconds`` column use the
    convention ``lap B - lap A``. Positive values mean lap A is ahead.
    """

    lap_a: LapSummary
    lap_b: LapSummary
    delta_seconds: float
    sectors: tuple[SectorComparison, SectorComparison, SectorComparison]
    telemetry: pd.DataFrame
    corners: tuple[CornerComparison, ...]
    explanation: LapExplanation

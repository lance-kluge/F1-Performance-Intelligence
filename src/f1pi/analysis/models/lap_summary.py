"""Selected-lap summary data."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class LapSummary:
    driver: str
    lap_number: int
    lap_time_seconds: float
    sector_times_seconds: tuple[float | None, float | None, float | None]
    is_accurate: bool | None

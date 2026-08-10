"""Sector comparison data."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SectorComparison:
    sector: int
    lap_a_seconds: float | None
    lap_b_seconds: float | None
    delta_seconds: float | None

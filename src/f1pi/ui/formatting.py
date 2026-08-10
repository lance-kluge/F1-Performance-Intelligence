"""Pure display formatting for the Streamlit presentation layer."""

from __future__ import annotations

import math

from f1pi.analysis.models import LapComparison, LapSelection

FASTEST_LAP = "Fastest accurate lap"
SPECIFIC_LAP = "Specific lap"


def lap_selection(driver: str, mode: str, lap_number: int | None = None) -> LapSelection:
    if mode == FASTEST_LAP:
        return LapSelection.fastest(driver)
    if mode == SPECIFIC_LAP and lap_number is not None:
        return LapSelection.numbered(driver, lap_number)
    raise ValueError("a specific lap number is required")


def format_lap_time(seconds: float) -> str:
    minutes = math.floor(seconds / 60)
    remainder = seconds - minutes * 60
    return f"{minutes}:{remainder:06.3f}"


def format_delta(seconds: float | None, *, precision: int = 3) -> str:
    if seconds is None:
        return "Unavailable"
    if abs(seconds) < 0.5 * 10**-precision:
        seconds = 0.0
    return f"{seconds:+.{precision}f}s"


def comparison_outcome(comparison: LapComparison) -> tuple[str, str]:
    if comparison.delta_seconds > 0:
        return comparison.lap_a.driver, f"{comparison.delta_seconds:.3f}s faster"
    if comparison.delta_seconds < 0:
        return comparison.lap_b.driver, f"{abs(comparison.delta_seconds):.3f}s faster"
    return "No advantage", "Identical recorded lap times"

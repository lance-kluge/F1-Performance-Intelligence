"""Driver-named gains for both directions of a signed B-minus-A interval."""

from __future__ import annotations

import math

from f1pi.analysis.models import LapComparison
from f1pi.ui.formatting import MEASUREMENT_DECIMALS


def gain_label(comparison: LapComparison, delta: float) -> str:
    include_lap = comparison.lap_a.driver == comparison.lap_b.driver
    identities = tuple(
        f"{lap.driver} lap {lap.lap_number}" if include_lap else lap.driver
        for lap in (comparison.lap_a, comparison.lap_b)
    )
    winner, loser = identities if delta > 0 else identities[::-1]
    return f"{winner} gained {abs(delta):.{MEASUREMENT_DECIMALS}f}s on {loser}"


def largest_sector_gain(comparison: LapComparison) -> str:
    measured = [
        sector for sector in comparison.sectors
        if sector.delta_seconds is not None and math.isfinite(sector.delta_seconds)
    ]
    if not measured:
        return "Unavailable"
    sector = max(measured, key=lambda sector: abs(sector.delta_seconds or 0))
    delta = sector.delta_seconds or 0
    if abs(delta) < 0.5 * 10**-MEASUREMENT_DECIMALS:
        return "No recorded gain"
    return f"Sector {sector.sector} · {gain_label(comparison, delta)}"

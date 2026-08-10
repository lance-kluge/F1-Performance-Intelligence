"""Complete lap comparison result."""

from dataclasses import dataclass

import pandas as pd

from f1pi.analysis.models.corner_comparison import CornerComparison
from f1pi.analysis.models.lap_explanation import LapExplanation
from f1pi.analysis.models.lap_summary import LapSummary
from f1pi.analysis.models.sector_comparison import SectorComparison
from f1pi.analysis.models.straight_comparison import StraightComparison


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
    straights: tuple[StraightComparison, ...] = ()

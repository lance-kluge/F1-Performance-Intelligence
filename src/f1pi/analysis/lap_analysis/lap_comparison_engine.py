"""Orchestration for a complete, presentation-neutral lap comparison."""

import pandas as pd

from f1pi.analysis.explanation import explain_comparison
from f1pi.analysis.lap_analysis.analysis_session import AnalysisSession
from f1pi.analysis.models import (
    LapComparison,
    LapSelection,
    SectorComparison,
    SynchronizationConfig,
)
from f1pi.analysis.selection import select_lap, summarize_lap
from f1pi.analysis.telemetry import compare_corners, prepare_trace, synchronize_traces
from f1pi.domain.exceptions import DatasetNotAvailableError


class LapComparisonEngine:
    """Compare two selected laps using an immutable session snapshot."""

    def __init__(self, config: SynchronizationConfig | None = None) -> None:
        self._config = config or SynchronizationConfig()

    def compare(
        self,
        session: AnalysisSession,
        lap_a: LapSelection,
        lap_b: LapSelection,
    ) -> LapComparison:
        laps = session.laps()
        selected_a = select_lap(laps, lap_a)
        selected_b = select_lap(laps, lap_b)
        summary_a = summarize_lap(selected_a)
        summary_b = summarize_lap(selected_b)

        trace_a = prepare_trace(
            session.car_telemetry(summary_a.driver),
            session.position(summary_a.driver),
            selected_a,
        )
        trace_b = prepare_trace(
            session.car_telemetry(summary_b.driver),
            session.position(summary_b.driver),
            selected_b,
        )
        telemetry = synchronize_traces(trace_a, trace_b, summary_a, self._config)
        try:
            circuit_corners = session.circuit_corners()
        except DatasetNotAvailableError:
            circuit_corners = pd.DataFrame()
        corners = compare_corners(telemetry, circuit_corners, self._config)
        sectors = _compare_sectors(summary_a.sector_times_seconds, summary_b.sector_times_seconds)

        return LapComparison(
            lap_a=summary_a,
            lap_b=summary_b,
            delta_seconds=summary_b.lap_time_seconds - summary_a.lap_time_seconds,
            sectors=sectors,
            telemetry=telemetry,
            corners=corners,
            explanation=explain_comparison(summary_a, summary_b, sectors, corners),
        )


def _compare_sectors(
    sectors_a: tuple[float | None, float | None, float | None],
    sectors_b: tuple[float | None, float | None, float | None],
) -> tuple[SectorComparison, SectorComparison, SectorComparison]:
    comparisons = tuple(
        SectorComparison(
            sector=index + 1,
            lap_a_seconds=value_a,
            lap_b_seconds=value_b,
            delta_seconds=(None if value_a is None or value_b is None else value_b - value_a),
        )
        for index, (value_a, value_b) in enumerate(zip(sectors_a, sectors_b, strict=True))
    )
    return comparisons[0], comparisons[1], comparisons[2]

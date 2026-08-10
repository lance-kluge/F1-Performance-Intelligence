"""Orchestration for a complete, presentation-neutral lap comparison."""

import pandas as pd

from f1pi.analysis.lap_analysis.analysis_session import AnalysisSession
from f1pi.analysis.models import (
    CornerComparison,
    LapComparison,
    LapSelection,
    PerformanceSectionComparison,
    SectionKind,
    SectorComparison,
    SegmentationConfig,
    StraightComparison,
    SynchronizationConfig,
)
from f1pi.analysis.performance import analyze_performance
from f1pi.analysis.selection import select_lap, summarize_lap
from f1pi.analysis.summary import (
    DeterministicSummaryNarrativeProvider,
    SummaryNarrativeProvider,
    summarize_performance,
)
from f1pi.analysis.telemetry import prepare_trace, synchronize_traces
from f1pi.domain.exceptions import DatasetNotAvailableError


class LapComparisonEngine:
    """Compare two selected laps using an immutable session snapshot."""

    def __init__(
        self,
        config: SynchronizationConfig | None = None,
        *,
        segmentation_config: SegmentationConfig | None = None,
        summary_provider: SummaryNarrativeProvider | None = None,
    ) -> None:
        self._config = config or SynchronizationConfig()
        self._segmentation_config = segmentation_config or SegmentationConfig(
            full_throttle_percent=self._config.full_throttle_percent,
            minimum_straight_metres=self._config.minimum_straight_metres,
        )
        self._summary_provider = summary_provider or DeterministicSummaryNarrativeProvider()

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
        sectors = _compare_sectors(summary_a.sector_times_seconds, summary_b.sector_times_seconds)
        sections, quality = analyze_performance(
            telemetry,
            circuit_corners,
            summary_a,
            summary_b,
            self._segmentation_config,
        )
        summary, explanation = summarize_performance(
            summary_a,
            summary_b,
            sectors,
            sections,
            quality,
            self._segmentation_config,
            self._summary_provider,
        )
        corners = _legacy_corners(sections)
        straights = _legacy_straights(sections, float(telemetry["distance_metres"].iloc[-1]))

        return LapComparison(
            lap_a=summary_a,
            lap_b=summary_b,
            delta_seconds=summary_b.lap_time_seconds - summary_a.lap_time_seconds,
            sectors=sectors,
            telemetry=telemetry,
            corners=corners,
            explanation=explanation,
            straights=straights,
            sections=sections,
            summary=summary,
            quality=quality,
        )


def _legacy_corners(
    sections: tuple[PerformanceSectionComparison, ...],
) -> tuple[CornerComparison, ...]:
    output: list[CornerComparison] = []
    for section in sections:
        if section.kind is not SectionKind.CORNER_COMPLEX:
            continue
        for turn in section.turns:
            if turn.turn.number is None:
                continue
            output.append(
                CornerComparison(
                    number=turn.turn.number,
                    letter=turn.turn.letter,
                    distance_metres=turn.turn.apex_distance_metres,
                    time_delta_seconds=turn.delta_seconds,
                    lap_a_min_speed_kph=turn.lap_a_metrics.minimum_speed_kph,
                    lap_b_min_speed_kph=turn.lap_b_metrics.minimum_speed_kph,
                    lap_a_full_throttle_metres=turn.lap_a_metrics.full_throttle_distance_metres,
                    lap_b_full_throttle_metres=turn.lap_b_metrics.full_throttle_distance_metres,
                )
            )
    return tuple(output)


def _legacy_straights(
    sections: tuple[PerformanceSectionComparison, ...], lap_length: float
) -> tuple[StraightComparison, ...]:
    output: list[StraightComparison] = []
    for section in sections:
        if section.kind is not SectionKind.STRAIGHT:
            continue
        if section.start_turn is None or section.end_turn is None:
            continue
        length = (
            lap_length - section.start_distance_metres + section.end_distance_metres
            if section.wraps_finish_line
            else section.end_distance_metres - section.start_distance_metres
        )
        output.append(
            StraightComparison(
                start_turn=section.start_turn,
                end_turn=section.end_turn,
                start_distance_metres=section.start_distance_metres,
                end_distance_metres=section.end_distance_metres,
                length_metres=length,
                time_delta_seconds=section.delta_seconds,
            )
        )
    return tuple(output)


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

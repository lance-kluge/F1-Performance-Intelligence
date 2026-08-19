"""Hybrid corner segmentation and exact lap-time attribution."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from numpy.typing import NDArray

from f1pi.analysis.models import (
    AnalysisQuality,
    Confidence,
    CornerPhaseKind,
    DriverCornerMetrics,
    DriverStraightMetrics,
    LapSummary,
    PerformanceSectionComparison,
    PhaseComparison,
    SectionKind,
    SegmentationConfig,
    SegmentationSource,
    TurnComparison,
    TurnReference,
)


@dataclass(frozen=True, slots=True)
class _TurnRegion:
    turn: TurnReference
    entry: float
    basin_start: float
    apex: float
    basin_end: float
    exit: float


@dataclass(frozen=True, slots=True)
class _CornerComplex:
    turns: tuple[_TurnRegion, ...]
    entry: float
    basin_start: float
    basin_end: float
    exit: float
    wraps_finish_line: bool = False


def analyze_performance(
    telemetry: pd.DataFrame,
    circuit_corners: pd.DataFrame,
    lap_a: LapSummary,
    lap_b: LapSummary,
    config: SegmentationConfig,
) -> tuple[tuple[PerformanceSectionComparison, ...], AnalysisQuality]:
    """Partition a synchronized lap and attribute every interval exactly once."""
    distances = telemetry["distance_metres"].to_numpy(dtype=float)
    consensus = _smoothed_consensus_speed(telemetry, config)
    warnings = _channel_warnings(telemetry)
    available_channels = _available_channels(telemetry)

    turns = _official_turns(telemetry, circuit_corners, consensus)
    if turns:
        source = SegmentationSource.OFFICIAL_AND_TELEMETRY
    else:
        source = SegmentationSource.TELEMETRY_ONLY
        warnings.append("corner_metadata_unavailable")
        turns = _detected_turns(distances, consensus, config)

    regions = _turn_regions(telemetry, turns, consensus, config)
    complexes = _merge_regions(
        regions,
        config.minimum_straight_metres,
        float(distances[-1]),
    )
    if not complexes:
        warnings.append("telemetry_corner_detection_failed")
        sections: tuple[PerformanceSectionComparison, ...] = (
            _unsegmented_lap_section(telemetry, lap_a, lap_b),
        )
    else:
        sections = _build_sections(telemetry, complexes, lap_a, lap_b, config, warnings)

    finish_delta = float(telemetry["time_delta_seconds"].iloc[-1])
    reconciliation_error = abs(sum(section.delta_seconds for section in sections) - finish_delta)
    if reconciliation_error > 1e-9:
        warnings.append("analysis_reconciliation_error")

    if reconciliation_error > 1e-9 or not complexes:
        confidence = Confidence.LOW
    elif source is SegmentationSource.TELEMETRY_ONLY or warnings:
        confidence = Confidence.MEDIUM
    else:
        confidence = Confidence.HIGH
    return sections, AnalysisQuality(
        confidence=confidence,
        segmentation_source=source,
        available_channels=available_channels,
        warnings=tuple(dict.fromkeys(warnings)),
        reconciliation_error_seconds=reconciliation_error,
    )


def _smoothed_consensus_speed(
    telemetry: pd.DataFrame, config: SegmentationConfig
) -> NDArray[np.float64]:
    speed = np.nanmean(
        telemetry[["lap_a_speed_kph", "lap_b_speed_kph"]].to_numpy(dtype=float), axis=1
    )
    distances = telemetry["distance_metres"].to_numpy(dtype=float)
    spacing = max(float(np.nanmedian(np.diff(distances))), 1e-6)
    samples = max(1, round(config.smoothing_window_metres / spacing))
    if samples % 2 == 0:
        samples += 1
    smoothed = pd.Series(speed).rolling(samples, center=True, min_periods=1).median()
    return smoothed.to_numpy(dtype=float)


def _official_turns(
    telemetry: pd.DataFrame,
    corners: pd.DataFrame,
    consensus: NDArray[np.float64],
) -> tuple[TurnReference, ...]:
    required = {"number", "x", "y"}
    if corners.empty or not required.issubset(corners.columns):
        return ()
    track = np.nanmean(
        np.stack(
            (
                telemetry[["lap_a_x", "lap_a_y"]].to_numpy(dtype=float),
                telemetry[["lap_b_x", "lap_b_y"]].to_numpy(dtype=float),
            )
        ),
        axis=0,
    )
    valid_track = ~np.isnan(track).any(axis=1)
    if not valid_track.any():
        return ()
    valid_indices = np.flatnonzero(valid_track)
    projected: list[tuple[pd.Series, int]] = []
    for _, corner in corners.iterrows():
        if pd.isna(corner["number"]) or pd.isna(corner["x"]) or pd.isna(corner["y"]):
            continue
        difference = track[valid_track] - np.array([float(corner["x"]), float(corner["y"])])
        index = int(valid_indices[int(np.argmin(np.square(difference).sum(axis=1)))])
        projected.append((corner, index))
    projected.sort(key=lambda item: item[1])
    if not projected:
        return ()

    output: list[TurnReference] = []
    last = len(consensus) - 1
    for offset, (corner, marker_index) in enumerate(projected):
        previous = projected[offset - 1][1] if offset else 0
        following = projected[offset + 1][1] if offset + 1 < len(projected) else last
        left = max(0, (previous + marker_index) // 2)
        right = min(last, (marker_index + following) // 2)
        local = consensus[left : right + 1]
        local_minimum = float(np.min(local))
        minimum_indices = np.flatnonzero(local <= local_minimum + 1e-9) + left
        apex_index = int(min(minimum_indices, key=lambda index: abs(index - marker_index)))
        letter = (
            "" if "letter" not in corner or pd.isna(corner["letter"]) else str(corner["letter"])
        )
        number = int(corner["number"])
        output.append(
            TurnReference(
                number=number,
                letter=letter,
                label=f"Turn {number}{letter}",
                apex_distance_metres=float(telemetry["distance_metres"].iloc[apex_index]),
                confidence=Confidence.HIGH,
            )
        )
    return tuple(output)


def _detected_turns(
    distances: NDArray[np.float64],
    consensus: NDArray[np.float64],
    config: SegmentationConfig,
) -> tuple[TurnReference, ...]:
    radius = max(2, int(np.searchsorted(distances, config.minimum_straight_metres) - 1))
    candidates: list[int] = []
    for index in range(1, len(consensus) - 1):
        if consensus[index] > consensus[index - 1] or consensus[index] > consensus[index + 1]:
            continue
        left = max(0, index - radius)
        right = min(len(consensus), index + radius + 1)
        left_peak = float(np.max(consensus[left : index + 1]))
        right_peak = float(np.max(consensus[index:right]))
        reference_peak = min(left_peak, right_peak)
        prominence = reference_peak - float(consensus[index])
        required = max(
            config.minimum_corner_prominence_kph,
            reference_peak * config.minimum_corner_prominence_fraction,
        )
        if prominence >= required:
            candidates.append(index)

    selected: list[int] = []
    for candidate in candidates:
        separated = (
            not selected
            or distances[candidate] - distances[selected[-1]]
            >= config.minimum_corner_separation_metres
        )
        if separated:
            selected.append(candidate)
        elif consensus[candidate] < consensus[selected[-1]]:
            selected[-1] = candidate
    return tuple(
        TurnReference(
            number=None,
            letter="",
            label=f"Detected corner {offset:02d}",
            apex_distance_metres=float(distances[index]),
            confidence=Confidence.MEDIUM,
        )
        for offset, index in enumerate(selected, start=1)
    )


def _turn_regions(
    telemetry: pd.DataFrame,
    turns: tuple[TurnReference, ...],
    consensus: NDArray[np.float64],
    config: SegmentationConfig,
) -> tuple[_TurnRegion, ...]:
    if not turns:
        return ()
    distances = telemetry["distance_metres"].to_numpy(dtype=float)
    apex_indices = [int(np.argmin(np.abs(distances - turn.apex_distance_metres))) for turn in turns]
    output: list[_TurnRegion] = []
    for offset, (turn, apex_index) in enumerate(zip(turns, apex_indices, strict=True)):
        left = 0 if offset == 0 else (apex_indices[offset - 1] + apex_index) // 2
        right = (
            len(distances) - 1
            if offset + 1 == len(turns)
            else (apex_index + apex_indices[offset + 1]) // 2
        )
        basin_left, basin_right = _speed_basin(consensus, apex_index, left, right, config)
        fallback_entry = left + int(np.argmax(consensus[left : apex_index + 1]))
        fallback_exit = apex_index + int(np.argmax(consensus[apex_index : right + 1]))
        entries = [
            event
            for side in ("lap_a", "lap_b")
            if (event := _entry_index(telemetry, side, left, apex_index, config)) is not None
        ]
        exits = [
            event
            for side in ("lap_a", "lap_b")
            if (event := _exit_index(telemetry, side, apex_index, right, config)) is not None
        ]
        entry_index = min([basin_left, *entries]) if entries else min(fallback_entry, basin_left)
        exit_index = max([basin_right, *exits]) if exits else max(fallback_exit, basin_right)
        output.append(
            _TurnRegion(
                turn=turn,
                entry=float(distances[entry_index]),
                basin_start=float(distances[basin_left]),
                apex=float(distances[apex_index]),
                basin_end=float(distances[basin_right]),
                exit=float(distances[exit_index]),
            )
        )
    return tuple(output)


def _speed_basin(
    consensus: NDArray[np.float64],
    apex: int,
    left: int,
    right: int,
    config: SegmentationConfig,
) -> tuple[int, int]:
    threshold = float(consensus[apex]) + config.apex_speed_band_kph
    basin_left = apex
    while basin_left > left and consensus[basin_left - 1] <= threshold:
        basin_left -= 1
    basin_right = apex
    while basin_right < right and consensus[basin_right + 1] <= threshold:
        basin_right += 1
    return basin_left, basin_right


def _entry_index(
    telemetry: pd.DataFrame,
    side: str,
    left: int,
    apex: int,
    config: SegmentationConfig,
) -> int | None:
    brake = _numeric_column(telemetry, f"{side}_brake")
    throttle = _numeric_column(telemetry, f"{side}_throttle_percent")
    state = np.zeros(len(telemetry), dtype=bool)
    measured = False
    if not np.isnan(brake).all():
        state |= brake >= 0.5
        measured = True
    if not np.isnan(throttle).all():
        state |= throttle < config.lift_threshold_percent
        measured = True
    if not measured:
        return None
    runs = _sustained_runs(telemetry, state, left, apex, config.sustained_input_metres)
    return None if not runs else runs[-1][0]


def _exit_index(
    telemetry: pd.DataFrame,
    side: str,
    apex: int,
    right: int,
    config: SegmentationConfig,
) -> int | None:
    throttle = _numeric_column(telemetry, f"{side}_throttle_percent")
    if np.isnan(throttle).all():
        return None
    state = throttle >= config.full_throttle_percent
    runs = _sustained_runs(telemetry, state, apex, right, config.sustained_input_metres)
    return None if not runs else runs[0][0]


def _sustained_runs(
    telemetry: pd.DataFrame,
    state: NDArray[np.bool_],
    left: int,
    right: int,
    minimum_metres: float,
) -> list[tuple[int, int]]:
    distances = telemetry["distance_metres"].to_numpy(dtype=float)
    runs: list[tuple[int, int]] = []
    start: int | None = None
    for index in range(left, right + 1):
        if state[index] and start is None:
            start = index
        if start is not None and (not state[index] or index == right):
            end = index if state[index] and index == right else index - 1
            if distances[end] - distances[start] >= minimum_metres:
                runs.append((start, end))
            start = None
    return runs


def _merge_regions(
    regions: tuple[_TurnRegion, ...], minimum_straight_metres: float, lap_length: float
) -> tuple[_CornerComplex, ...]:
    output: list[_CornerComplex] = []
    for region in regions:
        if output and region.entry - output[-1].exit < minimum_straight_metres:
            previous = output[-1]
            output[-1] = _CornerComplex(
                turns=(*previous.turns, region),
                entry=previous.entry,
                basin_start=min(previous.basin_start, region.basin_start),
                basin_end=max(previous.basin_end, region.basin_end),
                exit=max(previous.exit, region.exit),
            )
        else:
            output.append(
                _CornerComplex(
                    turns=(region,),
                    entry=region.entry,
                    basin_start=region.basin_start,
                    basin_end=region.basin_end,
                    exit=region.exit,
                )
            )
    if not output:
        return ()
    wraparound_length = lap_length - output[-1].exit + output[0].entry
    if wraparound_length >= minimum_straight_metres:
        return tuple(output)
    if len(output) == 1:
        only = output[0]
        return (
            _CornerComplex(
                turns=only.turns,
                entry=0.0,
                basin_start=only.basin_start,
                basin_end=only.basin_end,
                exit=lap_length,
            ),
        )
    first = output[0]
    last = output[-1]
    circular = _CornerComplex(
        turns=(*last.turns, *first.turns),
        entry=last.entry,
        basin_start=last.basin_start,
        basin_end=first.basin_end,
        exit=first.exit,
        wraps_finish_line=True,
    )
    return circular, *output[1:-1]


def _build_sections(
    telemetry: pd.DataFrame,
    complexes: tuple[_CornerComplex, ...],
    lap_a: LapSummary,
    lap_b: LapSummary,
    config: SegmentationConfig,
    warnings: list[str],
) -> tuple[PerformanceSectionComparison, ...]:
    sections: list[PerformanceSectionComparison] = []
    if complexes[0].wraps_finish_line:
        circular = complexes[0]
        sections.append(_corner_section(telemetry, circular, lap_a, lap_b, config, warnings))
        previous = circular
        for complex_ in complexes[1:]:
            if complex_.entry > previous.exit:
                sections.append(
                    _straight_section(telemetry, previous, complex_, lap_a, lap_b, wraps=False)
                )
            sections.append(_corner_section(telemetry, complex_, lap_a, lap_b, config, warnings))
            previous = complex_
        if circular.entry > previous.exit:
            sections.append(
                _straight_section(telemetry, previous, circular, lap_a, lap_b, wraps=False)
            )
        return tuple(sections)
    last = complexes[-1]
    first = complexes[0]
    if last.exit < float(telemetry["distance_metres"].iloc[-1]) or first.entry > 0:
        sections.append(_straight_section(telemetry, last, first, lap_a, lap_b, wraps=True))
    for index, complex_ in enumerate(complexes):
        sections.append(_corner_section(telemetry, complex_, lap_a, lap_b, config, warnings))
        if index + 1 < len(complexes):
            following = complexes[index + 1]
            if following.entry > complex_.exit:
                sections.append(
                    _straight_section(telemetry, complex_, following, lap_a, lap_b, wraps=False)
                )
    return tuple(sections)


def _corner_section(
    telemetry: pd.DataFrame,
    complex_: _CornerComplex,
    lap_a: LapSummary,
    lap_b: LapSummary,
    config: SegmentationConfig,
    warnings: list[str],
) -> PerformanceSectionComparison:
    if complex_.wraps_finish_line:
        return _circular_corner_section(
            telemetry, complex_, lap_a, lap_b, config, warnings
        )
    references = tuple(region.turn for region in complex_.turns)
    label = _complex_label(references)
    section_id = _corner_id(references)
    phases: list[PhaseComparison] = []
    phase_bounds = (
        (CornerPhaseKind.ENTRY, complex_.entry, complex_.basin_start),
        (CornerPhaseKind.APEX, complex_.basin_start, complex_.basin_end),
        (CornerPhaseKind.EXIT, complex_.basin_end, complex_.exit),
    )
    for kind, start, end in phase_bounds:
        if end - start <= 1e-6:
            warnings.append(f"corner_phase_unavailable:{section_id}:{kind.value}")
            continue
        delta = _interval_delta(telemetry, start, end)
        phases.append(
            PhaseComparison(
                kind,
                start,
                end,
                delta,
                _advantaged_driver(delta, lap_a, lap_b),
                abs(delta),
            )
        )

    turns: list[TurnComparison] = []
    for index, region in enumerate(complex_.turns):
        start = complex_.entry if index == 0 else (complex_.turns[index - 1].apex + region.apex) / 2
        end = (
            complex_.exit
            if index + 1 == len(complex_.turns)
            else (region.apex + complex_.turns[index + 1].apex) / 2
        )
        turns.append(
            TurnComparison(
                turn=region.turn,
                start_distance_metres=start,
                end_distance_metres=end,
                delta_seconds=_interval_delta(telemetry, start, end),
                lap_a_metrics=_corner_metrics(telemetry, "lap_a", start, end, region.apex, config),
                lap_b_metrics=_corner_metrics(telemetry, "lap_b", start, end, region.apex, config),
            )
        )
    delta = _interval_delta(telemetry, complex_.entry, complex_.exit)
    confidence = _lowest_confidence(tuple(turn.confidence for turn in references))
    return PerformanceSectionComparison(
        section_id=section_id,
        kind=SectionKind.CORNER_COMPLEX,
        label=label,
        start_distance_metres=complex_.entry,
        end_distance_metres=complex_.exit,
        wraps_finish_line=False,
        sector_numbers=_sector_numbers(telemetry, complex_.entry, complex_.exit, False),
        delta_seconds=delta,
        advantaged_driver=_advantaged_driver(delta, lap_a, lap_b),
        magnitude_seconds=abs(delta),
        confidence=confidence,
        turns=tuple(turns),
        phases=tuple(phases),
        lap_a_corner_metrics=_corner_metrics(
            telemetry,
            "lap_a",
            complex_.entry,
            complex_.exit,
            complex_.turns[0].apex,
            config,
            exit_apex=complex_.turns[-1].apex,
        ),
        lap_b_corner_metrics=_corner_metrics(
            telemetry,
            "lap_b",
            complex_.entry,
            complex_.exit,
            complex_.turns[0].apex,
            config,
            exit_apex=complex_.turns[-1].apex,
        ),
    )


def _circular_corner_section(
    telemetry: pd.DataFrame,
    complex_: _CornerComplex,
    lap_a: LapSummary,
    lap_b: LapSummary,
    config: SegmentationConfig,
    warnings: list[str],
) -> PerformanceSectionComparison:
    split = next(
        index
        for index in range(1, len(complex_.turns))
        if complex_.turns[index].apex < complex_.turns[index - 1].apex
    )
    tail_turns = complex_.turns[:split]
    head_turns = complex_.turns[split:]
    lap_length = float(telemetry["distance_metres"].iloc[-1])
    tail = _CornerComplex(
        turns=tail_turns,
        entry=complex_.entry,
        basin_start=min(turn.basin_start for turn in tail_turns),
        basin_end=max(turn.basin_end for turn in tail_turns),
        exit=lap_length,
    )
    head = _CornerComplex(
        turns=head_turns,
        entry=0.0,
        basin_start=min(turn.basin_start for turn in head_turns),
        basin_end=max(turn.basin_end for turn in head_turns),
        exit=complex_.exit,
    )
    tail_section = _corner_section(telemetry, tail, lap_a, lap_b, config, warnings)
    head_section = _corner_section(telemetry, head, lap_a, lap_b, config, warnings)
    references = tuple(turn.turn for turn in complex_.turns)
    delta = _interval_delta(telemetry, complex_.entry, complex_.exit, wraps=True)
    return PerformanceSectionComparison(
        section_id=_corner_id(references),
        kind=SectionKind.CORNER_COMPLEX,
        label=_complex_label(references),
        start_distance_metres=complex_.entry,
        end_distance_metres=complex_.exit,
        wraps_finish_line=True,
        sector_numbers=_sector_numbers(telemetry, complex_.entry, complex_.exit, True),
        delta_seconds=delta,
        advantaged_driver=_advantaged_driver(delta, lap_a, lap_b),
        magnitude_seconds=abs(delta),
        confidence=_lowest_confidence(tuple(turn.confidence for turn in references)),
        turns=(*tail_section.turns, *head_section.turns),
        phases=(*tail_section.phases, *head_section.phases),
        lap_a_corner_metrics=_combine_corner_metrics(
            tail_section.lap_a_corner_metrics,
            head_section.lap_a_corner_metrics,
        ),
        lap_b_corner_metrics=_combine_corner_metrics(
            tail_section.lap_b_corner_metrics,
            head_section.lap_b_corner_metrics,
        ),
    )


def _combine_corner_metrics(
    tail: DriverCornerMetrics | None, head: DriverCornerMetrics | None
) -> DriverCornerMetrics | None:
    if tail is None or head is None:
        return None
    minimum = min((tail, head), key=lambda metrics: metrics.minimum_speed_kph)
    gears = [gear for gear in (tail.minimum_gear, head.minimum_gear) if gear is not None]
    return DriverCornerMetrics(
        entry_speed_kph=tail.entry_speed_kph,
        minimum_speed_kph=minimum.minimum_speed_kph,
        minimum_speed_distance_metres=minimum.minimum_speed_distance_metres,
        exit_speed_kph=head.exit_speed_kph,
        brake_onset_distance_metres=(
            tail.brake_onset_distance_metres
            if tail.brake_onset_distance_metres is not None
            else head.brake_onset_distance_metres
        ),
        throttle_lift_distance_metres=(
            tail.throttle_lift_distance_metres
            if tail.throttle_lift_distance_metres is not None
            else head.throttle_lift_distance_metres
        ),
        throttle_reapplication_distance_metres=head.throttle_reapplication_distance_metres,
        full_throttle_distance_metres=head.full_throttle_distance_metres,
        minimum_gear=min(gears) if gears else None,
    )


def _straight_section(
    telemetry: pd.DataFrame,
    preceding: _CornerComplex,
    following: _CornerComplex,
    lap_a: LapSummary,
    lap_b: LapSummary,
    *,
    wraps: bool,
) -> PerformanceSectionComparison:
    start_turn = preceding.turns[-1].turn.name
    end_turn = following.turns[0].turn.name
    start = preceding.exit
    end = following.entry
    delta = _interval_delta(telemetry, start, end, wraps)
    prefix = "Start/finish straight" if wraps else "Straight"
    return PerformanceSectionComparison(
        section_id=f"straight:{_turn_token(preceding.turns[-1].turn)}-{_turn_token(following.turns[0].turn)}",
        kind=SectionKind.STRAIGHT,
        label=f"{prefix} · {start_turn} → {end_turn}",
        start_distance_metres=start,
        end_distance_metres=end,
        wraps_finish_line=wraps,
        sector_numbers=_sector_numbers(telemetry, start, end, wraps),
        delta_seconds=delta,
        advantaged_driver=_advantaged_driver(delta, lap_a, lap_b),
        magnitude_seconds=abs(delta),
        confidence=_lowest_confidence(
            (preceding.turns[-1].turn.confidence, following.turns[0].turn.confidence)
        ),
        lap_a_straight_metrics=_straight_metrics(telemetry, "lap_a", start, end, wraps),
        lap_b_straight_metrics=_straight_metrics(telemetry, "lap_b", start, end, wraps),
        start_turn=start_turn,
        end_turn=end_turn,
    )


def _unsegmented_lap_section(
    telemetry: pd.DataFrame, lap_a: LapSummary, lap_b: LapSummary
) -> PerformanceSectionComparison:
    start = 0.0
    end = float(telemetry["distance_metres"].iloc[-1])
    delta = _interval_delta(telemetry, start, end)
    return PerformanceSectionComparison(
        section_id="unsegmented:lap",
        kind=SectionKind.UNSEGMENTED,
        label="Lap",
        start_distance_metres=start,
        end_distance_metres=end,
        wraps_finish_line=False,
        sector_numbers=_sector_numbers(telemetry, start, end, False),
        delta_seconds=delta,
        advantaged_driver=_advantaged_driver(delta, lap_a, lap_b),
        magnitude_seconds=abs(delta),
        confidence=Confidence.LOW,
    )


def _corner_metrics(
    telemetry: pd.DataFrame,
    side: str,
    start: float,
    end: float,
    apex: float,
    config: SegmentationConfig,
    *,
    exit_apex: float | None = None,
) -> DriverCornerMetrics:
    distance = telemetry["distance_metres"].to_numpy(dtype=float)
    speed = _numeric_column(telemetry, f"{side}_speed_kph")
    mask = (distance >= start) & (distance <= end)
    indices = np.flatnonzero(mask)
    minimum_index = int(indices[int(np.nanargmin(speed[mask]))])
    apex_index = int(np.argmin(np.abs(distance - apex)))
    exit_apex_index = int(np.argmin(np.abs(distance - (exit_apex or apex))))
    left = int(indices[0])
    right = int(indices[-1])
    brake = _numeric_column(telemetry, f"{side}_brake")
    throttle = _numeric_column(telemetry, f"{side}_throttle_percent")
    gear = _numeric_column(telemetry, f"{side}_gear")
    return DriverCornerMetrics(
        entry_speed_kph=float(np.interp(start, distance, speed)),
        minimum_speed_kph=float(speed[minimum_index]),
        minimum_speed_distance_metres=float(distance[minimum_index]),
        exit_speed_kph=float(np.interp(end, distance, speed)),
        brake_onset_distance_metres=_first_state_distance(
            telemetry, brake >= 0.5, left, apex_index, config.sustained_input_metres
        ),
        throttle_lift_distance_metres=_first_state_distance(
            telemetry,
            throttle < config.lift_threshold_percent,
            left,
            apex_index,
            config.sustained_input_metres,
        ),
        throttle_reapplication_distance_metres=_first_state_transition_distance(
            telemetry,
            throttle >= config.throttle_reapplication_percent,
            exit_apex_index,
            right,
            config.sustained_input_metres,
        ),
        full_throttle_distance_metres=_first_state_distance(
            telemetry,
            throttle >= config.full_throttle_percent,
            exit_apex_index,
            right,
            config.sustained_input_metres,
        ),
        minimum_gear=(None if np.isnan(gear[mask]).all() else int(np.nanmin(gear[mask]))),
    )


def _first_state_distance(
    telemetry: pd.DataFrame,
    state: NDArray[np.bool_],
    left: int,
    right: int,
    minimum_metres: float,
) -> float | None:
    runs = _sustained_runs(telemetry, state, left, right, minimum_metres)
    if not runs:
        return None
    return float(telemetry["distance_metres"].iloc[runs[0][0]])


def _first_state_transition_distance(
    telemetry: pd.DataFrame,
    state: NDArray[np.bool_],
    left: int,
    right: int,
    minimum_metres: float,
) -> float | None:
    runs = _sustained_runs(telemetry, state, left, right, minimum_metres)
    for start, _ in runs:
        if start > 0 and not state[start - 1]:
            return float(telemetry["distance_metres"].iloc[start])
    return None


def _straight_metrics(
    telemetry: pd.DataFrame, side: str, start: float, end: float, wraps: bool
) -> DriverStraightMetrics:
    distance = telemetry["distance_metres"].to_numpy(dtype=float)
    speed = _numeric_column(telemetry, f"{side}_speed_kph")
    mask = (
        (distance >= start) | (distance <= end)
        if wraps
        else (distance >= start) & (distance <= end)
    )
    return DriverStraightMetrics(
        entry_speed_kph=float(np.interp(start, distance, speed)),
        exit_speed_kph=float(np.interp(end, distance, speed)),
        average_speed_kph=float(np.nanmean(speed[mask])),
        maximum_speed_kph=float(np.nanmax(speed[mask])),
    )


def _interval_delta(
    telemetry: pd.DataFrame, start: float, end: float, wraps: bool = False
) -> float:
    distance = telemetry["distance_metres"].to_numpy(dtype=float)
    delta = telemetry["time_delta_seconds"].to_numpy(dtype=float)
    if wraps:
        return float(
            delta[-1]
            - np.interp(start, distance, delta)
            + np.interp(end, distance, delta)
            - delta[0]
        )
    return float(np.interp(end, distance, delta) - np.interp(start, distance, delta))


def _sector_numbers(
    telemetry: pd.DataFrame, start: float, end: float, wraps: bool
) -> tuple[int, ...]:
    distance = telemetry["distance_metres"].to_numpy(dtype=float)
    mask = (
        (distance >= start) | (distance <= end)
        if wraps
        else (distance >= start) & (distance <= end)
    )
    values = telemetry.loc[mask, "sector"].dropna().astype(int).unique()
    return tuple(sorted(int(value) for value in values))


def _advantaged_driver(delta: float, lap_a: LapSummary, lap_b: LapSummary) -> str | None:
    if abs(delta) <= 1e-12:
        return None
    advantaged = lap_a if delta > 0 else lap_b
    if lap_a.driver == lap_b.driver:
        return f"{advantaged.driver} lap {advantaged.lap_number}"
    return advantaged.driver


def _complex_label(turns: tuple[TurnReference, ...]) -> str:
    if len(turns) == 1:
        return turns[0].name
    return f"{turns[0].name}-{turns[-1].name}"


def _corner_id(turns: tuple[TurnReference, ...]) -> str:
    if turns[0].number is None:
        return f"corner:{_turn_token(turns[0])}"
    return "corner:" + "-".join(_turn_token(turn) for turn in turns)


def _turn_token(turn: TurnReference) -> str:
    if turn.number is None:
        return f"detected-{turn.label.rsplit(' ', maxsplit=1)[-1]}"
    return f"t{turn.number}{turn.letter.lower()}"


def _numeric_column(telemetry: pd.DataFrame, name: str) -> NDArray[np.float64]:
    if name not in telemetry:
        return np.full(len(telemetry), np.nan)
    return telemetry[name].to_numpy(dtype=float, na_value=np.nan)


def _lowest_confidence(values: tuple[Confidence, ...]) -> Confidence:
    rank = {Confidence.LOW: 0, Confidence.MEDIUM: 1, Confidence.HIGH: 2}
    return min(values, key=rank.__getitem__, default=Confidence.LOW)


def _available_channels(telemetry: pd.DataFrame) -> tuple[str, ...]:
    output = ["speed", "position", "time_delta"]
    for channel in ("throttle_percent", "brake", "gear"):
        if any(
            column in telemetry and telemetry[column].notna().any()
            for column in (f"lap_a_{channel}", f"lap_b_{channel}")
        ):
            output.append(channel.removesuffix("_percent"))
    return tuple(output)


def _channel_warnings(telemetry: pd.DataFrame) -> list[str]:
    warnings: list[str] = []
    for side in ("lap_a", "lap_b"):
        for channel in ("throttle_percent", "brake", "gear"):
            column = f"{side}_{channel}"
            if column not in telemetry or telemetry[column].isna().all():
                warnings.append(f"{channel.removesuffix('_percent')}_channel_unavailable:{side}")
    return warnings

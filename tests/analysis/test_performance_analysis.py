from __future__ import annotations

from dataclasses import replace

import numpy as np
import pandas as pd
import pytest

from f1pi.analysis.models import (
    AnalysisQuality,
    Confidence,
    FindingKind,
    LapSummary,
    SectionKind,
    SectorComparison,
    SegmentationConfig,
    SegmentationSource,
    SummaryFinding,
)
from f1pi.analysis.performance import analyze_performance
from f1pi.analysis.summary import SummaryNarrativeProvider, summarize_performance


def _lap(driver: str, seconds: float) -> LapSummary:
    return LapSummary(driver, 1, seconds, (30.0, 30.0, seconds - 60.0), True)


def _telemetry() -> pd.DataFrame:
    distance = np.linspace(0.0, 1000.0, 1001)
    speed = (
        265.0
        - 145.0 * np.exp(-np.square((distance - 200.0) / 34.0))
        - 115.0 * np.exp(-np.square((distance - 265.0) / 30.0))
        - 150.0 * np.exp(-np.square((distance - 700.0) / 42.0))
    )
    corner = (distance >= 150.0) & (distance <= 315.0) | (distance >= 640.0) & (distance <= 760.0)
    brake = (distance >= 155.0) & (distance <= 195.0) | (distance >= 650.0) & (distance <= 695.0)
    throttle = np.where(corner, 35.0, 100.0)
    throttle[(distance >= 280.0) & (distance <= 315.0)] = 100.0
    throttle[(distance >= 725.0) & (distance <= 760.0)] = 100.0
    gear = np.clip(np.rint(speed / 35.0), 2, 8)
    return pd.DataFrame(
        {
            "distance_metres": distance,
            "relative_distance": distance / distance[-1],
            "lap_a_speed_kph": speed + np.where(corner, 3.0, 1.0),
            "lap_b_speed_kph": speed - np.where(corner, 3.0, 1.0),
            "lap_a_throttle_percent": throttle,
            "lap_b_throttle_percent": np.where(corner, np.maximum(0, throttle - 5), throttle),
            "lap_a_brake": pd.array(brake, dtype="boolean"),
            "lap_b_brake": pd.array(brake, dtype="boolean"),
            "lap_a_gear": pd.array(gear, dtype="Int64"),
            "lap_b_gear": pd.array(np.maximum(1, gear - 1), dtype="Int64"),
            "lap_a_x": distance,
            "lap_a_y": np.zeros(len(distance)),
            "lap_b_x": distance,
            "lap_b_y": np.zeros(len(distance)),
            "time_delta_seconds": 0.4 * distance / distance[-1],
            "sector": np.select([distance < 333.0, distance < 666.0], [1.0, 2.0], default=3.0),
        }
    )


def _corners() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "number": [3, 1, 2],
            "letter": ["", "", ""],
            "x": [700.0, 200.0, 265.0],
            "y": [0.0, 0.0, 0.0],
        }
    )


def test_official_segmentation_groups_chicane_and_reconciles_every_interval() -> None:
    telemetry = _telemetry()
    sections, quality = analyze_performance(
        telemetry,
        _corners(),
        _lap("NOR", 90.0),
        _lap("VER", 90.4),
        SegmentationConfig(),
    )

    corners = [section for section in sections if section.kind is SectionKind.CORNER_COMPLEX]
    assert corners[0].section_id == "corner:t1-t2"
    assert [turn.turn.number for turn in corners[0].turns] == [1, 2]
    assert corners[1].section_id == "corner:t3"
    assert sections[0].wraps_finish_line
    assert sections[0].label.startswith("Start/finish straight")
    assert sum(section.delta_seconds for section in sections) == pytest.approx(0.4)
    assert sum(
        phase.delta_seconds for corner in corners for phase in corner.phases
    ) == pytest.approx(sum(corner.delta_seconds for corner in corners))
    assert all(
        sum(turn.delta_seconds for turn in corner.turns) == pytest.approx(corner.delta_seconds)
        for corner in corners
    )
    assert corners[0].lap_a_corner_metrics is not None
    assert corners[0].lap_a_corner_metrics.minimum_gear is not None
    assert corners[0].lap_a_corner_metrics.throttle_reapplication_distance_metres is None
    lap_length = float(telemetry["distance_metres"].iloc[-1])
    covered = sum(
        lap_length - section.start_distance_metres + section.end_distance_metres
        if section.wraps_finish_line
        else section.end_distance_metres - section.start_distance_metres
        for section in sections
    )
    assert covered == pytest.approx(lap_length)
    assert quality.confidence is Confidence.HIGH
    assert quality.reconciliation_error_seconds < 1e-12


def test_short_start_finish_interval_merges_into_circular_corner_complex() -> None:
    telemetry = _telemetry()
    distance = telemetry["distance_metres"].to_numpy(dtype=float)
    speed = (
        265.0
        - 150.0 * np.exp(-np.square((distance - 100.0) / 30.0))
        - 150.0 * np.exp(-np.square((distance - 900.0) / 30.0))
    )
    corner = ((distance >= 65.0) & (distance <= 135.0)) | (
        (distance >= 865.0) & (distance <= 935.0)
    )
    throttle = np.where(corner, 35.0, 100.0)
    for side in ("lap_a", "lap_b"):
        telemetry[f"{side}_speed_kph"] = speed
        telemetry[f"{side}_throttle_percent"] = throttle
        telemetry[f"{side}_brake"] = pd.array(np.zeros(len(distance)), dtype="boolean")
    corners = pd.DataFrame(
        {
            "number": [1, 2],
            "letter": ["", ""],
            "x": [100.0, 900.0],
            "y": [0.0, 0.0],
        }
    )

    sections, quality = analyze_performance(
        telemetry,
        corners,
        _lap("NOR", 90.0),
        _lap("VER", 90.4),
        SegmentationConfig(minimum_straight_metres=200.0),
    )

    circular = next(section for section in sections if section.wraps_finish_line)
    assert circular.kind is SectionKind.CORNER_COMPLEX
    assert [turn.turn.number for turn in circular.turns] == [2, 1]
    assert sum(phase.delta_seconds for phase in circular.phases) == pytest.approx(
        circular.delta_seconds
    )
    assert sum(turn.delta_seconds for turn in circular.turns) == pytest.approx(
        circular.delta_seconds
    )
    assert all(not section.wraps_finish_line for section in sections if section is not circular)
    assert all(
        section.end_distance_metres - section.start_distance_metres >= 200.0
        for section in sections
        if section.kind is SectionKind.STRAIGHT
    )
    assert sum(
        (
            1000.0 - section.start_distance_metres + section.end_distance_metres
            if section.wraps_finish_line
            else section.end_distance_metres - section.start_distance_metres
        )
        for section in sections
    ) == pytest.approx(1000.0)
    assert quality.reconciliation_error_seconds < 1e-12


def test_throttle_reapplication_requires_a_rising_threshold_crossing() -> None:
    telemetry = _telemetry()
    telemetry.loc[
        telemetry["distance_metres"].between(250.0, 269.0),
        "lap_a_throttle_percent",
    ] = 0.0

    sections, _ = analyze_performance(
        telemetry,
        _corners(),
        _lap("NOR", 90.0),
        _lap("VER", 90.4),
        SegmentationConfig(),
    )
    corner = next(
        section
        for section in sections
        if section.kind is SectionKind.CORNER_COMPLEX and section.section_id == "corner:t1-t2"
    )

    assert corner.lap_a_corner_metrics is not None
    assert corner.lap_a_corner_metrics.throttle_reapplication_distance_metres == 270.0


def test_segmentation_is_invariant_when_comparison_order_is_reversed() -> None:
    telemetry = _telemetry()
    original, _ = analyze_performance(
        telemetry, _corners(), _lap("NOR", 90.0), _lap("VER", 90.4), SegmentationConfig()
    )
    swapped = telemetry.copy()
    paired = (
        "speed_kph",
        "throttle_percent",
        "brake",
        "gear",
        "x",
        "y",
    )
    for suffix in paired:
        swapped[f"lap_a_{suffix}"] = telemetry[f"lap_b_{suffix}"]
        swapped[f"lap_b_{suffix}"] = telemetry[f"lap_a_{suffix}"]
    swapped["time_delta_seconds"] = -telemetry["time_delta_seconds"]
    reversed_sections, _ = analyze_performance(
        swapped, _corners(), _lap("VER", 90.4), _lap("NOR", 90.0), SegmentationConfig()
    )

    assert [section.section_id for section in reversed_sections] == [
        section.section_id for section in original
    ]
    assert [section.start_distance_metres for section in reversed_sections] == pytest.approx(
        [section.start_distance_metres for section in original]
    )
    assert [section.delta_seconds for section in reversed_sections] == pytest.approx(
        [-section.delta_seconds for section in original]
    )


def test_same_driver_section_advantages_include_lap_numbers() -> None:
    sections, _ = analyze_performance(
        _telemetry(),
        _corners(),
        _lap("NOR", 90.0),
        replace(_lap("NOR", 90.4), lap_number=2),
        SegmentationConfig(),
    )

    assert {
        section.advantaged_driver for section in sections if section.delta_seconds != 0.0
    } == {"NOR lap 1"}
    assert {
        phase.advantaged_driver
        for section in sections
        for phase in section.phases
        if phase.delta_seconds != 0.0
    } == {"NOR lap 1"}


def test_telemetry_only_fallback_has_stable_ids_and_lower_confidence() -> None:
    sections, quality = analyze_performance(
        _telemetry(),
        pd.DataFrame(),
        _lap("NOR", 90.0),
        _lap("VER", 90.4),
        SegmentationConfig(),
    )
    corner_ids = [
        section.section_id for section in sections if section.kind is SectionKind.CORNER_COMPLEX
    ]

    assert corner_ids
    assert corner_ids[0].startswith("corner:detected-")
    assert quality.segmentation_source is SegmentationSource.TELEMETRY_ONLY
    assert quality.confidence is Confidence.MEDIUM
    assert "corner_metadata_unavailable" in quality.warnings


def test_missing_optional_channels_return_none_metrics_and_warnings() -> None:
    telemetry = _telemetry()
    for side in ("lap_a", "lap_b"):
        telemetry[f"{side}_throttle_percent"] = np.nan
        telemetry[f"{side}_brake"] = pd.array([pd.NA] * len(telemetry), dtype="boolean")
        telemetry[f"{side}_gear"] = pd.array([pd.NA] * len(telemetry), dtype="Int64")
    sections, quality = analyze_performance(
        telemetry,
        _corners(),
        _lap("NOR", 90.0),
        _lap("VER", 90.4),
        SegmentationConfig(),
    )
    corner = next(section for section in sections if section.kind is SectionKind.CORNER_COMPLEX)

    assert corner.lap_a_corner_metrics is not None
    assert corner.lap_a_corner_metrics.brake_onset_distance_metres is None
    assert corner.lap_a_corner_metrics.full_throttle_distance_metres is None
    assert corner.lap_a_corner_metrics.minimum_gear is None
    assert "brake_channel_unavailable:lap_a" in quality.warnings
    assert "gear_channel_unavailable:lap_b" in quality.warnings
    assert quality.confidence is Confidence.MEDIUM


class _FakeProvider(SummaryNarrativeProvider):
    def __init__(self) -> None:
        self.finding_count = 0

    def render(
        self,
        headline: str,
        findings: tuple[SummaryFinding, ...],
        quality: AnalysisQuality,
    ) -> str:
        del headline, quality
        self.finding_count = len(findings)
        return "Provider-rendered narrative."


def test_narrative_provider_changes_only_prose() -> None:
    lap_a = _lap("NOR", 90.0)
    lap_b = _lap("VER", 90.4)
    sections, quality = analyze_performance(
        _telemetry(), _corners(), lap_a, lap_b, SegmentationConfig()
    )
    sectors = (
        SectorComparison(1, 30.0, 30.1, 0.1),
        SectorComparison(2, 30.0, 30.1, 0.1),
        SectorComparison(3, 30.0, 30.2, 0.2),
    )
    provider = _FakeProvider()

    summary, explanation = summarize_performance(
        lap_a, lap_b, sectors, sections, quality, SegmentationConfig(), provider
    )

    assert provider.finding_count == len(summary.findings)
    assert summary.findings
    assert summary.narrative == "Provider-rendered narrative."
    assert explanation.text == "Provider-rendered narrative."
    assert summary.headline == "NOR is 0.400 seconds faster than VER."


def test_summary_reports_offsetting_gain_and_ignores_subthreshold_noise() -> None:
    lap_a = _lap("NOR", 90.0)
    lap_b = _lap("VER", 90.4)
    sections, quality = analyze_performance(
        _telemetry(), _corners(), lap_a, lap_b, SegmentationConfig()
    )
    adjusted = tuple(
        replace(
            section,
            delta_seconds=(-0.050 if index == 0 else 0.450 if index == 1 else 0.001),
            magnitude_seconds=(0.050 if index == 0 else 0.450 if index == 1 else 0.001),
        )
        for index, section in enumerate(sections)
    )
    sectors = (
        SectorComparison(1, 30.0, 30.1, 0.1),
        SectorComparison(2, 30.0, 30.1, 0.1),
        SectorComparison(3, 30.0, 30.2, 0.2),
    )

    summary, _ = summarize_performance(
        lap_a,
        lap_b,
        sectors,
        adjusted,
        quality,
        SegmentationConfig(),
        _FakeProvider(),
    )

    assert [finding.kind for finding in summary.findings] == [
        FindingKind.LOSS,
        FindingKind.GAIN,
    ]
    assert all(finding.time_seconds >= 0.010 for finding in summary.findings)


def test_tied_lap_explanation_ranks_local_differences_by_absolute_magnitude() -> None:
    lap_a = _lap("NOR", 90.0)
    lap_b = replace(_lap("NOR", 90.0), lap_number=2)
    sections, quality = analyze_performance(
        _telemetry(), _corners(), lap_a, lap_b, SegmentationConfig()
    )
    negative_corner = next(section for section in sections if section.section_id == "corner:t3")
    assert negative_corner.lap_a_corner_metrics is not None
    assert negative_corner.lap_b_corner_metrics is not None
    adjusted_negative_corner = replace(
        negative_corner,
        delta_seconds=-0.200,
        magnitude_seconds=0.200,
        lap_a_corner_metrics=replace(
            negative_corner.lap_a_corner_metrics,
            minimum_speed_kph=140.0,
            full_throttle_distance_metres=320.0,
        ),
        lap_b_corner_metrics=replace(
            negative_corner.lap_b_corner_metrics,
            minimum_speed_kph=150.0,
            full_throttle_distance_metres=290.0,
        ),
    )
    adjusted = tuple(
        adjusted_negative_corner
        if section.section_id == negative_corner.section_id
        else replace(
            section,
            delta_seconds=(0.100 if section.section_id == "corner:t1-t2" else 0.0),
            magnitude_seconds=(0.100 if section.section_id == "corner:t1-t2" else 0.0),
        )
        for section in sections
    )
    sectors = (
        SectorComparison(1, 30.0, 30.2, 0.2),
        SectorComparison(2, 30.2, 29.9, -0.3),
        SectorComparison(3, 29.8, 29.9, 0.1),
    )

    _, explanation = summarize_performance(
        lap_a,
        lap_b,
        sectors,
        adjusted,
        quality,
        SegmentationConfig(),
        _FakeProvider(),
    )

    assert explanation.largest_loss_sector == 2
    assert explanation.key_corner == negative_corner.label
    assert explanation.minimum_speed_advantage_kph == 10.0
    assert explanation.earlier_full_throttle_metres == 30.0


@pytest.mark.parametrize(
    "options",
    [
        {"smoothing_window_metres": 0},
        {"minimum_corner_prominence_fraction": 0},
        {"throttle_reapplication_percent": 96},
        {"full_throttle_percent": 90},
        {"finding_minimum_seconds": 0},
    ],
)
def test_segmentation_config_rejects_invalid_values(options: dict[str, float]) -> None:
    with pytest.raises(ValueError):
        SegmentationConfig(**options)

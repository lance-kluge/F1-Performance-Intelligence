from __future__ import annotations

import pandas as pd
import pytest

from f1pi.analysis.models import LapComparison, SectorComparison
from f1pi.ui.charts import (
    corner_loss_figure,
    delta_figure,
    dominance_shares,
    inputs_figure,
    normalized_corner_losses,
    normalized_straight_losses,
    sector_figure,
    speed_figure,
    straight_loss_figure,
    track_figure,
)


def test_core_figures_preserve_comparison_contract(comparison: LapComparison) -> None:
    comparison.telemetry.loc[1, "time_delta_seconds"] = 0.1236
    sectors = sector_figure(comparison)
    assert len(sectors.data) == 1
    assert sectors.layout.title.text == "SECTOR ADVANTAGE"
    assert sectors.layout.xaxis.title.text == "Time gained (seconds)"
    assert sectors.layout.xaxis.tickformat == ".3f"
    assert sectors.layout.yaxis.title.text is None
    assert sectors.data[0].text[0] == "NOR gained 0.050s on VER"
    assert "NOR: 30.000s · VER: 30.050s" in sectors.data[0].customdata[0]
    assert not sectors.layout.annotations
    track = track_figure(comparison)
    assert len(track.data) == 5
    assert list(track.data[-1].text) == ["T3", "T9"]
    assert track.layout.hovermode == "closest"
    assert track.data[1].customdata[0].endswith("Local window gain: NOR by 0.010s")
    assert "VER by 0.020s" in track.data[2].customdata[1]
    assert "Sector 2" in track.data[2].customdata[1]
    assert track.data[0].hoverinfo == "skip"
    assert track.data[-1].customdata is None
    speed = speed_figure(comparison)
    assert len(speed.data) == 2
    assert speed.layout.xaxis.title.text == "Lap progress"
    assert speed.layout.xaxis.ticksuffix == "%"
    assert speed.layout.xaxis.hoverformat == ".1f"
    assert speed.data[0].x[1] == 20.0
    assert "Turn" in speed.data[0].customdata[1]
    inputs = inputs_figure(comparison)
    assert len(inputs.data) == 4
    assert inputs.layout.xaxis.title.text == "Lap progress"
    assert inputs.layout.xaxis.ticksuffix == "%"
    delta = delta_figure(comparison)
    assert delta.data[0].x[1] == 20.0
    assert delta.data[0].y[1] == 0.124
    assert delta.data[0].y[-1] == 0.4
    assert delta.layout.xaxis.title.text == "Lap progress"
    assert delta.layout.xaxis.ticksuffix == "%"
    assert delta.layout.xaxis.hoverformat == ".1f"
    assert delta.layout.yaxis.tickformat == ".3f"
    assert "%{x:.1f}% of lap" in delta.data[0].hovertemplate
    corner_loss = corner_loss_figure(comparison)
    assert corner_loss is not None
    assert corner_loss.layout.xaxis.tickformat == ".3f"
    straight_loss = straight_loss_figure(comparison)
    assert straight_loss is not None
    assert straight_loss.layout.xaxis.tickformat == ".3f"
    assert normalized_corner_losses(comparison) == (("Turn 3", 0.08), ("Turn 9", 0.04))
    assert normalized_straight_losses(comparison) == (
        ("Straight · Turn 3 → Turn 9", 0.06),
        ("Start/finish straight · Turn 9 → Turn 3", 0.03),
    )
    assert dominance_shares(comparison) == pytest.approx((66.667, 33.333, 0.0), abs=0.001)


def test_sector_figure_names_both_driver_directions_and_missing_data(
    comparison: LapComparison,
) -> None:
    object.__setattr__(
        comparison,
        "sectors",
        (
            SectorComparison(1, 30.1, 30.0, -0.1),
            SectorComparison(2, 30.0, 30.0, 0.0),
            SectorComparison(3, None, None, None),
        ),
    )

    sectors = sector_figure(comparison)

    assert list(sectors.data[0].text) == [
        "VER gained 0.100s on NOR",
        "No recorded gain",
        "Unavailable",
    ]
    assert list(sectors.data[0].marker.color) == ["#ff4f47", "#aaa7a0", "#aaa7a0"]
    assert "VER: 30.000s" in sectors.data[0].customdata[0]


def test_figures_handle_missing_optional_channels(comparison: LapComparison) -> None:
    comparison.telemetry["lap_a_brake"] = pd.NA
    comparison.telemetry["lap_b_brake"] = pd.NA
    object.__setattr__(comparison, "corners", ())

    assert len(inputs_figure(comparison).data) == 2
    assert len(track_figure(comparison).data) == 4
    assert corner_loss_figure(comparison) is None


def test_corner_losses_follow_the_slower_driver(comparison: LapComparison) -> None:
    object.__setattr__(comparison, "delta_seconds", -0.4)

    assert normalized_corner_losses(comparison) == ()

    object.__setattr__(comparison, "delta_seconds", 0.0)
    assert normalized_corner_losses(comparison)[0] == ("Turn 3", 0.08)
    assert normalized_straight_losses(comparison)[0] == (
        "Straight · Turn 3 → Turn 9",
        0.06,
    )


def test_track_hover_distinguishes_wrapping_section_and_local_gain(comparison) -> None:
    from dataclasses import replace

    from f1pi.analysis.models import Confidence, PerformanceSectionComparison, SectionKind

    section = PerformanceSectionComparison(
        section_id="straight:finish", kind=SectionKind.STRAIGHT,
        label="Start/finish straight", start_distance_metres=800,
        end_distance_metres=200, wraps_finish_line=True, sector_numbers=(3, 1),
        delta_seconds=-0.123, advantaged_driver="VER", magnitude_seconds=.123,
        confidence=Confidence.HIGH,
    )
    comparison = replace(comparison, sections=(section,))
    comparison.telemetry.loc[0, "local_time_delta_seconds"] = 0
    hover = tuple(value for trace in track_figure(comparison).data
                  for value in (trace.customdata or ()))
    assert "Within 0.001s" in hover[0]
    assert "Whole section gain: VER by 0.123s" in hover[0]
    assert "Whole section gain: VER by 0.123s" in hover[-1]
    assert any("40.0% of lap" in value and "Whole section" not in value for value in hover)
    comparison = replace(comparison, lap_b=replace(comparison.lap_b, driver="NOR"))
    assert "NOR lap 8 by 0.123s" in track_figure(comparison).data[1].customdata[0]
    comparison.telemetry.drop(columns=["local_time_delta_seconds"], inplace=True)
    assert "Local window gain: NOR lap 7 by 0.050s" in (
        track_figure(comparison).data[1].customdata[0]
    )

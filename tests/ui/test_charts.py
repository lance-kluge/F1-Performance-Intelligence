from __future__ import annotations

import pandas as pd

from f1pi.analysis.models import LapComparison
from f1pi.ui.charts import (
    corner_loss_figure,
    delta_figure,
    inputs_figure,
    normalized_corner_losses,
    sector_figure,
    speed_figure,
    track_figure,
)


def test_core_figures_preserve_comparison_contract(comparison: LapComparison) -> None:
    comparison.telemetry.loc[1, "distance_metres"] = 200.1236
    comparison.telemetry.loc[1, "time_delta_seconds"] = 0.1236
    sectors = sector_figure(comparison)
    assert len(sectors.data) == 1
    assert sectors.layout.xaxis.title.text == "Seconds"
    assert sectors.layout.xaxis.tickformat == ".3f"
    assert sectors.layout.yaxis.title.text is None
    assert len(track_figure(comparison).data) == 3
    speed = speed_figure(comparison)
    assert len(speed.data) == 2
    assert speed.layout.xaxis.tickformat == ".3f"
    assert speed.data[0].x[1] == 200.124
    inputs = inputs_figure(comparison)
    assert len(inputs.data) == 4
    assert inputs.layout.xaxis.tickformat == ".3f"
    delta = delta_figure(comparison)
    assert delta.data[0].x[1] == 200.124
    assert delta.data[0].y[1] == 0.124
    assert delta.data[0].y[-1] == 0.4
    assert delta.layout.xaxis.tickformat == ".3f"
    assert delta.layout.yaxis.tickformat == ".3f"
    assert "%{x:.3f} m" in delta.data[0].hovertemplate
    corner_loss = corner_loss_figure(comparison)
    assert corner_loss is not None
    assert corner_loss.layout.xaxis.tickformat == ".3f"
    assert normalized_corner_losses(comparison) == (("Turn 3", 0.08), ("Turn 9", 0.04))


def test_figures_handle_missing_optional_channels(comparison: LapComparison) -> None:
    comparison.telemetry["lap_a_brake"] = pd.NA
    comparison.telemetry["lap_b_brake"] = pd.NA
    object.__setattr__(comparison, "corners", ())

    assert len(inputs_figure(comparison).data) == 2
    assert len(track_figure(comparison).data) == 2
    assert corner_loss_figure(comparison) is None


def test_corner_losses_follow_the_slower_driver(comparison: LapComparison) -> None:
    object.__setattr__(comparison, "delta_seconds", -0.4)

    assert normalized_corner_losses(comparison) == ()

    object.__setattr__(comparison, "delta_seconds", 0.0)
    assert normalized_corner_losses(comparison)[0] == ("Turn 3", 0.08)

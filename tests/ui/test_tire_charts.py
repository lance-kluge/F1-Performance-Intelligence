from __future__ import annotations

from dataclasses import replace

import pytest

from f1pi.ui.tire_charts import (
    degradation_curve_figure,
    degradation_rate_figure,
    shared_degradation_curve_ranges,
    validation_figure,
)


def test_tire_figures_preserve_uncertainty_and_validation_contract(tire_analysis_run) -> None:
    analysis = tire_analysis_run.analysis

    rates = degradation_rate_figure(analysis)
    assert rates.layout.title.text == "COMPOUND DEGRADATION RATE"
    assert rates.layout.xaxis.tickformat == "+.3f"
    assert list(rates.data[0].x) == [0.1, 0.2]
    assert list(rates.data[0].error_x.array) == pytest.approx([0.06, 0.22])
    assert list(rates.data[0].error_x.arrayminus) == pytest.approx([0.06, 0.22])
    assert list(rates.data[0].customdata[0]) == ["+0.100", "+0.040", "+0.160", 4, 2]
    assert "%{customdata[0]} s/lap" in rates.data[0].hovertemplate
    assert ":.3f" not in rates.data[0].hovertemplate

    curves = degradation_curve_figure(analysis)
    assert curves.layout.title.text == "RAW LAPS AND REFERENCE-CONDITION TREND"
    assert curves.layout.xaxis.title.text == "Tire age (laps)"
    assert len(curves.data) == 8
    assert sum(trace.fill == "toself" for trace in curves.data) == 4
    assert sum(trace.mode == "markers" for trace in curves.data) == 2
    marker_traces = [trace for trace in curves.data if trace.mode == "markers"]
    trend_traces = [trace for trace in curves.data if trace.mode == "lines"]
    assert all("raw clean laps" in trace.name for trace in marker_traces)
    assert all("raw lap time" in trace.hovertemplate for trace in marker_traces)
    assert all("reference-condition trend" in trace.name for trace in trend_traces)

    validation = validation_figure(analysis)
    assert validation.layout.title.text == "OUT-OF-SAMPLE ERROR"
    assert len(validation.data) == 2
    assert list(validation.data[0].x) == ["Overall", "Medium", "Soft"]
    assert list(validation.data[0].y) == [0.18, 0.16, 0.2]


def test_degradation_rate_figure_rounds_displayed_floats(tire_analysis_run) -> None:
    analysis = tire_analysis_run.analysis
    estimate = replace(
        analysis.estimates[0],
        seconds_per_lap=0.6000000001,
        confidence_lower_seconds_per_lap=0.5000000001,
        confidence_upper_seconds_per_lap=0.7000000001,
    )
    figure = degradation_rate_figure(replace(analysis, estimates=(estimate,)))

    assert list(figure.data[0].x) == [0.6]
    assert list(figure.data[0].error_x.array) == [0.1]
    assert list(figure.data[0].error_x.arrayminus) == [0.1]
    assert list(figure.data[0].customdata[0])[:3] == ["+0.600", "+0.500", "+0.700"]


def test_driver_curve_figures_can_share_identical_axes(tire_analysis_run) -> None:
    first = tire_analysis_run.analysis
    second_observations = first.observations.copy()
    second_observations["tire_age_laps"] += 2
    second_observations["lap_time_seconds"] += 8
    second_curves = first.curves.copy()
    second_curves["tire_age_laps"] += 2
    time_columns = [column for column in second_curves if column.endswith("_seconds")]
    second_curves[time_columns] += 8
    second = replace(first, observations=second_observations, curves=second_curves)

    x_range, y_range = shared_degradation_curve_ranges((first, second))
    first_figure = degradation_curve_figure(first, x_range=x_range, y_range=y_range)
    second_figure = degradation_curve_figure(second, x_range=x_range, y_range=y_range)

    assert tuple(first_figure.layout.xaxis.range) == tuple(second_figure.layout.xaxis.range)
    assert tuple(first_figure.layout.yaxis.range) == tuple(second_figure.layout.yaxis.range)
    assert x_range[0] < 1
    assert x_range[1] > 6
    assert y_range[0] < 89.5
    assert y_range[1] > 99

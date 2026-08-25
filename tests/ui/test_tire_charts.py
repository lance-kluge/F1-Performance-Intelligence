from __future__ import annotations

import pytest

from f1pi.ui.tire_charts import (
    degradation_curve_figure,
    degradation_rate_figure,
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

    curves = degradation_curve_figure(analysis)
    assert curves.layout.title.text == "LAP TIME ACROSS TIRE AGE"
    assert curves.layout.xaxis.title.text == "Tire age (laps)"
    assert len(curves.data) == 8
    assert sum(trace.fill == "toself" for trace in curves.data) == 4
    assert sum(trace.mode == "markers" for trace in curves.data) == 2

    validation = validation_figure(analysis)
    assert validation.layout.title.text == "OUT-OF-SAMPLE ERROR"
    assert len(validation.data) == 2
    assert list(validation.data[0].x) == ["Overall", "Medium", "Soft"]
    assert list(validation.data[0].y) == [0.18, 0.16, 0.2]

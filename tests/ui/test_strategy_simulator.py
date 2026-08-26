from __future__ import annotations

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from f1pi.analysis.models import NeutralizationSource
from f1pi.domain.exceptions import (
    InsufficientStrategyDataError,
    InvalidStrategyError,
    UnsupportedStrategySessionError,
)
from f1pi.ui.errors import user_error
from f1pi.ui.pages import strategy_simulator
from f1pi.ui.components.strategy_simulator.results import _summary_frame
from f1pi.ui.strategy_charts import finish_distribution_figure, position_trace_figure
from f1pi.ui.strategy_formatting import (
    format_gap,
    format_position,
    format_probability,
    format_strategy_time,
    strategy_warning_message,
)
from tests.ui.strategy_test_data import strategy_run, strategy_setup

FIXTURE_APP = Path(__file__).parent / "fixtures" / "strategy_simulator_app.py"


def test_strategy_workflow_loads_race_and_renders_simulation() -> None:
    app = AppTest.from_file(FIXTURE_APP).run()

    assert not app.exception
    assert [item.label for item in app.selectbox[:3]] == [
        "Season",
        "Race weekend",
        "Session",
    ]
    app.button[0].click().run()

    assert not app.exception
    assert app.selectbox(key="f1pi_strategy_driver").value.abbreviation == "NOR"
    assert app.multiselect(key="f1pi_strategy_scenarios").value == [
        "Actual race",
        "Green race",
    ]
    app.button[0].click().run()

    assert not app.exception
    request = app.session_state["fake_strategy_request"]
    assert request.driver == "NOR"
    assert [scenario.source for scenario in request.scenarios] == [
        NeutralizationSource.ACTUAL,
        NeutralizationSource.NONE,
    ]
    assert app.session_state["fake_strategy_config"].iterations == 2000
    markup = " ".join(element.proto.body for element in app.get("html"))
    assert "Simulation ready" in markup
    assert "P3.7" in markup
    assert "-1.245s vs baseline" in markup
    assert len(app.get("plotly_chart")) == 2
    assert len(app.dataframe) == 3
    assert any("small number" in warning.value for warning in app.warning)


def test_strategy_state_is_scoped_to_request_and_config() -> None:
    setup = strategy_setup()
    run = strategy_run()
    request = strategy_simulator.StrategySimulationRequest(
        "NOR",
        7,
        (
            strategy_simulator.StrategyPlan(
                "early", (strategy_simulator.PlannedPitStop(10, "HARD"),)
            ),
        ),
    )
    config = strategy_simulator.StrategySimulationConfig(iterations=500, random_seed=4)
    state = {
        "session_alias": setup.key.alias_id,
        "request": request,
        "config": config,
        "value": run,
    }

    assert strategy_simulator._run_from_state(state, setup.key, request, config) is run
    changed = strategy_simulator.StrategySimulationConfig(iterations=1000, random_seed=4)
    assert strategy_simulator._run_from_state(state, setup.key, request, changed) is None


def test_reserved_strategy_name_is_explained_without_crashing() -> None:
    app = AppTest.from_file(FIXTURE_APP).run()
    app.button[0].click().run()

    app.text_input(key="f1pi_strategy_name_a").set_value("baseline").run()

    assert not app.exception
    assert app.button[0].disabled
    assert any("reserved" in warning.value for warning in app.warning)


@pytest.mark.parametrize(
    "value,expected",
    [
        (0.0004, "+0.000s"),
        (-0.0004, "+0.000s"),
        (1.2345, "+1.234s"),
        (-1.2345, "-1.234s"),
    ],
)
def test_strategy_time_rounding_normalizes_display_zero(value: float, expected: str) -> None:
    assert format_strategy_time(value) == expected


def test_strategy_display_formatting_is_consistent() -> None:
    assert format_probability(0.6849) == "68.5%"
    assert format_probability(1.2) == "100.0%"
    assert format_position(3.749) == "P3.7"
    assert format_gap(-0.1) == "0.000s"
    assert format_gap(float("nan")) == "Lap down"
    assert "Pit-loss uncertainty" in strategy_warning_message(
        "sparse_green_pit_loss_calibration"
    )


def test_baseline_probability_is_shown_as_a_reference() -> None:
    summaries = strategy_run().analysis.summaries

    frame = _summary_frame(summaries)

    assert set(frame.loc[frame["Plan"] == "Baseline", "Better than baseline"]) == {
        "Reference"
    }


def test_median_finish_preserves_half_positions() -> None:
    summary = strategy_run().analysis.summaries[0]
    half_position_summary = type(summary)(
        **{field: getattr(summary, field) for field in summary.__dataclass_fields__}
        | {"median_finish_position": 4.5}
    )

    frame = _summary_frame([half_position_summary])

    assert frame.loc[0, "Median finish"] == "P4.5"


def test_strategy_figures_show_baseline_and_candidates() -> None:
    analysis = strategy_run().analysis

    trace = position_trace_figure(analysis, "actual")
    distribution = finish_distribution_figure(analysis, "actual")

    assert [item.name for item in trace.data if item.showlegend is not False] == [
        "Baseline",
        "Early Stop",
        "Extend Stint",
    ]
    assert trace.layout.yaxis.autorange == "reversed"
    assert [item.name for item in distribution.data] == [
        "Baseline",
        "Early Stop",
        "Extend Stint",
    ]


@pytest.mark.parametrize(
    "error,title",
    [
        (UnsupportedStrategySessionError(), "Race cannot be simulated"),
        (InvalidStrategyError(), "Strategy is not valid"),
        (InsufficientStrategyDataError(), "Not enough race data"),
    ],
)
def test_strategy_errors_are_actionable(error: Exception, title: str) -> None:
    assert user_error(error).title == title

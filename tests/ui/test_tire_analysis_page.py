from __future__ import annotations

import json
import logging
from contextlib import nullcontext
from pathlib import Path
from unittest.mock import Mock

from streamlit.testing.v1 import AppTest

from f1pi.analysis.models import CompoundDegradationEstimate, DegradationMode, TireModelMetrics
from f1pi.domain.models import SessionKey
from f1pi.ui.components.tire_degradation.results import (
    _eligibility_summary,
    _estimate_card,
    _observation_frame,
    _validation_summary,
)
from f1pi.ui.pages import tire_degradation
from f1pi.ui.pages.tire_degradation import TireAnalysisScope

FIXTURE_APP = Path(__file__).parent / "fixtures" / "tire_analysis_app.py"


def test_tire_workflow_runs_adjusted_model_and_renders_results() -> None:
    app = AppTest.from_file(FIXTURE_APP).run()

    assert not app.exception
    assert [item.label for item in app.selectbox[:3]] == [
        "Season",
        "Race weekend",
        "Session",
    ]
    assert app.radio(key="f1pi_tire_mode").value is DegradationMode.ADJUSTED
    assert not any(
        'aria-label="Tire analysis progress"' in element.proto.body
        for element in app.get("html")
    )

    app.button[0].click().run()

    assert not app.exception
    assert app.session_state["fake_tire_mode"] == "adjusted"
    state = app.session_state[tire_degradation.TIRE_ANALYSIS_KEY]
    assert state["session_alias"] == "2026:1:r"
    assert state["mode"] == "adjusted"
    markup = " ".join(element.proto.body for element in app.get("html"))
    assert "Australian Grand Prix" in markup
    assert "Compound trends" in markup
    assert "+0.100 s/lap" in markup
    assert "Direction uncertain" in markup
    assert "Out-of-sample accuracy" in markup
    assert "Lap eligibility" in markup
    assert len(app.get("plotly_chart")) == 3
    assert len(app.dataframe) == 3
    assert any("Rainfall did not vary" in warning.value for warning in app.warning)
    assert not any(
        'aria-label="Tire analysis progress"' in element.proto.body
        for element in app.get("html")
    )


def test_mode_change_clears_previous_tire_analysis() -> None:
    app = AppTest.from_file(FIXTURE_APP).run()
    app.button[0].click().run()

    app.radio(key="f1pi_tire_mode").set_value(DegradationMode.RAW).run()

    assert tire_degradation.TIRE_ANALYSIS_KEY not in app.session_state
    assert len(app.get("plotly_chart")) == 0
    app.button[0].click().run()
    assert app.session_state["fake_tire_mode"] == "raw"


def test_driver_view_compares_two_scoped_models_side_by_side() -> None:
    app = AppTest.from_file(FIXTURE_APP).run()

    app.radio(key="f1pi_tire_scope").set_value(TireAnalysisScope.DRIVERS).run()

    assert [item.label for item in app.selectbox[-2:]] == ["Driver A", "Driver B"]
    assert app.selectbox(key="f1pi_tire_driver_a").value.abbreviation == "NOR"
    assert app.selectbox(key="f1pi_tire_driver_b").value.abbreviation == "VER"

    app.button[0].click().run()

    assert not app.exception
    assert app.session_state["fake_tire_driver_comparison"] == ("NOR", "VER", "adjusted")
    state = app.session_state[tire_degradation.TIRE_ANALYSIS_KEY]
    assert state["scope"] == "drivers"
    assert state["drivers"] == ("NOR", "VER")
    markup = " ".join(element.proto.body for element in app.get("html"))
    assert "NOR" in markup
    assert "VER" in markup
    assert "Driver degradation rates" in markup
    assert "Modeled stint shapes" in markup
    assert "estimated from one stint" in " ".join(item.value for item in app.warning)
    charts = app.get("plotly_chart")
    assert len(charts) == 4
    first_curve = json.loads(charts[2].proto.spec)
    second_curve = json.loads(charts[3].proto.spec)
    assert first_curve["layout"]["xaxis"]["range"] == second_curve["layout"]["xaxis"]["range"]
    assert first_curve["layout"]["yaxis"]["range"] == second_curve["layout"]["yaxis"]["range"]
    assert len(app.dataframe) == 6


def test_driver_state_is_scoped_to_selected_pair() -> None:
    app = AppTest.from_file(FIXTURE_APP).run()
    app.radio(key="f1pi_tire_scope").set_value(TireAnalysisScope.DRIVERS).run()
    app.button[0].click().run()
    state = app.session_state[tire_degradation.TIRE_ANALYSIS_KEY]
    key = SessionKey(2026, 1, "R")

    assert tire_degradation._driver_analysis_from_state(
        state,
        key,
        DegradationMode.ADJUSTED,
        ("NOR", "VER"),
    )
    assert (
        tire_degradation._driver_analysis_from_state(
            state,
            key,
            DegradationMode.ADJUSTED,
            ("VER", "NOR"),
        )
        is None
    )


def test_tire_state_is_scoped_to_session_and_mode(tire_analysis_run) -> None:
    key = SessionKey(2026, 1, "R")
    state = tire_degradation._analysis_state(key, tire_analysis_run)

    assert tire_degradation._analysis_from_state(state, key, DegradationMode.ADJUSTED)
    assert tire_degradation._analysis_from_state(state, key, DegradationMode.RAW) is None
    assert (
        tire_degradation._analysis_from_state(
            state,
            SessionKey(2026, 2, "R"),
            DegradationMode.ADJUSTED,
        )
        is None
    )


def test_tire_error_logs_original_exception(caplog, monkeypatch) -> None:
    rendered_error = Mock()
    monkeypatch.setattr(tire_degradation.st, "error", rendered_error)
    error = RuntimeError("model failed")

    with caplog.at_level(logging.ERROR, logger=tire_degradation.__name__):
        try:
            raise error
        except RuntimeError as caught:
            tire_degradation._render_error(caught)

    record = caplog.records[-1]
    assert record.getMessage() == "Tire degradation operation failed"
    assert record.exc_info is not None
    assert record.exc_info[1] is error
    rendered_error.assert_called_once()


def test_audit_distinguishes_clean_unsupported_compound_laps(tire_analysis_run) -> None:
    observations = tire_analysis_run.analysis.observations.copy()
    observations.loc[0, "fitted_lap_time_seconds"] = float("nan")

    summary = _eligibility_summary(observations)

    support_row = summary.loc[summary["Decision"].eq("Compound below support threshold")].iloc[0]
    assert support_row["Laps"] == 1
    unsupported_lap = _observation_frame(observations).iloc[0]
    assert not bool(unsupported_lap["Included"])
    assert unsupported_lap["Decision"] == "Compound below support threshold"


def test_nonstandard_compound_card_uses_chart_fallback_color() -> None:
    estimate = CompoundDegradationEstimate("C6", 0.1, 0.04, 0.16, 4, 2, 1, 4)

    card = _estimate_card(estimate)

    assert "--compound-color: #ff9e64" in card


def test_analysis_uses_one_honest_message_while_model_is_running(
    tire_analysis_run, monkeypatch
) -> None:
    events: list[object] = []
    status = Mock()
    facade = Mock()
    facade.analyze.side_effect = lambda *_: events.append("analyze") or tire_analysis_run
    monkeypatch.setattr(tire_degradation.st, "session_state", {})
    monkeypatch.setattr(tire_degradation.st, "button", lambda *_, **__: True)
    monkeypatch.setattr(
        tire_degradation.st,
        "status",
        lambda *_, **__: nullcontext(status),
    )
    monkeypatch.setattr(
        tire_degradation.st,
        "write",
        lambda message: events.append(message),
    )
    monkeypatch.setattr(tire_degradation.st, "rerun", Mock())

    tire_degradation._run_or_restore_analysis(
        facade,
        SessionKey(2026, 1, "R"),
        DegradationMode.ADJUSTED,
    )

    assert events == [tire_degradation.ANALYSIS_PROGRESS_DETAIL, "analyze"]
    status.update.assert_called_once_with(
        label="Tire analysis ready",
        state="complete",
        expanded=False,
    )


def test_validation_does_not_claim_a_rounded_zero_improvement() -> None:
    metrics = TireModelMetrics(
        "overall",
        8,
        0.1796,
        0.24,
        0.72,
        0.18,
    )

    message, icon = _validation_summary(metrics)

    assert "same mean absolute error" in message
    assert "improves" not in message
    assert "0.000s" not in message
    assert icon == ":material/info:"

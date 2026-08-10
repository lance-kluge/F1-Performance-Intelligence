from __future__ import annotations

import logging
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

from streamlit.testing.v1 import AppTest

from f1pi.ui.formatting import SPECIFIC_LAP
from f1pi.ui.pages import lap_analysis

FIXTURE_APP = Path(__file__).parent / "fixtures" / "analysis_app.py"


def test_guided_analysis_workflow_uses_specific_lap_and_renders_results() -> None:
    app = AppTest.from_file(FIXTURE_APP).run()

    assert not app.exception
    assert [item.label for item in app.selectbox[:3]] == [
        "Season",
        "Race weekend",
        "Session",
    ]

    app.button[0].click().run()

    assert app.session_state["fake_load_called"] is True
    assert len(app.radio) == 2
    app.radio(key="f1pi_lap_mode_b").set_value(SPECIFIC_LAP).run()
    app.selectbox(key="f1pi_lap_number_b").select(10).run()
    app.button[0].click().run()

    assert not app.exception
    assert app.session_state["fake_comparison_laps"] == (None, 10)
    comparison_state = app.session_state[lap_analysis.COMPARISON_KEY]
    assert comparison_state["session_alias"] == "2026:1:q"
    rendered_markup = " ".join(element.proto.body for element in app.get("html"))
    assert "Australian Grand Prix" in rendered_markup
    assert "Where the time was lost" in rendered_markup
    assert "Turn 3" in rendered_markup
    assert len(app.get("plotly_chart")) == 6


def test_identical_selection_disables_comparison() -> None:
    app = AppTest.from_file(FIXTURE_APP).run()
    app.button[0].click().run()
    app.selectbox(key="f1pi_driver_b").select_index(0).run()

    assert app.warning
    assert app.button[0].disabled is True


def test_render_error_logs_original_exception_with_traceback(
    caplog, monkeypatch
) -> None:
    rendered_error = Mock()
    monkeypatch.setattr(lap_analysis.st, "error", rendered_error)
    error = RuntimeError("comparison failed")

    with caplog.at_level(logging.ERROR, logger=lap_analysis.__name__):
        try:
            raise error
        except RuntimeError as caught:
            lap_analysis._render_error(caught)

    record = caplog.records[-1]
    assert record.getMessage() == "Lap analysis operation failed"
    assert record.exc_info is not None
    assert record.exc_info[1] is error
    rendered_error.assert_called_once()


def test_state_survives_runtime_class_reload(loaded_session) -> None:
    """State from an older module identity remains usable after a hot reload."""
    legacy_loaded = SimpleNamespace(
        key=loaded_session.key,
        metadata=loaded_session.metadata,
        drivers=loaded_session.drivers,
        snapshot_reused=True,
    )
    legacy_comparison = SimpleNamespace(lap_a=object(), lap_b=object())

    assert (
        lap_analysis._loaded_session_from_state(legacy_loaded, loaded_session.key)
        is legacy_loaded
    )
    assert (
        lap_analysis._comparison_from_state(legacy_comparison, loaded_session.key)
        is legacy_comparison
    )


def test_state_envelopes_reject_another_session(loaded_session) -> None:
    other_key = type(loaded_session.key)(2026, 2, "Q")
    loaded_state = lap_analysis._session_state(loaded_session.key, loaded_session)
    comparison_state = lap_analysis._session_state(loaded_session.key, object())

    assert lap_analysis._loaded_session_from_state(loaded_state, other_key) is None
    assert lap_analysis._comparison_from_state(comparison_state, other_key) is None

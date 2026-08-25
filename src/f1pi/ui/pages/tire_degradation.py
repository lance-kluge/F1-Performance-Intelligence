"""Guided tire-degradation analysis workspace."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import cast

import streamlit as st

from f1pi.analysis.models import DegradationMode
from f1pi.domain.models import ScheduledEvent, ScheduledSession, SessionKey
from f1pi.ui.analysis_facade import TireDegradationFacade
from f1pi.ui.components.layout import render_footer, render_wordmark
from f1pi.ui.components.tire_degradation import (
    render_analysis_ready,
    render_tire_intro,
    render_tire_progress,
    render_tire_results,
    render_tire_session_context,
)
from f1pi.ui.components.workspace import render_step_header
from f1pi.ui.errors import user_error
from f1pi.ui.models import TireAnalysisRun
from f1pi.ui.runtime import get_tire_analysis_facade

MIN_TIRE_MODEL_YEAR = 2018
TIRE_ANALYSIS_KEY = "f1pi_tire_analysis"
logger = logging.getLogger(__name__)


@st.cache_data(ttl=6 * 60 * 60, show_spinner=False)
def available_tire_events(year: int) -> tuple[ScheduledEvent, ...]:
    return get_tire_analysis_facade().list_available_events(year)


def render_tire_degradation() -> None:
    """Render session selection, model controls, and durable tire results."""
    render_wordmark(section="Tire degradation")
    render_tire_intro()
    render_tire_progress(st.session_state.get(TIRE_ANALYSIS_KEY) is not None)
    facade = get_tire_analysis_facade()
    selection = _render_session_selection()
    if selection is None:
        render_footer()
        return
    key, event, session = selection
    render_tire_session_context(event, session)
    mode = _render_model_controls()
    _run_or_restore_analysis(facade, key, mode)
    render_footer()


def _render_session_selection() -> tuple[SessionKey, ScheduledEvent, ScheduledSession] | None:
    render_step_header(
        1,
        "Choose a race session",
        "Completed Races and Sprints contain the stable stints required for tire modeling.",
    )
    current_year = datetime.now(UTC).year
    years = tuple(range(current_year, MIN_TIRE_MODEL_YEAR - 1, -1))
    season_column, event_column, session_column = st.columns((0.58, 1.42, 1), gap="medium")
    with season_column:
        season = st.selectbox(
            "Season",
            years,
            key="f1pi_tire_season",
            on_change=_clear_analysis,
        )
    try:
        with st.spinner("Loading the season schedule…"):
            events = available_tire_events(season)
    except Exception as error:
        _render_error(error)
        return None
    if not events:
        st.info("No completed Race or Sprint sessions are available for this season yet.")
        return None
    with event_column:
        event = st.selectbox(
            "Race weekend",
            events,
            format_func=_event_label,
            key="f1pi_tire_event",
            on_change=_clear_analysis,
        )
    with session_column:
        session = st.selectbox(
            "Session",
            event.sessions,
            format_func=_session_label,
            key="f1pi_tire_session",
            on_change=_clear_analysis,
        )
    return SessionKey(season, event.round_number, session.session_type), event, session


def _render_model_controls() -> DegradationMode:
    render_step_header(
        2,
        "Choose the model view",
        "The adjusted view separates tire age from measured race progress, driver, and weather.",
    )
    mode = st.radio(
        "Model view",
        (DegradationMode.ADJUSTED, DegradationMode.RAW),
        format_func=_mode_label,
        horizontal=True,
        key="f1pi_tire_mode",
        on_change=_clear_analysis,
    )
    if mode is DegradationMode.ADJUSTED:
        st.caption(
            "Recommended · Controls for driver, race progress, track and air temperature, "
            "humidity, pressure, wind, and rainfall when those features vary."
        )
    else:
        st.caption(
            "Exploratory · Fits lap time against tire age without condition controls. Useful "
            "for seeing the raw session trend, but more exposed to fuel and track evolution."
        )
    return mode


def _run_or_restore_analysis(
    facade: TireDegradationFacade,
    key: SessionKey,
    mode: DegradationMode,
) -> None:
    stored = _analysis_from_state(st.session_state.get(TIRE_ANALYSIS_KEY), key, mode)
    if st.button("Analyze tire degradation", type="primary", width="stretch"):
        try:
            with st.status("Preparing tire model…", expanded=True) as status:
                st.write("Checking the local immutable snapshot")
                run = facade.analyze(key, mode)
                st.write("Filtering clean laps and reconstructing stable stints")
                st.write("Fitting compound trends and validating whole stints")
                status.update(label="Tire analysis ready", state="complete", expanded=False)
            st.session_state[TIRE_ANALYSIS_KEY] = _analysis_state(key, run)
        except Exception as error:
            _render_error(error)
        else:
            st.rerun()
    if stored is None:
        return
    render_analysis_ready(stored)
    render_step_header(
        3,
        "Read the degradation",
        "Compare compound slopes first, then check uncertainty, validation, and lap eligibility.",
    )
    try:
        render_tire_results(stored)
    except Exception as error:
        _render_error(error)


def _analysis_state(key: SessionKey, run: TireAnalysisRun) -> dict[str, object]:
    return {
        "session_alias": key.alias_id,
        "mode": run.analysis.mode.value,
        "value": run,
    }


def _analysis_from_state(
    value: object,
    key: SessionKey,
    mode: DegradationMode,
) -> TireAnalysisRun | None:
    if not isinstance(value, dict):
        return None
    if value.get("session_alias") != key.alias_id or value.get("mode") != mode.value:
        return None
    payload = value.get("value")
    return None if payload is None else cast(TireAnalysisRun, payload)


def _clear_analysis() -> None:
    st.session_state.pop(TIRE_ANALYSIS_KEY, None)


def _render_error(error: Exception) -> None:
    logger.exception("Tire degradation operation failed")
    message = user_error(error)
    st.error(f"**{message.title}**\n\n{message.detail}")


def _event_label(event: ScheduledEvent) -> str:
    return f"Round {event.round_number} — {event.event_name} · {event.location}"


def _session_label(session: ScheduledSession) -> str:
    return f"{session.name} · {session.starts_at_utc:%d %b, %H:%M UTC}"


def _mode_label(mode: DegradationMode) -> str:
    if mode is DegradationMode.ADJUSTED:
        return "Condition-adjusted · recommended"
    return "Raw lap-time trend"

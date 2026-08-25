"""Guided tire-degradation analysis workspace."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import cast

import streamlit as st

from f1pi.analysis.models import DegradationMode
from f1pi.domain.models import ScheduledEvent, ScheduledSession, SessionKey
from f1pi.ui.analysis_facade import TireDegradationFacade
from f1pi.ui.components.layout import render_footer, render_wordmark
from f1pi.ui.components.tire_degradation import (
    render_analysis_ready,
    render_driver_analysis_ready,
    render_driver_tire_results,
    render_tire_intro,
    render_tire_results,
    render_tire_session_context,
)
from f1pi.ui.components.workspace import render_step_header
from f1pi.ui.errors import user_error
from f1pi.ui.models import DriverOption, DriverTireAnalysisRun, TireAnalysisRun
from f1pi.ui.runtime import get_tire_analysis_facade

MIN_TIRE_MODEL_YEAR = 2018
TIRE_ANALYSIS_KEY = "f1pi_tire_analysis"
ANALYSIS_PROGRESS_DETAIL = (
    "Loading the session snapshot, reconstructing clean stints, fitting compound trends, and "
    "validating the model. First-time sessions may take a few minutes."
)
DRIVER_ANALYSIS_PROGRESS_DETAIL = (
    "Loading the shared session snapshot, then fitting each driver's clean stints independently. "
    "Single-stint estimates remain visible with explicit uncertainty notes."
)
logger = logging.getLogger(__name__)


class TireAnalysisScope(StrEnum):
    SESSION = "session"
    DRIVERS = "drivers"


@dataclass(frozen=True, slots=True)
class TireViewSelection:
    mode: DegradationMode
    scope: TireAnalysisScope
    drivers: tuple[str, str] | None = None


@st.cache_data(ttl=6 * 60 * 60, show_spinner=False)
def available_tire_events(year: int) -> tuple[ScheduledEvent, ...]:
    return get_tire_analysis_facade().list_available_events(year)


@st.cache_data(ttl=6 * 60 * 60, show_spinner=False)
def available_tire_drivers(key: SessionKey) -> tuple[DriverOption, ...]:
    return get_tire_analysis_facade().list_drivers(key)


def render_tire_degradation() -> None:
    """Render session selection, model controls, and durable tire results."""
    render_wordmark(section="Tire degradation")
    render_tire_intro()
    facade = get_tire_analysis_facade()
    selection = _render_session_selection()
    if selection is None:
        render_footer()
        return
    key, event, session = selection
    render_tire_session_context(event, session)
    view = _render_model_controls(key)
    if view is not None:
        if view.scope is TireAnalysisScope.DRIVERS:
            _run_or_restore_driver_analysis(facade, key, view)
        else:
            _run_or_restore_analysis(facade, key, view.mode)
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


def _render_model_controls(key: SessionKey) -> TireViewSelection | None:
    render_step_header(
        2,
        "Choose the model view",
        "Compare the whole field by compound or fit two drivers independently, stint by stint.",
    )
    scope = st.radio(
        "Analysis scope",
        (TireAnalysisScope.SESSION, TireAnalysisScope.DRIVERS),
        format_func=_scope_label,
        horizontal=True,
        key="f1pi_tire_scope",
        on_change=_clear_analysis,
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
        driver_control = "driver, " if scope is TireAnalysisScope.SESSION else ""
        st.caption(
            f"Recommended · Controls for {driver_control}race progress, track and air "
            "temperature, "
            "humidity, pressure, wind, and rainfall when those features vary."
        )
    else:
        st.caption(
            "Exploratory · Fits lap time against tire age without condition controls. Useful "
            "for seeing the raw session trend, but more exposed to fuel and track evolution."
        )
    if scope is TireAnalysisScope.SESSION:
        return TireViewSelection(mode=mode, scope=scope)
    drivers = _render_driver_selection(key)
    if drivers is None:
        return None
    return TireViewSelection(mode=mode, scope=scope, drivers=drivers)


def _render_driver_selection(key: SessionKey) -> tuple[str, str] | None:
    try:
        with st.spinner("Loading drivers from the session snapshot…"):
            options = available_tire_drivers(key)
    except Exception as error:
        _render_error(error)
        return None
    first_column, second_column = st.columns(2, gap="medium")
    with first_column:
        first = st.selectbox(
            "Driver A",
            options,
            format_func=lambda option: option.label,
            key="f1pi_tire_driver_a",
            on_change=_clear_analysis,
        )
    second_options = tuple(
        option for option in options if option.abbreviation != first.abbreviation
    )
    with second_column:
        second = st.selectbox(
            "Driver B",
            second_options,
            format_func=lambda option: option.label,
            key="f1pi_tire_driver_b",
            on_change=_clear_analysis,
        )
    st.caption(
        "Each driver is modeled only from their own clean laps. Compounds supported by one "
        "stint are labeled as descriptive estimates."
    )
    return first.abbreviation, second.abbreviation


def _run_or_restore_analysis(
    facade: TireDegradationFacade,
    key: SessionKey,
    mode: DegradationMode,
) -> None:
    stored = _analysis_from_state(st.session_state.get(TIRE_ANALYSIS_KEY), key, mode)
    if st.button("Analyze tire degradation", type="primary", width="stretch"):
        try:
            with st.status("Loading, fitting, and validating tire model…", expanded=True) as status:
                st.write(ANALYSIS_PROGRESS_DETAIL)
                run = facade.analyze(key, mode)
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


def _run_or_restore_driver_analysis(
    facade: TireDegradationFacade,
    key: SessionKey,
    view: TireViewSelection,
) -> None:
    if view.drivers is None:
        return
    stored = _driver_analysis_from_state(
        st.session_state.get(TIRE_ANALYSIS_KEY),
        key,
        view.mode,
        view.drivers,
    )
    if st.button("Compare driver degradation", type="primary", width="stretch"):
        try:
            with st.status("Fitting two driver tire models…", expanded=True) as status:
                st.write(DRIVER_ANALYSIS_PROGRESS_DETAIL)
                runs = facade.analyze_drivers(key, view.drivers, view.mode)
                status.update(label="Driver comparison ready", state="complete", expanded=False)
            st.session_state[TIRE_ANALYSIS_KEY] = _driver_analysis_state(key, runs)
        except Exception as error:
            _render_error(error)
        else:
            st.rerun()
    if stored is None:
        return
    render_driver_analysis_ready(stored)
    render_step_header(
        3,
        "Compare the stints",
        "Read each driver's degradation rate beside the clean laps and stints supporting it.",
    )
    try:
        render_driver_tire_results(stored)
    except Exception as error:
        _render_error(error)


def _analysis_state(key: SessionKey, run: TireAnalysisRun) -> dict[str, object]:
    return {
        "session_alias": key.alias_id,
        "mode": run.analysis.mode.value,
        "scope": TireAnalysisScope.SESSION.value,
        "value": run,
    }


def _driver_analysis_state(
    key: SessionKey,
    runs: tuple[DriverTireAnalysisRun, DriverTireAnalysisRun],
) -> dict[str, object]:
    return {
        "session_alias": key.alias_id,
        "mode": runs[0].analysis.mode.value,
        "scope": TireAnalysisScope.DRIVERS.value,
        "drivers": tuple(run.analysis.driver for run in runs),
        "value": runs,
    }


def _analysis_from_state(
    value: object,
    key: SessionKey,
    mode: DegradationMode,
) -> TireAnalysisRun | None:
    if not isinstance(value, dict):
        return None
    if (
        value.get("session_alias") != key.alias_id
        or value.get("mode") != mode.value
        or value.get("scope", TireAnalysisScope.SESSION.value)
        != TireAnalysisScope.SESSION.value
    ):
        return None
    payload = value.get("value")
    return None if payload is None else cast(TireAnalysisRun, payload)


def _driver_analysis_from_state(
    value: object,
    key: SessionKey,
    mode: DegradationMode,
    drivers: tuple[str, str],
) -> tuple[DriverTireAnalysisRun, DriverTireAnalysisRun] | None:
    if not isinstance(value, dict):
        return None
    if (
        value.get("session_alias") != key.alias_id
        or value.get("mode") != mode.value
        or value.get("scope") != TireAnalysisScope.DRIVERS.value
        or value.get("drivers") != drivers
    ):
        return None
    payload = value.get("value")
    if payload is None:
        return None
    return cast(tuple[DriverTireAnalysisRun, DriverTireAnalysisRun], payload)


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


def _scope_label(scope: TireAnalysisScope) -> str:
    if scope is TireAnalysisScope.SESSION:
        return "Session compounds"
    return "Driver comparison"

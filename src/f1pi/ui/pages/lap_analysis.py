"""Guided interactive lap-analysis workspace."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import cast

import streamlit as st

from f1pi.analysis.models import LapComparison, LapSelection
from f1pi.domain.models import ScheduledEvent, ScheduledSession, SessionKey, SessionType
from f1pi.ui.analysis_facade import AnalysisFacade
from f1pi.ui.components.layout import render_footer, render_wordmark
from f1pi.ui.components.results import render_results
from f1pi.ui.components.workspace import (
    render_comparison_ready,
    render_loaded_session,
    render_session_context,
    render_step_header,
    render_workflow_progress,
    render_workspace_intro,
)
from f1pi.ui.errors import user_error
from f1pi.ui.formatting import FASTEST_LAP, SPECIFIC_LAP, lap_selection
from f1pi.ui.models import DriverOption, LoadedSession
from f1pi.ui.runtime import get_analysis_facade

MIN_TELEMETRY_YEAR = 2018
LOADED_SESSION_KEY = "f1pi_loaded_session"
COMPARISON_KEY = "f1pi_comparison"
logger = logging.getLogger(__name__)


@st.cache_data(ttl=6 * 60 * 60, show_spinner=False)
def available_events(year: int) -> tuple[ScheduledEvent, ...]:
    return get_analysis_facade().list_available_events(year)


def render_lap_analysis() -> None:
    """Render the staged loading, selection, and results workflow."""
    render_wordmark(section="Lap analysis")
    render_workspace_intro()
    render_workflow_progress(_active_step())
    facade = get_analysis_facade()
    selection = _render_session_selection()
    if selection is None:
        render_footer()
        return
    key, event, scheduled_session = selection
    loaded = _load_or_restore_session(facade, key, event, scheduled_session)
    if loaded is not None:
        _render_comparison_controls(facade, loaded)
    render_footer()


def _render_session_selection() -> tuple[SessionKey, ScheduledEvent, ScheduledSession] | None:
    render_step_header(
        1,
        "Choose a session",
        "Completed sessions from 2018 onward include the telemetry channels used here.",
    )
    current_year = datetime.now(UTC).year
    years = tuple(range(current_year, MIN_TELEMETRY_YEAR - 1, -1))
    season_column, event_column, session_column = st.columns((0.58, 1.42, 1), gap="medium")
    with season_column:
        season = st.selectbox(
            "Season",
            years,
            key="f1pi_season",
            on_change=_clear_event_selection,
        )
    try:
        with st.spinner("Loading the season schedule…"):
            events = available_events(season)
    except Exception as error:
        _render_error(error)
        return None
    if not events:
        st.info("No completed telemetry sessions are available for this season yet.")
        return None

    with event_column:
        event = st.selectbox(
            "Race weekend",
            events,
            format_func=_event_label,
            key="f1pi_event",
            on_change=_clear_session_selection,
        )
    with session_column:
        scheduled_session = st.selectbox(
            "Session",
            event.sessions,
            index=_preferred_session_index(event.sessions),
            format_func=_session_label,
            key="f1pi_session",
            on_change=_clear_loaded_state,
        )
    return (
        SessionKey(season, event.round_number, scheduled_session.session_type),
        event,
        scheduled_session,
    )


def _load_or_restore_session(
    facade: AnalysisFacade,
    key: SessionKey,
    event: ScheduledEvent,
    session: ScheduledSession,
) -> LoadedSession | None:
    loaded = _loaded_session_from_state(st.session_state.get(LOADED_SESSION_KEY), key)
    if loaded is not None:
        render_loaded_session(loaded)
        return loaded

    render_session_context(event, session)
    if not st.button("Load session telemetry", type="primary", width="stretch"):
        return None
    try:
        with st.status("Loading session telemetry…", expanded=True) as status:
            st.write("Checking the local immutable snapshot")
            loaded = facade.load_session(key)
            st.write("Preparing accurate timed laps")
            status.update(label="Session ready", state="complete", expanded=False)
    except Exception as error:
        _render_error(error)
        return None
    st.session_state[LOADED_SESSION_KEY] = _session_state(key, loaded)
    st.session_state.pop(COMPARISON_KEY, None)
    # Start a clean run so transient loading controls disappear and progress
    # immediately advances to lap selection.
    st.rerun()


def _render_comparison_controls(facade: AnalysisFacade, loaded: LoadedSession) -> None:
    render_step_header(
        2,
        "Choose two laps",
        "Use each driver's fastest accurate lap or select an exact accurate lap number.",
    )
    left, right = st.columns(2, gap="large")
    with left, st.container(border=True):
        driver_a, lap_a = _lap_controls("A", loaded.drivers, default_index=0)
    with right, st.container(border=True):
        driver_b, lap_b = _lap_controls(
            "B",
            loaded.drivers,
            default_index=1 if len(loaded.drivers) > 1 else 0,
        )

    identical = lap_a == lap_b
    if identical:
        st.warning(
            "Choose different drivers or lap numbers. An identical selection has no "
            "performance difference to analyze."
        )
    if st.button(
        "Compare selected laps",
        type="primary",
        width="stretch",
        disabled=identical,
    ):
        try:
            with st.status("Synchronizing both laps…", expanded=True) as status:
                st.write(
                    f"Aligning {driver_a.abbreviation} and "
                    f"{driver_b.abbreviation} by distance"
                )
                comparison_result = facade.compare(loaded.key, lap_a, lap_b)
                status.update(label="Comparison ready", state="complete", expanded=False)
            st.session_state[COMPARISON_KEY] = _session_state(
                loaded.key, comparison_result
            )
        except Exception as error:
            _render_error(error)
        else:
            # Render the durable result on a clean run instead of relying on the
            # transient button run to deliver every chart update to the browser.
            st.rerun()

    stored_comparison = _comparison_from_state(
        st.session_state.get(COMPARISON_KEY), loaded.key
    )
    if stored_comparison is not None:
        render_comparison_ready(stored_comparison)
        render_step_header(
            3,
            "Read the lap",
            "Use the views below to move from the headline result to detailed evidence.",
        )
        try:
            render_results(loaded, stored_comparison)
        except Exception as error:
            _render_error(error)


def _lap_controls(
    side: str,
    drivers: tuple[DriverOption, ...],
    *,
    default_index: int,
) -> tuple[DriverOption, LapSelection]:
    st.html(f'<p class="f1pi-driver-label">Driver {side}</p>')
    driver = st.selectbox(
        f"Driver {side}",
        drivers,
        index=default_index,
        format_func=_driver_label,
        key=f"f1pi_driver_{side.lower()}",
        on_change=_clear_comparison_state,
        label_visibility="collapsed",
    )
    mode = st.radio(
        f"Driver {side} lap selection",
        (FASTEST_LAP, SPECIFIC_LAP),
        horizontal=True,
        key=f"f1pi_lap_mode_{side.lower()}",
        on_change=_clear_comparison_state,
    )
    lap_number = None
    if mode == SPECIFIC_LAP:
        lap_number = st.selectbox(
            f"Driver {side} accurate lap",
            driver.accurate_lap_numbers,
            key=f"f1pi_lap_number_{side.lower()}",
            on_change=_clear_comparison_state,
        )
    return driver, lap_selection(driver.abbreviation, mode, lap_number)


def _render_error(error: Exception) -> None:
    logger.exception("Lap analysis operation failed")
    message = user_error(error)
    st.error(f"**{message.title}**\n\n{message.detail}")


def _preferred_session_index(sessions: tuple[ScheduledSession, ...]) -> int:
    """Prefer completed Race, then Qualifying, then the first available session."""
    for preferred in (SessionType.RACE, SessionType.QUALIFYING):
        for index, session in enumerate(sessions):
            if session.session_type == preferred:
                return index
    return 0


def _clear_event_selection() -> None:
    st.session_state.pop("f1pi_event", None)
    _clear_session_selection()


def _clear_session_selection() -> None:
    st.session_state.pop("f1pi_session", None)
    _clear_loaded_state()


def _clear_loaded_state() -> None:
    st.session_state.pop(LOADED_SESSION_KEY, None)
    st.session_state.pop(COMPARISON_KEY, None)


def _clear_comparison_state() -> None:
    st.session_state.pop(COMPARISON_KEY, None)


def _active_step() -> int:
    """Return the current workflow step from durable Streamlit state."""
    if st.session_state.get(COMPARISON_KEY) is not None:
        return 3
    if st.session_state.get(LOADED_SESSION_KEY) is not None:
        return 2
    return 1


def _session_state(key: SessionKey, value: object) -> dict[str, object]:
    """Scope a UI payload without depending on its runtime class identity."""
    return {"session_alias": key.alias_id, "value": value}


def _loaded_session_from_state(value: object, key: SessionKey) -> LoadedSession | None:
    """Restore current and pre-envelope state across Streamlit module reloads."""
    if isinstance(value, dict):
        if value.get("session_alias") != key.alias_id:
            return None
        payload = value.get("value")
        return None if payload is None else cast(LoadedSession, payload)
    if value is not None and getattr(value, "key", None) == key:
        return cast(LoadedSession, value)
    return None


def _comparison_from_state(value: object, key: SessionKey) -> LapComparison | None:
    """Restore a comparison while rejecting results belonging to another session."""
    if isinstance(value, dict):
        if value.get("session_alias") != key.alias_id:
            return None
        payload = value.get("value")
        return None if payload is None else cast(LapComparison, payload)
    # Comparisons stored by the first version of the workspace were unscoped.
    # Selection callbacks already clear them, so retaining one during a hot reload
    # is safer than silently dropping a completed analysis.
    return None if value is None else cast(LapComparison, value)


def _event_label(event: ScheduledEvent) -> str:
    return f"Round {event.round_number} — {event.event_name} · {event.location}"


def _session_label(session: ScheduledSession) -> str:
    return f"{session.name} · {session.starts_at_utc:%d %b, %H:%M UTC}"


def _driver_label(driver: DriverOption) -> str:
    return driver.label

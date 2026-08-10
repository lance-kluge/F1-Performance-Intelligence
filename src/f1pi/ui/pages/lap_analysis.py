"""Guided interactive lap-analysis workspace."""

from __future__ import annotations

from datetime import UTC, datetime

import streamlit as st

from f1pi.analysis.models import LapComparison, LapSelection
from f1pi.domain.models import ScheduledEvent, ScheduledSession, SessionKey
from f1pi.ui.analysis_facade import AnalysisFacade
from f1pi.ui.components.layout import render_footer, render_wordmark
from f1pi.ui.components.results import render_results
from f1pi.ui.errors import user_error
from f1pi.ui.formatting import FASTEST_LAP, SPECIFIC_LAP, lap_selection
from f1pi.ui.models import DriverOption, LoadedSession
from f1pi.ui.runtime import get_analysis_facade

MIN_TELEMETRY_YEAR = 2018
LOADED_SESSION_KEY = "f1pi_loaded_session"
COMPARISON_KEY = "f1pi_comparison"


@st.cache_data(ttl=6 * 60 * 60, show_spinner=False)
def available_events(year: int) -> tuple[ScheduledEvent, ...]:
    return get_analysis_facade().list_available_events(year)


def render_lap_analysis() -> None:
    """Render the staged loading, selection, and results workflow."""
    render_wordmark(section="Lap analysis")
    st.html(
        """
        <section class="f1pi-analysis-intro" aria-labelledby="analysis-title">
          <p class="f1pi-eyebrow"><span></span> Interactive workspace</p>
          <h1 id="analysis-title">Compare the lap, not just the time.</h1>
          <p>Select a completed session, load its telemetry, then inspect where two accurate
          laps gained and lost performance around the circuit.</p>
        </section>
        """
    )
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
    st.html('<div class="f1pi-stage"><span>01</span><h2>Choose a session</h2></div>')
    current_year = datetime.now(UTC).year
    years = tuple(range(current_year, MIN_TELEMETRY_YEAR - 1, -1))
    season = st.selectbox(
        "Season",
        years,
        key="f1pi_season",
        on_change=_clear_loaded_state,
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

    event = st.selectbox(
        "Race weekend",
        events,
        format_func=_event_label,
        key="f1pi_event",
        on_change=_clear_loaded_state,
    )
    scheduled_session = st.selectbox(
        "Session",
        event.sessions,
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
    loaded = st.session_state.get(LOADED_SESSION_KEY)
    if isinstance(loaded, LoadedSession) and loaded.key == key:
        st.success(
            f"{loaded.metadata.event_name} · {loaded.metadata.session_name} is ready"
            + (" from the local snapshot." if loaded.snapshot_reused else ".")
        )
        return loaded

    st.caption(
        f"Round {event.round_number} · {session.name} · "
        f"{session.starts_at_utc:%d %b %Y, %H:%M UTC}"
    )
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
    st.session_state[LOADED_SESSION_KEY] = loaded
    st.session_state.pop(COMPARISON_KEY, None)
    st.success(f"{loaded.metadata.event_name} · {loaded.metadata.session_name} is ready.")
    return loaded


def _render_comparison_controls(facade: AnalysisFacade, loaded: LoadedSession) -> None:
    st.html('<div class="f1pi-stage"><span>02</span><h2>Choose two laps</h2></div>')
    left, right = st.columns(2, gap="large")
    with left:
        driver_a, lap_a = _lap_controls("A", loaded.drivers, default_index=0)
    with right:
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
        "Run lap comparison",
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
            st.session_state[COMPARISON_KEY] = comparison_result
        except Exception as error:
            _render_error(error)

    stored_comparison = st.session_state.get(COMPARISON_KEY)
    if isinstance(stored_comparison, LapComparison):
        st.html(
            '<div class="f1pi-stage f1pi-stage--results"><span>03</span>'
            "<h2>Read the lap</h2></div>"
        )
        render_results(loaded, stored_comparison)


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
    message = user_error(error)
    st.error(f"**{message.title}**\n\n{message.detail}")


def _clear_loaded_state() -> None:
    st.session_state.pop(LOADED_SESSION_KEY, None)
    st.session_state.pop(COMPARISON_KEY, None)


def _clear_comparison_state() -> None:
    st.session_state.pop(COMPARISON_KEY, None)


def _event_label(event: ScheduledEvent) -> str:
    return f"Round {event.round_number} — {event.event_name} · {event.location}"


def _session_label(session: ScheduledSession) -> str:
    return f"{session.name} · {session.starts_at_utc:%d %b, %H:%M UTC}"


def _driver_label(driver: DriverOption) -> str:
    return driver.label

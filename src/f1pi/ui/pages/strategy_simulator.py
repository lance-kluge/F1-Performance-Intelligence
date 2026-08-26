"""Guided retrospective race-strategy simulator workspace."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import cast

import streamlit as st

from f1pi.analysis.models import (
    NeutralizationScenario,
    PlannedPitStop,
    StrategyPlan,
    StrategySimulationConfig,
    StrategySimulationRequest,
)
from f1pi.domain.models import ScheduledEvent, ScheduledSession, SessionKey
from f1pi.ui.analysis_facade import StrategySimulatorFacade
from f1pi.ui.components.layout import render_footer, render_wordmark
from f1pi.ui.components.strategy_simulator import (
    render_setup_ready,
    render_simulation_ready,
    render_strategy_intro,
    render_strategy_results,
    render_strategy_session_context,
)
from f1pi.ui.components.workspace import render_step_header
from f1pi.ui.errors import user_error
from f1pi.ui.models import StrategySimulationRun, StrategySimulationSetup
from f1pi.ui.runtime import get_strategy_analysis_facade

MIN_STRATEGY_YEAR = 2018
STRATEGY_SETUP_KEY = "f1pi_strategy_setup"
STRATEGY_RUN_KEY = "f1pi_strategy_run"
SIMULATION_PROGRESS_DETAIL = (
    "Calibrating session pace, pit loss, traffic, and neutralization effects, then running "
    "paired full-field counterfactuals. This can take a few minutes."
)
SCENARIO_OPTIONS = ("Actual race", "Green race")
logger = logging.getLogger(__name__)


@st.cache_data(ttl=6 * 60 * 60, show_spinner=False)
def available_strategy_events(year: int) -> tuple[ScheduledEvent, ...]:
    return get_strategy_analysis_facade().list_available_events(year)


def render_strategy_simulator() -> None:
    """Render race selection, candidate-plan controls, and durable results."""
    render_wordmark(section="Strategy simulator")
    render_strategy_intro()
    facade = get_strategy_analysis_facade()
    selection = _render_session_selection()
    if selection is None:
        render_footer()
        return
    key, event, session = selection
    setup = _load_or_restore_setup(facade, key, event, session)
    if setup is not None:
        _render_simulation_workspace(facade, setup)
    render_footer()


def _render_session_selection() -> tuple[SessionKey, ScheduledEvent, ScheduledSession] | None:
    render_step_header(
        1,
        "Choose a completed race",
        "Race and Sprint snapshots provide the field, tire, weather, and track-status history.",
    )
    current_year = datetime.now(UTC).year
    years = tuple(range(current_year, MIN_STRATEGY_YEAR - 1, -1))
    season_column, event_column, session_column = st.columns((0.58, 1.42, 1), gap="medium")
    with season_column:
        season = st.selectbox(
            "Season", years, key="f1pi_strategy_season", on_change=_clear_strategy_state
        )
    try:
        with st.spinner("Loading the season schedule…"):
            events = available_strategy_events(season)
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
            key="f1pi_strategy_event",
            on_change=_clear_strategy_state,
        )
    with session_column:
        session = st.selectbox(
            "Session",
            event.sessions,
            format_func=_session_label,
            key="f1pi_strategy_session",
            on_change=_clear_strategy_state,
        )
    return SessionKey(season, event.round_number, session.session_type), event, session


def _load_or_restore_setup(
    facade: StrategySimulatorFacade,
    key: SessionKey,
    event: ScheduledEvent,
    session: ScheduledSession,
) -> StrategySimulationSetup | None:
    setup = _setup_from_state(st.session_state.get(STRATEGY_SETUP_KEY), key)
    if setup is not None:
        render_setup_ready(setup)
        return setup
    render_strategy_session_context(event, session)
    if not st.button("Load race for simulation", type="primary", width="stretch"):
        return None
    try:
        with st.status("Preparing race snapshot…", expanded=True) as status:
            st.write("Loading laps, classifications, weather, and track status")
            setup = facade.load_setup(key)
            status.update(label="Race ready", state="complete", expanded=False)
    except Exception as error:
        _render_error(error)
        return None
    st.session_state[STRATEGY_SETUP_KEY] = {"session_alias": key.alias_id, "value": setup}
    st.session_state.pop(STRATEGY_RUN_KEY, None)
    st.rerun()


def _render_simulation_workspace(
    facade: StrategySimulatorFacade, setup: StrategySimulationSetup
) -> None:
    render_step_header(
        2,
        "Define the decision and pit plans",
        "Stops occur after the named lap. Both candidates are compared with the observed "
        "remaining plan.",
    )
    driver = st.selectbox(
        "Target driver",
        setup.drivers,
        format_func=lambda option: option.label,
        key="f1pi_strategy_driver",
        on_change=_clear_simulation,
    )
    decision_laps = tuple(
        lap for lap in driver.accurate_lap_numbers if lap < setup.race_laps
    )
    if not decision_laps:
        st.warning("This driver has no usable decision lap before the finish.")
        return
    decision_lap = st.selectbox(
        "Last observed lap",
        decision_laps,
        index=_closest_index(decision_laps, max(1, setup.race_laps // 3)),
        key="f1pi_strategy_decision_lap",
        on_change=_clear_simulation,
        help="The simulator begins after this completed lap. A pit-in lap cannot be selected.",
    )
    stop_laps = tuple(range(decision_lap + 1, setup.race_laps))
    if not stop_laps:
        st.warning("Choose an earlier decision lap so at least one future stop can be tested.")
        return
    left, right = st.columns(2, gap="large")
    with left, st.container(border=True):
        first = _strategy_controls(
            "A",
            "Early stop",
            stop_laps,
            setup.compounds,
            default_lap=decision_lap + max(2, len(stop_laps) // 3),
            default_compound_index=0,
        )
    with right, st.container(border=True):
        second = _strategy_controls(
            "B",
            "Extend stint",
            stop_laps,
            setup.compounds,
            default_lap=decision_lap + max(3, 2 * len(stop_laps) // 3),
            default_compound_index=min(1, len(setup.compounds) - 1),
        )
    names_invalid = first.name.casefold() == second.name.casefold() or any(
        plan.name.casefold() == "baseline" or not plan.name.strip() for plan in (first, second)
    )
    if names_invalid:
        st.warning("Give each candidate a unique name; “baseline” is reserved.")
    scenario_labels = st.multiselect(
        "Race-control scenarios",
        SCENARIO_OPTIONS,
        default=SCENARIO_OPTIONS,
        key="f1pi_strategy_scenarios",
        on_change=_clear_simulation,
        help="Actual race replays observed SC/VSC periods. Green race removes them.",
    )
    if not scenario_labels:
        st.warning("Select at least one race-control scenario.")
    with st.expander("Simulation precision"):
        iterations = st.select_slider(
            "Paired runs per plan",
            options=(500, 1000, 2000, 5000),
            value=2000,
            key="f1pi_strategy_iterations",
            on_change=_clear_simulation,
        )
        random_seed = st.number_input(
            "Random seed",
            min_value=0,
            max_value=2_147_483_647,
            value=7,
            step=1,
            key="f1pi_strategy_seed",
            on_change=_clear_simulation,
            help="Keep this fixed to reproduce the same paired samples.",
        )
    disabled = names_invalid or not scenario_labels
    if disabled:
        st.button(
            "Simulate candidate strategies",
            type="primary",
            width="stretch",
            disabled=True,
        )
        return
    scenarios = tuple(_scenario(label) for label in scenario_labels)
    request = StrategySimulationRequest(
        driver.abbreviation,
        decision_lap,
        (first, second),
        scenarios,
    )
    config = StrategySimulationConfig(iterations=int(iterations), random_seed=int(random_seed))
    _run_or_restore_simulation(facade, setup, request, config)


def _strategy_controls(
    side: str,
    default_name: str,
    stop_laps: tuple[int, ...],
    compounds: tuple[str, ...],
    *,
    default_lap: int,
    default_compound_index: int,
) -> StrategyPlan:
    st.html(f'<p class="f1pi-driver-label">Candidate {side}</p>')
    name = st.text_input(
        f"Candidate {side} name",
        value=default_name,
        key=f"f1pi_strategy_name_{side.lower()}",
        on_change=_clear_simulation,
    )
    lap = st.selectbox(
        f"Stop after lap · Candidate {side}",
        stop_laps,
        index=_closest_index(stop_laps, default_lap),
        key=f"f1pi_strategy_stop_lap_{side.lower()}",
        on_change=_clear_simulation,
    )
    compound = st.selectbox(
        f"Next compound · Candidate {side}",
        compounds,
        index=default_compound_index,
        format_func=str.title,
        key=f"f1pi_strategy_compound_{side.lower()}",
        on_change=_clear_simulation,
    )
    tire_age = st.number_input(
        f"Starting tire age · Candidate {side}",
        min_value=0.0,
        max_value=50.0,
        value=1.0,
        step=1.0,
        format="%.1f",
        key=f"f1pi_strategy_tire_age_{side.lower()}",
        on_change=_clear_simulation,
        help="Use 1.0 for a new set, or enter the starting age of a used set.",
    )
    safe_name = name.strip() or f"Candidate {side}"
    return StrategyPlan(safe_name, (PlannedPitStop(lap, compound, float(tire_age)),))


def _run_or_restore_simulation(
    facade: StrategySimulatorFacade,
    setup: StrategySimulationSetup,
    request: StrategySimulationRequest,
    config: StrategySimulationConfig,
) -> None:
    stored = _run_from_state(
        st.session_state.get(STRATEGY_RUN_KEY), setup.key, request, config
    )
    if st.button(
        "Simulate candidate strategies",
        type="primary",
        width="stretch",
    ):
        try:
            with st.status("Calibrating and simulating the race…", expanded=True) as status:
                st.write(SIMULATION_PROGRESS_DETAIL)
                run = facade.simulate(setup, request, config)
                status.update(label="Strategy simulation ready", state="complete", expanded=False)
            st.session_state[STRATEGY_RUN_KEY] = {
                "session_alias": setup.key.alias_id,
                "request": request,
                "config": config,
                "value": run,
            }
        except Exception as error:
            _render_error(error)
        else:
            st.rerun()
    if stored is None:
        return
    render_simulation_ready(stored)
    render_step_header(
        3,
        "Compare the counterfactuals",
        "Start with mean outcomes, then inspect the position range and calibration support.",
    )
    try:
        render_strategy_results(stored)
    except Exception as error:
        _render_error(error)


def _setup_from_state(value: object, key: SessionKey) -> StrategySimulationSetup | None:
    if not isinstance(value, dict) or value.get("session_alias") != key.alias_id:
        return None
    payload = value.get("value")
    return None if payload is None else cast(StrategySimulationSetup, payload)


def _run_from_state(
    value: object,
    key: SessionKey,
    request: StrategySimulationRequest,
    config: StrategySimulationConfig,
) -> StrategySimulationRun | None:
    if not isinstance(value, dict):
        return None
    if (
        value.get("session_alias") != key.alias_id
        or value.get("request") != request
        or value.get("config") != config
    ):
        return None
    payload = value.get("value")
    return None if payload is None else cast(StrategySimulationRun, payload)


def _clear_strategy_state() -> None:
    st.session_state.pop(STRATEGY_SETUP_KEY, None)
    st.session_state.pop(STRATEGY_RUN_KEY, None)


def _clear_simulation() -> None:
    st.session_state.pop(STRATEGY_RUN_KEY, None)


def _render_error(error: Exception) -> None:
    logger.exception("Strategy simulation operation failed")
    message = user_error(error)
    st.error(f"**{message.title}**\n\n{message.detail}")


def _scenario(label: str) -> NeutralizationScenario:
    if label == "Actual race":
        return NeutralizationScenario.actual()
    return NeutralizationScenario.no_safety_car()


def _closest_index(values: tuple[int, ...], target: int) -> int:
    return min(range(len(values)), key=lambda index: abs(values[index] - target))


def _event_label(event: ScheduledEvent) -> str:
    return f"Round {event.round_number} — {event.event_name} · {event.location}"


def _session_label(session: ScheduledSession) -> str:
    return f"{session.name} · {session.starts_at_utc:%d %b, %H:%M UTC}"

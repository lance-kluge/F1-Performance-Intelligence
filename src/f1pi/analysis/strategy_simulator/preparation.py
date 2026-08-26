"""Normalize one stored race into simulator-ready state."""

from __future__ import annotations

import re
from dataclasses import dataclass

import numpy as np
import pandas as pd

from f1pi.analysis.models import (
    NeutralizationEvent,
    NeutralizationKind,
    NeutralizationScenario,
    NeutralizationSource,
    PlannedPitStop,
    StrategyPlan,
    StrategySimulationConfig,
    StrategySimulationRequest,
    TireModelConfig,
)
from f1pi.analysis.strategy_simulator.analysis_session import StrategyAnalysisSession
from f1pi.analysis.tire_model.features import prepare_observations
from f1pi.domain.exceptions import (
    InsufficientStrategyDataError,
    InvalidStrategyError,
    UnsupportedStrategySessionError,
)
from f1pi.domain.models import SessionMetadata, SessionType

GREEN = "green"
NANOSECONDS_PER_SECOND = 1_000_000_000.0


@dataclass(frozen=True, slots=True)
class InitialCarState:
    driver: str
    completed_laps: int
    elapsed_seconds: float
    compound: str
    tire_age_laps: float
    maximum_laps: int


@dataclass(frozen=True, slots=True)
class PreparedRace:
    metadata: SessionMetadata
    laps: pd.DataFrame
    observations: pd.DataFrame
    results: pd.DataFrame
    drivers: tuple[str, ...]
    race_laps: int
    race_origin_seconds: float
    initial_states: tuple[InitialCarState, ...]
    observed_plans: dict[str, StrategyPlan]
    baseline: StrategyPlan
    actual_events: tuple[NeutralizationEvent, ...]
    weather_by_lap: pd.DataFrame


def prepare_race(
    session: StrategyAnalysisSession,
    request: StrategySimulationRequest,
    config: StrategySimulationConfig,
) -> PreparedRace:
    if session.metadata.session_type not in {SessionType.RACE, SessionType.SPRINT}:
        raise UnsupportedStrategySessionError(
            "strategy simulation supports completed Race and Sprint sessions only"
        )

    laps = session.laps().copy()
    results = session.results().copy()
    weather = session.weather().copy()
    track_status = session.track_status().copy()
    if laps.empty or results.empty or weather.empty or track_status.empty:
        raise InsufficientStrategyDataError("laps, results, weather, and track status are required")
    if track_status["status"].astype(str).eq("5").any():
        raise UnsupportedStrategySessionError("red-flag races are not supported in v1")

    laps["driver"] = laps["driver"].astype("string").str.strip().str.upper()
    laps["compound"] = laps["compound"].astype("string").str.strip().str.upper()
    laps["lap_time_seconds"] = _seconds(laps["lap_time_ns"])
    laps["lap_start_seconds"] = _seconds(laps["lap_start_time_ns"])
    laps["lap_end_seconds"] = laps["lap_start_seconds"] + laps["lap_time_seconds"]
    laps["tire_age_laps"] = pd.to_numeric(laps["tyre_life"], errors="coerce")
    laps["condition"] = _conditions_from_timeline(laps, track_status)
    laps = laps.sort_values(["driver", "lap_number"], kind="stable").reset_index(drop=True)
    laps["gap_ahead_seconds"] = _gaps_at_line(laps)

    race_laps = int(pd.to_numeric(laps["lap_number"], errors="coerce").max())
    if request.decision_lap >= race_laps:
        raise InvalidStrategyError("decision_lap must precede the end of the race")
    _validate_target(results, laps, request.driver)
    _validate_request_windows(request, race_laps)

    observations = prepare_observations(
        laps,
        weather,
        track_status,
        TireModelConfig(
            confidence_level=config.confidence_level,
            quick_lap_ratio=2.0,
            minimum_compound_stints=2,
            minimum_compound_laps=5,
        ),
    )
    observations["gap_ahead_seconds"] = _lookup_column(observations, laps, "gap_ahead_seconds")
    observations["condition"] = _lookup_column(observations, laps, "condition")

    drivers = _ordered_drivers(results, laps)
    race_origin_seconds = float(
        laps.loc[laps["lap_number"].eq(1), "lap_start_seconds"].dropna().min()
    )
    initial_states = _initial_states(
        laps,
        results,
        drivers,
        request.decision_lap,
        race_laps,
        race_origin_seconds,
    )
    observed_plans = {driver: _observed_plan(laps, driver) for driver in drivers}
    baseline = StrategyPlan(
        "baseline",
        tuple(
            stop
            for stop in observed_plans[request.driver].stops
            if stop.after_lap > request.decision_lap
        ),
    )
    actual_events = _actual_events(laps, results)
    weather_by_lap = (
        observations.groupby("lap_number", sort=True)[
            [
                "race_progress",
                "track_temp",
                "air_temp",
                "humidity",
                "pressure",
                "wind_speed",
                "rainfall",
            ]
        ]
        .median()
        .reindex(range(1, race_laps + 1))
        .interpolate(limit_direction="both")
    )
    return PreparedRace(
        metadata=session.metadata,
        laps=laps,
        observations=observations,
        results=results,
        drivers=drivers,
        race_laps=race_laps,
        race_origin_seconds=race_origin_seconds,
        initial_states=initial_states,
        observed_plans=observed_plans,
        baseline=baseline,
        actual_events=actual_events,
        weather_by_lap=weather_by_lap,
    )


def scenario_events(
    scenario: NeutralizationScenario, prepared: PreparedRace, decision_lap: int
) -> tuple[NeutralizationEvent, ...]:
    if scenario.source is NeutralizationSource.NONE:
        return ()
    events = (
        prepared.actual_events
        if scenario.source is NeutralizationSource.ACTUAL
        else scenario.events
    )
    return tuple(event for event in events if event.end_lap > decision_lap)


def _seconds(values: pd.Series) -> pd.Series:
    return pd.to_numeric(values, errors="coerce").astype(float) / NANOSECONDS_PER_SECOND


def _condition_from_statuses(statuses: tuple[str, ...]) -> str:
    if any(status == "4" for status in statuses):
        return NeutralizationKind.SAFETY_CAR.value
    if any(status in {"6", "7"} for status in statuses):
        return NeutralizationKind.VIRTUAL_SAFETY_CAR.value
    return GREEN


def _conditions_from_timeline(laps: pd.DataFrame, track_status: pd.DataFrame) -> pd.Series:
    timeline = track_status.copy()
    timeline["_time_seconds"] = _seconds(timeline["time_ns"])
    timeline = timeline.dropna(subset=["_time_seconds"]).sort_values("_time_seconds")
    event_times = timeline["_time_seconds"].to_numpy(dtype=float)
    event_codes = timeline["status"].astype(str).to_numpy()
    conditions: list[str] = []
    for _, lap in laps.iterrows():
        start = lap["lap_start_seconds"]
        end = lap["lap_end_seconds"]
        if pd.isna(start) or pd.isna(end) or not len(event_times):
            conditions.append(GREEN)
            continue
        start_index = max(int(np.searchsorted(event_times, float(start), side="right")) - 1, 0)
        end_index = int(np.searchsorted(event_times, float(end), side="right"))
        statuses = tuple(str(status) for status in event_codes[start_index:end_index])
        conditions.append(_condition_from_statuses(statuses))
    return pd.Series(conditions, index=laps.index, dtype="string")


def _gaps_at_line(laps: pd.DataFrame) -> pd.Series:
    gaps = pd.Series(np.nan, index=laps.index, dtype=float)
    for _, same_lap in laps.groupby("lap_number", sort=False):
        ordered = same_lap.dropna(subset=["lap_end_seconds"]).sort_values("lap_end_seconds")
        gaps.loc[ordered.index] = ordered["lap_end_seconds"].diff().to_numpy()
        if not ordered.empty:
            gaps.loc[ordered.index[0]] = np.inf
    return gaps


def _lookup_column(target: pd.DataFrame, source: pd.DataFrame, column: str) -> pd.Series:
    values = source.set_index(["driver", "lap_number"])[column]
    index = pd.MultiIndex.from_frame(target[["driver", "lap_number"]])
    return pd.Series(values.reindex(index).to_numpy(), index=target.index)


def _validate_target(results: pd.DataFrame, laps: pd.DataFrame, driver: str) -> None:
    if not laps["driver"].eq(driver).any():
        raise InvalidStrategyError(f"driver is not present in session laps: {driver}")
    result = results.loc[results["abbreviation"].astype(str).str.upper().eq(driver)]
    if result.empty or result["position"].isna().all():
        raise InvalidStrategyError("target driver must have a classified result")
    status = str(result.iloc[0].get("status", ""))
    if not _is_classified_finisher(status):
        raise InvalidStrategyError("target driver must be a classified finisher")


def _validate_request_windows(request: StrategySimulationRequest, race_laps: int) -> None:
    for strategy in request.strategies:
        for stop in strategy.stops:
            if stop.after_lap <= request.decision_lap or stop.after_lap >= race_laps:
                raise InvalidStrategyError(
                    f"strategy {strategy.name!r} has a stop outside the simulatable window"
                )
    for scenario in request.scenarios:
        for event in scenario.events:
            if event.start_lap <= request.decision_lap or event.end_lap > race_laps:
                raise InvalidStrategyError(
                    f"scenario {scenario.name!r} has an event outside the simulatable window"
                )


def _ordered_drivers(results: pd.DataFrame, laps: pd.DataFrame) -> tuple[str, ...]:
    lap_drivers = set(laps["driver"].dropna().astype(str))
    ordered = [
        str(driver).upper()
        for driver in results.sort_values("position", na_position="last")["abbreviation"]
        if str(driver).upper() in lap_drivers
    ]
    ordered.extend(sorted(lap_drivers - set(ordered)))
    return tuple(ordered)


def _initial_states(
    laps: pd.DataFrame,
    results: pd.DataFrame,
    drivers: tuple[str, ...],
    decision_lap: int,
    race_laps: int,
    race_origin_seconds: float,
) -> tuple[InitialCarState, ...]:
    states: list[InitialCarState] = []
    for driver in drivers:
        driver_laps = laps.loc[laps["driver"].eq(driver)].sort_values("lap_number")
        completed = driver_laps.loc[driver_laps["lap_number"].le(decision_lap)]
        if completed.empty:
            continue
        current = completed.iloc[-1]
        if pd.isna(current["lap_end_seconds"]) or pd.isna(current["tire_age_laps"]):
            raise InsufficientStrategyDataError(f"initial state is incomplete for {driver}")
        result = results.loc[results["abbreviation"].astype(str).str.upper().eq(driver)]
        status = "" if result.empty else str(result.iloc[0].get("status", ""))
        classified_finisher = _is_classified_finisher(status)
        states.append(
            InitialCarState(
                driver=driver,
                completed_laps=int(current["lap_number"]),
                elapsed_seconds=float(current["lap_end_seconds"]) - race_origin_seconds,
                compound=str(current["compound"]),
                tire_age_laps=float(current["tire_age_laps"]),
                maximum_laps=(
                    race_laps if classified_finisher else int(driver_laps["lap_number"].max())
                ),
            )
        )
    if len(states) < 2:
        raise InsufficientStrategyDataError("at least two classified cars are required")
    return tuple(states)


def _is_classified_finisher(status: str) -> bool:
    normalized = status.strip()
    return normalized in {"Finished", "Lapped"} or bool(
        re.fullmatch(r"\+\s*\d+\s+Laps?", normalized, flags=re.IGNORECASE)
    )


def _observed_plan(laps: pd.DataFrame, driver: str) -> StrategyPlan:
    driver_laps = laps.loc[laps["driver"].eq(driver)].sort_values("lap_number")
    stops: list[PlannedPitStop] = []
    records = list(driver_laps.iterrows())
    for record_index, (_, lap) in enumerate(records[:-1]):
        if pd.isna(lap.get("pit_in_time_ns")):
            continue
        next_lap = records[record_index + 1][1]
        if int(next_lap["lap_number"]) != int(lap["lap_number"]) + 1:
            continue
        stops.append(
            PlannedPitStop(
                after_lap=int(lap["lap_number"]),
                compound=str(next_lap["compound"]),
                starting_tire_age_laps=float(next_lap["tire_age_laps"]),
            )
        )
    return StrategyPlan(f"observed:{driver}", tuple(stops))


def _actual_events(laps: pd.DataFrame, results: pd.DataFrame) -> tuple[NeutralizationEvent, ...]:
    winner_rows = results.loc[pd.to_numeric(results["position"], errors="coerce").eq(1)]
    leader = (
        str(winner_rows.iloc[0]["abbreviation"]).upper()
        if not winner_rows.empty
        else str(laps.loc[laps["lap_end_seconds"].idxmin(), "driver"])
    )
    leader_laps = laps.loc[laps["driver"].eq(leader)].sort_values("lap_number")
    conditions = [
        (int(row["lap_number"]), str(row["condition"]))
        for _, row in leader_laps.iterrows()
        if str(row["condition"]) != GREEN
    ]
    if not conditions:
        return ()
    events: list[NeutralizationEvent] = []
    start_lap, previous_lap = conditions[0][0], conditions[0][0]
    kind = NeutralizationKind(conditions[0][1])
    for lap_number, condition in conditions[1:]:
        next_kind = NeutralizationKind(condition)
        if lap_number != previous_lap + 1 or next_kind is not kind:
            events.append(NeutralizationEvent(kind, start_lap, previous_lap))
            start_lap, kind = lap_number, next_kind
        previous_lap = lap_number
    events.append(NeutralizationEvent(kind, start_lap, previous_lap))
    return tuple(events)

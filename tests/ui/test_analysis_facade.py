from __future__ import annotations

from unittest.mock import Mock

import pandas as pd
import pytest

from f1pi.analysis.models import DegradationMode
from f1pi.domain.exceptions import LapNotFoundError, UnsupportedStrategySessionError
from f1pi.domain.models import (
    IngestionResult,
    ScheduledEvent,
    ScheduledSession,
    SessionKey,
    SessionType,
)
from f1pi.ui.analysis_facade import (
    LapAnalysisFacade,
    StrategyAnalysisFacade,
    TireAnalysisFacade,
    driver_options,
)
from f1pi.ui.models import LoadedSession


def _session_frames() -> tuple[pd.DataFrame, pd.DataFrame]:
    results = pd.DataFrame(
        {
            "abbreviation": ["VER", "NOR", "ANT"],
            "full_name": ["Max Verstappen", "Lando Norris", "Kimi Antonelli"],
            "team_name": ["Red Bull Racing", "McLaren", "Mercedes"],
            "position": pd.array([2, 1, pd.NA], dtype="Int64"),
        }
    )
    laps = pd.DataFrame(
        {
            "driver": ["NOR", "NOR", "VER", "ANT"],
            "lap_number": pd.array([7, 9, 8, 10], dtype="Int64"),
            "lap_time_ns": pd.array([90, 89, 91, 92], dtype="Int64"),
            "lap_start_time_ns": pd.array([1, 2, 3, 4], dtype="Int64"),
            "is_accurate": pd.array([True, True, True, False], dtype="boolean"),
        }
    )
    return results, laps


def _tire_session_frames() -> tuple[pd.DataFrame, pd.DataFrame]:
    results, _ = _session_frames()
    drivers = ["NOR"] * 5 + ["VER"] * 5 + ["ANT"] * 4
    lap_numbers = list(range(1, 6)) + list(range(1, 6)) + list(range(1, 5))
    laps = pd.DataFrame(
        {
            "driver": drivers,
            "lap_number": pd.array(lap_numbers, dtype="Int64"),
            "lap_time_ns": pd.array(range(90, 90 + len(drivers)), dtype="Int64"),
            "lap_start_time_ns": pd.array(range(1, len(drivers) + 1), dtype="Int64"),
            "is_accurate": pd.array([True] * len(drivers), dtype="boolean"),
        }
    )
    return results, laps


def test_driver_options_are_classified_and_accurate_only() -> None:
    results, laps = _session_frames()

    options = driver_options(results, laps)

    assert [option.abbreviation for option in options] == ["NOR", "VER"]
    assert options[0].accurate_lap_numbers == (7, 9)
    assert options[0].label == "NOR — Lando Norris · McLaren"


def test_facade_loads_minimum_analysis_snapshot(loaded_session: LoadedSession) -> None:
    results, laps = _session_frames()
    platform = Mock()
    platform.ingestion.ingest.return_value = IngestionResult("session", "run", True, ())
    stored = Mock()
    stored.results.return_value = results
    stored.laps.return_value = laps
    stored.metadata = loaded_session.metadata
    platform.sessions.open.return_value = stored
    facade = LapAnalysisFacade(platform)
    key = SessionKey(2026, 1, "Q")

    loaded = facade.load_session(key)

    assert loaded.snapshot_reused is True
    assert [driver.abbreviation for driver in loaded.drivers] == ["NOR", "VER"]
    options = platform.ingestion.ingest.call_args.args[1]
    assert options.telemetry is True
    assert options.weather is False
    assert options.messages is False


def test_facade_rejects_session_without_accurate_laps(loaded_session: LoadedSession) -> None:
    results, laps = _session_frames()
    laps["is_accurate"] = False
    platform = Mock()
    platform.ingestion.ingest.return_value = IngestionResult("session", "run", False, ())
    stored = Mock()
    stored.results.return_value = results
    stored.laps.return_value = laps
    stored.metadata = loaded_session.metadata
    platform.sessions.open.return_value = stored

    with pytest.raises(LapNotFoundError, match="accurate timed lap"):
        LapAnalysisFacade(platform).load_session(SessionKey(2026, 1, "Q"))


def test_strategy_facade_rejects_red_flag_during_setup() -> None:
    platform = Mock()
    platform.ingestion.ingest.return_value = IngestionResult("session", "run", False, ())
    stored = Mock()
    stored.track_status.return_value = pd.DataFrame({"status": ["1", "5"]})
    platform.sessions.open.return_value = stored

    with pytest.raises(UnsupportedStrategySessionError, match="red-flag"):
        StrategyAnalysisFacade(platform).load_setup(SessionKey(2026, 1, "R"))


def test_tire_facade_exposes_only_race_and_sprint_sessions() -> None:
    platform = Mock()
    platform.session_discovery.list_available_events.return_value = (
        ScheduledEvent(
            2026,
            1,
            "Australian Grand Prix",
            "Australia",
            "Melbourne",
            (
                ScheduledSession(
                    SessionType.QUALIFYING,
                    "Qualifying",
                    pd.Timestamp("2026-03-07", tz="UTC"),
                ),
                ScheduledSession(
                    SessionType.SPRINT,
                    "Sprint",
                    pd.Timestamp("2026-03-08", tz="UTC"),
                ),
                ScheduledSession(
                    SessionType.RACE,
                    "Race",
                    pd.Timestamp("2026-03-09", tz="UTC"),
                ),
            ),
        ),
    )

    events = TireAnalysisFacade(platform).list_available_events(2026)

    assert len(events) == 1
    assert [session.session_type.value for session in events[0].sessions] == ["S", "R"]


@pytest.mark.parametrize(
    ("mode", "requires_weather"),
    [
        (DegradationMode.ADJUSTED, True),
        (DegradationMode.RAW, False),
    ],
)
def test_tire_facade_ingests_mode_specific_snapshot(
    mode: DegradationMode,
    requires_weather: bool,
) -> None:
    platform = Mock()
    platform.ingestion.ingest.return_value = IngestionResult("session", "run", True, ())
    platform.tire_model.analyze.return_value = object()
    facade = TireAnalysisFacade(platform)
    key = SessionKey(2026, 1, "R")

    run = facade.analyze(key, mode)

    assert run.snapshot_reused is True
    assert run.analysis is platform.tire_model.analyze.return_value
    options = platform.ingestion.ingest.call_args.args[1]
    assert options.telemetry is False
    assert options.weather is requires_weather
    assert options.messages is False
    config = platform.tire_model.analyze.call_args.args[1]
    assert config.mode is mode


def test_tire_facade_lists_drivers_from_lightweight_snapshot() -> None:
    results, laps = _tire_session_frames()
    platform = Mock()
    platform.ingestion.ingest.return_value = IngestionResult("session", "run", True, ())
    stored = Mock()
    stored.results.return_value = results
    stored.laps.return_value = laps
    platform.sessions.open.return_value = stored
    key = SessionKey(2026, 1, "R")

    drivers = TireAnalysisFacade(platform).list_drivers(key)

    assert [driver.abbreviation for driver in drivers] == ["NOR", "VER"]
    assert all(len(driver.accurate_lap_numbers) >= 5 for driver in drivers)
    options = platform.ingestion.ingest.call_args.args[1]
    assert options.telemetry is False
    assert options.weather is False
    assert options.messages is False


def test_tire_facade_runs_two_driver_models_from_one_snapshot() -> None:
    platform = Mock()
    platform.ingestion.ingest.return_value = IngestionResult("session", "run", False, ())
    first_analysis = object()
    second_analysis = object()
    platform.tire_model.analyze_driver.side_effect = (first_analysis, second_analysis)
    key = SessionKey(2026, 1, "R")

    runs = TireAnalysisFacade(platform).analyze_drivers(
        key,
        ("NOR", "VER"),
        DegradationMode.ADJUSTED,
    )

    assert [run.analysis for run in runs] == [first_analysis, second_analysis]
    assert not any(run.snapshot_reused for run in runs)
    platform.ingestion.ingest.assert_called_once()
    assert [call.args[1] for call in platform.tire_model.analyze_driver.call_args_list] == [
        "NOR",
        "VER",
    ]
    assert all(
        call.args[2].mode is DegradationMode.ADJUSTED
        for call in platform.tire_model.analyze_driver.call_args_list
    )

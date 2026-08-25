from __future__ import annotations

from unittest.mock import Mock

import pandas as pd
import pytest

from f1pi.analysis.models import DegradationMode
from f1pi.domain.exceptions import LapNotFoundError
from f1pi.domain.models import (
    IngestionResult,
    ScheduledEvent,
    ScheduledSession,
    SessionKey,
    SessionType,
)
from f1pi.ui.analysis_facade import LapAnalysisFacade, TireAnalysisFacade, driver_options
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

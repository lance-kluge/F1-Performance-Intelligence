from __future__ import annotations

from datetime import UTC, datetime

import pandas as pd
import pytest

from f1pi.domain.models import (
    DatasetKind,
    SessionMetadata,
    SessionType,
    SourceDataset,
    SourceSession,
)


@pytest.fixture
def metadata() -> SessionMetadata:
    return SessionMetadata(
        session_id="2022-01-bahrain-r",
        year=2022,
        round_number=1,
        event_name="Bahrain Grand Prix",
        country="Bahrain",
        location="Sakhir",
        session_type=SessionType.RACE,
        session_name="Race",
        session_date_utc=datetime(2022, 3, 20, 15, tzinfo=UTC),
        fastf1_version="3.8.3",
    )


@pytest.fixture
def source_session(metadata: SessionMetadata) -> SourceSession:
    date = pd.to_datetime(["2022-03-20T15:00:00Z", "2022-03-20T15:00:01Z"])
    datasets = (
        SourceDataset(
            DatasetKind.RESULTS,
            pd.DataFrame(
                {
                    "DriverNumber": ["16", "55"],
                    "Abbreviation": ["LEC", "SAI"],
                    "FullName": ["Charles Leclerc", "Carlos Sainz"],
                    "TeamName": ["Ferrari", "Ferrari"],
                    "Position": [1, 2],
                    "GridPosition": [1, 3],
                    "Status": ["Finished", "Finished"],
                }
            ),
        ),
        SourceDataset(
            DatasetKind.LAPS,
            pd.DataFrame(
                {
                    "Driver": ["LEC", "LEC"],
                    "DriverNumber": ["16", "16"],
                    "LapNumber": [1, 2],
                    "LapTime": pd.to_timedelta([95.1, 94.8], unit="s"),
                    "LapStartTime": pd.to_timedelta([0, 95.1], unit="s"),
                    "PitOutTime": pd.to_timedelta([None, None]),
                    "PitInTime": pd.to_timedelta([None, None]),
                    "Sector1Time": pd.to_timedelta([31.7, 31.6], unit="s"),
                    "Sector2Time": pd.to_timedelta([31.7, 31.6], unit="s"),
                    "Sector3Time": pd.to_timedelta([31.7, 31.6], unit="s"),
                    "Stint": [1, 1],
                    "Compound": ["SOFT", "SOFT"],
                    "TyreLife": [1.0, 2.0],
                    "FreshTyre": [True, True],
                    "IsAccurate": [True, True],
                    "Deleted": [False, False],
                }
            ),
        ),
        SourceDataset(
            DatasetKind.WEATHER,
            pd.DataFrame(
                {
                    "Time": pd.to_timedelta([0, 60], unit="s"),
                    "AirTemp": [24.0, 24.1],
                    "TrackTemp": [31.0, 31.1],
                    "Humidity": [48.0, 47.0],
                    "Pressure": [1012.0, 1012.1],
                    "Rainfall": [False, False],
                    "WindDirection": [210, 212],
                    "WindSpeed": [2.5, 2.6],
                }
            ),
        ),
        SourceDataset(
            DatasetKind.CAR_TELEMETRY,
            pd.DataFrame(
                {
                    "Date": date,
                    "SessionTime": pd.to_timedelta([0, 1], unit="s"),
                    "Speed": [0, 110],
                    "RPM": [5000, 9000],
                    "nGear": [1, 4],
                    "Throttle": [0, 104],
                    "Brake": [True, False],
                    "DRS": [0, 0],
                }
            ),
            "LEC",
        ),
        SourceDataset(
            DatasetKind.POSITION,
            pd.DataFrame(
                {
                    "Date": date,
                    "SessionTime": pd.to_timedelta([0, 1], unit="s"),
                    "X": [1, 2],
                    "Y": [3, 4],
                    "Z": [0, 0],
                    "Status": ["OnTrack", "OnTrack"],
                }
            ),
            "LEC",
        ),
        SourceDataset(
            DatasetKind.CIRCUIT_CORNERS,
            pd.DataFrame(
                {
                    "Number": [1],
                    "Letter": [""],
                    "X": [2.0],
                    "Y": [4.0],
                    "Angle": [0.0],
                    "Distance": [50.0],
                }
            ),
        ),
        SourceDataset(
            DatasetKind.TRACK_STATUS,
            pd.DataFrame(
                {
                    "Time": pd.to_timedelta([0], unit="s"),
                    "Status": ["1"],
                    "Message": ["AllClear"],
                }
            ),
        ),
        SourceDataset(
            DatasetKind.SESSION_STATUS,
            pd.DataFrame(
                {"Time": pd.to_timedelta([0], unit="s"), "Status": ["Started"]}
            ),
        ),
        SourceDataset(
            DatasetKind.RACE_CONTROL,
            pd.DataFrame({"Message": ["GREEN LIGHT - PIT EXIT OPEN"]}),
        ),
    )
    return SourceSession(metadata=metadata, datasets=datasets)

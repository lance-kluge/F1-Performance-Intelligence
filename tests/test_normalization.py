from __future__ import annotations

import pandas as pd
import pytest

from f1pi.domain import DatasetKind, SessionMetadata, SourceSession
from f1pi.exceptions import SchemaValidationError
from f1pi.normalization import normalize_frame, normalize_session, snake_case


def test_snake_case_handles_acronyms() -> None:
    assert snake_case("DriverNumber") == "driver_number"
    assert snake_case("nGear") == "n_gear"
    assert snake_case("DRS") == "drs"


def test_normalizes_and_validates_all_fixture_frames(source_session: SourceSession) -> None:
    datasets = normalize_session(source_session.metadata, source_session.datasets)
    assert datasets[0].kind is DatasetKind.SESSION
    laps = next(item.frame for item in datasets if item.kind is DatasetKind.LAPS)
    telemetry = next(item.frame for item in datasets if item.kind is DatasetKind.CAR_TELEMETRY)
    assert str(laps["lap_time_ns"].dtype) == "Int64"
    assert str(laps["fresh_tyre"].dtype) == "boolean"
    assert "date_utc_ns" in telemetry
    assert telemetry["driver"].unique().tolist() == ["LEC"]
    assert telemetry["throttle_raw"].tolist() == [0.0, 104.0]
    assert telemetry["throttle"].iloc[0] == 0.0
    assert pd.isna(telemetry["throttle"].iloc[1])


def test_results_keep_grid_positions_numeric(metadata: SessionMetadata) -> None:
    frame = pd.DataFrame(
        {
            "DriverNumber": ["16"],
            "Abbreviation": ["LEC"],
            "FullName": ["Charles Leclerc"],
            "TeamName": ["Ferrari"],
            "Position": [1.0],
            "GridPosition": [2.0],
            "Status": ["Finished"],
        }
    )

    normalized = normalize_frame(DatasetKind.RESULTS, frame, metadata)

    assert pd.api.types.is_numeric_dtype(normalized["grid_position"])
    assert normalized["grid_position"].tolist() == [2.0]


def test_results_store_finishing_positions_as_nullable_integers(
    metadata: SessionMetadata,
) -> None:
    frame = pd.DataFrame(
        {
            "DriverNumber": ["16", "55"],
            "Abbreviation": ["LEC", "SAI"],
            "FullName": ["Charles Leclerc", "Carlos Sainz"],
            "TeamName": ["Ferrari", "Ferrari"],
            "Position": [1.0, None],
            "GridPosition": [1.0, 3.0],
            "Status": ["Finished", "Retired"],
        }
    )

    normalized = normalize_frame(DatasetKind.RESULTS, frame, metadata)

    assert str(normalized["position"].dtype) == "Int64"
    assert normalized["position"].iloc[0] == 1
    assert pd.isna(normalized["position"].iloc[1])


def test_validation_reports_missing_columns(metadata: SessionMetadata) -> None:
    with pytest.raises(SchemaValidationError, match="laps failed schema validation"):
        normalize_frame(DatasetKind.LAPS, pd.DataFrame({"Driver": ["LEC"]}), metadata)


def test_validation_rejects_invalid_telemetry_range(metadata: SessionMetadata) -> None:
    frame = pd.DataFrame(
        {
            "Date": pd.to_datetime(["2022-03-20T15:00:00Z"]),
            "SessionTime": pd.to_timedelta([0], unit="s"),
            "Speed": [-1.0],
            "RPM": [1000.0],
            "nGear": [1.0],
            "Throttle": [120.0],
            "Brake": [False],
            "DRS": [0.0],
        }
    )
    with pytest.raises(SchemaValidationError, match="car_telemetry"):
        normalize_frame(DatasetKind.CAR_TELEMETRY, frame, metadata, "LEC")

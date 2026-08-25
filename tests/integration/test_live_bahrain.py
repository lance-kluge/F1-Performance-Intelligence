from __future__ import annotations

from pathlib import Path

import pytest

from f1pi.analysis import LapSelection
from f1pi.composition import build_platform
from f1pi.config import PlatformSettings
from f1pi.domain.models import DatasetKind, LoadOptions, SessionKey


@pytest.mark.live
def test_2022_bahrain_race_end_to_end(tmp_path: Path) -> None:
    platform = build_platform(
        PlatformSettings(
            data_dir=tmp_path / "data",
            fastf1_cache_dir=tmp_path / "fastf1-cache",
        )
    )
    key = SessionKey(2022, "Bahrain", "R")
    native = platform.fastf1.load(
        key, LoadOptions(telemetry=False, weather=False, messages=False)
    )
    assert native.laps.pick_drivers("LEC").pick_fastest()["Driver"] == "LEC"

    first = platform.ingestion.ingest(key)
    session = platform.sessions.open(key)

    assert session.metadata.event_name == "Bahrain Grand Prix"
    results = session.results().sort_values("position")
    assert results.iloc[0]["abbreviation"] == "LEC"
    assert not session.laps().empty
    assert not session.weather().empty
    assert not session.car_telemetry().empty
    assert not session.position().empty
    assert not session.frame(DatasetKind.TRACK_STATUS).empty
    assert not session.frame(DatasetKind.SESSION_STATUS).empty
    assert not session.frame(DatasetKind.RACE_CONTROL).empty

    comparison = platform.lap_analysis.compare(
        key,
        LapSelection.fastest("LEC"),
        LapSelection.fastest("SAI"),
    )
    assert comparison.sections
    assert sum(section.delta_seconds for section in comparison.sections) == pytest.approx(
        comparison.delta_seconds,
        abs=1e-9,
    )
    assert comparison.quality.reconciliation_error_seconds < 1e-9

    tire_analysis = platform.tire_model.analyze(key)
    assert tire_analysis.estimates
    assert tire_analysis.validation.fold_count >= 2
    for estimate in tire_analysis.estimates:
        assert estimate.confidence_lower_seconds_per_lap <= estimate.seconds_per_lap
        assert estimate.seconds_per_lap <= estimate.confidence_upper_seconds_per_lap
    assert (
        tire_analysis.curves["prediction_lower_seconds"]
        <= tire_analysis.curves["prediction_upper_seconds"]
    ).all()

    driver_tire_analysis = platform.tire_model.analyze_driver(key, "LEC")
    assert driver_tire_analysis.driver == "LEC"
    assert driver_tire_analysis.estimates
    assert driver_tire_analysis.observations["driver"].eq("LEC").all()

    second = platform.ingestion.ingest(key)
    assert second.snapshot_reused
    assert second.run_id == first.run_id
    refreshed = platform.ingestion.ingest(key, LoadOptions(refresh_upstream=True))
    assert not refreshed.snapshot_reused
    assert refreshed.run_id != first.run_id

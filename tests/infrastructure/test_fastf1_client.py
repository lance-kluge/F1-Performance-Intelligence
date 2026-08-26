from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest
from fastf1.core import Laps
from fastf1.exceptions import DataNotLoadedError

from f1pi.domain.exceptions import (
    InvalidSessionError,
    UpstreamRateLimitError,
    UpstreamUnavailableError,
)
from f1pi.domain.models import DatasetKind, LoadOptions, SessionKey, SessionType
from f1pi.infrastructure import fastf1_client
from f1pi.infrastructure.fastf1_client import FastF1Client


class FakeFastF1Session:
    def __init__(self) -> None:
        self.event = pd.Series(
            {
                "EventName": "Bahrain Grand Prix",
                "RoundNumber": 1,
                "Country": "Bahrain",
                "Location": "Sakhir",
            }
        )
        self.name = "Race"
        self.date = pd.Timestamp("2022-03-20T15:00:00Z")
        self.results = pd.DataFrame(
            {"DriverNumber": ["16"], "Abbreviation": ["LEC"]}
        )
        self._laps = pd.DataFrame()
        self.laps_loaded = True
        self.laps_read_count = 0
        self.unload_laps_after_first_read = False
        self.track_status = pd.DataFrame()
        self.session_status = pd.DataFrame()
        self.weather_data = pd.DataFrame()
        self.race_control_messages = pd.DataFrame()
        telemetry = pd.DataFrame({"Speed": [100.0]})
        self.car_data = {"16": telemetry}
        self.pos_data = {"16": pd.DataFrame({"X": [1.0]})}
        self.load_options: dict[str, bool] = {}

    def load(self, **options: bool) -> None:
        self.load_options = options

    @property
    def laps(self) -> pd.DataFrame:
        if not self.laps_loaded or (
            self.unload_laps_after_first_read and self.laps_read_count > 0
        ):
            raise DataNotLoadedError("laps were not loaded")
        self.laps_read_count += 1
        return self._laps

    def get_circuit_info(self) -> SimpleNamespace:
        return SimpleNamespace(
            rotation=27.0,
            corners=pd.DataFrame(
                {
                    "Number": [1],
                    "Letter": [""],
                    "X": [1.0],
                    "Y": [1.0],
                    "Angle": [0.0],
                    "Distance": [100.0],
                }
            )
        )


def test_client_returns_native_fastf1_session(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    session = FakeFastF1Session()
    monkeypatch.setattr(fastf1_client.fastf1, "get_session", lambda *args: session)
    cache_options: dict[str, object] = {}

    def enable_cache(path: str, **options: object) -> None:
        cache_options.update({"path": path, **options})

    monkeypatch.setattr(fastf1_client.fastf1.Cache, "enable_cache", enable_cache)
    client = FastF1Client(tmp_path / "cache")
    loaded = client.load(
        SessionKey(2022, "Bahrain", "R"),
        LoadOptions(telemetry=False, weather=False, messages=False),
    )
    assert loaded is session
    assert session.load_options == {
        "laps": True,
        "telemetry": False,
        "weather": False,
        "messages": False,
    }
    assert cache_options == {
        "path": str(tmp_path / "cache"),
        "force_renew": False,
    }


def test_client_can_force_fastf1_cache_renewal(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    session = FakeFastF1Session()
    cache_options: dict[str, object] = {}

    def enable_cache(path: str, **options: object) -> None:
        cache_options.update({"path": path, **options})

    monkeypatch.setattr(fastf1_client.fastf1, "get_session", lambda *args: session)
    monkeypatch.setattr(fastf1_client.fastf1.Cache, "enable_cache", enable_cache)

    FastF1Client(tmp_path / "cache").load(
        SessionKey(2022, "Bahrain", "R"), LoadOptions(refresh_upstream=True)
    )

    assert cache_options["force_renew"] is True


def test_client_maps_unloaded_laps_to_upstream_unavailable(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    session = FakeFastF1Session()
    session.laps_loaded = False
    monkeypatch.setattr(fastf1_client.fastf1, "get_session", lambda *args: session)
    monkeypatch.setattr(
        fastf1_client.fastf1.Cache, "enable_cache", lambda path, **options: None
    )

    with pytest.raises(UpstreamUnavailableError):
        FastF1Client(tmp_path / "cache").load(SessionKey(2022, "Bahrain", "R"))


def test_client_fetch_maps_laps_that_become_unavailable_after_loading(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    session = FakeFastF1Session()
    session.unload_laps_after_first_read = True
    monkeypatch.setattr(fastf1_client.fastf1, "get_session", lambda *args: session)
    monkeypatch.setattr(
        fastf1_client.fastf1.Cache, "enable_cache", lambda path, **options: None
    )

    with pytest.raises(UpstreamUnavailableError):
        FastF1Client(tmp_path / "cache").fetch(SessionKey(2022, "Bahrain", "R"), LoadOptions())


def test_client_normalizes_supported_event_schedule(monkeypatch: pytest.MonkeyPatch) -> None:
    schedule = pd.DataFrame(
        {
            "RoundNumber": [0, 1, 2],
            "EventName": [
                "Pre-Season Testing",
                "Australian Grand Prix",
                "Chinese Grand Prix",
            ],
            "Country": ["Bahrain", "Australia", "China"],
            "Location": ["Sakhir", "Melbourne", "Shanghai"],
            "F1ApiSupport": [False, True, False],
            "Session1": ["Practice 1", "Practice 1", "Practice 1"],
            "Session1DateUtc": pd.to_datetime(
                ["2026-02-20 00:00", "2026-03-06 00:00", "2026-03-13 00:00"]
            ),
            "Session2": ["Practice 2", "Sprint Qualifying", "Practice 2"],
            "Session2DateUtc": pd.to_datetime(
                ["2026-02-21 00:00", "2026-03-06 05:00", "2026-03-13 05:00"]
            ),
            "Session3": [pd.NA, "Mystery Session", pd.NA],
            "Session3DateUtc": pd.to_datetime([pd.NaT, "2026-03-07 00:00", pd.NaT]),
            "Session4": [pd.NA, "Qualifying", pd.NA],
            "Session4DateUtc": pd.to_datetime([pd.NaT, "2026-03-07 05:00", pd.NaT]),
            "Session5": [pd.NA, "Race", pd.NA],
            "Session5DateUtc": pd.to_datetime([pd.NaT, "2026-03-08 04:00", pd.NaT]),
        }
    )
    monkeypatch.setattr(
        fastf1_client.fastf1,
        "get_event_schedule",
        lambda *args, **kwargs: schedule,
    )

    events = FastF1Client(Path("cache")).events(2026)

    assert len(events) == 1
    assert events[0].round_number == 1
    assert [session.session_type for session in events[0].sessions] == [
        SessionType.FP1,
        SessionType.SPRINT_QUALIFYING,
        SessionType.QUALIFYING,
        SessionType.RACE,
    ]
    assert all(session.starts_at_utc.tzinfo is not None for session in events[0].sessions)


@pytest.mark.parametrize(
    "upstream,expected",
    [
        (fastf1_client.RateLimitExceededError("slow down"), UpstreamRateLimitError),
        (ValueError("bad year"), InvalidSessionError),
        (fastf1_client.RequestException("offline"), UpstreamUnavailableError),
    ],
)
def test_schedule_maps_upstream_errors(
    monkeypatch: pytest.MonkeyPatch,
    upstream: Exception,
    expected: type[Exception],
) -> None:
    def fail(*args: object, **kwargs: object) -> None:
        raise upstream

    monkeypatch.setattr(fastf1_client.fastf1, "get_event_schedule", fail)

    with pytest.raises(expected):
        FastF1Client(Path("cache")).events(2026)


def test_client_detaches_frames_for_ingestion(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    session = FakeFastF1Session()
    monkeypatch.setattr(fastf1_client.fastf1, "get_session", lambda *args: session)
    monkeypatch.setattr(
        fastf1_client.fastf1.Cache, "enable_cache", lambda path, **options: None
    )
    result = FastF1Client(tmp_path / "cache").fetch(
        SessionKey(2022, "Bahrain", "R"), LoadOptions()
    )
    assert result.metadata.session_id == "2022-01-bahrain-r"
    car = next(item for item in result.datasets if item.kind is DatasetKind.CAR_TELEMETRY)
    corners = next(
        item for item in result.datasets if item.kind is DatasetKind.CIRCUIT_CORNERS
    )
    assert car.partition == "LEC"
    assert type(car.frame) is pd.DataFrame
    assert corners.frame.iloc[0]["Number"] == 1
    assert corners.frame.iloc[0]["Rotation"] == 27.0


def test_client_omits_unavailable_optional_circuit_metadata(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    session = FakeFastF1Session()

    def unavailable_circuit_info() -> None:
        raise AttributeError("'NoneType' object has no attribute 'add_marker_distance'")

    monkeypatch.setattr(session, "get_circuit_info", unavailable_circuit_info)
    monkeypatch.setattr(fastf1_client.fastf1, "get_session", lambda *args: session)
    monkeypatch.setattr(
        fastf1_client.fastf1.Cache, "enable_cache", lambda path, **options: None
    )

    result = FastF1Client(tmp_path / "cache").fetch(
        SessionKey(2022, "Bahrain", "R"), LoadOptions()
    )

    assert any(item.kind is DatasetKind.CAR_TELEMETRY for item in result.datasets)
    assert all(item.kind is not DatasetKind.CIRCUIT_CORNERS for item in result.datasets)


def test_snapshot_frame_detaches_fastf1_session_behavior() -> None:
    upstream = Laps({"Driver": ["LEC"], "LapNumber": [1.0]}, session=object())

    snapshot = fastf1_client._snapshot_frame(upstream)

    assert type(snapshot) is pd.DataFrame
    assert not hasattr(snapshot, "session")
    snapshot.loc[0, "Driver"] = "SAI"
    assert upstream.loc[0, "Driver"] == "LEC"


@pytest.mark.parametrize(
    "upstream,expected",
    [
        (fastf1_client.RateLimitExceededError("slow down"), UpstreamRateLimitError),
        (fastf1_client.FastF1InvalidSessionError("bad session"), InvalidSessionError),
    ],
)
def test_adapter_maps_upstream_errors(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    upstream: Exception,
    expected: type[Exception],
) -> None:
    def fail(*args: object) -> None:
        raise upstream

    monkeypatch.setattr(fastf1_client.fastf1, "get_session", fail)
    monkeypatch.setattr(
        fastf1_client.fastf1.Cache, "enable_cache", lambda path, **options: None
    )
    with pytest.raises(expected):
        FastF1Client(tmp_path / "cache").load(SessionKey(2022, 1, "R"))

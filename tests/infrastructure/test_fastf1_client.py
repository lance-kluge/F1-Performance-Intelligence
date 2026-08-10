from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest
from fastf1.core import Laps

from f1pi.domain.exceptions import InvalidSessionError, UpstreamRateLimitError
from f1pi.domain.models import DatasetKind, LoadOptions, SessionKey
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
        self.laps = pd.DataFrame()
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

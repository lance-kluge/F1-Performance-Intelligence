"""Public FastF1 client and normalized ingestion adapter."""

from __future__ import annotations

from datetime import UTC
from pathlib import Path

import fastf1
import pandas as pd
from fastf1._api import SessionNotAvailableError
from fastf1.core import Session
from fastf1.exceptions import (
    InvalidSessionError as FastF1InvalidSessionError,
)
from fastf1.exceptions import (
    NoLapDataError,
    RateLimitExceededError,
)

from f1pi.domain import (
    DatasetKind,
    LoadOptions,
    SessionKey,
    SessionMetadata,
    SessionType,
    SourceDataset,
    SourceSession,
)
from f1pi.exceptions import (
    InvalidSessionError,
    UpstreamRateLimitError,
    UpstreamUnavailableError,
)


class FastF1Client:
    """Load native FastF1 sessions and create persistence-ready snapshots."""

    def __init__(self, cache_dir: Path) -> None:
        self._cache_dir = cache_dir

    def load(self, key: SessionKey, options: LoadOptions | None = None) -> Session:
        """Return a fully usable native :class:`fastf1.core.Session`."""
        options = options or LoadOptions()
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        fastf1.Cache.enable_cache(
            str(self._cache_dir), force_renew=options.refresh_upstream
        )
        try:
            session = fastf1.get_session(key.year, key.event, key.session_type.value)
            session.load(
                laps=True,
                telemetry=options.telemetry,
                weather=options.weather,
                messages=options.messages,
            )
        except RateLimitExceededError as error:
            raise UpstreamRateLimitError(str(error)) from error
        except FastF1InvalidSessionError as error:
            raise InvalidSessionError(str(error)) from error
        except (SessionNotAvailableError, NoLapDataError) as error:
            raise UpstreamUnavailableError(str(error)) from error
        return session

    def fetch(self, key: SessionKey, options: LoadOptions) -> SourceSession:
        """Load a native session and detach frames for normalized persistence."""
        session = self.load(key, options)
        event = session.event
        event_name = str(event["EventName"])
        round_number = int(event["RoundNumber"])
        session_id = _canonical_session_id(
            year=key.year,
            round_number=round_number,
            event_name=event_name,
            session_type=key.session_type,
        )
        session_date = pd.Timestamp(session.date).to_pydatetime()
        if session_date.tzinfo is None:
            session_date = session_date.replace(tzinfo=UTC)
        else:
            session_date = session_date.astimezone(UTC)
        metadata = SessionMetadata(
            session_id=session_id,
            year=key.year,
            round_number=round_number,
            event_name=event_name,
            country=str(event.get("Country", "")),
            location=str(event.get("Location", "")),
            session_type=key.session_type,
            session_name=str(session.name),
            session_date_utc=session_date,
            fastf1_version=fastf1.__version__,
        )

        results = _snapshot_frame(session.results)
        datasets = [
            SourceDataset(DatasetKind.RESULTS, results),
            SourceDataset(DatasetKind.LAPS, _snapshot_frame(session.laps)),
            SourceDataset(DatasetKind.TRACK_STATUS, _snapshot_frame(session.track_status)),
            SourceDataset(DatasetKind.SESSION_STATUS, _snapshot_frame(session.session_status)),
        ]
        if options.weather:
            datasets.append(
                SourceDataset(DatasetKind.WEATHER, _snapshot_frame(session.weather_data))
            )
        if options.messages:
            datasets.append(
                SourceDataset(
                    DatasetKind.RACE_CONTROL,
                    _snapshot_frame(session.race_control_messages),
                )
            )
        if options.telemetry:
            abbreviations = _driver_abbreviations(results)
            for number, frame in session.car_data.items():
                driver = abbreviations.get(str(number), str(number))
                datasets.append(
                    SourceDataset(DatasetKind.CAR_TELEMETRY, _snapshot_frame(frame), driver)
                )
            for number, frame in session.pos_data.items():
                driver = abbreviations.get(str(number), str(number))
                datasets.append(
                    SourceDataset(DatasetKind.POSITION, _snapshot_frame(frame), driver)
                )
        return SourceSession(metadata=metadata, datasets=tuple(datasets))


def _driver_abbreviations(results: pd.DataFrame) -> dict[str, str]:
    if "DriverNumber" not in results or "Abbreviation" not in results:
        return {}
    return {
        str(number): str(abbreviation)
        for number, abbreviation in zip(
            results["DriverNumber"], results["Abbreviation"], strict=False
        )
    }


def _snapshot_frame(frame: pd.DataFrame) -> pd.DataFrame:
    """Detach session-bound FastF1 behavior from a persistence snapshot."""
    return pd.DataFrame(frame).copy(deep=True)


def _canonical_session_id(
    year: int, round_number: int, event_name: str, session_type: SessionType
) -> str:
    event_slug = "-".join(part for part in event_name.lower().replace("grand prix", "").split())
    return f"{year}-{round_number:02d}-{event_slug}-{session_type.value.lower()}"

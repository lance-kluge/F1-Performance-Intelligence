"""Public FastF1 client and normalized ingestion adapter."""

from __future__ import annotations

import logging
from datetime import UTC
from pathlib import Path

import fastf1
import pandas as pd
from fastf1._api import SessionNotAvailableError
from fastf1.core import Session
from fastf1.exceptions import (
    DataNotLoadedError,
    NoLapDataError,
    RateLimitExceededError,
)
from fastf1.exceptions import (
    InvalidSessionError as FastF1InvalidSessionError,
)
from requests import RequestException

from f1pi.domain.exceptions import (
    InvalidSessionError,
    UpstreamRateLimitError,
    UpstreamUnavailableError,
)
from f1pi.domain.models import (
    DatasetKind,
    LoadOptions,
    ScheduledEvent,
    ScheduledSession,
    SessionKey,
    SessionMetadata,
    SessionType,
    SourceDataset,
    SourceSession,
)
from f1pi.infrastructure.logging import log_event


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
            # FastF1 can return from ``Session.load`` without lap data when an
            # upstream timing source is unavailable. Access it here so callers
            # receive a stable domain error instead of a later property error.
            _ = session.laps
        except RateLimitExceededError as error:
            raise UpstreamRateLimitError(str(error)) from error
        except FastF1InvalidSessionError as error:
            raise InvalidSessionError(str(error)) from error
        except (DataNotLoadedError, SessionNotAvailableError, NoLapDataError) as error:
            raise UpstreamUnavailableError(str(error)) from error
        return session

    def events(self, year: int) -> tuple[ScheduledEvent, ...]:
        """Return the normalized, telemetry-capable championship schedule."""
        try:
            schedule = fastf1.get_event_schedule(year, include_testing=False)
        except RateLimitExceededError as error:
            raise UpstreamRateLimitError(str(error)) from error
        except ValueError as error:
            raise InvalidSessionError(str(error)) from error
        except RequestException as error:
            raise UpstreamUnavailableError(str(error)) from error

        events: list[ScheduledEvent] = []
        for _, event in schedule.iterrows():
            round_number = int(event["RoundNumber"])
            if round_number < 1 or not bool(event.get("F1ApiSupport", False)):
                continue
            sessions = tuple(
                session
                for position in range(1, 6)
                if (session := _scheduled_session(event, position)) is not None
            )
            if sessions:
                events.append(
                    ScheduledEvent(
                        year=year,
                        round_number=round_number,
                        event_name=str(event["EventName"]),
                        country=str(event.get("Country", "")),
                        location=str(event.get("Location", "")),
                        sessions=sessions,
                    )
                )
        return tuple(events)

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
        try:
            laps = _snapshot_frame(session.laps)
        except DataNotLoadedError as error:
            raise UpstreamUnavailableError(str(error)) from error
        datasets = [
            SourceDataset(DatasetKind.RESULTS, results),
            SourceDataset(DatasetKind.LAPS, laps),
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
            try:
                circuit_info = session.get_circuit_info()
            except (AttributeError, KeyError) as error:
                # FastF1 derives marker distances from the fastest lap's merged
                # telemetry. Missing columns (for example Date) can break this
                # optional enrichment even when the session data loaded.
                log_event(
                    logging.getLogger(__name__),
                    logging.WARNING,
                    "optional circuit metadata unavailable",
                    session_id=session_id,
                    error_type=type(error).__name__,
                    error=str(error),
                )
                circuit_info = None
            if circuit_info is not None and not circuit_info.corners.empty:
                datasets.append(
                    SourceDataset(
                        DatasetKind.CIRCUIT_CORNERS,
                        _circuit_corners_snapshot(
                            circuit_info.corners, circuit_info.rotation
                        ),
                    )
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


_SCHEDULE_SESSION_TYPES = {
    "Practice 1": SessionType.FP1,
    "Practice 2": SessionType.FP2,
    "Practice 3": SessionType.FP3,
    "Qualifying": SessionType.QUALIFYING,
    "Sprint": SessionType.SPRINT,
    "Sprint Shootout": SessionType.SPRINT_SHOOTOUT,
    "Sprint Qualifying": SessionType.SPRINT_QUALIFYING,
    "Race": SessionType.RACE,
}


def _scheduled_session(event: pd.Series, position: int) -> ScheduledSession | None:
    name = event.get(f"Session{position}")
    starts_at = event.get(f"Session{position}DateUtc")
    if pd.isna(name) or pd.isna(starts_at):
        return None
    session_type = _SCHEDULE_SESSION_TYPES.get(str(name))
    if session_type is None:
        return None
    timestamp = pd.Timestamp(starts_at).to_pydatetime()
    return ScheduledSession(session_type, str(name), timestamp)


def _snapshot_frame(frame: pd.DataFrame) -> pd.DataFrame:
    """Detach session-bound FastF1 behavior from a persistence snapshot."""
    return pd.DataFrame(frame).copy(deep=True)


def _circuit_corners_snapshot(
    corners: pd.DataFrame, rotation: float
) -> pd.DataFrame:
    """Preserve the transform needed to align position data with corner markers."""
    snapshot = _snapshot_frame(corners)
    snapshot["Rotation"] = float(rotation)
    return snapshot


def _canonical_session_id(
    year: int, round_number: int, event_name: str, session_type: SessionType
) -> str:
    event_slug = "-".join(part for part in event_name.lower().replace("grand prix", "").split())
    return f"{year}-{round_number:02d}-{event_slug}-{session_type.value.lower()}"

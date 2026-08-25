"""Small immutable domain types shared by ports and services."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any

import pandas as pd

FIRST_CHAMPIONSHIP_YEAR = 1950
FIRST_ROUND_NUMBER = 1


class SessionType(StrEnum):
    FP1 = "FP1"
    FP2 = "FP2"
    FP3 = "FP3"
    QUALIFYING = "Q"
    SPRINT = "S"
    SPRINT_SHOOTOUT = "SS"
    SPRINT_QUALIFYING = "SQ"
    RACE = "R"

    @classmethod
    def parse(cls, value: SessionType | str) -> SessionType:
        if isinstance(value, cls):
            return value
        aliases = {
            "QUALIFYING": "Q",
            "RACE": "R",
            "SPRINT": "S",
            "SPRINT SHOOTOUT": "SS",
            "SPRINT QUALIFYING": "SQ",
        }
        normalized = aliases.get(value.strip().upper(), value.strip().upper())
        return cls(normalized)


@dataclass(frozen=True, slots=True)
class ScheduledSession:
    """One normalized session advertised by the upstream event schedule."""

    session_type: SessionType
    name: str
    starts_at_utc: datetime

    def __post_init__(self) -> None:
        starts_at = self.starts_at_utc
        if starts_at.tzinfo is None:
            starts_at = starts_at.replace(tzinfo=UTC)
        else:
            starts_at = starts_at.astimezone(UTC)
        object.__setattr__(self, "starts_at_utc", starts_at)


@dataclass(frozen=True, slots=True)
class ScheduledEvent:
    """A championship event and its telemetry-capable sessions."""

    year: int
    round_number: int
    event_name: str
    country: str
    location: str
    sessions: tuple[ScheduledSession, ...]


@dataclass(frozen=True, slots=True, init=False)
class SessionKey:
    year: int
    event: int | str
    session_type: SessionType

    def __init__(
        self, year: int, event: int | str, session_type: SessionType | str
    ) -> None:
        if year < FIRST_CHAMPIONSHIP_YEAR:
            raise ValueError(f"year must be {FIRST_CHAMPIONSHIP_YEAR} or later")
        if isinstance(event, int):
            if event < FIRST_ROUND_NUMBER:
                raise ValueError(
                    f"event round number must be {FIRST_ROUND_NUMBER} or greater"
                )
        elif not event.strip():
            raise ValueError("event name must not be empty")
        object.__setattr__(self, "year", year)
        object.__setattr__(self, "event", event)
        object.__setattr__(self, "session_type", SessionType.parse(session_type))

    @property
    def alias_id(self) -> str:
        event = str(self.event).strip().lower()
        event = re.sub(r"[^a-z0-9]+", "-", event).strip("-")
        return f"{self.year}:{event}:{self.session_type.value.lower()}"


class DatasetKind(StrEnum):
    SESSION = "session"
    RESULTS = "results"
    LAPS = "laps"
    WEATHER = "weather"
    CAR_TELEMETRY = "car_telemetry"
    POSITION = "position"
    CIRCUIT_CORNERS = "circuit_corners"
    TRACK_STATUS = "track_status"
    SESSION_STATUS = "session_status"
    RACE_CONTROL = "race_control"


class RunStatus(StrEnum):
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class LoadOptions:
    telemetry: bool = True
    weather: bool = True
    messages: bool = True
    rebuild_snapshot: bool = False
    refresh_upstream: bool = False

    @property
    def requires_ingestion(self) -> bool:
        """Return whether an existing analytical snapshot must be bypassed."""
        return self.rebuild_snapshot or self.refresh_upstream

    def required_dataset_kinds(self) -> frozenset[DatasetKind]:
        """Return the persisted datasets required to satisfy this load."""
        required = {
            DatasetKind.SESSION,
            DatasetKind.RESULTS,
            DatasetKind.LAPS,
            DatasetKind.TRACK_STATUS,
            DatasetKind.SESSION_STATUS,
        }
        if self.telemetry:
            required.update({DatasetKind.CAR_TELEMETRY, DatasetKind.POSITION})
        if self.weather:
            required.add(DatasetKind.WEATHER)
        if self.messages:
            required.add(DatasetKind.RACE_CONTROL)
        return frozenset(required)


@dataclass(frozen=True, slots=True)
class SessionMetadata:
    session_id: str
    year: int
    round_number: int
    event_name: str
    country: str
    location: str
    session_type: SessionType
    session_name: str
    session_date_utc: datetime
    fastf1_version: str
    schema_version: int = 3

    def __post_init__(self) -> None:
        if self.session_date_utc.tzinfo is None:
            object.__setattr__(
                self, "session_date_utc", self.session_date_utc.replace(tzinfo=UTC)
            )


@dataclass(frozen=True, slots=True)
class SourceDataset:
    kind: DatasetKind
    frame: pd.DataFrame
    partition: str | None = None


@dataclass(frozen=True, slots=True)
class SourceSession:
    metadata: SessionMetadata
    datasets: tuple[SourceDataset, ...]


@dataclass(frozen=True, slots=True)
class Artifact:
    kind: DatasetKind
    relative_path: Path
    row_count: int
    partition: str | None = None


@dataclass(frozen=True, slots=True)
class CatalogSession:
    metadata: SessionMetadata
    active_run_id: str
    ingested_at: datetime


@dataclass(frozen=True, slots=True)
class IngestionResult:
    session_id: str
    run_id: str
    snapshot_reused: bool
    artifacts: tuple[Artifact, ...]


def metadata_record(metadata: SessionMetadata) -> dict[str, Any]:
    """Return the stable one-row representation persisted as Parquet."""
    return {
        "session_id": metadata.session_id,
        "year": metadata.year,
        "round_number": metadata.round_number,
        "event_name": metadata.event_name,
        "country": metadata.country,
        "location": metadata.location,
        "session_type": metadata.session_type.value,
        "session_name": metadata.session_name,
        "session_date_utc": metadata.session_date_utc,
        "fastf1_version": metadata.fastf1_version,
        "schema_version": metadata.schema_version,
    }

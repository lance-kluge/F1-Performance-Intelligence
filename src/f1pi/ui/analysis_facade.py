"""Narrow application facade consumed by the Streamlit workspace."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

import pandas as pd

from f1pi.analysis.models import (
    DegradationMode,
    LapComparison,
    LapSelection,
    TireModelConfig,
)
from f1pi.domain.exceptions import LapNotFoundError
from f1pi.domain.models import (
    LoadOptions,
    ScheduledEvent,
    SessionKey,
    SessionType,
)
from f1pi.ui.models import DriverOption, LoadedSession, TireAnalysisRun

if TYPE_CHECKING:
    from f1pi.composition import Platform


class AnalysisFacade(Protocol):
    def list_available_events(self, year: int) -> tuple[ScheduledEvent, ...]: ...

    def load_session(self, key: SessionKey) -> LoadedSession: ...

    def compare(
        self,
        key: SessionKey,
        lap_a: LapSelection,
        lap_b: LapSelection,
    ) -> LapComparison: ...


class TireDegradationFacade(Protocol):
    def list_available_events(self, year: int) -> tuple[ScheduledEvent, ...]: ...

    def analyze(self, key: SessionKey, mode: DegradationMode) -> TireAnalysisRun: ...


class LapAnalysisFacade:
    """Adapt composed platform services into UI-ready records."""

    def __init__(self, platform: Platform) -> None:
        self._platform = platform

    def list_available_events(self, year: int) -> tuple[ScheduledEvent, ...]:
        return self._platform.session_discovery.list_available_events(year)

    def load_session(self, key: SessionKey) -> LoadedSession:
        ingestion = self._platform.ingestion.ingest(
            key,
            LoadOptions(telemetry=True, weather=False, messages=False),
        )
        session = self._platform.sessions.open(key)
        drivers = driver_options(session.results(), session.laps())
        if not drivers:
            raise LapNotFoundError("the session does not contain an accurate timed lap")
        return LoadedSession(
            key=key,
            metadata=session.metadata,
            drivers=drivers,
            snapshot_reused=ingestion.snapshot_reused,
        )

    def compare(
        self,
        key: SessionKey,
        lap_a: LapSelection,
        lap_b: LapSelection,
    ) -> LapComparison:
        return self._platform.lap_analysis.compare(key, lap_a, lap_b)


class TireAnalysisFacade:
    """Adapt tire-model services into a small UI-focused interface."""

    def __init__(self, platform: Platform) -> None:
        self._platform = platform

    def list_available_events(self, year: int) -> tuple[ScheduledEvent, ...]:
        events = self._platform.session_discovery.list_available_events(year)
        supported_types = {SessionType.RACE, SessionType.SPRINT}
        supported_events = []
        for event in events:
            sessions = tuple(
                session for session in event.sessions if session.session_type in supported_types
            )
            if sessions:
                supported_events.append(
                    ScheduledEvent(
                        year=event.year,
                        round_number=event.round_number,
                        event_name=event.event_name,
                        country=event.country,
                        location=event.location,
                        sessions=sessions,
                    )
                )
        return tuple(supported_events)

    def analyze(self, key: SessionKey, mode: DegradationMode) -> TireAnalysisRun:
        ingestion = self._platform.ingestion.ingest(
            key,
            LoadOptions(telemetry=False, weather=True, messages=False),
        )
        analysis = self._platform.tire_model.analyze(key, TireModelConfig(mode=mode))
        return TireAnalysisRun(analysis=analysis, snapshot_reused=ingestion.snapshot_reused)


def driver_options(results: pd.DataFrame, laps: pd.DataFrame) -> tuple[DriverOption, ...]:
    """Build classified driver choices with accurate, timed lap numbers."""
    eligible = laps.loc[
        laps["is_accurate"].fillna(False)
        & laps["lap_time_ns"].notna()
        & laps["lap_start_time_ns"].notna()
    ]
    lap_numbers = {
        str(driver).upper(): tuple(sorted({int(number) for number in group["lap_number"]}))
        for driver, group in eligible.groupby("driver")
    }
    ordered_results = results.sort_values("position", na_position="last")
    details = {
        str(row["abbreviation"]).upper(): (
            str(row.get("full_name", "")),
            str(row.get("team_name", "")),
        )
        for _, row in ordered_results.iterrows()
    }
    ordered_codes = [
        str(code).upper()
        for code in ordered_results["abbreviation"]
        if str(code).upper() in lap_numbers
    ]
    ordered_codes.extend(sorted(set(lap_numbers) - set(ordered_codes)))
    return tuple(
        DriverOption(code, *details.get(code, ("", "")), lap_numbers[code])
        for code in ordered_codes
    )

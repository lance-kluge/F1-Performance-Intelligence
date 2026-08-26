"""Narrow application facade consumed by the Streamlit workspace."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

import pandas as pd

from f1pi.analysis.models import (
    DegradationMode,
    DriverTireModelConfig,
    LapComparison,
    LapSelection,
    StrategySimulationAnalysis,
    StrategySimulationConfig,
    StrategySimulationRequest,
    TireModelConfig,
)
from f1pi.domain.exceptions import (
    InsufficientStrategyDataError,
    LapNotFoundError,
    UnsupportedStrategySessionError,
)
from f1pi.domain.models import (
    IngestionResult,
    LoadOptions,
    ScheduledEvent,
    SessionKey,
    SessionType,
)
from f1pi.ui.models import (
    DriverOption,
    DriverTireAnalysisRun,
    LoadedSession,
    StrategySimulationRun,
    StrategySimulationSetup,
    TireAnalysisRun,
)

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

    def list_drivers(self, key: SessionKey) -> tuple[DriverOption, ...]: ...

    def analyze(self, key: SessionKey, mode: DegradationMode) -> TireAnalysisRun: ...

    def analyze_drivers(
        self,
        key: SessionKey,
        drivers: tuple[str, str],
        mode: DegradationMode,
    ) -> tuple[DriverTireAnalysisRun, DriverTireAnalysisRun]: ...


class StrategySimulatorFacade(Protocol):
    def list_available_events(self, year: int) -> tuple[ScheduledEvent, ...]: ...

    def load_setup(self, key: SessionKey) -> StrategySimulationSetup: ...

    def simulate(
        self,
        setup: StrategySimulationSetup,
        request: StrategySimulationRequest,
        config: StrategySimulationConfig,
    ) -> StrategySimulationRun: ...


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
        ingestion = self._ingest(key, mode)
        analysis = self._platform.tire_model.analyze(key, TireModelConfig(mode=mode))
        return TireAnalysisRun(analysis=analysis, snapshot_reused=ingestion.snapshot_reused)

    def list_drivers(self, key: SessionKey) -> tuple[DriverOption, ...]:
        """Load the lightweight race snapshot and expose its classified drivers."""
        self._platform.ingestion.ingest(
            key,
            LoadOptions(telemetry=False, weather=False, messages=False),
        )
        session = self._platform.sessions.open(key)
        minimum_supported_laps = DriverTireModelConfig().minimum_compound_laps
        drivers = tuple(
            driver
            for driver in driver_options(session.results(), session.laps())
            if len(driver.accurate_lap_numbers) >= minimum_supported_laps
        )
        if len(drivers) < 2:
            raise LapNotFoundError(
                "the session does not contain two drivers with enough accurate laps"
            )
        return drivers

    def analyze_drivers(
        self,
        key: SessionKey,
        drivers: tuple[str, str],
        mode: DegradationMode,
    ) -> tuple[DriverTireAnalysisRun, DriverTireAnalysisRun]:
        """Run two existing driver models from one prepared session snapshot."""
        ingestion = self._ingest(key, mode)
        first = DriverTireAnalysisRun(
            analysis=self._platform.tire_model.analyze_driver(
                key,
                drivers[0],
                DriverTireModelConfig(mode=mode),
            ),
            snapshot_reused=ingestion.snapshot_reused,
        )
        second = DriverTireAnalysisRun(
            analysis=self._platform.tire_model.analyze_driver(
                key,
                drivers[1],
                DriverTireModelConfig(mode=mode),
            ),
            snapshot_reused=ingestion.snapshot_reused,
        )
        return first, second

    def _ingest(self, key: SessionKey, mode: DegradationMode) -> IngestionResult:
        return self._platform.ingestion.ingest(
            key,
            LoadOptions(
                telemetry=False,
                weather=mode is DegradationMode.ADJUSTED,
                messages=False,
            ),
        )


class StrategyAnalysisFacade:
    """Adapt the strategy service into discoverable, UI-ready operations."""

    def __init__(self, platform: Platform) -> None:
        self._platform = platform

    def list_available_events(self, year: int) -> tuple[ScheduledEvent, ...]:
        events = self._platform.session_discovery.list_available_events(year)
        supported_types = {SessionType.RACE, SessionType.SPRINT}
        return tuple(
            ScheduledEvent(
                year=event.year,
                round_number=event.round_number,
                event_name=event.event_name,
                country=event.country,
                location=event.location,
                sessions=tuple(
                    session
                    for session in event.sessions
                    if session.session_type in supported_types
                ),
            )
            for event in events
            if any(session.session_type in supported_types for session in event.sessions)
        )

    def load_setup(self, key: SessionKey) -> StrategySimulationSetup:
        ingestion = self._platform.ingestion.ingest(
            key,
            LoadOptions(telemetry=False, weather=True, messages=False),
        )
        session = self._platform.sessions.open(key)
        if session.track_status()["status"].astype(str).eq("5").any():
            raise UnsupportedStrategySessionError("red-flag races are not supported in v1")
        laps = session.laps()
        results = session.results()
        drivers = _classified_strategy_drivers(results, laps)
        if not drivers:
            raise InsufficientStrategyDataError(
                "the race has no classified drivers with usable lap data"
            )
        race_laps = int(pd.to_numeric(laps["lap_number"], errors="coerce").max())
        compounds = tuple(
            sorted(
                compound
                for compound in {
                    str(value).strip().upper() for value in laps["compound"].dropna()
                }
                if compound and compound != "UNKNOWN"
            )
        )
        if not compounds:
            raise InsufficientStrategyDataError("the race has no identifiable tire compounds")
        return StrategySimulationSetup(
            key=key,
            metadata=session.metadata,
            drivers=drivers,
            race_laps=race_laps,
            compounds=compounds,
            snapshot_reused=ingestion.snapshot_reused,
        )

    def simulate(
        self,
        setup: StrategySimulationSetup,
        request: StrategySimulationRequest,
        config: StrategySimulationConfig,
    ) -> StrategySimulationRun:
        analysis: StrategySimulationAnalysis = self._platform.strategy_simulator.simulate(
            setup.key, request, config
        )
        return StrategySimulationRun(analysis, setup.snapshot_reused)


def _classified_strategy_drivers(
    results: pd.DataFrame, laps: pd.DataFrame
) -> tuple[DriverOption, ...]:
    """Return classified finishers with every observed, non-pit-in decision lap."""
    classified = results.loc[
        results["position"].notna()
        & results["status"].astype(str).str.match(
            r"^(Finished|Lapped|\+\s*\d+\s+Laps?)$", case=False
        )
    ]
    eligible_codes = {
        str(value).strip().upper() for value in classified["abbreviation"].dropna()
    }
    choices = []
    for option in driver_options(results, laps):
        if option.abbreviation not in eligible_codes:
            continue
        driver_laps = laps.loc[
            laps["driver"].astype(str).str.upper().eq(option.abbreviation)
            & laps["lap_time_ns"].notna()
            & laps["lap_start_time_ns"].notna()
            & laps["pit_in_time_ns"].isna()
            & laps["compound"].astype("string").str.strip().str.upper().ne("UNKNOWN")
            & laps["compound"].notna()
            & pd.to_numeric(laps["tyre_life"], errors="coerce").notna()
        ]
        lap_numbers = tuple(
            sorted({int(number) for number in driver_laps["lap_number"].dropna()})
        )
        if lap_numbers:
            choices.append(
                DriverOption(
                    option.abbreviation,
                    option.full_name,
                    option.team_name,
                    lap_numbers,
                )
            )
    return tuple(choices)


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

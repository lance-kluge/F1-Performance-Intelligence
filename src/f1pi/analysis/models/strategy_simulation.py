"""Presentation-neutral contracts for race-strategy counterfactuals."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from itertools import pairwise

import pandas as pd

from f1pi.domain.models import SessionMetadata


class NeutralizationKind(StrEnum):
    SAFETY_CAR = "safety_car"
    VIRTUAL_SAFETY_CAR = "virtual_safety_car"


class NeutralizationSource(StrEnum):
    ACTUAL = "actual"
    NONE = "none"
    CUSTOM = "custom"


@dataclass(frozen=True, slots=True)
class NeutralizationAssumptions:
    """Explicit parameters used when a session cannot calibrate a custom event."""

    lap_time_multiplier: float
    pit_loss_multiplier: float
    restart_gap_seconds: float = 1.0

    def __post_init__(self) -> None:
        if self.lap_time_multiplier < 1:
            raise ValueError("lap_time_multiplier must be at least 1")
        if not 0 < self.pit_loss_multiplier <= 1:
            raise ValueError("pit_loss_multiplier must be in (0, 1]")
        if self.restart_gap_seconds <= 0:
            raise ValueError("restart_gap_seconds must be positive")


@dataclass(frozen=True, slots=True)
class NeutralizationEvent:
    kind: NeutralizationKind
    start_lap: int
    end_lap: int
    assumptions: NeutralizationAssumptions | None = None

    def __post_init__(self) -> None:
        if self.start_lap < 1:
            raise ValueError("neutralization start_lap must be positive")
        if self.end_lap < self.start_lap:
            raise ValueError("neutralization end_lap must not precede start_lap")


@dataclass(frozen=True, slots=True)
class NeutralizationScenario:
    name: str
    source: NeutralizationSource
    events: tuple[NeutralizationEvent, ...] = ()

    def __post_init__(self) -> None:
        normalized_name = self.name.strip()
        if not normalized_name:
            raise ValueError("scenario name must not be empty")
        object.__setattr__(self, "name", normalized_name)
        if self.source is not NeutralizationSource.CUSTOM and self.events:
            raise ValueError("only custom scenarios may declare events")
        ordered = tuple(sorted(self.events, key=lambda event: (event.start_lap, event.end_lap)))
        for previous, current in pairwise(ordered):
            if current.start_lap <= previous.end_lap:
                raise ValueError("neutralization events must not overlap")
        object.__setattr__(self, "events", ordered)

    @classmethod
    def actual(cls, name: str = "actual") -> NeutralizationScenario:
        return cls(name, NeutralizationSource.ACTUAL)

    @classmethod
    def no_safety_car(cls, name: str = "no_safety_car") -> NeutralizationScenario:
        return cls(name, NeutralizationSource.NONE)

    @classmethod
    def custom(cls, name: str, events: tuple[NeutralizationEvent, ...]) -> NeutralizationScenario:
        return cls(name, NeutralizationSource.CUSTOM, events)


@dataclass(frozen=True, slots=True)
class PlannedPitStop:
    after_lap: int
    compound: str
    starting_tire_age_laps: float = 1.0

    def __post_init__(self) -> None:
        if self.after_lap < 1:
            raise ValueError("after_lap must be positive")
        compound = self.compound.strip().upper()
        if not compound:
            raise ValueError("compound must not be empty")
        if self.starting_tire_age_laps < 0:
            raise ValueError("starting_tire_age_laps must be non-negative")
        object.__setattr__(self, "compound", compound)


@dataclass(frozen=True, slots=True)
class StrategyPlan:
    name: str
    stops: tuple[PlannedPitStop, ...] = ()

    def __post_init__(self) -> None:
        name = self.name.strip()
        if not name:
            raise ValueError("strategy name must not be empty")
        object.__setattr__(self, "name", name)
        laps = tuple(stop.after_lap for stop in self.stops)
        if laps != tuple(sorted(laps)) or len(laps) != len(set(laps)):
            raise ValueError("strategy stops must be strictly increasing")


@dataclass(frozen=True, slots=True)
class StrategySimulationRequest:
    driver: str
    decision_lap: int
    strategies: tuple[StrategyPlan, ...]
    scenarios: tuple[NeutralizationScenario, ...] = (NeutralizationScenario.actual(),)

    def __post_init__(self) -> None:
        driver = self.driver.strip().upper()
        if not driver:
            raise ValueError("driver must not be empty")
        if self.decision_lap < 1:
            raise ValueError("decision_lap must be positive")
        if not self.strategies:
            raise ValueError("at least one candidate strategy is required")
        if not self.scenarios:
            raise ValueError("at least one neutralization scenario is required")
        strategy_names = [strategy.name.casefold() for strategy in self.strategies]
        scenario_names = [scenario.name.casefold() for scenario in self.scenarios]
        if len(strategy_names) != len(set(strategy_names)):
            raise ValueError("strategy names must be unique")
        if "baseline" in strategy_names:
            raise ValueError("baseline is a reserved strategy name")
        if len(scenario_names) != len(set(scenario_names)):
            raise ValueError("scenario names must be unique")
        object.__setattr__(self, "driver", driver)


@dataclass(frozen=True, slots=True)
class StrategySimulationConfig:
    iterations: int = 2000
    random_seed: int = 0
    confidence_level: float = 0.95
    traffic_gap_seconds: float = 2.0

    def __post_init__(self) -> None:
        if self.iterations < 1:
            raise ValueError("iterations must be positive")
        if not 0 < self.confidence_level < 1:
            raise ValueError("confidence_level must be in (0, 1)")
        if self.traffic_gap_seconds <= 0:
            raise ValueError("traffic_gap_seconds must be positive")


@dataclass(frozen=True, slots=True)
class StrategyOutcomeSummary:
    scenario: str
    strategy: str
    expected_finish_position: float
    median_finish_position: float
    win_probability: float
    podium_probability: float
    top_ten_probability: float
    expected_gap_to_winner_seconds: float
    expected_delta_to_baseline_seconds: float
    probability_better_than_baseline: float


@dataclass(frozen=True, slots=True)
class StrategyCalibrationDiagnostics:
    pace_observation_count: int
    target_pace_observation_count: int
    pit_stop_sample_count: int
    traffic_sample_count: int
    pace_mae_seconds: float
    pace_rmse_seconds: float
    supported_compounds: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class StrategySimulationAnalysis:
    metadata: SessionMetadata
    driver: str
    decision_lap: int
    baseline: StrategyPlan
    summaries: tuple[StrategyOutcomeSummary, ...]
    diagnostics: StrategyCalibrationDiagnostics
    outcome_samples: pd.DataFrame
    lap_distributions: pd.DataFrame
    warnings: tuple[str, ...]

"""Session lookup use case for strategy counterfactual simulation."""

from __future__ import annotations

from typing import Protocol

from f1pi.analysis.models import (
    StrategySimulationAnalysis,
    StrategySimulationConfig,
    StrategySimulationRequest,
)
from f1pi.analysis.strategy_simulator import StrategySimulationEngine
from f1pi.analysis.strategy_simulator.analysis_session import StrategyAnalysisSession
from f1pi.domain.models import SessionKey


class StrategyAnalysisSessionRepository(Protocol):
    def open(self, key: SessionKey) -> StrategyAnalysisSession: ...


class StrategySimulationService:
    def __init__(
        self,
        sessions: StrategyAnalysisSessionRepository,
        engine: StrategySimulationEngine | None = None,
    ) -> None:
        self._sessions = sessions
        self._engine = engine or StrategySimulationEngine()

    def simulate(
        self,
        key: SessionKey,
        request: StrategySimulationRequest,
        config: StrategySimulationConfig | None = None,
    ) -> StrategySimulationAnalysis:
        return self._engine.simulate(self._sessions.open(key), request, config)

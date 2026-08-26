from __future__ import annotations

from typing import cast
from unittest.mock import Mock

from f1pi.analysis import (
    StrategyPlan,
    StrategySimulationAnalysis,
    StrategySimulationConfig,
    StrategySimulationEngine,
    StrategySimulationRequest,
)
from f1pi.application.strategy_simulator import (
    StrategyAnalysisSessionRepository,
    StrategySimulationService,
)
from f1pi.domain.models import SessionKey


def test_service_opens_session_and_delegates_simulation() -> None:
    opened_session = object()
    repository = Mock(spec=StrategyAnalysisSessionRepository)
    repository.open.return_value = opened_session
    engine = Mock(spec=StrategySimulationEngine)
    expected = cast(StrategySimulationAnalysis, object())
    engine.simulate.return_value = expected
    service = StrategySimulationService(repository, engine)
    key = SessionKey(2026, "Monaco", "R")
    request = StrategySimulationRequest("LEC", 10, (StrategyPlan("stay_out"),))
    config = StrategySimulationConfig(iterations=10)

    result = service.simulate(key, request, config)

    assert result is expected
    repository.open.assert_called_once_with(key)
    engine.simulate.assert_called_once_with(opened_session, request, config)

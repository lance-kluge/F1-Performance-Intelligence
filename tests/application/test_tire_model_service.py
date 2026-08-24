from __future__ import annotations

from typing import cast
from unittest.mock import Mock

from f1pi.analysis import TireDegradationAnalysis, TireDegradationEngine, TireModelConfig
from f1pi.application.tire_model import TireAnalysisSessionRepository, TireModelService
from f1pi.domain.models import SessionKey


def test_service_opens_session_and_delegates_analysis() -> None:
    opened_session = object()
    repository = Mock(spec=TireAnalysisSessionRepository)
    repository.open.return_value = opened_session
    engine = Mock(spec=TireDegradationEngine)
    expected_analysis = cast(TireDegradationAnalysis, object())
    engine.analyze.return_value = expected_analysis
    service = TireModelService(repository, engine)
    key = SessionKey(2026, "Monaco", "R")
    config = TireModelConfig()

    analysis = service.analyze(key, config)

    assert analysis is expected_analysis
    repository.open.assert_called_once_with(key)
    engine.analyze.assert_called_once_with(opened_session, config)

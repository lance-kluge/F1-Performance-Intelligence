from __future__ import annotations

from typing import cast
from unittest.mock import Mock

from f1pi.analysis import LapComparison, LapComparisonEngine, LapSelection
from f1pi.application.lap_analysis import AnalysisSessionRepository, LapAnalysisService
from f1pi.domain.models import SessionKey


def test_service_opens_session_and_delegates_comparison() -> None:
    session = object()
    repository = Mock(spec=AnalysisSessionRepository)
    repository.open.return_value = session
    engine = Mock(spec=LapComparisonEngine)
    expected = cast(LapComparison, object())
    engine.compare.return_value = expected
    service = LapAnalysisService(repository, engine)
    key = SessionKey(2026, "Monaco", "Q")
    lap_a = LapSelection.fastest("NOR")
    lap_b = LapSelection.fastest("VER")

    result = service.compare(key, lap_a, lap_b)

    assert result is expected
    repository.open.assert_called_once_with(key)
    engine.compare.assert_called_once_with(session, lap_a, lap_b)

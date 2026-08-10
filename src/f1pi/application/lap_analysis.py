"""Session lookup use case for lap comparison."""

from __future__ import annotations

from typing import Protocol

from f1pi.analysis.lap_analysis import AnalysisSession, LapComparisonEngine
from f1pi.analysis.models import LapComparison, LapSelection
from f1pi.domain.models import SessionKey


class AnalysisSessionRepository(Protocol):
    def open(self, key: SessionKey) -> AnalysisSession: ...


class LapAnalysisService:
    def __init__(
        self,
        sessions: AnalysisSessionRepository,
        engine: LapComparisonEngine | None = None,
    ) -> None:
        self._sessions = sessions
        self._engine = engine or LapComparisonEngine()

    def compare(
        self,
        key: SessionKey,
        lap_a: LapSelection,
        lap_b: LapSelection,
    ) -> LapComparison:
        return self._engine.compare(self._sessions.open(key), lap_a, lap_b)

"""Session lookup use case for tire degradation analysis."""

from __future__ import annotations

from typing import Protocol

from f1pi.analysis.models import (
    DriverTireDegradationAnalysis,
    DriverTireModelConfig,
    TireDegradationAnalysis,
    TireModelConfig,
)
from f1pi.analysis.tire_model import TireDegradationEngine
from f1pi.analysis.tire_model.analysis_session import TireAnalysisSession
from f1pi.domain.models import SessionKey


class TireAnalysisSessionRepository(Protocol):
    def open(self, key: SessionKey) -> TireAnalysisSession: ...


class TireModelService:
    def __init__(
        self,
        sessions: TireAnalysisSessionRepository,
        engine: TireDegradationEngine | None = None,
    ) -> None:
        self._sessions = sessions
        self._engine = engine or TireDegradationEngine()

    def analyze(
        self, key: SessionKey, config: TireModelConfig | None = None
    ) -> TireDegradationAnalysis:
        return self._engine.analyze(self._sessions.open(key), config)

    def analyze_driver(
        self,
        key: SessionKey,
        driver: str,
        config: DriverTireModelConfig | None = None,
    ) -> DriverTireDegradationAnalysis:
        return self._engine.analyze_driver(self._sessions.open(key), driver, config)

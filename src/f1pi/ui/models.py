"""Presentation-specific immutable view models."""

from __future__ import annotations

from dataclasses import dataclass

from f1pi.analysis.models import DriverTireDegradationAnalysis, TireDegradationAnalysis
from f1pi.domain.models import SessionKey, SessionMetadata


@dataclass(frozen=True, slots=True)
class DriverOption:
    abbreviation: str
    full_name: str
    team_name: str
    accurate_lap_numbers: tuple[int, ...]

    @property
    def label(self) -> str:
        details = f"{self.full_name} · {self.team_name}".strip(" ·")
        return f"{self.abbreviation} — {details}" if details else self.abbreviation


@dataclass(frozen=True, slots=True)
class LoadedSession:
    key: SessionKey
    metadata: SessionMetadata
    drivers: tuple[DriverOption, ...]
    snapshot_reused: bool


@dataclass(frozen=True, slots=True)
class TireAnalysisRun:
    """Completed tire model plus the provenance of its source snapshot."""

    analysis: TireDegradationAnalysis
    snapshot_reused: bool


@dataclass(frozen=True, slots=True)
class DriverTireAnalysisRun:
    """Completed driver-scoped tire model plus snapshot provenance."""

    analysis: DriverTireDegradationAnalysis
    snapshot_reused: bool

"""F1 Performance Intelligence data foundation."""

from __future__ import annotations

from importlib import import_module
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from f1pi.analysis import (
        AnalysisQuality,
        ComparisonSummary,
        CompoundDegradationEstimate,
        Confidence,
        DegradationMode,
        DriverTireDegradationAnalysis,
        DriverTireModelConfig,
        LapComparison,
        LapSelection,
        NeutralizationAssumptions,
        NeutralizationEvent,
        NeutralizationKind,
        NeutralizationScenario,
        NeutralizationSource,
        PerformanceSectionComparison,
        PlannedPitStop,
        SegmentationConfig,
        StrategyCalibrationDiagnostics,
        StrategyOutcomeSummary,
        StrategyPlan,
        StrategySimulationAnalysis,
        StrategySimulationConfig,
        StrategySimulationRequest,
        SummaryNarrativeProvider,
        SynchronizationConfig,
        TireDegradationAnalysis,
        TireModelConfig,
        TireModelMetrics,
        TireModelValidation,
        TireStintSummary,
    )
    from f1pi.composition import Platform, build_platform
    from f1pi.config import PlatformSettings
    from f1pi.domain import (
        IngestionResult,
        LoadOptions,
        ScheduledEvent,
        ScheduledSession,
        SessionKey,
        SessionType,
    )
    from f1pi.infrastructure.fastf1_client import FastF1Client

__all__ = [
    "AnalysisQuality",
    "ComparisonSummary",
    "CompoundDegradationEstimate",
    "Confidence",
    "DegradationMode",
    "DriverTireDegradationAnalysis",
    "DriverTireModelConfig",
    "FastF1Client",
    "IngestionResult",
    "LapComparison",
    "LapSelection",
    "LoadOptions",
    "NeutralizationAssumptions",
    "NeutralizationEvent",
    "NeutralizationKind",
    "NeutralizationScenario",
    "NeutralizationSource",
    "PerformanceSectionComparison",
    "PlannedPitStop",
    "Platform",
    "PlatformSettings",
    "ScheduledEvent",
    "ScheduledSession",
    "SegmentationConfig",
    "SessionKey",
    "SessionType",
    "StrategyCalibrationDiagnostics",
    "StrategyOutcomeSummary",
    "StrategyPlan",
    "StrategySimulationAnalysis",
    "StrategySimulationConfig",
    "StrategySimulationRequest",
    "SummaryNarrativeProvider",
    "SynchronizationConfig",
    "TireDegradationAnalysis",
    "TireModelConfig",
    "TireModelMetrics",
    "TireModelValidation",
    "TireStintSummary",
    "build_platform",
]

_EXPORTS = {
    "AnalysisQuality": ("f1pi.analysis", "AnalysisQuality"),
    "ComparisonSummary": ("f1pi.analysis", "ComparisonSummary"),
    "CompoundDegradationEstimate": ("f1pi.analysis", "CompoundDegradationEstimate"),
    "Confidence": ("f1pi.analysis", "Confidence"),
    "DegradationMode": ("f1pi.analysis", "DegradationMode"),
    "DriverTireDegradationAnalysis": ("f1pi.analysis", "DriverTireDegradationAnalysis"),
    "DriverTireModelConfig": ("f1pi.analysis", "DriverTireModelConfig"),
    "FastF1Client": ("f1pi.infrastructure.fastf1_client", "FastF1Client"),
    "IngestionResult": ("f1pi.domain", "IngestionResult"),
    "LapComparison": ("f1pi.analysis", "LapComparison"),
    "LapSelection": ("f1pi.analysis", "LapSelection"),
    "LoadOptions": ("f1pi.domain", "LoadOptions"),
    "NeutralizationAssumptions": ("f1pi.analysis", "NeutralizationAssumptions"),
    "NeutralizationEvent": ("f1pi.analysis", "NeutralizationEvent"),
    "NeutralizationKind": ("f1pi.analysis", "NeutralizationKind"),
    "NeutralizationScenario": ("f1pi.analysis", "NeutralizationScenario"),
    "NeutralizationSource": ("f1pi.analysis", "NeutralizationSource"),
    "PerformanceSectionComparison": ("f1pi.analysis", "PerformanceSectionComparison"),
    "PlannedPitStop": ("f1pi.analysis", "PlannedPitStop"),
    "Platform": ("f1pi.composition", "Platform"),
    "PlatformSettings": ("f1pi.config", "PlatformSettings"),
    "ScheduledEvent": ("f1pi.domain", "ScheduledEvent"),
    "ScheduledSession": ("f1pi.domain", "ScheduledSession"),
    "SegmentationConfig": ("f1pi.analysis", "SegmentationConfig"),
    "SessionKey": ("f1pi.domain", "SessionKey"),
    "SessionType": ("f1pi.domain", "SessionType"),
    "SummaryNarrativeProvider": ("f1pi.analysis", "SummaryNarrativeProvider"),
    "SynchronizationConfig": ("f1pi.analysis", "SynchronizationConfig"),
    "StrategyCalibrationDiagnostics": ("f1pi.analysis", "StrategyCalibrationDiagnostics"),
    "StrategyOutcomeSummary": ("f1pi.analysis", "StrategyOutcomeSummary"),
    "StrategyPlan": ("f1pi.analysis", "StrategyPlan"),
    "StrategySimulationAnalysis": ("f1pi.analysis", "StrategySimulationAnalysis"),
    "StrategySimulationConfig": ("f1pi.analysis", "StrategySimulationConfig"),
    "StrategySimulationRequest": ("f1pi.analysis", "StrategySimulationRequest"),
    "TireDegradationAnalysis": ("f1pi.analysis", "TireDegradationAnalysis"),
    "TireModelConfig": ("f1pi.analysis", "TireModelConfig"),
    "TireModelMetrics": ("f1pi.analysis", "TireModelMetrics"),
    "TireModelValidation": ("f1pi.analysis", "TireModelValidation"),
    "TireStintSummary": ("f1pi.analysis", "TireStintSummary"),
    "build_platform": ("f1pi.composition", "build_platform"),
}


def __getattr__(name: str) -> object:
    """Load public package exports only when callers request them."""
    try:
        module_name, attribute_name = _EXPORTS[name]
    except KeyError as error:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}") from error

    value = getattr(import_module(module_name), attribute_name)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    """Expose lazy public exports to interactive tooling."""
    return sorted({*globals(), *__all__})

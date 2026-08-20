"""F1 Performance Intelligence data foundation."""

from __future__ import annotations

from importlib import import_module
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from f1pi.analysis import (
        AnalysisQuality,
        ComparisonSummary,
        Confidence,
        LapComparison,
        LapSelection,
        PerformanceSectionComparison,
        SegmentationConfig,
        SummaryNarrativeProvider,
        SynchronizationConfig,
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
    "Confidence",
    "FastF1Client",
    "IngestionResult",
    "LapComparison",
    "LapSelection",
    "LoadOptions",
    "PerformanceSectionComparison",
    "Platform",
    "PlatformSettings",
    "ScheduledEvent",
    "ScheduledSession",
    "SegmentationConfig",
    "SessionKey",
    "SessionType",
    "SummaryNarrativeProvider",
    "SynchronizationConfig",
    "build_platform",
]

_EXPORTS = {
    "AnalysisQuality": ("f1pi.analysis", "AnalysisQuality"),
    "ComparisonSummary": ("f1pi.analysis", "ComparisonSummary"),
    "Confidence": ("f1pi.analysis", "Confidence"),
    "FastF1Client": ("f1pi.infrastructure.fastf1_client", "FastF1Client"),
    "IngestionResult": ("f1pi.domain", "IngestionResult"),
    "LapComparison": ("f1pi.analysis", "LapComparison"),
    "LapSelection": ("f1pi.analysis", "LapSelection"),
    "LoadOptions": ("f1pi.domain", "LoadOptions"),
    "PerformanceSectionComparison": ("f1pi.analysis", "PerformanceSectionComparison"),
    "Platform": ("f1pi.composition", "Platform"),
    "PlatformSettings": ("f1pi.config", "PlatformSettings"),
    "ScheduledEvent": ("f1pi.domain", "ScheduledEvent"),
    "ScheduledSession": ("f1pi.domain", "ScheduledSession"),
    "SegmentationConfig": ("f1pi.analysis", "SegmentationConfig"),
    "SessionKey": ("f1pi.domain", "SessionKey"),
    "SessionType": ("f1pi.domain", "SessionType"),
    "SummaryNarrativeProvider": ("f1pi.analysis", "SummaryNarrativeProvider"),
    "SynchronizationConfig": ("f1pi.analysis", "SynchronizationConfig"),
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

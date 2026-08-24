"""Public, presentation-neutral records returned by lap comparison."""

from f1pi.analysis.models.corner_comparison import CornerComparison
from f1pi.analysis.models.lap_comparison import LapComparison
from f1pi.analysis.models.lap_explanation import LapExplanation
from f1pi.analysis.models.lap_selection import LapSelection
from f1pi.analysis.models.lap_summary import LapSummary
from f1pi.analysis.models.performance_analysis import (
    AnalysisQuality,
    ComparisonSummary,
    Confidence,
    CornerPhaseKind,
    DriverCornerMetrics,
    DriverStraightMetrics,
    FindingEvidence,
    FindingKind,
    PerformanceSectionComparison,
    PhaseComparison,
    SectionKind,
    SegmentationConfig,
    SegmentationSource,
    SummaryFinding,
    TurnComparison,
    TurnReference,
)
from f1pi.analysis.models.sector_comparison import SectorComparison
from f1pi.analysis.models.straight_comparison import StraightComparison
from f1pi.analysis.models.synchronization_config import SynchronizationConfig
from f1pi.analysis.models.tire_model import (
    CompoundDegradationEstimate,
    DegradationMode,
    TireDegradationAnalysis,
    TireModelConfig,
    TireModelMetrics,
    TireModelValidation,
    TireStintSummary,
)

__all__ = [
    "AnalysisQuality",
    "ComparisonSummary",
    "CompoundDegradationEstimate",
    "Confidence",
    "CornerComparison",
    "CornerPhaseKind",
    "DegradationMode",
    "DriverCornerMetrics",
    "DriverStraightMetrics",
    "FindingEvidence",
    "FindingKind",
    "LapComparison",
    "LapExplanation",
    "LapSelection",
    "LapSummary",
    "PerformanceSectionComparison",
    "PhaseComparison",
    "SectionKind",
    "SectorComparison",
    "SegmentationConfig",
    "SegmentationSource",
    "StraightComparison",
    "SummaryFinding",
    "SynchronizationConfig",
    "TireDegradationAnalysis",
    "TireModelConfig",
    "TireModelMetrics",
    "TireModelValidation",
    "TireStintSummary",
    "TurnComparison",
    "TurnReference",
]

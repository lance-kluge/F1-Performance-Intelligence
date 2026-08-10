"""Structured performance-analysis records returned by lap comparison."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class Confidence(StrEnum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class SegmentationSource(StrEnum):
    OFFICIAL_AND_TELEMETRY = "official_and_telemetry"
    TELEMETRY_ONLY = "telemetry_only"


class SectionKind(StrEnum):
    CORNER_COMPLEX = "corner_complex"
    STRAIGHT = "straight"


class CornerPhaseKind(StrEnum):
    ENTRY = "entry"
    APEX = "apex"
    EXIT = "exit"


class FindingKind(StrEnum):
    LOSS = "loss"
    GAIN = "gain"


@dataclass(frozen=True, slots=True)
class TurnReference:
    number: int | None
    letter: str
    label: str
    apex_distance_metres: float
    confidence: Confidence

    @property
    def name(self) -> str:
        if self.number is None:
            return self.label
        return f"Turn {self.number}{self.letter}"


@dataclass(frozen=True, slots=True)
class DriverCornerMetrics:
    entry_speed_kph: float
    minimum_speed_kph: float
    minimum_speed_distance_metres: float
    exit_speed_kph: float
    brake_onset_distance_metres: float | None
    throttle_lift_distance_metres: float | None
    throttle_reapplication_distance_metres: float | None
    full_throttle_distance_metres: float | None
    minimum_gear: int | None


@dataclass(frozen=True, slots=True)
class DriverStraightMetrics:
    entry_speed_kph: float
    exit_speed_kph: float
    average_speed_kph: float
    maximum_speed_kph: float


@dataclass(frozen=True, slots=True)
class PhaseComparison:
    kind: CornerPhaseKind
    start_distance_metres: float
    end_distance_metres: float
    delta_seconds: float
    advantaged_driver: str | None
    magnitude_seconds: float


@dataclass(frozen=True, slots=True)
class TurnComparison:
    turn: TurnReference
    start_distance_metres: float
    end_distance_metres: float
    delta_seconds: float
    lap_a_metrics: DriverCornerMetrics
    lap_b_metrics: DriverCornerMetrics


@dataclass(frozen=True, slots=True)
class PerformanceSectionComparison:
    section_id: str
    kind: SectionKind
    label: str
    start_distance_metres: float
    end_distance_metres: float
    wraps_finish_line: bool
    sector_numbers: tuple[int, ...]
    delta_seconds: float
    advantaged_driver: str | None
    magnitude_seconds: float
    confidence: Confidence
    turns: tuple[TurnComparison, ...] = ()
    phases: tuple[PhaseComparison, ...] = ()
    lap_a_corner_metrics: DriverCornerMetrics | None = None
    lap_b_corner_metrics: DriverCornerMetrics | None = None
    lap_a_straight_metrics: DriverStraightMetrics | None = None
    lap_b_straight_metrics: DriverStraightMetrics | None = None
    start_turn: str | None = None
    end_turn: str | None = None


@dataclass(frozen=True, slots=True)
class FindingEvidence:
    metric: str
    lap_a_value: float
    lap_b_value: float
    unit: str


@dataclass(frozen=True, slots=True)
class SummaryFinding:
    kind: FindingKind
    affected_driver: str
    section_id: str
    section_label: str
    phase: CornerPhaseKind | None
    time_seconds: float
    confidence: Confidence
    evidence: tuple[FindingEvidence, ...]
    text: str


@dataclass(frozen=True, slots=True)
class ComparisonSummary:
    headline: str
    findings: tuple[SummaryFinding, ...]
    narrative: str


@dataclass(frozen=True, slots=True)
class AnalysisQuality:
    confidence: Confidence
    segmentation_source: SegmentationSource
    available_channels: tuple[str, ...]
    warnings: tuple[str, ...]
    reconciliation_error_seconds: float


@dataclass(frozen=True, slots=True)
class SegmentationConfig:
    smoothing_window_metres: float = 25.0
    minimum_corner_prominence_kph: float = 10.0
    minimum_corner_prominence_fraction: float = 0.08
    minimum_corner_separation_metres: float = 75.0
    lift_threshold_percent: float = 95.0
    throttle_reapplication_percent: float = 20.0
    full_throttle_percent: float = 98.0
    sustained_input_metres: float = 25.0
    minimum_straight_metres: float = 150.0
    apex_speed_band_kph: float = 5.0
    finding_minimum_seconds: float = 0.010

    def __post_init__(self) -> None:
        positive = {
            "smoothing_window_metres": self.smoothing_window_metres,
            "minimum_corner_prominence_kph": self.minimum_corner_prominence_kph,
            "minimum_corner_separation_metres": self.minimum_corner_separation_metres,
            "sustained_input_metres": self.sustained_input_metres,
            "minimum_straight_metres": self.minimum_straight_metres,
            "apex_speed_band_kph": self.apex_speed_band_kph,
            "finding_minimum_seconds": self.finding_minimum_seconds,
        }
        for name, value in positive.items():
            if value <= 0:
                raise ValueError(f"{name} must be positive")
        if not 0 < self.minimum_corner_prominence_fraction <= 1:
            raise ValueError("minimum_corner_prominence_fraction must be in (0, 1]")
        if not 0 < self.throttle_reapplication_percent < self.lift_threshold_percent:
            raise ValueError("throttle_reapplication_percent must be below lift threshold")
        if not self.lift_threshold_percent < self.full_throttle_percent <= 100:
            raise ValueError("full_throttle_percent must be above lift threshold and at most 100")

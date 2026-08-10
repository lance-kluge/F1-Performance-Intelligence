"""Telemetry synchronization configuration."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SynchronizationConfig:
    """Spatial sampling and explanation thresholds for a comparison."""

    sample_count: int = 1000
    corner_window_metres: float = 100.0
    full_throttle_percent: float = 98.0

    def __post_init__(self) -> None:
        if self.sample_count < 100:
            raise ValueError("sample_count must be at least 100")
        if self.corner_window_metres <= 0:
            raise ValueError("corner_window_metres must be positive")
        if not 0 < self.full_throttle_percent <= 100:
            raise ValueError("full_throttle_percent must be in (0, 100]")

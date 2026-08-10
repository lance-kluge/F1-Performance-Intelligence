"""Straight-line comparison data between two adjacent turns."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class StraightComparison:
    start_turn: str
    end_turn: str
    start_distance_metres: float
    end_distance_metres: float
    length_metres: float
    time_delta_seconds: float

    @property
    def name(self) -> str:
        return f"{self.start_turn} → {self.end_turn}"

    @property
    def section_label(self) -> str:
        prefix = (
            "Start/finish straight"
            if self.end_distance_metres < self.start_distance_metres
            else "Straight"
        )
        return f"{prefix} · {self.name}"

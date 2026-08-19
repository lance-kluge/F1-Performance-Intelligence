"""Corner comparison data."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class CornerComparison:
    number: int | None
    letter: str
    distance_metres: float
    time_delta_seconds: float
    lap_a_min_speed_kph: float
    lap_b_min_speed_kph: float
    lap_a_full_throttle_metres: float | None
    lap_b_full_throttle_metres: float | None
    label: str | None = None

    @property
    def name(self) -> str:
        if self.number is None:
            return self.label or "Detected corner"
        return f"Turn {self.number}{self.letter}"

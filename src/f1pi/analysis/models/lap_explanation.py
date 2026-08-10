"""Natural-language lap explanation data."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class LapExplanation:
    faster_driver: str | None
    slower_driver: str | None
    largest_loss_sector: int | None
    sector_loss_seconds: float | None
    key_corner: str | None
    corner_loss_seconds: float | None
    minimum_speed_advantage_kph: float | None
    earlier_full_throttle_metres: float | None
    text: str

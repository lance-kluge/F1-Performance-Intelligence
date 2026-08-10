"""Lap selection inputs."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class LapSelection:
    """Select a driver's fastest accurate lap or one explicit lap number."""

    driver: str
    lap_number: int | None = None
    accurate_only: bool = True

    def __post_init__(self) -> None:
        driver = self.driver.strip().upper()
        if not driver:
            raise ValueError("driver must not be empty")
        if self.lap_number is not None and self.lap_number < 1:
            raise ValueError("lap_number must be 1 or greater")
        object.__setattr__(self, "driver", driver)

    @classmethod
    def fastest(cls, driver: str) -> LapSelection:
        return cls(driver=driver)

    @classmethod
    def numbered(cls, driver: str, lap_number: int, *, accurate_only: bool = True) -> LapSelection:
        return cls(driver=driver, lap_number=lap_number, accurate_only=accurate_only)

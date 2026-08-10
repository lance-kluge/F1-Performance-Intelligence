"""Data-access contract required by lap analysis."""

from typing import Protocol

import pandas as pd


class AnalysisSession(Protocol):
    def laps(self) -> pd.DataFrame: ...

    def car_telemetry(self, driver: str | None = None) -> pd.DataFrame: ...

    def position(self, driver: str | None = None) -> pd.DataFrame: ...

    def circuit_corners(self) -> pd.DataFrame: ...

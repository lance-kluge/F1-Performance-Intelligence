"""Data-access contract required by tire degradation analysis."""

from typing import Protocol

import pandas as pd

from f1pi.domain.models import SessionMetadata


class TireAnalysisSession(Protocol):
    @property
    def metadata(self) -> SessionMetadata: ...

    def laps(self) -> pd.DataFrame: ...

    def weather(self) -> pd.DataFrame: ...

    def track_status(self) -> pd.DataFrame: ...

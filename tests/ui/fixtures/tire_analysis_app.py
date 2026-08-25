"""Deterministic AppTest entrypoint for the tire-degradation workspace."""

from __future__ import annotations

from datetime import UTC, datetime

import numpy as np
import pandas as pd
import streamlit as st

import f1pi.ui.pages.tire_degradation as page
from f1pi.analysis.models import (
    CompoundDegradationEstimate,
    DegradationMode,
    TireDegradationAnalysis,
    TireModelMetrics,
    TireModelValidation,
    TireStintSummary,
)
from f1pi.domain.models import ScheduledEvent, ScheduledSession, SessionKey, SessionMetadata
from f1pi.ui.models import TireAnalysisRun
from f1pi.ui.styles import load_styles


class FakeTireFacade:
    def list_available_events(self, year: int) -> tuple[ScheduledEvent, ...]:
        return (
            ScheduledEvent(
                year,
                1,
                "Australian Grand Prix",
                "Australia",
                "Melbourne",
                (
                    ScheduledSession(
                        session_type="R",
                        name="Race",
                        starts_at_utc=datetime(2026, 3, 8, 4, tzinfo=UTC),
                    ),
                ),
            ),
        )

    def analyze(self, key: SessionKey, mode: DegradationMode) -> TireAnalysisRun:
        st.session_state["fake_tire_mode"] = mode.value
        return _analysis_run(key, mode)


def _analysis_run(key: SessionKey, mode: DegradationMode) -> TireAnalysisRun:
    observations = pd.DataFrame(
        {
            "driver": ["NOR"] * 4 + ["VER"] * 5,
            "stint_id": ["NOR:1"] * 4 + ["VER:1"] * 5,
            "compound": ["MEDIUM"] * 4 + ["SOFT"] * 5,
            "lap_number": list(range(1, 10)),
            "stint_lap_index": [1, 2, 3, 4, 1, 2, 3, 4, 5],
            "tire_age_laps": [1.0, 2.0, 3.0, 4.0, 1.0, 2.0, 3.0, 4.0, 5.0],
            "lap_time_seconds": [91.0, 91.1, 91.2, 91.3, 90.0, 90.2, 90.4, 90.6, 105.0],
            "race_progress": np.linspace(0, 1, 9),
            "track_temp": [32.0] * 9,
            "air_temp": [22.0] * 9,
            "humidity": [50.0] * 9,
            "pressure": [1010.0] * 9,
            "wind_speed": [2.0] * 9,
            "rainfall": [False] * 9,
            "eligible": [True] * 8 + [False],
            "exclusion_reason": [""] * 8 + ["slow_lap"],
            "fitted_lap_time_seconds": [91.0, 91.1, 91.2, 91.3, 90.0, 90.2, 90.4, 90.6, np.nan],
            "residual_seconds": [0.0] * 8 + [np.nan],
        }
    )
    curves = pd.concat(
        [
            _curve("MEDIUM", 91.0, 0.1),
            _curve("SOFT", 90.0, 0.2),
        ],
        ignore_index=True,
    )
    metadata = SessionMetadata(
        session_id="2026-01-australian-r",
        year=key.year,
        round_number=1,
        event_name="Australian Grand Prix",
        country="Australia",
        location="Melbourne",
        session_type="R",
        session_name="Race",
        session_date_utc=datetime(2026, 3, 8, 4, tzinfo=UTC),
        fastf1_version="3.8.3",
    )
    overall = TireModelMetrics("overall", 8, 0.18, 0.24, 0.72, 0.36)
    analysis = TireDegradationAnalysis(
        metadata=metadata,
        mode=mode,
        stints=(
            TireStintSummary("NOR:1", "NOR", "MEDIUM", 1, 4, 1, 4, True, 4, 0),
            TireStintSummary("VER:1", "VER", "SOFT", 5, 9, 1, 5, False, 4, 1),
        ),
        estimates=(
            CompoundDegradationEstimate("MEDIUM", 0.1, 0.04, 0.16, 4, 2, 1, 4),
            CompoundDegradationEstimate("SOFT", 0.2, -0.02, 0.42, 4, 2, 1, 4),
        ),
        validation=TireModelValidation(
            2,
            overall,
            (
                TireModelMetrics("MEDIUM", 4, 0.16, 0.21, 0.75, 0.31),
                TireModelMetrics("SOFT", 4, 0.20, 0.27, 0.68, 0.41),
            ),
        ),
        observations=observations,
        curves=curves,
        warnings=("dropped_constant_feature:rainfall",),
    )
    return TireAnalysisRun(analysis, snapshot_reused=True)


def _curve(compound: str, base: float, slope: float) -> pd.DataFrame:
    ages = np.linspace(1, 4, 4)
    predicted = base + slope * (ages - 1)
    return pd.DataFrame(
        {
            "compound": compound,
            "tire_age_laps": ages,
            "predicted_lap_time_seconds": predicted,
            "mean_confidence_lower_seconds": predicted - 0.1,
            "mean_confidence_upper_seconds": predicted + 0.1,
            "prediction_lower_seconds": predicted - 0.5,
            "prediction_upper_seconds": predicted + 0.5,
        }
    )


st.set_page_config(page_title="Tire analysis test", layout="wide")
load_styles()
fake = FakeTireFacade()
page.get_tire_analysis_facade = lambda: fake
page.available_tire_events.clear()
page.render_tire_degradation()

from __future__ import annotations

from datetime import UTC, datetime

import numpy as np
import pandas as pd
import pytest

from f1pi.analysis.models import (
    CompoundDegradationEstimate,
    CornerComparison,
    DegradationMode,
    LapComparison,
    LapExplanation,
    LapSummary,
    SectorComparison,
    StraightComparison,
    TireDegradationAnalysis,
    TireModelMetrics,
    TireModelValidation,
    TireStintSummary,
)
from f1pi.domain.models import SessionKey, SessionMetadata
from f1pi.ui.models import DriverOption, LoadedSession, TireAnalysisRun


@pytest.fixture
def comparison() -> LapComparison:
    distance = np.linspace(0, 1000, 6)
    telemetry = pd.DataFrame(
        {
            "distance_metres": distance,
            "relative_distance": np.linspace(0, 1, 6),
            "lap_a_elapsed_seconds": np.linspace(0, 90, 6),
            "lap_b_elapsed_seconds": np.linspace(0, 90.4, 6),
            "lap_a_speed_kph": [100, 210, 150, 240, 170, 260],
            "lap_b_speed_kph": [98, 208, 146, 238, 168, 259],
            "lap_a_throttle_percent": [20, 100, 40, 100, 50, 100],
            "lap_b_throttle_percent": [15, 95, 35, 100, 45, 100],
            "lap_a_brake": pd.array([True, False, True, False, True, False], dtype="boolean"),
            "lap_b_brake": pd.array([True, False, True, False, False, False], dtype="boolean"),
            "lap_a_x": [0, 100, 250, 400, 250, 0],
            "lap_a_y": [0, 200, 300, 200, 0, 0],
            "lap_b_x": [0, 102, 252, 398, 248, 0],
            "lap_b_y": [0, 198, 302, 202, 2, 0],
            "time_delta_seconds": [0, 0.05, 0.08, 0.16, 0.22, 0.4],
            "local_time_delta_seconds": [0.01, 0.02, -0.02, -0.03, 0.04, 0.05],
            "sector": [1.0, 1.0, 2.0, 2.0, 3.0, 3.0],
        }
    )
    lap_a = LapSummary("NOR", 7, 90.0, (30.0, 30.0, 30.0), True)
    lap_b = LapSummary("VER", 8, 90.4, (30.05, 30.08, 30.27), True)
    return LapComparison(
        lap_a=lap_a,
        lap_b=lap_b,
        delta_seconds=0.4,
        sectors=(
            SectorComparison(1, 30.0, 30.05, 0.05),
            SectorComparison(2, 30.0, 30.08, 0.08),
            SectorComparison(3, 30.0, 30.27, 0.27),
        ),
        telemetry=telemetry,
        corners=(
            CornerComparison(3, "", 300.0, 0.08, 145.0, 140.0, 380.0, 405.0),
            CornerComparison(9, "", 700.0, 0.04, 170.0, 168.0, 780.0, 790.0),
        ),
        explanation=LapExplanation(
            "NOR",
            "VER",
            3,
            0.27,
            "Turn 3",
            0.08,
            5.0,
            25.0,
            "NOR is 0.400 seconds faster than VER. VER loses the most time in Sector 3.",
        ),
        straights=(
            StraightComparison("Turn 3", "Turn 9", 400.0, 600.0, 200.0, 0.06),
            StraightComparison("Turn 9", "Turn 3", 800.0, 200.0, 400.0, 0.03),
        ),
    )


@pytest.fixture
def loaded_session() -> LoadedSession:
    return LoadedSession(
        key=SessionKey(2026, 1, "Q"),
        metadata=SessionMetadata(
            session_id="2026-01-australian-q",
            year=2026,
            round_number=1,
            event_name="Australian Grand Prix",
            country="Australia",
            location="Melbourne",
            session_type="Q",
            session_name="Qualifying",
            session_date_utc=datetime(2026, 3, 7, 5, tzinfo=UTC),
            fastf1_version="3.8.3",
        ),
        drivers=(
            DriverOption("NOR", "Lando Norris", "McLaren", (7, 9)),
            DriverOption("VER", "Max Verstappen", "Red Bull Racing", (8, 10)),
        ),
        snapshot_reused=True,
    )


@pytest.fixture
def tire_analysis_run(loaded_session: LoadedSession) -> TireAnalysisRun:
    observations = pd.DataFrame(
        {
            "driver": ["NOR", "NOR", "NOR", "NOR", "VER", "VER", "VER", "VER", "VER"],
            "stint_id": ["NOR:1"] * 4 + ["VER:1"] * 5,
            "compound": ["MEDIUM"] * 4 + ["SOFT"] * 5,
            "lap_number": list(range(1, 10)),
            "stint_lap_index": [1, 2, 3, 4, 1, 2, 3, 4, 5],
            "tire_age_laps": [1.0, 2.0, 3.0, 4.0, 1.0, 2.0, 3.0, 4.0, 5.0],
            "lap_time_seconds": [91.0, 91.1, 91.2, 91.3, 90.0, 90.2, 90.4, 90.6, 105.0],
            "race_progress": np.linspace(0.0, 1.0, 9),
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
            pd.DataFrame(
                {
                    "compound": compound,
                    "tire_age_laps": ages,
                    "predicted_lap_time_seconds": base + slope * (ages - 1),
                    "mean_confidence_lower_seconds": base + slope * (ages - 1) - 0.1,
                    "mean_confidence_upper_seconds": base + slope * (ages - 1) + 0.1,
                    "prediction_lower_seconds": base + slope * (ages - 1) - 0.5,
                    "prediction_upper_seconds": base + slope * (ages - 1) + 0.5,
                }
            )
            for compound, ages, base, slope in (
                ("MEDIUM", np.linspace(1, 4, 4), 91.0, 0.1),
                ("SOFT", np.linspace(1, 4, 4), 90.0, 0.2),
            )
        ],
        ignore_index=True,
    )
    overall = TireModelMetrics("overall", 8, 0.18, 0.24, 0.72, 0.36)
    analysis = TireDegradationAnalysis(
        metadata=loaded_session.metadata,
        mode=DegradationMode.ADJUSTED,
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
    return TireAnalysisRun(analysis=analysis, snapshot_reused=True)

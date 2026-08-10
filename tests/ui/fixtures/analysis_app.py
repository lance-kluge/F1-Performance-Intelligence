"""Deterministic AppTest entrypoint for the interactive workspace."""

from __future__ import annotations

from datetime import UTC, datetime

import numpy as np
import pandas as pd
import streamlit as st

import f1pi.ui.pages.lap_analysis as page
from f1pi.analysis.models import (
    CornerComparison,
    LapComparison,
    LapExplanation,
    LapSelection,
    LapSummary,
    SectorComparison,
    StraightComparison,
)
from f1pi.domain.models import ScheduledEvent, ScheduledSession, SessionKey, SessionMetadata
from f1pi.ui.models import DriverOption, LoadedSession
from f1pi.ui.styles import load_styles


class FakeFacade:
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
                        session_type="Q",
                        name="Qualifying",
                        starts_at_utc=datetime(2026, 3, 7, 5, tzinfo=UTC),
                    ),
                ),
            ),
        )

    def load_session(self, key: SessionKey) -> LoadedSession:
        st.session_state["fake_load_called"] = True
        return LoadedSession(
            key=key,
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

    def compare(
        self,
        key: SessionKey,
        lap_a: LapSelection,
        lap_b: LapSelection,
    ) -> LapComparison:
        st.session_state["fake_comparison_laps"] = (lap_a.lap_number, lap_b.lap_number)
        del key
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
                "lap_a_brake": pd.array(
                    [True, False, True, False, True, False], dtype="boolean"
                ),
                "lap_b_brake": pd.array(
                    [True, False, True, False, False, False], dtype="boolean"
                ),
                "lap_a_x": [0, 100, 250, 400, 250, 0],
                "lap_a_y": [0, 200, 300, 200, 0, 0],
                "lap_b_x": [0, 102, 252, 398, 248, 0],
                "lap_b_y": [0, 198, 302, 202, 2, 0],
                "time_delta_seconds": [0, 0.05, 0.08, 0.16, 0.22, 0.4],
                "local_time_delta_seconds": [0.01, 0.02, -0.02, -0.03, 0.04, 0.05],
                "sector": [1.0, 1.0, 2.0, 2.0, 3.0, 3.0],
            }
        )
        return LapComparison(
            lap_a=LapSummary("NOR", lap_a.lap_number or 7, 90.0, (30.0, 30.0, 30.0), True),
            lap_b=LapSummary("VER", lap_b.lap_number or 8, 90.4, (30.05, 30.08, 30.27), True),
            delta_seconds=0.4,
            sectors=(
                SectorComparison(1, 30.0, 30.05, 0.05),
                SectorComparison(2, 30.0, 30.08, 0.08),
                SectorComparison(3, 30.0, 30.27, 0.27),
            ),
            telemetry=telemetry,
            corners=(CornerComparison(3, "", 300.0, 0.08, 145.0, 140.0, 380.0, 405.0),),
            explanation=LapExplanation(
                "NOR",
                "VER",
                3,
                0.27,
                "Turn 3",
                0.08,
                5.0,
                25.0,
                "NOR is 0.400 seconds faster than VER. VER loses most in Sector 3.",
            ),
            straights=(
                StraightComparison("Turn 3", "Turn 9", 400.0, 600.0, 200.0, 0.06),
            ),
        )


st.set_page_config(page_title="Analysis test", layout="wide")
load_styles()
fake = FakeFacade()
page.get_analysis_facade = lambda: fake
page.available_events.clear()
page.render_lap_analysis()

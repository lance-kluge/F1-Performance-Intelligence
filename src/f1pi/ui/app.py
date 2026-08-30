"""Application shell and navigation."""

from __future__ import annotations

import streamlit as st

from f1pi.ui.pages.lap_analysis import render_lap_analysis
from f1pi.ui.pages.strategy_simulator import render_strategy_simulator
from f1pi.ui.pages.tire_degradation import render_tire_degradation
from f1pi.ui.styles import load_styles


def main() -> None:
    """Configure and run the Streamlit application."""
    st.set_page_config(
        page_title="F1 Performance Intelligence",
        page_icon="🏁",
        layout="wide",
        initial_sidebar_state="collapsed",
        menu_items={"About": "F1 Performance Intelligence — telemetry made legible."},
    )
    load_styles()
    analysis = st.Page(
        render_lap_analysis,
        title="Lap analysis",
        icon=":material/query_stats:",
        url_path="lap-analysis",
        default=True,
    )
    tire_degradation = st.Page(
        render_tire_degradation,
        title="Tire degradation",
        icon=":material/tire_repair:",
        url_path="tire-degradation",
    )
    strategy_simulator = st.Page(
        render_strategy_simulator,
        title="Strategy simulator",
        icon=":material/alt_route:",
        url_path="strategy-simulator",
    )

    navigation = st.navigation([analysis, tire_degradation, strategy_simulator], position="top")
    navigation.run()

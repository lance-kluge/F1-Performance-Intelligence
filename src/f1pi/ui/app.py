"""Application shell and navigation."""

from __future__ import annotations

import streamlit as st

from f1pi.ui.pages.home import render_home
from f1pi.ui.pages.lap_analysis import render_lap_analysis
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
    )
    tire_degradation = st.Page(
        render_tire_degradation,
        title="Tire degradation",
        icon=":material/tire_repair:",
        url_path="tire-degradation",
    )

    def home_page() -> None:
        render_home(analysis, tire_degradation)

    home = st.Page(
        home_page,
        title="Overview",
        icon=":material/space_dashboard:",
        url_path="home",
        default=True,
    )
    navigation = st.navigation([home, analysis, tire_degradation], position="top")
    navigation.run()

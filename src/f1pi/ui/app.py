"""Application shell and navigation."""

from __future__ import annotations

import streamlit as st

from f1pi.ui.pages.home import render_home
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
    home = st.Page(render_home, title="Overview", icon=":material/space_dashboard:", default=True)
    navigation = st.navigation([home], position="top")
    navigation.run()

"""Lazy, cached construction for interactive-only services."""

from __future__ import annotations

import streamlit as st

from f1pi.ui.analysis_facade import LapAnalysisFacade, TireAnalysisFacade


@st.cache_resource(show_spinner=False)
def get_analysis_facade() -> LapAnalysisFacade:
    """Build the platform only when the analysis page is visited."""
    from f1pi.composition import build_platform

    return LapAnalysisFacade(build_platform())


@st.cache_resource(show_spinner=False)
def get_tire_analysis_facade() -> TireAnalysisFacade:
    """Build the platform only when the tire analysis page is visited."""
    from f1pi.composition import build_platform

    return TireAnalysisFacade(build_platform())

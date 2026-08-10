"""Product landing page."""

from __future__ import annotations

import streamlit as st

from f1pi.ui.components.landing import (
    render_analysis_preview,
    render_benefits,
    render_final_callout,
    render_hero_copy,
    render_methodology,
    render_workflow,
)
from f1pi.ui.components.layout import render_footer, render_wordmark


def render_home() -> None:
    """Render the network-free landing experience."""
    render_wordmark()
    hero_copy, hero_preview = st.columns((0.82, 1.18), gap="large", vertical_alignment="center")
    with hero_copy:
        render_hero_copy()
        st.button(
            "Open lap analysis — coming next",
            type="primary",
            disabled=True,
            width="stretch",
        )
        st.caption("FastF1 data stays local. No account required.")
    with hero_preview:
        render_analysis_preview()
    render_benefits()
    render_workflow()
    render_methodology()
    render_final_callout()
    st.button(
        "Open lap analysis — coming next",
        key="final_lap_analysis_cta",
        type="primary",
        disabled=True,
        width="stretch",
    )
    render_footer()

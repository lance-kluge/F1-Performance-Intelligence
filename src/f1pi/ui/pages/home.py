"""Product landing page."""

from __future__ import annotations

from typing import TYPE_CHECKING

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

if TYPE_CHECKING:
    from streamlit.navigation.page import Page


def render_home(analysis_page: Page | None = None) -> None:
    """Render the network-free landing experience."""
    render_wordmark()
    hero_copy, hero_preview = st.columns((0.82, 1.18), gap="large", vertical_alignment="center")
    with hero_copy:
        render_hero_copy()
        _analysis_link(analysis_page, key="hero")
        st.caption("FastF1 data stays local. No account required.")
    with hero_preview:
        render_analysis_preview()
    render_benefits()
    render_workflow()
    render_methodology()
    render_final_callout()
    _analysis_link(analysis_page, key="final")
    render_footer()


def _analysis_link(analysis_page: Page | None, *, key: str) -> None:
    if analysis_page is None:
        st.button(
            "Open lap analysis — coming next",
            key=f"{key}_lap_analysis_cta",
            type="primary",
            disabled=True,
            width="stretch",
        )
        return
    st.page_link(
        analysis_page,
        label="Open lap analysis",
        icon=":material/arrow_forward:",
        width="stretch",
    )

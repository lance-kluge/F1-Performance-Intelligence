"""Corner and straight gain drill-down view."""

from __future__ import annotations

from collections.abc import Mapping

import streamlit as st

from f1pi.analysis.models import LapComparison
from f1pi.ui.charts import corner_loss_figure, straight_loss_figure
from f1pi.ui.components.results.chrome import render_result_section


def render_loss_analysis(
    comparison: LapComparison, plot_config: Mapping[str, object]
) -> None:
    """Render ranked measured gains, naming the driver who gained in each section."""
    render_result_section(
        7, "Corner gains", "Rank the corners where either driver gained time."
    )
    corner_figure = corner_loss_figure(comparison)
    if corner_figure is None:
        st.info("Corner-level evidence is unavailable for this session.")
    else:
        st.plotly_chart(
            corner_figure,
            config=dict(plot_config),
            width="stretch",
            key="corner_losses",
        )

    render_result_section(
        8, "Straight gains", "Separate straight-line gains from the corner complexes."
    )
    straight_figure = straight_loss_figure(comparison)
    if straight_figure is None:
        st.info("No meaningful straight gain was measured for either selected lap.")
    else:
        st.caption(
            "Straights shorter than 150.000 metres are treated as part of the "
            "surrounding corner complex."
        )
        st.plotly_chart(
            straight_figure,
            config=dict(plot_config),
            width="stretch",
            key="straight_losses",
        )

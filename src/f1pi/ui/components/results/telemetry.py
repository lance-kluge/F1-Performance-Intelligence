"""Synchronized telemetry result view."""

from __future__ import annotations

from collections.abc import Mapping

import streamlit as st

from f1pi.analysis.models import LapComparison
from f1pi.ui.charts import delta_figure, inputs_figure, speed_figure
from f1pi.ui.components.results.chrome import render_result_section


def render_telemetry(comparison: LapComparison, plot_config: Mapping[str, object]) -> None:
    """Render cumulative timing, speed, and control inputs on one lap-progress axis."""
    render_result_section(
        4, "Live delta", "Follow the cumulative gap from the start line to the finish."
    )
    st.caption(
        "Positive means Driver A is ahead; negative means Driver B is ahead. "
        "Sector boundaries are shown as dotted lines."
    )
    st.plotly_chart(
        delta_figure(comparison),
        config=dict(plot_config),
        width="stretch",
        key="live_delta",
    )

    render_result_section(
        5, "Speed", "Compare speed at the same physical point on the circuit."
    )
    st.caption("Hover anywhere to see the current turn or straight and lap progress.")
    st.plotly_chart(
        speed_figure(comparison),
        config=dict(plot_config),
        width="stretch",
        key="speed_trace",
    )

    render_result_section(
        6, "Driver inputs", "Inspect throttle application and recorded braking."
    )
    if comparison.telemetry[["lap_a_brake", "lap_b_brake"]].isna().all().all():
        st.info("Brake channels are unavailable for both selected laps; throttle remains visible.")
    st.plotly_chart(
        inputs_figure(comparison),
        config=dict(plot_config),
        width="stretch",
        key="driver_inputs",
    )

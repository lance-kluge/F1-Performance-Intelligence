"""Composable result views for a completed lap comparison."""

from __future__ import annotations

import streamlit as st

from f1pi.analysis.models import Confidence, LapComparison
from f1pi.ui.components.results.insights import render_loss_analysis
from f1pi.ui.components.results.overview import render_overview
from f1pi.ui.components.results.straight_speed import render_straight_speed
from f1pi.ui.components.results.summary import render_summary
from f1pi.ui.components.results.telemetry import render_telemetry
from f1pi.ui.models import LoadedSession

PLOT_CONFIG = {
    "displayModeBar": False,
    "displaylogo": False,
    "responsive": True,
    "scrollZoom": False,
}


def render_results(session: LoadedSession, comparison: LapComparison) -> None:
    """Render a summary followed by three focused, navigable result views."""
    render_summary(session, comparison)
    _render_analysis_quality(comparison)
    st.html(
        """
        <div class="f1pi-results-guide">
          <span>Explore the comparison</span>
          <p>Start with the outcome, inspect the synchronized traces, then drill into the
          largest measured gains.</p>
        </div>
        """
    )
    overview, telemetry, losses = st.tabs(
        [
            ":material/overview: Overview",
            ":material/monitoring: Telemetry",
            ":material/troubleshoot: Gain analysis",
        ]
    )
    with overview:
        render_overview(comparison, PLOT_CONFIG)
    with telemetry:
        render_telemetry(comparison, PLOT_CONFIG)
    with losses:
        render_loss_analysis(comparison, PLOT_CONFIG)
        render_straight_speed(comparison)


def _render_analysis_quality(comparison: LapComparison) -> None:
    quality = comparison.quality
    if quality.confidence is Confidence.HIGH and not quality.warnings:
        return
    details = "; ".join(warning.replace("_", " ") for warning in quality.warnings)
    message = f"{quality.confidence.value.title()}-confidence analysis"
    if details:
        message += f": {details}."
    st.warning(message, icon=":material/warning:")


__all__ = ["PLOT_CONFIG", "render_results"]

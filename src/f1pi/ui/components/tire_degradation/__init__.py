"""Composable tire-degradation workspace and result views."""

from f1pi.ui.components.tire_degradation.chrome import (
    render_analysis_ready,
    render_tire_intro,
    render_tire_session_context,
)
from f1pi.ui.components.tire_degradation.results import render_tire_results

__all__ = [
    "render_analysis_ready",
    "render_tire_intro",
    "render_tire_results",
    "render_tire_session_context",
]

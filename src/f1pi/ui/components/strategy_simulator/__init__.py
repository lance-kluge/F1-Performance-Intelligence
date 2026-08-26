"""Strategy-simulator presentation components."""

from f1pi.ui.components.strategy_simulator.chrome import (
    render_setup_ready,
    render_simulation_ready,
    render_strategy_intro,
    render_strategy_session_context,
)
from f1pi.ui.components.strategy_simulator.results import render_strategy_results

__all__ = [
    "render_setup_ready",
    "render_simulation_ready",
    "render_strategy_intro",
    "render_strategy_results",
    "render_strategy_session_context",
]

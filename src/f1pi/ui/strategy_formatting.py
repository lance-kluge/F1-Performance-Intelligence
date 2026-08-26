"""Pure display formatting for strategy-simulation results."""

from __future__ import annotations

import re


def _display_zero(value: float, decimals: int) -> float:
    return 0.0 if abs(value) < 0.5 * 10**-decimals else value


def format_strategy_time(seconds: float) -> str:
    """Format a signed time difference to timing-screen precision."""
    return f"{_display_zero(seconds, 3):+.3f}s"


def format_gap(seconds: float) -> str:
    return f"{max(_display_zero(seconds, 3), 0.0):.3f}s"


def format_probability(probability: float) -> str:
    return f"{min(max(probability, 0.0), 1.0):.1%}"


def format_position(position: float) -> str:
    return f"P{max(position, 1.0):.1f}"


def strategy_warning_message(warning: str) -> str:
    """Translate simulator warning codes into concise, auditable UI copy."""
    if warning.startswith("traffic_contaminated_pace_fallback:"):
        driver = warning.partition(":")[2]
        return f"{driver} pace uses some traffic-affected laps because clean support was sparse."
    if warning.startswith("scaled_neutralized_pit_loss:"):
        kind = warning.partition(":")[2].replace("_", " ").upper()
        return f"{kind} pit loss was scaled from the available green-flag stop samples."
    messages = {
        "pit_loss_unavailable:no_stops": (
            "No observed pit stops were available, so strategies requiring a stop could not be "
            "evaluated with session-specific pit loss."
        ),
        "sparse_green_pit_loss_calibration": (
            "Pit-loss uncertainty is based on a small number of green-flag stops."
        ),
    }
    if warning in messages:
        return messages[warning]
    if warning.startswith("dropped_"):
        feature = warning.split(":")[-1].replace("_", " ")
        return f"{feature.title()} was omitted from calibration because it added no stable signal."
    return re.sub(r"[_:]", " ", warning).strip().capitalize() + "."


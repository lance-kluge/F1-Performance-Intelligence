"""Pure presentation helpers for tire-degradation results."""

from __future__ import annotations

import re

from f1pi.analysis.models import CompoundDegradationEstimate

EXCLUSION_LABELS = {
    "missing_required": "Missing timing or tire data",
    "unknown_compound": "Unknown compound",
    "inaccurate": "Inaccurate timing",
    "deleted": "Deleted lap",
    "pit_lap": "Pit in or out lap",
    "non_green": "Non-green track",
    "missing_adjusted_feature": "Missing weather data",
    "slow_lap": "Outside representative pace",
    "short_stint": "Stint too short",
}


def format_degradation_rate(seconds_per_lap: float) -> str:
    """Format a signed compound trend with a stable, readable precision."""
    if abs(seconds_per_lap) < 0.0005:
        seconds_per_lap = 0.0
    return f"{seconds_per_lap:+.3f} s/lap"


def estimate_signal(estimate: CompoundDegradationEstimate) -> str:
    """Describe whether the confidence interval supports a trend direction."""
    lower = estimate.confidence_lower_seconds_per_lap
    upper = estimate.confidence_upper_seconds_per_lap
    if lower <= 0 <= upper:
        return "Direction uncertain"
    if estimate.seconds_per_lap > 0:
        return "Lap time increases with tire age"
    return "Lap time decreases with tire age"


def exclusion_label(reason: str) -> str:
    return EXCLUSION_LABELS.get(reason, reason.replace("_", " ").strip().title())


def warning_message(warning: str) -> str:
    """Translate stable backend warning codes into concise UI copy."""
    if warning.startswith("insufficient_compound_data:"):
        compound = warning.partition(":")[2]
        return f"{compound.title()} was omitted because it lacks enough clean laps and stints."
    if warning.startswith("dropped_constant_feature:"):
        feature = warning.partition(":")[2].replace("_", " ")
        return f"{feature.title()} did not vary enough to help the adjusted model."
    if warning.startswith("dropped_collinear_feature:"):
        feature = warning.partition(":")[2].split(":")[-1].replace("_", " ")
        return f"{feature.title()} duplicated other information and was omitted."
    if warning.startswith("dropped_insufficient_degrees_of_freedom_feature:"):
        feature = warning.partition(":")[2].split(":")[-1].replace("_", " ")
        return f"{feature.title()} was omitted to preserve a stable fit."
    messages = {
        "incomplete_cross_validation": (
            "Some stints could not be scored out of sample; validation uses the folds that fit."
        ),
        "cluster_covariance_unavailable": (
            "There were too few independent stints for stint-clustered uncertainty."
        ),
    }
    return messages.get(warning, re.sub(r"[_:]", " ", warning).strip().capitalize() + ".")

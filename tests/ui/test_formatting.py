from __future__ import annotations

import pytest

from f1pi.analysis.models import LapComparison
from f1pi.ui.formatting import (
    FASTEST_LAP,
    SPECIFIC_LAP,
    comparison_outcome,
    format_delta,
    format_lap_time,
    lap_selection,
)


def test_display_formatters() -> None:
    assert format_lap_time(75.096) == "1:15.096"
    assert format_delta(0.184) == "+0.184s"
    assert format_delta(-0.022) == "-0.022s"
    assert format_delta(0.0001) == "+0.000s"
    assert format_delta(None) == "Unavailable"


def test_lap_selection_modes() -> None:
    assert lap_selection("nor", FASTEST_LAP).lap_number is None
    assert lap_selection("ver", SPECIFIC_LAP, 12).lap_number == 12
    with pytest.raises(ValueError, match="required"):
        lap_selection("VER", SPECIFIC_LAP)


def test_comparison_outcome_covers_both_drivers_and_tie(
    comparison: LapComparison,
) -> None:
    assert comparison_outcome(comparison) == ("NOR", "0.400s faster")

    object.__setattr__(comparison, "delta_seconds", -0.4)
    assert comparison_outcome(comparison) == ("VER", "0.400s faster")

    object.__setattr__(comparison, "delta_seconds", 0.0)
    assert comparison_outcome(comparison) == (
        "No advantage",
        "Identical recorded lap times",
    )

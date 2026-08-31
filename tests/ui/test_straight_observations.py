from dataclasses import replace

import pytest
from streamlit.testing.v1 import AppTest

from f1pi.analysis.models import (
    Confidence,
    DriverStraightMetrics,
    PerformanceSectionComparison,
    SectionKind,
)
from f1pi.ui.straight_observations import straight_speed_observations, straight_speed_summary


def _section(a_exit=310., b_exit=305., **changes):
    section = PerformanceSectionComparison(
        section_id="straight:t1-t2", kind=SectionKind.STRAIGHT, label="Straight · Turn 1 → Turn 2",
        start_distance_metres=100, end_distance_metres=400, wraps_finish_line=False,
        sector_numbers=(1,), delta_seconds=.1, advantaged_driver="NOR", magnitude_seconds=.1,
        confidence=Confidence.HIGH,
        lap_a_straight_metrics=DriverStraightMetrics(210, a_exit, 260, 315),
        lap_b_straight_metrics=DriverStraightMetrics(205, b_exit, 255, 310),
    )
    return replace(section, **changes)


def test_exit_speed_observations_count_both_drivers_and_preserve_context(comparison):
    comparison = replace(comparison, sections=(
        _section(), _section(300, 306), _section(300, 300.5),
    ))
    observations = straight_speed_observations(comparison)
    assert [o.exit_advantage for o in observations] == [
        "NOR by 5.0 km/h", "VER by 6.0 km/h", "Within 1.0 km/h",
    ]
    assert observations[0].lap_a_entry_kph == 210
    assert observations[0].confidence is Confidence.LOW
    text = straight_speed_summary(comparison, observations)
    assert "NOR is at least 1.0 km/h faster on 1 of 3 straights; VER on 1" in text
    assert "remaining 1" in text
    swapped = replace(comparison, lap_a=comparison.lap_b, lap_b=comparison.lap_a,
                      sections=(_section(305, 310),))
    assert straight_speed_observations(swapped)[0].exit_advantage == "NOR by 5.0 km/h"


@pytest.mark.parametrize("section", [
    _section(kind=SectionKind.UNSEGMENTED),
    _section(lap_a_straight_metrics=None),
    _section(float("nan"), 300),
    _section(300, float("inf")),
])
def test_unavailable_straight_evidence_never_produces_a_conclusion(comparison, section):
    comparison = replace(comparison, sections=(section,))
    assert straight_speed_observations(comparison) == ()
    assert "unavailable" in straight_speed_summary(comparison, ())


def test_same_driver_and_section_confidence_are_retained(comparison):
    comparison = replace(
        comparison, lap_b=replace(comparison.lap_b, driver="NOR"), sections=(_section(),),
        quality=replace(comparison.quality, confidence=Confidence.HIGH),
    )
    observations = straight_speed_observations(comparison)
    assert observations[0].exit_advantage == "NOR lap 7 by 5.0 km/h"
    assert observations[0].confidence is Confidence.HIGH
    medium = replace(comparison, sections=(_section(confidence=Confidence.MEDIUM),))
    assert straight_speed_observations(medium)[0].confidence is Confidence.MEDIUM


def test_straight_speed_view_shows_evidence_and_causal_limits(comparison):
    def straight_app(comparison):
        from f1pi.ui.components.results.straight_speed import render_straight_speed
        render_straight_speed(comparison)

    selected = replace(comparison, sections=(_section(),))
    app = AppTest.from_function(straight_app, args=(selected,)).run()
    assert not app.exception
    assert len(app.dataframe) == 1
    assert app.dataframe[0].value.iloc[0]["Exit speed advantage"] == "NOR by 5.0 km/h"
    assert "does not isolate" in app.info[0].value
    assert "not necessarily the maximum speed" in app.caption[0].value
    empty = AppTest.from_function(straight_app, args=(comparison,)).run()
    assert not empty.exception
    assert not empty.dataframe
    assert "unavailable" in empty.info[0].value

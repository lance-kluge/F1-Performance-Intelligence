from dataclasses import replace

import pytest

from f1pi.analysis.models import SectorComparison
from f1pi.ui.charts import corner_loss_figure
from f1pi.ui.gain_labels import largest_sector_gain


@pytest.mark.parametrize("delta, winner, loser", [(.123, "NOR", "VER"), (-.123, "VER", "NOR")])
def test_gains_name_the_same_driver_in_chart_and_sector_summary(comparison, delta, winner, loser):
    comparison = replace(
        comparison,
        sectors=(SectorComparison(1, 30, 30 + delta, delta),
                 SectorComparison(2, None, None, None), SectorComparison(3, 30, 30, 0)),
        corners=(replace(comparison.corners[0], time_delta_seconds=delta),),
    )
    expected = f"{winner} gained 0.123s on {loser}"
    assert largest_sector_gain(comparison) == f"Sector 1 · {expected}"
    chart = corner_loss_figure(comparison)
    assert chart.data[0].text[0] == expected
    assert chart.data[0].x[0] == .123


def test_sector_gain_handles_missing_tied_and_same_driver_laps(comparison):
    missing = tuple(SectorComparison(i, None, None, None) for i in (1, 2, 3))
    assert largest_sector_gain(replace(comparison, sectors=missing)) == "Unavailable"
    tied = tuple(SectorComparison(i, 30, 30, 0) for i in (1, 2, 3))
    assert largest_sector_gain(replace(comparison, sectors=tied)) == "No recorded gain"
    same_driver = replace(comparison, lap_b=replace(comparison.lap_b, driver="NOR"))
    assert largest_sector_gain(same_driver) == "Sector 3 · NOR lap 7 gained 0.270s on NOR lap 8"


@pytest.mark.parametrize("direction", [1, -1])
def test_narrative_names_gaining_driver_and_preserves_structured_contract(comparison, direction):
    from f1pi.analysis.models import (
        Confidence,
        FindingKind,
        PerformanceSectionComparison,
        SectionKind,
        SegmentationConfig,
    )
    from f1pi.analysis.performance_summary import (
        DeterministicSummaryNarrativeProvider,
        summarize_performance,
    )

    section = PerformanceSectionComparison(
        section_id="straight:test", kind=SectionKind.STRAIGHT, label="Test straight",
        start_distance_metres=100, end_distance_metres=400, wraps_finish_line=False,
        sector_numbers=(1,), delta_seconds=direction * .123, advantaged_driver=None,
        magnitude_seconds=.123, confidence=Confidence.HIGH,
    )
    summary, _ = summarize_performance(
        comparison.lap_a, comparison.lap_b, comparison.sectors, (section,), comparison.quality,
        SegmentationConfig(), DeterministicSummaryNarrativeProvider(),
    )
    finding = summary.findings[0]
    assert finding.affected_driver == "VER"
    assert finding.kind is (FindingKind.LOSS if direction > 0 else FindingKind.GAIN)
    winner, loser = ("NOR", "VER") if direction > 0 else ("VER", "NOR")
    assert finding.text.startswith(f"{winner} gained 0.123 seconds on {loser}")
    assert "lost" not in finding.text
    assert "recovered" not in finding.text

"""Measured straight-exit speed comparisons, without vehicle-causality claims."""

from __future__ import annotations

import math
from dataclasses import dataclass

from f1pi.analysis.models import Confidence, LapComparison, SectionKind

SPEED_DIFFERENCE_THRESHOLD_KPH = 1.0


@dataclass(frozen=True, slots=True)
class StraightSpeedObservation:
    section: str
    lap_a_entry_kph: float
    lap_b_entry_kph: float
    lap_a_exit_kph: float
    lap_b_exit_kph: float
    exit_advantage: str
    confidence: Confidence


def lap_identities(comparison: LapComparison) -> tuple[str, str]:
    same_driver = comparison.lap_a.driver == comparison.lap_b.driver
    a, b = (
        f"{lap.driver} lap {lap.lap_number}" if same_driver else lap.driver
        for lap in (comparison.lap_a, comparison.lap_b)
    )
    return a, b


def straight_speed_observations(comparison: LapComparison) -> tuple[StraightSpeedObservation, ...]:
    identities = lap_identities(comparison)
    observations: list[StraightSpeedObservation] = []
    for section in comparison.sections:
        a, b = section.lap_a_straight_metrics, section.lap_b_straight_metrics
        if section.kind is not SectionKind.STRAIGHT or a is None or b is None:
            continue
        values = (a.entry_speed_kph, b.entry_speed_kph, a.exit_speed_kph, b.exit_speed_kph)
        if not all(math.isfinite(value) for value in values):
            continue
        delta = a.exit_speed_kph - b.exit_speed_kph
        advantage = (
            f"{identities[0 if delta > 0 else 1]} by {abs(delta):.1f} km/h"
            if abs(delta) >= SPEED_DIFFERENCE_THRESHOLD_KPH else "Within 1.0 km/h"
        )
        confidence = (
            Confidence.LOW if Confidence.LOW in (section.confidence, comparison.quality.confidence)
            else Confidence.MEDIUM
            if Confidence.MEDIUM in (section.confidence, comparison.quality.confidence)
            else Confidence.HIGH
        )
        observations.append(StraightSpeedObservation(section.label, *values, advantage, confidence))
    return tuple(observations)


def straight_speed_summary(
    comparison: LapComparison, observations: tuple[StraightSpeedObservation, ...]
) -> str:
    if not observations:
        return "Straight-exit speed evidence is unavailable for these selected laps."
    a, b = lap_identities(comparison)
    a_faster = sum(o.lap_a_exit_kph - o.lap_b_exit_kph >= SPEED_DIFFERENCE_THRESHOLD_KPH
                   for o in observations)
    b_faster = sum(o.lap_b_exit_kph - o.lap_a_exit_kph >= SPEED_DIFFERENCE_THRESHOLD_KPH
                   for o in observations)
    close = len(observations) - a_faster - b_faster
    return (
        f"At the measured straight exits, {a} is at least 1.0 km/h faster on "
        f"{a_faster} of {len(observations)} straights; {b} on {b_faster}. "
        f"The remaining {close} are within 1.0 km/h. These observations describe only "
        "the two selected laps."
    )

"""Structured, deterministic summaries of attributed lap performance."""

from __future__ import annotations

from dataclasses import replace
from typing import Protocol

from f1pi.analysis.models import (
    AnalysisQuality,
    ComparisonSummary,
    Confidence,
    FindingEvidence,
    FindingKind,
    LapExplanation,
    LapSummary,
    PerformanceSectionComparison,
    SectionKind,
    SectorComparison,
    SegmentationConfig,
    SummaryFinding,
)


class SummaryNarrativeProvider(Protocol):
    """Optional prose renderer that cannot alter structured analytical facts."""

    def render(
        self,
        headline: str,
        findings: tuple[SummaryFinding, ...],
        quality: AnalysisQuality,
    ) -> str: ...


class DeterministicSummaryNarrativeProvider:
    def render(
        self,
        headline: str,
        findings: tuple[SummaryFinding, ...],
        quality: AnalysisQuality,
    ) -> str:
        del quality
        return " ".join((headline, *(finding.text for finding in findings)))


def summarize_performance(
    lap_a: LapSummary,
    lap_b: LapSummary,
    sectors: tuple[SectorComparison, SectorComparison, SectorComparison],
    sections: tuple[PerformanceSectionComparison, ...],
    quality: AnalysisQuality,
    config: SegmentationConfig,
    provider: SummaryNarrativeProvider,
) -> tuple[ComparisonSummary, LapExplanation]:
    headline = _headline(lap_a, lap_b)
    findings = _findings(lap_a, lap_b, sections, quality, config)
    narrative = provider.render(headline, findings, quality).strip()
    summary = ComparisonSummary(headline, findings, narrative)
    return summary, _legacy_explanation(lap_a, lap_b, sectors, sections, summary)


def _headline(lap_a: LapSummary, lap_b: LapSummary) -> str:
    delta = lap_b.lap_time_seconds - lap_a.lap_time_seconds
    identity_a, identity_b = _identities(lap_a, lap_b)
    if abs(delta) <= 1e-12:
        if identity_a == identity_b:
            return "The selected laps have identical recorded lap times."
        return f"{identity_a} and {identity_b} have identical recorded lap times."
    faster = identity_a if delta > 0 else identity_b
    slower = identity_b if delta > 0 else identity_a
    return f"{faster} is {abs(delta):.3f} seconds faster than {slower}."


def _findings(
    lap_a: LapSummary,
    lap_b: LapSummary,
    sections: tuple[PerformanceSectionComparison, ...],
    quality: AnalysisQuality,
    config: SegmentationConfig,
) -> tuple[SummaryFinding, ...]:
    overall_delta = lap_b.lap_time_seconds - lap_a.lap_time_seconds
    if abs(overall_delta) <= 1e-12:
        ranked = sorted(
            (
                section
                for section in sections
                if section.magnitude_seconds >= config.finding_minimum_seconds
            ),
            key=lambda section: section.magnitude_seconds,
            reverse=True,
        )[:2]
        return tuple(
            _finding(
                section,
                lap_b if section.delta_seconds > 0 else lap_a,
                lap_a,
                lap_b,
                FindingKind.LOSS,
                section.magnitude_seconds,
                1.0 if section.delta_seconds > 0 else -1.0,
                quality,
                config,
            )
            for section in ranked
        )

    direction = 1.0 if overall_delta > 0 else -1.0
    slower = lap_b if direction > 0 else lap_a
    losses = sorted(
        (
            (section, section.delta_seconds * direction)
            for section in sections
            if section.delta_seconds * direction >= config.finding_minimum_seconds
        ),
        key=lambda item: item[1],
        reverse=True,
    )
    gains = sorted(
        (
            (section, -section.delta_seconds * direction)
            for section in sections
            if -section.delta_seconds * direction >= config.finding_minimum_seconds
        ),
        key=lambda item: item[1],
        reverse=True,
    )
    output = [
        _finding(
            section,
            slower,
            lap_a,
            lap_b,
            FindingKind.LOSS,
            value,
            direction,
            quality,
            config,
        )
        for section, value in losses[:2]
    ]
    if gains:
        section, value = gains[0]
        output.append(
            _finding(
                section,
                slower,
                lap_a,
                lap_b,
                FindingKind.GAIN,
                value,
                direction,
                quality,
                config,
            )
        )
    return tuple(output)


def _finding(
    section: PerformanceSectionComparison,
    subject: LapSummary,
    lap_a: LapSummary,
    lap_b: LapSummary,
    kind: FindingKind,
    time_seconds: float,
    direction: float,
    quality: AnalysisQuality,
    config: SegmentationConfig,
) -> SummaryFinding:
    normalized_phases = [
        (phase, phase.delta_seconds * direction * (1 if kind is FindingKind.LOSS else -1))
        for phase in section.phases
    ]
    phase = max(normalized_phases, key=lambda item: item[1], default=(None, 0.0))[0]
    if phase is not None and abs(phase.delta_seconds) < config.finding_minimum_seconds:
        phase = None
    evidence = _evidence(section, direction, kind)
    identity_a, identity_b = _identities(lap_a, lap_b)
    winner, loser = (
        (identity_a, identity_b) if section.delta_seconds > 0 else (identity_b, identity_a)
    )
    finding = SummaryFinding(
        kind=kind,
        affected_driver=_identity(subject, lap_a.driver == lap_b.driver),
        section_id=section.section_id,
        section_label=section.label,
        phase=None if phase is None else phase.kind,
        time_seconds=time_seconds,
        confidence=_lower_confidence(section.confidence, quality.confidence),
        evidence=evidence,
        text="",
        sector_numbers=section.sector_numbers,
    )
    phase_text = "" if finding.phase is None else f" in the {finding.phase.value} phase"
    phase_text = _sector_context(finding.sector_numbers) + phase_text
    evidence_text = _evidence_text(finding.evidence, direction, kind, lap_a, lap_b)
    text = (
        f"{winner} gained "
        f"{finding.time_seconds:.3f} seconds on {loser} through "
        f"{finding.section_label}{phase_text}{evidence_text}."
    )
    return replace(finding, text=text)


def _sector_context(sector_numbers: tuple[int, ...]) -> str:
    """Locate a section without attributing its full delta to a single sector."""
    sectors = tuple(dict.fromkeys(sector_numbers))
    if not sectors:
        return ""
    if len(sectors) == 1:
        return f" (Sector {sectors[0]})"
    return f" (spanning Sectors {', '.join(str(sector) for sector in sectors)})"


def _evidence(
    section: PerformanceSectionComparison,
    direction: float,
    kind: FindingKind,
) -> tuple[FindingEvidence, ...]:
    multiplier = 1.0 if kind is FindingKind.LOSS else -1.0
    output: list[FindingEvidence] = []
    if section.kind is SectionKind.CORNER_COMPLEX:
        a = section.lap_a_corner_metrics
        b = section.lap_b_corner_metrics
        if a is None or b is None:
            return ()
        metric_values = (
            ("minimum_speed", a.minimum_speed_kph, b.minimum_speed_kph, "km/h", 0.5),
            ("exit_speed", a.exit_speed_kph, b.exit_speed_kph, "km/h", 1.0),
            ("entry_speed", a.entry_speed_kph, b.entry_speed_kph, "km/h", 1.0),
        )
        for name, value_a, value_b, unit, threshold in metric_values:
            advantage = (value_a - value_b) * direction * multiplier
            if advantage >= threshold:
                output.append(FindingEvidence(name, value_a, value_b, unit))
        if (
            a.full_throttle_distance_metres is not None
            and b.full_throttle_distance_metres is not None
        ):
            earlier = (
                (b.full_throttle_distance_metres - a.full_throttle_distance_metres)
                * direction
                * multiplier
            )
            if earlier >= 1.0:
                output.insert(
                    1,
                    FindingEvidence(
                        "full_throttle_distance",
                        a.full_throttle_distance_metres,
                        b.full_throttle_distance_metres,
                        "m",
                    ),
                )
    elif section.kind is SectionKind.STRAIGHT:
        straight_a = section.lap_a_straight_metrics
        straight_b = section.lap_b_straight_metrics
        if straight_a is not None and straight_b is not None:
            advantage = (
                (straight_a.average_speed_kph - straight_b.average_speed_kph)
                * direction
                * multiplier
            )
            if advantage >= 0.5:
                output.append(
                    FindingEvidence(
                        "average_speed",
                        straight_a.average_speed_kph,
                        straight_b.average_speed_kph,
                        "km/h",
                    )
                )
    return tuple(output[:2])


def _evidence_text(
    evidence: tuple[FindingEvidence, ...],
    direction: float,
    kind: FindingKind,
    lap_a: LapSummary,
    lap_b: LapSummary,
) -> str:
    if not evidence:
        return ""
    multiplier = 1.0 if kind is FindingKind.LOSS else -1.0
    advantaged = lap_a if direction * multiplier > 0 else lap_b
    observations: list[str] = []
    for item in evidence:
        if item.metric == "full_throttle_distance":
            observations.append(f"earlier full throttle recovery for {advantaged.driver}")
        elif item.metric == "minimum_speed":
            observations.append(f"more minimum speed for {advantaged.driver}")
        elif item.metric == "average_speed":
            observations.append(f"higher average straight-line speed for {advantaged.driver}")
        else:
            observations.append(f"higher {item.metric.replace('_', ' ')} for {advantaged.driver}")
    return ", associated with " + " and ".join(observations)


def _legacy_explanation(
    lap_a: LapSummary,
    lap_b: LapSummary,
    sectors: tuple[SectorComparison, SectorComparison, SectorComparison],
    sections: tuple[PerformanceSectionComparison, ...],
    summary: ComparisonSummary,
) -> LapExplanation:
    delta = lap_b.lap_time_seconds - lap_a.lap_time_seconds
    tied = abs(delta) <= 1e-12
    if tied:
        largest_sector = max(
            (sector for sector in sectors if sector.delta_seconds not in (None, 0.0)),
            key=lambda sector: abs(sector.delta_seconds or 0.0),
            default=None,
        )
        key_corner = max(
            (
                section
                for section in sections
                if section.kind is SectionKind.CORNER_COMPLEX
                and abs(section.delta_seconds) > 0.001
            ),
            key=lambda section: abs(section.delta_seconds),
            default=None,
        )
        direction = (
            1.0 if key_corner is None or key_corner.delta_seconds > 0 else -1.0
        )
    else:
        direction = 1.0 if delta > 0 else -1.0
        measured_sectors = [
            sector
            for sector in sectors
            if sector.delta_seconds is not None and sector.delta_seconds * direction > 0
        ]
        largest_sector = max(
            measured_sectors,
            key=lambda sector: (sector.delta_seconds or 0.0) * direction,
            default=None,
        )
        corner_losses = [
            section
            for section in sections
            if section.kind is SectionKind.CORNER_COMPLEX
            and section.delta_seconds * direction > 0.001
        ]
        key_corner = max(
            corner_losses,
            key=lambda section: section.delta_seconds * direction,
            default=None,
        )
    speed_advantage: float | None = None
    throttle_advantage: float | None = None
    if key_corner is not None:
        a = key_corner.lap_a_corner_metrics
        b = key_corner.lap_b_corner_metrics
        if a is not None and b is not None:
            speed = (a.minimum_speed_kph - b.minimum_speed_kph) * direction
            speed_advantage = speed if speed >= 0.5 else None
            if (
                a.full_throttle_distance_metres is not None
                and b.full_throttle_distance_metres is not None
            ):
                throttle = (
                    b.full_throttle_distance_metres - a.full_throttle_distance_metres
                ) * direction
                throttle_advantage = throttle if throttle >= 1.0 else None
    identity_a, identity_b = _identities(lap_a, lap_b)
    legacy_text = summary.narrative
    if key_corner is None and largest_sector is not None:
        winner, loser = (
            (identity_a, identity_b)
            if (largest_sector.delta_seconds or 0.0) > 0 else (identity_b, identity_a)
        )
        legacy_text += (
            f" {winner} gained {abs(largest_sector.delta_seconds or 0.0):.3f} seconds "
            f"on {loser} in Sector {largest_sector.sector}."
        )
    return LapExplanation(
        faster_driver=None if abs(delta) <= 1e-12 else (identity_a if delta > 0 else identity_b),
        slower_driver=None if abs(delta) <= 1e-12 else (identity_b if delta > 0 else identity_a),
        largest_loss_sector=None if largest_sector is None else largest_sector.sector,
        sector_loss_seconds=(
            None if largest_sector is None else abs(largest_sector.delta_seconds or 0.0)
        ),
        key_corner=None if key_corner is None else key_corner.label,
        corner_loss_seconds=None if key_corner is None else abs(key_corner.delta_seconds),
        minimum_speed_advantage_kph=speed_advantage,
        earlier_full_throttle_metres=throttle_advantage,
        text=legacy_text,
    )


def _lower_confidence(first: Confidence, second: Confidence) -> Confidence:
    rank = {Confidence.LOW: 0, Confidence.MEDIUM: 1, Confidence.HIGH: 2}
    return first if rank[first] <= rank[second] else second


def _identities(lap_a: LapSummary, lap_b: LapSummary) -> tuple[str, str]:
    include_number = lap_a.driver == lap_b.driver
    return _identity(lap_a, include_number), _identity(lap_b, include_number)


def _identity(lap: LapSummary, include_number: bool) -> str:
    return f"{lap.driver} lap {lap.lap_number}" if include_number else lap.driver

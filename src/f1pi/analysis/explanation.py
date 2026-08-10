"""Evidence-backed natural-language summaries of lap differences."""

from __future__ import annotations

from f1pi.analysis.models import (
    CornerComparison,
    LapExplanation,
    LapSummary,
    SectorComparison,
)


def explain_comparison(
    lap_a: LapSummary,
    lap_b: LapSummary,
    sectors: tuple[SectorComparison, SectorComparison, SectorComparison],
    corners: tuple[CornerComparison, ...],
) -> LapExplanation:
    if lap_a.lap_time_seconds == lap_b.lap_time_seconds:
        if lap_a.driver != lap_b.driver or lap_a.lap_number != lap_b.lap_number:
            return _explain_tied_laps(lap_a, lap_b, sectors, corners)
        return LapExplanation(
            faster_driver=None,
            slower_driver=None,
            largest_loss_sector=None,
            sector_loss_seconds=None,
            key_corner=None,
            corner_loss_seconds=None,
            minimum_speed_advantage_kph=None,
            earlier_full_throttle_metres=None,
            text="The selected laps have identical recorded lap times.",
        )
    if lap_a.lap_time_seconds <= lap_b.lap_time_seconds:
        faster, slower = lap_a, lap_b
        direction = 1.0
    else:
        faster, slower = lap_b, lap_a
        direction = -1.0

    overall = slower.lap_time_seconds - faster.lap_time_seconds
    largest_sector = _largest_sector_loss(sectors, direction)
    key_corner = _largest_corner_loss(corners, direction)
    speed_advantage = _speed_advantage(key_corner, direction)
    throttle_advantage = _throttle_advantage(key_corner, direction)
    distinguish_laps = faster.driver == slower.driver
    faster_identity = _lap_identity(faster, distinguish_laps)
    slower_identity = _lap_identity(slower, distinguish_laps)

    if distinguish_laps:
        opening = (
            f"{faster_identity} is {overall:.3f} seconds faster than {slower_identity}."
        )
    else:
        opening = (
            f"{faster.driver}'s lap is {overall:.3f} seconds faster than {slower.driver}'s."
        )
    sentences = [opening]
    if largest_sector is not None:
        sentences.append(
            f"{slower_identity} loses approximately "
            f"{abs(largest_sector.delta_seconds or 0.0):.3f} seconds in "
            f"Sector {largest_sector.sector}."
        )
    if key_corner is not None:
        evidence: list[str] = []
        if speed_advantage is not None:
            evidence.append(f"carries {speed_advantage:.1f} km/h more minimum speed")
        if throttle_advantage is not None:
            evidence.append(f"reaches full throttle {throttle_advantage:.0f} metres earlier")
        detail = ""
        if evidence:
            detail = f", where {faster_identity} " + " and ".join(evidence)
        sentences.append(
            f"The largest localized loss is approximately "
            f"{abs(key_corner.time_delta_seconds):.3f} seconds at "
            f"{key_corner.name}{detail}."
        )

    return LapExplanation(
        faster_driver=faster_identity,
        slower_driver=slower_identity,
        largest_loss_sector=None if largest_sector is None else largest_sector.sector,
        sector_loss_seconds=(
            None if largest_sector is None else abs(largest_sector.delta_seconds or 0.0)
        ),
        key_corner=None if key_corner is None else key_corner.name,
        corner_loss_seconds=(None if key_corner is None else abs(key_corner.time_delta_seconds)),
        minimum_speed_advantage_kph=speed_advantage,
        earlier_full_throttle_metres=throttle_advantage,
        text=" ".join(sentences),
    )


def _explain_tied_laps(
    lap_a: LapSummary,
    lap_b: LapSummary,
    sectors: tuple[SectorComparison, SectorComparison, SectorComparison],
    corners: tuple[CornerComparison, ...],
) -> LapExplanation:
    distinguish_laps = lap_a.driver == lap_b.driver
    identity_a = _lap_identity(lap_a, distinguish_laps)
    identity_b = _lap_identity(lap_b, distinguish_laps)
    largest_sector = max(
        (sector for sector in sectors if sector.delta_seconds not in (None, 0.0)),
        key=lambda sector: abs(sector.delta_seconds or 0.0),
        default=None,
    )
    key_corner = max(
        (corner for corner in corners if abs(corner.time_delta_seconds) > 0.001),
        key=lambda corner: abs(corner.time_delta_seconds),
        default=None,
    )

    sentences = [f"{identity_a} and {identity_b} have identical recorded lap times."]
    if largest_sector is not None:
        slower = identity_b if (largest_sector.delta_seconds or 0.0) > 0 else identity_a
        faster = identity_a if slower == identity_b else identity_b
        sentences.append(
            f"{slower} loses approximately "
            f"{abs(largest_sector.delta_seconds or 0.0):.3f} seconds to {faster} in "
            f"Sector {largest_sector.sector}."
        )

    speed_advantage: float | None = None
    throttle_advantage: float | None = None
    if key_corner is not None:
        corner_gainer = identity_a if key_corner.time_delta_seconds > 0 else identity_b
        evidence = [f"{corner_gainer} gains time"]
        speed_delta = key_corner.lap_a_min_speed_kph - key_corner.lap_b_min_speed_kph
        if abs(speed_delta) >= 0.5:
            speed_advantage = abs(speed_delta)
            speed_driver = identity_a if speed_delta > 0 else identity_b
            evidence.append(
                f"{speed_driver} carries {speed_advantage:.1f} km/h more minimum speed"
            )
        throttle_a = key_corner.lap_a_full_throttle_metres
        throttle_b = key_corner.lap_b_full_throttle_metres
        if throttle_a is not None and throttle_b is not None:
            throttle_delta = throttle_b - throttle_a
            if abs(throttle_delta) >= 1.0:
                throttle_advantage = abs(throttle_delta)
                throttle_driver = identity_a if throttle_delta > 0 else identity_b
                evidence.append(
                    f"{throttle_driver} reaches full throttle "
                    f"{throttle_advantage:.0f} metres earlier"
                )
        sentences.append(
            f"The largest localized difference is approximately "
            f"{abs(key_corner.time_delta_seconds):.3f} seconds at "
            f"{key_corner.name}, where " + " and ".join(evidence) + "."
        )

    return LapExplanation(
        faster_driver=None,
        slower_driver=None,
        largest_loss_sector=None if largest_sector is None else largest_sector.sector,
        sector_loss_seconds=(
            None if largest_sector is None else abs(largest_sector.delta_seconds or 0.0)
        ),
        key_corner=None if key_corner is None else key_corner.name,
        corner_loss_seconds=(None if key_corner is None else abs(key_corner.time_delta_seconds)),
        minimum_speed_advantage_kph=speed_advantage,
        earlier_full_throttle_metres=throttle_advantage,
        text=" ".join(sentences),
    )


def _lap_identity(lap: LapSummary, include_number: bool) -> str:
    return f"{lap.driver} lap {lap.lap_number}" if include_number else lap.driver


def _largest_sector_loss(
    sectors: tuple[SectorComparison, SectorComparison, SectorComparison], direction: float
) -> SectorComparison | None:
    measured = [
        sector
        for sector in sectors
        if sector.delta_seconds is not None and sector.delta_seconds * direction > 0
    ]
    return max(measured, key=lambda sector: (sector.delta_seconds or 0.0) * direction, default=None)


def _largest_corner_loss(
    corners: tuple[CornerComparison, ...], direction: float
) -> CornerComparison | None:
    measured = [corner for corner in corners if corner.time_delta_seconds * direction > 0.001]
    return max(measured, key=lambda corner: corner.time_delta_seconds * direction, default=None)


def _speed_advantage(corner: CornerComparison | None, direction: float) -> float | None:
    if corner is None:
        return None
    advantage = (
        corner.lap_a_min_speed_kph - corner.lap_b_min_speed_kph
        if direction > 0
        else corner.lap_b_min_speed_kph - corner.lap_a_min_speed_kph
    )
    return advantage if advantage >= 0.5 else None


def _throttle_advantage(corner: CornerComparison | None, direction: float) -> float | None:
    if (
        corner is None
        or corner.lap_a_full_throttle_metres is None
        or corner.lap_b_full_throttle_metres is None
    ):
        return None
    advantage = (
        corner.lap_b_full_throttle_metres - corner.lap_a_full_throttle_metres
        if direction > 0
        else corner.lap_a_full_throttle_metres - corner.lap_b_full_throttle_metres
    )
    return advantage if advantage >= 1.0 else None

"""Deterministic lap selection from normalized session data."""

from __future__ import annotations

import pandas as pd

from f1pi.analysis.models import LapSelection, LapSummary
from f1pi.domain.exceptions import LapNotFoundError

NANOSECONDS_PER_SECOND = 1_000_000_000


def select_lap(laps: pd.DataFrame, selection: LapSelection) -> pd.Series:
    candidates = laps.loc[
        laps["driver"].str.upper().eq(selection.driver) & laps["lap_time_ns"].notna()
    ]
    if selection.accurate_only:
        candidates = candidates.loc[candidates["is_accurate"].fillna(False)]
    if selection.lap_number is not None:
        candidates = candidates.loc[candidates["lap_number"].eq(selection.lap_number)]

    candidates = candidates.loc[candidates["lap_start_time_ns"].notna()]
    if candidates.empty:
        label = "fastest lap" if selection.lap_number is None else f"lap {selection.lap_number}"
        accuracy = " accurate" if selection.accurate_only else ""
        raise LapNotFoundError(
            f"no{accuracy} {label} with timing data is available for {selection.driver}"
        )
    if selection.lap_number is None:
        position = int(candidates["lap_time_ns"].astype("int64").to_numpy().argmin())
        return candidates.iloc[position]
    return candidates.sort_index().iloc[0]


def summarize_lap(lap: pd.Series) -> LapSummary:
    sectors = tuple(_seconds(lap[f"sector{number}_time_ns"]) for number in range(1, 4))
    accurate = lap["is_accurate"]
    return LapSummary(
        driver=str(lap["driver"]),
        lap_number=int(lap["lap_number"]),
        lap_time_seconds=float(lap["lap_time_ns"]) / NANOSECONDS_PER_SECOND,
        sector_times_seconds=(sectors[0], sectors[1], sectors[2]),
        is_accurate=None if pd.isna(accurate) else bool(accurate),
    )


def _seconds(value: object) -> float | None:
    if value is None or value is pd.NA:
        return None
    converted = float(value)  # type: ignore[arg-type]
    return None if pd.isna(converted) else converted / NANOSECONDS_PER_SECOND

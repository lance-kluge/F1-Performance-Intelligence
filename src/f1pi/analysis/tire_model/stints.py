"""Deterministic extraction of physical tire stints from normalized laps."""

from __future__ import annotations

import pandas as pd


def extract_stints(laps: pd.DataFrame) -> pd.DataFrame:
    """Return laps with stable stint IDs and one-based stint lap indices."""
    ordered_laps = laps.copy().reset_index(drop=True)
    ordered_laps["_source_order"] = ordered_laps.index
    ordered_laps["driver"] = ordered_laps["driver"].astype("string").str.strip().str.upper()
    ordered_laps["compound"] = ordered_laps["compound"].astype("string").str.strip().str.upper()
    ordered_laps = ordered_laps.sort_values(
        ["driver", "lap_number", "_source_order"], na_position="last", kind="stable"
    ).reset_index(drop=True)

    stint_ids: list[str] = []
    lap_indices_within_stint: list[int] = []
    previous_driver: str | None = None
    stint_ordinal = 0
    lap_index_within_stint = 0
    previous_lap: pd.Series | None = None

    for _, lap in ordered_laps.iterrows():
        driver = "" if pd.isna(lap["driver"]) else str(lap["driver"])
        starts_new_stint = driver != previous_driver or previous_lap is None
        if not starts_new_stint and previous_lap is not None:
            starts_new_stint = _starts_new_stint(previous_lap, lap)
        if starts_new_stint:
            if driver != previous_driver:
                stint_ordinal = 0
            stint_ordinal += 1
            lap_index_within_stint = 1
        else:
            lap_index_within_stint += 1
        stint_ids.append(f"{driver or 'UNKNOWN'}:{stint_ordinal:02d}")
        lap_indices_within_stint.append(lap_index_within_stint)
        previous_driver = driver
        previous_lap = lap

    ordered_laps["stint_id"] = pd.Series(stint_ids, dtype="string")
    ordered_laps["stint_lap_index"] = pd.array(lap_indices_within_stint, dtype="Int64")
    return ordered_laps.drop(columns="_source_order")


def _starts_new_stint(previous_lap: pd.Series, current_lap: pd.Series) -> bool:
    previous_stint = previous_lap.get("stint")
    current_stint = current_lap.get("stint")
    if (
        pd.notna(previous_stint)
        and pd.notna(current_stint)
        and int(previous_stint) != int(current_stint)
    ):
        return True

    previous_compound = previous_lap.get("compound")
    current_compound = current_lap.get("compound")
    if (
        pd.notna(previous_compound)
        and pd.notna(current_compound)
        and str(previous_compound) != str(current_compound)
    ):
        return True

    previous_lap_number = previous_lap.get("lap_number")
    current_lap_number = current_lap.get("lap_number")
    if (
        pd.notna(previous_lap_number)
        and pd.notna(current_lap_number)
        and int(current_lap_number) != int(previous_lap_number) + 1
    ):
        return True

    previous_age = previous_lap.get("tyre_life")
    current_age = current_lap.get("tyre_life")
    return bool(
        pd.notna(previous_age)
        and pd.notna(current_age)
        and float(current_age) < float(previous_age)
    )

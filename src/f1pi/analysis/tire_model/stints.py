"""Deterministic extraction of physical tire stints from normalized laps."""

from __future__ import annotations

import pandas as pd


def extract_stints(laps: pd.DataFrame) -> pd.DataFrame:
    """Return laps with stable stint IDs and one-based stint lap indices."""
    output = laps.copy().reset_index(drop=True)
    output["_source_order"] = output.index
    output["driver"] = output["driver"].astype("string").str.strip().str.upper()
    output["compound"] = output["compound"].astype("string").str.strip().str.upper()
    output = output.sort_values(
        ["driver", "lap_number", "_source_order"], na_position="last", kind="stable"
    ).reset_index(drop=True)

    stint_ids: list[str] = []
    stint_indices: list[int] = []
    current_driver: str | None = None
    ordinal = 0
    index_in_stint = 0
    previous: pd.Series | None = None

    for _, lap in output.iterrows():
        driver = "" if pd.isna(lap["driver"]) else str(lap["driver"])
        starts_stint = driver != current_driver or previous is None
        if not starts_stint and previous is not None:
            starts_stint = _stint_boundary(previous, lap)
        if starts_stint:
            if driver != current_driver:
                ordinal = 0
            ordinal += 1
            index_in_stint = 1
        else:
            index_in_stint += 1
        stint_ids.append(f"{driver or 'UNKNOWN'}:{ordinal:02d}")
        stint_indices.append(index_in_stint)
        current_driver = driver
        previous = lap

    output["stint_id"] = pd.Series(stint_ids, dtype="string")
    output["stint_lap_index"] = pd.array(stint_indices, dtype="Int64")
    return output.drop(columns="_source_order")


def _stint_boundary(previous: pd.Series, current: pd.Series) -> bool:
    previous_stint = previous.get("stint")
    current_stint = current.get("stint")
    if (
        pd.notna(previous_stint)
        and pd.notna(current_stint)
        and int(previous_stint) != int(current_stint)
    ):
        return True

    previous_compound = previous.get("compound")
    current_compound = current.get("compound")
    if (
        pd.notna(previous_compound)
        and pd.notna(current_compound)
        and str(previous_compound) != str(current_compound)
    ):
        return True

    previous_lap = previous.get("lap_number")
    current_lap = current.get("lap_number")
    if (
        pd.notna(previous_lap)
        and pd.notna(current_lap)
        and int(current_lap) != int(previous_lap) + 1
    ):
        return True

    previous_age = previous.get("tyre_life")
    current_age = current.get("tyre_life")
    return bool(
        pd.notna(previous_age)
        and pd.notna(current_age)
        and float(current_age) < float(previous_age)
    )

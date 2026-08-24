"""Lap eligibility and track-condition feature construction."""

from __future__ import annotations

from collections.abc import Iterable

import numpy as np
import pandas as pd

from f1pi.analysis.models import DegradationMode, TireModelConfig, TireStintSummary
from f1pi.analysis.tire_model.stints import extract_stints
from f1pi.domain.exceptions import InsufficientTireDataError

WEATHER_FEATURES = (
    "track_temp",
    "air_temp",
    "humidity",
    "pressure",
    "wind_speed",
    "rainfall",
)
UNKNOWN_COMPOUND_LABELS = frozenset({"", "UNKNOWN"})


def prepare_observations(
    laps: pd.DataFrame,
    weather: pd.DataFrame,
    track_status: pd.DataFrame,
    config: TireModelConfig,
) -> pd.DataFrame:
    """Build one auditable modeling row for every session lap."""
    if track_status.empty:
        raise InsufficientTireDataError("track status is required to identify clean laps")

    output = extract_stints(laps)
    output["lap_time_seconds"] = _seconds(output["lap_time_ns"])
    output["lap_start_seconds"] = _seconds(output["lap_start_time_ns"])
    output["lap_end_seconds"] = output["lap_start_seconds"] + output["lap_time_seconds"]
    output["tire_age_laps"] = pd.to_numeric(output["tyre_life"], errors="coerce")
    maximum_lap = pd.to_numeric(output["lap_number"], errors="coerce").max()
    denominator = max(float(maximum_lap) - 1.0, 1.0)
    output["race_progress"] = (
        pd.to_numeric(output["lap_number"], errors="coerce") - 1.0
    ) / denominator

    weather_values = _weather_by_lap(output, weather)
    for feature in WEATHER_FEATURES:
        output[feature] = weather_values[feature]

    output["exclusion_reason"] = pd.Series("", index=output.index, dtype="string")
    required = [
        "driver",
        "compound",
        "lap_number",
        "lap_time_seconds",
        "lap_start_seconds",
        "tire_age_laps",
    ]
    _exclude(output, output[required].isna().any(axis=1), "missing_required")
    _exclude(
        output,
        output["compound"].fillna("").isin(UNKNOWN_COMPOUND_LABELS),
        "unknown_compound",
    )
    _exclude(output, output["is_accurate"].ne(True).fillna(True), "inaccurate")
    _exclude(output, output["deleted"].eq(True).fillna(False), "deleted")
    pit_lap = output["pit_in_time_ns"].notna() | output["pit_out_time_ns"].notna()
    _exclude(output, pit_lap, "pit_lap")
    _exclude(output, _non_green_laps(output, track_status), "non_green")

    if config.mode is DegradationMode.ADJUSTED:
        _exclude(
            output,
            output[list(WEATHER_FEATURES)].isna().any(axis=1),
            "missing_weather",
        )

    currently_eligible = output["exclusion_reason"].eq("")
    fastest = output.loc[currently_eligible].groupby(["driver", "compound"])[
        "lap_time_seconds"
    ].transform("min")
    slow = output.loc[currently_eligible, "lap_time_seconds"] > fastest * config.quick_lap_ratio
    _exclude(output, slow.reindex(output.index, fill_value=False), "slow_lap")

    currently_eligible = output["exclusion_reason"].eq("")
    eligible_counts = output.loc[currently_eligible].groupby("stint_id").size()
    short_ids = eligible_counts[eligible_counts < config.minimum_stint_laps].index
    _exclude(output, output["stint_id"].isin(short_ids), "short_stint")
    output["eligible"] = output["exclusion_reason"].eq("")
    return output


def summarize_stints(observations: pd.DataFrame) -> tuple[TireStintSummary, ...]:
    summaries: list[TireStintSummary] = []
    for stint_id, stint in observations.groupby("stint_id", sort=True):
        valid_laps = stint["lap_number"].dropna()
        valid_ages = stint["tire_age_laps"].dropna()
        if valid_laps.empty or valid_ages.empty:
            continue
        fresh_values = stint["fresh_tyre"].dropna()
        summaries.append(
            TireStintSummary(
                stint_id=str(stint_id),
                driver=_first_string(stint["driver"]),
                compound=_first_string(stint["compound"]),
                start_lap=int(valid_laps.min()),
                end_lap=int(valid_laps.max()),
                start_tire_age=float(valid_ages.min()),
                end_tire_age=float(valid_ages.max()),
                fresh_tyre=(None if fresh_values.empty else bool(fresh_values.iloc[0])),
                included_laps=int(stint["eligible"].sum()),
                excluded_laps=int((~stint["eligible"]).sum()),
            )
        )
    return tuple(summaries)


def supported_compounds(
    observations: pd.DataFrame, config: TireModelConfig
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    supported: list[str] = []
    warnings: list[str] = []
    eligible = observations.loc[observations["eligible"]]
    compounds = sorted(
        compound
        for compound in observations["compound"].dropna().astype(str).unique()
        if compound not in UNKNOWN_COMPOUND_LABELS
    )
    for compound in compounds:
        rows = eligible.loc[eligible["compound"].eq(compound)]
        enough = (
            len(rows) >= config.minimum_compound_laps
            and rows["stint_id"].nunique() >= config.minimum_compound_stints
            and rows["tire_age_laps"].nunique() >= 2
        )
        if enough:
            supported.append(str(compound))
        else:
            warnings.append(f"insufficient_compound_data:{compound}")
    return tuple(supported), tuple(warnings)


def _seconds(values: pd.Series) -> pd.Series:
    return pd.to_numeric(values, errors="coerce").astype("Float64") / 1_000_000_000.0


def _exclude(frame: pd.DataFrame, mask: pd.Series, reason: str) -> None:
    selected = mask.fillna(False) & frame["exclusion_reason"].eq("")
    frame.loc[selected, "exclusion_reason"] = reason


def _weather_by_lap(laps: pd.DataFrame, weather: pd.DataFrame) -> pd.DataFrame:
    result = pd.DataFrame(index=laps.index, columns=WEATHER_FEATURES, dtype=float)
    if weather.empty or "time_ns" not in weather:
        return result
    samples = weather.copy()
    samples["_time_seconds"] = _seconds(samples["time_ns"])
    samples = samples.dropna(subset=["_time_seconds"]).sort_values("_time_seconds")
    if samples.empty:
        return result

    for index, lap in laps.iterrows():
        start = lap["lap_start_seconds"]
        end = lap["lap_end_seconds"]
        if pd.isna(start) or pd.isna(end):
            continue
        within = samples["_time_seconds"].between(float(start), float(end), inclusive="both")
        selected = samples.loc[within]
        if selected.empty:
            midpoint = (float(start) + float(end)) / 2.0
            nearest = (samples["_time_seconds"] - midpoint).abs().idxmin()
            selected = samples.loc[[nearest]]
        for feature in WEATHER_FEATURES:
            if feature not in selected:
                continue
            values = selected[feature].dropna()
            if values.empty:
                continue
            if feature == "rainfall":
                result.loc[index, feature] = float(values.astype(bool).mean() >= 0.5)
            else:
                result.loc[index, feature] = float(pd.to_numeric(values).mean())
    return result


def _non_green_laps(laps: pd.DataFrame, status: pd.DataFrame) -> pd.Series:
    events = status.copy()
    events["_time_seconds"] = _seconds(events["time_ns"])
    events = events.dropna(subset=["_time_seconds"]).sort_values("_time_seconds")
    if events.empty:
        return pd.Series(True, index=laps.index)
    event_times = events["_time_seconds"].to_numpy(dtype=float)
    event_status = events["status"].astype("string").to_numpy()
    output: list[bool] = []
    for _, lap in laps.iterrows():
        start = lap["lap_start_seconds"]
        end = lap["lap_end_seconds"]
        if pd.isna(start) or pd.isna(end):
            output.append(False)
            continue
        active_index = max(int(np.searchsorted(event_times, float(start), side="right")) - 1, 0)
        overlapping: Iterable[object] = event_status[
            active_index : int(np.searchsorted(event_times, float(end), side="right"))
        ]
        output.append(any(str(value) != "1" for value in overlapping))
    return pd.Series(output, index=laps.index)


def _first_string(values: pd.Series) -> str:
    valid = values.dropna()
    return "" if valid.empty else str(valid.iloc[0])

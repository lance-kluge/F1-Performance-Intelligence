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

    observations = extract_stints(laps)
    observations["lap_time_seconds"] = _seconds(observations["lap_time_ns"])
    observations["lap_start_seconds"] = _seconds(observations["lap_start_time_ns"])
    observations["lap_end_seconds"] = (
        observations["lap_start_seconds"] + observations["lap_time_seconds"]
    )
    observations["tire_age_laps"] = pd.to_numeric(observations["tyre_life"], errors="coerce")
    maximum_lap = pd.to_numeric(observations["lap_number"], errors="coerce").max()
    denominator = max(float(maximum_lap) - 1.0, 1.0)
    observations["race_progress"] = (
        pd.to_numeric(observations["lap_number"], errors="coerce") - 1.0
    ) / denominator

    lap_weather = _weather_by_lap(observations, weather)
    for feature in WEATHER_FEATURES:
        observations[feature] = lap_weather[feature]

    observations["exclusion_reason"] = pd.Series("", index=observations.index, dtype="string")
    required_columns = [
        "driver",
        "compound",
        "lap_number",
        "lap_time_seconds",
        "lap_start_seconds",
        "tire_age_laps",
    ]
    _exclude(
        observations,
        observations[required_columns].isna().any(axis=1),
        "missing_required",
    )
    _exclude(
        observations,
        observations["compound"].fillna("").isin(UNKNOWN_COMPOUND_LABELS),
        "unknown_compound",
    )
    _exclude(observations, observations["is_accurate"].ne(True).fillna(True), "inaccurate")
    _exclude(observations, observations["deleted"].eq(True).fillna(False), "deleted")
    pit_lap_mask = observations["pit_in_time_ns"].notna() | observations["pit_out_time_ns"].notna()
    _exclude(observations, pit_lap_mask, "pit_lap")
    _exclude(observations, _non_green_laps(observations, track_status), "non_green")

    if config.mode is DegradationMode.ADJUSTED:
        _exclude(
            observations,
            observations[list(WEATHER_FEATURES)].isna().any(axis=1),
            "missing_weather",
        )

    eligible_mask = observations["exclusion_reason"].eq("")
    fastest_lap_times = (
        observations.loc[eligible_mask]
        .groupby(["driver", "compound"])["lap_time_seconds"]
        .transform("min")
    )
    slow_lap_mask = (
        observations.loc[eligible_mask, "lap_time_seconds"]
        > fastest_lap_times * config.quick_lap_ratio
    )
    _exclude(
        observations,
        slow_lap_mask.reindex(observations.index, fill_value=False),
        "slow_lap",
    )

    eligible_mask = observations["exclusion_reason"].eq("")
    eligible_laps_by_stint = observations.loc[eligible_mask].groupby("stint_id").size()
    short_stint_ids = eligible_laps_by_stint[
        eligible_laps_by_stint < config.minimum_stint_laps
    ].index
    _exclude(observations, observations["stint_id"].isin(short_stint_ids), "short_stint")
    observations["eligible"] = observations["exclusion_reason"].eq("")
    return observations


def summarize_stints(observations: pd.DataFrame) -> tuple[TireStintSummary, ...]:
    summaries: list[TireStintSummary] = []
    for stint_id, stint_observations in observations.groupby("stint_id", sort=True):
        lap_numbers = stint_observations["lap_number"].dropna()
        tire_ages = stint_observations["tire_age_laps"].dropna()
        if lap_numbers.empty or tire_ages.empty:
            continue
        fresh_tire_values = stint_observations["fresh_tyre"].dropna()
        summaries.append(
            TireStintSummary(
                stint_id=str(stint_id),
                driver=_first_string(stint_observations["driver"]),
                compound=_first_string(stint_observations["compound"]),
                start_lap=int(lap_numbers.min()),
                end_lap=int(lap_numbers.max()),
                start_tire_age=float(tire_ages.min()),
                end_tire_age=float(tire_ages.max()),
                fresh_tyre=(None if fresh_tire_values.empty else bool(fresh_tire_values.iloc[0])),
                included_laps=int(stint_observations["eligible"].sum()),
                excluded_laps=int((~stint_observations["eligible"]).sum()),
            )
        )
    return tuple(summaries)


def supported_compounds(
    observations: pd.DataFrame, config: TireModelConfig
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    supported: list[str] = []
    warnings: list[str] = []
    eligible_observations = observations.loc[observations["eligible"]]
    compounds = sorted(
        compound
        for compound in observations["compound"].dropna().astype(str).unique()
        if compound not in UNKNOWN_COMPOUND_LABELS
    )
    for compound in compounds:
        compound_observations = eligible_observations.loc[
            eligible_observations["compound"].eq(compound)
        ]
        has_sufficient_support = (
            len(compound_observations) >= config.minimum_compound_laps
            and compound_observations["stint_id"].nunique() >= config.minimum_compound_stints
            and compound_observations["tire_age_laps"].nunique() >= 2
        )
        if has_sufficient_support:
            supported.append(str(compound))
        else:
            warnings.append(f"insufficient_compound_data:{compound}")
    return tuple(supported), tuple(warnings)


def _seconds(nanoseconds: pd.Series) -> pd.Series:
    return pd.to_numeric(nanoseconds, errors="coerce").astype("Float64") / 1_000_000_000.0


def _exclude(observations: pd.DataFrame, exclusion_mask: pd.Series, exclusion_reason: str) -> None:
    newly_excluded = exclusion_mask.fillna(False) & observations["exclusion_reason"].eq("")
    observations.loc[newly_excluded, "exclusion_reason"] = exclusion_reason


def _weather_by_lap(laps: pd.DataFrame, weather: pd.DataFrame) -> pd.DataFrame:
    lap_weather = pd.DataFrame(index=laps.index, columns=WEATHER_FEATURES, dtype=float)
    if weather.empty or "time_ns" not in weather:
        return lap_weather
    weather_samples = weather.copy()
    weather_samples["_time_seconds"] = _seconds(weather_samples["time_ns"])
    weather_samples = weather_samples.dropna(subset=["_time_seconds"]).sort_values("_time_seconds")
    if weather_samples.empty:
        return lap_weather

    for lap_index, lap in laps.iterrows():
        lap_start = lap["lap_start_seconds"]
        lap_end = lap["lap_end_seconds"]
        if pd.isna(lap_start) or pd.isna(lap_end):
            continue
        samples_within_lap = weather_samples["_time_seconds"].between(
            float(lap_start), float(lap_end), inclusive="both"
        )
        representative_samples = weather_samples.loc[samples_within_lap]
        if representative_samples.empty:
            lap_midpoint = (float(lap_start) + float(lap_end)) / 2.0
            nearest_sample_index = (weather_samples["_time_seconds"] - lap_midpoint).abs().idxmin()
            representative_samples = weather_samples.loc[[nearest_sample_index]]
        for feature in WEATHER_FEATURES:
            if feature not in representative_samples:
                continue
            feature_values = representative_samples[feature].dropna()
            if feature_values.empty:
                continue
            if feature == "rainfall":
                lap_weather.loc[lap_index, feature] = float(
                    feature_values.astype(bool).mean() >= 0.5
                )
            else:
                lap_weather.loc[lap_index, feature] = float(pd.to_numeric(feature_values).mean())
    return lap_weather


def _non_green_laps(laps: pd.DataFrame, track_status: pd.DataFrame) -> pd.Series:
    status_events = track_status.copy()
    status_events["_time_seconds"] = _seconds(status_events["time_ns"])
    status_events = status_events.dropna(subset=["_time_seconds"]).sort_values("_time_seconds")
    if status_events.empty:
        return pd.Series(True, index=laps.index)
    event_times = status_events["_time_seconds"].to_numpy(dtype=float)
    event_codes = status_events["status"].astype("string").to_numpy()
    non_green_flags: list[bool] = []
    for _, lap in laps.iterrows():
        lap_start = lap["lap_start_seconds"]
        lap_end = lap["lap_end_seconds"]
        if pd.isna(lap_start) or pd.isna(lap_end):
            non_green_flags.append(False)
            continue
        status_at_lap_start_index = max(
            int(np.searchsorted(event_times, float(lap_start), side="right")) - 1, 0
        )
        overlapping_statuses: Iterable[object] = event_codes[
            status_at_lap_start_index : int(
                np.searchsorted(event_times, float(lap_end), side="right")
            )
        ]
        non_green_flags.append(any(str(status_code) != "1" for status_code in overlapping_statuses))
    return pd.Series(non_green_flags, index=laps.index)


def _first_string(strings: pd.Series) -> str:
    non_null_values = strings.dropna()
    return "" if non_null_values.empty else str(non_null_values.iloc[0])

"""Spatial synchronization of independently sampled lap telemetry."""

from __future__ import annotations

from typing import cast

import numpy as np
import pandas as pd
from numpy.typing import NDArray

from f1pi.analysis.models import (
    CornerComparison,
    LapSummary,
    StraightComparison,
    SynchronizationConfig,
)
from f1pi.analysis.models.prepared_trace import PreparedTrace
from f1pi.domain.exceptions import TelemetryNotAvailableError

NANOSECONDS_PER_SECOND = 1_000_000_000


def prepare_trace(
    car: pd.DataFrame,
    position: pd.DataFrame,
    lap: pd.Series,
) -> PreparedTrace:
    start_ns = int(lap["lap_start_time_ns"])
    duration_ns = int(lap["lap_time_ns"])
    end_ns = start_ns + duration_ns
    target_time = _lap_sample_times(car, start_ns, end_ns)

    speed = _interpolate(car, "speed", target_time, required=True)
    throttle = _interpolate(car, "throttle", target_time)
    brake = _interpolate(car, "brake", target_time)
    gear = _step_interpolate(car, "n_gear", target_time)
    x = _interpolate(position, "x", target_time, required=True)
    y = _interpolate(position, "y", target_time, required=True)

    elapsed = (target_time - start_ns) / NANOSECONDS_PER_SECOND
    distance_steps = np.diff(elapsed) * (speed[:-1] + speed[1:]) / (2 * 3.6)
    distance = np.concatenate((np.array([0.0]), np.cumsum(distance_steps)))
    keep = np.concatenate((np.array([True]), np.diff(distance) > 1e-6))
    if keep.sum() < 10 or distance[-1] < 100:
        raise TelemetryNotAvailableError("lap telemetry does not cover a complete on-track lap")

    return PreparedTrace(
        distance=distance[keep],
        elapsed=elapsed[keep],
        speed=speed[keep],
        throttle=throttle[keep],
        brake=brake[keep],
        gear=gear[keep],
        x=x[keep],
        y=y[keep],
    )


def synchronize_traces(
    lap_a: PreparedTrace,
    lap_b: PreparedTrace,
    summary_a: LapSummary,
    config: SynchronizationConfig,
) -> pd.DataFrame:
    progress = np.linspace(0.0, 1.0, config.sample_count)
    lap_a_brake = _spatial_interpolate(lap_a, lap_a.brake, progress)
    lap_b_brake = _spatial_interpolate(lap_b, lap_b.brake, progress)
    lap_a_gear = _spatial_step_interpolate(lap_a, lap_a.gear, progress)
    lap_b_gear = _spatial_step_interpolate(lap_b, lap_b.gear, progress)
    synchronized = pd.DataFrame(
        {
            "distance_metres": progress * lap_a.length_metres,
            "relative_distance": progress,
            "lap_a_elapsed_seconds": _spatial_interpolate(lap_a, lap_a.elapsed, progress),
            "lap_b_elapsed_seconds": _spatial_interpolate(lap_b, lap_b.elapsed, progress),
            "lap_a_speed_kph": _spatial_interpolate(lap_a, lap_a.speed, progress),
            "lap_b_speed_kph": _spatial_interpolate(lap_b, lap_b.speed, progress),
            "lap_a_throttle_percent": _spatial_interpolate(lap_a, lap_a.throttle, progress),
            "lap_b_throttle_percent": _spatial_interpolate(lap_b, lap_b.throttle, progress),
            "lap_a_brake": _nullable_brake(lap_a_brake),
            "lap_b_brake": _nullable_brake(lap_b_brake),
            "lap_a_gear": _nullable_integer(lap_a_gear),
            "lap_b_gear": _nullable_integer(lap_b_gear),
            "lap_a_x": _spatial_interpolate(lap_a, lap_a.x, progress),
            "lap_a_y": _spatial_interpolate(lap_a, lap_a.y, progress),
            "lap_b_x": _spatial_interpolate(lap_b, lap_b.x, progress),
            "lap_b_y": _spatial_interpolate(lap_b, lap_b.y, progress),
        }
    )
    synchronized["time_delta_seconds"] = (
        synchronized["lap_b_elapsed_seconds"] - synchronized["lap_a_elapsed_seconds"]
    )
    synchronized["local_time_delta_seconds"] = _local_delta_change(
        synchronized["time_delta_seconds"].to_numpy(dtype=float),
        config.local_dominance_window_fraction,
    )
    synchronized["sector"] = _sector_numbers(
        synchronized["lap_a_elapsed_seconds"].to_numpy(), summary_a.sector_times_seconds
    )
    return synchronized


def _nullable_brake(values: NDArray[np.float64]) -> pd.arrays.BooleanArray:
    brake = pd.array(values >= 0.5, dtype="boolean")
    brake[np.isnan(values)] = pd.NA
    return brake


def _nullable_integer(values: NDArray[np.float64]) -> pd.arrays.IntegerArray:
    output = pd.array(np.rint(values), dtype="Int64")
    output[np.isnan(values)] = pd.NA
    return output


def compare_corners(
    telemetry: pd.DataFrame,
    corners: pd.DataFrame,
    config: SynchronizationConfig,
) -> tuple[CornerComparison, ...]:
    if corners.empty:
        return ()
    marker_indices = _marker_indices(telemetry, corners)
    marker_distances = telemetry.iloc[marker_indices]["distance_metres"].to_numpy(dtype=float)
    output: list[CornerComparison] = []
    lap_length = float(telemetry["distance_metres"].iloc[-1])

    for offset, (_, corner) in enumerate(corners.iterrows()):
        centre = float(marker_distances[offset])
        before = max(0.0, centre - config.corner_window_metres)
        after = min(lap_length, centre + config.corner_window_metres)
        window = telemetry["distance_metres"].between(before, after)
        if not window.any():
            continue

        next_centre = (
            float(marker_distances[offset + 1])
            if offset + 1 < len(marker_distances)
            else lap_length
        )
        throttle_end = min(lap_length, centre + 350.0, (centre + next_centre) / 2)
        output.append(
            CornerComparison(
                number=int(corner["number"]),
                letter="" if pd.isna(corner["letter"]) else str(corner["letter"]),
                distance_metres=centre,
                time_delta_seconds=_delta_change(telemetry, before, after),
                lap_a_min_speed_kph=float(telemetry.loc[window, "lap_a_speed_kph"].min()),
                lap_b_min_speed_kph=float(telemetry.loc[window, "lap_b_speed_kph"].min()),
                lap_a_full_throttle_metres=_full_throttle_distance(
                    telemetry, "lap_a_throttle_percent", centre, throttle_end, config
                ),
                lap_b_full_throttle_metres=_full_throttle_distance(
                    telemetry, "lap_b_throttle_percent", centre, throttle_end, config
                ),
            )
        )
    return tuple(output)


def compare_straights(
    telemetry: pd.DataFrame,
    corners: tuple[CornerComparison, ...],
    config: SynchronizationConfig,
) -> tuple[StraightComparison, ...]:
    """Compare meaningful straights between fixed corner-analysis windows."""
    if len(corners) < 2:
        return ()
    ordered = tuple(sorted(corners, key=lambda corner: corner.distance_metres))
    lap_length = float(telemetry["distance_metres"].iloc[-1])
    output: list[StraightComparison] = []

    for index, current in enumerate(ordered):
        following = ordered[(index + 1) % len(ordered)]
        start = min(lap_length, current.distance_metres + config.corner_window_metres)
        end = max(0.0, following.distance_metres - config.corner_window_metres)
        wraps_finish_line = index == len(ordered) - 1
        length = (lap_length - start + end) if wraps_finish_line else end - start
        if length < config.minimum_straight_metres:
            continue
        if wraps_finish_line:
            delta = _delta_change(telemetry, start, lap_length) + _delta_change(
                telemetry, 0.0, end
            )
        else:
            delta = _delta_change(telemetry, start, end)
        output.append(
            StraightComparison(
                start_turn=current.name,
                end_turn=following.name,
                start_distance_metres=start,
                end_distance_metres=end,
                length_metres=length,
                time_delta_seconds=delta,
            )
        )
    return tuple(output)


def _lap_sample_times(car: pd.DataFrame, start_ns: int, end_ns: int) -> NDArray[np.float64]:
    valid = car.loc[car["session_time_ns"].notna(), "session_time_ns"].astype("int64")
    if valid.empty or valid.min() > start_ns or valid.max() < end_ns:
        raise TelemetryNotAvailableError("car telemetry does not span the selected lap")
    within = valid.loc[valid.between(start_ns, end_ns)].to_numpy(dtype=float)
    times = np.unique(np.concatenate((within, np.array([float(start_ns), float(end_ns)]))))
    if len(times) < 10:
        raise TelemetryNotAvailableError("selected lap has too few car telemetry samples")
    return times


def _interpolate(
    frame: pd.DataFrame,
    column: str,
    target_time: NDArray[np.float64],
    *,
    required: bool = False,
) -> NDArray[np.float64]:
    if column not in frame:
        if required:
            raise TelemetryNotAvailableError(f"{column} telemetry is unavailable")
        return np.full(len(target_time), np.nan)
    valid = frame.loc[
        frame["session_time_ns"].notna() & frame[column].notna(),
        ["session_time_ns", column],
    ].sort_values("session_time_ns")
    valid = valid.drop_duplicates("session_time_ns", keep="last")
    if len(valid) < 2:
        if required:
            raise TelemetryNotAvailableError(f"{column} telemetry is unavailable")
        return np.full(len(target_time), np.nan)
    time = valid["session_time_ns"].to_numpy(dtype=float)
    if required and (time[0] > target_time[0] or time[-1] < target_time[-1]):
        raise TelemetryNotAvailableError(f"{column} telemetry does not span the selected lap")
    values = valid[column].astype(float).to_numpy()
    return np.interp(target_time, time, values, left=np.nan, right=np.nan)


def _step_interpolate(
    frame: pd.DataFrame,
    column: str,
    target_time: NDArray[np.float64],
) -> NDArray[np.float64]:
    if column not in frame:
        return np.full(len(target_time), np.nan)
    valid = frame.loc[
        frame["session_time_ns"].notna() & frame[column].notna(),
        ["session_time_ns", column],
    ].sort_values("session_time_ns")
    valid = valid.drop_duplicates("session_time_ns", keep="last")
    if valid.empty:
        return np.full(len(target_time), np.nan)
    time = valid["session_time_ns"].to_numpy(dtype=float)
    values = valid[column].astype(float).to_numpy()
    indices = np.searchsorted(time, target_time, side="right") - 1
    output = np.full(len(target_time), np.nan)
    covered = (indices >= 0) & (target_time <= time[-1])
    output[covered] = values[indices[covered]]
    return output


def _spatial_interpolate(
    trace: PreparedTrace,
    values: NDArray[np.float64],
    progress: NDArray[np.float64],
) -> NDArray[np.float64]:
    trace_progress = trace.distance / trace.length_metres
    valid = ~np.isnan(values)
    if valid.sum() < 2:
        return np.full(len(progress), np.nan)
    return np.interp(progress, trace_progress[valid], values[valid], left=np.nan, right=np.nan)


def _spatial_step_interpolate(
    trace: PreparedTrace,
    values: NDArray[np.float64],
    progress: NDArray[np.float64],
) -> NDArray[np.float64]:
    trace_progress = trace.distance / trace.length_metres
    valid = ~np.isnan(values)
    if not valid.any():
        return np.full(len(progress), np.nan)
    valid_progress = trace_progress[valid]
    valid_values = values[valid]
    indices = np.searchsorted(valid_progress, progress, side="right") - 1
    output = np.full(len(progress), np.nan)
    covered = (indices >= 0) & (progress <= valid_progress[-1])
    output[covered] = valid_values[indices[covered]]
    return output


def _local_delta_change(
    cumulative_delta: NDArray[np.float64], window_fraction: float
) -> NDArray[np.float64]:
    """Return time gained across a centered, finish-line-aware lap window."""
    half_window = max(1, round(len(cumulative_delta) * window_fraction / 2))
    last = len(cumulative_delta) - 1
    output = np.empty(len(cumulative_delta), dtype=float)
    for index in range(len(cumulative_delta)):
        before = index - half_window
        after = index + half_window
        if before < 0:
            output[index] = (
                cumulative_delta[after] - cumulative_delta[0]
                + cumulative_delta[last]
                - cumulative_delta[last + before]
            )
        elif after > last:
            output[index] = (
                cumulative_delta[last] - cumulative_delta[before]
                + cumulative_delta[after - last]
                - cumulative_delta[0]
            )
        else:
            output[index] = cumulative_delta[after] - cumulative_delta[before]
    return output


def _sector_numbers(
    elapsed: NDArray[np.float64],
    sectors: tuple[float | None, float | None, float | None],
) -> NDArray[np.float64]:
    if sectors[0] is None or sectors[1] is None:
        return np.full(len(elapsed), np.nan)
    return np.where(
        elapsed <= sectors[0],
        1.0,
        np.where(elapsed <= sectors[0] + sectors[1], 2.0, 3.0),
    )


def _marker_indices(telemetry: pd.DataFrame, corners: pd.DataFrame) -> NDArray[np.int64]:
    track_xy = telemetry[["lap_a_x", "lap_a_y"]].to_numpy(dtype=float)
    marker_xy = corners[["x", "y"]].to_numpy(dtype=float)
    differences = track_xy[np.newaxis, :, :] - marker_xy[:, np.newaxis, :]
    squared_distance = np.square(differences).sum(axis=2)
    indices = np.argmin(squared_distance, axis=1).astype(np.int64)
    return cast(NDArray[np.int64], indices)


def _delta_change(telemetry: pd.DataFrame, start: float, end: float) -> float:
    distance = telemetry["distance_metres"].to_numpy(dtype=float)
    delta = telemetry["time_delta_seconds"].to_numpy(dtype=float)
    return float(np.interp(end, distance, delta) - np.interp(start, distance, delta))


def _full_throttle_distance(
    telemetry: pd.DataFrame,
    column: str,
    start: float,
    end: float,
    config: SynchronizationConfig,
) -> float | None:
    window = telemetry.loc[
        telemetry["distance_metres"].between(start, end), ["distance_metres", column]
    ]
    reached = window.loc[window[column].ge(config.full_throttle_percent)]
    return None if reached.empty else float(reached["distance_metres"].iloc[0])

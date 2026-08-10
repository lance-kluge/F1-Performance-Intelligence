"""Spatial synchronization of independently sampled lap telemetry."""

from __future__ import annotations

from typing import cast

import numpy as np
import pandas as pd
from numpy.typing import NDArray

from f1pi.analysis.models import CornerComparison, LapSummary, SynchronizationConfig
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
            "lap_a_x": _spatial_interpolate(lap_a, lap_a.x, progress),
            "lap_a_y": _spatial_interpolate(lap_a, lap_a.y, progress),
            "lap_b_x": _spatial_interpolate(lap_b, lap_b.x, progress),
            "lap_b_y": _spatial_interpolate(lap_b, lap_b.y, progress),
        }
    )
    synchronized["time_delta_seconds"] = (
        synchronized["lap_b_elapsed_seconds"] - synchronized["lap_a_elapsed_seconds"]
    )
    synchronized["sector"] = _sector_numbers(
        synchronized["lap_a_elapsed_seconds"].to_numpy(), summary_a.sector_times_seconds
    )
    return synchronized


def _nullable_brake(values: NDArray[np.float64]) -> pd.arrays.BooleanArray:
    brake = pd.array(values >= 0.5, dtype="boolean")
    brake[np.isnan(values)] = pd.NA
    return brake


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

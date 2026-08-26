"""Lap-resolution full-field Monte Carlo race simulation."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from f1pi.analysis.models import (
    NeutralizationEvent,
    NeutralizationKind,
    StrategyPlan,
    StrategySimulationConfig,
)
from f1pi.analysis.strategy_simulator.calibration import CalibratedModels
from f1pi.analysis.strategy_simulator.preparation import GREEN, PreparedRace


@dataclass(frozen=True, slots=True)
class SharedRandomness:
    coefficients: np.ndarray
    pace_uniforms: np.ndarray
    traffic_uniforms: np.ndarray
    pit_uniforms: np.ndarray


@dataclass(frozen=True, slots=True)
class SimulationRun:
    final_positions: np.ndarray
    final_completed_laps: np.ndarray
    final_elapsed_seconds: np.ndarray
    final_gaps_seconds: np.ndarray
    target_positions: np.ndarray
    target_completed_laps: np.ndarray
    target_elapsed_seconds: np.ndarray
    target_gaps_seconds: np.ndarray
    position_history: np.ndarray
    elapsed_history: np.ndarray
    gap_history: np.ndarray


def shared_randomness(
    prepared: PreparedRace,
    models: CalibratedModels,
    config: StrategySimulationConfig,
) -> SharedRandomness:
    random = np.random.default_rng(config.random_seed)
    shape = (prepared.race_laps + 1, config.iterations, len(prepared.initial_states))
    return SharedRandomness(
        coefficients=models.pace.sample_coefficients(random, config.iterations),
        pace_uniforms=random.random(shape),
        traffic_uniforms=random.random(shape),
        pit_uniforms=random.random(shape),
    )


def simulate_strategy(
    prepared: PreparedRace,
    models: CalibratedModels,
    config: StrategySimulationConfig,
    target_driver: str,
    target_strategy: StrategyPlan,
    events: tuple[NeutralizationEvent, ...],
    randomness: SharedRandomness,
) -> SimulationRun:
    states = prepared.initial_states
    drivers = tuple(state.driver for state in states)
    driver_count = len(drivers)
    target_index = drivers.index(target_driver)
    iterations = config.iterations
    elapsed = np.repeat(
        np.asarray([state.elapsed_seconds for state in states], dtype=float)[None, :],
        iterations,
        axis=0,
    )
    completed = np.repeat(
        np.asarray([state.completed_laps for state in states], dtype=int)[None, :],
        iterations,
        axis=0,
    )
    maximum_laps = np.asarray([state.maximum_laps for state in states], dtype=int)
    compounds = np.asarray([state.compound for state in states], dtype=object)
    tire_ages = np.asarray([state.tire_age_laps for state in states], dtype=float)
    newly_fitted_tires = np.zeros(driver_count, dtype=bool)
    strategy_by_driver = {driver: prepared.observed_plans[driver] for driver in drivers}
    strategy_by_driver[target_driver] = target_strategy
    stop_maps = {
        driver: {stop.after_lap: stop for stop in plan.stops}
        for driver, plan in strategy_by_driver.items()
    }
    events_by_lap = {
        lap: event for event in events for lap in range(event.start_lap, event.end_lap + 1)
    }

    simulated_laps = prepared.race_laps - config_start_lap(prepared)
    position_history = np.zeros((iterations, simulated_laps, driver_count), dtype=np.int16)
    elapsed_history = np.zeros((iterations, simulated_laps, driver_count), dtype=float)
    gap_history = np.zeros((iterations, simulated_laps, driver_count), dtype=float)

    history_index = 0
    for lap_number in range(config_start_lap(prepared) + 1, prepared.race_laps + 1):
        active_driver = lap_number <= maximum_laps
        if not np.any(active_driver):
            break
        tire_ages[active_driver & ~newly_fitted_tires] += 1.0
        newly_fitted_tires[:] = False
        pace = models.pace.predict(
            lap_number,
            drivers,
            compounds,
            tire_ages,
            randomness.coefficients,
        )
        pace += models.pace.residual_draws(drivers, randomness.pace_uniforms[lap_number])
        pace = np.clip(pace, 30.0, 600.0)

        event = events_by_lap.get(lap_number)
        neutralization_parameters = None
        if event is not None:
            neutralization_parameters = models.neutralization.parameters(
                event.kind, event.assumptions
            )
            pace *= neutralization_parameters.lap_time_multiplier
        else:
            gaps = _gaps_by_elapsed(elapsed, completed, active_driver)
            pace += models.traffic.penalties(gaps, randomness.traffic_uniforms[lap_number])

        pace[:, ~active_driver] = 0.0
        elapsed += pace
        completed[:, active_driver] += 1

        for driver_index, driver in enumerate(drivers):
            stop = stop_maps[driver].get(lap_number)
            if stop is None or not active_driver[driver_index]:
                continue
            pit_losses = models.pit_loss.losses(
                GREEN, randomness.pit_uniforms[lap_number, :, driver_index]
            )
            if neutralization_parameters is not None:
                pit_losses *= neutralization_parameters.pit_loss_multiplier
            elapsed[:, driver_index] += pit_losses
            compounds[driver_index] = stop.compound
            tire_ages[driver_index] = stop.starting_tire_age_laps
            newly_fitted_tires[driver_index] = True

        if (
            event is not None
            and event.kind is NeutralizationKind.SAFETY_CAR
            and neutralization_parameters is not None
        ):
            _compress_field(
                elapsed,
                completed,
                active_driver,
                neutralization_parameters.restart_gap_seconds,
            )

        positions, gaps = _positions_and_gaps(elapsed, completed)
        position_history[:, history_index, :] = positions
        elapsed_history[:, history_index, :] = elapsed
        gap_history[:, history_index, :] = gaps
        history_index += 1

    if history_index < simulated_laps:
        position_history = position_history[:, :history_index, :]
        elapsed_history = elapsed_history[:, :history_index, :]
        gap_history = gap_history[:, :history_index, :]
    final_positions, final_gaps = _positions_and_gaps(elapsed, completed)
    return SimulationRun(
        final_positions=final_positions,
        final_completed_laps=completed.copy(),
        final_elapsed_seconds=elapsed.copy(),
        final_gaps_seconds=final_gaps,
        target_positions=final_positions[:, target_index],
        target_completed_laps=completed[:, target_index],
        target_elapsed_seconds=elapsed[:, target_index],
        target_gaps_seconds=final_gaps[:, target_index],
        position_history=position_history,
        elapsed_history=elapsed_history,
        gap_history=gap_history,
    )


def trace_distribution_frame(
    run: SimulationRun,
    prepared: PreparedRace,
    scenario: str,
    strategy: str,
    config: StrategySimulationConfig,
) -> pd.DataFrame:
    lower_quantile = (1.0 - config.confidence_level) / 2.0
    upper_quantile = 1.0 - lower_quantile
    drivers = tuple(state.driver for state in prepared.initial_states)
    rows: list[dict[str, object]] = []
    for lap_offset in range(run.position_history.shape[1]):
        lap_number = config_start_lap(prepared) + lap_offset + 1
        for driver_index, driver in enumerate(drivers):
            positions = run.position_history[:, lap_offset, driver_index]
            elapsed = run.elapsed_history[:, lap_offset, driver_index]
            gaps = run.gap_history[:, lap_offset, driver_index]
            rows.append(
                {
                    "scenario": scenario,
                    "strategy": strategy,
                    "driver": driver,
                    "lap_number": lap_number,
                    "position_lower": float(np.quantile(positions, lower_quantile)),
                    "position_median": float(np.median(positions)),
                    "position_upper": float(np.quantile(positions, upper_quantile)),
                    "elapsed_lower_seconds": float(np.quantile(elapsed, lower_quantile)),
                    "elapsed_median_seconds": float(np.median(elapsed)),
                    "elapsed_upper_seconds": float(np.quantile(elapsed, upper_quantile)),
                    "gap_lower_seconds": _nan_quantile(gaps, lower_quantile),
                    "gap_median_seconds": _nan_quantile(gaps, 0.5),
                    "gap_upper_seconds": _nan_quantile(gaps, upper_quantile),
                }
            )
    return pd.DataFrame(rows)


def config_start_lap(prepared: PreparedRace) -> int:
    return max(state.completed_laps for state in prepared.initial_states)


def _nan_quantile(values: np.ndarray, quantile: float) -> float:
    finite_values = values[np.isfinite(values)]
    return float(np.quantile(finite_values, quantile)) if len(finite_values) else float("nan")


def _gaps_by_elapsed(
    elapsed: np.ndarray, completed: np.ndarray, active_driver: np.ndarray
) -> np.ndarray:
    positions, _ = _positions_and_gaps(elapsed, completed)
    gaps = np.full_like(elapsed, np.inf, dtype=float)
    for iteration in range(elapsed.shape[0]):
        order = np.argsort(positions[iteration])
        for order_index in range(1, len(order)):
            driver = order[order_index]
            ahead = order[order_index - 1]
            if (
                not active_driver[driver]
                or completed[iteration, driver] != completed[iteration, ahead]
            ):
                continue
            gaps[iteration, driver] = max(
                elapsed[iteration, driver] - elapsed[iteration, ahead], 0.0
            )
    return gaps


def _positions_and_gaps(
    elapsed: np.ndarray, completed: np.ndarray
) -> tuple[np.ndarray, np.ndarray]:
    positions = np.empty_like(completed, dtype=np.int16)
    gaps = np.full_like(elapsed, np.nan, dtype=float)
    for iteration in range(elapsed.shape[0]):
        order = np.lexsort((elapsed[iteration], -completed[iteration]))
        positions[iteration, order] = np.arange(1, len(order) + 1, dtype=np.int16)
        leader = order[0]
        same_lap = completed[iteration] == completed[iteration, leader]
        gaps[iteration, same_lap] = np.maximum(
            elapsed[iteration, same_lap] - elapsed[iteration, leader], 0.0
        )
    return positions, gaps


def _compress_field(
    elapsed: np.ndarray,
    completed: np.ndarray,
    active_driver: np.ndarray,
    restart_gap_seconds: float,
) -> None:
    positions, _ = _positions_and_gaps(elapsed, completed)
    for iteration in range(elapsed.shape[0]):
        order = np.argsort(positions[iteration])
        previous: int | None = None
        for driver in order:
            if not active_driver[driver]:
                continue
            if (
                previous is not None
                and completed[iteration, driver] == completed[iteration, previous]
            ):
                elapsed[iteration, driver] = min(
                    elapsed[iteration, driver],
                    elapsed[iteration, previous] + restart_gap_seconds,
                )
                elapsed[iteration, driver] = max(
                    elapsed[iteration, driver], elapsed[iteration, previous] + 0.001
                )
            previous = int(driver)

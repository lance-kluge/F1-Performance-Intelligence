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
    elapsed_history_seconds: np.ndarray
    gap_history_seconds: np.ndarray


def shared_randomness(
    prepared: PreparedRace,
    models: CalibratedModels,
    config: StrategySimulationConfig,
) -> SharedRandomness:
    random_generator = np.random.default_rng(config.random_seed)
    sample_shape = (prepared.race_laps + 1, config.iterations, len(prepared.initial_states))
    return SharedRandomness(
        coefficients=models.pace.sample_coefficients(random_generator, config.iterations),
        pace_uniforms=random_generator.random(sample_shape),
        traffic_uniforms=random_generator.random(sample_shape),
        pit_uniforms=random_generator.random(sample_shape),
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
    initial_car_states = prepared.initial_states
    drivers = tuple(state.driver for state in initial_car_states)
    driver_count = len(drivers)
    target_index = drivers.index(target_driver)
    iterations = config.iterations
    elapsed_seconds = np.repeat(
        np.asarray([state.elapsed_seconds for state in initial_car_states], dtype=float)[None, :],
        iterations,
        axis=0,
    )
    completed_laps = np.repeat(
        np.asarray([state.completed_laps for state in initial_car_states], dtype=int)[None, :],
        iterations,
        axis=0,
    )
    maximum_laps = np.asarray([state.maximum_laps for state in initial_car_states], dtype=int)
    current_compounds = np.asarray(
        [state.compound for state in initial_car_states], dtype=object
    )
    current_tire_ages_laps = np.asarray(
        [state.tire_age_laps for state in initial_car_states], dtype=float
    )
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

    simulated_laps = prepared.race_laps - simulation_start_lap(prepared)
    position_history = np.zeros((iterations, simulated_laps, driver_count), dtype=np.int16)
    elapsed_history_seconds = np.zeros(
        (iterations, simulated_laps, driver_count), dtype=float
    )
    gap_history_seconds = np.zeros(
        (iterations, simulated_laps, driver_count), dtype=float
    )

    history_index = 0
    for lap_number in range(simulation_start_lap(prepared) + 1, prepared.race_laps + 1):
        active_drivers = lap_number <= maximum_laps
        if not np.any(active_drivers):
            break
        current_tire_ages_laps[active_drivers & ~newly_fitted_tires] += 1.0
        newly_fitted_tires[:] = False
        lap_times_seconds = models.pace.predict(
            lap_number,
            drivers,
            current_compounds,
            current_tire_ages_laps,
            randomness.coefficients,
        )
        lap_times_seconds += models.pace.residual_draws(
            drivers, randomness.pace_uniforms[lap_number]
        )
        lap_times_seconds = np.clip(lap_times_seconds, 30.0, 600.0)

        neutralization_event = events_by_lap.get(lap_number)
        neutralization_parameters = None
        if neutralization_event is not None:
            neutralization_parameters = models.neutralization.parameters(
                neutralization_event.kind, neutralization_event.assumptions
            )
            lap_times_seconds *= neutralization_parameters.lap_time_multiplier
        else:
            gaps_to_car_ahead_seconds = _gaps_by_elapsed(
                elapsed_seconds, completed_laps, active_drivers
            )
            lap_times_seconds += models.traffic.penalties(
                gaps_to_car_ahead_seconds, randomness.traffic_uniforms[lap_number]
            )

        lap_times_seconds[:, ~active_drivers] = 0.0
        elapsed_seconds += lap_times_seconds
        completed_laps[:, active_drivers] += 1

        for driver_index, driver in enumerate(drivers):
            stop = stop_maps[driver].get(lap_number)
            if stop is None or not active_drivers[driver_index]:
                continue
            pit_losses = models.pit_loss.losses(
                GREEN, randomness.pit_uniforms[lap_number, :, driver_index]
            )
            if neutralization_parameters is not None:
                pit_losses *= neutralization_parameters.pit_loss_multiplier
            elapsed_seconds[:, driver_index] += pit_losses
            current_compounds[driver_index] = stop.compound
            current_tire_ages_laps[driver_index] = stop.starting_tire_age_laps
            newly_fitted_tires[driver_index] = True

        if (
            neutralization_event is not None
            and neutralization_event.kind is NeutralizationKind.SAFETY_CAR
            and neutralization_parameters is not None
        ):
            _compress_field(
                elapsed_seconds,
                completed_laps,
                active_drivers,
                neutralization_parameters.restart_gap_seconds,
            )

        positions, gaps_to_leader_seconds = _positions_and_gaps(
            elapsed_seconds, completed_laps
        )
        position_history[:, history_index, :] = positions
        elapsed_history_seconds[:, history_index, :] = elapsed_seconds
        gap_history_seconds[:, history_index, :] = gaps_to_leader_seconds
        history_index += 1

    if history_index < simulated_laps:
        position_history = position_history[:, :history_index, :]
        elapsed_history_seconds = elapsed_history_seconds[:, :history_index, :]
        gap_history_seconds = gap_history_seconds[:, :history_index, :]
    _apply_chequered_flag(
        elapsed_seconds,
        completed_laps,
        np.asarray([state.completed_laps for state in initial_car_states], dtype=int),
        maximum_laps,
        prepared.race_laps,
        elapsed_history_seconds,
    )
    final_positions, final_gaps = _positions_and_gaps(elapsed_seconds, completed_laps)
    return SimulationRun(
        final_positions=final_positions,
        final_completed_laps=completed_laps.copy(),
        final_elapsed_seconds=elapsed_seconds.copy(),
        final_gaps_seconds=final_gaps,
        target_positions=final_positions[:, target_index],
        target_completed_laps=completed_laps[:, target_index],
        target_elapsed_seconds=elapsed_seconds[:, target_index],
        target_gaps_seconds=final_gaps[:, target_index],
        position_history=position_history,
        elapsed_history_seconds=elapsed_history_seconds,
        gap_history_seconds=gap_history_seconds,
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
        lap_number = simulation_start_lap(prepared) + lap_offset + 1
        for driver_index, driver in enumerate(drivers):
            positions = run.position_history[:, lap_offset, driver_index]
            elapsed_seconds = run.elapsed_history_seconds[:, lap_offset, driver_index]
            gaps_to_leader_seconds = run.gap_history_seconds[:, lap_offset, driver_index]
            rows.append(
                {
                    "scenario": scenario,
                    "strategy": strategy,
                    "driver": driver,
                    "lap_number": lap_number,
                    "position_lower": float(np.quantile(positions, lower_quantile)),
                    "position_median": float(np.median(positions)),
                    "position_upper": float(np.quantile(positions, upper_quantile)),
                    "elapsed_lower_seconds": float(
                        np.quantile(elapsed_seconds, lower_quantile)
                    ),
                    "elapsed_median_seconds": float(np.median(elapsed_seconds)),
                    "elapsed_upper_seconds": float(
                        np.quantile(elapsed_seconds, upper_quantile)
                    ),
                    "gap_lower_seconds": _nan_quantile(
                        gaps_to_leader_seconds, lower_quantile
                    ),
                    "gap_median_seconds": _nan_quantile(gaps_to_leader_seconds, 0.5),
                    "gap_upper_seconds": _nan_quantile(
                        gaps_to_leader_seconds, upper_quantile
                    ),
                }
            )
    return pd.DataFrame(rows)


def simulation_start_lap(prepared: PreparedRace) -> int:
    return max(state.completed_laps for state in prepared.initial_states)


def _nan_quantile(values: np.ndarray, quantile: float) -> float:
    finite_values = values[np.isfinite(values)]
    return float(np.quantile(finite_values, quantile)) if len(finite_values) else float("nan")


def _apply_chequered_flag(
    elapsed_seconds: np.ndarray,
    completed_laps: np.ndarray,
    initial_completed_laps: np.ndarray,
    maximum_laps: np.ndarray,
    race_laps: int,
    elapsed_history: np.ndarray,
) -> None:
    classified = maximum_laps >= race_laps
    for iteration in range(elapsed_seconds.shape[0]):
        finish_candidates = np.flatnonzero(
            classified & (completed_laps[iteration] >= race_laps)
        )
        if not len(finish_candidates):
            continue
        winner = finish_candidates[
            np.argmin(elapsed_seconds[iteration, finish_candidates])
        ]
        winner_finish_seconds = elapsed_seconds[iteration, winner]
        for driver in np.flatnonzero(classified):
            crossings = elapsed_history[iteration, :, driver]
            after_chequer = np.flatnonzero(crossings >= winner_finish_seconds)
            if not len(after_chequer):
                continue
            finish_index = int(after_chequer[0])
            completed_laps[iteration, driver] = min(
                int(initial_completed_laps[driver]) + finish_index + 1,
                race_laps,
            )
            elapsed_seconds[iteration, driver] = crossings[finish_index]


def _gaps_by_elapsed(
    elapsed_seconds: np.ndarray,
    completed_laps: np.ndarray,
    active_drivers: np.ndarray,
) -> np.ndarray:
    positions, _ = _positions_and_gaps(elapsed_seconds, completed_laps)
    gaps_to_car_ahead_seconds = np.full_like(elapsed_seconds, np.inf, dtype=float)
    for iteration in range(elapsed_seconds.shape[0]):
        order = np.argsort(positions[iteration])
        for order_index in range(1, len(order)):
            driver = order[order_index]
            ahead = order[order_index - 1]
            if (
                not active_drivers[driver]
                or completed_laps[iteration, driver] != completed_laps[iteration, ahead]
            ):
                continue
            gaps_to_car_ahead_seconds[iteration, driver] = max(
                elapsed_seconds[iteration, driver] - elapsed_seconds[iteration, ahead],
                0.0,
            )
    return gaps_to_car_ahead_seconds


def _positions_and_gaps(
    elapsed_seconds: np.ndarray, completed_laps: np.ndarray
) -> tuple[np.ndarray, np.ndarray]:
    positions = np.empty_like(completed_laps, dtype=np.int16)
    gaps_to_leader_seconds = np.full_like(elapsed_seconds, np.nan, dtype=float)
    for iteration in range(elapsed_seconds.shape[0]):
        order = np.lexsort((elapsed_seconds[iteration], -completed_laps[iteration]))
        positions[iteration, order] = np.arange(1, len(order) + 1, dtype=np.int16)
        leader = order[0]
        same_lap = completed_laps[iteration] == completed_laps[iteration, leader]
        gaps_to_leader_seconds[iteration, same_lap] = np.maximum(
            elapsed_seconds[iteration, same_lap] - elapsed_seconds[iteration, leader],
            0.0,
        )
    return positions, gaps_to_leader_seconds


def _compress_field(
    elapsed_seconds: np.ndarray,
    completed_laps: np.ndarray,
    active_drivers: np.ndarray,
    restart_gap_seconds: float,
) -> None:
    positions, _ = _positions_and_gaps(elapsed_seconds, completed_laps)
    for iteration in range(elapsed_seconds.shape[0]):
        order = np.argsort(positions[iteration])
        previous: int | None = None
        for driver in order:
            if not active_drivers[driver]:
                continue
            if (
                previous is not None
                and completed_laps[iteration, driver]
                == completed_laps[iteration, previous]
            ):
                elapsed_seconds[iteration, driver] = min(
                    elapsed_seconds[iteration, driver],
                    elapsed_seconds[iteration, previous] + restart_gap_seconds,
                )
                elapsed_seconds[iteration, driver] = max(
                    elapsed_seconds[iteration, driver],
                    elapsed_seconds[iteration, previous] + 0.001,
                )
            previous = int(driver)

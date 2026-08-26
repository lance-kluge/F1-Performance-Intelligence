"""Orchestration for presentation-neutral strategy counterfactuals."""

from __future__ import annotations

import numpy as np
import pandas as pd

from f1pi.analysis.models import (
    StrategyOutcomeSummary,
    StrategySimulationAnalysis,
    StrategySimulationConfig,
    StrategySimulationRequest,
)
from f1pi.analysis.strategy_simulator.analysis_session import StrategyAnalysisSession
from f1pi.analysis.strategy_simulator.calibration import calibrate_models
from f1pi.analysis.strategy_simulator.preparation import prepare_race, scenario_events
from f1pi.analysis.strategy_simulator.simulation import (
    SimulationRun,
    shared_randomness,
    simulate_strategy,
    trace_distribution_frame,
)
from f1pi.domain.exceptions import DatasetNotAvailableError, InsufficientStrategyDataError


class StrategySimulationEngine:
    """Calibrate one completed race and evaluate explicit future strategies."""

    def simulate(
        self,
        session: StrategyAnalysisSession,
        request: StrategySimulationRequest,
        config: StrategySimulationConfig | None = None,
    ) -> StrategySimulationAnalysis:
        config = config or StrategySimulationConfig()
        try:
            prepared = prepare_race(session, request, config)
        except DatasetNotAvailableError as error:
            raise InsufficientStrategyDataError(
                "laps, results, weather, and track status are required"
            ) from error
        models = calibrate_models(prepared, request, config)
        randomness = shared_randomness(prepared, models, config)
        outcome_frames: list[pd.DataFrame] = []
        trace_frames: list[pd.DataFrame] = []

        for scenario in request.scenarios:
            events = scenario_events(scenario, prepared, request.decision_lap)
            # Resolve assumptions before expensive simulation so malformed scenario sets fail early.
            for event in events:
                models.neutralization.parameters(event.kind, event.assumptions)
            baseline_run = simulate_strategy(
                prepared,
                models,
                config,
                request.driver,
                prepared.baseline,
                events,
                randomness,
            )
            outcome_frames.append(
                _outcome_frame(scenario.name, "baseline", baseline_run, baseline_run)
            )
            trace_frames.append(
                trace_distribution_frame(baseline_run, prepared, scenario.name, "baseline", config)
            )
            for strategy in request.strategies:
                run = simulate_strategy(
                    prepared,
                    models,
                    config,
                    request.driver,
                    strategy,
                    events,
                    randomness,
                )
                outcome_frames.append(
                    _outcome_frame(scenario.name, strategy.name, run, baseline_run)
                )
                trace_frames.append(
                    trace_distribution_frame(run, prepared, scenario.name, strategy.name, config)
                )

        outcomes = pd.concat(outcome_frames, ignore_index=True)
        traces = pd.concat(trace_frames, ignore_index=True)
        return StrategySimulationAnalysis(
            metadata=prepared.metadata,
            driver=request.driver,
            decision_lap=request.decision_lap,
            baseline=prepared.baseline,
            summaries=_summaries(outcomes),
            diagnostics=models.diagnostics,
            outcome_samples=outcomes,
            lap_distributions=traces,
            warnings=models.warnings,
        )


def _outcome_frame(
    scenario: str,
    strategy: str,
    run: SimulationRun,
    baseline: SimulationRun,
) -> pd.DataFrame:
    improved = (run.target_positions < baseline.target_positions) | (
        (run.target_positions == baseline.target_positions)
        & (run.target_elapsed_seconds < baseline.target_elapsed_seconds)
    )
    return pd.DataFrame(
        {
            "iteration": np.arange(len(run.target_positions), dtype=int),
            "scenario": scenario,
            "strategy": strategy,
            "finish_position": run.target_positions.astype(int),
            "completed_laps": run.target_completed_laps.astype(int),
            "elapsed_seconds": run.target_elapsed_seconds,
            "gap_to_winner_seconds": run.target_gaps_seconds,
            "delta_to_baseline_seconds": (
                run.target_elapsed_seconds - baseline.target_elapsed_seconds
            ),
            "better_than_baseline": improved,
        }
    )


def _summaries(outcomes: pd.DataFrame) -> tuple[StrategyOutcomeSummary, ...]:
    summaries: list[StrategyOutcomeSummary] = []
    for (scenario, strategy), rows in outcomes.groupby(["scenario", "strategy"], sort=False):
        positions = rows["finish_position"].to_numpy(dtype=float)
        summaries.append(
            StrategyOutcomeSummary(
                scenario=str(scenario),
                strategy=str(strategy),
                expected_finish_position=float(np.mean(positions)),
                median_finish_position=float(np.median(positions)),
                win_probability=float(np.mean(positions <= 1)),
                podium_probability=float(np.mean(positions <= 3)),
                top_ten_probability=float(np.mean(positions <= 10)),
                expected_gap_to_winner_seconds=float(rows["gap_to_winner_seconds"].mean()),
                expected_delta_to_baseline_seconds=float(rows["delta_to_baseline_seconds"].mean()),
                probability_better_than_baseline=float(rows["better_than_baseline"].mean()),
            )
        )
    return tuple(summaries)

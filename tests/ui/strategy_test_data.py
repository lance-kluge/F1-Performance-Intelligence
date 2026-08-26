"""Shared deterministic strategy UI records."""

from __future__ import annotations

from datetime import UTC, datetime

import pandas as pd

from f1pi.analysis.models import (
    PlannedPitStop,
    StrategyCalibrationDiagnostics,
    StrategyOutcomeSummary,
    StrategyPlan,
    StrategySimulationAnalysis,
)
from f1pi.domain.models import SessionKey, SessionMetadata, SessionType
from f1pi.ui.models import (
    DriverOption,
    StrategySimulationRun,
    StrategySimulationSetup,
)


def strategy_setup() -> StrategySimulationSetup:
    metadata = SessionMetadata(
        session_id="2026-01-australian-r",
        year=2026,
        round_number=1,
        event_name="Australian Grand Prix",
        country="Australia",
        location="Melbourne",
        session_type=SessionType.RACE,
        session_name="Race",
        session_date_utc=datetime(2026, 3, 8, 4, tzinfo=UTC),
        fastf1_version="3.8.3",
    )
    return StrategySimulationSetup(
        key=SessionKey(2026, 1, "R"),
        metadata=metadata,
        drivers=(
            DriverOption("NOR", "Lando Norris", "McLaren", tuple(range(1, 20))),
            DriverOption("VER", "Max Verstappen", "Red Bull Racing", tuple(range(1, 20))),
        ),
        race_laps=20,
        compounds=("HARD", "MEDIUM", "SOFT"),
        snapshot_reused=True,
    )


def strategy_run() -> StrategySimulationRun:
    setup = strategy_setup()
    summaries = []
    outcome_rows = []
    trace_rows = []
    values = {
        "baseline": (4.2, 0.0, 0.0),
        "Early stop": (3.7, -1.2454, 0.68),
        "Extend stint": (4.5, 0.5236, 0.41),
    }
    for scenario in ("actual", "no_safety_car"):
        for strategy, (position, delta, better) in values.items():
            summaries.append(
                StrategyOutcomeSummary(
                    scenario=scenario,
                    strategy=strategy,
                    expected_finish_position=position,
                    median_finish_position=round(position),
                    win_probability=0.08 if strategy == "Early stop" else 0.03,
                    podium_probability=0.42 if strategy == "Early stop" else 0.28,
                    top_ten_probability=0.96,
                    expected_gap_to_winner_seconds=12.3456,
                    expected_delta_to_baseline_seconds=delta,
                    probability_better_than_baseline=better,
                )
            )
            for iteration in range(10):
                outcome_rows.append(
                    {
                        "iteration": iteration,
                        "scenario": scenario,
                        "strategy": strategy,
                        "finish_position": max(1, round(position) + iteration % 2),
                        "completed_laps": 20,
                        "elapsed_seconds": 5400.0 + delta,
                        "gap_to_winner_seconds": 12.3456,
                        "delta_to_baseline_seconds": delta,
                        "better_than_baseline": iteration < round(better * 10),
                    }
                )
            for lap in range(8, 21):
                trace_rows.append(
                    {
                        "scenario": scenario,
                        "strategy": strategy,
                        "driver": "NOR",
                        "lap_number": lap,
                        "position_lower": max(1.0, position - 1.0),
                        "position_median": position,
                        "position_upper": position + 1.0,
                        "elapsed_lower_seconds": lap * 90.0 - 0.5,
                        "elapsed_median_seconds": lap * 90.0,
                        "elapsed_upper_seconds": lap * 90.0 + 0.5,
                        "gap_lower_seconds": 10.0,
                        "gap_median_seconds": 12.0,
                        "gap_upper_seconds": 14.0,
                    }
                )
    analysis = StrategySimulationAnalysis(
        metadata=setup.metadata,
        driver="NOR",
        decision_lap=7,
        baseline=StrategyPlan("baseline", (PlannedPitStop(12, "HARD"),)),
        summaries=tuple(summaries),
        diagnostics=StrategyCalibrationDiagnostics(
            pace_observation_count=184,
            target_pace_observation_count=16,
            pit_stop_sample_count=18,
            traffic_sample_count=94,
            pace_mae_seconds=0.4564,
            pace_rmse_seconds=0.6126,
            supported_compounds=("HARD", "MEDIUM", "SOFT"),
        ),
        outcome_samples=pd.DataFrame(outcome_rows),
        lap_distributions=pd.DataFrame(trace_rows),
        warnings=("sparse_green_pit_loss_calibration",),
    )
    return StrategySimulationRun(analysis, snapshot_reused=True)

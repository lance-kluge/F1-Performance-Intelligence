from __future__ import annotations

from datetime import UTC, datetime

import numpy as np
import pandas as pd
import pytest

from f1pi.analysis import (
    NeutralizationAssumptions,
    NeutralizationEvent,
    NeutralizationKind,
    NeutralizationScenario,
    PlannedPitStop,
    StrategyPlan,
    StrategySimulationConfig,
    StrategySimulationEngine,
    StrategySimulationRequest,
)
from f1pi.analysis.strategy_simulator.calibration import (
    EmpiricalTrafficModel,
    RegressionPaceModel,
)
from f1pi.analysis.strategy_simulator.preparation import prepare_race, scenario_events
from f1pi.analysis.strategy_simulator.simulation import _compress_field
from f1pi.domain.exceptions import (
    InsufficientStrategyDataError,
    InvalidStrategyError,
    UnsupportedStrategySessionError,
)
from f1pi.domain.models import SessionMetadata, SessionType


class StubStrategySession:
    def __init__(
        self,
        *,
        session_type: SessionType = SessionType.RACE,
        red_flag: bool = False,
    ) -> None:
        self.metadata = SessionMetadata(
            session_id="2026-01-test-r",
            year=2026,
            round_number=1,
            event_name="Test Grand Prix",
            country="Test",
            location="Test Circuit",
            session_type=session_type,
            session_name=session_type.name,
            session_date_utc=datetime(2026, 3, 1, tzinfo=UTC),
            fastf1_version="3.8.3",
        )
        self._laps = _sample_laps()
        final_time = int(self._laps["lap_start_time_ns"].max() + 200e9)
        self._weather = pd.DataFrame(
            {
                "time_ns": pd.array([0, final_time], dtype="Int64"),
                "air_temp": [24.0, 24.2],
                "track_temp": [32.0, 31.5],
                "humidity": [45.0, 46.0],
                "pressure": [1008.0, 1008.1],
                "rainfall": pd.array([False, False], dtype="boolean"),
                "wind_direction": pd.array([180, 185], dtype="Int64"),
                "wind_speed": [2.0, 2.2],
            }
        )
        self._track_status = pd.DataFrame(
            {
                "time_ns": pd.array([0], dtype="Int64"),
                "status": pd.array(["5" if red_flag else "1"], dtype="string"),
                "message": pd.array(["Red" if red_flag else "AllClear"], dtype="string"),
            }
        )
        self._results = pd.DataFrame(
            {
                "abbreviation": ["AAA", "BBB", "CCC", "DDD"],
                "position": pd.array([1, 2, 3, 4], dtype="Int64"),
                "status": ["Finished"] * 4,
            }
        )

    def laps(self) -> pd.DataFrame:
        return self._laps

    def results(self) -> pd.DataFrame:
        return self._results

    def weather(self) -> pd.DataFrame:
        return self._weather

    def track_status(self) -> pd.DataFrame:
        return self._track_status


def _sample_laps() -> pd.DataFrame:
    records: list[dict[str, object]] = []
    for driver_index, driver in enumerate(("AAA", "BBB", "CCC", "DDD")):
        start = 0.0
        switch_lap = 10 + driver_index % 2
        for lap_number in range(1, 21):
            first_stint = lap_number <= switch_lap
            compound = "SOFT" if first_stint else "HARD"
            tire_age = lap_number if first_stint else lap_number - switch_lap
            lap_time = (
                90.0
                + driver_index * 0.4
                + (0.14 if compound == "SOFT" else 0.05) * tire_age
                - 0.04 * lap_number
                + ((lap_number + driver_index) % 3 - 1) * 0.02
            )
            pit_in = lap_number == switch_lap
            pit_out = lap_number == switch_lap + 1
            if pit_in or pit_out:
                lap_time += 10.0
            records.append(
                {
                    "driver": driver,
                    "driver_number": str(driver_index + 1),
                    "lap_number": lap_number,
                    "lap_time_ns": int(lap_time * 1e9),
                    "lap_start_time_ns": int(start * 1e9),
                    "pit_out_time_ns": int((start + 5) * 1e9) if pit_out else pd.NA,
                    "pit_in_time_ns": int((start + lap_time - 5) * 1e9) if pit_in else pd.NA,
                    "sector1_time_ns": pd.NA,
                    "sector2_time_ns": pd.NA,
                    "sector3_time_ns": pd.NA,
                    "stint": 1 if first_stint else 2,
                    "compound": compound,
                    "tyre_life": float(tire_age),
                    "fresh_tyre": True,
                    "is_accurate": True,
                    "deleted": False,
                    "track_status": "1",
                }
            )
            start += lap_time
    return pd.DataFrame(records)


def _request(*scenarios: NeutralizationScenario) -> StrategySimulationRequest:
    return StrategySimulationRequest(
        " aaa ",
        5,
        (
            StrategyPlan("early", (PlannedPitStop(8, " hard "),)),
            StrategyPlan("late", (PlannedPitStop(13, "HARD", 2.0),)),
        ),
        scenarios or (NeutralizationScenario.actual(),),
    )


def test_simulates_full_field_with_paired_reproducible_outcomes() -> None:
    config = StrategySimulationConfig(iterations=30, random_seed=17)

    first = StrategySimulationEngine().simulate(StubStrategySession(), _request(), config)
    second = StrategySimulationEngine().simulate(StubStrategySession(), _request(), config)

    assert first.driver == "AAA"
    assert first.baseline.stops[0].after_lap == 10
    assert len(first.summaries) == 3
    assert set(first.outcome_samples["strategy"]) == {"baseline", "early", "late"}
    assert len(first.outcome_samples) == 90
    assert set(first.lap_distributions["driver"]) == {"AAA", "BBB", "CCC", "DDD"}
    pd.testing.assert_frame_equal(first.outcome_samples, second.outcome_samples)
    assert first.diagnostics.pace_observation_count > 20
    assert first.diagnostics.pit_stop_sample_count == 4
    assert set(first.diagnostics.supported_compounds) == {"HARD", "SOFT"}
    assert (
        first.outcome_samples.groupby("strategy")["delta_to_baseline_seconds"].mean()["early"] != 0
    )
    assert (
        first.outcome_samples.loc[
            first.outcome_samples["strategy"].eq("baseline"), "delta_to_baseline_seconds"
        ]
        .eq(0)
        .all()
    )
    assert all(0 <= summary.podium_probability <= 1 for summary in first.summaries)


def test_no_safety_car_and_custom_vsc_scenarios_share_one_result() -> None:
    custom = NeutralizationScenario.custom(
        "late_vsc",
        (
            NeutralizationEvent(
                NeutralizationKind.VIRTUAL_SAFETY_CAR,
                12,
                14,
                NeutralizationAssumptions(1.3, 0.7),
            ),
        ),
    )
    analysis = StrategySimulationEngine().simulate(
        StubStrategySession(),
        _request(NeutralizationScenario.no_safety_car(), custom),
        StrategySimulationConfig(iterations=8),
    )

    assert set(analysis.outcome_samples["scenario"]) == {"no_safety_car", "late_vsc"}
    assert len(analysis.summaries) == 6
    vsc_elapsed = analysis.outcome_samples.loc[
        analysis.outcome_samples["scenario"].eq("late_vsc"), "elapsed_seconds"
    ].mean()
    green_elapsed = analysis.outcome_samples.loc[
        analysis.outcome_samples["scenario"].eq("no_safety_car"), "elapsed_seconds"
    ].mean()
    assert vsc_elapsed > green_elapsed


def test_custom_safety_car_requires_assumptions_without_session_support() -> None:
    scenario = NeutralizationScenario.custom(
        "unsupported_sc",
        (NeutralizationEvent(NeutralizationKind.SAFETY_CAR, 12, 13),),
    )

    with pytest.raises(InsufficientStrategyDataError, match="custom assumptions"):
        StrategySimulationEngine().simulate(
            StubStrategySession(),
            _request(scenario),
            StrategySimulationConfig(iterations=2),
        )


def test_actual_scenario_is_derived_from_track_status_timeline() -> None:
    session = StubStrategySession()
    session._track_status = pd.DataFrame(
        {
            "time_ns": pd.array([0, int(1_000e9), int(1_200e9)], dtype="Int64"),
            "status": pd.array(["1", "6", "1"], dtype="string"),
            "message": pd.array(["AllClear", "VSCDeployed", "AllClear"], dtype="string"),
        }
    )

    request = _request()
    config = StrategySimulationConfig(iterations=3)
    prepared = prepare_race(session, request, config)
    actual_events = scenario_events(request.scenarios[0], prepared, request.decision_lap)
    analysis = StrategySimulationEngine().simulate(session, request, config)

    assert set(analysis.outcome_samples["scenario"]) == {"actual"}
    assert any(event.kind is NeutralizationKind.VIRTUAL_SAFETY_CAR for event in actual_events)


def test_no_stop_sprint_can_run_without_pit_loss_samples() -> None:
    session = StubStrategySession(session_type=SessionType.SPRINT)
    session._laps[["pit_in_time_ns", "pit_out_time_ns"]] = pd.NA
    request = StrategySimulationRequest("AAA", 5, (StrategyPlan("stay_out"),))

    analysis = StrategySimulationEngine().simulate(
        session, request, StrategySimulationConfig(iterations=2)
    )

    assert analysis.diagnostics.pit_stop_sample_count == 0
    assert "pit_loss_unavailable:no_stops" in analysis.warnings


def test_fastf1_lap_down_status_is_a_classified_finisher() -> None:
    session = StubStrategySession()
    session._results.loc[session._results["abbreviation"].eq("AAA"), "status"] = "+ 1 Lap"

    analysis = StrategySimulationEngine().simulate(
        session, _request(), StrategySimulationConfig(iterations=2)
    )

    assert analysis.driver == "AAA"


def test_first_post_stop_lap_uses_declared_tire_age(monkeypatch: pytest.MonkeyPatch) -> None:
    observed_ages: list[float] = []
    original_predict = RegressionPaceModel.predict

    def capture_predict(
        self: RegressionPaceModel,
        lap_number: int,
        drivers: tuple[str, ...],
        compounds: np.ndarray,
        tire_ages: np.ndarray,
        coefficients: np.ndarray,
    ) -> np.ndarray:
        target_index = drivers.index("AAA")
        if lap_number == 9 and compounds[target_index] == "HARD":
            observed_ages.append(float(tire_ages[target_index]))
        return original_predict(
            self, lap_number, drivers, compounds, tire_ages, coefficients
        )

    monkeypatch.setattr(RegressionPaceModel, "predict", capture_predict)
    StrategySimulationEngine().simulate(
        StubStrategySession(),
        StrategySimulationRequest(
            "AAA",
            5,
            (StrategyPlan("early", (PlannedPitStop(8, "HARD", 1.0),)),),
        ),
        StrategySimulationConfig(iterations=1),
    )

    assert observed_ages == [1.0]


def test_rejects_red_flags_non_races_bad_targets_and_invalid_windows() -> None:
    with pytest.raises(UnsupportedStrategySessionError, match="red-flag"):
        StrategySimulationEngine().simulate(
            StubStrategySession(red_flag=True), _request(), StrategySimulationConfig(iterations=1)
        )
    with pytest.raises(UnsupportedStrategySessionError, match="Race and Sprint"):
        StrategySimulationEngine().simulate(
            StubStrategySession(session_type=SessionType.QUALIFYING),
            _request(),
            StrategySimulationConfig(iterations=1),
        )
    missing = _request()
    missing = StrategySimulationRequest("ZZZ", missing.decision_lap, missing.strategies)
    with pytest.raises(InvalidStrategyError, match="not present"):
        StrategySimulationEngine().simulate(
            StubStrategySession(), missing, StrategySimulationConfig(iterations=1)
        )
    bad_window = StrategySimulationRequest(
        "AAA", 5, (StrategyPlan("bad", (PlannedPitStop(5, "HARD"),)),)
    )
    with pytest.raises(InvalidStrategyError, match="simulatable window"):
        StrategySimulationEngine().simulate(
            StubStrategySession(), bad_window, StrategySimulationConfig(iterations=1)
        )


def test_traffic_penalties_are_bounded_and_safety_car_compresses_field() -> None:
    model = EmpiricalTrafficModel(
        2.0,
        np.linspace(0, 2, 5),
        np.array([1.0, 0.8, 0.5, 0.2]),
        np.array([-0.1, 0.1]),
        4,
    )
    penalties = model.penalties(
        np.array([[0.2, 1.2, 3.0, np.inf]]), np.array([[0.0, 0.9, 0.5, 0.5]])
    )
    assert penalties[0, 0] == pytest.approx(0.9)
    assert penalties[0, 1] == pytest.approx(0.6)
    assert penalties[0, 2:].tolist() == [0.0, 0.0]

    elapsed = np.array([[100.0, 108.0, 120.0]])
    completed = np.array([[10, 10, 10]])
    _compress_field(elapsed, completed, np.array([True, True, True]), 1.0)
    assert elapsed.tolist() == [[100.0, 101.0, 102.0]]


@pytest.mark.parametrize(
    "factory",
    [
        lambda: StrategySimulationConfig(iterations=0),
        lambda: StrategySimulationConfig(confidence_level=1),
        lambda: StrategySimulationConfig(traffic_gap_seconds=0),
        lambda: PlannedPitStop(0, "SOFT"),
        lambda: PlannedPitStop(1, ""),
        lambda: StrategyPlan("x", (PlannedPitStop(3, "S"), PlannedPitStop(2, "H"))),
        lambda: NeutralizationAssumptions(0.9, 0.5),
        lambda: NeutralizationAssumptions(1.2, 0),
        lambda: NeutralizationAssumptions(float("nan"), 0.5),
        lambda: NeutralizationAssumptions(float("inf"), 0.5),
        lambda: NeutralizationAssumptions(1.2, float("nan")),
        lambda: NeutralizationAssumptions(1.2, 0.5, float("inf")),
        lambda: NeutralizationEvent(NeutralizationKind.SAFETY_CAR, 3, 2),
    ],
)
def test_contracts_validate_invalid_values(factory: object) -> None:
    with pytest.raises(ValueError):
        factory()  # type: ignore[operator]

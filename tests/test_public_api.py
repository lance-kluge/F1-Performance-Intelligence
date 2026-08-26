from f1pi import (
    CompoundDegradationEstimate,
    DegradationMode,
    DriverTireDegradationAnalysis,
    DriverTireModelConfig,
    NeutralizationKind,
    NeutralizationScenario,
    PlannedPitStop,
    StrategyPlan,
    StrategySimulationConfig,
    StrategySimulationRequest,
    TireDegradationAnalysis,
    TireModelConfig,
    TireModelMetrics,
    TireModelValidation,
    TireStintSummary,
)


def test_tire_model_contracts_are_public_lazy_exports() -> None:
    assert DegradationMode.ADJUSTED.value == "adjusted"
    assert TireModelConfig().mode is DegradationMode.ADJUSTED
    assert DriverTireModelConfig().minimum_compound_stints == 1
    assert all(
        contract is not None
        for contract in (
            CompoundDegradationEstimate,
            DriverTireDegradationAnalysis,
            TireDegradationAnalysis,
            TireModelMetrics,
            TireModelValidation,
            TireStintSummary,
        )
    )


def test_strategy_simulator_contracts_are_public_lazy_exports() -> None:
    stop = PlannedPitStop(20, " hard ")
    strategy = StrategyPlan("one_stop", (stop,))
    request = StrategySimulationRequest(" lec ", 10, (strategy,))

    assert stop.compound == "HARD"
    assert request.driver == "LEC"
    assert request.scenarios == (NeutralizationScenario.actual(),)
    assert StrategySimulationConfig().iterations == 2000
    assert NeutralizationKind.SAFETY_CAR.value == "safety_car"

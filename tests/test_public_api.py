from f1pi import (
    CompoundDegradationEstimate,
    DegradationMode,
    TireDegradationAnalysis,
    TireModelConfig,
    TireModelMetrics,
    TireModelValidation,
    TireStintSummary,
)


def test_tire_model_contracts_are_public_lazy_exports() -> None:
    assert DegradationMode.ADJUSTED.value == "adjusted"
    assert TireModelConfig().mode is DegradationMode.ADJUSTED
    assert all(
        contract is not None
        for contract in (
            CompoundDegradationEstimate,
            TireDegradationAnalysis,
            TireModelMetrics,
            TireModelValidation,
            TireStintSummary,
        )
    )

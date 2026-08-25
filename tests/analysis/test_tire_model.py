from __future__ import annotations

from datetime import UTC, datetime

import pandas as pd
import pytest

from f1pi.analysis import (
    DegradationMode,
    DriverTireModelConfig,
    TireDegradationEngine,
    TireModelConfig,
)
from f1pi.analysis.tire_model.features import prepare_observations
from f1pi.analysis.tire_model.regression import StatsmodelsTireRegressor, slope_column
from f1pi.analysis.tire_model.stints import extract_stints
from f1pi.domain.exceptions import (
    DatasetNotAvailableError,
    DriverNotFoundError,
    InsufficientTireDataError,
    UnsupportedTireSessionError,
)
from f1pi.domain.models import SessionMetadata, SessionType


class StubTireAnalysisSession:
    def __init__(
        self,
        *,
        session_type: SessionType = SessionType.RACE,
        weather_available: bool = True,
        track_status_available: bool = True,
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
        final_time = int(self._laps["lap_start_time_ns"].max() + 100_000_000_000)
        self._weather = pd.DataFrame(
            {
                "time_ns": pd.array([0, final_time], dtype="Int64"),
                "air_temp": [24.0, 24.0],
                "track_temp": [32.0, 32.0],
                "humidity": [45.0, 45.0],
                "pressure": [1008.0, 1008.0],
                "rainfall": pd.array([False, False], dtype="boolean"),
                "wind_direction": pd.array([180, 180], dtype="Int64"),
                "wind_speed": [2.0, 2.0],
            }
        )
        self._track_status = pd.DataFrame(
            {
                "time_ns": pd.array([0], dtype="Int64"),
                "status": pd.array(["1"], dtype="string"),
                "message": pd.array(["AllClear"], dtype="string"),
            }
        )
        self._weather_available = weather_available
        self._track_status_available = track_status_available

    def laps(self) -> pd.DataFrame:
        return self._laps

    def weather(self) -> pd.DataFrame:
        if not self._weather_available:
            raise DatasetNotAvailableError("weather unavailable")
        return self._weather

    def track_status(self) -> pd.DataFrame:
        if not self._track_status_available:
            raise DatasetNotAvailableError("track status unavailable")
        return self._track_status


def _sample_laps() -> pd.DataFrame:
    lap_records: list[dict[str, object]] = []
    driver_scenarios = (
        ("AAA", 0.0, 5),
        ("BBB", 0.35, 6),
        ("CCC", -0.2, 7),
        ("DDD", 0.15, 8),
    )
    for driver_index, (driver, driver_effect, switch_lap) in enumerate(driver_scenarios):
        start_seconds = 0.0
        for lap_number in range(1, 13):
            is_first_stint = lap_number <= switch_lap
            compound = "SOFT" if is_first_stint else "MEDIUM"
            stint_number = 1 if is_first_stint else 2
            tire_age_laps = lap_number if is_first_stint else lap_number - switch_lap
            degradation_rate = 0.12 if compound == "SOFT" else 0.05
            compound_effect = 0.0 if compound == "SOFT" else 0.6
            lap_time_noise = ((driver_index + tire_age_laps) % 3 - 1) * 0.012
            lap_time_seconds = (
                92.0
                + driver_effect
                + compound_effect
                + degradation_rate * tire_age_laps
                - 0.15 * lap_number
                + lap_time_noise
            )
            lap_records.append(
                {
                    "driver": driver,
                    "driver_number": str(driver_index + 1),
                    "lap_number": lap_number,
                    "lap_time_ns": int(lap_time_seconds * 1e9),
                    "lap_start_time_ns": int(start_seconds * 1e9),
                    "pit_out_time_ns": pd.NA,
                    "pit_in_time_ns": pd.NA,
                    "sector1_time_ns": pd.NA,
                    "sector2_time_ns": pd.NA,
                    "sector3_time_ns": pd.NA,
                    "stint": stint_number,
                    "compound": compound,
                    "tyre_life": float(tire_age_laps),
                    "fresh_tyre": True,
                    "is_accurate": True,
                    "deleted": False,
                }
            )
            start_seconds += lap_time_seconds
    return pd.DataFrame(lap_records)


def test_extracts_stints_on_upstream_change_gap_compound_and_tire_reset() -> None:
    laps = pd.DataFrame(
        {
            "driver": ["AAA"] * 5,
            "lap_number": [1, 2, 4, 5, 6],
            "stint": [1, 1, 1, 1, 1],
            "compound": ["SOFT", "SOFT", "SOFT", "MEDIUM", "MEDIUM"],
            "tyre_life": [4.0, 5.0, 6.0, 2.0, 1.0],
        }
    )

    extracted_laps = extract_stints(laps)

    assert extracted_laps["stint_id"].tolist() == [
        "AAA:01",
        "AAA:01",
        "AAA:02",
        "AAA:03",
        "AAA:04",
    ]
    assert extracted_laps["stint_lap_index"].tolist() == [1, 2, 1, 1, 1]
    assert extracted_laps["tyre_life"].tolist()[:2] == [4.0, 5.0]


def test_feature_preparation_applies_exclusion_precedence() -> None:
    session = StubTireAnalysisSession()
    laps = session.laps().loc[session.laps()["driver"].eq("AAA")].copy()
    laps.loc[laps.index[0], ["is_accurate", "deleted"]] = [False, True]
    laps.loc[laps.index[1], "deleted"] = True
    laps.loc[laps.index[2], "pit_in_time_ns"] = laps.loc[laps.index[2], "lap_start_time_ns"]

    observations = prepare_observations(
        laps,
        session.weather(),
        session.track_status(),
        TireModelConfig(quick_lap_ratio=2.0),
    )

    assert observations["exclusion_reason"].iloc[:3].tolist() == [
        "inaccurate",
        "deleted",
        "pit_lap",
    ]
    assert observations["track_temp"].dropna().eq(32.0).all()
    assert observations["race_progress"].between(0, 1).all()


def test_raw_and_adjusted_models_return_compound_rates_and_bands() -> None:
    engine = TireDegradationEngine()
    raw = engine.analyze(
        StubTireAnalysisSession(),
        TireModelConfig(mode=DegradationMode.RAW, quick_lap_ratio=2.0),
    )
    adjusted = engine.analyze(
        StubTireAnalysisSession(),
        TireModelConfig(mode=DegradationMode.ADJUSTED, quick_lap_ratio=2.0),
    )

    raw_rates = {estimate.compound: estimate.seconds_per_lap for estimate in raw.estimates}
    adjusted_rates = {
        estimate.compound: estimate.seconds_per_lap for estimate in adjusted.estimates
    }
    assert adjusted_rates["SOFT"] == pytest.approx(0.12, abs=0.02)
    assert adjusted_rates["MEDIUM"] == pytest.approx(0.05, abs=0.02)
    assert raw_rates["SOFT"] < adjusted_rates["SOFT"] - 0.05
    assert raw_rates["MEDIUM"] < adjusted_rates["MEDIUM"] - 0.05
    assert adjusted.validation.fold_count == 5
    assert {metric.scope for metric in adjusted.validation.per_compound} == {"MEDIUM", "SOFT"}
    assert len(adjusted.stints) == 8
    assert len(adjusted.curves) == 200
    assert adjusted.observations["eligible"].all()

    for estimate in adjusted.estimates:
        assert estimate.confidence_lower_seconds_per_lap <= estimate.seconds_per_lap
        assert estimate.seconds_per_lap <= estimate.confidence_upper_seconds_per_lap
        curve = adjusted.curves.loc[adjusted.curves["compound"].eq(estimate.compound)]
        assert curve["tire_age_laps"].min() == pytest.approx(estimate.minimum_tire_age)
        assert curve["tire_age_laps"].max() == pytest.approx(estimate.maximum_tire_age)
        assert (curve["mean_confidence_lower_seconds"] <= curve["predicted_lap_time_seconds"]).all()
        assert (curve["predicted_lap_time_seconds"] <= curve["mean_confidence_upper_seconds"]).all()
        assert (curve["prediction_lower_seconds"] <= curve["mean_confidence_lower_seconds"]).all()
        assert (curve["mean_confidence_upper_seconds"] <= curve["prediction_upper_seconds"]).all()


def test_driver_model_returns_only_selected_driver_with_session_race_progress() -> None:
    session = StubTireAnalysisSession()
    session._laps = session._laps.loc[
        session._laps["driver"].ne("AAA") | session._laps["lap_number"].le(8)
    ].copy()

    analysis = TireDegradationEngine().analyze_driver(
        session,
        " aaa ",
        DriverTireModelConfig(
            minimum_compound_laps=3,
            quick_lap_ratio=2.0,
        ),
    )

    assert analysis.driver == "AAA"
    assert analysis.mode is DegradationMode.ADJUSTED
    assert set(analysis.observations["driver"]) == {"AAA"}
    assert {stint.driver for stint in analysis.stints} == {"AAA"}
    assert {estimate.compound for estimate in analysis.estimates} == {"MEDIUM", "SOFT"}
    assert analysis.observations["race_progress"].max() == pytest.approx(7 / 11)
    assert analysis.validation is None
    assert "validation_unavailable:insufficient_independent_stints" in analysis.warnings
    assert "single_stint_estimate:MEDIUM" in analysis.warnings
    assert "single_stint_estimate:SOFT" in analysis.warnings
    assert "dropped_collinear_feature:condition::race_progress" in analysis.warnings


def test_driver_model_uses_hc3_when_only_one_stint_is_available() -> None:
    session = StubTireAnalysisSession()
    session._laps = session._laps.loc[
        session._laps["driver"].ne("AAA") | session._laps["lap_number"].le(5)
    ].copy()

    analysis = TireDegradationEngine().analyze_driver(
        session,
        "AAA",
        DriverTireModelConfig(mode=DegradationMode.RAW, quick_lap_ratio=2.0),
    )

    assert {estimate.compound for estimate in analysis.estimates} == {"SOFT"}
    assert analysis.estimates[0].stint_count == 1
    assert analysis.validation is None
    assert "cluster_covariance_unavailable" in analysis.warnings
    assert "single_stint_estimate:SOFT" in analysis.warnings


def test_driver_model_validates_repeated_same_compound_stints() -> None:
    session = StubTireAnalysisSession()
    selected_driver = session._laps["driver"].eq("AAA")
    session._laps.loc[selected_driver, "compound"] = "SOFT"

    analysis = TireDegradationEngine().analyze_driver(
        session,
        "AAA",
        DriverTireModelConfig(mode=DegradationMode.RAW, quick_lap_ratio=2.0),
    )

    assert len(analysis.estimates) == 1
    assert analysis.estimates[0].stint_count == 2
    assert analysis.validation is not None
    assert analysis.validation.fold_count == 2
    assert "single_stint_estimate:SOFT" not in analysis.warnings


def test_driver_model_rejects_unknown_driver() -> None:
    with pytest.raises(DriverNotFoundError, match="NOT-A-DRIVER"):
        TireDegradationEngine().analyze_driver(
            StubTireAnalysisSession(), "NOT-A-DRIVER"
        )


def test_driver_model_does_not_fall_back_to_other_drivers() -> None:
    session = StubTireAnalysisSession()
    session._laps = session._laps.loc[
        session._laps["driver"].ne("AAA") | session._laps["lap_number"].le(2)
    ].copy()

    with pytest.raises(InsufficientTireDataError, match="no compound"):
        TireDegradationEngine().analyze_driver(session, "AAA")


def test_clustered_intervals_use_stint_inference_degrees_of_freedom() -> None:
    observations = pd.DataFrame(
        {
            "lap_time_seconds": [91.0, 91.2, 91.4, 91.1, 91.4, 91.7],
            "stint_id": ["AAA:01"] * 3 + ["BBB:01"] * 3,
            "compound": ["SOFT"] * 6,
            "driver": ["AAA"] * 3 + ["BBB"] * 3,
            "tire_age_laps": [1.0, 2.0, 3.0] * 2,
        }
    )
    fitted_regressor = StatsmodelsTireRegressor().fit(observations, DegradationMode.RAW, 0.95)
    slope_coefficient_name = slope_column("SOFT")

    coefficient, lower_bound, upper_bound = fitted_regressor.coefficient_interval(
        slope_coefficient_name
    )
    prediction_interval = fitted_regressor.predict(observations.iloc[[0]])

    assert fitted_regressor.regression_result.df_resid_inference == 1
    coefficient_position = fitted_regressor.design_spec.columns.index(slope_coefficient_name)
    standard_error = float(
        fitted_regressor.regression_result.cov_params()[coefficient_position, coefficient_position]
        ** 0.5
    )
    assert (upper_bound - coefficient) / standard_error == pytest.approx(12.7062, rel=1e-4)
    predicted_mean = prediction_interval["predicted_lap_time_seconds"].iloc[0]
    design_values = fitted_regressor.design(observations.iloc[[0]]).to_numpy(dtype=float)
    mean_variance = float(
        (design_values @ fitted_regressor.regression_result.cov_params() @ design_values.T).item()
    )
    mean_standard_error = mean_variance**0.5
    assert (
        prediction_interval["mean_confidence_upper_seconds"].iloc[0] - predicted_mean
    ) / mean_standard_error == pytest.approx(12.7062, rel=1e-4)
    assert coefficient - lower_bound == pytest.approx(upper_bound - coefficient)


def test_raw_mode_does_not_require_weather() -> None:
    raw_analysis = TireDegradationEngine().analyze(
        StubTireAnalysisSession(weather_available=False),
        TireModelConfig(mode=DegradationMode.RAW, quick_lap_ratio=2.0),
    )

    assert raw_analysis.mode is DegradationMode.RAW


def test_adjusted_mode_requires_weather() -> None:
    with pytest.raises(InsufficientTireDataError, match="weather"):
        TireDegradationEngine().analyze(StubTireAnalysisSession(weather_available=False))


def test_model_requires_track_status() -> None:
    with pytest.raises(InsufficientTireDataError, match="track status"):
        TireDegradationEngine().analyze(StubTireAnalysisSession(track_status_available=False))


def test_model_rejects_non_race_session() -> None:
    with pytest.raises(UnsupportedTireSessionError, match="Race and Sprint"):
        TireDegradationEngine().analyze(
            StubTireAnalysisSession(session_type=SessionType.QUALIFYING)
        )


def test_model_rejects_session_without_supported_compound() -> None:
    session = StubTireAnalysisSession()
    session._laps = session._laps.head(4)
    with pytest.raises(InsufficientTireDataError, match="no compound"):
        TireDegradationEngine().analyze(session, TireModelConfig(quick_lap_ratio=2.0))


def test_model_returns_supported_compounds_and_warns_about_sparse_ones() -> None:
    session = StubTireAnalysisSession()
    ddd_second_stint = session._laps["driver"].eq("DDD") & session._laps["stint"].eq(2)
    session._laps.loc[ddd_second_stint, "compound"] = "HARD"

    sparse_compound_analysis = TireDegradationEngine().analyze(
        session, TireModelConfig(quick_lap_ratio=2.0)
    )

    assert {estimate.compound for estimate in sparse_compound_analysis.estimates} == {
        "MEDIUM",
        "SOFT",
    }
    assert "insufficient_compound_data:HARD" in sparse_compound_analysis.warnings
    hard_compound_rows = sparse_compound_analysis.observations["compound"].eq("HARD")
    assert (
        sparse_compound_analysis.observations.loc[hard_compound_rows, "fitted_lap_time_seconds"]
        .isna()
        .all()
    )


@pytest.mark.parametrize("sentinel", ["UNKNOWN", ""])
def test_unknown_compounds_remain_excluded_audit_rows(sentinel: str) -> None:
    session = StubTireAnalysisSession()
    soft_compound_laps = session._laps["compound"].eq("SOFT")
    session._laps.loc[soft_compound_laps, "compound"] = sentinel

    unknown_compound_analysis = TireDegradationEngine().analyze(
        session, TireModelConfig(quick_lap_ratio=2.0)
    )

    assert {estimate.compound for estimate in unknown_compound_analysis.estimates} == {"MEDIUM"}
    sentinel_rows = unknown_compound_analysis.observations["compound"].eq(sentinel)
    assert sentinel_rows.any()
    assert unknown_compound_analysis.observations.loc[sentinel_rows, "eligible"].eq(False).all()
    assert (
        unknown_compound_analysis.observations.loc[sentinel_rows, "exclusion_reason"]
        .eq("unknown_compound")
        .all()
    )
    assert f"insufficient_compound_data:{sentinel}" not in unknown_compound_analysis.warnings


def test_sprint_session_is_supported() -> None:
    sprint_analysis = TireDegradationEngine().analyze(
        StubTireAnalysisSession(session_type=SessionType.SPRINT),
        TireModelConfig(quick_lap_ratio=2.0),
    )

    assert sprint_analysis.estimates


def test_non_green_session_has_no_modeling_laps() -> None:
    session = StubTireAnalysisSession()
    session._track_status["status"] = "2"

    with pytest.raises(InsufficientTireDataError, match="no compound"):
        TireDegradationEngine().analyze(session)


@pytest.mark.parametrize(
    "invalid_config_values",
    [
        {"confidence_level": 1.0},
        {"minimum_stint_laps": 1},
        {"minimum_compound_stints": 1},
        {"minimum_compound_laps": 2},
        {"quick_lap_ratio": 0.9},
        {"maximum_validation_folds": 1},
        {"curve_points": 1},
    ],
)
def test_tire_model_config_rejects_invalid_values(
    invalid_config_values: dict[str, float],
) -> None:
    with pytest.raises(ValueError):
        TireModelConfig(**invalid_config_values)  # type: ignore[arg-type]


def test_driver_tire_model_config_uses_driver_support_defaults() -> None:
    config = DriverTireModelConfig()

    assert config.minimum_compound_stints == 1
    assert config.minimum_compound_laps == 5

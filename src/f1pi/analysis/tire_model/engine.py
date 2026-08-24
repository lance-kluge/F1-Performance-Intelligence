"""Orchestration for presentation-neutral tire degradation analysis."""

from __future__ import annotations

import numpy as np
import pandas as pd

from f1pi.analysis.models import (
    CompoundDegradationEstimate,
    DegradationMode,
    TireDegradationAnalysis,
    TireModelConfig,
)
from f1pi.analysis.tire_model.analysis_session import TireAnalysisSession
from f1pi.analysis.tire_model.features import (
    WEATHER_FEATURES,
    prepare_observations,
    summarize_stints,
    supported_compounds,
)
from f1pi.analysis.tire_model.regression import (
    FittedTireRegressor,
    StatsmodelsTireRegressor,
    TireRegressor,
    slope_column,
)
from f1pi.analysis.tire_model.validation import validate_model
from f1pi.domain.exceptions import (
    DatasetNotAvailableError,
    InsufficientTireDataError,
    UnsupportedTireSessionError,
)
from f1pi.domain.models import SessionType


class TireDegradationEngine:
    """Fit validated, compound-specific tire degradation over one session."""

    def __init__(self, regressor: TireRegressor | None = None) -> None:
        self._regressor = regressor or StatsmodelsTireRegressor()

    def analyze(
        self,
        session: TireAnalysisSession,
        config: TireModelConfig | None = None,
    ) -> TireDegradationAnalysis:
        config = config or TireModelConfig()
        if session.metadata.session_type not in {SessionType.RACE, SessionType.SPRINT}:
            raise UnsupportedTireSessionError(
                "tire degradation supports Race and Sprint sessions only"
            )

        try:
            track_status = session.track_status()
        except DatasetNotAvailableError as error:
            raise InsufficientTireDataError("track status is required for tire modeling") from error
        try:
            weather = session.weather()
        except DatasetNotAvailableError as error:
            if config.mode is DegradationMode.ADJUSTED:
                raise InsufficientTireDataError(
                    "weather is required for adjusted tire modeling"
                ) from error
            weather = pd.DataFrame()

        observations = prepare_observations(session.laps(), weather, track_status, config)
        compounds, support_warnings = supported_compounds(observations, config)
        if not compounds:
            raise InsufficientTireDataError(
                "no compound has enough clean laps and independent stints"
            )
        eligible_observations = observations.loc[
            observations["eligible"] & observations["compound"].isin(compounds)
        ].copy()
        fitted_regressor = self._regressor.fit(
            eligible_observations, config.mode, config.confidence_level
        )
        validation, validation_warnings = validate_model(
            eligible_observations, config.mode, config, self._regressor
        )

        observations["fitted_lap_time_seconds"] = np.nan
        observations["residual_seconds"] = np.nan
        fitted_lap_times = fitted_regressor.predict(eligible_observations)[
            "predicted_lap_time_seconds"
        ]
        observations.loc[eligible_observations.index, "fitted_lap_time_seconds"] = fitted_lap_times
        observations.loc[eligible_observations.index, "residual_seconds"] = (
            eligible_observations["lap_time_seconds"] - fitted_lap_times
        )

        estimates = tuple(
            self._estimate(compound, eligible_observations, fitted_regressor)
            for compound in compounds
        )
        prediction_curves = _prediction_curves(
            eligible_observations, compounds, fitted_regressor, config.curve_points
        )
        analysis_warnings = _unique_warnings(
            (*support_warnings, *fitted_regressor.warnings, *validation_warnings)
        )
        return TireDegradationAnalysis(
            metadata=session.metadata,
            mode=config.mode,
            stints=summarize_stints(observations),
            estimates=estimates,
            validation=validation,
            observations=_public_observations(observations),
            curves=prediction_curves,
            warnings=analysis_warnings,
        )

    @staticmethod
    def _estimate(
        compound: str,
        eligible_observations: pd.DataFrame,
        fitted_regressor: FittedTireRegressor,
    ) -> CompoundDegradationEstimate:
        degradation_rate, lower_bound, upper_bound = fitted_regressor.coefficient_interval(
            slope_column(compound)
        )
        compound_observations = eligible_observations.loc[
            eligible_observations["compound"].eq(compound)
        ]
        return CompoundDegradationEstimate(
            compound=compound,
            seconds_per_lap=degradation_rate,
            confidence_lower_seconds_per_lap=lower_bound,
            confidence_upper_seconds_per_lap=upper_bound,
            observation_count=len(compound_observations),
            stint_count=int(compound_observations["stint_id"].nunique()),
            minimum_tire_age=float(compound_observations["tire_age_laps"].min()),
            maximum_tire_age=float(compound_observations["tire_age_laps"].max()),
        )


def _prediction_curves(
    eligible_observations: pd.DataFrame,
    compounds: tuple[str, ...],
    fitted_regressor: FittedTireRegressor,
    curve_points: int,
) -> pd.DataFrame:
    compound_curves: list[pd.DataFrame] = []
    observed_drivers = tuple(sorted(eligible_observations["driver"].astype(str).unique()))
    for compound in compounds:
        compound_observations = eligible_observations.loc[
            eligible_observations["compound"].eq(compound)
        ]
        tire_ages = np.linspace(
            float(compound_observations["tire_age_laps"].min()),
            float(compound_observations["tire_age_laps"].max()),
            curve_points,
        )
        reference_conditions = {
            "race_progress": float(compound_observations["race_progress"].median()),
            **{
                feature: (
                    0.0
                    if compound_observations[feature].dropna().empty
                    else float(compound_observations[feature].median())
                )
                for feature in WEATHER_FEATURES
            },
        }
        prediction_rows = [
            {
                "_curve_index": age_index,
                "compound": compound,
                "tire_age_laps": age,
                "driver": driver,
                **reference_conditions,
            }
            for age_index, age in enumerate(tire_ages)
            for driver in observed_drivers
        ]
        driver_expanded_observations = pd.DataFrame(prediction_rows)
        driver_expanded_design = fitted_regressor.design(driver_expanded_observations)
        driver_averaged_design = driver_expanded_design.groupby(
            driver_expanded_observations["_curve_index"]
        ).mean()
        compound_curve = fitted_regressor.predict_design(driver_averaged_design).reset_index(
            drop=True
        )
        compound_curve.insert(0, "tire_age_laps", tire_ages)
        compound_curve.insert(0, "compound", compound)
        compound_curves.append(compound_curve)
    return pd.concat(compound_curves, ignore_index=True)


def _public_observations(observations: pd.DataFrame) -> pd.DataFrame:
    columns = [
        "driver",
        "stint_id",
        "compound",
        "lap_number",
        "stint_lap_index",
        "tire_age_laps",
        "lap_time_seconds",
        "race_progress",
        *WEATHER_FEATURES,
        "eligible",
        "exclusion_reason",
        "fitted_lap_time_seconds",
        "residual_seconds",
    ]
    return observations.loc[:, columns].reset_index(drop=True)


def _unique_warnings(warnings: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(warnings))

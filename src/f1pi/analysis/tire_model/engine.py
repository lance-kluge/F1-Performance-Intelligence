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

        observations = prepare_observations(
            session.laps(), weather, track_status, config
        )
        compounds, support_warnings = supported_compounds(observations, config)
        if not compounds:
            raise InsufficientTireDataError(
                "no compound has enough clean laps and independent stints"
            )
        model_frame = observations.loc[
            observations["eligible"] & observations["compound"].isin(compounds)
        ].copy()
        fitted = self._regressor.fit(model_frame, config.mode, config.confidence_level)
        validation, validation_warnings = validate_model(
            model_frame, config.mode, config, self._regressor
        )

        observations["fitted_lap_time_seconds"] = np.nan
        observations["residual_seconds"] = np.nan
        row_predictions = fitted.predict(model_frame)["predicted_lap_time_seconds"]
        observations.loc[model_frame.index, "fitted_lap_time_seconds"] = row_predictions
        observations.loc[model_frame.index, "residual_seconds"] = (
            model_frame["lap_time_seconds"] - row_predictions
        )

        estimates = tuple(
            self._estimate(compound, model_frame, fitted) for compound in compounds
        )
        curves = _prediction_curves(model_frame, compounds, fitted, config.curve_points)
        warnings = _unique((*support_warnings, *fitted.warnings, *validation_warnings))
        return TireDegradationAnalysis(
            metadata=session.metadata,
            mode=config.mode,
            stints=summarize_stints(observations),
            estimates=estimates,
            validation=validation,
            observations=_public_observations(observations),
            curves=curves,
            warnings=warnings,
        )

    @staticmethod
    def _estimate(
        compound: str, frame: pd.DataFrame, fitted: FittedTireRegressor
    ) -> CompoundDegradationEstimate:
        coefficient, lower, upper = fitted.coefficient_interval(slope_column(compound))
        rows = frame.loc[frame["compound"].eq(compound)]
        return CompoundDegradationEstimate(
            compound=compound,
            seconds_per_lap=coefficient,
            confidence_lower_seconds_per_lap=lower,
            confidence_upper_seconds_per_lap=upper,
            observation_count=len(rows),
            stint_count=int(rows["stint_id"].nunique()),
            minimum_tire_age=float(rows["tire_age_laps"].min()),
            maximum_tire_age=float(rows["tire_age_laps"].max()),
        )


def _prediction_curves(
    frame: pd.DataFrame,
    compounds: tuple[str, ...],
    fitted: FittedTireRegressor,
    curve_points: int,
) -> pd.DataFrame:
    output: list[pd.DataFrame] = []
    drivers = tuple(sorted(frame["driver"].astype(str).unique()))
    for compound in compounds:
        compound_rows = frame.loc[frame["compound"].eq(compound)]
        ages = np.linspace(
            float(compound_rows["tire_age_laps"].min()),
            float(compound_rows["tire_age_laps"].max()),
            curve_points,
        )
        representative = {
            "race_progress": float(compound_rows["race_progress"].median()),
            **{
                feature: (
                    0.0
                    if compound_rows[feature].dropna().empty
                    else float(compound_rows[feature].median())
                )
                for feature in WEATHER_FEATURES
            },
        }
        rows = [
            {
                "_curve_index": age_index,
                "compound": compound,
                "tire_age_laps": age,
                "driver": driver,
                **representative,
            }
            for age_index, age in enumerate(ages)
            for driver in drivers
        ]
        expanded = pd.DataFrame(rows)
        design = fitted.design(expanded)
        marginal_design = design.groupby(expanded["_curve_index"]).mean()
        predictions = fitted.predict_design(marginal_design).reset_index(drop=True)
        predictions.insert(0, "tire_age_laps", ages)
        predictions.insert(0, "compound", compound)
        output.append(predictions)
    return pd.concat(output, ignore_index=True)


def _public_observations(frame: pd.DataFrame) -> pd.DataFrame:
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
    return frame.loc[:, columns].reset_index(drop=True)


def _unique(values: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(values))

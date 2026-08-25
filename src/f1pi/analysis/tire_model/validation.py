"""Whole-stint cross-validation for tire degradation models."""

from __future__ import annotations

import math

import numpy as np
import pandas as pd

from f1pi.analysis.models import (
    DegradationMode,
    TireModelConfig,
    TireModelMetrics,
    TireModelValidation,
)
from f1pi.analysis.tire_model.regression import TireRegressor
from f1pi.domain.exceptions import InsufficientTireDataError


def validate_model(
    observations: pd.DataFrame,
    mode: DegradationMode,
    config: TireModelConfig,
    regressor: TireRegressor,
) -> tuple[TireModelValidation, tuple[str, ...]]:
    """Return deterministic out-of-fold metrics with stints kept intact."""
    stint_ids = tuple(sorted(observations["stint_id"].astype(str).unique()))
    fold_count = min(config.maximum_validation_folds, len(stint_ids))
    if fold_count < 2:
        raise InsufficientTireDataError("at least two stints are required for validation")
    fold_by_stint = {stint_id: index % fold_count for index, stint_id in enumerate(stint_ids)}
    out_of_fold_predictions = pd.Series(np.nan, index=observations.index, dtype=float)
    baseline_predictions = pd.Series(np.nan, index=observations.index, dtype=float)
    successful_folds = 0

    for fold_index in range(fold_count):
        is_validation_stint = observations["stint_id"].astype(str).map(fold_by_stint).eq(fold_index)
        training_observations = observations.loc[~is_validation_stint]
        validation_observations = observations.loc[is_validation_stint]
        validation_observations = validation_observations.loc[
            validation_observations["compound"].isin(training_observations["compound"].unique())
        ]
        if training_observations.empty or validation_observations.empty:
            continue
        try:
            fitted_regressor = regressor.fit(training_observations, mode, config.confidence_level)
            validation_predictions = fitted_regressor.predict(validation_observations)[
                "predicted_lap_time_seconds"
            ]
        except (InsufficientTireDataError, ValueError, np.linalg.LinAlgError):
            continue
        out_of_fold_predictions.loc[validation_observations.index] = validation_predictions
        training_compound_means = training_observations.groupby("compound")[
            "lap_time_seconds"
        ].mean()
        training_overall_mean = float(training_observations["lap_time_seconds"].mean())
        baseline_predictions.loc[validation_observations.index] = (
            validation_observations["compound"]
            .map(training_compound_means)
            .fillna(training_overall_mean)
        )
        successful_folds += 1

    evaluated_observations = observations.loc[out_of_fold_predictions.notna()].copy()
    if evaluated_observations.empty:
        raise InsufficientTireDataError("grouped validation could not fit any fold")
    evaluated_observations["_prediction"] = out_of_fold_predictions.loc[
        evaluated_observations.index
    ]
    evaluated_observations["_baseline"] = baseline_predictions.loc[evaluated_observations.index]
    per_compound = tuple(
        _metrics(str(compound), compound_observations)
        for compound, compound_observations in evaluated_observations.groupby("compound", sort=True)
    )
    is_complete = successful_folds == fold_count and len(evaluated_observations) == len(
        observations
    )
    warnings = () if is_complete else ("incomplete_cross_validation",)
    return (
        TireModelValidation(
            fold_count=successful_folds,
            overall=_metrics("overall", evaluated_observations),
            per_compound=per_compound,
        ),
        warnings,
    )


def _metrics(scope: str, evaluated_observations: pd.DataFrame) -> TireModelMetrics:
    actual_lap_times = evaluated_observations["lap_time_seconds"].to_numpy(dtype=float)
    predicted_lap_times = evaluated_observations["_prediction"].to_numpy(dtype=float)
    baseline_lap_times = evaluated_observations["_baseline"].to_numpy(dtype=float)
    prediction_errors = predicted_lap_times - actual_lap_times
    total_variance = float(np.sum((actual_lap_times - actual_lap_times.mean()) ** 2))
    r_squared = (
        None
        if len(actual_lap_times) < 2 or total_variance <= 0
        else 1.0 - float(np.sum(prediction_errors**2)) / total_variance
    )
    return TireModelMetrics(
        scope=scope,
        observation_count=len(evaluated_observations),
        mae_seconds=float(np.mean(np.abs(prediction_errors))),
        rmse_seconds=math.sqrt(float(np.mean(prediction_errors**2))),
        r_squared=r_squared,
        baseline_mae_seconds=float(np.mean(np.abs(baseline_lap_times - actual_lap_times))),
    )

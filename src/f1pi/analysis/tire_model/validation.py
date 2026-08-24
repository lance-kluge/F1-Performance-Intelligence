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
    frame: pd.DataFrame,
    mode: DegradationMode,
    config: TireModelConfig,
    regressor: TireRegressor,
) -> tuple[TireModelValidation, tuple[str, ...]]:
    """Return deterministic out-of-fold metrics with stints kept intact."""
    groups = tuple(sorted(frame["stint_id"].astype(str).unique()))
    fold_count = min(config.maximum_validation_folds, len(groups))
    if fold_count < 2:
        raise InsufficientTireDataError("at least two stints are required for validation")
    assignment = {group: index % fold_count for index, group in enumerate(groups)}
    predicted = pd.Series(np.nan, index=frame.index, dtype=float)
    baseline = pd.Series(np.nan, index=frame.index, dtype=float)
    successful_folds = 0

    for fold in range(fold_count):
        validation_mask = frame["stint_id"].astype(str).map(assignment).eq(fold)
        train = frame.loc[~validation_mask]
        test = frame.loc[validation_mask]
        test = test.loc[test["compound"].isin(train["compound"].unique())]
        if train.empty or test.empty:
            continue
        try:
            fitted = regressor.fit(train, mode, config.confidence_level)
            fold_prediction = fitted.predict(test)["predicted_lap_time_seconds"]
        except (InsufficientTireDataError, ValueError, np.linalg.LinAlgError):
            continue
        predicted.loc[test.index] = fold_prediction
        compound_means = train.groupby("compound")["lap_time_seconds"].mean()
        overall_mean = float(train["lap_time_seconds"].mean())
        baseline.loc[test.index] = test["compound"].map(compound_means).fillna(overall_mean)
        successful_folds += 1

    evaluated = frame.loc[predicted.notna()].copy()
    if evaluated.empty:
        raise InsufficientTireDataError("grouped validation could not fit any fold")
    evaluated["_prediction"] = predicted.loc[evaluated.index]
    evaluated["_baseline"] = baseline.loc[evaluated.index]
    per_compound = tuple(
        _metrics(str(compound), rows)
        for compound, rows in evaluated.groupby("compound", sort=True)
    )
    complete = successful_folds == fold_count and len(evaluated) == len(frame)
    warnings = () if complete else ("incomplete_cross_validation",)
    return (
        TireModelValidation(
            fold_count=successful_folds,
            overall=_metrics("overall", evaluated),
            per_compound=per_compound,
        ),
        warnings,
    )


def _metrics(scope: str, frame: pd.DataFrame) -> TireModelMetrics:
    actual = frame["lap_time_seconds"].to_numpy(dtype=float)
    predicted = frame["_prediction"].to_numpy(dtype=float)
    baseline = frame["_baseline"].to_numpy(dtype=float)
    error = predicted - actual
    total = float(np.sum((actual - actual.mean()) ** 2))
    r_squared = None if len(actual) < 2 or total <= 0 else 1.0 - float(np.sum(error**2)) / total
    return TireModelMetrics(
        scope=scope,
        observation_count=len(frame),
        mae_seconds=float(np.mean(np.abs(error))),
        rmse_seconds=math.sqrt(float(np.mean(error**2))),
        r_squared=r_squared,
        baseline_mae_seconds=float(np.mean(np.abs(baseline - actual))),
    )

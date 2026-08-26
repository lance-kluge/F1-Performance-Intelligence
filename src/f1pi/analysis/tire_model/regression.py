"""Replaceable linear-regression implementation for tire degradation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

import numpy as np
import pandas as pd
import statsmodels.api as sm

from f1pi.analysis.models import DegradationMode
from f1pi.analysis.tire_model.features import WEATHER_FEATURES
from f1pi.domain.exceptions import InsufficientTireDataError


class FittedTireRegressor(Protocol):
    warnings: tuple[str, ...]

    def predict(self, observations: pd.DataFrame) -> pd.DataFrame: ...

    def predict_design(self, design_matrix: pd.DataFrame) -> pd.DataFrame: ...

    def design(self, observations: pd.DataFrame) -> pd.DataFrame: ...

    def coefficient_interval(self, coefficient_name: str) -> tuple[float, float, float]: ...

    def sample_coefficients(self, random: np.random.Generator, sample_count: int) -> np.ndarray: ...

    def predict_with_coefficients(
        self, observations: pd.DataFrame, coefficients: np.ndarray
    ) -> np.ndarray: ...


class TireRegressor(Protocol):
    def fit(
        self,
        observations: pd.DataFrame,
        mode: DegradationMode,
        confidence_level: float,
    ) -> FittedTireRegressor: ...


@dataclass(frozen=True, slots=True)
class _DesignSpec:
    mode: DegradationMode
    compounds: tuple[str, ...]
    drivers: tuple[str, ...]
    condition_centres: dict[str, float]
    condition_scales: dict[str, float]
    columns: tuple[str, ...]


class StatsmodelsTireRegressor:
    """OLS with compound slopes and stint-clustered covariance."""

    def fit(
        self,
        observations: pd.DataFrame,
        mode: DegradationMode,
        confidence_level: float,
    ) -> FittedTireRegressor:
        design_spec, design_matrix, warnings = _fit_design(observations, mode)
        lap_times = observations["lap_time_seconds"].to_numpy(dtype=float)
        if len(observations) <= design_matrix.shape[1] or np.linalg.matrix_rank(
            design_matrix.to_numpy()
        ) < len(design_matrix.columns):
            raise InsufficientTireDataError(
                "the tire model design does not have enough independent observations"
            )

        ols_fit = sm.OLS(lap_times, design_matrix).fit()
        stint_groups = observations["stint_id"].astype(str).to_numpy()
        if len(np.unique(stint_groups)) >= 2:
            covariance_adjusted_result = ols_fit.get_robustcov_results(
                cov_type="cluster", groups=stint_groups, use_correction=True
            )
        else:
            covariance_adjusted_result = ols_fit.get_robustcov_results(cov_type="HC3")
            warnings.append("cluster_covariance_unavailable")
        return _StatsmodelsFit(
            regression_result=covariance_adjusted_result,
            design_spec=design_spec,
            confidence_level=confidence_level,
            warnings=tuple(warnings),
        )


@dataclass(slots=True)
class _StatsmodelsFit:
    regression_result: Any
    design_spec: _DesignSpec
    confidence_level: float
    warnings: tuple[str, ...]

    def design(self, observations: pd.DataFrame) -> pd.DataFrame:
        candidate_columns = _candidate_design(observations, self.design_spec)
        return candidate_columns.loc[:, list(self.design_spec.columns)]

    def predict(self, observations: pd.DataFrame) -> pd.DataFrame:
        return self.predict_design(self.design(observations))

    def predict_design(self, design_matrix: pd.DataFrame) -> pd.DataFrame:
        design_values = design_matrix.to_numpy(dtype=float)
        coefficients = np.asarray(self.regression_result.params, dtype=float)
        coefficient_covariance = np.asarray(self.regression_result.cov_params(), dtype=float)
        predicted_means = design_values @ coefficients
        mean_variance = np.einsum(
            "ij,jk,ik->i", design_values, coefficient_covariance, design_values
        )
        mean_standard_error = np.sqrt(np.maximum(mean_variance, 0.0))
        prediction_standard_error = np.sqrt(
            np.maximum(mean_variance + float(self.regression_result.scale), 0.0)
        )
        critical_value = _critical_value(self.regression_result, self.confidence_level)
        return pd.DataFrame(
            {
                "predicted_lap_time_seconds": predicted_means,
                "mean_confidence_lower_seconds": predicted_means
                - critical_value * mean_standard_error,
                "mean_confidence_upper_seconds": predicted_means
                + critical_value * mean_standard_error,
                "prediction_lower_seconds": predicted_means
                - critical_value * prediction_standard_error,
                "prediction_upper_seconds": predicted_means
                + critical_value * prediction_standard_error,
            },
            index=design_matrix.index,
        )

    def coefficient_interval(self, coefficient_name: str) -> tuple[float, float, float]:
        try:
            coefficient_position = self.design_spec.columns.index(coefficient_name)
        except ValueError as error:
            raise InsufficientTireDataError(
                f"model coefficient is unavailable: {coefficient_name}"
            ) from error
        coefficient = float(
            np.asarray(self.regression_result.params, dtype=float)[coefficient_position]
        )
        coefficient_covariance = np.asarray(self.regression_result.cov_params(), dtype=float)
        standard_error = float(
            np.sqrt(
                max(
                    coefficient_covariance[coefficient_position, coefficient_position],
                    0.0,
                )
            )
        )
        critical_value = _critical_value(self.regression_result, self.confidence_level)
        return (
            coefficient,
            coefficient - critical_value * standard_error,
            coefficient + critical_value * standard_error,
        )

    def sample_coefficients(self, random: np.random.Generator, sample_count: int) -> np.ndarray:
        """Draw correlated coefficient vectors for downstream uncertainty propagation."""
        coefficients = np.asarray(self.regression_result.params, dtype=float)
        covariance = np.asarray(self.regression_result.cov_params(), dtype=float)
        covariance = (covariance + covariance.T) / 2.0
        eigenvalues, eigenvectors = np.linalg.eigh(covariance)
        positive_covariance = (eigenvectors * np.maximum(eigenvalues, 0.0)) @ eigenvectors.T
        return random.multivariate_normal(
            coefficients,
            positive_covariance,
            size=sample_count,
            check_valid="ignore",
        )

    def predict_with_coefficients(
        self, observations: pd.DataFrame, coefficients: np.ndarray
    ) -> np.ndarray:
        """Predict rows for one or many coefficient vectors."""
        design_values = self.design(observations).to_numpy(dtype=float)
        return np.asarray(np.asarray(coefficients, dtype=float) @ design_values.T)


def _critical_value(regression_result: Any, confidence_level: float) -> float:
    zero_contrast_weights = np.zeros(len(regression_result.params), dtype=float)
    coefficient_contrast = regression_result.t_test(zero_contrast_weights)
    return float(
        coefficient_contrast.dist.ppf(
            (1.0 + confidence_level) / 2.0, *coefficient_contrast.dist_args
        )
    )


def slope_column(compound: str) -> str:
    return f"compound_tire_age::{compound}"


def _fit_design(
    observations: pd.DataFrame, mode: DegradationMode
) -> tuple[_DesignSpec, pd.DataFrame, list[str]]:
    compounds = tuple(sorted(observations["compound"].astype(str).unique()))
    drivers = tuple(sorted(observations["driver"].astype(str).unique()))
    condition_centres: dict[str, float] = {}
    condition_scales: dict[str, float] = {}
    if mode is DegradationMode.ADJUSTED:
        for feature in ("race_progress", *WEATHER_FEATURES):
            feature_values = pd.to_numeric(observations[feature], errors="coerce").astype(float)
            feature_centre = float(feature_values.mean())
            feature_scale = float(feature_values.std(ddof=0))
            if np.isfinite(feature_scale) and feature_scale > 1e-12:
                condition_centres[feature] = feature_centre
                condition_scales[feature] = feature_scale

    provisional_spec = _DesignSpec(
        mode, compounds, drivers, condition_centres, condition_scales, ()
    )
    candidate_columns = _candidate_design(observations, provisional_spec)
    required_columns = [
        column
        for compound in compounds
        for column in (f"compound_intercept::{compound}", slope_column(compound))
    ]
    selected_columns = list(required_columns)
    required_design = candidate_columns[required_columns].to_numpy(dtype=float)
    if np.linalg.matrix_rank(required_design) < len(required_columns):
        raise InsufficientTireDataError("compound degradation slopes are not identifiable")

    warnings: list[str] = []
    selected_rank = len(required_columns)
    for column in candidate_columns.columns:
        if column in selected_columns:
            continue
        expanded_design = candidate_columns[[*selected_columns, column]].to_numpy(dtype=float)
        expanded_rank = int(np.linalg.matrix_rank(expanded_design))
        if expanded_rank > selected_rank and expanded_rank <= len(observations) - 2:
            selected_columns.append(column)
            selected_rank = expanded_rank
        else:
            drop_reason = (
                "collinear" if expanded_rank == selected_rank else "insufficient_degrees_of_freedom"
            )
            warnings.append(f"dropped_{drop_reason}_feature:{column}")

    constant_conditions = set(("race_progress", *WEATHER_FEATURES)) - set(condition_centres)
    if mode is DegradationMode.ADJUSTED:
        warnings.extend(
            f"dropped_constant_feature:{feature}" for feature in sorted(constant_conditions)
        )
    design_spec = _DesignSpec(
        mode,
        compounds,
        drivers,
        condition_centres,
        condition_scales,
        tuple(selected_columns),
    )
    return design_spec, candidate_columns[selected_columns], warnings


def _candidate_design(observations: pd.DataFrame, design_spec: _DesignSpec) -> pd.DataFrame:
    design_columns: dict[str, pd.Series] = {}
    compound_values = observations["compound"].astype(str)
    tire_ages = pd.to_numeric(observations["tire_age_laps"], errors="coerce").astype(float)
    for compound in design_spec.compounds:
        compound_indicator = compound_values.eq(compound).astype(float)
        design_columns[f"compound_intercept::{compound}"] = compound_indicator
        design_columns[slope_column(compound)] = compound_indicator * tire_ages

    if design_spec.mode is DegradationMode.ADJUSTED:
        driver_values = observations["driver"].astype(str)
        for driver in design_spec.drivers[1:]:
            design_columns[f"driver::{driver}"] = driver_values.eq(driver).astype(float)
        for feature, feature_centre in design_spec.condition_centres.items():
            feature_values = pd.to_numeric(observations[feature], errors="coerce").astype(float)
            design_columns[f"condition::{feature}"] = (
                feature_values - feature_centre
            ) / design_spec.condition_scales[feature]
    return pd.DataFrame(design_columns, index=observations.index, dtype=float)

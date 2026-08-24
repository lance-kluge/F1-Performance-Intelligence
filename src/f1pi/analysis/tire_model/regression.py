"""Replaceable linear-regression implementation for tire degradation."""

from __future__ import annotations

from dataclasses import dataclass
from statistics import NormalDist
from typing import Any, Protocol

import numpy as np
import pandas as pd
import statsmodels.api as sm

from f1pi.analysis.models import DegradationMode
from f1pi.analysis.tire_model.features import WEATHER_FEATURES
from f1pi.domain.exceptions import InsufficientTireDataError


class FittedTireRegressor(Protocol):
    warnings: tuple[str, ...]

    def predict(self, frame: pd.DataFrame) -> pd.DataFrame: ...

    def predict_design(self, design: pd.DataFrame) -> pd.DataFrame: ...

    def design(self, frame: pd.DataFrame) -> pd.DataFrame: ...

    def coefficient_interval(self, name: str) -> tuple[float, float, float]: ...


class TireRegressor(Protocol):
    def fit(
        self,
        frame: pd.DataFrame,
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
        frame: pd.DataFrame,
        mode: DegradationMode,
        confidence_level: float,
    ) -> FittedTireRegressor:
        spec, design, warnings = _fit_design(frame, mode)
        target = frame["lap_time_seconds"].to_numpy(dtype=float)
        if len(frame) <= design.shape[1] or np.linalg.matrix_rank(design.to_numpy()) < len(
            design.columns
        ):
            raise InsufficientTireDataError(
                "the tire model design does not have enough independent observations"
            )

        fitted = sm.OLS(target, design).fit()
        groups = frame["stint_id"].astype(str).to_numpy()
        if len(np.unique(groups)) >= 2:
            result = fitted.get_robustcov_results(
                cov_type="cluster", groups=groups, use_correction=True
            )
        else:
            result = fitted.get_robustcov_results(cov_type="HC3")
            warnings.append("cluster_covariance_unavailable")
        return _StatsmodelsFit(
            result=result,
            spec=spec,
            confidence_level=confidence_level,
            warnings=tuple(warnings),
        )


@dataclass(slots=True)
class _StatsmodelsFit:
    result: Any
    spec: _DesignSpec
    confidence_level: float
    warnings: tuple[str, ...]

    def design(self, frame: pd.DataFrame) -> pd.DataFrame:
        candidates = _candidate_design(frame, self.spec)
        return candidates.loc[:, list(self.spec.columns)]

    def predict(self, frame: pd.DataFrame) -> pd.DataFrame:
        return self.predict_design(self.design(frame))

    def predict_design(self, design: pd.DataFrame) -> pd.DataFrame:
        values = design.to_numpy(dtype=float)
        parameters = np.asarray(self.result.params, dtype=float)
        covariance = np.asarray(self.result.cov_params(), dtype=float)
        mean = values @ parameters
        mean_variance = np.einsum("ij,jk,ik->i", values, covariance, values)
        mean_standard_error = np.sqrt(np.maximum(mean_variance, 0.0))
        prediction_standard_error = np.sqrt(
            np.maximum(mean_variance + float(self.result.scale), 0.0)
        )
        critical = NormalDist().inv_cdf((1.0 + self.confidence_level) / 2.0)
        return pd.DataFrame(
            {
                "predicted_lap_time_seconds": mean,
                "mean_confidence_lower_seconds": mean - critical * mean_standard_error,
                "mean_confidence_upper_seconds": mean + critical * mean_standard_error,
                "prediction_lower_seconds": mean - critical * prediction_standard_error,
                "prediction_upper_seconds": mean + critical * prediction_standard_error,
            },
            index=design.index,
        )

    def coefficient_interval(self, name: str) -> tuple[float, float, float]:
        try:
            position = self.spec.columns.index(name)
        except ValueError as error:
            raise InsufficientTireDataError(f"model coefficient is unavailable: {name}") from error
        coefficient = float(np.asarray(self.result.params, dtype=float)[position])
        covariance = np.asarray(self.result.cov_params(), dtype=float)
        standard_error = float(np.sqrt(max(covariance[position, position], 0.0)))
        critical = NormalDist().inv_cdf((1.0 + self.confidence_level) / 2.0)
        return (
            coefficient,
            coefficient - critical * standard_error,
            coefficient + critical * standard_error,
        )


def slope_column(compound: str) -> str:
    return f"compound_tire_age::{compound}"


def _fit_design(
    frame: pd.DataFrame, mode: DegradationMode
) -> tuple[_DesignSpec, pd.DataFrame, list[str]]:
    compounds = tuple(sorted(frame["compound"].astype(str).unique()))
    drivers = tuple(sorted(frame["driver"].astype(str).unique()))
    centres: dict[str, float] = {}
    scales: dict[str, float] = {}
    if mode is DegradationMode.ADJUSTED:
        for feature in ("race_progress", *WEATHER_FEATURES):
            values = pd.to_numeric(frame[feature], errors="coerce").astype(float)
            centre = float(values.mean())
            scale = float(values.std(ddof=0))
            if np.isfinite(scale) and scale > 1e-12:
                centres[feature] = centre
                scales[feature] = scale

    provisional = _DesignSpec(mode, compounds, drivers, centres, scales, ())
    candidates = _candidate_design(frame, provisional)
    core = [
        column
        for compound in compounds
        for column in (f"compound_intercept::{compound}", slope_column(compound))
    ]
    selected = list(core)
    core_values = candidates[core].to_numpy(dtype=float)
    if np.linalg.matrix_rank(core_values) < len(core):
        raise InsufficientTireDataError("compound degradation slopes are not identifiable")

    warnings: list[str] = []
    rank = len(core)
    for column in candidates.columns:
        if column in selected:
            continue
        proposed = candidates[[*selected, column]].to_numpy(dtype=float)
        proposed_rank = int(np.linalg.matrix_rank(proposed))
        if proposed_rank > rank and proposed_rank <= len(frame) - 2:
            selected.append(column)
            rank = proposed_rank
        else:
            reason = "collinear" if proposed_rank == rank else "insufficient_degrees_of_freedom"
            warnings.append(f"dropped_{reason}_feature:{column}")

    missing_conditions = set(("race_progress", *WEATHER_FEATURES)) - set(centres)
    if mode is DegradationMode.ADJUSTED:
        warnings.extend(f"dropped_constant_feature:{name}" for name in sorted(missing_conditions))
    spec = _DesignSpec(mode, compounds, drivers, centres, scales, tuple(selected))
    return spec, candidates[selected], warnings


def _candidate_design(frame: pd.DataFrame, spec: _DesignSpec) -> pd.DataFrame:
    output: dict[str, pd.Series] = {}
    compound_values = frame["compound"].astype(str)
    tire_age = pd.to_numeric(frame["tire_age_laps"], errors="coerce").astype(float)
    for compound in spec.compounds:
        indicator = compound_values.eq(compound).astype(float)
        output[f"compound_intercept::{compound}"] = indicator
        output[slope_column(compound)] = indicator * tire_age

    if spec.mode is DegradationMode.ADJUSTED:
        driver_values = frame["driver"].astype(str)
        for driver in spec.drivers[1:]:
            output[f"driver::{driver}"] = driver_values.eq(driver).astype(float)
        for feature, centre in spec.condition_centres.items():
            values = pd.to_numeric(frame[feature], errors="coerce").astype(float)
            output[f"condition::{feature}"] = (values - centre) / spec.condition_scales[feature]
    return pd.DataFrame(output, index=frame.index, dtype=float)

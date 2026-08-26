"""Calibrate replaceable pace, pit-loss, traffic, and neutralization models."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, cast

import numpy as np
import pandas as pd

from f1pi.analysis.models import (
    DegradationMode,
    NeutralizationAssumptions,
    NeutralizationKind,
    StrategyCalibrationDiagnostics,
    StrategySimulationConfig,
    StrategySimulationRequest,
)
from f1pi.analysis.strategy_simulator.preparation import GREEN, PreparedRace
from f1pi.analysis.tire_model.features import WEATHER_FEATURES
from f1pi.analysis.tire_model.regression import FittedTireRegressor, StatsmodelsTireRegressor
from f1pi.domain.exceptions import (
    InsufficientStrategyDataError,
    InsufficientTireDataError,
    InvalidStrategyError,
)


class PaceModel(Protocol):
    supported_compounds: tuple[str, ...]

    def sample_coefficients(
        self, random_generator: np.random.Generator, sample_count: int
    ) -> np.ndarray: ...

    def predict(
        self,
        lap_number: int,
        drivers: tuple[str, ...],
        compounds: np.ndarray,
        tire_ages: np.ndarray,
        coefficients: np.ndarray,
    ) -> np.ndarray: ...

    def residual_draws(self, drivers: tuple[str, ...], uniforms: np.ndarray) -> np.ndarray: ...


class PitLossModel(Protocol):
    @property
    def sample_count(self) -> int: ...

    def losses(self, condition: str, uniforms: np.ndarray) -> np.ndarray: ...


class TrafficModel(Protocol):
    @property
    def sample_count(self) -> int: ...

    def penalties(self, gaps: np.ndarray, uniforms: np.ndarray) -> np.ndarray: ...


class NeutralizationModel(Protocol):
    def parameters(
        self,
        kind: NeutralizationKind,
        assumptions: NeutralizationAssumptions | None,
    ) -> NeutralizationAssumptions: ...


@dataclass(frozen=True, slots=True)
class CalibratedModels:
    pace: PaceModel
    pit_loss: PitLossModel
    traffic: TrafficModel
    neutralization: NeutralizationModel
    diagnostics: StrategyCalibrationDiagnostics
    warnings: tuple[str, ...]


@dataclass(slots=True)
class RegressionPaceModel:
    tire_regressor: FittedTireRegressor
    weather_by_lap: pd.DataFrame
    supported_compounds: tuple[str, ...]
    compound_fallbacks: dict[str, str]
    residuals_by_driver: dict[str, np.ndarray]
    pooled_residuals: np.ndarray

    def sample_coefficients(
        self, random_generator: np.random.Generator, sample_count: int
    ) -> np.ndarray:
        return self.tire_regressor.sample_coefficients(random_generator, sample_count)

    def predict(
        self,
        lap_number: int,
        drivers: tuple[str, ...],
        compounds: np.ndarray,
        tire_ages: np.ndarray,
        coefficients: np.ndarray,
    ) -> np.ndarray:
        conditions = cast(pd.Series, self.weather_by_lap.loc[lap_number])
        modeled_compounds = np.asarray(
            [self.compound_fallbacks.get(str(value), str(value)) for value in compounds],
            dtype=object,
        )
        rows = pd.DataFrame(
            {
                "driver": drivers,
                "compound": modeled_compounds,
                "tire_age_laps": tire_ages,
                **{
                    feature: float(conditions[feature])
                    for feature in ("race_progress", *WEATHER_FEATURES)
                },
            }
        )
        return self.tire_regressor.predict_with_coefficients(rows, coefficients)

    def residual_draws(self, drivers: tuple[str, ...], uniforms: np.ndarray) -> np.ndarray:
        draws = np.zeros_like(uniforms, dtype=float)
        for driver_index, driver in enumerate(drivers):
            residuals = self.residuals_by_driver.get(driver, self.pooled_residuals)
            indices = np.minimum(
                (uniforms[:, driver_index] * len(residuals)).astype(int), len(residuals) - 1
            )
            draws[:, driver_index] = residuals[indices]
        return draws


@dataclass(frozen=True, slots=True)
class EmpiricalPitLossModel:
    values_by_condition: dict[str, np.ndarray]
    sample_count: int

    def losses(self, condition: str, uniforms: np.ndarray) -> np.ndarray:
        values = self.values_by_condition.get(condition, self.values_by_condition[GREEN])
        indices = np.minimum((uniforms * len(values)).astype(int), len(values) - 1)
        return np.asarray(np.maximum(values[indices], 0.0))


@dataclass(frozen=True, slots=True)
class EmpiricalTrafficModel:
    maximum_gap_seconds: float
    gap_bucket_edges_seconds: np.ndarray
    median_penalties_seconds: np.ndarray
    penalty_residuals_seconds: np.ndarray
    sample_count: int

    def penalties(self, gaps: np.ndarray, uniforms: np.ndarray) -> np.ndarray:
        penalties = np.zeros_like(gaps, dtype=float)
        active = np.isfinite(gaps) & (gaps >= 0) & (gaps <= self.maximum_gap_seconds)
        if not np.any(active):
            return penalties
        bucket = np.clip(
            np.searchsorted(self.gap_bucket_edges_seconds, gaps[active], side="right") - 1,
            0,
            3,
        )
        residual_indices = np.minimum(
            (uniforms[active] * len(self.penalty_residuals_seconds)).astype(int),
            len(self.penalty_residuals_seconds) - 1,
        )
        penalties[active] = np.maximum(
            self.median_penalties_seconds[bucket]
            + self.penalty_residuals_seconds[residual_indices],
            0.0,
        )
        return penalties


@dataclass(frozen=True, slots=True)
class EmpiricalNeutralizationModel:
    parameters_by_kind: dict[NeutralizationKind, NeutralizationAssumptions]

    def parameters(
        self,
        kind: NeutralizationKind,
        assumptions: NeutralizationAssumptions | None,
    ) -> NeutralizationAssumptions:
        if assumptions is not None:
            return assumptions
        try:
            return self.parameters_by_kind[kind]
        except KeyError as error:
            raise InsufficientStrategyDataError(
                f"{kind.value} is not calibrated; custom assumptions are required"
            ) from error


def calibrate_models(
    prepared: PreparedRace,
    request: StrategySimulationRequest,
    config: StrategySimulationConfig,
) -> CalibratedModels:
    observations = prepared.observations.copy()
    eligible_green = observations["eligible"] & observations["condition"].eq(GREEN)
    clean_air = observations["gap_ahead_seconds"].gt(config.traffic_gap_seconds) | np.isinf(
        observations["gap_ahead_seconds"].astype(float)
    )
    clean = observations.loc[eligible_green & clean_air].copy()
    warnings: list[str] = []

    # Retain every field driver's effect even when all of their valid laps were in traffic.
    for driver in prepared.drivers:
        driver_clean = clean.loc[clean["driver"].eq(driver)]
        if len(driver_clean) >= 3:
            continue
        fallback = observations.loc[eligible_green & observations["driver"].eq(driver)].head(3)
        if not fallback.empty:
            clean = pd.concat([clean, fallback]).drop_duplicates(["driver", "lap_number"])
            warnings.append(f"traffic_contaminated_pace_fallback:{driver}")

    compound_support = clean.groupby("compound").agg(
        laps=("lap_number", "size"), ages=("tire_age_laps", "nunique")
    )
    supported_compounds = tuple(
        sorted(
            str(compound)
            for compound, row in compound_support.iterrows()
            if int(row["laps"]) >= 5 and int(row["ages"]) >= 2
        )
    )
    clean = clean.loc[clean["compound"].isin(supported_compounds)].copy()
    if len(clean.loc[clean["driver"].eq(request.driver)]) < 3:
        raise InsufficientStrategyDataError("target driver has insufficient clean pace support")
    requested_compounds = {
        stop.compound for strategy in request.strategies for stop in strategy.stops
    }
    unsupported = requested_compounds - set(supported_compounds)
    if unsupported:
        raise InvalidStrategyError(
            f"strategy compounds lack calibrated tire support: {sorted(unsupported)}"
        )
    if not supported_compounds:
        raise InsufficientStrategyDataError("no compound has enough clean laps for pace modeling")

    try:
        tire_regressor = StatsmodelsTireRegressor().fit(
            clean, DegradationMode.ADJUSTED, config.confidence_level
        )
    except (InsufficientTireDataError, np.linalg.LinAlgError) as error:
        raise InsufficientStrategyDataError("pace model could not be identified") from error
    warnings.extend(tire_regressor.warnings)
    predicted_lap_times_seconds = tire_regressor.predict(clean)[
        "predicted_lap_time_seconds"
    ].to_numpy(dtype=float)
    residual_values = (
        clean["lap_time_seconds"].to_numpy(dtype=float) - predicted_lap_times_seconds
    )
    residual_values = residual_values - float(np.mean(residual_values))
    pooled_residuals = residual_values if len(residual_values) else np.array([0.0])
    residuals_by_driver = {
        str(driver): values["lap_time_seconds"].to_numpy(dtype=float)
        - tire_regressor.predict(values)["predicted_lap_time_seconds"].to_numpy(dtype=float)
        for driver, values in clean.groupby("driver")
        if len(values) >= 3
    }
    residuals_by_driver = {
        driver: residuals - float(np.mean(residuals))
        for driver, residuals in residuals_by_driver.items()
    }
    compound_fallbacks = _compound_fallbacks(observations, supported_compounds)
    warnings.extend(
        f"compound_pace_fallback:{compound}->{fallback}"
        for compound, fallback in sorted(compound_fallbacks.items())
    )
    pace = RegressionPaceModel(
        tire_regressor,
        prepared.weather_by_lap,
        supported_compounds,
        compound_fallbacks,
        residuals_by_driver,
        pooled_residuals,
    )
    try:
        pit_loss, pit_warnings = _calibrate_pit_loss(prepared, pace)
    except InsufficientStrategyDataError:
        future_plans = [
            *request.strategies,
            *prepared.observed_plans.values(),
        ]
        if any(
            stop.after_lap > request.decision_lap for plan in future_plans for stop in plan.stops
        ):
            raise
        pit_loss = EmpiricalPitLossModel({GREEN: np.array([0.0])}, 0)
        pit_warnings = ("pit_loss_unavailable:no_stops",)
    fitted_compound_observations = observations.loc[
        observations["compound"].isin(supported_compounds)
    ].copy()
    traffic, traffic_warnings = _calibrate_traffic(
        fitted_compound_observations, tire_regressor, config
    )
    neutralization, neutralization_warnings = _calibrate_neutralization(
        fitted_compound_observations, tire_regressor, pit_loss
    )
    warnings.extend((*pit_warnings, *traffic_warnings, *neutralization_warnings))

    diagnostics = StrategyCalibrationDiagnostics(
        pace_observation_count=len(clean),
        target_pace_observation_count=int(clean["driver"].eq(request.driver).sum()),
        pit_stop_sample_count=pit_loss.sample_count,
        traffic_sample_count=traffic.sample_count,
        pace_mae_seconds=float(np.mean(np.abs(residual_values))),
        pace_rmse_seconds=float(np.sqrt(np.mean(np.square(residual_values)))),
        supported_compounds=supported_compounds,
    )
    return CalibratedModels(
        pace,
        pit_loss,
        traffic,
        neutralization,
        diagnostics,
        tuple(dict.fromkeys(warnings)),
    )


def _compound_fallbacks(observations: pd.DataFrame, supported: tuple[str, ...]) -> dict[str, str]:
    eligible = observations.loc[observations["eligible"]]
    medians = eligible.groupby("compound")["lap_time_seconds"].median().to_dict()
    fallbacks: dict[str, str] = {}
    for compound in observations["compound"].dropna().astype(str).unique():
        if compound in supported:
            continue
        compound_median = float(medians.get(compound, np.median(list(medians.values()))))
        fallbacks[compound] = min(
            supported,
            key=lambda candidate: abs(
                float(medians.get(candidate, compound_median)) - compound_median
            ),
        )
    return fallbacks


def _calibrate_pit_loss(
    prepared: PreparedRace, pace: RegressionPaceModel
) -> tuple[EmpiricalPitLossModel, tuple[str, ...]]:
    observations = prepared.observations.set_index(["driver", "lap_number"], drop=False)
    samples: dict[str, list[float]] = {}
    for driver, driver_laps in prepared.laps.groupby("driver"):
        ordered = driver_laps.sort_values("lap_number")
        for row_index in range(len(ordered) - 1):
            in_lap = ordered.iloc[row_index]
            out_lap = ordered.iloc[row_index + 1]
            if pd.isna(in_lap.get("pit_in_time_ns")) or pd.isna(out_lap.get("pit_out_time_ns")):
                continue
            keys = (
                (str(driver), int(in_lap["lap_number"])),
                (str(driver), int(out_lap["lap_number"])),
            )
            if not all(key in observations.index for key in keys):
                continue
            pair = observations.loc[list(keys)]
            if pair[list(WEATHER_FEATURES)].isna().any(axis=None):
                continue
            expected = pace.tire_regressor.predict(pair)["predicted_lap_time_seconds"].sum()
            actual = pair["lap_time_seconds"].sum()
            loss = float(actual - expected)
            if not np.isfinite(loss) or loss <= 0:
                continue
            condition = str(in_lap["condition"])
            if str(out_lap["condition"]) != GREEN:
                condition = str(out_lap["condition"])
            samples.setdefault(condition, []).append(loss)
    pooled = [value for values in samples.values() for value in values]
    if not pooled:
        raise InsufficientStrategyDataError("no complete pit-stop pair is available")
    if GREEN not in samples:
        samples[GREEN] = pooled
    values_by_condition: dict[str, np.ndarray] = {}
    warnings: list[str] = []
    green = np.asarray(samples[GREEN], dtype=float)
    green_centre = float(np.median(green))
    for condition, values in samples.items():
        raw = np.asarray(values, dtype=float)
        centre = float(np.median(raw))
        values_by_condition[condition] = centre + (raw - centre)
    values_by_condition[GREEN] = green_centre + (green - green_centre)
    if len(green) < 3:
        warnings.append("sparse_green_pit_loss_calibration")
    return EmpiricalPitLossModel(values_by_condition, len(pooled)), tuple(warnings)


def _calibrate_traffic(
    observations: pd.DataFrame,
    tire_regressor: FittedTireRegressor,
    config: StrategySimulationConfig,
) -> tuple[EmpiricalTrafficModel, tuple[str, ...]]:
    candidates = observations.loc[
        observations["eligible"]
        & observations["condition"].eq(GREEN)
        & observations["gap_ahead_seconds"].between(0, config.traffic_gap_seconds)
    ].copy()
    edges = np.linspace(0.0, config.traffic_gap_seconds, 5)
    if candidates.empty:
        return (
            EmpiricalTrafficModel(
                config.traffic_gap_seconds, edges, np.zeros(4), np.array([0.0]), 0
            ),
            ("traffic_model_unavailable:no_close_laps",),
        )
    predicted_lap_times_seconds = tire_regressor.predict(candidates)[
        "predicted_lap_time_seconds"
    ].to_numpy(dtype=float)
    penalties = np.maximum(
        candidates["lap_time_seconds"].to_numpy(dtype=float) - predicted_lap_times_seconds,
        0.0,
    )
    buckets = np.clip(
        np.searchsorted(edges, candidates["gap_ahead_seconds"].to_numpy(dtype=float), side="right")
        - 1,
        0,
        3,
    )
    medians = np.array(
        [
            np.median(penalties[buckets == index]) if np.any(buckets == index) else np.nan
            for index in range(4)
        ]
    )
    pooled_median = float(np.median(penalties))
    medians = np.where(np.isnan(medians), pooled_median, medians)
    # Penalty cannot increase as the gap grows.
    medians = np.maximum.accumulate(medians[::-1])[::-1]
    residuals = penalties - medians[buckets]
    return (
        EmpiricalTrafficModel(
            config.traffic_gap_seconds,
            edges,
            medians,
            residuals if len(residuals) else np.array([0.0]),
            len(candidates),
        ),
        (),
    )


def _calibrate_neutralization(
    observations: pd.DataFrame,
    tire_regressor: FittedTireRegressor,
    pit_loss: EmpiricalPitLossModel,
) -> tuple[EmpiricalNeutralizationModel, tuple[str, ...]]:
    parameters: dict[NeutralizationKind, NeutralizationAssumptions] = {}
    warnings: list[str] = []
    green_centre = float(np.median(pit_loss.values_by_condition[GREEN]))
    for kind in NeutralizationKind:
        rows = _neutralization_pace_rows(observations, kind)
        if rows.empty:
            continue
        try:
            predicted_lap_times_seconds = tire_regressor.predict(rows)[
                "predicted_lap_time_seconds"
            ].to_numpy(dtype=float)
        except Exception:
            continue
        ratio = float(
            np.median(
                rows["lap_time_seconds"].to_numpy(dtype=float)
                / predicted_lap_times_seconds
            )
        )
        ratio = max(ratio, 1.0)
        direct_pit = pit_loss.values_by_condition.get(kind.value)
        pit_multiplier = (
            float(np.median(direct_pit)) / green_centre
            if direct_pit is not None and green_centre > 0
            else 1.0 / ratio
        )
        if direct_pit is None:
            warnings.append(f"scaled_neutralized_pit_loss:{kind.value}")
        parameters[kind] = NeutralizationAssumptions(
            lap_time_multiplier=ratio,
            pit_loss_multiplier=float(np.clip(pit_multiplier, 0.05, 1.0)),
            restart_gap_seconds=1.0,
        )
    return EmpiricalNeutralizationModel(parameters), tuple(warnings)


def _neutralization_pace_rows(
    observations: pd.DataFrame, kind: NeutralizationKind
) -> pd.DataFrame:
    return observations.loc[
        observations["condition"].eq(kind.value)
        & observations["lap_time_seconds"].notna()
        & observations[list(WEATHER_FEATURES)].notna().all(axis=1)
        & observations["pit_in_time_ns"].isna()
        & observations["pit_out_time_ns"].isna()
        & observations["is_accurate"].eq(True).fillna(False)
        & observations["deleted"].ne(True).fillna(False)
    ].copy()

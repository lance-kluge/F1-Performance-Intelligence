"""Versioned runtime schemas for normalized analytical datasets."""

from __future__ import annotations

import pandas as pd
import pandera.pandas as pa
from pandera.typing import Series

from f1pi.domain import DatasetKind
from f1pi.exceptions import SchemaValidationError

SCHEMA_VERSION = 1


class _BaseSchema(pa.DataFrameModel):
    session_id: Series[str] = pa.Field(nullable=False)

    class Config:
        coerce = True
        strict = False


class SessionSchema(_BaseSchema):
    year: Series[int] = pa.Field(ge=1950)
    round_number: Series[int] = pa.Field(gt=0)
    event_name: Series[str]
    country: Series[str]
    location: Series[str]
    session_type: Series[str]
    session_name: Series[str]
    session_date_utc_ns: Series[pd.Int64Dtype]
    fastf1_version: Series[str]
    schema_version: Series[int] = pa.Field(eq=SCHEMA_VERSION)


class ResultsSchema(_BaseSchema):
    driver_number: Series[str]
    abbreviation: Series[str] = pa.Field(str_length={"min_value": 3, "max_value": 3})
    full_name: Series[str]
    team_name: Series[str]
    position: Series[pd.Int64Dtype] = pa.Field(nullable=True, ge=1)
    grid_position: Series[float] = pa.Field(nullable=True, ge=0)
    status: Series[str] = pa.Field(nullable=True)


class LapsSchema(_BaseSchema):
    driver: Series[str] = pa.Field(str_length={"min_value": 3, "max_value": 3})
    driver_number: Series[str]
    lap_number: Series[float] = pa.Field(ge=1)
    lap_time_ns: Series[pd.Int64Dtype] = pa.Field(nullable=True, gt=0)
    stint: Series[float] = pa.Field(nullable=True, ge=1)
    compound: Series[str] = pa.Field(nullable=True)
    tyre_life: Series[float] = pa.Field(nullable=True, ge=0)
    fresh_tyre: Series[pd.BooleanDtype] = pa.Field(nullable=True)
    is_accurate: Series[pd.BooleanDtype] = pa.Field(nullable=True)


class WeatherSchema(_BaseSchema):
    time_ns: Series[pd.Int64Dtype] = pa.Field(nullable=True, ge=0)
    air_temp: Series[float] = pa.Field(nullable=True)
    track_temp: Series[float] = pa.Field(nullable=True)
    humidity: Series[float] = pa.Field(nullable=True, ge=0, le=100)
    pressure: Series[float] = pa.Field(nullable=True, gt=0)
    rainfall: Series[pd.BooleanDtype] = pa.Field(nullable=True)
    wind_direction: Series[float] = pa.Field(nullable=True, ge=0, le=360)
    wind_speed: Series[float] = pa.Field(nullable=True, ge=0)


class CarTelemetrySchema(_BaseSchema):
    driver: Series[str]
    date_utc_ns: Series[pd.Int64Dtype] = pa.Field(nullable=True)
    session_time_ns: Series[pd.Int64Dtype] = pa.Field(nullable=True, ge=0)
    speed: Series[float] = pa.Field(nullable=True, ge=0)
    rpm: Series[float] = pa.Field(nullable=True, ge=0)
    n_gear: Series[float] = pa.Field(nullable=True, ge=0)
    throttle: Series[float] = pa.Field(nullable=True, ge=0, le=100)
    throttle_raw: Series[float] = pa.Field(nullable=True, ge=0, le=104)
    brake: Series[pd.BooleanDtype] = pa.Field(nullable=True)
    drs: Series[float] = pa.Field(nullable=True, ge=0)


class PositionSchema(_BaseSchema):
    driver: Series[str]
    date_utc_ns: Series[pd.Int64Dtype] = pa.Field(nullable=True)
    session_time_ns: Series[pd.Int64Dtype] = pa.Field(nullable=True, ge=0)
    x: Series[float] = pa.Field(nullable=True)
    y: Series[float] = pa.Field(nullable=True)
    z: Series[float] = pa.Field(nullable=True)
    status: Series[str] = pa.Field(nullable=True)


class TrackStatusSchema(_BaseSchema):
    time_ns: Series[pd.Int64Dtype] = pa.Field(nullable=True, ge=0)
    status: Series[str]
    message: Series[str] = pa.Field(nullable=True)


class SessionStatusSchema(_BaseSchema):
    time_ns: Series[pd.Int64Dtype] = pa.Field(nullable=True, ge=0)
    status: Series[str]


class RaceControlSchema(_BaseSchema):
    message: Series[str]


SCHEMAS: dict[DatasetKind, type[pa.DataFrameModel]] = {
    DatasetKind.SESSION: SessionSchema,
    DatasetKind.RESULTS: ResultsSchema,
    DatasetKind.LAPS: LapsSchema,
    DatasetKind.WEATHER: WeatherSchema,
    DatasetKind.CAR_TELEMETRY: CarTelemetrySchema,
    DatasetKind.POSITION: PositionSchema,
    DatasetKind.TRACK_STATUS: TrackStatusSchema,
    DatasetKind.SESSION_STATUS: SessionStatusSchema,
    DatasetKind.RACE_CONTROL: RaceControlSchema,
}


def validate_frame(kind: DatasetKind, frame: pd.DataFrame) -> pd.DataFrame:
    """Validate and coerce a frame using its versioned schema."""
    try:
        return SCHEMAS[kind].validate(frame, lazy=True)
    except pa.errors.SchemaErrors as error:
        details = error.failure_cases.to_dict(orient="records")
        raise SchemaValidationError(f"{kind.value} failed schema validation: {details}") from error

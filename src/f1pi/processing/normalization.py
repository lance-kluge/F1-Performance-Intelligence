"""Normalization from FastF1-flavored frames to stable platform schemas."""

from __future__ import annotations

import re
from collections.abc import Sequence

import pandas as pd
from pandas.api import types as ptypes

from f1pi.domain.models import DatasetKind, SessionMetadata, SourceDataset, metadata_record
from f1pi.processing.schemas import validate_frame

_STRING_COLUMNS = {
    "session_id",
    "driver",
    "driver_number",
    "abbreviation",
    "full_name",
    "team_name",
    "status",
    "message",
    "compound",
    "source",
    "category",
    "flag",
    "scope",
    "sector",
    "racing_number",
    "broadcast_name",
    "first_name",
    "last_name",
    "headshot_url",
    "country_code",
    "position_text",
    "classified_position",
    "team_color",
}
_BOOLEAN_COLUMNS = {"brake", "rainfall", "fresh_tyre", "is_accurate", "deleted"}


def snake_case(name: object) -> str:
    """Convert FastF1/Pandas labels to stable snake_case names."""
    value = str(name).strip().replace(" ", "_").replace("-", "_")
    value = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", value)
    value = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1_\2", value)
    return re.sub(r"_+", "_", value).strip("_").lower()


def _nullable_nanoseconds(series: pd.Series) -> pd.Series:
    values = series.astype("int64").astype("Int64")
    return values.mask(series.isna())


def normalize_frame(
    kind: DatasetKind,
    frame: pd.DataFrame,
    metadata: SessionMetadata,
    partition: str | None = None,
) -> pd.DataFrame:
    """Normalize one upstream frame and validate it."""
    normalized = frame.copy().reset_index(drop=True)
    normalized.columns = [snake_case(column) for column in normalized.columns]
    normalized.insert(0, "session_id", metadata.session_id)
    if partition is not None:
        if "driver" in normalized:
            normalized["driver"] = partition.upper()
        else:
            normalized.insert(1, "driver", partition.upper())

    renamed: dict[str, str] = {}
    for column in list(normalized.columns):
        series = normalized[column]
        if ptypes.is_timedelta64_dtype(series.dtype):
            renamed[column] = f"{column}_ns"
            normalized[column] = _nullable_nanoseconds(series)
        elif ptypes.is_datetime64_any_dtype(series.dtype):
            utc = pd.to_datetime(series, utc=True, errors="coerce")
            renamed[column] = f"{column}_utc_ns"
            normalized[column] = _nullable_nanoseconds(utc)
    if renamed:
        normalized = normalized.rename(columns=renamed)

    if kind is DatasetKind.CAR_TELEMETRY and "throttle" in normalized:
        throttle_index = list(normalized.columns).index("throttle")
        normalized.insert(
            throttle_index + 1,
            "throttle_raw",
            normalized["throttle"].copy(),
        )
        normalized["throttle"] = normalized["throttle"].mask(
            normalized["throttle"].eq(104)
        )

    for column in normalized.columns.intersection(list(_STRING_COLUMNS)):
        normalized[column] = normalized[column].astype("string")
    for column in normalized.columns.intersection(list(_BOOLEAN_COLUMNS)):
        normalized[column] = normalized[column].astype("boolean")

    return validate_frame(kind, normalized)


def normalize_session(
    metadata: SessionMetadata, datasets: Sequence[SourceDataset]
) -> tuple[SourceDataset, ...]:
    """Add metadata and normalize every dataset in an upstream session."""
    session_date = pd.Timestamp(metadata.session_date_utc)
    session_frame = pd.DataFrame(
        [{**metadata_record(metadata), "session_date_utc_ns": session_date.value}]
    ).drop(columns="session_date_utc")
    output = [
        SourceDataset(
            kind=DatasetKind.SESSION,
            frame=validate_frame(DatasetKind.SESSION, session_frame),
        )
    ]
    output.extend(
        SourceDataset(
            kind=item.kind,
            partition=item.partition,
            frame=normalize_frame(item.kind, item.frame, metadata, item.partition),
        )
        for item in datasets
    )
    return tuple(output)

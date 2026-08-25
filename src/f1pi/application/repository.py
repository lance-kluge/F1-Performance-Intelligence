"""Public read API over the active local dataset snapshot."""

from __future__ import annotations

from typing import cast

import pandas as pd
from pandera.typing import DataFrame

from f1pi.application.ports import Catalog, DatasetReader
from f1pi.domain.exceptions import (
    DatasetNotAvailableError,
    IncompatibleSchemaError,
    SessionNotInStoreError,
    StorageError,
)
from f1pi.domain.models import (
    Artifact,
    CatalogSession,
    DatasetKind,
    SessionKey,
    SessionMetadata,
)
from f1pi.processing.schemas import (
    SCHEMA_VERSION,
    CarTelemetrySchema,
    LapsSchema,
    PositionSchema,
    ResultsSchema,
    TrackStatusSchema,
    WeatherSchema,
    validate_frame,
)


class SessionDataset:
    """Typed access to one immutable local session snapshot."""

    def __init__(
        self,
        session: CatalogSession,
        artifacts: tuple[Artifact, ...],
        store: DatasetReader,
    ) -> None:
        self._session = session
        self._artifacts = artifacts
        self._store = store

    @property
    def metadata(self) -> SessionMetadata:
        return self._session.metadata

    @property
    def run_id(self) -> str:
        return self._session.active_run_id

    def laps(self) -> DataFrame[LapsSchema]:
        return cast(DataFrame[LapsSchema], self._read(DatasetKind.LAPS))

    def results(self) -> DataFrame[ResultsSchema]:
        return cast(DataFrame[ResultsSchema], self._read(DatasetKind.RESULTS))

    def weather(self) -> DataFrame[WeatherSchema]:
        return cast(DataFrame[WeatherSchema], self._read(DatasetKind.WEATHER))

    def track_status(self) -> DataFrame[TrackStatusSchema]:
        return cast(
            DataFrame[TrackStatusSchema], self._read(DatasetKind.TRACK_STATUS)
        )

    def car_telemetry(self, driver: str | None = None) -> DataFrame[CarTelemetrySchema]:
        return cast(
            DataFrame[CarTelemetrySchema], self._read(DatasetKind.CAR_TELEMETRY, driver)
        )

    def position(self, driver: str | None = None) -> DataFrame[PositionSchema]:
        return cast(DataFrame[PositionSchema], self._read(DatasetKind.POSITION, driver))

    def circuit_corners(self) -> pd.DataFrame:
        return self._read(DatasetKind.CIRCUIT_CORNERS)

    def frame(self, kind: DatasetKind, partition: str | None = None) -> pd.DataFrame:
        """Read status, race-control, or session metadata datasets."""
        return self._read(kind, partition)

    def _read(self, kind: DatasetKind, partition: str | None = None) -> pd.DataFrame:
        selected = [artifact for artifact in self._artifacts if artifact.kind is kind]
        if partition is not None:
            selected = [
                artifact
                for artifact in selected
                if artifact.partition and artifact.partition.upper() == partition.upper()
            ]
        if not selected:
            suffix = f" for partition {partition}" if partition else ""
            raise DatasetNotAvailableError(f"{kind.value} is not available{suffix}")
        try:
            frames = [self._store.read_artifact(artifact) for artifact in selected]
        except Exception as error:
            raise StorageError(
                f"failed to read {kind.value} for {self.metadata.session_id}"
            ) from error
        frame = frames[0] if len(frames) == 1 else pd.concat(frames, ignore_index=True)
        return validate_frame(kind, frame)


class SessionRepository:
    """Locate and open the catalog's active session snapshots."""

    def __init__(self, catalog: Catalog, store: DatasetReader) -> None:
        self._catalog = catalog
        self._store = store

    def exists(self, key: SessionKey) -> bool:
        session = self._catalog.find_session(key)
        if session is None or session.metadata.schema_version != SCHEMA_VERSION:
            return False
        artifacts = self._catalog.list_artifacts(session.active_run_id)
        return bool(artifacts) and all(self._store.artifact_exists(item) for item in artifacts)

    def metadata(self, key: SessionKey) -> SessionMetadata:
        session = self._catalog.find_session(key)
        if session is None:
            raise SessionNotInStoreError(f"session is not in the local store: {key.alias_id}")
        return session.metadata

    def open(self, key: SessionKey) -> SessionDataset:
        session = self._catalog.find_session(key)
        if session is None:
            raise SessionNotInStoreError(f"session is not in the local store: {key.alias_id}")
        if session.metadata.schema_version != SCHEMA_VERSION:
            raise IncompatibleSchemaError(
                f"session snapshot uses schema version {session.metadata.schema_version}; "
                f"re-ingest it with schema version {SCHEMA_VERSION}"
            )
        artifacts = self._catalog.list_artifacts(session.active_run_id)
        if not artifacts or not all(self._store.artifact_exists(item) for item in artifacts):
            raise SessionNotInStoreError(
                f"catalog entry is incomplete for session: {session.metadata.session_id}"
            )
        return SessionDataset(session, artifacts, self._store)

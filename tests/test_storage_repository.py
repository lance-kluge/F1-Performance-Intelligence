from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from f1pi.adapters.parquet_store import ParquetDatasetStore
from f1pi.adapters.sqlite_catalog import SQLiteCatalog
from f1pi.domain import Artifact, DatasetKind, SessionKey, SessionMetadata, SourceSession
from f1pi.exceptions import DatasetNotAvailableError, SessionNotInStoreError, StorageError
from f1pi.normalization import normalize_session
from f1pi.repository import SessionRepository


class InMemoryDatasetReader:
    def __init__(self, frames: dict[Path, pd.DataFrame]) -> None:
        self._frames = frames

    def artifact_exists(self, artifact: Artifact) -> bool:
        return artifact.relative_path in self._frames

    def read_artifact(self, artifact: Artifact) -> pd.DataFrame:
        return self._frames[artifact.relative_path]


def test_parquet_catalog_repository_round_trip(
    tmp_path: Path, metadata: SessionMetadata, source_session: SourceSession
) -> None:
    store = ParquetDatasetStore(tmp_path / "processed")
    catalog = SQLiteCatalog(tmp_path / "catalog.sqlite3")
    key = SessionKey(2022, "Bahrain", "R")
    run_id = catalog.begin_run(key)
    artifacts = store.publish(
        run_id, metadata, normalize_session(metadata, source_session.datasets)
    )
    catalog.commit_success(run_id, key, metadata, artifacts)

    repository = SessionRepository(catalog, store)
    assert repository.exists(key)
    assert repository.metadata(key).event_name == "Bahrain Grand Prix"
    session = repository.open(key)
    assert session.run_id == run_id
    assert session.results().iloc[0]["abbreviation"] == "LEC"
    assert len(session.laps()) == 2
    assert len(session.weather()) == 2
    assert len(session.car_telemetry("lec")) == 2
    assert len(session.car_telemetry()) == 2
    assert len(session.position("LEC")) == 2
    assert session.frame(DatasetKind.TRACK_STATUS).iloc[0]["status"] == "1"
    assert all(store.artifact_exists(artifact) for artifact in artifacts)


def test_repository_reports_missing_data(tmp_path: Path) -> None:
    repository = SessionRepository(
        SQLiteCatalog(tmp_path / "catalog.sqlite3"),
        ParquetDatasetStore(tmp_path / "processed"),
    )
    key = SessionKey(2022, "Bahrain", "R")
    assert not repository.exists(key)
    with pytest.raises(SessionNotInStoreError):
        repository.metadata(key)
    with pytest.raises(SessionNotInStoreError):
        repository.open(key)


def test_repository_reads_through_dataset_reader(tmp_path: Path, metadata: SessionMetadata) -> None:
    catalog = SQLiteCatalog(tmp_path / "catalog.sqlite3")
    key = SessionKey(2022, 1, "R")
    run_id = catalog.begin_run(key)
    artifact = Artifact(DatasetKind.RESULTS, Path("results.parquet"), row_count=1)
    catalog.commit_success(run_id, key, metadata, (artifact,))
    reader = InMemoryDatasetReader(
        {
            artifact.relative_path: pd.DataFrame(
                {
                    "session_id": [metadata.session_id],
                    "driver_number": ["16"],
                    "abbreviation": ["LEC"],
                    "full_name": ["Charles Leclerc"],
                    "team_name": ["Ferrari"],
                    "position": [1.0],
                    "grid_position": [2.0],
                    "status": ["Finished"],
                }
            )
        }
    )

    assert SessionRepository(catalog, reader).open(key).results().iloc[0]["abbreviation"] == "LEC"


def test_dataset_reports_unloaded_partition(
    tmp_path: Path, metadata: SessionMetadata, source_session: SourceSession
) -> None:
    store = ParquetDatasetStore(tmp_path / "processed")
    catalog = SQLiteCatalog(tmp_path / "catalog.sqlite3")
    key = SessionKey(2022, 1, "R")
    run_id = catalog.begin_run(key)
    artifacts = store.publish(
        run_id, metadata, normalize_session(metadata, source_session.datasets)
    )
    catalog.commit_success(run_id, key, metadata, artifacts)
    with pytest.raises(DatasetNotAvailableError):
        SessionRepository(catalog, store).open(key).position("VER")


def test_failed_catalog_commit_rolls_back(tmp_path: Path, metadata: SessionMetadata) -> None:
    catalog = SQLiteCatalog(tmp_path / "catalog.sqlite3")
    with pytest.raises(StorageError, match="commit successful"):
        catalog.commit_success("missing-run", SessionKey(2022, 1, "R"), metadata, ())
    assert catalog.get_session(metadata.session_id) is None


def test_store_rejects_duplicate_and_unsafe_runs(
    tmp_path: Path, metadata: SessionMetadata, source_session: SourceSession
) -> None:
    store = ParquetDatasetStore(tmp_path / "processed")
    datasets = normalize_session(metadata, source_session.datasets)
    artifacts = store.publish("same", metadata, datasets)
    with pytest.raises(StorageError, match="already exists"):
        store.publish("same", metadata, datasets)
    store.remove_run(artifacts)
    assert not store.artifact_exists(artifacts[0])


def test_store_rejects_empty_partition(
    tmp_path: Path, metadata: SessionMetadata, source_session: SourceSession
) -> None:
    store = ParquetDatasetStore(tmp_path / "processed")
    telemetry = next(
        item for item in source_session.datasets if item.kind is DatasetKind.CAR_TELEMETRY
    )
    invalid = SourceSession(
        metadata=metadata,
        datasets=(
            type(telemetry)(kind=telemetry.kind, frame=telemetry.frame, partition="!!!"),
        ),
    )
    datasets = normalize_session(metadata, invalid.datasets)
    with pytest.raises(StorageError, match="safe identifier"):
        store.publish("unsafe", metadata, datasets)

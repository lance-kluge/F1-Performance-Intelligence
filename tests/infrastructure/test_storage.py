from pathlib import Path

import pytest

from f1pi.domain.exceptions import StorageError
from f1pi.domain.models import DatasetKind, SessionKey, SessionMetadata, SourceSession
from f1pi.infrastructure.parquet_store import ParquetDatasetStore
from f1pi.infrastructure.sqlite_catalog import SQLiteCatalog
from f1pi.processing.normalization import normalize_session


def test_catalog_read_errors_are_translated(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    catalog = SQLiteCatalog(tmp_path / "catalog.sqlite3")
    monkeypatch.setattr(catalog, "_path", tmp_path)

    with pytest.raises(StorageError, match="find catalog session"):
        catalog.find_session(SessionKey(2022, 1, "R"))
    with pytest.raises(StorageError, match="get catalog session"):
        catalog.get_session("2022-01-bahrain-r")
    with pytest.raises(StorageError, match="list catalog artifacts"):
        catalog.list_artifacts("run")


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

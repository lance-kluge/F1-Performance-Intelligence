from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pandas as pd
import pytest

from f1pi.adapters.parquet_store import ParquetDatasetStore
from f1pi.adapters.sqlite_catalog import SQLiteCatalog
from f1pi.domain import DatasetKind, LoadOptions, SessionKey, SourceDataset, SourceSession
from f1pi.exceptions import SchemaValidationError
from f1pi.ingestion import IngestionService
from f1pi.repository import SessionRepository


class FakeSource:
    def __init__(self, session: SourceSession) -> None:
        self.session = session
        self.calls = 0

    def fetch(self, key: SessionKey, options: LoadOptions) -> SourceSession:
        self.calls += 1
        return self.session


def build_service(tmp_path: Path, source: FakeSource) -> tuple[IngestionService, SessionRepository]:
    catalog = SQLiteCatalog(tmp_path / "catalog.sqlite3")
    store = ParquetDatasetStore(tmp_path / "processed")
    return IngestionService(source, store, catalog), SessionRepository(catalog, store)


def test_ingestion_is_idempotent_and_force_refreshes(
    tmp_path: Path, source_session: SourceSession
) -> None:
    source = FakeSource(source_session)
    service, repository = build_service(tmp_path, source)
    key = SessionKey(2022, "Bahrain", "R")

    first = service.ingest(key)
    second = service.ingest(key)
    forced = service.ingest(key, LoadOptions(force=True))

    assert not first.cache_hit
    assert second.cache_hit
    assert second.run_id == first.run_id
    assert not forced.cache_hit
    assert forced.run_id != first.run_id
    assert source.calls == 2
    assert repository.open(key).run_id == forced.run_id


def test_failed_validation_does_not_publish_session(
    tmp_path: Path, source_session: SourceSession
) -> None:
    broken = replace(
        source_session,
        datasets=(SourceDataset(DatasetKind.LAPS, pd.DataFrame({"Driver": ["LEC"]})),),
    )
    source = FakeSource(broken)
    service, repository = build_service(tmp_path, source)
    key = SessionKey(2022, "Bahrain", "R")
    with pytest.raises(SchemaValidationError):
        service.ingest(key)
    assert not repository.exists(key)


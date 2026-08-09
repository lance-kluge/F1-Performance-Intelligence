from __future__ import annotations

import sqlite3
from contextlib import closing
from dataclasses import replace
from pathlib import Path

import pandas as pd
import pytest

from f1pi.adapters.parquet_store import ParquetDatasetStore
from f1pi.adapters.sqlite_catalog import SQLiteCatalog
from f1pi.domain import DatasetKind, LoadOptions, SessionKey, SourceDataset, SourceSession
from f1pi.exceptions import SchemaValidationError, StorageError
from f1pi.ingestion import IngestionService
from f1pi.repository import SessionRepository


class FakeSource:
    def __init__(self, session: SourceSession) -> None:
        self.session = session
        self.calls = 0
        self.options: list[LoadOptions] = []

    def fetch(self, key: SessionKey, options: LoadOptions) -> SourceSession:
        self.calls += 1
        self.options.append(options)
        excluded = set()
        if not options.telemetry:
            excluded.update({DatasetKind.CAR_TELEMETRY, DatasetKind.POSITION})
        if not options.weather:
            excluded.add(DatasetKind.WEATHER)
        if not options.messages:
            excluded.add(DatasetKind.RACE_CONTROL)
        return replace(
            self.session,
            datasets=tuple(
                dataset for dataset in self.session.datasets if dataset.kind not in excluded
            ),
        )


def _raise_catalog_commit_error(*args: object, **kwargs: object) -> None:
    raise StorageError("catalog commit failed")


def _raise_cleanup_error(*args: object, **kwargs: object) -> None:
    raise OSError("cleanup failed")


def build_service(tmp_path: Path, source: FakeSource) -> tuple[IngestionService, SessionRepository]:
    catalog = SQLiteCatalog(tmp_path / "catalog.sqlite3")
    store = ParquetDatasetStore(tmp_path / "processed")
    return IngestionService(source, store, catalog), SessionRepository(catalog, store)


def test_ingestion_reuses_snapshot_and_can_rebuild_it(
    tmp_path: Path, source_session: SourceSession
) -> None:
    source = FakeSource(source_session)
    service, repository = build_service(tmp_path, source)
    key = SessionKey(2022, "Bahrain", "R")

    first = service.ingest(key)
    second = service.ingest(key)
    rebuilt = service.ingest(key, LoadOptions(rebuild_snapshot=True))

    assert not first.snapshot_reused
    assert second.snapshot_reused
    assert second.run_id == first.run_id
    assert not rebuilt.snapshot_reused
    assert rebuilt.run_id != first.run_id
    assert source.calls == 2
    assert source.options[-1].rebuild_snapshot
    assert not source.options[-1].refresh_upstream
    assert repository.open(key).run_id == rebuilt.run_id


def test_refresh_upstream_also_bypasses_existing_snapshot(
    tmp_path: Path, source_session: SourceSession
) -> None:
    source = FakeSource(source_session)
    service, repository = build_service(tmp_path, source)
    key = SessionKey(2022, "Bahrain", "R")

    first = service.ingest(key)
    refreshed = service.ingest(key, LoadOptions(refresh_upstream=True))

    assert not refreshed.snapshot_reused
    assert refreshed.run_id != first.run_id
    assert source.calls == 2
    assert source.options[-1].refresh_upstream
    assert repository.open(key).run_id == refreshed.run_id


@pytest.mark.parametrize(
    ("partial_options", "required_kind"),
    [
        (LoadOptions(telemetry=False), DatasetKind.CAR_TELEMETRY),
        (LoadOptions(weather=False), DatasetKind.WEATHER),
        (LoadOptions(messages=False), DatasetKind.RACE_CONTROL),
    ],
)
def test_default_ingest_upgrades_partial_snapshot(
    tmp_path: Path,
    source_session: SourceSession,
    partial_options: LoadOptions,
    required_kind: DatasetKind,
) -> None:
    source = FakeSource(source_session)
    service, _ = build_service(tmp_path, source)
    key = SessionKey(2022, "Bahrain", "R")

    partial = service.ingest(key, partial_options)
    repeated_partial = service.ingest(key, partial_options)
    upgraded = service.ingest(key)
    repeated_full = service.ingest(key)

    assert not partial.snapshot_reused
    assert repeated_partial.snapshot_reused
    assert repeated_partial.run_id == partial.run_id
    assert not upgraded.snapshot_reused
    assert upgraded.run_id != partial.run_id
    assert required_kind in {artifact.kind for artifact in upgraded.artifacts}
    assert repeated_full.snapshot_reused
    assert repeated_full.run_id == upgraded.run_id
    assert source.calls == 2


def test_full_snapshot_satisfies_partial_request(
    tmp_path: Path, source_session: SourceSession
) -> None:
    source = FakeSource(source_session)
    service, _ = build_service(tmp_path, source)
    key = SessionKey(2022, "Bahrain", "R")

    full = service.ingest(key)
    partial = service.ingest(
        key, LoadOptions(telemetry=False, weather=False, messages=False)
    )

    assert partial.snapshot_reused
    assert partial.run_id == full.run_id
    assert source.calls == 1


def test_ingestion_refreshes_snapshot_from_previous_schema_version(
    tmp_path: Path, source_session: SourceSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = FakeSource(source_session)
    service, _ = build_service(tmp_path, source)
    key = SessionKey(2022, "Bahrain", "R")

    first = service.ingest(key)
    monkeypatch.setattr("f1pi.ingestion.SCHEMA_VERSION", source_session.metadata.schema_version + 1)
    refreshed = service.ingest(key)

    assert not first.snapshot_reused
    assert not refreshed.snapshot_reused
    assert refreshed.run_id != first.run_id
    assert source.calls == 2


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


def test_catalog_records_failure_when_artifact_cleanup_fails(
    tmp_path: Path, source_session: SourceSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    catalog = SQLiteCatalog(tmp_path / "catalog.sqlite3")
    store = ParquetDatasetStore(tmp_path / "processed")
    service = IngestionService(FakeSource(source_session), store, catalog)
    monkeypatch.setattr(catalog, "commit_success", _raise_catalog_commit_error)
    monkeypatch.setattr(store, "remove_run", _raise_cleanup_error)

    with pytest.raises(StorageError, match="catalog commit failed"):
        service.ingest(SessionKey(2022, "Bahrain", "R"))

    with closing(sqlite3.connect(tmp_path / "catalog.sqlite3")) as connection:
        status = connection.execute("SELECT status FROM ingestion_runs").fetchone()[0]
    assert status == "failed"

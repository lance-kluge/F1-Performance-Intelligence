"""Application service coordinating ingestion as one transaction-like workflow."""

from __future__ import annotations

import logging
from dataclasses import replace
from time import monotonic

from f1pi.application.ports import Catalog, DatasetStore, SessionSource
from f1pi.domain.models import DatasetKind, IngestionResult, LoadOptions, SessionKey
from f1pi.infrastructure.logging import log_event
from f1pi.processing.normalization import normalize_session
from f1pi.processing.schemas import SCHEMA_VERSION


class IngestionService:
    def __init__(self, source: SessionSource, store: DatasetStore, catalog: Catalog) -> None:
        self._source = source
        self._store = store
        self._catalog = catalog
        self._logger = logging.getLogger("f1pi.ingestion")

    def ingest(
        self, key: SessionKey, options: LoadOptions | None = None
    ) -> IngestionResult:
        options = options or LoadOptions()
        cached = self._catalog.find_session(key)
        if cached is not None and not options.requires_ingestion:
            artifacts = self._catalog.list_artifacts(cached.active_run_id)
            artifact_kinds = {artifact.kind for artifact in artifacts}
            has_required_datasets = options.required_dataset_kinds() <= artifact_kinds
            has_current_schema = cached.metadata.schema_version == SCHEMA_VERSION
            artifacts_exist = all(self._store.artifact_exists(item) for item in artifacts)
            if (
                artifacts
                and has_required_datasets
                and has_current_schema
                and artifacts_exist
            ):
                log_event(
                    self._logger,
                    logging.INFO,
                    "session snapshot reused",
                    session_id=cached.metadata.session_id,
                    run_id=cached.active_run_id,
                    snapshot_reused=True,
                )
                return IngestionResult(
                    session_id=cached.metadata.session_id,
                    run_id=cached.active_run_id,
                    snapshot_reused=True,
                    artifacts=artifacts,
                )
            if artifacts and has_current_schema and artifacts_exist:
                options = _preserve_existing_datasets(options, artifact_kinds)

        run_id = self._catalog.begin_run(key)
        started = monotonic()
        artifacts = ()
        try:
            source_session = self._source.fetch(key, options)
            datasets = normalize_session(source_session.metadata, source_session.datasets)
            artifacts = self._store.publish(run_id, source_session.metadata, datasets)
            self._catalog.commit_success(
                run_id, key, source_session.metadata, artifacts
            )
        except Exception as error:
            if artifacts:
                try:
                    self._store.remove_run(artifacts)
                except Exception as cleanup_error:
                    log_event(
                        self._logger,
                        logging.ERROR,
                        "ingestion artifact cleanup failed",
                        run_id=run_id,
                        error_type=type(cleanup_error).__name__,
                    )
            try:
                self._catalog.fail_run(run_id, error)
            except Exception as catalog_error:
                raise error from catalog_error
            log_event(
                self._logger,
                logging.ERROR,
                "session ingestion failed",
                run_id=run_id,
                requested_session=key.alias_id,
                elapsed_seconds=round(monotonic() - started, 3),
                error_type=type(error).__name__,
            )
            raise
        log_event(
            self._logger,
            logging.INFO,
            "session ingestion succeeded",
            session_id=source_session.metadata.session_id,
            run_id=run_id,
            snapshot_reused=False,
            elapsed_seconds=round(monotonic() - started, 3),
            artifact_count=len(artifacts),
            row_count=sum(item.row_count for item in artifacts),
        )
        return IngestionResult(
            session_id=source_session.metadata.session_id,
            run_id=run_id,
            snapshot_reused=False,
            artifacts=artifacts,
        )


def _preserve_existing_datasets(
    options: LoadOptions,
    artifact_kinds: set[DatasetKind],
) -> LoadOptions:
    """Keep optional capabilities when a partial snapshot must be upgraded."""
    has_telemetry = {
        DatasetKind.CAR_TELEMETRY,
        DatasetKind.POSITION,
    } <= artifact_kinds
    return replace(
        options,
        telemetry=options.telemetry or has_telemetry,
        weather=options.weather or DatasetKind.WEATHER in artifact_kinds,
        messages=options.messages or DatasetKind.RACE_CONTROL in artifact_kinds,
    )

"""Explicit construction of the local platform."""

from __future__ import annotations

from dataclasses import dataclass

from f1pi.application.ingestion import IngestionService
from f1pi.application.lap_analysis import LapAnalysisService
from f1pi.application.repository import SessionRepository
from f1pi.config import PlatformSettings
from f1pi.infrastructure.fastf1_client import FastF1Client
from f1pi.infrastructure.logging import configure_logging
from f1pi.infrastructure.parquet_store import ParquetDatasetStore
from f1pi.infrastructure.sqlite_catalog import SQLiteCatalog


@dataclass(frozen=True, slots=True)
class Platform:
    fastf1: FastF1Client
    ingestion: IngestionService
    sessions: SessionRepository
    lap_analysis: LapAnalysisService


def build_platform(settings: PlatformSettings | None = None) -> Platform:
    """Wire concrete adapters into the public platform services."""
    settings = settings or PlatformSettings.from_env()
    configure_logging(settings.log_level)
    catalog = SQLiteCatalog(settings.catalog_path)
    store = ParquetDatasetStore(settings.processed_dir)
    fastf1_client = FastF1Client(settings.fastf1_cache_dir)
    sessions = SessionRepository(catalog, store)
    return Platform(
        fastf1=fastf1_client,
        ingestion=IngestionService(fastf1_client, store, catalog),
        sessions=sessions,
        lap_analysis=LapAnalysisService(sessions),
    )

"""Protocols for external data and persistence boundaries."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Protocol

import pandas as pd

from f1pi.domain.models import (
    Artifact,
    CatalogSession,
    LoadOptions,
    ScheduledEvent,
    SessionKey,
    SessionMetadata,
    SourceDataset,
    SourceSession,
)


class SessionSource(Protocol):
    def fetch(self, key: SessionKey, options: LoadOptions) -> SourceSession: ...


class EventScheduleSource(Protocol):
    def events(self, year: int) -> tuple[ScheduledEvent, ...]: ...


class DatasetStore(Protocol):
    @property
    def root(self) -> Path: ...

    def publish(
        self,
        run_id: str,
        metadata: SessionMetadata,
        datasets: Sequence[SourceDataset],
    ) -> tuple[Artifact, ...]: ...

    def remove_run(self, artifacts: Sequence[Artifact]) -> None: ...

    def artifact_exists(self, artifact: Artifact) -> bool: ...


class DatasetReader(Protocol):
    """Read persisted artifacts without coupling callers to a storage adapter."""

    def artifact_exists(self, artifact: Artifact) -> bool: ...

    def read_artifact(self, artifact: Artifact) -> pd.DataFrame: ...


class Catalog(Protocol):
    def find_session(self, key: SessionKey) -> CatalogSession | None: ...

    def get_session(self, session_id: str) -> CatalogSession | None: ...

    def list_artifacts(self, run_id: str) -> tuple[Artifact, ...]: ...

    def begin_run(self, key: SessionKey) -> str: ...

    def commit_success(
        self,
        run_id: str,
        key: SessionKey,
        metadata: SessionMetadata,
        artifacts: Sequence[Artifact],
    ) -> None: ...

    def fail_run(self, run_id: str, error: Exception) -> None: ...

"""Immutable, atomic Parquet snapshot storage."""

from __future__ import annotations

import re
import shutil
from collections.abc import Sequence
from pathlib import Path

import pandas as pd

from f1pi.domain import Artifact, SessionMetadata, SourceDataset
from f1pi.exceptions import StorageError


class ParquetDatasetStore:
    """Publish complete ingestion runs as immutable directory snapshots."""

    def __init__(self, root: Path) -> None:
        self._root = root.resolve()

    @property
    def root(self) -> Path:
        return self._root

    def publish(
        self,
        run_id: str,
        metadata: SessionMetadata,
        datasets: Sequence[SourceDataset],
    ) -> tuple[Artifact, ...]:
        staging = self._root / ".staging" / run_id
        relative_run = Path(
            f"schema_version={metadata.schema_version}",
            f"year={metadata.year}",
            f"round={metadata.round_number:02d}",
            f"session={metadata.session_type.value.lower()}",
            f"run={run_id}",
        )
        target = self._root / relative_run
        if staging.exists() or target.exists():
            raise StorageError(f"run path already exists: {run_id}")

        artifacts: list[Artifact] = []
        try:
            staging.mkdir(parents=True, exist_ok=False)
            for dataset in datasets:
                partition = _safe_partition(dataset.partition) if dataset.partition else None
                relative_file = Path(dataset.kind.value)
                if partition:
                    relative_file /= f"driver={partition}"
                relative_file /= "data.parquet"
                staged_file = staging / relative_file
                staged_file.parent.mkdir(parents=True, exist_ok=True)
                dataset.frame.to_parquet(staged_file, engine="pyarrow", index=False)
                artifacts.append(
                    Artifact(
                        kind=dataset.kind,
                        relative_path=relative_run / relative_file,
                        row_count=len(dataset.frame),
                        partition=dataset.partition.upper() if dataset.partition else None,
                    )
                )
            target.parent.mkdir(parents=True, exist_ok=True)
            staging.rename(target)
        except Exception as error:
            if staging.exists():
                shutil.rmtree(staging)
            raise StorageError(f"failed to publish Parquet run {run_id}: {error}") from error
        return tuple(artifacts)

    def remove_run(self, artifacts: Sequence[Artifact]) -> None:
        if not artifacts:
            return
        path = self._run_path(artifacts[0])
        try:
            if path.exists():
                shutil.rmtree(path)
        except OSError as error:
            raise StorageError(f"failed to remove unpublished run at {path}") from error

    def artifact_exists(self, artifact: Artifact) -> bool:
        path = (self._root / artifact.relative_path).resolve()
        return path.is_relative_to(self._root) and path.is_file()

    def absolute_path(self, artifact: Artifact) -> Path:
        path = (self._root / artifact.relative_path).resolve()
        if not path.is_relative_to(self._root):
            raise StorageError(f"artifact escaped storage root: {artifact.relative_path}")
        return path

    def read_artifact(self, artifact: Artifact) -> pd.DataFrame:
        return pd.read_parquet(self.absolute_path(artifact))

    def _run_path(self, artifact: Artifact) -> Path:
        parts = artifact.relative_path.parts
        run_index = next(
            (index for index, part in enumerate(parts) if part.startswith("run=")), None
        )
        if run_index is None:
            raise StorageError(f"artifact path does not identify a run: {artifact.relative_path}")
        path = (self._root / Path(*parts[: run_index + 1])).resolve()
        if not path.is_relative_to(self._root):
            raise StorageError(f"run path escaped storage root: {path}")
        return path


def _safe_partition(value: str) -> str:
    partition = re.sub(r"[^A-Za-z0-9_-]", "-", value.strip()).strip("-")
    if not partition:
        raise StorageError("partition must contain a safe identifier")
    return partition.upper()

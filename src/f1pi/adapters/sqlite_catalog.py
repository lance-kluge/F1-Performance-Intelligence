"""SQLite metadata catalog."""

from __future__ import annotations

import sqlite3
import uuid
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

from f1pi.domain import (
    Artifact,
    CatalogSession,
    DatasetKind,
    SessionKey,
    SessionMetadata,
    SessionType,
)
from f1pi.exceptions import StorageError


class SQLiteCatalog:
    """Track successful snapshots and ingestion history transactionally."""

    def __init__(self, path: Path) -> None:
        self._path = path.resolve()
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def find_session(self, key: SessionKey) -> CatalogSession | None:
        query = """
            SELECT s.* FROM session_aliases a
            JOIN sessions s ON s.session_id = a.session_id
            WHERE a.alias_id = ?
        """
        try:
            with self._connection() as connection:
                row = connection.execute(query, (key.alias_id,)).fetchone()
        except sqlite3.Error as error:
            raise StorageError("failed to find catalog session") from error
        return _catalog_session(row) if row else None

    def get_session(self, session_id: str) -> CatalogSession | None:
        try:
            with self._connection() as connection:
                row = connection.execute(
                    "SELECT * FROM sessions WHERE session_id = ?", (session_id,)
                ).fetchone()
        except sqlite3.Error as error:
            raise StorageError("failed to get catalog session") from error
        return _catalog_session(row) if row else None

    def list_artifacts(self, run_id: str) -> tuple[Artifact, ...]:
        try:
            with self._connection() as connection:
                rows = connection.execute(
                    """
                    SELECT dataset_kind, relative_path, row_count, partition_key
                    FROM artifacts WHERE run_id = ?
                    ORDER BY dataset_kind, partition_key
                    """,
                    (run_id,),
                ).fetchall()
        except sqlite3.Error as error:
            raise StorageError("failed to list catalog artifacts") from error
        return tuple(
            Artifact(
                kind=DatasetKind(row["dataset_kind"]),
                relative_path=Path(row["relative_path"]),
                row_count=int(row["row_count"]),
                partition=row["partition_key"],
            )
            for row in rows
        )

    def begin_run(self, key: SessionKey) -> str:
        run_id = uuid.uuid4().hex
        now = _utc_now()
        try:
            with self._connection() as connection:
                connection.execute(
                    """
                    INSERT INTO ingestion_runs (
                        run_id, requested_alias, status, started_at
                    ) VALUES (?, ?, 'running', ?)
                    """,
                    (run_id, key.alias_id, now),
                )
        except sqlite3.Error as error:
            raise StorageError("failed to begin ingestion run") from error
        return run_id

    def commit_success(
        self,
        run_id: str,
        key: SessionKey,
        metadata: SessionMetadata,
        artifacts: Sequence[Artifact],
    ) -> None:
        completed_at = _utc_now()
        values = (
            metadata.session_id,
            metadata.year,
            metadata.round_number,
            metadata.event_name,
            metadata.country,
            metadata.location,
            metadata.session_type.value,
            metadata.session_name,
            metadata.session_date_utc.astimezone(UTC).isoformat(),
            metadata.fastf1_version,
            metadata.schema_version,
            run_id,
            completed_at,
        )
        try:
            with self._connection() as connection:
                connection.execute(
                    """
                    INSERT INTO sessions (
                        session_id, year, round_number, event_name, country, location,
                        session_type, session_name, session_date_utc, fastf1_version,
                        schema_version, active_run_id, ingested_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(session_id) DO UPDATE SET
                        event_name=excluded.event_name,
                        country=excluded.country,
                        location=excluded.location,
                        session_name=excluded.session_name,
                        session_date_utc=excluded.session_date_utc,
                        fastf1_version=excluded.fastf1_version,
                        schema_version=excluded.schema_version,
                        active_run_id=excluded.active_run_id,
                        ingested_at=excluded.ingested_at
                    """,
                    values,
                )
                connection.execute(
                    """
                    INSERT INTO session_aliases (alias_id, session_id)
                    VALUES (?, ?)
                    ON CONFLICT(alias_id) DO UPDATE SET session_id=excluded.session_id
                    """,
                    (key.alias_id, metadata.session_id),
                )
                connection.executemany(
                    """
                    INSERT INTO artifacts (
                        run_id, dataset_kind, partition_key, relative_path, row_count
                    ) VALUES (?, ?, ?, ?, ?)
                    """,
                    [
                        (
                            run_id,
                            artifact.kind.value,
                            artifact.partition,
                            artifact.relative_path.as_posix(),
                            artifact.row_count,
                        )
                        for artifact in artifacts
                    ],
                )
                cursor = connection.execute(
                    """
                    UPDATE ingestion_runs
                    SET session_id=?, status='succeeded', completed_at=?
                    WHERE run_id=? AND status='running'
                    """,
                    (metadata.session_id, completed_at, run_id),
                )
                if cursor.rowcount != 1:
                    raise sqlite3.IntegrityError(f"run is not active: {run_id}")
        except sqlite3.Error as error:
            raise StorageError("failed to commit successful ingestion") from error

    def fail_run(self, run_id: str, error: Exception) -> None:
        try:
            with self._connection() as connection:
                connection.execute(
                    """
                    UPDATE ingestion_runs
                    SET status='failed', completed_at=?, error_type=?, error_message=?
                    WHERE run_id=? AND status='running'
                    """,
                    (_utc_now(), type(error).__name__, str(error)[:4000], run_id),
                )
        except sqlite3.Error as catalog_error:
            raise StorageError("failed to record ingestion failure") from catalog_error

    def _initialize(self) -> None:
        ddl = """
            CREATE TABLE IF NOT EXISTS sessions (
                session_id TEXT PRIMARY KEY,
                year INTEGER NOT NULL,
                round_number INTEGER NOT NULL,
                event_name TEXT NOT NULL,
                country TEXT NOT NULL,
                location TEXT NOT NULL,
                session_type TEXT NOT NULL,
                session_name TEXT NOT NULL,
                session_date_utc TEXT NOT NULL,
                fastf1_version TEXT NOT NULL,
                schema_version INTEGER NOT NULL,
                active_run_id TEXT NOT NULL,
                ingested_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS session_aliases (
                alias_id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL REFERENCES sessions(session_id)
            );
            CREATE TABLE IF NOT EXISTS ingestion_runs (
                run_id TEXT PRIMARY KEY,
                requested_alias TEXT NOT NULL,
                session_id TEXT,
                status TEXT NOT NULL CHECK(status IN ('running', 'succeeded', 'failed')),
                started_at TEXT NOT NULL,
                completed_at TEXT,
                error_type TEXT,
                error_message TEXT
            );
            CREATE TABLE IF NOT EXISTS artifacts (
                artifact_id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id TEXT NOT NULL REFERENCES ingestion_runs(run_id),
                dataset_kind TEXT NOT NULL,
                partition_key TEXT,
                relative_path TEXT NOT NULL UNIQUE,
                row_count INTEGER NOT NULL CHECK(row_count >= 0)
            );
            CREATE INDEX IF NOT EXISTS artifacts_run_idx ON artifacts(run_id);
        """
        try:
            with self._connection() as connection:
                connection.executescript(ddl)
        except sqlite3.Error as error:
            raise StorageError(f"failed to initialize catalog at {self._path}") from error

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self._path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        try:
            with connection:
                yield connection
        finally:
            connection.close()


def _catalog_session(row: sqlite3.Row) -> CatalogSession:
    metadata = SessionMetadata(
        session_id=row["session_id"],
        year=int(row["year"]),
        round_number=int(row["round_number"]),
        event_name=row["event_name"],
        country=row["country"],
        location=row["location"],
        session_type=SessionType.parse(row["session_type"]),
        session_name=row["session_name"],
        session_date_utc=datetime.fromisoformat(row["session_date_utc"]),
        fastf1_version=row["fastf1_version"],
        schema_version=int(row["schema_version"]),
    )
    return CatalogSession(
        metadata=metadata,
        active_run_id=row["active_run_id"],
        ingested_at=datetime.fromisoformat(row["ingested_at"]),
    )


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()

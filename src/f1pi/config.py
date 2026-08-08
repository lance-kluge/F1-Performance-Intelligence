"""Application configuration."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class PlatformSettings:
    """Filesystem and logging settings for the local platform."""

    data_dir: Path
    fastf1_cache_dir: Path
    log_level: str = "INFO"

    @classmethod
    def from_env(cls, base_dir: Path | None = None) -> PlatformSettings:
        """Build settings from environment variables with local defaults."""
        root = (base_dir or Path.cwd()).resolve()
        data_dir = Path(os.getenv("F1PI_DATA_DIR", root / "data")).expanduser().resolve()
        cache_dir = Path(
            os.getenv("F1PI_FASTF1_CACHE_DIR", data_dir / "cache" / "fastf1")
        ).expanduser().resolve()
        return cls(
            data_dir=data_dir,
            fastf1_cache_dir=cache_dir,
            log_level=os.getenv("F1PI_LOG_LEVEL", "INFO").upper(),
        )

    @property
    def processed_dir(self) -> Path:
        return self.data_dir / "processed"

    @property
    def catalog_path(self) -> Path:
        return self.data_dir / "catalog.sqlite3"


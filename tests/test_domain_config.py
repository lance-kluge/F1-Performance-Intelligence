from __future__ import annotations

from datetime import UTC
from pathlib import Path

import pytest

from f1pi.config import PlatformSettings
from f1pi.domain import SessionKey, SessionMetadata, SessionType, metadata_record


def test_session_key_normalizes_aliases() -> None:
    assert SessionKey(2022, " Bahrain Grand Prix ", "race").alias_id == (
        "2022:bahrain-grand-prix:r"
    )
    assert SessionKey(2022, 1, SessionType.RACE).alias_id == "2022:1:r"
    assert SessionType.parse("qualifying") is SessionType.QUALIFYING


def test_session_key_accepts_inaugural_championship_year() -> None:
    assert SessionKey(1950, 1, "R").year == 1950


def test_session_key_rejects_zero_based_round_number() -> None:
    with pytest.raises(ValueError, match="round number must be 1 or greater"):
        SessionKey(2022, 0, "R")


@pytest.mark.parametrize("year,event", [(1949, 1), (2022, "  ")])
def test_session_key_rejects_invalid_values(year: int, event: int | str) -> None:
    with pytest.raises(ValueError):
        SessionKey(year, event, "R")


def test_settings_use_environment(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("F1PI_DATA_DIR", str(tmp_path / "custom"))
    monkeypatch.setenv("F1PI_FASTF1_CACHE_DIR", str(tmp_path / "raw"))
    monkeypatch.setenv("F1PI_LOG_LEVEL", "debug")
    settings = PlatformSettings.from_env(tmp_path)
    assert settings.data_dir == (tmp_path / "custom").resolve()
    assert settings.fastf1_cache_dir == (tmp_path / "raw").resolve()
    assert settings.log_level == "DEBUG"
    assert settings.catalog_path.name == "catalog.sqlite3"


def test_metadata_makes_naive_time_utc(metadata: SessionMetadata) -> None:
    naive = SessionMetadata(
        session_id=metadata.session_id,
        year=metadata.year,
        round_number=metadata.round_number,
        event_name=metadata.event_name,
        country=metadata.country,
        location=metadata.location,
        session_type=metadata.session_type,
        session_name=metadata.session_name,
        session_date_utc=metadata.session_date_utc.replace(tzinfo=None),
        fastf1_version=metadata.fastf1_version,
    )
    assert naive.session_date_utc.tzinfo is UTC
    assert metadata_record(naive)["schema_version"] == 1

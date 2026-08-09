from pathlib import Path

import pytest

from f1pi.config import PlatformSettings


def test_settings_use_environment(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("F1PI_DATA_DIR", str(tmp_path / "custom"))
    monkeypatch.setenv("F1PI_FASTF1_CACHE_DIR", str(tmp_path / "raw"))
    monkeypatch.setenv("F1PI_LOG_LEVEL", "debug")
    settings = PlatformSettings.from_env(tmp_path)
    assert settings.data_dir == (tmp_path / "custom").resolve()
    assert settings.fastf1_cache_dir == (tmp_path / "raw").resolve()
    assert settings.log_level == "DEBUG"
    assert settings.catalog_path.name == "catalog.sqlite3"
